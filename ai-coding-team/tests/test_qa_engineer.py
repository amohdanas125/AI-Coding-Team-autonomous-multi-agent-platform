"""Tests for the real QA Engineer agent (agents/qa_engineer.py).

Unlike every other agent in this project, QA Engineer doesn't just call
an LLM - it actually runs code (npm install, an in-memory MongoDB, Jest)
in a sandboxed temp directory. These tests mock BOTH layers: the LLM call
(gemini_client.call_agent, via agents.qa_engineer.call_agent) and the
subprocess layer (agents.qa_engineer._run_subprocess,
agents.qa_engineer.shutil.which), so they run without network access, an
API key, Node, or npm - they verify the ORCHESTRATION (right number of
LLM calls, jest output correctly parsed into QA_REPORT_SCHEMA shape,
npm-install-failure and bad-jest-output handled without crashing), not
that the live API generates correct tests or that real jest/npm/mongo
actually work together. For that, run scripts/test_qa_agent.py yourself
with a real GROQ_API_KEY - it could not be run from the sandbox that
built this (no network access to api.groq.com there, and no network
access to mongodb-memory-server's binary download host either).
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import QA_ENTITY_TEST_SCHEMA, QA_REPORT_SCHEMA, validate_payload

TWO_ENTITY_SPEC = {
    "app_name": "StubApp",
    "app_description": "A minimal two-entity spec for testing.",
    "auth_required": True,
    "entities": [
        {"name": "User", "fields": [
            {"name": "email", "type": "string", "required": True, "references_entity": None},
            {"name": "password", "type": "string", "required": True, "references_entity": None},
        ]},
        {"name": "Item", "fields": [
            {"name": "title", "type": "string", "required": True, "references_entity": None},
        ]},
    ],
    "relationships": [],
    "endpoints": [
        {"method": "POST", "path": "/auth/register", "description": "register",
         "entity": "User", "requires_auth": False},
        {"method": "POST", "path": "/auth/login", "description": "login",
         "entity": "User", "requires_auth": False},
        {"method": "GET", "path": "/items", "description": "list items",
         "entity": "Item", "requires_auth": False},
    ],
    "pages": [],
}

BACKEND_OUTPUT = {
    "files": [{"path": "package.json", "content": json.dumps({"name": "stub", "dependencies": {}})}],
    "api_contract": [
        {"method": "POST", "path": "/auth/register", "request_body_fields": [], "response_shape_fields": [], "requires_auth": False},
        {"method": "POST", "path": "/auth/login", "request_body_fields": [], "response_shape_fields": ["token"], "requires_auth": False},
        {"method": "GET", "path": "/items", "request_body_fields": [], "response_shape_fields": ["_id", "title"], "requires_auth": False},
    ],
    "setup_notes": "",
}

FAKE_TEST_FILE_OUTPUT = {
    "files": [{"path": "tests/stub.test.js", "content": "// fake test"}],
}


def test_fake_test_file_output_is_schema_valid():
    validate_payload(FAKE_TEST_FILE_OUTPUT, QA_ENTITY_TEST_SCHEMA)


# --- Pure Python logic, no mocking needed ---

def test_find_auth_endpoints_extracts_required_fields():
    from agents.qa_engineer import _find_auth_endpoints

    result = _find_auth_endpoints(TWO_ENTITY_SPEC)

    assert result == {
        "register_path": "/auth/register",
        "login_path": "/auth/login",
        "required_fields": ["email", "password"],
    }


def test_find_auth_endpoints_returns_none_when_app_has_no_auth():
    from agents.qa_engineer import _find_auth_endpoints

    no_auth_spec = dict(TWO_ENTITY_SPEC)
    no_auth_spec["endpoints"] = [TWO_ENTITY_SPEC["endpoints"][2]]  # just the GET /items

    assert _find_auth_endpoints(no_auth_spec) is None


def test_relevant_endpoints_for_entity_filters_correctly():
    from agents.qa_engineer import _relevant_endpoints_for_entity

    result = _relevant_endpoints_for_entity("Item", BACKEND_OUTPUT["api_contract"], TWO_ENTITY_SPEC["endpoints"])

    assert [ep["path"] for ep in result] == ["/items"]


def test_parse_jest_results_extracts_only_failures():
    from agents.qa_engineer import _parse_jest_results

    jest_json = {
        "testResults": [{
            "assertionResults": [
                {"title": "passes", "fullName": "Item passes", "status": "passed", "failureMessages": []},
                {"title": "fails", "fullName": "Item fails", "status": "failed",
                 "failureMessages": ["Expected: 200\nReceived: 500"]},
            ]
        }]
    }

    failures = _parse_jest_results(jest_json)

    assert len(failures) == 1
    assert failures[0]["test_name"] == "Item fails"
    assert "500" in failures[0]["error_log"]


def test_parse_jest_results_empty_when_everything_passes():
    from agents.qa_engineer import _parse_jest_results

    jest_json = {"testResults": [{"assertionResults": [
        {"title": "passes", "fullName": "Item passes", "status": "passed", "failureMessages": []},
    ]}]}

    assert _parse_jest_results(jest_json) == []


# --- generate_qa_report orchestration - mocks the LLM call AND the
# subprocess layer, so these run with no network, no API key, no Node. ---

def _mock_which(name):
    return f"/usr/bin/{name}"


@patch("agents.qa_engineer.shutil.which", side_effect=_mock_which)
@patch("agents.qa_engineer._run_subprocess")
@patch("agents.qa_engineer.call_agent")
def test_generate_qa_report_all_passing(mock_call_agent, mock_subprocess, mock_which):
    mock_call_agent.return_value = FAKE_TEST_FILE_OUTPUT
    mock_subprocess.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),  # npm install
        MagicMock(returncode=0, stdout=json.dumps({"testResults": []}), stderr=""),  # jest
    ]

    from agents.qa_engineer import generate_qa_report
    result = generate_qa_report(TWO_ENTITY_SPEC, BACKEND_OUTPUT)

    validate_payload(result, QA_REPORT_SCHEMA)
    assert result["all_tests_passed"] is True
    assert result["failures"] == []
    # one call per entity that actually has endpoints (both do here)
    assert mock_call_agent.call_count == 2


@patch("agents.qa_engineer.shutil.which", side_effect=_mock_which)
@patch("agents.qa_engineer._run_subprocess")
@patch("agents.qa_engineer.call_agent")
def test_generate_qa_report_with_real_test_failures(mock_call_agent, mock_subprocess, mock_which):
    mock_call_agent.return_value = FAKE_TEST_FILE_OUTPUT
    jest_output = {
        "testResults": [{
            "assertionResults": [
                {"title": "x", "fullName": "Item x", "status": "failed", "failureMessages": ["boom"]},
            ]
        }]
    }
    mock_subprocess.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),
        MagicMock(returncode=0, stdout=json.dumps(jest_output), stderr=""),
    ]

    from agents.qa_engineer import generate_qa_report
    result = generate_qa_report(TWO_ENTITY_SPEC, BACKEND_OUTPUT)

    assert result["all_tests_passed"] is False
    assert len(result["failures"]) == 1
    assert result["failures"][0]["test_name"] == "Item x"


@patch("agents.qa_engineer.shutil.which", side_effect=_mock_which)
@patch("agents.qa_engineer._run_subprocess")
@patch("agents.qa_engineer.call_agent")
def test_generate_qa_report_handles_npm_install_failure_without_crashing(mock_call_agent, mock_subprocess, mock_which):
    mock_call_agent.return_value = FAKE_TEST_FILE_OUTPUT
    mock_subprocess.return_value = MagicMock(returncode=1, stdout="", stderr="npm ERR! something broke")

    from agents.qa_engineer import generate_qa_report
    result = generate_qa_report(TWO_ENTITY_SPEC, BACKEND_OUTPUT)

    validate_payload(result, QA_REPORT_SCHEMA)  # still a well-formed report, not an exception
    assert result["all_tests_passed"] is False
    assert "npm install" in result["failures"][0]["test_name"]
    assert "something broke" in result["failures"][0]["error_log"]
    # jest should never have been attempted after install failed
    assert mock_subprocess.call_count == 1


@patch("agents.qa_engineer.shutil.which", side_effect=_mock_which)
@patch("agents.qa_engineer._run_subprocess")
@patch("agents.qa_engineer.call_agent")
def test_generate_qa_report_handles_unparseable_jest_output(mock_call_agent, mock_subprocess, mock_which):
    mock_call_agent.return_value = FAKE_TEST_FILE_OUTPUT
    mock_subprocess.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),
        MagicMock(returncode=1, stdout="not json at all", stderr="jest crashed"),
    ]

    from agents.qa_engineer import generate_qa_report
    result = generate_qa_report(TWO_ENTITY_SPEC, BACKEND_OUTPUT)

    validate_payload(result, QA_REPORT_SCHEMA)
    assert result["all_tests_passed"] is False
    assert "jest run" in result["failures"][0]["test_name"]


@patch("agents.qa_engineer.shutil.which", side_effect=_mock_which)
@patch("agents.qa_engineer._run_subprocess")
@patch("agents.qa_engineer.call_agent")
def test_jest_run_gets_a_jwt_secret_even_though_sandbox_has_no_real_env_file(mock_call_agent, mock_subprocess, mock_which):
    # middleware/auth.js throws at require-time without JWT_SECRET, and the
    # sandbox never writes a real .env file - confirms this was actually
    # fixed, not just described in a comment nobody enforces.
    mock_call_agent.return_value = FAKE_TEST_FILE_OUTPUT
    mock_subprocess.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),
        MagicMock(returncode=0, stdout=json.dumps({"testResults": []}), stderr=""),
    ]

    from agents.qa_engineer import generate_qa_report
    generate_qa_report(TWO_ENTITY_SPEC, BACKEND_OUTPUT)

    jest_call = mock_subprocess.call_args_list[1]
    assert jest_call.kwargs["env"]["JWT_SECRET"]


@patch("agents.qa_engineer.shutil.which", return_value=None)
def test_generate_qa_report_raises_clearly_when_npm_missing(mock_which):
    from agents.qa_engineer import generate_qa_report
    try:
        generate_qa_report(TWO_ENTITY_SPEC, BACKEND_OUTPUT)
        assert False, "expected a RuntimeError"
    except RuntimeError as e:
        assert "npm" in str(e)


def _mock_which_no_npx(name):
    return None if name == "npx" else f"/usr/bin/{name}"


@patch("agents.qa_engineer.shutil.which", side_effect=_mock_which_no_npx)
def test_generate_qa_report_raises_clearly_when_npx_missing(mock_which):
    from agents.qa_engineer import generate_qa_report
    try:
        generate_qa_report(TWO_ENTITY_SPEC, BACKEND_OUTPUT)
        assert False, "expected a RuntimeError"
    except RuntimeError as e:
        assert "npx" in str(e)


def test_parse_jest_results_encodes_test_file_name_when_present():
    from agents.qa_engineer import _parse_jest_results

    jest_json = {
        "testResults": [{
            "name": "/sandbox/tests/order.test.js",
            "assertionResults": [
                {"title": "fails", "fullName": "Order POST /orders fails", "status": "failed",
                 "failureMessages": ["Expected: 201\nReceived: 400"]},
            ]
        }]
    }

    failures = _parse_jest_results(jest_json)

    assert len(failures) == 1
    assert failures[0]["test_name"] == "[tests/order.test.js] Order POST /orders fails"
    assert "400" in failures[0]["error_log"]


def test_helpers_js_includes_robust_token_extraction():
    from agents.qa_engineer import _build_helpers_js

    auth_endpoints = {
        "register_path": "/auth/register",
        "login_path": "/auth/login",
        "required_fields": ["email", "password"],
    }
    helpers = _build_helpers_js(auth_endpoints)
    assert "accessToken" in helpers
    assert "throw new Error('getAuthToken failed" in helpers
