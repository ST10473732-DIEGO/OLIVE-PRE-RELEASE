from __future__ import annotations


class ToolRegistry:
    def __init__(self): self._tools = {}

    def register(self, tool) -> None:
        name = tool.definition.name
        if name in self._tools: raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = tool

    def unregister(self, name: str) -> bool: return self._tools.pop(name, None) is not None
    def get(self, name: str): return self._tools.get(name)
    def require(self, name: str):
        tool = self.get(name)
        if not tool: raise KeyError(f"Unknown tool: {name}")
        return tool
    def definitions(self, category: str | None = None):
        tools = self._tools.values()
        return [t.definition for t in tools if not getattr(t, "internal_only", False) and (category is None or t.definition.category == category)]
