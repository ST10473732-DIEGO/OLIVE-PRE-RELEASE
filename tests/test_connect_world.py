"""OLIVE Connect World integration: real relay, real World clients, real pinned Connect TLS.

Desktop A (DesktopDeviceService + LocalNetwork + WorldService presence) and
phone-role peers (DesktopDeviceService + WorldPeer) meet through a loopback
development relay. Direct is not used unless a test says so ("forced World").
"""
import json
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from olive.connect.contracts import ConnectError, RequestEnvelope, canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.connect.world import WorldSettingsStore, parse_provisioning
from olive.connect.world_peer import WorldPeer, provision
from olive.world import wire
from tests.test_connect_network import pair, request, until
from tests.test_connect_pairing import MemoryVault
from tests.world_fixture import RelayThread

SECRET = 'OLIVE_WORLD_SECRET_SENTENCE_12345'


def tls_records(stream):
    """Split a relay-visible byte stream into TLS records: [(content_type, length)]."""
    records, offset = [], 0
    while offset + 5 <= len(stream):
        kind, length = stream[offset], int.from_bytes(stream[offset + 3:offset + 5], 'big')
        records.append((kind, length))
        offset += 5 + length
    return records, offset == len(stream)


class WorldIntegrationBase(unittest.TestCase):
    def setUp(self):
        self.thread_errors = []
        self.original_hook = threading.excepthook
        threading.excepthook = self.thread_errors.append
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.seen = []
        self.tamper = None
        self.relay = RelayThread(observer=self.observe).start()
        self.vaults = {}
        self.desk = self.service('desk')
        self.phone = self.service('phone')
        pair(self.phone, self.desk)
        self.attach()
        self.nd = self.desk.enable_network('127.0.0.1', discovery=False)
        self.np = self.phone.enable_network('127.0.0.1', discovery=False)
        self.desk.world.dev = True
        self.desk.world.set_relay_url(self.relay.url)
        self.desk.world.set_enabled(True)
        self.peers = []

    def attach(self):
        """Subclasses attach application services before the network starts."""

    def detach(self):
        """Subclasses close application stores after Connect, before the profile is removed."""

    def service(self, name):
        vault = self.vaults.setdefault(name, MemoryVault())
        return DesktopDeviceService(self.root / name, key_store=DeviceKeyStore(vault))

    def observe(self, role, payload):
        self.seen.append((role, payload))
        if self.tamper is not None:
            return self.tamper(role, payload)
        return None

    def tearDown(self):
        for peer in self.peers:
            peer.close()
        for service in [s for s in vars(self).values() if isinstance(s, DesktopDeviceService)]:
            service.close()
        self.detach()
        self.relay.stop()
        self.temp.cleanup()
        threading.excepthook = self.original_hook
        self.assertEqual(self.thread_errors, [], 'uncaught worker exception')

    def world_peer(self, phone=None, desk=None):
        phone, desk = phone or self.phone, desk or self.desk
        peer = WorldPeer(phone, desk.local_id, dev=True)
        self.peers.append(peer)
        return peer

    def direct(self, phone=None, desk=None, nd=None):
        phone, desk = phone or self.phone, desk or self.desk
        return phone.network.connect(desk.local_id, '127.0.0.1', (nd or desk.network).port)

    def provisioned(self, phone=None, desk=None):
        """The one-time World enrolment over an authenticated Direct session, then Direct off."""
        phone, desk = phone or self.phone, desk or self.desk
        channel = self.direct(phone, desk)
        peer = self.world_peer(phone, desk)
        result = provision(channel, phone, desk.local_id)
        self.assertEqual(result['state'], 'provisioned')
        peer.store(result)
        phone.network.disconnect(desk.local_id)
        until(lambda: desk.network.status(phone.local_id)['state'] != 'online')
        until(lambda: desk.world.status()['peers'][phone.local_id]['route'] == 'registered', 6)
        return peer

    def world_connect(self, peer, attempts=40):
        last = None
        for _ in range(attempts):
            try:
                return peer.connect(wait=3)
            except Exception as error:
                last = error
                time.sleep(.25)
        raise AssertionError('World did not connect: %r' % (last,))

    def ping(self, channel, phone=None, desk=None, nonce=None):
        phone, desk = phone or self.phone, desk or self.desk
        desk.set_permission(phone.local_id, 'connect.ping', 'allow')
        value = request(phone, desk)
        if nonce:
            value['arguments'] = {'nonce': nonce}
        return channel.request(canonical(value))

    def executed(self, desk=None):
        with sqlite3.connect((desk or self.desk).repository.path) as db:
            return db.execute("SELECT COUNT(*) FROM requests WHERE response IS NOT NULL").fetchone()[0]


