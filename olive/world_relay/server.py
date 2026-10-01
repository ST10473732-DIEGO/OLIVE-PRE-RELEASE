"""OLIVE Connect World relay: a deliberately dumb, stateless rendezvous forwarder.

It joins exactly two WebSocket connections that present the same route
credential (one ``desktop``, one ``phone``) and forwards their binary messages
in memory. Those bytes are the paired devices' own TLS 1.3 records; the relay
holds no key that could read them, stores nothing and logs no content, route
identifiers or credentials. Standard library only.
"""
import asyncio
import base64
from collections import deque
from dataclasses import dataclass, field
import hmac
import itertools
import json
import logging
import time

from ..world import wire
from ..world.websocket import (BINARY, TEXT, Closed, WebSocket, WebSocketError, accept_value,
                               header_tokens, read_http_head)

VERSION = '1.0.0'
log = logging.getLogger('olive.world_relay')


@dataclass
class Limits:
    max_message: int = wire.MAX_MESSAGE      # One binary tunnel message.
    max_connections: int = 2048               # Whole relay.
    per_ip_connections: int = 64              # Concurrent, per client address (CGNAT-friendly).
    per_ip_rate: int = 120                    # New connections per window, per client address.
    rate_window: float = 60.0
    hello_timeout: float = 10.0               # Accept -> valid hello, unauthenticated.
    phone_wait: float = 20.0                  # A phone waits this long for its computer.
    ping_interval: float = 20.0
    idle_timeout: float = 60.0                # Nothing received (pongs count) -> closed.
    stall_timeout: float = 30.0               # A partner that will not read -> session closed.
    write_buffer: int = 262144                # Per-connection transport high-water mark.
    max_routes: int = 4096


@dataclass(eq=False)
class Endpoint:
    conn: int
    role: str
    ws: WebSocket
    key: bytes
    partner: 'Endpoint | None' = None
    started: float = field(default_factory=time.monotonic)
    category: str = 'closed'


