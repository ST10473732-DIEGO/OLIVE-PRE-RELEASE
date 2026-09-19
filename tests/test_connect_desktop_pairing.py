"""Ordinary C4 services and real loopback sockets; only the vault is synthetic."""
import json
from pathlib import Path
import socket
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

from olive.connect.contracts import ConnectError, canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.pairing_wire import decode_offer, validate_endpoint
from olive.connect.service import DesktopDeviceService
from olive.connect.workspace import DevicesWorkspace
from tests.test_connect_pairing import MemoryVault


def wait(predicate, timeout=7):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.03)
    raise AssertionError('desktop pairing condition timed out')


class DesktopPairingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-c41-')
        self.vaults = [MemoryVault() for _ in range(3)]
        self.services = [DesktopDeviceService(Path(self.temp.name)/str(i), key_store=DeviceKeyStore(v))
                         for i, v in enumerate(self.vaults)]
        self.a, self.b, self.c = self.services
        self.ua, self.ub, self.uc = [DevicesWorkspace(s) for s in self.services]
        for s in self.services:
            s.enable_network('127.0.0.1', discovery=False)

    def tearDown(self):
        for s in self.services:
            s.close()
        self.temp.cleanup()

    def start(self, responder=None):
        responder = responder or self.ub
        offer = self.ua.create_pairing()
        self.sid = offer['session_id']
        self.offer = offer
        responder.accept_pairing(offer['offer'])
        wait(lambda: self.ua.pairing_status(self.sid).get('comparison') and responder.pairing_status(self.sid).get('comparison'))
        return self.ua.pairing_status(self.sid), responder.pairing_status(self.sid)

    def confirm(self):
        value = self.ua.pairing_status(self.sid)['comparison']
        self.ua.confirm_pairing(self.sid, value)
        self.ub.confirm_pairing(self.sid, value)
        wait(lambda: all(u.pairing_status(self.sid)['state'] == 'completed' for u in (self.ua, self.ub)))

    def test_real_desktops_pair_then_c3_ping_permission_and_revocation(self):
        left, right = self.start()
        self.assertEqual(left['comparison'], right['comparison'])
        self.assertEqual(left['candidate_id'], self.b.local_id)
        self.assertEqual(right['candidate_id'], self.a.local_id)
        self.ua.confirm_pairing(self.sid, right['comparison'])
        time.sleep(.3)
        self.assertEqual(self.ua.pairing_status(self.sid)['state'], 'confirmed')
        self.assertEqual(self.a.paired_devices(), [])
        self.assertEqual(self.b.paired_devices(), [])
        self.ub.confirm_pairing(self.sid, left['comparison'])
        wait(lambda: self.a.paired_devices() and self.b.paired_devices())
        wait(lambda: self.a.pairing_transport.listener is None)
        for s, peer in ((self.a, self.b), (self.b, self.a)):
            record = s.device(peer.local_id)
            self.assertEqual(record['public_identity'], peer.cryptographic_identity())
            self.assertEqual(record['permissions'], [])
            self.assertEqual(record['connection_state'], 'offline')
        self.a.network.connect(self.b.local_id, '127.0.0.1', self.b.network.port)
        self.assertEqual(self.ua.ping(self.b.local_id)['error'], 'permission_off')
        self.b.set_permission(self.a.local_id, 'connect.ping', 'allow')
        self.assertTrue(self.ua.ping(self.b.local_id)['result']['pong'])
        self.b.revoke(self.a.local_id)
        wait(lambda: self.a.network.status(self.b.local_id)['state'] == 'offline')
        with self.assertRaises(ConnectError):
            self.b.pairing.completion.complete(self.sid)

    def test_explicit_interface_and_listener_lifecycle(self):
        self.a.disable_network()
        with self.assertRaisesRegex(ConnectError, 'select_connect_interface'):
            self.ua.create_pairing()
        self.a.enable_network('127.0.0.1', discovery=False)
        offer = self.ua.create_pairing()
        endpoint = json.loads(offer['offer'])['endpoint']
        self.assertEqual(endpoint['address'], '127.0.0.1')
        self.assertNotEqual(endpoint['port'], self.a.network.port)
        self.a.pairing_transport.cancel(offer['session_id'])
        self.assertIsNone(self.a.pairing_transport.listener)
        with self.assertRaises(OSError):
            socket.create_connection((endpoint['address'], endpoint['port']), timeout=.3)
        offer = self.ua.create_pairing()
        with self.a.pairing._lock:
            self.a.pairing._sessions[offer['session_id']]['deadline'] = 0
        wait(lambda: self.a.pairing_transport.listener is None)
        self.assertEqual(self.ua.pairing_status(offer['session_id'])['state'], 'expired')
        self.ua.create_pairing()
        self.a.close()
        self.assertIsNone(self.a.pairing_transport.listener)

    def test_numeric_local_endpoint_and_strict_version(self):
        for address in ('0.0.0.0', '8.8.8.8', 'example.local', '169.254.1.2', '::', 'ff02::1', '::ffff:127.0.0.1'):
            with self.subTest(address=address), self.assertRaises(ConnectError):
                validate_endpoint(dict(address=address, port=1234))
        for port in (True, 0, 65536, '1234'):
            with self.assertRaises(ConnectError):
                validate_endpoint(dict(address='127.0.0.1', port=port))
        offer = json.loads(self.ua.create_pairing()['offer'])
        self.assertEqual(offer['protocol'], 'olive-pairing-tls13/2')
        with self.assertRaises(ConnectError):
            decode_offer(canonical(dict(offer, protocol='olive-pairing-tls13/1')), time.time())
        changed = dict(offer, endpoint=dict(address='192.168.1.1', port=1234))
        with self.assertRaisesRegex(ConnectError, 'outside_interface'):
            self.ub.accept_pairing(canonical(changed).decode())

    def test_malformed_connections_do_not_consume_offer_or_dispatch(self):
        offer = self.ua.create_pairing()
        self.sid = offer['session_id']
        endpoint = json.loads(offer['offer'])['endpoint']
        for raw in (struct.pack('!I', 999999), struct.pack('!I', 2) + b'{}', b'\0'):
            with socket.create_connection((endpoint['address'], endpoint['port']), timeout=1) as sock:
                sock.sendall(raw)
        self.ub.accept_pairing(offer['offer'])
        wait(lambda: self.ua.pairing_status(self.sid).get('comparison'))
        self.assertEqual(self.a.paired_devices(), [])
        self.confirm()

    def test_copied_offer_first_connection_same_name_has_no_authority(self):
        self.c.rename(self.c.local_id, self.b.this_device()['display_name'])
        left, hostile = self.start(self.uc)
        self.uc.confirm_pairing(self.sid, left['comparison'])
        time.sleep(.2)
        self.assertEqual(self.a.paired_devices(), [])
        self.assertEqual(self.c.paired_devices(), [])
        self.assertEqual(left['candidate_id'], self.c.local_id)
        self.assertNotEqual(left['candidate_id'], self.b.local_id)
        with self.assertRaises(ConnectError):
            self.ua.confirm_pairing(self.sid, '00:' * 32)
        wait(lambda: self.a.pairing_transport.listener is None)
        self.assertEqual(self.a.paired_devices(), [])
        # Local cancellation/new intent allows the legitimate desktop to join.
        self.start()
        self.confirm()
        self.assertEqual(self.a.paired_devices()[0]['device_id'], self.b.local_id)

    def test_redirected_offer_wrong_identity_fails_tls(self):
        target = json.loads(self.uc.create_pairing()['offer'])
        honest = json.loads(self.ua.create_pairing()['offer'])
        honest['endpoint'] = target['endpoint']
        sid = self.ub.accept_pairing(canonical(honest).decode())['session_id']
        wait(lambda: self.ub.pairing_status(sid)['state'] == 'interrupted')
        self.assertTrue(all(not s.paired_devices() for s in self.services))

    def test_completion_network_drop_restart_and_idempotent_receipt_recovery(self):
        left, right = self.start()
        # Stop the carrier after one local confirmation is durable, then record
        # the other local confirmation against its already authenticated C2 TLS.
        self.ua.confirm_pairing(self.sid, right['comparison'])
        with patch.object(self.b.pairing, 'exchange', side_effect=ConnectError('injected_drop')):
            self.ub.confirm_pairing(self.sid, left['comparison'])
            wait(lambda: self.ub.pairing_status(self.sid)['state'] == 'interrupted')
        codes = [s.pairing.completion.export(self.sid) for s in (self.a, self.b)]
        for i in (0, 1):
            self.services[i].close()
            self.services[i] = DesktopDeviceService(Path(self.temp.name)/str(i), key_store=DeviceKeyStore(self.vaults[i]))
        self.a, self.b = self.services[:2]
        self.ua, self.ub = DevicesWorkspace(self.a), DevicesWorkspace(self.b)
        for ui, code in ((self.ua, codes[1]), (self.ub, codes[0])):
            self.assertEqual(ui.accept_pairing(code)['state'], 'completed')
            self.assertEqual(ui.accept_pairing(code)['state'], 'completed')
        self.assertIsNone(self.a.pairing_transport.listener)
        self.assertEqual(self.a.device(self.b.local_id)['permissions'], [])
        self.assertEqual(self.b.device(self.a.local_id)['permissions'], [])

    def test_receipts_cannot_infer_local_confirmation_or_override_cancel(self):
        left, right = self.start()
        self.ua.confirm_pairing(self.sid, right['comparison'])
        code = self.a.pairing.completion.export(self.sid)
        with self.assertRaisesRegex(ConnectError, 'confirmation_required'):
            self.ub.accept_pairing(code)
        self.ub.confirm_pairing(self.sid, left['comparison'])
        # Cancel is locally authoritative even when both confirmations exist.
        self.b.pairing_transport.cancel(self.sid)
        if not self.b.paired_devices():
            with self.assertRaises(ConnectError):
                self.ub.accept_pairing(code)
        with self.assertRaises(ConnectError):
            self.uc.accept_pairing(code)

    def test_receipts_tampering_durable_recovery_and_no_private_audit_material(self):
        self.start(); self.confirm()
        code = self.a.pairing.completion.export(self.sid)
        altered = json.loads(code)
        altered['reply']['display_name'] = 'Changed transcript'
        with self.assertRaises(ConnectError):
            self.ub.accept_pairing(canonical(altered).decode())
        altered = json.loads(code)
        altered['receipts'][self.a.local_id] = 'A' * 88
        with self.assertRaises(ConnectError):
            self.ub.accept_pairing(canonical(altered).decode())
        with patch.object(self.a, 'clock', return_value=json.loads(code)['offer']['expires_at'] + 600):
            self.assertEqual(self.ua.accept_pairing(code)['state'], 'completed')
        audit = json.dumps(self.a.repository.activity())
        for forbidden in ('certificate', '"comparison"', 'receipts', 'endpoint', 'private'):
            self.assertNotIn(forbidden, audit)


