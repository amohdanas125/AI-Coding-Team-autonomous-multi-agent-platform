"""Backend Developer agent: takes a PM-generated spec (schemas.PM_SPEC_SCHEMA)
and generates a working Express + Mongoose backend (schemas.BACKEND_OUTPUT_SCHEMA).

Internally makes ONE Groq call per entity plus ONE "skeleton" call, instead
of a single call for the whole backend. A single big call hits Groq's
free-tier TPM (tokens-per-minute) limit on larger specs - seen directly:
"Limit 8000, Requested 10760" for a real 5-entity/15-endpoint spec.
generate_backend()'s external signature and return shape are UNCHANGED by
this - callers (orchestrator/graph.py, scripts/test_backend_agent.py) don't
need to know or care that this happens internally.

SEEDING: each entity's call also returns `seed_records` - a few realistic
sample values for that entity's own non-reference fields. This piggybacks
on the existing per-entity call (same Groq request, extended schema) rather
than adding a whole new call per entity, so it costs no extra free-tier
budget. Reference fields are deliberately NOT asked of the model - a model
has no way to know another entity's real _id at this point in generation,
and asking it to invent one would produce IDs that don't exist. Instead,
generate_backend() assembles all entities' seed_records into seed.js -
plain Python-generated JS, not itself LLM-written - which inserts entities
in dependency order and fills in reference fields with the real _id of an
already-inserted record. This mirrors the same "don't trust the model for
code correctness, only content" split used throughout this project (see
schemas.py's validate_payload docstring for the same philosophy applied to
schema adherence).

KNOWN LIMITATION (deliberate, not an oversight): on a QA-triggered retry,
orchestrator/graph.py currently calls generate_backend() again in full,
not the "regenerate only the failing piece" behavior the master prompt
specifies. Deferred to Phase 4 - see that module's docstring for why.
"""
import json
import os
import shutil
import subprocess
import tempfile

from groq_client import call_agent
from schemas import BACKEND_ENTITY_OUTPUT_SCHEMA, BACKEND_SKELETON_OUTPUT_SCHEMA

ENTITY_SYSTEM_PROMPT = """You are the Backend Developer agent in a multi-agent system that builds small CRUD web apps. You will be given ONE entity from a larger app spec - its fields and its endpoints - plus whether the whole app requires auth. Generate the Mongoose model and Express router for THIS entity only. Never invent scope beyond what's given.

Tech stack - use exactly this, no substitutions:
- Express.js for routing, Mongoose for the model
- bcrypt for password hashing and jsonwebtoken for issuing tokens - ONLY if this entity's own endpoints clearly include registration or login (e.g. paths containing "register" or "login"). Most entities don't need this.
- Standard Node.js CommonJS (require/module.exports), not ES modules

Files to produce, exactly these two paths:
- models/<EntityName>.js - the Mongoose schema for this entity. A "reference" field becomes `{ type: mongoose.Schema.Types.ObjectId, ref: '<ReferencedEntity>' }`, using the entity name given in that field's references_entity. Never add an explicit id field - MongoDB provides _id automatically. If this entity has a password field and a register/login endpoint, hash it before save (e.g. a pre('save') hook) - never store it in plaintext.
- routes/{route_filename}.js - use the EXACT route_filename value given in the input, not your own derivation from the entity name - this must match byte-for-byte what the separately-generated server.js will require(), so don't rename, pluralize, or re-case it. An Express Router implementing EXACTLY the endpoints given, using their FULL absolute paths exactly as given (a given path of "/orders/:id" means router.get('/orders/:id', ...), NOT router.get('/:id', ...) - these routers are mounted at the application root, not under a per-entity prefix, so relative paths resolve to the wrong URL). If any endpoint needs auth (requires_auth: true), `const auth = require('../middleware/auth');` and use it as middleware - that file exists even though you don't generate it yourself.

Critical security rule - this is the most important part of your job:
requires_auth: true on an endpoint means "must be logged in" - it does NOT mean the endpoint is safely scoped, and this system has no admin/staff role. If this entity is owned by a specific user (has a "reference" field pointing at what is clearly a User/Member/Customer-type entity): list/get endpoints must filter by req.userId (set by the auth middleware) - never return another user's records, and never accept a user id from the request body or query string as the filter. Update/delete endpoints must load the record first and verify its owning reference matches req.userId before modifying it - respond 403 if it doesn't match, 404 if the record doesn't exist. An :id in the URL is never sufficient authorization by itself.

If this entity has a register/login-style endpoint: hash passwords with bcrypt, never store or return plaintext passwords, and issue a JWT containing the user's id (as { userId: ... }) on successful login, reading the secret from process.env.JWT_SECRET only - never hardcode a fallback like 'secretkey'.

api_contract: after writing the router, describe what you actually built - one entry per endpoint you implemented. For request_body_fields, describe each field as {name, is_reference, references_entity}: set is_reference true and references_entity to the target entity's name for any field the client must supply as another document's real _id (any field with type "reference" on this entity); set is_reference false and references_entity null for everything else. response_shape_fields stays a plain list of field name strings. This must match your code exactly, since the Frontend Developer agent builds against this contract, not your source, and needs to know which fields require picking a real record rather than typing free text.

seed_records: separately from the code files, also generate EXACTLY 2 realistic sample values for THIS entity's own fields, for a data-seeding script that runs after your code (you don't write that script - just supply values). Keep this small and simple on purpose - only include the non-reference fields you were given, never invent a reference field's value (another entity's real ID isn't known yet, it's resolved outside your response), never include _id, and never include password_hash-style derived fields (a plaintext password field is fine - it will be hashed automatically when inserted through your model's pre('save') hook). Make the 2 values realistic and clearly distinct from each other, not placeholder text like 'string1' or 'sample name'.

If previous_qa_failures is provided, carefully review the automated test failure messages and error logs from the previous attempt and fix the exact bug in this entity's router or model (e.g. status codes, query filters, reference handling, or missing fields).

Keep it minimal and correct over impressive. If something is ambiguous, make the simplest reasonable choice."""

