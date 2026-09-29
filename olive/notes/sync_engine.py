"""olive-notes/1 sync engine. Transport-agnostic; OLIVE Connect adapts it.

Model (every device runs the same code; no device is authoritative):

* Each device has a durable change feed: every committed note change or purge
  gets a new `change_seq`. For every peer it stores `acked_seq`, the feed
  position through which that peer has confirmed durable receipt.
* A pump sends the feed entries after `acked_seq` with the note's state vector
  and, when the peer's state vector is known, the CRDT diff against it (which
  always carries the full delete set, since deletions are invisible to state
  vectors). The receiver applies, commits, and answers with its own state
  vector. An entry is delivered only when an update was shipped and the answer
  covers what was sent; then `acked_seq` advances over the delivered prefix.
* Receiving is idempotent (CRDT), so a lost answer just means a resend.
* A note changed by a peer, when everything before it had been delivered to
  that peer, is not echoed back to it; everything else still converges by diff.
* Epochs: every store has a random epoch. If a peer's epoch changes (restore,
  reinstall), its cursor resets to 0 and full reconciliation runs again.
"""
import hashlib
import threading
import time
import uuid

from . import statevector
from .limits import LIMITS, PROTOCOL
from .protocol import NotesProtocolError, b64, validate_result
from .service import NotesError

EMPTY_SV = b'\x00'


class NotesSyncError(RuntimeError):
    """Fixed categories for peer/transport failures."""


