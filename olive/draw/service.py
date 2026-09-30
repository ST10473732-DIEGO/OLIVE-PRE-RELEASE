"""DrawService: the one owner of OLIVE Draw documents in a process.

Each drawing is a replicated record set (see ``records``). Renderer windows are
views: they send completed edits here, this service turns each into a record
with the next Lamport value for the drawing, commits it in one transaction and
announces the new feed position. Every open view (and every paired device, via
the sync engine) then applies the same records and renders the same picture.

Undo and Redo act on this device's own edits only: the stacks are local (and
survive restart); the effect is a synced visibility record.

Logs record drawing/asset IDs, sizes and categories only; never titles,
stroke points or image bytes.
"""
import base64
import json
import logging
import threading
import time
import uuid

from . import assets, records
from .document import (LIMITS, SCHEMA_VERSION, DrawingFormatError, clean_title, decode_record,
                       validate_background, validate_canvas, validate_operation)
from .records import DEFAULT_TITLE
from .store import DrawStorageError, DrawStore, utc_now

logger = logging.getLogger(__name__)

PAGE_BYTES = 600_000          # One page of records stays well below the 1 MiB bridge frame.
ASSET_CHUNK = 450_000         # Raw bytes per asset chunk on the local bridge (base64 < 600 KB).
MAX_UPLOADS = 2
UPLOAD_IDLE = 120


class DrawError(ValueError):
    """User-facing, content-free Draw errors."""


MESSAGES = {
    'draw_unavailable': 'Drawing storage unavailable. Your drawings were left untouched.',
    'draw_storage_unavailable': 'Drawing storage unavailable. Your drawings were left untouched.',
    'draw_storage_newer': 'Drawing storage was created by a newer OLIVE. It was left untouched.',
    'draw_storage_unrecognized': 'Drawing storage unavailable: the database was not recognised and was left untouched.',
    'drawing_not_found': 'That drawing no longer exists.',
    'drawing_purged': 'That drawing was permanently deleted.',
    'drawing_unsupported': 'Drawing format unsupported. It was made by a newer OLIVE and was left untouched.',
    'drawing_corrupted': 'Could not load drawing. The stored data was kept for recovery.',
    'canvas_too_large': 'Canvas too large. Drawings can be up to 8192 pixels on a side and 33.5 million pixels in total.',
    'invalid_canvas': 'Canvas too small or invalid. Use whole pixels between 16 and 8192.',
    'invalid_background': 'Choose a white or transparent background.',
    'invalid_title': 'Drawing titles are plain text.',
    'invalid_operation': 'Could not save drawing: an edit was malformed.',
    'invalid_record': 'Could not save drawing: an edit was malformed.',
    'drawing_too_large': 'Could not save drawing: it reached its size limit. Start a new drawing or clear this one.',
    'too_many_operations': 'Could not save drawing: it reached 20,000 edits. Start a new drawing or clear this one.',
    'drawings_capacity': 'Drawing limit reached. Delete drawings you no longer need.',
    'in_trash': 'This drawing is in Recently Deleted. Restore it to edit it.',
    'not_in_trash': 'Move the drawing to Recently Deleted before deleting it permanently.',
    'invalid_thumbnail': 'Thumbnail rejected.',
    'invalid_image': 'Could not import image: the file is not a valid PNG or JPEG image.',
    'unsupported_image': 'Could not import image: only PNG and JPEG images can be imported.',
    'image_too_large': 'Could not import image: it is too large. Images can be up to 8192 pixels on a side, '
                       '33.5 million pixels and 48 MB.',
    'checksum_mismatch': 'Could not import image: the data did not arrive intact.',
    'asset_not_found': 'That image is not available on this device yet.',
    'upload_busy': 'Could not import image: another import is still in progress.',
}
FORMAT_CODES = {
    'invalid_number': 'invalid_operation', 'invalid_points': 'invalid_operation',
    'unsupported_operation': 'invalid_operation', 'operation_too_large': 'invalid_operation',
    'invalid_operation': 'invalid_operation', 'invalid_record': 'invalid_operation',
    'canvas_too_large': 'canvas_too_large', 'invalid_canvas': 'invalid_canvas',
    'invalid_background': 'invalid_background', 'invalid_title': 'invalid_title',
}


def error(code):
    return DrawError(MESSAGES.get(code, 'Could not save drawing.'))


def drawing_id(value):
    if type(value) is not str:
        raise error('drawing_not_found')
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise error('drawing_not_found') from None
    return value


