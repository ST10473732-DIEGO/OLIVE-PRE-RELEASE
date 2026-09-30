"""olive-draw/1 sync engine. Transport-agnostic; OLIVE Connect adapts it.

Model (every device runs the same code; no device is authoritative):

* A drawing is a grow-only set of immutable records (``records``). Replicas
  that hold the same set render the same picture, whatever order the records
  arrived in; so sync only has to make the sets equal.
* Each device keeps a durable change feed: every record it stores (made here
  or received) and every permanent-deletion tombstone gets a feed ``seq``. For
  each peer it stores ``acked_seq``: the feed position that peer confirmed.
* A pump sends the feed after ``acked_seq`` in bounded batches. The receiver
  inserts each record idempotently in one transaction and answers per entry
  (applied / duplicate / purged / rejected); the cursor then advances over the
  whole batch. A lost answer means a resend, which is harmless.
* Records a device received from a peer are forwarded to its other peers (so
  A -> B -> C converges) but never echoed back to the peer they came from.
* A tombstone beats every record: records for a purged drawing are dropped and
  answered 'purged', which makes a stale sender purge too.
* Image bytes are not records. A receiver lists the asset ids it still needs
  (``wants``) in every answer; the sender streams those assets in bounded,
  checksummed chunks. A partial asset is never visible; an interrupted
  transfer simply starts again.
* Epochs: every store has a random epoch, renewed on restore. If a peer's epoch
  changes, its cursor resets to 0 and everything is offered again.
"""
import hashlib
import json
import logging
import threading
import time
import uuid

from . import records
from .protocol import (CAPABILITY, LIMITS, PROTOCOL, SCHEMAS, DrawProtocolError, b64, validate_result)
from .service import DrawError
from .store import DrawStore, utc_now

logger = logging.getLogger(__name__)

__all__ = ['DrawSyncEngine', 'DrawSyncError', 'CAPABILITY']


class DrawSyncError(RuntimeError):
    """Fixed categories for peer/transport failures."""


