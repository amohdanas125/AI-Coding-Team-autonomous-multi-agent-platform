"""QA Engineer agent: takes the PM spec and Backend Developer's output
(schemas.BACKEND_OUTPUT_SCHEMA) and produces a QA_REPORT_SCHEMA-shaped
report - the first agent in this project that ACTUALLY EXECUTES generated
code rather than only generating it. Project Manager, Backend Developer,
and Frontend Developer are pure LLM-generation functions; this one makes
one LLM call per entity to write Jest/Supertest test file content, then
does real, non-LLM work: writes the backend's files plus the generated
tests into a temp sandbox directory, runs `npm install`, boots an
in-memory MongoDB, runs the tests with Jest, and parses the real JSON
test-run output into failures - none of that is something an LLM call
can do, only a subprocess can.

SHARED TEST INFRASTRUCTURE (tests/helpers.js, jest.config.js) is
deterministic Python-templated code, NOT an LLM call - unlike Backend/
Frontend's skeleton files, it doesn't depend on app-specific content
(the in-memory MongoDB bootstrap and app-import logic are identical
regardless of what the app actually does), so there's no reason to spend
tokens or risk sampling noise generating something that's the same shape
every time. It reuses generate_backend()'s seed.js output directly (its
seedDatabase() export) rather than inventing separate test fixtures -
same dependency-ordered, cross-referenced sample data Backend Developer
already produces.

EXECUTION CAVEAT, same honesty as every other agent in this project: the
sandbox that built this could install jest/supertest/mongodb-memory-server
themselves (see tests/test_qa_engineer.py's node --check verification),
but could NOT run a full end-to-end generate_qa_report() call against a
live-generated backend - that needs a real GROQ_API_KEY (for Backend
Developer) plus mongodb-memory-server's first-run MongoDB binary download,
which needs network access this sandbox doesn't have to that specific
download host. Run scripts/test_qa_agent.py yourself to verify the real
execution path end to end.

KNOWN LIMITATION, deliberate: when QA fails, orchestrator/graph.py still
sends the ENTIRE spec back to generate_backend() for a full regeneration,
not a surgical "fix only the failing entity" pass, even though Jest's
JSON output DOES identify which test FILE (and therefore which entity)
failed. Wiring that up is a real, valuable next step, deliberately left
for its own pass rather than bundled into getting execution working at
all in the first place.
"""
import json
import os
import shutil
import subprocess
import tempfile

from groq_client import call_agent
from schemas import QA_ENTITY_TEST_SCHEMA

ENTITY_TEST_SYSTEM_PROMPT = """You are the QA Engineer agent in a multi-agent system that builds small CRUD web apps. You will be given ONE entity's own endpoints - taken from the Backend Developer's actual api_contract, not the original spec, since api_contract reflects what was really implemented - plus whether an authenticated test helper is available. Write a Jest + Supertest test file for THIS entity's endpoints only.

Tech stack - use exactly this, no substitutions:
- Jest as the test runner, supertest for HTTP-style assertions made directly against the Express app object (no real network port is opened).
- Import shared test infrastructure from './helpers': const { app, request, startTestDb, stopTestDb[, getAuthToken] } = require('./helpers'); - never write your own MongoDB connection or app-boot logic, that already exists and works.
- Always invoke supertest using request(app).<method>(path), e.g. await request(app).get('/items').
- Import this entity's own Mongoose model directly (e.g. const Restaurant = require('../models/Restaurant');) ONLY if you need to look up a real seeded record's _id for a reference field - never invent a fake ObjectId string, the seeded test data is real and queryable via the model.

File to produce, exactly this one path:
- tests/<entity-name-lowercase>.test.js

Structure:
- beforeAll(async () => { await startTestDb(); }, 180000); and afterAll(async () => { await stopTestDb(); }, 60000); - the generous 180-second timeout matters, since starting the in-memory MongoDB can be slow on its very first run (it downloads the database binary).
- One describe block for this entity.
- For each GET endpoint with no :id segment (a list endpoint) in the given endpoints: a test that requests it with await request(app).get(path) (attach an Authorization: Bearer <token> header from await getAuthToken() first, only if requires_auth is true AND getAuthToken is available) and expects a 200 status with an array response body.
- For each POST endpoint in the given endpoints: build the request body using the EXACT field names from that endpoint's request_body_fields. For any field with is_reference: true, query that field's references_entity's own Mongoose model with findOne() to get a real _id from the seeded data - never a hardcoded fake id. For every other field, use any plausible value of a matching type. Send it with await request(app).post(path).send(body) with an auth header if requires_auth is true and getAuthToken is available. Expect a 2xx status (expect(res.status).toBeGreaterThanOrEqual(200); expect(res.status).toBeLessThan(300);).
- For DELETE endpoints: send with await request(app).delete(path). Expect a 2xx status (either 200 or 204).
- If an endpoint's requires_auth is true but getAuthToken is NOT available, skip writing a test for that one endpoint rather than guessing at authentication.

Keep it minimal and correct - a few solid, passing tests beat many flaky or wrong ones. If a request field's correct type or shape is ambiguous, make the simplest reasonable choice. Never backslash-escape single quotes inside string literals (write 'hello', never \\'hello\\'). The output must be strictly conforming JSON."""


