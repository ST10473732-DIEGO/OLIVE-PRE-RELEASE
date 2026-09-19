from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentSession:
    chat_id: str
    mode: str = "chat"
    current_task_id: str | None = None
    cancellation_event: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self): self.cancellation_event.set()