class NotesSyncEngine:
    def __init__(self, service, local_id):
        self.s = service
        self.local_id = local_id
        self.remote_sv = {}      # peer -> {note_id: state vector}; worker thread only
        self.transfers = {}      # (peer, transfer_id) -> staging; worker thread only
        self.errors = {}         # peer -> {note_id: code}; notes a peer refused
        self.lock = threading.Lock()
        self.states = {}         # peer -> public status (any thread, under lock)

    # --- public status -------------------------------------------------------------
    def set_state(self, peer, state, **extra):
        with self.lock:
            current = dict(self.states.get(peer, {}))
            current.update(state=state, **extra)
            current['updated'] = time.time()
            self.states[peer] = current

    def state(self, peer):
        with self.lock:
            return dict(self.states.get(peer, {'state': 'idle'}))

    # --- receiving (worker thread) ---------------------------------------------------
    def handle(self, peer, request):
        operation, arguments = request['operation'], request['arguments']
        if operation == 'hello':
            if PROTOCOL not in arguments['versions']:
                raise NotesProtocolError('unsupported_protocol')
            return {'versions': [PROTOCOL], 'epoch': self.s.epoch()}
        self._observe_epoch(peer, arguments['epoch'])
        if operation == 'sync':
            return {'epoch': self.s.epoch(), 'results': [self._receive_entry(peer, entry) for entry in arguments['entries']]}
        return self._receive_chunk(peer, arguments)

    def _observe_epoch(self, peer, epoch):
        stored = self.s.peer(peer)
        if stored['peer_epoch'] != epoch:
            if stored['peer_epoch'] is not None:
                # The peer's store was replaced: it may lack what it once acknowledged.
                self.s.save_peer(peer, acked_seq=0)
                self.remote_sv.pop(peer, None)
            self.s.save_peer(peer, peer_epoch=epoch, protocol=PROTOCOL)
            return True
        return False

    def _receive_entry(self, peer, entry):
        nid = entry['note_id']
        self.remote_sv.setdefault(peer, {})[nid] = entry['sv']
        if entry['purged']:
            self.s.purge(nid, origin='remote', peer=peer)
            return {'note_id': nid, 'status': 'purged', 'sv': ''}
        if self.s.is_purged(nid):
            return {'note_id': nid, 'status': 'purged', 'sv': ''}
        if 'update' in entry:
            return self._apply(peer, nid, entry['update'], entry['sv'])
        local, exists = self.s.state_vector_of(nid)
        covered = exists and statevector.covers(statevector.decode(local), statevector.decode(entry['sv']))
        return {'note_id': nid, 'status': 'current' if covered else 'needs', 'sv': b64(local)}

    def _apply(self, peer, nid, update, sender_sv):
        status, local = self.s.apply_remote(nid, update, peer)
        if status == 'purged':
            return {'note_id': nid, 'status': 'purged', 'sv': ''}
        if status.startswith('rejected'):
            code = status.partition(':')[2] or 'invalid_update'
            return {'note_id': nid, 'status': 'rejected', 'sv': '',
                    'error': code if code in ('note_too_large', 'notes_capacity', 'invalid_update') else 'invalid_update'}
        covered = statevector.covers(statevector.decode(local), statevector.decode(sender_sv))
        return {'note_id': nid, 'status': 'applied' if covered else 'needs', 'sv': b64(local)}

    def _receive_chunk(self, peer, arguments):
        now = time.monotonic()
        for key in [k for k, v in self.transfers.items() if v['expires'] < now]:
            self.transfers.pop(key)
        key = (peer, arguments['transfer_id'])
        staging = self.transfers.get(key)
        fixed = ('note_id', 'seq', 'count', 'total_bytes', 'sha256')
        if staging is None:
            if sum(1 for p, _ in self.transfers if p == peer) >= LIMITS['max_transfers_per_peer']:
                raise NotesProtocolError('busy')
            staging = dict({k: arguments[k] for k in fixed}, parts={}, size=0)
            self.transfers[key] = staging
        elif any(staging[k] != arguments[k] for k in fixed):
            self.transfers.pop(key, None)
            raise NotesProtocolError('malformed_message')
        staging['expires'] = now + LIMITS['transfer_idle_seconds']
        if arguments['index'] not in staging['parts']:
            staging['parts'][arguments['index']] = arguments['data']
            staging['size'] += len(arguments['data'])
        if staging['size'] > staging['total_bytes']:
            self.transfers.pop(key, None)
            raise NotesProtocolError('payload_too_large')
        epoch = self.s.epoch()
        if len(staging['parts']) < staging['count']:
            return {'epoch': epoch, 'status': 'partial', 'sv': ''}
        self.transfers.pop(key, None)
        payload = b''.join(staging['parts'][i] for i in range(staging['count']))
        if len(payload) != staging['total_bytes'] or hashlib.sha256(payload).hexdigest() != staging['sha256']:
            raise NotesProtocolError('invalid_update')
        nid = arguments['note_id']
        self.remote_sv.setdefault(peer, {})[nid] = arguments['sv']
        if self.s.is_purged(nid):
            return {'epoch': epoch, 'status': 'purged', 'sv': ''}
        result = self._apply(peer, nid, payload, arguments['sv'])
        result.pop('note_id')
        return dict(result, epoch=epoch)

    # --- sending (caller thread; data work hops onto the worker) ----------------------
    def pump(self, peer, send, *, hello=False, keep_going=lambda: True):
        """Push this device's pending changes to `peer` until caught up.

        `send(operation, arguments)` performs one request and returns the peer's
        completed result dict, or raises. Returns 'synced' or 'partial'.
        """
        self.set_state(peer, 'syncing')
        if hello:
            result = validate_result('hello', send('hello', {'versions': [PROTOCOL]}))
            if PROTOCOL not in result['versions']:
                raise NotesSyncError('unsupported_protocol')
            self.s.run(self._observe_epoch, peer, result['epoch'])
        stalled = 0
        for _ in range(LIMITS['max_rounds_per_pump']):
            if not keep_going():
                return 'partial'
            batch = self.s.run(self._prepare, peer)
            if batch is None:
                self.set_state(peer, 'synced', last_sync=time.time(), pending=0)
                self.s.run(self.s.save_peer, peer, last_sync=_utc(), last_error=None)
                return 'synced'
            if batch['arguments'] is None:
                continue  # Only echo-suppressed entries: cursor advanced locally.
            result = validate_result('sync', send('sync', batch['arguments']), batch['arguments']['entries'])
            progress = self.s.run(self._process, peer, batch, result)
            for transfer in batch['transfers']:
                if not keep_going():
                    return 'partial'
                self._send_transfer(peer, transfer, send)
                progress = True
            stalled = 0 if progress else stalled + 1
            if stalled >= 3:
                raise NotesSyncError('sync_stalled')
        return 'partial'

    def _prepare(self, peer):
        acked = self.s.peer(peer)['acked_seq']
        feed = self.s.pending(peer, acked, LIMITS['max_entries'])
        if not feed:
            return None
        entries, meta, transfers = [], [], []
        budget = LIMITS['max_request_update_bytes']
        known = self.remote_sv.get(peer, {})
        for seq, nid, purged, skip in feed:
            if skip:
                meta.append({'seq': seq, 'kind': 'skip'})
                continue
            if purged:
                entries.append({'note_id': nid, 'seq': seq, 'sv': b64(EMPTY_SV), 'purged': True})
                meta.append({'seq': seq, 'kind': 'purge', 'note_id': nid})
                continue
            try:
                document = self.s.document(nid)
            except NotesError:
                meta.append({'seq': seq, 'kind': 'skip'})
                continue
            sv = document.state_vector()
            entry = {'note_id': nid, 'seq': seq, 'sv': b64(sv), 'purged': False}
            kind = 'offer'
            if nid in known:
                update = document.diff(known[nid])
                if len(update) > LIMITS['max_inline_update_bytes']:
                    kind = 'transfer'
                    transfers.append({'note_id': nid, 'seq': seq, 'sv': sv, 'data': update})
                elif len(update) <= budget:
                    entry['update'] = b64(update)
                    budget -= len(update)
                    kind = 'update'
                elif entries:
                    break  # Request budget used; the rest goes in the next round.
            entries.append(entry)
            meta.append({'seq': seq, 'kind': kind, 'note_id': nid, 'sv': sv})
        if not entries:
            last = meta[-1]['seq']
            self.s.save_peer(peer, acked_seq=last)
            return {'arguments': None, 'meta': meta, 'transfers': []}
        return {'arguments': {'epoch': self.s.epoch(), 'entries': entries}, 'meta': meta, 'transfers': transfers,
                'acked': acked}

    def _process(self, peer, batch, result):
        if self._observe_epoch(peer, result['epoch']) and self.s.peer(peer)['acked_seq'] == 0 and batch['acked'] > 0:
            return True  # The peer's store changed identity; start over from 0.
        rows = iter(result['results'])
        delivered, learned = [], False
        refused = self.errors.setdefault(peer, {})
        known = self.remote_sv.setdefault(peer, {})
        for item in batch['meta']:
            if item['kind'] == 'skip':
                delivered.append(True)
                continue
            row = next(rows)
            nid = item['note_id']
            if row['status'] == 'purged':
                if item['kind'] != 'purge':
                    self.s.purge(nid, origin='remote', peer=peer)
                delivered.append(True)
                continue
            if row['status'] == 'rejected':
                # Never let one refused note block every later change; it is
                # retried when it changes again, and the refusal is surfaced.
                refused[nid] = row['error'] or 'invalid_update'
                delivered.append(True)
                continue
            refused.pop(nid, None)
            known[nid] = row['sv']
            learned = True
            covered = statevector.covers(statevector.decode(row['sv']), statevector.decode(item['sv']))
            delivered.append(item['kind'] == 'update' and covered and row['status'] in ('applied', 'current'))
        new_acked = batch['acked']
        for item, ok in zip(batch['meta'], delivered):
            if not ok:
                break
            new_acked = item['seq']
        if new_acked > batch['acked']:
            self.s.save_peer(peer, acked_seq=new_acked, last_error=None)
        return new_acked > batch['acked'] or learned

    def _send_transfer(self, peer, transfer, send):
        data = transfer['data']
        size = LIMITS['max_chunk_bytes']
        count = -(-len(data) // size)
        arguments = {'epoch': self.s.run(self.s.epoch), 'transfer_id': str(uuid.uuid4()), 'note_id': transfer['note_id'],
                     'seq': transfer['seq'], 'sv': b64(transfer['sv']), 'count': count, 'total_bytes': len(data),
                     'sha256': hashlib.sha256(data).hexdigest()}
        result = None
        for index in range(count):
            result = validate_result('chunk', send('chunk', dict(arguments, index=index, data=b64(data[index * size:(index + 1) * size]))))
            if result['status'] == 'rejected':
                raise NotesSyncError(result['error'] or 'invalid_update')
        def learn():
            if result['status'] == 'purged':
                self.s.purge(transfer['note_id'], origin='remote', peer=peer)
            elif result['sv']:
                self.remote_sv.setdefault(peer, {})[transfer['note_id']] = result['sv']
        self.s.run(learn)

    def pending(self, peer):
        return self.s.run(self.s.pending_count, peer)

    def refused(self, peer):
        return self.s.run(lambda: dict(self.errors.get(peer, {})))

    def forget(self, peer):
        """Revocation/permission Off: drop transient knowledge; durable cursors stay."""
        def drop():
            self.remote_sv.pop(peer, None)
            for key in [k for k in self.transfers if k[0] == peer]:
                self.transfers.pop(key)
        self.s.run(drop)


def _utc():
    from .service import utc_now
    return utc_now()
