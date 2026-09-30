"""Chat-native REIMAGINE / AUDIO / VIDEO with fake local engines (no real services)."""
import asyncio
import base64
import hashlib
import io
import json
import struct
import subprocess
import shutil
import tempfile
import unittest
import wave
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image

from olive.agent.confirmation_service import ConfirmationResponse
from olive.application.service_container import ServiceContainer
from olive.bridge.public_errors import public_error
from olive.models import Chat, Message, clean_artifact
from olive.services import media_workflows as wf
from olive.services.chat_media_service import speech_request
from olive.services.local_comfy_runtime import LocalComfyRuntime
from olive.services.media_comfy import ComfyWorkflows
from olive.services.media_errors import MediaError
from olive.services.voicestudio import VoiceStudio, loopback


def png(color='red', size=(64, 48)):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format='PNG')
    return buffer.getvalue()


_MP4 = {}


def mp4(frames=49, size=(1536, 896), audio=True):
    """A real H.264/AAC clip shaped like one LTX segment (the pipeline probes it
    with ffprobe), or a bare MP4 header on a computer without FFmpeg."""
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        return struct.pack('>I', 24) + b'ftypisom' + b'\0' * 12 + b'fake-mp4-payload'
    key = (frames, size, audio)
    if key not in _MP4:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'clip.mp4'
            argv = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size={size[0]}x{size[1]}:rate=24']
            if audio:
                argv += ['-f', 'lavfi', '-t', '2.01', '-i', 'sine=frequency=440:sample_rate=48000', '-c:a', 'aac', '-ac', '2']
            argv += ['-frames:v', str(frames), '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-f', 'mp4', str(target)]
            subprocess.run(argv, check=True)
            _MP4[key] = target.read_bytes()
    return _MP4[key]


def wav(seconds=0.5):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(24000)
        clip.writeframes(b'\0\0' * int(24000 * seconds))
    return buffer.getvalue()


def object_info(workflows, modules=None):
    info = {}
    for workflow in workflows:
        for node, prefixes in workflow.nodes.items():
            module = (modules or {}).get(node) or ('nodes' if prefixes[0] == 'nodes' else prefixes[0])
            info.setdefault(node, {'python_module': module, 'input': {'required': {}}})
        for (node, name), filename in workflow.files.items():
            required = info.setdefault(node, {'python_module': 'nodes', 'input': {'required': {}}})['input']['required']
            options = required.setdefault(name, [[]])[0]
            options.append(filename)
    return info


class FakeComfy:
    """Minimal ComfyUI HTTP behaviour: queue, history, view, free, interrupt."""

    def __init__(self, workflows, output=b'', version='0.35.0', allocator_measured=True, finish_after=1, fail=False):
        self.workflows, self.output, self.version = workflows, output, version
        self.measured, self.finish_after, self.fail = allocator_measured, finish_after, fail
        self.prompts, self.uploads, self.calls, self.polls = {}, {}, [], 0
        self.running = None
        self.vram = 0
        self.interrupted = []

    def handler(self, request):
        path = request.url.path
        self.calls.append((request.method, path))
        if path == '/system_stats':
            argv = ['main.py', '--disable-dynamic-vram'] if self.measured else ['main.py']
            name = 'cuda:0 GPU : native' if self.measured else 'cuda:0 GPU : cudaMallocAsync'
            return httpx.Response(200, json={'system': {'comfyui_version': self.version, 'argv': argv},
                                             'devices': [{'type': 'cuda', 'name': name, 'torch_vram_total': self.vram}]})
        if path == '/object_info':
            return httpx.Response(200, json=object_info(self.workflows))
        if path == '/queue' and request.method == 'GET':
            running = [[0, self.running]] if self.running else []
            return httpx.Response(200, json={'queue_running': running, 'queue_pending': []})
        if path == '/queue':
            return httpx.Response(200, content=b'')
        if path == '/interrupt':
            self.interrupted.append(json.loads(request.content)['prompt_id'])
            self.running = None
            return httpx.Response(200, content=b'')
        if path == '/free':
            self.vram = 0
            return httpx.Response(200, content=b'')
        if path == '/upload/image':
            name = request.content.split(b'filename="')[1].split(b'"')[0].decode()
            self.uploads[name] = request.content
            return httpx.Response(200, json={'name': name, 'subfolder': '', 'type': 'input'})
        if path == '/prompt':
            body = json.loads(request.content)
            prompt_id = 'a' * 8 + '-' + 'b' * 4 + '-' + 'c' * 4 + '-' + 'd' * 4 + '-' + 'e' * 12
            self.prompts[prompt_id] = body
            self.running = prompt_id
            self.vram = 9_000_000_000
            return httpx.Response(200, json={'prompt_id': prompt_id, 'number': 1, 'node_errors': {}})
        if path.startswith('/history/'):
            prompt_id = path.rsplit('/', 1)[1]
            self.polls += 1
            if self.running != prompt_id or self.polls < self.finish_after:
                return httpx.Response(200, json={})
            self.running = None
            if self.fail:
                return httpx.Response(200, json={prompt_id: {'status': {'status_str': 'error'}, 'outputs': {}}})
            prefix = self.prompts[prompt_id]['prompt']['save']['inputs']['filename_prefix'].split('/', 1)[1]
            extension = 'mp4' if self.output[4:8] == b'ftyp' else 'png'
            return httpx.Response(200, json={prompt_id: {'status': {'status_str': 'success'}, 'outputs': {
                'save': {'images': [{'filename': f'{prefix}_00001_.{extension}', 'subfolder': 'OLIVE', 'type': 'output'}]}}}})
        if path == '/view':
            return httpx.Response(200, content=self.output)
        return httpx.Response(404)


class ChatMediaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        async def deny(_): return ConfirmationResponse(False)
        self.s = ServiceContainer(lambda *a: None, deny, self.root / 'profile', migrate=False)
        self.chat_id = self.s.current_chat_id
        # Text inference must never run for a media preset.
        self.s.ollama.chat_stream = AsyncMock(side_effect=AssertionError('text inference used'))
        self.s.ollama.loaded_models = AsyncMock(return_value=[])
        self.s.ollama.unload_model = AsyncMock()
        self.stack = ExitStack()

    async def asyncTearDown(self):
        self.stack.close()
        await self.s.shutdown()
        self.temp.cleanup()

    def engine(self, kind, fake):
        """Configure one engine as discovered and serve it from a FakeComfy."""
        engine = self.s.chat_media.engines.get(kind)
        engine.runtime.root, engine.runtime.python = str(self.root / kind), str(self.root / 'python')
        (self.root / kind).mkdir(exist_ok=True)
        (self.root / kind / 'main.py').write_text('')
        (self.root / 'python').write_text('')
        transport = httpx.MockTransport(fake.handler)
        real = httpx.AsyncClient
        factory = lambda *a, **k: real(transport=transport, base_url=k.get('base_url', engine.endpoint))
        self.stack.enter_context(patch('olive.services.media_comfy.httpx.AsyncClient', side_effect=factory))
        self.stack.enter_context(patch.object(LocalComfyRuntime, 'ready', new=AsyncMock(return_value=True)))
        self.stack.enter_context(patch('olive.services.media_engines.port_bound', return_value=True))
        return engine

    def preset(self, key):
        self.s.chat.update(self.chat_id, preset=key)

    async def test_text_to_image_persists_artifact_without_paths_and_reloads(self):
        fake = FakeComfy(wf.IMAGE_WORKFLOWS, png())
        self.engine('image', fake)
        self.preset('reimagine')
        result = await self.s.chat.send(self.chat_id, 'Generate a cinematic image of Cape Town at night.')
        message = result['messages'][-1]
        self.assertEqual(message['role'], 'assistant')
        self.assertEqual(message['provider'], {'runtime': 'OLIVE Media', 'preset': 'reimagine', 'media_kind': 'image',
                                               'tier': 'IMAGE', 'family': 'FLUX.2 Klein'})
        artifact = message['artifacts'][0]
        self.assertEqual((artifact['kind'], artifact['mime_type'], artifact['available']), ('image', 'image/png', True))
        self.assertEqual(artifact['generator']['workflow'], 'flux2-klein-9b')
        self.assertEqual(artifact['parameters']['prompt'], 'Generate a cinematic image of Cape Town at night.')
        self.assertEqual((artifact['width'], artifact['height']), (64, 48))
        # One engine, one workflow, the user's exact words, no hosted call.
        self.assertEqual(len(fake.prompts), 1)
        graph = next(iter(fake.prompts.values()))['prompt']
        self.assertEqual(graph['positive']['inputs']['text'], 'Generate a cinematic image of Cape Town at night.')
        self.s.ollama.chat_stream.assert_not_called()
        # Paths stay internal: not in the Chat snapshot nor in the persisted chat.
        profile = str(self.root)
        self.assertNotIn(profile, json.dumps(result))
        self.s.save_chats()
        stored = (self.root / 'profile' / 'chats.json').read_text()
        self.assertNotIn(profile, stored)
        self.assertIn(artifact['id'], stored)
        # A restarted runtime reopens the same Chat with its artifact metadata.
        async def deny(_): return ConfirmationResponse(False)
        reopened = ServiceContainer(lambda *a: None, deny, self.root / 'profile', migrate=False)
        try:
            again = reopened.chat.get(self.chat_id)
            self.assertEqual(again['preset'], 'reimagine')
            self.assertEqual(again['messages'][-1]['artifacts'][0]['id'], artifact['id'])
            self.assertTrue(again['messages'][-1]['artifacts'][0]['available'])
        finally:
            await reopened.shutdown()
        file = self.s.media.artifact_file(artifact['id'])
        self.assertEqual(hashlib.sha256(Path(file['path']).read_bytes()).hexdigest(), artifact['sha256'])
        self.assertTrue(fake.vram == 0 and ('POST', '/free') in fake.calls, 'engine released after generation')

    async def test_image_attachment_is_an_edit_reference_and_original_is_preserved(self):
        fake = FakeComfy(wf.IMAGE_WORKFLOWS, png('green'))
        self.engine('image', fake)
        self.preset('reimagine')
        source = self.root / 'photo.png'
        source.write_bytes(png('red'))
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        await self.s.knowledge.attach(self.chat_id, [str(source)])
        result = await self.s.chat.send(self.chat_id, 'Make the sky darker and remove the person in the background.')
        artifact = result['messages'][-1]['artifacts'][0]
        self.assertEqual(artifact['parameters']['operation'], 'edit')
        self.assertEqual(result['messages'][-1]['content'], 'Image edited from your attachment.')
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        original = next(r for r in self.s.media.records()['artifacts'] if r['id'] == artifact['source_ids'][0])
        self.assertEqual((original['kind'], original['sha256']), ('original', before))
        self.assertNotEqual(artifact['sha256'], before)
        graph = next(iter(fake.prompts.values()))['prompt']
        self.assertEqual(graph['reference']['inputs']['image'], next(iter(fake.uploads)))
        self.assertEqual(graph['guider']['inputs']['positive'], ['positive_ref', 0])
        self.assertEqual(result['images'], [])  # The reference is consumed by the request.
        # Reuse a generated image as the next reference.
        reused = self.s.media.reuse(self.chat_id, artifact['id'])
        self.assertEqual(len(reused['images']), 1)

    async def test_attachment_validation(self):
        fake = FakeComfy(wf.IMAGE_WORKFLOWS, png())
        self.engine('image', fake)
        self.preset('reimagine')
        self.s.chat.images[self.chat_id] = [('a.gif', base64.b64encode(b'GIF89a-not-supported').decode())]
        with self.assertRaisesRegex(ValueError, 'PNG, JPEG, WebP or BMP'):
            await self.s.chat.send(self.chat_id, 'Turn this into an oil painting.')
        data = base64.b64encode(png()).decode()
        self.s.chat.images[self.chat_id] = [('a.png', data), ('b.png', data)]
        with self.assertRaisesRegex(ValueError, 'one reference image'):
            await self.s.chat.send(self.chat_id, 'Combine these')
        self.assertEqual(fake.prompts, {})
        self.preset('video')
        self.engine('video', FakeComfy(wf.VIDEO_WORKFLOWS, mp4()))
        self.s.chat.images[self.chat_id] = [('a.png', data)]
        # A computer without the validated image-to-video workflow refuses truthfully.
        with self.assertRaisesRegex(ValueError, 'supports text prompts only'):
            await self.s.chat.send(self.chat_id, 'Animate this scene with slow camera movement.')

    async def test_missing_engine_start_failure_and_remote_target(self):
        self.preset('reimagine')
        with self.assertRaises(MediaError) as caught:
            await self.s.chat.send(self.chat_id, 'An olive')
        self.assertEqual(public_error(caught.exception)['code'], 'Media_image_not_configured')
        engine = self.s.chat_media.engines.image
        engine.runtime.root, engine.runtime.python = str(self.root), str(self.root / 'python')
        (self.root / 'main.py').write_text('')
        (self.root / 'python').write_text('')
        with patch.object(LocalComfyRuntime, 'ready', new=AsyncMock(return_value=False)), \
             patch.object(LocalComfyRuntime, 'start_for', new=AsyncMock(side_effect=RuntimeError('exited during startup'))):
            with self.assertRaisesRegex(ValueError, 'could not start'):
                await self.s.chat.send(self.chat_id, 'An olive')
        self.assertEqual(engine.status()['state'], 'failed')
        self.s.chat.targets[self.chat_id] = '00000000-0000-4000-8000-000000000000'
        with self.assertRaisesRegex(ValueError, 'This device only'):
            await self.s.chat.send(self.chat_id, 'An olive')
        self.assertFalse(any(m.role == 'assistant' for m in self.s.chats[self.chat_id].messages))

    async def test_stop_during_generation_interrupts_own_prompt_and_frees_everything(self):
        fake = FakeComfy(wf.IMAGE_WORKFLOWS, png(), finish_after=10_000)
        engine = self.engine('image', fake)
        self.preset('reimagine')
        task = asyncio.create_task(self.s.chat.send(self.chat_id, 'A lighthouse'))
        for _ in range(200):
            await asyncio.sleep(.01)
            if fake.running:
                break
        self.s.chat.stop(self.chat_id)
        result = await task
        last = result['messages'][-1]
        self.assertEqual((last['completion_state'], last['artifacts']), ('incomplete', []))
        self.assertIn('Generation stopped', last['content'])
        self.assertEqual(fake.interrupted, list(fake.prompts))
        self.assertFalse(self.s.ollama.residency.lock.locked())
        self.assertIsNone(self.s.ollama.residency.active)
        self.assertFalse(engine.active)
        self.assertEqual(self.s.media.records()['artifacts'], [])
        self.assertEqual(result['media_progress'], '')

    async def test_gpu_handoff_text_media_text(self):
        fake = FakeComfy(wf.IMAGE_WORKFLOWS, png())
        self.engine('image', fake)
        residency = self.s.ollama.residency
        residency.current = 'gpt-oss:20b'
        self.preset('reimagine')
        await self.s.chat.send(self.chat_id, 'An olive')
        self.s.ollama.unload_model.assert_awaited_with('gpt-oss:20b')
        self.assertIsNone(residency.current)
        # Text can reacquire the GPU: the guard verifies the engine is released.
        async with residency.lease('gpt-oss:20b'):
            self.assertEqual(residency.current, 'gpt-oss:20b')
        # Another client's model is never evicted.
        self.s.ollama.loaded_models = AsyncMock(return_value=[{'name': 'someone-else:7b', 'size': 1, 'size_vram': 1}])
        with self.assertRaises(MediaError) as caught:
            await self.s.chat.send(self.chat_id, 'Another olive')
        self.assertEqual(caught.exception.code, 'gpu_busy')
        # An OLIVE model left resident from before a restart is OLIVE's to unload.
        loaded = [[{'name': 'gpt-oss:20b', 'size': 1, 'size_vram': 1}], []]
        self.s.ollama.loaded_models = AsyncMock(side_effect=lambda: loaded.pop(0) if loaded else [])
        self.s.ollama.unload_model.reset_mock()
        with patch('olive.services.chat_media_service.asyncio.sleep', new_callable=AsyncMock):
            await self.s.chat.send(self.chat_id, 'Third olive')
        self.s.ollama.unload_model.assert_awaited_with('gpt-oss:20b')

    async def test_image_then_video_releases_the_other_engine(self):
        image_fake, video_fake = FakeComfy(wf.IMAGE_WORKFLOWS, png()), FakeComfy(wf.VIDEO_WORKFLOWS, mp4())
        image = self.s.chat_media.engines.image
        video = self.s.chat_media.engines.video
        for engine in (image, video):
            engine.runtime.root, engine.runtime.python = str(self.root), str(self.root / 'python')
        (self.root / 'main.py').write_text('')
        (self.root / 'python').write_text('')
        real = httpx.AsyncClient
        def factory(*a, **k):
            fake = image_fake if k['base_url'].endswith(':8188') else video_fake
            return real(transport=httpx.MockTransport(fake.handler), base_url=k['base_url'])
        self.stack.enter_context(patch('olive.services.media_comfy.httpx.AsyncClient', side_effect=factory))
        self.stack.enter_context(patch.object(LocalComfyRuntime, 'ready', new=AsyncMock(return_value=True)))
        self.stack.enter_context(patch('olive.services.media_engines.port_bound', return_value=True))
        self.preset('reimagine')
        await self.s.chat.send(self.chat_id, 'An olive')
        image_fake.calls.clear()
        self.preset('video')
        result = await self.s.chat.send(self.chat_id, 'Generate a cinematic video of a futuristic city in the rain.')
        self.assertIn(('POST', '/free'), image_fake.calls)  # Image engine verified idle before video.
        artifact = result['messages'][-1]['artifacts'][0]
        self.assertEqual((artifact['kind'], artifact['mime_type']), ('video', 'video/mp4'))
        self.assertEqual(result['messages'][-1]['provider']['tier'], 'LTX')
        graph = next(iter(video_fake.prompts.values()))['prompt']
        conditioning = graph['conditioning']['inputs']
        self.assertEqual((conditioning['width'], conditioning['height'], conditioning['length'], conditioning['frame_rate']), (768, 448, 49, 24.0))
        self.assertEqual(graph['sample']['inputs']['steps'], 8)
        self.assertEqual(graph['sample']['inputs']['schedule'], 'distilled (8 steps)')
        self.assertIn('audio', graph['video']['inputs'])  # Synchronized audio is kept.
        video_fake.calls.clear()
        self.preset('reimagine')
        await self.s.chat.send(self.chat_id, 'Back to images')
        self.assertIn(('POST', '/free'), video_fake.calls)

    async def test_generation_failure_and_no_output_are_specific(self):
        fake = FakeComfy(wf.IMAGE_WORKFLOWS, png(), fail=True)
        self.engine('image', fake)
        self.preset('reimagine')
        with self.assertRaises(MediaError) as caught:
            await self.s.chat.send(self.chat_id, 'An olive')
        self.assertEqual(caught.exception.code, 'generation_failed')
        self.assertNotIn('Traceback', str(caught.exception))
        fake.fail, fake.output = False, b'not an image'
        with self.assertRaises(MediaError) as caught:
            await self.s.chat.send(self.chat_id, 'An olive')
        self.assertEqual(caught.exception.code, 'no_artifact')
        self.assertEqual(self.s.media.records()['artifacts'], [])

    async def test_missing_model_or_workflow_is_reported_not_substituted(self):
        fake = FakeComfy((wf.QWEN,), png())  # Only a blocked workflow is installed.
        self.engine('image', fake)
        self.preset('reimagine')
        with self.assertRaises(MediaError) as caught:
            await self.s.chat.send(self.chat_id, 'An olive')
        self.assertEqual(caught.exception.code, 'model_missing')
        self.assertEqual(fake.prompts, {})
        video = FakeComfy(wf.VIDEO_WORKFLOWS, mp4())
        self.engine('video', video)
        with patch('olive.services.media_workflows.availability', return_value='workflow node unavailable: LTXV23ModelsLoader'):
            self.preset('video')
            with self.assertRaises(MediaError) as caught:
                await self.s.chat.send(self.chat_id, 'A city')
        self.assertEqual(caught.exception.code, 'workflow_missing')

    async def test_missing_artifact_file_is_truthful(self):
        self.engine('image', FakeComfy(wf.IMAGE_WORKFLOWS, png()))
        self.preset('reimagine')
        result = await self.s.chat.send(self.chat_id, 'An olive')
        artifact = result['messages'][-1]['artifacts'][0]
        Path(self.s.media.artifact_file(artifact['id'])['path']).unlink()
        self.assertFalse(self.s.chat.get(self.chat_id)['messages'][-1]['artifacts'][0]['available'])
        with self.assertRaisesRegex(ValueError, 'no longer available'):
            self.s.media.artifact_file(artifact['id'])
        for bad in ('../../etc/passwd', 'x' * 32, artifact['id'].upper()):
            with self.assertRaises(MediaError):
                self.s.media.artifact_file(bad)

    async def test_media_modes_never_regenerate_or_warm(self):
        self.preset('video')
        self.assertEqual(await self.s.chat.warm(self.chat_id), {'warmed': False})
        self.s.chats[self.chat_id].add_message('user', 'x')
        self.s.chats[self.chat_id].add_message('assistant', 'y')
        self.engine('video', FakeComfy(wf.VIDEO_WORKFLOWS, mp4()))
        with self.assertRaisesRegex(ValueError, 'Regeneration of media is not supported'):
            await self.s.chat.send(self.chat_id, regenerate=True)


