"""OLIVE Connect World: key schedule vectors, olive-world/1 wire, WebSocket codec fuzz,
backoff and the Direct/World path state machine."""
import ast
import json
import random
import struct
import unittest
from pathlib import Path

from olive.world import wire
from olive.world.backoff import Backoff, DELAYS
from olive.world.paths import DIRECT, WORLD, PathSelector, WORLD_FALLBACK_DELAY
from olive.world.websocket import (BINARY, CLOSE, PING, TEXT, FrameReader, WebSocketError, accept_value,
                                   apply_mask, encode_frame, parse_close)

VECTORS = json.loads((Path(__file__).parent / 'fixtures' / 'world_vectors_v1.json').read_text())


class KeyScheduleTests(unittest.TestCase):
    def test_hkdf_matches_rfc5869_case_1_and_cryptography(self):
        okm = wire.hkdf_sha256(b'\x0b' * 22, salt=bytes(range(13)), info=bytes(range(0xf0, 0xfa)), length=42)
        self.assertEqual(okm.hex(), '3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865')
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        for size in (16, 32, 64):
            ikm = bytes(random.Random(size).randbytes(32))
            self.assertEqual(wire.hkdf_sha256(ikm, info=b'x', length=size),
                             HKDF(hashes.SHA256(), size, wire.CONTEXT, b'x').derive(ikm))

    def test_fixed_vectors(self):
        v = VECTORS
        master = bytes.fromhex(v['master'])
        args = (master, v['local_device_id'], v['peer_device_id'], v['generation'], v['identity'])
        secret = wire.route_secret(*args)
        route = wire.route_id(*args)
        credential = wire.relay_credential(secret)
        self.assertEqual(secret.hex(), v['route_secret'])
        self.assertEqual(route.hex(), v['route_id'])
        self.assertEqual(credential.hex(), v['relay_credential'])
        self.assertEqual(wire.rendezvous(route, credential).hex(), v['rendezvous'])
        self.assertEqual(wire.hello('phone', route, credential), v['phone_hello'])
        rotated = wire.route_secret(master, v['local_device_id'], v['peer_device_id'], 2, v['identity'])
        self.assertEqual(rotated.hex(), v['route_secret_generation_2'])
        self.assertEqual(v['context'], wire.CONTEXT.decode())

    def test_domain_separation_and_binding(self):
        master = bytes(32)
        a = wire.route_secret(master, 'a', 'b', 1, 'id')
        self.assertNotEqual(a, wire.route_id(master, 'a', 'b', 1, 'id') + bytes(16))
        self.assertNotEqual(a, wire.relay_credential(a))
        self.assertNotEqual(a, wire.route_secret(master, 'a', 'c', 1, 'id'), 'per pair')
        self.assertNotEqual(a, wire.route_secret(master, 'a', 'b', 2, 'id'), 'per generation')
        self.assertNotEqual(a, wire.route_secret(master, 'a', 'b', 1, 'other'), 'bound to Connect identity')
        for bad in (b'', bytes(31), 'x' * 32):
            with self.assertRaises(wire.WorldError):
                wire.route_secret(bad, 'a', 'b', 1, 'id')
        for generation in (0, -1, True, 1.0, 2 ** 63):
            with self.assertRaises(wire.WorldError):
                wire.route_secret(master, 'a', 'b', generation, 'id')

    def test_vectors_are_embedded_in_swift_tests(self):
        swift = (Path(__file__).parents[1] / 'mobile/ios/OLIVEMobileTests/WorldTests.swift').read_text()
        for key in ('route_secret', 'relay_credential', 'route_id'):
            self.assertIn(VECTORS[key], swift)


