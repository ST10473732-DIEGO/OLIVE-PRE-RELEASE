"""OLIVE Draw: the real Swift phone engine against the real Python desktop engine.

The phone side is the Swift interop tool built by
``mobile/ios/scripts/check-connect-interop.sh`` from the app's own sources
(``OLIVEMobile/Core/Draw``: SQLite store, replica rules, olive-draw/1 codec,
image canonicalization, CoreGraphics renderer). Every exchange carries real
olive-draw/1 request/response bytes produced and parsed by each side's
production codec. Phone "restarts" kill the Swift process (SIGKILL) and start a
new one on the same store.

Skipped unless OLIVE_DRAW_SWIFT_HARNESS names that tool (macOS with Xcode).
This verifies the Swift implementation and protocol interop; it does NOT
verify UIKit, touch input or a physical phone (see docs/OLIVE_DRAWNOTE.md).
"""
import base64
import hashlib
import io
import json
import os
import random
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from olive.draw import assets, protocol, records
from olive.draw.document import validate_record
from olive.draw.sync_engine import DrawSyncError
from tests.draw_sync_fixture import SimDrawNetwork, background, clear, erase, png, stroke

ROOT = Path(__file__).resolve().parents[1]
HARNESS = os.environ.get('OLIVE_DRAW_SWIFT_HARNESS')
FIXTURE = json.loads((ROOT / 'olive/draw/conformance_v1.json').read_text(encoding='utf-8'))