def image_info(data):
    return assets.image_info(data)


class DrawService:
    def __init__(self, path, *, device_id, publish=lambda topic, data: None):
        self.path = path
        self.device_id = device_id
        self.publish = publish
        self.store = None
        self.unavailable = None
        self.listeners = []       # Sync layer: called after commits with (drawing_id or None, peer or None).
        self.uploads = {}         # asset_id -> staging for renderer uploads
        self.upload_lock = threading.Lock()
        try:
            self.store = DrawStore(path, device_id=device_id)
            if self.store.migrated_from:
                logger.info('Drawing storage migrated from store schema %s', self.store.migrated_from)
        except DrawStorageError as failure:
            self.unavailable = str(failure)
            logger.warning('Drawing storage unavailable: %s', failure)
        except Exception:
            self.unavailable = 'draw_storage_unavailable'
            logger.warning('Drawing storage unavailable')

    # --- plumbing ---------------------------------------------------------------
    def _require(self):
        if self.store is None:
            raise error(self.unavailable or 'draw_unavailable')
        return self.store

    @staticmethod
    def _format(failure):
        return error(FORMAT_CODES.get(str(failure), 'invalid_operation'))

    def _emit(self, topic, data):
        try:
            self.publish(topic, data)
        except Exception:
            logger.warning('Draw event failed')

    def _committed(self, did, *, reason=None, cursor=None, peer=None):
        """After a commit: tell views (records/list) and the sync layer."""
        if cursor is not None:
            self._emit('draw.records', {'drawing_id': did, 'cursor': cursor})
        if reason:
            self._emit('draw.changed', {'drawing_id': did, 'reason': reason})
        for listener in list(self.listeners):
            try:
                listener(did, peer)
            except Exception:
                logger.warning('Draw change listener failed')

    @staticmethod
    def _summary(row, thumb=None):
        return {
            'drawing_id': row['drawing_id'], 'title': row['title'] or DEFAULT_TITLE,
            'created_at': row['created_at'], 'updated_at': row['updated_at'],
            'width': row['width'], 'height': row['height'], 'background': row['background'],
            'schema_version': row['schema_version'], 'revision': row['revision'],
            'op_count': row['op_count'], 'bytes': row['doc_bytes'],
            'trashed': bool(row['trashed']), 'trashed_at': row['trashed_at'],
            'status': 'unsupported' if row['schema_version'] > SCHEMA_VERSION else row['status'],
            'thumbnail_revision': thumb,
        }

    def _row(self, db, did):
        row = DrawStore.drawing(db, did)
        if row is None:
            raise error('drawing_purged' if DrawStore.purged(db, did) else 'drawing_not_found')
        return row

    def _described(self, db, row):
        thumb = db.execute('SELECT revision FROM draw_thumbnails WHERE drawing_id=?', (row['drawing_id'],)).fetchone()
        return self._summary(row, thumb[0] if thumb else None)

    def _editable(self, db, did):
        row = self._row(db, did)
        if row['schema_version'] > SCHEMA_VERSION:
            raise error('drawing_unsupported')
        if row['status'] != 'ok':
            raise error('drawing_corrupted')
        return row

    def _local(self, db, did, kind, body, **options):
        record = records.make(db, self.device_id, did, kind, body, **options)
        status = records.insert(db, record)
        if status != 'applied':
            code = status.partition(':')[2] or ('drawing_purged' if status == 'purged' else 'invalid_record')
            raise error(code)
        return record, self._seq(db, record['record_id'])

    @staticmethod
    def _seq(db, record_id):
        return db.execute('SELECT seq FROM draw_records WHERE record_id=?', (record_id,)).fetchone()[0]

    # --- library ----------------------------------------------------------------
    def status(self):
        if self.store is None:
            return {'available': False, 'message': MESSAGES.get(self.unavailable, MESSAGES['draw_unavailable'])}
        with self.store.transaction(read_only=True) as db:
            count = db.execute('SELECT COUNT(*) FROM drawings WHERE trashed=0').fetchone()[0]
        return {'available': True, 'message': '', 'drawings': count, 'schema_version': SCHEMA_VERSION,
                'limits': dict(LIMITS)}

    def list_drawings(self, view='drawings'):
        store = self._require()
        if view not in ('drawings', 'trash'):
            raise DrawError('Unknown Draw view')
        order = 'd.trashed_at DESC, d.last_seq DESC' if view == 'trash' else 'd.last_seq DESC'
        with store.transaction(read_only=True) as db:
            rows = db.execute('SELECT d.*, t.revision AS thumb FROM drawings d '
                              'LEFT JOIN draw_thumbnails t ON t.drawing_id=d.drawing_id '
                              f'WHERE d.trashed=? ORDER BY {order} LIMIT ?',
                              (int(view == 'trash'), LIMITS['max_drawings'])).fetchall()
            counts = dict(db.execute('SELECT trashed, COUNT(*) FROM drawings GROUP BY trashed').fetchall())
        return {'drawings': [self._summary(row, row['thumb']) for row in rows],
                'counts': {'drawings': counts.get(0, 0), 'trash': counts.get(1, 0)}}

    def get(self, did):
        did = drawing_id(did)
        with self._require().transaction(read_only=True) as db:
            return self._described(db, self._row(db, did))

    def create(self, title='', width=1920, height=1080, background='#ffffff'):
        store = self._require()
        try:
            title = clean_title(title)
            width, height = validate_canvas(width, height)
            background = validate_background(background)
        except DrawingFormatError as failure:
            raise self._format(failure) from None
        did = str(uuid.uuid4())
        now = utc_now()
        with store.transaction() as db:
            if db.execute('SELECT COUNT(*) FROM drawings').fetchone()[0] >= LIMITS['max_drawings']:
                raise error('drawings_capacity')
            _, seq = self._local(db, did, 'create', {'width': width, 'height': height, 'background': background,
                                                     'title': title or DEFAULT_TITLE, 'created_at': now})
            summary = self._described(db, self._row(db, did))
        logger.info('Drawing created %s (%dx%d)', did, width, height)
        self._committed(did, reason='created', cursor=seq)
        return summary

    def _meta(self, did, field, value, reason):
        did = drawing_id(did)
        with self._require().transaction() as db:
            self._row(db, did)
            _, seq = self._local(db, did, 'meta', {'field': field, 'value': value})
            summary = self._described(db, self._row(db, did))
        self._committed(did, reason=reason, cursor=seq)
        return summary

    def rename(self, did, title):
        try:
            title = clean_title(title) or DEFAULT_TITLE
        except DrawingFormatError as failure:
            raise self._format(failure) from None
        return self._meta(did, 'title', title, 'renamed')

    def trash(self, did):
        return self._meta(did, 'trashed', True, 'trashed')

    def restore(self, did):
        return self._meta(did, 'trashed', False, 'restored')

    def duplicate(self, did):
        """A new drawing (new id) with copies of the visible operations, in order.
        Image operations keep the same asset id: bytes are never duplicated."""
        did = drawing_id(did)
        copy = str(uuid.uuid4())
        now = utc_now()
        with self._require().transaction() as db:
            row = self._editable(db, did)
            if db.execute('SELECT COUNT(*) FROM drawings').fetchone()[0] >= LIMITS['max_drawings']:
                raise error('drawings_capacity')
            title = (row['title'] + ' (copy)')[:LIMITS['max_title_chars']]
            self._local(db, copy, 'create', {'width': row['width'], 'height': row['height'],
                                             'background': row['background'], 'title': title, 'created_at': now})
            seq = None
            for op in self._visible_ops(db, did):
                body = dict(op)
                body.pop('id')
                record, seq = self._local(db, copy, 'op', body)
                records.push(db, copy, 'undo', record['record_id'])
            db.execute('INSERT INTO draw_thumbnails(drawing_id,revision,mime,image,created_at) '
                       'SELECT ?, (SELECT revision FROM drawings WHERE drawing_id=?), mime, image, ? '
                       'FROM draw_thumbnails WHERE drawing_id=?', (copy, copy, now, did))
            summary = self._described(db, self._row(db, copy))
        self._committed(copy, reason='duplicated', cursor=seq)
        return summary

    def purge(self, did):
        """Permanent deletion, only from Recently Deleted. A tombstone stays so a
        stale peer can never bring the drawing back."""
        did = drawing_id(did)
        with self._require().transaction() as db:
            row = self._row(db, did)
            if not row['trashed']:
                raise error('not_in_trash')
            self._purge(db, did, device=self.device_id, at=utc_now())
        logger.info('Drawing permanently deleted %s', did)
        self._committed(did, reason='purged')
        return {'purged': True}

    @staticmethod
    def _purge(db, did, *, device, at):
        db.execute('DELETE FROM draw_visibility WHERE target IN (SELECT record_id FROM draw_records WHERE drawing_id=?)', (did,))
        for table in ('draw_records', 'draw_history', 'draw_thumbnails', 'draw_wanted', 'drawings'):
            db.execute(f'DELETE FROM {table} WHERE drawing_id=?', (did,))
        db.execute('INSERT OR IGNORE INTO draw_purges VALUES(?,?,?,?)', (did, at, device, DrawStore.next_seq(db)))

    def is_purged(self, did):
        with self._require().transaction(read_only=True) as db:
            return DrawStore.purged(db, did)

    # --- document ---------------------------------------------------------------
    @staticmethod
    def _visible_ops(db, did):
        rows = db.execute("SELECT r.body FROM draw_records r LEFT JOIN draw_visibility v ON v.target=r.record_id "
                          "WHERE r.drawing_id=? AND r.kind='op' AND COALESCE(v.hidden,0)=0 ORDER BY r.sort_key", (did,))
        return [json.loads(r[0])['body'] for r in rows]

    def since(self, did, after=0):
        """Records of one drawing after a feed position, a page at a time. A view
        applies them to its replica in any order (the rules are commutative)."""
        did = drawing_id(did)
        if type(after) is not int or after < 0:
            raise error('drawing_not_found')
        with self._require().transaction(read_only=True) as db:
            row = self._row(db, did)
            if row['schema_version'] > SCHEMA_VERSION:
                raise error('drawing_unsupported')
            if row['status'] != 'ok':
                raise error('drawing_corrupted')
            rows = db.execute('SELECT seq, body FROM draw_records WHERE drawing_id=? AND seq>? ORDER BY seq',
                              (did, after))
            out, size, cursor, more = [], 0, after, False
            for seq, data in rows:
                if out and size + len(data) > PAGE_BYTES:
                    more = True
                    break
                try:
                    out.append(decode_record(data))
                except DrawingFormatError:
                    logger.warning('Drawing %s has an unreadable record', did)
                    raise error('drawing_corrupted') from None
                size += len(data)
                cursor = seq
            if not more:
                cursor = max(cursor, self._drawing_cursor(db, did, after))
            summary = self._described(db, row)
            history = records.history(db, did)
            missing = [r[0] for r in db.execute('SELECT asset_id FROM draw_wanted WHERE drawing_id=? LIMIT 64', (did,))]
        return {'drawing': summary, 'records': out, 'cursor': cursor, 'more': more, 'history': history,
                'missing_assets': missing, 'device': self.device_id}

    @staticmethod
    def _drawing_cursor(db, did, after):
        value = db.execute('SELECT MAX(seq) FROM draw_records WHERE drawing_id=?', (did,)).fetchone()[0]
        return max(after, value or 0)

    def open(self, did):
        return self.since(did, 0)

    def append(self, did, op):
        """One completed local edit. ``op['id']`` is a 32-hex id chosen by the
        renderer, so a retried request is recognised and not applied twice."""
        did = drawing_id(did)
        if type(op) is not dict or type(op.get('id')) is not str or not records_id(op['id']):
            raise error('invalid_operation')
        try:
            validate_operation(op)
        except DrawingFormatError as failure:
            raise self._format(failure) from None
        with self._require().transaction() as db:
            row = self._editable(db, did)
            existing = db.execute('SELECT seq, body, drawing_id, device FROM draw_records WHERE record_id=?',
                                  (op['id'],)).fetchone()
            if existing is not None:
                if existing['drawing_id'] != did or existing['device'] != self.device_id:
                    raise error('invalid_operation')
                record, seq = json.loads(existing['body']), existing['seq']
            else:
                if row['trashed']:
                    raise error('in_trash')
                body = dict(op)
                body.pop('id')
                record, seq = self._local(db, did, 'op', body, record_id=op['id'])
                records.push(db, did, 'undo', record['record_id'])
                records.clear_stack(db, did, 'redo')
            history = records.history(db, did)
            summary = self._described(db, self._row(db, did))
        self._committed(did, cursor=seq)
        return {'record': record, 'cursor': seq, 'history': history, 'drawing': summary}

    def _step(self, did, source, target_stack, hidden):
        did = drawing_id(did)
        with self._require().transaction() as db:
            row = self._editable(db, did)
            if row['trashed']:
                raise error('in_trash')
            record = seq = None
            while True:
                target = records.pop(db, did, source)
                if target is None:
                    break
                exists = db.execute("SELECT 1 FROM draw_records WHERE record_id=? AND kind='op'", (target,)).fetchone()
                if exists is None or records.hidden(db, target) == hidden:
                    continue   # Already undone/redone elsewhere (another window): skip it.
                record, seq = self._local(db, did, 'visibility', {'target': target, 'hidden': hidden})
                records.push(db, did, target_stack, target)
                break
            history = records.history(db, did)
        if record is not None:
            self._committed(did, cursor=seq)
        return {'record': record, 'cursor': seq, 'history': history}

    def undo(self, did):
        """Undo this device's latest visible edit (never another device's)."""
        return self._step(did, 'undo', 'redo', True)

    def redo(self, did):
        return self._step(did, 'redo', 'undo', False)

    def visible_ops(self, did):
        did = drawing_id(did)
        with self._require().transaction(read_only=True) as db:
            self._row(db, did)
            return self._visible_ops(db, did)

    # --- thumbnails ---------------------------------------------------------------
    def thumbnail_put(self, did, revision, image):
        """A small bounded preview rendered by the renderer; a local cache, never synced."""
        did = drawing_id(did)
        if type(image) is not str or len(image) > (LIMITS['thumbnail_max_bytes'] * 4) // 3 + 8:
            raise error('invalid_thumbnail')
        try:
            data = base64.b64decode(image, validate=True)
        except Exception:
            raise error('invalid_thumbnail') from None
        info = image_info(data)
        side = LIMITS['thumbnail_max_side']
        if (len(data) > LIMITS['thumbnail_max_bytes'] or info is None or not 1 <= info[1] <= side
                or not 1 <= info[2] <= side):
            raise error('invalid_thumbnail')
        with self._require().transaction() as db:
            row = self._row(db, did)
            if type(revision) is not int or not 0 <= revision <= row['revision']:
                raise error('invalid_thumbnail')
            current = db.execute('SELECT revision FROM draw_thumbnails WHERE drawing_id=?', (did,)).fetchone()
            if current is not None and current[0] > revision:
                return {'stored': False, 'revision': current[0]}
            db.execute('INSERT INTO draw_thumbnails VALUES(?,?,?,?,?) ON CONFLICT(drawing_id) DO UPDATE SET '
                       'revision=excluded.revision, mime=excluded.mime, image=excluded.image, created_at=excluded.created_at',
                       (did, revision, info[0], data, utc_now()))
        return {'stored': True, 'revision': revision}

    def thumbnail_get(self, did):
        did = drawing_id(did)
        with self._require().transaction(read_only=True) as db:
            self._row(db, did)
            row = db.execute('SELECT revision, mime, image FROM draw_thumbnails WHERE drawing_id=?', (did,)).fetchone()
        if row is None:
            return {'drawing_id': did, 'revision': None, 'mime': '', 'image': ''}
        return {'drawing_id': did, 'revision': row['revision'], 'mime': row['mime'],
                'image': base64.b64encode(row['image']).decode('ascii')}

    def find_by_title(self, title):
        """Exact, case-insensitive title matches among drawings not in the trash."""
        wanted = ' '.join(str(title).split()).casefold()
        return [d for d in self.list_drawings('drawings')['drawings'] if d['title'].casefold() == wanted]

    # --- assets -------------------------------------------------------------------
    def asset_info(self, asset_id):
        with self._require().transaction(read_only=True) as db:
            row = db.execute('SELECT asset_id, mime, width, height, size FROM draw_assets WHERE asset_id=?',
                             (asset_id,)).fetchone()
        return dict(row) if row else None

    def store_asset(self, data, *, origin='local', expected_id=None):
        """Validate and keep one image. Content-addressed: the same bytes are stored once."""
        try:
            asset_id, mime, width, height = assets.validate(data, expected_id=expected_id)
        except assets.AssetError as failure:
            raise error(str(failure)) from None
        with self._require().transaction() as db:
            if not db.execute('SELECT 1 FROM draw_assets WHERE asset_id=?', (asset_id,)).fetchone():
                db.execute('INSERT INTO draw_assets VALUES(?,?,?,?,?,?,?,?)',
                           (asset_id, mime, width, height, len(data), data, utc_now(), origin))
            db.execute('DELETE FROM draw_wanted WHERE asset_id=?', (asset_id,))
        logger.info('Draw asset stored %s (%d bytes, %s)', asset_id[:12], len(data), origin)
        self._emit('draw.asset', {'asset_id': asset_id})
        return {'asset_id': asset_id, 'mime': mime, 'width': width, 'height': height, 'size': len(data)}

    def asset_upload(self, asset_id, index, count, data):
        """Renderer upload of a normalized image in bridge-sized chunks. Staged in
        memory (bounded), checked against its SHA-256 id, then stored."""
        if type(asset_id) is not str or len(asset_id) != 64 or type(index) is not int or type(count) is not int:
            raise error('invalid_image')
        if not 1 <= count <= -(-LIMITS['max_asset_bytes'] // ASSET_CHUNK) or not 0 <= index < count:
            raise error('image_too_large')
        try:
            chunk = base64.b64decode(data, validate=True)
        except Exception:
            raise error('invalid_image') from None
        if len(chunk) > ASSET_CHUNK:
            raise error('image_too_large')
        if self.asset_info(asset_id) is not None:
            return {'stored': True, 'asset_id': asset_id, 'existing': True}
        now = time.monotonic()
        with self.upload_lock:
            for key in [k for k, v in self.uploads.items() if v['expires'] < now]:
                self.uploads.pop(key)
            staging = self.uploads.get(asset_id)
            if staging is None:
                if len(self.uploads) >= MAX_UPLOADS:
                    raise error('upload_busy')
                staging = self.uploads[asset_id] = {'count': count, 'parts': {}, 'size': 0}
            elif staging['count'] != count:
                self.uploads.pop(asset_id, None)
                raise error('invalid_image')
            staging['expires'] = now + UPLOAD_IDLE
            if index not in staging['parts']:
                staging['parts'][index] = chunk
                staging['size'] += len(chunk)
            if staging['size'] > LIMITS['max_asset_bytes']:
                self.uploads.pop(asset_id, None)
                raise error('image_too_large')
            if len(staging['parts']) < count:
                return {'stored': False, 'received': len(staging['parts'])}
            self.uploads.pop(asset_id, None)
        payload = b''.join(staging['parts'][i] for i in range(count))
        info = self.store_asset(payload, origin='local', expected_id=asset_id)
        return dict(info, stored=True)

    def asset_chunk(self, asset_id, index):
        """One chunk of a stored asset for the renderer (base64)."""
        with self._require().transaction(read_only=True) as db:
            row = db.execute('SELECT mime, width, height, size, substr(data, ?, ?) AS part FROM draw_assets WHERE asset_id=?',
                             (index * ASSET_CHUNK + 1, ASSET_CHUNK, asset_id)).fetchone()
        if row is None:
            raise error('asset_not_found')
        count = max(1, -(-row['size'] // ASSET_CHUNK))
        if not 0 <= index < count:
            raise error('asset_not_found')
        return {'asset_id': asset_id, 'mime': row['mime'], 'width': row['width'], 'height': row['height'],
                'size': row['size'], 'index': index, 'count': count,
                'data': base64.b64encode(bytes(row['part'])).decode('ascii')}

    def ingest_trusted_image(self, path):
        """Future hook (e.g. "Open this REIMAGINE image in Draw"): normalize an
        image file that OLIVE itself produced into an asset. Orientation is
        applied, metadata dropped, colour converted to sRGB, re-encoded as PNG.
        Not wired to any UI or Chat action in this milestone."""
        from PIL import Image, ImageOps
        import io
        from pathlib import Path
        source = Path(path)
        if not source.is_file() or source.stat().st_size > LIMITS['max_import_bytes']:
            raise error('image_too_large')
        data = source.read_bytes()
        info = image_info(data)
        if info is None:
            raise error('unsupported_image')
        if info[1] * info[2] > LIMITS['max_import_pixels']:
            raise error('image_too_large')
        try:
            with Image.open(io.BytesIO(data)) as image:
                image = ImageOps.exif_transpose(image).convert('RGBA')
                image.thumbnail((LIMITS['max_asset_side'], LIMITS['max_asset_side']))
                out = io.BytesIO()
                image.save(out, format='PNG', optimize=False)
        except Exception:
            raise error('invalid_image') from None
        return self.store_asset(out.getvalue(), origin='trusted-file')

    # --- sync hooks (used by olive.draw.sync_engine) ------------------------------
    def epoch(self):
        with self._require().transaction(read_only=True) as db:
            return DrawStore.meta_value(db, 'epoch')


def records_id(value):
    from .document import RECORD_ID
    return bool(RECORD_ID.fullmatch(value))