SKELETON_SYSTEM_PROMPT = """You are the Backend Developer agent, generating the shared skeleton files for a small CRUD web app - NOT any entity's model or routes, those already exist as separately generated files at each path listed in route_filenames.

Tech stack - use exactly this, no substitutions:
- Express.js, Mongoose, dotenv, cors
- bcrypt + jsonwebtoken as dependencies only if auth_required is true
- Standard Node.js CommonJS (require/module.exports), not ES modules

Files to produce - use exactly these paths, one entry in `files` per file:
- package.json - dependencies: express, mongoose, dotenv, cors, and (only if auth_required) bcrypt and jsonwebtoken. A "start" script that runs server.js.
- app.js - creates the Express app and mounts everything on it, but does NOT connect to MongoDB and does NOT call app.listen(). Enable CORS first (const cors = require('cors'); app.use(cors());) then app.use(express.json()) so request bodies parse. Mount EVERY router at the application ROOT - app.use('/', require('./routes/<n>')) for each name in route_filenames given (these are exact, pre-computed filenames - use them exactly as given, do not re-derive your own from anything else) - since each router already defines its own full absolute paths. End with module.exports = app; - this file must be requireable and testable on its own without opening a real network port, which is why the database connection and app.listen() live in server.js instead.
- server.js - the FIRST line must be require('dotenv').config(), before anything reads process.env. Then connect to MongoDB via process.env.MONGODB_URI. Then const app = require('./app'); and app.listen(process.env.PORT || 3000, ...) with a console.log confirming the port.
- middleware/auth.js - ONLY if auth_required is true. Exports a function that verifies a JWT from the Authorization header (format "Bearer <token>") and attaches the decoded userId to req.userId, or responds 401 if the header is missing or the token is invalid. Read the secret from process.env.JWT_SECRET only - never hardcode a fallback like 'secretkey'; if it's missing, throw at startup with a clear message instead of silently using a weak default.

setup_notes: a short string - anything a developer should know before running this (e.g. required env vars).

Write every JavaScript file as normal, readable code - one statement per line, standard indentation, never minified or compressed onto a single line, where one mismatched bracket is easy to make and hard to spot.

Keep it minimal and correct. If something is ambiguous, make the simplest reasonable choice and note it in setup_notes."""

def _route_filename(entity_name: str) -> str:
    """Deterministic route filename for an entity - computed ONCE here in
    Python and given explicitly to both generate_entity_backend (which
    generates the file at this path) and generate_backend_skeleton (which
    require()s it), so the two independently-generated LLM calls can't
    disagree on the name. Confirmed live: leaving this to each call to
    derive on its own from a text instruction ("entity-name-lowercase")
    let them actually disagree - server.js ended up require()ing a file
    the entity call had named slightly differently, a MODULE_NOT_FOUND
    crash on startup. Same fix as seed.js's dependency ordering: don't
    trust two separate model calls to independently derive the same
    string identically - compute it once, tell both."""
    return entity_name.lower()


