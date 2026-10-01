"""Bounded RFC 6455 WebSocket for OLIVE Connect World (standard library only).

Only what World needs: no extensions, binary and text messages, ping/pong and
the close handshake. Every length is checked before any buffer is allocated.
TLS (wss://) comes from the standard ``ssl`` module with normal system trust.
"""
import asyncio
import base64
import hashlib
import os
import struct

GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
CONTINUATION, TEXT, BINARY, CLOSE, PING, PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
DATA_OPCODES = (CONTINUATION, TEXT, BINARY)
CONTROL_OPCODES = (CLOSE, PING, PONG)
MAX_HEADER_BYTES = 8192
MAX_CONTROL = 125
VALID_CLOSE = set(range(1000, 1004)) | set(range(1007, 1012)) | set(range(3000, 5000))


class WebSocketError(Exception):
    """Fixed category codes only; never peer content."""


class Closed(WebSocketError):
    def __init__(self, code=1006, reason=''):
        super().__init__('closed')
        self.code, self.reason = code, reason


def accept_value(key):
    return base64.b64encode(hashlib.sha1(key.encode('ascii') + GUID).digest()).decode('ascii')


def encode_frame(opcode, payload=b'', *, mask, fin=True):
    if type(payload) is not bytes or opcode not in DATA_OPCODES + CONTROL_OPCODES:
        raise WebSocketError('invalid_frame')
    if opcode in CONTROL_OPCODES and (len(payload) > MAX_CONTROL or not fin):
        raise WebSocketError('invalid_control_frame')
    size = len(payload)
    head = bytearray([(0x80 if fin else 0) | opcode])
    bit = 0x80 if mask else 0
    if size < 126:
        head.append(bit | size)
    elif size < 65536:
        head.append(bit | 126)
        head += struct.pack('!H', size)
    else:
        head.append(bit | 127)
        head += struct.pack('!Q', size)
    if not mask:
        return bytes(head) + payload
    key = os.urandom(4)
    return bytes(head) + key + apply_mask(payload, key)


