"""Opt-in synthetic evaluation through OLIVE's existing provider adapter.

No downloads, prompt/output persistence, generated-code execution or defaults
migration. Compiler/rubric/lifecycle cases are explicitly pending/separate.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time

from ..services.ollama_service import OllamaService
from ..services.model_registry import ModelCapabilityRegistry
from ..services.model_residency_service import ModelResidencyService
from .model_fixtures import schema, vision_image

FIXTURES = Path(__file__).parent / 'fixtures/backend_v3.json'


def load_cases(split='development'):
    suite = json.loads(FIXTURES.read_text())
    return [c for c in suite['cases'] if c['split'] == split]


def grade_json(content, expected):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    try:
        value = json.loads(content, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-JSON constant')))
    except (ValueError, TypeError):
        return False, False
    valid = isinstance(value, dict) and set(value) == set(expected) and all(type(value[k]) is type(v) for k, v in expected.items())
    return valid, valid and value == expected


def distribution(values):
    values = [v for v in values if v is not None]
    return {'n': len(values), 'median': statistics.median(values), 'min': min(values), 'max': max(values)} if values else {'n': 0}


async def sample_resources(stop, samples):
    import psutil
    while not stop.is_set():
        memory = psutil.virtual_memory()
        item = {'ram_available_bytes': memory.available, 'swap_used_bytes': psutil.swap_memory().used}
        try:
            process = await asyncio.create_subprocess_exec('nvidia-smi', '--query-gpu=memory.used,memory.total',
                '--format=csv,noheader,nounits', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(process.communicate(), 5)
            if process.returncode == 0:
                used, total = map(int, out.decode().splitlines()[0].split(','))
                item.update(vram_used_mib=used, vram_total_mib=total)
        except (OSError, ValueError, TimeoutError):
            if 'process' in locals() and process.returncode is None:
                process.kill()
                await process.wait()
        samples.append(item)
        try:
            await asyncio.wait_for(stop.wait(), 1)
        except TimeoutError:
            pass


async def run(models, output, *, split='development', trials=3, case_limit=None, context=4096, num_predict=512, num_gpu=None):
    if not 1 <= trials <= 10 or not 1024 <= context <= 16384:
        raise ValueError('Trials/context outside evaluation bounds')
    service = OllamaService('http://127.0.0.1:11434')
    registry = ModelCapabilityRegistry(service)
    await registry.refresh()
    if any(not registry.get(name) for name in models):
        raise ValueError('Every requested artifact must already be installed')
    if await service.loaded_models():
        raise RuntimeError('Runtime already has resident models; no externally owned work will be evicted')
    service.residency = ModelResidencyService(service, lambda: {'keep_alive': 60, 'contexts': {'general': context}})
    cases = load_cases(split)
    executable = [c for c in cases if c['kind'] in {'json', 'vision'}]
    if case_limit:
        executable = executable[:case_limit]
    result = {'schema_version': 1, 'suite': 'olive-backend-v3.1', 'fixture_sha256': hashlib.sha256(FIXTURES.read_bytes()).hexdigest(),
              'date': datetime.now(timezone.utc).isoformat(), 'split': split, 'trials': trials,
              'runtime_version': (await service.client._client.get('/api/version')).json()['version'],
              'resource_sample_seconds': 1, 'cold_definition': 'not resident, filesystem cache not cleared',
              'pending_cases': [c['id'] for c in cases if c not in executable], 'records': [], 'summaries': {}}
    try:
        for model in models:
            cap = registry.get(model)
            thinking = 'low' if model.startswith('gpt-oss:') else True if model.startswith('qwen3.8:') else False
            options = {'num_ctx': context, 'num_predict': num_predict, 'temperature': 0, 'seed': 42}
            if num_gpu is not None:
                options['num_gpu'] = num_gpu
            for trial in range(trials):
                for index, case in enumerate(executable):
                    if case['kind'] == 'vision' and not cap.supports_vision:
                        result['records'].append({'model': model, 'case': case['id'], 'trial': trial, 'status': 'unsupported', 'correct': False})
                        continue
                    message = {'role': 'user', 'content': case['prompt']}
                    if case['kind'] == 'vision':
                        message['images'] = [vision_image()]
                    record = {'model': model, 'digest': cap.digest, 'quantization': cap.quantization,
                              'template_sha256': cap.template_sha256, 'case': case['id'], 'trial': trial,
                              'cold_switch': trial == 0 and index == 0, 'options': options, 'think': thinking,
                              'correct': False, 'schema_valid': False, 'status': 'failed'}
                    stop, samples = asyncio.Event(), []
                    sampler = asyncio.create_task(sample_resources(stop, samples))
                    started = time.perf_counter()
                    try:
                        async with asyncio.timeout(120):
                            answer = await service.chat_measured(model, [message], options=options,
                                format=schema(case['expected']), think=thinking, stream=True)
                        record['schema_valid'], record['correct'] = grade_json(answer['content'], case['expected'])
                        record.update(status='completed', output_characters=len(answer['content']),
                                      first_visible_ms=answer['first_token_ms'], reasoning_stream_ms=answer['reasoning_stream_ms'],
                                      load_ms=answer['load_duration']/1e6, output_tokens=answer['eval_count'],
                                      prompt_tokens=answer['prompt_eval_count'],
                                      decode_tokens_s=answer['eval_count']/max(answer['eval_duration']/1e9, 1e-9),
                                      prefill_tokens_s=answer['prompt_eval_count']/max(answer['prompt_eval_duration']/1e9, 1e-9))
                    except Exception as error:
                        record['error'] = type(error).__name__
                    finally:
                        record['completion_ms'] = (time.perf_counter()-started)*1000
                        stop.set()
                        await sampler
                    record['resource_samples'] = len(samples)
                    record['peak_vram_mib'] = max((s.get('vram_used_mib', 0) for s in samples), default=None)
                    record['min_ram_available_bytes'] = min((s['ram_available_bytes'] for s in samples), default=None)
                    record['swap_growth_bytes'] = max((s['swap_used_bytes'] for s in samples), default=0) - (samples[0]['swap_used_bytes'] if samples else 0)
                    record['placement'] = await service.loaded_models()
                    result['records'].append(record)
                    output.write_text(json.dumps(result, indent=2)+'\n')
                    print(json.dumps({k: record.get(k) for k in ('model','case','trial','status','correct','completion_ms','error')}), flush=True)
            records = [r for r in result['records'] if r['model'] == model]
            result['summaries'][model] = {'n': len(records), 'correct': sum(r['correct'] for r in records),
                'failures': sum(r['status'] != 'completed' for r in records),
                'warm_first_visible_ms': distribution([r.get('first_visible_ms') for r in records if not r.get('cold_switch')]),
                'completion_ms': distribution([r.get('completion_ms') for r in records]),
                'promotion': 'NOT_PROMOTED: full rubric, compiler, workflow and held-out gates required'}
            output.write_text(json.dumps(result, indent=2)+'\n')
    finally:
        # This runner only releases the model it leased; never a GPU reset.
        if service.residency.current:
            await service.unload_model(service.residency.current)
        await service.client._client.aclose()
    return result
