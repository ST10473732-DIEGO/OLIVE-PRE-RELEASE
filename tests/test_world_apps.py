"""Application protocols through forced OLIVE Connect World, unchanged.

olive-chat/1 (every mode, cancel, attachments, artifacts, recovery), olive-notes/1
and olive-draw/1 run over the real relay, real World clients and the real pinned
Connect TLS session. Direct is never used after the one-time enrolment. The
relay's view is captured and searched for application content.
"""
import asyncio
import hashlib
import json
import random
import threading
import time
import unittest
import uuid

from olive.connect import chat_protocol as cp
from olive.connect.contracts import ConnectError
from olive.draw.service import DrawService
from olive.notes.service import NotesService
from tests.draw_sync_fixture import png, stroke
from tests.fixtures.chat_test_runtime import ChatTestRuntime
from tests.test_connect_network import until
from tests.test_connect_world import SECRET, WorldIntegrationBase, tls_records

VIDEO_BYTES = 24 * 1024 * 1024 + 12345     # A deterministic synthetic "MP4" (no generation run).
ATTACHMENT_BYTES = 12 * 1024 * 1024 + 777


def synthetic_video():
    block = hashlib.sha256(b'olive-world-video').digest() * 2048  # 64 KiB pattern
    data = (b'\x00\x00\x00\x18ftypisom' + block * (VIDEO_BYTES // len(block) + 1))[:VIDEO_BYTES]
    return data


class WorldChatTests(WorldIntegrationBase):
    def attach(self):
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self.loop.run_forever, name='test-chat-loop', daemon=True)
        self.loop_thread.start()
        self.runtime = ChatTestRuntime(self.root / 'artifacts', video=synthetic_video)
        self.runtime.slow_seconds = 3
        self.chat = self.desk.attach_chat(self.runtime, self.loop)

    def tearDown(self):
        asyncio.run_coroutine_threadsafe(self.chat.shutdown(), self.loop).result(10)
        super().tearDown()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join(5)
        self.loop.close()

    def setUp(self):
        super().setUp()
        self.desk.set_permission(self.phone.local_id, 'models.remote', 'allow')
        self.peer = self.provisioned()
        self.channel = self.world_connect(self.peer)
        self.assertEqual(self.channel.path, 'world')

    def call(self, op, args, binary=b'', channel=None):
        raw = cp.request(self.phone.local_id, self.desk.local_id, op, args, now=int(time.time()), binary=binary)
        value, data = cp.unpack((channel or self.channel).chat_request(raw))
        return value, data

    def reconnect(self):
        self.peer.drop()
        until(lambda: self.channel.stop.is_set(), 6)
        self.channel = self.world_connect(self.peer)
        return self.channel

    def start_args(self, text, mode='fast', attachments=(), job=None):
        args = dict(job_id=job or str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), mode=mode, voice=None,
                    messages=[dict(role='user', content=text)], attachments=list(attachments))
        args['input_fingerprint'] = cp.start_fingerprint(args)
        return args

    def finish(self, job_id, timeout=30):
        after, text, deadline = 0, '', time.monotonic() + timeout
        while time.monotonic() < deadline:
            value, _ = self.call('poll', dict(job_id=job_id, after=after))
            self.assertIsNone(value['error'], value)
            result = value['result']
            text += result['text']; after += len(result['text'].encode())
            if result['state'] in cp.TERMINAL and after >= result['total']:
                return result, text
            time.sleep(.05)
        raise AssertionError('job did not finish')

    def test_every_mode_once_with_correct_attribution(self):
        value, _ = self.call('capabilities', {})
        self.assertEqual([m['id'] for m in value['result']['modes']], list(cp.MODES))
        document = b'OLIVE World deep document. The unique phrase is world-relay-checked.\n'
        descriptor = dict(attachment_id=hashlib.sha256(document).hexdigest(), kind='document', mime='text/plain',
                          size=len(document), name='world-deep.txt')
        self.call('attachment_offer', descriptor)
        self.call('attachment_chunk', dict(attachment_id=descriptor['attachment_id'], offset=0), binary=document)
        expected = {}
        for mode in cp.MODES:
            prompt = {'fast': 'Reply with exactly: fast-world-ready', 'normal': 'Reply with exactly: normal-world-ready',
                      'max': 'Reply with exactly: max-world-ready', 'uncensored': 'Write a short story about a relay',
                      'now': 'What is the weather back home?', 'deep': 'What is the unique phrase?',
                      'reimagine': 'Generate a blue square', 'audio': 'Say: OLIVE world audio.',
                      'video': 'A calm synthetic scene'}[mode]
            args = self.start_args(prompt, mode=mode, attachments=[descriptor] if mode == 'deep' else [])
            value, _ = self.call('start', args)
            self.assertIsNone(value['error'], (mode, value))
            result, text = self.finish(args['job_id'])
            self.assertEqual(result['state'], 'completed', (mode, result))
            expected[mode] = (result, text)
        self.assertEqual(expected['fast'][1], 'fast-world-ready')
        self.assertEqual(expected['normal'][1], 'normal-world-ready')
        self.assertEqual(expected['max'][1], 'max-world-ready')
        for mode in ('fast', 'normal', 'max'):
            self.assertEqual(expected[mode][0]['attribution']['label'], mode.upper())
        self.assertEqual(expected['uncensored'][0]['attribution']['label'], 'UNCENSORED · CREATIVE')
        self.assertEqual([s['id'] for s in expected['now'][0]['sources']], ['S1', 'S2'])
        self.assertIn('[D1]', expected['deep'][1])
        self.assertEqual([expected[m][0]['artifacts'][0]['kind'] for m in ('reimagine', 'audio', 'video')],
                         ['image', 'audio', 'video'])
        self.assertEqual([mode for _, mode, _ in self.runtime.runs], list(cp.MODES), 'one run per request, no duplicates')
        self.assertEqual(self.nd.status(self.phone.local_id)['connection'], 'world')
        relay_view = b''.join(p for _, p in self.seen)
        for needle in (b'fast-world-ready', b'world-relay-checked', b'world-deep.txt', b'weather back home', b'olive-chat/1'):
            self.assertNotIn(needle, relay_view)

    def test_cancel_and_idempotent_start_across_a_path_drop(self):
        args = self.start_args('slow reply please')
        self.assertIsNone(self.call('start', args)[0]['error'])
        self.reconnect()                                          # Cellular blip mid-job.
        again, _ = self.call('start', args)                       # The phone does not know if it landed.
        self.assertIsNone(again['error'])
        value, _ = self.call('cancel', dict(job_id=args['job_id']))
        self.assertIsNone(value['error'], value)
        result, _ = self.finish(args['job_id'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(len(self.runtime.runs), 1, 'accepted work is never resubmitted')

    def test_accepted_job_survives_relay_restart(self):
        args = self.start_args('slow reply please about the relay')
        self.assertIsNone(self.call('start', args)[0]['error'])
        port = self.relay.port
        self.relay.stop()                                         # Relay process restarts; it held no job state.
        until(lambda: self.channel.stop.is_set(), 6)
        from tests.world_fixture import RelayThread
        self.relay = RelayThread(observer=self.observe, port=port).start()
        until(lambda: self.desk.world.status()['peers'][self.phone.local_id]['route'] == 'registered', 20)
        self.channel = self.world_connect(self.peer)
        result, text = self.finish(args['job_id'])
        self.assertEqual(result['state'], 'completed')
        self.assertTrue(text.startswith('FAST test host reply'))
        self.assertEqual(len(self.runtime.runs), 1)

    def test_attachment_upload_resumes_across_world_interruption(self):
        rng = random.Random(5)
        line = b'OLIVE world attachment line with the unique phrase world-upload-checked.\n'
        data = (line * (ATTACHMENT_BYTES // len(line) + 1))[:ATTACHMENT_BYTES]
        name = 'OLIVE_WORLD_SECRET_FILENAME.txt'
        descriptor = dict(attachment_id=hashlib.sha256(data).hexdigest(), kind='document', mime='text/plain',
                          size=len(data), name=name)
        value, _ = self.call('attachment_offer', descriptor)
        received = value['result']['received']
        interrupted = False
        started = time.perf_counter()
        while True:
            try:
                value, _ = self.call('attachment_chunk', dict(attachment_id=descriptor['attachment_id'], offset=received),
                                     binary=data[received:received + cp.CHUNK_BYTES])
            except ConnectError:
                self.channel = self.world_connect(self.peer)
                value, _ = self.call('attachment_offer', descriptor)   # Resume from the desktop's offset.
                self.assertEqual(value['result']['state'], 'partial')
                received = value['result']['received']
                continue
            self.assertIsNone(value['error'], value)
            received = value['result']['received']
            if value['result']['state'] == 'present':
                break
            if not interrupted and received >= ATTACHMENT_BYTES // 2 + rng.randint(0, 99_999):
                interrupted = True
                self.peer.drop()                                  # Wi-Fi -> cellular mid-upload.
                until(lambda: self.channel.stop.is_set(), 6)
        elapsed = time.perf_counter() - started
        self.assertTrue(interrupted)
        folder = self.root / 'desk' / 'connect' / 'chat-staging' / self.phone.local_id
        staged = [p for p in folder.rglob('*') if p.is_file() and p.suffix != '.json']   # .json: staging metadata
        self.assertEqual(len(staged), 1, 'exactly one staged file and no leftover .part')
        self.assertEqual(staged[0].suffix, '.txt')
        self.assertEqual(hashlib.sha256(staged[0].read_bytes()).hexdigest(), descriptor['attachment_id'])
        args = self.start_args('What is the unique phrase?', mode='deep', attachments=[descriptor])
        self.assertIsNone(self.call('start', args)[0]['error'])
        result, text = self.finish(args['job_id'], timeout=60)
        self.assertEqual(result['state'], 'completed')
        self.assertIn('world-upload-checked', text)
        self.assertEqual(len(self.runtime.runs), 1)
        self.assertEqual(self.runtime.received[0]['sha256'], descriptor['attachment_id'])
        relay_view = b''.join(p for _, p in self.seen)
        self.assertNotIn(name.encode(), relay_view)
        self.assertNotIn(b'world-upload-checked', relay_view)
        print(f'\nWorld loopback upload: {ATTACHMENT_BYTES / 1048576:.1f} MiB incl. one interruption in {elapsed:.2f} s', end='')

    def test_media_download_resumes_the_same_part_file(self):
        args = self.start_args('A calm synthetic scene', mode='video')
        self.assertIsNone(self.call('start', args)[0]['error'])
        result, _ = self.finish(args['job_id'])
        artifact = result['artifacts'][0]
        self.assertEqual((artifact['kind'], artifact['size']), ('video', VIDEO_BYTES))
        part = self.root / 'phone-media' / (artifact['artifact_id'] + '.part')
        part.parent.mkdir()
        interrupted = False
        started = time.perf_counter()
        with part.open('ab') as out:
            while out.tell() < artifact['size']:
                offset = out.tell()
                try:
                    value, chunk = self.call('artifact_chunk', dict(artifact_id=artifact['artifact_id'], offset=offset,
                                                                    length=cp.CHUNK_BYTES))
                except ConnectError:
                    self.channel = self.world_connect(self.peer)  # Same .part, same offset: no regeneration.
                    continue
                self.assertIsNone(value['error'], value)
                out.write(chunk)
                if not interrupted and out.tell() >= 10 * 1024 * 1024:
                    interrupted = True
                    self.peer.drop()
                    until(lambda: self.channel.stop.is_set(), 6)
        elapsed = time.perf_counter() - started
        self.assertTrue(interrupted)
        final = part.with_suffix('.mp4')
        part.rename(final)
        self.assertEqual(hashlib.sha256(final.read_bytes()).hexdigest(), artifact['sha256'])
        self.assertEqual([p.name for p in final.parent.iterdir()], [final.name], 'one local file')
        self.assertEqual([m for _, m, _ in self.runtime.runs], ['video'], 'VIDEO was generated once')
        print(f'\nWorld loopback download: {VIDEO_BYTES / 1048576:.1f} MiB incl. one interruption in {elapsed:.2f} s '
              f'({VIDEO_BYTES / 1048576 / elapsed:.1f} MiB/s)', end='')

    def test_permission_is_unchanged_by_world(self):
        self.desk.set_permission(self.phone.local_id, 'models.remote', 'deny')
        value, _ = self.call('start', self.start_args('Reply with exactly: nope'))
        self.assertIsNotNone(value['error'])
        self.assertEqual(self.runtime.runs, [])


class WorldNotesDrawTests(WorldIntegrationBase):
    def attach(self):
        self.notes_d = NotesService(self.root / 'desk' / 'notes.sqlite3', device_id=self.desk.local_id)
        self.notes_p = NotesService(self.root / 'phone' / 'notes.sqlite3', device_id=self.phone.local_id)
        self.draw_d = DrawService(self.root / 'desk' / 'drawings.sqlite3', device_id=self.desk.local_id)
        self.draw_p = DrawService(self.root / 'phone' / 'drawings.sqlite3', device_id=self.phone.local_id)
        self.desk.attach_notes(self.notes_d); self.phone.attach_notes(self.notes_p)
        self.desk.attach_draw(self.draw_d); self.phone.attach_draw(self.draw_p)

    def detach(self):
        self.notes_d.close(); self.notes_p.close()

    def allow(self, capability):
        self.desk.set_permission(self.phone.local_id, capability, 'allow')
        self.phone.set_permission(self.desk.local_id, capability, 'allow')

    @staticmethod
    def text(notes, nid):
        try:
            return notes.run(notes.read_text, nid)['text']
        except Exception:
            return None

    @staticmethod
    def ids(draw, did):
        try:
            return [op['id'] for op in draw.visible_ops(did)]
        except Exception:
            return None

    def test_notes_both_ways_offline_edits_converge_and_relay_is_blind(self):
        peer = self.provisioned()
        channel = self.world_connect(peer)
        nid = self.notes_d.run(self.notes_d.create, 'World note', 'Desktop line ' + SECRET)['note_id']
        time.sleep(.3)
        self.assertEqual(self.notes_p.run(self.notes_p.list_notes)['notes'], [], 'sync.notes is still Off')
        self.allow('sync.notes')
        until(lambda: self.text(self.notes_p, nid) == 'Desktop line ' + SECRET, 8)
        self.notes_p.run(self.notes_p.append_text, nid, 'Phone line via World')
        until(lambda: (self.text(self.notes_d, nid) or '').endswith('Phone line via World'), 8)
        peer.drop()                                               # Phone goes offline.
        until(lambda: channel.stop.is_set(), 6)
        self.notes_p.run(self.notes_p.append_text, nid, 'Offline phone edit')
        self.notes_d.run(self.notes_d.append_text, nid, 'Offline desktop edit')
        self.world_connect(peer)
        until(lambda: self.text(self.notes_d, nid) == self.text(self.notes_p, nid)
              and 'Offline phone edit' in (self.text(self.notes_d, nid) or '')
              and 'Offline desktop edit' in (self.text(self.notes_p, nid) or ''), 10)
        self.assertEqual(self.nd.status(self.phone.local_id)['connection'], 'world')
        relay_view = b''.join(p for _, p in self.seen)
        for needle in (SECRET, 'World note', 'Phone line via World', 'Offline phone edit', 'olive-notes/1'):
            self.assertNotIn(needle.encode(), relay_view)
        _, whole = tls_records(b''.join(p for r, p in self.seen if r == 'desktop'))
        self.assertTrue(whole)

    def test_draw_strokes_image_undo_and_offline_converge(self):
        peer = self.provisioned()
        channel = self.world_connect(peer)
        until(lambda: self.desk.local_id in self.phone.draw.announced, 6)
        self.allow('sync.draw')
        did = self.draw_p.create('World drawing', 640, 480)['drawing_id']
        first = stroke([10, 10, 600, 400], color='#e53935')
        self.draw_p.append(did, first)
        until(lambda: self.ids(self.draw_d, did) == [first['id']], 8)
        data = png(320, 240, (0, 128, 255, 255), transparent_corner=True)
        asset = self.draw_d.store_asset(data)['asset_id']
        image = {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': asset, 'x': 160, 'y': 120,
                 'width': 320, 'height': 240, 'opacity': 1}
        self.draw_d.append(did, image)
        until(lambda: self.draw_p.asset_info(asset) is not None, 10)
        self.assertEqual(self.draw_p.asset_info(asset)['size'], len(data))
        until(lambda: self.ids(self.draw_p, did) == [first['id'], image['id']], 8)
        self.draw_d.undo(did)                                     # Undo is local history: it syncs as an edit,
        until(lambda: self.ids(self.draw_p, did) == [first['id']], 8)  # never the other device's undo stack.
        peer.drop()
        until(lambda: channel.stop.is_set(), 6)
        a_op, b_op = stroke([1, 1, 300, 1], color='#1e63e9'), stroke([1, 9, 300, 9], color='#43a047')
        self.draw_d.append(did, a_op)
        self.draw_p.append(did, b_op)
        self.world_connect(peer)
        until(lambda: sorted(self.ids(self.draw_d, did) or []) == sorted([first['id'], a_op['id'], b_op['id']]), 10)
        until(lambda: self.ids(self.draw_p, did) == self.ids(self.draw_d, did), 10)
        self.assertEqual(self.nd.status(self.phone.local_id)['connection'], 'world')
        relay_view = b''.join(p for _, p in self.seen)
        for needle in (b'World drawing', b'olive-draw/1', b'#e53935', asset.encode()):
            self.assertNotIn(needle, relay_view)

    def test_world_does_not_bypass_sync_permissions(self):
        peer = self.provisioned()
        self.world_connect(peer)
        self.allow('sync.notes')
        nid = self.notes_d.run(self.notes_d.create, 'Before', 'shared')['note_id']
        until(lambda: self.text(self.notes_p, nid) == 'shared', 8)
        self.desk.set_permission(self.phone.local_id, 'sync.notes', 'deny')
        self.notes_d.run(self.notes_d.append_text, nid, 'private after deny')
        time.sleep(.8)
        self.assertEqual(self.text(self.notes_p, nid), 'shared')
        did = self.draw_d.create('Draw stays off', 100, 100)['drawing_id']
        time.sleep(.5)
        self.assertIsNone(self.ids(self.draw_p, did))


if __name__ == '__main__':
    unittest.main()