def apply_mask(payload, key):
    if not payload:
        return b''
    # Whole-buffer XOR through big integers; avoids a per-byte Python loop.
    repeated = (key * (len(payload) // 4 + 1))[:len(payload)]
    return (int.from_bytes(payload, 'big') ^ int.from_bytes(repeated, 'big')).to_bytes(len(payload), 'big')


def close_payload(code, reason=''):
    raw = reason.encode('utf-8')[:120]
    return struct.pack('!H', code) + raw


def parse_close(payload):
    if not payload:
        return 1005, ''
    if len(payload) == 1:
        raise WebSocketError('invalid_close')
    code = struct.unpack('!H', payload[:2])[0]
    if code not in VALID_CLOSE:
        raise WebSocketError('invalid_close')
    try:
        reason = payload[2:].decode('utf-8')
    except UnicodeDecodeError:
        raise WebSocketError('invalid_close') from None
    return code, reason


class FrameReader:
    """Incremental frame parser. ``max_payload`` is enforced on the declared length."""

    def __init__(self, *, max_payload, expect_mask):
        self.max_payload = max_payload
        self.expect_mask = expect_mask
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer += data
        # Never hold more than one maximal frame plus its header.
        if len(self.buffer) > self.max_payload + 14 + 65536:
            raise WebSocketError('buffer_limit')

    def next(self):
        """Return (fin, opcode, payload) or None when more bytes are needed."""
        buffer = self.buffer
        if len(buffer) < 2:
            return None
        first, second = buffer[0], buffer[1]
        if first & 0x70:
            raise WebSocketError('reserved_bits')
        fin, opcode = bool(first & 0x80), first & 0x0F
        if opcode not in DATA_OPCODES + CONTROL_OPCODES:
            raise WebSocketError('unknown_opcode')
        masked = bool(second & 0x80)
        if masked != self.expect_mask:
            raise WebSocketError('mask_policy')
        size = second & 0x7F
        offset = 2
        if size == 126:
            if len(buffer) < 4:
                return None
            size = struct.unpack('!H', buffer[2:4])[0]
            offset = 4
            if size < 126:
                raise WebSocketError('non_minimal_length')
        elif size == 127:
            if len(buffer) < 10:
                return None
            size = struct.unpack('!Q', buffer[2:10])[0]
            offset = 10
            if size >> 63 or size < 65536:
                raise WebSocketError('non_minimal_length')
        if opcode in CONTROL_OPCODES and (size > MAX_CONTROL or not fin):
            raise WebSocketError('invalid_control_frame')
        if size > self.max_payload:
            raise WebSocketError('frame_too_large')  # Rejected before the payload arrives.
        if masked:
            offset += 4
        if len(buffer) < offset + size:
            return None
        payload = bytes(buffer[offset:offset + size])
        if masked:
            payload = apply_mask(payload, bytes(buffer[offset - 4:offset]))
        del buffer[:offset + size]
        return fin, opcode, payload


class WebSocket:
    """One established WebSocket over asyncio streams.

    ``recv()`` returns complete (opcode, payload) data messages and answers
    control frames itself. Writes are serialized; ``drain`` gives backpressure.
    """

    def __init__(self, reader, writer, *, client, max_message=262144, read_chunk=65536):
        self.reader, self.writer = reader, writer
        self.client = client
        self.max_message = max_message
        self.frames = FrameReader(max_payload=max_message, expect_mask=not client)
        self.read_chunk = read_chunk
        self.write_lock = asyncio.Lock()
        self.closed = False
        self.close_code = None
        self.close_sent = False
        self.bytes_in = 0
        self.bytes_out = 0
        self.last_received = asyncio.get_running_loop().time()
        self.pongs = 0

    async def _write(self, opcode, payload=b''):
        async with self.write_lock:
            if self.close_sent:
                raise Closed(self.close_code or 1006)
            if opcode == CLOSE:
                self.close_sent = True
            self.writer.write(encode_frame(opcode, payload, mask=self.client))
            if opcode in (BINARY, TEXT):
                self.bytes_out += len(payload)
            await self.writer.drain()

    async def send_binary(self, payload):
        if len(payload) > self.max_message:
            raise WebSocketError('frame_too_large')
        await self._write(BINARY, payload)

    async def send_text(self, text):
        raw = text.encode('utf-8')
        if len(raw) > self.max_message:
            raise WebSocketError('frame_too_large')
        await self._write(TEXT, raw)

    async def ping(self, payload=b''):
        await self._write(PING, payload)

    async def close(self, code=1000, reason='', *, wait=1.0):
        """Send our close frame (once), then wait briefly for the peer's."""
        if not self.close_sent:
            try:
                await asyncio.wait_for(self._write(CLOSE, close_payload(code, reason)), wait)
            except (Exception, asyncio.CancelledError):
                pass
            if self.close_code is None:
                self.close_code = code
        self.closed = True
        self.abort()

    def abort(self):
        self.closed = True
        try:
            self.writer.close()
        except Exception:
            pass

    async def recv(self):
        """Next complete data message as (opcode, payload); raises Closed at the end."""
        message_opcode, parts, size = None, [], 0
        while True:
            frame = self.frames.next()
            if frame is None:
                if self.closed:
                    raise Closed(self.close_code or 1006)
                try:
                    data = await self.reader.read(self.read_chunk)
                except (ConnectionError, OSError):
                    data = b''
                if not data:
                    self.abort()
                    raise Closed(self.close_code or 1006)
                self.last_received = asyncio.get_running_loop().time()
                self.frames.feed(data)
                continue
            fin, opcode, payload = frame
            if opcode == PING:
                try:
                    await self._write(PONG, payload)
                except Closed:
                    pass
                continue
            if opcode == PONG:
                self.pongs += 1
                continue
            if opcode == CLOSE:
                code, reason = parse_close(payload)
                self.close_code = code
                if not self.close_sent:
                    try:
                        await self._write(CLOSE, payload[:2] if payload else b'')
                    except Exception:
                        pass
                self.abort()
                raise Closed(code, reason)
            if opcode == CONTINUATION:
                if message_opcode is None:
                    raise WebSocketError('unexpected_continuation')
            else:
                if message_opcode is not None:
                    raise WebSocketError('interleaved_message')
                message_opcode = opcode
            size += len(payload)
            if size > self.max_message:
                raise WebSocketError('message_too_large')
            parts.append(payload)
            if fin:
                body = b''.join(parts)
                if message_opcode == TEXT:
                    try:
                        body.decode('utf-8')
                    except UnicodeDecodeError:
                        raise WebSocketError('invalid_utf8') from None
                self.bytes_in += len(body)
                return message_opcode, body


async def read_http_head(reader, *, timeout):
    """Read one HTTP head (request or response) of at most MAX_HEADER_BYTES."""
    try:
        raw = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), timeout)
    except asyncio.LimitOverrunError:
        raise WebSocketError('header_too_large') from None
    except asyncio.IncompleteReadError:
        raise WebSocketError('handshake_eof') from None
    if len(raw) > MAX_HEADER_BYTES:
        raise WebSocketError('header_too_large')
    try:
        text = raw.decode('latin-1')
    except UnicodeDecodeError:  # pragma: no cover - latin-1 decodes everything
        raise WebSocketError('invalid_header') from None
    lines = text[:-4].split('\r\n')
    start, headers = lines[0], {}
    if len(lines) > 64:
        raise WebSocketError('invalid_header')
    for line in lines[1:]:
        name, sep, value = line.partition(':')
        if not sep or not name or name != name.strip() or any(c in name for c in ' \t'):
            raise WebSocketError('invalid_header')
        key = name.lower()
        value = value.strip()
        headers[key] = headers[key] + ', ' + value if key in headers else value
    return start, headers


def header_tokens(value):
    return {token.strip().lower() for token in (value or '').split(',') if token.strip()}


def client_request(host_header, path, key, protocol):
    return ('GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
            'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: %s\r\n'
            'User-Agent: OLIVE-World/1\r\n\r\n' % (path, host_header, key, protocol)).encode('ascii')


def check_server_response(start, headers, key, protocol):
    parts = start.split(' ', 2)
    if len(parts) < 2 or parts[0] != 'HTTP/1.1' or parts[1] != '101':
        raise WebSocketError('upgrade_refused')
    if 'websocket' not in header_tokens(headers.get('upgrade')) or 'upgrade' not in header_tokens(headers.get('connection')):
        raise WebSocketError('upgrade_refused')
    if headers.get('sec-websocket-accept') != accept_value(key):
        raise WebSocketError('bad_accept')
    if headers.get('sec-websocket-protocol') != protocol or headers.get('sec-websocket-extensions'):
        raise WebSocketError('protocol_mismatch')


def new_key():
    return base64.b64encode(os.urandom(16)).decode('ascii')
