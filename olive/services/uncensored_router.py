"""Automatic local routing for OLIVE UNCENSORED.

The public UI exposes simple capability tiers. Exact checkpoint names remain
internal implementation details and never grant additional execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re


FAST = (
    "lukey03/qwen3.5-9b-abliterated:latest",
    "olive-eval-hauhau-q6:20260924",
)

BALANCED = (
    "orcarouter/Qwen3.8-27B-Uncensored:q3_K_M",
    "olive-uncensored-qwen38-hauhau:latest",
)

DEEP = (
    "olive-uncensored-qwen38-hauhau:latest",
    "olive-uncensored-qwen36-35b:latest",
    "orcarouter/Qwen3.8-27B-Uncensored:q3_K_M",
)

MAXIMUM = (
    "olive-uncensored-qwen36-35b:latest",
    "olive-uncensored-qwen38-hauhau:latest",
    "orcarouter/Qwen3.8-27B-Uncensored:q3_K_M",
)

CREATIVE = (
    "olive-uncensored-dolphin24b:latest",
    "olive-uncensored-qwen38-hauhau:latest",
)

ALL_MODELS = tuple(
    dict.fromkeys(
        (*FAST, *BALANCED, *DEEP, *MAXIMUM, *CREATIVE)
    )
)


@dataclass(frozen=True, slots=True)
class UncensoredSelection:
    model: str
    tier: str
    reason: str


class UncensoredRouter:
    def __init__(self, registry):
        self.registry = registry
        self.decisions: list[dict[str, str]] = []

    def _installed(self, name: str) -> bool:
        model = self.registry.get(name)
        return bool(
            model
            and getattr(model, "installed", False)
            and not getattr(model, "supports_embeddings", False)
            and getattr(model, "backend", "ollama") == "ollama"
        )

    def available_models(self) -> list[str]:
        return [name for name in ALL_MODELS if self._installed(name)]

    def available(self) -> bool:
        return bool(self.available_models())

    @staticmethod
    def require_local(ollama):
        from ipaddress import ip_address
        from urllib.parse import urlsplit
        host = ollama.host
        endpoint = urlsplit(host if "://" in host else "http://" + host)
        local = endpoint.hostname == "localhost"
        try:
            local = local or ip_address(endpoint.hostname or "").is_loopback
        except ValueError:
            pass
        if endpoint.scheme not in {"http", "https"} or not local:
            raise ValueError("OLIVE UNCENSORED requires an Ollama server on this device.")

    def for_request(self, selection: UncensoredSelection):
        return _RequestRouter(self, selection.model)

    def interpreter_provider(self, ollama, selection: UncensoredSelection):
        return _InterpreterProvider(ollama, selection.model)

    def _first_available(self, names: tuple[str, ...]) -> str | None:
        return next((name for name in names if self._installed(name)), None)

    def select(self, text: str) -> UncensoredSelection:
        prompt = (text or "").strip()
        lower = prompt.lower()

        code_signal = bool(
            re.search(
                r"\b("
                r"code|coding|program|function|class|api|sql|python|javascript|"
                r"typescript|java|csharp|rust|debug|bug|compile|refactor|"
                r"repository|algorithm|regex|docker|linux|powershell|bash"
                r")\b|\bc#(?!\w)",
                lower,
            )
        )

        reasoning_signal = bool(
            re.search(
                r"\b("
                r"analyse|analyze|reason|prove|derive|compare|architectur(?:e|al)|"
                r"trade[- ]?offs?|evaluate|diagnose|step by step|why does|"
                r"complex|deep|plan|strategy|mathematics|math|logic"
                r")\b",
                lower,
            )
        )

        creative_signal = bool(
            re.search(
                r"\b("
                r"story|roleplay|role-play|poem|creative|character|dialogue|"
                r"screenplay|lyrics|rewrite|worldbuilding|brainstorm"
                r")\b",
                lower,
            )
        )

        maximum_signal = bool(
            re.search(
                r"\b("
                r"maximum|max quality|highest quality|most powerful|"
                r"very complex|extremely complex|exhaustive|full architecture|"
                r"large refactor|production[- ]grade"
                r")\b",
                lower,
            )
        )

        very_large = len(prompt) >= 3000 or prompt.count("\n") >= 35
        moderately_large = len(prompt) >= 1200 or prompt.count("\n") >= 18

        if maximum_signal or very_large or (code_signal and reasoning_signal):
            tier = "MAX"
            candidates = MAXIMUM
            reason = "highest-resource request"

        elif creative_signal and not code_signal:
            tier = "CREATIVE"
            candidates = CREATIVE
            reason = "creative or long-form writing request"

        elif reasoning_signal or moderately_large:
            tier = "DEEP"
            candidates = DEEP
            reason = "reasoning-intensive request"

        elif code_signal:
            tier = "BALANCED"
            candidates = BALANCED
            reason = "technical or coding request"

        elif len(prompt) <= 420:
            tier = "FAST"
            candidates = FAST
            reason = "short general request"

        else:
            tier = "BALANCED"
            candidates = BALANCED
            reason = "general request requiring more capability"

        model = self._first_available(candidates)

        if model is None:
            model = self._first_available(ALL_MODELS)

        if model is None:
            raise ValueError(
                "OLIVE UNCENSORED has no installed local model available."
            )

        selection = UncensoredSelection(
            model=model,
            tier=tier,
            reason=reason,
        )

        self.decisions.append(
            {
                "model": selection.model,
                "tier": selection.tier,
                "reason": selection.reason,
            }
        )
        self.decisions = self.decisions[-100:]

        return selection


class _RequestRouter:
    """Interpretation and its bounded retries use the selected answer model.

    This adapter is request-local; it never changes the shared router, residency
    service, tool routing, or permissions. A vision-capable completion model can
    also serve a text role without being used for image interpretation here.
    """

    def __init__(self, router, model):
        self.router, self.model = router, model

    def route(self, request, *, record=True):
        if request.role not in {"fast", "general", "reasoning", "coding"}:
            return None
        if not self.router._installed(self.model):
            raise ValueError("OLIVE UNCENSORED has no installed local model available.")
        model = self.router.registry.get(self.model)
        if model.context_length < request.context_required:
            raise ValueError("The selected UNCENSORED model has insufficient context for interpretation.")
        if record:
            from .model_policy import REQUEST_ROLE
            REQUEST_ROLE.set("general")
        return replace(model, role=request.role)


class _InterpreterProvider:
    """Keep all interpretation helpers on one non-thinking local model.

    Some installed templates reject a second System message, including the
    interpreter's examples. Join only leading System messages; user content
    never gains system authority. The real adapter still owns limits/leases.
    """

    def __init__(self, ollama, model):
        self.ollama, self.model = ollama, model

    def _messages(self, model, messages):
        if model != self.model:
            raise ValueError("UNCENSORED interpretation cannot switch models within a request")
        boundary = 0
        while boundary < len(messages) and messages[boundary].get("role") == "system":
            boundary += 1
        if boundary < 2:
            return messages
        return [{"role": "system", "content": "\n\n".join(m["content"] for m in messages[:boundary])},
                *messages[boundary:]]

    async def chat_measured(self, model, messages, **kwargs):
        kwargs["think"] = False
        return await self.ollama.chat_measured(model, self._messages(model, messages), **kwargs)

    async def chat_once(self, model, messages, **kwargs):
        kwargs["think"] = False
        return await self.ollama.chat_once(model, self._messages(model, messages), **kwargs)