def _enforce_route_filename(files: list, expected_path: str) -> list:
    """Defense in depth on top of _route_filename: telling the model the
    exact filename fixes this most of the time, but a model can still
    ignore instructions. If the expected path isn't present, find
    whatever routes/*.js file the model DID produce and rename it -
    cheap insurance against a repeat of the exact crash this exists to
    prevent, without another Groq call."""
    if any(f["path"] == expected_path for f in files):
        return files
    for f in files:
        if f["path"].startswith("routes/") and f["path"].endswith(".js"):
            f["path"] = expected_path
            break
    return files

# Field type -> JSON Schema type, used to build each entity's seed_records
# schema dynamically (unlike the static schemas in schemas.py, this must
# vary per entity since every entity has different fields).
_FIELD_TYPE_TO_JSON_TYPE = {
    "string": "string",
    "number": "number",
    "boolean": "boolean",
    "date": "string",  # ISO date string, not a native JSON Schema date type
}


def _build_entity_schema(entity: dict) -> dict:
    """Extend the static BACKEND_ENTITY_OUTPUT_SCHEMA with a seed_records
    property whose item shape matches THIS entity's own non-reference
    fields. Deep-copies rather than mutating the shared static schema
    (see gemini_client.py's _to_gemini_schema for the same precaution -
    mutating a shared schema object in place would corrupt other call
    sites in the same process)."""
    seed_field_props = {}
    seed_required = []
    for field in entity["fields"]:
        if field["type"] == "reference":
            continue
        seed_field_props[field["name"]] = {"type": _FIELD_TYPE_TO_JSON_TYPE[field["type"]]}
        seed_required.append(field["name"])

    seed_record_schema = {
        "type": "object",
        "properties": seed_field_props,
        "required": seed_required,
        "additionalProperties": False,
    }

    schema = json.loads(json.dumps(BACKEND_ENTITY_OUTPUT_SCHEMA))  # deep copy
    schema["properties"]["seed_records"] = {
        "type": "array",
        "items": seed_record_schema,
        "minItems": 2,
        "maxItems": 2,
    }
    schema["required"].append("seed_records")
    return schema


def _topological_order(entities: list) -> list:
    """Order entities so any entity referenced by another comes first -
    needed so seed.js can insert e.g. Restaurant before MenuItem and know
    real _ids to fill MenuItem.restaurant with. Falls back to appending
    whatever's left if a circular reference is somehow present, rather
    than looping forever."""
    ordered = []
    scheduled = set()
    remaining = {e["name"]: e for e in entities}
    while remaining:
        progress = False
        for name, entity in list(remaining.items()):
            refs = [f["references_entity"] for f in entity["fields"] if f["type"] == "reference"]
            if all(r in scheduled for r in refs):
                ordered.append(entity)
                scheduled.add(name)
                del remaining[name]
                progress = True
        if not progress:
            ordered.extend(remaining.values())
            break
    return ordered


