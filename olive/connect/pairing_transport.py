"""Explicit, temporary, selected-interface carrier for C2. No action dispatch."""
import json
import socket
import struct
import threading
import time

from .contracts import ConnectError
from .pairing import TERMINAL
from .pairing_wire import DESKTOP_PROTOCOL, decode_offer, MAX_OFFER

HEADER = struct.Struct('!I')
MAX_FRAME = 32768
MAX_BYTES = 262144
MAX_FRAMES = 3000
HANDSHAKE_TIMEOUT = 5
IDLE_TIMEOUT = 2
MAX_ATTEMPTS = 12


class Frames:
    def __init__(self, sock):
        self.sock = sock
        self.bytes = self.frames = 0

    def _read(self, size):
        result = bytearray()
        deadline = time.monotonic() + IDLE_TIMEOUT
        while len(result) < size:
            self.sock.settimeout(max(.001, deadline - time.monotonic()))
            part = self.sock.recv(size - len(result))
            if not part or time.monotonic() > deadline:
                raise ConnectError('pairing_interrupted')
            result.extend(part)
        return bytes(result)

    def receive(self, limit=MAX_FRAME):
        size = HEADER.unpack(self._read(HEADER.size))[0]
        self.frames += 1
        self.bytes += size + HEADER.size
        if size > limit or self.bytes > MAX_BYTES or self.frames > MAX_FRAMES:
            raise ConnectError('pairing_message_budget_exceeded')
        return self._read(size)

    def send(self, data):
        if len(data) > MAX_FRAME:
            raise ConnectError('invalid_pairing_message')
        self.sock.settimeout(IDLE_TIMEOUT)
        self.sock.sendall(HEADER.pack(len(data)) + data)


def shutdown(sock):
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()


