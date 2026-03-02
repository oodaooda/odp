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
