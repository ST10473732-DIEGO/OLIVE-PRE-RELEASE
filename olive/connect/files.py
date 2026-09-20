"""Secure individual-file transfer orchestration; C3 alone supplies wire identity."""
import hashlib
import mimetypes
import os
from pathlib import Path
import stat
import threading
import time
import uuid

from ..agent.permission_service import PermissionDecision, PermissionService
from .contracts import ConnectError, canonical
from .file_protocol import FileRequest, PROTOCOL, CHUNK_SIZE, MAX_FILE_SIZE, TERMINAL, filename
from .file_store import FileStore


class FileTransferService:
    def __init__(self, service, profile):
        self.service = service
        self.lock = threading.RLock()
        self.store = FileStore(service, profile)
        self.sources = {}
        self.hashes = {}
        self.activity = {}
        self.approval_ids = {}
        self.workers = set()
        self.stopping = threading.Event()
        self.reaper = None
        self.accepting = False

    def activate(self):
        with self.lock:
            self.stopping.clear()
            self.accepting = True

    def _start(self):
        if self.service.closed or not self.accepting or self.stopping.is_set():
            raise ConnectError('service_closed')
        if self.reaper is None or not self.reaper.is_alive():
            self.reaper = threading.Thread(target=self._reap, name='olive-file-cleanup', daemon=True)
            self.reaper.start()

    def _reap(self):
        while not self.stopping.wait(.5):
            with self.lock, self.service.repository.transaction() as db:
                now = time.monotonic()
                for row in self.store.list(db):
                    if row['state'] in TERMINAL:
                        continue
                    started, last = self.activity.get(row['transfer_id'], (now, now))
                    limit = 120 if row['state'] in {'offered', 'awaiting_approval'} else 30
                    if now - started > 600 or now - last > limit:
                        self._finish(db, row, 'interrupted', 'transfer_timeout')

    def _touch(self, tid):
        now = time.monotonic()
        self.activity[tid] = (self.activity.get(tid, (now, now))[0], now)

    def _finish(self, db, row, state, error=None):
        self.store.finish(db, row, state, error)
        tid = row['transfer_id']
        self.hashes.pop(tid, None)
        self.sources.pop(tid, None)
        self.activity.pop(tid, None)
        approval = self.approval_ids.pop(tid, None)
        if approval and self.service.approvals is not None:
            self.service.approvals.discard(*approval)

    def _authority(self, db, peer, public, capability):
        record = self.service.repository.get(db, peer)
        if (self.service.closed or not self.accepting or self.stopping.is_set() or not record or record.get('trust_state') != 'paired'
                or record.get('revoked_at') is not None or record.get('public_identity') != public):
            raise ConnectError('device_not_paired')
        local = self.service.repository.get(db, self.service.local_id)
        policy = next((c for c in local['capabilities'] if c['capability'] == capability), {})
        if policy.get('policy_disabled'):
            raise ConnectError('capability_unavailable')
        decision = PermissionService.evaluate_device(record['permissions'], capability)
        if decision == PermissionDecision.DENY:
            raise ConnectError('permission_off')
        return record, decision

    def _approval(self, request, public, record, decision, *, sending=False):
        if decision != PermissionDecision.ASK:
            return True
        approvals = self.service.approvals
        if approvals is None:
            return False
        self.approval_ids[request.transfer_id] = (request.source_device_id, request.request_id)
        if sending:
            # Separate non-wire approval capability and operation; cannot reflect an offer.
            from .contracts import RequestEnvelope
            request = RequestEnvelope(request.request_id, PROTOCOL, request.source_device_id,
                request.target_device_id, 'files.send', 'local_send', request.arguments,
                request.timestamp, request.expires_at)
        return approvals.check(request, public, record, target_name='This device')

    def receive(self, packet, peer, public):
        request, data = FileRequest.decode(packet)
        row = None
        try:
            with self.lock, self.service.repository.transaction(timeout=.25) as db:
                if request.source_device_id != peer or public['device_id'] != peer:
                    raise ConnectError('source_mismatch')
                if request.target_device_id != self.service.local_id:
                    raise ConnectError('wrong_target')
                now = int(self.service.clock())
                if request.timestamp > now + 5 or request.expires_at <= now:
                    raise ConnectError('expired_request')
                # Cancel/status are still authenticated, but do not require receive permission.
                record = self.service.repository.get(db, peer)
                if not record or record.get('trust_state') != 'paired' or record.get('public_identity') != public:
                    raise ConnectError('device_not_paired')
                row = self.store.get(db, request.transfer_id)
                if row and row['peer_id'] != peer:
                    row = None
                    raise ConnectError('transfer_owner_mismatch')
                if request.operation == 'cancel':
                    if not row:
                        raise ConnectError('unknown_transfer')
                    self._finish(db, row, 'cancelled')
                elif request.operation == 'status':
                    if not row:
                        raise ConnectError('unknown_transfer')
                else:
                    if row and row['direction'] != 'incoming':
                        row = None
                        raise ConnectError('transfer_owner_mismatch')
                    record, decision = self._authority(db, peer, public, 'files.receive')
                    if request.operation == 'offer':
                        if row and row['metadata'] != request.arguments:
                            row = None  # A changed duplicate cannot mutate the original receipt.
                            raise ConnectError('changed_duplicate')
                        if row is None:
                            self.store.reserve(db, peer, request.arguments['size'], 'incoming')
                            row = self._record(request.transfer_id, peer, 'incoming', request.arguments)
                            row['offer'] = packet.hex()  # Metadata only: offer has no bytes, bounded at 4 KiB.
                            self.store.put(db, row)
                            self.store.audit(db, row, 'file_offer')
                            self._touch(request.transfer_id)
                            self._start()
                        if row['state'] not in TERMINAL and row['state'] in {'offered', 'awaiting_approval'}:
                            original, _ = FileRequest.decode(bytes.fromhex(row['offer']))
                            if original.fingerprint() != request.fingerprint():
                                raise ConnectError('changed_offer_request')
                            if self._approval(request, public, record, decision):
                                self.store.path(request.transfer_id, 'part').touch(mode=0o600, exist_ok=False)
                                self.hashes[request.transfer_id] = hashlib.sha256()
                                row.update(state='accepted', permission_binding=canonical(record['permissions']).decode())
                                self.store.audit(db, row, 'file_accepted')
                                self._touch(request.transfer_id)
                            else:
                                row['state'] = 'awaiting_approval'
                            self.store.put(db, row)
                    elif row is None:
                        raise ConnectError('unknown_transfer')
                    elif row['state'] in TERMINAL:
                        pass  # Durable terminal receipt, no writes or second artifact.
                    elif row['state'] not in {'accepted', 'transferring'}:
                        raise ConnectError('transfer_not_accepted')
                    elif row['permission_binding'] != canonical(record['permissions']).decode():
                        raise ConnectError('permission_changed')
                    elif request.operation == 'chunk':
                        if request.arguments['offset'] != row['received_size'] or row['received_size'] + len(data) > row['metadata']['size']:
                            raise ConnectError('invalid_chunk_offset_or_size')
                        with self.store.path(request.transfer_id, 'part').open('ab') as stream:
                            stream.write(data)
                        self.hashes[request.transfer_id].update(data)
                        if row['state'] == 'accepted':
                            self.store.audit(db, row, 'transfer_started')
                        row.update(state='transferring', received_size=row['received_size'] + len(data))
                        self.store.put(db, row)
                        self._touch(request.transfer_id)
                    elif request.operation == 'complete':
                        row['state'] = 'verifying'
                        self.store.put(db, row)
                        if row['received_size'] != row['metadata']['size'] or self.hashes[request.transfer_id].hexdigest() != row['metadata']['sha256']:
                            raise ConnectError('content_integrity_failed')
                        path = self.store.path(request.transfer_id, 'part')
                        with path.open('rb') as stream:
                            os.fsync(stream.fileno())
                        path.replace(self.store.path(request.transfer_id, 'bin'))
                        self._finish(db, row, 'completed')
                result = dict(state=row['state'], received_size=row['received_size'])
            return dict(protocol_version=PROTOCOL, request_id=request.request_id, state='completed', result=result)
        except Exception as error:
            code = str(error) if isinstance(error, ConnectError) else 'file_io_failed'
            # Exceptions roll back SQLite; clean the owned partial in a new transaction.
            with self.lock, self.service.repository.transaction() as db:
                if row is not None:
                    current = self.store.get(db, request.transfer_id)
                    if current and current['peer_id'] == peer:
                        self._finish(db, current, 'declined' if code == 'request_denied' else 'failed', code)
                        if current['state'] != 'completed':
                            self.store.path(request.transfer_id, 'bin').unlink(missing_ok=True)
            return dict(protocol_version=PROTOCOL, request_id=request.request_id, state='rejected', error=code)

    def _record(self, tid, peer, direction, meta):
        now = int(self.service.clock())
        return dict(transfer_id=tid, source_device_id=peer if direction == 'incoming' else self.service.local_id,
            target_device_id=self.service.local_id if direction == 'incoming' else peer,
            peer_id=peer, direction=direction, metadata=dict(meta), received_size=0, state='offered',
            created_at=now, updated_at=now, error=None, artifact_reference=tid)

    def list(self, peer=None):
        with self.lock, self.service.repository.transaction() as db:
            return [{k: v for k, v in row.items() if k not in {'offer', 'permission_binding'}}
                    for row in self.store.list(db) if peer is None or row['peer_id'] == peer][:100]

    @staticmethod
    def _open_regular(path):
        path = Path(path)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ConnectError('regular_file_required')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))
        stream = os.fdopen(fd, 'rb')
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            stream.close()
            raise ConnectError('regular_file_required')
        return stream

    @staticmethod
    def _snapshot(stream):
        s = os.fstat(stream.fileno())
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

    def prepare(self, device_id, path):
        # Native file selection is the sole source of path authority. Snapshot reads
        # run outside the device DB transaction so ping/revocation remain responsive.
        with self._open_regular(path) as source:
            before = self._snapshot(source)
            if before[2] > MAX_FILE_SIZE:
                raise ConnectError('file_too_large_or_invalid_size')
            name = filename(Path(path).name)
            tid = str(uuid.uuid4())
            meta = dict(name=name, size=before[2], sha256='0' * 64,
                        mime=mimetypes.guess_type(name)[0] or 'application/octet-stream')
            with self.lock, self.service.repository.transaction() as db:
                peer = self.service.repository.get(db, device_id)
                if not peer:
                    raise ConnectError('device_not_paired')
                self._authority(db, device_id, peer.get('public_identity'), 'files.send')
                self.store.reserve(db, device_id, before[2], 'outgoing')
                row = self._record(tid, device_id, 'outgoing', meta)
                self.store.put(db, row)
                self.store.path(tid, 'out').touch(mode=0o600, exist_ok=False)
                self._touch(tid)
                self._start()
            try:
                digest, count = hashlib.sha256(), 0
                while data := source.read(CHUNK_SIZE):
                    count += len(data)
                    if count > before[2]:
                        raise ConnectError('source_changed_review_again')
                    digest.update(data)
                    with self.lock, self.service.repository.transaction() as db:
                        row = self.store.get(db, tid)
                        if row['state'] in TERMINAL:
                            raise ConnectError('transfer_stopped')
                        with self.store.path(tid, 'out').open('ab') as target:
                            target.write(data)
                if count != before[2] or before != self._snapshot(source):
                    raise ConnectError('source_changed_review_again')
                with self.lock, self.service.repository.transaction() as db:
                    row = self.store.get(db, tid)
                    if row['state'] in TERMINAL:
                        raise ConnectError('transfer_stopped')
                    row['metadata']['sha256'] = digest.hexdigest()
                    self.store.put(db, row)
                    self.sources[tid] = (Path(path), before)
                    return row
            except BaseException:
                with self.lock, self.service.repository.transaction() as db:
                    self._finish(db, self.store.get(db, tid), 'failed', 'source_changed_review_again')
                raise

    def _channel(self, peer):
        network = self.service.network
        if not network:
            raise ConnectError('network_disabled')
        with network.lock:
            channel = network.channels.get(peer)
        if channel is None:
            raise ConnectError('device_offline')
        if channel.stop.is_set() or channel.public is None:
            raise ConnectError('device_offline')
        return channel

    def _request(self, tid, peer, operation, arguments=None):
        now = int(self.service.clock())
        return FileRequest(str(uuid.uuid4()), PROTOCOL, tid, self.service.local_id,
                           peer, operation, arguments or {}, now, now + 120)

    def start(self, transfer_id):
        with self.lock, self.service.repository.transaction() as db:
            row = self.store.get(db, transfer_id)
            if not row or row['direction'] != 'outgoing' or row['state'] != 'offered' or transfer_id not in self.sources:
                raise ConnectError('transfer_not_ready')
            if len(self.workers) >= 4:
                raise ConnectError('transfer_capacity_reached')
            self._channel(row['peer_id'])
            row['state'] = 'awaiting_approval'
            self.store.put(db, row)
            worker = threading.Thread(target=self._send, args=(transfer_id,), name='olive-file-send', daemon=True)
            self.workers.add(worker)
            worker.start()
            return {'started': True}

    def _sending(self, tid):
        with self.lock, self.service.repository.transaction() as db:
            row = self.store.get(db, tid)
            if self.stopping.is_set() or not row or row['state'] in TERMINAL:
                raise ConnectError('transfer_stopped')
            channel = self._channel(row['peer_id'])
            record, decision = self._authority(db, row['peer_id'], channel.public, 'files.send')
            return row, channel, record, decision

    def _send(self, tid):
        try:
            row, channel, record, decision = self._sending(tid)
            offer = self._request(tid, row['peer_id'], 'offer', row['metadata'])
            while not self._approval(offer, channel.public, record, decision, sending=True):
                if self.stopping.wait(1) or self.service.clock() >= offer.expires_at:
                    raise ConnectError('approval_expired')
                row, channel, record, decision = self._sending(tid)
            # Revalidate actual source after local review, then send immutable owned snapshot.
            with self.lock:
                path, before = self.sources[tid]
            with self._open_regular(path) as source:
                digest = hashlib.sha256()
                count = 0
                while data := source.read(CHUNK_SIZE):
                    self._sending(tid)
                    count += len(data)
                    if count > row['metadata']['size']:
                        raise ConnectError('source_changed_review_again')
                    digest.update(data)
                if before != self._snapshot(source) or count != row['metadata']['size'] or digest.hexdigest() != row['metadata']['sha256']:
                    raise ConnectError('source_changed_review_again')
            while True:
                row, channel, _, _ = self._sending(tid)
                answer = channel.file_request(offer.encode())
                result = self._result(answer)
                if result['state'] != 'awaiting_approval':
                    break
                if self.stopping.wait(1) or self.service.clock() >= offer.expires_at:
                    raise ConnectError('approval_expired')
            if result['state'] != 'accepted':
                raise ConnectError('file_offer_declined')
            # Receiver Ask may have waited after the initial source validation.
            # A source edit during that wait requires a new local review.
            with self._open_regular(path) as source:
                if before != self._snapshot(source):
                    raise ConnectError('source_changed_review_again')
            with self.lock, self.service.repository.transaction() as db:
                row = self.store.get(db, tid)
                if row['state'] in TERMINAL:
                    raise ConnectError('transfer_stopped')
                row['state'] = 'transferring'
                self.store.put(db, row)
                self.store.audit(db, row, 'transfer_started')
                self._touch(tid)
            # Open/read one chunk per lock boundary, so cancellation can remove the spool on Windows.
            offset = 0
            while offset < row['metadata']['size']:
                row, channel, _, _ = self._sending(tid)
                with self.lock:
                    with self.store.path(tid, 'out').open('rb') as source:
                        source.seek(offset)
                        data = source.read(CHUNK_SIZE)
                result = self._result(channel.file_request(self._request(tid, row['peer_id'], 'chunk', {'offset': offset}).encode(data)))
                offset += len(data)
                if result != {'state': 'transferring', 'received_size': offset}:
                    raise ConnectError('invalid_file_ack')
                with self.lock, self.service.repository.transaction() as db:
                    row = self.store.get(db, tid)
                    if row['state'] in TERMINAL:
                        raise ConnectError('transfer_stopped')
                    row['received_size'] = offset
                    self.store.put(db, row)
                    self._touch(tid)
            row, channel, _, _ = self._sending(tid)
            result = self._result(channel.file_request(self._request(tid, row['peer_id'], 'complete').encode()))
            if result != {'state': 'completed', 'received_size': row['metadata']['size']}:
                raise ConnectError('invalid_file_ack')
            with self.lock, self.service.repository.transaction() as db:
                self._finish(db, self.store.get(db, tid), 'completed')
        except Exception as error:
            code = str(error) if isinstance(error, ConnectError) else 'file_io_failed'
            with self.lock, self.service.repository.transaction() as db:
                row = self.store.get(db, tid)
                self._finish(db, row, 'interrupted' if code in {'connection_closed', 'device_offline', 'file_request_timeout'} else 'failed', code)
            # Best effort scoped cancellation, never close a shared C3 session.
            try:
                self._channel(row['peer_id']).file_request(self._request(tid, row['peer_id'], 'cancel').encode())
            except Exception:
                pass
        finally:
            with self.lock:
                self.workers.discard(threading.current_thread())

    @staticmethod
    def _result(answer):
        if answer['state'] != 'completed':
            raise ConnectError(answer['error'])
        return answer['result']

    def cancel(self, transfer_id):
        with self.lock, self.service.repository.transaction() as db:
            row = self.store.get(db, transfer_id)
            if not row:
                raise ConnectError('unknown_transfer')
            self._finish(db, row, 'cancelled')
        try:
            self._channel(row['peer_id']).file_request(self._request(transfer_id, row['peer_id'], 'cancel').encode())
        except ConnectError:
            pass
        return {'cancelled': row['state'] == 'cancelled'}

    def invalidate(self, peer=None, reason='interrupted'):
        with self.lock, self.service.repository.transaction() as db:
            for row in self.store.list(db):
                if peer is None or row['peer_id'] == peer:
                    self._finish(db, row, 'interrupted', reason)

    def export(self, transfer_id, path):
        with self.lock, self.service.repository.transaction() as db:
            row = self.store.get(db, transfer_id)
            if not row:
                raise ConnectError('unknown_transfer')
        return self.store.export(row, path)

    def dismiss(self, transfer_id):
        with self.lock, self.service.repository.transaction() as db:
            row = self.store.get(db, transfer_id)
            if not row or row['direction'] != 'incoming' or row['state'] != 'completed':
                raise ConnectError('file_not_completed')
            self.store.path(transfer_id, 'bin').unlink(missing_ok=True)
            row['state'] = 'dismissed'
            self.store.put(db, row)  # Retain replay receipt even after explicit local deletion.
        return {'dismissed': True}

    def close(self):
        with self.lock:
            self.accepting = False
            self.stopping.set()
        self.invalidate(reason='network_disabled')
        with self.lock:
            workers = list(self.workers)
        for worker in workers:
            worker.join(timeout=7)
        if self.reaper:
            self.reaper.join(timeout=2)
        if any(w.is_alive() for w in workers) or (self.reaper and self.reaper.is_alive()):
            raise ConnectError('file_shutdown_timeout')
