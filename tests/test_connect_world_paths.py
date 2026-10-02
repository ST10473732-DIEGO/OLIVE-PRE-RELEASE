"""Direct <-> World path ownership when a path dies silently.

A phone that switches Wi-Fi off closes its Direct socket, but its FIN never
reaches the computer: the LAN interface is already gone. The computer's
Direct channel then looks current until its idle timeout. These tests put a
blackhole proxy on the Direct path (bytes stop flowing both ways, no FIN, no
reset) and check that a valid World tunnel is not rejected against that dead
channel, while a healthy Direct channel still wins.
"""
import socket
import threading
import time
import unittest

from olive.connect.contracts import ConnectError
from tests.test_connect_network import until
from tests.test_connect_world import WorldIntegrationBase


class BlackholeProxy:
    """TEST-ONLY TCP relay for the Direct path. ``blackhole()`` models Wi-Fi loss:
    sockets stay open, every byte in both directions is dropped."""

    def __init__(self, target):
        self.target = target
        self.listener = socket.create_server(('127.0.0.1', 0))
        self.port = self.listener.getsockname()[1]
        self.dropping = threading.Event()
        self.closing = threading.Event()
        self.sockets = []
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._accept, name='test-blackhole-accept', daemon=True).start()
        return self

    def _accept(self):
        self.listener.settimeout(.1)
        while not self.closing.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            upstream = socket.create_connection(self.target)
            with self.lock:
                self.sockets += [client, upstream]
            for source, sink in ((client, upstream), (upstream, client)):
                threading.Thread(target=self._pump, args=(source, sink), name='test-blackhole-pump',
                                 daemon=True).start()

    def _pump(self, source, sink):
        source.settimeout(.1)
        while not self.closing.is_set():
            try:
                data = source.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                return
            if not data:
                if not self.dropping.is_set():
                    try:
                        sink.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                return
            if not self.dropping.is_set():
                try:
                    sink.sendall(data)
                except OSError:
                    return

    def blackhole(self):
        self.dropping.set()

    def close(self):
        self.closing.set()
        self.listener.close()
        with self.lock:
            for sock in self.sockets:
                try:
                    sock.close()
                except OSError:
                    pass


