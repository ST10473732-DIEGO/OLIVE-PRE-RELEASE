"""OLIVE Draw sync (olive-draw/1): convergence, undo, tombstones, assets, faults."""
import base64
import hashlib
import io
import json
import random
import unittest
import uuid
from pathlib import Path

from olive.draw import protocol
from olive.draw.sync_engine import DrawSyncError
from olive.services.backup_service import BackupService
from tests.draw_sync_fixture import SimDrawNetwork, background, clear, erase, png, render, stroke


class DrawSyncTests(unittest.TestCase):
    def setUp(self):
        self.net = SimDrawNetwork()
        self.a = self.net.device('a')
        self.b = self.net.device('b')
        self.net.pair(self.a, self.b)

    def tearDown(self):
        self.net.close()

    def converged(self, did, devices=None):
        devices = devices or [self.a, self.b]
        states = [d.state(did) for d in devices]
        for state in states[1:]:
            self.assertEqual(state, states[0])
        hashes = {render(d, did) for d in devices}
        self.assertEqual(len(hashes), 1, 'rendered pixels differ between replicas')
        return states[0]

    def test_create_and_strokes_both_directions(self):
        drawing = self.a.service.create('Shared', 400, 300)
        did = drawing['drawing_id']
        red = stroke([10, 10, 200, 200], color='#e53935', width=8)
        self.a.service.append(did, red)
        self.net.connect(self.a, self.b)
        self.assertEqual(self.b.drawings()[0]['title'], 'Shared')
        self.assertEqual([op['id'] for op in self.b.ops(did)], [red['id']])
        blue = stroke([300, 20, 0.5, 50, 250, 0.2, 60, 260, 0.9], color='#1e63e9', width=20, pressure=True)
        self.b.service.append(did, blue)
        self.net.settle()
        state = self.converged(did)
        self.assertEqual(state['ops'], [red['id'], blue['id']])
        self.assertEqual(self.a.ops(did)[1]['points'], blue['points'])   # Pressure values travel unchanged.
        # B's own drawing reaches A too.
        mine = self.b.service.create('From B', 200, 200)
        self.net.settle()
        self.assertIn('From B', [d['title'] for d in self.a.drawings()])
        self.assertTrue(any(topic == 'draw.changed' for topic, _ in self.a.events))

    def test_eraser_clear_background_rename_trash_restore_purge(self):
        did = self.a.service.create('Doc', 200, 200)['drawing_id']
        self.a.service.append(did, stroke([10, 10, 190, 190]))
        self.a.service.append(did, erase([100, 0, 100, 200], width=30))
        self.a.service.append(did, background('transparent'))
        self.net.connect(self.a, self.b)
        state = self.converged(did)
        self.assertEqual(state['background'], 'transparent')
        self.b.service.append(did, clear())
        self.b.service.rename(did, 'Renamed on B')
        self.net.settle()
        state = self.converged(did)
        self.assertEqual(state['title'], 'Renamed on B')
        self.assertEqual(self.a.ops(did)[-1]['type'], 'clear')
        self.a.service.trash(did)
        self.net.settle()
        self.assertTrue(self.b.service.get(did)['trashed'])
        self.b.service.restore(did)
        self.net.settle()
        self.assertFalse(self.a.service.get(did)['trashed'])
        self.a.service.trash(did)
        self.a.service.purge(did)
        self.net.settle()
        self.assertTrue(self.b.service.is_purged(did))
        self.assertEqual(self.b.drawings('trash'), [])

    def test_duplicate_delivery_lost_ack_and_out_of_order(self):
        did = self.a.service.create('Faults', 300, 300)['drawing_id']
        ops = [stroke([i, i, i + 50, i + 20]) for i in range(0, 60, 10)]
        for op in ops[:3]:
            self.a.service.append(did, op)
        self.net.fault('duplicate')
        self.net.connect(self.a, self.b)
        self.assertEqual(len(self.b.ops(did)), 3)
        for op in ops[3:]:
            self.a.service.append(did, op)
        self.net.fault('drop_response')
        with self.assertRaises(DrawSyncError):
            self.net.sync(self.a, self.b)          # Applied on B, answer lost.
        self.net.sync(self.a, self.b)              # Resend: duplicates, no double effect.
        self.assertEqual([op['id'] for op in self.b.ops(did)], [op['id'] for op in ops])
        # Held requests delivered in reverse order converge to the same state.
        later = [stroke([5, 200, 250, 210], color='#43a047'), stroke([5, 250, 250, 260], color='#8e24aa')]
        self.net.hold = True
        for op in later:
            self.a.service.append(did, op)
            with self.assertRaises(DrawSyncError):
                self.net.sync(self.a, self.b)
        self.net.hold = False
        self.net.release(order=[1, 0])
        self.net.settle()
        self.converged(did)
        with self.b.service.store.transaction(read_only=True) as db:
            count = db.execute('SELECT COUNT(*) FROM draw_records WHERE drawing_id=?', (did,)).fetchone()[0]
        self.assertEqual(count, 1 + len(ops) + len(later))   # Exactly one of each record.

    def test_restart_before_ack_resends_safely(self):
        did = self.a.service.create('Restart', 300, 300)['drawing_id']
        self.a.service.append(did, stroke([1, 1, 99, 99]))
        self.net.fault('drop_response')
        with self.assertRaises(DrawSyncError):
            self.net.connect(self.a, self.b)
        self.a.restart()                             # Cursor was never advanced: durable outbox.
        self.b.restart()
        self.assertEqual(self.a.engine.pending(self.b.id), 2)
        self.net.connect(self.a, self.b)
        self.converged(did)
        self.assertEqual(self.a.engine.pending(self.b.id), 0)

    def test_offline_edits_on_both_are_both_kept(self):
        did = self.a.service.create('Offline', 300, 300)['drawing_id']
        self.net.connect(self.a, self.b)
        self.net.disconnect(self.a, self.b)
        a_ops = [stroke([10, 10, 290, 10], color='#e53935'), stroke([10, 30, 290, 30], color='#e53935')]
        b_ops = [stroke([10, 20, 290, 20], color='#1e63e9')]
        for op in a_ops:
            self.a.service.append(did, op)
        for op in b_ops:
            self.b.service.append(did, op)
        with self.assertRaises(DrawSyncError):
            self.net.sync(self.a, self.b)
        self.net.reconnect(self.a, self.b)
        self.net.settle()
        state = self.converged(did)
        self.assertEqual(sorted(state['ops']), sorted(op['id'] for op in a_ops + b_ops))

    def test_concurrent_conflicts_converge_deterministically(self):
        did = self.a.service.create('Conflicts', 300, 300)['drawing_id']
        self.a.service.append(did, stroke([0, 150, 300, 150], width=10))
        self.net.connect(self.a, self.b)
        self.net.disconnect(self.a, self.b)
        # Same area: A erases, B draws through it; A clears, B draws; both change
        # background and title.
        self.a.service.append(did, erase([150, 0, 150, 300], width=40))
        self.b.service.append(did, stroke([140, 0, 160, 300], color='#43a047', width=12))
        self.a.service.append(did, background('transparent'))
        self.b.service.append(did, background('#ffffff'))
        self.a.service.rename(did, 'A title')
        self.b.service.rename(did, 'B title')
        self.a.service.append(did, clear())
        self.b.service.append(did, stroke([0, 0, 300, 300], color='#8e24aa'))
        self.net.reconnect(self.a, self.b)
        self.net.settle()
        first = self.converged(did)
        # No oscillation: further rounds change nothing on either side.
        for _ in range(3):
            self.net.connect(self.a, self.b)
            self.assertEqual(self.converged(did), first)
        self.assertIn(first['title'], ('A title', 'B title'))
        # Every edit is kept (the first stroke plus three from each side); Clear
        # hides earlier ink in the picture, and Undo of the Clear brings it back.
        self.assertEqual(len(first['ops']), 7)

    def test_local_origin_undo_and_redo(self):
        did = self.a.service.create('Undo', 300, 300)['drawing_id']
        red = stroke([10, 10, 290, 10], color='#e53935')
        self.a.service.append(did, red)
        self.net.connect(self.a, self.b)
        blue = stroke([10, 20, 290, 20], color='#1e63e9')
        self.b.service.append(did, blue)
        self.net.settle()
        green = stroke([10, 30, 290, 30], color='#43a047')
        self.a.service.append(did, green)
        self.net.settle()
        # Desktop Undo removes desktop's green, not the phone's blue that arrived in between.
        self.a.service.undo(did)
        self.net.settle()
        self.assertEqual(self.converged(did)['ops'], [red['id'], blue['id']])
        # A remote edit between Undo and Redo does not disturb Redo.
        purple = stroke([10, 40, 290, 40], color='#8e24aa')
        self.b.service.append(did, purple)
        self.net.settle()
        self.a.service.redo(did)
        self.net.settle()
        self.assertEqual(sorted(self.converged(did)['ops']), sorted([red['id'], blue['id'], green['id'], purple['id']]))
        # B's Undo only ever touches B's own edits.
        self.b.service.undo(did)
        self.b.service.undo(did)
        self.b.service.undo(did)   # Nothing more of B's to undo.
        self.net.settle()
        self.assertEqual(self.converged(did)['ops'], [red['id'], green['id']])
        # A new edit after Undo clears that device's Redo.
        self.assertEqual(self.b.service.redo(did)['history']['redo'], 1)
        self.b.service.append(did, stroke([1, 1, 2, 2]))
        self.assertIsNone(self.b.service.redo(did)['record'])
        # A visibility record claiming someone else's operation is ignored everywhere.
        with self.b.service.store.transaction() as db:
            from olive.draw import records
            forged = records.make(db, self.b.id, did, 'visibility', {'target': red['id'], 'hidden': True})
            self.assertEqual(records.insert(db, forged), 'applied')
        self.net.settle()
        self.assertIn(red['id'], self.converged(did)['ops'])

    def test_undo_history_survives_restart(self):
        did = self.a.service.create('Persist', 200, 200)['drawing_id']
        ops = [stroke([1, i, 100, i]) for i in range(1, 4)]
        for op in ops:
            self.a.service.append(did, op)
        self.a.service.undo(did)
        self.a.restart()
        self.assertEqual(self.a.service.redo(did)['history'], {'undo': 3, 'redo': 0})
        self.a.service.undo(did)
        self.a.service.undo(did)
        self.assertEqual([op['id'] for op in self.a.ops(did)], [ops[0]['id']])

    def test_three_replicas_with_partial_connectivity(self):
        c = self.net.device('c')
        self.net.pair(self.b, c)          # A <-> B <-> C; A and C never talk directly.
        did = self.a.service.create('Three', 300, 300)['drawing_id']
        self.net.settle()
        self.assertEqual(c.drawings()[0]['drawing_id'], did)   # Relayed through B.
        self.net.disconnect(self.a, self.b)
        self.a.service.append(did, stroke([1, 1, 50, 50], color='#e53935'))
        self.b.service.append(did, stroke([1, 60, 50, 110], color='#1e63e9'))
        c.service.append(did, stroke([1, 120, 50, 170], color='#43a047'))
        c.service.rename(did, 'C named it')
        self.net.settle()
        self.net.reconnect(self.a, self.b)
        self.net.settle()
        state = self.converged(did, [self.a, self.b, c])
        self.assertEqual(len(state['ops']), 3)
        self.assertEqual(state['title'], 'C named it')

    def test_purge_is_never_resurrected_by_a_stale_peer(self):
        did = self.a.service.create('Doomed', 200, 200)['drawing_id']
        self.a.service.append(did, stroke([1, 1, 9, 9]))
        self.net.connect(self.a, self.b)
        self.net.disconnect(self.a, self.b)
        self.a.service.trash(did)
        self.a.service.purge(did)
        self.b.service.append(did, stroke([5, 5, 50, 50]))    # Stale device keeps editing offline.
        self.b.service.rename(did, 'Still here?')
        self.net.reconnect(self.a, self.b)
        self.net.settle()
        for device in (self.a, self.b):
            self.assertTrue(device.service.is_purged(did))
            self.assertNotIn(did, [d['drawing_id'] for d in device.drawings() + device.drawings('trash')])
        # A third device that only knew the old drawing cannot bring it back either.
        c = self.net.device('c')
        self.net.pair(c, self.b)
        with c.service.store.transaction() as db:
            from olive.draw import records
            ghost = records.make(db, c.id, did, 'create', {'width': 10 * 20, 'height': 200, 'background': '#ffffff',
                                                          'title': 'Ghost', 'created_at': '2026-01-01T00:00:00.000Z'})
            records.insert(db, ghost)
        self.net.settle()
        self.assertTrue(c.service.is_purged(did))
        self.assertTrue(self.b.service.is_purged(did))

    def test_images_sync_by_content_hash_with_placeholder_first(self):
        did = self.a.service.create('Photo', 400, 300)['drawing_id']
        data = png(64, 48, (255, 0, 0, 255), transparent_corner=True)
        info = self.a.service.store_asset(data)
        self.assertEqual(info['asset_id'], hashlib.sha256(data).hexdigest())
        image = {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': info['asset_id'], 'x': 100, 'y': 50,
                 'width': 64, 'height': 48, 'opacity': 1}
        self.a.service.append(did, image)
        self.a.service.append(did, stroke([0, 0, 400, 300]))
        # Operations arrive first; B shows a placeholder and wants the asset.
        self.net.block_assets = True
        with self.assertRaises(DrawSyncError):
            self.net.sync(self.a, self.b, hello=True)
        self.net.block_assets = False
        self.assertIsNone(self.b.service.asset_info(info['asset_id']))
        self.assertEqual(self.b.engine.wants(), [info['asset_id']])
        self.assertEqual(len(self.b.ops(did)), 2)
        # Next exchange serves the wanted asset; it is not sent again after that.
        self.net.settle()
        self.assertEqual(self.b.service.asset_info(info['asset_id'])['size'], len(data))
        self.converged(did)
        sent = sum(1 for operation, _, _ in self.net.messages if operation == 'asset')
        self.net.settle()
        self.a.service.duplicate(did)
        self.net.settle()
        self.assertEqual(sum(1 for operation, _, _ in self.net.messages if operation == 'asset'), sent)
        with self.b.service.store.transaction(read_only=True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM draw_assets').fetchone()[0], 1)

    def test_interrupted_asset_transfer_restarts_and_never_shows_partial(self):
        did = self.a.service.create('Big', 1000, 1000)['drawing_id']
        rng = random.Random(7)
        from PIL import Image
        noise = Image.frombytes('RGB', (700, 700), bytes(rng.getrandbits(8) for _ in range(700 * 700 * 3)))
        out = io.BytesIO()
        noise.save(out, format='PNG')
        data = out.getvalue()
        self.assertGreater(len(data), protocol.LIMITS['asset_chunk_bytes'] * 3)
        asset = self.a.service.store_asset(data)['asset_id']
        self.a.service.append(did, {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': asset, 'x': 0, 'y': 0,
                                    'width': 700, 'height': 700, 'opacity': 1})
        self.net.kill_after_chunks = 2        # Two chunks accepted, then the receiver dies.
        with self.assertRaises(DrawSyncError):
            self.net.sync(self.a, self.b, hello=True)
        self.assertIsNone(self.b.service.asset_info(asset))    # Nothing partial is ever stored.
        self.assertEqual(self.b.engine.wants(), [asset])       # Still wanted after the restart.
        self.assertEqual(len(self.b.ops(did)), 1)
        self.net.settle()
        self.assertEqual(self.b.service.asset_info(asset)['size'], len(data))
        self.converged(did)
        # A corrupted transfer is refused and nothing is stored.
        fresh = self.net.device('c')
        self.net.pair(self.a, fresh)
        bad = bytearray(data[:protocol.LIMITS['asset_chunk_bytes']])
        bad[100] ^= 0xFF
        chunk = protocol.LIMITS['asset_chunk_bytes']
        arguments = {'epoch': self.a.service.epoch(), 'transfer_id': str(uuid.uuid4()), 'asset_id': asset,
                     'mime': 'image/png', 'width': 700, 'height': 700, 'total_bytes': len(data),
                     'count': -(-len(data) // chunk)}
        send = self.net.sender(self.a, fresh)
        results = [send('asset', dict(arguments, index=i, data=base64.b64encode(
            bytes(bad) if i == 0 else data[i * chunk:(i + 1) * chunk]).decode())) for i in range(arguments['count'])]
        self.assertEqual(results[-1]['status'], 'rejected')
        self.assertEqual(results[-1]['error'], 'checksum_mismatch')
        self.assertIsNone(fresh.service.asset_info(asset))

    def test_permission_off_sends_nothing_then_catches_up(self):
        did = self.a.service.create('Private', 200, 200)['drawing_id']
        self.a.service.append(did, stroke([1, 1, 9, 9]))
        self.b.allowed.discard(self.a.id)               # B has Draw sync Off for A.
        with self.assertRaises(DrawSyncError) as refused:
            self.net.connect(self.a, self.b)
        self.assertEqual(str(refused.exception), 'permission_off')
        self.assertEqual(self.b.drawings(), [])
        self.b.allowed.add(self.a.id)                   # Allow: catch up.
        self.net.connect(self.a, self.b)
        self.converged(did)

    def test_restore_renews_epoch_and_peers_refill_it(self):
        did = self.a.service.create('Backed', 200, 200)['drawing_id']
        self.a.service.append(did, stroke([1, 1, 50, 50]))
        self.net.connect(self.a, self.b)
        root = self.a.path.parent
        backups = BackupService(root)
        archive = backups.create(components={'draw'})
        late = stroke([60, 60, 120, 120], color='#e53935')
        self.a.service.append(did, late)
        self.net.settle()                     # B has the late stroke too.
        self.a.service.rename(did, 'Changed')
        self.net.settle()
        old_epoch = self.a.service.epoch()
        backups.restore(archive, confirmed=True)
        self.a.restart()
        self.assertNotEqual(self.a.service.epoch(), old_epoch)
        self.assertNotIn(late['id'], [op['id'] for op in self.a.ops(did)])
        self.net.connect(self.a, self.b)
        self.net.settle()
        state = self.converged(did)
        self.assertIn(late['id'], state['ops'])       # No silent loss: the peer refilled it.
        self.assertEqual(state['title'], 'Changed')

    def test_protocol_bytes_are_strict(self):
        send = self.net.sender(self.a, self.b)
        with self.assertRaises(DrawSyncError) as unsupported:
            send('hello', {'versions': ['olive-draw/9'], 'schemas': [1]})
        self.assertEqual(str(unsupported.exception), 'unsupported_protocol')
        raw = protocol.encode_request(str(uuid.uuid4()), self.a.id, self.b.id, 'hello',
                                      {'versions': ['olive-draw/1'], 'schemas': [1, 2]}, 0)
        value = json.loads(raw)
        value['extra'] = 1
        self.assertEqual(json.loads(self.net.deliver(self.b, self.a.id, json.dumps(value).encode()))['error'],
                         'malformed_message')
        for arguments in ({'epoch': str(uuid.uuid4()), 'entries': [{'seq': 1}]},
                          {'epoch': 'x', 'entries': []},
                          {'epoch': str(uuid.uuid4()), 'entries': [{'seq': 1, 'record': {}, 'purge': {}}]}):
            with self.assertRaises(DrawSyncError):
                send('sync', arguments)
        # A record B cannot accept is refused alone; the rest of the batch applies.
        did = self.a.service.create('Strict', 100, 100)['drawing_id']
        self.net.connect(self.a, self.b)
        good = {'record_id': uuid.uuid4().hex, 'drawing_id': did, 'device': self.a.id, 'lamport': 9, 'kind': 'op',
                'at': '2026-09-30T10:00:00.000Z', 'body': stroke([1, 1, 2, 2])}
        good['body']['id'] = good['record_id']
        future = dict(good, record_id=uuid.uuid4().hex, body={'type': 'hologram', 'id': 'x' * 32})
        result = send('sync', {'epoch': self.a.service.epoch(), 'entries': [{'seq': 1, 'record': future},
                                                                           {'seq': 2, 'record': good}]})
        self.assertEqual([r['status'] for r in result['results']], ['rejected', 'applied'])

    def test_large_drawing_initial_sync_then_one_stroke_delta(self):
        did = self.a.service.create('Five thousand', 1920, 1080)['drawing_id']
        with self.a.service.store.transaction() as db:
            from olive.draw import records
            for index in range(5000):
                points = []
                for step in range(80):
                    points += [round(100 + (index * 7.31 + step * 3.17) % 1700, 2), round(100 + (index * 3.7 + step * 1.9) % 880, 2)]
                body = stroke(points, width=4)
                body.pop('id')
                records.insert(db, records.make(db, self.a.id, did, 'op', body))
        self.net.connect(self.a, self.b)
        initial = [(op, len(raw), len(resp)) for op, raw, resp in self.net.messages if op == 'sync']
        self.assertEqual(len(self.b.ops(did)), 5000)
        self.net.messages.clear()
        self.a.service.append(did, stroke([10, 10, 20, 20, 30, 15]))
        self.net.settle()
        delta = [(op, len(raw), len(resp)) for op, raw, resp in self.net.messages if op == 'sync']
        self.assertEqual(len(delta), 1)
        self.assertLess(delta[0][1], 2000)
        self.converged(did)
        print(f'\nDraw sync 5,000 strokes: initial {len(initial)} sync requests, '
              f'{sum(r for _, r, _ in initial) / 1e6:.2f} MB sent; one new stroke: {len(delta)} request, '
              f'{delta[0][1]} bytes', end='')


class RandomizedConvergenceTests(unittest.TestCase):
    def history(self, device, did, rng, count):
        mine = []
        for _ in range(count):
            roll = rng.random()
            if roll < 0.45:
                points = [round(rng.uniform(0, 200), 2) for _ in range(2 * rng.randint(1, 6))]
                op = stroke(points, color=rng.choice(['#000000', '#e53935', '#1e63e9']), width=rng.choice([2, 6, 14]),
                            opacity=rng.choice([1, 1, 0.5]))
            elif roll < 0.6:
                op = erase([round(rng.uniform(0, 200), 2) for _ in range(4)], width=rng.choice([10, 30]))
            elif roll < 0.65:
                op = clear()
            elif roll < 0.72:
                op = background(rng.choice(['#ffffff', 'transparent']))
            elif roll < 0.85:
                device.service.undo(did)
                continue
            elif roll < 0.92:
                device.service.redo(did)
                continue
            else:
                device.service.rename(did, rng.choice(['Alpha', 'Beta', 'Gamma']))
                continue
            device.service.append(did, op)
            mine.append(op['id'])
        return mine

    def test_seeded_random_histories_converge_in_state_and_pixels(self):
        for seed in range(12):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                net = SimDrawNetwork()
                try:
                    a, b = net.device('a'), net.device('b')
                    net.pair(a, b)
                    did = a.service.create('Random', 200, 200)['drawing_id']
                    self.history(a, did, rng, 5)
                    net.connect(a, b)
                    net.disconnect(a, b)
                    self.history(a, did, rng, rng.randint(5, 25))
                    self.history(b, did, rng, rng.randint(5, 25))
                    net.reconnect(a, b)
                    for _ in range(rng.randint(0, 4)):
                        net.fault(rng.choice(['duplicate', 'drop_response', 'drop_request']))
                    for _ in range(6):
                        try:
                            if rng.random() < 0.5:
                                net.sync(a, b, hello=True)
                                net.sync(b, a, hello=True)
                            else:
                                net.sync(b, a, hello=True)
                                net.sync(a, b, hello=True)
                        except DrawSyncError:
                            pass
                    net.settle()
                    self.assertEqual(a.state(did), b.state(did))
                    self.assertEqual(render(a, did), render(b, did))
                finally:
                    net.close()


if __name__ == '__main__':
    unittest.main()
