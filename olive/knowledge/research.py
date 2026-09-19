from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ResearchClaim:
    claim: str
    status: str = "unverified"
    source_ids: list[str] = field(default_factory=list)
    uncertainty: str = ""


@dataclass(slots=True)
class ResearchResult:
    summary: str
    claims: list[ResearchClaim]
    sources: list


class ResearchProviderRegistry:
    def __init__(self): self._providers = {}
    def register(self, provider): self._providers[provider.name] = provider
    def get(self, name): return self._providers.get(name)
    def available(self): return sorted(self._providers)