class WorldPathOwnershipTests(WorldIntegrationBase):
    def setUp(self):
        super().setUp()
        self.proxies = []

    def tearDown(self):
        for proxy in self.proxies:
            proxy.close()
        super().tearDown()

    def proxied_direct(self):
        proxy = BlackholeProxy(('127.0.0.1', self.nd.port)).start()
        self.proxies.append(proxy)
        channel = self.phone.network.connect(self.desk.local_id, '127.0.0.1', proxy.port)
        until(lambda: self.nd.status(self.phone.local_id)['connection'] == 'local')
        return proxy, channel

    def lose_wifi(self, proxy):
        """Wi-Fi off: the phone retires Direct locally; nothing reaches the computer."""
        proxy.blackhole()
        self.phone.network.disconnect(self.desk.local_id, wait=False)

    def desk_channel(self):
        with self.nd.lock:
            return self.nd.channels.get(self.phone.local_id)

    def retired(self, category):
        with self.nd.lock:
            return [s for _, s in self.nd.retired if (s.get('terminal') or {}).get('category') == category]

    def rejected_worlds(self):
        """World channels refused at adoption (a World merely replaced by Direct ends later, while reading)."""
        return [s for s in self.retired('retirement_direct_preferred') if s['terminal']['phase'] == 'hello']

    def test_stale_direct_does_not_block_world(self):
        peer = self.provisioned()
        proxy, direct = self.proxied_direct()
        self.assertTrue(self.ping(direct)['result']['pong'])
        stale = self.desk_channel()
        self.assertEqual(stale.path, 'direct')
        before = self.executed()
        self.lose_wifi(proxy)
        started = time.monotonic()
        world = self.world_connect(peer)
        # Far inside the 60 s idle timeout that used to be the only way out.
        until(lambda: self.nd.status(self.phone.local_id)['connection'] == 'world', 10)
        self.assertLess(time.monotonic() - started, 10)
        until(lambda: stale.stop.is_set())
        self.assertEqual(stale.diagnostics.snapshot()['terminal']['category'], 'retirement_stale')
        self.assertIs(self.desk_channel().path, 'world')
        self.assertEqual(len(self.nd.channels), 1, 'one logical peer')
        self.assertEqual(self.rejected_worlds(), [], 'World is never rejected against a dead Direct channel')
        self.assertTrue(self.ping(world)['result']['pong'])
        self.assertEqual(self.executed(), before + 1, 'the request ran exactly once')
        routes = self.desk.world.status()['peers'][self.phone.local_id]
        self.assertLessEqual(routes['reconnects'], 1, 'no reconnect loop')

    def test_healthy_direct_keeps_preference(self):
        peer = self.provisioned()
        direct = self.direct()
        self.assertTrue(self.ping(direct)['result']['pong'])
        current = self.desk_channel()
        before = self.executed()
        try:
            # The phone-side race: World authenticates while Direct is live.
            self.world_peer().connect(credentials=peer.credentials, wait=3)
        except ConnectError:
            pass
        until(lambda: len(self.rejected_worlds()) == 1, 10)
        self.assertIs(self.desk_channel(), current, 'the healthy Direct channel stays current')
        self.assertFalse(current.stop.is_set())
        self.assertEqual(self.nd.status(self.phone.local_id)['connection'], 'local')
        self.assertEqual(len(self.nd.channels), 1)
        self.assertEqual(self.retired('retirement_stale'), [])
        self.assertTrue(self.ping(direct)['result']['pong'])
        self.assertEqual(self.executed(), before + 1)

    def test_direct_world_direct_transition(self):
        peer = self.provisioned()
        proxy, direct = self.proxied_direct()
        self.assertTrue(self.ping(direct)['result']['pong'])
        stale = self.desk_channel()
        before = self.executed()
        observed = set()
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                with self.nd.lock:
                    live = [c for c in self.nd.channels.values() if not c.stop.is_set()]
                observed.add(len(live))
                time.sleep(.005)
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            self.lose_wifi(proxy)
            world = self.world_connect(peer)
            until(lambda: self.nd.status(self.phone.local_id)['connection'] == 'world', 10)
            self.assertTrue(self.ping(world)['result']['pong'])
            back = self.direct()                       # Wi-Fi is back: Direct replaces World.
            until(lambda: self.nd.status(self.phone.local_id)['connection'] == 'local')
            until(lambda: world.stop.is_set())
            self.assertTrue(self.ping(back)['result']['pong'])
            # The retired channel's late teardown never replaces newer state.
            until(lambda: not stale.thread.is_alive(), 6)
            time.sleep(.3)
            self.assertEqual(self.nd.status(self.phone.local_id)['connection'], 'local')
            self.assertEqual(self.nd.status(self.phone.local_id)['state'], 'online')
        finally:
            stop.set()
            watcher.join(2)
        self.assertLessEqual(observed, {0, 1}, 'never two logical channels for one peer')
        self.assertEqual(len(self.nd.channels), 1)
        self.assertEqual(self.executed(), before + 2, 'no duplicate jobs across handovers')
        # No oscillation: one stale retirement, one World retired by Direct, nothing refused.
        self.assertEqual(len(self.retired('retirement_stale')), 1)
        self.assertEqual(len(self.retired('retirement_direct_preferred')), 1)
        self.assertEqual(self.rejected_worlds(), [])

    def test_rejected_world_never_reports_the_relay_unavailable(self):
        peer = self.provisioned()
        self.direct()
        relays = []
        try:
            self.world_peer().connect(credentials=peer.credentials, wait=3)
        except ConnectError:
            pass
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            status = self.desk.world.status()
            relays.append(status['relay'])
            time.sleep(.02)
        self.assertNotIn('unavailable', relays, 'a retired tunnel is not a relay outage')
        until(lambda: self.desk.world.status()['peers'][self.phone.local_id]['route'] == 'registered', 6)
        status = self.desk.world.status()
        self.assertEqual(status['relay'], 'connected')
        self.assertIsNone(status['error'])
        self.assertEqual(status['peers'][self.phone.local_id]['path'], 'direct')


if __name__ == '__main__':
    unittest.main()
