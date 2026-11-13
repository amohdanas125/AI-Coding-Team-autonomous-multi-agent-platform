"""Assembly and packaging module for the AI Coding Team project.
Takes the final pipeline outputs from all agents and packages them into
a ready-to-run project directory structure:
  output/<app_name>/
    README.md
    API_REFERENCE.md
    backend/
      (backend files + tests + helpers.js + jest.config.js + test devDependencies + .env.example)
    frontend/
      (frontend React + Vite files)

And creates output/<app_name>.zip for distribution.
"""
import json
import os
import re
import shutil

from agents.qa_engineer import _build_helpers_js, _build_jest_config_js, _find_auth_endpoints


def _clean_name(app_name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "-", app_name.strip().lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "generated-app"


def assemble_project(
    task_id: str,
    spec: dict,
    backend_output: dict,
    frontend_output: dict,
    qa_report: dict,
    docs_output: dict,
    output_base_dir: str = "output",
) -> dict:
    """Write backend files, frontend files, QA test files, and documentation
    into output/<app_name>/{backend,frontend}, and produce output/<app_name>.zip."""
    app_name = spec.get("app_name", "app")
    clean_name = _clean_name(app_name)

    project_dir = os.path.join(output_base_dir, clean_name)
    backend_dir = os.path.join(project_dir, "backend")
    frontend_dir = os.path.join(project_dir, "frontend")

    os.makedirs(backend_dir, exist_ok=True)
    os.makedirs(frontend_dir, exist_ok=True)

    # 1. Write Backend Files
    for file_obj in backend_output.get("files", []):
        file_path = os.path.join(backend_dir, file_obj["path"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(file_obj["content"])

    # 2. Add Test Infrastructure & devDependencies to Backend package.json
    package_json_path = os.path.join(backend_dir, "package.json")
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path, "r", encoding="utf-8") as fh:
                pkg = json.load(fh)
        except json.JSONDecodeError:
            pkg = {"name": f"{clean_name}-backend", "version": "1.0.0", "dependencies": {}}
    else:
        pkg = {"name": f"{clean_name}-backend", "version": "1.0.0", "dependencies": {}}

    pkg.setdefault("devDependencies", {})
    pkg["devDependencies"].update({
        "jest": "^30.0.0",
        "supertest": "^7.0.0",
        "mongodb-memory-server": "^11.0.0",
    })
    pkg.setdefault("scripts", {})
    pkg["scripts"].setdefault("start", "node server.js")
    pkg["scripts"]["test"] = "jest"

    with open(package_json_path, "w", encoding="utf-8") as fh:
        json.dump(pkg, fh, indent=2)

    # 3. Write QA Test Files into Backend
    for test_file in qa_report.get("test_files", []):
        tpath = os.path.join(backend_dir, test_file["path"])
        os.makedirs(os.path.dirname(tpath), exist_ok=True)
        with open(tpath, "w", encoding="utf-8") as fh:
            fh.write(test_file["content"])

    # Ensure tests/helpers.js exists
    helpers_path = os.path.join(backend_dir, "tests", "helpers.js")
    if not os.path.exists(helpers_path):
        os.makedirs(os.path.dirname(helpers_path), exist_ok=True)
        auth_eps = _find_auth_endpoints(spec)
        with open(helpers_path, "w", encoding="utf-8") as fh:
            fh.write(_build_helpers_js(auth_eps))

    # Ensure jest.config.js exists
    jest_config_path = os.path.join(backend_dir, "jest.config.js")
    if not os.path.exists(jest_config_path):
        with open(jest_config_path, "w", encoding="utf-8") as fh:
            fh.write(_build_jest_config_js())

    # Write backend .env.example
    backend_env_example = os.path.join(backend_dir, ".env.example")
    lines = [
        "PORT=3000",
        f"MONGODB_URI=mongodb://localhost:27017/{clean_name}",
    ]
    if spec.get("auth_required"):
        lines.append("JWT_SECRET=supersecret_jwt_secret_change_in_production")
    with open(backend_env_example, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # 4. Write Frontend Files
    for file_obj in frontend_output.get("files", []):
        file_path = os.path.join(frontend_dir, file_obj["path"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(file_obj["content"])

    # Ensure frontend package.json is always valid unescaped JSON (protects against LLM escaped quotes: \")
    fe_pkg_path = os.path.join(frontend_dir, "package.json")
    if os.path.exists(fe_pkg_path):
        try:
            with open(fe_pkg_path, "r", encoding="utf-8") as fh:
                raw_fe_pkg = fh.read()
            cleaned_pkg = raw_fe_pkg.replace('\\"', '"')
            fe_pkg = json.loads(cleaned_pkg)
        except Exception:
            fe_pkg = {
                "name": f"{clean_name}-frontend",
                "version": "0.1.0",
                "private": True,
                "type": "module",
                "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
                "dependencies": {
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                    "react-router-dom": "^6.14.1",
                },
                "devDependencies": {
                    "vite": "^5.0.0",
                    "@vitejs/plugin-react": "^4.2.0",
                },
            }
        fe_pkg.setdefault("type", "module")
        fe_pkg.setdefault("scripts", {})
        fe_pkg["scripts"].setdefault("dev", "vite")
        fe_pkg["scripts"].setdefault("build", "vite build")
        fe_pkg["scripts"].setdefault("preview", "vite preview")
        with open(fe_pkg_path, "w", encoding="utf-8") as fh:
            json.dump(fe_pkg, fh, indent=2)

    # Write frontend .env.example
    frontend_env_example = os.path.join(frontend_dir, ".env.example")
    with open(frontend_env_example, "w", encoding="utf-8") as fh:
        fh.write("VITE_API_BASE_URL=http://localhost:3000\n")

    # 5. Write Documentation Files in Project Root
    for file_obj in docs_output.get("files", []):
        file_path = os.path.join(project_dir, file_obj["path"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(file_obj["content"])

    # 6. Create Zip Archive
    zip_base = os.path.join(output_base_dir, clean_name)
    zip_path = shutil.make_archive(zip_base, "zip", output_base_dir, clean_name)

    return {
        "task_id": task_id,
        "clean_name": clean_name,
        "project_dir": project_dir,
        "zip_path": zip_path,
    }
