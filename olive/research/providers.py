from typing import Protocol
from .models import PageObservation, SearchResult


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int = 8, freshness: str = "any") -> list[SearchResult]: ...


class BrowserProvider(Protocol):
    name: str

    async def open(self, url: str) -> PageObservation: ...
    async def navigate(self, url: str) -> PageObservation: ...
    async def read(self, url: str) -> PageObservation: ...
    async def page_info(self, url: str) -> dict: ...
    async def links(self, url: str) -> list[dict]: ...
    async def follow_link(self, url: str, target: str) -> PageObservation: ...
    async def cancel(self): ...
    async def close(self): ...


class TorResearchProvider:
    """Future isolated provider contract; no Tor transport or proxy configuration."""

    name = "tor"
    available = False

    async def search(self, *args, **kwargs):
        raise NotImplementedError("Tor connectivity is not part of OLIVE 3.3")

    async def open(self, *args, **kwargs):
        raise NotImplementedError("Tor connectivity is not part of OLIVE 3.3")
