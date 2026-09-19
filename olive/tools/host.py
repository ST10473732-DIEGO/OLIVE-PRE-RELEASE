from __future__ import annotations

from typing import Protocol


class ToolHost(Protocol):
    async def execute(self, tool_name: str, arguments: dict, context): ...


class InProcessToolHost:
    """Boundary that can later be replaced by an authenticated Windows service client."""
    def __init__(self, registry): self.registry = registry
    async def execute(self, tool_name: str, arguments: dict, context):
        return await self.registry.require(tool_name).execute(arguments, context)
