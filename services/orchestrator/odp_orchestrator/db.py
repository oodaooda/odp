from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def db_url_from_env() -> str:
    url = os.getenv("ODP_DATABASE_URL")
    if not url:
        # Local dev default.
        url = "postgresql+asyncpg://odp:odp@localhost:5432/odp"
    return url


def create_engine() -> AsyncEngine:
    return create_async_engine(db_url_from_env(), pool_pre_ping=True)


SCHEMA_SQL_PG = """
create extension if not exists vector;

create table if not exists memory_events (
  project_id uuid not null,
  event_id uuid primary key,
  task_id uuid not null,
  type text not null check (type in ('message','decision','artifact','summary','state_transition')),
  actor text not null,
  payload jsonb not null,
  compaction_of uuid[],
  created_at timestamptz not null default now()
);
create index if not exists memory_events_task_id_idx on memory_events(task_id);
create index if not exists memory_events_type_idx on memory_events(type);
create index if not exists memory_events_project_id_idx on memory_events(project_id);

create table if not exists artifacts (
  project_id uuid not null,
  artifact_id uuid primary key,
  task_id uuid not null,
  type text not null check (type in ('screenshot','log','diff','report')),
  uri text not null,
  created_at timestamptz not null default now()
);
create index if not exists artifacts_task_id_idx on artifacts(task_id);
create index if not exists artifacts_project_id_idx on artifacts(project_id);

create table if not exists agent_memory_pending (
  project_id uuid not null,
  agent_memory_id uuid primary key,
  task_id uuid not null,
  role text not null check (role in ('engineer','qa','security')),
  type text not null check (type in ('scope_of_work','roadmap','test_log','verification_result')),
  payload jsonb not null,
  status text not null check (status in ('pending','approved','rejected')) default 'pending',
  created_at timestamptz not null default now()
);
create index if not exists agent_memory_pending_task_id_idx on agent_memory_pending(task_id);
create index if not exists agent_memory_pending_project_id_idx on agent_memory_pending(project_id);
create index if not exists agent_memory_pending_status_idx on agent_memory_pending(status);

create table if not exists promotion_decisions (
  project_id uuid not null,
  promotion_id uuid primary key,
  agent_memory_id uuid not null,
  decision text not null check (decision in ('approved','rejected')),
  note text,
  reviewer text not null,
  created_at timestamptz not null default now()
);
create index if not exists promotion_decisions_agent_memory_id_idx on promotion_decisions(agent_memory_id);
create index if not exists promotion_decisions_project_id_idx on promotion_decisions(project_id);

create table if not exists chat_messages (
  project_id uuid not null,
  message_id uuid primary key,
  task_id uuid,
  actor text not null check (actor in ('user','orchestrator')),
  text text not null,
  created_at timestamptz not null default now()
);
create index if not exists chat_messages_project_id_idx on chat_messages(project_id);
create index if not exists chat_messages_task_id_idx on chat_messages(task_id);
"""

# Dockerless/unit-test fallback (sqlite). Not production.
SCHEMA_SQLITE = """
create table if not exists memory_events (
  project_id text not null,
  event_id text primary key,
  task_id text not null,
  type text not null,
  actor text not null,
  payload text not null,
  compaction_of text,
  created_at text not null default (datetime('now'))
);
create index if not exists memory_events_task_id_idx on memory_events(task_id);
create index if not exists memory_events_type_idx on memory_events(type);
create index if not exists memory_events_project_id_idx on memory_events(project_id);

create table if not exists artifacts (
  project_id text not null,
  artifact_id text primary key,
  task_id text not null,
  type text not null,
  uri text not null,
  created_at text not null default (datetime('now'))
);
create index if not exists artifacts_task_id_idx on artifacts(task_id);
create index if not exists artifacts_project_id_idx on artifacts(project_id);

create table if not exists agent_memory_pending (
  project_id text not null,
  agent_memory_id text primary key,
  task_id text not null,
  role text not null,
  type text not null,
  payload text not null,
  status text not null default 'pending',
  created_at text not null default (datetime('now'))
);
create index if not exists agent_memory_pending_task_id_idx on agent_memory_pending(task_id);
create index if not exists agent_memory_pending_project_id_idx on agent_memory_pending(project_id);
create index if not exists agent_memory_pending_status_idx on agent_memory_pending(status);

create table if not exists promotion_decisions (
  project_id text not null,
  promotion_id text primary key,
  agent_memory_id text not null,
  decision text not null,
  note text,
  reviewer text not null,
  created_at text not null default (datetime('now'))
);
create index if not exists promotion_decisions_agent_memory_id_idx on promotion_decisions(agent_memory_id);
create index if not exists promotion_decisions_project_id_idx on promotion_decisions(project_id);

create table if not exists chat_messages (
  project_id text not null,
  message_id text primary key,
  task_id text,
  actor text not null,
  text text not null,
  created_at text not null default (datetime('now'))
);
create index if not exists chat_messages_project_id_idx on chat_messages(project_id);
create index if not exists chat_messages_task_id_idx on chat_messages(task_id);
"""


