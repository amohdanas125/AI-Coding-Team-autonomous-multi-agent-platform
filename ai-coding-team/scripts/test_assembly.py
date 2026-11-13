import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from orchestrator.assembly import assemble_project
from agents.documentation_writer import generate_docs
BACKEND_DIR = os.path.join(PROJECT_ROOT, "generated_apps", "food-delivery-backend")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "generated_apps", "food-delivery-frontend")
MANIFEST_PATH = os.path.join(BACKEND_DIR, ".generation-manifest.json")

with open(MANIFEST_PATH, encoding="utf-8") as fh:
    manifest = json.load(fh)
spec = manifest["spec"]
api_contract = manifest["api_contract"]

# Read backend files
EXCLUDED_NAMES = {"node_modules", "package-lock.json", ".env", ".env.example", ".generation-manifest.json"}
backend_files = []
for root, dirs, files in os.walk(BACKEND_DIR):
    dirs[:] = [d for d in dirs if d not in EXCLUDED_NAMES]
    for fn in files:
        if fn in EXCLUDED_NAMES:
            continue
        full_path = os.path.join(root, fn)
        rel_path = os.path.relpath(full_path, BACKEND_DIR).replace(os.sep, "/")
        with open(full_path, encoding="utf-8") as fh:
            backend_files.append({"path": rel_path, "content": fh.read()})

# Read frontend files
frontend_files = []
for root, dirs, files in os.walk(FRONTEND_DIR):
    dirs[:] = [d for d in dirs if d not in EXCLUDED_NAMES]
    for fn in files:
        if fn in EXCLUDED_NAMES:
            continue
        full_path = os.path.join(root, fn)
        rel_path = os.path.relpath(full_path, FRONTEND_DIR).replace(os.sep, "/")
        with open(full_path, encoding="utf-8") as fh:
            frontend_files.append({"path": rel_path, "content": fh.read()})

backend_output = {"files": backend_files, "api_contract": api_contract, "setup_notes": ""}
frontend_output = {"files": frontend_files, "setup_notes": ""}
qa_report = {"all_tests_passed": True, "test_files": [], "failures": []}

print("Generating docs...")
docs_output = generate_docs(spec, backend_output, frontend_output)

print(f"Assembling project for '{spec['app_name']}'...")
res = assemble_project(
    task_id="live-test-task",
    spec=spec,
    backend_output=backend_output,
    frontend_output=frontend_output,
    qa_report=qa_report,
    docs_output=docs_output,
    output_base_dir="output",
)

print("\nAssembly complete!")
print("Project Dir:", res["project_dir"])
print("Zip Path:", res["zip_path"])
print("Zip exists:", os.path.exists(res["zip_path"]))
print("Zip size:", os.path.getsize(res["zip_path"]), "bytes")
