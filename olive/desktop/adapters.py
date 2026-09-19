from __future__ import annotations

from typing import Protocol


class ApplicationAdapter(Protocol):
    name:str
    capabilities:tuple[str,...]
    async def launch(self,arguments:dict):...
    async def read_state(self,arguments:dict):...
    async def perform_action(self,action:str,arguments:dict):...


class ApplicationAdapterRegistry:
    def __init__(self):self._adapters={}
    def register(self,adapter:ApplicationAdapter):
        if adapter.name in self._adapters:raise ValueError(f"Duplicate application adapter: {adapter.name}")
        self._adapters[adapter.name]=adapter
    def require(self,name:str):
        if name not in self._adapters:raise KeyError(name)
        return self._adapters[name]
    def capabilities(self):return {name:tuple(adapter.capabilities) for name,adapter in self._adapters.items()}
