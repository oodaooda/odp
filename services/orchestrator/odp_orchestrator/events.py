from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from .redis_store import _k, RedisStore


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class EventBus:
    redis: Redis
    store: RedisStore

    def channel(self, project_id: UUID, task_id: UUID) -> str:
        return _k(project_id, "task", str(task_id), "events:pubsub")

    async def emit(self, project_id: UUID, task_id: UUID, type_: str, payload: dict[str, Any]) -> None:
        event = {
            "ts_ms": now_ms(),
            "type": type_,
            **payload,
        }
        idx = await self.store.append_event(project_id, task_id, event)
        event["idx"] = idx - 1
        await self.redis.publish(self.channel(project_id, task_id), str(event["idx"]))
