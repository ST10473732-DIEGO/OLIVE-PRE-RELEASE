"""Opt-in persistent endpoints, startup fail-closed and real socket reuse."""
from dataclasses import asdict
from pathlib import Path
import json
import socket
import tempfile
import unittest
from unittest.mock import patch

from olive.connect.contracts import ConnectError
from olive.connect.discovery import interfaces, Interface
from olive.connect.identity import DeviceKeyStore
from olive.connect.listener import listener_socket
from olive.connect.network_settings import NetworkSettingsStore
from olive.connect.service import DesktopDeviceService
from olive.connect.workspace import DevicesWorkspace
from tests.test_connect_pairing import MemoryVault


class PersistentNetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.profile = Path(self.temp.name)
        self.vault = MemoryVault()
        self.service = self.make_service()

    def make_service(self):
        return DesktopDeviceService(self.profile, key_store=DeviceKeyStore(self.vault))

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def enable(self):
        self.service.configure_network('127.0.0.1', discovery=False, persistent=True)
        return self.service.network.port, self.service.pairing_port

    def test_old_installation_and_session_only_still_start_off(self):
        self.service.restore_network()
        self.assertIsNone(self.service.network)
        self.service.configure_network('127.0.0.1', discovery=False)
        self.service.close()
        self.service = self.make_service()
        self.service.restore_network()
        self.assertIsNone(self.service.network)
        self.assertIsNone(self.service.network_settings.load())

    def test_restart_preserves_exact_ports_identity_and_off_cancels_startup(self):
        ports = self.enable()
        identity = self.service.cryptographic_identity()
        offer = json.loads(self.service.pairing_transport.create())
        self.assertEqual(offer['endpoint']['port'], ports[1])
        self.service.pairing_transport.cancel(offer['session_id'])
        # Another fresh dialog reuses the selected pairing port, with a new session.
        offer2 = json.loads(self.service.pairing_transport.create())
        self.assertEqual(offer2['endpoint']['port'], ports[1])
        self.assertNotEqual(offer['session_id'], offer2['session_id'])
        self.service.close()
        self.service = self.make_service()
        self.service.restore_network()
        self.assertEqual((self.service.network.port, self.service.pairing_port), ports)
        self.assertEqual(self.service.cryptographic_identity(), identity)
        state = DevicesWorkspace(self.service).snapshot()['network']
        self.assertTrue(state['persistent'])
        # Pairing is not listening simply because startup is enabled.
        with listener_socket('127.0.0.1') as probe:
            probe.bind(('127.0.0.1', ports[1]))
            probe.listen(1)
        DevicesWorkspace(self.service).disable()
        self.service.close()
        self.service = self.make_service()
        self.service.restore_network()
        self.assertIsNone(self.service.network)
        self.assertEqual(self.enable(), ports)

    def test_listener_collision_does_not_fall_back_or_overwrite_saved_port(self):
        ports = self.enable()
        self.service.close()
        with listener_socket('127.0.0.1') as occupied:
            occupied.bind(('127.0.0.1', ports[0]))
            occupied.listen(1)
            self.service = self.make_service()
            self.service.restore_network()
            self.assertIsNone(self.service.network)
            self.assertEqual(self.service.network_error, 'saved_connect_listener_unavailable')
            self.assertEqual(self.service.network_settings.load()['port'], ports[0])
        self.service.restore_network()
        self.assertEqual(self.service.network.port, ports[0])

    def test_changed_interface_or_subnet_never_substitutes(self):
        self.enable()
        saved = self.service.network_settings.load()
        self.service.close()
        self.service = self.make_service()
        original = saved['interface']
        for changed in ([], [Interface('different', original['address'], original['network'])],
                        [Interface(original['name'], original['address'], '127.0.0.1/32')]):
            with patch('olive.connect.discovery.interfaces', return_value=changed):
                self.service.restore_network()
            self.assertIsNone(self.service.network)
            self.assertEqual(self.service.network_error, 'saved_connect_interface_unavailable')

    def test_corrupt_config_is_retained_and_cannot_enable_listener(self):
        self.service.network_settings.path.parent.mkdir(exist_ok=True)
        self.service.network_settings.path.write_text('{broken')
        self.service.restore_network()
        self.assertIsNone(self.service.network)
        self.assertEqual(self.service.network_error, 'network_settings_invalid')
        self.assertEqual(self.service.network_settings.path.read_text(), '{broken')

    def test_store_failure_rolls_back_network_and_startup_intent(self):
        with patch.object(self.service.network_settings, 'save', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.enable()
        self.assertIsNone(self.service.network)
        self.assertFalse(self.service.persistent_network)
        self.assertIsNone(self.service.network_settings.load())

    def test_pairing_port_collision_cannot_open_random_replacement(self):
        ports = self.enable()
        with listener_socket('127.0.0.1') as occupied:
            occupied.bind(('127.0.0.1', ports[1]))
            occupied.listen(1)
            with self.assertRaisesRegex(ConnectError, 'pairing_listener_unavailable'):
                self.service.pairing_transport.create()
        self.assertEqual(self.service.pairing_port, ports[1])
        self.assertEqual(self.service.paired_devices(), [])

    def test_live_port_exclusive_and_restart_after_server_active_close(self):
        # Actual accepted TCP connections leave TIME_WAIT; restart must keep its
        # exact port without SO_REUSEPORT or an overlapping live listener.
        with listener_socket('127.0.0.1') as first:
            first.bind(('127.0.0.1', 0)); first.listen(1)
            port = first.getsockname()[1]
            with listener_socket('127.0.0.1') as duplicate:
                with self.assertRaises(OSError):
                    duplicate.bind(('127.0.0.1', port)); duplicate.listen(1)
            with socket.create_connection(('127.0.0.1', port), timeout=2) as client:
                accepted, _ = first.accept()
                accepted.shutdown(socket.SHUT_WR)
                self.assertEqual(client.recv(1), b'')
                client.shutdown(socket.SHUT_WR)
                self.assertEqual(accepted.recv(1), b'')
                accepted.close()
        with listener_socket('127.0.0.1') as restarted:
            restarted.bind(('127.0.0.1', port)); restarted.listen(1)

    def test_settings_reject_wrong_types_wildcard_duplicate_or_privileged_ports(self):
        self.enable()
        valid = self.service.network_settings.load()
        for field, value in [('enabled', 1), ('discovery', 'true'), ('version', True),
                             ('port', True), ('port', 443), ('pairing_port', valid['port'])]:
            with self.subTest(field=field, value=value), self.assertRaises(ConnectError):
                NetworkSettingsStore.validate({**valid, field: value})
        for address in ('0.0.0.0', '224.0.0.251', '192.168.1.1'):
            with self.assertRaises(ConnectError):
                NetworkSettingsStore.validate({**valid, 'interface': {**valid['interface'], 'address': address}})
