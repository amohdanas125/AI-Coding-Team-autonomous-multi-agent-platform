"""Documentation Writer agent: takes the PM spec, Backend Developer's output
(api_contract, setup_notes), Frontend Developer's output, and QA Engineer's
report, and produces a complete, production-ready documentation package
(schemas.DOCS_OUTPUT_SCHEMA).

Follows Architecture Rule 1:
"Anything a program can compute, compute in Python rather than asking an LLM."
- The API Reference is generated DETERMINISTICALLY in Python from spec + api_contract.
- Setup steps (prerequisites, ports 3000 and 5173, env vars, seed.js, test scripts)
  are generated DETERMINISTICALLY in Python.
- LLM (Gemini) is used ONLY for prose descriptions (executive overview, feature
  breakdowns, architecture narrative).
- If QA attempts failed (needs_human_review=True), a clear warning banner is
  prominently displayed at the top of the documentation.
"""
import json
import os
import sys

from groq_client import call_agent
from schemas import DOCS_OUTPUT_SCHEMA, validate_payload

DOCS_PROSE_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "features": {
            "type": "array",
            "items": {"type": "string"},
        },
        "architecture_summary": {"type": "string"},
    },
    "required": ["overview", "features", "architecture_summary"],
    "additionalProperties": False,
}

PROSE_SYSTEM_PROMPT = """You are the Documentation Writer agent in an autonomous multi-agent software engineering team.
You are given the specification of a full-stack web application (Express + Mongoose + React + Vite).
Write high-quality, professional markdown documentation prose for the project.

Produce:
1. overview: A compelling 2-3 paragraph summary explaining what the application does, its target audience, and key value propositions.
2. features: A list of 4-8 bullet points highlighting the core functionalities (e.g. authentication, CRUD workflows, reference linking, UI experience).
3. architecture_summary: A concise explanation of how the Express backend and React frontend interact, security practices (JWT auth, password hashing, ownership checks), and data modeling.

Keep it technical, clear, and professional. Do NOT include setup commands or markdown tables - those will be generated deterministically and merged with your response."""


def _build_api_reference_markdown(spec: dict, api_contract: list) -> str:
    """Deterministically generate a complete Markdown API Reference from
    the PM spec and Backend api_contract. No LLM hallucinations or missing
    endpoints possible."""
    lines = [
        "## API Reference",
        "",
        "### Entities & Data Models",
        "",
    ]

    for entity in spec.get("entities", []):
        lines.append(f"#### `{entity['name']}`")
        lines.append("")
        lines.append("| Field | Type | Required | Reference Target |")
        lines.append("|---|---|---|---|")
        for field in entity.get("fields", []):
            ref = f"`{field['references_entity']}`" if field.get("references_entity") else "None"
            req = "Yes" if field.get("required") else "No"
            lines.append(f"| `{field['name']}` | `{field['type']}` | {req} | {ref} |")
        lines.append("")

    lines.append("### Endpoints")
    lines.append("")
    lines.append("| Method | Path | Auth Required | Request Body Fields | Response Fields | Description |")
    lines.append("|---|---|---|---|---|---|")

    spec_endpoints = {ep["path"]: ep for ep in spec.get("endpoints", [])}

    for ep in api_contract:
        method = ep.get("method", "GET")
        path = ep.get("path", "")
        auth = "Yes" if ep.get("requires_auth") else "No"
        
        # Format request body fields
        req_fields = ep.get("request_body_fields", [])
        if req_fields:
            rf_str = ", ".join(
                f"`{rf['name']}`" + (f" (ref `{rf['references_entity']}`)" if rf.get("is_reference") else "")
                for rf in req_fields
            )
        else:
            rf_str = "None"

        # Format response shape fields
        resp_fields = ep.get("response_shape_fields", [])
        resp_str = ", ".join(f"`{f}`" for f in resp_fields) if resp_fields else "Standard JSON / Array"

        # Lookup description from spec
        desc = spec_endpoints.get(path, {}).get("description", "-")

        lines.append(f"| `{method}` | `{path}` | {auth} | {rf_str} | {resp_str} | {desc} |")

    lines.append("")
    return "\n".join(lines)


