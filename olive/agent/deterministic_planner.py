from __future__ import annotations

from .fast_path import FastPathService


class DeterministicPlanner:
    def __init__(self): self.fast_path = FastPathService()
    async def create_plan(self, request, tools):
        result = self.fast_path.resolve(request)
        return [result.action] if result and result.action else []
    async def next_action(self, task, observations): return None
