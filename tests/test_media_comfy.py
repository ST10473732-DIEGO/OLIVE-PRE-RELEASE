import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from olive.services.media_comfy import ComfyImages


class ComfyProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_or_unmeasured_runtime_cannot_configure(self):
        for stats, message in [
            ({'system': {'comfyui_version': '0.34.0'}}, '0.35.0 or newer'),
            ({'system': {'comfyui_version': '0.35.0'},
              'devices': [{'name': 'cudaMallocAsync'}]}, 'disable-cuda-malloc'),
            ({'system': {'comfyui_version': '0.35.0'},
              'devices': [{'name': 'native'}]}, 'disable-dynamic-vram'),
        ]:
            engine = ComfyImages('http://127.0.0.1:8188')
            engine.request = AsyncMock(side_effect=[stats, {}])
            with self.assertRaisesRegex(ValueError, message):
                await engine.inspect()

    async def test_release_times_out_if_model_memory_remains(self):
        engine = ComfyImages('http://127.0.0.1:8188')
        async def request(method, path, **kwargs):
            if path == '/system_stats':
                return {'system': {'argv': ['--disable-dynamic-vram']},
                        'devices': [{'type': 'cuda', 'torch_vram_total': 4_000_000_000}]}
            return {}
        engine.request = AsyncMock(side_effect=request)
        with patch('olive.services.media_comfy.time.monotonic', side_effect=[0, 1, 31]), \
             patch('olive.services.media_comfy.asyncio.sleep', new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError, 'did not confirm GPU memory release'):
                await engine.release_idle()

    async def test_empty_command_ack_is_valid_but_empty_stats_is_not(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b''))
        client = httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:8188')
        with patch('olive.services.media_comfy.httpx.AsyncClient', return_value=client):
            self.assertEqual(await ComfyImages('http://127.0.0.1:8188').request('POST', '/free'), {})
        client = httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:8188')
        with patch('olive.services.media_comfy.httpx.AsyncClient', return_value=client):
            with self.assertRaises(ValueError):
                await ComfyImages('http://127.0.0.1:8188').request('GET', '/system_stats')

    async def test_release_waits_for_allocator_not_http_ack(self):
        engine = ComfyImages('http://127.0.0.1:8188')
        observations = iter([4_000_000_000, 0])
        async def request(method, path, **kwargs):
            if path == '/system_stats':
                return {'system': {'argv': ['--disable-dynamic-vram']},
                        'devices': [{'type': 'cuda', 'torch_vram_total': next(observations)}]}
            return {}
        engine.request = AsyncMock(side_effect=request)
        with patch('olive.services.media_comfy.asyncio.sleep', new_callable=AsyncMock) as sleep:
            await engine.release_idle()
            sleep.assert_awaited_once()
        self.assertEqual(sum(c.args[1] == '/system_stats' for c in engine.request.await_args_list), 2)

    async def test_release_does_not_unload_a_busy_engine(self):
        engine = ComfyImages('http://127.0.0.1:8188')
        engine.request = AsyncMock(return_value={'queue_running': [[0, 'another-prompt']]})
        with self.assertRaisesRegex(RuntimeError, 'still busy'):
            await engine.release_idle()
        self.assertEqual(engine.request.await_count, 1)

    async def test_cancel_interrupts_only_own_prompt_and_waits_for_stop(self):
        engine = ComfyImages('http://127.0.0.1:8188')
        engine.inspect = AsyncMock(return_value={'checkpoints': ['model'], 'version': '0.35.0'})
        engine.release_idle = AsyncMock()
        cancel = asyncio.Event()
        prompt_id = 'a' * 32
        queued = False
        polls = 0
        async def request(method, path, **kwargs):
            nonlocal queued, polls
            if path == '/prompt':
                queued = True
                cancel.set()
                return {'prompt_id': prompt_id}
            if path == '/queue' and method == 'GET' and queued:
                polls += 1
                return {'queue_running': [[0, prompt_id]] if polls == 1 else []}
            return {}
        engine.request = AsyncMock(side_effect=request)
        with patch('olive.services.media_comfy.asyncio.sleep', new_callable=AsyncMock):
            with self.assertRaises(asyncio.CancelledError):
                await engine.render({'checkpoint': 'model', 'prompt': 'olive', 'width': 512,
                    'height': 512, 'seed': 0, 'steps': 20, 'cfg': 7}, None, 'job', cancel, lambda _: None)
        engine.request.assert_any_await('POST', '/interrupt', json={'prompt_id': prompt_id})
        engine.request.assert_any_await('POST', '/queue', json={'delete': [prompt_id]})
        self.assertEqual(polls, 2)
        engine.release_idle.assert_awaited_once()
