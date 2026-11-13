"""Run this yourself, locally, with a real GROQ_API_KEY set in .env.

Generates a React frontend against the Backend Developer's api_contract
and writes it to disk, then automatically runs `npm install && npm run
build` - the real way to validate JSX (plain `node --check` can't parse
JSX syntax at all, so it isn't used here the way it was for the backend).
This could NOT be run from the sandbox that built Phase 3 (no network
access to api.groq.com there, and no point building a React app that
can't be installed against a real npm registry from here anyway).

Prefers the exact spec + api_contract already saved by
scripts/test_backend_agent.py (in generated_apps/food-delivery-backend/
.generation-manifest.json) over regenerating them - Backend Developer's
output is non-deterministic, so regenerating would risk building this
frontend against a DIFFERENT contract than the backend you already
verified end-to-end. Falls back to a fresh PM + Backend generation only
if that manifest doesn't exist yet.

    python scripts/test_frontend_agent.py
"""
import json
import os
import subprocess
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agents.frontend_developer import generate_frontend
from schemas import FRONTEND_OUTPUT_SCHEMA, validate_payload

PROMPT = "Build a food delivery website"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_MANIFEST = os.path.join(PROJECT_ROOT, "generated_apps", "food-delivery-backend", ".generation-manifest.json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "generated_apps", "food-delivery-frontend")


def get_spec_and_contract():
    if os.path.exists(BACKEND_MANIFEST):
        print(f"Reusing spec + api_contract from {BACKEND_MANIFEST}")
        print("(the exact backend you already verified end-to-end - not a fresh, possibly-different regeneration)")
        with open(BACKEND_MANIFEST, encoding="utf-8") as fh:
            manifest = json.load(fh)
        return manifest["spec"], manifest["api_contract"]

    print(f"No manifest found at {BACKEND_MANIFEST} - falling back to a fresh PM + Backend generation.")
    print("(run scripts/test_backend_agent.py first if you want Frontend built against your already-verified backend)")
    from agents.project_manager import generate_spec
    from agents.backend_developer import generate_backend
    from schemas import PM_SPEC_SCHEMA, BACKEND_OUTPUT_SCHEMA
    spec = generate_spec(PROMPT)
    validate_payload(spec, PM_SPEC_SCHEMA)
    backend_output = generate_backend(spec)
    validate_payload(backend_output, BACKEND_OUTPUT_SCHEMA)
    return spec, backend_output["api_contract"]


if __name__ == "__main__":
    spec, api_contract = get_spec_and_contract()

    print(f"\nGenerating frontend for '{spec['app_name']}' "
          f"({len(spec['pages'])} pages, {len(api_contract)} contracted endpoints)...")
    print("(makes one small Groq call per page plus one for shared files, with automatic pauses")
    print(f" between them to stay under the free tier's rate limit - budget roughly {len(spec['pages'])} x 15-20s")
    print(" just in built-in pauses, on top of actual generation time.)")
    output = generate_frontend(spec, api_contract)
    # Raises if strict mode was silently ignored (see schemas.py docstring) -
    # if this throws, that's the provider returning a non-conforming
    # response, not a bug in this script.
    validate_payload(output, FRONTEND_OUTPUT_SCHEMA)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for f in output["files"]:
        path = os.path.join(OUTPUT_DIR, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f["content"])

    print(f"\nWrote {len(output['files'])} files to {OUTPUT_DIR}:")
    for f in output["files"]:
        print(" -", f["path"])

    # Plain-JS files can be checked with node directly. .jsx files can't -
    # node --check doesn't understand JSX syntax, so a valid JSX file would
    # incorrectly show up as "broken" here. Real JSX validation happens via
    # npm run build below, the same tool Vite itself uses.
    print("\nSyntax-checking non-JSX JS files with `node --check`...")
    for f in output["files"]:
        if f["path"].endswith(".js") and not f["path"].endswith(".jsx"):
            full_path = os.path.join(OUTPUT_DIR, f["path"])
            result = subprocess.run(["node", "--check", full_path], capture_output=True, text=True)
            status = "OK" if result.returncode == 0 else "FAIL"
            print(f"  {status}  {f['path']}")
            if result.returncode != 0:
                print("   ", result.stderr.strip().replace("\n", "\n    "))

    api_js = next((f["content"] for f in output["files"] if f["path"] == "src/api.js"), "")
    if "localStorage" not in api_js or "401" not in api_js:
        print("\n*** WARNING: src/api.js doesn't look like it follows the required token/401 pattern. ***")
        print("*** Check it by hand - every page is supposed to call the API through this helper only. ***")
    if ".json(" not in api_js:
        print("\n*** WARNING: src/api.js doesn't appear to parse the response body (no '.json(' call). ***")
        print("*** Confirmed live to cause a silent 'no data ever shows' bug: fetch succeeds, but every ***")
        print("*** page receives the raw Response object instead of actual data, and treats it as empty. ***")

    print("setup_notes:", output["setup_notes"])

    # On Windows, `npm` is npm.cmd (a batch script), not a real .exe -
    # subprocess.run(["npm", ...]) can fail to find it even when `npm`
    # works fine in an interactive terminal, because subprocess doesn't
    # go through the same shell-based resolution. shutil.which() finds
    # the actual executable (npm.cmd on Windows, npm on Linux/Mac) and
    # passing that full path to subprocess.run works on both. Resolved
    # once and reused for both the install and build calls below.
    npm_path = shutil.which("npm")
    if npm_path is None:
        print("\n*** npm not found on PATH. ***")
        print("*** If `npm --version` works in your terminal, try restarting your terminal/VS Code ***")
        print("*** so it picks up an updated PATH, then rerun this script. ***")
        sys.exit(1)

    print(f"\nRunning `npm install` in {OUTPUT_DIR} (this can take a minute)...")
    install_result = subprocess.run([npm_path, "install"], cwd=OUTPUT_DIR, capture_output=True, text=True)
    if install_result.returncode != 0:
        print("npm install FAILED:")
        print(install_result.stderr[-2000:])
        sys.exit(1)
    print("npm install succeeded.")

    print("\nRunning `npm run build` - the real JSX/import validation (equivalent to what `node --check` did for the backend)...")
    build_result = subprocess.run([npm_path, "run", "build"], cwd=OUTPUT_DIR, capture_output=True, text=True)
    if build_result.returncode == 0:
        print("BUILD SUCCEEDED.")
        print("\nEvery file is valid JSX/JS and every import resolves. Next steps:")
        print(f"  cd {OUTPUT_DIR}")
        print("  npm run dev")
        print("  open the printed localhost URL - make sure your backend is also running in another terminal")
    else:
        print("BUILD FAILED:")
        print(build_result.stdout[-3000:])
        print(build_result.stderr[-2000:])
        print("\nThis is a real code bug from the model (bad JSX, an import that doesn't exist, etc.),")
        print("not a schema problem - strict mode only guarantees the JSON shape of the response,")
        print("not that the embedded code inside it is correct. Paste this error back for a fix.")
