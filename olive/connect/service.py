"""Desktop device service. Fixture dispatch has no reference to Agent or tool registry."""
import json
import platform as host_platform
import sys
import time

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

    def cryptographic_identity(self):
        if self.closed:
            raise ConnectError('service_closed')
        return self.identities.ensure()

    def require_paired_identity(self, public):
        """Check a public binding, NOT proof of possession or action authorization.

        C3 must first authenticate a live transport and recheck this binding plus
        current permissions at dispatch. C2 exposes no authenticated action route.
        """
        from .identity import fingerprint
        expected = fingerprint(public)
        record = self.device(public['device_id'])
        if record.get('trust_state') != 'paired' or record.get('revoked_at') is not None:
            raise ConnectError('device_not_paired')
        if record.get('identity_fingerprint') != expected:
            raise ConnectError('identity_mismatch')
        return record

    def this_device(self):
        return self.device(self.local_id)

    def device(self, device_id):
        identifier(device_id)
        with self.repository.transaction() as db:
            record = self.repository.get(db, device_id)
            if record is None:
                raise ConnectError('unknown_device')
            return record

    def paired_devices(self):
        return self.repository.devices()

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
        return self.this_device()['capabilities']

    def enroll_fixture(self, name, *, capabilities=()):
        if not self.fixture_mode or self.closed:
            raise ConnectError('fixtures_disabled')
        return self.repository.add_fixture(name, int(self.clock()), capabilities=capabilities)

    def set_permission(self, device_id, capability, decision, *, scope=None):
        """Local settings API only; no bridge, model or transport route exposes this.

        Future Devices UI must call this through the guarded settings adapter.
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
        return record

    def _authorize(self, db, request, peer):
        if not self.fixture_mode or self.closed:
            raise ConnectError('fixtures_disabled')
        # Peer comes from local fixture construction, never the message's source field.
        if peer != request.source_device_id:
            raise ConnectError('source_mismatch')
        record = self.repository.get(db, peer)
        if not record:
            raise ConnectError('unknown_device')
        if record.get('trust_state') != 'paired' or record.get('revoked_at') is not None:
            raise ConnectError('device_not_paired')
        if record.get('connection_kind') != 'fixture':
            raise ConnectError('unauthenticated_transport')
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
        if decision != PermissionDecision.ALLOW:
            # C1 intentionally has no remote confirmation route or boolean approval field.
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
        request = None
        peer = None
        try:
            peer = identifier(peer_device_id)
            request = RequestEnvelope.decode(raw)
            with self.repository.transaction() as db:
                self._authorize(db, request, peer)
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
            with self.repository.transaction() as db:
                # Re-check revocation/permissions after claim. Writer lock serializes revoke.
                self._authorize(db, request, peer)
                result = self._execute(request)
                response = dict(protocol_version=PROTOCOL, request_id=request.request_id,
                                state='completed', result=result)
                db.execute('UPDATE requests SET response=? WHERE source=? AND request_id=?',
                           (json.dumps(response), peer, request.request_id))
                record = self.repository.get(db, peer)
                record['last_seen'] = int(self.clock())
                record['revision'] += 1
                self.repository.put(db, record)
                self.repository.audit(db, peer, request.request_id, request.capability, int(self.clock()), 'completed')
                return response
        except ConnectError as error:
            code = str(error)
        except Exception:
            # Never persist provider exception strings or retry uncertain work.
            code = 'internal_error'
        with self.repository.transaction() as db:
            self.repository.audit(db, peer, request.request_id if request else None,
                                  request.capability if request else None, int(self.clock()), code)
        return dict(protocol_version=PROTOCOL, request_id=request.request_id if request else None,
                    state='rejected', error=code)

    def close(self):
        self.pairing.close()
        self.closed = True  # No socket, worker, persistent connection or discovery to stop.
