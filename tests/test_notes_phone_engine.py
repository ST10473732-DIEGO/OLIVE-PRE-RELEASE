"""The committed phone engine bundle against the real Python desktop engine.

The bundle runs in a bare JavaScript context (no crypto, TextEncoder, atob or
console), as in the iOS app's JavaScriptCore. Requests and answers are real
olive-notes/1 bytes. This verifies protocol interop and convergence; it does
NOT verify Swift, UIKit or a physical phone.
"""
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from olive.notes import protocol
from olive.notes.service import NotesService
from olive.notes.sync_engine import NotesSyncEngine, NotesSyncError

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'mobile/ios/OLIVEMobile/Resources/NotesEngine.js'
HARNESS = ROOT / 'tests/fixtures/notes_phone_harness.cjs'
NODE = shutil.which('node')
# On the Mac, check-connect-interop.sh sets this to the Swift interop tool so the
# same tests drive the real Swift JavaScriptCore host and SQLite store.
SWIFT_HARNESS = os.environ.get('OLIVE_NOTES_SWIFT_HARNESS')


def utf16(text):
    return len(text.encode('utf-16-le')) // 2


class Phone:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.store = tempfile.mkdtemp(prefix='olive-notes-phone-store-')
        command = ([SWIFT_HARNESS, '--notes-harness', str(BUNDLE), self.store] if SWIFT_HARNESS
                   else [NODE, str(HARNESS), str(BUNDLE)])
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        text=True, encoding='utf-8', bufsize=1)
        self.counter = 0
        self.command('boot', self.id)

    def command(self, cmd, *args):
        self.counter += 1
        self.process.stdin.write(json.dumps({'id': self.counter, 'cmd': cmd, 'args': list(args)}) + '\n')
        self.process.stdin.flush()
        reply = json.loads(self.process.stdout.readline())
        if 'error' in reply:
            raise RuntimeError(reply['error'])
        return reply['result']

    def call(self, method, *args):
        raw = self.command('call', method, *args)
        if method in ('handle', 'next', 'answer'):
            return json.loads(raw)
        value = json.loads(raw)
        if not value['ok']:
            raise RuntimeError(value['error'])
        return value['value']

    def text(self, note_id):
        return self.call('text', note_id)

    def close(self):
        self.process.stdin.close()
        self.process.wait(10)
        self.process.stdout.close()
        shutil.rmtree(self.store, ignore_errors=True)


class PhoneBundleFreshnessTests(unittest.TestCase):
    def test_committed_bundle_matches_its_sources(self):
        """Same hash as desktop/scripts/build-notes-engine.mjs: rebuild after engine changes."""
        import hashlib
        engine = ROOT / 'desktop/src/features/notes/engine'
        inputs = [engine / name for name in ('phone-entry.ts', 'replica.ts', 'protocol.ts', 'doc.ts', 'text.ts', 'protocol_v1.json')]
        inputs += [ROOT / 'desktop/node_modules/yjs/package.json', ROOT / 'desktop/node_modules/lib0/package.json']
        if not all(path.exists() for path in inputs):
            self.skipTest('desktop/node_modules is not installed')
        digest = hashlib.sha256()
        for path in inputs:
            digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0' + path.read_bytes() + b'\0')
        header = BUNDLE.read_text(encoding='utf-8').split('\n', 2)[1]
        self.assertIn(digest.hexdigest(), header, 'Run: node desktop/scripts/build-notes-engine.mjs')

    def test_shared_protocol_definition_is_identical(self):
        import json
        python = json.loads((ROOT / 'olive/notes/protocol_v1.json').read_text(encoding='utf-8'))
        typescript = json.loads((ROOT / 'desktop/src/features/notes/engine/protocol_v1.json').read_text(encoding='utf-8'))
        self.assertEqual(python, typescript)


