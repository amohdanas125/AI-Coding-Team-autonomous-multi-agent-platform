"""Tests for the real Backend Developer agent (agents/backend_developer.py).

generate_backend() makes several smaller Groq calls internally (one per
entity, one for the skeleton) instead of one big call, to stay under
Groq's free-tier TPM limit - see the module docstring in
agents/backend_developer.py. Call spacing itself is handled by
groq_client.call_agent (tested in tests/test_groq_client.py), not by this
module - these tests mock groq_client.call_agent directly and verify the
orchestration (right number of calls, no cross-entity leakage, files/
contract correctly combined, seed.js correctly assembled), not that the
live Groq API generates correct code. For that, run
scripts/test_backend_agent.py yourself with a real GROQ_API_KEY - it
could not be run from the sandbox that built this (no network access to
api.groq.com there).
"""
import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import (
    BACKEND_OUTPUT_SCHEMA, BACKEND_ENTITY_OUTPUT_SCHEMA, BACKEND_SKELETON_OUTPUT_SCHEMA,
    validate_payload,
)

TWO_ENTITY_SPEC = {
    "app_name": "StubApp",
    "app_description": "A minimal two-entity spec for testing.",
    "auth_required": True,
    "entities": [
        {"name": "User", "fields": [
            {"name": "email", "type": "string", "required": True, "references_entity": None},
        ]},
        {"name": "Item", "fields": [
            {"name": "title", "type": "string", "required": True, "references_entity": None},
            {"name": "owner", "type": "reference", "required": True, "references_entity": "User"},
        ]},
    ],
    "relationships": [{"from_entity": "User", "to_entity": "Item", "relationship_type": "one_to_many"}],
    "endpoints": [
        {"method": "POST", "path": "/auth/register", "description": "register",
         "entity": "User", "requires_auth": False},
        {"method": "GET", "path": "/items", "description": "list items",
         "entity": "Item", "requires_auth": True},
    ],
    "pages": [{"name": "Home", "route": "/", "description": "list items", "primary_entity": "Item"}],
}

# NOTE: FAKE_ENTITY_OUTPUT is deliberately entity-agnostic (used as the
# mocked response for BOTH the User and Item calls below) - its
# seed_records values don't need to match either entity's real fields,
# since these tests check orchestration (call count, file assembly,
# seed.js presence), not that seed_records' shape matches a specific
# entity's schema. That schema-shape correctness is instead checked by
# test_fake_entity_output_is_schema_valid below, which validates this
# exact fixture against BACKEND_ENTITY_OUTPUT_SCHEMA - if this fixture's
# seed_records shape ever drifts from what real entities produce, that
# test is the one that will catch it.
FAKE_ENTITY_OUTPUT = {
    "files": [{"path": "models/Stub.js", "content": "// fake model"},
              {"path": "routes/stub.js", "content": "// fake router"}],
    "api_contract": [{"method": "GET", "path": "/stub", "request_body_fields": [],
                       "response_shape_fields": ["_id"], "requires_auth": False}],
    "seed_records": [{"name": "Fake One"}, {"name": "Fake Two"}],
}

FAKE_SKELETON_OUTPUT = {
    "files": [{"path": "package.json", "content": "{}"}, {"path": "server.js", "content": "// fake server"}],
    "setup_notes": "npm install && npm start",
}

# BACKEND_ENTITY_OUTPUT_SCHEMA (imported from schemas.py) doesn't itself
# include seed_records - that property is added dynamically per-entity by
# _build_entity_schema() in backend_developer.py, since its item shape
# depends on that entity's own fields (see that function's docstring).
# So FAKE_ENTITY_OUTPUT_SCHEMA_CHECK below validates only the base shape
# (files/api_contract) that IS static across every entity.


