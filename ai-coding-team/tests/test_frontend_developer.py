"""Tests for the real Frontend Developer agent (agents/frontend_developer.py).

generate_frontend() makes several smaller calls internally (one per page,
one for the skeleton) instead of one big call - see the module docstring
in agents/frontend_developer.py. These tests mock gemini_client.call_agent
(patched via agents.frontend_developer.call_agent, so they're agnostic to
which underlying provider module that name currently points at), so they
run without network access or an API key, and verify the orchestration,
the api_contract-not-source design point, and the reference-field lookup
resolution - not that the live API generates a working React app. For
that, run scripts/test_frontend_agent.py yourself with real credentials -
it could not be run from the sandbox that built this (no network access
to any LLM provider from there).
"""
import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import (
    FRONTEND_OUTPUT_SCHEMA, FRONTEND_PAGE_OUTPUT_SCHEMA, FRONTEND_SKELETON_OUTPUT_SCHEMA,
    validate_payload,
)

# Two entities, Order referencing Restaurant - deliberately shaped so
# Restaurant's own GET-list endpoint would be filtered OUT of the Order
# page's scoped_contract by _relevant_endpoints (different primary_entity),
# which is exactly the situation that broke a real generated Order form:
# it needs Restaurant's list endpoint to populate a picker, but that
# endpoint doesn't "belong" to the Order page's own entity.
TWO_ENTITY_SPEC = {
    "app_name": "StubApp",
    "app_description": "A minimal two-entity, two-page spec for testing endpoint filtering and reference lookups.",
    "auth_required": True,
    "entities": [
        {"name": "Restaurant", "fields": [
            {"name": "name", "type": "string", "required": True, "references_entity": None},
        ]},
        {"name": "Order", "fields": [
            {"name": "restaurant", "type": "reference", "required": True, "references_entity": "Restaurant"},
        ]},
    ],
    "relationships": [{"from_entity": "Restaurant", "to_entity": "Order", "relationship_type": "one_to_many"}],
    "endpoints": [
        {"method": "GET", "path": "/restaurants", "description": "list restaurants",
         "entity": "Restaurant", "requires_auth": False},
        {"method": "POST", "path": "/orders", "description": "create order",
         "entity": "Order", "requires_auth": True},
    ],
    "pages": [
        {"name": "Home", "route": "/", "description": "list restaurants", "primary_entity": "Restaurant"},
        {"name": "OrderForm", "route": "/orders/new", "description": "create an order", "primary_entity": "Order"},
    ],
}

FULL_API_CONTRACT = [
    {"method": "GET", "path": "/restaurants", "request_body_fields": [],
     "response_shape_fields": ["_id", "name"], "requires_auth": False},
    {"method": "POST", "path": "/orders",
     "request_body_fields": [
         {"name": "restaurant", "is_reference": True, "references_entity": "Restaurant"},
         {"name": "status", "is_reference": False, "references_entity": None},
     ],
     "response_shape_fields": ["_id", "restaurant", "status"], "requires_auth": True},
]

FAKE_PAGE_OUTPUT = {
    "files": [{"path": "src/pages/Stub.jsx", "content": "// fake page"}],
}

FAKE_SKELETON_OUTPUT = {
    "files": [{"path": "package.json", "content": '{"name": "stub-frontend"}'},
              {"path": "src/App.jsx", "content": "// fake app"},
              {"path": "src/api.js", "content": "// fake api helper"}],
    "setup_notes": "npm install && npm run dev",
}


def test_fake_page_output_is_schema_valid():
    validate_payload(FAKE_PAGE_OUTPUT, FRONTEND_PAGE_OUTPUT_SCHEMA)


def test_fake_skeleton_output_is_schema_valid():
    validate_payload(FAKE_SKELETON_OUTPUT, FRONTEND_SKELETON_OUTPUT_SCHEMA)


# --- _relevant_endpoints, tested directly ---

def test_relevant_endpoints_filters_to_the_matching_entity_only():
    from agents.frontend_developer import _relevant_endpoints

    home_page = {"name": "Home", "route": "/", "description": "", "primary_entity": "Restaurant"}
    result = _relevant_endpoints(home_page, FULL_API_CONTRACT, TWO_ENTITY_SPEC["endpoints"])

    assert result == [FULL_API_CONTRACT[0]]  # only the /restaurants entry, not /orders


def test_relevant_endpoints_falls_back_to_full_contract_when_nothing_matches():
    from agents.frontend_developer import _relevant_endpoints

    orphan_page = {"name": "Weird", "route": "/x", "description": "", "primary_entity": "NoSuchEntity"}
    result = _relevant_endpoints(orphan_page, FULL_API_CONTRACT, TWO_ENTITY_SPEC["endpoints"])

    assert result == FULL_API_CONTRACT


# --- reference field resolution - the actual fix for the "restaurant name
# instead of restaurant _id" bug found live ---

def test_find_list_endpoint_for_entity_locates_the_right_get_endpoint():
    from agents.frontend_developer import _find_list_endpoint_for_entity

    result = _find_list_endpoint_for_entity("Restaurant", FULL_API_CONTRACT, TWO_ENTITY_SPEC["endpoints"])

    assert result == "/restaurants"


