"""Long-form OLIVE VIDEO through the real ChatMediaService pipeline.

A fake ComfyUI (HTTP only) returns real H.264/AAC segments made by FFmpeg, so
planning, continuation wiring, stitching, trimming, verification, publishing,
cancellation and cleanup all run for real. No model, no GPU.
"""
import asyncio
import base64
import hashlib
import json
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from olive.agent.confirmation_service import ConfirmationResponse
from olive.application.service_container import ServiceContainer
from olive.services import media_workflows as wf
from olive.services import video_assembly as assembly
from olive.services.local_comfy_runtime import LocalComfyRuntime
from olive.services.media_errors import MediaError
from olive.services.remote_chat_runtime import RemoteChatRuntime
from tests.test_chat_media import FakeComfy, mp4, png

TOOLS = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))


class RecordingComfy(FakeComfy):
    """Keeps every queued graph and upload; optionally reacts when a prompt is queued."""

    def __init__(self, *args, on_prompt=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.graphs, self.on_prompt = [], on_prompt

    def handler(self, request):
        if request.url.path == '/prompt':
            self.graphs.append(json.loads(request.content)['prompt'])
            if self.on_prompt:
                self.on_prompt(len(self.graphs))
        return super().handler(request)


@unittest.skipUnless(TOOLS, 'FFmpeg/ffprobe are not installed on this computer')
class LongVideoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        async def deny(_): return ConfirmationResponse(False)
        self.s = ServiceContainer(lambda *a: None, deny, self.root / 'profile', migrate=False)
        self.chat_id = self.s.current_chat_id
        self.s.ollama.chat_stream = AsyncMock(side_effect=AssertionError('text inference used'))
        self.s.ollama.loaded_models = AsyncMock(return_value=[])
        self.s.ollama.unload_model = AsyncMock()
        self.stack = ExitStack()
        self.s.chat.update(self.chat_id, preset='video')

    async def asyncTearDown(self):
        self.stack.close()
        await self.s.shutdown()
        self.temp.cleanup()

    def engine(self, fake, *, i2v=True):
        engine = self.s.chat_media.engines.video
        engine.runtime.root, engine.runtime.python = str(self.root / 'video'), str(self.root / 'python')
        (self.root / 'video').mkdir(exist_ok=True)
        (self.root / 'video' / 'main.py').write_text('')
        (self.root / 'python').write_text('')
        transport = httpx.MockTransport(fake.handler)
        real = httpx.AsyncClient
        factory = lambda *a, **k: real(transport=transport, base_url=k.get('base_url', engine.endpoint))
        self.stack.enter_context(patch('olive.services.media_comfy.httpx.AsyncClient', side_effect=factory))
        self.stack.enter_context(patch.object(LocalComfyRuntime, 'ready', new=AsyncMock(return_value=True)))
        self.stack.enter_context(patch('olive.services.media_engines.port_bound', return_value=True))
        # Planning reads installed files; mark the validated workflows installed (or only T2V).
        states = {'ltx-2.3-t2av': 'ready', 'ltx-2.3-i2av': 'ready' if i2v else 'model missing: test'}
        self.stack.enter_context(patch.object(type(engine), 'workflow_states', lambda self, inventory=None: dict(states)))
        return engine

    def records(self):
        return self.s.media.records()['artifacts']

    def jobs(self):
        folder = Path(self.s.media.root) / 'jobs'
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    async def test_long_text_to_video_continues_from_each_last_frame_and_is_exact(self):
        fake = RecordingComfy(wf.VIDEO_WORKFLOWS, mp4())
        self.engine(fake)
        stages = []
        request = self.s.chat_media.plan(self.s.chats[self.chat_id], 'Generate a 5 second calm scene of clouds moving over mountains.', [])
        _, artifact = await self.s.chat_media.generate(self.chat_id, request, asyncio.Event(),
                                                        on_progress=lambda text, detail=None: stages.append((text, detail)))
        self.assertEqual(len(fake.graphs), 3, 'three bounded native segments, not one giant latent')
        self.assertNotIn('reference', fake.graphs[0])
        for graph in fake.graphs:
            self.assertEqual(graph['conditioning']['inputs']['length'], 49)
            self.assertEqual(graph['conditioning']['inputs']['prompt'], 'Generate a calm scene of clouds moving over mountains.')
        # Segment N+1 is conditioned on the exact PNG of segment N's last frame.
        for index, graph in enumerate(fake.graphs[1:], start=1):
            name = graph['reference']['inputs']['image']
            self.assertEqual(graph['conditioning']['inputs']['image'], ['reference', 0])
            self.assertTrue(name.endswith(f'-c{index:03d}.png'))
            self.assertTrue(fake.uploads[name])
        seeds = [g['sample']['inputs']['seed'] for g in fake.graphs]
        self.assertEqual(len(set(seeds)), 3, 'each segment has its own seed')
        self.assertEqual((artifact['target_duration_seconds'], artifact['duration_seconds']), (5.0, 5.0))
        self.assertEqual((artifact['segment_count'], artifact['generation_mode'], artifact['continuation']), (3, 'text_to_video', 'last_frame'))
        self.assertTrue(artifact['has_audio'])
        self.assertEqual(artifact['parameters']['prompt'], 'Generate a 5 second calm scene of clouds moving over mountains.')
        self.assertEqual(artifact['parameters']['duration_source'], 'prompt')
        record = next(r for r in self.records() if r['id'] == artifact['id'])
        provenance = record['provenance']
        self.assertEqual([s['seed'] for s in provenance['segments']], seeds)
        for before, after in zip(provenance['segments'], provenance['segments'][1:]):
            self.assertEqual(after['conditioned_on'], before['continuation_frame']['sha256'])
            self.assertIsInstance(after['boundary_psnr_db'], float)
        self.assertEqual(provenance['ffprobe']['frames'], 120)
        self.assertNotIn(str(self.root), json.dumps(artifact), 'no filesystem path in the chat artifact')
        file = self.s.media.artifact_file(artifact['id'])
        self.assertEqual(hashlib.sha256(Path(file['path']).read_bytes()).hexdigest(), artifact['sha256'])
        texts = [t for t, _ in stages]
        for expected in ('Generating segment 1 of 3…', 'Generating segment 3 of 3…', 'Extracting continuation frame…',
                         'Stitching 3 segments…', 'Verifying output…'):
            self.assertIn(expected, texts)
        self.assertIn({'stage': 'segment', 'current': 2, 'total': 3}, [d for _, d in stages])
        self.assertEqual(self.jobs(), [], 'the job workspace is removed after publishing')
        self.assertIn(('POST', '/free'), fake.calls)

    async def test_image_to_video_uses_the_attachment_once_and_keeps_it_intact(self):
        fake = RecordingComfy(wf.VIDEO_WORKFLOWS, mp4())
        self.engine(fake)
        source = png('blue', (320, 180))
        images = [('../../etc/passwd.png', base64.b64encode(source).decode())]
        request = self.s.chat_media.plan(self.s.chats[self.chat_id], 'Animate the water and make the clouds move',
                                         images, {'target_duration_seconds': 3})
        _, artifact = await self.s.chat_media.generate(self.chat_id, request, asyncio.Event())
        first = fake.graphs[0]
        self.assertTrue(first['reference']['inputs']['image'].endswith('-reference.png'), 'OLIVE names the upload, never the peer')
        self.assertEqual(len(fake.graphs), 2)
        self.assertTrue(fake.graphs[1]['reference']['inputs']['image'].endswith('-c001.png'))
        self.assertEqual((artifact['generation_mode'], artifact['target_duration_seconds'], artifact['duration_seconds']),
                         ('image_to_video', 3.0, 3.0))
        self.assertEqual(artifact['parameters']['operation'], 'animate')
        original = next(r for r in self.records() if r['id'] == artifact['source_ids'][0])
        self.assertEqual(Path(original['path']).read_bytes(), source, 'the original attachment is preserved unchanged')
        record = next(r for r in self.records() if r['id'] == artifact['id'])
        self.assertEqual(record['provenance']['source_image_sha256'], hashlib.sha256(source).hexdigest())

    async def test_desktop_send_path_carries_the_length_and_captions_image_to_video(self):
        fake = RecordingComfy(wf.VIDEO_WORKFLOWS, mp4())
        self.engine(fake)
        self.s.chat.images[self.chat_id] = [('sky.png', base64.b64encode(png('blue', (320, 180))).decode())]
        result = await self.s.interaction.submit('Animate the clouds', self.chat_id, video_duration_seconds=3)
        message = result['messages'][-1]
        self.assertEqual(message['content'], 'Video generated from your image on this device.')
        self.assertEqual((message['artifacts'][0]['target_duration_seconds'], message['artifacts'][0]['duration_seconds']), (3.0, 3.0))
        self.assertEqual(len(fake.graphs), 2)

    async def test_explicit_length_overrides_the_prompt_and_is_recorded(self):
        fake = RecordingComfy(wf.VIDEO_WORKFLOWS, mp4())
        self.engine(fake)
        request = self.s.chat_media.plan(self.s.chats[self.chat_id], 'make a 5 second scene of rain', [], {'target_duration_seconds': 1})
        self.assertEqual((request['target_duration_seconds'], request['prompt_duration_seconds'], request['duration_conflict']), (1, 5, True))
        _, artifact = await self.s.chat_media.generate(self.chat_id, request, asyncio.Event())
        self.assertEqual(len(fake.graphs), 1)
        self.assertEqual((artifact['duration_seconds'], artifact['segment_count']), (1.0, 1), 'one segment trimmed to 24 frames')
        self.assertEqual(fake.graphs[0]['conditioning']['inputs']['prompt'], 'make a 5 second scene of rain', 'explicit: prompt kept verbatim')

    async def test_default_request_is_one_native_segment_published_directly(self):
        fake = RecordingComfy(wf.VIDEO_WORKFLOWS, mp4())
        self.engine(fake)
        request = self.s.chat_media.plan(self.s.chats[self.chat_id], 'A calm lake at sunrise', [])
        with patch.object(assembly, 'stitch', side_effect=AssertionError('no re-encode for the default')):
            _, artifact = await self.s.chat_media.generate(self.chat_id, request, asyncio.Event())
        self.assertEqual((artifact['target_duration_seconds'], artifact['segment_count']), (2.0, 1))
        self.assertAlmostEqual(artifact['duration_seconds'], 49 / 24, places=2)

    async def test_stop_during_a_segment_publishes_nothing_and_cleans_up(self):
        cancel = asyncio.Event()
        fake = RecordingComfy(wf.VIDEO_WORKFLOWS, mp4(), finish_after=10 ** 9,
                              on_prompt=lambda n: cancel.set() if n == 2 else None)
        # The first segment completes, the second never does until Stop.
        fake.finish_after = 1
        original = fake.handler
        def handler(request):
            if request.url.path.startswith('/history/') and len(fake.graphs) >= 2:
                return httpx.Response(200, json={})
            return original(request)
        fake.handler = handler
        self.engine(fake)
        before = len(self.records())
        request = self.s.chat_media.plan(self.s.chats[self.chat_id], 'a 20 second video of a lighthouse', [])
        with self.assertRaises(asyncio.CancelledError):
            await self.s.chat_media.generate(self.chat_id, request, cancel)
        self.assertEqual(len(fake.graphs), 2, 'segment 3 never starts')
        self.assertTrue(fake.interrupted, 'the running ComfyUI prompt is interrupted')
        self.assertEqual(len(self.records()), before, 'no artifact is published')
        self.assertEqual(self.jobs(), [], 'partial segments are removed')
        self.assertIn(('POST', '/free'), fake.calls, 'the engine is released')
        self.assertIsNone(self.s.ollama.residency.active)
        self.assertFalse(self.s.ollama.residency.lock.locked())

    async def assert_fails(self, code, fake, text='a 5 second video of waves', options=None, images=(), i2v=True):
        self.engine(fake, i2v=i2v)
        before = len(self.records())
        with self.assertRaises(MediaError) as caught:
            request = self.s.chat_media.plan(self.s.chats[self.chat_id], text, list(images), options)
            await self.s.chat_media.generate(self.chat_id, request, asyncio.Event())
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(len(self.records()), before, 'nothing is saved on failure')
        self.assertEqual(self.jobs(), [])
        return caught.exception

    async def test_wrong_dimensions_and_missing_audio_are_refused(self):
        await self.assert_fails('video_segment_invalid', RecordingComfy(wf.VIDEO_WORKFLOWS, mp4(size=(640, 360))))

    async def test_missing_audio_is_refused(self):
        await self.assert_fails('video_segment_invalid', RecordingComfy(wf.VIDEO_WORKFLOWS, mp4(audio=False)))

    async def test_short_segment_is_refused(self):
        await self.assert_fails('video_segment_invalid', RecordingComfy(wf.VIDEO_WORKFLOWS, mp4(frames=30)))

    async def test_invalid_segment_bytes_are_refused(self):
        bogus = b'\0\0\0\x18ftypisom' + b'\0' * 2000
        await self.assert_fails('video_verify_failed', RecordingComfy(wf.VIDEO_WORKFLOWS, bogus))

    async def test_stitch_and_probe_failures_publish_nothing(self):
        with patch.object(assembly, 'stitch', AsyncMock(side_effect=MediaError('video_assembly_failed', 'test'))):
            await self.assert_fails('video_assembly_failed', RecordingComfy(wf.VIDEO_WORKFLOWS, mp4()))

    async def test_final_probe_failure_publishes_nothing(self):
        real = assembly.probe
        async def probe(path, workspace, **kw):
            if Path(path).name == 'final.tmp.mp4':
                raise MediaError('video_verify_failed', 'ffprobe failed')
            return await real(path, workspace, **kw)
        with patch.object(assembly, 'probe', probe):
            await self.assert_fails('video_verify_failed', RecordingComfy(wf.VIDEO_WORKFLOWS, mp4()))

    async def test_limits_disk_and_missing_ffmpeg_fail_before_gpu_time(self):
        fake = RecordingComfy(wf.VIDEO_WORKFLOWS, mp4())
        self.s.settings['media_video'] = {'max_duration_seconds': 10}
        error = await self.assert_fails('video_duration_too_long', fake, 'a 20 second video')
        self.assertIn('10 s', str(error)); self.assertIn('media_video.max_duration_seconds', str(error))
        await self.assert_fails('video_duration_invalid', fake, 'x', {'target_duration_seconds': -2})
        self.s.settings.pop('media_video')
        with patch('olive.services.chat_media_service.shutil.disk_usage', return_value=type('U', (), {'free': 10})()):
            await self.assert_fails('video_storage_full', fake)
        with patch.object(assembly, 'tools', return_value=None):
            await self.assert_fails('video_assembly_unavailable', fake)
        self.assertEqual(fake.graphs, [], 'no GPU work was queued for any refused request')

    async def test_one_starting_image_and_older_engines(self):
        data = base64.b64encode(png()).decode()
        fake = RecordingComfy(wf.VIDEO_WORKFLOWS, mp4())
        await self.assert_fails('video_one_image', fake, 'animate', images=[('a.png', data), ('b.png', data)])
        self.stack.close(); self.stack = ExitStack()
        await self.assert_fails('video_image_unsupported', RecordingComfy(wf.VIDEO_WORKFLOWS, mp4()), 'animate',
                                images=[('a.png', data)], i2v=False)

    async def test_long_text_to_video_without_image_to_video_is_labelled_independent(self):
        fake = RecordingComfy(wf.VIDEO_WORKFLOWS, mp4())
        self.engine(fake, i2v=False)
        request = self.s.chat_media.plan(self.s.chats[self.chat_id], 'a 3 second video of waves', [])
        _, artifact = await self.s.chat_media.generate(self.chat_id, request, asyncio.Event())
        self.assertEqual(artifact['continuation'], 'independent', 'no continuity is claimed')
        self.assertTrue(all('reference' not in g for g in fake.graphs))
        self.assertEqual(artifact['duration_seconds'], 3.0)


class AssemblySecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_workspace_paths_are_olive_owned(self):
        workspace = assembly.JobWorkspace(self.root / 'jobs', 'a' * 32).create()
        for bad in ('..', '../x', '/etc/passwd', 'a/b', '', 'x' * 80, 'segments/../../x'):
            with self.assertRaises(ValueError):
                workspace.file(bad)
        with self.assertRaises(ValueError):
            assembly.JobWorkspace(self.root, '../../etc')
        outside = self.root / 'elsewhere.mp4'
        outside.write_bytes(b'x')
        with self.assertRaises(MediaError):
            assembly._input(outside, workspace)
        with self.assertRaises(MediaError):
            assembly._output(self.root / 'x.mp4', workspace)

    def test_ffmpeg_command_is_an_argument_list_of_owned_files(self):
        from olive.services.video_duration import plan
        workspace = assembly.JobWorkspace(self.root / 'jobs', 'b' * 32).create()
        parts = []
        for index, segment in enumerate(plan(5).segments, start=1):
            path = workspace.file('segments', f'{index:04d}.mp4')
            path.write_bytes(b'x')
            parts.append((path, segment.keep_start, segment.keep_frames))
        argv = assembly.stitch_command('ffmpeg', parts, workspace.file('final.tmp.mp4'), plan(5), workspace, audio=True)
        self.assertIsInstance(argv, list)
        inputs = [argv[i + 1] for i, value in enumerate(argv) if value == '-i']
        self.assertEqual(len(inputs), 3)
        for value in inputs:
            self.assertTrue(value.startswith('file:' + str(workspace.path)))
        self.assertEqual(argv.count('-protocol_whitelist'), 3)
        self.assertTrue(argv[-1].startswith('file:' + str(workspace.path)))
        self.assertIn('+faststart', argv)
        self.assertNotIn('http', ' '.join(argv))

    def test_sweep_removes_only_olive_job_folders(self):
        jobs = self.root / 'jobs'
        (jobs / ('c' * 32) / 'segments').mkdir(parents=True)
        (jobs / 'keep-me').mkdir()
        (jobs / 'note.txt').write_text('x')
        self.assertEqual(assembly.JobWorkspace.sweep(jobs), 1)
        self.assertEqual(sorted(p.name for p in jobs.iterdir()), ['keep-me', 'note.txt'])


class RemoteVideoCapabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        async def deny(_): return ConfirmationResponse(False)
        self.s = ServiceContainer(lambda *a: None, deny, Path(self.temp.name) / 'profile', migrate=False)

    async def asyncTearDown(self):
        await self.s.shutdown()
        self.temp.cleanup()

    async def test_phone_matrix_comes_from_the_desktop_capability(self):
        runtime = RemoteChatRuntime(self.s)
        video = {'supports_text_to_video': True, 'supports_image_to_video': True, 'supports_audio': True,
                 'native_segment_seconds': 49 / 24, 'fps': 24, 'max_images': 1, 'accepted_attachment_kinds': ['image'],
                 'continuation': 'last_frame', 'duration': {'configurable': True, 'default_seconds': 2.0, 'minimum_seconds': 0.5,
                 'maximum_seconds': 180.0, 'long_video_warning_seconds': 30.0, 'presets': [2, 5, 10, 20, 30, 60]}}
        preset = {'available': True, 'model': '', 'capabilities': ['text-to-video', 'video-audio', 'image-to-video', 'long-video']}
        with patch.object(self.s.chat_media, 'video_capability', return_value=video), \
                patch.object(RemoteChatRuntime, '_preset', lambda self, key: preset if key == 'video' else {'available': False, 'model': '', 'capabilities': []}):
            plain = next(m for m in runtime.capabilities() if m['id'] == 'video')
            self.assertNotIn('options', plain, 'phones that did not ask get the original shape')
            self.assertEqual(plain['inputs']['image']['max'], 1)
            self.assertIn('one_start_image', plain['limitations'])
            extended = next(m for m in runtime.capabilities(extended=True) if m['id'] == 'video')
            self.assertEqual(extended['options']['duration']['maximum_ms'], 180000)
            summary = runtime.summary()
            self.assertEqual([g['id'] for g in summary['groups']], ['chat', 'research', 'create'])
            self.assertEqual(summary['video'], {'image_to_video': True, 'maximum_seconds': 180.0, 'long_form': True})
            with self.assertRaises(Exception) as caught:
                runtime.validate('video', [{'kind': 'image', 'mime': 'image/png'}] * 2, [])
            self.assertEqual(str(caught.exception), 'video_one_image')
        job = type('J', (), {'mode': 'video', 'arguments': {'messages': [{'role': 'user', 'content': 'waves'}],
                                                             'options': {'target_duration_ms': 20000}}})()
        self.assertGreater(runtime.deadline(job), runtime.deadline(type('J', (), {'mode': 'video', 'arguments': {
            'messages': [{'role': 'user', 'content': 'waves'}]}})()), 'long videos get a proportionally longer bound')
        self.assertEqual(runtime.deadline(type('J', (), {'mode': 'fast', 'arguments': {}})()), 240)


if __name__ == '__main__':
    unittest.main()
