from __future__ import annotations

import re

from ..memory import Memory
from ..models import now_iso
from ..storage.memory_repository import MemoryRepository


class MemoryService:
    def __init__(self, repository: MemoryRepository):
        self.repository = repository

    def list_all(self) -> list[Memory]:
        return sorted(self.repository.load_all().values(), key=lambda m: m.updated_at, reverse=True)

    def add(
        self,
        content: str,
        category: str = "fact",
        source_chat_id: str | None = None,
        source_message_index: int | None = None,
        source_message_id: str | None = None,
        confidence: float | None = None,
        reason: str | None = None,
    ) -> Memory:
        content = content.strip()
        if not content:
            raise ValueError("Memory content cannot be empty")
        memories = self.repository.load_all()
        normalized = _normalize(content)
        for existing in memories.values():
            if _normalize(existing.content) == normalized:
                return existing
        memory = Memory(
            content=content,
            category=category,
            source_chat_id=source_chat_id,
            source_message_index=source_message_index,
            source_message_id=source_message_id,
            confidence=confidence, reason=reason,
        )
        memories[memory.id] = memory
        self.repository.save_all(memories.values())
        return memory

    def update(self, memory_id: str, *, content: str, category: str | None = None) -> Memory:
        memories = self.repository.load_all()
        if memory_id not in memories:
            raise KeyError(memory_id)
        memory = memories[memory_id]
        memory.content = content.strip()
        if not memory.content:
            raise ValueError("Memory content cannot be empty")
        if category is not None:
            memory.category = category
        memory.updated_at = now_iso()
        self.repository.save_all(memories.values())
        return memory

    def delete(self, memory_id: str) -> bool:
        memories = self.repository.load_all()
        removed = memories.pop(memory_id, None) is not None
        if removed:
            self.repository.save_all(memories.values())
        return removed

    def search(self, query: str, limit: int = 5, minimum_score: float = 0.2) -> list[tuple[Memory, float]]:
        terms = set(_tokens(query))
        if not terms:
            return []
        ranked = []
        for memory in self.repository.load_all().values():
            words = set(_tokens(memory.content + " " + memory.category))
            score = len(terms & words) / len(terms)
            if score >= minimum_score:
                ranked.append((memory, score))
        ranked.sort(key=lambda item: (item[1], item[0].updated_at), reverse=True)
        return ranked[: max(0, limit)]

    def search_for_project(self, query: str, project_id: str | None, project_memory_ids: list[str] | None = None,
                           limit: int = 5) -> list[tuple[Memory, float]]:
        ranked=self.search(query,limit=max(limit*3,limit),minimum_score=0.1)
        preferred=set(project_memory_ids or [])
        ranked.sort(key=lambda item:(item[0].id in preferred,item[1],item[0].updated_at),reverse=True)
        return ranked[:limit]


def _tokens(value: str) -> list[str]:
    return re.findall(r"[\w-]+", value.lower(), flags=re.UNICODE)


def _normalize(value: str) -> str:
    return " ".join(_tokens(value))