@dataclass
class MemoryWriter:
    engine: AsyncEngine

    async def init_schema(self) -> None:
        schema = SCHEMA_SQLITE if self.engine.dialect.name == "sqlite" else SCHEMA_SQL_PG
        async with self.engine.begin() as conn:
            for stmt in [s.strip() for s in schema.split(";\n") if s.strip()]:
                try:
                    await conn.execute(text(stmt))
                except Exception as e:
                    # pgvector may not be installed in some dev/test environments.
                    # Milestone 1 does not require embeddings; proceed without vector support.
                    if "vector" in stmt.lower():
                        continue
                    raise

    async def write_memory_event(
        self,
        *,
        project_id: UUID,
        task_id: UUID,
        type_: str,
        actor: str,
        payload: dict[str, Any],
        compaction_of: list[UUID] | None = None,
    ) -> UUID:
        event_id = uuid4()
        payload_json = json.dumps(payload)
        compaction_val: Any
        if compaction_of:
            compaction_val = [str(x) for x in compaction_of]
            if self.engine.dialect.name == "sqlite":
                compaction_val = json.dumps(compaction_val)
        else:
            compaction_val = None

        if self.engine.dialect.name == "sqlite":
            stmt = """
                insert into memory_events(project_id,event_id,task_id,type,actor,payload,compaction_of)
                values (:project_id,:event_id,:task_id,:type,:actor,:payload,:compaction_of)
            """
        else:
            stmt = """
                insert into memory_events(project_id,event_id,task_id,type,actor,payload,compaction_of)
                values (:project_id,:event_id,:task_id,:type,:actor,:payload::jsonb,:compaction_of)
            """

        async with self.engine.begin() as conn:
            await conn.execute(
                text(stmt),
                {
                    "project_id": str(project_id),
                    "event_id": str(event_id),
                    "task_id": str(task_id),
                    "type": type_,
                    "actor": actor,
                    "payload": payload_json,
                    "compaction_of": compaction_val,
                },
            )
        return event_id

    async def write_chat_message(
        self, *, project_id: UUID, task_id: UUID | None, actor: str, text_: str
    ) -> UUID:
        message_id = uuid4()
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    insert into chat_messages(project_id,message_id,task_id,actor,text)
                    values (:project_id,:message_id,:task_id,:actor,:text)
                    """
                ),
                {
                    "project_id": str(project_id),
                    "message_id": str(message_id),
                    "task_id": str(task_id) if task_id else None,
                    "actor": actor,
                    "text": text_,
                },
            )
        return message_id

    async def list_chat_messages(
        self,
        *,
        project_id: UUID,
        task_id: UUID | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        where = ["project_id=:project_id"]
        params: dict[str, Any] = {"project_id": str(project_id), "limit": int(limit)}
        if task_id:
            where.append("task_id=:task_id")
            params["task_id"] = str(task_id)

        sql = (
            "select message_id,task_id,actor,text,created_at from chat_messages where "
            + " and ".join(where)
            + " order by created_at desc limit :limit"
        )
        async with self.engine.begin() as conn:
            rows = (await conn.execute(text(sql), params)).mappings().all()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "message_id": str(r["message_id"]),
                    "task_id": str(r["task_id"]) if r["task_id"] else None,
                    "actor": str(r["actor"]),
                    "text": str(r["text"]),
                    "created_at": str(r["created_at"]),
                }
            )
        return out

    async def record_artifact(self, *, project_id: UUID, task_id: UUID, type_: str, uri: str) -> UUID:
        artifact_id = uuid4()
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    insert into artifacts(project_id,artifact_id,task_id,type,uri)
                    values (:project_id,:artifact_id,:task_id,:type,:uri)
                    """
                ),
                {
                    "project_id": str(project_id),
                    "artifact_id": str(artifact_id),
                    "task_id": str(task_id),
                    "type": type_,
                    "uri": uri,
                },
            )
        return artifact_id

    async def record_agent_memory_pending(
        self,
        *,
        project_id: UUID,
        task_id: UUID,
        role: str,
        type_: str,
        payload: dict[str, Any],
    ) -> UUID:
        agent_memory_id = uuid4()
        payload_json = json.dumps(payload)

        if self.engine.dialect.name == "sqlite":
            stmt = """
                insert into agent_memory_pending(project_id,agent_memory_id,task_id,role,type,payload,status)
                values (:project_id,:agent_memory_id,:task_id,:role,:type,:payload,'pending')
            """
        else:
            stmt = """
                insert into agent_memory_pending(project_id,agent_memory_id,task_id,role,type,payload,status)
                values (:project_id,:agent_memory_id,:task_id,:role,:type,:payload::jsonb,'pending')
            """

        async with self.engine.begin() as conn:
            await conn.execute(
                text(stmt),
                {
                    "project_id": str(project_id),
                    "agent_memory_id": str(agent_memory_id),
                    "task_id": str(task_id),
                    "role": role,
                    "type": type_,
                    "payload": payload_json,
                },
            )
        return agent_memory_id

    async def promote_agent_memory(
        self,
        *,
        project_id: UUID,
        agent_memory_id: UUID,
        decision: str,
        reviewer: str,
        note: str | None = None,
    ) -> UUID:
        promotion_id = uuid4()
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    insert into promotion_decisions(project_id,promotion_id,agent_memory_id,decision,note,reviewer)
                    values (:project_id,:promotion_id,:agent_memory_id,:decision,:note,:reviewer)
                    """
                ),
                {
                    "project_id": str(project_id),
                    "promotion_id": str(promotion_id),
                    "agent_memory_id": str(agent_memory_id),
                    "decision": decision,
                    "note": note,
                    "reviewer": reviewer,
                },
            )
            await conn.execute(
                text(
                    """
                    update agent_memory_pending
                    set status=:status
                    where project_id=:project_id and agent_memory_id=:agent_memory_id
                    """
                ),
                {
                    "status": decision,
                    "project_id": str(project_id),
                    "agent_memory_id": str(agent_memory_id),
                },
            )
        return promotion_id

    async def list_agent_memory(
        self,
        *,
        project_id: UUID,
        status: str | None = None,
        task_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where = ["project_id=:project_id"]
        params: dict[str, Any] = {"project_id": str(project_id), "limit": int(limit)}
        if status:
            where.append("status=:status")
            params["status"] = status
        if task_id:
            where.append("task_id=:task_id")
            params["task_id"] = str(task_id)
        sql = (
            "select agent_memory_id,task_id,role,type,payload,status,created_at "
            "from agent_memory_pending where "
            + " and ".join(where)
            + " order by created_at desc limit :limit"
        )

        async with self.engine.begin() as conn:
            rows = (await conn.execute(text(sql), params)).mappings().all()

        out: list[dict[str, Any]] = []
        for r in rows:
            payload_val = r["payload"]
            if isinstance(payload_val, str):
                try:
                    payload_val = json.loads(payload_val)
                except Exception:
                    payload_val = {"raw": payload_val}
            out.append(
                {
                    "agent_memory_id": str(r["agent_memory_id"]),
                    "task_id": str(r["task_id"]),
                    "role": str(r["role"]),
                    "type": str(r["type"]),
                    "payload": payload_val,
                    "status": str(r["status"]),
                    "created_at": str(r["created_at"]),
                }
            )
        return out

    async def get_agent_memory_meta(
        self, *, project_id: UUID, agent_memory_id: UUID
    ) -> dict[str, Any] | None:
        sql = """
            select agent_memory_id,task_id,role,type,payload,status
            from agent_memory_pending
            where project_id=:project_id and agent_memory_id=:agent_memory_id
            limit 1
        """
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(sql),
                    {"project_id": str(project_id), "agent_memory_id": str(agent_memory_id)},
                )
            ).mappings().first()
        if not row:
            return None
        payload_val = row["payload"]
        if isinstance(payload_val, str):
            try:
                payload_val = json.loads(payload_val)
            except Exception:
                payload_val = {"raw": payload_val}
        return {
            "agent_memory_id": str(row["agent_memory_id"]),
            "task_id": str(row["task_id"]),
            "role": str(row["role"]),
            "type": str(row["type"]),
            "payload": payload_val,
            "status": str(row["status"]),
        }
