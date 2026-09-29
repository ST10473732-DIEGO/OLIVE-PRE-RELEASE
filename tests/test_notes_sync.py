"""OLIVE Notes sync over a deterministic simulated Connect (real protocol bytes)."""
import base64
import json
import random
import statistics
import time
import unittest
import uuid
from unittest import mock

import pycrdt

from olive.notes import protocol, statevector
from olive.notes.limits import LIMITS, PROTOCOL
from olive.notes.sync_engine import NotesSyncError
from tests.notes_sync_fixture import SimNetwork


class CodePointText:
    """Test view over pycrdt.Text using Python str indices (pycrdt uses UTF-8 bytes)."""
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return str(self.text)

    def _byte(self, index):
        return len(str(self.text)[:index].encode('utf-8'))

    def insert(self, index, value):
        self.text.insert(self._byte(index), value)

    def __delitem__(self, key):
        start, stop = key.start or 0, key.stop if key.stop is not None else len(str(self.text))
        del self.text[self._byte(start):self._byte(stop)]


def edit(device, note_id, change):
    """A local editor edit (like the renderer or phone): a Yjs update from a replica."""
    opened = device.run('open', note_id)
    replica = pycrdt.Doc()
    replica.apply_update(base64.b64decode(opened['state']))
    body = CodePointText(replica.get('body', type=pycrdt.Text))
    before = replica.get_state()
    change(body)
    return device.run('apply_update', note_id, base64.b64encode(replica.get_update(before)).decode())


