from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import re
import uuid

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MemorySuggestion:
    content: str
    category: str
    source_chat_id: str
    source_message_index: int
    confidence: float = 0.7
    reason: str = "Durable information may be useful in future conversations"
    source_message_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class MemorySuggestionService:
    _durable_patterns = (
        (re.compile(r"\b(?:i|we) prefer\b", re.I), "preference"),
        (re.compile(r"\b(?:always|please always|standing instruction)\b", re.I), "instruction"),
        (re.compile(r"\bremember that\b", re.I), "fact"),
        (re.compile(r"\b(?:my|our) (?:long[- ]term )?goal is\b", re.I), "goal"),
        (re.compile(r"\b(?:this|the|our) project (?:uses|is|requires)\b", re.I), "project"),
    )
    _blocked = re.compile(
        r"(?:password|passphrase|api[-_ ]?key|secret|access[-_ ]?token|private key|credit card|"
        r"social security|medical diagnosis|bank account)", re.I
    )

    _temporary = re.compile(r"\b(?:today|tomorrow|right now|this time|for this request|one[- ]off)\b", re.I)
    _categories = {"preference", "instruction", "fact", "goal", "project"}

    def __init__(self, memory_service, ollama=None):
        self.memory_service = memory_service
        self.ollama = ollama

    def suggest(self, message: str, source_chat_id: str, source_message_index: int,
                source_message_id: str | None = None) -> list[MemorySuggestion]:
        content = " ".join(message.strip().split())
        if not self._safe(content):
            return []
        for pattern, category in self._durable_patterns:
            if pattern.search(content):
                if self.memory_service.search(content, limit=1, minimum_score=0.8):
                    return []
                return [MemorySuggestion(content, category, source_chat_id, source_message_index,
                                         source_message_id=source_message_id)]
        return []

    async def propose_structured(self, message: str, model: str, source_chat_id: str,
                                 source_message_id: str, source_message_index: int) -> list[MemorySuggestion]:
        if not self.ollama or not self._safe(message):
            return []
        schema = {"type": "object", "properties": {"memory": {"type": "string"},
            "category": {"type": "string"}, "confidence": {"type": "number"},
            "reason": {"type": "string"}},
            "required": ["memory", "category", "confidence", "reason"]}
        raw = await self.ollama.chat_once(model, [
            {"role": "system", "content": "Propose at most one durable, non-sensitive memory. Return strict JSON only."},
            {"role": "user", "content": message},
        ], options={"temperature": 0.0, "num_predict": 250}, format=schema)
        candidate = self._parse(raw, source_chat_id, source_message_id, source_message_index)
        return [candidate] if candidate else []

    def _parse(self, raw: str, chat_id: str, message_id: str, message_index: int) -> MemorySuggestion | None:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Local memory proposal returned invalid JSON")
            return None
        if not isinstance(value, dict) or set(value) != {"memory", "category", "confidence", "reason"}:
            return None
        content, category, reason = value["memory"], value["category"], value["reason"]
        confidence = value["confidence"]
        if (not isinstance(content, str) or not isinstance(category, str) or not isinstance(reason, str)
                or not isinstance(confidence, (int, float)) or category not in self._categories
                or not 0 <= float(confidence) <= 1 or float(confidence) < 0.65
                or len(reason) > 240 or not self._safe(content)):
            return None
        if self.memory_service.search(content, limit=1, minimum_score=0.8):
            return None
        return MemorySuggestion(content.strip(), category, chat_id, message_index, float(confidence),
                                reason.strip(), message_id)

    def _safe(self, content: str) -> bool:
        return bool(content.strip()) and len(content) <= 400 and not self._blocked.search(content) \
            and not self._temporary.search(content)

    def approve(self, suggestion: MemorySuggestion):
        return self.memory_service.add(
            suggestion.content, suggestion.category,
            suggestion.source_chat_id, suggestion.source_message_index,
            suggestion.source_message_id,
            suggestion.confidence, suggestion.reason,
        )