def _build_setup_instructions_markdown(spec: dict, needs_human_review: bool = False) -> str:
    """Deterministically generate setup instructions with exact ports,
    environment variables, seeding, and test instructions."""
    app_name = spec.get("app_name", "app")
    auth_required = spec.get("auth_required", False)

    lines = []
    if needs_human_review:
        lines.extend([
            "> [!WARNING]",
            "> **QA Automated Verification Warning**: One or more test suites failed after 3 retry attempts.",
            "> The application requires human code review and manual testing before production deployment.",
            "",
        ])

    lines.extend([
        "## Setup & Installation",
        "",
        "### Prerequisites",
        "- **Node.js** (v18.0.0 or higher recommended)",
        "- **npm** (v9.0.0 or higher)",
        "- **MongoDB** running locally (`mongodb://localhost:27017`) or a MongoDB Atlas connection string",
        "",
        "### Port Allocation",
        "- **Backend Server**: `http://localhost:3000`",
        "- **Frontend Client**: `http://localhost:5173`",
        "",
        "### 1. Backend Setup",
        "```bash",
        "cd backend",
        "npm install",
        "```",
        "",
        "Create a `.env` file in the `backend/` directory:",
        "```ini",
        "PORT=3000",
        f"MONGODB_URI=mongodb://localhost:27017/{app_name.lower()}_db",
    ])

    if auth_required:
        lines.extend([
            "JWT_SECRET=your_super_secret_jwt_key_change_in_production",
        ])

    lines.extend([
        "```",
        "",
        "Start the backend server:",
        "```bash",
        "npm start",
        "```",
        "",
        "Seed sample initial data (in a separate terminal inside `backend/`):",
        "```bash",
        "node seed.js",
        "```",
        "",
        "Run automated tests (Jest + Supertest + in-memory MongoDB):",
        "```bash",
        "npm test",
        "```",
        "",
        "### 2. Frontend Setup",
        "```bash",
        "cd frontend",
        "npm install",
        "npm run dev",
        "```",
        "Open your browser and navigate to `http://localhost:5173`.",
        "",
    ])

    return "\n".join(lines)


def _build_fallback_prose(spec: dict) -> dict:
    """Fallback prose generator if LLM call is unavailable or fails."""
    app_name = spec.get("app_name", "Application")
    app_desc = spec.get("app_description", "A full-stack CRUD web application.")
    entities = [e["name"] for e in spec.get("entities", [])]

    features = [
        f"Full CRUD capabilities for primary entities: {', '.join(entities)}.",
        "RESTful API design with Express.js and Mongoose ODM.",
        "Interactive Single-Page Application (SPA) frontend built with React and Vite.",
    ]
    if spec.get("auth_required"):
        features.append("JWT-based user authentication with bcrypt password hashing and ownership-scoped access.")

    return {
        "overview": f"# {app_name}\n\n{app_desc}\n\nBuilt by the AI Coding Team multi-agent system.",
        "features": features,
        "architecture_summary": (
            f"The application features a decoupled architecture with an Express.js REST API "
            f"persisting data to MongoDB via Mongoose, and a fast React frontend bundled with Vite. "
            f"Entity models enforce schema validation and cross-entity reference consistency."
        ),
    }


def generate_docs(
    spec: dict,
    backend_output: dict,
    frontend_output: dict | None = None,
    qa_report: dict | None = None,
    needs_human_review: bool = False,
) -> dict:
    """Generate comprehensive project documentation adhering to DOCS_OUTPUT_SCHEMA.

    Combines an LLM call (Gemini) for prose summaries with deterministic
    Python generators for the API reference and setup guides.
    """
    app_name = spec.get("app_name", "Application")
    api_contract = backend_output.get("api_contract", [])

    # 1. Fetch prose from LLM with defensive fallback
    prose = None
    try:
        user_prompt = json.dumps({
            "app_name": app_name,
            "app_description": spec.get("app_description", ""),
            "auth_required": spec.get("auth_required", False),
            "entities": [e["name"] for e in spec.get("entities", [])],
            "endpoints_count": len(api_contract),
        }, indent=2)
        prose = call_agent(
            system_prompt=PROSE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema=DOCS_PROSE_SCHEMA,
            schema_name="docs_prose_output",
            max_tokens=2000,
        )
    except Exception:
        prose = _build_fallback_prose(spec)

    if not prose or "overview" not in prose:
        prose = _build_fallback_prose(spec)

    # 2. Build deterministic sections
    setup_md = _build_setup_instructions_markdown(spec, needs_human_review=needs_human_review)
    api_ref_md = _build_api_reference_markdown(spec, api_contract)

    # 3. Assemble README.md
    features_md = "\n".join(f"- {f}" for f in prose.get("features", []))
    readme_content = f"""# {app_name}

{prose.get("overview", "")}

## Features
{features_md}

## Architecture Overview
{prose.get("architecture_summary", "")}

{setup_md}

{api_ref_md}
"""

    output = {
        "files": [
            {"path": "README.md", "content": readme_content.strip() + "\n"},
            {"path": "API_REFERENCE.md", "content": f"# {app_name} - API Reference\n\n" + api_ref_md.strip() + "\n"},
        ]
    }

    validate_payload(output, DOCS_OUTPUT_SCHEMA)
    return output
