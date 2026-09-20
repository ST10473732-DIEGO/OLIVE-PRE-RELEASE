"""Manual bounded C3 sync sessions; no scheduler, tools or generic RPC."""
from dataclasses import asdict
from contextlib import contextmanager
import threading
import time
import uuid

from ..agent.permission_service import PermissionDecision, PermissionService
from ..connect.contracts import ConnectError, canonical, identifier
from .records import SyncRequest, SyncRecord, CAPABILITIES, PROTOCOL
from .store import SyncStore


class RecordSyncService:
    def __init__(self, connect, personal):
        self.connect = connect
        def sign_record(value):
            from .provenance import sign
            if connect.network is not None:
                public, key = connect.network.local_identity
            else:
                public = connect.cryptographic_identity()
                key = connect.identities.key_store.load(public)
            return sign(value, public, key)
        self.store = SyncStore(personal, connect.local_id, sign_record)
        self.lock = threading.RLock()
        self.worker = None
        self.dispatch = None
        self.changed = lambda: None
        self.approved_responses = {}
        self.cancelled = threading.Event()
        self.state = dict(state='idle', sent=0, received=0, conflicts=0, last_sync=None, peer=None)

    def owned(self, action):
        return self.dispatch(action) if self.dispatch else action()

    def authorize(self, db, request, peer, public):
        s = self.connect
        if s.closed or s.network is None or public is None:
            raise ConnectError('unauthenticated_transport')
        if request.source_device_id != peer or request.updated_by_device_id != peer:
            raise ConnectError('source_mismatch')
        if request.target_device_id != s.local_id:
            raise ConnectError('wrong_target')
        record = s.repository.get(db, peer)
        if not record or record.get('trust_state') != 'paired' or record.get('revoked_at') is not None:
            raise ConnectError('device_not_paired')
        if record.get('public_identity') != public:
            raise ConnectError('identity_mismatch')
        now = int(s.clock())
        if request.timestamp > now + 5 or request.expires_at <= now:
            raise ConnectError('expired_request')
        metadata = next((c for c in s.repository.get(db, s.local_id)['capabilities'] if c['capability'] == request.capability), {})
        if metadata.get('policy_disabled') or (request.capability == 'sync.chat' and self.store.chat is None):
            raise ConnectError('capability_unavailable')
        decision = PermissionService.evaluate_device(record['permissions'], request.capability)
        if decision == PermissionDecision.ASK and s.approvals is not None:
            if s.approvals.check(request, public, record, target_name=s.repository.get(db, s.local_id)['display_name']):
                return
        if decision != PermissionDecision.ALLOW:
            raise ConnectError('confirmation_required' if decision == PermissionDecision.ASK else 'permission_off')

    def receive(self, raw, peer, public):
        return self.owned(lambda: self._locked_receive(raw, peer, public))

    def _locked_receive(self, raw, peer, public):
        with self.lock:
            return self._receive(raw, peer, public)

    def _receive(self, raw, peer, public):
        request = None
        try:
            request = SyncRequest.decode(raw)
            self.store.flush()
            # Lock order is always authority then native data. Permission/revoke
            # commits cannot race a batch; each subsequent batch rechecks policy.
            with self.connect.repository.transaction(timeout=.25) as authority:
                self.authorize(authority, request, peer, public)
                now = time.monotonic()
                self.approved_responses = {k:v for k,v in self.approved_responses.items() if v['deadline'] > now}
                key = (peer, request.request_id)
                cached = self.approved_responses.get(key)
                if cached:
                    if cached['fingerprint'] != request.fingerprint():
                        raise ConnectError('changed_duplicate')
                    if request.capability == 'sync.chat':
                        with self.store.native.transaction() as db:
                            if any(not self.store.chat.allowed(db, peer, SyncRecord.parse(r))
                                   for r in cached['response']['result']['records']):
                                raise ConnectError('sync_selection_changed')
                    return cached['response']
                policy = self.connect.repository.get(authority, peer)['permissions']
                cache_response = PermissionService.evaluate_device(policy, request.capability) == PermissionDecision.ASK
                if cache_response and len(self.approved_responses) >= 32:
                    raise ConnectError('approval_capacity_reached')
                from .provenance import bind_editors
                bind_editors(self.connect, authority, request.arguments["records"], peer, public)
                with self.store.native.transaction() as db:
                    self.store.capture(db)
                    results = self.store.receive(db, peer, request.arguments['records'])
                    records, cursor, more = self.store.batch(db, request.capability, request.arguments['cursor'], peer)
                    self.store.save_status(db, dict(state='batch_committed', sent=len(records),
                        received=len(request.arguments['records']), conflicts=results.count('conflict'),
                        last_sync=int(self.connect.clock()), peer=peer))
                self.connect.repository.audit(authority, peer, request.request_id, request.capability,
                    int(self.connect.clock()), 'sync_batch_committed')
            self.store.flush()
            self.changed()
            result = dict(ack=[value['revision'] for value in request.arguments['records']],
                          results=results, records=records, cursor=cursor, more=more)
            response = dict(protocol_version=PROTOCOL, request_id=request.request_id, state='completed', result=result)
            if cache_response:
                self.approved_responses[key] = dict(fingerprint=request.fingerprint(), response=response,
                    deadline=time.monotonic() + max(0, request.expires_at - self.connect.clock()))
            return response
        except ConnectError as error:
            code = str(error)
        except Exception:
            code = 'sync_storage_error'
        return dict(protocol_version=PROTOCOL, request_id=request.request_id if request else None,
                    state='rejected', error=code)

    def status(self, peer=None):
        with self.lock:
            active = peer is None or (self.state['peer'] == peer and self.worker and self.worker.is_alive())
            result = dict(self.state) if active else None
        if result is None:
            result = self.store.stored_status(peer) or dict(
                state='idle', sent=0, received=0, conflicts=0, last_sync=None, peer=peer)
        result['conflicts'] = self.store.conflict_count(result['peer']) if result['peer'] else 0
        return result

    def start(self, device_id):
        identifier(device_id)
        s = self.connect
        if s.network is None:
            raise ConnectError('network_disabled')
        s.device(device_id)
        previous = self.status(device_id)
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ConnectError('sync_busy')
            self.cancelled.clear()
            self.state.update(state='running', peer=device_id, sent=0, received=0, conflicts=0, error=None, last_sync=previous.get('last_sync'))
            self.worker = threading.Thread(target=self.run, args=(device_id,), name='olive-record-sync', daemon=True)
            self.worker.start()
        return self.status()

    def cancel(self):
        self.cancelled.set()
        return self.status()

    def close(self):
        self.cancelled.set()
        worker = self.worker
        if worker and worker is not threading.current_thread():
            worker.join(6)
            if worker.is_alive():
                raise ConnectError('sync_shutdown_timeout')

    def run(self, peer):
        s = self.connect
        deadline = time.monotonic() + 90
        try:
            rounds = 0
            unfinished = False
            permitted = False
            for capability in sorted(CAPABILITIES):
                if self.cancelled.is_set():
                    raise ConnectError('sync_cancelled')
                if time.monotonic() >= deadline:
                    raise ConnectError('sync_partial')
                if s.permission(peer, capability) == PermissionDecision.DENY:
                    continue
                permitted = True
                while rounds < 8 and time.monotonic() < deadline:
                    if self.cancelled.is_set():
                        raise ConnectError('sync_cancelled')
                    network = s.network
                    if network is None:
                        raise ConnectError('network_disabled')
                    with network.lock:
                        channel = network.channels.get(peer)
                    if channel is None:
                        raise ConnectError('device_offline')
                    now = int(s.clock())
                    # Capture native edits and outbound data under current local
                    # authority, not simply because the peer grants us access.
                    def prepare():
                        self.store.flush()
                        with s.repository.transaction() as authority:
                            decision = PermissionService.evaluate_device(s.repository.get(authority, peer)['permissions'], capability)
                            if decision == PermissionDecision.DENY:
                                raise ConnectError('permission_off')
                            with self.store.native.transaction() as db:
                                self.store.capture(db)
                                sent, received = self.store.cursors(db, peer, capability)
                                records, end, more = self.store.batch(db, capability, sent, peer)
                                return sent, received, records, end, more
                    sent, received, records, end, more = self.owned(prepare)
                    request = SyncRequest(PROTOCOL, str(uuid.uuid4()), s.local_id, peer, s.local_id,
                        capability, 'exchange', dict(records=records, cursor=received), now, now + 120)
                    raw = canonical(asdict(request))
                    # Use the trusted C4 confirmation adapter for local Ask too.
                    local_scope = SyncRequest(PROTOCOL, request.request_id, peer, s.local_id, peer,
                        capability, 'initiate', request.arguments, now, now + 120)
                    while True:
                        if self.cancelled.is_set() or time.monotonic() >= deadline:
                            raise ConnectError('sync_cancelled' if self.cancelled.is_set() else 'sync_partial')
                        try:
                            with s.repository.transaction() as authority:
                                self.authorize(authority, local_scope, peer, channel.public)
                        except ConnectError as error:
                            if str(error) != 'confirmation_required':
                                raise
                            with self.lock:
                                self.state['state'] = 'awaiting_approval'
                            self.cancelled.wait(.75)
                            continue
                        @contextmanager
                        def admission():
                            with s.repository.transaction() as authority:
                                self.authorize(authority, local_scope, peer, channel.public)
                                if capability == 'sync.chat':
                                    with self.store.native.transaction() as db:
                                        if any(not self.store.chat.allowed(db, peer, SyncRecord.parse(r)) for r in records):
                                            raise ConnectError('sync_selection_changed')
                                yield
                        response = channel.sync_request(raw, admission=admission)
                        if response.get('error') == 'confirmation_required':
                            with self.lock:
                                self.state['state'] = 'awaiting_approval'
                            self.cancelled.wait(1)
                            continue
                        break
                    if response['state'] != 'completed':
                        code = response.get('error')
                        if code not in {'permission_off', 'device_not_paired', 'confirmation_required', 'request_denied', 'approval_changed_request', 'expired_request', 'sync_ledger_capacity', 'sync_conflict_capacity', 'unsupported_record_version', 'sync_storage_error', 'capability_unavailable'}:
                            code = 'sync_peer_rejected'
                        raise ConnectError(code)
                    result = response['result']
                    if (type(result) is not dict or set(result) != {'ack','results','records','cursor','more'}
                            or result['ack'] != [r['revision'] for r in records]
                            or type(result['results']) is not list or len(result['results']) != len(records)
                            or any(type(r) is not str or r not in {'applied', 'duplicate', 'stale', 'tombstone', 'conflict'} for r in result['results'])
                            or type(result['cursor']) is not int or result['cursor'] < received
                            or type(result['more']) is not bool):
                        raise ConnectError('invalid_sync_ack')
                    # Reuse the strict record/batch/scope validator on untrusted
                    # results, then recheck local authority before committing.
                    inbound = SyncRequest(PROTOCOL, request.request_id, peer, s.local_id, peer,
                        capability, 'exchange', dict(records=result['records'], cursor=result['cursor']), now, now + 120)
                    SyncRequest.decode(canonical(asdict(inbound)))
                    def commit():
                        self.store.flush()
                        with s.repository.transaction() as authority:
                            self.authorize(authority, local_scope, peer, channel.public)
                            from .provenance import bind_editors
                            bind_editors(s, authority, result["records"], peer, channel.public)
                            with self.store.native.transaction() as db:
                                self.store.capture(db)
                                outcomes = self.store.receive(db, peer, result['records'])
                                self.store.checkpoint(db, peer, capability, end, result['cursor'])
                        self.store.flush()
                        self.changed()
                        return outcomes
                    if self.cancelled.is_set():
                        raise ConnectError('sync_cancelled')
                    outcomes = self.owned(commit)
                    with self.lock:
                        self.state.update(state='running', sent=self.state['sent'] + len(records),
                            received=self.state['received'] + len(result['records']),
                            conflicts=self.state['conflicts'] + outcomes.count('conflict'))
                    rounds += 1
                    unfinished = more or result['more']
                    if not unfinished:
                        break
                if rounds >= 8:
                    unfinished = True
                    break
            with self.lock:
                self.state.update(state='partial' if unfinished else 'completed' if permitted else 'off',
                                  last_sync=int(s.clock()) if permitted and not unfinished else self.state['last_sync'])
        except ConnectError as error:
            with self.lock:
                self.state.update(state='cancelled' if str(error) == 'sync_cancelled' else 'partial', error=str(error))
        except Exception:
            with self.lock:
                self.state.update(state='partial', error='sync_storage_error')
        finally:
            with self.lock:
                final = dict(self.state)
            try:
                with self.store.native.transaction() as db:
                    self.store.save_status(db, final)
                with s.repository.transaction() as db:
                    s.repository.audit(db, peer, None, None, int(s.clock()), 'sync_' + final['state'])
            except Exception:
                with self.lock:
                    self.state.update(state='partial', error='sync_status_storage_error')