def _relevant_endpoints_for_entity(entity_name: str, api_contract: list, spec_endpoints: list) -> list:
    """Filter api_contract down to entries belonging to one entity, using
    spec_endpoints (which carries 'entity' - api_contract itself doesn't).
    Same bridging pattern as agents/frontend_developer.py's
    _relevant_endpoints - duplicated rather than shared, a small enough
    function that a new shared-utility module isn't worth the extra
    moving part for two call sites."""
    entity_by_path = {ep["path"]: ep["entity"] for ep in spec_endpoints}
    return [ep for ep in api_contract if entity_by_path.get(ep["path"]) == entity_name]


def _find_auth_endpoints(spec: dict) -> dict | None:
    """Find register/login endpoint paths and the auth entity's own
    required fields, using the same "register"/"login" substring
    heuristic already proven in scripts/test_pm_agent.py. Returns None if
    either endpoint can't be found (no auth-token helper gets generated
    in that case, and no test attempts an authenticated request)."""
    register_path = None
    login_path = None
    auth_entity_name = None
    for ep in spec["endpoints"]:
        path_lower = ep["path"].lower()
        if ep["method"] != "POST":
            continue
        if "register" in path_lower:
            register_path = ep["path"]
            auth_entity_name = ep["entity"]
        elif "login" in path_lower:
            login_path = ep["path"]

    if not (register_path and login_path):
        return None

    auth_entity = next((e for e in spec["entities"] if e["name"] == auth_entity_name), None)
    required_fields = []
    if auth_entity:
        required_fields = [f["name"] for f in auth_entity["fields"]
                            if f["required"] and f["type"] != "reference"]

    return {"register_path": register_path, "login_path": login_path, "required_fields": required_fields}


def _fake_field_value_js(field_name: str) -> str:
    """A plausible JS literal for a registration field, based on its
    name - deterministic, not LLM-guessed, since this is boilerplate
    fixture data, not app logic."""
    lower = field_name.lower()
    if "email" in lower:
        return "`qa-test-${Date.now()}@example.com`"
    if "password" in lower:
        return "'TestPassword123!'"
    if "user" in lower or "name" in lower:
        return "`qa_user_${Date.now()}_${Math.random().toString(36).substring(7)}`"
    return "`qa_val_${Date.now()}`"


def _build_helpers_js(auth_endpoints: dict | None) -> str:
    """Deterministic shared test helper - NOT an LLM call, see module
    docstring for why. Each test FILE calls startTestDb()/stopTestDb() in
    its own beforeAll/afterAll rather than sharing one process-wide
    in-memory MongoDB via Jest's globalSetup - slower (each file spins up
    its own mongod) but far more reliable, since it needs no cross-process
    coordination to get right, which matters more than speed here."""
    lines = [
        "// Auto-generated shared test helpers - NOT LLM-written, deterministic",
        "// boilerplate every entity's test file uses via require('./helpers').",
        "process.env.JWT_SECRET = process.env.JWT_SECRET || 'qa-sandbox-test-secret-do-not-use-in-production';",
        "const { MongoMemoryServer } = require('mongodb-memory-server');",
        "const mongoose = require('mongoose');",
        "const rawRequest = require('supertest');",
        "const app = require('../app');",
        "const { seedDatabase } = require('../seed');",
        "",
        "const defaultRequest = rawRequest(app);",
        "function request(targetApp) {",
        "  if (targetApp) return rawRequest(targetApp);",
        "  return defaultRequest;",
        "}",
        "['get', 'post', 'put', 'patch', 'delete'].forEach(method => {",
        "  request[method] = (...args) => defaultRequest[method](...args);",
        "});",
        "",
        "let mongoServer;",
        "",
        "async function startTestDb() {",
        "  mongoServer = await MongoMemoryServer.create();",
        "  await mongoose.connect(mongoServer.getUri());",
        "  await seedDatabase();",
        "}",
        "",
        "async function stopTestDb() {",
        "  await mongoose.disconnect();",
        "  if (mongoServer) await mongoServer.stop();",
        "}",
        "",
    ]
    if auth_endpoints:
        body_fields = ", ".join(
            f"{name}: {_fake_field_value_js(name)}" for name in auth_endpoints["required_fields"]
        )
        lines += [
            "// Registers a throwaway test user and logs in for a real JWT - exercises",
            "// the actual auth flow rather than reimplementing token signing here.",
            "async function getAuthToken() {",
            f"  const body = {{ {body_fields} }};",
            f"  await request(app).post({json.dumps(auth_endpoints['register_path'])}).send(body);",
            f"  const res = await request(app).post({json.dumps(auth_endpoints['login_path'])}).send(body);",
            "  const token = res.body && (res.body.token || res.body.accessToken || res.body.jwt || (res.body.data && res.body.data.token));",
            "  if (!token) {",
            "    throw new Error('getAuthToken failed: no token in login response. Status: ' + res.status + ', body: ' + JSON.stringify(res.body));",
            "  }",
            "  return token;",
            "}",
            "",
            "module.exports = { app, request, startTestDb, stopTestDb, getAuthToken };",
        ]
    else:
        lines += [
            "module.exports = { app, request, startTestDb, stopTestDb };",
        ]
    return "\n".join(lines)