class HelloTests(unittest.TestCase):
    def test_round_trip_and_strictness(self):
        route, credential = bytes(range(16)), bytes(range(32))
        self.assertEqual(wire.parse_hello(wire.hello('desktop', route, credential)), ('desktop', route, credential))
        good = json.loads(wire.hello('phone', route, credential))
        cases = [
            ('not json', 'protocol_error'), ('[]', 'protocol_error'), ('{}', 'protocol_error'),
            (json.dumps(dict(good, v=2)), 'unsupported_version'), (json.dumps(dict(good, v=True)), 'unsupported_version'),
            (json.dumps(dict(good, role='relay')), 'protocol_error'),
            (json.dumps(dict(good, route='00' * 15)), 'protocol_error'),
            (json.dumps(dict(good, route=good['route'].upper())), 'protocol_error'),
            (json.dumps(dict(good, credential='zz' * 32)), 'protocol_error'),
            (json.dumps(dict(good, extra=1)), 'protocol_error'),
            (json.dumps(dict(good, credential=good['credential'] + '00')), 'protocol_error'),
            ('{"v":1,' * 200, 'protocol_error'), ('x' * 600, 'protocol_error'),
            (json.dumps(dict(good, v=float('nan'))), 'protocol_error'),
        ]
        for text, code in cases:
            with self.subTest(text=text[:40]), self.assertRaises(wire.WorldError) as raised:
                wire.parse_hello(text)
            self.assertEqual(str(raised.exception), code)

    def test_fuzzed_hellos_fail_closed(self):
        rng = random.Random(7)
        base = wire.hello('phone', bytes(16), bytes(32))
        for _ in range(2000):
            raw = bytearray(base.encode())
            for _ in range(rng.randint(1, 4)):
                raw[rng.randrange(len(raw))] = rng.randrange(256)
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                continue
            try:
                role, route, credential = wire.parse_hello(text)
            except wire.WorldError:
                continue
            self.assertIn(role, wire.ROLES)
            self.assertEqual((len(route), len(credential)), (16, 32))

    def test_events(self):
        self.assertEqual(wire.parse_event(wire.event('paired')), 'paired')
        for bad in ('{}', '{"v":1,"event":"other"}', '{"v":2,"event":"paired"}', '{"v":1,"event":"paired","x":1}', 'x'):
            with self.assertRaises(wire.WorldError):
                wire.parse_event(bad)

    def test_relay_url_policy(self):
        target = wire.parse_relay_url('wss://relay.example.com')
        self.assertEqual((target.tls, target.port, target.path, target.host_header), (True, 443, '/olive-world/1', 'relay.example.com'))
        self.assertEqual(wire.parse_relay_url('wss://relay.example.com:8443/world/x').path, '/world/x')
        self.assertEqual(wire.parse_relay_url('ws://127.0.0.1:8765', dev=True).tls, False)
        for url, dev in (('ws://relay.example.com', False), ('ws://relay.example.com', True), ('ws://127.0.0.1:1', False),
                         ('ws://10.0.0.2', True), ('https://relay.example.com', False), ('wss://user:pw@relay.example.com', False),
                         ('wss://relay.example.com/?token=1', False), ('wss://relay.example.com/#x', False), ('wss://', False),
                         ('wss://relay.example.com/a b', False), (' wss://relay.example.com', False), ('wss://a/%2e', False),
                         ('wss://' + 'a' * 300, False), (None, False), ('wss://relay.example.com:99999', False)):
            with self.subTest(url=url), self.assertRaises(wire.WorldError):
                wire.parse_relay_url(url, dev=dev)
        self.assertEqual(wire.relay_host('wss://relay.example.com/x'), 'relay.example.com')

    def test_test_lan_plaintext_is_private_addresses_only(self):
        # TEST-ONLY Mac test-host mode: plaintext to a private LAN address; never public, never by default.
        self.assertFalse(wire.parse_relay_url('ws://192.168.1.20:8765', test_lan=True).tls)
        self.assertFalse(wire.parse_relay_url('ws://10.0.0.5:8765', test_lan=True).tls)
        for url in ('ws://192.168.1.20:8765', 'ws://8.8.8.8:8765', 'ws://relay.example.com'):
            with self.subTest(url=url), self.assertRaises(wire.WorldError):
                wire.parse_relay_url(url, test_lan=url != 'ws://192.168.1.20:8765')

    def test_relay_and_world_packages_are_standard_library_only(self):
        root = Path(__file__).parents[1] / 'olive'
        allowed_prefix = ('olive.world', '..world', '.')
        import sys
        for package in ('world', 'world_relay'):
            for path in (root / package).glob('*.py'):
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertIn(alias.name.split('.')[0], sys.stdlib_module_names, path.name)
                    elif isinstance(node, ast.ImportFrom):
                        name = ('.' * node.level) + (node.module or '')
                        if node.level:
                            self.assertTrue(name.startswith(allowed_prefix), (path.name, name))
                            self.assertNotIn('connect', name)
                        else:
                            self.assertIn(node.module.split('.')[0], sys.stdlib_module_names, (path.name, name))


