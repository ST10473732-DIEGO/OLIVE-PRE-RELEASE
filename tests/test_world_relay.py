"""The OLIVE World relay: rendezvous, isolation, limits, backpressure and hygiene (real sockets)."""
import asyncio
import json
import logging
import os
import random
import unittest

from olive.world import wire
from olive.world.client import RelayRefused, open_relay, rendezvous
from olive.world.websocket import BINARY, TEXT, Closed, encode_frame
from olive.world_relay.server import Limits, Relay


def creds(seed):
    rng = random.Random(seed)
    return rng.randbytes(16), rng.randbytes(32)


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seen = []
        self.limits = Limits(hello_timeout=1.0, phone_wait=1.0, ping_interval=.3, idle_timeout=1.2, stall_timeout=3)
        self.relay = Relay(self.limits, observer=lambda role, payload: self.seen.append((role, payload)))
        self.port = await self.relay.start('127.0.0.1', 0)
        self.url = 'ws://127.0.0.1:%d' % self.port
        self.logs = []
        handler = logging.Handler()
        handler.emit = lambda record: self.logs.append(record.getMessage())
        self.handler = handler
        logging.getLogger('olive.world_relay').addHandler(handler)
        logging.getLogger('olive.world_relay').setLevel(logging.INFO)

    async def asyncTearDown(self):
        await self.relay.shutdown(grace=1)
        logging.getLogger('olive.world_relay').removeHandler(self.handler)

    async def join(self, role, route, credential, *, wait=5):
        ws = await open_relay(self.url, dev=True)
        await rendezvous(ws, role, route, credential, timeout=wait)
        return ws

    async def http(self, request):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        writer.write(request)
        await writer.drain()
        data = await asyncio.wait_for(reader.read(65536), 3)
        writer.close()
        return data

    async def closed_with(self, ws, timeout=4):
        try:
            while True:
                await asyncio.wait_for(ws.recv(), timeout)
        except Closed as closed:
            return wire.CLOSE_NAMES.get(closed.code, closed.code)

    # ------------------------------------------------------------------ rendezvous
    async def test_pair_forwards_binary_both_ways_only_between_its_two_ends(self):
        r1, c1 = creds(1)
        r2, c2 = creds(2)
        desktop1 = await open_relay(self.url, dev=True)
        waiting = asyncio.ensure_future(rendezvous(desktop1, 'desktop', r1, c1))
        desktop2 = await open_relay(self.url, dev=True)
        waiting2 = asyncio.ensure_future(rendezvous(desktop2, 'desktop', r2, c2))
        await asyncio.sleep(.1)
        phone1 = await self.join('phone', r1, c1)
        phone2 = await self.join('phone', r2, c2)
        await waiting; await waiting2
        await phone1.send_binary(b'to-desktop-1')
        await phone2.send_binary(b'to-desktop-2')
        await desktop1.send_binary(b'to-phone-1')
        self.assertEqual(await desktop1.recv(), (BINARY, b'to-desktop-1'))
        self.assertEqual(await desktop2.recv(), (BINARY, b'to-desktop-2'))
        self.assertEqual(await phone1.recv(), (BINARY, b'to-phone-1'))
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(phone2.recv(), .3)  # No broadcast room: phone 2 never sees route 1.
        self.assertEqual(self.relay.tunnels, 2)
        health = json.loads((await self.http(b'GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n')).split(b'\r\n\r\n', 1)[1])
        self.assertEqual(set(health), {'status', 'version', 'protocol', 'active_tunnels'})
        self.assertEqual(health['active_tunnels'], 2)
        for ws in (desktop1, desktop2, phone1, phone2):
            await ws.close()

    async def test_random_or_wrong_token_never_reaches_a_route(self):
        route, credential = creds(3)
        desktop = await open_relay(self.url, dev=True)
        waiting = asyncio.ensure_future(rendezvous(desktop, 'desktop', route, credential))
        # Same route id, random credential: a different rendezvous key, so it waits alone.
        intruder = await open_relay(self.url, dev=True)
        with self.assertRaises(RelayRefused) as refused:
            await rendezvous(intruder, 'phone', route, os.urandom(32), timeout=5)
        self.assertEqual(refused.exception.category, 'peer_unavailable')
        self.assertFalse(waiting.done(), 'the desktop never paired with the intruder')
        self.assertEqual(self.relay.tunnels, 0)
        waiting.cancel()
        await desktop.close()

    async def test_newest_connection_replaces_and_partner_is_told(self):
        route, credential = creds(4)
        desktop = await open_relay(self.url, dev=True)
        waiting = asyncio.ensure_future(rendezvous(desktop, 'desktop', route, credential))
        first = await self.join('phone', route, credential)
        await waiting
        second = await open_relay(self.url, dev=True)
        await second.send_text(wire.hello('phone', route, credential))
        self.assertEqual(await self.closed_with(first), 'replaced')
        self.assertEqual(await self.closed_with(desktop), 'peer_left')
        await second.close()

    # ------------------------------------------------------------------ refusals
    async def test_handshake_refusals_fail_closed(self):
        cases = [
            ('{"v":2,"role":"phone","route":"' + '0' * 32 + '","credential":"' + '0' * 64 + '"}', 'unsupported_version'),
            ('{"v":1}', 'protocol_error'),
            ('not json', 'protocol_error'),
        ]
        for text, code in cases:
            ws = await open_relay(self.url, dev=True)
            await ws.send_text(text)
            self.assertEqual(await self.closed_with(ws), code)
        ws = await open_relay(self.url, dev=True)
        await ws.send_binary(b'\x16\x03\x01')  # TLS before rendezvous: never forwarded.
        self.assertEqual(await self.closed_with(ws), 'protocol_error')
        ws = await open_relay(self.url, dev=True)  # Silent after upgrade.
        self.assertEqual(await self.closed_with(ws), 'hello_timeout')
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)  # Silent before upgrade.
        self.assertEqual(await asyncio.wait_for(reader.read(), 3), b'')
        writer.close()
        self.assertEqual(self.seen, [])

    async def test_binary_before_pairing_and_text_after_are_refused(self):
        route, credential = creds(5)
        desktop = await open_relay(self.url, dev=True)
        waiting = asyncio.ensure_future(rendezvous(desktop, 'desktop', route, credential))
        phone = await self.join('phone', route, credential)
        await waiting
        await phone.send_text('{"v":1,"event":"paired"}')
        self.assertEqual(await self.closed_with(phone), 'protocol_error')
        self.assertEqual(await self.closed_with(desktop), 'peer_left')

    async def test_oversized_frame_refused_from_its_header(self):
        route, credential = creds(6)
        desktop = await open_relay(self.url, dev=True)
        waiting = asyncio.ensure_future(rendezvous(desktop, 'desktop', route, credential))
        phone = await self.join('phone', route, credential)
        await waiting
        # Declare a 1 GiB message but send only the header: refused before allocation.
        header = bytes([0x82, 0x80 | 127]) + (1 << 30).to_bytes(8, 'big') + os.urandom(4)
        phone.writer.write(header)
        await phone.writer.drain()
        self.assertEqual(await self.closed_with(phone), 'too_large')

    async def test_http_surface_is_minimal(self):
        ok = await self.http(b'GET /readiness HTTP/1.1\r\nHost: x\r\n\r\n')
        self.assertTrue(ok.startswith(b'HTTP/1.1 200'))
        self.assertIn(b'Cache-Control: no-store', ok)
        for request, status in ((b'GET / HTTP/1.1\r\n\r\n', b'404'), (b'GET /admin HTTP/1.1\r\n\r\n', b'404'),
                                (b'POST /healthz HTTP/1.1\r\n\r\n', b'405'), (b'GET /olive-world/1 HTTP/1.1\r\n\r\n', b'426'),
                                (b'GET /olive-world/1 HTTP/1.0\r\n\r\n', b'400'), (b'garbage\r\n\r\n', b'400')):
            with self.subTest(request=request):
                self.assertIn(status, (await self.http(request)).split(b'\r\n')[0])
        huge = b'GET /healthz HTTP/1.1\r\nX: ' + b'a' * 20000 + b'\r\n\r\n'
        self.assertNotIn(b'200', (await self.http(huge))[:12])
        rng = random.Random(9)
        for _ in range(40):
            try:
                await self.http(rng.randbytes(rng.randint(1, 300)) + b'\r\n\r\n')
            except (asyncio.TimeoutError, ConnectionError):
                pass
        self.assertTrue((await self.http(b'GET /healthz HTTP/1.1\r\n\r\n')).startswith(b'HTTP/1.1 200'))

    async def test_per_ip_connection_limit(self):
        await self.relay.shutdown(grace=1)
        self.relay = Relay(Limits(per_ip_connections=2, hello_timeout=2))
        self.port = await self.relay.start('127.0.0.1', 0)
        self.url = 'ws://127.0.0.1:%d' % self.port
        held = [await open_relay(self.url, dev=True) for _ in range(2)]
        with self.assertRaises(Exception):
            await open_relay(self.url, dev=True)
        self.assertIn(b'429', await self.http(b'GET /healthz HTTP/1.1\r\n\r\n'))
        for ws in held:
            await ws.close()

    async def test_trusted_proxy_accounts_per_forwarded_client(self):
        # Behind Caddy every TCP peer is the proxy: limits must apply per real client, not to everyone.
        await self.relay.shutdown(grace=1)
        self.relay = Relay(Limits(per_ip_connections=2, hello_timeout=3), trusted_proxies={'127.0.0.1'})
        self.port = await self.relay.start('127.0.0.1', 0)

        async def upgrade(client):
            reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
            writer.write(('GET /olive-world/1 HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                          'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n'
                          'Sec-WebSocket-Protocol: olive-world.1\r\nX-Forwarded-For: %s\r\n\r\n' % client).encode())
            await writer.drain()
            status = (await asyncio.wait_for(reader.readline(), 3)).split(b' ')[1]
            return status, writer
        held = [await upgrade('203.0.113.%d' % n) for n in range(1, 6)]      # Five clients, one proxy.
        self.assertEqual([status for status, _ in held], [b'101'] * 5)
        same = [await upgrade('198.51.100.7') for _ in range(3)]
        self.assertEqual([status for status, _ in same], [b'101', b'101', b'429'])
        for _, writer in held + same:
            writer.close()

    async def test_rate_limit_per_ip(self):
        await self.relay.shutdown(grace=1)
        self.relay = Relay(Limits(per_ip_rate=5))
        self.port = await self.relay.start('127.0.0.1', 0)
        statuses = [(await self.http(b'GET /healthz HTTP/1.1\r\n\r\n'))[9:12] for _ in range(8)]
        self.assertEqual(statuses[:5], [b'200'] * 5)
        self.assertEqual(set(statuses[5:]), {b'429'})

    async def test_idle_and_dead_peers_are_closed(self):
        route, credential = creds(7)
        desktop = await open_relay(self.url, dev=True)
        await desktop.send_text(wire.hello('desktop', route, credential))
        # Never reads, so never answers pings: closed after idle_timeout.
        await asyncio.sleep(self.limits.idle_timeout + 1)
        self.assertEqual(self.relay.routes, {}, 'unmatched routes do not linger')
        self.assertTrue(any('category=idle_timeout' in line for line in self.logs))

    # ------------------------------------------------------------------ backpressure
    async def test_flood_is_bounded_by_backpressure_and_control_plane_stays_up(self):
        route, credential = creds(8)
        desktop = await open_relay(self.url, dev=True)
        waiting = asyncio.ensure_future(rendezvous(desktop, 'desktop', route, credential))
        phone = await self.join('phone', route, credential)
        await waiting
        chunk = os.urandom(wire.CHUNK)
        sent = 0

        async def flood():
            nonlocal sent
            while sent < 40 * 1024 * 1024:
                await desktop.send_binary(chunk)
                sent += len(chunk)
        flooding = asyncio.ensure_future(flood())
        await asyncio.sleep(1.0)            # The phone is not reading at all.
        self.assertFalse(flooding.done())
        self.assertLess(sent, 16 * 1024 * 1024, 'the sender is held back, not buffered without bound')
        endpoint = next(e for slots in self.relay.routes.values() for e in slots.values() if e.role == 'phone')
        self.assertLessEqual(endpoint.ws.writer.transport.get_write_buffer_size(),
                             self.limits.write_buffer + self.limits.max_message + 64)
        started = asyncio.get_running_loop().time()
        self.assertIn(b'200', await self.http(b'GET /healthz HTTP/1.1\r\n\r\n'))
        self.assertLess(asyncio.get_running_loop().time() - started, 1.0)
        received = 0
        while received < sent or not flooding.done():  # Reading releases the flood, in order and complete.
            opcode, payload = await asyncio.wait_for(phone.recv(), 5)
            self.assertEqual(payload, chunk)
            received += len(payload)
            if received >= 40 * 1024 * 1024:
                break
        self.assertEqual(received, 40 * 1024 * 1024)
        await desktop.close(); await phone.close()

    # ------------------------------------------------------------------ lifecycle & hygiene
    async def test_graceful_shutdown_closes_sessions_with_going_away(self):
        route, credential = creds(10)
        desktop = await open_relay(self.url, dev=True)
        waiting = asyncio.ensure_future(rendezvous(desktop, 'desktop', route, credential))
        phone = await self.join('phone', route, credential)
        await waiting
        shutdown = asyncio.ensure_future(self.relay.shutdown(grace=2))
        self.assertEqual(await self.closed_with(phone), 'going_away')
        self.assertEqual(await self.closed_with(desktop), 'going_away')
        await shutdown

    async def test_logs_hold_no_route_credential_or_content(self):
        route, credential = creds(11)
        desktop = await open_relay(self.url, dev=True)
        waiting = asyncio.ensure_future(rendezvous(desktop, 'desktop', route, credential))
        phone = await self.join('phone', route, credential)
        await waiting
        await phone.send_binary(b'OLIVE_WORLD_SECRET_SENTENCE_12345')
        await desktop.recv()
        await phone.close(); await desktop.close()
        await asyncio.sleep(.2)
        text = '\n'.join(self.logs)
        self.assertIn('event=paired', text)
        for secret in (route.hex(), credential.hex(), wire.rendezvous(route, credential).hex(),
                       'OLIVE_WORLD_SECRET_SENTENCE_12345', '127.0.0.1'):
            self.assertNotIn(secret, text)