class DrawSyncEngine:
    def __init__(self, service, local_id):
        self.s = service
        self.local_id = local_id
        self.lock = threading.Lock()
        self.states = {}         # peer -> public status
        self.transfers = {}      # (peer, transfer_id) -> staging (receiver side)
        self.refused = {}        # peer -> {record_id or asset_id: code}

    # --- status -----------------------------------------------------------------
    def set_state(self, peer, state, **extra):
        with self.lock:
            current = dict(self.states.get(peer, {}))
            current.update(state=state, **extra)
            current['updated'] = time.time()
            self.states[peer] = current

    def state(self, peer):
        with self.lock:
            return dict(self.states.get(peer, {'state': 'idle'}))

    # --- durable peer state ---------------------------------------------------------
    def _store(self):
        if self.s.store is None:
            raise DrawProtocolError('draw_unavailable')
        return self.s.store

    def peer(self, peer):
        with self._store().transaction(read_only=True) as db:
            row = db.execute('SELECT * FROM draw_peers WHERE device_id=?', (peer,)).fetchone()
        return dict(row) if row else {'device_id': peer, 'acked_seq': 0, 'peer_epoch': None, 'last_sync': None,
                                      'last_error': None, 'protocol': None}

    def save_peer(self, peer, **values):
        with self._store().transaction() as db:
            db.execute('INSERT OR IGNORE INTO draw_peers(device_id) VALUES(?)', (peer,))
            for key, value in values.items():
                if key not in ('acked_seq', 'peer_epoch', 'last_sync', 'last_error', 'protocol'):
                    raise ValueError(key)
                db.execute(f'UPDATE draw_peers SET {key}=? WHERE device_id=?', (value, peer))

    def _observe_epoch(self, peer, epoch):
        stored = self.peer(peer)
        if stored['peer_epoch'] != epoch:
            if stored['peer_epoch'] is not None:
                # The peer's store was replaced (restore/reinstall): it may lack
                # what it once confirmed -- including records it made itself, so
                # echo suppression for them is lifted too. Offer everything again.
                with self._store().transaction() as db:
                    db.execute('UPDATE draw_peers SET acked_seq=0 WHERE device_id=?', (peer,))
                    db.execute("UPDATE draw_records SET source='' WHERE source=?", (peer,))
                logger.info('Draw peer epoch changed; full resend scheduled')
            self.save_peer(peer, peer_epoch=epoch, protocol=PROTOCOL)
            return True
        return False

    def wants(self):
        with self._store().transaction(read_only=True) as db:
            return [r[0] for r in db.execute('SELECT asset_id FROM draw_wanted ORDER BY since, asset_id LIMIT ?',
                                             (LIMITS['max_wants'],))]

    # --- receiving ----------------------------------------------------------------
    def handle(self, peer, request):
        operation, arguments = request['operation'], request['arguments']
        epoch = self.s.epoch()
        if operation == 'hello':
            if PROTOCOL not in arguments['versions']:
                raise DrawProtocolError('unsupported_protocol')
            return {'versions': [PROTOCOL], 'epoch': epoch, 'schemas': list(SCHEMAS), 'wants': self.wants()}
        self._observe_epoch(peer, arguments['epoch'])
        if operation == 'sync':
            return {'epoch': epoch, 'results': self._receive_entries(peer, arguments['entries']), 'wants': self.wants()}
        return dict(self._receive_chunk(peer, arguments), epoch=epoch)

    def _receive_entries(self, peer, entries):
        results, touched, listed = [], {}, set()
        now = utc_now()
        with self._store().transaction() as db:
            for entry in entries:
                if 'purge' in entry:
                    purge = entry['purge']
                    did = purge['drawing_id']
                    if DrawStore.purged(db, did):
                        results.append({'status': 'duplicate'})
                        continue
                    self.s._purge(db, did, device=purge['device'], at=purge['at'])
                    results.append({'status': 'applied'})
                    touched[did] = None
                    listed.add(did)
                    continue
                record = entry['record']
                status = records.insert(db, record, source=peer, now=now)
                if status.startswith('rejected'):
                    code = status.partition(':')[2] or 'invalid_record'
                    results.append({'status': 'rejected', 'error': code if code in (
                        'invalid_record', 'drawing_too_large', 'too_many_operations', 'drawings_capacity') else 'invalid_record'})
                    continue
                results.append({'status': status})
                if status == 'applied':
                    did = record['drawing_id']
                    touched[did] = db.execute('SELECT seq FROM draw_records WHERE record_id=?', (record['record_id'],)).fetchone()[0]
                    if record['kind'] in ('create', 'meta'):
                        listed.add(did)
        for did, cursor in touched.items():
            self.s._committed(did, reason='remote' if did in listed else None, cursor=cursor, peer=peer)
        return results

    def _receive_chunk(self, peer, arguments):
        now = time.monotonic()
        with self.lock:
            for key in [k for k, v in self.transfers.items() if v['expires'] < now]:
                self.transfers.pop(key)
            key = (peer, arguments['transfer_id'])
            staging = self.transfers.get(key)
            fixed = ('asset_id', 'mime', 'width', 'height', 'total_bytes', 'count')
            if staging is None:
                if self.s.asset_info(arguments['asset_id']) is not None:
                    return {'status': 'exists'}
                mine = [v for (p, _), v in self.transfers.items() if p == peer]
                if len(mine) >= LIMITS['max_asset_transfers_per_peer'] or \
                        sum(v['total_bytes'] for v in mine) + arguments['total_bytes'] > LIMITS['max_staged_bytes_per_peer']:
                    raise DrawProtocolError('busy')
                staging = dict({k: arguments[k] for k in fixed}, parts={}, size=0)
                self.transfers[key] = staging
            elif any(staging[k] != arguments[k] for k in fixed):
                self.transfers.pop(key, None)
                raise DrawProtocolError('malformed_message')
            staging['expires'] = now + LIMITS['transfer_idle_seconds']
            if arguments['index'] not in staging['parts']:
                staging['parts'][arguments['index']] = arguments['data']
                staging['size'] += len(arguments['data'])
            if staging['size'] > staging['total_bytes']:
                self.transfers.pop(key, None)
                raise DrawProtocolError('payload_too_large')
            if len(staging['parts']) < staging['count']:
                return {'status': 'partial'}
            self.transfers.pop(key, None)
        payload = b''.join(staging['parts'][i] for i in range(staging['count']))
        if len(payload) != staging['total_bytes'] or hashlib.sha256(payload).hexdigest() != staging['asset_id']:
            return {'status': 'rejected', 'error': 'checksum_mismatch'}
        try:
            info = self.s.store_asset(payload, origin='peer', expected_id=staging['asset_id'])
        except DrawError:
            return {'status': 'rejected', 'error': 'invalid_image'}
        if info['mime'] != staging['mime'] or (info['width'], info['height']) != (staging['width'], staging['height']):
            return {'status': 'rejected', 'error': 'invalid_image'}
        return {'status': 'stored'}

    # --- sending --------------------------------------------------------------------
    def pump(self, peer, send, *, hello=False, keep_going=lambda: True):
        """Push this device's pending feed (and wanted assets) to ``peer``.

        ``send(operation, arguments)`` performs one request and returns the
        peer's completed result dict, or raises. Returns 'synced' or 'partial'.
        """
        self.set_state(peer, 'syncing')
        if hello:
            result = validate_result('hello', send('hello', {'versions': [PROTOCOL], 'schemas': list(SCHEMAS)}))
            if PROTOCOL not in result['versions']:
                raise DrawSyncError('unsupported_protocol')
            self._observe_epoch(peer, result['epoch'])
            self._serve_assets(peer, result['wants'], send, keep_going)
        for _ in range(LIMITS['max_rounds_per_pump']):
            if not keep_going():
                return 'partial'
            batch = self._prepare(peer)
            if batch is None:
                self.set_state(peer, 'synced', last_sync=time.time(), pending=0)
                self.save_peer(peer, last_sync=utc_now(), last_error=None)
                return 'synced'
            if not batch['entries']:
                self.save_peer(peer, acked_seq=batch['last'])
                continue   # Only echo-suppressed entries.
            arguments = {'epoch': self.s.epoch(), 'entries': batch['entries']}
            result = validate_result('sync', send('sync', arguments), batch['entries'])
            if self._observe_epoch(peer, result['epoch']) and self.peer(peer)['acked_seq'] == 0:
                continue   # The peer's store changed identity: start over from 0.
            self._process(peer, batch, result)
            self._serve_assets(peer, result['wants'], send, keep_going)
        return 'partial'

    def _prepare(self, peer):
        acked = self.peer(peer)['acked_seq']
        budget = LIMITS['max_request_bytes']
        entries, last, size = [], acked, 0
        with self._store().transaction(read_only=True) as db:
            rows = db.execute(
                "SELECT seq, 'record' AS kind, body, source, bytes FROM draw_records WHERE seq>? "
                "UNION ALL SELECT seq, 'purge', drawing_id || ' ' || purged_at || ' ' || device, '', 64 FROM draw_purges WHERE seq>? "
                'ORDER BY seq LIMIT ?', (acked, acked, LIMITS['max_entries'])).fetchall()
            for row in rows:
                if entries and size + row['bytes'] > budget:
                    break
                last = row['seq']
                if row['kind'] == 'purge':
                    did, at, device = row['body'].split(' ')
                    entries.append({'seq': row['seq'], 'purge': {'drawing_id': did, 'at': at, 'device': device}})
                    size += 64
                    continue
                if row['source'] == peer:
                    continue   # Came from this peer: never echo it back.
                try:
                    record = json.loads(row['body'])
                except ValueError:
                    continue   # Unreadable local data is kept, never sent.
                entries.append({'seq': row['seq'], 'record': record})
                size += row['bytes']
        if last == acked:
            return None
        return {'entries': entries, 'last': last, 'acked': acked}

    def _process(self, peer, batch, result):
        refused = self.refused.setdefault(peer, {})
        for entry, row in zip(batch['entries'], result['results']):
            if 'record' not in entry:
                continue
            record = entry['record']
            if row['status'] == 'purged':
                # The peer holds a tombstone: this drawing was permanently deleted.
                with self._store().transaction() as db:
                    if not DrawStore.purged(db, record['drawing_id']):
                        self.s._purge(db, record['drawing_id'], device=peer, at=utc_now())
                        purged = True
                    else:
                        purged = False
                if purged:
                    self.s._committed(record['drawing_id'], reason='purged', peer=peer)
            elif row['status'] == 'rejected':
                # Never let one refused record block every later change.
                refused[record['record_id']] = row['error'] or 'invalid_record'
        self.save_peer(peer, acked_seq=batch['last'], last_error=None)

    def _serve_assets(self, peer, wants, send, keep_going):
        refused = self.refused.setdefault(peer, {})
        for asset_id in wants:
            if not keep_going() or asset_id in refused:
                continue
            with self._store().transaction(read_only=True) as db:
                row = db.execute('SELECT mime, width, height, data FROM draw_assets WHERE asset_id=?', (asset_id,)).fetchone()
            if row is None:
                continue   # Not here either; another peer may have it.
            data = bytes(row['data'])
            size = LIMITS['asset_chunk_bytes']
            count = -(-len(data) // size)
            arguments = {'epoch': self.s.epoch(), 'transfer_id': str(uuid.uuid4()), 'asset_id': asset_id,
                         'mime': row['mime'], 'width': row['width'], 'height': row['height'],
                         'total_bytes': len(data), 'count': count}
            for index in range(count):
                result = validate_result('asset', send('asset', dict(arguments, index=index,
                                                                      data=b64(data[index * size:(index + 1) * size]))))
                if result['status'] in ('exists', 'stored'):
                    break
                if result['status'] == 'rejected':
                    refused[asset_id] = result['error'] or 'invalid_image'
                    break

    # --- status helpers --------------------------------------------------------------
    def pending(self, peer):
        acked = self.peer(peer)['acked_seq']
        with self._store().transaction(read_only=True) as db:
            records_left = db.execute('SELECT COUNT(*) FROM draw_records WHERE seq>? AND source!=?', (acked, peer)).fetchone()[0]
            purges = db.execute('SELECT COUNT(*) FROM draw_purges WHERE seq>?', (acked,)).fetchone()[0]
        return records_left + purges

    def pending_assets(self):
        with self._store().transaction(read_only=True) as db:
            return db.execute('SELECT COUNT(*) FROM draw_wanted').fetchone()[0]

    def forget(self, peer):
        """Revocation/permission Off: drop transient state; durable cursors stay."""
        with self.lock:
            for key in [k for k in self.transfers if k[0] == peer]:
                self.transfers.pop(key)
            self.refused.pop(peer, None)
