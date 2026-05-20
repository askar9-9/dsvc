from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class DomainEvent:
    type: str
    entity_id: str | None = None
    old_state: str | None = None
    new_state: str | None = None
    attributes: dict | None = None
    source: str = "system"
    timestamp: datetime | None = None
    user_id: UUID | None = None
    automation_id: UUID | None = None
    metadata: dict | None = None

    def sse_payload(self) -> dict:
        data = {
            "type": self.type,
            "entity_id": self.entity_id,
            "new_state": self.new_state,
            "attributes": self.attributes or {},
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z") if self.timestamp else None,
        }
        if self.automation_id:
            data["automation_id"] = str(self.automation_id)
        return data


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[DomainEvent]] = set()

    def subscribe(self) -> asyncio.Queue[DomainEvent]:
        queue: asyncio.Queue[DomainEvent] = asyncio.Queue(maxsize=128)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[DomainEvent]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: DomainEvent) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self.unsubscribe(queue)

    async def stream(self) -> AsyncIterator[DomainEvent]:
        queue = self.subscribe()
        try:
            while True:
                yield await queue.get()
        finally:
            self.unsubscribe(queue)


event_bus = EventBus()
