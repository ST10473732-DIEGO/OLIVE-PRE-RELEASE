"""Opt-in, bounded benchmark of the user's installed stack; no model downloads."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from olive.services.ollama_service import OllamaService
from olive.services.model_registry import ModelCapabilityRegistry
from olive.services.model_residency_service import ModelResidencyService
from olive.services.model_benchmark_service import ModelBenchmarkService


async def main(output):
    ollama = OllamaService()
    registry = ModelCapabilityRegistry(ollama)
    await registry.refresh()
    residency = ModelResidencyService(ollama)
    ollama.residency = residency
    names = ["qwen3:8b", "gpt-oss:20b", "qwen3-coder:30b", "devstral:24b", "qwen3-vl:8b"]

    def emit(topic, value):
        print(json.dumps(value), flush=True)

    service = ModelBenchmarkService(ollama, registry, output, emit)
    try:
        await service.run(names, timeout=90)
        await residency.refresh()
        print(json.dumps({"residency": residency.snapshot()}), flush=True)
    finally:
        if residency.current:
            await ollama.unload_model(residency.current)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=".qt-smoke/model-benchmarks-3.4.json")
    args = parser.parse_args()
    asyncio.run(main(Path(args.output)))
