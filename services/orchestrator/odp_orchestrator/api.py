from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Query
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

    @app.get("/ui/projects/{project_id}", response_class=HTMLResponse)
    async def ui_project(project_id: UUID) -> str:
        return f"""
<!doctype html>
<html>
<head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>ODP Project {project_id}</title>
<style>body{{font-family:system-ui;background:#0b0f14;color:#e6edf3;margin:24px}} a{{color:#9cdcfe}}</style>
</head>
<body>
<h1>Project {project_id}</h1>
<p><a href='/'>Home</a></p>
<div id='tasks'></div>
<script>
(async ()=>{{
  const r = await fetch(`/projects/{project_id}/tasks`);
  const tasks = await r.json();
  const el = document.getElementById('tasks');
  el.innerHTML = `<h3>Tasks</h3>` + tasks.map(t=>`<div><a href='/ui/projects/{project_id}/tasks/${{t.task_id}}'>${{t.title}}</a> — <code>${{t.state}}</code></div>`).join('');
}})();
</script>
</body>
</html>
"""

    @app.get("/ui/projects/{project_id}/tasks/{task_id}", response_class=HTMLResponse)
    async def ui_task(project_id: UUID, task_id: UUID) -> str:
        return f"""
<!doctype html>
<html>
<head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>ODP Task {task_id}</title>
<style>body{{font-family:system-ui;background:#0b0f14;color:#e6edf3;margin:24px}} a{{color:#9cdcfe}} pre{{white-space:pre-wrap}}</style>
</head>
<body>
<h1>Task {task_id}</h1>
<p><a href='/ui/projects/{project_id}'>Back to project</a></p>
<div id='task'></div>
<h3>Events</h3>
<pre id='events'></pre>
<script>
(async ()=>{{
  const t = await (await fetch(`/projects/{project_id}/tasks/{task_id}`)).json();
  document.getElementById('task').innerHTML = `<div><b>${{t.title}}</b> — <code>${{t.state}}</code></div>`;
  const ev = await (await fetch(`/projects/{project_id}/memory-events?task_id={task_id}&limit=200`)).json();
  document.getElementById('events').innerText = JSON.stringify(ev.events, null, 2);
}})();
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
        # For now, chat doesn't trigger agent work. It is persisted only.
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
        msgs = await memory.list_chat_messages(project_id=project_id, task_id=req.task_id, limit=5000)
        msgs = list(reversed(msgs))
        if len(msgs) <= req.keep_last:
            return {"ok": True, "compacted": 0}

        n = min(req.compact_n, max(0, len(msgs) - req.keep_last))
        to_compact = msgs[:n]
        compaction_of = [UUID(m["message_id"]) for m in to_compact]
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
