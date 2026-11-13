"""Tests for the real Project Manager agent (agents/project_manager.py).

These mock groq_client.call_agent, so they run without network access or
an API key - they prove the WIRING is correct (generate_spec builds the
right request, project_manager_node updates state correctly), NOT that
the live Groq API returns good specs for real prompts. For that, run
scripts/test_pm_agent.py yourself with a real GROQ_API_KEY - it could not
be run from the sandbox that built this (no network access to
api.groq.com there).
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import PM_SPEC_SCHEMA, validate_payload

FAKE_SPEC = {
    "app_name": "QuickBite",
    "app_description": "Users browse restaurants, place orders, and track delivery status.",
    "auth_required": True,
    "entities": [
        {"name": "User", "fields": [
            {"name": "email", "type": "string", "required": True, "references_entity": None},
        ]},
        {"name": "Order", "fields": [
            {"name": "user", "type": "reference", "required": True, "references_entity": "User"},
        ]},
    ],
    "relationships": [
        {"from_entity": "User", "to_entity": "Order", "relationship_type": "one_to_many"},
    ],
    "endpoints": [
        {"method": "POST", "path": "/orders", "description": "create an order",
         "entity": "Order", "requires_auth": True},
    ],
    "pages": [
        {"name": "Home", "route": "/", "description": "browse restaurants", "primary_entity": "Order"},
    ],
}


def test_fake_spec_is_schema_valid():
    # Sanity check on the fixture itself before relying on it below.
    validate_payload(FAKE_SPEC, PM_SPEC_SCHEMA)


@patch("agents.project_manager.call_agent")
def test_generate_spec_calls_groq_with_correct_schema(mock_call_agent):
    mock_call_agent.return_value = FAKE_SPEC
    from agents.project_manager import generate_spec, SYSTEM_PROMPT

    result = generate_spec("Build a food delivery website")

    mock_call_agent.assert_called_once_with(
        system_prompt=SYSTEM_PROMPT,
        user_prompt="Build a food delivery website",
        schema=PM_SPEC_SCHEMA,
        schema_name="project_manager_spec",
    )
    assert result == FAKE_SPEC


@patch("agents.project_manager.call_agent")
def test_project_manager_node_updates_state_correctly(mock_call_agent):
    mock_call_agent.return_value = FAKE_SPEC
    from orchestrator.graph import project_manager_node
    from orchestrator.state import initial_state

    state = initial_state("test-task", "Build a food delivery website")
    result = project_manager_node(state)

    assert result["spec"] == FAKE_SPEC
    assert len(result["agent_log"]) == 1
    assert result["agent_log"][0]["from_agent"] == "project_manager"
    assert result["agent_log"][0]["to_agent"] == "backend_developer"
    assert result["agent_log"][0]["status"] == "done"


@patch("agents.project_manager.call_agent")
def test_generate_spec_propagates_validation_error_on_bad_response(mock_call_agent):
    # If Groq's strict mode is ever silently ignored (it has happened - see
    # schemas.py docstring), call_agent's own validate_payload() call
    # raises before generate_spec can return garbage upstream.
    import jsonschema
    mock_call_agent.side_effect = jsonschema.exceptions.ValidationError("simulated schema violation")
    from agents.project_manager import generate_spec

    try:
        generate_spec("Build a food delivery website")
        assert False, "expected a ValidationError to propagate"
    except jsonschema.exceptions.ValidationError:
        pass
