"""Tests for project assembly (orchestrator/assembly.py) and FastAPI endpoints
(orchestrator/main.py).
"""
import json
import os
import shutil
import sys
import tempfile
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.assembly import assemble_project
from orchestrator.main import app

client = TestClient(app)

SAMPLE_SPEC = {
    "app_name": "TaskMaster Pro",
    "app_description": "A collaborative task management application.",
    "auth_required": True,
    "entities": [
        {"name": "Task", "fields": [
            {"name": "title", "type": "string", "required": True, "references_entity": None},
        ]},
    ],
    "relationships": [],
    "endpoints": [
        {"method": "GET", "path": "/tasks", "description": "list tasks", "entity": "Task", "requires_auth": False},
        {"method": "POST", "path": "/tasks", "description": "create task", "entity": "Task", "requires_auth": True},
    ],
    "pages": [],
}

SAMPLE_BACKEND = {
    "files": [
        {"path": "package.json", "content": json.dumps({"name": "backend", "scripts": {"start": "node server.js"}})},
        {"path": "app.js", "content": "const express = require('express'); const app = express(); module.exports = app;"},
        {"path": "server.js", "content": "const app = require('./app'); app.listen(3000);"},
        {"path": "models/Task.js", "content": "// model"},
        {"path": "routes/task.js", "content": "// router"},
        {"path": "seed.js", "content": "module.exports = { seedDatabase: async () => {} };"},
    ],
    "api_contract": [
        {"method": "GET", "path": "/tasks", "request_body_fields": [], "response_shape_fields": ["_id", "title"], "requires_auth": False},
    ],
    "setup_notes": "npm install && npm start",
}

SAMPLE_FRONTEND = {
    "files": [
        {"path": "package.json", "content": json.dumps({"name": "frontend"})},
        {"path": "src/App.jsx", "content": "export default function App() { return <h1>TaskMaster</h1>; }"},
        {"path": "vite.config.js", "content": "export default {}"},
    ],
    "setup_notes": "npm install && npm run dev",
}

SAMPLE_QA = {
    "all_tests_passed": True,
    "test_files": [
        {"path": "tests/task.test.js", "content": "test('tasks', () => {});"},
    ],
    "failures": [],
}

SAMPLE_DOCS = {
    "files": [
        {"path": "README.md", "content": "# TaskMaster Pro\n\nDocs content"},
        {"path": "API_REFERENCE.md", "content": "# API Reference\n\nEndpoints"},
    ],
}


def test_assemble_project_writes_complete_directory_tree_and_zip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = assemble_project(
            task_id="test-task-1",
            spec=SAMPLE_SPEC,
            backend_output=SAMPLE_BACKEND,
            frontend_output=SAMPLE_FRONTEND,
            qa_report=SAMPLE_QA,
            docs_output=SAMPLE_DOCS,
            output_base_dir=tmp_dir,
        )

        project_dir = result["project_dir"]
        zip_path = result["zip_path"]

        assert os.path.exists(project_dir)
        assert os.path.exists(zip_path)
        assert zip_path.endswith(".zip")

        # 1. Check Backend Directory
        backend_dir = os.path.join(project_dir, "backend")
        assert os.path.exists(os.path.join(backend_dir, "app.js"))
        assert os.path.exists(os.path.join(backend_dir, "server.js"))
        assert os.path.exists(os.path.join(backend_dir, "seed.js"))
        assert os.path.exists(os.path.join(backend_dir, "tests", "task.test.js"))
        assert os.path.exists(os.path.join(backend_dir, "tests", "helpers.js"))
        assert os.path.exists(os.path.join(backend_dir, "jest.config.js"))
        assert os.path.exists(os.path.join(backend_dir, ".env.example"))

        # Check package.json devDependencies and scripts
        with open(os.path.join(backend_dir, "package.json"), "r", encoding="utf-8") as fh:
            pkg = json.load(fh)
        assert "jest" in pkg["devDependencies"]
        assert "supertest" in pkg["devDependencies"]
        assert "mongodb-memory-server" in pkg["devDependencies"]
        assert pkg["scripts"]["test"] == "jest"
        assert pkg["scripts"]["start"] == "node server.js"

        # 2. Check Frontend Directory
        frontend_dir = os.path.join(project_dir, "frontend")
        assert os.path.exists(os.path.join(frontend_dir, "src", "App.jsx"))
        assert os.path.exists(os.path.join(frontend_dir, ".env.example"))

        # 3. Check Root Documentation
        assert os.path.exists(os.path.join(project_dir, "README.md"))
        assert os.path.exists(os.path.join(project_dir, "API_REFERENCE.md"))

        # 4. Verify ZIP Contents
        with zipfile.ZipFile(zip_path, "r") as archive:
            names = archive.namelist()
            # Must contain both backend and frontend files
            assert any("backend/app.js" in n for n in names)
            assert any("backend/tests/helpers.js" in n for n in names)
            assert any("frontend/src/App.jsx" in n for n in names)
            assert any("README.md" in n for n in names)


def test_api_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_api_post_build_synchronous(monkeypatch):
    # Mock _graph.invoke to return completed state without making LLM calls
    fake_state = {
        "task_id": "api-test-task",
        "user_prompt": "Build a task app",
        "spec": SAMPLE_SPEC,
        "backend_output": SAMPLE_BACKEND,
        "frontend_output": SAMPLE_FRONTEND,
        "qa_report": SAMPLE_QA,
        "docs_output": SAMPLE_DOCS,
        "qa_attempt": 1,
        "needs_human_review": False,
        "agent_log": [],
    }
    monkeypatch.setattr("orchestrator.main._graph.invoke", lambda init_st: fake_state)

    res = client.post("/build", json={"user_prompt": "Build a task app"})
    assert res.status_code == 200
    data = res.json()
    assert "assembly" in data
    assert "zip_path" in data["assembly"]
    assert data["assembly"]["download_url"] == f"/download/{data['assembly']['clean_name']}"

    # Test download endpoint
    dl_res = client.get(data["assembly"]["download_url"])
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/zip"