def test_fake_entity_output_matches_base_schema():
    # Only checks the static part of the schema (files/api_contract) -
    # seed_records isn't part of BACKEND_ENTITY_OUTPUT_SCHEMA itself since
    # its shape is entity-specific and built dynamically at call time.
    base_only = {"files": FAKE_ENTITY_OUTPUT["files"], "api_contract": FAKE_ENTITY_OUTPUT["api_contract"]}
    validate_payload(base_only, BACKEND_ENTITY_OUTPUT_SCHEMA)


def test_fake_skeleton_output_is_schema_valid():
    validate_payload(FAKE_SKELETON_OUTPUT, BACKEND_SKELETON_OUTPUT_SCHEMA)


@patch("agents.backend_developer.call_agent")
def test_generate_backend_makes_one_call_per_entity_plus_one_skeleton_call(mock_call_agent):
    mock_call_agent.side_effect = [FAKE_ENTITY_OUTPUT, FAKE_ENTITY_OUTPUT, FAKE_SKELETON_OUTPUT]
    from agents.backend_developer import generate_backend

    generate_backend(TWO_ENTITY_SPEC)

    assert mock_call_agent.call_count == 3  # 2 entities + 1 skeleton
    schema_names = [c.kwargs["schema_name"] for c in mock_call_agent.call_args_list]
    assert schema_names == ["backend_entity_output", "backend_entity_output", "backend_skeleton_output"]


@patch("agents.backend_developer.call_agent")
def test_generate_backend_combines_files_and_contract_correctly(mock_call_agent):
    mock_call_agent.side_effect = [FAKE_ENTITY_OUTPUT, FAKE_ENTITY_OUTPUT, FAKE_SKELETON_OUTPUT]
    from agents.backend_developer import generate_backend

    result = generate_backend(TWO_ENTITY_SPEC)

    validate_payload(result, BACKEND_OUTPUT_SCHEMA)  # combined output still matches the original schema
    # 2 files x 2 entity calls + 2 skeleton files + 1 auto-assembled seed.js
    assert len(result["files"]) == 2 + 2 + 2 + 1
    assert len(result["api_contract"]) == 2  # 1 contract entry x 2 entity calls
    assert result["setup_notes"] == "npm install && npm start Run `node seed.js` after `npm install` to populate sample data."


@patch("agents.backend_developer.call_agent")
def test_generate_backend_appends_seed_js(mock_call_agent):
    mock_call_agent.side_effect = [FAKE_ENTITY_OUTPUT, FAKE_ENTITY_OUTPUT, FAKE_SKELETON_OUTPUT]
    from agents.backend_developer import generate_backend

    result = generate_backend(TWO_ENTITY_SPEC)

    seed_file = next((f for f in result["files"] if f["path"] == "seed.js"), None)
    assert seed_file is not None
    # User has no reference fields, so it should be seeded before Item
    # (which references User) - confirm dependency order in the actual
    # generated script content, not just that the file exists.
    assert seed_file["content"].index("const User = require") < seed_file["content"].index("const Item = require")
    assert "createdUser[Math.floor" in seed_file["content"]  # Item.owner resolved from createdUser


@patch("agents.backend_developer.call_agent")
def test_each_entity_call_only_receives_its_own_endpoints(mock_call_agent):
    # The whole point of splitting per-entity is a smaller prompt each time -
    # confirm Item's endpoint never leaks into User's call, and vice versa.
    mock_call_agent.side_effect = [FAKE_ENTITY_OUTPUT, FAKE_ENTITY_OUTPUT, FAKE_SKELETON_OUTPUT]
    from agents.backend_developer import generate_backend

    generate_backend(TWO_ENTITY_SPEC)

    user_call_prompt = json.loads(mock_call_agent.call_args_list[0].kwargs["user_prompt"])
    assert user_call_prompt["entity"]["name"] == "User"
    assert [e["path"] for e in user_call_prompt["endpoints"]] == ["/auth/register"]

    item_call_prompt = json.loads(mock_call_agent.call_args_list[1].kwargs["user_prompt"])
    assert item_call_prompt["entity"]["name"] == "Item"
    assert [e["path"] for e in item_call_prompt["endpoints"]] == ["/items"]


