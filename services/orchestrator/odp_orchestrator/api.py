from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse, FileResponse
from redis.asyncio import Redis
from pydantic import BaseModel, Field

# Optional: dockerless tests
try:
    import fakeredis.aioredis  # type: ignore
except Exception:  # pragma: no cover
    fakeredis = None  # type: ignore

from .db import MemoryWriter, create_engine
from .events import EventBus
from .models import ChatMessageRequest, Task, TaskCreateRequest
from .agent_runner import AgentRunConfig
from .orchestrator import Orchestrator
from .redis_store import RedisStore


class PromoteRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=2000)


class CompactChatRequest(BaseModel):
    task_id: UUID | None = None
    keep_last: int = Field(default=50, ge=0, le=5000)
    compact_n: int = Field(default=50, ge=1, le=5000)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        memory: MemoryWriter = app.state.memory
        orch: Orchestrator = app.state.orch
        if os.getenv("ODP_AUTO_MIGRATE", "1") == "1":
            await memory.init_schema()
        try:
            yield
        finally:
            # Ensure background tasks are cancelled/awaited before the event loop closes.
            for t in list(orch.background_tasks):
                t.cancel()
            if orch.background_tasks:
                await asyncio.gather(*list(orch.background_tasks), return_exceptions=True)

            # Close DB connections (aiosqlite will otherwise emit ResourceWarnings on gc).
            try:
                await memory.engine.dispose()
            except Exception:
                pass

            # Close redis connection if supported.
            try:
                r = app.state.redis
                if hasattr(r, "aclose"):
                    await r.aclose()  # type: ignore[attr-defined]
            except Exception:
                pass

    app = FastAPI(title="ODP Orchestrator", version="0.1", lifespan=lifespan)

    redis_url = os.getenv("ODP_REDIS_URL", "redis://localhost:6379/0")

    if os.getenv("ODP_FAKE_REDIS", "0") == "1":
        if fakeredis is None:  # pragma: no cover
            raise RuntimeError("fakeredis not installed but ODP_FAKE_REDIS=1")
        redis = fakeredis.aioredis.FakeRedis()
    else:
        redis = Redis.from_url(redis_url, decode_responses=False)
    # Expose clients for tests/debug.
    app.state.redis = redis

    store = RedisStore(redis)
    bus = EventBus(redis=redis, store=store)
    memory = MemoryWriter(create_engine())

    repo_root = Path(os.getenv("ODP_REPO_ROOT", Path(__file__).resolve().parents[3]))
    agent_cfg = AgentRunConfig(
        repo_root=repo_root,
        workspaces_root=Path(os.getenv("ODP_WORKSPACE_DIR", "runtime/workspaces")),
        artifacts_root=Path(os.getenv("ODP_ARTIFACT_DIR", "runtime/artifacts")),
        timeout_s=int(os.getenv("ODP_AGENT_TIMEOUT_S", "1200")),
    )
    orch = Orchestrator(store=store, bus=bus, memory=memory, agent_cfg=agent_cfg)

    # Expose for lifespan + tests/debug.
    app.state.memory = memory
    app.state.orch = orch
    app.state.bus = bus
    app.state.store = store
    app.state.metrics = {"requests_total": 0}

    def _rbac_tokens(env_key: str) -> set[str]:
        raw = os.getenv(env_key, "").strip()
        if not raw:
            return set()
        return {t.strip() for t in raw.split(",") if t.strip()}

    def _role_for_token(token: str) -> str | None:
        # Back-compat: single token acts as admin.
        if os.getenv("ODP_API_TOKEN") and token == os.getenv("ODP_API_TOKEN"):
            return "admin"
        if token in _rbac_tokens("ODP_RBAC_ADMIN_TOKENS"):
            return "admin"
        if token in _rbac_tokens("ODP_RBAC_WRITE_TOKENS"):
            return "writer"
        if token in _rbac_tokens("ODP_RBAC_READ_TOKENS"):
            return "reader"
        return None

    def _auth_enabled() -> bool:
        return bool(
            os.getenv("ODP_API_TOKEN")
            or os.getenv("ODP_RBAC_ADMIN_TOKENS")
            or os.getenv("ODP_RBAC_WRITE_TOKENS")
            or os.getenv("ODP_RBAC_READ_TOKENS")
        )

    def _required_role(path: str, method: str) -> str:
        # Conservative defaults.
        if method in {"GET", "HEAD"}:
            return "reader"
        if path.startswith("/projects/") and ("/promote" in path or path.endswith("/chat/compact")):
            return "admin"
        return "writer"

    def _role_rank(role: str) -> int:
        return {"reader": 1, "writer": 2, "admin": 3}.get(role, 0)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        app.state.metrics["requests_total"] += 1
        do_log = os.getenv("ODP_LOG_REQUESTS", "0") == "1"

        if not _auth_enabled():
            resp = await call_next(request)
            if do_log:
                print(
                    json.dumps(
                        {
                            "method": request.method,
                            "path": request.url.path,
                            "status": resp.status_code,
                        }
                    )
                )
            return resp

        # Allow health/metrics without auth.
        if request.url.path in {"/healthz", "/metrics"}:
            resp = await call_next(request)
            if do_log:
                print(json.dumps({"method": request.method, "path": request.url.path, "status": resp.status_code}))
            return resp

        auth = request.headers.get("authorization", "")
        token = ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
        role = _role_for_token(token) if token else None
        required = _required_role(request.url.path, request.method)

        if not role or _role_rank(role) < _role_rank(required):
            resp = JSONResponse({"detail": "unauthorized"}, status_code=401)
            if do_log:
                print(json.dumps({"method": request.method, "path": request.url.path, "status": resp.status_code}))
            return resp

        request.state.role = role
        resp = await call_next(request)
        if do_log:
            print(json.dumps({"method": request.method, "path": request.url.path, "status": resp.status_code, "role": role}))
        return resp


    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/metrics")
    async def metrics() -> str:
        m = app.state.metrics
        return "\n".join([f"odp_requests_total {m['requests_total']}"])

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ODP Dashboard</title>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: ui-sans-serif, system-ui; background: #0b0f14; color: #e6edf3; }
    .app { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }
    .sidebar { background: #0f141a; border-right: 1px solid #1f2a36; padding: 24px; }
    .brand { font-size: 26px; font-weight: 700; letter-spacing: 0.4px; }
    .brand-sub { color: #9aa4b2; font-size: 12px; margin-top: 4px; }
    .nav { margin-top: 22px; display: grid; gap: 8px; }
    .nav a { color: #9aa4b2; text-decoration: none; padding: 10px 12px; border-radius: 10px; }
    .nav a.active { background: #151c24; color: #e6edf3; }
    .content { padding: 24px 32px; }
    .topbar { display:flex; align-items:center; justify-content:space-between; background: #171d24; border:1px solid #232c38; border-radius: 14px; padding: 14px 18px; }
    .topbar h1 { margin: 0; font-size: 18px; }
    .meta { color: #9aa4b2; font-size: 12px; }
    .btn { background: #3a79c5; border: none; color: #0b0f14; padding: 10px 14px; border-radius: 10px; cursor: pointer; }
    .grid { display: grid; gap: 16px; margin-top: 16px; }
    .kpis { grid-template-columns: repeat(4, minmax(160px, 1fr)); }
    .panel { background: #1a1f26; border: 1px solid #232c38; border-radius: 14px; padding: 16px; }
    .panel h3 { margin: 0 0 10px 0; font-size: 14px; }
    .split { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; }
    .muted { color: #9aa4b2; }
    input, textarea { width: 100%; background:#0f141a; color:#e6edf3; border:1px solid #232c38; border-radius: 10px; padding: 10px 12px; }
    textarea { min-height: 110px; }
    .row { display:flex; gap: 10px; }
    .table { display:grid; gap: 8px; }
    .thead, .trow { display:grid; grid-template-columns: 1fr 120px 140px; gap: 10px; align-items:center; }
    .thead { color:#9aa4b2; font-size:12px; }
    .badge { padding: 2px 8px; border-radius: 8px; background:#242b36; color:#9aa4b2; font-size: 11px; }
    .status.running { color:#6aa9ff; }
    .status.pending { color:#d7b46a; }
    .status.failed { color:#d87474; }
    .chat { display:grid; gap:10px; }
    .chatbox { background:#20262f; border:1px solid #2a3442; border-radius: 12px; padding: 12px; height: 170px; overflow: auto; }
    .msg { background:#2a303a; border-radius: 10px; padding: 8px 10px; margin-bottom: 8px; }
    .msg.you { background:#2f3b4e; }
    .inputbar { display:flex; gap:10px; }
    .inputbar input { flex:1; }
    .rightcol { display:grid; gap:16px; }
    @media (max-width: 1100px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { border-right: none; border-bottom: 1px solid #1f2a36; }
      .split { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">ODP</div>
      <div class="brand-sub">Orchestrated Dev Platform</div>
      <nav class="nav">
        <a class="active" href="/">Dashboard</a>
        <a href="#" onclick="scrollToPanel('tasks')">Tasks</a>
        <a id="navGates" href="#">Gates</a>
        <a href="#" onclick="scrollToPanel('agents')">Agents</a>
        <a id="navChat" href="#">Chat</a>
        <a id="navAudit" href="#">Audit Log</a>
      </nav>
    </aside>
    <main class="content">
      <div class="topbar">
        <div>
          <h1>Dashboard</h1>
          <div class="meta">Project: <span id="projectLabel">not set</span></div>
        </div>
        <div>
          <button class="btn" onclick="createTask()">New Task +</button>
          <button class="btn" onclick="seedDemo()" style="margin-left:8px">Seed Demo</button>
        </div>
      </div>

      <div class="grid kpis">
        <div class="panel"><div class="muted">Active Tasks</div><div id="kpiTasks">0</div></div>
        <div class="panel"><div class="muted">Gate Status</div><div id="kpiGates">n/a</div></div>
        <div class="panel"><div class="muted">Agents Online</div><div id="kpiAgents">3</div></div>
        <div class="panel"><div class="muted">Last Run</div><div id="kpiLast">—</div></div>
      </div>

      <div class="split" id="tasks">
        <section class="panel">
          <h3>Tasks (Task schema)</h3>
          <div class="row">
            <input id="project" placeholder="project UUID"/>
            <input id="title" placeholder="task title"/>
          </div>
          <div class="table" style="margin-top:10px">
            <div class="thead"><div>Task</div><div>Status</div><div>Phase</div></div>
            <div id="taskList"></div>
          </div>
        </section>
        <section class="panel chat">
          <h3>Orchestrator Chat</h3>
          <div class="chatbox" id="chatLog"></div>
          <div class="inputbar">
            <input id="chatText" placeholder="Type a message..."/>
            <button class="btn" onclick="sendChat()">Send</button>
          </div>
        </section>
      </div>

      <div class="split">
        <section class="panel" id="gates">
          <h3>Gate Status</h3>
          <div class="table">
            <div class="trow"><div>phase-1-orchestrator</div><div class="status running" id="gateP1">pass</div><div class="muted">evidence: tests.log</div></div>
            <div class="trow"><div>phase-2-engineer</div><div class="status pending" id="gateP2">pending</div><div class="muted">evidence: diff.patch</div></div>
            <div class="trow"><div>phase-3-qa</div><div class="status pending" id="gateP3">pending</div><div class="muted">evidence: qa_report.md</div></div>
            <div class="trow"><div>phase-4-security</div><div class="status pending" id="gateP4">pending</div><div class="muted">evidence: scan.log</div></div>
            <div class="trow"><div>phase-5-ui</div><div class="status pending" id="gateP5">pending</div><div class="muted">evidence: ws.log</div></div>
          </div>
        </section>
        <section class="panel" id="agents">
          <h3>Agents</h3>
          <div class="table">
            <div class="trow"><div>Engineer</div><div class="status running">active</div><div class="muted" id="agentEngineer">task: n/a</div></div>
            <div class="trow"><div>QA</div><div class="status running">active</div><div class="muted">spec compliance</div></div>
            <div class="trow"><div>Security</div><div class="status pending">idle</div><div class="muted">awaiting gates</div></div>
            <div class="trow"><div>Observer</div><div class="status running">spawned</div><div class="muted">monitoring ws</div></div>
          </div>
        </section>
      </div>
    </main>
  </div>
<script>
const STORE_KEY = 'odp_project_id';
function scrollToPanel(id){ document.getElementById(id).scrollIntoView({behavior:'smooth'}); }
function setProject(id){
  if(!id){ return; }
  localStorage.setItem(STORE_KEY, id);
  document.getElementById('projectLabel').innerText = id;
  document.getElementById('project').value = id;
  document.getElementById('navGates').href = `/ui/projects/${id}/gates`;
  document.getElementById('navChat').href = `/ui/chat?project_id=${id}`;
  document.getElementById('navAudit').href = `/ui/projects/${id}/audit`;
}
async function createTask(){
  const project = document.getElementById('project').value;
  const title = document.getElementById('title').value;
  if(!project || !title){ return; }
  const r = await fetch(`/projects/${project}/tasks`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({title})});
  const t = await r.json();
  setProject(project);
  document.getElementById('kpiLast').innerText = new Date().toLocaleTimeString();
  await loadTasks(project);
  await loadChat(project);
}
async function loadTasks(project){
  const r = await fetch(`/projects/${project}/tasks`);
  const tasks = await r.json();
  document.getElementById('kpiTasks').innerText = tasks.length;
  const el = document.getElementById('taskList');
  el.innerHTML = tasks.map(t=>`<div class='trow'><div><a href='/ui/projects/${project}/tasks/${t.task_id}'>${t.title}</a></div><div class='status ${t.state}'>${t.state}</div><div class='muted'>${t.phase || '-'}</div></div>`).join('');
}
async function sendChat(){
  const project = document.getElementById('project').value;
  const text = document.getElementById('chatText').value;
  if(!project || !text){ return; }
  await fetch(`/projects/${project}/chat`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({actor:'user', text})});
  const log = document.getElementById('chatLog');
  log.innerHTML += `<div class='msg you'>You: ${text}</div>`;
  log.scrollTop = log.scrollHeight;
  document.getElementById('chatText').value = '';
}
async function loadChat(project){
  const r = await fetch(`/projects/${project}/chat?limit=50`);
  const data = await r.json();
  const log = document.getElementById('chatLog');
  log.innerHTML = (data.messages||[]).map(m=>`<div class='msg ${m.actor==='user'?'you':''}'>${m.actor}: ${m.text}</div>`).join('');
  log.scrollTop = log.scrollHeight;
}
async function seedDemo(){
  const project = document.getElementById('project').value || localStorage.getItem(STORE_KEY);
  if(!project){ return; }
  await fetch(`/projects/${project}/demo`, {method:'POST'});
  await loadTasks(project);
  await loadChat(project);
}
const saved = localStorage.getItem(STORE_KEY);
if(saved){ setProject(saved); loadTasks(saved); loadChat(saved); }
</script>
</body>
</html>
"""

    @app.get("/ui/chat", response_class=HTMLResponse)
    async def ui_chat(project_id: UUID | None = None, task_id: UUID | None = None) -> str:
        pid = str(project_id) if project_id else ""
        tid = str(task_id) if task_id else ""
        html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ODP Chat</title>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: ui-sans-serif, system-ui; background: #0b0f14; color: #e6edf3; }
    .app { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }
    .sidebar { background: #0f141a; border-right: 1px solid #1f2a36; padding: 24px; }
    .brand { font-size: 26px; font-weight: 700; }
    .brand-sub { color: #9aa4b2; font-size: 12px; margin-top: 4px; }
    .nav { margin-top: 22px; display: grid; gap: 8px; }
    .nav a { color: #9aa4b2; text-decoration: none; padding: 10px 12px; border-radius: 10px; }
    .nav a.active { background: #151c24; color: #e6edf3; }
    .content { padding: 24px 32px; }
    .topbar { display:flex; align-items:center; justify-content:space-between; background: #171d24; border:1px solid #232c38; border-radius: 14px; padding: 14px 18px; }
    .panel { background: #1a1f26; border: 1px solid #232c38; border-radius: 14px; padding: 16px; }
    .chatbox { background:#20262f; border:1px solid #2a3442; border-radius: 12px; padding: 12px; height: 420px; overflow: auto; }
    .msg { background:#2a303a; border-radius: 10px; padding: 8px 10px; margin-bottom: 8px; }
    .msg.you { background:#2f3b4e; }
    .inputbar { display:flex; gap:10px; margin-top: 12px; }
    .inputbar input { flex:1; background:#0f141a; color:#e6edf3; border:1px solid #232c38; border-radius: 10px; padding: 10px 12px; }
    .btn { background: #3a79c5; border: none; color: #0b0f14; padding: 10px 14px; border-radius: 10px; cursor: pointer; }
    .small { font-size: 12px; color:#9aa4b2; }
    @media (max-width: 1100px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { border-right: none; border-bottom: 1px solid #1f2a36; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">ODP</div>
      <div class="brand-sub">Orchestrated Dev Platform</div>
      <nav class="nav">
        <a href="/">Dashboard</a>
        <a class="active" href="#">Chat</a>
        <a id="navTasks" href="#">Tasks</a>
        <a id="navGates" href="#">Gates</a>
        <a id="navAudit" href="#">Audit Log</a>
      </nav>
    </aside>
    <main class="content">
      <div class="topbar">
        <div>
          <div style="font-weight:600">Orchestrator Chat</div>
          <div class="small">Project: <span id="projectLabel">not set</span></div>
        </div>
      </div>
      <div style="height:16px"></div>
      <div class="panel">
        <div class="chatbox" id="chatLog"></div>
        <div class="inputbar">
          <input id="chatText" placeholder="Type a message..."/>
          <button class="btn" onclick="sendChat()">Send</button>
        </div>
        <div class="small" style="margin-top:8px">Optional task_id: <input id="taskId" placeholder="task UUID" value="__TID__" style="width:260px"/></div>
      </div>
    </main>
  </div>
<script>
const STORE_KEY = 'odp_project_id';
function setProject(id){
  if(!id){ return; }
  localStorage.setItem(STORE_KEY, id);
  document.getElementById('projectLabel').innerText = id;
  document.getElementById('navTasks').href = `/ui/projects/${id}`;
  document.getElementById('navGates').href = `/ui/projects/${id}/gates`;
  document.getElementById('navAudit').href = `/ui/projects/${id}/audit`;
}
async function loadChat(project){
  const taskId = document.getElementById('taskId').value;
  const url = taskId ? `/projects/${project}/chat?task_id=${taskId}&limit=50` : `/projects/${project}/chat?limit=50`;
  const r = await fetch(url);
  const data = await r.json();
  const log = document.getElementById('chatLog');
  log.innerHTML = (data.messages||[]).map(m=>`<div class='msg ${m.actor==='user'?'you':''}'>${m.actor}: ${m.text}</div>`).join('');
  log.scrollTop = log.scrollHeight;
}
async function sendChat(){
  const project = localStorage.getItem(STORE_KEY);
  const text = document.getElementById('chatText').value;
  const taskId = document.getElementById('taskId').value || null;
  if(!project || !text){ return; }
  await fetch(`/projects/${project}/chat`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({actor:'user', text, task_id: taskId})});
  document.getElementById('chatText').value = '';
  await loadChat(project);
}
const saved = "__PID__" || localStorage.getItem(STORE_KEY);
if(saved){ setProject(saved); loadChat(saved); }
</script>
</body>
</html>
"""
        return html.replace("__PID__", pid).replace("__TID__", tid)

    @app.get("/ui/projects/{project_id}/gates", response_class=HTMLResponse)
    async def ui_gates(project_id: UUID, task_id: UUID | None = None) -> str:
        pid = str(project_id)
        tid = str(task_id) if task_id else ""
        html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ODP Gate Evidence</title>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: ui-sans-serif, system-ui; background: #0b0f14; color: #e6edf3; }
    .app { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }
    .sidebar { background: #0f141a; border-right: 1px solid #1f2a36; padding: 24px; }
    .brand { font-size: 26px; font-weight: 700; }
    .brand-sub { color: #9aa4b2; font-size: 12px; margin-top: 4px; }
    .nav { margin-top: 22px; display: grid; gap: 8px; }
    .nav a { color: #9aa4b2; text-decoration: none; padding: 10px 12px; border-radius: 10px; }
    .nav a.active { background: #151c24; color: #e6edf3; }
    .content { padding: 24px 32px; }
    .topbar { display:flex; align-items:center; justify-content:space-between; background: #171d24; border:1px solid #232c38; border-radius: 14px; padding: 14px 18px; }
    .panel { background: #1a1f26; border: 1px solid #232c38; border-radius: 14px; padding: 16px; }
    .grid { display:grid; gap:16px; }
    .split { display:grid; grid-template-columns: 1.4fr 1fr; gap:16px; }
    .row { display:grid; grid-template-columns: 1fr 100px 1fr; gap:10px; align-items:center; }
    .status.pass { color:#6bbf7b; }
    .status.fail { color:#d87474; }
    .status.pending { color:#d7b46a; }
    .badge { padding: 2px 8px; border-radius: 8px; background:#242b36; color:#9aa4b2; font-size: 11px; }
    .muted { color:#9aa4b2; }
    @media (max-width: 1100px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { border-right: none; border-bottom: 1px solid #1f2a36; }
      .split { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">ODP</div>
      <div class="brand-sub">Orchestrated Dev Platform</div>
      <nav class="nav">
        <a href="/">Dashboard</a>
        <a href="/ui/chat?project_id=__PID__">Chat</a>
        <a href="/ui/projects/__PID__">Tasks</a>
        <a class="active" href="#">Gates</a>
        <a href="/ui/projects/__PID__/audit">Audit Log</a>
      </nav>
    </aside>
    <main class="content">
      <div class="topbar">
        <div>
          <div style="font-weight:600">Gate Evidence</div>
          <div class="muted">Project: __PID__</div>
        </div>
      </div>
      <div style="height:16px"></div>
      <div class="grid">
        <div class="split">
          <section class="panel">
            <h3>Gate Decisions (Gate schema)</h3>
            <div id="gateRows"></div>
          </section>
          <section class="panel">
            <h3>Evidence Viewer</h3>
            <div id="evidenceBox" class="muted">Select a task to view artifacts.</div>
          </section>
        </div>
        <section class="panel">
          <h3>Agent Tools</h3>
          <div class="row"><div>Screenshot</div><div class="muted">Capture UI state</div><div class="muted">attach to evidence</div></div>
          <div class="row"><div>Log Reader</div><div class="muted">Tail logs</div><div class="muted">parse failures</div></div>
          <div class="row"><div>Test Runner</div><div class="muted">Trigger tests</div><div class="muted">attach output</div></div>
        </section>
        <section class="panel">
          <h3>State Transition Timeline</h3>
          <div class="row"><div class="badge">INIT</div><div class="badge">DISPATCH</div><div class="badge">COLLECT</div><div class="badge">VALIDATE</div><div class="badge">COMMIT/ROLLBACK</div></div>
        </section>
      </div>
    </main>
  </div>
<script>
const PROJECT_ID = "__PID__";
const TASK_ID = "__TID__";
const STORE_KEY = 'odp_project_id';
if(PROJECT_ID){ localStorage.setItem(STORE_KEY, PROJECT_ID); }
async function loadGates(){
  const ev = await (await fetch(`/projects/${PROJECT_ID}/memory-events?limit=200`)).json();
  const decisions = (ev.events||[]).filter(e=>e.type === 'decision' || (e.payload && e.payload.gate));
  const rows = decisions.length ? decisions.map(d=>{
    const label = d.payload?.gate || d.payload?.phase || 'gate';
    const status = d.payload?.status || d.payload?.decision || 'pending';
    const evidence = d.payload?.evidence || d.payload?.artifact || '-';
    return `<div class='row'><div>${label}</div><div class='status ${status}'>${status}</div><div class='muted'>${evidence}</div></div>`;
  }).join('') : `<div class='muted'>(no gate decisions yet)</div>`;
  document.getElementById('gateRows').innerHTML = rows;
}
async function loadEvidence(){
  const params = new URLSearchParams(location.search);
  const task = params.get('task_id') || TASK_ID;
  if(!task){ return; }
  const arts = await (await fetch(`/projects/${PROJECT_ID}/tasks/${task}/artifacts?limit=200`)).json();
  const list = (arts.artifacts||[]).map(a=>{
    const isImage = (a.type === 'screenshot') || (a.uri && a.uri.toLowerCase().endsWith('.png'));
    const img = isImage ? `<div style="grid-column:1 / -1;margin-top:6px"><img src="/projects/${PROJECT_ID}/tasks/${task}/artifacts/${a.artifact_id}" style="max-width:100%;border-radius:10px;border:1px solid #2a3442"/></div>` : '';
    return `<div class='row'><div>${a.type}</div><div class='muted'>${a.uri}</div><div></div></div>${img}`;
  }).join('');
  document.getElementById('evidenceBox').innerHTML = list || '<div class="muted">(none)</div>';
}
loadGates();
loadEvidence();
</script>
</body>
</html>
"""
        return html.replace("__PID__", pid).replace("__TID__", tid)

    @app.get("/ui/projects/{project_id}/audit", response_class=HTMLResponse)
    async def ui_audit(project_id: UUID) -> str:
        pid = str(project_id)
        html = """
<!doctype html>
<html>
<head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>ODP Audit __PID__</title>
<style>
  :root{color-scheme:dark}*{box-sizing:border-box}
  body{margin:0;font-family:ui-sans-serif,system-ui;background:#0b0f14;color:#e6edf3}
  .app{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
  .sidebar{background:#0f141a;border-right:1px solid #1f2a36;padding:24px}
  .brand{font-size:26px;font-weight:700}
  .brand-sub{color:#9aa4b2;font-size:12px;margin-top:4px}
  .nav{margin-top:22px;display:grid;gap:8px}
  .nav a{color:#9aa4b2;text-decoration:none;padding:10px 12px;border-radius:10px}
  .nav a.active{background:#151c24;color:#e6edf3}
  .content{padding:24px 32px}
  .topbar{display:flex;align-items:center;justify-content:space-between;background:#171d24;border:1px solid #232c38;border-radius:14px;padding:14px 18px}
  .panel{background:#1a1f26;border:1px solid #232c38;border-radius:14px;padding:16px}
  pre{white-space:pre-wrap}
  .muted{color:#9aa4b2}
  @media (max-width:1100px){.app{grid-template-columns:1fr}.sidebar{border-right:none;border-bottom:1px solid #1f2a36}}
</style>
</head>
<body>
<div class='app'>
  <aside class='sidebar'>
    <div class='brand'>ODP</div>
    <div class='brand-sub'>Orchestrated Dev Platform</div>
    <nav class='nav'>
      <a href='/'>Dashboard</a>
      <a href='/ui/projects/__PID__'>Tasks</a>
      <a href='/ui/projects/__PID__/gates'>Gates</a>
      <a href='/ui/chat?project_id=__PID__'>Chat</a>
      <a class='active' href='#'>Audit Log</a>
    </nav>
  </aside>
  <main class='content'>
    <div class='topbar'>
      <div>
        <div style='font-weight:600'>Audit Log</div>
        <div class='muted'>Project __PID__</div>
      </div>
    </div>
    <div style='height:16px'></div>
    <div class='panel'>
      <pre id='events'>(loading)</pre>
    </div>
  </main>
</div>
<script>
const PROJECT_ID = "__PID__";
(function(){ localStorage.setItem('odp_project_id', PROJECT_ID); })();
(async ()=>{
  const ev = await (await fetch(`/projects/${PROJECT_ID}/memory-events?limit=200`)).json();
  document.getElementById('events').innerText = JSON.stringify(ev.events, null, 2);
})();
</script>
</body></html>
"""
        return html.replace("__PID__", pid)

    @app.get("/ui/projects/{project_id}", response_class=HTMLResponse)
    async def ui_project(project_id: UUID) -> str:
        pid = str(project_id)
        html = """
<!doctype html>
<html>
<head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>ODP Project __PID__</title>
<style>
  :root{color-scheme:dark}*{box-sizing:border-box}
  body{margin:0;font-family:ui-sans-serif,system-ui;background:#0b0f14;color:#e6edf3}
  .app{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
  .sidebar{background:#0f141a;border-right:1px solid #1f2a36;padding:24px}
  .brand{font-size:26px;font-weight:700}
  .brand-sub{color:#9aa4b2;font-size:12px;margin-top:4px}
  .nav{margin-top:22px;display:grid;gap:8px}
  .nav a{color:#9aa4b2;text-decoration:none;padding:10px 12px;border-radius:10px}
  .nav a.active{background:#151c24;color:#e6edf3}
  .content{padding:24px 32px}
  .topbar{display:flex;align-items:center;justify-content:space-between;background:#171d24;border:1px solid #232c38;border-radius:14px;padding:14px 18px}
  .panel{background:#1a1f26;border:1px solid #232c38;border-radius:14px;padding:16px}
  a{color:#9cdcfe}
  .muted{color:#9aa4b2}
  @media (max-width:1100px){.app{grid-template-columns:1fr}.sidebar{border-right:none;border-bottom:1px solid #1f2a36}}
</style>
</head>
<body>
<div class='app'>
  <aside class='sidebar'>
    <div class='brand'>ODP</div>
    <div class='brand-sub'>Orchestrated Dev Platform</div>
    <nav class='nav'>
      <a href='/'>Dashboard</a>
      <a class='active' href='#'>Tasks</a>
      <a href='/ui/projects/__PID__/gates'>Gates</a>
      <a href='/ui/chat?project_id=__PID__'>Chat</a>
      <a href='/ui/projects/__PID__/audit'>Audit Log</a>
    </nav>
  </aside>
  <main class='content'>
    <div class='topbar'>
      <div>
        <div style='font-weight:600'>Tasks</div>
        <div class='muted'>Project __PID__</div>
      </div>
    </div>
    <div style='height:16px'></div>
    <div class='panel'>
      <div id='tasks'>(loading)</div>
    </div>
  </main>
</div>
<script>
const PROJECT_ID = "__PID__";
(function(){ localStorage.setItem('odp_project_id', PROJECT_ID); })();
(async ()=>{
  const r = await fetch(`/projects/${PROJECT_ID}/tasks`);
  const tasks = await r.json();
  const el = document.getElementById('tasks');
  el.innerHTML = `<h3>Tasks</h3>` + tasks.map(t=>`<div><a href='/ui/projects/${PROJECT_ID}/tasks/${t.task_id}'>${t.title}</a> — <code>${t.state}</code></div>`).join('');
})();
</script>
</body>
</html>
"""
        return html.replace("__PID__", pid)

    @app.get("/ui/projects/{project_id}/tasks/{task_id}", response_class=HTMLResponse)
    async def ui_task(project_id: UUID, task_id: UUID) -> str:
        pid = str(project_id)
        tid = str(task_id)
        html = """
<!doctype html>
<html>
<head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>ODP Task __TID__</title>
<style>
  :root{color-scheme:dark}*{box-sizing:border-box}
  body{margin:0;font-family:ui-sans-serif,system-ui;background:#0b0f14;color:#e6edf3}
  .app{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
  .sidebar{background:#0f141a;border-right:1px solid #1f2a36;padding:24px}
  .brand{font-size:26px;font-weight:700}
  .brand-sub{color:#9aa4b2;font-size:12px;margin-top:4px}
  .nav{margin-top:22px;display:grid;gap:8px}
  .nav a{color:#9aa4b2;text-decoration:none;padding:10px 12px;border-radius:10px}
  .nav a.active{background:#151c24;color:#e6edf3}
  .content{padding:24px 32px}
  .topbar{display:flex;align-items:center;justify-content:space-between;background:#171d24;border:1px solid #232c38;border-radius:14px;padding:14px 18px}
  .panel{background:#1a1f26;border:1px solid #232c38;border-radius:14px;padding:16px}
  .grid{display:grid;gap:16px}
  .split{display:grid;grid-template-columns:1.4fr 1fr;gap:16px}
  .row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .muted{color:#9aa4b2}
  .code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#b7c4d6}
  .status.running{color:#6aa9ff}.status.pending{color:#d7b46a}.status.failed{color:#d87474}.status.pass{color:#6bbf7b}.status.fail{color:#d87474}
  .table{display:grid;gap:8px}
  .trow{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;align-items:center}
  .audit{background:#20262f;border:1px solid #2a3442;border-radius:12px;padding:12px}
  @media (max-width:1100px){.app{grid-template-columns:1fr}.sidebar{border-right:none;border-bottom:1px solid #1f2a36}.split{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class='app'>
  <aside class='sidebar'>
    <div class='brand'>ODP</div>
    <div class='brand-sub'>Orchestrated Dev Platform</div>
    <nav class='nav'>
      <a href='/'>Dashboard</a>
      <a class='active' href='#'>Task</a>
      <a href='/ui/projects/__PID__'>Tasks</a>
      <a href='/ui/projects/__PID__/gates'>Gates</a>
      <a href='/ui/chat?project_id=__PID__'>Chat</a>
      <a href='/ui/projects/__PID__/audit'>Audit Log</a>
    </nav>
  </aside>
  <main class='content'>
    <div class='topbar'>
      <div>
        <div style='font-weight:600'>Task Detail: __TID__</div>
        <div class='muted'>Project __PID__</div>
      </div>
      <div class='btn' style='pointer-events:none'>New Task +</div>
    </div>
    <div style='height:16px'></div>

    <div class='grid'>
      <div class='split'>
        <section class='panel'>
          <h3>Task (Task schema)</h3>
          <div id='task'>(loading)</div>
        </section>
        <section class='panel'>
          <h3>Spec Refs</h3>
          <div class='table'>
            <div class='muted'>01_PRD.md</div>
            <div class='muted'>02_SRD.md</div>
            <div class='muted'>04_ICD.md</div>
            <div class='muted'>06_VV_PLAN.md</div>
          </div>
        </section>
      </div>

      <div class='split'>
        <section class='panel'>
          <h3>Agent Results (Agent Result schema)</h3>
          <div id='agentResults' class='table'>(loading)</div>
        </section>
        <section class='panel'>
          <h3>State Transitions</h3>
          <div id='transitions' class='table'>(loading)</div>
        </section>
      </div>

      <section class='panel'>
        <h3>Audit Log</h3>
        <div id='events' class='audit'>(loading)</div>
      </section>

      <section class='panel'>
        <h3>Screenshots</h3>
        <div id='screenshots' class='table'>(loading)</div>
      </section>
    </div>
  </main>
</div>
<script>
const PROJECT_ID = "__PID__";
const TASK_ID = "__TID__";
const STORE_KEY = 'odp_project_id';
if(PROJECT_ID){ localStorage.setItem(STORE_KEY, PROJECT_ID); }
(async ()=>{
  const t = await (await fetch(`/projects/${PROJECT_ID}/tasks/${TASK_ID}`)).json();
  document.getElementById('task').innerHTML = `
    <div class='row'><div class='muted'>task_id</div><div class='code'>${t.task_id}</div></div>
    <div class='row'><div class='muted'>status</div><div class='status ${t.state}'>${t.state}</div></div>
    <div class='row'><div class='muted'>phase</div><div class='code'>${t.phase || '-'}</div></div>
    <div class='row'><div class='muted'>created_at</div><div class='code'>${t.created_at || '-'}</div></div>
  `;
  const ev = await (await fetch(`/projects/${PROJECT_ID}/memory-events?task_id=${TASK_ID}&limit=200`)).json();
  const events = ev.events || [];
  document.getElementById('events').innerText = JSON.stringify(events, null, 2);

  const transitions = events.filter(e=>e.type === 'state_transition');
  document.getElementById('transitions').innerHTML = transitions.length
    ? transitions.map(e=>`<div class='trow'><div>${e.payload?.from || '-'}</div><div>${e.payload?.to || '-'}</div><div class='muted'>${e.created_at || ''}</div></div>`).join('')
    : '<div class="muted">(none)</div>';

  // Artifacts
  const arts = await (await fetch(`/projects/${PROJECT_ID}/tasks/${TASK_ID}/artifacts?limit=200`)).json();
  // Pending agent memory + promotion
  const am = await (await fetch(`/projects/${PROJECT_ID}/agent-memory?status=pending&task_id=${TASK_ID}&limit=200`)).json();
  const memHtml = (am.agent_memory||[]).map(m=>`<div class='trow'><div>${m.role}:${m.type}</div><div class='muted'>${JSON.stringify(m.payload)}</div><div></div></div>`).join('');
  document.getElementById('agentResults').innerHTML = memHtml || '<div class="muted">(none)</div>';

  const shots = (arts.artifacts||[]).filter(a=>a.type==='screenshot' || (a.uri && a.uri.toLowerCase().endsWith('.png')));
  const shotHtml = shots.map(a=>`<div style="margin-bottom:10px"><div class="muted">${a.uri}</div><img src="/projects/${PROJECT_ID}/tasks/${TASK_ID}/artifacts/${a.artifact_id}" style="max-width:100%;border-radius:10px;border:1px solid #2a3442"/></div>`).join('');
  document.getElementById('screenshots').innerHTML = shotHtml || '<div class="muted">(none)</div>';
})();
</script>
</body>
</html>
"""
        return html.replace("__PID__", pid).replace("__TID__", tid)

    @app.post("/projects/{project_id}/tasks", response_model=Task)
    async def create_task(project_id: UUID, req: TaskCreateRequest) -> Task:
        return await orch.create_task(project_id, req)

    @app.post("/projects/{project_id}/demo")
    async def seed_demo(project_id: UUID) -> dict[str, Any]:
        # Create a few sample tasks + events for UI demo purposes.
        t1 = await orch.create_task(project_id, TaskCreateRequest(title="ODP-014"))
        t2 = await orch.create_task(project_id, TaskCreateRequest(title="ODP-015"))
        t3 = await orch.create_task(project_id, TaskCreateRequest(title="ODP-016"))
        for t, state in [(t1, "running"), (t2, "pending"), (t3, "failed")]:
            await memory.write_memory_event(
                project_id=project_id,
                task_id=t.task_id,
                type_="state_transition",
                actor="orchestrator",
                payload={"from": "INIT", "to": state},
            )
        return {"ok": True, "task_ids": [str(t1.task_id), str(t2.task_id), str(t3.task_id)]}

    @app.get("/projects/{project_id}/tasks", response_model=list[Task])
    async def list_tasks(project_id: UUID) -> list[Task]:
        return await orch.list_tasks(project_id)

    @app.get("/projects/{project_id}/tasks/{task_id}", response_model=Task)
    async def get_task(project_id: UUID, task_id: UUID) -> Task:
        t = await orch.get_task(project_id, task_id)
        if not t:
            raise HTTPException(status_code=404, detail="task not found")
        return t

    @app.post("/projects/{project_id}/chat")
    async def chat(project_id: UUID, req: ChatMessageRequest) -> dict[str, Any]:
        await memory.write_chat_message(
            project_id=project_id, task_id=req.task_id, actor=req.actor, text_=req.text
        )
        # Lightweight buffer to improve robustness under concurrent sqlite writes (tests/dev).
        try:
            if req.task_id:
                await store.redis.rpush(f"chatbuf:{project_id}:{req.task_id}", req.text)
        except Exception:
            pass
        return {"ok": True}

    @app.get("/projects/{project_id}/chat")
    async def list_chat(
        project_id: UUID,
        task_id: UUID | None = None,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        msgs = await memory.list_chat_messages(project_id=project_id, task_id=task_id, limit=limit)
        return {"messages": msgs}

    @app.post("/projects/{project_id}/chat/compact")
    async def compact_chat(project_id: UUID, req: CompactChatRequest) -> dict[str, Any]:
        # Pull messages oldest->newest for deterministic compaction.
        # Under concurrent writes (e.g., background task activity in tests), allow a short retry
        # window for freshly inserted chat rows to become visible.
        import asyncio as _asyncio

        for _ in range(10):
            msgs = await memory.list_chat_messages(project_id=project_id, task_id=req.task_id, limit=5000)
            msgs = list(reversed(msgs))
            if len(msgs) > req.keep_last:
                break
            await _asyncio.sleep(0.02)

        if len(msgs) <= req.keep_last:
            # Fallback: read buffered chat texts (dev/test robustness).
            try:
                if req.task_id:
                    buf = await store.redis.lrange(f"chatbuf:{project_id}:{req.task_id}", 0, -1)
                    buf = [b.decode() if isinstance(b, (bytes, bytearray)) else str(b) for b in buf]
                    msgs = [{"message_id": "", "task_id": str(req.task_id), "actor": "user", "text": t, "created_at": ""} for t in buf]
            except Exception:
                pass
            if len(msgs) <= req.keep_last:
                return {"ok": True, "compacted": 0}

        n = min(req.compact_n, max(0, len(msgs) - req.keep_last))
        to_compact = msgs[:n]
        compaction_of: list[UUID] = []
        for m in to_compact:
            try:
                if m.get("message_id"):
                    compaction_of.append(UUID(m["message_id"]))
            except Exception:
                pass
        text = "\n".join([m["text"] for m in to_compact])
        summary = (text[:4000] + "…") if len(text) > 4000 else text
        task_id: UUID
        if req.task_id:
            task_id = req.task_id
        elif to_compact and to_compact[-1]["task_id"]:
            task_id = UUID(to_compact[-1]["task_id"])
        else:
            raise HTTPException(status_code=400, detail="task_id required for compaction")

        await memory.write_memory_event(
            project_id=project_id,
            task_id=task_id,
            type_="summary",
            actor="orchestrator",
            payload={"summary": summary, "compacted": n},
            compaction_of=compaction_of,
        )
        await bus.emit(project_id, task_id, "chat_compacted", {"compacted": n})
        return {"ok": True, "compacted": n}

    @app.get("/projects/{project_id}/memory-events")
    async def list_memory_events(
        project_id: UUID,
        task_id: UUID | None = None,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        evs = await memory.list_memory_events(project_id=project_id, task_id=task_id, limit=limit)
        return {"events": evs}

    @app.get("/projects/{project_id}/memory/search")
    async def memory_search(
        project_id: UUID,
        q: str = Query(min_length=1, max_length=2000),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> dict[str, Any]:
        # pgvector-first is implemented best-effort; sqlite uses text fallback.
        results = await memory.search_memory_events_text(project_id=project_id, query=q, limit=limit)
        enriched: list[dict[str, Any]] = []
        for r in results:
            try:
                tid = UUID(r["task_id"])
                artifacts = await memory.list_artifacts(project_id=project_id, task_id=tid, limit=50)
            except Exception:
                artifacts = []
            enriched.append({**r, "artifacts": artifacts})
        return {"results": enriched}

    @app.get("/projects/{project_id}/agent-memory")
    async def list_agent_memory(
        project_id: UUID,
        status: str | None = Query(default=None),
        task_id: UUID | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, Any]:
        rows = await memory.list_agent_memory(project_id=project_id, status=status, task_id=task_id, limit=limit)
        return {"agent_memory": rows}

    @app.post("/projects/{project_id}/agent-memory/{agent_memory_id}/promote")
    async def promote_agent_memory(
        project_id: UUID, agent_memory_id: UUID, req: PromoteRequest
    ) -> dict[str, Any]:
        meta = await memory.get_agent_memory_meta(project_id=project_id, agent_memory_id=agent_memory_id)
        if not meta:
            raise HTTPException(status_code=404, detail="agent memory not found")

        promotion_id = await memory.promote_agent_memory(
            project_id=project_id,
            agent_memory_id=agent_memory_id,
            decision=req.decision,
            reviewer="orchestrator",
            note=req.note,
        )

        task_id = UUID(meta["task_id"])
        # Record an auditable memory event on approval/rejection.
        await memory.write_memory_event(
            project_id=project_id,
            task_id=task_id,
            type_="decision",
            actor="orchestrator",
            payload={
                "promotion_id": str(promotion_id),
                "agent_memory_id": str(agent_memory_id),
                "decision": req.decision,
                "note": req.note,
                "type": meta.get("type"),
                "role": meta.get("role"),
            },
        )
        await bus.emit(
            project_id,
            task_id,
            "agent_memory_promoted",
            {"agent_memory_id": str(agent_memory_id), "decision": req.decision},
        )
        return {"ok": True, "promotion_id": str(promotion_id)}

    @app.get("/projects/{project_id}/tasks/{task_id}/artifacts")
    async def list_task_artifacts(project_id: UUID, task_id: UUID, limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
        rows = await memory.list_artifacts(project_id=project_id, task_id=task_id, limit=limit)
        return {"artifacts": rows}

    @app.get("/projects/{project_id}/tasks/{task_id}/artifacts/{artifact_id}")
    async def get_task_artifact(project_id: UUID, task_id: UUID, artifact_id: UUID) -> FileResponse:
        row = await memory.get_artifact(project_id=project_id, task_id=task_id, artifact_id=artifact_id)
        if not row:
            raise HTTPException(status_code=404, detail="artifact not found")
        base = Path(os.getenv("ODP_ARTIFACT_DIR", "runtime/artifacts")).resolve()
        path = Path(row["uri"])
        if not path.is_absolute():
            path = base / path
        try:
            resolved = path.resolve()
        except Exception:
            raise HTTPException(status_code=404, detail="artifact not found")
        try:
            resolved.relative_to(base)
        except Exception:
            raise HTTPException(status_code=403, detail="artifact path forbidden")
        if not resolved.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(str(resolved))

    @app.post("/projects/{project_id}/tasks/{task_id}/artifacts")
    async def upload_artifact(project_id: UUID, task_id: UUID, file: UploadFile = File(...)) -> dict[str, Any]:
        base = os.getenv("ODP_ARTIFACT_DIR", "runtime/artifacts")
        path = os.path.join(base, str(project_id), str(task_id), "uploads")
        os.makedirs(path, exist_ok=True)
        out = os.path.join(path, file.filename)
        with open(out, "wb") as f:
            f.write(await file.read())
        await memory.record_artifact(project_id=project_id, task_id=task_id, type_="log", uri=out)
        await bus.emit(project_id, task_id, "artifact_uploaded", {"uri": out, "filename": file.filename})
        return {"ok": True, "uri": out}

    @app.websocket("/ws/projects/{project_id}/tasks/{task_id}")
    async def ws_task(websocket: WebSocket, project_id: UUID, task_id: UUID, since: int = 0) -> None:
        await websocket.accept()

        # Replay backlog
        events = await store.read_events(project_id, task_id, start_idx=since)
        for e in events:
            await websocket.send_text(str(e))

        pubsub = redis.pubsub()
        await pubsub.subscribe(bus.channel(project_id, task_id))
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    await asyncio.sleep(0.05)
                    continue
                # msg["data"] is event idx; fetch from list (single element)
                idx_raw = msg.get("data")
                if isinstance(idx_raw, bytes):
                    idx_raw = idx_raw.decode("utf-8")
                idx = int(idx_raw)
                ev = await store.read_events(project_id, task_id, start_idx=idx)
                for e in ev:
                    await websocket.send_text(str(e))
        except WebSocketDisconnect:
            return
        finally:
            try:
                await pubsub.unsubscribe(bus.channel(project_id, task_id))
                await pubsub.aclose()
            except Exception:
                pass

    @app.post("/projects/{project_id}/resume")
    async def resume(project_id: UUID) -> dict[str, Any]:
        n = await orch.resume_incomplete(project_id)
        return {"resumed": n}

    return app