if __name__ == '__main__':
    unittest.main()


class RelayTLSTests(unittest.IsolatedAsyncioTestCase):
    """wss:// end to end with a real certificate check; verification can never be turned off."""
    async def asyncSetUp(self):
        import datetime
        import ssl
        import tempfile
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        self.temp = tempfile.TemporaryDirectory()
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1))
                .not_valid_after(now + datetime.timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(key, hashes.SHA256()))
        self.cert = os.path.join(self.temp.name, 'cert.pem')
        keyfile = os.path.join(self.temp.name, 'key.pem')
        with open(self.cert, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(keyfile, 'wb') as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(self.cert, keyfile)
        self.relay = Relay(Limits())
        self.port = await self.relay.start('127.0.0.1', 0, ssl=server)
        self.url = 'wss://localhost:%d' % self.port

    async def asyncTearDown(self):
        await self.relay.shutdown(grace=1)
        self.temp.cleanup()

    async def test_wss_with_validated_certificate(self):
        import ssl
        trusted = ssl.create_default_context(cafile=self.cert)
        route, credential = creds(20)
        desktop = await open_relay(self.url, ssl_context=trusted)
        waiting = asyncio.ensure_future(rendezvous(desktop, 'desktop', route, credential))
        phone = await open_relay(self.url, ssl_context=trusted)
        await rendezvous(phone, 'phone', route, credential, timeout=5)
        await waiting
        await phone.send_binary(b'over-wss')
        self.assertEqual(await desktop.recv(), (BINARY, b'over-wss'))
        await phone.close(); await desktop.close()

    async def test_untrusted_certificate_and_disabled_verification_are_refused(self):
        import ssl
        from olive.world.client import category_for
        # The refused handshake makes asyncio log a reset on the server side (production silences it).
        asyncio_log = logging.getLogger('asyncio')
        level = asyncio_log.level
        asyncio_log.setLevel(logging.CRITICAL)
        self.addCleanup(asyncio_log.setLevel, level)
        with self.assertRaises(ssl.SSLCertVerificationError) as raised:
            await open_relay(self.url)               # System trust: a self-signed relay is refused.
        self.assertEqual(category_for(raised.exception), 'relay_certificate_invalid')
        insecure = ssl.create_default_context()
        insecure.check_hostname = False
        insecure.verify_mode = ssl.CERT_NONE
        with self.assertRaises(wire.WorldError):
            await open_relay(self.url, ssl_context=insecure)