class ProvisioningTests(WorldIntegrationBase):
    def test_existing_pair_is_provisioned_without_repairing_and_idempotently(self):
        channel = self.direct()
        first = provision(channel, self.phone, self.desk.local_id)
        second = provision(channel, self.phone, self.desk.local_id)
        self.assertEqual(first['state'], 'provisioned')
        self.assertEqual((second['route_id'], second['route_secret']), (first['route_id'], first['route_secret']),
                         'repeated provisioning never creates new routes')
        confirmed = provision(channel, self.phone, self.desk.local_id, have=first['route_id'])
        self.assertEqual(confirmed, dict(world_protocol='olive-world/1', state='current', route_id=first['route_id'],
                                         relay_url=self.relay.url))
        self.assertEqual(self.desk.world.status()['peers'][self.phone.local_id]['confirmed'], True)
        stale = provision(channel, self.phone, self.desk.local_id, have='0' * 32)
        self.assertEqual(stale['route_secret'], first['route_secret'], 'a mismatch re-sends the current route')
        self.assertEqual(self.desk.world.status()['peers'][self.phone.local_id]['confirmed'], False)
        settings = (self.root / 'desk' / 'connect' / 'world-v1.json').read_text()
        self.assertNotIn(first['route_secret'], settings)
        self.assertNotIn(first['route_id'], settings)
        status = json.dumps(self.desk.world.status())
        for secret in (first['route_secret'], first['route_id'], wire.relay_credential(bytes.fromhex(first['route_secret'])).hex()):
            self.assertNotIn(secret, status)
        # The master key sits in the OS vault slot next to the Connect identity key.
        self.assertIn('connect-world-v1', self.vaults['desk'].values)

    def test_protocol_probe_is_additive_for_strict_older_phones(self):
        channel = self.direct()
        now = int(time.time())
        raw = canonical(dict(request_id=str(uuid.uuid4()), protocol_version='olive-connect/1',
            source_device_id=self.phone.local_id, target_device_id=self.desk.local_id, capability='connect.ping',
            operation='protocols', arguments={}, timestamp=now, expires_at=now + 60))
        result = channel.request(raw)['result']
        self.assertEqual(set(result), {'pong', 'protocols'}, 'no new keys an exact decoder would reject')
        self.assertIn('olive-world/1', result['protocols'])
        self.assertTrue(all(type(p) is str for p in result['protocols']))

    def test_older_desktop_refuses_world_op_without_dropping_the_channel(self):
        channel = self.direct()
        with patch.object(RequestEnvelope, 'is_world_request', property(lambda self: False)):
            with self.assertRaises(ConnectError) as refused:
                provision(channel, self.phone, self.desk.local_id)
        self.assertEqual(str(refused.exception), 'unknown_operation')
        self.assertTrue(self.ping(channel)['result']['pong'], 'the channel stays usable')

    def test_world_off_or_unconfigured_is_truthful_and_holds_no_relay_presence(self):
        channel = self.direct()
        self.desk.world.set_enabled(False)
        self.assertEqual(provision(channel, self.phone, self.desk.local_id),
                         dict(world_protocol='olive-world/1', state='unavailable', reason='disabled'))
        self.assertEqual(self.desk.world.status()['relay'], 'off')
        self.desk.world.set_enabled(True)
        self.desk.world.set_relay_url(None)
        self.assertEqual(provision(channel, self.phone, self.desk.local_id)['reason'], 'relay_not_configured')
        self.assertEqual(self.desk.world.status()['relay'], 'not_configured')
        self.assertEqual(self.desk.world.presence.active_tasks(), {})
        self.assertEqual(self.relay.run(lambda: len(self.relay.relay.routes)), 0)
        with self.assertRaises(ConnectError):
            self.desk.world.set_relay_url('ws://relay.example.com')  # Never a plaintext production relay.

    def test_fixture_transport_cannot_provision(self):
        now = int(time.time())
        raw = canonical(dict(request_id=str(uuid.uuid4()), protocol_version='olive-connect/1',
            source_device_id=self.phone.local_id, target_device_id=self.desk.local_id, capability='connect.ping',
            operation='world', arguments={}, timestamp=now, expires_at=now + 60))
        self.assertEqual(self.desk._receive(raw, peer_device_id=self.phone.local_id)['error'], 'unauthenticated_transport')

    def test_malformed_provisioning_arguments_and_client_parser(self):
        channel = self.direct()
        for arguments in ({'have': 'XYZ'}, {'have': 5}, {'other': 1}, {'have': 'A' * 32}):
            now = int(time.time())
            raw = canonical(dict(request_id=str(uuid.uuid4()), protocol_version='olive-connect/1',
                source_device_id=self.phone.local_id, target_device_id=self.desk.local_id, capability='connect.ping',
                operation='world', arguments=arguments, timestamp=now, expires_at=now + 60))
            self.assertEqual(channel.request(raw)['error'], 'invalid_arguments')
        good = provision(channel, self.phone, self.desk.local_id)
        for bad in (dict(good, extra=1), dict(good, state='other'), dict(good, route_secret='zz' * 32),
                    dict(good, world_protocol='olive-world/2'), {k: v for k, v in good.items() if k != 'generation'}):
            with self.assertRaises((ConnectError, ValueError)):
                parse_provisioning(bad)

    def test_settings_file_is_validated(self):
        store = WorldSettingsStore(self.root / 'desk')
        for bad in ('[]', '{"version":1}', json.dumps(dict(version=1, enabled=True, relay_url=None,
                    peers={'x': dict(generation=1, state='active', issued_at=None, confirmed=False)}))):
            store.path.write_text(bad)
            with self.assertRaises(ConnectError):
                store.load()


