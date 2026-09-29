"""OLIVE Notes over real OLIVE Connect: mutually authenticated TLS loopback."""
import json
import statistics
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from olive.connect.contracts import canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.network_wire import NOTES_REQUEST, frame
from olive.connect.service import DesktopDeviceService
from olive.notes import protocol
from olive.notes.service import NotesService
from tests.test_connect_network import pair, request, until
from tests.test_connect_pairing import MemoryVault


class ConnectNotesTests(unittest.TestCase):
    def setUp(self):
        self.thread_errors = []
        self.original_hook = threading.excepthook
        threading.excepthook = self.thread_errors.append
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.a = DesktopDeviceService(root / 'a', key_store=DeviceKeyStore(MemoryVault()))
        self.b = DesktopDeviceService(root / 'b', key_store=DeviceKeyStore(MemoryVault()))
        self.notes_a = NotesService(root / 'a' / 'notes.sqlite3', device_id=self.a.local_id)
        self.notes_b = NotesService(root / 'b' / 'notes.sqlite3', device_id=self.b.local_id)
        self.a.attach_notes(self.notes_a)
        self.b.attach_notes(self.notes_b)
        pair(self.a, self.b)
        self.na = self.a.enable_network('127.0.0.1', discovery=False)
        self.nb = self.b.enable_network('127.0.0.1', discovery=False)

    def tearDown(self):
        for service in (self.a, self.b):
            service.close()
        self.notes_a.close()
        self.notes_b.close()
        self.temp.cleanup()
        threading.excepthook = self.original_hook
        self.assertEqual(self.thread_errors, [], 'uncaught worker exception')

    def connect(self):
        channel = self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port)
        until(lambda: self.nb.status(self.a.local_id)['state'] == 'online')
        return channel

    def allow(self):
        self.a.set_permission(self.b.local_id, 'sync.notes', 'allow')
        self.b.set_permission(self.a.local_id, 'sync.notes', 'allow')

    def text(self, notes, nid):
        try:
            return notes.run(notes.read_text, nid)['text']
        except Exception:
            return None

    def test_off_by_default_then_live_sync_both_ways(self):
        channel = self.connect()
        nid = self.notes_a.run(self.notes_a.create, 'Shopping', 'Milk\nBread')['note_id']
        time.sleep(.3)
        self.assertEqual(self.notes_b.run(self.notes_b.list_notes)['notes'], [])
        now = int(time.time())
        raw = protocol.encode_request(str(uuid.uuid4()), self.a.local_id, self.b.local_id, 'hello',
                                      {'versions': [protocol.PROTOCOL]}, now)
        self.assertEqual(channel.notes_request(raw)['error'], 'permission_off')
        self.assertIn('sync.notes', [c['capability'] for c in self.b.capabilities()])
        self.allow()                                   # Initial sync starts on Allow.
        until(lambda: self.text(self.notes_b, nid) == 'Milk\nBread', 6)
        self.notes_b.run(self.notes_b.append_text, nid, 'Eggs')
        until(lambda: self.text(self.notes_a, nid) == 'Milk\nBread\nEggs', 6)
        samples = []
        for index in range(15):
            started = time.perf_counter()
            self.notes_a.run(self.notes_a.append_text, nid, f'item {index}')
            until(lambda: self.text(self.notes_b, nid).endswith(f'item {index}'), 6)
            samples.append((time.perf_counter() - started) * 1000)
        print(f'\nNotes over real Connect TLS loopback: edit -> remote applied median {statistics.median(samples):.0f} ms, '
              f'max {max(samples):.0f} ms (includes 40 ms batching and 10 ms polling)')
        until(lambda: self.a.notes.status(self.b.local_id)['pending'] == 0, 6)
        self.assertEqual(self.text(self.notes_a, nid), self.text(self.notes_b, nid))
        # Ordinary Connect traffic is unaffected by Notes frames.
        self.b.set_permission(self.a.local_id, 'connect.ping', 'allow')
        self.assertTrue(channel.request(canonical(request(self.a, self.b)))['result']['pong'])

    def test_malformed_frame_is_rejected_without_closing_channel(self):
        channel = self.connect()
        self.allow()
        future_id = str(uuid.uuid4())
        raw = json.dumps({'protocol_version': protocol.PROTOCOL, 'request_id': future_id}).encode()
        with channel.lock:
            channel.writes.put_nowait(frame(NOTES_REQUEST, raw))
        time.sleep(.3)
        self.assertEqual(self.na.status(self.b.local_id)['state'], 'online')
        nid = self.notes_a.run(self.notes_a.create, '', 'after malformed')['note_id']
        until(lambda: self.text(self.notes_b, nid) == 'after malformed', 6)

    def test_revocation_stops_delivery_and_keeps_local_notes(self):
        self.connect()
        self.allow()
        nid = self.notes_a.run(self.notes_a.create, '', 'shared')['note_id']
        until(lambda: self.text(self.notes_b, nid) == 'shared', 6)
        self.b.revoke(self.a.local_id)
        until(lambda: not self.na.channels)
        self.notes_a.run(self.notes_a.append_text, nid, 'private after revoke')
        time.sleep(.5)
        self.assertEqual(self.text(self.notes_b, nid), 'shared')
        self.assertEqual(self.text(self.notes_a, nid), 'shared\nprivate after revoke')
        self.assertEqual(self.b.notes.status(self.a.local_id)['state'], 'off')

    def test_never_initiates_notes_toward_a_peer_that_has_not_spoken_notes(self):
        # B only has an inbound channel from A. Until A sends a Notes frame, B must
        # not send one: an older phone would drop the connection on frame 13.
        self.a.notes.close()
        self.a.notes = None
        channel = self.connect()
        self.b.set_permission(self.a.local_id, 'sync.notes', 'allow')
        self.notes_b.run(self.notes_b.create, '', 'stays on B')
        time.sleep(.4)
        self.assertNotIn(self.a.local_id, self.b.notes.announced)
        self.assertEqual(self.na.notes_rates, {})
        self.assertEqual(self.na.status(self.b.local_id)['state'], 'online')
        self.assertTrue(channel)

    def test_ask_is_not_offered_for_notes(self):
        from olive.connect.workspace import DevicesWorkspace
        from olive.connect.contracts import ConnectError
        with self.assertRaises(ConnectError):
            DevicesWorkspace(self.b).permission(self.a.local_id, 'sync.notes', 'ask')


if __name__ == '__main__':
    unittest.main()
