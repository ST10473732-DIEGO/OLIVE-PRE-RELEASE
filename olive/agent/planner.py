from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PlannedAction:
    tool_name: str
    arguments: dict
    rationale: str = ""


class Planner:
    async def create_plan(self, request: str, tools: list) -> list[PlannedAction]:
        """Provider boundary. Concrete planners may use a fast or general local model."""
        return []

    async def next_action(self, task, observations: list) -> PlannedAction | None:
        return None