class Relay:
    def __init__(self, limits=None, *, trusted_proxies=(), observer=None, clock=time.monotonic):
        self.limits = limits or Limits()
        self.trusted_proxies = frozenset(trusted_proxies)
        # TEST-ONLY instrumentation: sees exactly what the relay forwards (and may alter it, to
        # model a malicious relay). The CLI never sets it.
        self.observer = observer
        self.clock = clock
        self.routes = {}
        self.connections = set()
        self.per_ip = {}
        self.rates = {}
        self.ids = itertools.count(1)
        self.draining = False
        self.server = None
        self.tunnels = 0

    # ------------------------------------------------------------------ admission
    def _admit(self, ip):
        """Admission for one client address. A trusted reverse proxy is not a client: its
        connections are admitted on the global cap here and accounted per forwarded client
        address once the request head names it (see _account)."""
        now = self.clock()
        if ip in self.trusted_proxies:
            if self.draining:
                return 'going_away'
            return 'capacity' if len(self.connections) >= self.limits.max_connections else None
        window = self.rates.setdefault(ip, deque())
        while window and window[0] <= now - self.limits.rate_window:
            window.popleft()
        if len(self.rates) > 65536:  # Bound the rate table itself.
            for stale in [k for k, v in self.rates.items() if not v][:4096]:
                self.rates.pop(stale, None)
        if self.draining:
            return 'going_away'
        if len(self.connections) >= self.limits.max_connections:
            return 'capacity'
        if self.per_ip.get(ip, 0) >= self.limits.per_ip_connections or len(window) >= self.limits.per_ip_rate:
            return 'rate_limited'
        window.append(now)
        return None

    def _client_ip(self, writer, headers):
        peer = writer.get_extra_info('peername')
        ip = peer[0] if peer else 'unknown'
        if ip in self.trusted_proxies and headers.get('x-forwarded-for'):
            # Only a configured reverse proxy may name the client; take its last hop.
            candidate = headers['x-forwarded-for'].split(',')[-1].strip()
            if 0 < len(candidate) <= 64:
                return candidate
        return ip

    # ------------------------------------------------------------------ HTTP surface
    @staticmethod
    async def _respond(writer, status, body, *, content_type='application/json'):
        reasons = {200: 'OK', 400: 'Bad Request', 404: 'Not Found', 405: 'Method Not Allowed',
                   426: 'Upgrade Required', 429: 'Too Many Requests', 503: 'Service Unavailable'}
        raw = body.encode('utf-8')
        head = ('HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: no-store\r\n'
                'X-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n' % (
                    status, reasons.get(status, 'Error'), content_type, len(raw)))
        try:
            writer.write(head.encode('ascii') + raw)
            await asyncio.wait_for(writer.drain(), 2)
        except Exception:
            pass
        finally:
            writer.close()

    def health(self):
        return dict(status='ok', version=VERSION, protocol=wire.PROTOCOL, active_tunnels=self.tunnels)

    async def handle(self, reader, writer):
        conn = next(self.ids)
        peer = writer.get_extra_info('peername')
        ip = peer[0] if peer else 'unknown'
        refused = self._admit(ip)
        if refused:
            await self._respond(writer, 503 if refused != 'rate_limited' else 429, json.dumps(dict(error=refused)))
            return
        self.connections.add(conn)
        self.per_ip[ip] = self.per_ip.get(ip, 0) + 1
        endpoint = None
        started = self.clock()
        try:
            try:
                start, headers = await read_http_head(reader, timeout=self.limits.hello_timeout)
            except (WebSocketError, asyncio.TimeoutError):
                writer.close()
                return
            parts = start.split(' ')
            if len(parts) != 3 or parts[2] != 'HTTP/1.1':
                await self._respond(writer, 400, '{"error":"bad_request"}')
                return
            method, target = parts[0], parts[1]
            client_ip = self._client_ip(writer, headers)
            if ip in self.trusted_proxies:
                # Behind the proxy: concurrency and rate per forwarded client address.
                refused = self._admit(client_ip) if client_ip not in self.trusted_proxies else None
                if refused:
                    await self._respond(writer, 503 if refused != 'rate_limited' else 429, json.dumps(dict(error=refused)))
                    return
                self.per_ip[ip] -= 1
                if not self.per_ip[ip]:
                    del self.per_ip[ip]
                ip = client_ip
                self.per_ip[ip] = self.per_ip.get(ip, 0) + 1
            if target in ('/healthz', '/readiness'):
                if method != 'GET':
                    await self._respond(writer, 405, '{"error":"method"}')
                elif target == '/healthz':
                    await self._respond(writer, 200, json.dumps(self.health(), sort_keys=True))
                else:
                    await self._respond(writer, 503 if self.draining else 200,
                                        json.dumps(dict(ready=not self.draining)))
                return
            if target != wire.PATH:
                await self._respond(writer, 404, '{"error":"not_found"}')
                return
            ws = await self._upgrade(method, headers, reader, writer)
            if ws is None:
                return
            endpoint = await self._hello(conn, ws, started)
            if endpoint is None:
                return
            await self._serve(endpoint)
        except Exception:
            # Fixed category only; never a traceback with peer bytes in it.
            log.warning('conn=%d event=error category=internal', conn)
        finally:
            if endpoint is not None:
                self._unregister(endpoint)
                ws = endpoint.ws
                log.info('conn=%d event=close role=%s category=%s duration=%.1f bytes_in=%d bytes_out=%d',
                         conn, endpoint.role, endpoint.category, self.clock() - endpoint.started,
                         ws.bytes_in, ws.bytes_out)
            try:
                writer.close()
            except Exception:
                pass
            self.connections.discard(conn)
            self.per_ip[ip] -= 1
            if not self.per_ip[ip]:
                del self.per_ip[ip]

    async def _upgrade(self, method, headers, reader, writer):
        key = headers.get('sec-websocket-key', '')
        try:
            valid_key = len(base64.b64decode(key, validate=True)) == 16
        except (ValueError, TypeError):
            valid_key = False
        if (method != 'GET' or 'websocket' not in header_tokens(headers.get('upgrade'))
                or 'upgrade' not in header_tokens(headers.get('connection'))
                or headers.get('sec-websocket-version') != '13' or not valid_key):
            await self._respond(writer, 426 if method == 'GET' else 405, '{"error":"websocket_required"}')
            return None
        if wire.SUBPROTOCOL not in header_tokens(headers.get('sec-websocket-protocol')):
            await self._respond(writer, 400, '{"error":"unsupported_protocol"}')
            return None
        if self.draining:
            await self._respond(writer, 503, '{"error":"going_away"}')
            return None
        transport = writer.transport
        transport.set_write_buffer_limits(high=self.limits.write_buffer)
        writer.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                      'Sec-WebSocket-Accept: %s\r\nSec-WebSocket-Protocol: %s\r\n\r\n' % (
                          accept_value(key), wire.SUBPROTOCOL)).encode('ascii'))
        await writer.drain()
        return WebSocket(reader, writer, client=False, max_message=self.limits.max_message)

    async def _hello(self, conn, ws, started):
        remaining = self.limits.hello_timeout - (self.clock() - started)
        try:
            opcode, payload = await asyncio.wait_for(ws.recv(), max(.1, remaining))
            if opcode != TEXT:
                raise wire.WorldError('protocol_error')
            role, route, credential = wire.parse_hello(payload.decode('utf-8'))
        except asyncio.TimeoutError:
            await ws.close(wire.CLOSE_CODES['hello_timeout'])
            return None
        except wire.WorldError as error:
            code = str(error) if str(error) in wire.CLOSE_CODES else 'protocol_error'
            await ws.close(wire.CLOSE_CODES[code])
            log.info('conn=%d event=refused category=%s', conn, code)
            return None
        except (WebSocketError, Closed, UnicodeDecodeError):
            ws.abort()
            return None
        if len(self.routes) >= self.limits.max_routes and wire.rendezvous(route, credential) not in self.routes:
            await ws.close(wire.CLOSE_CODES['capacity'])
            return None
        endpoint = Endpoint(conn=conn, role=role, ws=ws, key=wire.rendezvous(route, credential))
        await self._register(endpoint)
        return endpoint

    # ------------------------------------------------------------------ rendezvous
    async def _register(self, endpoint):
        slots = self.routes.setdefault(endpoint.key, {})
        old = slots.get(endpoint.role)
        if old is not None:
            # Newest connection wins (a phone that changed networks reconnects first).
            old.category = 'replaced'
            self._detach(old)
            asyncio.ensure_future(old.ws.close(wire.CLOSE_CODES['replaced']))
        slots[endpoint.role] = endpoint
        other = slots.get('phone' if endpoint.role == 'desktop' else 'desktop')
        log.info('conn=%d event=hello role=%s', endpoint.conn, endpoint.role)
        if other is not None and other.partner is None and endpoint.partner is None:
            endpoint.partner, other.partner = other, endpoint
            self.tunnels += 1
            for side in (other, endpoint):
                try:
                    await side.ws.send_text(wire.event('paired'))
                except Exception:
                    pass
            log.info('conn=%d event=paired peer_conn=%d', endpoint.conn, other.conn)
        else:
            await endpoint.ws.send_text(wire.event('waiting'))

    def _detach(self, endpoint):
        """End this endpoint's session: its partner is closed and reconnects fresh."""
        partner = endpoint.partner
        if partner is not None:
            endpoint.partner = None
            partner.partner = None
            self.tunnels -= 1
            partner.category = 'peer_left'
            asyncio.ensure_future(partner.ws.close(wire.CLOSE_CODES['peer_left']))

    def _unregister(self, endpoint):
        self._detach(endpoint)
        slots = self.routes.get(endpoint.key)
        if slots is not None and slots.get(endpoint.role) is endpoint:
            del slots[endpoint.role]
            if not slots:
                del self.routes[endpoint.key]

    async def _serve(self, endpoint):
        ws = endpoint.ws
        keepalive = asyncio.ensure_future(self._keepalive(endpoint))
        try:
            while True:
                try:
                    opcode, payload = await ws.recv()
                except Closed as closed:
                    if endpoint.category == 'closed':
                        endpoint.category = wire.CLOSE_NAMES.get(closed.code, 'closed')
                    return
                except WebSocketError as error:
                    endpoint.category = 'too_large' if 'large' in str(error) else 'protocol_error'
                    await ws.close(wire.CLOSE_CODES[endpoint.category])
                    return
                partner = endpoint.partner
                if opcode != BINARY or partner is None:
                    # Before rendezvous nothing may be forwarded; afterwards only binary.
                    endpoint.category = 'protocol_error'
                    await ws.close(wire.CLOSE_CODES['protocol_error'])
                    return
                if self.observer is not None:
                    # TEST-ONLY: an observer may also stand in for a malicious relay.
                    altered = self.observer(endpoint.role, payload)
                    if altered is not None:
                        payload = altered
                try:
                    # drain() inside send applies backpressure: we stop reading this
                    # socket until the partner's bounded write buffer empties.
                    await asyncio.wait_for(partner.ws.send_binary(payload), self.limits.stall_timeout)
                except asyncio.TimeoutError:
                    endpoint.category = 'stalled'
                    await ws.close(wire.CLOSE_CODES['peer_left'])
                    return
                except Exception:
                    if endpoint.partner is partner:
                        self._detach(endpoint)
                    endpoint.category = 'peer_left'
                    await ws.close(wire.CLOSE_CODES['peer_left'])
                    return
        finally:
            keepalive.cancel()

    async def _keepalive(self, endpoint):
        ws, limits = endpoint.ws, self.limits
        loop = asyncio.get_running_loop()
        try:
            while not ws.closed:
                await asyncio.sleep(min(limits.ping_interval, 1.0) if endpoint.partner is None and endpoint.role == 'phone'
                                    else limits.ping_interval)
                now = loop.time()
                if endpoint.role == 'phone' and endpoint.partner is None and \
                        self.clock() - endpoint.started >= limits.phone_wait:
                    endpoint.category = 'peer_unavailable'
                    await ws.close(wire.CLOSE_CODES['peer_unavailable'])
                    return
                if now - ws.last_received >= limits.idle_timeout:
                    endpoint.category = 'idle_timeout'
                    await ws.close(wire.CLOSE_CODES['idle_timeout'])
                    return
                if now - ws.last_received >= limits.ping_interval * .5:
                    await ws.ping(b'')
        except (asyncio.CancelledError, Closed):
            pass
        except Exception:
            ws.abort()

    # ------------------------------------------------------------------ lifecycle
    async def start(self, host, port, *, ssl=None):
        self.server = await asyncio.start_server(self.handle, host, port, ssl=ssl,
                                                 limit=8192, reuse_address=True)
        return self.server.sockets[0].getsockname()[1]

    async def shutdown(self, grace=5.0):
        """Readiness goes 503, new connections stop, sessions close with 1001 (going away)."""
        self.draining = True
        if self.server is not None:
            self.server.close()
        closing = []
        for slots in list(self.routes.values()):
            for endpoint in list(slots.values()):
                endpoint.category = 'going_away'
                closing.append(endpoint.ws.close(wire.CLOSE_CODES['going_away']))
        if closing:
            await asyncio.wait_for(asyncio.gather(*closing, return_exceptions=True), grace)
        if self.server is not None:
            try:
                await asyncio.wait_for(self.server.wait_closed(), grace)
            except asyncio.TimeoutError:
                pass


def constant_time_equal(a, b):
    return hmac.compare_digest(a, b)