def _build_seed_script(entities_ordered: list, seed_data: dict) -> str:
    """Deterministically assemble seed.js from each entity's seed_records.
    Plain Python string-building, NOT an LLM call - the insertion order
    and reference-resolution logic below can't have the kind of bugs a
    freeform code-generation call could, since it's the same template
    every time regardless of app content."""
    lines = [
        "/**",
        " * Auto-generated by the Backend Developer agent - seeds sample data for",
        " * every entity via Mongoose, in dependency order (referenced entities",
        " * first). The insertion logic here is plain generated JS, not itself",
        " * LLM-written - only the sample field VALUES inside came from the model.",
        " *",
        " * Safe to run more than once - clears each entity's collection first.",
        " *",
        " *   node seed.js",
        " */",
        "const mongoose = require('mongoose');",
        "require('dotenv').config();",
        "",
    ]
    for entity in entities_ordered:
        lines.append(f"const {entity['name']} = require('./models/{entity['name']}');")
    lines += [
        "",
        "const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/app';",
        "",
        "// No connect() or disconnect() in here - this function assumes a mongoose",
        "// connection is already open, so tests/qa-engineer.js can call it directly",
        "// against an in-memory MongoDB without duplicating connection lifecycle code.",
        "async function seedDatabase() {",
    ]
    for entity in entities_ordered:
        lines.append(f"  await {entity['name']}.deleteMany({{}});")
    lines.append("")
    for entity in entities_ordered:
        lines.append(f"  const created{entity['name']} = [];")
    lines.append("")

    for entity in entities_ordered:
        name = entity["name"]
        records = seed_data.get(name, [])
        ref_fields = [f for f in entity["fields"] if f["type"] == "reference"]

        lines.append(f"  // --- {name} ---")
        lines.append(f"  const {name.lower()}Records = {json.dumps(records, indent=2)};")
        for rf in ref_fields:
            ref_entity = rf["references_entity"]
            lines.append(f"  if (created{ref_entity}.length === 0) {{")
            lines.append(
                f"    throw new Error('No {ref_entity} records available to reference for "
                f"{name}.{rf['name']} - seed data generation produced none.');"
            )
            lines.append("  }")
        lines.append(f"  for (const rec of {name.lower()}Records) {{")
        lines.append("    const doc = { ...rec };")
        for rf in ref_fields:
            ref_entity = rf["references_entity"]
            lines.append(
                f"    doc.{rf['name']} = created{ref_entity}"
                f"[Math.floor(Math.random() * created{ref_entity}.length)]._id;"
            )
        lines.append(f"    const saved = await {name}.create(doc);")
        lines.append(f"    created{name}.push(saved);")
        lines.append(f"    console.log(`  Created {name}: ${{saved._id}}`);")
        lines.append("  }")
        lines.append("")

    lines += [
        "}",
        "",
        "module.exports = { seedDatabase };",
        "",
        "if (require.main === module) {",
        "  (async () => {",
        "    console.log(`Connecting to ${MONGODB_URI} ...`);",
        "    await mongoose.connect(MONGODB_URI);",
        "    console.log('Connected.');",
        "    await seedDatabase();",
        "    console.log('\\nSeed complete.');",
        "    await mongoose.disconnect();",
        "    process.exit(0);",
        "  })().catch((err) => {",
        "    console.error('Seed failed:', err);",
        "    process.exit(1);",
        "  });",
        "}",
    ]
    return "\n".join(lines)