@patch("agents.backend_developer.call_agent")
def test_backend_developer_node_still_returns_backend_output_shape(mock_call_agent):
    # graph.py's node function shouldn't need to know anything changed internally.
    mock_call_agent.side_effect = [FAKE_ENTITY_OUTPUT, FAKE_ENTITY_OUTPUT, FAKE_SKELETON_OUTPUT]
    from orchestrator.graph import backend_developer_node
    from orchestrator.state import initial_state

    state = initial_state("test-task", "Build a stub app")
    state["spec"] = TWO_ENTITY_SPEC
    result = backend_developer_node(state)

    validate_payload(result["backend_output"], BACKEND_OUTPUT_SCHEMA)
    assert result["agent_log"][0]["to_agent"] == "frontend_developer"


@patch("agents.backend_developer.call_agent")
def test_backend_developer_node_routes_to_qa_directly_on_retry(mock_call_agent):
    mock_call_agent.side_effect = [FAKE_ENTITY_OUTPUT, FAKE_ENTITY_OUTPUT, FAKE_SKELETON_OUTPUT]
    from orchestrator.graph import backend_developer_node
    from orchestrator.state import initial_state

    state = initial_state("test-task", "Build a stub app")
    state["spec"] = TWO_ENTITY_SPEC
    state["qa_report"] = {"all_tests_passed": False, "test_files": [], "failures": []}
    result = backend_developer_node(state)

    assert result["agent_log"][0]["to_agent"] == "qa_engineer"


# --- route filename consistency - both entity and skeleton calls must
# agree on the same filename without independently deriving it, since
# that's exactly what caused a live "Cannot find module './routes/order'"
# crash: server.js required a name the Order entity call had derived
# slightly differently on its own. ---

def test_route_filename_is_just_lowercase_no_hidden_transformation():
    from agents.backend_developer import _route_filename

    assert _route_filename("Order") == "order"
    assert _route_filename("OrderItem") == "orderitem"


@patch("agents.backend_developer.call_agent")
def test_entity_call_is_told_the_exact_route_filename_to_use(mock_call_agent):
    mock_call_agent.side_effect = [FAKE_ENTITY_OUTPUT, FAKE_ENTITY_OUTPUT, FAKE_SKELETON_OUTPUT]
    from agents.backend_developer import generate_backend

    generate_backend(TWO_ENTITY_SPEC)

    user_call_prompt = json.loads(mock_call_agent.call_args_list[0].kwargs["user_prompt"])
    assert user_call_prompt["route_filename"] == "user"

    item_call_prompt = json.loads(mock_call_agent.call_args_list[1].kwargs["user_prompt"])
    assert item_call_prompt["route_filename"] == "item"


@patch("agents.backend_developer.call_agent")
def test_skeleton_call_receives_the_same_filenames_the_entity_calls_were_given(mock_call_agent):
    mock_call_agent.side_effect = [FAKE_ENTITY_OUTPUT, FAKE_ENTITY_OUTPUT, FAKE_SKELETON_OUTPUT]
    from agents.backend_developer import generate_backend

    generate_backend(TWO_ENTITY_SPEC)

    skeleton_call_prompt = json.loads(mock_call_agent.call_args_list[2].kwargs["user_prompt"])
    assert skeleton_call_prompt["route_filenames"] == ["user", "item"]


@patch("agents.backend_developer.call_agent")
def test_mismatched_route_filename_from_the_model_gets_corrected(mock_call_agent):
    # Simulates the actual failure: the model ignores route_filename and
    # names its router something else. generate_entity_backend must fix
    # this itself rather than silently shipping a name server.js won't find.
    wrong_name_output = {
        "files": [
            {"path": "models/Order.js", "content": "// fake model"},
            {"path": "routes/orders.js", "content": "// model used plural, ignoring route_filename"},
        ],
        "api_contract": [],
        "seed_records": [{"title": "A"}, {"title": "B"}],
    }
    mock_call_agent.side_effect = [wrong_name_output, FAKE_SKELETON_OUTPUT]
    from agents.backend_developer import generate_backend

    single_entity_spec = dict(TWO_ENTITY_SPEC)
    single_entity_spec["entities"] = [
        {"name": "Order", "fields": [{"name": "title", "type": "string", "required": True, "references_entity": None}]},
    ]
    single_entity_spec["endpoints"] = []

    result = generate_backend(single_entity_spec)

    route_files = [f["path"] for f in result["files"] if f["path"].startswith("routes/")]
    assert route_files == ["routes/order.js"]  # corrected from the model's "orders.js"