@unittest.skipUnless((NODE or SWIFT_HARNESS) and BUNDLE.exists(), 'node (or the Swift harness) and the phone engine bundle are required')
class PhoneEngineInteropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix='olive-notes-phone-')
        self.desktop_id = str(uuid.uuid4())
        self.desktop = NotesService(Path(self.temp) / 'notes.sqlite3', device_id=self.desktop_id, timers=False)
        self.engine = NotesSyncEngine(self.desktop, self.desktop_id)
        self.phone = Phone()
        self.online = True

    def tearDown(self):
        self.phone.close()
        self.desktop.close()
        shutil.rmtree(self.temp, ignore_errors=True)

    # Connect stand-ins: the same checks the desktop's Connect adapter performs.
    def phone_pushes(self):
        for _ in range(64):
            step = self.phone.call('next', self.desktop_id)
            if 'done' in step:
                return step['done']
            raw = json.dumps(step['request']).encode()
            request = protocol.decode_request(raw)
            self.assertEqual(request['source_device_id'], self.phone.id)
            protocol.check_fresh(request, int(time.time()))
            try:
                response = protocol.encode_response(request['request_id'], result=self.desktop.run(self.engine.handle, self.phone.id, request))
            except protocol.NotesProtocolError as failure:
                response = protocol.encode_response(request['request_id'], error=str(failure))
            answer = self.phone.call('answer', self.desktop_id, step['ticket'], response.decode())
            if 'error' in answer:
                raise NotesSyncError(answer['error'])
        raise AssertionError('phone pump did not finish')

    def desktop_pushes(self, hello=False):
        def send(operation, arguments):
            if not self.online:
                raise NotesSyncError('device_offline')
            raw = protocol.encode_request(str(uuid.uuid4()), self.desktop_id, self.phone.id, operation, arguments, int(time.time()))
            response = protocol.decode_response(json.dumps(self.phone.call('handle', self.desktop_id, raw.decode())).encode())
            if response['state'] != 'completed':
                raise NotesSyncError(response['error'])
            return response['result']
        return self.engine.pump(self.phone.id, send, hello=hello)

    def settle(self):
        for _ in range(6):
            self.phone_pushes()
            self.desktop_pushes()
            if not self.desktop.run(self.desktop.pending_count, self.phone.id) and not self.phone.call('status', self.desktop_id)['pending']:
                return
        self.fail('did not settle')

    def test_create_edit_both_ways_with_live_deltas(self):
        note = self.phone.call('create', 'Shopping', 'Milk\nBread')
        self.phone_pushes()
        self.assertEqual(self.desktop.run(self.desktop.read_text, note['note_id'])['text'], 'Milk\nBread')
        self.phone.call('open', note['note_id'])
        self.desktop.run(self.desktop.append_text, note['note_id'], 'Eggs')
        self.desktop_pushes(hello=True)
        self.assertEqual(self.phone.text(note['note_id']), 'Milk\nBread\nEggs')
        deltas = [e for e in self.phone.command('events') if e['type'] == 'delta']
        self.assertEqual(deltas[-1]['delta'], [{'retain': 10}, {'insert': '\nEggs'}])
        text = self.phone.text(note['note_id'])
        self.phone.call('edit', note['note_id'], len(text), 0, '\nCoffee ☕')
        self.phone_pushes()
        self.assertEqual(self.desktop.run(self.desktop.read_text, note['note_id'])['text'], 'Milk\nBread\nEggs\nCoffee ☕')
        self.assertEqual(self.phone.call('status', self.desktop_id)['pending'], 0)

    def test_offline_concurrent_edits_converge(self):
        note = self.desktop.run(self.desktop.create, '', 'Hello world')
        self.desktop_pushes(hello=True)
        nid = note['note_id']
        self.desktop.run(self.desktop.replace_text, nid, 'Hello beautiful world')
        self.phone.call('edit', nid, 6, 0, 'amazing 😀 ')
        self.settle()
        desktop_text = self.desktop.run(self.desktop.read_text, nid)['text']
        self.assertEqual(desktop_text, self.phone.text(nid))
        self.assertIn('beautiful', desktop_text)
        self.assertIn('amazing 😀', desktop_text)

    def test_randomized_convergence_with_unicode(self):
        rng = random.Random(9271)
        nid = self.desktop.run(self.desktop.create, '', 'seed')['note_id']
        self.desktop_pushes(hello=True)
        for _ in range(25):
            for _ in range(rng.randint(1, 3)):
                current = self.desktop.run(self.desktop.read_text, nid)['text']
                cut = rng.randint(0, len(current))
                self.desktop.run(self.desktop.replace_text, nid, current[:cut] + rng.choice(['a', 'é', '日', '\n', '👍🏽']) + current[cut:])
            for _ in range(rng.randint(1, 3)):
                current = self.phone.text(nid)
                units = len(current.encode('utf-16-le')) // 2
                if units > 4 and rng.random() < .3:
                    # Delete a whole code point range: stay off surrogate halves.
                    start = rng.randint(0, len(current) - 2)
                    prefix = len(current[:start].encode('utf-16-le')) // 2
                    size = len(current[start:start + 2].encode('utf-16-le')) // 2
                    self.phone.call('edit', nid, prefix, size, '')
                else:
                    at = rng.randint(0, len(current))
                    self.phone.call('edit', nid, len(current[:at].encode('utf-16-le')) // 2, 0, rng.choice(['b', 'ß', '中', '😀']))
            self.settle()
            self.assertEqual(self.desktop.run(self.desktop.read_text, nid)['text'], self.phone.text(nid))

    def test_phone_restart_keeps_pending_edits(self):
        note = self.phone.call('create', '', 'typed before restart')
        self.phone.command('restart', self.phone.id)
        self.assertEqual(self.phone.text(note['note_id']), 'typed before restart')
        self.phone_pushes()
        self.assertEqual(self.desktop.run(self.desktop.read_text, note['note_id'])['text'], 'typed before restart')

    def test_failed_local_commit_is_never_reported_saved(self):
        note = self.phone.call('create', '', 'kept')
        self.phone.call('open', note['note_id'])
        self.phone.command('failCommits', 1)
        with self.assertRaises(RuntimeError):
            self.phone.call('edit', note['note_id'], 4, 0, ' lost')
        self.assertIn('reset', [e['type'] for e in self.phone.command('events')])
        self.assertEqual(self.phone.text(note['note_id']), 'kept')

    def test_large_notes_travel_in_chunks_both_ways(self):
        big = ''.join(chr(0x61 + i % 26) for i in range(700_000))
        phone_note = self.phone.call('create', 'Phone big', big)
        desk_note = self.desktop.run(self.desktop.create, 'Desktop big', big.upper())
        for _ in range(4):
            self.phone_pushes()
            self.desktop_pushes(hello=True)
        self.assertEqual(len(self.desktop.run(self.desktop.read_text, phone_note['note_id'])['text']), 700_000)
        self.assertEqual(self.phone.text(desk_note['note_id']), big.upper())

    def test_purge_tombstone_and_restore_same_id(self):
        note = self.desktop.run(self.desktop.create, 'Temp', 'x')
        nid = note['note_id']
        self.desktop_pushes(hello=True)
        self.desktop.run(self.desktop.trash, nid)
        self.desktop_pushes()
        self.assertTrue(next(r for r in self.phone.call('list', 'trash') if r['note_id'] == nid)['trashed'])
        self.phone.call('restore', nid)
        self.phone_pushes()
        self.assertFalse(self.desktop.run(self.desktop.get, nid)['trashed'])
        self.phone.call('edit', nid, 1, 0, ' offline')   # stale edit, not yet sent
        self.desktop.run(self.desktop.trash, nid)
        self.desktop.run(self.desktop.purge, nid)
        self.settle()
        self.assertEqual(self.phone.call('list', 'notes'), [])
        self.assertEqual(self.phone.call('list', 'trash'), [])
        self.assertTrue(self.desktop.run(self.desktop.is_purged, nid))

    def test_phone_undo_is_local_only(self):
        note = self.phone.call('create', '', 'start')
        nid = note['note_id']
        self.phone_pushes()
        self.phone.call('edit', nid, 5, 0, ' A')
        self.desktop.run(self.desktop.append_text, nid, 'B')
        self.desktop_pushes(hello=True)
        self.phone.call('undo', nid, False)
        self.assertEqual(self.phone.text(nid), 'start\nB')
        self.settle()
        self.assertEqual(self.desktop.run(self.desktop.read_text, nid)['text'], 'start\nB')

    # --- helpers for the tests below -------------------------------------------
    def to_phone(self, operation, arguments):
        """One olive-notes/1 request from the desktop, straight to the phone."""
        raw = protocol.encode_request(str(uuid.uuid4()), self.desktop_id, self.phone.id, operation, arguments, int(time.time()))
        return protocol.decode_response(json.dumps(self.phone.call('handle', self.desktop_id, raw.decode())).encode())

    def desktop_text(self, nid):
        return self.desktop.run(self.desktop.read_text, nid)['text']

    def phone_database(self):
        import sqlite3
        path = Path(self.phone.command('runtime')['database'])
        return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)

    def test_edit_positions_match_across_scripts_both_ways(self):
        """UTF-16 (phone/Yjs) vs code points (Python) vs UTF-8 bytes (pycrdt)."""
        lines = ['ASCII text', 'café ñandú ë', 'e\u0301 combining n\u0303', '👍🏽 skin 👩\u200d👩\u200d👧 family 🇿🇦',
                 '日本語の中文 한국어', 'مرحبا שלום', '𝕏 astral 𝄞']
        body = '\n'.join(lines)
        nid = self.desktop.run(self.desktop.create, 'Scripts', body)['note_id']
        self.desktop_pushes(hello=True)
        self.phone.call('open', nid)
        self.assertEqual(self.phone.text(nid), body)
        # Phone inserts at every code-point boundary (UTF-16 offsets), last first.
        expected = body
        for cut in range(len(body), -1, -3):
            self.phone.call('edit', nid, utf16(expected[:cut]), 0, '|')
            expected = expected[:cut] + '|' + expected[cut:]
        self.phone_pushes()
        self.assertEqual(self.desktop_text(nid), expected)
        self.assertEqual(self.phone.text(nid), expected)
        # Desktop inserts by code point; the phone sees the matching UTF-16 retain.
        self.phone.command('events')
        for cut in (1, 13, 40, 77, len(expected) - 2):
            current = self.desktop_text(nid)
            self.desktop.run(self.desktop.replace_text, nid, current[:cut] + '#' + current[cut:])
            self.desktop_pushes()
            deltas = [e['delta'] for e in self.phone.command('events') if e['type'] == 'delta']
            self.assertEqual(deltas[-1], [{'retain': utf16(current[:cut])}, {'insert': '#'}])
            self.assertEqual(self.phone.text(nid), self.desktop_text(nid))
        # Whole-grapheme deletes from the phone: combining pair, skin tone, ZWJ family, flag.
        nid = self.desktop.run(self.desktop.create, 'Clusters', body)['note_id']
        self.desktop_pushes()
        self.phone.call('open', nid)
        for cluster in ('e\u0301', '👍🏽', '👩\u200d👩\u200d👧', '🇿🇦'):
            current = self.phone.text(nid)
            at = current.index(cluster)
            self.phone.call('edit', nid, utf16(current[:at]), utf16(cluster), '')
        self.phone_pushes()
        final = self.desktop_text(nid)
        self.assertEqual(final, self.phone.text(nid))
        for cluster in ('e\u0301', '👍🏽', '👩\u200d👩\u200d👧', '🇿🇦'):
            self.assertNotIn(cluster, final)
        # Desktop deletes an astral character; the phone deletes 2 UTF-16 units.
        self.phone.command('events')
        at = final.index('𝄞')
        self.desktop.run(self.desktop.replace_text, nid, final[:at] + final[at + 1:])
        self.desktop_pushes()
        delta = [e['delta'] for e in self.phone.command('events') if e['type'] == 'delta'][-1]
        self.assertEqual(delta, [{'retain': utf16(final[:at])}, {'delete': 2}])
        self.assertEqual(self.phone.text(nid), self.desktop_text(nid))

    def test_lost_ack_redelivery_never_duplicates_text(self):
        nid = self.desktop.run(self.desktop.create, 'Shopping', 'Milk')['note_id']
        self.desktop_pushes(hello=True)
        # Desktop -> phone: the phone applies, the answer is lost, the desktop resends.
        self.desktop.run(self.desktop.append_text, nid, 'Bread')
        def deliver_then_drop(operation, arguments):
            self.to_phone(operation, arguments)
            raise NotesSyncError('connection_lost')
        with self.assertRaises(NotesSyncError):
            self.engine.pump(self.phone.id, deliver_then_drop)
        self.assertEqual(self.phone.text(nid), 'Milk\nBread')
        self.desktop_pushes()
        self.assertEqual(self.phone.text(nid), 'Milk\nBread')
        # Phone -> desktop: the desktop applies, the answer never reaches the phone.
        self.phone.call('edit', nid, 10, 0, '\nEggs')
        step = self.phone.call('next', self.desktop_id)
        request = protocol.decode_request(json.dumps(step['request']).encode())
        self.desktop.run(self.engine.handle, self.phone.id, request)
        self.phone.call('fail', self.desktop_id, 'connection_lost')
        self.settle()
        self.assertEqual(self.desktop_text(nid), 'Milk\nBread\nEggs')
        self.assertEqual(self.phone.text(nid), 'Milk\nBread\nEggs')

    def test_out_of_order_and_duplicate_updates_on_the_phone(self):
        for restart in (False, True):
            with self.subTest(restart=restart):
                nid = self.desktop.run(self.desktop.create, '', 'Start')['note_id']
                self.desktop_pushes(hello=True)
                document = lambda: self.desktop.document(nid)
                updates, vectors = [], [self.desktop.run(lambda: document().state_vector())]
                for word in (' one', ' two'):
                    self.desktop.run(self.desktop.replace_text, nid, self.desktop_text(nid) + word)
                    updates.append(self.desktop.run(lambda: document().diff(vectors[-1])))
                    vectors.append(self.desktop.run(lambda: document().state_vector()))
                epoch = self.desktop.run(self.desktop.epoch)
                def deliver(update, seq):
                    entry = {'note_id': nid, 'seq': seq, 'sv': protocol.b64(vectors[-1]), 'purged': False, 'update': protocol.b64(update)}
                    return self.to_phone('sync', {'epoch': epoch, 'entries': [entry]})['result']['results'][0]['status']
                # The second edit first: its dependency is missing, so the phone asks for more.
                self.assertEqual(deliver(updates[1], 900), 'needs')
                self.assertEqual(self.phone.text(nid), 'Start')
                if restart:
                    self.phone.command('restart', self.phone.id)
                deliver(updates[0], 901)
                for seq, update in ((902, updates[0]), (903, updates[1])):   # Duplicates change nothing.
                    deliver(update, seq)
                self.settle()   # The sender resends whatever the phone's state vector still lacks.
                self.assertEqual(self.phone.text(nid), 'Start one two')
                self.assertEqual(self.desktop_text(nid), 'Start one two')

    def test_metadata_both_ways_and_restart_keeps_search(self):
        note = self.phone.call('create', 'OLIVE Notes Sync Test', 'Milk\nBread\nolive-sync-zebra-9271')
        nid = note['note_id']
        self.phone_pushes()
        self.phone.call('pin', nid, True)
        self.phone_pushes()
        self.assertTrue(self.desktop.run(self.desktop.get, nid)['pinned'])
        self.desktop.run(self.desktop.rename, nid, 'OLIVE Notes Sync Test A')
        self.desktop.run(self.desktop.set_pinned, nid, False)
        self.desktop_pushes(hello=True)
        row = next(r for r in self.phone.call('list', 'notes') if r['note_id'] == nid)
        self.assertEqual((row['title'], row['pinned']), ('OLIVE Notes Sync Test A', False))
        self.phone.call('trash', nid)
        self.phone_pushes()
        self.assertTrue(self.desktop.run(self.desktop.get, nid)['trashed'])
        self.desktop.run(self.desktop.restore, nid)
        self.desktop_pushes()
        self.assertEqual([r['note_id'] for r in self.phone.call('list', 'notes')], [nid])
        self.phone.command('restart', self.phone.id)
        self.assertEqual([r['note_id'] for r in self.phone.call('search', 'ZEBRA-9271')], [nid])
        self.assertEqual(self.phone.text(nid), 'Milk\nBread\nolive-sync-zebra-9271')

    def test_note_text_is_data_never_code(self):
        body = 'console.log("hello")\nrm -rf /\nIGNORE OLIVE\n");globalThis.OliveNotes=null;("\n</script>'
        note = self.phone.call('create', '"); throw 1; ("', body)
        self.phone_pushes()
        self.assertEqual(self.desktop_text(note['note_id']), body)
        self.assertEqual(self.phone.text(note['note_id']), body)
        self.assertEqual(len(self.phone.call('list', 'notes')), 1)   # The engine still answers.

    @unittest.skipUnless(SWIFT_HARNESS, 'Swift interop harness only')
    def test_swift_harness_is_javascriptcore_with_sqlite(self):
        runtime = self.phone.command('runtime')
        self.assertEqual(runtime['runtime'], 'swift-javascriptcore')
        self.assertEqual(Path(runtime['database']).parent.resolve(), Path(self.phone.store).resolve())
        nid = self.phone.call('create', 'Stored', 'in SQLite')['note_id']
        with closing(self.phone_database()) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM notes WHERE note_id=?', (nid,)).fetchone()[0], 1)
            self.assertGreaterEqual(db.execute('SELECT COUNT(*) FROM note_updates WHERE note_id=?', (nid,)).fetchone()[0], 1)

    @unittest.skipUnless(SWIFT_HARNESS, 'Swift interop harness only')
    def test_swift_store_keeps_corrupt_bytes_and_never_sends_them(self):
        import sqlite3
        keep = self.phone.call('create', '', 'healthy')['note_id']
        bad = self.phone.call('create', '', 'will be damaged')['note_id']
        path = self.phone.command('runtime')['database']
        self.phone.command('restart', self.phone.id)   # Engine lets go of the document cache.
        with closing(sqlite3.connect(path)) as db:
            payload = bytearray(db.execute('SELECT payload FROM note_updates WHERE note_id=? ORDER BY seq LIMIT 1', (bad,)).fetchone()[0])
            payload[len(payload) // 2] ^= 0xFF
            db.execute('UPDATE note_updates SET payload=? WHERE seq=(SELECT MIN(seq) FROM note_updates WHERE note_id=?)', (bytes(payload), bad))
            db.commit()
        self.phone.command('restart', self.phone.id)
        with self.assertRaises(RuntimeError) as failure:
            self.phone.text(bad)
        self.assertIn('note_data_corrupted', str(failure.exception))
        self.phone_pushes()
        self.assertEqual(self.desktop_text(keep), 'healthy')
        with self.assertRaises(Exception):
            self.desktop.run(self.desktop.read_text, bad)
        with closing(sqlite3.connect(path)) as db:   # Bytes retained for recovery.
            self.assertEqual(db.execute('SELECT payload FROM note_updates WHERE note_id=? ORDER BY seq LIMIT 1', (bad,)).fetchone()[0], bytes(payload))

    @unittest.skipUnless(SWIFT_HARNESS, 'Swift interop harness only')
    def test_swift_store_refuses_a_newer_schema_untouched(self):
        import hashlib
        import sqlite3
        self.phone.call('create', '', 'x')
        path = self.phone.command('runtime')['database']
        self.phone.process.stdin.close()   # Stop the Swift process; keep its store.
        self.phone.process.wait(10)
        self.phone.process.stdout.close()
        with closing(sqlite3.connect(path)) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA user_version=2')
            db.commit()
        before = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        self.phone = Phone.__new__(Phone)
        self.phone.id, self.phone.store, self.phone.counter = str(uuid.uuid4()), str(Path(path).parent), 0
        self.phone.process = subprocess.Popen([SWIFT_HARNESS, '--notes-harness', str(BUNDLE), self.phone.store], stdin=subprocess.PIPE,
                                              stdout=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        with self.assertRaises(RuntimeError) as failure:
            self.phone.command('boot', self.phone.id)
        self.assertIn('newer', str(failure.exception))
        self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), before)
        self.assertEqual(sorted(p.name for p in Path(path).parent.iterdir()), ['notes-v1.sqlite3'])

    def test_phone_search_and_rejects_bad_requests(self):
        note = self.desktop.run(self.desktop.create, '', 'olive-sync-zebra-9271')
        self.desktop_pushes(hello=True)
        self.assertEqual([r['note_id'] for r in self.phone.call('search', 'zebra-9271')], [note['note_id']])
        bad = self.phone.call('handle', self.desktop_id, '{"protocol_version":"olive-notes/2"}')
        self.assertEqual(bad['state'], 'rejected')
        spoof = protocol.encode_request(str(uuid.uuid4()), str(uuid.uuid4()), self.phone.id, 'hello',
                                        {'versions': ['olive-notes/1']}, int(time.time())).decode()
        self.assertEqual(self.phone.call('handle', self.desktop_id, spoof)['error'], 'source_mismatch')
        self.assertEqual(len(self.phone.call('list', 'notes')), 1)


if __name__ == '__main__':
    unittest.main()
