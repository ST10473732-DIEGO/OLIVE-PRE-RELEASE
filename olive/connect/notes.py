"""OLIVE Notes over OLIVE Connect: frames 13/14 carrying olive-notes/1.

Only authenticated, paired, non-revoked peers with `sync.notes` set to Allow
may exchange Notes. The authenticated channel supplies the peer identity; a
message's own device fields must match it. No new socket, listener or relay.

Sending is push-based: a local change (or a peer coming online, or a permission
turning on) marks that peer dirty and one pump thread per peer drains the
durable change feed. Failures retry the transport with bounded backoff; edits
are never retried because they are already durable and CRDT-idempotent.
"""
import logging
import threading
import time
import uuid

from ..agent.permission_service import PermissionDecision, PermissionService
from ..notes import protocol
from ..notes.limits import CAPABILITY
from ..notes.sync_engine import NotesSyncEngine, NotesSyncError
from .contracts import ConnectError

logger = logging.getLogger(__name__)

DEBOUNCE = 0.04          # Coalesce a burst of keystrokes into one exchange.
BACKOFF = (0.5, 1, 2, 4, 8)
SENDER_ERRORS = frozenset({'device_offline', 'connection_lost', 'connection_closed', 'backpressure', 'busy',
                           'rate_limited', 'notes_request_timeout', 'request_timeout'})


class _Pump:
    def __init__(self):
        self.dirty = False
        self.thread = None
        self.hello = False
        self.failures = 0


