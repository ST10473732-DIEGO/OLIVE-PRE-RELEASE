from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable
import uuid


@dataclass(slots=True)
class ConfirmationRequest:
    task_id: str
    tool_name: str
    summary: str
    risk_level: str
    targets: list[str] = field(default_factory=list)
    allow_remember: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfirmationResponse:
    approved: bool
    cancel_task: bool = False
    remember: bool = False
    remember_all: bool = False


class ConfirmationService:
    def __init__(self, handler: Callable[[ConfirmationRequest], Awaitable[ConfirmationResponse]] | None = None):
        self.handler = handler

    async def request(self, request: ConfirmationRequest) -> ConfirmationResponse:
        if not self.handler: return ConfirmationResponse(False)
        return await self.handler(request)
