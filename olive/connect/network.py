"""Dedicated opt-in LAN transport. Bounded threads, queues and fresh TLS per socket."""
from collections import deque
from contextlib import nullcontext
from concurrent.futures import Future
import ipaddress
import json
import queue
import select
import socket
import threading
import time

from OpenSSL import SSL
from cryptography.hazmat.primitives import serialization

from .contracts import ConnectError, RequestEnvelope, canonical, _unique_object
from .discovery import LocalDiscovery, interfaces
from .network_wire import (HEADER, REQUEST, RESPONSE, CLOSE, HELLO, SYNC_REQUEST, SYNC_RESPONSE, frame, header,
                           require_current, tls_context)

CONNECT_TIMEOUT = 3.0
HANDSHAKE_TIMEOUT = 3.0
FRAME_TIMEOUT = 3.0
WRITE_TIMEOUT = 2.0
REQUEST_TIMEOUT = 5.0
IDLE_TIMEOUT = 60.0
MAX_CONNECTIONS = 8
MAX_PENDING = 8


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
    def __init__(self, owner, sock, expected=None, endpoint=None):
        self.owner, self.sock, self.expected = owner, sock, expected
        self.outbound = expected is not None
        self.endpoint = endpoint
        self.peer = None
        self.public = None
        self.tls = None
        self.stop = threading.Event()
        # Protected by owner.lock; explicit local intent outlives worker cleanup.
        self.locally_disconnected = False
        self.ready = Future()
        self.writes = queue.Queue(MAX_PENDING)
        self.pending = {}
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.run, name='olive-connect-channel', daemon=True)
        self.last_latency_ms = None

    def check(self):
        if self.stop.is_set() or self.owner.stopping.is_set():
            raise ConnectError('connection_closed')
        if self.public is not None:
            self.owner.service.require_paired_identity(self.public, timeout=.25)
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
        deadline = time.monotonic() + WRITE_TIMEOUT
        offset = 0
        while offset < len(raw):
            sent = self.io(lambda: self.tls.send(raw[offset:]), deadline)
            if not sent:
                raise ConnectError('connection_closed')
            offset += sent

    def sync_request(self, raw, *, admission=None):
        return self.request(raw, _sync=True, _admission=admission)

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
            self.close()
            raise ConnectError('request_timeout') from None
        finally:
            with self.lock:
                self.pending.pop(request.request_id, None)

    def process(self, kind, payload):
        self.check()
        if not self.owner.allow_message(self.peer):
            raise ConnectError('rate_limited')
        if kind == CLOSE:
            raise ConnectError('connection_closed')
        if kind == HELLO:
            raise ConnectError('unexpected_hello')
        if kind == SYNC_REQUEST:
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
                self.sock.settimeout(CONNECT_TIMEOUT)
                self.sock.bind((self.owner.interface.address, 0))
                self.sock.connect(self.endpoint)
                self.check()
                with self.owner.lock:
                    self.check()
                    self.owner.states[self.expected] = dict(state='authenticating', error=None)
                self.owner.audit(self.expected, 'connection_started')
            ctx, peers = tls_context(self.owner.service, self.expected, local=self.owner.local_identity)
            self.sock.setblocking(False)
            self.tls = SSL.Connection(ctx, self.sock)
            (self.tls.set_connect_state if self.outbound else self.tls.set_accept_state)()
            self.io(self.tls.do_handshake, time.monotonic() + HANDSHAKE_TIMEOUT)
            cert = self.tls.get_peer_certificate().to_cryptography().public_bytes(serialization.Encoding.DER)
            self.public = peers.get(cert)
            if self.public is None or self.tls.get_protocol_version_name() != 'TLSv1.3':
                raise ConnectError('identity_mismatch')
            self.peer = self.public['device_id']
            self.check()
            # TLS 1.3 clients may finish locally before the server rejects their
            # certificate. An encrypted fixed hello proves both verifiers finished.
            hello = frame(HELLO)
            self.write(hello)
            received = bytearray()
            deadline = time.monotonic() + HANDSHAKE_TIMEOUT
            while len(received) < len(hello):
                part = self.io(lambda: self.tls.recv(len(hello) - len(received)), deadline)
                if not part:
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
                self.check()
                try:
                    self.write(self.writes.get_nowait())
                except queue.Empty:
                    pass
                now = time.monotonic()
                if now - last >= IDLE_TIMEOUT or (started is not None and now - started >= FRAME_TIMEOUT):
                    raise ConnectError('connection_timeout')
                try:
                    data = self.tls.recv(16384)
                except SSL.WantReadError:
                    select.select([self.sock], [], [], .05)
                    continue
                if not data:
                    raise ConnectError('connection_closed')
                last = now
                if not buffer:
                    started = now
                buffer.extend(data)
                while len(buffer) >= HEADER.size:
                    size, kind = header(buffer[:HEADER.size])
                    if len(buffer) < HEADER.size + size:
                        break
                    payload = bytes(buffer[HEADER.size:HEADER.size + size])
                    del buffer[:HEADER.size + size]
                    self.process(kind, payload)
                    started = time.monotonic() if buffer else None
        except ConnectError as error:
            reason = str(error)
        except Exception:
            reason = 'tls_or_connection_failed'
        finally:
            self.close()
            self.sock.close()
            if not self.ready.done():
                self.ready.set_exception(ConnectError(reason))
            with self.lock:
                for future in self.pending.values():
                    if not future.done():
                        future.set_exception(ConnectError('connection_closed'))
            self.owner.finished(self, reason)

    def close(self):
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
        self.states = {}
        self.rates = {}
        self.targets = {}
        self.attempts = Budget(12, 60)
        self.audit_budget = Budget(30, 60)
        self.discovery = None
        self.listener = socket.socket(socket.AF_INET if ipaddress.ip_address(address).version == 4 else socket.AF_INET6)
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
                if peer in self.channels and not self.channels[peer].stop.is_set():
                    return self.channels[peer]
                if self.stopping.is_set() or (_automatic and peer not in self.targets):
                    raise ConnectError('connection_closed')
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
                    if current is not None and not current.stop.is_set():
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

    def adopt(self, channel):
        with self.lock:
            channel.check()
            existing = self.channels.get(channel.peer)
            # Both sides prefer the socket initiated by the lower stable C2 UUID.
            preferred = channel.outbound == (self.service.local_id < channel.peer)
            if existing is not None and not existing.stop.is_set():
                if not preferred or existing.outbound == channel.outbound:
                    raise ConnectError('connection_collision')
                existing.close()
            self.channels[channel.peer] = channel
            self.states[channel.peer] = dict(state='online', error=None)
        self.audit(channel.peer, 'connection_authenticated')

    def allow_message(self, peer):
        with self.lock:
            # Only authenticated peers reach here; cap across reconnects, no eviction.
            if peer not in self.rates:
                if len(self.rates) >= 256:
                    return False
                self.rates[peer] = Budget(60, 60)
            return self.rates[peer].take()

    def finished(self, channel, reason):
        with self.lock:
            peer = channel.peer or channel.expected
            if self.channels.get(peer) is channel:
                self.channels.pop(peer)
                self.states[peer] = dict(state='offline', error=reason)
            elif peer and peer not in self.channels and not channel.locally_disconnected:
                self.states[peer] = dict(state='failed', error=reason)
        try:
            self.audit(peer, 'connection_closed' if channel.peer else 'connection_failed')
        finally:
            with self.lock:
                self.workers.discard(channel)

    def status(self, peer):
        with self.lock:
            state = dict(self.states.get(peer, dict(state='offline', error=None)))
            channel = self.channels.get(peer)
            if channel is not None and channel.stop.is_set():
                channel = None
                state['state'] = 'offline'
            state.update(connection='local' if channel else None, encrypted=bool(channel),
                         latency_ms=channel.last_latency_ms if channel else None)
            return state

    def disconnect(self, peer, *, revoked=False):
        with self.lock:
            self.targets.pop(peer, None)
            for channel in list(self.workers):
                if peer in (channel.peer, channel.expected):
                    channel.locally_disconnected = True
                    channel.close()
            self.channels.pop(peer, None)
            self.states[peer] = dict(state='offline', error='device_revoked' if revoked else None)
        if revoked:
            self.audit(peer, 'revoked_connection_closed')

    def close(self):
        self.stopping.set()
        self.listener.close()
        with self.lock:
            workers = list(self.workers)
            for channel in workers:
                channel.close()
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
