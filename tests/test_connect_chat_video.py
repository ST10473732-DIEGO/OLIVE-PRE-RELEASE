"""olive-chat/1 VIDEO duration, image-to-video and progress, over the real desktop
service with the deterministic test runtime (no model, no engine)."""
import asyncio
import hashlib
import unittest
import uuid

import tests.test_connect_chat as base
from olive.connect import chat_protocol as cp
from tests.fixtures.chat_test_runtime import png

LEGACY_MODE_KEYS = {'id', 'available', 'reason', 'inputs', 'outputs', 'citations', 'stream', 'cancel', 'prompt_required',
                    'tiers', 'voices', 'limitations'}
LEGACY_VIEW_KEYS = {'job_id', 'state', 'phase', 'text', 'offset', 'total', 'sources', 'artifacts', 'attribution', 'error'}


class Helpers:
    """The existing RemoteChatTests fixtures, without re-running its tests."""


for _name in ('asyncSetUp', 'asyncTearDown', 'policy', 'raw', 'unchecked', 'call', 'start_args', 'upload', 'finish'):
    setattr(Helpers, _name, getattr(base.RemoteChatTests, _name))


class RemoteVideoChatTests(Helpers, unittest.IsolatedAsyncioTestCase):
    def video_args(self, text='A calm synthetic scene', ms=None, source='explicit', attachments=(), job=None, options=True):
        args = self.start_args(text, mode='video', attachments=attachments, job=job)
        if options:
            args['options'] = {} if ms is None else {'target_duration_ms': ms, 'duration_source': source}
            args['input_fingerprint'] = cp.start_fingerprint(args)
        return args

    async def hostile_start(self, args):
        """A start that skips client validation but is correctly correlated (request id = job id)."""
        import time
        now = int(time.time())
        return await self.raw(cp.packet(dict(protocol_version=cp.PROTOCOL, request_id=args['job_id'],
            source_device_id=self.phone.local_id, target_device_id=self.desktop.local_id, operation='start',
            arguments=args, timestamp=now, expires_at=now + 60)))

    async def views(self, job_id):
        """Every poll view until terminal (keys included)."""
        seen = []
        async with asyncio.timeout(10):
            while True:
                value, _ = await self.call('poll', dict(job_id=job_id, after=0))
                self.assertIsNone(value['error'], value)
                seen.append(value['result'])
                if value['result']['state'] in cp.TERMINAL:
                    return seen
                await asyncio.sleep(.01)

    async def test_phones_that_do_not_ask_get_the_original_shapes(self):
        self.runtime.animate = True
        value, _ = await self.call('capabilities', {})
        result = value['result']
        self.assertEqual(set(result), {'chat_protocol', 'permission', 'modes', 'limits'})
        for mode in result['modes']:
            self.assertEqual(set(mode), LEGACY_MODE_KEYS, mode['id'])
        args = self.start_args('A calm synthetic scene', mode='video')
        await self.call('start', args)
        for view in await self.views(args['job_id']):
            self.assertEqual(set(view), LEGACY_VIEW_KEYS, 'no progress key for a phone that sent no options')

    async def test_extension_adds_video_options_and_ignores_unknown_tokens(self):
        self.runtime.animate = True
        value, _ = await self.call('capabilities', {'accept': ['mode_options/1', 'teleport/9']})
        result = value['result']
        self.assertEqual(result['extensions'], ['mode_options/1'])
        video = next(m for m in result['modes'] if m['id'] == 'video')
        self.assertEqual(video['inputs']['image']['max'], 1)
        options = video['options']
        self.assertTrue(options['supports_image_to_video'])
        self.assertEqual((options['duration']['maximum_ms'], options['native_segment_ms']), (180000, 2042))
        self.assertTrue(all(m['options'] == {} for m in result['modes'] if m['id'] != 'video'))
        value, _ = await self.unchecked('capabilities', {'accept': 'mode_options/1'})
        self.assertEqual(value['error'], 'invalid_request')
        value, _ = await self.unchecked('capabilities', {'accept': [], 'debug': True})
        self.assertEqual(value['error'], 'invalid_request')

    async def test_duration_request_runs_once_reports_segments_and_returns_the_length(self):
        self.runtime.animate = True
        args = self.video_args('Generate a 20 second cinematic scene', ms=20000, source='prompt')
        first, _ = await self.call('start', args)
        again, _ = await self.call('start', args)  # A resend after a lost acknowledgement.
        self.assertIsNone(first['error']); self.assertIsNone(again['error'])
        views = await self.views(args['job_id'])
        stages = [v['progress'] for v in views if v.get('progress')]
        self.assertTrue(stages and stages[0]['stage'] == 'segment' and stages[0]['total'] == 10, stages)
        self.assertTrue(all('progress' in v for v in views))
        self.assertIsNone(views[-1]['progress'], 'no progress once terminal')
        final = views[-1]
        self.assertEqual(final['state'], 'completed')
        self.assertEqual(final['artifacts'][0]['duration_ms'], 20000)
        self.assertEqual(len([r for r in self.runtime.runs if r[0] == args['job_id']]), 1, 'never generated twice')
        # The same job id with a different length is a changed request, not the same one.
        changed = self.video_args('Generate a 20 second cinematic scene', ms=5000, job=args['job_id'])
        value, _ = await self.call('start', changed)
        self.assertEqual(value['error'], 'changed_duplicate')

    async def test_duration_options_are_validated_before_any_receipt(self):
        self.runtime.animate = True
        for ms, code in ((0, 'video_duration_invalid'), (-5, 'video_duration_invalid'), (cp.MAX_VIDEO_MS + 1, 'video_duration_too_long')):
            args = self.start_args('x', mode='video')
            args['options'] = {'target_duration_ms': ms}
            args['input_fingerprint'] = cp.start_fingerprint(args)
            value, _ = await self.hostile_start(args)
            self.assertEqual(value['error'], code, ms)
        for mode, options in (('normal', {}), ('video', {'target_duration_ms': 2000, 'segment_path': '/tmp/a'})):
            args = self.start_args('x', mode=mode)
            args['options'] = options
            args['input_fingerprint'] = cp.start_fingerprint(args)
            value, _ = await self.hostile_start(args)
            self.assertEqual(value['error'], 'invalid_request', (mode, options))
        # A fingerprint that omits the options is not the same request.
        args = self.video_args(ms=20000)
        args['input_fingerprint'] = cp.start_fingerprint({k: v for k, v in args.items() if k != 'options'})
        value, _ = await self.hostile_start(args)
        self.assertEqual(value['error'], 'invalid_request')

    async def test_one_starting_image_is_accepted_only_when_advertised(self):
        first, second = png(12, 8, lambda x, y: (40, 120, 230)), png(12, 8, lambda x, y: (220, 30, 30))
        refs = [base.ref(first, name='sky.png'), base.ref(second, name='circle.png')]
        for data, descriptor in zip((first, second), refs):
            await self.upload(data, descriptor)
        # An older computer (no image-to-video) refuses truthfully.
        value, _ = await self.call('start', self.start_args('Animate', mode='video', attachments=refs[:1]))
        self.assertEqual(value['error'], 'attachment_unsupported_mode')
        self.runtime.animate = True
        value, _ = await self.call('start', self.video_args('Animate', ms=5000, attachments=refs))
        self.assertEqual(value['error'], 'video_one_image')
        args = self.video_args('Animate the clouds', ms=5000, attachments=refs[:1])
        value, _ = await self.call('start', args)
        self.assertIsNone(value['error'], value)
        result, text = await self.finish(args['job_id'])
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(self.runtime.received[-1]['sha256'], hashlib.sha256(first).hexdigest(), 'the image bytes arrive unchanged')

    async def test_stop_during_a_long_video_attaches_nothing(self):
        self.runtime.animate = True
        args = self.video_args('slow 20 second video', ms=20000)
        await self.call('start', args)
        await asyncio.sleep(.5)
        value, _ = await self.call('cancel', dict(job_id=args['job_id']))
        self.assertEqual(value['result']['state'], 'cancelled')
        result, _ = await self.finish(args['job_id'])
        self.assertEqual((result['state'], result['artifacts']), ('cancelled', []))

    async def test_long_video_artifact_is_chunked_and_verified(self):
        self.runtime.animate = True
        payload = b'\0\0\0\x18ftypisom' + bytes(range(256)) * 12_000  # ~3 MB: many 128 KiB chunks, never one frame.
        self.runtime.video = lambda: payload
        args = self.video_args(ms=30000)
        await self.call('start', args)
        result, _ = await self.finish(args['job_id'])
        artifact = result['artifacts'][0]
        self.assertEqual(artifact['size'], len(payload))
        received, offset = bytearray(), 0
        while offset < artifact['size']:
            value, binary = await self.call('artifact_chunk', dict(artifact_id=artifact['artifact_id'], offset=offset, length=cp.CHUNK_BYTES))
            self.assertIsNone(value['error'], value)
            self.assertLessEqual(len(binary), cp.CHUNK_BYTES)
            self.assertEqual(value['result']['sha256'], artifact['sha256'])
            received += binary; offset += len(binary)
        self.assertEqual(hashlib.sha256(received).hexdigest(), artifact['sha256'])
        # Resuming from a verified offset returns the same bytes; nothing is regenerated.
        runs = len(self.runtime.runs)
        value, binary = await self.call('artifact_chunk', dict(artifact_id=artifact['artifact_id'], offset=cp.CHUNK_BYTES * 3, length=1000))
        self.assertEqual(binary, bytes(received[cp.CHUNK_BYTES * 3:cp.CHUNK_BYTES * 3 + 1000]))
        self.assertEqual(len(self.runtime.runs), runs)

    async def test_devices_snapshot_shows_the_phone_matrix_and_no_stale_chat_entry(self):
        from olive.connect.mobile_capabilities import FUTURE_CONTROLS, unavailable_controls
        from olive.connect.workspace import DevicesWorkspace
        self.runtime.summary = lambda: {'protocol': 'olive-chat/1', 'groups': [], 'attachments': ['image'], 'video': None}
        snapshot = await asyncio.to_thread(DevicesWorkspace(self.desktop).snapshot)
        self.assertEqual(snapshot['remote_chat']['protocol'], 'olive-chat/1')
        unavailable = snapshot['mobile_controls']['unavailable']
        self.assertNotIn('chat', unavailable, 'Chat is served by Remote AI')
        self.assertEqual(unavailable, list(FUTURE_CONTROLS), 'future remote controls stay listed, none implemented')
        self.assertEqual(snapshot['mobile_controls']['provided_by'], {'chat': 'models.remote'})
        self.assertEqual(unavailable_controls([{'capability': 'terminal', 'supported': True, 'policy_disabled': False}])[:1], ['tasks'])
        self.assertNotIn('terminal', unavailable_controls([{'capability': 'terminal', 'supported': True, 'policy_disabled': False}]))

    async def test_video_capability_never_grants_other_authority(self):
        self.runtime.animate = True
        value, _ = await self.call('capabilities', {'accept': ['mode_options/1']})
        text = str(value['result'])
        for word in ('terminal', 'desktop_control', 'filesystem', 'apps.launch', 'software.install', '/home', 'ltx-2'):
            self.assertNotIn(word, text)


if __name__ == '__main__':
    unittest.main()
