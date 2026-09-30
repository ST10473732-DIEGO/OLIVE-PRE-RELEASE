"""Preset readiness follows the live model inventory, and every refresh tells the windows.

Regression: NOW answered live queries while the title bar and Chat still said
"NOW needs setup". NOW's preset carried a descriptive status instead of the
shared "Ready" word, and Settings › Models › Refresh never told the renderer.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from olive.agent.confirmation_service import ConfirmationResponse
from olive.application.service_container import ServiceContainer
from olive.services.ollama_service import ModelInfo
from olive.services.presets import MEDIA_PRESETS, PRESETS

NOW_MODEL = PRESETS['now']['model']


class ModelStateSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        async def deny(_):
            return ConfirmationResponse(False)

        self.events = []
        self.s = ServiceContainer(lambda topic, value: self.events.append(topic), deny,
                                  Path(temp.name), migrate=False)
        self.addAsyncCleanup(self.s.shutdown)
        # Deterministic local inventory; no live Ollama and never a download.
        self.inventory = {}
        ollama = self.s.ollama
        ollama.list_models = AsyncMock(side_effect=lambda: [ModelInfo(n, digest=d) for n, (d, _) in self.inventory.items()])
        ollama.model_capabilities = AsyncMock(side_effect=lambda name: self.inventory[name][1])
        ollama.context_length = AsyncMock(return_value=32768)
        ollama.loaded_models = AsyncMock(return_value=[])
        ollama.pull = AsyncMock(side_effect=AssertionError('refresh must not download'))

    def install(self, name, capabilities=('completion',), digest='d'):
        self.inventory[name] = (digest, capabilities)

    def preset(self, key):
        return self.s.presets.get(key)

    async def test_refresh_turns_now_ready_and_publishes(self):
        now = self.preset('now')
        self.assertEqual((now['available'], now['status']), (False, 'Needs setup'))

        self.install(NOW_MODEL, ('completion', 'vision', 'tools', 'thinking'))
        self.events.clear()
        result = await self.s.models.refresh()

        now = self.preset('now')
        self.assertEqual((now['available'], now['status']), (True, 'Ready'))
        # NowService's own wording is kept, not overwritten or faked.
        self.assertEqual(now['detail'], 'Local ready · live retrieval checked on request')
        self.assertEqual(now['inference_status'], 'Ready')
        self.assertEqual(next(p for p in result['presets'] if p['id'] == 'now')['status'], 'Ready')
        self.assertEqual(self.s.ollama_state, 'Ollama ready')
        self.assertEqual([m.name for m in self.s.model_infos], [NOW_MODEL])
        self.assertIn('models', self.events)
        self.assertIn('status', self.events)
        self.s.ollama.pull.assert_not_awaited()

    async def test_now_without_its_model_still_needs_setup(self):
        self.install('qwen3:8b')
        self.install(PRESETS['normal']['model'])
        await self.s.models.refresh()
        now = self.preset('now')
        self.assertEqual((now['available'], now['status']), (False, 'Needs setup'))
        self.assertEqual(now['detail'], 'Needs setup')

    async def test_now_embedding_only_model_is_not_ready(self):
        self.install(NOW_MODEL, ('embedding',))
        await self.s.models.refresh()
        self.assertEqual(self.preset('now')['status'], 'Needs setup')

    async def test_model_removed_on_refresh_needs_setup_again(self):
        self.install(NOW_MODEL)
        await self.s.models.refresh()
        self.assertEqual(self.preset('now')['status'], 'Ready')
        del self.inventory[NOW_MODEL]
        await self.s.models.refresh()
        self.assertEqual((self.preset('now')['available'], self.preset('now')['status']), (False, 'Needs setup'))

    async def test_ollama_down_on_refresh_reports_unavailable_not_stale_ready(self):
        self.install(NOW_MODEL)
        await self.s.models.refresh()
        self.s.ollama.list_models.side_effect = ConnectionError('refused')
        self.events.clear()
        with self.assertRaisesRegex(RuntimeError, 'not reachable'):
            await self.s.models.refresh()
        self.assertEqual(self.s.ollama_state, 'Ollama unavailable. Start Ollama and refresh Models')
        self.assertEqual(self.preset('now')['status'], 'Needs setup')
        # The windows still hear about it, so they show "AI offline".
        self.assertEqual(self.events[-2:], ['models', 'status'])

    async def test_ordinary_presets_follow_inventory(self):
        for key in ('fast', 'normal', 'deep'):
            self.assertEqual(self.preset(key)['status'], 'Needs setup')
        self.install('qwen3:8b')
        self.install(PRESETS['normal']['model'])
        self.install(PRESETS['max']['model'], digest=PRESETS['max']['pinned_digest'])
        await self.s.models.refresh()
        for key in ('fast', 'normal', 'max', 'deep'):
            preset = self.preset(key)
            self.assertEqual((preset['available'], preset['status']), (True, 'Ready'), key)
            self.assertNotIn('detail', preset)

    async def test_max_digest_comes_from_the_same_refresh(self):
        # model_infos used to be left stale by Settings › Refresh; MAX's pin reads it.
        self.install(PRESETS['max']['model'], digest='0' * 64)
        await self.s.models.refresh()
        self.assertEqual(self.preset('max')['status'], 'Needs setup')
        self.install(PRESETS['max']['model'], digest=PRESETS['max']['pinned_digest'])
        await self.s.models.refresh()
        self.assertEqual(self.preset('max')['status'], 'Ready')

    async def test_media_presets_are_untouched_by_model_refresh(self):
        before = {key: self.preset(key) for key in MEDIA_PRESETS}
        self.install(NOW_MODEL)
        await self.s.models.refresh()
        self.assertEqual({key: self.preset(key) for key in MEDIA_PRESETS}, before)

    async def test_startup_publishes_ready_inventory(self):
        self.install(NOW_MODEL)
        self.events.clear()
        await self.s.initialize()
        self.assertEqual(self.preset('now')['status'], 'Ready')
        self.assertLess(self.events.index('models'), self.events.index('status'))

    async def test_data_refresh_uses_inventory_refresh_not_startup(self):
        self.s.initialize = AsyncMock(side_effect=AssertionError('startup must not re-run'))
        self.install(NOW_MODEL)
        self.events.clear()
        models = await self.s.data.refresh_models()
        self.assertEqual([m['name'] for m in models], [NOW_MODEL])
        self.assertEqual(self.preset('now')['status'], 'Ready')
        self.assertIn('models', self.events)


if __name__ == '__main__':
    unittest.main()