def _build_jest_config_js() -> str:
    """Deterministic jest.config.js - NOT an LLM call. testEnvironment
    'node' (not the default jsdom) since this tests an Express API, and a
    generous default testTimeout since mongodb-memory-server's first run
    downloads a real MongoDB binary."""
    return "\n".join([
        "module.exports = {",
        "  testEnvironment: 'node',",
        "  testTimeout: 180000,",
        "};",
    ])


def generate_entity_test(entity: dict, entity_endpoints: list, has_auth_helper: bool) -> dict:
    """Generate one entity's test file. Internal helper - see
    generate_qa_report() for the public interface."""
    user_prompt = json.dumps(
        {"entity": {"name": entity["name"]}, "endpoints": entity_endpoints, "has_auth_helper": has_auth_helper},
        indent=2,
    )
    return call_agent(
        system_prompt=ENTITY_TEST_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=QA_ENTITY_TEST_SCHEMA,
        schema_name="qa_entity_test_output",
        max_tokens=4000,
    )


def _write_files(files: list, target_dir: str) -> None:
    for f in files:
        path = os.path.join(target_dir, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f["content"])


def _run_subprocess(args: list, cwd: str, timeout: int, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)


def _parse_jest_results(jest_json: dict) -> list:
    """Convert Jest's own --json output into QA_REPORT_SCHEMA's failures
    shape. Deliberately does NOT try to regex-parse "Expected: X /
    Received: Y" out of Jest's free-form failureMessages text - that
    wording varies by assertion type and matcher, and a fragile parser
    guessing at it is worse than an honest generic placeholder with the
    real detail preserved verbatim in error_log."""
    failures = []
    for test_file in jest_json.get("testResults", []):
        file_path = test_file.get("name", "")
        file_label = ""
        if file_path:
            norm = file_path.replace("\\", "/")
            if "tests/" in norm:
                file_label = "tests/" + norm.split("tests/")[-1]
            else:
                file_label = os.path.basename(norm)

        for assertion in test_file.get("assertionResults", []):
            if assertion.get("status") == "failed":
                raw_name = assertion.get("fullName") or assertion.get("title", "unknown test")
                test_name = f"[{file_label}] {raw_name}" if file_label else raw_name
                failures.append({
                    "test_name": test_name,
                    "expected": "test to pass",
                    "actual": "test failed - see error_log",
                    "error_log": "\n".join(assertion.get("failureMessages", [])) or "(no failure message captured)",
                })
    return failures


