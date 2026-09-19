"""Read current role choices and run two bounded local residency requests."""
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.services.ollama_service import OllamaService
from olive.services.model_registry import ModelCapabilityRegistry
from olive.services.model_benchmark_service import ModelBenchmarkService
from olive.services.model_residency_service import ModelResidencyService
from olive.storage.settings_repository import SettingsRepository
from olive.agent.model_router import ModelRouter, RoutingRequest
from olive.desktop.vision import DesktopVision
from olive.config import DATA_DIR


async def main():
    policy = SettingsRepository().load().get("model_policy", {})
    ollama = OllamaService()
    residency = ModelResidencyService(ollama, lambda: policy)
    ollama.residency = residency
    registry = ModelCapabilityRegistry(ollama)
    await registry.refresh()
    benchmarks = ModelBenchmarkService(ollama, registry, DATA_DIR / "model_benchmarks.json")
    router = ModelRouter(registry, lambda: policy, benchmarks, residency)
    roles = {role: router.route(RoutingRequest(role), record=False).name for role in sorted(router.ROLES)}
    try:
        capture = {"id": "owned-acceptance-image", "path": str(Path(__file__).resolve().parents[1] / ".qt-smoke" / "visual-fixture.png")}
        vision = await DesktopVision(ollama, router).verify_label(capture, "Preview")
        first = await residency.refresh()
        model = router.route(RoutingRequest("reasoning"))
        response = await asyncio.wait_for(ollama.chat_measured(model.name,
            [{"role": "user", "content": 'Return JSON {"answer": 42} for six multiplied by seven.'}],
            options={"temperature": 0, "num_predict": 180, "num_ctx": 2048},
            format={"type": "object", "required": ["answer"], "properties": {"answer": {"type": "integer"}}},
            think="low" if model.name.startswith("gpt-oss") else False, stream=True), 45)
        if json.loads(response["content"]) != {"answer": 42} or not vision["verified"]:
            raise AssertionError("Bounded residency requests did not return valid results")
        second = await residency.refresh()
        print(json.dumps({"roles": roles, "deterministic_desktop_model_calls": 0, "vision_verified": vision["verified"],
                          "reasoning_latency_ms": response["duration_ms"], "after_vision": first, "after_reasoning": second}), flush=True)
    finally:
        if residency.current:
            await ollama.unload_model(residency.current)


if __name__ == "__main__":
    asyncio.run(main())
