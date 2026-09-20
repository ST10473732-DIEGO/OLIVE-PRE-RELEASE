"""Device trust and safe dispatch; neither fixtures nor LAN can reach the tool registry."""
import json
import platform as host_platform
import sys
import time
from threading import RLock

from ..agent.permission_service import PermissionDecision, PermissionService
from .contracts import (CAPABILITIES, PROTOCOL, ConnectError, RequestEnvelope,
                        display_name, identifier)
from .repository import DeviceRepository


class DesktopDeviceService:
    def __init__(self, profile, *, fixture_mode=False, clock=time.time, key_store=None, monotonic=time.monotonic):
        self.repository = DeviceRepository(profile / 'connect' / 'devices.sqlite3')
        self.clock = clock
        self.fixture_mode = fixture_mode
        self.closed = False
        self.network = None
        self._network_lock = RLock()
        self.approvals = None
        self.sync = None
        platform = {'win32': 'windows', 'linux': 'linux', 'darwin': 'macos'}.get(sys.platform, 'unknown')
        os_name = host_platform.system() or 'Unknown'
        if sys.platform == 'linux':
            try:
                os_name = host_platform.freedesktop_os_release().get('NAME', 'Linux')
            except OSError:
                os_name = 'Linux'
        self.local_id = self.repository.ensure_local(platform, os_name, int(clock()))['device_id']
        from .identity import DeviceIdentityService, DeviceKeyStore
        from .pairing import PairingService
        from ..services.credential_vault import CredentialVault
        self.identities = DeviceIdentityService(self.repository, self.local_id,
            key_store if key_store is not None else DeviceKeyStore(CredentialVault(profile)), clock)
        # Vault access is lazy: unavailable pairing must not prevent local Chat startup.
        self.pairing = PairingService(self, self.identities, monotonic=monotonic)
        from .pairing_transport import DesktopPairingTransport
        self.pairing_transport = DesktopPairingTransport(self)
        from .files import FileTransferService
        self.files = FileTransferService(self, profile)

    def attach_sync(self, personal):
        from ..sync.service import RecordSyncService
        self.sync = RecordSyncService(self, personal)
        return self.sync

    def cryptographic_identity(self):
        if self.closed:
            raise ConnectError('service_closed')
        return self.identities.ensure()

    def require_paired_identity(self, public, *, timeout=10):
        """Check a public binding, NOT proof of possession or action authorization.

        C3 authenticates the live transport before using this check, then rechecks
        the exact public identity and current permissions in the dispatch transaction.
        """
        from .identity import fingerprint
        expected = fingerprint(public)
        record = self.device(public['device_id'], timeout=timeout)
        if record.get('trust_state') != 'paired' or record.get('revoked_at') is not None:
            raise ConnectError('device_not_paired')
        if record.get('identity_fingerprint') != expected:
            raise ConnectError('identity_mismatch')
        return record

    def this_device(self):
        return self.device(self.local_id)

    def device(self, device_id, *, timeout=10):
        identifier(device_id)
        # A short committed snapshot; dispatch rechecks authority under its
        # writer transaction before claiming or executing any request.
        with self.repository.transaction(timeout=timeout, read_only=True) as db:
            record = self.repository.get(db, device_id)
            if record is None:
                raise ConnectError('unknown_device')
            return record

    def paired_devices(self, *, timeout=10):
        return self.repository.devices(timeout=timeout)

    def rename(self, device_id, name):
        identifier(device_id)
        name = display_name(name)
        with self.repository.transaction() as db:
            record = self.repository.get(db, device_id)
            if not record:
                raise ConnectError('unknown_device')
            record.update(display_name=name, revision=record['revision'] + 1)
            self.repository.put(db, record)
        return record

    def capabilities(self):
        values = self.this_device()['capabilities']
        policies = {v['capability']: v['policy_disabled'] for v in values}
        values = [v for v in values if v['capability'] not in {'files.receive', 'files.send'}] + [
            dict(capability=c, supported=True, policy_disabled=policies.get(c, False))
            for c in ('files.receive', 'files.send')]
        if self.sync is not None:
            from ..sync.records import CAPABILITIES
            existing = {v['capability']: v for v in values}
            values = [v for v in values if v['capability'] not in CAPABILITIES]
            values += [dict(capability=c, supported=(c != 'sync.chat' or self.sync.store.chat is not None),
                            policy_disabled=existing.get(c, {}).get('policy_disabled', False)) for c in sorted(CAPABILITIES)]
        return values

    def enroll_fixture(self, name, *, capabilities=()):
        if not self.fixture_mode or self.closed:
            raise ConnectError('fixtures_disabled')
        return self.repository.add_fixture(name, int(self.clock()), capabilities=capabilities)

    def set_permission(self, device_id, capability, decision, *, scope=None):
        """Local settings API, used by the strict Devices facade, never transport.

        Off is the existing DENY value, never an independent permission engine.
        """
        identifier(device_id)
        if capability not in CAPABILITIES:
            raise ConnectError('unknown_capability')
        decision = PermissionDecision(decision)
        if scope is not None and (type(scope) is not str or not 1 <= len(scope) <= 160):
            raise ConnectError('invalid_scope')
        with self.repository.transaction() as db:
            record = self.repository.get(db, device_id)
            if not record or record.get('trust_state') != 'paired':
                raise ConnectError('device_not_paired')
            rules = [r for r in record['permissions'] if (r['capability'], r['scope']) != (capability, scope)]
            rules.append(dict(capability=capability, scope=scope, decision=decision.value))
            record.update(permissions=rules, revision=record['revision'] + 1)
            self.repository.put(db, record)
            self.repository.audit(db, device_id, None, capability, int(self.clock()), 'permission_changed')
        self.files.invalidate(device_id, 'permission_or_trust_changed')
        if self.approvals is not None:
            self.approvals.invalidate(device_id)

    def permission(self, device_id, capability, *, scope=None):
        if capability not in CAPABILITIES:
            raise ConnectError('unknown_capability')
        record = self.device(device_id)
        if record.get('trust_state') != 'paired':
            return PermissionDecision.DENY
        return PermissionService.evaluate_device(record['permissions'], capability, scope)

    def revoke(self, device_id):
        identifier(device_id)
        with self.repository.transaction() as db:
            record = self.repository.get(db, device_id)
            if not record or device_id == self.local_id:
                raise ConnectError('unknown_device')
            if record['trust_state'] != 'revoked':
                record.update(trust_state='revoked', revoked_at=int(self.clock()),
                              connection_state='offline', permissions=[], revision=record['revision'] + 1)
                self.repository.put(db, record)
                self.repository.audit(db, device_id, None, None, int(self.clock()), 'device_revoked')
        self.files.invalidate(device_id, 'permission_or_trust_changed')
        if self.approvals is not None:
            self.approvals.invalidate(device_id)
        if self.network is not None:
            self.network.disconnect(device_id, revoked=True)
        return record

    def _authorize(self, db, request, peer, public=None):
        if self.closed or (public is None and not self.fixture_mode):
            raise ConnectError('fixtures_disabled')
        # Peer comes from the authenticated channel or explicit fixture, never the message.
        if peer != request.source_device_id:
            raise ConnectError('source_mismatch')
        record = self.repository.get(db, peer)
        if not record:
            raise ConnectError('unknown_device')
        if record.get('trust_state') != 'paired' or record.get('revoked_at') is not None:
            raise ConnectError('device_not_paired')
        if public is None:
            if record.get('connection_kind') != 'fixture':
                raise ConnectError('unauthenticated_transport')
        elif record.get('public_identity') != public:
            raise ConnectError('identity_mismatch')
        if request.target_device_id != self.local_id:
            raise ConnectError('wrong_target')
        now = int(self.clock())
        if request.timestamp > now + 5 or request.expires_at <= now:
            raise ConnectError('expired_request')
        request.validate_operation()
        metadata = next(c for c in self.capabilities_from_db(db) if c['capability'] == request.capability)
        if not metadata['supported'] or metadata['policy_disabled']:
            raise ConnectError('capability_unavailable')
        decision = PermissionService.evaluate_device(record['permissions'], request.capability)
        if decision == PermissionDecision.ASK and public is not None and self.approvals is not None:
            if self.approvals.check(request, public, record,
                                    target_name=self.repository.get(db, self.local_id)['display_name']):
                return
        if decision != PermissionDecision.ALLOW:
            # Only the trusted local adapter can satisfy Ask; no wire approval flag exists.
            raise ConnectError('confirmation_required' if decision == PermissionDecision.ASK else 'permission_off')

    def capabilities_from_db(self, db):
        return self.repository.get(db, self.local_id)['capabilities']

    def _execute(self, request):
        if request.capability == 'connect.ping':
            return {'pong': True}
        if request.capability == 'device.status':
            return {'core_available': True, 'transport': 'fixture', 'encrypted': False}
        if request.capability == 'chat.metadata.read':
            return {'content_access': False, 'inference_access': False}
        raise ConnectError('capability_unavailable')

    def receive_fixture(self, raw, *, peer_device_id):
        """Only InProcessFixtureTransport calls this; not a public/authenticated endpoint."""
        return self._receive(raw, peer_device_id=peer_device_id)

    def _receive(self, raw, *, peer_device_id, public=None):
        database_timeout = .25 if public is not None else 10
        deadline = time.monotonic() + 5 if public is not None else None
        request = None
        peer = None
        try:
            peer = identifier(peer_device_id)
            request = RequestEnvelope.decode(raw)
            with self.repository.transaction(timeout=database_timeout) as db:
                self._authorize(db, request, peer, public)
                row = db.execute('SELECT fingerprint,response FROM requests WHERE source=? AND request_id=?',
                                 (peer, request.request_id)).fetchone()
                if row:
                    if row[0] != request.fingerprint():
                        raise ConnectError('changed_duplicate')
                    if row[1] is None:
                        raise ConnectError('request_indeterminate')
                    self.repository.audit(db, peer, request.request_id, request.capability, int(self.clock()), 'duplicate')
                    return json.loads(row[1])
                if db.execute('SELECT COUNT(*) FROM requests').fetchone()[0] >= 10_000:
                    raise ConnectError('replay_capacity_reached')
                # Commit a durable claim BEFORE execution. A crash cannot replay work.
                db.execute('INSERT INTO requests VALUES(?,?,?,NULL)', (peer, request.request_id, request.fingerprint()))
            with self.repository.transaction(timeout=database_timeout) as db:
                # Re-check revocation/permissions after claim. Writer lock serializes revoke.
                self._authorize(db, request, peer, public)
                if deadline is not None and time.monotonic() >= deadline:
                    raise ConnectError('request_timeout')
                result = self._execute(request)
                if public is not None and request.capability == 'device.status':
                    result = dict(core_available=True, transport='local', encrypted=True)
                response = dict(protocol_version=PROTOCOL, request_id=request.request_id,
                                state='completed', result=result)
                db.execute('UPDATE requests SET response=? WHERE source=? AND request_id=?',
                           (json.dumps(response), peer, request.request_id))
                record = self.repository.get(db, peer)
                record['last_seen'] = int(self.clock())
                record['revision'] += 1
                self.repository.put(db, record)
                if self.approvals is not None:
                    self.approvals.completed(request, record)
                self.repository.audit(db, peer, request.request_id, request.capability, int(self.clock()), 'completed')
                return response
        except ConnectError as error:
            code = str(error)
        except Exception:
            # Never persist provider exception strings or retry uncertain work.
            code = 'internal_error'
        with self.repository.transaction(timeout=database_timeout) as db:
            self.repository.audit(db, peer, request.request_id if request else None,
                                  request.capability if request else None, int(self.clock()), code)
        return dict(protocol_version=PROTOCOL, request_id=request.request_id if request else None,
                    state='rejected', error=code)

    def enable_network(self, address, *, port=0, discovery=True):
        """Explicit trusted local action; session-only, with serialized shutdown."""
        with self._network_lock:
            if self.closed:
                raise ConnectError('service_closed')
            if self.network is not None:
                raise ConnectError('network_already_enabled')
            from .network import LocalNetwork
            network = LocalNetwork(self, address, port=port, discovery=discovery)
            self.network = network
            self.files.activate()
            return network

    def disable_network(self):
        with self._network_lock:
            self.pairing_transport.close()
            self.files.close()
            if self.sync is not None:
                self.sync.close()
            if self.network is not None:
                self.network.close()
                self.network = None
            if self.approvals is not None:
                self.approvals.invalidate()

    def close(self):
        with self._network_lock:
            self.disable_network()
            if self.approvals is not None:
                self.approvals.close()
            self.pairing.close()
            self.closed = True