class NotesSyncTests(unittest.TestCase):
    def setUp(self):
        self.net = SimNetwork()
        self.desktop = self.net.device('desktop')
        self.phone = self.net.device('phone')
        self.net.pair(self.desktop, self.phone)

    def tearDown(self):
        self.net.close()

    def converge(self, *devices):
        self.assertTrue(self.net.settle(list(devices) or None))

    def assertSame(self, note_id, *devices):
        devices = devices or (self.desktop, self.phone)
        texts = [d.text(note_id) for d in devices]
        self.assertEqual(len(set(texts)), 1, texts)
        states = [statevector.decode(d.service.run(lambda d=d: d.service.document(note_id).state_vector())) for d in devices]
        self.assertTrue(all(state == states[0] for state in states), states)
        return texts[0]

    # 1-6 ---------------------------------------------------------------------
    def test_create_type_delete_paste_both_directions(self):
        note = self.desktop.run('create', '', 'Desktop line 1')
        self.converge()
        self.assertEqual(self.phone.text(note['note_id']), 'Desktop line 1')
        phone_note = self.phone.run('create', 'From phone', 'hello')
        self.converge()
        self.assertEqual(self.desktop.text(phone_note['note_id']), 'hello')
        nid = note['note_id']
        edit(self.desktop, nid, lambda b: b.insert(len(str(b)), '\nDesktop line 2'))
        self.converge()
        self.assertEqual(self.phone.text(nid), 'Desktop line 1\nDesktop line 2')
        edit(self.phone, nid, lambda b: b.insert(len(str(b)), '\nPhone line 1'))
        self.converge()
        self.assertEqual(self.desktop.text(nid), 'Desktop line 1\nDesktop line 2\nPhone line 1')
        edit(self.desktop, nid, lambda b: b.__delitem__(slice(0, 15)))
        self.converge()
        self.assertEqual(self.phone.text(nid), 'Desktop line 2\nPhone line 1')
        paragraph = '\nPasted paragraph: lorem ipsum dolor sit amet, 😀 unicode.'
        edit(self.phone, nid, lambda b: b.insert(len(str(b)), paragraph))
        self.converge()
        self.assertEqual(self.assertSame(nid), 'Desktop line 2\nPhone line 1' + paragraph)

    # 7-10 --------------------------------------------------------------------
    def test_rename_pin_trash_restore_same_id(self):
        nid = self.desktop.run('create', 'Old', 'x')['note_id']
        self.converge()
        self.phone.run('rename', nid, 'New title')
        self.phone.run('set_pinned', nid, True)
        self.converge()
        summary = self.desktop.run('get', nid)
        self.assertEqual((summary['display_title'], summary['pinned']), ('New title', True))
        self.desktop.run('set_pinned', nid, False)
        self.desktop.run('trash', nid)
        self.converge()
        self.assertEqual([n['note_id'] for n in self.phone.notes('trash')], [nid])
        self.assertFalse(self.phone.run('get', nid)['pinned'])
        self.phone.run('restore', nid)
        self.converge()
        restored = self.desktop.run('get', nid)
        self.assertEqual((restored['note_id'], restored['trashed'], restored['display_title']), (nid, False, 'New title'))
        self.assertEqual(len(self.desktop.notes()), 1)

    # 11-12, 17-19 ---------------------------------------------------------------
    def test_duplicate_delivery_dropped_ack_and_out_of_order(self):
        nid = self.desktop.run('create', '', 'base')['note_id']
        self.converge()
        edit(self.desktop, nid, lambda b: b.insert(4, ' one'))
        self.net.fault('duplicate')
        self.net.sync(self.desktop, self.phone)
        self.assertEqual(self.phone.text(nid), 'base one')
        edit(self.desktop, nid, lambda b: b.insert(len(str(b)), ' two'))
        self.net.fault('drop_response')
        with self.assertRaises(NotesSyncError):
            self.net.sync(self.desktop, self.phone)
        self.assertEqual(self.phone.text(nid), 'base one two')  # Applied, ACK lost.
        self.assertGreater(self.desktop.engine.pending(self.phone.id), 0)
        self.converge()
        self.assertEqual(self.assertSame(nid), 'base one two')
        # Out of order: capture three separate deltas, deliver C, A, B.
        self.net.hold = True
        for word in (' A', ' B', ' C'):
            edit(self.desktop, nid, lambda b, w=word: b.insert(len(str(b)), w))
            with self.assertRaises(NotesSyncError):
                self.net.sync(self.desktop, self.phone)
        self.net.hold = False
        self.net.release([2, 0, 1])
        self.converge()
        self.assertEqual(self.assertSame(nid), 'base one two A B C')

    def test_restart_sender_before_ack_and_receiver_after_apply(self):
        nid = self.desktop.run('create', '', 'start')['note_id']
        self.converge()
        edit(self.desktop, nid, lambda b: b.insert(5, ' unsent'))
        self.desktop.crash()                      # Edit durable, never transmitted.
        self.assertEqual(self.desktop.text(nid), 'start unsent')
        self.converge()
        self.assertEqual(self.phone.text(nid), 'start unsent')
        edit(self.desktop, nid, lambda b: b.insert(len(str(b)), ' more'))
        self.net.fault('drop_response')
        with self.assertRaises(NotesSyncError):
            self.net.sync(self.desktop, self.phone)
        self.phone.crash()                        # Applied and committed, ACK never sent.
        self.assertEqual(self.phone.text(nid), 'start unsent more')
        self.converge()
        self.assertEqual(self.assertSame(nid), 'start unsent more')

    # 13-16 --------------------------------------------------------------------
    def test_offline_edits_both_directions(self):
        self.net.disconnect(self.desktop, self.phone)
        ids = [self.desktop.run('create', f'Offline {i}', f'body {i}')['note_id'] for i in range(10)]
        self.net.reconnect(self.desktop, self.phone)
        self.converge()
        self.assertEqual(sorted(n['note_id'] for n in self.phone.notes()), sorted(ids))
        self.net.disconnect(self.desktop, self.phone)
        self.desktop.close()                      # "Desktop closed"
        for nid in ids[:5]:
            self.phone.run('append_text', nid, 'phone edit')
        self.desktop.restart()
        self.net.reconnect(self.desktop, self.phone)
        self.converge()
        for nid in ids[:5]:
            self.assertTrue(self.desktop.text(nid).endswith('phone edit'))

    def test_shopping_scenario_concurrent_offline(self):
        nid = self.desktop.run('create', 'Shopping', 'Milk\nBread')['note_id']
        self.converge()
        self.phone.run('append_text', nid, 'Eggs')
        self.converge()
        self.net.disconnect(self.desktop, self.phone)
        self.desktop.run('append_text', nid, 'Chicken')
        self.phone.run('append_text', nid, 'Coffee')
        self.net.reconnect(self.desktop, self.phone)
        self.converge()
        text = self.assertSame(nid)
        for item in ('Milk', 'Bread', 'Eggs', 'Chicken', 'Coffee'):
            self.assertIn(item, text)

    def test_same_position_concurrent_inserts(self):
        nid = self.desktop.run('create', '', 'Hello world')['note_id']
        self.converge()
        self.net.disconnect(self.desktop, self.phone)
        edit(self.desktop, nid, lambda b: b.insert(6, 'beautiful '))
        edit(self.phone, nid, lambda b: b.insert(6, 'amazing '))
        self.net.reconnect(self.desktop, self.phone)
        self.converge()
        text = self.assertSame(nid)
        self.assertIn('beautiful ', text)
        self.assertIn('amazing ', text)
        self.assertTrue(text.startswith('Hello ') and text.endswith('world'))

    def test_delete_vs_edit_overlap(self):
        nid = self.desktop.run('create', '', 'Keep this. The quick brown fox jumps. End.')['note_id']
        self.converge()
        self.net.disconnect(self.desktop, self.phone)
        start = 'Keep this. '.__len__()
        sentence = 'The quick brown fox jumps. '
        edit(self.desktop, nid, lambda b: b.__delitem__(slice(start, start + len(sentence))))
        edit(self.phone, nid, lambda b: b.insert(start + 4, 'very '))
        self.net.reconnect(self.desktop, self.phone)
        self.converge()
        text = self.assertSame(nid)
        # Yjs keeps a concurrent insert made inside a concurrently deleted range.
        self.assertEqual(text, 'Keep this. very End.')

    def test_concurrent_rename_converges_without_oscillation(self):
        nid = self.desktop.run('create', 'Start', '')['note_id']
        self.converge()
        self.net.disconnect(self.desktop, self.phone)
        self.desktop.run('rename', nid, 'Desktop title')
        self.phone.run('rename', nid, 'Phone title')
        self.net.reconnect(self.desktop, self.phone)
        self.converge()
        titles = {self.desktop.run('get', nid)['title'], self.phone.run('get', nid)['title']}
        self.assertEqual(len(titles), 1)
        self.assertIn(titles.pop(), {'Desktop title', 'Phone title'})
        self.assertEqual(self.desktop.engine.pending(self.phone.id), 0)
        self.assertEqual(self.phone.engine.pending(self.desktop.id), 0)

    # 20-21 --------------------------------------------------------------------
    def test_initial_and_partial_initial_sync(self):
        ids = [self.desktop.run('create', f'Note {i}', f'content {i}')['note_id'] for i in range(50)]
        with mock.patch.dict(LIMITS, {'max_entries': 3}):
            self.net.fault('drop_response', 1)
            with self.assertRaises(NotesSyncError):
                self.net.sync(self.desktop, self.phone, hello=True)   # offer of 3 lost
            self.net.sync  # Connection dies after 3 of 50 notes are transferred:
            calls = {'n': 0}
            real = self.net.sender(self.desktop, self.phone)
            def limited(operation, arguments):
                calls['n'] += 1
                if calls['n'] > 2:
                    raise NotesSyncError('connection_lost')
                return real(operation, arguments)
            with self.assertRaises(NotesSyncError):
                self.desktop.engine.pump(self.phone.id, limited)
        partial = self.phone.notes()
        self.assertLessEqual(len(partial), 3)
        for note in partial:
            self.assertTrue(self.phone.text(note['note_id']).startswith('content'))  # Never half-created.
        self.desktop.restart()
        self.phone.restart()
        self.converge()
        received = [n['note_id'] for n in self.phone.notes()]
        self.assertEqual(sorted(received), sorted(ids))
        self.assertEqual(len(received), len(set(received)))
        self.assertEqual(self.desktop.engine.pending(self.phone.id), 0)

    # 22-25 ----------------------------------------------------------------------
    def test_revoked_device_stops_receiving(self):
        nid = self.desktop.run('create', '', 'shared')['note_id']
        self.converge()
        self.phone.allowed.discard(self.desktop.id)      # Revoked/Off on the phone side
        self.desktop.run('append_text', nid, 'after revoke')
        with self.assertRaises(NotesSyncError) as raised:
            self.net.sync(self.desktop, self.phone)
        self.assertEqual(str(raised.exception), 'permission_off')
        self.assertEqual(self.phone.text(nid), 'shared')
        self.assertEqual(self.desktop.text(nid), 'shared\nafter revoke')  # Local notebook intact.

    def test_unsupported_protocol_and_malformed_and_huge(self):
        now = int(time.time())
        def request(**override):
            value = {'protocol_version': PROTOCOL, 'request_id': str(uuid.uuid4()), 'source_device_id': self.desktop.id,
                     'target_device_id': self.phone.id, 'operation': 'hello', 'arguments': {'versions': [PROTOCOL]},
                     'timestamp': now, 'expires_at': now + 60}
            value.update(override)
            return json.dumps(value).encode()
        def answer(raw):
            return protocol.decode_response(self.net.deliver(self.phone, self.desktop.id, raw))
        self.assertEqual(answer(request(protocol_version='olive-notes/2'))['error'], 'unsupported_protocol')
        self.assertEqual(answer(request(arguments={'versions': ['olive-notes/9']}))['error'], 'unsupported_protocol')
        epoch = str(uuid.uuid4())
        nid = str(uuid.uuid4())
        bad = [
            b'{not json',
            request()[:-1] + b',"operation":"hello"}',                                      # duplicate key
            request(operation='sync', arguments={'epoch': epoch, 'entries': [{'note_id': nid, 'seq': 1, 'sv': 'AA==', 'purged': False, 'update': '***'}]}),
            request(operation='sync', arguments={'epoch': epoch, 'entries': [{'note_id': nid, 'seq': 1, 'sv': 'BQE=', 'purged': False}]}),
            request(operation='sync', arguments={'epoch': epoch, 'entries': [], 'extra': 1}),
            request(operation='sync', arguments={'epoch': epoch, 'entries': [{'note_id': 'Shopping', 'seq': 1, 'sv': 'AA==', 'purged': False}]}),
            request(operation='eval', arguments={}),
            request(timestamp=now + 3600, expires_at=now + 3660),
        ]
        for raw in bad:
            self.assertEqual(answer(raw)['state'], 'rejected', raw[:80])
        garbage = base64.b64encode(b'\x01\x01\x05garbage-crdt').decode()
        result = answer(request(operation='sync', arguments={'epoch': epoch, 'entries': [
            {'note_id': nid, 'seq': 1, 'sv': 'AA==', 'purged': False, 'update': garbage}]}))
        self.assertEqual(result['result']['results'][0]['status'], 'rejected')
        self.assertEqual(self.phone.notes(), [])
        huge = [
            b'x' * (LIMITS['max_frame_bytes'] + 1),
            request(operation='sync', arguments={'epoch': epoch, 'entries': [
                {'note_id': str(uuid.uuid4()), 'seq': 1, 'sv': 'AA==', 'purged': False} for _ in range(LIMITS['max_entries'] + 1)]}),
            request(operation='sync', arguments={'epoch': epoch, 'entries': [
                {'note_id': nid, 'seq': 1, 'sv': 'AA==', 'purged': False,
                 'update': base64.b64encode(b'u' * (LIMITS['max_inline_update_bytes'] + 1)).decode()}]}),
            request(operation='chunk', arguments={'epoch': epoch, 'transfer_id': str(uuid.uuid4()), 'note_id': nid, 'seq': 1,
                    'sv': 'AA==', 'index': 0, 'count': 1, 'total_bytes': LIMITS['max_transfer_bytes'] + 1,
                    'sha256': '0' * 64, 'data': 'AA=='}),
        ]
        for raw in huge:
            self.assertEqual(answer(raw)['state'], 'rejected')
        self.assertEqual(self.phone.notes(), [])

    # Required extras ---------------------------------------------------------------
    def test_randomized_convergence(self):
        rng = random.Random(20260929)
        alphabet = ['a', 'b', ' ', '\n', 'é', '😀', '日', 'ש']
        nid = self.desktop.run('create', '', 'seed text')['note_id']
        self.converge()
        for round_index in range(40):
            self.net.disconnect(self.desktop, self.phone)
            for device in (self.desktop, self.phone):
                for _ in range(rng.randint(1, 4)):
                    def change(body):
                        current = str(body)
                        if current and rng.random() < 0.35:
                            start = rng.randrange(len(current))
                            del body[start:min(len(current), start + rng.randint(1, 5))]
                        else:
                            body.insert(rng.randint(0, len(current)), ''.join(rng.choice(alphabet) for _ in range(rng.randint(1, 6))))
                    edit(device, nid, change)
            self.net.reconnect(self.desktop, self.phone)
            order = [(self.desktop, self.phone), (self.phone, self.desktop)]
            rng.shuffle(order)
            for a, b in order:
                self.net.sync(a, b)
            self.converge()
            self.assertSame(nid)

    def test_three_devices_partial_connectivity(self):
        laptop = self.net.device('laptop')
        self.net.pair(self.phone, laptop)
        self.net.pair(self.desktop, laptop)
        nid = self.desktop.run('create', '', 'origin')['note_id']
        self.net.disconnect(self.desktop, laptop)             # A offline from C
        self.converge()
        self.assertEqual(laptop.text(nid), 'origin')          # Relayed A -> B -> C
        self.desktop.run('append_text', nid, 'A edit')
        self.phone.run('append_text', nid, 'B edit')
        laptop.run('append_text', nid, 'C edit')
        self.converge()
        self.net.reconnect(self.desktop, laptop)
        self.converge()
        text = self.assertSame(nid, self.desktop, self.phone, laptop)
        for part in ('A edit', 'B edit', 'C edit'):
            self.assertIn(part, text)

    def test_permanent_delete_tombstone_prevents_resurrection(self):
        laptop = self.net.device('laptop')
        self.net.pair(self.desktop, laptop)
        self.net.pair(self.phone, laptop)
        nid = self.desktop.run('create', 'Doomed', 'old copy')['note_id']
        self.converge()
        self.net.disconnect(self.phone, self.desktop)
        self.net.disconnect(self.phone, laptop)                # B offline with old copy
        self.phone.run('append_text', nid, 'offline edit')
        self.desktop.run('trash', nid)
        self.desktop.run('purge', nid)
        self.converge(self.desktop, laptop)
        self.assertTrue(laptop.run('is_purged', nid))
        self.net.reconnect(self.phone, self.desktop)
        self.net.reconnect(self.phone, laptop)
        self.converge()
        for device in (self.desktop, self.phone, laptop):
            self.assertTrue(device.run('is_purged', nid))
            self.assertEqual(device.notes(), [])
            self.assertEqual(device.notes('trash'), [])

    def test_trash_is_not_undone_by_stale_device_and_restore_keeps_id(self):
        nid = self.desktop.run('create', 'List', 'content')['note_id']
        self.converge()
        self.net.disconnect(self.desktop, self.phone)
        self.desktop.run('trash', nid)
        self.phone.run('append_text', nid, 'stale edit')    # Old copy, edited offline
        self.net.reconnect(self.desktop, self.phone)
        self.converge()
        for device in (self.desktop, self.phone):
            self.assertTrue(device.run('get', nid)['trashed'])
            self.assertIn('stale edit', device.text(nid))
        self.desktop.run('restore', nid)
        self.converge()
        self.assertEqual([n['note_id'] for n in self.phone.notes()], [nid])

    def test_history_restore_syncs_as_new_edit(self):
        nid = self.desktop.run('create', '', 'version one')['note_id']
        self.desktop.service.run(self.desktop.service._checkpoint, nid, 'edit')
        self.desktop.run('replace_text', nid, 'version two')
        self.converge()
        entry = next(h for h in self.desktop.run('history', nid)['history']
                     if self.desktop.run('history_text', h['history_id'])['text'] == 'version one')
        self.desktop.run('restore_history', nid, entry['history_id'])
        self.converge()
        self.assertEqual(self.assertSame(nid), 'version one')
        # History itself stays local/private; the restore arrived as an ordinary edit.
        self.assertEqual(self.phone.run('history', nid)['history'], [])

    def test_remote_edit_is_searchable_offline(self):
        nid = self.desktop.run('create', 'Trip', 'plain')['note_id']
        self.converge()
        edit(self.desktop, nid, lambda b: b.insert(len(str(b)), ' olive-sync-zebra-9271'))
        self.converge()
        self.net.disconnect(self.desktop, self.phone)
        self.phone.service.flush()
        hits = self.phone.run('search', 'olive-sync-zebra-9271')['results']
        self.assertEqual([h['note_id'] for h in hits], [nid])

    def test_compaction_then_stale_peer_catches_up(self):
        nid = self.desktop.run('create', '', '')['note_id']
        self.converge()
        self.net.disconnect(self.desktop, self.phone)
        for index in range(2000):
            self.desktop.service.run(lambda i=index: self.desktop.service._edit(
                nid, lambda d: d.append_text(f'{i}'), origin='local', reason='edited'))
        self.assertTrue(self.desktop.service.run(self.desktop.service._compact, nid))
        self.desktop.restart()
        self.net.reconnect(self.desktop, self.phone)
        requests = []
        real = self.net.sender(self.desktop, self.phone)
        def counted(operation, arguments):
            requests.append(operation)
            return real(operation, arguments)
        self.desktop.engine.pump(self.phone.id, counted)
        self.converge()
        self.assertSame(nid)
        self.assertLess(len(requests), 10)  # State diff, not replaying 2000 edits.

    def test_large_note_uses_bounded_chunks(self):
        body = ''.join(chr(0x61 + (i % 26)) for i in range(1_000_000))
        nid = self.desktop.run('create', 'Big', body)['note_id']
        sizes = []
        real = self.net.sender(self.desktop, self.phone)
        def measured(operation, arguments):
            sizes.append(len(protocol.dumps(arguments)))
            return real(operation, arguments)
        for _ in range(3):
            self.desktop.engine.pump(self.phone.id, measured)
        self.converge()
        self.assertEqual(len(self.phone.text(nid)), 1_000_000)
        self.assertLessEqual(max(sizes), LIMITS['max_frame_bytes'])

    def test_epoch_change_triggers_full_resend(self):
        nid = self.desktop.run('create', '', 'kept')['note_id']
        self.converge()
        self.phone.close()
        import shutil
        shutil.rmtree(self.phone.path.parent)      # Phone reinstalled: new empty store
        self.phone._start()
        self.net.connect(self.desktop, self.phone)   # Connection establishment says hello.
        self.converge()
        self.assertEqual(self.phone.text(nid), 'kept')

    def test_no_echo_loop_and_idle_is_quiet(self):
        nid = self.desktop.run('create', '', 'x')['note_id']
        self.converge()
        edit(self.desktop, nid, lambda b: b.insert(1, 'y'))
        self.converge()
        requests = []
        for a, b in ((self.desktop, self.phone), (self.phone, self.desktop)):
            real = self.net.sender(a, b)
            a.engine.pump(b.id, lambda op, args, real=real: (requests.append(op), real(op, args))[1])
        self.assertEqual(requests, [])
        self.assertEqual(self.phone.engine.pending(self.desktop.id), 0)

    def test_rapid_multi_note_updates_do_not_cross(self):
        first = self.desktop.run('create', '', 'first')['note_id']
        second = self.desktop.run('create', '', 'second')['note_id']
        self.converge()
        for index in range(20):
            edit(self.phone if index % 2 else self.desktop, first if index % 3 else second,
                 lambda b, i=index: b.insert(len(str(b)), f' {i}'))
        self.converge()
        self.assertTrue(self.assertSame(first).startswith('first'))
        self.assertTrue(self.assertSame(second).startswith('second'))
        self.assertNotIn('second', self.desktop.text(first))

    def test_latency_diagnostic(self):
        nid = self.desktop.run('create', '', '')['note_id']
        self.converge()
        samples = []
        for index in range(30):
            started = time.perf_counter()
            edit(self.desktop, nid, lambda b, i=index: b.insert(len(str(b)), str(i % 10)))
            self.net.sync(self.desktop, self.phone)
            samples.append((time.perf_counter() - started) * 1000)
        self.assertSame(nid)
        print(f'\nNotes simulated local edit -> remote durable apply: median {statistics.median(samples):.1f} ms '
              f'(p90 {sorted(samples)[26]:.1f} ms, in-process transport, SQLite FULL sync)')


if __name__ == '__main__':
    unittest.main()
