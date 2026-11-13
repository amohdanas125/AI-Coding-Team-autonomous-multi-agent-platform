"""Tests for Documentation Writer agent (agents/documentation_writer.py).
Mocks the LLM layer so tests run offline with zero API calls.
"""
import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import DOCS_OUTPUT_SCHEMA, validate_payload

SAMPLE_SPEC = {
    "app_name": "QuickBite",
    "app_description": "Food delivery app connecting hungry customers with local restaurants.",
    "auth_required": True,
    "entities": [
        {
            "name": "Restaurant",
            "fields": [
                {"name": "name", "type": "string", "required": True, "references_entity": None},
                {"name": "cuisine", "type": "string", "required": False, "references_entity": None},
            ],
        },
        {
            "name": "Order",
            "fields": [
                {"name": "total", "type": "number", "required": True, "references_entity": None},
                {"name": "restaurant", "type": "reference", "required": True, "references_entity": "Restaurant"},
            ],
        },
    ],
    "relationships": [
        {"from_entity": "Restaurant", "to_entity": "Order", "relationship_type": "one_to_many"},
    ],
    "endpoints": [
        {"method": "GET", "path": "/restaurants", "description": "List all restaurants", "entity": "Restaurant", "requires_auth": False},
        {"method": "POST", "path": "/orders", "description": "Place a new order", "entity": "Order", "requires_auth": True},
    ],
    "pages": [],
}

SAMPLE_BACKEND_OUTPUT = {
    "files": [],
    "api_contract": [
        {
            "method": "GET",
            "path": "/restaurants",
            "request_body_fields": [],
            "response_shape_fields": ["_id", "name", "cuisine"],
            "requires_auth": False,
        },
        {
            "method": "POST",
            "path": "/orders",
            "request_body_fields": [
                {"name": "total", "is_reference": False, "references_entity": None},
                {"name": "restaurant", "is_reference": True, "references_entity": "Restaurant"},
            ],
            "response_shape_fields": ["_id", "total", "restaurant", "createdAt"],
            "requires_auth": True,
        },
    ],
    "setup_notes": "",
}

FAKE_PROSE_OUTPUT = {
    "overview": "QuickBite is an agile food delivery platform designed for urban foodies.",
    "features": [
        "Browse curated local restaurants",
        "Place instant food delivery orders",
        "Secure customer accounts",
    ],
    "architecture_summary": "Decoupled architecture with an Express/Mongoose backend and React/Vite frontend.",
}


def test_build_api_reference_markdown_contains_entities_and_endpoints():
    from agents.documentation_writer import _build_api_reference_markdown

    md = _build_api_reference_markdown(SAMPLE_SPEC, SAMPLE_BACKEND_OUTPUT["api_contract"])

    assert "### Entities & Data Models" in md
    assert "#### `Restaurant`" in md
    assert "#### `Order`" in md
    assert "| `restaurant` | `reference` | Yes | `Restaurant` |" in md
    assert "### Endpoints" in md
    assert "| `GET` | `/restaurants` | No |" in md
    assert "| `POST` | `/orders` | Yes |" in md
    assert "ref `Restaurant`" in md


def test_build_setup_instructions_contains_ports_and_seed():
    from agents.documentation_writer import _build_setup_instructions_markdown

    md = _build_setup_instructions_markdown(SAMPLE_SPEC, needs_human_review=False)

    assert "http://localhost:3000" in md
    assert "http://localhost:5173" in md
    assert "node seed.js" in md
    assert "npm test" in md
    assert "JWT_SECRET=" in md
    assert "QA Automated Verification Warning" not in md


def test_build_setup_instructions_includes_warning_when_review_needed():
    from agents.documentation_writer import _build_setup_instructions_markdown

    md = _build_setup_instructions_markdown(SAMPLE_SPEC, needs_human_review=True)

    assert "QA Automated Verification Warning" in md
    assert "requires human code review" in md


@patch("agents.documentation_writer.call_agent")
def test_generate_docs_produces_valid_schema_output(mock_call_agent):
    mock_call_agent.return_value = FAKE_PROSE_OUTPUT
    from agents.documentation_writer import generate_docs

    output = generate_docs(SAMPLE_SPEC, SAMPLE_BACKEND_OUTPUT)

    validate_payload(output, DOCS_OUTPUT_SCHEMA)
    assert len(output["files"]) == 2
    paths = [f["path"] for f in output["files"]]
    assert "README.md" in paths
    assert "API_REFERENCE.md" in paths

    readme = next(f["content"] for f in output["files"] if f["path"] == "README.md")
    assert "QuickBite is an agile food delivery platform" in readme
    assert "Browse curated local restaurants" in readme
    assert "http://localhost:3000" in readme
    assert "### Endpoints" in readme


@patch("agents.documentation_writer.call_agent", side_effect=RuntimeError("Gemini down"))
def test_generate_docs_graceful_fallback_when_llm_fails(mock_call_agent):
    from agents.documentation_writer import generate_docs

    output = generate_docs(SAMPLE_SPEC, SAMPLE_BACKEND_OUTPUT)

    validate_payload(output, DOCS_OUTPUT_SCHEMA)
    readme = next(f["content"] for f in output["files"] if f["path"] == "README.md")
    assert "QuickBite" in readme
    assert "http://localhost:3000" in readme