class SwiftPhone:
    """One phone replica: the Swift DrawEngine in its own process and store."""

    def __init__(self, name='phone'):
        self.name = name
        self.id = str(uuid.uuid4())
        self.store = tempfile.mkdtemp(prefix='olive-draw-phone-store-')
        self.allowed = set()
        self.process = None
        self.counter = 0
        self.start()

    def start(self):
        self.process = subprocess.Popen([HARNESS, '--draw-harness', self.store], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        self.command('boot', self.id)
        for peer in self.allowed:
            self.command('allow', peer, True)

    def restart(self):
        """Hard process termination (SIGKILL), then a fresh process on the same store."""
        self.process.send_signal(signal.SIGKILL)
        self.process.wait(10)
        self.process.stdin.close()
        self.process.stdout.close()
        self.start()

    def _write(self, value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()

    def _read(self):
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('Swift harness exited')
        return json.loads(line)

    def command(self, cmd, *args):
        self.counter += 1
        self._write({'id': self.counter, 'cmd': cmd, 'args': list(args)})
        reply = self._read()
        if 'error' in reply:
            raise PhoneError(reply['error'])
        return reply['result']

    def allow(self, peer):
        self.allowed.add(peer)
        self.command('allow', peer, True)

    def deny(self, peer):
        self.allowed.discard(peer)
        self.command('allow', peer, False)

    def handle(self, peer, raw):
        return self.command('handle', peer, raw.decode('utf-8')).encode('utf-8')

    def pump(self, peer, hello, transfer):
        """Swift pumps; each request it emits is carried by ``transfer(raw) -> bytes``."""
        self.counter += 1
        self._write({'id': self.counter, 'cmd': 'pump', 'args': [peer, hello]})
        while True:
            message = self._read()
            if 'send' in message:
                try:
                    self._write({'response': transfer(message['send'].encode('utf-8')).decode('utf-8')})
                except DrawSyncError as failure:
                    self._write({'error': str(failure)})
                continue
            if 'error' in message:
                raise DrawSyncError(message['error'])
            return message['result']

    # Views (same shapes as tests/draw_sync_fixture.SimDrawDevice) -----------------------
    def state(self, did):
        value = self.command('state', did)
        return {k: value[k] for k in ('title', 'trashed', 'width', 'height', 'background', 'ops')}

    def ops(self, did):
        return self.command('ops', did)

    def drawings(self, view='drawings'):
        return self.command('list', view)

    def pending(self, peer):
        return self.command('pending', peer)

    def wants(self):
        return self.command('wants')

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.stdin.close()
            self.process.wait(10)
            self.process.stdout.close()
        shutil.rmtree(self.store, ignore_errors=True)


class PhoneError(RuntimeError):
    pass


class Mesh:
    """Python desktops (SimDrawDevice) and Swift phones on one simulated Connect."""

    def __init__(self):
        self.net = SimDrawNetwork()
        self.phones = []
        self.bytes_sent = []      # (operation, request bytes) for size checks

    def desktop(self, name):
        return self.net.device(name)

    def phone(self, name='phone'):
        phone = SwiftPhone(name)
        self.phones.append(phone)
        return phone

    def pair(self, a, b):
        for x, y in ((a, b), (b, a)):
            if isinstance(x, SwiftPhone):
                x.allow(y.id)
            else:
                x.allowed.add(y.id)

    def deliver(self, receiver, sender_id, raw):
        if isinstance(receiver, SwiftPhone):
            return receiver.handle(sender_id, raw)
        return self.net.deliver(receiver, sender_id, raw)

    def transfer(self, a, b, raw):
        """One request from a to b over the simulated channel (with the fixture's faults)."""
        net = self.net
        if not net.online(a, b):
            raise DrawSyncError('device_offline')
        operation = json.loads(raw)['operation']
        self.bytes_sent.append((operation, raw))
        if net._take('drop_request'):
            raise DrawSyncError('connection_lost')
        if net.hold:
            net.held.append((b, a.id, raw))
            raise DrawSyncError('connection_lost')
        if operation == 'asset' and net.block_assets:
            raise DrawSyncError('connection_lost')
        if operation == 'asset' and net.kill_after_chunks is not None:
            if net.kill_after_chunks == 0:
                net.kill_after_chunks = None
                b.restart()         # Receiver dies mid-transfer: staged chunks are gone.
                raise DrawSyncError('connection_lost')
            net.kill_after_chunks -= 1
        response = self.deliver(b, a.id, raw)
        if net._take('duplicate'):
            response = self.deliver(b, a.id, raw)
        if net._take('drop_response'):
            raise DrawSyncError('connection_lost')
        return response

    def sync(self, a, b, hello=True):
        if isinstance(a, SwiftPhone):
            return a.pump(b.id, hello, lambda raw: self.transfer(a, b, raw))

        def send(operation, arguments):
            raw = protocol.encode_request(str(uuid.uuid4()), a.id, b.id, operation, arguments, int(time.time()))
            value = protocol.decode_response(self.transfer(a, b, raw))
            if value['state'] != 'completed':
                raise DrawSyncError(value['error'])
            return value['result']
        return a.engine.pump(b.id, send, hello=hello)

    def release(self, order=None):
        held, self.net.held = self.net.held, []
        for index in (order or range(len(held))):
            receiver, sender_id, raw = held[index]
            self.deliver(receiver, sender_id, raw)

    def connect(self, a, b):
        self.sync(a, b)
        self.sync(b, a)

    @staticmethod
    def pending(a, b):
        return a.pending(b.id) if isinstance(a, SwiftPhone) else a.engine.pending(b.id)

    @staticmethod
    def wants(b):
        return b.wants() if isinstance(b, SwiftPhone) else b.engine.wants()

    def settle(self, devices, rounds=12):
        for _ in range(rounds):
            busy = False
            for a in devices:
                for b in devices:
                    if a is b or b.id not in a.allowed or a.id not in b.allowed or not self.net.online(a, b):
                        continue
                    before = (self.pending(a, b), len(self.wants(b)))
                    if before[0] or before[1]:
                        self.sync(a, b)
                        if (self.pending(a, b), len(self.wants(b))) != before:
                            busy = True
            if not busy:
                return True
        return False

    def close(self):
        for phone in self.phones:
            phone.close()
        self.net.close()


def state_of(device, did):
    return device.state(did)


def jpeg_with_exif_gps(width=64, height=32):
    """A synthetic JPEG: left half red, right half blue, EXIF orientation 6 (90° CW),
    camera make/model, a timestamp and GPS coordinates. No real photo."""
    from PIL import Image
    image = Image.new('RGB', (width, height), (220, 20, 20))
    for x in range(width // 2, width):
        for y in range(height):
            image.putpixel((x, y), (20, 20, 220))
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F] = 'SyntheticCam'
    exif[0x0110] = 'Model Fixture'
    exif[0x0132] = '2026:09:30 10:00:00'
    exif[0x8825] = {1: 'N', 2: (51.0, 30.0, 12.0), 3: 'W', 4: (0.0, 7.0, 39.0)}
    out = io.BytesIO()
    image.save(out, format='JPEG', quality=95, exif=exif.tobytes())
    return out.getvalue()


@unittest.skipUnless(HARNESS, 'Set OLIVE_DRAW_SWIFT_HARNESS (built by mobile/ios/scripts/check-connect-interop.sh)')
class PhoneDrawInteropTests(unittest.TestCase):
    def setUp(self):
        self.mesh = Mesh()
        self.desk = self.mesh.desktop('desktop')
        self.phone = self.mesh.phone()
        self.mesh.pair(self.desk, self.phone)

    def tearDown(self):
        self.mesh.close()

    def converged(self, did, devices=None):
        devices = devices or [self.desk, self.phone]
        states = [state_of(d, did) for d in devices]
        for state in states[1:]:
            self.assertEqual(state, states[0])
        return states[0]

    # --- identity -----------------------------------------------------------------------
    def test_runtime_is_the_swift_engine_with_its_own_sqlite_store(self):
        info = self.phone.command('runtime')
        self.assertEqual(info['runtime'], 'swift-draw-engine')
        self.assertTrue(info['available'])
        self.assertTrue(info['database'].endswith('drawings.sqlite3'))
        self.assertTrue(Path(info['database']).is_file())
        import sqlite3
        with sqlite3.connect(info['database']) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'meta', 'drawings', 'draw_records', 'draw_visibility', 'draw_history', 'draw_purges', 'draw_assets',
                         'draw_wanted', 'draw_peers', 'draw_thumbnails'} <= tables)

    # --- conformance --------------------------------------------------------------------
    def test_shared_conformance_fixture_in_random_arrival_orders(self):
        rng = random.Random(11)
        for scenario in FIXTURE['scenarios']:
            for attempt in range(12):
                order = list(scenario['records'])
                rng.shuffle(order)
                phone = SwiftPhone('conformance')
                try:
                    with self.subTest(scenario=scenario['name'], attempt=attempt):
                        self.assertEqual(phone.command('apply', order), ['applied'] * len(order))
                        self.assertEqual(phone.command('apply', order), ['duplicate'] * len(order))
                        did = scenario['records'][0]['drawing_id']
                        state = phone.command('state', did)
                        expect = scenario['expect']
                        self.assertEqual(phone.command('order', did), expect['order'])
                        self.assertEqual(state['ops'], expect['visible'])
                        self.assertEqual((state['title'], state['trashed'], state['background'], state['width'], state['height']),
                                         (expect['title'], expect['trashed'], expect['background'], expect['width'], expect['height']))
                finally:
                    phone.close()

    def test_phone_records_pass_desktop_validation_and_lamport(self):
        did = self.phone.command('create', 'From phone', 400, 300, '#ffffff')['drawing_id']
        first = self.phone.command('append', did, stroke([10.25, 10.5, 0.3, 200, 150.75, 0.9], color='#1e63e9', width=12, pressure=True))
        second = self.phone.command('append', did, erase([0, 0, 50, 50], width=8))
        page = self.phone.command('since', did, 0)
        for record in page['records']:
            validate_record(record)                     # Python accepts every phone record unchanged.
            self.assertEqual(len(record['record_id']), 32)
            self.assertEqual(record['device'], self.phone.id)
        self.assertEqual([r['lamport'] for r in page['records']], [1, 2, 3])
        self.assertEqual(first['record']['body']['points'], [10.25, 10.5, 0.3, 200, 150.75, 0.9])
        self.assertEqual(second['undo'], 2)
        # A remote record raises the phone's observed clock: the next local edit sorts after it.
        self.mesh.sync(self.phone, self.desk)
        self.desk.service.append(did, stroke([1, 1, 2, 2]))
        self.desk.service.append(did, stroke([3, 3, 4, 4]))
        self.mesh.sync(self.desk, self.phone)
        third = self.phone.command('append', did, stroke([5, 5, 6, 6]))
        self.assertEqual(third['record']['lamport'], 6)

    # --- live sync ----------------------------------------------------------------------
    def test_create_and_strokes_both_directions(self):
        did = self.desk.service.create('Shared', 400, 300)['drawing_id']
        red = stroke([10, 10, 200, 200], color='#e53935', width=8)
        self.desk.service.append(did, red)
        self.mesh.connect(self.desk, self.phone)
        self.assertEqual(self.phone.drawings()[0]['title'], 'Shared')
        self.assertEqual([op['id'] for op in self.phone.ops(did)], [red['id']])
        blue = stroke([300, 20, 0.5, 50, 250, 0.2, 60, 260, 0.9], color='#1e63e9', width=20, pressure=True)
        self.phone.command('append', did, blue)
        self.mesh.settle([self.desk, self.phone])
        state = self.converged(did)
        self.assertEqual(state['ops'], [red['id'], blue['id']])
        self.assertEqual(self.desk.ops(did)[1]['points'], blue['points'])   # Pressure values travel unchanged.
        mine = self.phone.command('create', 'From phone', 200, 200, 'transparent')
        self.mesh.settle([self.desk, self.phone])
        self.assertIn('From phone', [d['title'] for d in self.desk.drawings()])
        self.assertEqual(self.desk.service.get(mine['drawing_id'])['background'], 'transparent')
        # Duplicate titles are allowed: identity is the drawing id.
        again = self.phone.command('create', 'Shared', 400, 300, '#ffffff')
        self.mesh.settle([self.desk, self.phone])
        self.assertEqual(sorted(d['drawing_id'] for d in self.desk.drawings() if d['title'] == 'Shared'),
                         sorted([did, again['drawing_id']]))

    def test_local_origin_undo_isolation_across_devices(self):
        did = self.desk.service.create('Undo', 300, 300)['drawing_id']
        self.mesh.connect(self.desk, self.phone)
        red, blue, green = (stroke([10, y, 290, y], color=c) for y, c in ((50, '#e53935'), (150, '#1e63e9'), (250, '#43a047')))
        self.desk.service.append(did, red)
        self.mesh.settle([self.desk, self.phone])
        self.phone.command('append', did, blue)
        self.mesh.settle([self.desk, self.phone])
        self.desk.service.append(did, green)
        self.mesh.settle([self.desk, self.phone])
        self.assertEqual(self.converged(did)['ops'], [red['id'], blue['id'], green['id']])
        # Phone Undo hides the phone's blue only, on both devices.
        self.phone.command('undo', did)
        self.mesh.settle([self.desk, self.phone])
        self.assertEqual(self.converged(did)['ops'], [red['id'], green['id']])
        # Phone Redo brings blue back.
        self.phone.command('redo', did)
        self.mesh.settle([self.desk, self.phone])
        self.assertEqual(self.converged(did)['ops'], [red['id'], blue['id'], green['id']])
        # Desktop Undo hides the desktop's green (its latest), never the phone's blue.
        self.desk.service.undo(did)
        self.mesh.settle([self.desk, self.phone])
        self.assertEqual(self.converged(did)['ops'], [red['id'], blue['id']])
        # A remote edit between phone Undo and Redo does not destroy phone Redo.
        self.phone.command('undo', did)
        self.desk.service.append(did, stroke([1, 1, 5, 5]))
        self.mesh.settle([self.desk, self.phone])
        self.assertEqual(self.phone.command('redo', did)['record']['body'], {'target': blue['id'], 'hidden': False})
        # A new local edit after Undo clears only the phone's Redo stack.
        self.phone.command('undo', did)
        edit = self.phone.command('append', did, stroke([7, 7, 9, 9]))
        self.assertEqual(edit['redo'], 0)
        # A visibility record the phone forges for a desktop operation is ignored everywhere.
        forged = {'record_id': uuid.uuid4().hex, 'drawing_id': did, 'device': self.phone.id, 'lamport': 99, 'kind': 'visibility',
                  'at': '2026-09-30T10:00:00.000Z', 'body': {'target': red['id'], 'hidden': True}}
        self.phone.command('apply', [forged])
        self.mesh.settle([self.desk, self.phone])
        self.assertIn(red['id'], self.converged(did)['ops'])

    def test_phone_undo_history_survives_process_kill_and_excludes_remote_edits(self):
        did = self.phone.command('create', 'Restart undo', 300, 300, '#ffffff')['drawing_id']
        mine = [stroke([10, y, 200, y]) for y in (10, 20, 30)]
        for op in mine:
            self.phone.command('append', did, op)
        self.mesh.connect(self.phone, self.desk)
        remote = stroke([5, 5, 6, 6], color='#e53935')
        self.desk.service.append(did, remote)
        self.mesh.settle([self.desk, self.phone])
        self.phone.restart()                                   # SIGKILL + relaunch
        state = self.phone.command('state', did)
        self.assertEqual((state['undo'], state['redo']), (3, 0))
        for expected in reversed(mine):
            self.assertEqual(self.phone.command('undo', did)['record']['body']['target'], expected['id'])
        self.assertIsNone(self.phone.command('undo', did)['record'])   # Remote edits are not in the phone's stack.
        self.assertEqual(self.phone.command('state', did)['ops'], [remote['id']])

    def test_offline_edits_on_both_converge_without_prompts(self):
        did = self.desk.service.create('Offline', 300, 300)['drawing_id']
        self.mesh.connect(self.desk, self.phone)
        self.mesh.net.disconnect(self.desk, self.phone)
        green = stroke([10, 10, 290, 10], color='#43a047')
        purple = stroke([10, 20, 290, 20], color='#8e24aa')
        self.desk.service.append(did, green)
        self.phone.command('append', did, purple)
        with self.assertRaises(DrawSyncError):
            self.mesh.sync(self.phone, self.desk)
        self.assertEqual(self.phone.pending(self.desk.id), 1)
        self.mesh.net.reconnect(self.desk, self.phone)
        self.mesh.settle([self.desk, self.phone])
        state = self.converged(did)
        self.assertEqual(sorted(state['ops']), sorted([green['id'], purple['id']]))

    def test_duplicate_delivery_lost_answers_and_out_of_order(self):
        did = self.phone.command('create', 'Faults', 300, 300, '#ffffff')['drawing_id']
        ops = [stroke([i, i, i + 50, i + 20]) for i in range(0, 60, 10)]
        for op in ops[:3]:
            self.phone.command('append', did, op)
        self.mesh.net.fault('duplicate')
        self.mesh.connect(self.phone, self.desk)
        self.assertEqual(len(self.desk.ops(did)), 3)
        for op in ops[3:]:
            self.phone.command('append', did, op)
        self.mesh.net.fault('drop_response')
        with self.assertRaises(DrawSyncError):
            self.mesh.sync(self.phone, self.desk)            # Applied on desktop, answer lost.
        self.mesh.sync(self.phone, self.desk)                # Resend: duplicates, no double effect.
        self.assertEqual([op['id'] for op in self.desk.ops(did)], [op['id'] for op in ops])
        # Desktop → phone: held requests delivered in reverse order.
        later = [stroke([5, 200, 250, 210], color='#43a047'), stroke([5, 250, 250, 260], color='#8e24aa')]
        self.mesh.net.hold = True
        for op in later:
            self.desk.service.append(did, op)
            with self.assertRaises(DrawSyncError):
                self.mesh.sync(self.desk, self.phone)
        self.mesh.net.hold = False
        self.mesh.release(order=[1, 0])
        self.mesh.settle([self.desk, self.phone])
        self.converged(did)
        self.assertEqual(len(self.phone.command('since', did, 0)['records']), 1 + len(ops) + len(later))

    def test_force_quit_before_ack_resends_exactly_once(self):
        did = self.phone.command('create', 'Force quit', 300, 300, '#ffffff')['drawing_id']
        op = stroke([1, 1, 99, 99])
        self.phone.command('append', did, op)
        self.mesh.net.disconnect(self.desk, self.phone)
        self.phone.restart()                                  # Offline, unsynced edit, SIGKILL.
        self.assertEqual(self.phone.command('state', did)['ops'], [op['id']])
        self.assertEqual(self.phone.pending(self.desk.id), 2)
        self.mesh.net.reconnect(self.desk, self.phone)
        self.mesh.net.fault('drop_response')
        with self.assertRaises(DrawSyncError):
            self.mesh.sync(self.phone, self.desk)             # Delivered, answer lost...
        self.phone.restart()                                  # ...and the phone is killed before the ACK.
        self.assertEqual(self.phone.pending(self.desk.id), 2)  # Durable outbox: cursor never advanced.
        self.mesh.connect(self.phone, self.desk)
        self.converged(did)
        self.assertEqual(self.phone.pending(self.desk.id), 0)
        with self.desk.service.store.transaction(read_only=True) as db:
            count = db.execute('SELECT COUNT(*) FROM draw_records WHERE drawing_id=?', (did,)).fetchone()[0]
        self.assertEqual(count, 2)                            # No duplicate stroke.

    def test_conflicts_converge_deterministically(self):
        did = self.desk.service.create('Conflicts', 300, 300)['drawing_id']
        self.desk.service.append(did, stroke([0, 150, 300, 150], width=10))
        self.mesh.connect(self.desk, self.phone)
        self.mesh.net.disconnect(self.desk, self.phone)
        # Phone erases where the desktop draws; phone clears while the desktop draws;
        # both change background and title; same-area red/blue strokes.
        self.phone.command('append', did, erase([150, 0, 150, 300], width=40))
        self.desk.service.append(did, stroke([140, 0, 160, 300], color='#43a047', width=12))
        self.phone.command('append', did, background('transparent'))
        self.desk.service.append(did, background('#ffffff'))
        self.phone.command('rename', did, 'Phone title')
        self.desk.service.rename(did, 'Desktop title')
        self.phone.command('append', did, stroke([20, 20, 80, 80], color='#1e63e9'))
        self.desk.service.append(did, stroke([20, 20, 80, 80], color='#e53935'))
        self.phone.command('append', did, clear())
        self.desk.service.append(did, stroke([0, 0, 300, 300], color='#8e24aa'))
        self.mesh.net.reconnect(self.desk, self.phone)
        self.mesh.settle([self.desk, self.phone])
        first = self.converged(did)
        for _ in range(3):   # No oscillation.
            self.mesh.connect(self.desk, self.phone)
            self.assertEqual(self.converged(did), first)
        self.assertEqual(len(first['ops']), 9)
        # The outcome is the canonical order: the greatest meta/background record wins.
        with self.desk.service.store.transaction(read_only=True) as db:
            title_row = db.execute("SELECT body FROM draw_records WHERE drawing_id=? AND kind='meta' ORDER BY sort_key DESC LIMIT 1",
                                   (did,)).fetchone()
        self.assertEqual(first['title'], json.loads(title_row[0])['body']['value'])

    def test_three_replicas_desktop_phone_and_third(self):
        third = self.mesh.desktop('third')
        self.mesh.pair(self.phone, third)          # third ↔ phone ↔ desktop (no desktop↔third link)
        did = self.desk.service.create('Three', 300, 300)['drawing_id']
        self.desk.service.append(did, stroke([1, 1, 50, 50]))
        self.mesh.settle([self.desk, self.phone, third])
        third.service.append(did, stroke([60, 60, 90, 90], color='#e53935'))
        self.phone.command('append', did, stroke([100, 100, 150, 150], color='#1e63e9'))
        self.mesh.settle([self.desk, self.phone, third])
        state = self.converged(did, [self.desk, self.phone, third])
        self.assertEqual(len(state['ops']), 3)     # A → phone → C forwarding works both ways.

    def test_seeded_random_histories_converge_across_three_replicas(self):
        phone2 = self.mesh.phone('phone2')
        devices = [self.desk, self.phone, phone2]
        self.mesh.pair(self.phone, phone2)
        self.mesh.pair(self.desk, phone2)
        for seed in range(4):
            rng = random.Random(seed)
            with self.subTest(seed=seed):
                did = self.desk.service.create(f'Random {seed}', 200, 200)['drawing_id']
                self.mesh.settle(devices)
                for step in range(30):
                    device = rng.choice(devices)
                    if rng.random() < 0.25:
                        a, b = rng.sample(devices, 2)
                        self.mesh.net.disconnect(a, b) if self.mesh.net.online(a, b) else self.mesh.net.reconnect(a, b)
                    kind = rng.choice(['stroke', 'stroke', 'erase', 'clear', 'background', 'undo', 'redo', 'rename', 'trash'])
                    self.apply_random(device, did, kind, rng)
                    if rng.random() < 0.3:
                        a, b = rng.sample(devices, 2)
                        try:
                            self.mesh.sync(a, b)
                        except DrawSyncError:
                            pass
                for a in devices:
                    for b in devices:
                        self.mesh.net.reconnect(a, b)
                self.mesh.settle(devices)
                state = self.converged(did, devices)
                self.assertEqual(state, state_of(phone2, did))
                pixels = {hashlib.sha256(base64.b64decode(p.command('render', did)['data'])).hexdigest() for p in (self.phone, phone2)}
                self.assertEqual(len(pixels), 1, 'phone replicas render different pixels')

    def apply_random(self, device, did, kind, rng):
        color = rng.choice(['#e53935', '#1e63e9', '#43a047', '#000000'])
        points = [round(rng.uniform(0, 200), 2) for _ in range(6)]
        phone = isinstance(device, SwiftPhone)
        try:
            if kind == 'stroke':
                op = stroke(points, color=color, width=rng.choice([2, 8, 20]), opacity=rng.choice([1, 0.5]))
                device.command('append', did, op) if phone else device.service.append(did, op)
            elif kind == 'erase':
                op = erase(points, width=rng.choice([10, 30]))
                device.command('append', did, op) if phone else device.service.append(did, op)
            elif kind == 'clear':
                device.command('append', did, clear()) if phone else device.service.append(did, clear())
            elif kind == 'background':
                op = background(rng.choice(['#ffffff', 'transparent']))
                device.command('append', did, op) if phone else device.service.append(did, op)
            elif kind in ('undo', 'redo'):
                device.command(kind, did) if phone else getattr(device.service, kind)(did)
            elif kind == 'rename':
                title = rng.choice(['Alpha', 'Beta', 'Gamma'])
                device.command('rename', did, title) if phone else device.service.rename(did, title)
            elif kind == 'trash':
                trashed = (device.command('get', did) if phone else device.service.get(did))['trashed']
                name = 'restore' if trashed else 'trash'
                device.command(name, did) if phone else getattr(device.service, name)(did)
        except (PhoneError, Exception) as failure:   # Editing a trashed drawing is refused; that is expected.
            if 'trash' not in str(failure).lower() and 'Recently Deleted' not in str(failure):
                raise

    # --- tombstones -----------------------------------------------------------------------
    def test_stale_offline_phone_cannot_resurrect_a_purged_drawing(self):
        did = self.desk.service.create('Purge me', 200, 200)['drawing_id']
        self.desk.service.append(did, stroke([1, 1, 9, 9]))
        self.mesh.connect(self.desk, self.phone)
        self.mesh.net.disconnect(self.desk, self.phone)
        self.phone.command('append', did, stroke([5, 5, 50, 50]))       # Stale phone keeps editing offline.
        self.phone.command('rename', did, 'Still here?')
        self.desk.service.trash(did)
        self.desk.service.purge(did)
        self.mesh.net.reconnect(self.desk, self.phone)
        self.mesh.settle([self.desk, self.phone])
        self.assertTrue(self.desk.service.is_purged(did))
        self.assertTrue(self.phone.command('is_purged', did))
        self.assertNotIn(did, [d['drawing_id'] for d in self.phone.drawings()])
        # And the reverse: a phone purge beats a stale desktop.
        other = self.phone.command('create', 'Phone purge', 100, 100, '#ffffff')['drawing_id']
        self.mesh.settle([self.desk, self.phone])
        self.mesh.net.disconnect(self.desk, self.phone)
        self.desk.service.append(other, stroke([1, 1, 2, 2]))
        self.phone.command('trash', other)
        self.phone.command('purge', other)
        self.mesh.net.reconnect(self.desk, self.phone)
        self.mesh.settle([self.desk, self.phone])
        self.assertTrue(self.desk.service.is_purged(other))
        self.assertNotIn(other, [d['drawing_id'] for d in self.desk.drawings()])

    def test_trash_and_restore_sync_both_ways(self):
        did = self.phone.command('create', 'Trash', 100, 100, '#ffffff')['drawing_id']
        self.mesh.settle([self.desk, self.phone])
        self.phone.command('trash', did)
        self.mesh.settle([self.desk, self.phone])
        self.assertTrue(self.desk.service.get(did)['trashed'])
        self.desk.service.restore(did)
        self.mesh.settle([self.desk, self.phone])
        self.assertFalse(self.phone.command('get', did)['trashed'])

    # --- images -----------------------------------------------------------------------------
    def test_phone_import_strips_exif_gps_applies_orientation_and_desktop_accepts_it(self):
        did = self.phone.command('create', 'Image', 400, 300, '#ffffff')['drawing_id']
        source = jpeg_with_exif_gps(64, 32)
        imported = self.phone.command('import', did, base64.b64encode(source).decode('ascii'))
        data = base64.b64decode(self.phone.command('asset', imported['asset_id']))
        self.assertEqual(hashlib.sha256(data).hexdigest(), imported['asset_id'])
        self.assertEqual(assets.validate(data)[1:], ('image/jpeg', 32, 64))   # Orientation 6 applied: 32 × 64.
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            exif = image.getexif()
            self.assertNotIn(0x8825, exif)                     # No GPS
            self.assertNotIn(0x010F, exif)                     # No camera make
            self.assertNotIn(0x0110, exif)                     # No camera model
            self.assertNotIn(0x0132, exif)                     # No timestamp
            self.assertIn(exif.get(0x0112, 1), (1,))           # No rotation left to apply
            rgb = image.convert('RGB')
            # Rotated 90° clockwise: the red (left) half is now on top.
            self.assertGreater(rgb.getpixel((16, 8))[0], 180)
            self.assertGreater(rgb.getpixel((16, 56))[2], 180)
        for marker in (b'GPS', b'SyntheticCam', b'Model Fixture', b'2026:09:30', b'Exif', b'Photoshop'):
            self.assertNotIn(marker, data)
        op = imported['edit']['record']['body']
        self.assertEqual((op['x'], op['y'], op['width'], op['height']), (184, 118, 32, 64))
        # The asset and operation reach the desktop, which stores it after its own checks.
        self.mesh.settle([self.desk, self.phone])
        self.assertEqual(self.desk.service.asset_info(imported['asset_id'])['size'], len(data))
        self.assertEqual(self.desk.ops(did)[0]['asset_id'], imported['asset_id'])

    def test_png_transparency_and_oversized_placement(self):
        did = self.phone.command('create', 'PNG', 400, 300, 'transparent')['drawing_id']
        big = png(1000, 500, (0, 200, 0, 255), transparent_corner=True)
        imported = self.phone.command('import', did, base64.b64encode(big).decode('ascii'))
        op = imported['edit']['record']['body']
        self.assertEqual((op['width'], op['height']), (360, 180))       # Scaled to 90 % of the canvas, aspect kept.
        self.assertEqual((op['x'], op['y']), (20, 60))
        data = base64.b64decode(self.phone.command('asset', imported['asset_id']))
        self.assertEqual(assets.validate(data)[1:], ('image/png', 360, 180))
        for chunk in (b'eXIf', b'tEXt', b'iTXt', b'zTXt', b'tIME'):
            self.assertNotIn(chunk, data)
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.convert('RGBA').getpixel((10, 10))[3], 0)      # Transparent corner kept.
            self.assertEqual(image.convert('RGBA').getpixel((300, 150)), (0, 200, 0, 255))
        small = png(20, 10, (200, 0, 0, 255))
        op2 = self.phone.command('import', did, base64.b64encode(small).decode('ascii'))['edit']['record']['body']
        self.assertEqual((op2['width'], op2['height'], op2['x'], op2['y']), (20, 10, 190, 145))   # Never upscaled.

    def test_bad_images_are_refused(self):
        did = self.phone.command('create', 'Bad', 100, 100, '#ffffff')['drawing_id']
        for data, code in ((b'not an image', 'unsupported_image'), (png(10, 10)[:40], 'invalid_image'),
                           (b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'unsupported_image')):
            with self.subTest(code=code), self.assertRaises(PhoneError) as caught:
                self.phone.command('import', did, base64.b64encode(data).decode('ascii'))
            self.assertIn(caught.exception.args[0], ('unsupported_image', 'invalid_image'))
        # Oversized header (100000 × 10 PNG) is refused before any decode.
        header = bytearray(png(10, 10))
        header[16:20] = (100000).to_bytes(4, 'big')
        with self.assertRaises(PhoneError) as caught:
            self.phone.command('import', did, base64.b64encode(bytes(header)).decode('ascii'))
        self.assertEqual(caught.exception.args[0], 'image_too_large')
        with self.assertRaises(PhoneError):
            self.phone.command('store_asset', base64.b64encode(bytes(header)).decode('ascii'))
        self.assertEqual(self.phone.command('ops', did), [])

    def test_images_sync_by_hash_with_placeholder_first_both_directions(self):
        did = self.desk.service.create('Images', 300, 300)['drawing_id']
        data = png(40, 20, (255, 0, 0, 255))
        info = self.desk.service.store_asset(data)
        self.desk.service.append(did, {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': info['asset_id'],
                                       'x': 10, 'y': 10, 'width': 40, 'height': 20, 'opacity': 1})
        self.desk.service.append(did, stroke([0, 30, 300, 30], color='#000000', width=4))
        self.mesh.net.block_assets = True
        with self.assertRaises(DrawSyncError):
            self.mesh.sync(self.desk, self.phone)                # Records arrive; the image bytes do not (yet).
        # Operation first: the phone wants the asset and keeps other strokes visible.
        self.assertEqual(self.phone.wants(), [info['asset_id']])
        rendered = self.phone.command('render', did)
        self.assertEqual(rendered['missing'], [info['asset_id']])
        with self.assertRaises(PhoneError) as caught:
            self.phone.command('export', did, 'png')             # Export refuses while the image is arriving.
        self.assertEqual(caught.exception.args[0], 'asset_not_found')
        self.mesh.net.block_assets = False
        self.mesh.settle([self.desk, self.phone])
        self.assertEqual(self.phone.wants(), [])
        stored = base64.b64decode(self.phone.command('asset', info['asset_id']))
        self.assertEqual(stored, data)                            # Exact bytes, verified by SHA-256.
        png_out = base64.b64decode(self.phone.command('export', did, 'png')['data'])
        from PIL import Image
        with Image.open(io.BytesIO(png_out)) as image:
            self.assertEqual(image.size, (300, 300))
            self.assertEqual(image.convert('RGBA').getpixel((20, 15)), (255, 0, 0, 255))
        # Phone → desktop, and duplicating on the phone never transfers the bytes again.
        imported = self.phone.command('import', did, base64.b64encode(png(30, 30, (0, 0, 255, 255))).decode('ascii'))
        self.mesh.settle([self.desk, self.phone])
        self.assertIsNotNone(self.desk.service.asset_info(imported['asset_id']))
        copy = self.phone.command('duplicate', did)['drawing_id']
        before = sum(1 for op, _ in self.mesh.bytes_sent if op == 'asset')
        self.mesh.settle([self.desk, self.phone])
        after = sum(1 for op, _ in self.mesh.bytes_sent if op == 'asset')
        self.assertEqual(before, after)
        self.assertEqual(len(self.desk.ops(copy)), len(self.phone.ops(copy)))
        # Receiving an asset the phone already has answers "exists".
        request = protocol.encode_request(str(uuid.uuid4()), self.desk.id, self.phone.id, 'asset', {
            'epoch': self.desk.service.epoch(), 'transfer_id': str(uuid.uuid4()), 'asset_id': info['asset_id'], 'mime': 'image/png',
            'width': 40, 'height': 20, 'total_bytes': len(data), 'count': 1, 'index': 0,
            'data': base64.b64encode(data).decode('ascii')}, int(time.time()))
        answer = protocol.decode_response(self.phone.handle(self.desk.id, request))
        self.assertEqual(answer['result']['status'], 'exists')

    def test_interrupted_asset_transfer_phone_killed_mid_transfer(self):
        did = self.desk.service.create('Big image', 1200, 1200)['drawing_id']
        from PIL import Image
        noise = Image.effect_noise((1000, 1000), 90).convert('RGB')
        out = io.BytesIO()
        noise.save(out, format='PNG')
        data = out.getvalue()
        self.assertGreater(len(data), 3 * protocol.LIMITS['asset_chunk_bytes'])
        info = self.desk.service.store_asset(data)
        self.desk.service.append(did, {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': info['asset_id'],
                                       'x': 100, 'y': 100, 'width': 1000, 'height': 1000, 'opacity': 1})
        self.mesh.net.kill_after_chunks = 2                     # Phone SIGKILLed after two accepted chunks.
        with self.assertRaises(DrawSyncError):
            self.mesh.connect(self.desk, self.phone)
        self.assertIsNone(self.phone.command('asset', info['asset_id']))   # No partial bytes stored.
        self.assertEqual(self.phone.command('staged'), 0)
        self.assertEqual(self.phone.wants(), [info['asset_id']])
        self.assertEqual(self.phone.command('render', did)['missing'], [info['asset_id']])
        self.mesh.settle([self.desk, self.phone])                # Transfer restarts and completes later.
        stored = base64.b64decode(self.phone.command('asset', info['asset_id']))
        self.assertEqual(hashlib.sha256(stored).hexdigest(), info['asset_id'])

    def test_corrupted_asset_transfer_is_refused_and_nothing_kept(self):
        data = png(20, 20)
        asset_id = hashlib.sha256(data).hexdigest()
        corrupt = bytearray(data)
        corrupt[-20] ^= 0xFF
        request = protocol.encode_request(str(uuid.uuid4()), self.desk.id, self.phone.id, 'asset', {
            'epoch': self.desk.service.epoch(), 'transfer_id': str(uuid.uuid4()), 'asset_id': asset_id, 'mime': 'image/png',
            'width': 20, 'height': 20, 'total_bytes': len(data), 'count': 1, 'index': 0,
            'data': base64.b64encode(bytes(corrupt)).decode('ascii')}, int(time.time()))
        answer = protocol.decode_response(self.phone.handle(self.desk.id, request))
        self.assertEqual(answer['result'], {'epoch': answer['result']['epoch'], 'status': 'rejected', 'error': 'checksum_mismatch'})
        self.assertIsNone(self.phone.command('asset', asset_id))

    # --- permission, epochs, strictness ------------------------------------------------------
    def test_permission_off_sends_nothing_then_allow_catches_up(self):
        self.desk.allowed.discard(self.phone.id)                 # Desktop: Draw sync Off for this phone.
        did = self.phone.command('create', 'Pending', 100, 100, '#ffffff')['drawing_id']
        self.phone.command('append', did, stroke([1, 1, 50, 50]))
        with self.assertRaises(DrawSyncError) as caught:
            self.mesh.sync(self.phone, self.desk)
        self.assertEqual(str(caught.exception), 'permission_off')
        self.assertEqual(self.desk.drawings(), [])
        self.assertEqual(self.phone.pending(self.desk.id), 2)   # Still waiting on the phone.
        # The phone's own switch Off: it answers the desktop with permission_off and shares nothing.
        self.phone.deny(self.desk.id)
        self.desk.allowed.add(self.phone.id)
        own = self.desk.service.create('Desk only', 100, 100)['drawing_id']
        with self.assertRaises(DrawSyncError):
            self.mesh.sync(self.desk, self.phone)
        self.assertNotIn(own, [d['drawing_id'] for d in self.phone.drawings()])
        self.phone.allow(self.desk.id)
        self.mesh.settle([self.desk, self.phone])
        self.assertEqual([op['points'] for op in self.desk.ops(did)], [[1, 1, 50, 50]])
        self.assertIn(own, [d['drawing_id'] for d in self.phone.drawings()])

    def test_store_epoch_changes_reset_cursors_and_offer_again(self):
        did = self.phone.command('create', 'Epoch', 100, 100, '#ffffff')['drawing_id']
        self.phone.command('append', did, stroke([1, 1, 2, 2]))
        self.mesh.connect(self.phone, self.desk)
        self.assertEqual(self.phone.command('peer', self.desk.id)['acked_seq'], 2)
        # The desktop restores an older Draw backup: new epoch, records gone.
        backup = Path(tempfile.mkdtemp()) / 'backup.sqlite3'
        import sqlite3
        with sqlite3.connect(self.desk.path) as source, sqlite3.connect(backup) as copy:
            source.backup(copy)
        with sqlite3.connect(backup) as db:
            db.execute("DELETE FROM draw_records WHERE drawing_id=?", (did,))
            db.execute("DELETE FROM drawings WHERE drawing_id=?", (did,))
            db.execute("UPDATE meta SET value=? WHERE key='epoch'", (str(uuid.uuid4()),))
        shutil.copy(backup, self.desk.path)
        for suffix in ('-wal', '-shm'):
            Path(str(self.desk.path) + suffix).unlink(missing_ok=True)
        self.desk.restart()
        self.mesh.connect(self.phone, self.desk)                # Phone sees the new epoch and offers everything again.
        self.assertEqual([d['drawing_id'] for d in self.desk.drawings()], [did])
        self.converged(did)
        # The phone's own store epoch renews (as after a restore): the desktop re-offers too.
        self.desk.service.append(did, stroke([3, 3, 4, 4]))
        self.mesh.settle([self.desk, self.phone])
        self.phone.command('renew_epoch')
        self.mesh.connect(self.desk, self.phone)
        self.assertEqual(self.desk.engine.peer(self.phone.id)['acked_seq'] > 0, True)
        self.converged(did)

    def test_protocol_bytes_are_strict_on_the_phone(self):
        epoch = self.desk.service.epoch()
        good = json.loads(protocol.encode_request(str(uuid.uuid4()), self.desk.id, self.phone.id, 'hello',
                                                  {'versions': ['olive-draw/1'], 'schemas': [1, 2]}, int(time.time())))
        cases = [
            (dict(good, extra=1), 'malformed_message'),
            (dict(good, protocol_version='olive-draw/9'), 'unsupported_protocol'),
            (dict(good, source_device_id=str(uuid.uuid4())), 'source_mismatch'),
            (dict(good, target_device_id=str(uuid.uuid4())), 'wrong_target'),
            (dict(good, timestamp=good['timestamp'] - 1000, expires_at=good['timestamp'] - 1000 + 60), 'expired_request'),
            (dict(good, operation='drop_tables'), 'malformed_message'),
            (dict(good, arguments={'versions': ['olive-draw/1'], 'schemas': [1, 2], 'x': 1}), 'malformed_message'),
            (dict(good, operation='sync', arguments={'epoch': epoch, 'entries': [{'seq': 1, 'record': {'record_id': 'x'}}] * 257}),
             'payload_too_large'),
        ]
        for value, code in cases:
            with self.subTest(code=code):
                raw = json.dumps(value, separators=(',', ':')).encode('utf-8')
                answer = protocol.decode_response(self.phone.handle(self.desk.id, raw))
                self.assertEqual((answer['state'], answer['error']), ('rejected', code))
        answer = protocol.decode_response(self.phone.handle(self.desk.id, b'{"protocol_version":"olive-draw/1","request_id":1,'))
        self.assertEqual(answer['error'], 'malformed_message')
        # One record the phone cannot accept is refused alone; the rest still apply.
        did = str(uuid.uuid4())
        create = {'record_id': uuid.uuid4().hex, 'drawing_id': did, 'device': self.desk.id, 'lamport': 1, 'kind': 'create',
                  'at': '2026-09-30T10:00:00.000Z',
                  'body': {'width': 100, 'height': 100, 'background': '#ffffff', 'title': 'Mixed', 'created_at': '2026-09-30T10:00:00.000Z'}}
        future_id = uuid.uuid4().hex
        future = {'record_id': future_id, 'drawing_id': did, 'device': self.desk.id, 'lamport': 2, 'kind': 'op',
                  'at': '2026-09-30T10:00:00.000Z', 'body': {'type': 'hologram', 'id': future_id}}
        ok = stroke([1, 1, 2, 2])
        normal = {'record_id': ok['id'], 'drawing_id': did, 'device': self.desk.id, 'lamport': 3, 'kind': 'op',
                  'at': '2026-09-30T10:00:00.000Z', 'body': ok}
        request = protocol.encode_request(str(uuid.uuid4()), self.desk.id, self.phone.id, 'sync', {
            'epoch': epoch, 'entries': [{'seq': 1, 'record': create}, {'seq': 2, 'record': future}, {'seq': 3, 'record': normal}]},
            int(time.time()))
        answer = protocol.decode_response(self.phone.handle(self.desk.id, request))
        self.assertEqual([r['status'] for r in answer['result']['results']], ['applied', 'rejected', 'applied'])
        self.assertEqual(self.phone.command('state', did)['ops'], [ok['id']])

    def test_large_initial_sync_then_small_delta(self):
        did = self.desk.service.create('Large', 1920, 1080)['drawing_id']
        rng = random.Random(5)
        with self.desk.service.store.transaction() as db:
            for i in range(1000):
                points = [round(rng.uniform(0, 1900), 2) for _ in range(160)]
                record = records.make(db, self.desk.id, did, 'op', {k: v for k, v in stroke(points).items() if k != 'id'})
                self.assertEqual(records.insert(db, record), 'applied')
        started = time.monotonic()
        self.mesh.connect(self.desk, self.phone)
        elapsed = time.monotonic() - started
        self.assertEqual(len(self.phone.ops(did)), 1000)
        syncs = [raw for op, raw in self.mesh.bytes_sent if op == 'sync']
        self.assertGreaterEqual(len(syncs), 2)
        self.assertTrue(all(len(raw) <= protocol.LIMITS['max_frame_bytes'] for raw in syncs))
        self.mesh.bytes_sent.clear()
        self.phone.command('append', did, stroke([1, 2, 3, 4, 5, 6]))
        self.mesh.settle([self.desk, self.phone])
        delta = [raw for op, raw in self.mesh.bytes_sent if op == 'sync']
        self.assertEqual(len(delta), 1)
        self.assertLess(len(delta[0]), 1200)
        print(f'\n[draw-phone] 1,000-stroke initial sync desktop→Swift: {elapsed:.2f} s; one-stroke delta {len(delta[0])} bytes')

    def test_rendered_pixels_at_key_coordinates(self):
        did = self.desk.service.create('Pixels', 200, 100)['drawing_id']
        info = self.desk.service.store_asset(png(20, 20, (0, 128, 255, 255)))
        ops = [stroke([10, 50, 190, 50], color='#e53935', width=20),
               erase([100, 0, 100, 100], width=20),
               {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': info['asset_id'], 'x': 150, 'y': 70, 'width': 20, 'height': 20, 'opacity': 1},
               stroke([20, 10, 60, 10], color='#1e63e9', width=6, opacity=0.5)]
        for op in ops:
            self.desk.service.append(did, op)
        self.mesh.connect(self.desk, self.phone)
        from PIL import Image
        opaque = Image.open(io.BytesIO(base64.b64decode(self.phone.command('render', did)['data']))).convert('RGBA')
        self.assertEqual(opaque.getpixel((50, 50)), (229, 57, 53, 255))      # stroke
        self.assertEqual(opaque.getpixel((100, 50)), (255, 255, 255, 255))   # eraser cut shows the background
        self.assertEqual(opaque.getpixel((5, 90)), (255, 255, 255, 255))     # background
        self.assertEqual(opaque.getpixel((160, 80)), (0, 128, 255, 255))     # image colour
        r, g, b, a = opaque.getpixel((40, 10))                               # 50 % blue over white
        self.assertTrue(abs(r - 143) <= 2 and abs(g - 177) <= 2 and b >= 243 and a == 255, (r, g, b, a))
        self.desk.service.append(did, background('transparent'))
        self.mesh.settle([self.desk, self.phone])
        clear_png = Image.open(io.BytesIO(base64.b64decode(self.phone.command('export', did, 'png')['data']))).convert('RGBA')
        self.assertEqual(clear_png.getpixel((5, 90))[3], 0)                   # transparent area stays transparent
        self.assertEqual(clear_png.getpixel((100, 50))[3], 0)
        jpeg = Image.open(io.BytesIO(base64.b64decode(self.phone.command('export', did, 'jpeg')['data']))).convert('RGB')
        self.assertTrue(all(c >= 245 for c in jpeg.getpixel((5, 90))))       # JPEG: white matte, never black
        self.assertTrue(all(abs(x - y) <= 12 for x, y in zip(jpeg.getpixel((50, 50)), (229, 57, 53))))


if __name__ == '__main__':
    unittest.main()