# --- package.json content validation - confirmed live to fail in a
# uniquely confusing way: an overall schema-valid response can still
# embed BROKEN JSON as package.json's string content, and node --check
# then fails on EVERY file in the project with the same misleading
# ERR_INVALID_PACKAGE_CONFIG, since it must read package.json before it
# can check anything else. ---

@patch("agents.backend_developer.call_agent")
def test_skeleton_retries_when_package_json_content_is_invalid_json(mock_call_agent):
    broken_output = {
        "files": [
            {"path": "package.json", "content": '{"name": "app",}'},  # trailing comma - invalid JSON
            {"path": "server.js", "content": "// stub"},
        ],
        "setup_notes": "npm install && npm start",
    }
    mock_call_agent.side_effect = [broken_output, FAKE_SKELETON_OUTPUT]
    from agents.backend_developer import generate_backend_skeleton

    result = generate_backend_skeleton("App", True, ["Order"])

    assert mock_call_agent.call_count == 2
    assert result == FAKE_SKELETON_OUTPUT


@patch("agents.backend_developer.call_agent")
def test_skeleton_raises_clearly_if_package_json_stays_invalid_after_retries(mock_call_agent):
    broken_output = {
        "files": [{"path": "package.json", "content": '{"name": "app",}'}],
        "setup_notes": "npm install && npm start",
    }
    mock_call_agent.side_effect = [broken_output, broken_output]
    from agents.backend_developer import generate_backend_skeleton

    try:
        generate_backend_skeleton("App", True, ["Order"], max_attempts=2)
        assert False, "expected a ValueError"
    except ValueError as e:
        assert "package.json" in str(e)
    assert mock_call_agent.call_count == 2  # respected max_attempts, didn't loop forever


@patch("agents.backend_developer.call_agent")
def test_skeleton_raises_clearly_if_package_json_missing_entirely(mock_call_agent):
    no_package_json = {
        "files": [{"path": "server.js", "content": "// stub, no package.json at all"}],
        "setup_notes": "npm install && npm start",
    }
    mock_call_agent.side_effect = [no_package_json, no_package_json]
    from agents.backend_developer import generate_backend_skeleton

    try:
        generate_backend_skeleton("App", True, ["Order"], max_attempts=2)
        assert False, "expected a ValueError"
    except ValueError as e:
        assert "package.json" in str(e)


# --- JavaScript syntax validation of the skeleton's own files. Confirmed
# live: server.js came back minified onto one line with one wrong bracket,
# passing every schema check, and only failed later in node --check. ---

import shutil as _shutil
import pytest as _pytest

# The actual broken server.js from that live run, verbatim.
LIVE_BROKEN_SERVER_JS = (
    "require('dotenv').config();const mongoose=require('mongoose');const app=require('./app');"
    "const MONGODB_URI=process.env.MONGODB_URI;if(!MONGODB_URI){console.error('MONGODB_URI required');process.exit(1);}"
    "mongoose.connect(MONGODB_URI).then(()=>{console.log('Connected to MongoDB');const PORT=process.env.PORT||3000;"
    "app.listen(PORT,()=>{console.log(`Server running on port ${PORT}`});});}).catch(err=>{process.exit(1);});"
)

needs_node = _pytest.mark.skipif(_shutil.which("node") is None, reason="node not installed")


