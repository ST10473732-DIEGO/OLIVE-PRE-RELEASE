"""Outbound relay connection and the byte bridge into an OLIVE Connect channel.

Both devices only ever dial OUT to the relay (wss://, TCP 443 in production),
so World works through NAT, CGNAT and firewalls without port forwarding.
After rendezvous the bridge copies raw bytes between the relay and a local
socket pair whose other end is an ordinary Connect channel: the existing
pinned TLS 1.3 session runs end to end, unchanged, through the relay.
"""
import asyncio
import ssl

from . import wire
from .websocket import (BINARY, TEXT, Closed, WebSocket, WebSocketError, check_server_response,
                        client_request, new_key, read_http_head)

CONNECT_TIMEOUT = 10.0
KEEPALIVE = 25.0       # WebSocket ping cadence: inside common NAT/mobile idle windows, not a flood.
DEAD_AFTER = 70.0      # Nothing received (relay pings every 20 s) -> the path is dead.
LOCAL_BUFFER = 262144  # Bound on bytes queued toward the local Connect channel.


class RelayRefused(Exception):
    """The relay closed with a known category (see wire.CLOSE_CODES)."""
    def __init__(self, category):
        super().__init__(category)
        self.category = category


def category_for(error):
    """Fixed public category for a relay/path failure; never exception text."""
    if isinstance(error, RelayRefused):
        return error.category
    if isinstance(error, Closed):
        return wire.CLOSE_NAMES.get(error.code, 'relay_closed')
    if isinstance(error, ssl.SSLCertVerificationError):
        return 'relay_certificate_invalid'
    if isinstance(error, ssl.SSLError):
        return 'relay_tls_failed'
    if isinstance(error, asyncio.TimeoutError):
        return 'relay_timeout'
    if isinstance(error, WebSocketError):
        return 'relay_protocol_error'
    if isinstance(error, (OSError, ConnectionError)):
        return 'relay_unreachable'
    if isinstance(error, wire.WorldError):
        return str(error)
    return 'world_error'


async def open_relay(url, *, dev=False, test_lan=False, ssl_context=None, timeout=CONNECT_TIMEOUT):
    """TCP (+ TLS with normal certificate validation) + WebSocket upgrade."""
    target = wire.parse_relay_url(url, dev=dev, test_lan=test_lan)
    context = None
    if target.tls:
        context = ssl_context or ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise wire.WorldError('relay_tls_verification_required')
    reader, writer = await asyncio.wait_for(asyncio.open_connection(
        target.host, target.port, ssl=context, server_hostname=target.host if context else None,
        limit=65536), timeout)
    try:
        key = new_key()
        writer.write(client_request(target.host_header, target.path, key, wire.SUBPROTOCOL))
        await writer.drain()
        start, headers = await read_http_head(reader, timeout=timeout)
        check_server_response(start, headers, key, wire.SUBPROTOCOL)
        return WebSocket(reader, writer, client=True, max_message=wire.MAX_MESSAGE)
    except BaseException:
        writer.close()
        raise


async def rendezvous(ws, role, route, credential, *, on_waiting=None, timeout=None):
    """Send the hello and wait for 'paired'. A desktop waits indefinitely (keepalive runs)."""
    await ws.send_text(wire.hello(role, route, credential))
    keepalive = asyncio.ensure_future(_keepalive(ws))
    try:
        async def wait():
            while True:
                try:
                    opcode, payload = await ws.recv()
                except Closed as closed:
                    raise RelayRefused(wire.CLOSE_NAMES.get(closed.code, 'relay_closed')) from None
                if opcode != TEXT:
                    raise wire.WorldError('relay_protocol_error')
                event = wire.parse_event(payload.decode('utf-8'))
                if event == 'paired':
                    return
                if on_waiting is not None:
                    on_waiting()
        if timeout is None:
            await wait()
        else:
            await asyncio.wait_for(wait(), timeout)
    finally:
        keepalive.cancel()


async def _keepalive(ws, *, interval=KEEPALIVE, dead_after=DEAD_AFTER):
    loop = asyncio.get_running_loop()
    try:
        while not ws.closed:
            await asyncio.sleep(min(interval, dead_after / 3))
            if loop.time() - ws.last_received >= dead_after:
                ws.abort()  # The reader then sees EOF and the path is retired.
                return
            await ws.ping(b'')
    except (asyncio.CancelledError, Closed, WebSocketError, OSError):
        pass


async def bridge(ws, sock, *, keepalive=KEEPALIVE, dead_after=DEAD_AFTER):
    """Copy bytes both ways until either side ends. Returns a fixed reason.

    Backpressure: each direction awaits the other side's drain, so neither the
    relay nor this process accumulates more than one bounded buffer per side.
    """
    sock.setblocking(False)
    reader, writer = await asyncio.open_connection(sock=sock, limit=wire.CHUNK)
    writer.transport.set_write_buffer_limits(high=LOCAL_BUFFER)

    async def up():
        while True:
            data = await reader.read(wire.CHUNK)
            if not data:
                return 'local_closed'
            await ws.send_binary(data)

    async def down():
        while True:
            try:
                opcode, payload = await ws.recv()
            except Closed as closed:
                return wire.CLOSE_NAMES.get(closed.code, 'relay_closed')
            if opcode != BINARY:
                return 'relay_protocol_error'
            writer.write(payload)
            await writer.drain()

    async def alive():
        await _keepalive(ws, interval=keepalive, dead_after=dead_after)
        return 'path_dead'

    tasks = [asyncio.ensure_future(c) for c in (up(), down(), alive())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        task = next(iter(done))
        try:
            reason = task.result()
        except (WebSocketError, OSError, ConnectionError):
            reason = 'path_failed'
        return reason
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await ws.close(1000)
        try:
            writer.close()
        except Exception:
            pass