class WebSocketCodecTests(unittest.TestCase):
    def frames(self, raw, *, mask_expected=True, max_payload=1024):
        reader = FrameReader(max_payload=max_payload, expect_mask=mask_expected)
        reader.feed(raw)
        out = []
        while (frame := reader.next()) is not None:
            out.append(frame)
        return out

    def test_round_trip_sizes_and_masking(self):
        for size in (0, 1, 125, 126, 65535, 65536, 200_000):
            payload = random.Random(size).randbytes(size)
            for mask in (True, False):
                reader = FrameReader(max_payload=262144, expect_mask=mask)
                raw = encode_frame(BINARY, payload, mask=mask)
                for start in range(0, len(raw), 7919):  # Arbitrary split points.
                    reader.feed(raw[start:start + 7919])
                self.assertEqual(reader.next(), (True, BINARY, payload))
        self.assertEqual(apply_mask(apply_mask(b'abcdefg', b'\x01\x02\x03\x04'), b'\x01\x02\x03\x04'), b'abcdefg')
        self.assertEqual(accept_value('dGhlIHNhbXBsZSBub25jZQ=='), 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')  # RFC 6455 §1.3

    def test_size_checked_before_allocation(self):
        # A declared 8 GiB frame is refused from its 10-byte header alone.
        header = bytes([0x82, 0x80 | 127]) + struct.pack('!Q', 8 * 1024 ** 3)
        with self.assertRaises(WebSocketError) as raised:
            self.frames(header)
        self.assertEqual(str(raised.exception), 'frame_too_large')
        with self.assertRaises(WebSocketError):
            self.frames(bytes([0x82, 0x80 | 127]) + struct.pack('!Q', 1 << 63))
        reader = FrameReader(max_payload=1024, expect_mask=True)
        with self.assertRaises(WebSocketError):
            reader.feed(b'\0' * (1024 + 14 + 65537))

    def test_malformed_frames_fail_closed(self):
        masked = lambda opcode, payload, **kw: encode_frame(opcode, payload, mask=True, **kw)
        cases = {
            'reserved_bits': bytes([0x82 | 0x40, 0x80]) + b'\0' * 4,
            'unknown_opcode': bytes([0x83, 0x80]) + b'\0' * 4,
            'mask_policy': encode_frame(BINARY, b'x', mask=False),
            'non_minimal_length': bytes([0x82, 0x80 | 126]) + struct.pack('!H', 5) + b'\0' * 9,
            'invalid_control_frame': bytes([0x09, 0x80]) + b'\0' * 4,  # Fragmented ping.
        }
        for code, raw in cases.items():
            with self.subTest(code=code), self.assertRaises(WebSocketError) as raised:
                self.frames(raw)
            self.assertEqual(str(raised.exception), code)
        big_ping = bytes([0x89, 0x80 | 126]) + struct.pack('!H', 200) + b'\0' * 204
        with self.assertRaises(WebSocketError):
            self.frames(big_ping)
        with self.assertRaises(WebSocketError):
            encode_frame(PING, b'x' * 126, mask=True)
        self.assertEqual(self.frames(masked(TEXT, b'hi')), [(True, TEXT, b'hi')])

    def test_close_payloads(self):
        self.assertEqual(parse_close(b''), (1005, ''))
        self.assertEqual(parse_close(struct.pack('!H', 4003) + b'replaced'), (4003, 'replaced'))
        for bad in (b'\x03', struct.pack('!H', 999), struct.pack('!H', 1005), struct.pack('!H', 5000),
                    struct.pack('!H', 1000) + b'\xff'):
            with self.assertRaises(WebSocketError):
                parse_close(bad)

    def test_random_bytes_never_crash(self):
        rng = random.Random(11)
        for _ in range(3000):
            reader = FrameReader(max_payload=4096, expect_mask=rng.random() < .5)
            try:
                reader.feed(rng.randbytes(rng.randint(0, 64)))
                while reader.next() is not None:
                    pass
            except WebSocketError:
                pass


class BackoffTests(unittest.TestCase):
    def test_schedule_bounds_jitter_and_reset(self):
        backoff = Backoff(rng=random.Random(1))
        delays = [backoff.next() for _ in range(10)]
        for delay, base in zip(delays, DELAYS + (30.0,) * 4):
            self.assertTrue(base * .8 <= delay <= base * 1.2, (delay, base))
        self.assertLessEqual(max(delays), 36)
        backoff.settled(5)
        self.assertGreater(backoff.next(), 20, 'a short-lived connection keeps backing off')
        backoff.settled(31)
        self.assertLess(backoff.next(), 1, 'a stable connection resets the schedule')


class PathSelectorTests(unittest.TestCase):
    def test_direct_first_world_after_bounded_delay(self):
        paths = PathSelector(world_available=True)
        actions = paths.start(lan_usable=True)
        self.assertEqual([(a, p, d) for a, p, _, d in actions], [('connect', DIRECT, 0.0), ('connect', WORLD, WORLD_FALLBACK_DELAY)])
        self.assertLess(WORLD_FALLBACK_DELAY, 3, 'never a 30 s wait before World')
        off_lan = PathSelector(world_available=True).start(lan_usable=False)
        self.assertEqual(off_lan[1][3], 0.0, 'no Wi-Fi: World starts at once')

    def test_direct_preferred_when_both_authenticate(self):
        paths = PathSelector(world_available=True)
        (_, _, gd, _), (_, _, gw, _) = paths.start(lan_usable=True)
        self.assertEqual(paths.authenticated(WORLD, gw), [])
        self.assertEqual(paths.state, 'world')
        actions = paths.authenticated(DIRECT, gd)
        self.assertEqual(actions, [('close', WORLD, gw, 0.0)])
        self.assertEqual((paths.state, paths.active), ('direct', DIRECT))
        # Reverse order: World arriving after Direct is closed, Direct stays.
        paths = PathSelector(world_available=True)
        (_, _, gd, _), (_, _, gw, _) = paths.start(lan_usable=True)
        paths.authenticated(DIRECT, gd)
        self.assertEqual(paths.authenticated(WORLD, gw), [('close', WORLD, gw, 0.0)])
        self.assertEqual(paths.active, DIRECT)

    def test_direct_loss_hands_over_to_world_and_back(self):
        paths = PathSelector(world_available=True)
        (_, _, gd, _), (_, _, gw, _) = paths.start(lan_usable=True)
        paths.authenticated(DIRECT, gd)
        actions = paths.failed(DIRECT, gd)
        self.assertEqual([(a, p) for a, p, _, _ in actions], [('connect', WORLD)])
        g2 = actions[0][2]
        paths.authenticated(WORLD, g2)
        self.assertEqual(paths.state, 'world')
        (_, _, g3, _), = paths.direct_candidate()
        self.assertEqual(paths.direct_candidate(), [], 'one Direct probe at a time')
        self.assertEqual(paths.authenticated(DIRECT, g3), [('close', WORLD, g2, 0.0)])
        self.assertEqual(paths.active, DIRECT)

    def test_stale_callbacks_never_overwrite_state(self):
        paths = PathSelector(world_available=True)
        (_, _, gd, _), (_, _, gw, _) = paths.start(lan_usable=True)
        paths.authenticated(WORLD, gw)        # World connects
        paths.authenticated(DIRECT, gd)       # Direct connects (World retired)
        self.assertEqual(paths.failed(WORLD, gw), [], 'retired World generation is ignored')
        self.assertEqual((paths.state, paths.active), ('direct', DIRECT))
        actions = paths.failed(DIRECT, gd)    # Direct dies
        self.assertEqual(paths.failed(DIRECT, gd), [], 'duplicate death ignored')
        self.assertEqual(paths.authenticated(DIRECT, gd), [('close', DIRECT, gd, 0.0)], 'late success of a dead attempt is closed')
        self.assertEqual(paths.state, 'world_connecting')
        paths.authenticated(WORLD, actions[0][2])
        self.assertEqual((paths.state, paths.active), ('world', WORLD))

    def test_forced_world_direct_only_and_revoked(self):
        forced = PathSelector(world_available=True, direct_allowed=False)
        actions = forced.start(lan_usable=True)
        self.assertEqual([(p, d) for _, p, _, d in actions], [(WORLD, 0.0)])
        self.assertEqual(forced.direct_candidate(), [])
        direct_only = PathSelector(world_available=True, world_allowed=False)
        self.assertEqual([p for _, p, _, _ in direct_only.start(lan_usable=False)], [DIRECT])
        unprovisioned = PathSelector(world_available=False)
        (_, _, gd, _), = unprovisioned.start(lan_usable=True)
        self.assertEqual(unprovisioned.failed(DIRECT, gd), [])
        self.assertEqual(unprovisioned.state, 'offline')
        paths = PathSelector(world_available=True)
        (_, _, gd, _), _ = paths.start(lan_usable=True)
        paths.authenticated(DIRECT, gd)
        self.assertTrue(paths.revoke())
        self.assertEqual(paths.start(lan_usable=True), [])
        self.assertEqual(paths.state, 'revoked')

    def test_randomized_event_orders_are_deterministic_and_single_active(self):
        rng = random.Random(3)
        for _ in range(500):
            paths = PathSelector(world_available=True)
            pending = [(p, g) for _, p, g, _ in paths.start(lan_usable=True)]
            events = []
            for path, generation in pending:
                events.append(('ok', path, generation))
                events.append(('fail', path, generation))
            rng.shuffle(events)
            for kind, path, generation in events:
                actions = (paths.authenticated if kind == 'ok' else paths.failed)(path, generation)
                for action, new_path, new_generation, _ in actions:
                    if action == 'connect':
                        events.append(('ok', new_path, new_generation))
                if len(events) > 50:
                    break
            self.assertIn(paths.state, ('direct', 'world', 'offline', 'world_connecting', 'direct_connecting', 'switching'))
            if paths.active is not None:
                self.assertEqual(paths.state, paths.active)


if __name__ == '__main__':
    unittest.main()
