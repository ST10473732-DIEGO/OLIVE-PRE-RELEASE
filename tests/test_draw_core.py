"""OLIVE Draw storage: records, history, migration, assets, limits, safety."""
import base64
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import uuid
import zlib

from olive.bridge.contracts import validate as validate_envelope
from olive.draw import document
from olive.draw.assets import image_info, validate as validate_asset, AssetError
from olive.draw.contracts import UNLEDGERED, validate
from olive.draw.service import ASSET_CHUNK, DrawError, DrawService
from olive.draw.store import DrawStorageError, DrawStore
from olive.services.backup_service import BackupService
from tests.draw_sync_fixture import png, stroke, erase

ROOT = Path(__file__).resolve().parents[1]
DEVICE = str(uuid.uuid4())

V1_SCHEMA = '''
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE drawings(drawing_id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL, background TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 0, head INTEGER NOT NULL DEFAULT 0,
    op_count INTEGER NOT NULL DEFAULT 0, doc_bytes INTEGER NOT NULL DEFAULT 0, last_save_id TEXT NOT NULL DEFAULT '',
    trashed INTEGER NOT NULL DEFAULT 0, trashed_at TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'ok');
CREATE INDEX drawings_updated ON drawings(trashed, updated_at);
CREATE TABLE drawing_ops(drawing_id TEXT NOT NULL REFERENCES drawings(drawing_id) ON DELETE CASCADE,
    idx INTEGER NOT NULL, op TEXT NOT NULL, PRIMARY KEY(drawing_id, idx));
CREATE TABLE drawing_thumbnails(drawing_id TEXT PRIMARY KEY REFERENCES drawings(drawing_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL, mime TEXT NOT NULL, image BLOB NOT NULL, created_at TEXT NOT NULL)
'''


def v1_op(points, color='#000000', op_id=None):
    return {'type': 'stroke', 'id': op_id or uuid.uuid4().hex[:12], 'tool': 'pen', 'color': color, 'width': 4,
            'opacity': 1, 'pressure': False, 'points': points}