def generate_qa_report(spec: dict, backend_output: dict) -> dict:
    """Generate test files (one LLM call per entity) and ACTUALLY RUN them
    against the backend's real code in a sandboxed temp directory - npm
    install, an in-memory MongoDB, Jest - to produce a dict shaped like
    schemas.QA_REPORT_SCHEMA. See module docstring for why this agent is
    different from every other one in this project (it executes code,
    not just generates it), and for the execution caveat this sandbox
    couldn't verify end to end."""
    npm_path = shutil.which("npm")
    if npm_path is None:
        raise RuntimeError(
            "npm not found on PATH - QA Engineer needs it to install the backend's "
            "dependencies plus jest/supertest/mongodb-memory-server before it can run any tests."
        )

    npx_path = shutil.which("npx")
    if npx_path is None:
        raise RuntimeError(
            "npx not found on PATH - QA Engineer needs it to run jest inside the sandbox."
        )

    auth_endpoints = _find_auth_endpoints(spec)
    has_auth_helper = auth_endpoints is not None

    all_test_files = []
    for entity in spec["entities"]:
        entity_endpoints = _relevant_endpoints_for_entity(
            entity["name"], backend_output["api_contract"], spec["endpoints"]
        )
        if not entity_endpoints:
            continue
        result = generate_entity_test(entity, entity_endpoints, has_auth_helper)
        all_test_files.extend(result["files"])

    helpers_file = {"path": "tests/helpers.js", "content": _build_helpers_js(auth_endpoints)}
    jest_config_file = {"path": "jest.config.js", "content": _build_jest_config_js()}
    all_test_files_with_helpers = all_test_files + [helpers_file, jest_config_file]

    with tempfile.TemporaryDirectory(prefix="qa-sandbox-") as sandbox_dir:
        _write_files(backend_output["files"], sandbox_dir)
        _write_files(all_test_files_with_helpers, sandbox_dir)

        # Add test-only devDependencies to whatever package.json the
        # skeleton call already produced, rather than asking Backend
        # Developer's skeleton call to know about QA's tooling needs too.
        package_json_path = os.path.join(sandbox_dir, "package.json")
        with open(package_json_path, encoding="utf-8") as fh:
            package_json = json.load(fh)
        package_json.setdefault("devDependencies", {})
        package_json["devDependencies"].update({
            "jest": "^30.0.0",
            "supertest": "^7.0.0",
            "mongodb-memory-server": "^11.0.0",
        })
        with open(package_json_path, "w", encoding="utf-8") as fh:
            json.dump(package_json, fh, indent=2)

        try:
            install_result = _run_subprocess(
                [npm_path, "install", "--prefer-offline", "--no-audit", "--no-fund"],
                cwd=sandbox_dir,
                timeout=600,
            )
        except subprocess.TimeoutExpired as e:
            return {
                "all_tests_passed": False,
                "test_files": all_test_files,
                "failures": [{
                    "test_name": "npm install",
                    "expected": "dependencies to install successfully",
                    "actual": "npm install timed out",
                    "error_log": f"npm install timed out after 600s: {e}",
                }],
            }

        if install_result.returncode != 0:
            return {
                "all_tests_passed": False,
                "test_files": all_test_files,
                "failures": [{
                    "test_name": "npm install",
                    "expected": "dependencies to install successfully",
                    "actual": "npm install failed",
                    "error_log": install_result.stderr[-2000:] or install_result.stdout[-2000:],
                }],
            }

        npx_path = shutil.which("npx")
        # middleware/auth.js (generated by Backend Developer, only present
        # if auth_required) reads process.env.JWT_SECRET and throws at
        # require-time if it's missing - the sandbox has no real .env file
        # (MONGODB_URI isn't needed here either, since helpers.js connects
        # directly to the in-memory instance's own URI), so this has to be
        # supplied explicitly or every auth-required app's QA run would
        # crash on import before a single test even runs, regardless of
        # whether the actual route logic is correct.
        jest_env = dict(os.environ)
        jest_env["JWT_SECRET"] = "qa-sandbox-test-secret-do-not-use-in-production"
        try:
            jest_result = _run_subprocess(
                [npx_path, "jest", "--json", "--runInBand"], cwd=sandbox_dir, timeout=600, env=jest_env
            )
        except subprocess.TimeoutExpired as e:
            return {
                "all_tests_passed": False,
                "test_files": all_test_files,
                "failures": [{
                    "test_name": "jest run",
                    "expected": "tests to complete within timeout",
                    "actual": "jest execution timed out",
                    "error_log": f"jest execution timed out after 600s: {e}",
                }],
            }
        try:
            jest_json = json.loads(jest_result.stdout)
        except json.JSONDecodeError:
            return {
                "all_tests_passed": False,
                "test_files": all_test_files,
                "failures": [{
                    "test_name": "jest run",
                    "expected": "parseable JSON test results",
                    "actual": "jest did not produce valid JSON output",
                    "error_log": (jest_result.stderr or jest_result.stdout)[-2000:],
                }],
            }

        failures = _parse_jest_results(jest_json)
        return {
            "all_tests_passed": len(failures) == 0,
            "test_files": all_test_files,
            "failures": failures,
        }
