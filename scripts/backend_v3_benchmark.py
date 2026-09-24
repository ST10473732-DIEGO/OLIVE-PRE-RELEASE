"""Explicit live benchmark; never downloads or promotes models."""
import argparse
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.evaluation.backend_benchmark import run

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--models', nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--split', choices=['development', 'held_out'], default='development')
    p.add_argument('--trials', type=int, default=3)
    p.add_argument('--case-limit', type=int)
    p.add_argument('--context', type=int, default=4096)
    p.add_argument('--num-predict', type=int, default=512)
    p.add_argument('--num-gpu', type=int)
    p.add_argument('--answer-gate', action='store_true')
    p.add_argument('--implicit-context-gate', action='store_true')
    a = vars(p.parse_args())
    answer_gate = a.pop('answer_gate')
    implicit = a.pop('implicit_context_gate')
    if answer_gate or implicit:
        async def answers():
            import shutil
            from olive.services.ollama_service import OllamaService
            from olive.services.model_registry import ModelCapabilityRegistry
            from olive.services.model_residency_service import ModelResidencyService
            from olive.services.local_ollama_runtime import LocalOllamaRuntime
            from olive.evaluation.answer_gate import run as gate, CANDIDATES
            if a['models'] != [*CANDIDATES, 'gpt-oss:20b']:
                raise ValueError('Answer gate requires exactly the two pinned candidates and installed baseline')
            service = OllamaService()
            runtime = LocalOllamaRuntime(service.host)
            await runtime.start()
            try:
                registry = ModelCapabilityRegistry(service)
                await registry.refresh()
                if await service.loaded_models():
                    raise RuntimeError('Close active inference and let its existing owner release the model first')
                service.residency = ModelResidencyService(service, lambda:{'contexts':{'general':8192}})
                if implicit:
                    from olive.evaluation.answer_gate import implicit_context_gate
                    await implicit_context_gate(service,registry,a['output'])
                else:
                    await gate(service,registry,a['output'],shutil.which('node'))
            finally:
                if service.residency and service.residency.current:
                    await service.unload_model(service.residency.current)
                await service.client._client.aclose()
                await runtime.close()
        asyncio.run(answers())
    else:
        asyncio.run(run(**a))
