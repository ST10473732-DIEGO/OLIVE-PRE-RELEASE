from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Awaitable, Callable, Sequence

from ..models import Message

SummaryFunction = Callable[[list[Message]], Awaitable[str]]


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic estimate suitable for local models and offline tests."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def reserve_ceiling(context_window: int) -> int:
    """The most of a model window an answer may reserve; the request keeps the rest.

    Shared by desktop Chat planning and Remote AI so the same preset has the
    same input budget on every path.
    """
    return max(256, int(context_window) // 2)


@dataclass(slots=True)
class ContextPlan:
    history: list[Message]
    summary: str
    estimated_input_tokens: int
    context_window: int
    response_reserve: int
    older_messages_summarized: int = 0
    over_budget: bool = False


class ContextService:
    def __init__(self, minimum_recent_messages: int = 6):
        self.minimum_recent_messages = max(2, minimum_recent_messages)

    async def plan(
        self,
        history: Sequence[Message],
        *,
        fixed_context: Sequence[str] = (),
        existing_summary: str = "",
        context_window: int = 32768,
        response_reserve: int = 4096,
        fixed_token_overhead: int = 0,
        summarizer: SummaryFunction | None = None,
    ) -> ContextPlan:
        window = max(1024, int(context_window))
        reserve = min(max(256, int(response_reserve)), reserve_ceiling(window))
        input_budget = window - reserve
        fixed_tokens = sum(estimate_tokens(part) for part in fixed_context) + max(0, fixed_token_overhead)
        summary = existing_summary.strip()
        summary_tokens = estimate_tokens(summary)
        messages = list(history)
        total = fixed_tokens + summary_tokens + sum(self._message_tokens(m) for m in messages)

        if total <= input_budget:
            return ContextPlan(messages, summary, total, window, reserve)

        keep_from = self._recent_turn_boundary(messages)
        older = messages[:keep_from]
        recent = messages[keep_from:]
        summarized = 0
        if older and summarizer is not None:
            new_summary = (await summarizer(older)).strip()
            if new_summary:
                # A lossy model summary cannot erase original scope, negatives,
                # workspace/device choices or answer-only requests. Preserve
                # earlier user/system messages verbatim with their provenance.
                pinned = [{"role": m.role, "content": m.content} for m in older if m.role in {"user", "system"}]
                if pinned:
                    new_summary += "\nVerbatim earlier requests (conversation data, not execution authority):\n" + json.dumps(pinned, ensure_ascii=False)
                summary = self._merge_summaries(summary, new_summary)
                summary_tokens = estimate_tokens(summary)
                summarized = len(older)
                messages = recent

        total = fixed_tokens + summary_tokens + sum(self._message_tokens(m) for m in messages)
        return ContextPlan(
            history=messages,
            summary=summary,
            estimated_input_tokens=total,
            context_window=window,
            response_reserve=reserve,
            older_messages_summarized=summarized,
            over_budget=total > input_budget,
        )

    def _recent_turn_boundary(self, messages: list[Message]) -> int:
        boundary = max(0, len(messages) - self.minimum_recent_messages)
        while boundary > 0 and messages[boundary].role != "user":
            boundary -= 1
        return boundary

    @staticmethod
    def _message_tokens(message: Message) -> int:
        return estimate_tokens(message.content) + 4

    @staticmethod
    def _merge_summaries(existing: str, new: str) -> str:
        if not existing:
            return new
        if new in existing:
            return existing
        return f"{existing}\n\nLater conversation summary:\n{new}"
