from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from redis.asyncio import Redis


def _k(project_id: UUID, *parts: str) -> str:
    return ":".join(["odp", str(project_id), *parts])


@dataclass(frozen=True)
class RedisStore:
    redis: Redis

    async def put_json(self, key: str, obj: Any) -> None:
        await self.redis.set(key, json.dumps(obj, separators=(",", ":"), default=str))

    async def get_json(self, key: str) -> Any | None:
        raw = await self.redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    # Task
    def task_key(self, project_id: UUID, task_id: UUID) -> str:
        return _k(project_id, "task", str(task_id))

    def task_index_key(self, project_id: UUID) -> str:
        return _k(project_id, "tasks")

    async def index_task(self, project_id: UUID, task_id: UUID) -> None:
        await self.redis.sadd(self.task_index_key(project_id), str(task_id))

    async def list_task_ids(self, project_id: UUID) -> list[UUID]:
        ids = await self.redis.smembers(self.task_index_key(project_id))
        out: list[UUID] = []
        for x in ids:
            if isinstance(x, bytes):
                x = x.decode("utf-8")
            out.append(UUID(str(x)))
        return sorted(out)

    # Event log (reconnect-safe WS)
    def event_list_key(self, project_id: UUID, task_id: UUID) -> str:
        return _k(project_id, "task", str(task_id), "events")

    async def append_event(self, project_id: UUID, task_id: UUID, event: dict[str, Any]) -> int:
        # Store as a capped list.
        key = self.event_list_key(project_id, task_id)
        payload = json.dumps(event, separators=(",", ":"), default=str)
        await self.redis.rpush(key, payload)
        await self.redis.ltrim(key, -5000, -1)
        return int(await self.redis.llen(key))

    async def read_events(self, project_id: UUID, task_id: UUID, start_idx: int = 0) -> list[dict[str, Any]]:
        key = self.event_list_key(project_id, task_id)
        items = await self.redis.lrange(key, start_idx, -1)
        out: list[dict[str, Any]] = []
        for raw in items:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            out.append(json.loads(raw))
        return out
