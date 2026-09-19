from __future__ import annotations

from typing import Protocol


class KnowledgeProvider(Protocol):
    name: str
    source_types: tuple[str, ...]
    async def fetch(self, origin: str, options: dict | None = None): ...


FUTURE_PROVIDER_TYPES = ("normal_web", "authenticated_web", "archives", "git", "rss", "tor")
