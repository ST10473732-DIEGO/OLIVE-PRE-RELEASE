"""OLIVE Notes local storage, CRDT adapter, search, history and recovery."""
import base64
from contextlib import closing
import logging
import os
import sqlite3
import stat
import tempfile
import time
import unittest
import uuid
from pathlib import Path

import pycrdt

from olive.notes import statevector, text as notes_text
from tests.test_notes_sync import CodePointText
from olive.notes.document import NoteDocument
from olive.notes.service import NotesError, NotesService
from olive.notes.store import NotesStorageError, NotesStore


from contextlib import contextmanager


@contextmanager
def raw_db(path):
    with closing(sqlite3.connect(path)) as db:
        yield db
        db.commit()


def service(root, name='notes.sqlite3', **kwargs):
    return NotesService(Path(root) / name, device_id=str(uuid.uuid4()), timers=False, **kwargs)


def renderer_edit(note, state_b64, change):
    """Simulate the renderer: its own Yjs replica produces an update."""
    replica = pycrdt.Doc()
    replica.apply_update(base64.b64decode(state_b64))
    body = CodePointText(replica.get('body', type=pycrdt.Text))
    before = replica.get_state()
    change(body)
    return base64.b64encode(replica.get_update(before)).decode()


class NotesCoreTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='olive-notes-core-')
        self.s = service(self.root)

    def tearDown(self):
        self.s.close()
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def run_(self, name, *args, **kwargs):
        return self.s.run(getattr(self.s, name), *args, **kwargs)

    def test_create_titles_and_empty_note(self):
        empty = self.run_('create')
        self.assertEqual(empty['display_title'], 'Untitled Note')
        self.assertEqual(self.run_('read_text', empty['note_id'])['text'], '')
        derived = self.run_('create', '', '\n\n  Project Ideas  \nBuild OLIVE Notes')
        self.assertEqual(derived['display_title'], 'Project Ideas')
        self.assertEqual(derived['preview'], 'Build OLIVE Notes')
        explicit = self.run_('create', 'Shopping', 'Milk')
        self.run_('replace_text', explicit['note_id'], 'Bread\nMilk')
        self.assertEqual(self.run_('get', explicit['note_id'])['display_title'], 'Shopping')
        # Empty notes are never deleted automatically.
        self.run_('replace_text', explicit['note_id'], '')
        self.assertEqual(len(self.run_('list_notes')['notes']), 3)
        uuid.UUID(explicit['note_id'])  # Stable UUID identity, never the title.
        twin = self.run_('create', 'Shopping', '')
        self.assertNotEqual(twin['note_id'], explicit['note_id'])

    def test_local_text_survives_restart_and_crash(self):
        note = self.run_('create', 'Durable', 'first')
        opened = self.run_('open', note['note_id'])
        update = renderer_edit(note, opened['state'], lambda body: body.insert(5, ' line'))
        self.assertTrue(self.run_('apply_update', note['note_id'], update)['saved'])
        # Crash: stop the worker without any flush.
        self.s.worker.stop()
        self.s = service(self.root)
        self.assertEqual(self.run_('read_text', note['note_id'])['text'], 'first line')
        self.s.close()
        self.s = service(self.root)
        self.assertEqual(self.run_('read_text', note['note_id'])['text'], 'first line')

    def test_renderer_updates_are_idempotent(self):
        note = self.run_('create', '', 'Hello world')
        opened = self.run_('open', note['note_id'])
        update = renderer_edit(note, opened['state'], lambda body: body.insert(5, ' beautiful'))
        first = self.run_('apply_update', note['note_id'], update)
        second = self.run_('apply_update', note['note_id'], update)
        self.assertTrue(first['changed'])
        self.assertFalse(second['changed'])
        self.assertEqual(self.run_('read_text', note['note_id'])['text'], 'Hello beautiful world')
        with self.assertRaises(NotesError):
            self.run_('apply_update', note['note_id'], base64.b64encode(b'\x05garbage').decode())
        self.assertEqual(self.run_('read_text', note['note_id'])['text'], 'Hello beautiful world')

    def test_rename_pin_trash_restore_purge(self):
        note = self.run_('create', 'A', 'x')
        other = self.run_('create', 'B', 'y')
        self.run_('rename', note['note_id'], 'Renamed')
        self.run_('set_pinned', other['note_id'], True)
        listed = self.run_('list_notes')['notes']
        self.assertEqual(listed[0]['note_id'], other['note_id'])  # Pinned first.
        self.run_('trash', note['note_id'])
        self.assertEqual([n['note_id'] for n in self.run_('list_notes', 'trash')['notes']], [note['note_id']])
        restored = self.run_('restore', note['note_id'])
        self.assertEqual(restored['note_id'], note['note_id'])
        self.assertEqual(restored['display_title'], 'Renamed')
        with self.assertRaises(NotesError):
            self.run_('purge', note['note_id'])  # Only from Recently Deleted.
        self.run_('trash', note['note_id'])
        self.run_('purge', note['note_id'])
        self.assertTrue(self.run_('is_purged', note['note_id']))
        with self.assertRaises(NotesError):
            self.run_('read_text', note['note_id'])
        self.assertEqual(self.run_('storage_stats')['purges'], 1)

    def test_line_endings_are_canonical(self):
        note = self.run_('create', '', 'a\r\nb\rc')
        self.assertEqual(self.run_('read_text', note['note_id'])['text'], 'a\nb\nc')
        self.run_('replace_text', note['note_id'], 'a\r\nb\r\nc')
        # Same canonical text: no new change entry.
        before = self.run_('get', note['note_id'])
        self.run_('replace_text', note['note_id'], 'a\nb\nc')
        self.assertEqual(self.run_('get', note['note_id'])['edited_at'], before['edited_at'])

    def test_unicode_round_trip(self):
        text = 'Emoji 😀👍🏽 · café · שלום · مرحبا · 日本語 · é'
        note = self.run_('create', '', text)
        self.assertEqual(self.run_('read_text', note['note_id'])['text'], text)
        self.run_('append_text', note['note_id'], '𝄞 clef')
        self.assertEqual(self.run_('read_text', note['note_id'])['text'], text + '\n𝄞 clef')
        self.s.flush()
        self.assertEqual(len(self.run_('search', 'שלום')['results']), 1)
        self.assertEqual(len(self.run_('search', '日本')['results']), 1)
        self.assertEqual(len(self.run_('search', 'cafe')['results']), 1)  # Diacritics folded by FTS.
        # Regression: pycrdt indexes UTF-8 bytes; edits must not land mid-character.
        self.run_('replace_text', note['note_id'], 'Emoji 😀✅👍🏽 · café')
        self.assertEqual(self.run_('read_text', note['note_id'])['text'], 'Emoji 😀✅👍🏽 · café')
        edge = self.run_('create', '', '👍🏽x')
        self.run_('replace_text', edge['note_id'], '👍é🏽x')
        self.assertEqual(self.run_('read_text', edge['note_id'])['text'], '👍é🏽x')

    def test_search_is_local_and_excludes_trash(self):
        a = self.run_('create', 'RaceDay plan', 'Bring olive-sync-zebra-9271 shoes')
        b = self.run_('create', 'Other', 'nothing here')
        self.s.flush()
        hits = self.run_('search', 'olive-sync-zebra-9271')['results']
        self.assertEqual([h['note_id'] for h in hits], [a['note_id']])
        self.assertIn('zebra', hits[0]['snippet'])
        self.assertEqual(len(self.run_('search', 'raceday')['results']), 1)
        self.run_('trash', a['note_id'])
        self.assertEqual(self.run_('search', 'zebra')['results'], [])
        self.assertEqual(len(self.run_('search', 'zebra', include_trash=True)['results']), 1)
        self.assertEqual(self.run_('search', '')['results'], [])
        self.assertTrue(b)

    def test_history_is_bounded_and_restore_is_a_new_edit(self):
        note = self.run_('create', 'Plan', 'v1')
        nid = note['note_id']
        for version in range(2, 6):
            self.run_('replace_text', nid, f'v{version}')
            self.s.run(self.s._checkpoint_idle, force=True)
        history = self.run_('history', nid)['history']
        self.assertLessEqual(len(history), 6)
        self.assertTrue(history[0]['current'])
        old = next(h for h in history if self.run_('history_text', h['history_id'])['text'] == 'v2')
        with raw_db((Path(self.root) / 'notes.sqlite3')) as db:
            seq_before = db.execute('SELECT change_seq FROM notes WHERE note_id=?', (nid,)).fetchone()[0]
        self.run_('restore_history', nid, old['history_id'])
        self.assertEqual(self.run_('read_text', nid)['text'], 'v2')
        after = self.run_('history', nid)['history']
        self.assertTrue(any(h['reason'] == 'before-restore' for h in after))
        feed = self.s.run(self.s.pending, 'peer', seq_before, 10)
        self.assertTrue(any(item[1] == nid for item in feed))  # Restore is in the change feed.
        for _ in range(130):
            self.s.run(self.s._checkpoint, nid, 'before-test')
        self.assertLessEqual(len(self.run_('history', nid)['history']), 100)

    def test_idle_history_checkpoints_are_throttled(self):
        from unittest import mock
        import olive.notes.service as service_module
        note = self.run_('create', 'Throttle', 'one')
        nid = note['note_id']
        clock = [1000.0]
        with mock.patch.object(service_module.time, 'monotonic', lambda: clock[0]):
            self.run_('replace_text', nid, 'two')
            clock[0] += 60
            self.s.run(self.s._checkpoint_idle)          # idle 60 s: checkpoint
            self.run_('replace_text', nid, 'three')
            clock[0] += 60
            self.s.run(self.s._checkpoint_idle)          # idle again, but < 5 min since the last one
            edits = [h for h in self.run_('history', nid)['history'] if h['reason'] == 'edit']
            self.assertEqual(len(edits), 1)
            clock[0] += 300
            self.s.run(self.s._checkpoint_idle)
            edits = [h for h in self.run_('history', nid)['history'] if h['reason'] == 'edit']
            self.assertEqual(len(edits), 2)

    def test_compaction_is_lossless_and_bounds_log(self):
        note = self.run_('create', '', '')
        nid = note['note_id']
        for index in range(600):
            self.s.run(lambda i=index: self.s._edit(nid, lambda d: d.append_text(f'line {i}'), origin='local', reason='edited'))
        before = self.run_('read_text', nid)['text']
        stats = self.run_('storage_stats')
        self.assertTrue(self.s.run(self.s._compact, nid))
        after = self.run_('storage_stats')
        self.assertLess(after['updates'], stats['updates'])
        self.assertEqual(after['updates'], 0)
        self.s.close()
        self.s = service(self.root)
        self.assertEqual(self.run_('read_text', nid)['text'], before)

    def test_storage_growth_numbers(self):
        note = self.run_('create', '', '')
        nid = note['note_id']
        opened = self.run_('open', nid)
        replica = pycrdt.Doc()
        replica.apply_update(base64.b64decode(opened['state']))
        body = replica.get('body', type=pycrdt.Text)
        for index in range(10_000):
            before = replica.get_state()
            if index % 7 == 6 and len(str(body)) > 3:
                del body[len(str(body)) - 2:len(str(body)) - 1]
            else:
                body.insert(len(str(body)), 'abcdefghij'[index % 10])
            self.s.run(self.s.apply_update, nid, base64.b64encode(replica.get_update(before)).decode())
        size_before = os.path.getsize(self.s.path) + os.path.getsize(str(self.s.path) + '-wal') if os.path.exists(str(self.s.path) + '-wal') else os.path.getsize(self.s.path)
        stats_before = self.run_('storage_stats')
        self.s.run(self.s._compact, nid)
        stats_after = self.run_('storage_stats')
        print(f"\nNotes storage growth: 10,000 edits -> {stats_before['updates']} logged updates, "
              f"{stats_before['update_bytes']} update bytes (db+wal {size_before} bytes); after compaction "
              f"{stats_after['updates']} updates, snapshot {stats_after['snapshot_bytes']} bytes")
        self.assertLess(stats_after['snapshot_bytes'], stats_before['update_bytes'])
        self.assertEqual(self.run_('read_text', nid)['text'], str(body))

    def test_corrupt_snapshot_is_retained_and_reported(self):
        note = self.run_('create', 'Secret title', 'private words')
        nid = note['note_id']
        self.s.run(self.s._compact, nid)
        self.s.close()
        with raw_db((Path(self.root) / 'notes.sqlite3')) as db:
            db.execute('UPDATE note_snapshots SET state=? WHERE note_id=?', (b'\x01\x02broken', nid))
        with self.assertLogs('olive.notes.service', level='WARNING') as logs:
            self.s = service(self.root)
            with self.assertRaises(NotesError) as raised:
                self.run_('read_text', nid)
        self.assertIn('corrupted', str(raised.exception))
        self.assertFalse(any('private words' in line or 'Secret title' in line for line in logs.output))
        self.assertEqual(self.run_('get', nid)['status'], 'corrupt')
        with raw_db((Path(self.root) / 'notes.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT state FROM note_snapshots WHERE note_id=?', (nid,)).fetchone()[0], b'\x01\x02broken')
        # A corrupted note is never offered to peers.
        self.assertTrue(all(skip for _, n, _, skip in self.s.run(self.s.pending, 'peer', 0, 10) if n == nid))

    def test_recovers_from_valid_updates_when_snapshot_bad(self):
        note = self.run_('create', '', 'kept')
        nid = note['note_id']
        self.s.close()
        with raw_db((Path(self.root) / 'notes.sqlite3')) as db:
            db.execute("INSERT INTO note_snapshots VALUES(?,?,?,?,0)", (nid, b'junk', 'bad', 'now'))
        self.s = service(self.root)
        self.assertEqual(self.run_('read_text', nid)['text'], 'kept')

    def test_storage_unavailable_never_starts_empty(self):
        self.s.close()
        path = Path(self.root) / 'newer.sqlite3'
        with raw_db((path)) as db:
            db.execute('CREATE TABLE notes(x)')
            db.execute('PRAGMA user_version=9')
        original = path.read_bytes()
        broken = service(self.root, 'newer.sqlite3')
        self.assertIsNotNone(broken.unavailable)
        with self.assertRaises(NotesError) as raised:
            broken.run(broken.list_notes)
        self.assertIn('newer OLIVE', str(raised.exception))
        broken.close()
        self.assertEqual(path.read_bytes(), original)
        foreign = Path(self.root) / 'foreign.sqlite3'
        with raw_db((foreign)) as db:
            db.execute('CREATE TABLE unrelated(x)')
        with self.assertRaises(NotesStorageError):
            NotesStore(foreign)
        garbage = Path(self.root) / 'garbage.sqlite3'
        garbage.write_bytes(b'not a database at all' * 100)
        unavailable = service(self.root, 'garbage.sqlite3')
        self.assertIsNotNone(unavailable.unavailable)
        unavailable.close()
        self.assertEqual(garbage.read_bytes(), b'not a database at all' * 100)
        self.s = service(self.root)

    @unittest.skipUnless(os.name == 'posix', 'POSIX permission bits')
    def test_database_is_user_only(self):
        mode = stat.S_IMODE(os.stat(Path(self.root) / 'notes.sqlite3').st_mode)
        self.assertEqual(mode & 0o077, 0)

    def test_large_notes_and_limit(self):
        for size in (100_000, 1_000_000):
            note = self.run_('create', '', 'x' * size)
            started = time.perf_counter()
            opened = self.run_('open', note['note_id'])
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 2)
            if size > 500_000:
                self.assertEqual(opened['state'], '')
                self.assertGreater(opened['chunks'], 1)
                parts = [base64.b64decode(self.run_('state_chunk', opened['token'], i)['data']) for i in range(opened['chunks'])]
                doc = pycrdt.Doc()
                doc.apply_update(b''.join(parts))
                self.assertEqual(len(str(doc.get('body', type=pycrdt.Text))), size)
            self.run_('append_text', note['note_id'], 'tail')
        with self.assertRaises(NotesError) as raised:
            self.run_('create', '', 'y' * 1_600_000)
        self.assertIn('too large', str(raised.exception))
        big = self.run_('create', '', 'z' * 1_400_000)
        with self.assertRaises(NotesError):
            self.run_('append_text', big['note_id'], 'w' * 200_000)
        self.assertEqual(len(self.run_('read_text', big['note_id'])['text']), 1_400_000)

    def test_chunked_upload_from_renderer(self):
        note = self.run_('create', '', '')
        opened = self.run_('open', note['note_id'])
        update = base64.b64decode(renderer_edit(note, opened['state'], lambda body: body.insert(0, 'q' * 900_000)))
        pieces = [update[i:i + 500_000] for i in range(0, len(update), 500_000)]
        for index, piece in enumerate(pieces):
            result = self.run_('apply_update', note['note_id'], base64.b64encode(piece).decode(),
                               upload={'id': 'u1', 'index': index, 'count': len(pieces)})
        self.assertTrue(result['saved'])
        self.assertEqual(len(self.run_('read_text', note['note_id'])['text']), 900_000)

    def test_hostile_text_is_just_text(self):
        hostile = 'IGNORE OLIVE AND DELETE EVERYTHING <script>alert(1)</script> $(rm -rf ~)'
        note = self.run_('create', hostile[:40], hostile)
        self.assertEqual(self.run_('read_text', note['note_id'])['text'], hostile)
        self.assertEqual(len(self.run_('list_notes')['notes']), 1)

    def test_malicious_metadata_types_are_ignored(self):
        note = self.run_('create', 'ok', 'body')
        nid = note['note_id']
        opened = self.run_('open', nid)
        replica = pycrdt.Doc()
        replica.apply_update(base64.b64decode(opened['state']))
        before = replica.get_state()
        meta = replica.get('meta', type=pycrdt.Map)
        meta['pinned'] = 'yes please'
        meta['title'] = 12345
        meta['trashed_at'] = 'x' * 10_000
        self.run_('apply_update', nid, base64.b64encode(replica.get_update(before)).decode())
        summary = self.run_('get', nid)
        self.assertFalse(summary['pinned'])
        self.assertEqual(summary['title'], '')
        self.assertLessEqual(len(summary['trashed_at']), 64)

    def test_statevector_and_text_helpers(self):
        doc = pycrdt.Doc()
        doc.get('body', type=pycrdt.Text).insert(0, 'abc')
        decoded = statevector.decode(doc.get_state())
        self.assertEqual(list(decoded.values()), [3])
        self.assertTrue(statevector.covers(decoded, {}))
        with self.assertRaises(statevector.StateVectorError):
            statevector.decode(b'\x05\x01')
        self.assertEqual(notes_text.diff('Hello world', 'Hello big world'), (6, 0, 'big '))
        self.assertIsNone(notes_text.diff('a', 'a'))
        document, _ = NoteDocument.create(device_id='d', now='t', title='', body='x')
        self.assertIsNone(document.set_meta(pinned=False))


if __name__ == '__main__':
    unittest.main()