class RemoteNotesService:
    def __init__(self, connect, notes):
        self.connect = connect
        self.notes = notes
        self.engine = NotesSyncEngine(notes, connect.local_id)
        self.lock = threading.Lock()
        self.pumps = {}
        self.stopping = threading.Event()
        self.on_status = lambda: None
        # Peers known to speak olive-notes/1: they sent us a Notes frame, or we
        # dialed them. An older peer closes the channel on an unknown frame type,
        # so we never start Notes traffic toward a phone that has not spoken first.
        self.announced = set()
        notes.listeners.append(self._local_change)

    # --- authority -------------------------------------------------------------------
    def permitted(self, peer, *, db=None):
        """Current local decision; Ask is not offered for live Notes sync."""
        s = self.connect
        try:
            if db is None:
                record = s.device(peer, timeout=.25)
            else:
                record = s.repository.get(db, peer)
        except Exception:
            return False
        if not record or record.get('trust_state') != 'paired' or record.get('revoked_at') is not None:
            return False
        return PermissionService.evaluate_device(record['permissions'], CAPABILITY) == PermissionDecision.ALLOW

    def _authorize(self, request, channel):
        s = self.connect
        if s.closed or s.network is None or channel.public is None:
            raise protocol.NotesProtocolError('device_not_paired')
        if request['source_device_id'] != channel.peer:
            raise protocol.NotesProtocolError('source_mismatch')
        if request['target_device_id'] != s.local_id:
            raise protocol.NotesProtocolError('wrong_target')
        with s.repository.transaction(timeout=.25, read_only=True) as db:
            record = s.repository.get(db, channel.peer)
            if not record or record.get('trust_state') != 'paired' or record.get('revoked_at') is not None:
                raise protocol.NotesProtocolError('device_not_paired')
            if record.get('public_identity') != channel.public:
                raise protocol.NotesProtocolError('identity_mismatch')
            metadata = next((c for c in s.repository.get(db, s.local_id)['capabilities'] if c['capability'] == CAPABILITY), {})
            if metadata.get('policy_disabled'):
                raise protocol.NotesProtocolError('capability_unavailable')
            if PermissionService.evaluate_device(record['permissions'], CAPABILITY) != PermissionDecision.ALLOW:
                raise protocol.NotesProtocolError('permission_off')
        protocol.check_fresh(request, int(s.clock()))

    # --- receiving (channel thread) --------------------------------------------------
    def receive(self, raw, channel, write):
        request_id = None
        try:
            request = protocol.decode_request(raw)
            request_id = request['request_id']
            with self.lock:
                self.announced.add(channel.peer)
            self._authorize(request, channel)
            if self.notes.unavailable:
                raise protocol.NotesProtocolError('notes_unavailable')
            result = self.notes.run(self.engine.handle, channel.peer, request, timeout=10)
            write(protocol.encode_response(request_id, result=result))
        except protocol.NotesProtocolError as failure:
            write(protocol.encode_response(request_id, error=str(failure)))
            return
        except ConnectError:
            write(protocol.encode_response(request_id, error='device_not_paired'))
            return
        except Exception:
            logger.warning('Notes sync request failed (%s)', 'storage')
            write(protocol.encode_response(request_id, error='notes_unavailable'))
            return
        # A peer that talks to us is online: make sure our side reaches it too.
        self.kick(channel.peer)

    # --- sending ---------------------------------------------------------------------
    def channel_ready(self, peer):
        channel = self._channel(peer)
        with self.lock:
            pump = self.pumps.setdefault(peer, _Pump())
            pump.hello = False
            pump.failures = 0
            if channel is not None and channel.outbound:
                self.announced.add(peer)   # We dialed a desktop: we speak first.
        self.kick(peer)

    def channel_closed(self, peer):
        self.engine.set_state(peer, 'offline')
        self.on_status()

    def permission_changed(self, peer):
        if self.permitted(peer):
            self.channel_ready(peer)   # Newly allowed: initial sync starts now.
        else:
            self.engine.forget(peer)
            self.engine.set_state(peer, 'off')
            self.on_status()

    def _local_change(self, note_id, peer):
        network = self.connect.network
        if network is None:
            return
        with network.lock:
            online = [p for p, channel in network.channels.items() if not channel.stop.is_set()]
        for device in online:
            self.kick(device)

    def kick(self, peer):
        if self.stopping.is_set():
            return
        with self.lock:
            if peer not in self.announced:
                return
            pump = self.pumps.setdefault(peer, _Pump())
            pump.dirty = True
            if pump.thread is not None and pump.thread.is_alive():
                return
            pump.thread = threading.Thread(target=self._run, args=(peer, pump), name='olive-notes-sync', daemon=True)
            pump.thread.start()

    def _channel(self, peer):
        network = self.connect.network
        if network is None:
            return None
        with network.lock:
            channel = network.channels.get(peer)
        return None if channel is None or channel.stop.is_set() else channel

    def _run(self, peer, pump):
        if self.stopping.wait(DEBOUNCE):
            return
        while not self.stopping.is_set():
            with self.lock:
                if not pump.dirty:
                    pump.thread = None
                    return
                pump.dirty = False
            channel = self._channel(peer)
            if channel is None:
                self.engine.set_state(peer, 'offline')
                self.on_status()
                continue
            if not self.permitted(peer):
                self.engine.set_state(peer, 'off')
                self.on_status()
                continue
            try:
                outcome = self.engine.pump(peer, lambda operation, arguments: self._send(channel, peer, operation, arguments),
                                           hello=not pump.hello, keep_going=lambda: not self.stopping.is_set())
                pump.hello = True
                pump.failures = 0
                if outcome == 'partial':
                    with self.lock:
                        pump.dirty = True
                self.on_status()
            except (NotesSyncError, ConnectError, protocol.NotesProtocolError) as failure:
                code = str(failure)
                self.engine.set_state(peer, 'offline' if code in SENDER_ERRORS else 'error', error=code)
                self.on_status()
                if code in ('permission_off', 'device_not_paired', 'identity_mismatch', 'unsupported_protocol'):
                    continue  # Waits for a new local change or permission/channel event.
                pump.failures += 1
                if pump.failures > len(BACKOFF) or self._channel(peer) is None:
                    continue
                with self.lock:
                    pump.dirty = True
                if self.stopping.wait(BACKOFF[pump.failures - 1]):
                    return
            except Exception:
                logger.warning('Notes sync pump failed (%s)', 'internal')
                self.engine.set_state(peer, 'error', error='notes_unavailable')
                self.on_status()

    def _send(self, channel, peer, operation, arguments):
        s = self.connect
        raw = protocol.encode_request(str(uuid.uuid4()), s.local_id, peer, operation, arguments, int(s.clock()))
        response = channel.notes_request(raw)
        if response['state'] != 'completed':
            raise NotesSyncError(response['error'])
        return response['result']

    # --- status ------------------------------------------------------------------------
    def status(self, peer):
        state = self.engine.state(peer)
        if not self.permitted(peer):
            state['state'] = 'off'
        elif self._channel(peer) is None and state.get('state') != 'error':
            state['state'] = 'offline'
        try:
            state['pending'] = self.engine.pending(peer) if not self.notes.unavailable else 0
            peer_state = self.notes.run(self.notes.peer, peer)
            state['last_sync'] = peer_state['last_sync']
            state['refused'] = len(self.engine.refused(peer))
        except Exception:
            state['pending'] = None
        if state.get('state') == 'synced' and state.get('pending'):
            state['state'] = 'syncing'
        return state

    def close(self):
        self.stopping.set()
        with self.lock:
            threads = [p.thread for p in self.pumps.values() if p.thread is not None]
        deadline = time.monotonic() + 4
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(max(0, deadline - time.monotonic()))
