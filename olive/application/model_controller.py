"""Model policy and opt-in benchmarks for the shared runtime."""

from ..services.model_policy import ROLES, validated_policy
from ..agent.model_router import RoutingRequest


class ModelController:
    def __init__(self, services):
        self.s = services

    def status(self):
        policy = validated_policy(self.s.settings.get("model_policy"))
        assignments = []
        from ..services.model_policy import REQUEST_ROLE
        token = REQUEST_ROLE.set("general")
        try:
            for role in ROLES:
                selected = self.s.model_router.route(RoutingRequest(role), record=False)
                assignments.append({"role": role, "model": selected.name if selected else "Unavailable",
                    "override": policy["overrides"].get(role, ""), "context": policy["contexts"][role],
                    "benchmark": self.s.model_benchmarks.summary(selected.name, role) if selected else None})
        finally:
            REQUEST_ROLE.reset(token)
        return {"policy": policy, "assignments": assignments, "installed": list(self.s.model_registry.models),
                "presets": self.s.presets.list(),
                "conversation": {"chat_id": self.s.current_chat_id, "model": self.s.chats[self.s.current_chat_id].model},
                "residency": self.s.model_residency.snapshot(), "metrics": self.s.model_metrics.summary()[-30:],
                "decisions": self.s.model_router.decisions[-20:], "benchmark_active": bool(self.s.model_benchmarks.active)}

    async def refresh(self):
        await self.s.model_registry.refresh()
        await self.s.model_residency.refresh()
        return self.status()

    def save(self, policy):
        self.s.settings["model_policy"] = validated_policy(policy)
        self.s.settings_repo.save(self.s.settings)
        return self.status()

    async def benchmark(self, models, timeout=60):
        return await self.s.model_benchmarks.run(models, timeout)

    def stop_benchmark(self):
        self.s.model_benchmarks.cancel()
