"""Dedicated opt-in LAN transport. Bounded threads, queues and fresh TLS per socket."""
from collections import deque
from contextlib import nullcontext, contextmanager
from concurrent.futures import Future
import errno
import ipaddress
import json
import logging
import queue
import select
import socket
import threading
import time

from OpenSSL import SSL
from cryptography.hazmat.primitives import serialization

from .contracts import ConnectError, RequestEnvelope, canonical, _unique_object
from .discovery import LocalDiscovery, interfaces
from .network_diagnostics import ChannelDiagnostics
from .network_wire import (HEADER, REQUEST, RESPONSE, CLOSE, HELLO, SYNC_REQUEST, SYNC_RESPONSE, frame, header,
                           require_current, tls_context, FILE_REQUEST, FILE_RESPONSE,
                           INFERENCE_REQUEST, INFERENCE_RESPONSE, STUDIO_REQUEST, STUDIO_RESPONSE,
                           NOTES_REQUEST, NOTES_RESPONSE, DRAW_REQUEST, DRAW_RESPONSE,
                           CHAT_REQUEST, CHAT_RESPONSE)

DIRECT, WORLD = 'direct', 'world'
CONNECT_TIMEOUT = 3.0
HANDSHAKE_TIMEOUT = 3.0
FRAME_TIMEOUT = 3.0
WRITE_TIMEOUT = 2.0
# World paths cross the internet (cellular uplinks included). Only their per-frame,
# handshake and write deadlines are relaxed; limits and the idle timeout are not.
WORLD_TIME_SCALE = 5
REQUEST_TIMEOUT = 5.0
IDLE_TIMEOUT = 60.0
# A peer that lost a path silently (Wi-Fi off: its FIN never arrives) leaves a
# channel that looks current until IDLE_TIMEOUT. Before such a channel may block
# a newly authenticated one, it must answer one heartbeat within this window.
LIVENESS_TIMEOUT = 2.0
MAX_CONNECTIONS = 8
MAX_PENDING = 8
PEER_CLOSED_ERRNOS = frozenset(getattr(errno, name) for name in (
    'ECONNRESET', 'ECONNABORTED', 'ENOTCONN', 'EPIPE',
    'WSAECONNRESET', 'WSAECONNABORTED', 'WSAENOTCONN') if hasattr(errno, name))
# Path ownership decisions: fixed words, device-ID prefixes and generations only.
paths_log = logging.getLogger('olive.connect.paths')


def _short(value):
    return (value or '-')[:8]


class Budget:
    def __init__(self, count, window, clock=time.monotonic):
        self.count, self.window, self.clock = count, window, clock
        self.events = deque()

    def take(self):
        now = self.clock()
        while self.events and self.events[0] <= now - self.window:
            self.events.popleft()
        if len(self.events) >= self.count:
            return False
        self.events.append(now)
        return True


