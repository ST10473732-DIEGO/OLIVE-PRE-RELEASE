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

    def test_disconnect_waits_for_peer_retirement_before_immediate_reconnect(self):
        channel = self.connect(); self.allow()
        remote = self.nb.channels[self.a.local_id]
        local_retired, remote_retiring, release = (threading.Event() for _ in range(3))
        local_finished, remote_finished = self.na.finished, self.nb.finished

        def finished_local(worker, reason):
            local_finished(worker, reason)
            if worker is channel:
                local_retired.set()

        def held_remote(worker, reason):
            if worker is remote:
                remote_retiring.set()
                if not release.wait(4):
                    raise AssertionError('peer retirement was not released')
            remote_finished(worker, reason)

        with patch.object(self.na, 'finished', finished_local), \
             patch.object(self.nb, 'finished', held_remote), ThreadPoolExecutor(1) as pool:
            completion = pool.submit(self.na.disconnect, self.b.local_id)
            try:
                self.assertTrue(local_retired.wait(3))
                self.assertTrue(remote_retiring.wait(3))
                self.assertFalse(completion.done())
                self.assertNotEqual(channel.sock.fileno(), -1)
                self.assertNotIn(self.b.local_id, self.na.channels)
                with self.assertRaisesRegex(ConnectError, 'connection_closed'):
                    channel.request(canonical(request(self.a, self.b)))
            finally:
                release.set()
            completion.result(4)
        # No peer-map polling, sleep or reconnect retry between return and connect.
        replacement = self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port)
        self.assertTrue(replacement.request(canonical(request(self.a, self.b)))['result']['pong'])
        self.assertIsNot(replacement, channel)
        remote.thread.join(4)
        self.assertFalse(remote.thread.is_alive())
        self.assertFalse(channel.thread.is_alive())
        self.assertEqual(channel.sock.fileno(), -1)
        self.assertEqual(remote.sock.fileno(), -1)

    def test_disconnect_peer_retirement_timeout_is_not_success(self):
        channel = self.connect()
        remote = self.nb.channels[self.a.local_id]
        entered, release = threading.Event(), threading.Event()
        finished = self.nb.finished

        def held_remote(worker, reason):
            if worker is remote:
                entered.set()
                if not release.wait(4):
                    raise AssertionError('peer retirement was not released')
            finished(worker, reason)

        with patch.object(self.nb, 'finished', held_remote), \
             patch('olive.connect.network.WRITE_TIMEOUT', .1), ThreadPoolExecutor(1) as pool:
            completion = pool.submit(self.na.disconnect, self.b.local_id)
            try:
                self.assertTrue(entered.wait(3))
                with self.assertRaisesRegex(ConnectError, 'disconnect_timeout'):
                    completion.result(4)
                self.assertFalse(channel.thread.is_alive())
                self.assertEqual(channel.sock.fileno(), -1)
                self.assertNotIn(self.b.local_id, self.na.targets)
            finally:
                release.set()
        remote.thread.join(4)

    def disconnect_after_peer_eof(self, *, malformed):
        from OpenSSL import SSL
        channel = self.connect()
        remote = self.nb.channels[self.a.local_id]
        with self.na.lock:
            self.na.targets.pop(self.b.local_id, None)
        eof, release, disconnecting = (threading.Event() for _ in range(3))
        receive, invalidate = remote.tls.recv, self.b.files.invalidate

        def observed_eof():
            eof.set()
            if not release.wait(4):
                raise AssertionError('observed peer EOF was not released')

        def held_receive(*args, **kwargs):
            try:
                data = receive(*args, **kwargs)
            except (SSL.ZeroReturnError, SSL.SysCallError):
                observed_eof()
                raise
            if not data:
                observed_eof()
            return data

        def entered_disconnect(*args, **kwargs):
            result = invalidate(*args, **kwargs)
            if threading.current_thread() is not remote.thread:
                disconnecting.set()
            return result

        with patch.object(remote.tls, 'recv', held_receive), \
             patch.object(self.b.files, 'invalidate', entered_disconnect), ThreadPoolExecutor(1) as pool:
            try:
                if malformed:
                    channel.writes.put_nowait(frame(1, b'{'))
                else:
                    channel.close()
                self.assertTrue(eof.wait(3))
                channel.thread.join(4)
                self.assertFalse(channel.thread.is_alive())
                self.assertEqual(channel.sock.fileno(), -1)
                # The exact peer transport is gone, but its TLS EOF has not yet
                # reached run()'s exception/finally transition on this worker.
                self.assertFalse(remote.stop.is_set())
                self.assertIs(self.nb.channels.get(self.a.local_id), remote)
                completion = pool.submit(self.nb.disconnect, self.a.local_id)
                self.assertTrue(disconnecting.wait(3))
                self.assertFalse(completion.done())
                self.assertTrue(remote.graceful_disconnect)
                release.set()
                completion.result(4)
            finally:
                release.set()
        self.assertTrue(remote.peer_closed)
        self.assertFalse(remote.thread.is_alive())
        self.assertEqual(remote.sock.fileno(), -1)
        # Retired workers and repeated cleanup must not require a new EOF edge.
        for _ in range(2):
            self.disconnect_and_join()
        self.assertFalse(self.na.targets)
        self.assertFalse(self.nb.targets)
        self.allow()
        replacement = self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port)
        self.assertTrue(replacement.request(canonical(request(self.a, self.b)))['result']['pong'])

    def test_disconnect_after_malformed_protocol_observed_eof_is_idempotent(self):
        self.disconnect_after_peer_eof(malformed=True)

    def test_disconnect_after_remote_close_observed_eof_is_idempotent(self):
        self.disconnect_after_peer_eof(malformed=False)

    def test_repeated_disconnect_joins_same_live_retirement(self):
        channel = self.connect()
        remote = self.nb.channels[self.a.local_id]
        entered, release, both_callers = (threading.Event() for _ in range(3))
        finished, invalidate = self.nb.finished, self.a.files.invalidate
        calls = []

        def held_finished(worker, reason):
            if worker is remote:
                entered.set()
                if not release.wait(4):
                    raise AssertionError('peer retirement was not released')
            finished(worker, reason)

        def invalidated(*args, **kwargs):
            result = invalidate(*args, **kwargs)
            calls.append(True)  # Both callers hold files.lock here.
            if len(calls) == 2:
                both_callers.set()
            return result

        with patch.object(self.nb, 'finished', held_finished), \
             patch.object(self.a.files, 'invalidate', invalidated), \
             patch.object(channel, 'close', wraps=channel.close) as close, ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.na.disconnect, self.b.local_id)
            try:
                self.assertTrue(entered.wait(3))
                second = pool.submit(self.na.disconnect, self.b.local_id)
                self.assertTrue(both_callers.wait(3))
                close.assert_not_called()
                self.assertFalse(first.done())
                self.assertFalse(second.done())
            finally:
                release.set()
            first.result(4); second.result(4)
        self.assertTrue(channel.peer_closed)
        self.assertFalse(channel.thread.is_alive())
        self.assertEqual(channel.sock.fileno(), -1)

    def test_old_worker_retirement_cannot_clear_replacement_or_share_eof(self):
        channel = self.connect(); self.allow()
        remote = self.nb.channels[self.a.local_id]
        with self.na.lock:
            self.na.targets.pop(self.b.local_id, None)
        entered, release = threading.Event(), threading.Event()
        finished = self.na.finished

        def held_finished(worker, reason):
            if worker is channel:
                entered.set()
                if not release.wait(4):
                    raise AssertionError('old worker retirement was not released')
            finished(worker, reason)

        with patch.object(self.na, 'finished', held_finished):
            try:
                remote.close()
                remote.thread.join(4)
                self.assertFalse(remote.thread.is_alive())
                self.assertTrue(entered.wait(3))
                replacement = self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port)
                self.assertIsNot(replacement, channel)
                self.assertTrue(channel.peer_closed)
                self.assertFalse(replacement.peer_closed)
            finally:
                release.set()
                channel.thread.join(4)
        self.assertFalse(channel.thread.is_alive())
        self.assertIs(self.na.channels[self.b.local_id], replacement)
        self.assertEqual(self.na.status(self.b.local_id)['state'], 'online')
        self.assertFalse(replacement.peer_closed)
        self.assertTrue(replacement.request(canonical(request(self.a, self.b)))['result']['pong'])

    def test_equal_socket_handles_do_not_share_channel_retirement(self):
        from types import SimpleNamespace
        from olive.connect.network import Channel
        old_socket = SimpleNamespace(fileno=lambda: 42, shutdown=lambda _: None)
        new_socket = SimpleNamespace(fileno=lambda: 42, shutdown=lambda _: None)
        old = Channel(self.na, old_socket, self.b.local_id)
        replacement = Channel(self.na, new_socket, self.b.local_id)
        old.peer = replacement.peer = self.b.local_id
        old.peer_closed = True
        old.close()
        with patch.dict(self.na.channels, {self.b.local_id: replacement}):
            self.na.finished(old, 'connection_closed')
            self.assertIs(self.na.channels[self.b.local_id], replacement)
            self.assertFalse(replacement.stop.is_set())
            self.assertFalse(replacement.peer_closed)
            self.assertIsNone(replacement.debug_snapshot()['terminal'])
            self.assertNotEqual(old.generation, replacement.generation)
            with self.assertRaises(AttributeError):
                replacement.generation = old.generation

    def test_close_diagnostics_are_bounded_private_and_preserve_first_cause(self):
        from OpenSSL import SSL
        from olive.connect.network_diagnostics import ChannelDiagnostics
        diagnostics = ChannelDiagnostics()
        diagnostics.at('dispatch')
        diagnostics.failed(ConnectError('private-request-content'))
        diagnostics.closed('shutdown')
        value = diagnostics.snapshot()
        self.assertEqual(value['terminal'], dict(category='protocol_violation',
            phase='dispatch', error_kind='connect', error_code=None))
        self.assertNotIn('private-request-content', json.dumps(value))
        value['terminal']['category'] = 'changed-copy'
        self.assertEqual(diagnostics.snapshot()['terminal']['category'], 'protocol_violation')
        tls = ChannelDiagnostics()
        tls.at('read')
        tls.failed(SSL.WantWriteError('private-tls-context'))
        self.assertEqual(tls.snapshot()['terminal'], dict(category='tls_failure',
            phase='read', error_kind='tls_want_write', error_code=None))
        self.assertNotIn('private-tls-context', json.dumps(tls.snapshot()))
        import errno
        from olive.connect.storage_diagnostics import details, storage_operation
        denied = PermissionError(errno.EACCES, 'private-checkpoint-path')
        denied.winerror = 5
        try:
            with storage_operation('checkpoint', 'write'):
                raise denied
        except PermissionError:
            value = details(denied)
        self.assertEqual(value, dict(component='checkpoint', operation='write', namespace='win32',
            exception_class='PermissionError', sqlite_errorcode=None, sqlite_errorname=None,
            errno=errno.EACCES, winerror=5))
        self.assertNotIn('private-checkpoint-path', json.dumps(value))
        for _ in range(10):
            diagnostics.storage_failed(denied)
        self.assertEqual(len(diagnostics.snapshot()['storage_failures']), 4)
        channel = self.connect()
        self.na.disconnect(self.b.local_id)
        self.assertEqual(channel.debug_snapshot()['terminal']['category'], 'local_disconnect')
        snapshot = self.na.debug_snapshot(self.b.local_id)
        self.assertTrue(snapshot['retired'][-1]['retired'])
        self.assertEqual(snapshot['retired'][-1]['generation'], channel.generation)
        self.assertEqual(self.na.retired.maxlen, 16)
        self.assertNotIn('generation', json.dumps(self.na.status(self.b.local_id)))

    def test_audit_failure_does_not_close_authenticated_channel(self):
        channel = self.connect(); self.allow()
        with patch.object(self.a.repository, 'audit', side_effect=OSError('private-storage-path')):
            with self.assertLogs('olive.connect.network', level='WARNING') as logs:
                self.na.audit(self.b.local_id, 'connection_authenticated')
        self.assertEqual(logs.output, ['WARNING:olive.connect.network:Connect audit unavailable'])
        self.assertGreaterEqual(self.na.debug_snapshot(self.b.local_id)['audit_failures'], 1)
        self.assertTrue(channel.request(canonical(request(self.a, self.b)))['result']['pong'])
        self.assertFalse(channel.stop.is_set())
        self.assertIsNone(channel.debug_snapshot()['terminal'])

    def test_diagnostics_identify_failed_authority_read_without_exposing_storage(self):
        channel = self.connect()
        with self.na.lock:
            self.na.targets.pop(self.b.local_id, None)
        entered, release, failed = (threading.Event() for _ in range(3))
        require = self.a.require_paired_identity
        finished = self.na.finished

        def held_authority(*args, **kwargs):
            if threading.current_thread() is channel.thread:
                entered.set()
                if not release.wait(4):
                    raise AssertionError('authority read was not released')
            return require(*args, **kwargs)

        def observed_finished(worker, reason):
            if worker is channel:
                failed.set()
            finished(worker, reason)

        with patch.object(self.a, 'require_paired_identity', held_authority), \
             patch.object(self.na, 'finished', observed_finished):
            try:
                self.assertTrue(entered.wait(3))
                with closing(sqlite3.connect(self.a.repository.path)) as db:
                    db.execute('BEGIN EXCLUSIVE')
                    release.set()
                    self.assertTrue(failed.wait(3))
                    terminal = channel.debug_snapshot()['terminal']
                    storage = terminal.pop('storage')
                    self.assertEqual(terminal, dict(category='storage_unavailable',
                        phase='authority', error_kind='storage', error_code=sqlite3.SQLITE_BUSY))
                    self.assertEqual(storage, dict(component='device_repository', operation='read',
                        namespace='sqlite', exception_class='sqlite3.OperationalError', sqlite_errorcode=5,
                        sqlite_errorname='SQLITE_BUSY', errno=None, winerror=None))
                    self.assertTrue(channel.stop.is_set())
                    self.assertNotIn(str(self.a.repository.path), json.dumps(terminal))
                    db.rollback()
            finally:
                release.set()
                channel.thread.join(4)
        self.assertFalse(channel.thread.is_alive())
        with self.assertRaisesRegex(ConnectError, 'connection_closed'):
            channel.check()

    def test_dispatch_storage_failure_retires_while_activity_writer_is_held(self):
        channel = self.connect(); self.allow()
        remote = self.nb.channels[self.a.local_id]
        with self.na.lock:
            self.na.targets.pop(self.b.local_id, None)
        # The exact same reserved writer that previously stranded C3 in
        # files.invalidate()'s ten-second transaction remains held throughout.
        with self.b.repository.transaction(component='activity_repository') as db, ThreadPoolExecutor(1) as pool:
            self.b.repository.audit(db, None, None, None, 0, 'request_denied')
            result = pool.submit(channel.request, canonical(request(self.a, self.b)))
            remote.thread.join(3)
            self.assertFalse(remote.thread.is_alive(), remote.debug_snapshot())
            self.assertEqual(remote.sock.fileno(), -1)
            terminal = remote.debug_snapshot()['terminal']
            self.assertEqual(terminal['category'], 'storage_unavailable')
            self.assertEqual(terminal['storage']['sqlite_errorname'], 'SQLITE_BUSY')
            self.assertIn(self.a.local_id, self.b.files.invalidation_pending)
            self.nb.close()
            with self.assertRaisesRegex(ConnectError, 'connection_closed'):
                result.result(3)
        self.b.files._cleanup_pass()
        self.assertFalse(self.b.files.invalidation_pending)

    def test_pinned_authority_snapshot_avoids_nested_reader_and_is_thread_scoped(self):
        from types import SimpleNamespace
        from olive.connect.network import Channel
        channel = Channel(self.na, SimpleNamespace(fileno=lambda: 42), self.b.local_id)
        channel.public = self.a.device(self.b.local_id)['public_identity']
        with closing(sqlite3.connect(self.a.repository.path, timeout=0)) as writer:
            with self.a.repository.transaction(read_only=True) as reader:
                self.a.repository.get(reader, self.b.local_id)  # Hold SHARED.
                writer.execute('BEGIN IMMEDIATE')
                self.a.repository.audit(writer, None, None, None, 0, 'request_denied')
                with self.assertRaises(sqlite3.OperationalError) as busy:
                    writer.commit()  # Retains PENDING until reader retires.
                self.assertEqual(busy.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
                with channel.authority_snapshot(reader), ThreadPoolExecutor(1) as pool:
                    channel.check()  # Existing pinned reader remains usable.
                    with self.assertRaises(sqlite3.OperationalError):
                        pool.submit(channel.check).result(3)  # No cross-thread reuse.
                self.assertIsNone(channel.authority.db)
            writer.commit()
        self.a.revoke(self.b.local_id)
        with self.assertRaisesRegex(ConnectError, 'device_not_paired'):
            channel.check()  # No cached snapshot survives its transaction.

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
        # C8 assigns 11/12 to Studio; 13 remains an unknown frame type.
        for values in ((16385, 1, 1), (0, 2, 1), (0, 1, 13), (1, 1, 3)):
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
