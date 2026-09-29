import asyncio
import hashlib
import tempfile
from pathlib import Path
import unittest
from PIL import Image
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.services.media_comfy import endpoint
from unittest.mock import AsyncMock, patch

class MediaTests(unittest.IsolatedAsyncioTestCase):
    def engine_running(self):
        # A configured engine that is listening and answering; release is what varies.
        return (patch('olive.services.media_engines.port_bound',return_value=True),
                patch('olive.services.local_comfy_runtime.LocalComfyRuntime.ready',new_callable=AsyncMock,return_value=True),
                patch('olive.services.media_comfy.ComfyWorkflows.release_idle',new_callable=AsyncMock))
    async def test_disconnect_requires_verified_release_and_retains_config_on_failure(self):
        self.s.media.config.write({'endpoint':'http://127.0.0.1:8188'})
        bound,ready,release_patch=self.engine_running()
        with bound,ready,release_patch as release:
            release.side_effect=RuntimeError('engine offline')
            with self.assertRaisesRegex(RuntimeError,'Cannot verify media GPU release'):
                await self.s.media.disconnect()
            self.assertTrue(self.s.media.config.read({})['endpoint'])
            release.side_effect=None
            result=await self.s.media.disconnect()
            self.assertEqual(result['engine'],{})
            self.assertEqual(result['image_generation'],'Needs setup')
    async def test_chat_blocks_until_configured_media_releases_gpu(self):
        self.s.media.config.write({'endpoint':'http://127.0.0.1:8188'})
        bound,ready,release_patch=self.engine_running()
        with bound,ready,release_patch as release:
            release.side_effect=RuntimeError('still running')
            with self.assertRaisesRegex(RuntimeError,'Cannot verify media GPU release'):
                async with self.s.ollama.residency.lease('fixture-model'):
                    self.fail('A model must not load while the media engine is unresolved')
            self.assertIsNone(self.s.ollama.residency.current)
            self.assertFalse(self.s.ollama.residency.lock.locked())
            release.side_effect=None
            async with self.s.ollama.residency.lease('fixture-model'):
                self.assertEqual(self.s.ollama.residency.current,'fixture-model')
    async def test_bound_but_silent_engine_is_not_proof_of_release(self):
        self.s.media.config.write({'endpoint':'http://127.0.0.1:8188'})
        with patch('olive.services.media_engines.port_bound',return_value=True), \
             patch('olive.services.local_comfy_runtime.LocalComfyRuntime.ready',new_callable=AsyncMock,return_value=False):
            with self.assertRaisesRegex(RuntimeError,'Cannot verify media GPU release'):
                async with self.s.ollama.residency.lease('fixture-model'):
                    self.fail('unreachable engine')
    async def test_unconfigured_engines_are_never_probed_or_started(self):
        # Nothing discovered or configured: a server on these ports is an unrelated app.
        with patch('olive.services.media_engines.port_bound') as bound, \
             patch('olive.services.local_comfy_runtime.LocalComfyRuntime.start_for',new_callable=AsyncMock) as start:
            async with self.s.ollama.residency.lease('fixture-model'):
                pass
            await self.s.chat_media.refresh()
        bound.assert_not_called();start.assert_not_awaited()
        self.assertEqual(self.s.chat_media.diagnostics()['video']['state'],'not installed')
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        async def deny(request):return ConfirmationResponse(False)
        self.s=ServiceContainer(lambda *args:None,deny,self.root/'profile',migrate=False)
        self.original=self.root/'source.png';Image.new('RGB',(80,60),'red').save(self.original)
    async def asyncTearDown(self):
        await self.s.shutdown();self.temp.cleanup()
    async def test_real_raster_edits_preserve_input_and_export_is_exclusive(self):
        before=self.original.read_bytes();source=await self.s.media.load(str(self.original))
        job=await self.s.media.start({'operation':'crop','source_id':source['id'],'width':32,'height':24,'left':8,'top':8})
        await self.s.media.tasks[job['id']];self.assertEqual(job['state'],'completed',job)
        output=Path(job['artifact']['path'])
        with Image.open(output) as image:self.assertEqual(image.size,(32,24));self.assertEqual(image.getpixel((0,0)),(255,0,0,255))
        self.assertEqual(self.original.read_bytes(),before);self.assertEqual(Path(source['path']).read_bytes(),before)
        self.assertEqual(job['artifact']['sha256'],hashlib.sha256(output.read_bytes()).hexdigest())
        destination=self.root/'export.png';self.s.media.export(job['id'],str(destination))
        with self.assertRaises(FileExistsError):self.s.media.export(job['id'],str(destination))
    async def test_cancelled_or_denied_operation_has_no_output(self):
        source=await self.s.media.load(str(self.original))
        await self.s.media.lock.acquire()
        job=await self.s.media.start({'operation':'resize','source_id':source['id'],'width':32,'height':32})
        self.s.media.cancel(job['id']);self.s.media.lock.release();await self.s.media.tasks[job['id']]
        self.assertEqual(job['state'],'cancelled');self.assertFalse((self.s.media.root/'outputs').exists())
        self.s.permissions.save({'filesystem.write':'deny'})
        job=await self.s.media.start({'operation':'resize','source_id':source['id'],'width':32,'height':32});await self.s.media.tasks[job['id']]
        self.assertEqual(job['state'],'failed');self.assertFalse((self.s.media.root/'outputs').exists())
    async def test_missing_generation_engine_is_not_a_generated_artifact(self):
        job=await self.s.media.start({'operation':'generate','prompt':'synthetic green circle','width':512,'height':512})
        await self.s.media.tasks[job['id']];self.assertEqual(job['state'],'failed');self.assertIsNone(job['artifact'])
        self.assertIn('Needs setup',job['error']);self.assertEqual(self.s.media.records()['artifacts'],[])
        for url in ['https://remote.example','http://localhost:8188','http://127.0.0.1:8188/evil','http://u:p@127.0.0.1:8188']:
            with self.assertRaises(ValueError):endpoint(url)
        self.assertEqual(endpoint('http://127.0.0.1:8188/'),'http://127.0.0.1:8188')
