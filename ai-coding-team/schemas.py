"""
JSON Schemas for AI Coding Team inter-agent handoffs.

Written for Groq's strict: true Structured Outputs (OpenAI-compatible
json_schema response_format, constrained decoding). As of writing, strict
mode is only supported on openai/gpt-oss-20b and openai/gpt-oss-120b -
strict=True is silently ignored on any other model.

Two rules make strict mode work:
  1. Every property must appear in "required" - there's no such thing as an
     optional key. If a value is genuinely optional, its type includes
     "null" instead (e.g. ["string", "null"]) and the model returns null.
  2. Every object must set "additionalProperties": False, so the model
     can't add extra keys we didn't ask for.

Each schema below is ONLY an agent's `payload` schema - not the full
envelope ({from_agent, to_agent, task_id, status, payload}). The envelope
is assembled by the orchestrator in plain Python after the LLM call
returns (see make_envelope), since from_agent/to_agent/task_id are known
before the call and status depends on whether the call succeeded. Making
the model generate that metadata would waste tokens for no benefit.

There's at least one community-reported case of Groq silently ignoring
strict:true and returning free-form text anyway. Don't trust the "100%
schema adherence" guarantee blindly - validate_payload() below checks
every response locally regardless. Treat a validation failure as an
agent failure to retry, the same as a QA failure.
"""

# ---------------------------------------------------------------------------
# Shared sub-schema
# ---------------------------------------------------------------------------

GENERATED_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["path", "content"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# 1. Project Manager -> {Backend Developer, Frontend Developer}
# ---------------------------------------------------------------------------

PM_SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "app_name": {"type": "string"},
        "app_description": {"type": "string"},
        "auth_required": {"type": "boolean"},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": ["string", "number", "boolean", "date", "reference"],
                                },
                                "required": {"type": "boolean"},
                                "references_entity": {"type": ["string", "null"]},
                            },
                            "required": ["name", "type", "required", "references_entity"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["name", "fields"],
                "additionalProperties": False,
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from_entity": {"type": "string"},
                    "to_entity": {"type": "string"},
                    "relationship_type": {
                        "type": "string",
                        "enum": ["one_to_many", "many_to_many", "one_to_one"],
                    },
                },
                "required": ["from_entity", "to_entity", "relationship_type"],
                "additionalProperties": False,
            },
        },
        "endpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                    "path": {"type": "string"},
                    "description": {"type": "string"},
                    "entity": {"type": "string"},
                    "requires_auth": {"type": "boolean"},
                },
                "required": ["method", "path", "description", "entity", "requires_auth"],
                "additionalProperties": False,
            },
        },
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "route": {"type": "string"},
                    "description": {"type": "string"},
                    "primary_entity": {"type": "string"},
                },
                "required": ["name", "route", "description", "primary_entity"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "app_name", "app_description", "auth_required",
        "entities", "relationships", "endpoints", "pages",
    ],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# 2. Backend Developer -> {Frontend Developer, QA Engineer}
# ---------------------------------------------------------------------------

REQUEST_BODY_FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "is_reference": {"type": "boolean"},
        "references_entity": {"type": ["string", "null"]},
    },
    "required": ["name", "is_reference", "references_entity"],
    "additionalProperties": False,
}

API_CONTRACT_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        "path": {"type": "string"},
        "request_body_fields": {"type": "array", "items": REQUEST_BODY_FIELD_SCHEMA},
        "response_shape_fields": {"type": "array", "items": {"type": "string"}},
        "requires_auth": {"type": "boolean"},
    },
    "required": ["method", "path", "request_body_fields", "response_shape_fields", "requires_auth"],
    "additionalProperties": False,
}
# request_body_fields carries is_reference/references_entity (response_shape_fields
# stays plain strings - it's for display only). Confirmed live: a plain string list
# gives Frontend Developer zero signal that a field like Order.restaurant must be a
# real Restaurant _id rather than free text, and it generated a text input that sent
# a restaurant NAME where the backend needed an ObjectId - a 400 on every submit.
# That's not a one-off mistake; a bare-string contract can't distinguish "type
# anything" from "must be an existing record's real id" for ANY reference field, on
# ANY page. See agents/frontend_developer.py's _reference_field_lookups for how this
# gets used to render a proper picker instead.

