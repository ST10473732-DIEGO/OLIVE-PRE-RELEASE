from __future__ import annotations

from dataclasses import dataclass
from ..services.model_policy import CANDIDATES, REQUEST_ROLE, validated_policy


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    role: str = "general"
    context_required: int = 0
    prefer_low_latency: bool = False
    task_type: str = ""
    # Callers whose prompts and budgets suit any candidate (including thinking models)
    # may reuse the loaded model instead of switching.
    prefer_loaded: bool = False


class ModelRouter:
    ROLES = {"fast", "general", "reasoning", "coding", "vision", "embedding"}
    def __init__(self, registry, settings=lambda: {}, benchmarks=None, residency=None):
        self.registry, self.settings = registry, settings
        self.benchmarks, self.residency = benchmarks, residency
        self.decisions = []

    def route(self, request: RoutingRequest, *, record=True):
        role={"simple_edit":"fast","code_search":"fast","planning":"coding","debugging":"reasoning","large_refactor":"coding","vision_testing":"vision"}.get(request.task_type,request.role)
        role = {"research_planning": "reasoning", "source_selection": "fast", "evidence_extraction": "general", "research_synthesis": "reasoning", "desktop_planning": "fast"}.get(role, role)
        if role not in self.ROLES: raise ValueError("Unknown model role")
        policy = validated_policy(self.settings())
        models = [m for m in self.registry.models.values() if getattr(m, "installed", True)]
        capable = [m for m in models if self._supports(m, role) and
                   int(getattr(m, "context_length", 0) or 0) >= request.context_required]
        if not capable:
            if record:
                self._record(role, None, "No compatible installed model")
            return None
        override = policy["overrides"].get(role)
        selected = next((m for m in capable if m.name == override), None)
        mode = "Performance" if request.prefer_low_latency else policy["mode"]

        def score(model):
            preferred = CANDIDATES[role]
            hint = preferred.index(model.name) if model.name in preferred else len(preferred) + (0 if getattr(model, "role", "") == role else 1)
            measured = self.benchmarks.summary(model.name, role) if self.benchmarks else None
            if measured:
                latency, quality = measured["latency_ms"] / 1000, measured["quality"]
                if quality < .5:
                    return (2, -quality, latency, hint)
                rank = (-quality, latency) if mode == "Quality" else (0 if quality >= .75 else 1, latency) if mode == "Performance" else (-quality + min(latency, 180) / 600, latency)
                return (0, *rank, hint)
            return (1, hint, int(getattr(model, "size", 0) or 0), model.name)

        # One managed model is resident at a time, so a different model means an unload and
        # a load. Opted-in callers keep the loaded model when it is a listed, adequately
        # measured candidate for this role.
        resident = (getattr(self.residency, "current", None)
                    if request.prefer_loaded and record and not selected else None)
        warm = next((m for m in capable if m.name == resident and m.name in CANDIDATES.get(role, ())), None)
        if warm is not None and self.benchmarks:
            measured = self.benchmarks.summary(warm.name, role)
            if measured and measured["quality"] < .5:
                warm = None
        reason = ("manual override" if selected else "already loaded; avoids a model switch" if warm
                  else "local measurements / compatible candidates")
        selected = selected or warm or min(capable, key=score)
        if record:
            REQUEST_ROLE.set(role)
            self._record(role, selected.name, reason)
        return selected

    def _record(self, role, model, reason):
        self.decisions.append({"role": role, "model": model, "reason": reason})
        self.decisions = self.decisions[-100:]

    @staticmethod
    def _supports(model, role):
        if role == "embedding": return bool(getattr(model, "supports_embeddings", False))
        if role == "vision": return bool(getattr(model, "supports_vision", False))
        return not bool(getattr(model, "supports_embeddings", False)) and not bool(getattr(model, "supports_vision", False))
