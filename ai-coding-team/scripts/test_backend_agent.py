"""Run this yourself, locally, with a real GROQ_API_KEY set in .env.

Chains the real Project Manager agent into the real Backend Developer
agent - generates a fresh spec for the food delivery prompt, then builds
a backend from it, and writes the result to disk so you can run it. This
could NOT be run from the sandbox that built Phase 2 (no network access
to api.groq.com there).

Deliberately generates the spec fresh each run rather than using a
hardcoded one - a hardcoded spec goes stale the moment either agent's
system prompt changes, and silently tests against the wrong thing.

    python scripts/test_backend_agent.py
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agents.project_manager import generate_spec
from agents.backend_developer import generate_backend
from schemas import PM_SPEC_SCHEMA, BACKEND_OUTPUT_SCHEMA, validate_payload

PROMPT = "Build a food delivery website"

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "generated_apps", "food-delivery-backend",
)

if __name__ == "__main__":
    print(f"Generating spec for: {PROMPT}")
    spec = generate_spec(PROMPT)
    validate_payload(spec, PM_SPEC_SCHEMA)
    print(json.dumps(spec, indent=2))

    auth_paths = [e["path"] for e in spec["endpoints"] if "login" in e["path"].lower() or "register" in e["path"].lower() or e["path"] in ("/users", "/login")]
    if spec["auth_required"] and not auth_paths:
        print("\n*** WARNING: auth_required is true but no register/login-looking endpoint was found. ***")
        print("*** The generated backend will have no way to issue a token. Check the endpoints above. ***\n")
    else:
        print(f"\nAuth endpoints found: {auth_paths or '(none needed, auth_required is false)'}")

    print(f"\nGenerating backend ({len(spec['entities'])} entities, {len(spec['endpoints'])} endpoints)...")
    print("(makes one small Groq call per entity plus one for shared files, with short pauses")
    print(" between them to stay under the free tier's rate limit - this will take a bit longer")
    print(f" than a single call would: roughly {len(spec['entities'])} x 15-20s just in built-in pauses.)")
    output = generate_backend(spec)
    # Raises if strict mode was silently ignored (see schemas.py docstring) -
    # if this throws, that's Groq returning a non-conforming response, not a
    # bug in this script.
    validate_payload(output, BACKEND_OUTPUT_SCHEMA)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for f in output["files"]:
        path = os.path.join(OUTPUT_DIR, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f["content"])

    # Write a ready-to-fill .env template right next to the code, so the
    # "wait, which .env goes where" mixup from before can't happen again -
    # this one is separate from the project root's .env (which holds
    # GROQ_API_KEY) and belongs to the generated app, not the orchestrator.
    env_example_path = os.path.join(OUTPUT_DIR, ".env.example")
    with open(env_example_path, "w", encoding="utf-8") as fh:
        fh.write("MONGODB_URI=your_mongodb_connection_string_here\n")
        fh.write("JWT_SECRET=replace_with_a_long_random_string\n")
        fh.write("PORT=3000\n")

    print(f"\nWrote {len(output['files'])} files + .env.example to {OUTPUT_DIR}:")
    js_files = []
    for f in output["files"]:
        print(" -", f["path"])
        if f["path"].endswith(".js"):
            js_files.append(f["path"])

    print("\nSyntax-checking generated JS with `node --check`...")
    all_ok = True
    package_config_error_seen = False
    for rel_path in js_files:
        full_path = os.path.join(OUTPUT_DIR, rel_path)
        result = subprocess.run(["node", "--check", full_path], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  OK  {rel_path}")
        else:
            all_ok = False
            if "ERR_INVALID_PACKAGE_CONFIG" in result.stderr:
                # Node needs to read package.json before checking ANY file
                # in this directory - if IT is broken, every other file
                # fails with this same misleading trace regardless of
                # whether that file has anything wrong with it. Printing
                # 14 near-identical stack traces here obscures that this
                # is really one bug, not fourteen - so collapse them.
                package_config_error_seen = True
                continue
            print(f"  FAIL  {rel_path}")
            print("   ", result.stderr.strip().replace("\n", "\n    "))

    if package_config_error_seen:
        print("\n*** package.json itself isn't valid JSON. Node needs to read it before checking ANY")
        print("*** other file in this directory, so that one broken file shows up as every file")
        print("*** failing - the files above (if any) may be genuinely fine. generate_backend_skeleton()")
        print("*** now validates and retries this automatically - if you're still hitting it, check")
        print("*** package.json's actual content by hand; it's likely a stray trailing comma or similar.")

    # Defensive check: confirm dotenv actually made it into both files,
    # since a missing .env is invisible until npm start fails at runtime.
    pkg_json = next((f["content"] for f in output["files"] if f["path"] == "package.json"), "")
    server_js = next((f["content"] for f in output["files"] if f["path"] == "server.js"), "")
    if "dotenv" not in pkg_json or "dotenv" not in server_js:
        print("\n*** WARNING: 'dotenv' not found in package.json and/or server.js. ***")
        print("*** Creating .env won't be picked up automatically - check server.js by hand. ***")

    print(f"\napi_contract has {len(output['api_contract'])} endpoints")
    print("setup_notes:", output["setup_notes"])

    # Save spec + api_contract for scripts/test_frontend_agent.py to reuse.
    # Backend Developer's output is non-deterministic - regenerating it
    # again for the frontend test could silently produce a DIFFERENT
    # api_contract than the backend you already tested end-to-end, and
    # Frontend would then be built against a contract that doesn't match
    # what's actually running on disk. Saving it here means Frontend uses
    # the exact contract this exact backend implements.
    manifest_path = os.path.join(OUTPUT_DIR, ".generation-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"spec": spec, "api_contract": output["api_contract"]}, fh, indent=2)
    print(f"\nSaved spec + api_contract to {manifest_path} for scripts/test_frontend_agent.py to reuse.")

    if all_ok:
        print(f"\nAll files are syntactically valid JS. Next steps:")
        print(f"  cd {OUTPUT_DIR}")
        print("  npm install")
        print("  copy .env.example to .env and fill in a real MONGODB_URI + JWT_SECRET")
        print("  npm start")
        print("  curl localhost:3000/restaurants   # should return [] against an empty DB, not an error")
    else:
        print("\nAt least one file failed `node --check` - fix that before trying npm install.")
        print("This is a real code bug from the model, not a schema problem (strict mode only")
        print("guarantees the JSON shape, not that the embedded code inside it is correct).")