class AudioTests(ChatMediaTests.__base__):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        async def deny(_): return ConfirmationResponse(False)
        self.s = ServiceContainer(lambda *a: None, deny, Path(self.temp.name), migrate=False)
        self.chat_id = self.s.current_chat_id
        self.s.chat.update(self.chat_id, preset='audio')
        self.s.ollama.loaded_models = AsyncMock(return_value=[])
        self.installed = True
        self.paths = []
        self.hold = None
        async def handler(request):
            self.paths.append((request.method, request.url.path))
            path = request.url.path
            if path == '/health':
                return httpx.Response(200, json={'status': 'ok', 'version': '0.5.6'})
            if path == '/engines/tts':
                return httpx.Response(200, json={'active': 'omnivoice', 'active_model': 'k2-fsa/OmniVoice',
                                                 'backends': [{'id': 'omnivoice', 'display_name': 'VoiceStudio', 'available': True}]})
            if path == '/models':
                return httpx.Response(200, json={'models': [{'repo_id': 'k2-fsa/OmniVoice', 'installed': self.installed, 'incomplete': False}]})
            if path == '/profiles':
                return httpx.Response(200, json=[{'id': 'demo0001', 'name': 'Demo Voice', 'ref_audio_path': '/secret/demo.wav'}])
            if path == '/v1/audio/speech':
                if self.hold:
                    await self.hold.wait()
                self.body = json.loads(request.content)
                return httpx.Response(200, content=wav(), headers={'content-type': 'audio/wav'})
            if path == '/model/unload/tts':
                return httpx.Response(200, json={})
            return httpx.Response(404)
        real = httpx.AsyncClient
        self.patch = patch('olive.services.voicestudio.httpx.AsyncClient',
                           side_effect=lambda *a, **k: real(transport=httpx.MockTransport(handler), base_url=k['base_url']))
        self.patch.start()
        self.scope = 'loopback'
        self.scope_patch = patch('olive.services.voicestudio.listener_scope', side_effect=lambda port: self.scope)
        self.scope_patch.start()
        self.s.chat_media.voice = VoiceStudio('http://127.0.0.1:3900')

    async def asyncTearDown(self):
        self.patch.stop()
        self.scope_patch.stop()
        await self.s.shutdown()
        self.temp.cleanup()

    def test_speech_text_parsing(self):
        self.assertEqual(speech_request('Say: Welcome to OLIVE.'), ('Welcome to OLIVE.', ''))
        self.assertEqual(speech_request('Create a calm voiceover saying: Hello there, friend.'), ('Hello there, friend.', 'calm'))
        self.assertEqual(speech_request('Create a calm voice saying "Welcome to OLIVE."'), ('Welcome to OLIVE.', 'calm'))
        self.assertEqual(speech_request('Welcome to OLIVE'), ('Welcome to OLIVE', ''))
        with self.assertRaisesRegex(MediaError, 'Say what OLIVE should speak'):
            speech_request('Create a podcast about space')

    async def test_text_to_speech_artifact_and_release(self):
        result = await self.s.chat.send(self.chat_id, 'Create a calm voice saying: Welcome to OLIVE.')
        message = result['messages'][-1]
        artifact = message['artifacts'][0]
        self.assertEqual((artifact['kind'], artifact['mime_type'], artifact['duration_seconds']), ('audio', 'audio/wav', 0.5))
        self.assertEqual(message['provider']['tier'], 'SPEECH')
        self.assertEqual(self.body, {'model': 'omnivoice', 'input': 'Welcome to OLIVE.', 'voice': 'default',
                                     'response_format': 'wav', 'instructions': 'calm'})
        self.assertIn(('POST', '/model/unload/tts'), self.paths)
        # Only the documented synthesis/status API; never install/download routes.
        self.assertTrue({p for _, p in self.paths} <= {'/health', '/engines/tts', '/models', '/v1/audio/speech', '/model/unload/tts'})
        self.assertNotIn(self.temp.name, json.dumps(result))

    async def test_missing_voice_model_is_needs_setup_and_never_downloads(self):
        self.installed = False
        with self.assertRaises(MediaError) as caught:
            await self.s.chat.send(self.chat_id, 'Say: Welcome to OLIVE.')
        self.assertEqual(caught.exception.code, 'audio_model_missing')
        self.assertNotIn(('POST', '/v1/audio/speech'), self.paths)
        await self.s.chat_media.refresh()
        preset = next(p for p in self.s.presets.list() if p['id'] == 'audio')
        self.assertEqual((preset['available'], preset['status']), (False, 'Needs setup · no voice model installed'))
        self.assertEqual(preset['capabilities'], [])

    async def test_voice_enumeration_lists_only_service_voices_without_paths(self):
        voices = await self.s.chat_media.voices()
        self.assertEqual(voices['voices'], [{'id': 'default', 'name': 'VoiceStudio default'}, {'id': 'demo0001', 'name': 'Demo Voice'}])
        self.assertEqual((await self.s.chat_media.select_voice('demo0001'))['selected'], 'demo0001')
        with self.assertRaises(ValueError):
            await self.s.chat_media.select_voice('invented-voice')

    async def test_stop_prevents_stale_audio_attachment(self):
        self.hold = asyncio.Event()
        task = asyncio.create_task(self.s.chat.send(self.chat_id, 'Say: Welcome to OLIVE.'))
        for _ in range(200):
            await asyncio.sleep(.01)
            if ('POST', '/v1/audio/speech') in self.paths:
                break
        self.s.chat.stop(self.chat_id)
        result = await task
        self.assertEqual(result['messages'][-1]['completion_state'], 'incomplete')
        self.assertEqual(result['messages'][-1]['artifacts'], [])
        self.assertEqual(self.s.media.records()['artifacts'], [])
        self.assertFalse(self.s.ollama.residency.lock.locked())

    async def test_network_exposed_or_unverified_service_is_never_sent_text(self):
        for scope, code, label in [('network', 'audio_exposed', 'exposed on the network'),
                                   ('unknown', 'audio_unverified', 'cannot verify')]:
            self.scope = scope
            self.paths.clear()
            with self.assertRaises(MediaError) as caught:
                await self.s.chat.send(self.chat_id, 'Say: Welcome to OLIVE.')
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn(('POST', '/v1/audio/speech'), self.paths)
            preset = next(p for p in self.s.presets.list() if p['id'] == 'audio')
            self.assertFalse(preset['available'])
            self.assertIn(label, preset['status'])

    async def test_unsupported_or_empty_audio_requests_fail_safely(self):
        for text, code in [('Sing happy birthday', 'audio_unsupported'), ('Create a song about olives', 'audio_unsupported'),
                           ('Make background music', 'audio_unsupported'), ('Clone my voice and say hi', 'audio_unsupported'),
                           ('Create a podcast about space', 'speech_text_required'), ('Say:', 'speech_text_required'),
                           ('   ', 'prompt_required')]:
            with self.assertRaises(ValueError) as caught:
                await self.s.chat.send(self.chat_id, text)
            self.assertEqual(getattr(caught.exception, 'code', 'plain'), code, text)
        self.assertNotIn(('POST', '/v1/audio/speech'), self.paths)
        # Words to speak may mention music; only the instruction is checked.
        result = await self.s.chat.send(self.chat_id, 'Say: I love music.')
        self.assertEqual(result['messages'][-1]['artifacts'][0]['parameters']['text'], 'I love music.')

    async def test_stopped_service_is_started_loopback_only_on_request(self):
        voice = self.s.chat_media.voice
        voice.runtime.root = self.temp.name
        Path(self.temp.name, 'backend').mkdir()
        Path(self.temp.name, 'backend', 'main.py').write_text('')
        Path(self.temp.name, '.venv', 'bin').mkdir(parents=True)
        Path(voice.runtime.python).write_text('')
        real = voice.status
        calls = []
        async def status():
            if not calls:
                calls.append('first')
                voice.last = {'state': 'stopped'}
                return voice.last
            return await real()
        voice.status = status
        with patch.object(type(voice.runtime), 'start', new_callable=AsyncMock) as start:
            result = await self.s.chat.send(self.chat_id, 'Say: Welcome to OLIVE.')
        start.assert_awaited_once()
        self.assertEqual(result['messages'][-1]['artifacts'][0]['kind'], 'audio')

    async def test_managed_launch_is_loopback_offline_and_never_uv_run(self):
        from olive.services.voicestudio import LocalVoiceStudioRuntime
        runtime = LocalVoiceStudioRuntime('http://127.0.0.1:3900', self.temp.name)
        Path(self.temp.name, 'backend').mkdir(exist_ok=True)
        Path(self.temp.name, 'backend', 'main.py').write_text('')
        Path(self.temp.name, '.venv', 'bin').mkdir(parents=True, exist_ok=True)
        Path(runtime.python).write_text('')
        with patch('olive.services.gpu_probe.port_bound', return_value=False), \
             patch('olive.studio_tooling.posix_process.start_owned_process', new_callable=AsyncMock) as start, \
             patch('psutil.Process'), patch.object(LocalVoiceStudioRuntime, 'healthy', new=AsyncMock(return_value=True)):
            start.return_value.returncode = None
            await runtime.start()
        args, kwargs = start.await_args
        self.assertEqual(args[0][args[0].index('--host') + 1], '127.0.0.1')
        self.assertNotIn('uv', args[0])
        self.assertEqual((kwargs['env']['HF_HUB_OFFLINE'], kwargs['env']['TRANSFORMERS_OFFLINE']), ('1', '1'))
        with patch('olive.services.gpu_probe.port_bound', return_value=True), \
             patch('olive.studio_tooling.posix_process.start_owned_process', new_callable=AsyncMock) as again:
            await runtime.start()  # A running service is never replaced.
        again.assert_not_awaited()

    def test_only_loopback_services(self):
        for url in ('http://example.com:3900', 'https://127.0.0.1:3900', 'http://10.0.0.2:3900', 'http://u:p@127.0.0.1:3900'):
            with self.assertRaises(ValueError):
                loopback(url)
        self.assertEqual(loopback('http://127.0.0.1:3900/'), 'http://127.0.0.1:3900')


class WorkflowAndRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def inventory(self, workflows, version='0.35.0'):
        return wf.engine_inventory(version, object_info(workflows), wf.IMAGE_WORKFLOWS + wf.VIDEO_WORKFLOWS)

    def test_routing_is_deterministic_single_and_validated(self):
        engine = self.inventory(wf.IMAGE_WORKFLOWS)
        # Qwen-Image 2.1 is installed but blocked on ComfyUI 0.35.0; Klein serves both.
        for prompt, refs, expected, shape in [
            ('A cinematic city', [], 'flux2-klein-9b', 'generate'),
            ('Make the sky darker', [('a', b'')], 'flux2-klein-9b', 'edit'),
            ('A poster that says "OLIVE"', [], 'flux2-klein-9b', 'text'),
        ]:
            workflow, got_shape, reasons = wf.route('image', prompt, refs, engine)
            self.assertEqual((workflow.key, got_shape), (expected, shape))
            if shape != 'generate':
                self.assertIn('cannot load', reasons['qwen-image-2.1'])
        with patch.object(wf, 'QWEN', wf.QWEN), patch.dict(wf.WORKFLOWS, {'qwen-image-2.1': wf.Workflow(
                **{**wf.QWEN.__dict__, 'validated': frozenset({'0.35.0'}), 'blocked': ''})}):
            self.assertEqual(wf.route('image', 'Remove the background', [('a', b'')], engine)[0].key, 'qwen-image-2.1')
            self.assertEqual(wf.route('image', 'A poster that says "OLIVE"', [], engine)[0].key, 'qwen-image-2.1')
            self.assertEqual(wf.route('image', 'A cinematic city', [], engine)[0].key, 'flux2-klein-9b')
        # SDXL is compatibility only: never an editor, and only when nothing newer is ready.
        sdxl_only = self.inventory((wf.SDXL,))
        self.assertEqual(wf.route('image', 'A city', [], sdxl_only)[0].key, 'sdxl-base')
        self.assertIsNone(wf.route('image', 'Edit this', [('a', b'')], sdxl_only)[0])
        self.assertIsNone(wf.route('image', 'A city', [], self.inventory(wf.IMAGE_WORKFLOWS, '0.36.0'))[0])
        self.assertEqual(wf.route('video', 'A city', [], self.inventory(wf.VIDEO_WORKFLOWS))[0].key, 'ltx-2.3-t2av')

    def test_custom_nodes_must_come_from_the_reviewed_module(self):
        info = object_info(wf.VIDEO_WORKFLOWS, {'LTXV23ModelsLoader': 'custom_nodes.SomethingElse'})
        engine = wf.engine_inventory('0.35.0', info, wf.VIDEO_WORKFLOWS)
        self.assertEqual(wf.availability(wf.LTX, engine), 'workflow node unavailable: LTXV23ModelsLoader')
        self.assertEqual(wf.combo_options(['COMBO', {'options': ['a', 'b']}]), ('a', 'b'))
        self.assertEqual(wf.combo_options([['x']]), ('x',))
        self.assertEqual(wf.ltx_frames(50), 49)
        self.assertEqual(wf.ltx_frames(1000), 97)

    def test_image_and_video_runtimes_are_separate_and_video_keeps_the_gguf_loader(self):
        from olive.services.media_engines import MediaEngines
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {
                'OLIVE_COMFY_ROOT': '/opt/image', 'OLIVE_COMFY_PYTHON': '/opt/image/python',
                'OLIVE_VIDEO_COMFY_ROOT': '/opt/video', 'OLIVE_VIDEO_COMFY_PYTHON': '/opt/video/python',
                'OLIVE_MEDIA_MODELS': '/opt/models'}):
            engines = MediaEngines(directory)
            image, video = engines.image.runtime.arguments(), engines.video.runtime.arguments()
            self.assertEqual((engines.image.runtime.port, engines.video.runtime.port), (8188, 8190))
            for args in (image, video):
                self.assertEqual(args[args.index('--listen') + 1], '127.0.0.1')
                self.assertIn('--disable-api-nodes', args)
            self.assertIn('--whitelist-custom-nodes', video)
            self.assertEqual(video[video.index('--whitelist-custom-nodes') + 1], 'ComfyUI-GGUF-Loader')
            self.assertNotIn('--whitelist-custom-nodes', image)
            self.assertIn('--disable-dynamic-vram', image)
            config = Path(image[image.index('--extra-model-paths-config') + 1]).read_text()
            self.assertIn('flux2/split_files/vae', config)
            self.assertNotIn('--extra-model-paths-config', video)

    async def test_externally_started_engine_is_reused_and_never_stopped(self):
        runtime = LocalComfyRuntime('http://127.0.0.1:8190', '/opt/video', '/opt/video/python')
        with patch('olive.services.local_comfy_runtime.sys.platform', 'linux'), \
             patch.object(LocalComfyRuntime, 'ready', new=AsyncMock(return_value=True)), \
             patch('olive.studio_tooling.posix_process.start_owned_process', new_callable=AsyncMock) as start:
            await runtime.start_for('http://127.0.0.1:8190')
            start.assert_not_awaited()
        self.assertFalse(runtime.owned())
        await runtime.close()  # No owned process: nothing is signalled.

    async def test_unmeasured_allocator_release_uses_process_memory_evidence(self):
        client = ComfyWorkflows('http://127.0.0.1:8190')
        stats = {'system': {'argv': ['main.py']}, 'devices': [{'type': 'cuda', 'name': 'x : cudaMallocAsync', 'torch_vram_total': 134217728}]}
        with patch('olive.services.gpu_probe.listening_pid', return_value=4242), \
             patch('olive.services.gpu_probe.process_gpu_mib', new=AsyncMock(return_value=394)):
            self.assertTrue(await client.released(stats))
        with patch('olive.services.gpu_probe.listening_pid', return_value=4242), \
             patch('olive.services.gpu_probe.process_gpu_mib', new=AsyncMock(return_value=12000)):
            self.assertFalse(await client.released(stats))
        with patch('olive.services.gpu_probe.listening_pid', return_value=None), \
             patch('olive.services.gpu_probe.process_gpu_mib', new=AsyncMock(return_value=None)):
            with self.assertRaisesRegex(RuntimeError, 'cannot be observed'):
                await client.released(stats)

    def test_persisted_artifacts_migrate_and_drop_untrusted_fields(self):
        legacy = Message.from_dict({'role': 'assistant', 'content': 'old answer'})
        self.assertEqual(legacy.artifacts, [])
        self.assertIsNone(clean_artifact({'id': 'x', 'kind': 'executable'}))
        clean = clean_artifact({'id': 'x', 'kind': 'image', 'path': '/home/me/secret.png', 'filename': 'a.png'})
        self.assertEqual(clean, {'id': 'x', 'kind': 'image', 'filename': 'a.png'})
        chat = Chat.from_dict({'preset': 'video', 'messages': [{'role': 'assistant', 'content': 'Video generated',
                                                                'artifacts': [{'id': 'v', 'kind': 'video'}]}]})
        self.assertEqual((chat.preset, chat.messages[0].artifacts[0]['kind']), ('video', 'video'))
        self.assertEqual(Chat.from_dict(chat.to_dict()).messages[0].artifacts, chat.messages[0].artifacts)
        self.assertEqual(Chat.from_dict({'preset': 'audio'}).preset, 'audio')

    def test_public_errors_are_specific(self):
        codes = {public_error(MediaError(code))['message'] for code in MediaError.MESSAGES}
        self.assertEqual(len(codes), len(MediaError.MESSAGES))
        self.assertNotIn('The request could not complete.', codes)
        error = MediaError('engine_start_failed', '/home/me/.local/share/olive/runtime traceback')
        self.assertNotIn('/home', public_error(error)['message'])


if __name__ == '__main__':
    unittest.main()
