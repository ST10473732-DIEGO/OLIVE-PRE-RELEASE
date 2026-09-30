"""OLIVE Draw over real OLIVE Connect: mutually authenticated TLS loopback."""
import io
import statistics
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from olive.connect.contracts import ConnectError, canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.draw import protocol
from olive.draw.service import DrawService
from olive.notes.service import NotesService
from tests.draw_sync_fixture import png, stroke
from tests.test_connect_network import pair, request, until
from tests.test_connect_pairing import MemoryVault


class ConnectDrawTests(unittest.TestCase):
    def setUp(self):
        self.thread_errors = []
        self.original_hook = threading.excepthook
        threading.excepthook = self.thread_errors.append
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.a = DesktopDeviceService(root / 'a', key_store=DeviceKeyStore(MemoryVault()))
        self.b = DesktopDeviceService(root / 'b', key_store=DeviceKeyStore(MemoryVault()))
        self.draw_a = DrawService(root / 'a' / 'drawings.sqlite3', device_id=self.a.local_id)
        self.draw_b = DrawService(root / 'b' / 'drawings.sqlite3', device_id=self.b.local_id)
        self.notes_a = NotesService(root / 'a' / 'notes.sqlite3', device_id=self.a.local_id)
        self.notes_b = NotesService(root / 'b' / 'notes.sqlite3', device_id=self.b.local_id)
        self.a.attach_notes(self.notes_a)
        self.b.attach_notes(self.notes_b)
        self.a.attach_draw(self.draw_a)
        self.b.attach_draw(self.draw_b)
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
        self.a.set_permission(self.b.local_id, 'sync.draw', 'allow')
        self.b.set_permission(self.a.local_id, 'sync.draw', 'allow')

    @staticmethod
    def ids(draw, did):
        try:
            return [op['id'] for op in draw.visible_ops(did)]
        except Exception:
            return None

    def test_off_by_default_separate_from_notes_then_live_both_ways(self):
        channel = self.connect()
        until(lambda: self.b.local_id in self.a.draw.announced)      # Probe: B speaks olive-draw/1.
        did = self.draw_a.create('Shared', 800, 600)['drawing_id']
        first = stroke([10, 10, 700, 500], color='#e53935')
        self.draw_a.append(did, first)
        # Notes permission does not grant Draw.
        self.a.set_permission(self.b.local_id, 'sync.notes', 'allow')
        self.b.set_permission(self.a.local_id, 'sync.notes', 'allow')
        time.sleep(.4)
        self.assertEqual(self.draw_b.list_drawings()['drawings'], [])
        raw = protocol.encode_request(str(uuid.uuid4()), self.a.local_id, self.b.local_id, 'hello',
                                      {'versions': [protocol.PROTOCOL], 'schemas': [1, 2]}, int(time.time()))
        self.assertEqual(channel.draw_request(raw)['error'], 'permission_off')
        self.assertIn('sync.draw', [c['capability'] for c in self.b.capabilities()])
        self.assertEqual(self.a.draw.status(self.b.local_id)['state'], 'off')
        self.allow()                                                  # Catch-up starts on Allow.
        until(lambda: self.ids(self.draw_b, did) == [first['id']], 6)
        blue = stroke([20, 500, 780, 20], color='#1e63e9', width=12)
        self.draw_b.append(did, blue)
        until(lambda: self.ids(self.draw_a, did) == [first['id'], blue['id']], 6)
        samples = []
        for index in range(12):
            started = time.perf_counter()
            op = stroke([index, 1, index + 50, 60])
            self.draw_a.append(did, op)
            until(lambda: (self.ids(self.draw_b, did) or [])[-1:] == [op['id']], 6)
            samples.append((time.perf_counter() - started) * 1000)
        print(f'\nDraw over real Connect TLS loopback: completed stroke -> remote stored median '
              f'{statistics.median(samples):.0f} ms, max {max(samples):.0f} ms', end='')
        until(lambda: self.a.draw.status(self.b.local_id)['pending'] == 0, 6)
        self.assertEqual(self.ids(self.draw_a, did), self.ids(self.draw_b, did))
        # Ordinary Connect traffic is unaffected by Draw frames.
        self.b.set_permission(self.a.local_id, 'connect.ping', 'allow')
        self.assertTrue(channel.request(canonical(request(self.a, self.b)))['result']['pong'])

    def test_offline_edits_on_both_sides_converge_after_reconnect(self):
        channel = self.connect()
        self.allow()
        did = self.draw_a.create('Offline', 400, 400)['drawing_id']
        until(lambda: self.ids(self.draw_b, did) == [], 6)
        channel.close('test_offline')
        until(lambda: not self.na.channels and not self.nb.channels, 6)
        a_op, b_op = stroke([1, 1, 300, 1], color='#e53935'), stroke([1, 9, 300, 9], color='#1e63e9')
        self.draw_a.append(did, a_op)
        self.draw_b.append(did, b_op)
        self.draw_b.rename(did, 'Named offline')
        self.connect()
        until(lambda: sorted(self.ids(self.draw_a, did) or []) == sorted([a_op['id'], b_op['id']]), 8)
        until(lambda: self.ids(self.draw_b, did) == self.ids(self.draw_a, did), 8)
        until(lambda: self.draw_a.get(did)['title'] == 'Named offline', 6)

    def test_image_asset_travels_by_hash_once(self):
        self.connect()
        self.allow()
        did = self.draw_a.create('Photo', 640, 480)['drawing_id']
        data = png(320, 240, (0, 128, 255, 255), transparent_corner=True)
        asset = self.draw_a.store_asset(data)['asset_id']
        self.draw_a.append(did, {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': asset, 'x': 160, 'y': 120,
                                 'width': 320, 'height': 240, 'opacity': 1})
        until(lambda: self.draw_b.asset_info(asset) is not None, 8)
        self.assertEqual(self.draw_b.asset_info(asset)['size'], len(data))
        self.assertEqual(self.draw_b.visible_ops(did)[0]['asset_id'], asset)
        until(lambda: self.b.draw.status(self.a.local_id)['pending_assets'] == 0, 6)

    def test_peer_without_draw_is_never_sent_draw_frames(self):
        # B answers the probe without olive-draw/1 (an older desktop, or Draw
        # absent). A must not send frame 15, and the channel must stay up.
        self.b.draw.close()
        self.b.draw = None
        self.a.set_permission(self.b.local_id, 'sync.draw', 'allow')
        channel = self.connect()
        until(lambda: self.b.local_id in self.a.draw.unsupported, 6)
        self.draw_a.create('Local only', 100, 100)
        time.sleep(.4)
        self.assertEqual(self.nb.draw_rates, {})
        self.assertEqual(self.na.status(self.b.local_id)['state'], 'online')
        self.assertEqual(self.a.draw.status(self.b.local_id)['state'], 'unsupported')
        self.assertTrue(channel)

    def test_old_build_probe_rejection_keeps_channel(self):
        # What an older desktop does with the probe: RequestEnvelope accepts
        # connect.ping, then the operation is refused with a correlated
        # "unknown_operation" answer. Simulated on B by answering like that.
        original = self.b._protocols
        self.b._protocols = lambda request, peer, public, timeout: dict(
            protocol_version='olive-connect/1', request_id=request.request_id, state='rejected', error='unknown_operation')
        try:
            self.a.set_permission(self.b.local_id, 'sync.draw', 'allow')
            self.connect()
            until(lambda: self.b.local_id in self.a.draw.unsupported, 6)
            self.assertEqual(self.nb.draw_rates, {})
            self.assertEqual(self.na.status(self.b.local_id)['state'], 'online')
        finally:
            self.b._protocols = original

    def test_inbound_side_waits_for_the_peer_to_speak_draw(self):
        # B has only an inbound channel from A. Until A sends a Draw frame, B must
        # not send one: an older phone would drop the connection on frame 15.
        self.a.draw.close()
        self.a.draw = None
        self.connect()
        self.b.set_permission(self.a.local_id, 'sync.draw', 'allow')
        self.draw_b.create('Stays on B', 100, 100)
        time.sleep(.4)
        self.assertNotIn(self.a.local_id, self.b.draw.announced)
        self.assertEqual(self.na.draw_rates, {})
        self.assertEqual(self.na.status(self.b.local_id)['state'], 'online')

    def test_revocation_stops_delivery_and_keeps_local_drawings(self):
        self.connect()
        self.allow()
        did = self.draw_a.create('Shared', 100, 100)['drawing_id']
        until(lambda: self.ids(self.draw_b, did) == [], 6)
        self.b.revoke(self.a.local_id)
        until(lambda: not self.na.channels)
        private = stroke([1, 1, 5, 5])
        self.draw_a.append(did, private)
        time.sleep(.5)
        self.assertEqual(self.ids(self.draw_b, did), [])
        self.assertEqual(self.ids(self.draw_a, did), [private['id']])
        self.assertEqual(self.b.draw.status(self.a.local_id)['state'], 'off')

    def test_ask_is_not_offered_for_draw(self):
        from olive.connect.workspace import DevicesWorkspace
        with self.assertRaises(ConnectError):
            DevicesWorkspace(self.b).permission(self.a.local_id, 'sync.draw', 'ask')
        snapshot = DevicesWorkspace(self.b).permission(self.a.local_id, 'sync.draw', 'allow')
        device = next(d for d in snapshot['devices'] if d['device_id'] == self.a.local_id)
        self.assertIn('draw_sync', device)


if __name__ == '__main__':
    unittest.main()