class Channel:
    def __init__(self, owner, sock, expected=None, endpoint=None, *, path=DIRECT, route_peer=None):
        self.owner, self.sock, self.expected = owner, sock, expected
        self.outbound = expected is not None
        self.endpoint = endpoint
        # Connect World: the same TLS session over a relay byte stream. The path
        # never changes authority; route_peer pins the only identity this
        # World route may authenticate as (a route belongs to one pair).
        self.path = path
        self.route_peer = route_peer
        self.scale = WORLD_TIME_SCALE if path == WORLD else 1
        self.peer = None
        self.public = None
        self.tls = None
        self.stop = threading.Event()
        # Protected by owner.lock; explicit local intent outlives worker cleanup.
        self.locally_disconnected = False
        self.graceful_disconnect = False
        self.peer_closed = False  # Latched EOF/reset for this exact socket only.
        self.ready = Future()
        self.writes = queue.Queue(MAX_PENDING)
        self.pending = {}
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.run, name='olive-connect-channel', daemon=True)
        self.last_latency_ms = None
        self.last_inbound = None  # Monotonic time of the last bytes read on this socket.
        self.failure_category = None  # Transient diagnostics, never provider text.
        self.diagnostics = ChannelDiagnostics()
        self.authority = threading.local()

    @contextmanager
    def authority_snapshot(self, db):
        """Reuse the dispatcher's pinned identity snapshot for this thread only.

        A second reader can deadlock behind a pending writer whose commit is
        blocked by this very snapshot. Stop and certificate checks still run.
        No connection or snapshot outlives the dispatch transaction.
        """
        previous = getattr(self.authority, 'db', None)
        self.authority.db = db
        try:
            yield
        finally:
            self.authority.db = previous

    @property
    def generation(self):
        return self.diagnostics.generation

    def debug_snapshot(self):
        return dict(self.diagnostics.snapshot(), stopped=self.stop.is_set(), peer_closed=self.peer_closed,
            locally_disconnected=self.locally_disconnected, graceful_disconnect=self.graceful_disconnect,
            worker_alive=self.thread.is_alive(), socket_open=self.sock.fileno() != -1,
            network_stopping=self.owner.stopping.is_set())

    def check(self):
        if self.stop.is_set() or self.owner.stopping.is_set():
            raise ConnectError('connection_closed')
        if self.public is not None:
            self.owner.service.require_paired_identity(self.public, timeout=.25,
                db=getattr(self.authority, 'db', None))
            require_current(self.public)

    def io(self, action, deadline):
        while True:
            self.check()
            if time.monotonic() >= deadline:
                raise ConnectError('connection_timeout')
            try:
                return action()
            except (SSL.WantReadError, SSL.WantWriteError) as error:
                select.select([self.sock] if isinstance(error, SSL.WantReadError) else [],
                              [self.sock] if isinstance(error, SSL.WantWriteError) else [], [],
                              min(.05, max(0, deadline - time.monotonic())))

    def write(self, raw):
        deadline = time.monotonic() + WRITE_TIMEOUT * self.scale
        offset = 0
        while offset < len(raw):
            sent = self.io(lambda: self.tls.send(raw[offset:]), deadline)
            if not sent:
                raise ConnectError('connection_closed')
            offset += sent

    def file_request(self, raw):
        from .file_protocol import FileRequest
        request, _ = FileRequest.decode(raw)
        if request.source_device_id != self.owner.service.local_id or request.target_device_id != self.peer:
            raise ConnectError('source_mismatch')
        self.check()
        future = Future()
        future.sync_protocol = 'olive-files/1'
        with self.lock:
            if len(self.pending) >= MAX_PENDING or request.request_id in self.pending:
                raise ConnectError('backpressure')
            self.pending[request.request_id] = future
            try:
                self.writes.put_nowait(frame(FILE_REQUEST, raw))
            except queue.Full:
                self.pending.pop(request.request_id)
                raise ConnectError('backpressure') from None
        try:
            return future.result(timeout=REQUEST_TIMEOUT)
        except TimeoutError:
            # A file deadline is scoped to the transfer, not a shared channel close.
            raise ConnectError('file_request_timeout') from None
        finally:
            with self.lock:
                self.pending.pop(request.request_id, None)

    def sync_request(self, raw, *, admission=None):
        return self.request(raw, _sync=True, _admission=admission)

    def inference_request(self, raw, timeout=REQUEST_TIMEOUT):
        from .inference_protocol import InferenceRequest, PROTOCOL
        request = InferenceRequest.decode(raw)
        if request.source_device_id != self.owner.service.local_id or request.target_device_id != self.peer:
            raise ConnectError('source_mismatch')
        self.check()
        future = Future()
        future.sync_protocol = PROTOCOL
        future.job_id = request.job_id
        with self.lock:
            if len(self.pending) >= MAX_PENDING or request.request_id in self.pending:
                raise ConnectError('busy')
            self.pending[request.request_id] = future
            try:
                self.writes.put_nowait(frame(INFERENCE_REQUEST, raw))
            except queue.Full:
                self.pending.pop(request.request_id)
                raise ConnectError('busy') from None
        try:
            return future.result(timeout=min(timeout, REQUEST_TIMEOUT))
        except TimeoutError:
            raise ConnectError('connection_lost') from None
        finally:
            with self.lock:
                self.pending.pop(request.request_id, None)

    def alive(self, timeout=LIVENESS_TIMEOUT):
        """True when this authenticated channel still reaches its peer now.

        One read-only olive-inference/1 ``status`` exchange: the C7 heartbeat
        every Connect peer answers (a phone with its fixed non-host reply), with
        no permission and no job. Any bytes read meanwhile also prove it.
        """
        from .inference_protocol import request
        if self.stop.is_set() or self.peer is None:
            return False
        since = time.monotonic()
        try:
            probe = request(self.owner.service.local_id, self.peer, 'status', now=int(self.owner.service.clock()))
            self.inference_request(probe.encode(), timeout=timeout)
            return not self.stop.is_set()
        except ConnectError:
            pass
        inbound = self.last_inbound
        return not self.stop.is_set() and inbound is not None and inbound > since

    def studio_request(self, raw):
        from .studio_protocol import StudioRequest, PROTOCOL
        request = StudioRequest.decode(raw)
        if request.source_device_id != self.owner.service.local_id or request.target_device_id != self.peer:
            raise ConnectError('invalid_request')
        self.check()
        future = Future()
        future.sync_protocol = PROTOCOL
        future.studio_request = request
        with self.lock:
            if len(self.pending) >= MAX_PENDING or request.request_id in self.pending:
                raise ConnectError('busy')
            self.pending[request.request_id] = future
            try:
                self.writes.put_nowait(frame(STUDIO_REQUEST, raw))
            except queue.Full:
                self.pending.pop(request.request_id)
                raise ConnectError('busy') from None
        try:
            return future.result(timeout=REQUEST_TIMEOUT)
        except TimeoutError:
            raise ConnectError('connection_lost') from None
        finally:
            with self.lock:
                self.pending.pop(request.request_id, None)

    def notes_request(self, raw):
        """One olive-notes/1 exchange. A timeout fails this request only."""
        from ..notes import protocol as notes_protocol
        request = notes_protocol.decode_request(raw)
        if request['source_device_id'] != self.owner.service.local_id or request['target_device_id'] != self.peer:
            raise ConnectError('source_mismatch')
        self.check()
        future = Future()
        future.sync_protocol = notes_protocol.PROTOCOL
        with self.lock:
            if len(self.pending) >= MAX_PENDING or request['request_id'] in self.pending:
                raise ConnectError('backpressure')
            self.pending[request['request_id']] = future
            try:
                self.writes.put_nowait(frame(NOTES_REQUEST, raw))
            except queue.Full:
                self.pending.pop(request['request_id'])
                raise ConnectError('backpressure') from None
        try:
            return future.result(timeout=REQUEST_TIMEOUT)
        except TimeoutError:
            raise ConnectError('notes_request_timeout') from None
        finally:
            with self.lock:
                self.pending.pop(request['request_id'], None)

    def draw_request(self, raw):
        """One olive-draw/1 exchange. A timeout fails this request only."""
        from ..draw import protocol as draw_protocol
        request = draw_protocol.decode_request(raw)
        if request['source_device_id'] != self.owner.service.local_id or request['target_device_id'] != self.peer:
            raise ConnectError('source_mismatch')
        self.check()
        future = Future()
        future.sync_protocol = draw_protocol.PROTOCOL
        with self.lock:
            if len(self.pending) >= MAX_PENDING or request['request_id'] in self.pending:
                raise ConnectError('backpressure')
            self.pending[request['request_id']] = future
            try:
                self.writes.put_nowait(frame(DRAW_REQUEST, raw))
            except queue.Full:
                self.pending.pop(request['request_id'])
                raise ConnectError('backpressure') from None
        try:
            return future.result(timeout=REQUEST_TIMEOUT * 3)
        except TimeoutError:
            raise ConnectError('draw_request_timeout') from None
        finally:
            with self.lock:
                self.pending.pop(request['request_id'], None)

    def chat_request(self, raw, timeout=20.0):
        """Client side of one olive-chat/1 exchange (a phone's role). Send only to a
        computer that listed olive-chat/1 in its protocol probe."""
        from . import chat_protocol as cp
        value, _ = cp.unpack(raw)
        if value.get('source_device_id') != self.owner.service.local_id or value.get('target_device_id') != self.peer:
            raise ConnectError('source_mismatch')
        self.check()
        future = Future()
        future.sync_protocol = cp.PROTOCOL
        request_id = value['request_id']
        with self.lock:
            if len(self.pending) >= MAX_PENDING or request_id in self.pending:
                raise ConnectError('backpressure')
            self.pending[request_id] = future
            try:
                self.writes.put_nowait(frame(CHAT_REQUEST, raw))
            except queue.Full:
                self.pending.pop(request_id)
                raise ConnectError('backpressure') from None
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            raise ConnectError('chat_request_timeout') from None
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def request(self, raw, timeout=REQUEST_TIMEOUT, *, _sync=False, _admission=None):
        if _sync:
            from ..sync.records import SyncRequest
            request = SyncRequest.decode(raw)
        else:
            request = RequestEnvelope.decode(raw)
        if request.source_device_id != self.owner.service.local_id or request.target_device_id != self.peer:
            raise ConnectError('source_mismatch')
        self.check()
        future = Future()
        with (_admission() if _admission else nullcontext()):
            with self.lock:
                if len(self.pending) >= MAX_PENDING or request.request_id in self.pending:
                    raise ConnectError('backpressure')
                future.sync_protocol = 'olive-sync/1' if _sync else 'olive-connect/1'
                self.pending[request.request_id] = future
                try:
                    self.writes.put_nowait(frame(SYNC_REQUEST if _sync else REQUEST, raw))
                except queue.Full:
                    self.pending.pop(request.request_id)
                    raise ConnectError('backpressure') from None
        start = time.monotonic()
        try:
            response = future.result(timeout=min(timeout, REQUEST_TIMEOUT))
            if request.capability == 'connect.ping' and response.get('state') == 'completed':
                self.last_latency_ms = (time.monotonic() - start) * 1000
            return response
        except TimeoutError:
            self.close('request_timeout')
            raise ConnectError('request_timeout') from None
        finally:
            with self.lock:
                self.pending.pop(request.request_id, None)

    def process(self, kind, payload):
        self.check()
        allowed = (self.owner.allow_chat_message(self.peer) if kind in (CHAT_REQUEST, CHAT_RESPONSE)
                   else self.owner.allow_notes_message(self.peer) if kind in (NOTES_REQUEST, NOTES_RESPONSE)
                   else self.owner.allow_draw_message(self.peer) if kind in (DRAW_REQUEST, DRAW_RESPONSE)
                   else self.owner.allow_studio_message(self.peer) if kind in (STUDIO_REQUEST, STUDIO_RESPONSE)
                   else self.owner.allow_inference_message(self.peer) if kind in (INFERENCE_REQUEST, INFERENCE_RESPONSE)
                   else self.owner.allow_file_message(self.peer) if kind in (FILE_REQUEST, FILE_RESPONSE)
                   else self.owner.allow_message(self.peer))
        if not allowed:
            raise ConnectError('rate_limited')
        if kind == CLOSE:
            self.diagnostics.closed('peer_close')
            raise ConnectError('connection_closed')
        if kind == HELLO:
            raise ConnectError('unexpected_hello')
        if kind == CHAT_REQUEST:
            chat = getattr(self.owner.service, 'chat', None)
            if chat is None:
                raise ConnectError('capability_unavailable')  # Never advertised; a peer that sends it anyway is closed.
            chat.receive(payload, self, lambda raw: self.write(frame(CHAT_RESPONSE, raw)))
            return
        if kind == CHAT_RESPONSE:
            # Only a correlated answer to our own chat_request; anything else closes the channel.
            from . import chat_protocol as cp
            try:
                request_id = cp.unpack(payload)[0]['request_id']
            except Exception:
                raise ConnectError('invalid_response') from None
            with self.lock:
                future = self.pending.get(request_id) if type(request_id) is str else None
                if future is None or future.done() or getattr(future, 'sync_protocol', '') != cp.PROTOCOL:
                    raise ConnectError('invalid_response')
                future.set_result(payload)
            return
        if kind == NOTES_REQUEST:
            notes = self.owner.service.notes
            if notes is None:
                from ..notes import protocol as notes_protocol
                self.write(frame(NOTES_RESPONSE, notes_protocol.encode_response(None, error='capability_unavailable')))
            else:
                notes.receive(payload, self, lambda raw: self.write(frame(NOTES_RESPONSE, raw)))
        elif kind == NOTES_RESPONSE:
            from ..notes import protocol as notes_protocol
            try:
                response = notes_protocol.decode_response(payload)
            except notes_protocol.NotesProtocolError:
                raise ConnectError('invalid_response') from None
            with self.lock:
                future = self.pending.get(response['request_id']) if response['request_id'] else None
                if future is not None:
                    if future.done() or getattr(future, 'sync_protocol', '') != notes_protocol.PROTOCOL:
                        raise ConnectError('invalid_response')
                    future.set_result(response)
                # A late answer after a local timeout is inert: CRDT resend is idempotent.
        elif kind == DRAW_REQUEST:
            draw = getattr(self.owner.service, 'draw', None)
            if draw is None:
                from ..draw import protocol as draw_protocol
                self.write(frame(DRAW_RESPONSE, draw_protocol.encode_response(None, error='capability_unavailable')))
            else:
                draw.receive(payload, self, lambda raw: self.write(frame(DRAW_RESPONSE, raw)))
        elif kind == DRAW_RESPONSE:
            from ..draw import protocol as draw_protocol
            try:
                response = draw_protocol.decode_response(payload)
            except draw_protocol.DrawProtocolError:
                raise ConnectError('invalid_response') from None
            with self.lock:
                future = self.pending.get(response['request_id']) if response['request_id'] else None
                if future is not None:
                    if future.done() or getattr(future, 'sync_protocol', '') != draw_protocol.PROTOCOL:
                        raise ConnectError('invalid_response')
                    future.set_result(response)
                # A late answer after a local timeout is inert: record resend is idempotent.
        elif kind == STUDIO_REQUEST:
            studio = self.owner.service.studio
            if studio is None:
                raise ConnectError('capability_unavailable')
            studio.receive(payload, self, lambda raw: self.write(frame(STUDIO_RESPONSE, raw)))
        elif kind == STUDIO_RESPONSE:
            from .studio_protocol import response as decode_studio, validate_result, PROTOCOL
            response = decode_studio(payload)
            with self.lock:
                future = self.pending.get(response['request_id'])
                if future is not None:
                    if future.done() or getattr(future, 'sync_protocol', '') != PROTOCOL:
                        raise ConnectError('invalid_request')
                    if response['error'] is None:
                        validate_result(future.studio_request, response['result'])
                    future.set_result(response)
        elif kind == INFERENCE_REQUEST:
            inference = self.owner.service.inference
            if inference is None:
                # Like a phone, a computer without Remote AI still answers, so a
                # peer's heartbeat never drops the channel. Malformed still closes.
                from .inference_protocol import InferenceRequest, PROTOCOL
                request = InferenceRequest.decode(payload)
                self.write(frame(INFERENCE_RESPONSE, canonical(dict(protocol_version=PROTOCOL,
                    request_id=request.request_id, job_id=request.job_id, result=None, error='device_unavailable'))))
                return
            inference.receive(payload, self, lambda raw: self.write(frame(INFERENCE_RESPONSE, raw)))
        elif kind == INFERENCE_RESPONSE:
            from .inference_protocol import response as decode_response, PROTOCOL
            response = decode_response(payload)
            with self.lock:
                future = self.pending.get(response['request_id'])
                if future is not None:
                    if (future.done() or getattr(future, 'sync_protocol', '') != PROTOCOL
                            or future.job_id != response['job_id']):
                        raise ConnectError('stream_invalid')
                    future.set_result(response)
                # A correlated caller may have cancelled/timed out. No unsolicited
                # stream can attach to a different job or create Chat content.
        elif kind == FILE_REQUEST:
            response = self.owner.service.files.receive(payload, self.peer, self.public)
            self.write(frame(FILE_RESPONSE, canonical(response)))
        elif kind == FILE_RESPONSE:
            from .file_protocol import response as decode_response
            response = decode_response(payload)
            with self.lock:
                future = self.pending.get(response['request_id'])
                if future is not None:
                    if future.done() or getattr(future, 'sync_protocol', '') != 'olive-files/1':
                        raise ConnectError('invalid_file_response')
                    future.set_result(response)
                # A late bounded acknowledgement after a file-only timeout is inert.
        elif kind == SYNC_REQUEST:
            sync = self.owner.service.sync
            if sync is None:
                raise ConnectError('sync_unavailable')
            response = sync.receive(payload, self.peer, self.public)
            self.write(frame(SYNC_RESPONSE, canonical(response)))
        elif kind == REQUEST:
            # This is the sole network dispatch entry. TLS supplies public and peer.
            response = self.owner.service._receive(payload, peer_device_id=self.peer, public=self.public)
            self.write(frame(RESPONSE, canonical(response)))
        else:
            try:
                response = json.loads(payload, object_pairs_hook=_unique_object,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if (type(response) is not dict or response.get('protocol_version') != ('olive-sync/1' if kind == SYNC_RESPONSE else 'olive-connect/1')
                        or response.get('state') not in ('completed', 'rejected')
                        or set(response) != {'protocol_version', 'request_id', 'state',
                            'result' if response['state'] == 'completed' else 'error'}):
                    raise ValueError()
                with self.lock:
                    future = self.pending.get(response['request_id'])
                    if future is None or future.done() or getattr(future, 'sync_protocol', 'olive-connect/1') != response['protocol_version']:
                        raise ValueError()
                    # Untrusted peer result is returned to the local caller only, never logged.
                    future.set_result(response)
            except Exception:
                raise ConnectError('invalid_response') from None

    def run(self):
        reason = 'connection_closed'
        try:
            self.check()
            if self.outbound:
                if self.path == DIRECT:
                    self.diagnostics.at('connect')
                    self.sock.settimeout(CONNECT_TIMEOUT)
                    self.sock.bind((self.owner.interface.address, 0))
                    self.sock.connect(self.endpoint)
                self.check()
                with self.owner.lock:
                    self.check()
                    self.owner.states[self.expected] = dict(state='authenticating', error=None)
                self.owner.audit(self.expected, 'connection_started')
            self.diagnostics.at('tls')
            ctx, peers = tls_context(self.owner.service, self.expected or self.route_peer,
                                     local=self.owner.local_identity)
            self.sock.setblocking(False)
            self.tls = SSL.Connection(ctx, self.sock)
            (self.tls.set_connect_state if self.outbound else self.tls.set_accept_state)()
            self.io(self.tls.do_handshake, time.monotonic() + HANDSHAKE_TIMEOUT * self.scale)
            cert = self.tls.get_peer_certificate().to_cryptography().public_bytes(serialization.Encoding.DER)
            self.public = peers.get(cert)
            if self.public is None or self.tls.get_protocol_version_name() != 'TLSv1.3':
                raise ConnectError('identity_mismatch')
            self.peer = self.public['device_id']
            if self.route_peer is not None and self.peer != self.route_peer:
                raise ConnectError('identity_mismatch')  # Another pair's route: never accepted.
            self.check()
            # TLS 1.3 clients may finish locally before the server rejects their
            # certificate. An encrypted fixed hello proves both verifiers finished.
            hello = frame(HELLO)
            self.diagnostics.at('hello')
            self.write(hello)
            received = bytearray()
            deadline = time.monotonic() + HANDSHAKE_TIMEOUT * self.scale
            while len(received) < len(hello):
                part = self.io(lambda: self.tls.recv(len(hello) - len(received)), deadline)
                if not part:
                    self.peer_closed = True
                    raise ConnectError('connection_closed')
                received.extend(part)
            if bytes(received) != hello:
                raise ConnectError('unsupported_protocol')
            self.owner.adopt(self)
            self.ready.set_result(self)
            buffer = bytearray()
            started = None
            last = time.monotonic()
            while True:
                self.diagnostics.at('authority')
                self.check()
                try:
                    self.diagnostics.at('write')
                    self.write(self.writes.get_nowait())
                except queue.Empty:
                    pass
                now = time.monotonic()
                if now - last >= IDLE_TIMEOUT or (started is not None and now - started >= FRAME_TIMEOUT * self.scale):
                    self.diagnostics.closed('idle_timeout' if now - last >= IDLE_TIMEOUT else 'frame_timeout')
                    raise ConnectError('connection_timeout')
                try:
                    self.diagnostics.at('read')
                    data = self.tls.recv(16384)
                except SSL.WantReadError:
                    select.select([self.sock], [], [], .05)
                    continue
                if not data:
                    self.peer_closed = True
                    raise ConnectError('connection_closed')
                last = self.last_inbound = now
                if not buffer:
                    started = now
                buffer.extend(data)
                while len(buffer) >= HEADER.size:
                    size, kind = header(buffer[:HEADER.size])
                    if len(buffer) < HEADER.size + size:
                        break
                    payload = bytes(buffer[HEADER.size:HEADER.size + size])
                    del buffer[:HEADER.size + size]
                    self.diagnostics.at('dispatch')
                    self.process(kind, payload)
                    started = time.monotonic() if buffer else None
        except ConnectError as error:
            self.diagnostics.failed(error, peer_closed=self.peer_closed)
            reason = str(error)
        except Exception as error:
            # OpenSSL can consume EOF before explicit disconnect sets its stop
            # flag. Retain that terminal state instead of requiring a new EOF.
            if isinstance(error, SSL.ZeroReturnError) or (
                    isinstance(error, SSL.SysCallError) and (
                        error.args == (-1, 'Unexpected EOF') or
                        (error.args and error.args[0] in PEER_CLOSED_ERRNOS))):
                self.peer_closed = True
            self.diagnostics.failed(error, peer_closed=self.peer_closed)
            self.failure_category = type(error).__name__
            reason = 'tls_or_connection_failed'
        finally:
            # Revoke authority before publishing EOF. A peer waiting for EOF
            # may immediately establish a fresh authenticated channel.
            self.stop.set()
            self.diagnostics.at('retirement')
            try:
                if not self.ready.done():
                    self.ready.set_exception(ConnectError(reason))
                with self.lock:
                    for future in self.pending.values():
                        if not future.done():
                            future.set_exception(ConnectError('connection_closed'))
                self.owner.finished(self, reason)
                if self.peer is not None:
                    paths_log.info('channel closed peer=%s path=%s gen=%s reason=%s category=%s',
                        _short(self.peer), self.path, self.generation[:8], reason,
                        (self.diagnostics.snapshot()['terminal'] or {}).get('category'))
                if self.graceful_disconnect and not self.peer_closed:
                    self.peer_closed = self.drain_disconnect()
            finally:
                self.close(None)
                self.sock.close()
                with self.owner.lock:
                    self.owner.workers.discard(self)
                    snapshot = self.debug_snapshot()
                    snapshot.pop('worker_alive')  # Historical event, not a live thread observation.
                    snapshot['retired'] = True
                    self.owner.retired.append((self.peer or self.expected, snapshot))

    def drain_disconnect(self):
        """Worker-only half-close barrier; no TLS/application work after this.

        FIN makes the peer's TLS reader retire its channel. Its EOF is published
        only after authority cleanup above. Discard in-flight encrypted bytes;
        they cannot become responses or actions on a disconnected channel.
        """
        deadline = time.monotonic() + WRITE_TIMEOUT
        try:
            self.sock.shutdown(socket.SHUT_WR)
            while time.monotonic() < deadline:
                readable, _, _ = select.select([self.sock], [], [], max(0, deadline - time.monotonic()))
                if not readable:
                    break
                try:
                    if not self.sock.recv(16384):
                        return True
                except (BlockingIOError, InterruptedError):
                    continue
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # A peer reset also retires its transport.
            return True
        except OSError as error:
            # An established socket can retire before TLS consumes its EOF.
            # ENOTCONN is terminal state, not a missed retirement notification.
            return error.errno in PEER_CLOSED_ERRNOS
        return False

    def close(self, category='local_disconnect'):
        if category is not None:
            self.diagnostics.closed(category)
        self.stop.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        # Only the owning worker closes the descriptor after its final TLS call.
        # Closing here could recycle the fd while OpenSSL still holds its number.
        self.last_latency_ms = None


class LocalNetwork:
    def __init__(self, service, address, *, port=0, discovery=True):
        candidates = [i for i in interfaces() if i.address == address]
        if len(candidates) != 1:
            raise ConnectError('select_active_local_interface')
        if type(port) is not int or not 0 <= port <= 65535:
            raise ConnectError('invalid_port')
        self.interface = candidates[0]
        self.service = service
        # Fail before listening if the vault or local certificate is unavailable.
        public = service.cryptographic_identity()
        require_current(public)
        self.local_identity = (public, service.identities.key_store.load(public))
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.channels = {}
        self.workers = set()
        self.retired = deque(maxlen=16)
        self.audit_failures = 0
        self.states = {}
        self.rates = {}
        self.file_rates = {}
        self.inference_rates = {}
        self.studio_rates = {}
        self.notes_rates = {}
        self.draw_rates = {}
        self.chat_rates = {}
        self.targets = {}
        self.attempts = Budget(12, 60)
        self.world_attempts = Budget(30, 60)
        self.audit_budget = Budget(30, 60)
        self.discovery = None
        from .listener import listener_socket
        self.listener = listener_socket(address)
        try:
            self.listener.bind((address, port))
            self.listener.listen(MAX_CONNECTIONS)
            self.listener.settimeout(.1)
            self.port = self.listener.getsockname()[1]
            if discovery:
                self.discovery = LocalDiscovery(self.interface, self.port)
            self.thread = threading.Thread(target=self.accept, name='olive-connect-listener', daemon=True)
            self.thread.start()
            self.reconnector = threading.Thread(target=self.reconnect, name='olive-connect-reconnect', daemon=True)
            self.reconnector.start()
        except BaseException:
            self.listener.close()
            if self.discovery:
                self.discovery.close()
            raise

    def audit(self, peer, event):
        with self.lock:
            if not self.audit_budget.take():
                return
        try:
            with self.service.repository.transaction(timeout=.25) as db:
                self.service.repository.audit(db, peer, None, None, int(self.service.clock()), event)
        except Exception:
            with self.lock:
                self.audit_failures = min(65535, self.audit_failures + 1)
            # Storage contention cannot strand socket workers or leak provider text.
            import logging
            logging.getLogger(__name__).warning('Connect audit unavailable')

    def accept(self):
        while not self.stopping.is_set():
            try:
                sock, address = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self.lock:
                if (self.stopping.is_set() or not self.interface.permits(address[0])
                        or len(self.workers) >= MAX_CONNECTIONS or not self.attempts.take()):
                    sock.close()
                    continue
                channel = Channel(self, sock)
                self.workers.add(channel)
                channel.thread.start()

    def connect(self, peer, address, port, *, retries=0, _automatic=False):
        if type(retries) is not int or not 0 <= retries <= 3:
            raise ConnectError('invalid_retry_limit')
        if not self.interface.permits(address) or type(port) is not int or not 1 <= port <= 65535:
            raise ConnectError('endpoint_not_local')
        for attempt in range(retries + 1):
            if self.stopping.is_set():
                raise ConnectError('connection_closed')
            record = self.service.device(peer, timeout=.25)
            self.service.require_paired_identity(record.get('public_identity'), timeout=.25)
            require_current(record['public_identity'])
            with self.lock:
                if (peer in self.channels and not self.channels[peer].stop.is_set()
                        and self.channels[peer].path == DIRECT):
                    return self.channels[peer]
                if self.stopping.is_set() or (_automatic and peer not in self.targets):
                    raise ConnectError('connection_closed')
                # An explicit retry may race the reconnect worker before either
                # handshake is adopted. Share that exact in-flight connection:
                # two same-direction sockets can otherwise win in opposite order
                # at the endpoints and retire each other's selected channel.
                pending = [candidate for candidate in self.workers if candidate.outbound
                           and candidate.path == DIRECT and candidate.expected == peer and not candidate.stop.is_set()
                           and not candidate.ready.done()]
                if pending:
                    if len(pending) != 1 or pending[0].endpoint != (address, port):
                        raise ConnectError('backpressure')
                    channel = pending[0]
                else:
                    if len(self.workers) >= MAX_CONNECTIONS or not self.attempts.take():
                        raise ConnectError('backpressure')
                    self.states[peer] = dict(state='connecting', error=None)
                    sock = socket.socket(self.listener.family)
                    channel = Channel(self, sock, peer, (address, port))
                    self.workers.add(channel)
                    try:
                        channel.thread.start()
                    except Exception:
                        self.workers.discard(channel)
                        sock.close()
                        raise
            try:
                result = channel.ready.result(timeout=CONNECT_TIMEOUT + 2 * HANDSHAKE_TIMEOUT + 1)
                if not _automatic:
                    with self.lock:
                        if channel.stop.is_set() or self.stopping.is_set():
                            raise ConnectError('connection_closed')
                        self.targets[peer] = dict(address=address, port=port, attempts=0,
                                                  next=time.monotonic() + .5)
                return result
            except Exception:
                channel.close()
                with self.lock:
                    if channel.locally_disconnected or self.stopping.is_set():
                        raise ConnectError('connection_closed') from None
                    current = self.channels.get(peer)
                    if current is not None and not current.stop.is_set() and current.path == DIRECT:
                        return current
                if attempt == retries:
                    raise ConnectError('connection_failed_check_pairing_certificate_and_firewall') from None
                if self.stopping.wait(min(2 ** attempt * .25, 1)):
                    raise ConnectError('connection_closed')
        raise ConnectError('connection_failed')

    def reconnect(self):
        # At most three background attempts per explicit local connection intent.
        # A successful retry does not refill the budget (avoids flapping forever).
        while not self.stopping.wait(.1):
            with self.lock:
                candidates = [(peer, dict(target)) for peer, target in self.targets.items()
                    if peer not in self.channels and target['attempts'] < 3
                    and target['next'] <= time.monotonic()]
            for peer, target in candidates:
                with self.lock:
                    current = self.targets.get(peer)
                    if current is None or peer in self.channels:
                        continue
                    current['attempts'] += 1
                    current['next'] = time.monotonic() + 2 ** current['attempts'] * .5
                try:
                    self.connect(peer, target['address'], target['port'], _automatic=True)
                except Exception:
                    pass  # Fixed connection status contains the failure, never provider text.

    def connect_discovered(self, peer, instance, *, retries=0):
        entries = self.discovery.nearby() if self.discovery else []
        entry = next((e for e in entries if e['instance'] == instance), None)
        if entry is None:
            raise ConnectError('discovery_expired')
        return self.connect(peer, entry['address'], entry['port'], retries=retries)

    def attach_world(self, sock, peer):
        """A relay tunnel reached this computer for ``peer``'s World route.

        The bytes are the peer's TLS client handshake; this side is the TLS
        server pinned to that peer's certificate only. Returns the Channel.
        """
        with self.lock:
            if self.stopping.is_set() or len(self.workers) >= MAX_CONNECTIONS or not self.world_attempts.take():
                sock.close()
                raise ConnectError('backpressure')
            channel = Channel(self, sock, path=WORLD, route_peer=peer)
            self.workers.add(channel)
            try:
                channel.thread.start()
            except Exception:
                self.workers.discard(channel)
                sock.close()
                raise
        return channel

    def connect_world(self, peer, sock, *, timeout=None):
        """The client (phone) role over an already-joined World route."""
        record = self.service.device(peer, timeout=.25)
        self.service.require_paired_identity(record.get('public_identity'), timeout=.25)
        with self.lock:
            if self.stopping.is_set() or len(self.workers) >= MAX_CONNECTIONS or not self.world_attempts.take():
                sock.close()
                raise ConnectError('backpressure')
            if not (peer in self.channels and not self.channels[peer].stop.is_set()):
                self.states[peer] = dict(state='connecting', error=None)
            channel = Channel(self, sock, peer, None, path=WORLD)
            self.workers.add(channel)
            try:
                channel.thread.start()
            except Exception:
                self.workers.discard(channel)
                sock.close()
                raise
        try:
            return channel.ready.result(timeout=timeout or 2 * HANDSHAKE_TIMEOUT * WORLD_TIME_SCALE + 1)
        except Exception as error:
            channel.close()
            raise ConnectError(str(error) if isinstance(error, ConnectError) else 'connection_failed') from None

    def _blocking(self, existing, channel):
        """The rule that would reject ``channel`` in favour of a live ``existing``, else None."""
        if existing is None or existing is channel or existing.stop.is_set():
            return None
        if existing.path != channel.path:
            return 'direct_preferred' if channel.path == WORLD else None
        preferred = channel.outbound == (self.service.local_id < channel.peer)
        return 'connection_collision' if not preferred or existing.outbound == channel.outbound else None

    def _stale_blocker(self, channel):
        """The current channel that would reject ``channel`` but no longer reaches its peer.

        Only a peer that has given up a path dials a new one over the same path
        or over World, so the old channel must prove itself with one heartbeat.
        The probe runs on the new channel's worker with no lock held.
        """
        with self.lock:
            existing = self.channels.get(channel.peer)
            rule = self._blocking(existing, channel)
        if rule is None:
            return None
        alive = existing.alive()
        paths_log.info('liveness peer=%s current=%s/%s incoming=%s/%s rule=%s alive=%s',
            _short(channel.peer), existing.path, existing.generation[:8], channel.path,
            channel.generation[:8], rule, alive)
        return None if alive else existing

    def adopt(self, channel):
        stale = self._stale_blocker(channel)
        # File admission uses files.lock -> network.lock. Keep that order and
        # finish old transfer invalidation before publishing a replacement.
        with self.service.files.lock, self.lock:
            channel.check()
            existing = self.channels.get(channel.peer)
            # One logical peer. A healthy Direct always beats World (both ends apply
            # the same rule); within one path both sides prefer the socket initiated
            # by the lower stable C2 UUID. A channel that failed its liveness probe
            # never blocks: its peer already left it.
            rule = self._blocking(existing, channel)
            current = (existing.path, existing.generation[:8]) if existing is not None else (None, None)
            if existing is not None and existing is stale and rule is not None:
                existing.close('retirement_stale')
                decision = 'replaced_stale'
            elif rule is not None:
                paths_log.info('adopt peer=%s incoming=%s/%s current=%s/%s decision=rejected reason=%s',
                    _short(channel.peer), channel.path, channel.generation[:8], *current, rule)
                raise ConnectError(rule)
            elif existing is not None and not existing.stop.is_set():
                existing.close('retirement_direct_preferred' if existing.path != channel.path else 'retirement_replaced')
                decision = 'replaced'
            else:
                decision = 'adopted'
            paths_log.info('adopt peer=%s incoming=%s/%s current=%s/%s decision=%s',
                _short(channel.peer), channel.path, channel.generation[:8], *current, decision)
            self.channels[channel.peer] = channel
            self.states[channel.peer] = dict(state='online', error=None)
        self.audit(channel.peer, 'connection_authenticated_world' if channel.path == WORLD else 'connection_authenticated')
        if self.service.notes is not None:
            self.service.notes.channel_ready(channel.peer)  # Non-blocking: starts a pump thread.
        if getattr(self.service, 'draw', None) is not None:
            self.service.draw.channel_ready(channel.peer)   # Non-blocking: probe and/or pump thread.

    def allow_message(self, peer):
        with self.lock:
            # Only authenticated peers reach here; cap across reconnects, no eviction.
            if peer not in self.rates:
                if len(self.rates) >= 256:
                    return False
                self.rates[peer] = Budget(60, 60)
            return self.rates[peer].take()

    def allow_notes_message(self, peer):
        with self.lock:
            if peer not in self.notes_rates:
                if len(self.notes_rates) >= 256:
                    return False
                self.notes_rates[peer] = Budget(3000, 60)
            return self.notes_rates[peer].take()

    def allow_chat_message(self, peer):
        # Attachment and artifact chunks are one bounded frame per request/response,
        # stop-and-wait, so control frames never queue behind a large transfer.
        with self.lock:
            if peer not in self.chat_rates:
                if len(self.chat_rates) >= 256:
                    return False
                self.chat_rates[peer] = Budget(6000, 60)
            return self.chat_rates[peer].take()

    def allow_draw_message(self, peer):
        with self.lock:
            if peer not in self.draw_rates:
                if len(self.draw_rates) >= 256:
                    return False
                self.draw_rates[peer] = Budget(6000, 60)
            return self.draw_rates[peer].take()

    def allow_file_message(self, peer):
        with self.lock:
            if peer not in self.file_rates:
                if len(self.file_rates) >= 256:
                    return False
                self.file_rates[peer] = Budget(2400, 60)
            return self.file_rates[peer].take()

    def finished(self, channel, reason):
        if self.service.studio is not None:
            self.service.studio.invalidate(channel=channel, reason="connection_lost")
        if self.service.inference is not None:
            # Exact channel identity avoids old teardown cancelling replacement work.
            self.service.inference.invalidate(channel=channel, reason='connection_lost')
        affected = False
        with self.service.files.lock:
            with self.lock:
                peer = channel.peer or channel.expected
                if self.channels.get(peer) is channel:
                    affected = True
                    self.channels.pop(peer)
                    self.states[peer] = dict(state='offline', error=reason)
                elif peer and peer not in self.channels and not channel.locally_disconnected:
                    self.states[peer] = dict(state='failed', error=reason)
            if affected:
                self.service.files.invalidate(peer, 'connection_closed')
        if affected and self.service.notes is not None:
            self.service.notes.channel_closed(peer)
        if affected and getattr(self.service, 'draw', None) is not None:
            self.service.draw.channel_closed(peer)
        self.audit(peer, 'connection_closed' if channel.peer else 'connection_failed')

    def status(self, peer):
        with self.lock:
            state = dict(self.states.get(peer, dict(state='offline', error=None)))
            channel = self.channels.get(peer)
            if channel is not None and channel.stop.is_set():
                channel = None
                state['state'] = 'offline'
            # 'local' is the established Direct value older UIs already understand.
            state.update(connection=('world' if channel.path == WORLD else 'local') if channel else None,
                         encrypted=bool(channel),
                         latency_ms=channel.last_latency_ms if channel else None)
            return state

    def debug_snapshot(self, peer):
        """Private test/developer data; absent from public status and wire frames."""
        with self.lock:
            return dict(audit_failures=self.audit_failures,
                workers=[c.debug_snapshot() for c in self.workers if peer in (c.peer, c.expected)],
                retired=[value for identity, value in self.retired if identity == peer][-4:])

    def allow_studio_message(self, peer):
        with self.lock:
            if peer not in self.studio_rates:
                if len(self.studio_rates) >= 256:
                    return False
                self.studio_rates[peer] = Budget(300, 60)
            return self.studio_rates[peer].take()

    def allow_inference_message(self, peer):
        with self.lock:
            if peer not in self.inference_rates:
                if len(self.inference_rates) >= 256:
                    return False
                self.inference_rates[peer] = Budget(600, 60)
            return self.inference_rates[peer].take()

    def disconnect(self, peer, *, revoked=False, wait=True):
        with self.service.files.lock:
            with self.lock:
                self.targets.pop(peer, None)
                workers = [c for c in self.workers if peer in (c.peer, c.expected)]
                for channel in workers:
                    channel.locally_disconnected = True
                    channel.diagnostics.closed('device_revoked' if revoked else 'local_disconnect')
                    if wait and not revoked and channel.graceful_disconnect:
                        # Another caller already owns this exact retirement.
                        # Join it; do not turn our own SHUT_RD into a false EOF.
                        continue
                    if wait and not revoked and channel.ready.done() and not channel.stop.is_set():
                        # The owning worker finishes its last TLS call, removes
                        # authority, half-closes and waits for the peer to retire.
                        channel.graceful_disconnect = True
                        channel.stop.set()
                    else:
                        channel.close()
                self.channels.pop(peer, None)
                self.states[peer] = dict(state='offline', error='device_revoked' if revoked else None)
            self.service.files.invalidate(peer, 'device_revoked' if revoked else 'connection_closed')
        if wait:
            deadline = time.monotonic() + 4
            for channel in workers:
                if channel.thread is not threading.current_thread():
                    channel.thread.join(max(0, deadline - time.monotonic()))
            if any(c.thread.is_alive() and c.thread is not threading.current_thread() for c in workers):
                raise ConnectError('disconnect_timeout')
            if any(c.graceful_disconnect and not c.peer_closed for c in workers):
                raise ConnectError('disconnect_timeout')
        if revoked:
            self.audit(peer, 'revoked_connection_closed')

    def close(self):
        self.stopping.set()
        self.listener.close()
        with self.lock:
            workers = list(self.workers)
            for channel in workers:
                channel.close('shutdown')
        if self.discovery:
            self.discovery.close()
        self.thread.join(timeout=4)
        self.reconnector.join(timeout=4)
        deadline = time.monotonic() + 4
        for channel in workers:
            if channel.thread.ident is not None:
                channel.thread.join(timeout=max(0, deadline - time.monotonic()))
        if self.thread.is_alive() or self.reconnector.is_alive() or any(c.thread.is_alive() for c in workers):
            raise ConnectError('shutdown_timeout')
        self.local_identity = None