class WorldTransportTests(WorldIntegrationBase):
    def test_forced_world_is_one_authenticated_logical_peer(self):
        peer = self.provisioned()
        started = time.perf_counter()
        channel = self.world_connect(peer)
        elapsed = time.perf_counter() - started
        self.assertEqual(channel.path, 'world')
        self.assertTrue(self.ping(channel)['result']['pong'])
        until(lambda: self.nd.status(self.phone.local_id)['connection'] == 'world')
        status = self.nd.status(self.phone.local_id)
        self.assertEqual((status['state'], status['encrypted']), ('online', True))
        until(lambda: self.desk.world.status()['peers'][self.phone.local_id]['connected'])
        self.assertEqual(len(self.nd.channels), 1)
        self.assertIn('connection_authenticated_world', [a['result_state'] for a in self.desk.repository.activity()])
        self.assertLess(elapsed, 5)

    def test_relay_sees_only_tls_records(self):
        peer = self.provisioned()
        channel = self.world_connect(peer)
        self.ping(channel, nonce=SECRET)
        for role in ('phone', 'desktop'):
            stream = b''.join(p for r, p in self.seen if r == role)
            self.assertNotIn(SECRET.encode(), stream)
            self.assertNotIn(self.phone.local_id.encode(), stream)
            records, whole = tls_records(stream)
            self.assertTrue(whole, 'every relay-visible byte belongs to a TLS record')
            self.assertTrue(set(kind for kind, _ in records) <= {0x14, 0x15, 0x16, 0x17})
            self.assertEqual(records[0][0], 0x16)
            self.assertIn(0x17, [kind for kind, _ in records], 'application data is TLS-encrypted')

    def test_direct_preferred_and_handover_without_duplicates(self):
        peer = self.provisioned()
        world = self.world_connect(peer)
        self.assertTrue(self.ping(world)['result']['pong'])
        before = self.executed()
        direct = self.direct()                       # Back on the LAN: Direct replaces World.
        self.assertEqual(direct.path, 'direct')
        until(lambda: self.nd.status(self.phone.local_id)['connection'] == 'local')
        until(lambda: world.stop.is_set())
        self.assertEqual(len(self.nd.channels), 1)
        with self.assertRaises(ConnectError):
            self.world_peer().connect(credentials=peer.credentials, wait=3)  # World never displaces Direct.
        self.assertEqual(self.nd.status(self.phone.local_id)['connection'], 'local')
        self.assertTrue(self.ping(direct)['result']['pong'])
        self.phone.network.disconnect(self.desk.local_id)   # Wi-Fi gone: World takes over.
        world = self.world_connect(peer)
        until(lambda: self.nd.status(self.phone.local_id)['connection'] == 'world')
        self.assertTrue(self.ping(world)['result']['pong'])
        self.assertEqual(self.executed(), before + 2, 'each request ran exactly once across handovers')

    def test_lost_world_path_recovers(self):
        peer = self.provisioned()
        channel = self.world_connect(peer)
        peer.drop()                                   # Cellular drop: no close handshake.
        until(lambda: channel.stop.is_set(), 6)
        until(lambda: self.nd.status(self.phone.local_id)['state'] != 'online', 6)
        channel = self.world_connect(peer)
        self.assertTrue(self.ping(channel)['result']['pong'])

    def test_relay_restart_recovers_with_backoff(self):
        peer = self.provisioned()
        channel = self.world_connect(peer)
        port = self.relay.port
        self.relay.stop()
        until(lambda: channel.stop.is_set(), 6)
        until(lambda: self.desk.world.status()['relay'] in ('unavailable', 'connecting'), 6)
        self.relay = RelayThread(observer=self.observe, port=port).start()
        until(lambda: self.desk.world.status()['peers'][self.phone.local_id]['route'] == 'registered', 20)
        channel = self.world_connect(peer)
        self.assertTrue(self.ping(channel)['result']['pong'])

    def test_relay_down_never_blocks_direct(self):
        self.provisioned()
        self.relay.stop()
        started = time.perf_counter()
        channel = self.direct()
        self.assertTrue(self.ping(channel)['result']['pong'])
        self.assertLess(time.perf_counter() - started, 2)
        until(lambda: self.desk.world.status()['relay'] in ('unavailable', 'connecting'), 6)
        self.relay = RelayThread(observer=self.observe).start()  # tearDown stops it again.

    def test_tampered_byte_in_transit_is_rejected(self):
        peer = self.provisioned()
        channel = self.world_connect(peer)
        before = self.executed()

        def flip(role, payload):
            if role == 'phone' and payload[:1] == b'\x17':
                self.tamper = None                    # Exactly one altered byte.
                return payload[:-1] + bytes([payload[-1] ^ 1])
            return None
        self.tamper = flip
        with self.assertRaises(ConnectError):
            self.ping(channel)
        until(lambda: channel.stop.is_set(), 6)
        self.assertEqual(self.executed(), before, 'no corrupted request reached the application')

    def test_replayed_record_is_rejected(self):
        peer = self.provisioned()
        channel = self.world_connect(peer)
        before = self.executed()

        def replay(role, payload):
            if role == 'phone' and payload[:1] == b'\x17':
                self.tamper = None
                return payload + payload              # The same encrypted record delivered twice.
            return None
        self.tamper = replay
        try:
            self.ping(channel)
        except ConnectError:
            pass
        until(lambda: channel.stop.is_set(), 6)
        self.assertLessEqual(self.executed() - before, 1, 'a replayed record never runs a request twice')

    def test_wrong_peer_and_stolen_token_never_authenticate(self):
        peer = self.provisioned()
        # Phone C (also paired with this desktop) presents phone B's route.
        other = self.service('other-phone')
        pair(other, self.desk)
        other.enable_network('127.0.0.1', discovery=False)
        thief = self.world_peer(other)
        with self.assertRaises(ConnectError):
            thief.connect(credentials=peer.credentials, wait=3)
        self.assertNotEqual(self.nd.status(other.local_id)['state'], 'online')
        # Desktop D (paired with phone B) somehow holds desktop A's route: B pins A's certificate.
        impostor = self.service('impostor-desk')
        pair(self.phone, impostor)
        impostor.enable_network('127.0.0.1', discovery=False)
        impostor.world.dev = True
        self.desk.world.set_enabled(False)            # Only the impostor waits on the route now.
        until(lambda: self.desk.world.presence.active_tasks() == {})
        route = bytes.fromhex(peer.credentials['route_id'])
        credential = wire.relay_credential(bytes.fromhex(peer.credentials['route_secret']))
        url = self.relay.url
        with patch.object(impostor.world, 'relay_url', lambda value=None: url):
            impostor.world.presence.reconcile({self.phone.local_id: (1, route, credential)})
            time.sleep(.5)
            with self.assertRaises(ConnectError):
                peer.connect(wait=3)
            impostor.world.presence.stop()
        self.assertNotEqual(impostor.network.status(self.phone.local_id)['state'], 'online')
        self.assertNotIn(self.desk.local_id, self.np.channels)

    def test_revoked_device_cannot_return_through_world(self):
        peer = self.provisioned()
        channel = self.world_connect(peer)
        self.ping(channel)
        self.desk.revoke(self.phone.local_id)
        until(lambda: channel.stop.is_set(), 6)
        self.assertEqual(self.desk.world.presence.active_tasks(), {}, 'its route is retired')
        self.assertTrue(self.desk.world.status()['peers'][self.phone.local_id]['revoked'])
        with self.assertRaises(ConnectError):
            peer.connect(wait=2)                     # The relay never finds this computer again.
        # Even if an old route registration is replayed at the relay, Connect trust decides.
        route = bytes.fromhex(peer.credentials['route_id'])
        credential = wire.relay_credential(bytes.fromhex(peer.credentials['route_secret']))
        self.desk.world.presence.reconcile({self.phone.local_id: (1, route, credential)})
        time.sleep(.5)
        with self.assertRaises(ConnectError):
            peer.connect(wait=3)
        self.desk.world.presence.stop()
        self.assertNotIn(self.phone.local_id, self.nd.channels)
        with self.assertRaises(ConnectError):
            provision(self.direct(), self.phone, self.desk.local_id)

    def test_rotation_retires_the_old_route_without_touching_trust(self):
        peer = self.provisioned()
        old = dict(peer.credentials)
        self.desk.world.rotate(self.phone.local_id)
        until(lambda: self.desk.world.status()['peers'][self.phone.local_id]['provisioned'] is False)
        with self.assertRaises(ConnectError):
            peer.connect(credentials=old, wait=2)     # The old route no longer meets this computer.
        channel = self.direct()
        result = provision(channel, self.phone, self.desk.local_id, have=old['route_id'])
        self.assertEqual(result['state'], 'provisioned')
        self.assertEqual(result['generation'], 2)
        self.assertNotEqual(result['route_id'], old['route_id'])
        peer.store(result)
        self.phone.network.disconnect(self.desk.local_id)
        channel = self.world_connect(peer)
        self.assertTrue(self.ping(channel)['result']['pong'])
        self.assertEqual(self.desk.device(self.phone.local_id)['trust_state'], 'paired')

    def test_multiple_phones_have_isolated_routes_and_revocation(self):
        second = self.service('phone-2')
        pair(second, self.desk)
        second.enable_network('127.0.0.1', discovery=False)
        a = self.provisioned()
        b = self.provisioned(second)
        self.assertNotEqual(a.credentials['route_id'], b.credentials['route_id'])
        ca, cb = self.world_connect(a), self.world_connect(b)
        self.assertTrue(self.ping(ca)['result']['pong'])
        self.assertTrue(self.ping(cb, phone=second)['result']['pong'])
        self.assertEqual({c.path for c in self.nd.channels.values()}, {'world'})
        self.assertEqual(len(self.nd.channels), 2)
        self.desk.revoke(second.local_id)
        until(lambda: cb.stop.is_set(), 6)
        self.assertFalse(ca.stop.is_set(), 'one revocation leaves the other phone untouched')
        self.assertTrue(self.ping(ca)['result']['pong'])
        self.assertEqual(set(self.desk.world.presence.active_tasks()), {self.phone.local_id})

    def test_presence_never_duplicates_loops_or_routes(self):
        self.provisioned()
        for _ in range(10):
            self.desk.world.refresh()
            self.desk.world.set_enabled(True)
        tasks = self.desk.world.presence.active_tasks()
        self.assertEqual(list(tasks), [self.phone.local_id])
        names = [t.name for t in threading.enumerate() if t.name == 'olive-connect-world']
        self.assertEqual(len(names), 1)
        self.assertEqual(self.relay.run(lambda: len(self.relay.relay.routes)), 1)
        self.desk.world.set_enabled(False)
        until(lambda: self.relay.run(lambda: len(self.relay.relay.routes)) == 0, 6)

    def test_desktop_restart_reconnects_without_reprovisioning(self):
        peer = self.provisioned()
        channel = self.world_connect(peer)
        self.desk.close()
        until(lambda: channel.stop.is_set(), 6)       # The phone sees the computer go offline.
        self.desk = self.service('desk')
        self.desk.world.dev = True
        self.nd = self.desk.enable_network('127.0.0.1', discovery=False)
        until(lambda: self.desk.world.status()['peers'][self.phone.local_id]['route'] == 'registered', 10)
        channel = self.world_connect(peer)
        self.assertTrue(self.ping(channel)['result']['pong'])

    def test_profile_copy_conflict_is_detected(self):
        peer = self.provisioned()
        route = bytes.fromhex(peer.credentials['route_id'])
        credential = wire.relay_credential(bytes.fromhex(peer.credentials['route_secret']))
        copy = self.service('copied-desk')
        copy.enable_network('127.0.0.1', discovery=False)
        copy.world.dev = True
        url = self.relay.url
        with patch('olive.connect.world.CONFLICT_REPLACEMENTS', 2), \
                patch.object(copy.world, 'relay_url', lambda value=None: url):
            copy.world.presence.reconcile({self.phone.local_id: (1, route, credential)})
            until(lambda: any(r['state'] == 'conflict' for r in list(self.desk.world.routes.values())
                              + list(copy.world.routes.values())), 20)
            copy.world.presence.stop()
        statuses = [self.desk.world.status()['relay'], copy.world.status()['relay']]
        self.assertTrue(any(s == 'conflict' for s in statuses) or
                        any(r.get('error') == 'world_identity_conflict' for r in self.desk.world.routes.values()), statuses)


if __name__ == '__main__':
    unittest.main()
