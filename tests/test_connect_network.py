"""Real loopback TLS with distinct C2 identities; no multicast requirement in CI."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from olive.connect.contracts import ConnectError, canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.network import Budget
from olive.connect.network_wire import frame, header, HEADER
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault


def pair(a, b):
    offer = a.pairing.create_offer()
    reply = b.pairing.accept_offer(offer)
    sid = json.loads(offer)['session_id']
    a.pairing.receive_reply(reply)
    def pump():
        pending = b''
        for _ in range(8):
            pending = a.pairing.exchange(sid, b.pairing.exchange(sid, pending))
    pump()
    a.pairing.confirm(sid, b.pairing.preview(sid)['comparison'])
    b.pairing.confirm(sid, a.pairing.preview(sid)['comparison'])
    pump()
    a.pairing.complete(sid)
    b.pairing.complete(sid)


def request(a, b, capability='connect.ping'):
    now = int(time.time())
    return dict(request_id=str(uuid.uuid4()), protocol_version='olive-connect/1',
        source_device_id=a.local_id, target_device_id=b.local_id, capability=capability,
        operation='ping' if capability == 'connect.ping' else 'read', arguments={},
        timestamp=now, expires_at=now + 60)


def until(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('condition timed out')


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.thread_errors = []
        self.original_hook = threading.excepthook
        threading.excepthook = self.thread_errors.append
        self.temp = tempfile.TemporaryDirectory()
        self.services = [DesktopDeviceService(Path(self.temp.name) / str(i),
            key_store=DeviceKeyStore(MemoryVault())) for i in range(3)]
        self.a, self.b, self.c = self.services
        pair(self.a, self.b)
        self.na = self.a.enable_network('127.0.0.1', discovery=False)
        self.nb = self.b.enable_network('127.0.0.1', discovery=False)

    def tearDown(self):
        for s in self.services:
            s.close()
        self.temp.cleanup()
        threading.excepthook = self.original_hook
        self.assertEqual(self.thread_errors, [], 'uncaught network worker exception')

    def connect(self):
        channel = self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port)
        until(lambda: self.nb.status(self.a.local_id)['state'] == 'online')
        return channel

    def allow(self):
        self.b.set_permission(self.a.local_id, 'connect.ping', 'allow')

    def disconnect_and_join(self):
        workers = []
        for network, peer in ((self.na, self.b.local_id), (self.nb, self.a.local_id)):
            network.disconnect(peer)
            with network.lock:
                workers.extend(network.workers)
        deadline = time.monotonic() + 4
        for worker in workers:
            worker.thread.join(max(0, deadline - time.monotonic()))
            self.assertFalse(worker.thread.is_alive(), 'channel teardown did not finish')
        self.assertFalse(self.na.workers)
        self.assertFalse(self.nb.workers)

    def test_ipv6_loopback_when_available(self):
        from olive.connect.discovery import interfaces
        if '::1' not in {i.address for i in interfaces()}:
            self.skipTest('No active IPv6 loopback interface')
        self.a.disable_network(); self.b.disable_network()
        self.na = self.a.enable_network('::1', discovery=False)
        self.nb = self.b.enable_network('::1', discovery=False)
        channel = self.na.connect(self.b.local_id, '::1', self.nb.port)
        self.allow()
        self.assertTrue(channel.request(canonical(request(self.a, self.b)))['result']['pong'])

    def test_disabled_default_and_interface_policy(self):
        self.assertIsNone(self.c.network)
        for address in ('0.0.0.0', '8.8.8.8'):
            with self.assertRaises(ConnectError):
                self.c.enable_network(address)
        with self.assertRaises(ConnectError):
            self.na.connect(self.b.local_id, '8.8.8.8', 443)

    def test_real_tls_permissions_replay_and_reconnect(self):
        channel = self.connect()
        raw = canonical(request(self.a, self.b))
        self.assertEqual(channel.request(raw)['error'], 'permission_off')
        self.b.set_permission(self.a.local_id, 'connect.ping', 'ask')
        self.assertEqual(channel.request(raw)['error'], 'confirmation_required')
        self.allow()
        first = channel.request(raw)
        self.assertTrue(first['result']['pong'])
        self.assertEqual(channel.request(raw), first)
        changed = json.loads(raw); changed['arguments'] = {'nonce': 'changed'}
        self.assertEqual(channel.request(canonical(changed))['error'], 'changed_duplicate')
        self.assertTrue(self.na.status(self.b.local_id)['encrypted'])
        self.assertGreaterEqual(self.na.status(self.b.local_id)['latency_ms'], 0)
        self.na.disconnect(self.b.local_id)
        until(lambda: not self.nb.channels)
        channel = self.connect()
        self.assertEqual(channel.request(raw), first)
        events = self.b.repository.activity()
        self.assertEqual(sum(e['result_state'] == 'completed' for e in events), 1)

    def test_revocation_closes_and_prevents_reconnect(self):
        channel = self.connect(); self.allow()
        self.b.revoke(self.a.local_id)
        until(lambda: not self.na.channels)
        self.assertIsNone(self.nb.status(self.a.local_id)['latency_ms'])
        with self.assertRaises(ConnectError):
            channel.request(canonical(request(self.a, self.b)))
        with self.assertRaises(ConnectError):
            self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port)

    def test_remote_revoke_closes_worker_but_reconnect_can_report_failed(self):
        from olive.connect.workspace import DevicesWorkspace
        channel = self.connect(); self.allow()
        self.assertTrue(channel.request(canonical(request(self.a, self.b)))['result']['pong'])
        # Choose the scheduling order explicitly, without waiting for the retry timer.
        with self.na.lock:
            self.na.targets[self.b.local_id]['next'] = float('inf')
        self.b.revoke(self.a.local_id)
        channel.thread.join(4)
        self.assertFalse(channel.thread.is_alive())
        self.assertEqual(channel.sock.fileno(), -1)
        self.assertIsNone(channel.last_latency_ms)
        workspace = DevicesWorkspace(self.a)
        self.assertEqual(workspace.snapshot()['devices'][0]['live']['state'], 'offline')
        with self.assertRaises(ConnectError):
            self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port, _automatic=True)
        with self.na.lock:
            workers = list(self.na.workers)
        for worker in workers:
            worker.thread.join(4)
            self.assertFalse(worker.thread.is_alive())
        live = workspace.snapshot()['devices'][0]['live']
        self.assertEqual(live['state'], 'failed')
        self.assertFalse(live['encrypted'])
        self.assertIsNone(live['latency_ms'])
        self.assertIn(self.b.local_id, self.na.targets)

    def test_explicit_disconnect_state_survives_worker_completion(self):
        from olive.connect.workspace import DevicesWorkspace
        from concurrent.futures import Future
        channel = self.connect()
        entered, release = threading.Event(), threading.Event()
        original = self.na.finished

        def held_finished(worker, reason):
            entered.set()
            if not release.wait(4):
                raise AssertionError('worker completion was not released')
            original(worker, reason)

        pending = Future()
        with channel.lock:
            channel.pending['test-pending'] = pending
        workspace = DevicesWorkspace(self.a)
        with patch.object(self.na, 'finished', side_effect=held_finished):
            try:
                self.na.disconnect(self.b.local_id, wait=False)
                self.assertTrue(entered.wait(3))
                self.assertEqual(workspace.snapshot()['devices'][0]['live']['state'], 'offline')
                self.assertNotIn(self.b.local_id, self.na.targets)
                with self.assertRaises(ConnectError):
                    pending.result(1)
            finally:
                release.set()
                channel.thread.join(4)
        self.assertFalse(channel.thread.is_alive())
        self.assertEqual(channel.sock.fileno(), -1)
        live = workspace.snapshot()['devices'][0]['live']
        self.assertEqual(live['state'], 'offline')
        self.assertFalse(live['encrypted'])
        self.assertIsNone(live['latency_ms'])

    def test_disconnect_returns_only_after_worker_completion(self):
        channel = self.connect()
        entered, release = threading.Event(), threading.Event()
        original = self.na.finished
        def held_finished(worker, reason):
            entered.set()
            if not release.wait(4):
                raise AssertionError('completion not released')
            return original(worker, reason)
        with patch.object(self.na, 'finished', held_finished), ThreadPoolExecutor(1) as pool:
            completion = pool.submit(self.na.disconnect, self.b.local_id)
            try:
                self.assertTrue(entered.wait(3))
                self.assertFalse(completion.done())
            finally:
                release.set()
            completion.result(4)
        self.assertFalse(channel.thread.is_alive())
        self.assertEqual(channel.sock.fileno(), -1)
        self.assertNotIn(channel, self.na.workers)
        self.assertNotIn(self.b.local_id, self.na.targets)
        self.assertEqual(self.na.status(self.b.local_id)['state'], 'offline')

    def test_disconnect_before_connect_returns_cannot_rearm_reconnect(self):
        from concurrent.futures import Future
        from olive.connect.network import Channel
        entered, release = threading.Event(), threading.Event()
        original = Future.result

        def held_result(future, *args, **kwargs):
            result = original(future, *args, **kwargs)
            if isinstance(result, Channel):
                entered.set()
                if not release.wait(4):
                    raise AssertionError('connect result was not released')
            return result

        with patch.object(Future, 'result', held_result), ThreadPoolExecutor(1) as pool:
            attempt = pool.submit(self.na.connect, self.b.local_id, '127.0.0.1', self.nb.port, retries=1)
            try:
                self.assertTrue(entered.wait(3))
                self.na.disconnect(self.b.local_id)
            finally:
                release.set()
            with self.assertRaises(ConnectError):
                attempt.result(4)
        self.disconnect_and_join()
        self.assertNotIn(self.b.local_id, self.na.targets)
        self.assertEqual(self.na.status(self.b.local_id)['state'], 'offline')

    def test_channel_close_snapshot_and_disable_join(self):
        from olive.connect.workspace import DevicesWorkspace
        channel = self.connect(); self.allow()
        self.assertTrue(channel.request(canonical(request(self.a, self.b)))['result']['pong'])
        with self.na.lock:
            self.na.targets[self.b.local_id]['next'] = float('inf')
        channel.close()
        live = DevicesWorkspace(self.a).snapshot()['devices'][0]['live']
        self.assertEqual(live['state'], 'offline')
        self.assertFalse(live['encrypted'])
        self.assertIsNone(live['latency_ms'])
        with self.assertRaises(ConnectError):
            channel.request(canonical(request(self.a, self.b)))
        self.a.disable_network()
        self.assertFalse(channel.thread.is_alive())
        self.assertEqual(channel.sock.fileno(), -1)
        self.assertFalse(self.na.thread.is_alive())
        self.assertFalse(self.na.reconnector.is_alive())
        self.assertFalse(self.na.workers)
        self.assertIsNone(self.a.network)

    def test_unknown_and_wrong_endpoint_never_online(self):
        nc = self.c.enable_network('127.0.0.1', discovery=False)
        with self.assertRaises(ConnectError):
            self.na.connect(self.b.local_id, '127.0.0.1', nc.port)
        self.assertFalse(self.na.status(self.b.local_id)['encrypted'])
        self.assertEqual(self.c.paired_devices(), [])

    def test_source_binding_and_no_remote_approval_or_tools(self):
        channel = self.connect(); self.allow()
        # Send from the channel's worker; bypass local outbound schema checks to model a hostile peer.
        raw = request(self.a, self.b)
        raw['source_device_id'] = self.c.local_id
        from concurrent.futures import Future
        future = Future()
        with channel.lock:
            channel.pending[raw['request_id']] = future
        channel.writes.put_nowait(frame(1, canonical(raw)))
        self.assertEqual(future.result(3)['error'], 'source_mismatch')
        with channel.lock:
            channel.pending.clear()
        for capability in ('terminal', 'studio.run', 'models.remote', 'filesystem.full',
                           'apps.launch', 'desktop_control', 'software.install'):
            self.b.set_permission(self.a.local_id, capability, 'allow')
            self.assertEqual(channel.request(canonical(request(self.a, self.b, capability)))['error'],
                             'capability_unavailable')
        raw = request(self.a, self.b); raw['arguments'] = {'approved': True}
        self.assertEqual(channel.request(canonical(raw))['error'], 'invalid_arguments')

    def test_permission_changes_between_claim_and_execution(self):
        from contextlib import contextmanager
        channel = self.connect(); self.allow()
        raw = request(self.a, self.b)
        original = self.b.repository.transaction
        changed = []
        @contextmanager
        def transaction(**kwargs):
            with original(**kwargs) as db:
                yield db
                claim = db.execute('SELECT response FROM requests WHERE request_id=?',
                                   (raw['request_id'],)).fetchone()
            if claim is not None and claim[0] is None and not changed:
                changed.append(True)
                self.b.set_permission(self.a.local_id, 'connect.ping', 'deny')
        with patch.object(self.b.repository, 'transaction', transaction), \
             patch.object(self.b, '_execute') as execute:
            result = channel.request(canonical(raw))
            execute.assert_not_called()
        self.assertEqual(result['error'], 'permission_off')
        self.assertEqual(self.b.permission(self.a.local_id, 'connect.ping').value, 'deny')

    def test_collision(self):
        with ThreadPoolExecutor(2) as pool:
            left = pool.submit(self.na.connect, self.b.local_id, '127.0.0.1', self.nb.port)
            right = pool.submit(self.nb.connect, self.a.local_id, '127.0.0.1', self.na.port)
            left.result(); right.result()
        until(lambda: len(self.na.workers) == len(self.nb.workers) == 1)
        self.assertEqual(self.na.channels[self.b.local_id].outbound, self.a.local_id < self.b.local_id)
        self.allow()
        self.assertTrue(self.na.channels[self.b.local_id].request(canonical(request(self.a, self.b)))['result']['pong'])

    def test_listener_collision_and_connection_ceiling(self):
        with self.assertRaises(OSError):
            self.c.enable_network('127.0.0.1', port=self.nb.port, discovery=False)
        self.assertIsNone(self.c.network)
        sockets = []
        try:
            for _ in range(10):
                sockets.append(socket.create_connection(('127.0.0.1', self.nb.port)))
            until(lambda: len(self.nb.workers) == 8)
            self.assertLessEqual(len(self.nb.workers), 8)
        finally:
            for sock in sockets:
                sock.close()

    def test_revocation_between_claim_and_execution(self):
        from contextlib import contextmanager
        channel = self.connect(); self.allow()
        raw = request(self.a, self.b)
        original = self.b.repository.transaction
        revoked = []
        @contextmanager
        def transaction(**kwargs):
            with original(**kwargs) as db:
                yield db
                claim = db.execute('SELECT response FROM requests WHERE request_id=?',
                                   (raw['request_id'],)).fetchone()
            # The durable claim has committed; revoke before execution starts.
            if claim is not None and claim[0] is None and not revoked:
                revoked.append(True)
                self.b.revoke(self.a.local_id)
        with patch.object(self.b.repository, 'transaction', transaction), \
             patch.object(self.b, '_execute') as execute:
            with self.assertRaises(ConnectError):
                channel.request(canonical(raw))
            until(lambda: not self.nb.workers)
            execute.assert_not_called()
        self.assertEqual(self.b.device(self.a.local_id)['trust_state'], 'revoked')

    def test_malformed_tls_and_handshake_timeout(self):
        with patch('olive.connect.network.HANDSHAKE_TIMEOUT', .15):
            sock = socket.create_connection(('127.0.0.1', self.nb.port))
            try:
                until(lambda: len(self.nb.workers) == 1)
                until(lambda: not self.nb.workers)
            finally:
                sock.close()
        sock = socket.create_connection(('127.0.0.1', self.nb.port))
        sock.sendall(b'not TLS')
        sock.close()
        until(lambda: not self.nb.workers)
        self.assertFalse(self.nb.channels)

    def test_slow_frame_and_oversize_close(self):
        with patch('olive.connect.network.FRAME_TIMEOUT', .15):
            channel = self.connect()
            channel.writes.put_nowait(b'\x00')
            until(lambda: not self.nb.channels)
        until(lambda: not self.na.channels)
        channel = self.connect()
        channel.writes.put_nowait(HEADER.pack(2**32-1, 1, 1))
        until(lambda: not self.nb.channels)

    def test_rate_limit_across_reconnect(self):
        channel = self.connect(); self.allow()
        with self.nb.lock:
            self.nb.rates[self.a.local_id] = Budget(2, 60)
        for _ in range(2):
            channel.request(canonical(request(self.a, self.b)))
        with self.assertRaises(ConnectError):
            channel.request(canonical(request(self.a, self.b)))
        until(lambda: not self.nb.channels)
        until(lambda: not self.na.channels)
        channel = self.connect()
        with self.assertRaises(ConnectError):
            channel.request(canonical(request(self.a, self.b)))

    def test_private_exception_and_status(self):
        channel = self.connect(); self.allow()
        with patch.object(self.b, '_execute', side_effect=RuntimeError('/private/secret credential')):
            result = channel.request(canonical(request(self.a, self.b)))
        self.assertEqual(result['error'], 'internal_error')
        self.assertNotIn('secret', json.dumps(self.b.repository.activity()))
        self.b.set_permission(self.a.local_id, 'device.status', 'allow')
        status = channel.request(canonical(request(self.a, self.b, 'device.status')))['result']
        self.assertEqual(status, dict(core_available=True, encrypted=True, transport='local'))

    def test_automatic_reconnect_fresh_channel(self):
        channel = self.connect(); self.allow()
        channel.close()  # Ordinary network loss; retain explicit reconnect intent.
        until(lambda: self.na.channels.get(self.b.local_id) not in (None, channel), timeout=5)
        replacement = self.na.channels[self.b.local_id]
        self.assertIsNot(replacement.tls, channel.tls)
        self.assertTrue(replacement.request(canonical(request(self.a, self.b)))['result']['pong'])

    def test_expired_certificate_rejected_without_replacement(self):
        from olive.connect.identity import public_identity
        from olive.connect.network_wire import require_current, tls_context
        public = self.b.cryptographic_identity()
        key = self.b.identities.key_store.load(public)
        expired = public_identity(self.b.local_id, key, int(time.time()) - 3651 * 86400)
        with self.assertRaisesRegex(ConnectError, 'certificate_expired'):
            require_current(expired)
        with self.a.repository.transaction() as db:
            record = self.a.repository.get(db, self.b.local_id)
            record['public_identity'] = expired
            self.a.repository.put(db, record)
        with self.assertRaisesRegex(ConnectError, 'certificate_expired'):
            tls_context(self.a, self.b.local_id)
        self.assertEqual(self.a.device(self.b.local_id)['public_identity'], expired)

    def test_same_uuid_changed_key_and_same_display_name_rejected(self):
        from olive.connect.identity import public_identity
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        public = self.b.cryptographic_identity()
        changed = public_identity(self.b.local_id, Ed25519PrivateKey.generate(), int(time.time()))
        with self.assertRaisesRegex(ConnectError, 'identity_mismatch'):
            self.a.require_paired_identity(changed)
        self.c.rename(self.c.local_id, self.b.this_device()['display_name'])
        nc = self.c.enable_network('127.0.0.1', discovery=False)
        with self.assertRaises(ConnectError):
            self.na.connect(self.b.local_id, '127.0.0.1', nc.port)
        self.assertEqual(self.a.device(self.b.local_id)['public_identity'], public)

    def test_pending_and_write_limits(self):
        from concurrent.futures import Future
        channel = self.connect()
        with channel.lock:
            channel.pending = {str(uuid.uuid4()): Future() for _ in range(8)}
        with self.assertRaisesRegex(ConnectError, 'backpressure'):
            channel.request(canonical(request(self.a, self.b)))
        self.assertEqual(channel.writes.maxsize, 8)

    def test_live_expired_client_certificate_rejected_by_openssl(self):
        from olive.connect.identity import public_identity
        from olive.connect.tls_identity import identity_context
        from olive.connect.network_wire import certificate_bytes, tls_context
        public = self.a.cryptographic_identity()
        key = self.a.identities.key_store.load(public)
        expired = public_identity(self.a.local_id, key, int(time.time()) - 3651 * 86400)
        with self.b.repository.transaction() as db:
            record = self.b.repository.get(db, self.a.local_id)
            record['public_identity'] = expired
            self.b.repository.put(db, record)
        remote = self.b.cryptographic_identity()
        def malicious(service, expected=None, **kwargs):
            if service is self.a:
                return identity_context(key, expired, [remote]), {certificate_bytes(remote): remote}
            return tls_context(service, expected, **kwargs)
        with patch('olive.connect.network.tls_context', side_effect=malicious):
            with self.assertRaises(ConnectError):
                self.connect()
        self.assertFalse(self.nb.status(self.a.local_id)['encrypted'])

    def test_malformed_request_unknown_capability_and_message_type(self):
        for payload in (b'{', canonical(dict(request(self.a, self.b), capability='arbitrary.tool'))):
            channel = self.connect()
            # This test owns each reconnect; automatic reconnect is tested separately.
            with self.na.lock:
                self.na.targets.pop(self.b.local_id, None)
            with patch.object(self.b, '_execute') as execute:
                channel.writes.put_nowait(frame(1, payload))
                until(lambda: not self.na.channels)
                execute.assert_not_called()
            self.disconnect_and_join()
        channel = self.connect()
        channel.writes.put_nowait(HEADER.pack(0, 1, 99))
        until(lambda: not self.nb.channels)

    def test_device_reads_during_previous_channel_closing_audit(self):
        channel = self.connect()
        entered, release = threading.Event(), threading.Event()
        original = self.a.repository.audit

        def held_audit(db, peer, request_id, capability, now, state):
            original(db, peer, request_id, capability, now, state)
            if state == 'connection_closed':
                entered.set()
                if not release.wait(4):
                    raise AssertionError('closing audit was not released')

        with patch.object(self.a.repository, 'audit', side_effect=held_audit):
            try:
                self.na.disconnect(self.b.local_id, wait=False)
                self.assertTrue(entered.wait(3))
                self.assertFalse(self.na.channels)
                self.assertIn(channel, self.na.workers)
                self.assertTrue(channel.thread.is_alive())
                # The old worker still owns a real SQLite write transaction.
                # These are snapshots, not request execution authorization.
                record = self.a.device(self.b.local_id, timeout=.25)
                self.assertEqual(record['trust_state'], 'paired')
                self.a.require_paired_identity(record['public_identity'], timeout=.25)
                self.assertEqual(len(self.a.paired_devices(timeout=.25)), 1)
            finally:
                release.set()
                self.disconnect_and_join()
        self.assertIsNot(self.connect(), channel)

    def test_device_read_exclusive_lock_remains_bounded(self):
        with closing(sqlite3.connect(self.a.repository.path)) as holder:
            holder.execute('BEGIN EXCLUSIVE')
            started = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError) as failure:
                self.a.device(self.b.local_id, timeout=.25)
            self.assertEqual(failure.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
            self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(self.a.device(self.b.local_id)['trust_state'], 'paired')

    def test_idle_and_request_timeouts_clear_authority(self):
        with patch('olive.connect.network.IDLE_TIMEOUT', .15):
            channel = self.connect()
            until(lambda: not self.nb.channels)
        self.na.disconnect(self.b.local_id)
        until(lambda: not self.na.workers)
        channel = self.connect(); self.allow()
        original = self.b._execute
        def slow(req):
            time.sleep(.1)
            return original(req)
        with patch.object(self.b, '_execute', side_effect=slow):
            with self.assertRaisesRegex(ConnectError, 'request_timeout'):
                channel.request(canonical(request(self.a, self.b)), timeout=.02)
        self.assertTrue(channel.stop.is_set())

    def test_write_deadline_with_nonreading_peer(self):
        from OpenSSL import SSL
        from olive.connect.network import Channel
        from types import SimpleNamespace
        # OpenSSL WantWrite boundary models a full kernel socket buffer.
        left, right = socket.socketpair()
        channel = Channel(self.na, left)
        channel.tls = SimpleNamespace(send=lambda raw: (_ for _ in ()).throw(SSL.WantWriteError()))
        try:
            with patch('olive.connect.network.WRITE_TIMEOUT', .05):
                with self.assertRaisesRegex(ConnectError, 'connection_timeout'):
                    channel.write(b'x')
        finally:
            channel.close(); left.close(); right.close()

    def test_live_same_uuid_different_key_rejected(self):
        from olive.connect.identity import public_identity
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        changed = public_identity(self.b.local_id, key, int(time.time()))
        with patch.object(self.c, 'cryptographic_identity', return_value=changed), \
             patch.object(self.c.identities.key_store, 'load', return_value=key):
            nc = self.c.enable_network('127.0.0.1', discovery=False)
            with self.assertRaises(ConnectError):
                self.na.connect(self.b.local_id, '127.0.0.1', nc.port)
        self.assertFalse(self.na.status(self.b.local_id)['encrypted'])

    def test_connection_timeout_and_unknown_protocol(self):
        with patch('socket.socket.connect', side_effect=socket.timeout):
            with self.assertRaises(ConnectError):
                self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port)
        until(lambda: not self.na.workers)
        channel = self.connect()
        channel.writes.put_nowait(HEADER.pack(0, 2, 1))
        until(lambda: not self.nb.channels)

    def test_shutdown_owns_connect_in_progress(self):
        entered = threading.Event()
        def pending(sock, endpoint):
            entered.set()
            time.sleep(.1)
            raise socket.timeout()
        with patch('socket.socket.connect', pending), ThreadPoolExecutor(1) as pool:
            attempt = pool.submit(self.na.connect, self.b.local_id, '127.0.0.1', self.nb.port)
            self.assertTrue(entered.wait(2))
            workers = list(self.na.workers)
            self.a.disable_network()
            with self.assertRaises(ConnectError):
                attempt.result(2)
            self.assertTrue(all(not worker.thread.is_alive() for worker in workers))
            self.assertTrue(all(worker.sock.fileno() == -1 for worker in workers))

    def test_shutdown_workers_sockets(self):
        channel = self.connect()
        workers = list(self.na.workers)
        self.a.disable_network()
        self.assertFalse(self.na.thread.is_alive())
        self.assertTrue(all(not c.thread.is_alive() and c.sock.fileno() == -1 for c in workers))
        self.assertEqual(self.na.listener.fileno(), -1)
        with self.assertRaises(ConnectError):
            channel.request(canonical(request(self.a, self.b)))


class WireTests(unittest.TestCase):
    def test_header_bounds(self):
        for values in ((16385, 1, 1), (0, 2, 1), (0, 1, 9), (1, 1, 3)):
            with self.assertRaises(ConnectError):
                header(HEADER.pack(*values))
        with self.assertRaises(ConnectError):
            frame(1, bytes(16385))

    def test_budget_clock(self):
        now = [0]
        budget = Budget(2, 60, lambda: now[0])
        self.assertTrue(budget.take()); self.assertTrue(budget.take())
        self.assertFalse(budget.take())
        now[0] = 60
        self.assertTrue(budget.take())


class DiscoveryTests(unittest.TestCase):
    def test_spoofed_metadata_never_has_authority(self):
        import threading
        from types import SimpleNamespace
        from olive.connect.discovery import LocalDiscovery, Interface, SERVICE
        directory = LocalDiscovery.__new__(LocalDiscovery)
        directory.interface = Interface('fixture', '127.0.0.1', '127.0.0.0/8')
        directory.lock = threading.Lock(); directory.entries = {}; directory.closed = False
        directory.name = 'ours.' + SERVICE
        info = SimpleNamespace(properties={b'product': b'OLIVE', b'version': b'1'},
                               port=12345, parsed_addresses=lambda: ['127.0.0.2'])
        zc = SimpleNamespace(get_service_info=lambda *a, **kw: info)
        spoof = str(uuid.uuid4()) + '.' + SERVICE
        directory.add_service(zc, SERVICE, spoof)
        entry = directory.nearby()[0]
        self.assertEqual(entry['state'], 'discovered')
        self.assertEqual(set(entry), {'instance', 'address', 'port', 'state', 'seen'})
        for field in (b'device_id', b'display_name', b'permissions', b'hostname'):
            info.properties[field] = b'spoof'
            directory.add_service(zc, SERVICE, field.decode() + '.' + SERVICE)
            info.properties.pop(field)
        self.assertEqual(len(directory.nearby()), 1)
        info.parsed_addresses = lambda: ['8.8.8.8']
        directory.add_service(zc, SERVICE, 'public.' + SERVICE)
        self.assertEqual(len(directory.nearby()), 1)
        info.parsed_addresses = lambda: ['127.0.0.2']
        for i in range(100):
            directory.add_service(zc, SERVICE, str(i) + '.' + SERVICE)
        self.assertEqual(len(directory.nearby()), 64)

    def test_virtual_and_public_interfaces_filtered(self):
        from types import SimpleNamespace
        from olive.connect.discovery import interfaces
        entry = lambda address: SimpleNamespace(family=socket.AF_INET, address=address, netmask='255.255.255.0')
        addresses = {'eth0': [entry('192.168.1.3')], 'tun0': [entry('10.1.1.2')],
                     'docker0': [entry('172.17.0.1')], 'public': [entry('8.8.8.8')]}
        with patch('psutil.net_if_stats', return_value={n: SimpleNamespace(isup=True) for n in addresses}), \
             patch('psutil.net_if_addrs', return_value=addresses):
            self.assertEqual([i.name for i in interfaces()], ['eth0'])
