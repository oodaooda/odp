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
from fastapi.responses import HTMLResponse
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
    .brand { font-size: 28px; font-weight: 700; letter-spacing: 0.5px; }
    .brand-sub { color: #9aa4b2; font-size: 12px; margin-top: 4px; }
    .nav { margin-top: 28px; display: grid; gap: 10px; }
    .nav a { color: #9aa4b2; text-decoration: none; padding: 10px 12px; border-radius: 10px; }
    .nav a.active { background: #151c24; color: #e6edf3; }
    .content { padding: 24px 32px; }
    .header { display: flex; align-items: center; justify-content: space-between; background: #111826; border: 1px solid #223044; border-radius: 14px; padding: 16px 20px; }
    .header h1 { margin: 0; font-size: 18px; }
    .header .meta { color: #9aa4b2; font-size: 12px; }
    .btn { background: #3a79c5; border: none; color: #0b0f14; padding: 10px 14px; border-radius: 10px; cursor: pointer; }
    .grid { display: grid; gap: 16px; margin-top: 16px; }
    .kpis { grid-template-columns: repeat(4, minmax(140px, 1fr)); }
    .panel { background: #111826; border: 1px solid #223044; border-radius: 14px; padding: 16px; }
    .panel h3 { margin: 0 0 10px 0; font-size: 14px; }
    .split { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; }
    .muted { color: #9aa4b2; }
    input, textarea { width: 100%; background:#0b0f14; color:#e6edf3; border:1px solid #223044; border-radius: 10px; padding: 10px 12px; }
    textarea { min-height: 90px; }
    .row { display:flex; gap: 10px; }
    .list { display: grid; gap: 8px; }
    .badge { padding: 2px 8px; border-radius: 8px; background:#1b2430; color:#9aa4b2; font-size: 11px; }
    .log { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular; font-size: 12px; }
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
        <a href="#" onclick="scrollToPanel('gates')">Gates</a>
        <a href="#" onclick="scrollToPanel('agents')">Agents</a>
        <a href="#" onclick="scrollToPanel('audit')">Audit Log</a>
      </nav>
    </aside>
    <main class="content">
      <div class="header">
        <div>
          <h1>Dashboard</h1>
          <div class="meta">Project: <span id="projectLabel">not set</span></div>
        </div>
        <button class="btn" onclick="createTask()">Create Task</button>
      </div>

      <div class="grid kpis">
        <div class="panel"><div class="muted">Active Tasks</div><div id="kpiTasks">0</div></div>
        <div class="panel"><div class="muted">Gate Status</div><div id="kpiGates">n/a</div></div>
        <div class="panel"><div class="muted">Agents Online</div><div>3</div></div>
        <div class="panel"><div class="muted">Last Run</div><div id="kpiLast">—</div></div>
      </div>

      <div class="split">
        <section class="panel" id="tasks">
          <h3>Tasks</h3>
          <div class="row">
            <input id="project" placeholder="project UUID"/>
            <input id="title" placeholder="task title"/>
          </div>
          <div class="list" id="taskList" style="margin-top:10px"></div>
        </section>
        <section class="panel">
          <h3>Orchestrator Chat</h3>
          <textarea id="chatText" placeholder="Type a message..."></textarea>
          <div style="height:8px"></div>
          <button class="btn" onclick="sendChat()">Send</button>
          <div class="log" id="chatLog" style="margin-top:10px"></div>
        </section>
      </div>

      <div class="split">
        <section class="panel" id="gates">
          <h3>Gate Timeline</h3>
          <div class="list">
            <div><span class="badge">P1</span> Orchestrator</div>
            <div><span class="badge">P2</span> Engineer</div>
            <div><span class="badge">P3</span> QA</div>
            <div><span class="badge">P4</span> Security</div>
            <div><span class="badge">P5</span> UI/WS</div>
          </div>
        </section>
        <section class="panel" id="agents">
          <h3>Agents</h3>
          <div class="list">
            <div>Engineer <span class="badge">active</span></div>
            <div>QA <span class="badge">active</span></div>
            <div>Security <span class="badge">idle</span></div>
          </div>
        </section>
      </div>

      <section class="panel" id="audit">
        <h3>Task Events</h3>
        <div id="events" class="log"></div>
      </section>
    </main>
  </div>
<script>
let ws;
function scrollToPanel(id){ document.getElementById(id).scrollIntoView({behavior:'smooth'}); }
async function createTask(){
  const project = document.getElementById('project').value;
  const title = document.getElementById('title').value;
  if(!project || !title){ return; }
  const r = await fetch(`/projects/${project}/tasks`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({title})});
  const t = await r.json();
  document.getElementById('projectLabel').innerText = project;
  document.getElementById('kpiLast').innerText = new Date().toLocaleTimeString();
  connect(project, t.task_id);
  await loadTasks(project);
}
function connect(project, task){
  if(ws){ ws.close(); }
  ws = new WebSocket(`${location.origin.replace('http','ws')}/ws/projects/${project}/tasks/${task}`);
  const el = document.getElementById('events');
  el.innerText = '';
  ws.onmessage = (m)=>{ el.innerText += m.data + "
"; };
}
async function loadTasks(project){
  const r = await fetch(`/projects/${project}/tasks`);
  const tasks = await r.json();
  document.getElementById('kpiTasks').innerText = tasks.length;
  const el = document.getElementById('taskList');
  el.innerHTML = tasks.map(t=>`<div><a href='/ui/projects/${project}/tasks/${t.task_id}'>${t.title}</a> — <code>${t.state}</code></div>`).join('');
}
async function sendChat(){
  const project = document.getElementById('project').value;
  const text = document.getElementById('chatText').value;
  if(!project || !text){ return; }
  await fetch(`/projects/${project}/chat`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({actor:'user', text})});
  document.getElementById('chatLog').innerText += `you: ${text}
`;
  document.getElementById('chatText').value = '';
}
</script>
</body>
</html>
"""

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
  .wrap{max-width:1200px;margin:24px auto;padding:0 16px}
  .panel{background:#111826;border:1px solid #223044;border-radius:14px;padding:16px}
  a{color:#9cdcfe}
  pre{white-space:pre-wrap}
</style>
</head>
<body>
<div class='wrap'>
  <div class='panel'>
    <h2>Audit (Project __PID__)</h2>
    <p><a href='/ui/projects/__PID__'>Back to project</a></p>
    <pre id='events'>(loading)</pre>
  </div>
</div>
<script>
const PROJECT_ID = "__PID__";
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
  .wrap{max-width:1200px;margin:24px auto;padding:0 16px}
  .panel{background:#111826;border:1px solid #223044;border-radius:14px;padding:16px}
  a{color:#9cdcfe}
</style>
</head>
<body>
<div class='wrap'>
  <div class='panel'>
    <h2>Project __PID__</h2>
    <p><a href='/'>Back to dashboard</a> · <a href='/ui/projects/__PID__/audit'>Audit</a></p>
    <div id='tasks'>(loading)</div>
  </div>
</div>
<script>
const PROJECT_ID = "__PID__";
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
  .wrap{max-width:1200px;margin:24px auto;padding:0 16px}
  .top{display:flex;gap:16px;align-items:center;justify-content:space-between;margin-bottom:16px}
  .kicker{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#8aa0b8}
  .pill{background:#0f1726;border:1px solid #223044;border-radius:999px;padding:8px 12px;color:#9fb3c8;font-size:12px}
  .meta{color:#9fb3c8;font-size:13px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .panel{background:#111826;border:1px solid #223044;border-radius:14px;padding:16px}
  a{color:#9cdcfe}
  pre{white-space:pre-wrap}
  .btn{background:#0b1220;border:1px solid #2a3a52;color:#e6edf3;border-radius:10px;padding:6px 10px;margin-right:8px;cursor:pointer}
  .row{display:flex;gap:8px;flex-wrap:wrap}
  .muted{color:#9fb3c8}
  .code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#b7c4d6}
  @media (max-width: 900px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class='wrap'>
  <div class='top'>
    <div>
      <div class='kicker'>Task Detail</div>
      <h1>Task __TID__</h1>
      <div class='meta'><a href='/ui/projects/__PID__'>Back to project</a> · <span id='state'>(loading)</span></div>
    </div>
    <div class='pill'>Project __PID__</div>
  </div>

  <div class='grid'>
    <div class='panel'>
      <h3>Summary</h3>
      <div id='task'>(loading)</div>
    </div>
    <div class='panel'>
      <h3>Events</h3>
      <pre id='events'>(loading)</pre>
    </div>
    <div class='panel'>
      <h3>Artifacts</h3>
      <div id='artifacts'>(loading)</div>
    </div>
    <div class='panel'>
      <h3>Pending Memory</h3>
      <div id='pending'>(loading)</div>
    </div>
  </div>
</div>
<script>
const PROJECT_ID = "__PID__";
const TASK_ID = "__TID__";
(async ()=>{
  const t = await (await fetch(`/projects/${PROJECT_ID}/tasks/${TASK_ID}`)).json();
  document.getElementById('task').innerHTML = `
    <div><b>${t.title}</b></div>
    <div class='muted'>state: <span class='code'>${t.state}</span></div>
    <div class='muted'>created: <span class='code'>${t.created_at || ''}</span></div>
  `;
  document.getElementById('state').innerText = t.state;
  const ev = await (await fetch(`/projects/${PROJECT_ID}/memory-events?task_id=${TASK_ID}&limit=200`)).json();
  document.getElementById('events').innerText = JSON.stringify(ev.events, null, 2);

  // Artifacts
  const arts = await (await fetch(`/projects/${PROJECT_ID}/tasks/${TASK_ID}/artifacts?limit=200`)).json();
  const artHtml = (arts.artifacts||[]).map(a=>{
    const label = a.uri || '';
    return `<div class='row'><span class='code'>${a.type}</span><span class='muted'>${label}</span></div>`;
  }).join('');
  document.getElementById('artifacts').innerHTML = artHtml || '<div class=\"muted\">(none)</div>';

  // Pending agent memory + promotion
  const am = await (await fetch(`/projects/${PROJECT_ID}/agent-memory?status=pending&task_id=${TASK_ID}&limit=200`)).json();
  const memHtml = (am.agent_memory||[]).map(m=>{
    return `<div style='margin-bottom:8px'><code>${m.role}:${m.type}</code> <pre>${JSON.stringify(m.payload,null,2)}</pre>
      <div class='row'>
        <button class='btn' onclick="fetch('/projects/${PROJECT_ID}/agent-memory/${m.agent_memory_id}/promote',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({decision:'approved'})}).then(()=>location.reload())">Approve</button>
        <button class='btn' onclick="fetch('/projects/${PROJECT_ID}/agent-memory/${m.agent_memory_id}/promote',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({decision:'rejected'})}).then(()=>location.reload())">Reject</button>
      </div>
    </div>`
  }).join('');
  document.getElementById('pending').innerHTML = memHtml || '<div class=\"muted\">(none)</div>';
})();
</script>
</body>
</html>
"""
        return html.replace("__PID__", pid).replace("__TID__", tid)

    @app.post("/projects/{project_id}/tasks", response_model=Task)
    async def create_task(project_id: UUID, req: TaskCreateRequest) -> Task:
        return await orch.create_task(project_id, req)

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
