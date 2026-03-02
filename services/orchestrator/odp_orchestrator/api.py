from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from redis.asyncio import Redis

from .db import MemoryWriter, create_engine
from .events import EventBus
from .models import ChatMessageRequest, Task, TaskCreateRequest
from .orchestrator import Orchestrator
from .redis_store import RedisStore


def create_app() -> FastAPI:
    app = FastAPI(title="ODP Orchestrator", version="0.1")

    redis_url = os.getenv("ODP_REDIS_URL", "redis://localhost:6379/0")
    redis = Redis.from_url(redis_url, decode_responses=False)
    store = RedisStore(redis)
    bus = EventBus(redis=redis, store=store)
    memory = MemoryWriter(create_engine())
    orch = Orchestrator(store=store, bus=bus, memory=memory)

    @app.on_event("startup")
    async def _startup() -> None:
        if os.getenv("ODP_AUTO_MIGRATE", "1") == "1":
            await memory.init_schema()

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        # Minimal dashboard shell; UI spec is prototype-driven, so we keep this lean.
        return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ODP Dashboard (M1)</title>
  <style>
    :root { color-scheme: dark; }
    body { font-family: ui-sans-serif, system-ui; background: #0b0f14; color: #e6edf3; margin: 24px; }
    .row { display:flex; gap: 24px; align-items:flex-start; }
    .card { background: #111826; border: 1px solid #243041; border-radius: 12px; padding: 16px; width: 520px; }
    input, button { background:#0b0f14; color:#e6edf3; border:1px solid #243041; border-radius: 10px; padding: 10px 12px; }
    button { cursor:pointer; }
    code { color: #9cdcfe; }
    .log { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular; font-size: 12px; }
  </style>
</head>
<body>
  <h1>ODP Dashboard (Milestone 1)</h1>
  <div class="row">
    <div class="card">
      <h3>Create task</h3>
      <input id="project" placeholder="project UUID" style="width:100%"/>
      <div style="height:8px"></div>
      <input id="title" placeholder="task title" style="width:100%"/>
      <div style="height:8px"></div>
      <button onclick="createTask()">Start</button>
      <p id="created"></p>
    </div>
    <div class="card">
      <h3>Task events</h3>
      <div id="events" class="log"></div>
    </div>
  </div>
<script>
let ws;
async function createTask(){
  const project = document.getElementById('project').value;
  const title = document.getElementById('title').value;
  const r = await fetch(`/projects/${project}/tasks`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({title})});
  const t = await r.json();
  document.getElementById('created').innerText = `Created task ${t.task_id}`;
  connect(project, t.task_id);
}
function connect(project, task){
  if(ws){ ws.close(); }
  ws = new WebSocket(`${location.origin.replace('http','ws')}/ws/projects/${project}/tasks/${task}`);
  const el = document.getElementById('events');
  el.innerText = '';
  ws.onmessage = (m)=>{ el.innerText += m.data + "\n"; };
}
</script>
</body>
</html>
"""

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
        # For M1, chat doesn't trigger agent work. It is persisted only.
        return {"ok": True}

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
                await pubsub.close()
            except Exception:
                pass

    @app.post("/projects/{project_id}/resume")
    async def resume(project_id: UUID) -> dict[str, Any]:
        n = await orch.resume_incomplete(project_id)
        return {"resumed": n}

    return app