class DesktopPairingTransport:
    """One explicitly active session and at most one accepted socket per desktop."""
    def __init__(self, service):
        self.service = service
        self.pairing = service.pairing
        self.lock = threading.RLock()
        self.listener = self.socket = self.thread = None
        self.session_id = None
        self.error = None
        self.stopping = threading.Event()

    def _interface(self):
        network = self.service.network
        if self.service.closed or not network or network.stopping.is_set():
            raise ConnectError('select_connect_interface')
        return network.interface

    def _start(self):
        self.close(cancel=True)
        self.stopping.clear()
        self.error = None
        return self._interface()

    def create(self):
        with self.lock:
            interface = self._start()
            family = socket.AF_INET6 if ':' in interface.address else socket.AF_INET
            listener = socket.socket(family, socket.SOCK_STREAM)
            try:
                listener.bind((interface.address, 0))
                listener.listen(2)
                listener.settimeout(.2)
                offer = self.pairing.create_offer(endpoint=dict(address=interface.address,
                                                               port=listener.getsockname()[1]))
            except Exception:
                listener.close()
                raise ConnectError('pairing_listener_unavailable') from None
            self.listener = listener
            self.session_id = json.loads(offer)['session_id']
            self.thread = threading.Thread(target=self._listen, args=(interface,), daemon=True,
                                           name='OLIVE-pairing')
            self.thread.start()
            return offer

    def accept(self, raw):
        with self.lock:
            offer = decode_offer(raw, self.service.clock())
            if offer['protocol'] != DESKTOP_PROTOCOL:
                raise ConnectError('desktop_pairing_offer_required')
            interface = self._interface()
            if not interface.permits(offer['endpoint']['address']):
                raise ConnectError('pairing_endpoint_outside_interface')
            self._start()
            reply = self.pairing.accept_offer(raw)
            self.session_id = offer['session_id']
            self.thread = threading.Thread(target=self._connect, args=(interface, offer, reply),
                                           daemon=True, name='OLIVE-pairing')
            self.thread.start()
            return self.session_id

    def _alive(self):
        if self.stopping.is_set():
            return False
        try:
            return self.pairing.presentation(self.session_id)['state'] not in TERMINAL
        except ConnectError:
            return False

    def _listen(self, interface):
        try:
            attempts = 0
            while self._alive() and attempts < MAX_ATTEMPTS:
                try:
                    sock, address = self.listener.accept()
                except socket.timeout:
                    continue
                attempts += 1
                self.socket = sock
                try:
                    if not interface.permits(address[0]):
                        continue
                    frames = Frames(sock)
                    reply = frames.receive(MAX_OFFER)
                    # Malformed public attempts do not consume the active C2 offer.
                    decoded = decode_offer(reply, self.service.clock())
                    if decoded['protocol'] != DESKTOP_PROTOCOL or decoded['session_id'] != self.session_id:
                        continue
                    self.pairing.receive_reply(reply)
                    self.pairing._audit(self.session_id, 'peer_joined')
                    self._pump(frames, server=True)
                    return
                except (OSError, ConnectError, ValueError):
                    if not self._alive():
                        return
                    with self.pairing._lock:
                        started = self.pairing._sessions[self.session_id]['reply'] is not None
                    if started:
                        raise ConnectError('pairing_interrupted') from None
                finally:
                    shutdown(sock)
                    self.socket = None
            if self._alive():
                raise ConnectError('pairing_attempt_limit')
        except Exception:
            self.error = 'pairing_interrupted'
            self._interrupted()
        finally:
            shutdown(self.listener)
            self.listener = None

    def _connect(self, interface, offer, reply):
        sock = socket.socket(socket.AF_INET6 if ':' in interface.address else socket.AF_INET, socket.SOCK_STREAM)
        self.socket = sock
        joined = False
        try:
            sock.bind((interface.address, 0))
            sock.settimeout(IDLE_TIMEOUT)
            sock.connect((offer['endpoint']['address'], offer['endpoint']['port']))
            frames = Frames(sock)
            frames.send(reply)
            joined = True
            self._pump(frames, server=False)
        except Exception:
            self.error = 'pairing_interrupted' if joined else 'pairing_unreachable'
            self._interrupted()
        finally:
            shutdown(sock)
            self.socket = None

    def _interrupted(self):
        # A final acknowledgement may be lost after both receipts are durable.
        try:
            self.pairing.complete_desktop(self.session_id)
            self.error = None
        except ConnectError:
            self.pairing.interrupt(self.session_id)

    def _pump(self, frames, *, server):
        authenticated = False
        deadline = time.monotonic() + HANDSHAKE_TIMEOUT
        incoming = b''
        while self._alive():
            if server:
                incoming = frames.receive()
            outgoing = self.pairing.exchange(self.session_id, incoming)
            frames.send(outgoing)
            with self.pairing._lock:
                session = self.pairing._sessions[self.session_id]
                ready = bool(session['tls'] and session['tls'].ready)
                completed = session.get('receipt_received', False)
            if ready and not authenticated:
                authenticated = True
                self.pairing._audit(self.session_id, 'comparison_ready')
            if completed:
                self.pairing.complete_desktop(self.session_id)
                return
            if not authenticated and time.monotonic() >= deadline:
                raise ConnectError('pairing_handshake_timeout')
            if not server:
                incoming = frames.receive()
                self.stopping.wait(.1)

    def status(self, sid):
        try:
            result = self.pairing.presentation(sid)
        except ConnectError:
            saved = self.pairing.completion.load(sid)
            with self.service.repository.transaction() as db:
                row = db.execute('SELECT state FROM pairing_ledger WHERE session_id=?', (sid,)).fetchone()
            result = dict(session_id=sid, state='interrupted' if row[0] == 'consumed' else row[0],
                          expires_at=saved['offer']['expires_at'])
        if sid == self.session_id:
            result['listener_active'] = self.listener is not None
            if self.error:
                result['error'] = self.error
        try:
            if result['state'] in ('cancelled', 'expired', 'failed'):
                raise ConnectError('pairing_not_active')
            result['completion_code'] = self.pairing.completion.export(sid)
        except ConnectError:
            pass
        return result

    def import_completion(self, raw):
        sid = self.pairing.completion.import_receipts(raw)
        self.pairing.complete_desktop(sid)
        if sid == self.session_id:
            self.close()
        return self.status(sid)

    def close(self, *, cancel=False):
        with self.lock:
            self._close(cancel=cancel)

    def _close(self, *, cancel=False):
        self.stopping.set()
        shutdown(self.listener)
        shutdown(self.socket)
        thread = self.thread
        if thread and thread is not threading.current_thread():
            thread.join(30)
            if thread.is_alive():
                raise ConnectError('pairing_shutdown_pending')
        self.listener = self.socket = self.thread = None
        if self.session_id and not cancel:
            self.pairing.interrupt(self.session_id)
        if cancel and self.session_id:
            try:
                self.cancel(self.session_id)
            except ConnectError:
                pass

    def cancel(self, sid):
        # Invalidate receipts before closing sockets; cancellation beats recovery.
        with self.pairing._lock:
            session = self.pairing._sessions.get(sid)
            if session and session['state'] != 'completed':
                self.pairing._finish(sid, 'cancelled')
            elif session is None:
                with self.service.repository.transaction() as db:
                    db.execute("UPDATE pairing_ledger SET state='cancelled' WHERE session_id=? AND state!='completed'", (sid,))
        if sid == self.session_id:
            self.close()