def desktop_worker(pipe, profile):
    """Test control pipe invokes the same facade as the C4 bridge; no TLS pump."""
    service = DesktopDeviceService(Path(profile), key_store=DeviceKeyStore(MemoryVault()))
    workspace = DevicesWorkspace(service)
    try:
        while True:
            command, args = pipe.recv()
            try:
                if command == 'close':
                    service.close(); pipe.send(True); return
                methods = dict(enable=workspace.enable, create=workspace.create_pairing,
                    accept=workspace.accept_pairing, status=workspace.pairing_status,
                    confirm=workspace.confirm_pairing, snapshot=workspace.snapshot,
                    permission=workspace.permission, connect=workspace.connect,
                    ping=workspace.ping, revoke=service.revoke, rename=lambda name: service.rename(service.local_id, name))
                pipe.send(dict(result=methods[command](**args)))
            except Exception as error:
                pipe.send(dict(error=str(error)))
    finally:
        service.close(); pipe.close()


class DesktopProcessAcceptance(unittest.TestCase):
    def test_three_ordinary_processes_pair_attack_then_c3(self):
        import multiprocessing
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory(prefix='olive-c41-process-') as root:
            children, pipes = [], []
            def call(index, command, **args):
                pipes[index].send((command, args))
                self.assertTrue(pipes[index].poll(10), 'ordinary desktop response timeout')
                response = pipes[index].recv()
                if 'error' in response:
                    raise ConnectError(response['error'])
                return response['result']
            try:
                for i in range(3):
                    parent, child = context.Pipe()
                    process = context.Process(target=desktop_worker, args=(child, str(Path(root)/str(i))))
                    process.start(); child.close(); children.append(process); pipes.append(parent)
                snapshots = [call(i, 'enable', address='127.0.0.1', discovery=False) for i in range(3)]
                ids = [s['local']['device_id'] for s in snapshots]
                # A copied offer and the same human-readable name cannot confer trust.
                call(2, 'rename', name=snapshots[1]['local']['display_name'])
                offer = call(0, 'create'); sid = offer['session_id']
                call(2, 'accept', offer=offer['offer'])
                preview = wait(lambda: (s if (s := call(0, 'status', session_id=sid)).get('comparison') else None))
                self.assertEqual(preview['candidate_id'], ids[2])
                call(2, 'confirm', session_id=sid, compared_value=preview['comparison'])
                self.assertFalse(call(0, 'snapshot')['devices'])
                with self.assertRaises(ConnectError):
                    call(0, 'confirm', session_id=sid, compared_value='wrong comparison')
                self.assertFalse(call(2, 'snapshot')['devices'])
                # Same ordinary service creates a fresh explicit ceremony for B.
                offer = call(0, 'create'); sid = offer['session_id']
                endpoint = json.loads(offer['offer'])['endpoint']
                with socket.create_connection((endpoint['address'], endpoint['port']), timeout=1) as sock:
                    sock.sendall(struct.pack('!I', 999999))
                call(1, 'accept', offer=offer['offer'])
                previews = [wait(lambda i=i: (s if (s := call(i, 'status', session_id=sid)).get('comparison') else None)) for i in (0, 1)]
                self.assertEqual(previews[0]['comparison'], previews[1]['comparison'])
                call(0, 'confirm', session_id=sid, compared_value=previews[1]['comparison'])
                self.assertFalse(call(0, 'snapshot')['devices'])
                self.assertFalse(call(1, 'snapshot')['devices'])
                call(1, 'confirm', session_id=sid, compared_value=previews[0]['comparison'])
                for i in (0, 1):
                    wait(lambda i=i: call(i, 'status', session_id=sid)['state'] == 'completed')
                    self.assertEqual(call(i, 'snapshot')['devices'][0]['permissions'], [])
                wait(lambda: not call(0, 'status', session_id=sid)['listener_active'])
                call(0, 'connect', device_id=ids[1], address='127.0.0.1', port=snapshots[1]['network']['port'])
                self.assertEqual(call(0, 'ping', device_id=ids[1])['error'], 'permission_off')
                call(1, 'permission', device_id=ids[0], capability='connect.ping', decision='allow')
                self.assertTrue(call(0, 'ping', device_id=ids[1])['result']['pong'])
                call(1, 'revoke', device_id=ids[0])
                wait(lambda: call(0, 'snapshot')['devices'][0]['live']['state'] == 'offline')
            finally:
                for pipe, process in zip(pipes, children):
                    if process.is_alive():
                        pipe.send(('close', {}))
                        if pipe.poll(5):
                            pipe.recv()
                    process.join(5)
                    if process.is_alive():
                        process.terminate(); process.join(5)
                    pipe.close()
