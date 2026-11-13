"""Run this yourself, locally, with a real GROQ_API_KEY and GEMINI_API_KEY
set in .env, AFTER running scripts/test_backend_agent.py (this reuses
that backend's already-generated files and manifest, rather than
regenerating - same reasoning as test_frontend_agent.py: Backend
Developer's output is non-deterministic, so QA should test the exact
backend sitting on disk, not a fresh, possibly-different regeneration).

This is the one agent that could NOT be verified at all from the sandbox
that built it - not just "the live LLM call couldn't be tested" (true of
every agent), but the actual EXECUTION (npm install, an in-memory
MongoDB, Jest) needs network access to mongodb-memory-server's binary
download host, which that sandbox didn't have either. Every other script
in this project could at least prove its own subprocess logic works in
principle; this one's real end-to-end behavior is entirely unverified
until you run it here.

    python scripts/test_qa_agent.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agents.qa_engineer import generate_qa_report
from schemas import QA_REPORT_SCHEMA, validate_payload

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "generated_apps", "food-delivery-backend")
BACKEND_MANIFEST = os.path.join(BACKEND_DIR, ".generation-manifest.json")

# Files that exist in the backend's own directory but aren't part of what
# QA should copy into its sandbox - node_modules/package-lock.json get
# regenerated fresh by the sandbox's own npm install, and .env/.env.example
# are irrelevant here (the sandbox uses an in-memory MongoDB, and JWT_SECRET
# is supplied directly to the jest subprocess - see qa_engineer.py).
EXCLUDED_NAMES = {"node_modules", "package-lock.json", ".env", ".env.example", ".generation-manifest.json"}


def _read_backend_files_from_disk(backend_dir: str) -> list:
    files = []
    for root, dirs, filenames in os.walk(backend_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_NAMES]
        for filename in filenames:
            if filename in EXCLUDED_NAMES:
                continue
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, backend_dir).replace(os.sep, "/")
            with open(full_path, encoding="utf-8") as fh:
                files.append({"path": rel_path, "content": fh.read()})
    return files


if __name__ == "__main__":
    if not os.path.exists(BACKEND_MANIFEST):
        print(f"No manifest found at {BACKEND_MANIFEST}.")
        print("Run scripts/test_backend_agent.py first - QA Engineer tests an already-generated")
        print("backend, it doesn't generate one itself.")
        sys.exit(1)

    with open(BACKEND_MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    spec = manifest["spec"]
    api_contract = manifest["api_contract"]

    backend_files = _read_backend_files_from_disk(BACKEND_DIR)
    print(f"Read {len(backend_files)} files from {BACKEND_DIR}")
    if not any(f["path"] == "app.js" for f in backend_files):
        print("\n*** WARNING: no app.js found in the backend directory. ***")
        print("*** This backend was likely generated before the app.js/server.js split - ***")
        print("*** regenerate it with the current scripts/test_backend_agent.py first. ***")
        sys.exit(1)

    backend_output = {"files": backend_files, "api_contract": api_contract, "setup_notes": ""}

    print(f"\nGenerating tests for '{spec['app_name']}' ({len(spec['entities'])} entities)...")
    print("(one small Gemini call per entity, then REAL execution: npm install, an in-memory")
    print(" MongoDB, and a Jest run - this will take noticeably longer than any other script,")
    print(" especially on the very first run, which also downloads a MongoDB binary.)")

    report = generate_qa_report(spec, backend_output)
    # Raises if strict mode was silently ignored on the test-generation
    # call (see schemas.py docstring) - if this throws, that's the
    # provider returning a non-conforming response, not a bug here.
    validate_payload(report, QA_REPORT_SCHEMA)

    print(f"\nGenerated {len(report['test_files'])} test file(s):")
    for f in report["test_files"]:
        print(" -", f["path"])

    if report["all_tests_passed"]:
        print("\nALL TESTS PASSED.")
    else:
        print(f"\n{len(report['failures'])} TEST(S) FAILED:")
        for failure in report["failures"]:
            print(f"\n  {failure['test_name']}")
            print(f"    {failure['error_log'][:500]}")
        print("\nThis could be a real bug in the generated backend code, OR a bug in the")
        print("generated test itself (e.g. a wrong assumption about response shape) - read")
        print("the error_log above before assuming which one. Paste this output back for help.")