@needs_node
def test_js_syntax_errors_catches_the_real_live_failure():
    from agents.backend_developer import _js_syntax_errors

    errors = _js_syntax_errors([{"path": "server.js", "content": LIVE_BROKEN_SERVER_JS}])

    assert len(errors) == 1
    assert errors[0][0] == "server.js"


@needs_node
def test_js_syntax_errors_passes_valid_files_and_ignores_non_js():
    from agents.backend_developer import _js_syntax_errors

    errors = _js_syntax_errors([
        {"path": "server.js", "content": "const x = 1;\nconsole.log(x);\n"},
        {"path": "package.json", "content": "this is not js at all {{{"},
    ])

    assert errors == []


@patch("agents.backend_developer.shutil.which", return_value=None)
def test_js_syntax_errors_is_a_no_op_when_node_is_missing(mock_which):
    from agents.backend_developer import _js_syntax_errors

    # A missing tool must never block generation.
    assert _js_syntax_errors([{"path": "server.js", "content": "this is not valid js {{{"}]) == []


@patch("agents.backend_developer._js_syntax_errors")
@patch("agents.backend_developer.call_agent")
def test_skeleton_retries_when_a_js_file_has_a_syntax_error(mock_call_agent, mock_js_errors):
    mock_call_agent.side_effect = [FAKE_SKELETON_OUTPUT, FAKE_SKELETON_OUTPUT]
    mock_js_errors.side_effect = [[("server.js", "SyntaxError: missing ) after argument list")], []]
    from agents.backend_developer import generate_backend_skeleton

    result = generate_backend_skeleton("App", True, ["Order"])

    assert mock_call_agent.call_count == 2
    assert result == FAKE_SKELETON_OUTPUT


@patch("agents.backend_developer._js_syntax_errors")
@patch("agents.backend_developer.call_agent")
def test_skeleton_raises_clearly_if_js_syntax_error_persists(mock_call_agent, mock_js_errors):
    mock_call_agent.side_effect = [FAKE_SKELETON_OUTPUT, FAKE_SKELETON_OUTPUT]
    mock_js_errors.return_value = [("server.js", "SyntaxError: unexpected token")]
    from agents.backend_developer import generate_backend_skeleton

    try:
        generate_backend_skeleton("App", True, ["Order"], max_attempts=2)
        assert False, "expected a ValueError"
    except ValueError as e:
        assert "server.js" in str(e)
    assert mock_call_agent.call_count == 2


def test_skeleton_prompt_forbids_minified_code():
    from agents.backend_developer import SKELETON_SYSTEM_PROMPT

    assert "never minified" in SKELETON_SYSTEM_PROMPT


# --- Surgical Retry Tests (Task D) ---

def test_find_failing_entities_identifies_entity_from_test_name():
    from agents.backend_developer import find_failing_entities

    qa_report = {
        "all_tests_passed": False,
        "failures": [
            {
                "test_name": "[tests/item.test.js] Item GET /items returns 200",
                "expected": "200",
                "actual": "500",
                "error_log": "error in item router",
            }
        ],
    }
    failing = find_failing_entities(qa_report, TWO_ENTITY_SPEC["entities"])
    assert failing == ["Item"]


def test_find_failing_entities_returns_none_on_global_failures():
    from agents.backend_developer import find_failing_entities

    # npm install failure
    npm_fail_report = {
        "all_tests_passed": False,
        "failures": [{"test_name": "npm install", "expected": "0", "actual": "1", "error_log": "npm ERR!"}],
    }
    assert find_failing_entities(npm_fail_report, TWO_ENTITY_SPEC["entities"]) is None

    # jest crash
    jest_fail_report = {
        "all_tests_passed": False,
        "failures": [{"test_name": "jest run", "expected": "json", "actual": "crash", "error_log": "syntax error"}],
    }
    assert find_failing_entities(jest_fail_report, TWO_ENTITY_SPEC["entities"]) is None


