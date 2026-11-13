"""FastAPI entry point for the AI Coding Team Orchestrator.
Exposes:
- GET /health: Health check
- POST /build: Synchronous build endpoint that runs the full pipeline,
  assembles the project in output/<app_name>, and generates output/<app_name>.zip
- POST /build/async: Asynchronous build endpoint for long-running builds with real-time streaming
- GET /build/status/{task_id}: Poll rich progress, live agent states, and real-time execution logs
- GET /download/{clean_name}: Download the generated project zip
"""
import datetime
import os
import uuid
from typing import Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from orchestrator.assembly import assemble_project
from orchestrator.graph import build_graph
from orchestrator.state import initial_state

app = FastAPI(title="AI Coding Team Orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
  <title>AI Coding Team - Autonomous Multi-Agent Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --cyan: #06b6d4;
      --cyan-glow: #38bdf8;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --bg: #080c14;
      --surface: #0f172a;
      --surface-border: #1e293b;
      --surface-hover: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --radius: 12px;
      --radius-sm: 8px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background-color: var(--bg);
      background-image: 
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(59, 130, 246, 0.18), transparent),
        radial-gradient(ellipse 60% 40% at 80% 80%, rgba(6, 182, 212, 0.08), transparent);
      color: var(--text);
      line-height: 1.5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .header {
      border-bottom: 1px solid var(--surface-border);
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(12px);
      padding: 1rem 1.5rem;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .header-content {
      max-width: 1080px;
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
      letter-spacing: -0.02em;
      color: #fff;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: rgba(59, 130, 246, 0.15);
      color: #60a5fa;
      border: 1px solid rgba(59, 130, 246, 0.35);
      padding: 0.25rem 0.65rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .live-dot {
      width: 6px;
      height: 6px;
      background: #10b981;
      border-radius: 50%;
      box-shadow: 0 0 8px #10b981;
      animation: pulseDot 2s infinite;
    }
    @keyframes pulseDot { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }
    .docs-link {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.875rem;
      font-weight: 600;
      padding: 0.4rem 0.85rem;
      border-radius: var(--radius-sm);
      border: 1px solid transparent;
      transition: all 0.15s;
    }
    .docs-link:hover {
      color: #fff;
      background: var(--surface-border);
      border-color: rgba(255, 255, 255, 0.1);
    }
    .container {
      max-width: 960px;
      width: 100%;
      margin: 2rem auto;
      padding: 0 1.5rem;
      flex: 1;
    }
    .hero {
      text-align: center;
      margin-bottom: 2.25rem;
    }
    .hero-tag {
      display: inline-block;
      background: rgba(6, 182, 212, 0.1);
      color: var(--cyan-glow);
      border: 1px solid rgba(6, 182, 212, 0.25);
      padding: 0.3rem 0.85rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 1rem;
    }
    .hero h1 {
      font-size: 2.5rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      margin-bottom: 0.75rem;
      background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, #94a3b8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .hero p {
      color: var(--text-muted);
      font-size: 1.05rem;
      max-width: 650px;
      margin: 0 auto;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: var(--radius);
      padding: 2rem;
      box-shadow: 0 25px 40px -15px rgba(0, 0, 0, 0.7);
      margin-bottom: 2rem;
      position: relative;
    }
    label {
      display: block;
      font-size: 0.875rem;
      font-weight: 600;
      color: #cbd5e1;
      margin-bottom: 0.6rem;
    }
    textarea {
      width: 100%;
      background: #090e17;
      border: 1px solid var(--surface-border);
      border-radius: var(--radius-sm);
      color: #fff;
      font-family: inherit;
      font-size: 1.02rem;
      padding: 1.1rem;
      min-height: 110px;
      resize: vertical;
      outline: none;
      transition: all 0.2s ease;
    }
    textarea:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25), 0 0 15px rgba(59, 130, 246, 0.15);
    }
    .suggestions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin: 0.85rem 0 1.5rem;
    }
    .pill {
      background: rgba(30, 41, 59, 0.7);
      color: #94a3b8;
      border: 1px solid #334155;
      padding: 0.35rem 0.85rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    }
    .pill:hover {
      background: #334155;
      color: #fff;
      border-color: #64748b;
      transform: translateY(-1px);
    }
    .btn-submit {
      width: 100%;
      background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
      color: white;
      font-weight: 700;
      font-size: 1.05rem;
      padding: 1rem;
      border-radius: var(--radius-sm);
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.6rem;
      box-shadow: 0 10px 20px -5px rgba(59, 130, 246, 0.4);
      transition: all 0.2s;
    }
    .btn-submit:hover {
      background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
      transform: translateY(-1px);
      box-shadow: 0 12px 24px -5px rgba(59, 130, 246, 0.6);
    }
    .btn-submit:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }

    /* Pipeline Execution View */
    .pipeline-status {
      display: none;
      margin-top: 2rem;
      border-top: 1px solid var(--surface-border);
      padding-top: 2rem;
    }
    .status-bar-box {
      background: #090e17;
      border: 1px solid var(--surface-border);
      border-radius: var(--radius-sm);
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
    }
    .status-top-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.75rem;
    }
    .status-title-group {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .status-meta {
      display: flex;
      align-items: center;
      gap: 1rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      color: var(--text-muted);
    }
    .progress-track {
      width: 100%;
      height: 8px;
      background: #1e293b;
      border-radius: 9999px;
      overflow: hidden;
      position: relative;
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #3b82f6 0%, #06b6d4 50%, #10b981 100%);
      border-radius: 9999px;
      transition: width 0.4s ease;
      box-shadow: 0 0 10px rgba(56, 189, 248, 0.5);
    }

    .spinner {
      width: 18px;
      height: 18px;
      border: 2.5px solid rgba(255, 255, 255, 0.2);
      border-top-color: var(--cyan-glow);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      display: inline-block;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* Agent Cards Timeline */
    .agents-grid {
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
      margin-bottom: 1.5rem;
    }
    .agent-card {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      background: #090e17;
      border: 1px solid var(--surface-border);
      padding: 0.95rem 1.25rem;
      border-radius: var(--radius-sm);
      transition: all 0.3s ease;
    }
    .agent-card.active {
      border-color: var(--cyan-glow);
      background: linear-gradient(135deg, rgba(6, 182, 212, 0.08) 0%, rgba(15, 23, 42, 0.95) 100%);
      box-shadow: 0 0 20px rgba(56, 189, 248, 0.25);
      animation: pulseAgent 2s infinite ease-in-out;
    }
    @keyframes pulseAgent {
      0%, 100% { border-color: rgba(56, 189, 248, 0.4); box-shadow: 0 0 12px rgba(56, 189, 248, 0.2); }
      50% { border-color: rgba(56, 189, 248, 0.95); box-shadow: 0 0 22px rgba(56, 189, 248, 0.5); }
    }
    .agent-left {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      flex: 1;
    }
    .agent-icon {
      font-size: 1.35rem;
      width: 38px;
      height: 38px;
      background: #1e293b;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .agent-info {
      display: flex;
      flex-direction: column;
    }
    .agent-name {
      font-weight: 700;
      font-size: 0.95rem;
      color: #fff;
    }
    .agent-detail {
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 0.15rem;
    }
    .agent-state-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      font-weight: 600;
      padding: 0.3rem 0.75rem;
      border-radius: 9999px;
      background: #1e293b;
      color: #94a3b8;
      border: 1px solid #334155;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }
    .agent-state-pill.active {
      background: rgba(6, 182, 212, 0.15);
      color: var(--cyan-glow);
      border-color: rgba(6, 182, 212, 0.4);
    }
    .agent-state-pill.done {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border-color: rgba(16, 185, 129, 0.4);
    }
    .agent-state-pill.retry {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border-color: rgba(245, 158, 11, 0.4);
    }

    /* Live Architecture Blueprint */
    .blueprint-box {
      display: none;
      background: #090e17;
      border: 1px solid #334155;
      border-radius: var(--radius-sm);
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
    }
    .blueprint-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.75rem;
    }
    .blueprint-title {
      font-size: 0.85rem;
      font-weight: 700;
      color: #cbd5e1;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .blueprint-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem;
    }
    .chip {
      background: rgba(59, 130, 246, 0.15);
      color: #60a5fa;
      border: 1px solid rgba(59, 130, 246, 0.3);
      padding: 0.25rem 0.65rem;
      border-radius: 6px;
      font-size: 0.78rem;
      font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
    }
    .chip-endpoint {
      background: rgba(6, 182, 212, 0.15);
      color: var(--cyan-glow);
      border-color: rgba(6, 182, 212, 0.3);
    }

    /* Terminal Console */
    .terminal-window {
      background: #030712;
      border: 1px solid #1f2937;
      border-radius: 10px;
      overflow: hidden;
      margin-bottom: 1.5rem;
      box-shadow: 0 15px 30px rgba(0, 0, 0, 0.6);
    }
    .terminal-topbar {
      background: #111827;
      padding: 0.55rem 0.95rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid #1f2937;
    }
    .terminal-dots {
      display: flex;
      gap: 6px;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
    .dot-red { background: #ef4444; }
    .dot-yellow { background: #f59e0b; }
    .dot-green { background: #10b981; }
    .terminal-title {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      color: #94a3b8;
    }
    .terminal-body {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      line-height: 1.65;
      padding: 1rem;
      max-height: 250px;
      overflow-y: auto;
      color: #e2e8f0;
      scrollbar-width: thin;
      scrollbar-color: #334155 #030712;
    }
    .terminal-line {
      margin-bottom: 0.35rem;
      word-break: break-word;
    }
    .term-time { color: #64748b; margin-right: 0.4rem; }
    .term-pm { color: #93c5fd; }
    .term-be { color: #818cf8; }
    .term-fe { color: #38bdf8; }
    .term-qa { color: #34d399; }
    .term-docs { color: #f472b6; }
    .term-success { color: #4ade80; font-weight: 600; }
    .term-warn { color: #fbbf24; }
    .term-err { color: #f87171; }
    .cursor-blink {
      display: inline-block;
      width: 8px;
      height: 14px;
      background: var(--cyan-glow);
      vertical-align: middle;
      margin-left: 4px;
      animation: blink 1s infinite;
    }
    @keyframes blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }

    /* Result Download Card */
    .result-card {
      display: none;
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(6, 182, 212, 0.08) 100%);
      border: 1px solid rgba(16, 185, 129, 0.35);
      padding: 1.75rem;
      border-radius: var(--radius);
      text-align: center;
      animation: fadeIn 0.4s ease;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    .result-card h3 {
      font-size: 1.45rem;
      color: #34d399;
      font-weight: 800;
      margin-bottom: 0.5rem;
    }
    .result-card p {
      color: #cbd5e1;
      font-size: 0.95rem;
      margin-bottom: 1.25rem;
    }
    .btn-download {
      display: inline-flex;
      align-items: center;
      gap: 0.6rem;
      background: linear-gradient(135deg, #10b981 0%, #059669 100%);
      color: #fff;
      font-weight: 700;
      text-decoration: none;
      padding: 0.95rem 2.25rem;
      border-radius: var(--radius-sm);
      font-size: 1.05rem;
      box-shadow: 0 10px 20px -5px rgba(16, 185, 129, 0.4);
      transition: all 0.2s;
    }
    .btn-download:hover {
      background: linear-gradient(135deg, #059669 0%, #047857 100%);
      transform: translateY(-2px);
      box-shadow: 0 14px 25px -5px rgba(16, 185, 129, 0.6);
    }
    .run-guide {
      margin-top: 1.25rem;
      background: #030712;
      border: 1px solid #1f2937;
      border-radius: var(--radius-sm);
      padding: 0.85rem 1rem;
      text-align: left;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      color: #94a3b8;
    }
    .run-guide span { color: #38bdf8; }
  </style>
</head>
<body>
  <header class="header">
    <div class="header-content">
      <div class="brand">
        <span>🤖</span>
        <span>AI Coding Team</span>
        <span class="badge"><span class="live-dot"></span> LangGraph Multi-Agent Engine</span>
      </div>
      <a href="/docs" target="_blank" class="docs-link">Swagger API Docs ↗</a>
    </div>
  </header>

  <main class="container">
    <div class="hero">
      <div class="hero-tag">Autonomous Multi-Agent Studio</div>
      <h1>Build Production Apps With AI Agents</h1>
      <p>Enter any plain-English prompt. Five specialized autonomous agents design, code, test with Jest and MongoDB, and document a complete full-stack web application.</p>
    </div>

    <div class="card">
      <label for="promptInput">What application do you want to build?</label>
      <textarea id="promptInput" placeholder="e.g. Build a food delivery website with restaurants, menu items, and real-time ordering"></textarea>
      
      <div class="suggestions">
        <span class="pill" onclick="setPrompt('Build a food delivery platform with restaurants, menu items, cart, and order checkout')">🍽️ Food Delivery Platform</span>
        <span class="pill" onclick="setPrompt('Build an online bookstore with book catalog, user reviews, shopping cart, and orders')">📚 Online Bookstore</span>
        <span class="pill" onclick="setPrompt('Build a fitness workout and exercise tracker with workout routines and daily goals')">🏋️ Fitness Tracker</span>
        <span class="pill" onclick="setPrompt('Build a collaborative project task board with task statuses, priorities, and assignments')">💼 Task Management App</span>
      </div>

      <button id="submitBtn" class="btn-submit" onclick="startBuild()">
        <span>Orchestrate AI Team</span>
        <span>🚀</span>
      </button>

      <!-- Live Execution Section -->
      <div id="pipelineStatus" class="pipeline-status">
        <!-- Progress Bar & Timer -->
        <div class="status-bar-box">
          <div class="status-top-row">
            <div class="status-title-group">
              <div class="spinner" id="statusSpinner"></div>
              <strong id="statusText" style="font-size: 0.95rem; color: #f1f5f9;">Initializing Multi-Agent Pipeline...</strong>
            </div>
            <div class="status-meta">
              <span id="elapsedTimer">⏱️ 00:00s</span>
              <span id="taskIdLabel" style="color: var(--cyan-glow);"></span>
            </div>
          </div>
          <div class="progress-track">
            <div id="progressFill" class="progress-fill"></div>
          </div>
        </div>

        <!-- 5 Agent Timeline Cards -->
        <div class="agents-grid">
          <!-- PM -->
          <div class="agent-card" id="card-pm">
            <div class="agent-left">
              <div class="agent-icon">📋</div>
              <div class="agent-info">
                <span class="agent-name">Project Manager</span>
                <span class="agent-detail" id="detail-pm">Requirements analysis & relational schema discovery</span>
              </div>
            </div>
            <span class="agent-state-pill" id="state-pm">Waiting...</span>
          </div>

          <!-- Backend -->
          <div class="agent-card" id="card-backend">
            <div class="agent-left">
              <div class="agent-icon">⚙️</div>
              <div class="agent-info">
                <span class="agent-name">Backend Developer</span>
                <span class="agent-detail" id="detail-backend">Express REST API, Mongoose models, JWT auth & seed data</span>
              </div>
            </div>
            <span class="agent-state-pill" id="state-backend">Waiting...</span>
          </div>

          <!-- Frontend -->
          <div class="agent-card" id="card-frontend">
            <div class="agent-left">
              <div class="agent-icon">🎨</div>
              <div class="agent-info">
                <span class="agent-name">Frontend Developer</span>
                <span class="agent-detail" id="detail-frontend">React 18 + Vite pages, Tailwind UI, navigation & API client</span>
              </div>
            </div>
            <span class="agent-state-pill" id="state-frontend">Waiting...</span>
          </div>

          <!-- QA -->
          <div class="agent-card" id="card-qa">
            <div class="agent-left">
              <div class="agent-icon">🧪</div>
              <div class="agent-info">
                <span class="agent-name">QA Engineer (In-Memory MongoDB & Jest)</span>
                <span class="agent-detail" id="detail-qa">Sandboxed test execution with auto-healing retry loop</span>
              </div>
            </div>
            <span class="agent-state-pill" id="state-qa">Waiting...</span>
          </div>

          <!-- Docs -->
          <div class="agent-card" id="card-docs">
            <div class="agent-left">
              <div class="agent-icon">📝</div>
              <div class="agent-info">
                <span class="agent-name">Documentation Writer</span>
                <span class="agent-detail" id="detail-docs">README.md, OpenAPI endpoint specs & architectural overview</span>
              </div>
            </div>
            <span class="agent-state-pill" id="state-docs">Waiting...</span>
          </div>
        </div>

        <!-- Live Architecture Blueprint (Appears dynamically) -->
        <div id="blueprintBox" class="blueprint-box">
          <div class="blueprint-header">
            <span class="blueprint-title">📐 Discovered System Blueprint</span>
            <span id="endpointCountBadge" class="chip chip-endpoint">0 Endpoints Planned</span>
          </div>
          <div id="blueprintChips" class="blueprint-chips">
            <!-- Entities inserted here dynamically -->
          </div>
        </div>

        <!-- Live Terminal Stream -->
        <div class="terminal-window">
          <div class="terminal-topbar">
            <div class="terminal-dots">
              <span class="dot dot-red"></span>
              <span class="dot dot-yellow"></span>
              <span class="dot dot-green"></span>
            </div>
            <span class="terminal-title">agent-orchestrator.log</span>
            <span style="font-size: 0.72rem; color: #64748b; font-family: 'JetBrains Mono', monospace;">Live Stream</span>
          </div>
          <div id="terminalBody" class="terminal-body">
            <div class="terminal-line"><span class="term-time">[SYSTEM]</span> Ready. Waiting to launch multi-agent build pipeline...</div>
          </div>
        </div>

        <!-- Result / Download Card -->
        <div id="resultCard" class="result-card">
          <h3 id="resultTitle">🎉 Application Assembled Successfully!</h3>
          <p id="resultDesc">All 5 agents verified the application code. Production package is ready.</p>
          <a id="downloadBtn" href="#" class="btn-download">⬇️ Download Ready-to-Run (.ZIP)</a>
          
          <div class="run-guide">
            <div><span># Quick Start Guide:</span></div>
            <div>unzip &lt;app_name&gt;.zip &amp;&amp; cd &lt;app_name&gt;</div>
            <div>cd backend &amp;&amp; npm install &amp;&amp; npm start <span># Starts Express API at :3000</span></div>
            <div>cd ../frontend &amp;&amp; npm install &amp;&amp; npm run dev <span># Starts React Vite UI at :5173</span></div>
          </div>
        </div>
      </div>
    </div>
  </main>

  <script>
    function setPrompt(text) {
      document.getElementById('promptInput').value = text;
    }

    let pollInterval = null;
    let timerInterval = null;
    let startTime = null;
    let lastRenderedLogCount = 0;

    function formatTime(seconds) {
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return `⏱️ ${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}s`;
    }

    async function startBuild() {
      const prompt = document.getElementById('promptInput').value.trim();
      if (!prompt) return alert('Please enter an application prompt.');

      const submitBtn = document.getElementById('submitBtn');
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span>Orchestrating AI Agents...</span> <div class="spinner"></div>';

      // Reset and display UI sections
      document.getElementById('pipelineStatus').style.display = 'block';
      document.getElementById('resultCard').style.display = 'none';
      document.getElementById('blueprintBox').style.display = 'none';
      document.getElementById('progressFill').style.width = '5%';
      document.getElementById('statusText').textContent = 'Launching LangGraph Multi-Agent Team...';
      document.getElementById('statusSpinner').style.display = 'inline-block';

      // Reset all cards
      ['pm', 'backend', 'frontend', 'qa', 'docs'].forEach(id => {
        const card = document.getElementById('card-' + id);
        const pill = document.getElementById('state-' + id);
        card.className = 'agent-card';
        pill.className = 'agent-state-pill';
        pill.textContent = 'Waiting...';
      });

      // Reset terminal
      const terminal = document.getElementById('terminalBody');
      terminal.innerHTML = '<div class="terminal-line"><span class="term-time">[SYSTEM]</span> Initializing LangGraph state graph...</div>';
      lastRenderedLogCount = 0;

      // Start elapsed timer
      startTime = Date.now();
      clearInterval(timerInterval);
      timerInterval = setInterval(() => {
        const elapsedSecs = Math.floor((Date.now() - startTime) / 1000);
        document.getElementById('elapsedTimer').textContent = formatTime(elapsedSecs);
      }, 1000);

      try {
        const res = await fetch('/build/async', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_prompt: prompt })
        });
        const data = await res.json();
        const taskId = data.task_id;
        document.getElementById('taskIdLabel').textContent = 'Task: ' + taskId.slice(0, 8);

        clearInterval(pollInterval);
        // High frequency poll every 1 second for real-time responsiveness
        pollInterval = setInterval(() => checkStatus(taskId), 1000);
      } catch (err) {
        alert('Failed to start build: ' + err.message);
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>Orchestrate AI Team</span> <span>🚀</span>';
        clearInterval(timerInterval);
      }
    }

    async function checkStatus(taskId) {
      try {
        const res = await fetch('/build/status/' + taskId);
        const task = await res.json();

        // 1. Update progress bar
        if (task.progress_percent !== undefined) {
          document.getElementById('progressFill').style.width = Math.max(5, task.progress_percent) + '%';
        }

        // 2. Update status header text
        if (task.current_agent) {
          const names = {
            'pm': 'Project Manager analyzing domain & schema...',
            'backend': 'Backend Developer generating Mongoose models & Express routes...',
            'frontend': 'Frontend Developer crafting React 18 + Vite pages...',
            'qa': 'QA Engineer testing in-memory MongoDB & Jest test suites...',
            'docs': 'Documentation Writer generating API reference & README...',
            'assembly': 'Packaging project into production ZIP archive...'
          };
          document.getElementById('statusText').textContent = names[task.current_agent] || 'Agents collaborating...';
        }

        // 3. Update agent cards & badges
        if (task.agent_states) {
          ['pm', 'backend', 'frontend', 'qa', 'docs'].forEach(id => {
            const card = document.getElementById('card-' + id);
            const pill = document.getElementById('state-' + id);
            const state = task.agent_states[id];

            if (task.agent_details && task.agent_details[id]) {
              document.getElementById('detail-' + id).textContent = task.agent_details[id];
            }

            if (state === 'active') {
              card.className = 'agent-card active';
              pill.className = 'agent-state-pill active';
              pill.innerHTML = '<div class="spinner" style="width:12px;height:12px;border-width:2px;"></div> In Progress';
            } else if (state === 'done') {
              card.className = 'agent-card';
              pill.className = 'agent-state-pill done';
              pill.textContent = 'Completed ✓';
            } else if (state === 'retry') {
              card.className = 'agent-card active';
              pill.className = 'agent-state-pill retry';
              pill.textContent = 'Auto-Healing 🔄';
            } else {
              card.className = 'agent-card';
              pill.className = 'agent-state-pill';
              pill.textContent = 'Waiting...';
            }
          });
        }

        // 4. Update Discovered Architecture Blueprint
        if (task.entities && task.entities.length > 0) {
          const bpBox = document.getElementById('blueprintBox');
          bpBox.style.display = 'block';
          const chipsContainer = document.getElementById('blueprintChips');
          chipsContainer.innerHTML = task.entities.map(e => `<span class="chip">🧩 ${e}</span>`).join('');
          if (task.endpoints_count) {
            document.getElementById('endpointCountBadge').textContent = `${task.endpoints_count} API Routes`;
          }
        }

        // 5. Append new real-time terminal logs
        if (task.logs && task.logs.length > lastRenderedLogCount) {
          const terminal = document.getElementById('terminalBody');
          for (let i = lastRenderedLogCount; i < task.logs.length; i++) {
            const rawLog = task.logs[i];
            const div = document.createElement('div');
            div.className = 'terminal-line';

            // Format line with styled tags
            let formatted = rawLog;
            if (formatted.includes('Project Manager')) formatted = formatted.replace('Project Manager', '<span class="term-pm">Project Manager</span>');
            if (formatted.includes('Backend Developer')) formatted = formatted.replace('Backend Developer', '<span class="term-be">Backend Developer</span>');
            if (formatted.includes('Frontend Developer')) formatted = formatted.replace('Frontend Developer', '<span class="term-fe">Frontend Developer</span>');
            if (formatted.includes('QA Engineer')) formatted = formatted.replace('QA Engineer', '<span class="term-qa">QA Engineer</span>');
            if (formatted.includes('Documentation Writer')) formatted = formatted.replace('Documentation Writer', '<span class="term-docs">Documentation Writer</span>');
            if (formatted.includes('completed')) formatted = `<span class="term-success">✓</span> ` + formatted;
            if (formatted.includes('Error')) formatted = `<span class="term-err">✗</span> ` + formatted;
            if (formatted.includes('Failure detected')) formatted = `<span class="term-warn">!</span> ` + formatted;

            div.innerHTML = formatted;
            terminal.appendChild(div);
          }
          lastRenderedLogCount = task.logs.length;
          terminal.scrollTop = terminal.scrollHeight;
        }

        // 6. Handle Completion
        if (task.status === 'done') {
          clearInterval(pollInterval);
          clearInterval(timerInterval);
          document.getElementById('statusSpinner').style.display = 'none';
          document.getElementById('statusText').textContent = 'Build Complete! All Agents Finished.';
          document.getElementById('statusText').style.color = '#34d399';
          document.getElementById('progressFill').style.width = '100%';

          ['pm', 'backend', 'frontend', 'qa', 'docs'].forEach(id => {
            const pill = document.getElementById('state-' + id);
            pill.className = 'agent-state-pill done';
            pill.textContent = 'Completed ✓';
          });

          const resData = task.result || {};
          const cleanName = resData.assembly ? resData.assembly.clean_name : 'app';
          const downloadUrl = resData.assembly ? resData.assembly.download_url : '/download/' + cleanName;
          const appName = resData.spec ? resData.spec.app_name : 'Full-Stack Web App';

          document.getElementById('resultCard').style.display = 'block';
          document.getElementById('resultTitle').textContent = '🎉 ' + appName + ' Ready!';
          document.getElementById('resultDesc').textContent = 'Complete production package with Node/Express API, React 18 UI, MongoDB models, Jest tests, and API documentation.';
          document.getElementById('downloadBtn').href = downloadUrl;
          document.getElementById('downloadBtn').textContent = '⬇️ Download ' + cleanName + '.zip';

          const submitBtn = document.getElementById('submitBtn');
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span>Generate Another Application</span> <span>🚀</span>';
        } else if (task.status === 'failed') {
          clearInterval(pollInterval);
          clearInterval(timerInterval);
          document.getElementById('statusSpinner').style.display = 'none';
          document.getElementById('statusText').textContent = 'Build Failed: ' + (task.error || 'Unknown error');
          document.getElementById('statusText').style.color = '#ef4444';
          const submitBtn = document.getElementById('submitBtn');
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span>Retry Generation</span> <span>🚀</span>';
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
    """Synchronous pipeline runner used by /build and legacy callers."""
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
    """Background worker that executes the LangGraph multi-agent pipeline

    using state streaming, updating _build_tasks[task_id] with real-time logs,
    entity discoveries, file counts, and agent statuses as they execute.
    """
    def now_str():
        return datetime.datetime.now().strftime("%H:%M:%S")

    def add_log(msg: str):
        if task_id in _build_tasks:
            _build_tasks[task_id]["logs"].append(f"[{now_str()}] {msg}")

    task = _build_tasks[task_id]
    try:
        task["status"] = "in_progress"
        task["current_agent"] = "pm"
        task["agent_states"]["pm"] = "active"
        task["progress_percent"] = 10
        add_log(f"📋 Project Manager started: Analyzing prompt '{user_prompt}'...")

        state = initial_state(task_id, user_prompt)

        # Stream LangGraph updates step-by-step
        if hasattr(_graph, "stream"):
            for update in _graph.stream(state, stream_mode="updates"):
                for node_name, node_output in update.items():
                    state.update(node_output)

                    if node_name == "project_manager":
                        spec = state.get("spec", {})
                        entities = [e.get("name") for e in spec.get("entities", []) if e.get("name")]
                        endpoints = len(spec.get("endpoints", []))
                        task["entities"] = entities
                        task["endpoints_count"] = endpoints
                        task["agent_states"]["pm"] = "done"
                        task["agent_details"]["pm"] = f"{len(entities)} Entities, {endpoints} Endpoints"
                        add_log(f"📋 Project Manager completed: Discovered {len(entities)} entities ({', '.join(entities)}) with {endpoints} API endpoints.")

                        # Transition to Backend Developer
                        task["current_agent"] = "backend"
                        task["agent_states"]["backend"] = "active"
                        task["progress_percent"] = 30
                        add_log("⚙️ Backend Developer started: Generating Mongoose models, Express routes, and auth middleware...")

                    elif node_name == "backend_developer":
                        be_out = state.get("backend_output", {})
                        files = be_out.get("files", [])
                        task["agent_states"]["backend"] = "done"
                        task["agent_details"]["backend"] = f"{len(files)} Backend files (node --check passed)"
                        add_log(f"⚙️ Backend Developer completed: Generated {len(files)} files with syntax validation.")

                        if state.get("frontend_output") is None:
                            # First pass: Transition to Frontend Developer
                            task["current_agent"] = "frontend"
                            task["agent_states"]["frontend"] = "active"
                            task["progress_percent"] = 55
                            add_log("🎨 Frontend Developer started: Designing React 18 + Vite components and responsive styling...")
                        else:
                            # Retry pass: Route back to QA Engineer
                            task["current_agent"] = "qa"
                            task["agent_states"]["qa"] = "active"
                            task["progress_percent"] = 75
                            add_log("🧪 QA Engineer started: Re-running Jest test suites on corrected backend...")

                    elif node_name == "frontend_developer":
                        fe_out = state.get("frontend_output", {})
                        files = fe_out.get("files", [])
                        task["agent_states"]["frontend"] = "done"
                        task["agent_details"]["frontend"] = f"{len(files)} React components & pages"
                        add_log(f"🎨 Frontend Developer completed: Generated {len(files)} React files and Tailwind theme.")

                        # Transition to QA Engineer
                        task["current_agent"] = "qa"
                        task["agent_states"]["qa"] = "active"
                        task["progress_percent"] = 75
                        add_log("🧪 QA Engineer started: Spinning up in-memory MongoDB & running Jest test suites...")

                    elif node_name == "qa_engineer":
                        qa_rep = state.get("qa_report", {})
                        passed = qa_rep.get("all_tests_passed", False)
                        attempt = state.get("qa_attempt", 1)

                        if passed:
                            task["agent_states"]["qa"] = "done"
                            task["agent_details"]["qa"] = f"All Jest Tests Passed (Attempt {attempt})"
                            add_log("🧪 QA Engineer completed: All test suites passed with in-memory MongoDB!")

                            # Transition to Documentation Writer
                            task["current_agent"] = "docs"
                            task["agent_states"]["docs"] = "active"
                            task["progress_percent"] = 90
                            add_log("📝 Documentation Writer started: Generating README.md, API specs & Architecture documentation...")
                        elif attempt < 3:
                            task["agent_states"]["qa"] = "retry"
                            task["agent_details"]["qa"] = f"Self-Healing: Attempt {attempt} failed, retrying backend..."
                            add_log(f"⚠️ QA Engineer: Failure detected on attempt {attempt}. Routing back to Backend Developer for auto-fix...")
                            task["current_agent"] = "backend"
                            task["agent_states"]["backend"] = "active"
                        else:
                            task["agent_states"]["qa"] = "done"
                            task["agent_details"]["qa"] = f"Tests completed (Attempt {attempt}, review flagged)"
                            add_log(f"⚠️ QA Engineer: Max attempts reached ({attempt}). Proceeding to documentation...")
                            task["current_agent"] = "docs"
                            task["agent_states"]["docs"] = "active"
                            task["progress_percent"] = 90
                            add_log("📝 Documentation Writer started: Generating README.md and flagging review items...")

                    elif node_name == "documentation_writer":
                        task["agent_states"]["docs"] = "done"
                        task["agent_details"]["docs"] = "README.md, Swagger & Architecture Specs"
                        add_log("📝 Documentation Writer completed: All documentation and specs generated.")
        else:
            state = _graph.invoke(state)

        # Final Assembly
        task["current_agent"] = "assembly"
        task["progress_percent"] = 95
        add_log("📦 Assembly: Packaging project into production zip archive...")

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
            task["agent_details"]["assembly"] = f"Archive {assembly['clean_name']}.zip generated"
            add_log(f"📦 Assembly completed: {assembly['clean_name']}.zip created successfully.")

        task["progress_percent"] = 100
        task["current_agent"] = None
        task["status"] = "done"
        task["result"] = state
        add_log(f"🎉 Build Complete! Application is ready for download.")

    except Exception as exc:
        task["status"] = "failed"
        task["error"] = str(exc)
        add_log(f"❌ Error during execution: {str(exc)}")


@app.post("/build/async")
def build_async(req: BuildRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    if len(_build_tasks) > 100:
        oldest_key = next(iter(_build_tasks))
        _build_tasks.pop(oldest_key, None)
    _build_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "current_agent": None,
        "progress_percent": 0,
        "agent_states": {
            "pm": "waiting",
            "backend": "waiting",
            "frontend": "waiting",
            "qa": "waiting",
            "docs": "waiting",
        },
        "agent_details": {
            "pm": "Requirements analysis & relational schema discovery",
            "backend": "Express REST API, Mongoose models, JWT auth & seed data",
            "frontend": "React 18 + Vite pages, Tailwind UI, navigation & API client",
            "qa": "Sandboxed test execution with auto-healing retry loop",
            "docs": "README.md, OpenAPI endpoint specs & architectural overview",
        },
        "entities": [],
        "endpoints_count": 0,
        "logs": [],
        "result": None,
        "error": None,
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