def jpeg(width, height, *, orientation=None, gps=False):
    from PIL import Image
    image = Image.new('RGB', (width, height), (200, 30, 30))
    for x in range(width // 4):
        for y in range(height):
            image.putpixel((x, y), (20, 20, 220))    # A blue band on the left edge marks orientation.
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    if gps:
        exif[0x8825] = {1: 'N', 2: (51.0, 30.0, 0.0)}
    out = io.BytesIO()
    image.save(out, format='JPEG', quality=92, exif=exif.tobytes())
    return out.getvalue()


class DrawStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-draw-')
        self.path = Path(self.temp.name) / 'drawings.sqlite3'
        self.events = []
        self.draw = DrawService(self.path, device_id=DEVICE, publish=lambda topic, data: self.events.append((topic, data)))

    def tearDown(self):
        self.temp.cleanup()

    def ops(self, did):
        return [op['id'] for op in self.draw.visible_ops(did)]

    def all_records(self, did):
        opened = self.draw.open(did)
        records = list(opened['records'])
        while opened['more']:
            opened = self.draw.since(did, opened['cursor'])
            records += opened['records']
        return records

    def test_database_is_private_and_versioned(self):
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {'meta', 'drawings', 'draw_records', 'draw_visibility', 'draw_history', 'draw_purges',
                                  'draw_assets', 'draw_wanted', 'draw_peers', 'draw_thumbnails'})
        DrawStore.validate_database(self.path)

    def test_newer_or_foreign_database_is_left_untouched(self):
        newer = Path(self.temp.name) / 'newer.sqlite3'
        with closing(sqlite3.connect(newer)) as db, db:
            db.execute('CREATE TABLE future(x)')
            db.execute('PRAGMA user_version=7')
        before = newer.read_bytes()
        service = DrawService(newer, device_id=DEVICE)
        self.assertEqual(service.unavailable, 'draw_storage_newer')
        self.assertIn('newer OLIVE', service.status()['message'])
        with self.assertRaisesRegex(DrawError, 'newer OLIVE'):
            service.list_drawings()
        self.assertEqual(newer.read_bytes(), before)
        self.assertFalse(Path(str(newer) + '-wal').exists())
        foreign = Path(self.temp.name) / 'foreign.sqlite3'
        with closing(sqlite3.connect(foreign)) as db, db:
            db.execute('CREATE TABLE something(x)')
        self.assertEqual(DrawService(foreign, device_id=DEVICE).unavailable, 'draw_storage_unrecognized')
        with self.assertRaises(DrawStorageError):
            DrawStore.validate_database(newer)

    def test_library_create_rename_duplicate_trash_restore_purge(self):
        first = self.draw.create()
        self.assertEqual((first['title'], first['width'], first['height'], first['background']),
                         ('Untitled drawing', 1920, 1080, '#ffffff'))
        second = self.draw.create('Plan', 1080, 1080, 'transparent')
        self.assertNotEqual(self.draw.create('Plan', 800, 600)['drawing_id'], second['drawing_id'])
        self.draw.append(first['drawing_id'], stroke([1, 2, 3, 4]))
        listing = self.draw.list_drawings()
        self.assertEqual(listing['drawings'][0]['drawing_id'], first['drawing_id'])   # Recently edited first.
        self.assertEqual(listing['counts'], {'drawings': 3, 'trash': 0})
        renamed = self.draw.rename(second['drawing_id'], '  <b>Board</b>\n\x07plan  ')
        self.assertEqual(renamed['title'], '<b>Board</b> plan')   # Plain text; rendered as text by the UI.
        copy = self.draw.duplicate(first['drawing_id'])
        self.assertEqual(copy['title'], 'Untitled drawing (copy)')
        self.assertNotEqual(self.ops(copy['drawing_id']), self.ops(first['drawing_id']))   # New record ids...
        self.assertEqual([op['points'] for op in self.draw.visible_ops(copy['drawing_id'])],
                         [op['points'] for op in self.draw.visible_ops(first['drawing_id'])])   # ...same content.
        with self.assertRaisesRegex(DrawError, 'Recently Deleted before'):
            self.draw.purge(first['drawing_id'])
        self.draw.trash(first['drawing_id'])
        with self.assertRaisesRegex(DrawError, 'Restore it'):
            self.draw.append(first['drawing_id'], stroke([5, 5]))
        self.draw.restore(first['drawing_id'])
        self.draw.trash(first['drawing_id'])
        self.assertEqual(self.draw.purge(first['drawing_id']), {'purged': True})
        with self.assertRaisesRegex(DrawError, 'permanently deleted'):
            self.draw.open(first['drawing_id'])
        self.assertTrue(self.draw.is_purged(first['drawing_id']))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM draw_records WHERE drawing_id=?', (first['drawing_id'],)).fetchone()[0], 0)
        self.assertEqual(len(self.ops(copy['drawing_id'])), 1)
        reasons = [data['reason'] for topic, data in self.events if topic == 'draw.changed']
        self.assertEqual(reasons, ['created', 'created', 'created', 'renamed', 'duplicated', 'trashed',
                                   'restored', 'trashed', 'purged'])

    def test_canvas_limits_are_refused_cleanly(self):
        for width, height in ((100000, 100000), (8193, 16), (8192, 8192), (15, 100), (0, 0)):
            with self.assertRaises(DrawError, msg=(width, height)):
                self.draw.create('', width, height)
        with self.assertRaises(DrawError):
            self.draw.create('', 1920.5, 1080)
        with self.assertRaisesRegex(DrawError, 'white or transparent'):
            self.draw.create('', 100, 100, 'url(javascript:alert(1))')
        self.assertEqual(self.draw.create('', 8192, 4096)['width'], 8192)

    def test_append_undo_redo_history_and_idempotent_retry(self):
        did = self.draw.create()['drawing_id']
        a, b, c = stroke([0, 0, 10, 10]), stroke([5, 5, 6, 6], color='#ff0000'), erase([0, 0, 3, 3])
        first = self.draw.append(did, a)
        self.assertEqual(self.draw.append(did, a)['cursor'], first['cursor'])   # Retry: same record.
        self.draw.append(did, b)
        self.assertEqual(self.ops(did), [a['id'], b['id']])
        undone = self.draw.undo(did)
        self.assertEqual((undone['record']['kind'], undone['record']['body']), ('visibility', {'target': b['id'], 'hidden': True}))
        self.assertEqual(undone['history'], {'undo': 1, 'redo': 1})
        self.assertEqual(self.ops(did), [a['id']])
        self.draw.redo(did)
        self.assertEqual(self.ops(did), [a['id'], b['id']])
        self.draw.undo(did)
        self.draw.append(did, c)                       # A new edit clears Redo.
        self.assertEqual(self.draw.redo(did)['record'], None)
        self.assertEqual(self.ops(did), [a['id'], c['id']])
        clear = {'type': 'clear', 'id': uuid.uuid4().hex}
        back = {'type': 'background', 'id': uuid.uuid4().hex, 'value': 'transparent'}
        self.draw.append(did, clear)
        self.draw.append(did, back)
        self.assertEqual(self.ops(did)[-2:], [clear['id'], back['id']])
        self.draw.undo(did)
        self.draw.undo(did)
        self.assertEqual(self.ops(did), [a['id'], c['id']])
        # Everything is still in the record set (history is data, not deletion).
        kinds = [r['kind'] for r in self.all_records(did)]
        self.assertEqual(kinds.count('op'), 5)

    def test_malformed_operations_are_rejected_without_partial_writes(self):
        did = self.draw.create()['drawing_id']
        bad = [
            {'type': 'script', 'id': uuid.uuid4().hex},
            dict(stroke([1, 1]), color='red'), dict(stroke([1, 1]), width=0), dict(stroke([1, 1]), width=True),
            dict(stroke([1, 1]), opacity=0), dict(stroke([1, 1]), tool='spray'), dict(stroke([1, 1]), href='x'),
            dict(stroke([1, 1]), id='../../etc'), dict(stroke([1, 1]), id='abc12345'),
            dict(stroke([1, 1, 2]), pressure=True), dict(stroke([float('nan'), 1])), dict(stroke([1e9, 1])),
            dict(stroke([1, 1] * (document.LIMITS['max_points'] + 1))),
            {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': '/etc/passwd', 'x': 0, 'y': 0, 'width': 1, 'height': 1, 'opacity': 1},
            {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': 'a' * 64, 'x': 0, 'y': 0, 'width': 0, 'height': 1, 'opacity': 1},
            {'type': 'background', 'id': uuid.uuid4().hex, 'value': '#000000'}, 'stroke',
        ]
        for op in bad:
            with self.assertRaises(DrawError, msg=str(op)[:80]):
                self.draw.append(did, op)
        self.assertEqual(self.ops(did), [])
        ok = stroke([0.25, 1.75, 0.5, 2, 3, 0.125], pressure=True, opacity=0.35, width=0.5)
        self.draw.append(did, ok)
        self.assertEqual(self.draw.visible_ops(did), [ok])

    def test_paging_large_documents_round_trips_exactly(self):
        did = self.draw.create()['drawing_id']
        big = [stroke([round(i * 0.37, 2) % 1900 for i in range(4000)], width=8) for _ in range(40)]
        for op in big:
            self.draw.append(did, op)
        opened = self.draw.open(did)
        self.assertTrue(opened['more'])
        records = self.all_records(did)
        self.assertEqual([r['body'] for r in records if r['kind'] == 'op'], big)
        self.assertLess(len(json.dumps(opened, separators=(',', ':'))), 1_048_576 - 4096)
        # A view that is up to date gets nothing new.
        latest = self.draw.since(did, self.draw.since(did, 0)['cursor'])
        while latest['more']:
            latest = self.draw.since(did, latest['cursor'])
        self.assertEqual(self.draw.since(did, latest['cursor'])['records'], [])

    def test_document_limits_refuse_instead_of_truncating(self):
        did = self.draw.create()['drawing_id']
        with mock.patch.dict(document.LIMITS, {'max_operations': 3}):
            for op in (stroke([1, 1]), stroke([2, 2]), stroke([3, 3])):
                self.draw.append(did, op)
            with self.assertRaisesRegex(DrawError, '20,000 edits'):
                self.draw.append(did, stroke([4, 4]))
        self.assertEqual(len(self.ops(did)), 3)

    def test_unreadable_drawings_are_kept_and_not_edited(self):
        did = self.draw.create()['drawing_id']
        self.draw.append(did, stroke([1, 1]))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE draw_records SET body='{\"kind\":\"op\"}' WHERE drawing_id=? AND kind='op'", (did,))
        with self.assertRaisesRegex(DrawError, 'Could not load drawing'):
            self.draw.open(did)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM draw_records WHERE drawing_id=?', (did,)).fetchone()[0], 2)

    def test_thumbnails_are_local_bounded_images_only(self):
        did = self.draw.create()['drawing_id']
        self.draw.append(did, stroke([1, 1]))
        revision = self.draw.get(did)['revision']
        image = base64.b64encode(png(64, 36)).decode()
        self.assertEqual(self.draw.thumbnail_put(did, revision, image), {'stored': True, 'revision': revision})
        self.assertEqual(self.draw.thumbnail_get(did)['image'], image)
        self.assertEqual(self.draw.list_drawings()['drawings'][0]['thumbnail_revision'], revision)
        for rejected in (base64.b64encode(b'<svg onload=alert(1)>').decode(), base64.b64encode(png(400, 10)).decode(), 'x!'):
            with self.assertRaises(DrawError):
                self.draw.thumbnail_put(did, revision, rejected)

    def test_image_header_parser(self):
        self.assertEqual(image_info(png(3, 2)), ('image/png', 3, 2))
        self.assertEqual(image_info(jpeg(40, 30)), ('image/jpeg', 40, 30))
        from PIL import Image
        out = io.BytesIO()
        Image.new('RGB', (33, 21)).save(out, format='JPEG', progressive=True)
        self.assertEqual(image_info(out.getvalue()), ('image/jpeg', 33, 21))   # SOF2 progressive.
        self.assertIsNone(image_info(b'GIF89a'))
        self.assertIsNone(image_info(b'\xff\xd8\xff\x00'))

    def test_assets_are_validated_content_addressed_and_deduplicated(self):
        data = png(120, 80, (0, 200, 0, 128), transparent_corner=True)
        stored = self.draw.store_asset(data)
        self.assertEqual(stored['asset_id'], hashlib.sha256(data).hexdigest())
        self.assertEqual((stored['mime'], stored['width'], stored['height']), ('image/png', 120, 80))
        self.draw.store_asset(data)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM draw_assets').fetchone()[0], 1)
        # Content decides the type, never a name; malformed or absurd images are refused.
        huge = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>IIBBBBB', 100000, 100000, 8, 6, 0, 0, 0)
        truncated = data[:len(data) // 2]
        for bad, message in ((b'GIF89a....', 'only PNG and JPEG'), (b'<svg/>', 'only PNG and JPEG'),
                             (huge, 'too large'), (truncated, 'not a valid')):
            with self.assertRaisesRegex(DrawError, message):
                self.draw.store_asset(bad)
        with self.assertRaisesRegex(DrawError, 'did not arrive intact'):
            self.draw.store_asset(data, expected_id='0' * 64)
        # Bridge upload in chunks, checked against the SHA-256 id.
        other = png(300, 300, (1, 2, 3, 255))
        asset = hashlib.sha256(other).hexdigest()
        chunks = [other[i:i + 100] for i in range(0, len(other), 100)]
        for index, chunk in enumerate(chunks):
            result = self.draw.asset_upload(asset, index, len(chunks), base64.b64encode(chunk).decode())
        self.assertTrue(result['stored'])
        back = b''.join(base64.b64decode(self.draw.asset_chunk(asset, i)['data'])
                        for i in range(self.draw.asset_chunk(asset, 0)['count']))
        self.assertEqual(back, other)
        wrong = hashlib.sha256(b'nope').hexdigest()
        with self.assertRaisesRegex(DrawError, 'did not arrive intact'):
            self.draw.asset_upload(wrong, 0, 1, base64.b64encode(png(4, 4)).decode())

    def test_image_operations_want_missing_assets_and_duplicate_reuses_bytes(self):
        did = self.draw.create('Photo', 800, 600)['drawing_id']
        data = png(200, 100)
        asset = hashlib.sha256(data).hexdigest()
        image = {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': asset, 'x': 300, 'y': 250,
                 'width': 200, 'height': 100, 'opacity': 1}
        self.draw.append(did, image)
        self.assertEqual(self.draw.open(did)['missing_assets'], [asset])     # Placeholder until it arrives.
        self.assertEqual(self.draw.get(did)['schema_version'], 2)
        self.draw.store_asset(data)
        self.assertEqual(self.draw.open(did)['missing_assets'], [])
        copy = self.draw.duplicate(did)
        self.assertEqual(self.draw.visible_ops(copy['drawing_id'])[0]['asset_id'], asset)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM draw_assets').fetchone()[0], 1)
        # Deleting drawings keeps assets (retention policy: no GC in this version).
        self.draw.trash(did)
        self.draw.purge(did)
        self.assertIsNotNone(self.draw.asset_info(asset))
        # A drawing with only v1 operations stays document schema 1.
        plain = self.draw.create()['drawing_id']
        self.draw.append(plain, stroke([1, 1]))
        self.assertEqual(self.draw.get(plain)['schema_version'], 1)

    def test_trusted_image_ingest_orients_and_strips_metadata(self):
        source = Path(self.temp.name) / 'rotated.jpg'
        source.write_bytes(jpeg(80, 40, orientation=6, gps=True))     # EXIF: rotate 90 degrees clockwise.
        stored = self.draw.ingest_trusted_image(source)
        self.assertEqual((stored['mime'], stored['width'], stored['height']), ('image/png', 40, 80))
        data = b''.join(base64.b64decode(self.draw.asset_chunk(stored['asset_id'], i)['data'])
                        for i in range(self.draw.asset_chunk(stored['asset_id'], 0)['count']))
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(dict(image.getexif()), {})
            self.assertNotIn('exif', image.info)
            pixel = image.getpixel((20, 5))[:3]                              # The band is now on top.
            self.assertTrue(all(abs(a - b) <= 6 for a, b in zip(pixel, (20, 20, 220))), pixel)

    def test_backup_includes_drawings_and_assets_and_restores_them(self):
        did = self.draw.create('Backed up', 400, 300)['drawing_id']
        data = png(50, 50)
        asset = self.draw.store_asset(data)['asset_id']
        self.draw.append(did, {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': asset, 'x': 1, 'y': 1,
                               'width': 50, 'height': 50, 'opacity': 1})
        self.draw.append(did, stroke([1, 2, 3, 4]))
        backups = BackupService(Path(self.temp.name))
        archive = backups.create(components={'draw'})
        self.assertEqual(backups.validate(archive)['schema_versions'], {'draw': 2})
        epoch = self.draw.epoch()
        self.draw.trash(did)
        self.draw.purge(did)
        backups.restore(archive, confirmed=True)
        restored = DrawService(self.path, device_id=DEVICE)
        self.assertEqual(restored.list_drawings()['drawings'][0]['title'], 'Backed up')
        self.assertEqual(len(restored.visible_ops(did)), 2)
        self.assertEqual(restored.asset_info(asset)['size'], len(data))
        self.assertNotEqual(restored.epoch(), epoch)            # Peers will re-offer everything.
        self.assertIn('draw', backups.validate(backups.create())['included_components'])


class DrawMigrationTests(unittest.TestCase):
    def test_store_v1_is_backed_up_kept_and_migrated_with_history(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'drawings.sqlite3'
            did, trashed = str(uuid.uuid4()), str(uuid.uuid4())
            ops = [v1_op([i, i, i + 10, i + 10], color='#e53935', op_id=f'{i:012d}') for i in range(4)]
            with closing(sqlite3.connect(path)) as db, db:
                for statement in V1_SCHEMA.strip().split(';'):
                    if statement.strip():
                        db.execute(statement)
                db.execute('PRAGMA user_version=1')
                at = '2026-09-29T10:00:00.000Z'
                db.execute("INSERT INTO drawings(drawing_id,title,created_at,updated_at,width,height,background,revision,"
                           "head,op_count) VALUES(?,?,?,?,?,?,?,?,?,?)", (did, 'Old one', at, at, 640, 480, '#ffffff', 7, 3, 4))
                db.execute("INSERT INTO drawings(drawing_id,title,created_at,updated_at,width,height,background,trashed,"
                           "trashed_at) VALUES(?,?,?,?,?,?,?,1,?)", (trashed, 'Binned', at, at, 100, 100, 'transparent', at))
                for index, op in enumerate(ops):
                    db.execute('INSERT INTO drawing_ops VALUES(?,?,?)', (did, index, json.dumps(op)))
                db.execute('INSERT INTO drawing_thumbnails VALUES(?,?,?,?,?)', (did, 7, 'image/png', png(4, 4), at))
            v1_bytes = path.read_bytes()
            service = DrawService(path, device_id=DEVICE)
            self.assertIsNone(service.unavailable)
            backup = next(Path(temp).glob('drawings.sqlite3.store-v1-*.bak'))
            with closing(sqlite3.connect(backup)) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM drawing_ops').fetchone()[0], 4)
            self.assertEqual(len(backup.read_bytes()), len(v1_bytes))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM legacy_v1_drawing_ops').fetchone()[0], 4)   # Kept.
            drawing = service.get(did)
            self.assertEqual((drawing['title'], drawing['width'], drawing['height']), ('Old one', 640, 480))
            visible = service.visible_ops(did)
            self.assertEqual([op['points'] for op in visible], [op['points'] for op in ops[:3]])   # head = 3
            self.assertEqual(service.redo(did)['history'], {'undo': 4, 'redo': 0})              # Redo branch kept.
            self.assertEqual(len(service.visible_ops(did)), 4)
            service.undo(did)
            service.undo(did)
            self.assertEqual(len(service.visible_ops(did)), 2)
            self.assertTrue(service.get(trashed)['trashed'])
            self.assertEqual(service.get(did)['thumbnail_revision'], drawing['revision'])
            self.assertIsNotNone(service.thumbnail_get(did)['revision'])
            # Opening again does not migrate again; ids are stable.
            ids = [op['id'] for op in service.visible_ops(did)]
            again = DrawService(path, device_id=DEVICE)
            self.assertIsNone(again.store.migrated_from)
            self.assertEqual([op['id'] for op in again.visible_ops(did)], ids)
            self.assertEqual(len(list(Path(temp).glob('*.bak'))), 1)


class DrawContractTests(unittest.TestCase):
    def test_bridge_methods_are_typed_and_bounded(self):
        did = str(uuid.uuid4())
        envelope = lambda method, args: {'v': 1, 'id': 'r1', 'method': method, 'args': args}
        validate_envelope(envelope('draw.list', {'view': 'trash'}))
        validate_envelope(envelope('draw.append', {'drawing_id': did, 'op': stroke([1, 1])}))
        validate_envelope(envelope('draw.since', {'drawing_id': did, 'after': 0}))
        for method, args in (
            ('draw.list', {'view': 'all'}),
            ('draw.open', {'drawing_id': 'Shopping'}),
            ('draw.open', {'drawing_id': did, 'path': '/etc/passwd'}),
            ('draw.create', {'width': '1920'}),
            ('draw.create', {'width': True}),
            ('draw.append', {'drawing_id': did, 'op': 'stroke'}),
            ('draw.asset_upload', {'asset_id': 'x', 'index': 0, 'count': 1, 'data': 'AA=='}),
            ('draw.asset_upload', {'asset_id': 'a' * 64, 'index': 0, 'count': 1, 'data': '<script>'}),
            ('draw.thumbnail_put', {'drawing_id': did, 'revision': 1, 'image': '<script>'}),
            ('draw.export', {'drawing_id': did, 'path': '/tmp/x.png'}),
            ('draw.save', {'drawing_id': did}),
        ):
            with self.assertRaises(ValueError, msg=method):
                validate_envelope(envelope(method, args))
        self.assertIn('draw.append', UNLEDGERED)
        self.assertNotIn('draw.purge', UNLEDGERED)
        self.assertFalse(any(word in name for name in validate.__globals__['SPEC'] for word in ('sql', 'exec', 'eval', 'path', 'file')))

    def test_renderer_copies_of_shared_definitions_match(self):
        for name in ('drawing_schema.json', 'protocol_v1.json', 'conformance_v1.json'):
            python = json.loads((ROOT / 'olive/draw' / name).read_text(encoding='utf-8'))
            renderer = json.loads((ROOT / 'desktop/src/features/draw' / name).read_text(encoding='utf-8'))
            self.assertEqual(python, renderer, name)


CRASH_WRITER = r'''
import os, sys, uuid
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from olive.draw.service import DrawService
draw = DrawService(Path(sys.argv[2]), device_id=str(uuid.uuid4()))
drawing = draw.create('Crash')
print(drawing['drawing_id'], flush=True)
for index in range(int(sys.argv[3])):
    op = {'type': 'stroke', 'id': uuid.uuid4().hex, 'tool': 'pen', 'color': '#000000', 'width': 4,
          'opacity': 1, 'pressure': False, 'points': [index, index, index + 50, index + 20] * 40}
    draw.append(drawing['drawing_id'], op)
    print('saved', index + 1, flush=True)
os._exit(9)   # Simulated crash: no close, no cleanup, WAL left behind.
'''


class DrawDurabilityTests(unittest.TestCase):
    def test_completed_strokes_survive_a_killed_process(self):
        with tempfile.TemporaryDirectory(prefix='olive-draw-crash-') as temp:
            path = Path(temp) / 'drawings.sqlite3'
            result = subprocess.run([sys.executable, '-c', CRASH_WRITER, str(ROOT), str(path), '25'],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 9, result.stderr)
            lines = result.stdout.split()
            self.assertEqual(lines[-1], '25')
            draw = DrawService(path, device_id=DEVICE)
            self.assertEqual(len(draw.visible_ops(lines[0])), 25)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_storage_growth_is_measured(self):
        """Approximate stored size for typical freehand strokes (80 points each)."""
        report = []
        with tempfile.TemporaryDirectory(prefix='olive-draw-growth-') as temp:
            draw = DrawService(Path(temp) / 'drawings.sqlite3', device_id=DEVICE)
            for count in (100, 1000, 5000):
                did = draw.create(f'{count} strokes')['drawing_id']
                started = time.perf_counter()
                for index in range(count):
                    points = []
                    for step in range(80):
                        points += [round(100 + (index * 7.31 + step * 3.17) % 1700, 2), round(100 + (index * 3.7 + step * 1.9) % 880, 2)]
                    draw.append(did, stroke(points, width=6))
                elapsed = time.perf_counter() - started
                loaded = time.perf_counter()
                opened = draw.open(did)
                pages = 1
                while opened['more']:
                    opened = draw.since(did, opened['cursor'])
                    pages += 1
                load = time.perf_counter() - loaded
                report.append((count, draw.get(did)['bytes'], elapsed, load, pages))
            db_bytes = sum(p.stat().st_size for p in Path(temp).iterdir())
        for count, size, elapsed, load, pages in report:
            print(f'\nDraw storage growth: {count} strokes x 80 points -> {size / 1e6:.2f} MB serialized '
                  f'({elapsed * 1000 / count:.1f} ms per committed stroke, full load {load * 1000:.0f} ms in {pages} pages)', end='')
        print(f'\nDraw database files (all three drawings, incl. WAL): {db_bytes / 1e6:.2f} MB')
        self.assertLess(report[-1][1], document.LIMITS['max_document_bytes'])


if __name__ == '__main__':
    unittest.main()
