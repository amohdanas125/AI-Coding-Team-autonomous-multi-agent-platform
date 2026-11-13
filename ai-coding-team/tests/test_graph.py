"""Graph-level tests: prove the topology and retry loop work correctly.
No Groq API calls happen here. Mocked at each agent's top-level
generate_X() function (as imported into orchestrator.graph), not at
call_agent() - deliberately, so this file doesn't need to change every
time an agent's internal implementation does. That already mattered once:
Backend Developer went from one call_agent() call to several (one per
entity, one for the skeleton) without this file needing to change at all.
See tests/test_project_manager.py, tests/test_backend_developer.py, and
tests/test_frontend_developer.py for the mocked wiring tests specific to
each agent's own internals, and the scripts/test_*.py files for the LIVE
tests against the real API that you need to run yourself."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.graph import build_graph
from orchestrator.state import initial_state

FAKE_SPEC = {
    "app_name": "StubApp",
    "app_description": "Fake spec injected by the test suite.",
    "auth_required": True,
    "entities": [{"name": "Item", "fields": [
        {"name": "title", "type": "string", "required": True, "references_entity": None}
    ]}],
    "relationships": [],
    "endpoints": [{"method": "GET", "path": "/items", "description": "list items",
                    "entity": "Item", "requires_auth": False}],
    "pages": [{"name": "Home", "route": "/", "description": "list items",
               "primary_entity": "Item"}],
}

FAKE_BACKEND_OUTPUT = {
    "files": [{"path": "server.js", "content": "// fake express app"}],
    "api_contract": [{"method": "GET", "path": "/items", "request_body_fields": [],
                       "response_shape_fields": ["_id", "title"], "requires_auth": False}],
    "setup_notes": "npm install && npm start",
}

FAKE_FRONTEND_OUTPUT = {
    "files": [{"path": "src/App.jsx", "content": "// fake react app"}],
    "setup_notes": "npm install && npm run dev",
}

FAKE_QA_REPORT_FAIL = {
    "all_tests_passed": False,
    "test_files": [{"path": "tests/items.test.js", "content": "// fake test"}],
    "failures": [{"test_name": "GET /items returns 200", "expected": "200",
                  "actual": "500", "error_log": "stub failure"}],
}

FAKE_QA_REPORT_PASS = {
    "all_tests_passed": True,
    "test_files": [{"path": "tests/items.test.js", "content": "// fake test"}],
    "failures": [],
}


def _make_qa_report_mock():
    # Now that qa_engineer is real, this mock has to replicate the
    # fail-fail-pass behavior the old built-in stub used to provide
    # directly in graph.py, since that's exactly what the retry-loop
    # tests below depend on. A closure over its own counter, fresh per
    # test via the autouse fixture below.
    call_count = {"n": 0}

    def mock_generate_qa_report(spec, backend_output):
        call_count["n"] += 1
        return FAKE_QA_REPORT_PASS if call_count["n"] >= 3 else FAKE_QA_REPORT_FAIL

    return mock_generate_qa_report


@pytest.fixture(autouse=True)
def mock_agents(monkeypatch):
    monkeypatch.setattr("orchestrator.graph.generate_spec", lambda prompt: FAKE_SPEC)
    monkeypatch.setattr("orchestrator.graph.generate_backend", lambda spec, **kwargs: FAKE_BACKEND_OUTPUT)
    monkeypatch.setattr("orchestrator.graph.generate_frontend", lambda spec, api_contract: FAKE_FRONTEND_OUTPUT)
    monkeypatch.setattr("orchestrator.graph.generate_qa_report", _make_qa_report_mock())
    monkeypatch.setattr(
        "orchestrator.graph.generate_docs",
        lambda spec, backend_output, **kwargs: {"files": [{"path": "README.md", "content": "# StubApp"}]},
    )


def _run(prompt="Build a to-do list app with user accounts"):
    graph = build_graph()
    return graph.invoke(initial_state("test-task", prompt))


def test_full_pipeline_reaches_docs():
    state = _run()
    assert state["docs_output"] is not None
    assert state["spec"] is not None
    assert state["backend_output"] is not None
    assert state["frontend_output"] is not None
    assert state["qa_report"] is not None


def test_qa_retry_loop_runs_three_times_then_passes():
    # Stub QA fails on attempts 1-2, passes on attempt 3.
    state = _run()
    assert state["qa_attempt"] == 3
    assert state["qa_report"]["all_tests_passed"] is True
    assert state["needs_human_review"] is False


def test_frontend_only_runs_once_despite_retries():
    # Frontend shouldn't be regenerated just because a backend test failed.
    state = _run()
    frontend_log_entries = [e for e in state["agent_log"] if e["from_agent"] == "frontend_developer"]
    assert len(frontend_log_entries) == 1


def test_backend_developer_runs_once_per_qa_attempt():
    state = _run()
    backend_log_entries = [e for e in state["agent_log"] if e["from_agent"] == "backend_developer"]
    assert len(backend_log_entries) == 3  # initial generation + 2 retries


def test_agent_log_records_every_step_in_order():
    state = _run()
    agents_in_order = [e["from_agent"] for e in state["agent_log"]]
    assert agents_in_order[0] == "project_manager"
    assert agents_in_order[-1] == "documentation_writer"
    assert agents_in_order.count("qa_engineer") == 3


def test_every_logged_payload_validates_against_its_own_schema():
    # Belt-and-suspenders: even stub payloads should already satisfy the
    # real schemas, since Phase 1 will swap stub logic for a real LLM call
    # returning the same shape.
    from schemas import PM_SPEC_SCHEMA, BACKEND_OUTPUT_SCHEMA, FRONTEND_OUTPUT_SCHEMA, QA_REPORT_SCHEMA, DOCS_OUTPUT_SCHEMA, validate_payload

    state = _run()
    validate_payload(state["spec"], PM_SPEC_SCHEMA)
    validate_payload(state["backend_output"], BACKEND_OUTPUT_SCHEMA)
    validate_payload(state["frontend_output"], FRONTEND_OUTPUT_SCHEMA)
    validate_payload(state["qa_report"], QA_REPORT_SCHEMA)
    validate_payload(state["docs_output"], DOCS_OUTPUT_SCHEMA)


def test_qa_retry_loop_fails_all_three_attempts_sets_needs_human_review(monkeypatch):
    # When QA fails all 3 times, pipeline reaches docs with needs_human_review=True
    monkeypatch.setattr("orchestrator.graph.generate_qa_report", lambda spec, backend: FAKE_QA_REPORT_FAIL)

    state = _run()
    assert state["qa_attempt"] == 3
    assert state["qa_report"]["all_tests_passed"] is False
    assert state["needs_human_review"] is True
    assert state["docs_output"] is not None