@patch("agents.backend_developer.call_agent")
def test_surgical_retry_only_calls_agent_for_failing_entity(mock_call_agent):
    from agents.backend_developer import generate_backend

    # 1. Initial run: 2 entities + 1 skeleton = 3 calls
    user_entity_output = {
        "files": [{"path": "models/User.js", "content": "// user model"}, {"path": "routes/user.js", "content": "// user route"}],
        "api_contract": [{"method": "POST", "path": "/auth/register", "request_body_fields": [], "response_shape_fields": [], "requires_auth": False}],
        "seed_records": [{"email": "user1@example.com"}, {"email": "user2@example.com"}],
    }
    item_entity_output = {
        "files": [{"path": "models/Item.js", "content": "// item model"}, {"path": "routes/item.js", "content": "// item route"}],
        "api_contract": [{"method": "GET", "path": "/items", "request_body_fields": [], "response_shape_fields": ["_id"], "requires_auth": True}],
        "seed_records": [{"title": "Old Item 1"}, {"title": "Old Item 2"}],
    }
    skeleton_output = {
        "files": [
            {"path": "package.json", "content": json.dumps({"name": "app"})},
            {"path": "app.js", "content": "// app"},
            {"path": "server.js", "content": "// server"},
        ],
        "setup_notes": "Setup notes",
    }
    mock_call_agent.side_effect = [user_entity_output, item_entity_output, skeleton_output]
    initial_backend = generate_backend(TWO_ENTITY_SPEC)
    assert mock_call_agent.call_count == 3

    # 2. QA fails on Item only
    qa_report = {
        "all_tests_passed": False,
        "failures": [
            {
                "test_name": "[tests/item.test.js] Item GET /items returns 200",
                "expected": "200",
                "actual": "500",
                "error_log": "Item error",
            }
        ],
    }

    # Reset mock for retry run
    mock_call_agent.reset_mock()
    mock_call_agent.side_effect = None
    fixed_item_output = {
        "files": [{"path": "models/Item.js", "content": "// fixed item model"}, {"path": "routes/item.js", "content": "// fixed item route"}],
        "api_contract": [{"method": "GET", "path": "/items", "request_body_fields": [], "response_shape_fields": ["_id"], "requires_auth": True}],
        "seed_records": [{"title": "Fixed Item 1"}, {"title": "Fixed Item 2"}],
    }
    mock_call_agent.return_value = fixed_item_output

    retry_backend = generate_backend(TWO_ENTITY_SPEC, qa_report=qa_report, previous_output=initial_backend)

    # EXACTLY 1 call made! Only for Item!
    assert mock_call_agent.call_count == 1
    call_prompt = json.loads(mock_call_agent.call_args.kwargs["user_prompt"])
    assert call_prompt["entity"]["name"] == "Item"
    assert "Item error" in call_prompt["previous_qa_failures"]

    # Verify output retains User and Skeleton files, but has new Item files
    file_map = {f["path"]: f["content"] for f in retry_backend["files"]}
    assert file_map["models/User.js"] == "// user model"  # Preserved!
    assert file_map["routes/user.js"] == "// user route"  # Preserved!
    assert file_map["package.json"]  # Preserved!
    assert file_map["models/Item.js"] == "// fixed item model"  # Updated!
    assert file_map["routes/item.js"] == "// fixed item route"  # Updated!
    assert "seed.js" in file_map  # Re-assembled!


@patch("agents.backend_developer._js_syntax_errors")
@patch("agents.backend_developer.call_agent")
def test_generate_entity_backend_retries_on_syntax_error(mock_call_agent, mock_js_errors):
    from agents.backend_developer import generate_entity_backend

    mock_call_agent.side_effect = [FAKE_ENTITY_OUTPUT, FAKE_ENTITY_OUTPUT]
    mock_js_errors.side_effect = [[("routes/stub.js", "SyntaxError")], []]

    result = generate_entity_backend(TWO_ENTITY_SPEC["entities"][0], [], False)
    assert mock_call_agent.call_count == 2
    assert result["files"][0]["path"] == "models/Stub.js"

