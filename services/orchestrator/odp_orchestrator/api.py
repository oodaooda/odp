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
            # Always log auth failures for security audit.
            print(json.dumps({
                "event": "auth_failure", "method": request.method,
                "path": request.url.path, "required": required,
                "client": request.client.host if request.client else "unknown",
            }))
            resp = JSONResponse({"detail": "unauthorized"}, status_code=401)
            return resp

        request.state.role = role
        resp = await call_next(request)
        if do_log:
            print(json.dumps({"method": request.method, "path": request.url.path, "status": resp.status_code, "role": role}))
        return resp


    @app.get("/healthz")
    async def healthz(request: Request) -> dict[str, Any]:
        role = getattr(request.state, "role", None)
        return {"ok": True, "role": role}

    @app.get("/metrics")
    async def metrics() -> str:
        m = app.state.metrics
        return "\n".join([f"odp_requests_total {m['requests_total']}"])

    # ── Old embedded HTML UI routes removed ──
    # The React SPA in apps/web/ now handles all UI rendering.
    # See the SPA catch-all at the bottom of this file.

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

    @app.websocket("/ws/projects/{project_id}")
    async def ws_project(websocket: WebSocket, project_id: UUID) -> None:
        """Project-level WebSocket: broadcasts all task events for the project."""
        await websocket.accept()
        pubsub = redis.pubsub()
        await pubsub.subscribe(bus.project_channel(project_id))
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    await asyncio.sleep(0.05)
                    continue
                data = msg.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                await websocket.send_text(str(data))
        except WebSocketDisconnect:
            return
        finally:
            try:
                await pubsub.unsubscribe(bus.project_channel(project_id))
                await pubsub.aclose()
            except Exception:
                pass

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

    @app.post("/projects/{project_id}/tasks/{task_id}/cancel")
    async def cancel_task(project_id: UUID, task_id: UUID) -> dict[str, Any]:
        ok = await orch.cancel_task(project_id, task_id)
        if not ok:
            raise HTTPException(status_code=400, detail="task not cancellable (already terminal or not found)")
        return {"ok": True}

    @app.post("/projects/{project_id}/resume")
    async def resume(project_id: UUID) -> dict[str, Any]:
        n = await orch.resume_incomplete(project_id)
        return {"resumed": n}

    # ── Project Management ──

    @app.get("/projects")
    async def list_projects() -> dict[str, Any]:
        """List all known projects (stored in Redis)."""
        keys = []
        try:
            async for key in redis.scan_iter("odp:project:*:meta"):
                keys.append(key)
        except Exception:
            pass
        projects = []
        for k in keys:
            raw = await redis.get(k)
            if raw:
                try:
                    projects.append(json.loads(raw if isinstance(raw, str) else raw.decode("utf-8")))
                except Exception:
                    pass
        return {"projects": projects}

    class ProjectCreateRequest(BaseModel):
        name: str = Field(min_length=1, max_length=200)
        github_repo: str = Field(default="", max_length=200)
        default_branch: str = Field(default="main", max_length=100)

    @app.post("/projects")
    async def create_project(req: ProjectCreateRequest) -> dict[str, Any]:
        from uuid import uuid4
        project_id = str(uuid4())
        meta = {
            "project_id": project_id,
            "name": req.name,
            "github_repo": req.github_repo,
            "default_branch": req.default_branch,
        }
        await redis.set(f"odp:project:{project_id}:meta", json.dumps(meta))
        return meta

    class ProjectUpdateRequest(BaseModel):
        name: str | None = Field(default=None, max_length=200)
        github_repo: str | None = Field(default=None, max_length=200)
        default_branch: str | None = Field(default=None, max_length=100)

    @app.patch("/projects/{project_id}")
    async def update_project(project_id: UUID, req: ProjectUpdateRequest) -> dict[str, Any]:
        key = f"odp:project:{project_id}:meta"
        raw = await redis.get(key)
        if not raw:
            raise HTTPException(status_code=404, detail="project not found")
        meta = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        if req.name is not None:
            meta["name"] = req.name
        if req.github_repo is not None:
            meta["github_repo"] = req.github_repo
        if req.default_branch is not None:
            meta["default_branch"] = req.default_branch
        await redis.set(key, json.dumps(meta))
        return meta

    # ── GitHub Webhook ──

    @app.post("/webhooks/github")
    async def github_webhook(request: Request) -> dict[str, Any]:
        """Receive GitHub webhook events and create tasks."""
        import hashlib
        import hmac

        secret = os.getenv("ODP_GITHUB_WEBHOOK_SECRET", "")
        body = await request.body()

        # Verify signature if secret is configured.
        if secret:
            sig_header = request.headers.get("X-Hub-Signature-256", "")
            expected = "sha256=" + hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                raise HTTPException(status_code=403, detail="invalid signature")

        try:
            payload = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON")

        event_type = request.headers.get("X-GitHub-Event", "")

        # Issue with 'odp' label → create task.
        if event_type == "issues" and payload.get("action") == "opened":
            labels = [l.get("name", "") for l in payload.get("issue", {}).get("labels", [])]
            if "odp" in labels:
                issue = payload["issue"]
                # Use default project for now; multi-project matching by repo is future work.
                default_pid = UUID("00000000-0000-0000-0000-000000000001")
                t = await orch.create_task(
                    default_pid,
                    TaskCreateRequest(
                        title=issue.get("title", "GitHub Issue"),
                        description=issue.get("body", ""),
                    ),
                )
                return {"ok": True, "task_id": str(t.task_id), "source": "issue"}

        # PR opened → create review task.
        if event_type == "pull_request" and payload.get("action") in ("opened", "synchronize"):
            pr = payload.get("pull_request", {})
            default_pid = UUID("00000000-0000-0000-0000-000000000001")
            t = await orch.create_task(
                default_pid,
                TaskCreateRequest(
                    title=f"Review PR #{pr.get('number', '?')}: {pr.get('title', '')}",
                    description=pr.get("body", ""),
                ),
            )
            return {"ok": True, "task_id": str(t.task_id), "source": "pull_request"}

        # Acknowledged but not handled.
        return {"ok": True, "action": "ignored"}

    # ── Serve React SPA (production build) ──
    # When apps/web/dist exists, serve its static files and fall back to
    # index.html for client-side routing.
    _spa_dir = Path(__file__).resolve().parents[3] / "apps" / "web" / "dist"
    if _spa_dir.is_dir():
        from fastapi.staticfiles import StaticFiles

        # Serve /assets/* directly
        _assets = _spa_dir / "assets"
        if _assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(_assets)), name="spa-assets")

        _index_html = _spa_dir / "index.html"

        @app.get("/{full_path:path}", response_class=HTMLResponse)
        async def spa_fallback(full_path: str):
            """Serve index.html for any unmatched route (SPA client-side routing)."""
            if _index_html.is_file():
                return HTMLResponse(_index_html.read_text())
            raise HTTPException(404)

    return app