def test_find_list_endpoint_for_entity_returns_none_when_no_list_endpoint_exists():
    from agents.frontend_developer import _find_list_endpoint_for_entity

    result = _find_list_endpoint_for_entity("NoSuchEntity", FULL_API_CONTRACT, TWO_ENTITY_SPEC["endpoints"])

    assert result is None


def test_reference_field_lookups_finds_restaurant_endpoint_even_though_it_was_scoped_out():
    # The core case: OrderForm's scoped_contract only contains /orders (its
    # own entity) - Restaurant's /restaurants was filtered OUT by
    # _relevant_endpoints. _reference_field_lookups must still find it by
    # searching the FULL contract, not the scoped one.
    from agents.frontend_developer import _relevant_endpoints, _reference_field_lookups

    order_page = {"name": "OrderForm", "route": "/orders/new", "description": "", "primary_entity": "Order"}
    scoped = _relevant_endpoints(order_page, FULL_API_CONTRACT, TWO_ENTITY_SPEC["endpoints"])
    assert scoped == [FULL_API_CONTRACT[1]]  # confirm /restaurants really was scoped out first

    lookups = _reference_field_lookups(scoped, FULL_API_CONTRACT, TWO_ENTITY_SPEC["endpoints"])

    assert lookups == {"restaurant": {"references_entity": "Restaurant", "list_endpoint": "/restaurants"}}


def test_reference_field_lookups_empty_when_no_reference_fields_present():
    from agents.frontend_developer import _reference_field_lookups

    # /restaurants itself has no request_body_fields at all (GET, no body)
    lookups = _reference_field_lookups([FULL_API_CONTRACT[0]], FULL_API_CONTRACT, TWO_ENTITY_SPEC["endpoints"])

    assert lookups == {}


# --- generate_frontend orchestration ---

@patch("agents.frontend_developer.call_agent")
def test_generate_frontend_makes_one_call_per_page_plus_one_skeleton_call(mock_call_agent):
    mock_call_agent.side_effect = [FAKE_PAGE_OUTPUT, FAKE_PAGE_OUTPUT, FAKE_SKELETON_OUTPUT]
    from agents.frontend_developer import generate_frontend

    generate_frontend(TWO_ENTITY_SPEC, FULL_API_CONTRACT)

    assert mock_call_agent.call_count == 3  # 2 pages + 1 skeleton
    schema_names = [c.kwargs["schema_name"] for c in mock_call_agent.call_args_list]
    assert schema_names == ["frontend_page_output", "frontend_page_output", "frontend_skeleton_output"]


@patch("agents.frontend_developer.call_agent")
def test_generate_frontend_combines_files_correctly(mock_call_agent):
    mock_call_agent.side_effect = [FAKE_PAGE_OUTPUT, FAKE_PAGE_OUTPUT, FAKE_SKELETON_OUTPUT]
    from agents.frontend_developer import generate_frontend

    result = generate_frontend(TWO_ENTITY_SPEC, FULL_API_CONTRACT)

    validate_payload(result, FRONTEND_OUTPUT_SCHEMA)
    assert len(result["files"]) == 1 + 1 + 3
    assert result["setup_notes"] == "npm install && npm run dev"


@patch("agents.frontend_developer.call_agent")
def test_order_page_prompt_includes_reference_lookup_for_restaurant(mock_call_agent):
    # End-to-end through generate_frontend: confirm the OrderForm page's
    # actual prompt (not just the helper functions in isolation) carries
    # the resolved lookup - this is what the model sees.
    mock_call_agent.side_effect = [FAKE_PAGE_OUTPUT, FAKE_PAGE_OUTPUT, FAKE_SKELETON_OUTPUT]
    from agents.frontend_developer import generate_frontend

    generate_frontend(TWO_ENTITY_SPEC, FULL_API_CONTRACT)

    order_call = json.loads(mock_call_agent.call_args_list[1].kwargs["user_prompt"])
    assert order_call["page"]["name"] == "OrderForm"
    assert order_call["reference_lookups"]["restaurant"]["list_endpoint"] == "/restaurants"


@patch("agents.frontend_developer.call_agent")
def test_frontend_developer_node_passes_api_contract_not_backend_source(mock_call_agent):
    # The whole point of the contract is that Frontend never sees Backend's
    # source files - confirm no call's prompt contains backend source.
    mock_call_agent.side_effect = [FAKE_PAGE_OUTPUT, FAKE_PAGE_OUTPUT, FAKE_SKELETON_OUTPUT]
    from orchestrator.graph import frontend_developer_node
    from orchestrator.state import initial_state

    state = initial_state("test-task", "Build a stub app")
    state["spec"] = TWO_ENTITY_SPEC
    state["backend_output"] = {
        "files": [{"path": "server.js", "content": "SECRET_IMPLEMENTATION_DETAIL"}],
        "api_contract": FULL_API_CONTRACT,
        "setup_notes": "npm start",
    }
    result = frontend_developer_node(state)

    for call in mock_call_agent.call_args_list:
        assert "SECRET_IMPLEMENTATION_DETAIL" not in call.kwargs["user_prompt"]
    validate_payload(result["frontend_output"], FRONTEND_OUTPUT_SCHEMA)
    assert result["agent_log"][0]["to_agent"] == "qa_engineer"