BACKEND_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
        "api_contract": {"type": "array", "items": API_CONTRACT_ENTRY_SCHEMA},
        "setup_notes": {"type": "string"},
    },
    "required": ["files", "api_contract", "setup_notes"],
    "additionalProperties": False,
}

# --- 2a. Sub-schemas for Backend Developer's internal per-entity + skeleton
# calls (agents/backend_developer.py). generate_backend() still returns
# something matching BACKEND_OUTPUT_SCHEMA above - these two are only used
# internally to keep each individual Groq call small enough to stay under
# Groq's free-tier tokens-per-minute limit, which a single call for an
# entire multi-entity app can exceed (seen directly: a 5-entity/15-endpoint
# spec needed ~10,760 tokens against an 8,000 TPM limit).

BACKEND_ENTITY_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
        "api_contract": {"type": "array", "items": API_CONTRACT_ENTRY_SCHEMA},
    },
    "required": ["files", "api_contract"],
    "additionalProperties": False,
}

BACKEND_SKELETON_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
        "setup_notes": {"type": "string"},
    },
    "required": ["files", "setup_notes"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# 3. Frontend Developer -> (final assembly)
# ---------------------------------------------------------------------------

FRONTEND_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
        "setup_notes": {"type": "string"},
    },
    "required": ["files", "setup_notes"],
    "additionalProperties": False,
}

# --- 3a. Sub-schemas for Frontend Developer's internal per-page + skeleton
# calls (agents/frontend_developer.py) - same reason as Backend Developer's
# split: a single call for a multi-page app can exceed Groq's free-tier
# TPM limit (seen directly: 11301 tokens requested against an 8000 limit
# for a 5-page/11-endpoint app). generate_frontend() still returns
# something matching FRONTEND_OUTPUT_SCHEMA above.

FRONTEND_PAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
    },
    "required": ["files"],
    "additionalProperties": False,
}

FRONTEND_SKELETON_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
        "setup_notes": {"type": "string"},
    },
    "required": ["files", "setup_notes"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# 4. QA Engineer -> Backend Developer (on failure) / orchestrator (on pass)
# ---------------------------------------------------------------------------

QA_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "all_tests_passed": {"type": "boolean"},
        "test_files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
        "failures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test_name": {"type": "string"},
                    "expected": {"type": "string"},
                    "actual": {"type": "string"},
                    "error_log": {"type": "string"},
                },
                "required": ["test_name", "expected", "actual", "error_log"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["all_tests_passed", "test_files", "failures"],
    "additionalProperties": False,
}
# "failures" is just [] when all_tests_passed is True - one flat shape,
# so the model never has to choose between two different response shapes.

# --- 4a. Sub-schema for QA Engineer's internal per-entity test-writing
# calls (agents/qa_engineer.py). Only the TEST FILE CONTENT is an LLM
# call - actually running the tests (npm install, spinning up an
# in-memory MongoDB, executing Jest, parsing results into
# QA_REPORT_SCHEMA above) is deterministic Python/subprocess work, not
# something an LLM call can do at all. The shared test infrastructure
# (mongodb-memory-server bootstrap, app-import helper, auth-token helper)
# is ALSO deterministic Python-templated code, not an LLM call - unlike
# Backend/Frontend's skeleton files, it doesn't depend on app-specific
# content, so there's no reason to spend a call (or risk sampling noise)
# generating something that's the same shape every time.

