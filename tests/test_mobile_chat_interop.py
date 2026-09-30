"""Remote Chat v2: the real Swift phone client against the real Python desktop service.

The phone side is the Swift interop tool built by
``mobile/ios/scripts/check-connect-interop.sh`` from the app's own sources
(RemoteChatClient, ChatWire, ChatMediaStore). Every exchange is a real
olive-chat/1 packet produced by one side and strictly parsed by the other. This
test stands in for the TLS channel only (covered by the Connect interop tests);
it does not verify UIKit or a physical phone, and no model runs (TEST runtime).

Skipped unless OLIVE_CHAT_SWIFT_HARNESS names that tool (macOS with Xcode).
"""
import asyncio
import base64
import hashlib
import json
import os
import select
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from olive.connect.identity import DeviceKeyStore
from olive.connect.network_wire import CHAT_REQUEST, REQUEST, frame, header, HEADER
from olive.connect.service import DesktopDeviceService
from tests.fixtures.chat_test_runtime import ChatTestRuntime, png
from tests.test_connect_chat import FakeChannel
from tests.test_connect_network import pair
from tests.test_connect_pairing import MemoryVault

HARNESS = os.environ.get('OLIVE_CHAT_SWIFT_HARNESS')


@unittest.skipUnless(HARNESS, 'set OLIVE_CHAT_SWIFT_HARNESS to the Swift interop tool')
class SwiftChatInteropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.phone, self.desktop = [DesktopDeviceService(self.root / n, key_store=DeviceKeyStore(MemoryVault())) for n in ('phone', 'desktop')]
        pair(self.phone, self.desktop)
        self.desktop.set_permission(self.phone.local_id, 'models.remote', 'allow')
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.runtime = ChatTestRuntime(self.root / 'artifacts')
        self.chat = self.desktop.attach_chat(self.runtime, self.loop)
        self.chat.activate()
        self.channel = FakeChannel(self.desktop, self.phone)
        self.drops = set()      # frame numbers whose reply is "lost"
        self.frames = 0
        self.swift = subprocess.Popen([HARNESS, '--chat-harness', self.phone.local_id, self.desktop.local_id, str(self.root / 'swift')],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def tearDown(self):
        self.swift.kill(); self.swift.wait()
        self.swift.stdin.close(); self.swift.stdout.close()
        asyncio.run_coroutine_threadsafe(self.chat.shutdown(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.desktop.close(); self.phone.close()
        self.temp.cleanup()

    def serve(self, kind, payload):
        """What C3 does with one phone frame, minus TLS: bound check, dispatch, reply bytes."""
        header(HEADER.pack(len(payload), 1, kind))  # The desktop's own frame limits apply.
        if kind == REQUEST:
            response = self.desktop._receive(payload, peer_device_id=self.phone.local_id, public=self.channel.public)
            from olive.connect.contracts import canonical
            return canonical(response)
        self.assertEqual(kind, CHAT_REQUEST)
        out = []
        self.chat.receive(payload, self.channel, out.append)
        frame(kind + 1, out[0])
        return out[0]

    def run_command(self, command, timeout=30):
        self.swift.stdin.write(json.dumps(command) + '\n'); self.swift.stdin.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([self.swift.stdout], [], [], 1)
            if not ready:
                continue
            line = json.loads(self.swift.stdout.readline())
            if 'frame' in line:
                self.frames += 1
                if self.frames in self.drops:
                    self.swift.stdin.write(json.dumps({'drop': True}) + '\n')
                else:
                    reply = self.serve(line['kind'], base64.b64decode(line['frame']))
                    self.swift.stdin.write(json.dumps({'reply': base64.b64encode(reply).decode()}) + '\n')
                self.swift.stdin.flush()
                continue
            return line
        self.fail('harness timed out')

    def done(self, command, **kw):
        line = self.run_command(command, **kw)
        self.assertIn('done', line, line)
        return line['done']

    def test_negotiation_text_modes_and_idempotent_start(self):
        self.assertTrue(self.done({'cmd': 'probe'}))
        capabilities = self.done({'cmd': 'capabilities'})
        self.assertEqual([m['id'] for m in capabilities['modes']],
                         ['fast', 'normal', 'max', 'uncensored', 'now', 'deep', 'reimagine', 'audio', 'video'])
        job, conversation = str(uuid.uuid4()), str(uuid.uuid4())
        start = {'cmd': 'start', 'job': job, 'conversation': conversation, 'mode': 'fast', 'text': 'Reply with exactly: fast-mobile-ready'}
        self.assertIn(self.done(start)['state'], ('queued', 'running'))
        self.done(start)  # Resent after a lost acknowledgement: the desktop's receipt makes it idempotent.
        result = self.done({'cmd': 'follow', 'job': job})
        self.assertEqual((result['state'], result['text'], result['label']), ('completed', 'fast-mobile-ready', 'FAST'))
        self.assertEqual(len(self.runtime.runs), 1)
        story = str(uuid.uuid4())
        self.done({'cmd': 'start', 'job': story, 'conversation': conversation, 'mode': 'uncensored', 'text': 'Write a short story'})
        self.assertEqual(self.done({'cmd': 'follow', 'job': story})['label'], 'UNCENSORED · CREATIVE')

    def test_now_sources_and_typed_failure(self):
        job = str(uuid.uuid4())
        self.done({'cmd': 'start', 'job': job, 'conversation': str(uuid.uuid4()), 'mode': 'now', 'text': 'Weather in Cape Town now?'})
        result = self.done({'cmd': 'follow', 'job': job})
        self.assertEqual([s['url'] for s in result['sources']], ['https://example.org/weather', 'https://example.com/status'])
        failed = str(uuid.uuid4())
        self.done({'cmd': 'start', 'job': failed, 'conversation': str(uuid.uuid4()), 'mode': 'now', 'text': 'offline news'})
        self.assertEqual(self.done({'cmd': 'follow', 'job': failed})['error'], 'search_unavailable')

    def test_attachment_upload_resumes_after_drop_and_deep_cites(self):
        doc = self.root / 'synthetic.txt'
        doc.write_bytes(('Filler line.\n' * 30000 + 'The unique test phrase is amber-falcon-7.\n').encode())
        self.drops = {3}  # The second chunk's reply is lost mid-upload.
        failed = self.run_command({'cmd': 'upload', 'path': str(doc), 'kind': 'document', 'mime': 'text/plain', 'name': 'synthetic.txt'})
        self.assertEqual(failed.get('failed'), 'connectionLost')
        self.drops = set()
        descriptor = self.done({'cmd': 'upload', 'path': str(doc), 'kind': 'document', 'mime': 'text/plain', 'name': 'synthetic.txt'})
        staged = list((self.root / 'desktop/connect/chat-staging' / self.phone.local_id).glob('*.txt'))
        self.assertEqual(len(staged), 1, 'exactly one attachment, no duplicate')
        self.assertEqual(hashlib.sha256(staged[0].read_bytes()).hexdigest(), descriptor['attachment_id'])
        before = self.frames
        self.done({'cmd': 'upload', 'path': str(doc), 'kind': 'document', 'mime': 'text/plain', 'name': 'synthetic.txt'})
        self.assertEqual(self.frames - before, 1, 'same hash: an offer only, no bytes')
        job = str(uuid.uuid4())
        self.done({'cmd': 'start', 'job': job, 'conversation': str(uuid.uuid4()), 'mode': 'deep',
                   'text': 'What is the unique test phrase?', 'attachments': [descriptor]})
        result = self.done({'cmd': 'follow', 'job': job})
        self.assertIn('amber-falcon-7', result['text'])
        self.assertEqual(result['sources'][0]['id'], 'D1')

    def test_media_artifact_download_resumes_and_verifies(self):
        # A synthetic container larger than one chunk (not playable; the test host uses real MP4s).
        self.runtime.video = lambda: b'\0\0\0\x18ftypisom' + os.urandom(400_000)
        job = str(uuid.uuid4())
        self.done({'cmd': 'start', 'job': job, 'conversation': str(uuid.uuid4()), 'mode': 'video', 'text': 'A calm synthetic scene'})
        result = self.done({'cmd': 'follow', 'job': job})
        artifact = result['artifacts'][0]
        self.assertEqual(artifact['kind'], 'video')
        self.drops = {self.frames + 2}  # The second chunk is lost: a partial file remains, not a result.
        self.runtime.files[artifact['artifact_id']]  # Exists on the desktop.
        failed = self.run_command({'cmd': 'download', 'artifact_id': artifact['artifact_id']})
        self.assertEqual(failed.get('failed'), 'connectionLost')
        self.assertEqual(self.done({'cmd': 'partial', 'artifact_id': artifact['artifact_id']}), 131072)
        self.drops = set()
        runs = len(self.runtime.runs)
        path = self.done({'cmd': 'download', 'artifact_id': artifact['artifact_id']})['path']
        self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), artifact['sha256'])
        self.assertEqual(len(self.runtime.runs), runs, 'a transfer is resumed, never regenerated')

    def test_reimagine_reference_and_stop(self):
        image = self.root / 'drawing.png'
        image.write_bytes(png(16, 16, lambda x, y: (255, 0, 0)))
        descriptor = self.done({'cmd': 'upload', 'path': str(image), 'kind': 'image', 'mime': 'image/png', 'name': 'drawing.png'})
        job = str(uuid.uuid4())
        self.done({'cmd': 'start', 'job': job, 'conversation': str(uuid.uuid4()), 'mode': 'reimagine',
                   'text': 'Make it darker', 'attachments': [descriptor]})
        self.assertEqual(self.done({'cmd': 'follow', 'job': job})['artifacts'][0]['kind'], 'image')
        slow = str(uuid.uuid4())
        self.done({'cmd': 'start', 'job': slow, 'conversation': str(uuid.uuid4()), 'mode': 'video', 'text': 'A slow scene'})
        time.sleep(.4)
        self.assertEqual(self.done({'cmd': 'cancel', 'job': slow})['state'], 'cancelled')
        result = self.done({'cmd': 'follow', 'job': slow})
        self.assertEqual((result['state'], result['artifacts']), ('cancelled', []))

    def test_old_desktop_is_not_sent_olive_chat_frames(self):
        self.desktop.chat = None  # A desktop build without olive-chat/1.
        self.assertFalse(self.done({'cmd': 'probe'}))
        self.assertEqual(self.frames, 1, 'only the read-only probe was sent')


if __name__ == '__main__':
    unittest.main()
