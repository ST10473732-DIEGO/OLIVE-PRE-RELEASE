"""Public Devices presentation facade; no private identities leave this module."""
from dataclasses import asdict
import json
from threading import RLock
import uuid
import time

from .contracts import ConnectError, PROTOCOL, SAFE_OPERATIONS, canonical
from .discovery import interfaces
from .identity import fingerprint


class DevicesWorkspace:
    def __init__(self, service):
        self.service = service
        self.lock = RLock()
        self.network_state = 'off'
        self.network_error = None
        self.offer = None
        self.pings = {}

    def snapshot(self):
        s = self.service
        network = s.network
        try:
            candidates = [asdict(i) for i in interfaces()]
            interface_error = None
        except Exception:
            candidates, interface_error = [], 'interface_enumeration_unavailable'
        local = s.this_device()
        with s.repository.transaction() as db:
            row = db.execute('SELECT public,state FROM connect_keys WHERE device_id=?', (s.local_id,)).fetchone()
            recovery = []
            for sid, record, state in db.execute('SELECT c.session_id,c.record,l.state FROM pairing_completion_v1 c JOIN pairing_ledger l ON c.session_id=l.session_id'):
                if state not in ('cancelled', 'failed', 'expired'):
                    recovery.append(dict(session_id=sid, state=state))
        local['fingerprint'] = fingerprint(json.loads(row[0])) if row and row[1] == 'ready' else None
        local['core_available'] = True
        devices = []
        for record in s.paired_devices():
            value = {k: v for k, v in record.items() if k != 'public_identity'}
            value['live'] = network.status(record['device_id']) if network else dict(
                state='offline', error=None, encrypted=False, connection=None, latency_ms=None)
            value['transfers'] = s.files.list(record['device_id'])
            value['remote_ai'] = s.inference.snapshot(record['device_id']) if s.inference else None
            value['sync'] = s.sync.status(record['device_id']) if s.sync else None
            devices.append(value)
        return dict(local=local, devices=devices, capabilities=s.capabilities(),
            interfaces=candidates, interface_error=interface_error, protocol=PROTOCOL,
            network=dict(state=('on' if not network.stopping.is_set() else 'off') if network else ('off' if self.network_state == 'on' else self.network_state), error=self.network_error,
                interface=asdict(network.interface) if network else None,
                port=network.port if network else None, discovery=bool(network and network.discovery)),
            nearby=[{k: v for k, v in entry.items() if k != 'seen'} for entry in network.discovery.nearby()] if network and network.discovery else [],
            sync=s.sync.status() if s.sync else None, activity=s.repository.activity()[-200:], pairing_recovery=recovery[-32:])

    def enable(self, address, discovery):
        with self.lock:
            self.network_state, self.network_error = 'starting', None
            try:
                self.service.enable_network(address, discovery=discovery)
                self.network_state = 'on'
            except Exception as error:
                self.network_state = 'failed'
                self.network_error = str(error) if isinstance(error, ConnectError) else 'listener_or_discovery_unavailable'
            return self.snapshot()

    def disable(self):
        with self.lock:
            self.service.disable_network()
            self.network_state, self.network_error = 'off', None
            self.pings.clear()
            return self.snapshot()

    def permission(self, device_id, capability, decision):
        metadata = next((c for c in self.service.capabilities() if c['capability'] == capability), None)
        if not metadata or not metadata['supported'] or metadata['policy_disabled'] or capability not in (set(SAFE_OPERATIONS) | {'models.remote', 'sync.tasks', 'sync.calendar', 'sync.reminders', 'sync.chat', 'files.send', 'files.receive'}):
            raise ConnectError('capability_unavailable')
        self.service.set_permission(device_id, capability, decision)
        return self.snapshot()

    def create_pairing(self):
        with self.lock:
            if self.offer:
                try:
                    self.service.pairing_transport.cancel(self.offer['session_id'])
                except ConnectError:
                    pass
            raw = self.service.pairing_transport.create().decode('utf-8')
            value = json.loads(raw)
            self.offer = dict(session_id=value['session_id'], expires_at=value['expires_at'], offer=raw)
            return self.pairing_status(value['session_id'])

    def accept_pairing(self, offer):
        raw = offer.encode('utf-8')
        if len(raw) > 12288:
            raise ConnectError('invalid_pairing_offer')
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            raise ConnectError('invalid_pairing_offer') from None
        if type(value) is dict and value.get('protocol') == 'olive-pairing-completion/1':
            return self.service.pairing_transport.import_completion(raw)
        sid = self.service.pairing_transport.accept(raw)
        return self.pairing_status(sid)

    def pairing_status(self, session_id):
        with self.lock:
            result = self.service.pairing_transport.status(session_id)
            if self.offer and self.offer['session_id'] == session_id:
                result.setdefault('expires_at', self.offer['expires_at'])
                if result['state'] == 'offer_ready':
                    result['offer'] = self.offer['offer']
            return result

    def confirm_pairing(self, session_id, compared_value):
        self.service.pairing.confirm(session_id, compared_value)
        return self.pairing_status(session_id)

    def connect(self, device_id, address, port):
        network = self.service.network
        if not network:
            raise ConnectError('network_disabled')
        network.connect(device_id, address, port)
        return self.snapshot()

    def ping(self, device_id):
        network = self.service.network
        if not network:
            raise ConnectError('network_disabled')
        with network.lock:
            channel = network.channels.get(device_id)
        if not channel:
            raise ConnectError('device_offline')
        now = int(self.service.clock())
        with self.lock:
            self.pings = {key: value for key, value in self.pings.items()
                          if value['expires_at'] > now and value['deadline'] > time.monotonic()}
            pending = self.pings.get(device_id)
            if pending is None:
                if len(self.pings) >= 32:
                    raise ConnectError('request_capacity_reached')
                raw = canonical(dict(request_id=str(uuid.uuid4()), protocol_version=PROTOCOL,
                    source_device_id=self.service.local_id, target_device_id=device_id, capability='connect.ping',
                    operation='ping', arguments={}, timestamp=now, expires_at=now + 120))
                pending = dict(raw=raw, expires_at=now + 120, deadline=time.monotonic() + 120)
                self.pings[device_id] = pending
            response = channel.request(pending['raw'])
            if response.get('error') != 'confirmation_required':
                self.pings.pop(device_id, None)
            return response
