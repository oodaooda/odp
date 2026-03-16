from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

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
from .models import ChatMessageRequest, ProjectCreateRequest, ProjectUpdateRequest, SecretSetRequest, Task, TaskCreateRequest
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

    # Endpoints requiring admin role.
    _ADMIN_PATHS = {"/promote", "/chat/compact", "/demo", "/resume"}

    def _required_role(path: str, method: str) -> str:
        # Conservative defaults: read=reader, admin ops=admin, everything else=writer.
        if method in {"GET", "HEAD"}:
            return "reader"
        if path.startswith("/projects/") and any(ap in path for ap in _ADMIN_PATHS):
            return "admin"
        # Webhook has its own auth (signature verification).
        if path == "/webhooks/github":
            return "reader"
        return "writer"

    def _role_rank(role: str) -> int:
        return {"reader": 1, "writer": 2, "admin": 3}.get(role, 0)

    # ── Rate Limiting ── (per-IP, in-process; Caddy provides edge limiting)
    _rate_buckets: dict[str, list[float]] = {}
    _RATE_WINDOW = 60.0  # seconds
    _RATE_LIMIT_WRITE = int(os.getenv("ODP_RATE_LIMIT_WRITE", "60"))
    _RATE_LIMIT_READ = int(os.getenv("ODP_RATE_LIMIT_READ", "300"))

    def _check_rate_limit(client_ip: str, limit: int) -> bool:
        import time
        now = time.monotonic()
        key = f"{client_ip}:{limit}"
        bucket = _rate_buckets.setdefault(key, [])
        # Prune old entries.
        cutoff = now - _RATE_WINDOW
        _rate_buckets[key] = bucket = [t for t in bucket if t > cutoff]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        app.state.metrics["requests_total"] += 1
        do_log = os.getenv("ODP_LOG_REQUESTS", "0") == "1"

        # Rate limiting.
        client_ip = request.client.host if request.client else "unknown"
        limit = _RATE_LIMIT_READ if request.method in {"GET", "HEAD"} else _RATE_LIMIT_WRITE
        if not _check_rate_limit(client_ip, limit):
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)

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

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' wss: ws:; "
            "img-src 'self' data:; "
            "frame-ancestors 'none'"
        )
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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

    async def _hydrate_task(task: Task) -> dict[str, Any]:
        """Resolve Redis key references in agent_results and gate_decisions to full objects."""
        d = task.model_dump()
        # Hydrate agent_results: resolve Redis keys to full AgentResult dicts.
        hydrated_results = []
        fallback = {"ok": False, "summary": "", "artifacts": [], "logs": [], "memory_entries": []}
        for key in task.agent_results:
            raw = await store.redis.get(key)
            if raw:
                try:
                    obj = json.loads(raw if isinstance(raw, str) else raw.decode())
                except Exception:
                    obj = {**fallback, "role": key.split(":")[-1]}
            else:
                obj = {**fallback, "role": key.split(":")[-1]}
            # Map model field 'role' to frontend field 'agent_role'.
            if "role" in obj and "agent_role" not in obj:
                obj["agent_role"] = obj["role"]
            hydrated_results.append(obj)
        d["agent_results"] = hydrated_results
        # Hydrate gate_decisions: resolve Redis keys to full GateDecision dicts.
        hydrated_gates = []
        for key in task.gate_decisions:
            raw = await store.redis.get(key)
            if raw:
                try:
                    obj = json.loads(raw if isinstance(raw, str) else raw.decode())
                    # Map model field 'phase' to frontend field 'gate_phase'.
                    if "phase" in obj and "gate_phase" not in obj:
                        obj["gate_phase"] = obj["phase"]
                    hydrated_gates.append(obj)
                except Exception:
                    pass
        d["gate_decisions"] = hydrated_gates
        return d

    @app.get("/projects/{project_id}/tasks")
    async def list_tasks(project_id: UUID) -> list[dict[str, Any]]:
        tasks = await orch.list_tasks(project_id)
        return [await _hydrate_task(t) for t in tasks]

    @app.get("/projects/{project_id}/tasks/{task_id}")
    async def get_task(project_id: UUID, task_id: UUID) -> dict[str, Any]:
        t = await orch.get_task(project_id, task_id)
        if not t:
            raise HTTPException(status_code=404, detail="not found")
        return await _hydrate_task(t)

    @app.post("/projects/{project_id}/chat")
    async def chat(project_id: UUID, req: ChatMessageRequest) -> dict[str, Any]:
        # Only generate a reply for user messages (not orchestrator echoes).
        if req.actor == "user":
            await memory.write_chat_message(
                project_id=project_id, task_id=req.task_id, actor="user", text_=req.text
            )
            try:
                if req.task_id:
                    await store.redis.rpush(f"chatbuf:{project_id}:{req.task_id}", req.text)
            except Exception:
                pass

            # Generate orchestrator reply via LLM (Anthropic) if configured.
            reply_text: str | None = None
            try:
                from .llm import call_llm
                # Build conversation history as context.
                recent = await memory.list_chat_messages(
                    project_id=project_id, task_id=req.task_id, limit=20
                )
                history_msgs: list[dict[str, str]] = []
                for m in reversed(recent[-10:]):  # oldest first, last 10
                    role = "user" if m["actor"] == "user" else "assistant"
                    history_msgs.append({"role": role, "content": m["text"]})
                # Current message may not be in DB yet — ensure it's last.
                if not history_msgs or history_msgs[-1]["content"] != req.text:
                    history_msgs.append({"role": "user", "content": req.text})

                system = (
                    "You are the ODP (Orchestrated Dev Platform) orchestrator — an autonomous "
                    "software engineering platform. You help the user manage tasks, understand "
                    "agent results, and plan work. Be concise and helpful. "
                    "If the user asks about a task, refer to the project context."
                )
                resp = await call_llm(
                    system=system, messages=history_msgs,
                    max_tokens=512, env_prefix="ODP_ORCH_LLM"
                )
                if resp:
                    reply_text = resp.text
                    # Track orchestrator tokens against the task if provided.
                    if req.task_id:
                        t = await orch.get_task(project_id, req.task_id)
                        if t:
                            t.token_usage.orchestrator.add(
                                resp.input_tokens, resp.output_tokens, resp.cost_estimate
                            )
                            await orch._save_task(t)
                            total = t.token_usage.total
                            await bus.emit(project_id, req.task_id, "token_update", {
                                "token_usage": t.token_usage.model_dump(),
                                "total": total.model_dump(),
                            })
            except Exception:
                logger.exception("LLM chat reply failed")  # Fallback: static reply

            if not reply_text:
                reply_text = (
                    "I received your message. "
                    "Set ODP_ORCH_LLM_PROVIDER=anthropic and ODP_ORCH_LLM_API_KEY to enable AI responses."
                )

            await memory.write_chat_message(
                project_id=project_id, task_id=req.task_id,
                actor="orchestrator", text_=reply_text
            )
            await bus.emit(project_id, req.task_id or project_id, "chat_message", {
                "actor": "orchestrator", "text": reply_text
            })
        else:
            # Direct orchestrator message write (used internally).
            await memory.write_chat_message(
                project_id=project_id, task_id=req.task_id, actor=req.actor, text_=req.text
            )
        return {"ok": True}

    @app.get("/projects/{project_id}/chat")
    async def list_chat(
        project_id: UUID,
        task_id: UUID | None = None,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        msgs = await memory.list_chat_messages(project_id=project_id, task_id=task_id, limit=limit)
        # Return oldest-first so the frontend can render in chronological order.
        msgs = list(reversed(msgs))
        return {"messages": msgs}

    @app.delete("/projects/{project_id}/chat")
    async def clear_chat(project_id: UUID, task_id: UUID | None = None) -> dict[str, Any]:
        await memory.delete_chat_messages(project_id=project_id, task_id=task_id)
        return {"ok": True}

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
            raise HTTPException(status_code=404, detail="not found")

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
            raise HTTPException(status_code=404, detail="not found")
        base = Path(os.getenv("ODP_ARTIFACT_DIR", "runtime/artifacts")).resolve()
        path = Path(row["uri"])
        if not path.is_absolute():
            path = base / path
        try:
            resolved = path.resolve()
        except Exception:
            raise HTTPException(status_code=404, detail="not found")
        try:
            resolved.relative_to(base)
        except Exception:
            raise HTTPException(status_code=403, detail="forbidden")
        if not resolved.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(str(resolved))

    MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

    @app.post("/projects/{project_id}/tasks/{task_id}/artifacts")
    async def upload_artifact(project_id: UUID, task_id: UUID, file: UploadFile = File(...)) -> dict[str, Any]:
        # Sanitize filename: strip path components, reject suspicious names.
        raw_name = file.filename or "upload"
        safe_name = Path(raw_name).name  # strip directory components
        if not safe_name or safe_name.startswith(".") or "/" in raw_name or "\\" in raw_name:
            from uuid import uuid4 as _uuid4
            safe_name = f"{_uuid4().hex[:12]}.bin"

        base = Path(os.getenv("ODP_ARTIFACT_DIR", "runtime/artifacts")).resolve()
        upload_dir = base / str(project_id) / str(task_id) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        out = (upload_dir / safe_name).resolve()

        # Verify resolved path stays within upload dir.
        if not str(out).startswith(str(upload_dir)):
            raise HTTPException(status_code=400, detail="invalid filename")

        # Stream with size limit.
        total = 0
        with open(out, "wb") as f:
            while chunk := await file.read(8192):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    out.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="file too large")
                f.write(chunk)

        uri = str(out)
        await memory.record_artifact(project_id=project_id, task_id=task_id, type_="log", uri=uri)
        await bus.emit(project_id, task_id, "artifact_uploaded", {"uri": uri, "filename": safe_name})
        return {"ok": True, "uri": uri}

    def _ws_auth(websocket: WebSocket) -> bool:
        """Check WebSocket auth via query param or header. Returns True if allowed."""
        if not _auth_enabled():
            return True
        token = websocket.query_params.get("token", "")
        if not token:
            auth = websocket.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
        role = _role_for_token(token) if token else None
        return role is not None and _role_rank(role) >= _role_rank("reader")

    @app.websocket("/ws/projects/{project_id}")
    async def ws_project(websocket: WebSocket, project_id: UUID) -> None:
        """Project-level WebSocket: broadcasts all task events for the project."""
        if not _ws_auth(websocket):
            await websocket.close(code=1008, reason="unauthorized")
            return
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
        if not _ws_auth(websocket):
            await websocket.close(code=1008, reason="unauthorized")
            return
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

    @app.delete("/projects/{project_id}/tasks/{task_id}")
    async def delete_task(project_id: UUID, task_id: UUID) -> dict[str, Any]:
        """Delete a task and its associated Redis keys."""
        prefix = f"odp:{project_id}:task:{task_id}"
        # Remove task key and all sub-keys (agent results, gates, etc.)
        async for key in store.redis.scan_iter(f"{prefix}*"):
            await store.redis.delete(key)
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

    @app.patch("/projects/{project_id}")
    async def update_project(project_id: UUID, req: ProjectUpdateRequest) -> dict[str, Any]:
        key = f"odp:project:{project_id}:meta"
        raw = await redis.get(key)
        if not raw:
            # Auto-create if this is the fallback project or a valid UUID.
            meta = {"project_id": str(project_id), "name": "", "github_repo": "", "default_branch": "main"}
        else:
            meta = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        if req.name is not None:
            meta["name"] = req.name
        if req.github_repo is not None:
            meta["github_repo"] = req.github_repo
        if req.default_branch is not None:
            meta["default_branch"] = req.default_branch
        await redis.set(key, json.dumps(meta))
        return meta

    # ── Secrets (server-side only, never returned in full) ──

    _SECRETS_PREFIX = "odp:secrets:"

    @app.get("/projects/{project_id}/secrets/{secret_name}")
    async def get_secret_status(project_id: UUID, secret_name: str) -> dict[str, Any]:
        """Check if a secret is set. Returns masked value, never the real one."""
        allowed = {"github_token"}
        if secret_name not in allowed:
            raise HTTPException(status_code=400, detail=f"Unknown secret: {secret_name}")
        key = f"{_SECRETS_PREFIX}{project_id}:{secret_name}"
        raw = await redis.get(key)
        if raw:
            val = raw if isinstance(raw, str) else raw.decode()
            masked = val[:4] + "*" * (len(val) - 8) + val[-4:] if len(val) > 8 else "****"
            return {"set": True, "masked": masked}
        # Fall back to env var.
        env_val = os.getenv("ODP_GITHUB_TOKEN", "")
        if env_val:
            masked = env_val[:4] + "*" * (len(env_val) - 8) + env_val[-4:] if len(env_val) > 8 else "****"
            return {"set": True, "masked": masked, "source": "env"}
        return {"set": False, "masked": ""}

    @app.put("/projects/{project_id}/secrets/{secret_name}")
    async def set_secret(project_id: UUID, secret_name: str, req: SecretSetRequest) -> dict[str, Any]:
        """Store a secret in Redis (server-side only)."""
        allowed = {"github_token"}
        if secret_name not in allowed:
            raise HTTPException(status_code=400, detail=f"Unknown secret: {secret_name}")
        key = f"{_SECRETS_PREFIX}{project_id}:{secret_name}"
        await redis.set(key, req.value)
        return {"ok": True}

    @app.delete("/projects/{project_id}/secrets/{secret_name}")
    async def delete_secret(project_id: UUID, secret_name: str) -> dict[str, Any]:
        """Remove a secret from Redis."""
        key = f"{_SECRETS_PREFIX}{project_id}:{secret_name}"
        await redis.delete(key)
        return {"ok": True}

    # ── GitHub Webhook ──

    @app.post("/webhooks/github")
    async def github_webhook(request: Request) -> dict[str, Any]:
        """Receive GitHub webhook events and create tasks."""
        import hashlib
        import hmac

        secret = os.getenv("ODP_GITHUB_WEBHOOK_SECRET", "")
        body = await request.body()

        # Require secret to be configured; reject if not.
        if not secret:
            raise HTTPException(status_code=503, detail="webhook not configured")

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
