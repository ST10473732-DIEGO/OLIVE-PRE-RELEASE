from __future__ import annotations

from pathlib import Path
from ..knowledge.source import KnowledgeSource
from .json_store import JsonStore


class KnowledgeSourceRepository:
    def __init__(self, path: Path): self.store = JsonStore(path)
    def load_all(self):
        value=self.store.read({"schema_version":1,"sources":[]}); sources=[KnowledgeSource.from_dict(x) for x in value.get("sources",[])]
        return {source.id:source for source in sources}
    def save(self, source):
        values=self.load_all(); values[source.id]=source
        self.store.write({"schema_version":1,"sources":[x.to_dict() for x in values.values()]}); return source
