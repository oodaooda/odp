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

    def project_channel(self, project_id: UUID) -> str:
        return _k(project_id, "events:pubsub")

    async def emit(self, project_id: UUID, task_id: UUID, type_: str, payload: dict[str, Any]) -> None:
        event = {
            "ts_ms": now_ms(),
            "type": type_,
            **payload,
        }
        idx = await self.store.append_event(project_id, task_id, event)
        event["idx"] = idx - 1
        # Publish to task-level and project-level channels.
        await self.redis.publish(self.channel(project_id, task_id), str(event["idx"]))
        # Project-level: include task_id so clients can filter.
        import json

        def _serialize(obj: Any) -> Any:
            if isinstance(obj, UUID):
                return str(obj)
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

        project_event = {"task_id": str(task_id), "type": type_, "ts_ms": event["ts_ms"], **payload}
        await self.redis.publish(self.project_channel(project_id), json.dumps(project_event, default=_serialize))