QA_ENTITY_TEST_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
    },
    "required": ["files"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# 5. Documentation Writer -> (final assembly)
# ---------------------------------------------------------------------------

DOCS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
    },
    "required": ["files"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Envelope - assembled by the orchestrator, NEVER generated by an LLM call
# ---------------------------------------------------------------------------

AGENT_NAMES = [
    "orchestrator",
    "project_manager",
    "backend_developer",
    "frontend_developer",
    "qa_engineer",
    "documentation_writer",
]

STATUSES = ["pending", "in_progress", "done", "failed"]


def make_envelope(from_agent: str, to_agent: str, task_id: str, status: str, payload: dict) -> dict:
    """Wrap an agent's payload in the standard envelope. Called by the
    orchestrator after an LLM call returns - never generated by the model."""
    assert from_agent in AGENT_NAMES, f"unknown agent: {from_agent}"
    assert to_agent in AGENT_NAMES, f"unknown agent: {to_agent}"
    assert status in STATUSES, f"unknown status: {status}"
    return {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "task_id": task_id,
        "status": status,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Local validation - don't rely on strict:true alone, see module docstring
# ---------------------------------------------------------------------------

def validate_payload(payload: dict, schema: dict) -> None:
    """Validate an LLM's payload against its expected schema locally.
    Raises jsonschema.exceptions.ValidationError if it doesn't match.
    Call this on every agent response even though we're using strict:true -
    treat a failure here the same way you'd treat a QA test failure."""
    from jsonschema import validate
    validate(instance=payload, schema=schema)


if __name__ == "__main__":
    # Self-test: confirm every schema above is well-formed, and that a
    # realistic example validates against PM_SPEC_SCHEMA. Run with:
    #   python schemas.py
    from jsonschema import Draft202012Validator

    all_schemas = {
        "PM_SPEC_SCHEMA": PM_SPEC_SCHEMA,
        "BACKEND_OUTPUT_SCHEMA": BACKEND_OUTPUT_SCHEMA,
        "BACKEND_ENTITY_OUTPUT_SCHEMA": BACKEND_ENTITY_OUTPUT_SCHEMA,
        "BACKEND_SKELETON_OUTPUT_SCHEMA": BACKEND_SKELETON_OUTPUT_SCHEMA,
        "FRONTEND_OUTPUT_SCHEMA": FRONTEND_OUTPUT_SCHEMA,
        "FRONTEND_PAGE_OUTPUT_SCHEMA": FRONTEND_PAGE_OUTPUT_SCHEMA,
        "FRONTEND_SKELETON_OUTPUT_SCHEMA": FRONTEND_SKELETON_OUTPUT_SCHEMA,
        "QA_REPORT_SCHEMA": QA_REPORT_SCHEMA,
        "QA_ENTITY_TEST_SCHEMA": QA_ENTITY_TEST_SCHEMA,
        "DOCS_OUTPUT_SCHEMA": DOCS_OUTPUT_SCHEMA,
    }
    for name, schema in all_schemas.items():
        Draft202012Validator.check_schema(schema)
        print(f"  OK  {name} is a well-formed JSON Schema")

    example_spec = {
        "app_name": "QuickBite",
        "app_description": "Users browse restaurants, place orders, and track delivery status.",
        "auth_required": True,
        "entities": [
            {"name": "User", "fields": [
                {"name": "name", "type": "string", "required": True, "references_entity": None},
                {"name": "email", "type": "string", "required": True, "references_entity": None},
            ]},
            {"name": "Restaurant", "fields": [
                {"name": "name", "type": "string", "required": True, "references_entity": None},
            ]},
            {"name": "Order", "fields": [
                {"name": "status", "type": "string", "required": True, "references_entity": None},
                {"name": "user", "type": "reference", "required": True, "references_entity": "User"},
                {"name": "restaurant", "type": "reference", "required": True, "references_entity": "Restaurant"},
            ]},
        ],
        "relationships": [
            {"from_entity": "User", "to_entity": "Order", "relationship_type": "one_to_many"},
            {"from_entity": "Restaurant", "to_entity": "Order", "relationship_type": "one_to_many"},
        ],
        "endpoints": [
            {"method": "POST", "path": "/orders", "description": "Create a new order", "entity": "Order", "requires_auth": True},
            {"method": "GET", "path": "/orders/:id", "description": "Get order status", "entity": "Order", "requires_auth": True},
        ],
        "pages": [
            {"name": "Restaurant List", "route": "/", "description": "Browse restaurants", "primary_entity": "Restaurant"},
            {"name": "Order Tracking", "route": "/orders/:id", "description": "Track an order", "primary_entity": "Order"},
        ],
    }
    validate_payload(example_spec, PM_SPEC_SCHEMA)
    print("  OK  example 'food delivery' spec validates against PM_SPEC_SCHEMA")