def _js_syntax_errors(files: list) -> list:
    """Run `node --check` on every .js file in a generated file list and
    return [(path, error_text), ...] for any that fail. Returns [] if node
    isn't on PATH - a missing tool must never block generation, it just
    means this safety net isn't available on that machine.

    Confirmed live: server.js came back minified onto one line with a
    single wrong bracket (`${PORT}`}` instead of `${PORT}`)`). Nothing
    in schemas.py can catch that - the schema only knows file content is
    *a string* - so it surfaced only after generation, in the live test
    script's own node --check pass."""
    node_path = shutil.which("node")
    if node_path is None:
        return []
    errors = []
    with tempfile.TemporaryDirectory(prefix="js-check-") as tmp:
        for f in files:
            if not f["path"].endswith(".js"):
                continue
            target = os.path.join(tmp, f["path"])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(f["content"])
            result = subprocess.run([node_path, "--check", target], capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                errors.append((f["path"], result.stderr.strip()[-500:]))
    return errors


def generate_entity_backend(
    entity: dict,
    entity_endpoints: list,
    auth_required: bool,
    failure_notes: str | None = None,
    max_attempts: int = 3,
) -> dict:
    """Generate one entity's model + router + seed_records. Internal
    helper - see generate_backend() for the public interface.
    Validates and retries on JavaScript syntax errors (Task F)."""
    route_filename = _route_filename(entity["name"])
    expected_route_path = f"routes/{route_filename}.js"
    payload = {
        "entity": entity,
        "endpoints": entity_endpoints,
        "auth_required": auth_required,
        "route_filename": route_filename,
    }
    if failure_notes:
        payload["previous_qa_failures"] = failure_notes

    user_prompt = json.dumps(payload, indent=2)
    schema = _build_entity_schema(entity)
    last_problem = None
    for attempt in range(max_attempts):
        result = call_agent(
            system_prompt=ENTITY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema=schema,
            schema_name="backend_entity_output",
            max_tokens=3500,  # bumped from 3000 - seed_records adds a bit more content
        )
        result["files"] = _enforce_route_filename(result["files"], expected_route_path)
        syntax_errors = _js_syntax_errors(result["files"])
        if not syntax_errors:
            return result
        last_problem = "\n".join(f"{p}: {err}" for p, err in syntax_errors)
        if attempt < max_attempts - 1:
            print(f"  [entity {entity['name']} JS syntax error, retrying {attempt + 2}/{max_attempts}: {syntax_errors[0][0]}]")

    raise ValueError(
        f"Backend Developer could not generate valid JavaScript for entity {entity['name']} after {max_attempts} attempts:\n{last_problem}"
    )


def generate_backend_skeleton(app_name: str, auth_required: bool, entity_names: list, max_attempts: int = 3) -> dict:
    """Generate the shared package.json/app.js/server.js/middleware files.
    Internal helper - see generate_backend() for the public interface.

    Validates and retries on two failure modes that both pass schema
    validation, since the schema only knows each file's content is *a
    string*: (1) package.json whose content isn't valid JSON - which also
    makes `node --check` fail on EVERY file in the directory with a
    misleading ERR_INVALID_PACKAGE_CONFIG, since node reads package.json
    first - and (2) any generated .js file with a syntax error."""
    route_filenames = [_route_filename(name) for name in entity_names]
    user_prompt = json.dumps(
        {"app_name": app_name, "auth_required": auth_required, "route_filenames": route_filenames},
        indent=2,
    )
    last_problem = None
    for attempt in range(max_attempts):
        result = call_agent(
            system_prompt=SKELETON_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema=BACKEND_SKELETON_OUTPUT_SCHEMA,
            schema_name="backend_skeleton_output",
            max_tokens=3000,
        )
        problems = []
        package_json_file = next((f for f in result["files"] if f["path"] == "package.json"), None)
        if package_json_file is None:
            problems.append("(no package.json file was present at all)")
        else:
            try:
                json.loads(package_json_file["content"])
            except json.JSONDecodeError:
                problems.append(f"package.json isn't valid JSON:\n{package_json_file['content']}")
        for path, error_text in _js_syntax_errors(result["files"]):
            problems.append(f"{path} has a JavaScript syntax error:\n{error_text}")

        if not problems:
            return result
        last_problem = "\n\n".join(problems)
        if attempt < max_attempts - 1:
            print(f"  [skeleton had problems, retrying generation {attempt + 2}/{max_attempts}: "
                  f"{problems[0].splitlines()[0]}]")

    raise ValueError(
        "Backend Developer's skeleton call couldn't produce a valid package.json and "
        f"syntactically valid JavaScript files, even after {max_attempts} attempts.\n"
        f"Last attempt's problems:\n{last_problem}"
    )


def _map_failure_to_entity(failure: dict, entities: list) -> str | None:
    """Map a single QA test failure to its owning entity name.
    Returns None if the failure cannot be clearly mapped (e.g. global crash)."""
    test_name = failure.get("test_name", "")
    error_log = failure.get("error_log", "")

    # Global or environmental failures that cannot be attributed to a single entity
    if any(k in test_name.lower() for k in ["npm install", "jest run", "helpers.js"]):
        return None

    # Check for test file markers in test_name, e.g. [tests/order.test.js] or [order.test.js]
    for entity in entities:
        rf = _route_filename(entity["name"])  # e.g. "order"
        if f"tests/{rf}.test.js" in test_name.lower() or f"[{rf}.test.js]" in test_name.lower():
            return entity["name"]

    # Check for test file markers in error_log
    for entity in entities:
        rf = _route_filename(entity["name"])
        if f"tests/{rf}.test.js" in error_log.lower() or f"{rf}.test.js" in error_log.lower():
            return entity["name"]

    # Check for entity name in test_name
    for entity in entities:
        name = entity["name"]
        if f" {name} " in test_name or test_name.startswith(f"{name} ") or f"] {name} " in test_name or f"[{name}]" in test_name:
            return name

    return None


def find_failing_entities(qa_report: dict | None, entities: list) -> list[str] | None:
    """Identify which entities failed according to the QA report.
    Returns a list of entity names if all failures can be cleanly mapped to entities.
    Returns None if any failure has no owning entity (e.g. npm install failure,
    jest crash, or unmapped file), which triggers a full regeneration fallback."""
    if not qa_report or qa_report.get("all_tests_passed"):
        return None

    failures = qa_report.get("failures", [])
    if not failures:
        return None

    failing = set()
    for failure in failures:
        entity_name = _map_failure_to_entity(failure, entities)
        if entity_name is None:
            # Cannot map cleanly -> fall back to full regeneration
            return None
        failing.add(entity_name)

    return sorted(list(failing))


def _extract_seed_data_from_script(script_content: str, entity_name: str) -> list:
    """Extract sample seed records for an entity from an already-generated seed.js."""
    import re
    var_name = f"{entity_name.lower()}Records"
    pattern = rf"const\s+{var_name}\s*=\s*(\[[\s\S]*?\]);"
    match = re.search(pattern, script_content)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    return []


def generate_backend(
    spec: dict,
    qa_report: dict | None = None,
    previous_output: dict | None = None,
) -> dict:
    """Generate a full backend from a PM spec. Returns a dict shaped like
    schemas.BACKEND_OUTPUT_SCHEMA.

    SURGICAL RETRY (Task D): If qa_report and previous_output are supplied
    and the test failures map cleanly to specific entities (e.g. Order route
    failure), only those failing entities are regenerated with failure logs
    passed into their prompts. Non-failing entities and skeleton files are
    reused from previous_output. If failures cannot be isolated (e.g. npm install
    or Jest crash), it safely falls back to a full regeneration.
    """
    entities = spec["entities"]
    failing_entities = find_failing_entities(qa_report, entities) if (qa_report and previous_output) else None

    # Surgical retry path:
    if failing_entities and previous_output:
        all_files = []
        all_contract = []
        seed_data = {}

        # 1. Reuse skeleton files from previous output
        skeleton_files = [
            f for f in previous_output["files"]
            if f["path"] in ["package.json", "app.js", "server.js", "middleware/auth.js"]
        ]
        all_files.extend(skeleton_files)

        # 2. Extract existing seed script to recover non-failing entities' seed data
        prev_seed_file = next((f for f in previous_output["files"] if f["path"] == "seed.js"), None)
        prev_seed_content = prev_seed_file["content"] if prev_seed_file else ""

        spec_entity_by_path = {ep["path"]: ep["entity"] for ep in spec["endpoints"]}

        for entity in entities:
            entity_name = entity["name"]
            route_fn = _route_filename(entity_name)
            entity_endpoints = [e for e in spec["endpoints"] if e["entity"] == entity_name]

            if entity_name in failing_entities:
                entity_failures = [
                    f for f in qa_report["failures"]
                    if _map_failure_to_entity(f, entities) == entity_name
                ]
                failure_text = "\n".join(
                    f"- {f.get('test_name', '')}:\n{f.get('error_log', '')}"
                    for f in entity_failures
                )
                result = generate_entity_backend(
                    entity,
                    entity_endpoints,
                    spec["auth_required"],
                    failure_notes=failure_text,
                )
                all_files.extend(result["files"])
                all_contract.extend(result["api_contract"])
                seed_data[entity_name] = result["seed_records"]
            else:
                expected_model = f"models/{entity_name}.js"
                expected_route = f"routes/{route_fn}.js"
                existing_entity_files = [
                    f for f in previous_output["files"]
                    if f["path"] in [expected_model, expected_route]
                ]
                all_files.extend(existing_entity_files)

                existing_contract = [
                    c for c in previous_output["api_contract"]
                    if spec_entity_by_path.get(c["path"]) == entity_name
                ]
                all_contract.extend(existing_contract)

                seed_data[entity_name] = _extract_seed_data_from_script(prev_seed_content, entity_name)

        entities_ordered = _topological_order(entities)
        seed_script = _build_seed_script(entities_ordered, seed_data)
        all_files.append({"path": "seed.js", "content": seed_script})

        return {
            "files": all_files,
            "api_contract": all_contract,
            "setup_notes": previous_output.get("setup_notes", ""),
        }

    # Full generation path (initial run or fallback)
    all_files = []
    all_contract = []
    seed_data = {}

    for entity in entities:
        entity_endpoints = [e for e in spec["endpoints"] if e["entity"] == entity["name"]]
        result = generate_entity_backend(entity, entity_endpoints, spec["auth_required"])
        all_files.extend(result["files"])
        all_contract.extend(result["api_contract"])
        seed_data[entity["name"]] = result["seed_records"]

    entity_names = [e["name"] for e in entities]
    skeleton = generate_backend_skeleton(spec["app_name"], spec["auth_required"], entity_names)
    all_files.extend(skeleton["files"])

    entities_ordered = _topological_order(entities)
    seed_script = _build_seed_script(entities_ordered, seed_data)
    all_files.append({"path": "seed.js", "content": seed_script})

    setup_notes = skeleton["setup_notes"] + " Run `node seed.js` after `npm install` to populate sample data."

    return {
        "files": all_files,
        "api_contract": all_contract,
        "setup_notes": setup_notes,
    }
