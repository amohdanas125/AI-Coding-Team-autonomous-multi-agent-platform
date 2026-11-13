"""FastAPI entry point for the AI Coding Team Orchestrator.
Exposes:
- GET /health: Health check
- POST /build: Synchronous build endpoint that runs the full pipeline,
  assembles the project in output/<app_name>, and generates output/<app_name>.zip
- POST /build/async: Asynchronous build endpoint for long-running builds
- GET /build/status/{task_id}: Poll status for async builds
- GET /download/{clean_name}: Download the generated project zip
"""
import os
import uuid
from typing import Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from orchestrator.assembly import assemble_project
from orchestrator.graph import build_graph
from orchestrator.state import initial_state

app = FastAPI(title="AI Coding Team Orchestrator")
_graph = build_graph()
_build_tasks: Dict[str, dict] = {}


class BuildRequest(BaseModel):
    user_prompt: str


@app.get("/health")
def health():
    return {"status": "ok"}


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Coding Team - Autonomous Multi-Agent System</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --primary-light: #eff6ff;
      --success: #10b981;
      --bg: #0b0f19;
      --surface: #111827;
      --surface-border: #1f2937;
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --radius: 12px;
      --radius-sm: 8px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .header {
      border-bottom: 1px solid var(--surface-border);
      background: rgba(17, 24, 39, 0.8);
      backdrop-filter: blur(8px);
      padding: 1rem 1.5rem;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .header-content {
      max-width: 1000px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-size: 1.25rem;
      font-weight: 800;
      color: #fff;
    }
    .badge {
      background: rgba(59, 130, 246, 0.2);
      color: #60a5fa;
      border: 1px solid rgba(59, 130, 246, 0.4);
      padding: 0.2rem 0.6rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .docs-link {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.875rem;
      font-weight: 600;
      transition: color 0.15s;
    }
    .docs-link:hover { color: #fff; }
    .container {
      max-width: 860px;
      width: 100%;
      margin: 2.5rem auto;
      padding: 0 1.5rem;
      flex: 1;
    }
    .hero {
      text-align: center;
      margin-bottom: 2.5rem;
    }
    .hero h1 {
      font-size: 2.5rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      margin-bottom: 0.75rem;
      background: linear-gradient(135deg, #fff 0%, #94a3b8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .hero p {
      color: var(--text-muted);
      font-size: 1.1rem;
      max-width: 600px;
      margin: 0 auto;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: var(--radius);
      padding: 2rem;
      box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.5);
      margin-bottom: 2rem;
    }
    label {
      display: block;
      font-size: 0.875rem;
      font-weight: 600;
      color: #d1d5db;
      margin-bottom: 0.5rem;
    }
    textarea {
      width: 100%;
      background: #0b0f19;
      border: 1px solid var(--surface-border);
      border-radius: var(--radius-sm);
      color: #fff;
      font-family: inherit;
      font-size: 1rem;
      padding: 1rem;
      min-height: 100px;
      resize: vertical;
      outline: none;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    textarea:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
    }
    .suggestions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin: 0.75rem 0 1.5rem;
    }
    .pill {
      background: #1f2937;
      color: #9ca3af;
      border: 1px solid #374151;
      padding: 0.35rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    }
    .pill:hover {
      background: #374151;
      color: #fff;
    }
    .btn-submit {
      width: 100%;
      background: var(--primary);
      color: white;
      font-weight: 700;
      font-size: 1.05rem;
      padding: 0.95rem;
      border-radius: var(--radius-sm);
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      transition: all 0.15s;
    }
    .btn-submit:hover { background: var(--primary-hover); transform: translateY(-1px); }
    .btn-submit:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
    .pipeline-status {
      display: none;
      margin-top: 2rem;
      border-top: 1px solid var(--surface-border);
      padding-top: 2rem;
    }
    .status-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1.5rem;
    }
    .spinner {
      width: 20px;
      height: 20px;
      border: 3px solid rgba(255, 255, 255, 0.2);
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      display: inline-block;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .agents-list {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      margin-bottom: 2rem;
    }
    .agent-item {
      display: flex;
      align-items: center;
      gap: 1rem;
      background: #0b0f19;
      border: 1px solid var(--surface-border);
      padding: 0.85rem 1.25rem;
      border-radius: var(--radius-sm);
      font-size: 0.95rem;
    }
    .agent-icon { font-size: 1.25rem; }
    .agent-title { font-weight: 600; flex: 1; }
    .agent-state {
      font-size: 0.8rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-muted);
    }
    .result-card {
      display: none;
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 1.5rem;
      border-radius: var(--radius);
      text-align: center;
    }
    .result-card h3 {
      font-size: 1.35rem;
      color: #34d399;
      margin-bottom: 0.5rem;
    }
    .result-card p {
      color: #d1d5db;
      font-size: 0.95rem;
      margin-bottom: 1.5rem;
    }
    .btn-download {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background: var(--success);
      color: #fff;
      font-weight: 700;
      text-decoration: none;
      padding: 0.85rem 2rem;
      border-radius: var(--radius-sm);
      font-size: 1rem;
      transition: all 0.15s;
    }
    .btn-download:hover { background: #059669; transform: translateY(-1px); }
  </style>
</head>
<body>
  <header class="header">
    <div class="header-content">
      <div class="brand">
        <span>🤖</span>
        <span>AI Coding Team</span>
        <span class="badge">LangGraph Multi-Agent</span>
      </div>
      <a href="/docs" target="_blank" class="docs-link">Swagger API Docs ↗</a>
    </div>
  </header>

  <main class="container">
    <div class="hero">
      <h1>Autonomous Full-Stack Engineering</h1>
      <p>Enter any plain-English prompt. Five autonomous agents design, code, test, and document a production-ready web app.</p>
    </div>

    <div class="card">
      <label for="promptInput">What application do you want to build?</label>
      <textarea id="promptInput" placeholder="e.g. Build a food delivery website with restaurants, menus, and orders"></textarea>
      
      <div class="suggestions">
        <span class="pill" onclick="setPrompt('Build a food delivery website with restaurants, menus, and orders')">🍽️ Food Delivery Platform</span>
        <span class="pill" onclick="setPrompt('Build an online bookstore with book catalog, reviews, and shopping cart')">📚 Bookstore</span>
        <span class="pill" onclick="setPrompt('Build a fitness workout and exercise tracking application')">🏋️ Fitness Tracker</span>
      </div>

      <button id="submitBtn" class="btn-submit" onclick="startBuild()">
        <span>Generate Full-Stack Project</span>
        <span>🚀</span>
      </button>

      <div id="pipelineStatus" class="pipeline-status">
        <div class="status-header">
          <div style="display: flex; align-items: center; gap: 0.75rem;">
            <div class="spinner" id="statusSpinner"></div>
            <strong id="statusText">Agents executing pipeline...</strong>
          </div>
          <span id="taskIdLabel" style="font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--text-muted);"></span>
        </div>

        <div class="agents-list">
          <div class="agent-item" id="agent-pm">
            <span class="agent-icon">📋</span>
            <span class="agent-title">Project Manager</span>
            <span class="agent-state" id="state-pm">Waiting...</span>
          </div>
          <div class="agent-item" id="agent-backend">
            <span class="agent-icon">⚙️</span>
            <span class="agent-title">Backend Developer</span>
            <span class="agent-state" id="state-backend">Waiting...</span>
          </div>
          <div class="agent-item" id="agent-frontend">
            <span class="agent-icon">🎨</span>
            <span class="agent-title">Frontend Developer</span>
            <span class="agent-state" id="state-frontend">Waiting...</span>
          </div>
          <div class="agent-item" id="agent-qa">
            <span class="agent-icon">🧪</span>
            <span class="agent-title">QA Engineer (In-Memory Mongo & Jest)</span>
            <span class="agent-state" id="state-qa">Waiting...</span>
          </div>
          <div class="agent-item" id="agent-docs">
            <span class="agent-icon">📝</span>
            <span class="agent-title">Documentation Writer</span>
            <span class="agent-state" id="state-docs">Waiting...</span>
          </div>
        </div>

        <div id="resultCard" class="result-card">
          <h3 id="resultTitle">🎉 Project Generated Successfully!</h3>
          <p id="resultDesc">All 5 agents completed their work and verified the code.</p>
          <a id="downloadBtn" href="#" class="btn-download">⬇️ Download Ready-to-Run (.ZIP)</a>
        </div>
      </div>
    </div>
  </main>

  <script>
    function setPrompt(text) {
      document.getElementById('promptInput').value = text;
    }

    let pollInterval = null;

    async function startBuild() {
      const prompt = document.getElementById('promptInput').value.trim();
      if (!prompt) return alert('Please enter an application prompt.');

      const submitBtn = document.getElementById('submitBtn');
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span>Orchestrating Agents...</span> <div class="spinner"></div>';

      document.getElementById('pipelineStatus').style.display = 'block';
      document.getElementById('resultCard').style.display = 'none';
      document.getElementById('state-pm').textContent = 'In Progress...';
      document.getElementById('state-pm').style.color = '#60a5fa';

      try {
        const res = await fetch('/build/async', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_prompt: prompt })
        });
        const data = await res.json();
        const taskId = data.task_id;
        document.getElementById('taskIdLabel').textContent = 'Task: ' + taskId.slice(0, 8);

        pollInterval = setInterval(() => checkStatus(taskId), 3000);
      } catch (err) {
        alert('Failed to start build: ' + err.message);
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>Generate Full-Stack Project</span> <span>🚀</span>';
      }
    }

    async function checkStatus(taskId) {
      try {
        const res = await fetch('/build/status/' + taskId);
        const task = await res.json();

        if (task.status === 'in_progress') {
          document.getElementById('statusText').textContent = 'Agents collaborating (PM ➔ Backend ➔ Frontend ➔ QA ➔ Docs)...';
        } else if (task.status === 'done') {
          clearInterval(pollInterval);
          document.getElementById('statusSpinner').style.display = 'none';
          document.getElementById('statusText').textContent = 'Build Complete!';
          document.getElementById('statusText').style.color = '#34d399';

          ['pm', 'backend', 'frontend', 'qa', 'docs'].forEach(id => {
            const el = document.getElementById('state-' + id);
            el.textContent = 'Completed ✓';
            el.style.color = '#34d399';
          });

          const resData = task.result;
          const cleanName = resData.assembly ? resData.assembly.clean_name : 'app';
          const downloadUrl = resData.assembly ? resData.assembly.download_url : '/download/' + cleanName;

          document.getElementById('resultCard').style.display = 'block';
          document.getElementById('resultTitle').textContent = '🎉 ' + (resData.spec ? resData.spec.app_name : 'Application') + ' Ready!';
          document.getElementById('resultDesc').textContent = 'Includes Express backend, React Vite frontend, automated Jest tests, and API reference documentation.';
          document.getElementById('downloadBtn').href = downloadUrl;
          document.getElementById('downloadBtn').textContent = '⬇️ Download ' + cleanName + '.zip';

          const submitBtn = document.getElementById('submitBtn');
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span>Generate Another Project</span> <span>🚀</span>';
        } else if (task.status === 'failed') {
          clearInterval(pollInterval);
          document.getElementById('statusSpinner').style.display = 'none';
          document.getElementById('statusText').textContent = 'Build Failed: ' + (task.error || 'Unknown error');
          document.getElementById('statusText').style.color = '#f87171';
          document.getElementById('submitBtn').disabled = false;
          document.getElementById('submitBtn').innerHTML = '<span>Retry Generation</span> <span>🚀</span>';
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return DASHBOARD_HTML


def _run_and_assemble(task_id: str, user_prompt: str) -> dict:
    state = _graph.invoke(initial_state(task_id, user_prompt))
    if state.get("backend_output") and state.get("frontend_output"):
        assembly = assemble_project(
            task_id=task_id,
            spec=state.get("spec", {}),
            backend_output=state.get("backend_output", {}),
            frontend_output=state.get("frontend_output", {}),
            qa_report=state.get("qa_report", {}),
            docs_output=state.get("docs_output", {}),
        )
        assembly["download_url"] = f"/download/{assembly['clean_name']}"
        state["assembly"] = assembly
    return state


@app.post("/build")
def build(req: BuildRequest):
    task_id = str(uuid.uuid4())
    final_state = _run_and_assemble(task_id, req.user_prompt)
    return final_state


def _async_worker(task_id: str, user_prompt: str):
    try:
        _build_tasks[task_id]["status"] = "in_progress"
        final_state = _run_and_assemble(task_id, user_prompt)
        _build_tasks[task_id]["status"] = "done"
        _build_tasks[task_id]["result"] = final_state
    except Exception as exc:
        _build_tasks[task_id]["status"] = "failed"
        _build_tasks[task_id]["error"] = str(exc)


@app.post("/build/async")
def build_async(req: BuildRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    _build_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "result": None,
    }
    background_tasks.add_task(_async_worker, task_id, req.user_prompt)
    return {"task_id": task_id, "status": "pending"}


@app.get("/build/status/{task_id}")
def build_status(task_id: str):
    task = _build_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/download/{clean_name}")
def download(clean_name: str):
    zip_path = os.path.join("output", f"{clean_name}.zip")
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail=f"Project zip archive {clean_name}.zip not found")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{clean_name}.zip",
    )
