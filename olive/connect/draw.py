"""OLIVE Draw over OLIVE Connect: frames 15/16 carrying olive-draw/1.

Only authenticated, paired, non-revoked peers with ``sync.draw`` set to Allow
may exchange drawings. ``sync.draw`` is separate from ``sync.notes`` and is Off
by default. The authenticated channel supplies the peer identity; a message's
own device fields must match it. No new socket, listener or relay.

Compatibility: an older OLIVE build closes a channel on an unknown frame type,
so Draw frames are only ever sent to a peer that has shown it speaks
olive-draw/1: it sent us a Draw frame first (a phone always speaks first), or,
on a channel we dialed (a desktop listener), it answered the read-only
``connect.ping`` / ``protocols`` probe with olive-draw/1. Older desktops answer
that probe with a normal "unknown operation" rejection and keep the channel.

Sending is push-based, like Notes: a local change, a peer coming online or a
permission turning on marks the peer dirty and one pump thread per peer drains
the durable change feed. Records are idempotent, so resends are harmless.
"""
import logging
import threading
import time
import uuid

from ..agent.permission_service import PermissionDecision, PermissionService
from ..draw import protocol
from ..draw.protocol import CAPABILITY, PROTOCOL
from ..draw.sync_engine import DrawSyncEngine, DrawSyncError
from .contracts import PROTOCOL as CONNECT_PROTOCOL, ConnectError, canonical

logger = logging.getLogger(__name__)

DEBOUNCE = 0.03
BACKOFF = (0.5, 1, 2, 4, 8)
SENDER_ERRORS = frozenset({'device_offline', 'connection_lost', 'connection_closed', 'backpressure', 'busy',
                           'rate_limited', 'draw_request_timeout', 'request_timeout'})


class _Pump:
    def __init__(self):
        self.dirty = False
        self.thread = None
        self.hello = False
        self.failures = 0


class RemoteDrawService:
    def __init__(self, connect, draw):
        self.connect = connect
        self.draw = draw
        self.engine = DrawSyncEngine(draw, connect.local_id)
        self.lock = threading.Lock()
        self.pumps = {}
        self.stopping = threading.Event()
        self.on_status = lambda: None
        self.announced = set()      # Peers known to speak olive-draw/1.
        self.unsupported = set()    # Desktops that answered the probe without Draw.
        self.probing = set()
        draw.listeners.append(self._local_change)

    # --- authority ---------------------------------------------------------------
    def permitted(self, peer, *, db=None):
        """Current local decision; Ask is not offered for live Draw sync."""
        s = self.connect
        try:
            record = s.device(peer, timeout=.25) if db is None else s.repository.get(db, peer)
        except Exception:
            return False
        if not record or record.get('trust_state') != 'paired' or record.get('revoked_at') is not None:
            return False
        return PermissionService.evaluate_device(record['permissions'], CAPABILITY) == PermissionDecision.ALLOW

    def _authorize(self, request, channel):
        s = self.connect
        if s.closed or s.network is None or channel.public is None:
            raise protocol.DrawProtocolError('device_not_paired')
        if request['source_device_id'] != channel.peer:
            raise protocol.DrawProtocolError('source_mismatch')
        if request['target_device_id'] != s.local_id:
            raise protocol.DrawProtocolError('wrong_target')
        with s.repository.transaction(timeout=.25, read_only=True) as db:
            record = s.repository.get(db, channel.peer)
            if not record or record.get('trust_state') != 'paired' or record.get('revoked_at') is not None:
                raise protocol.DrawProtocolError('device_not_paired')
            if record.get('public_identity') != channel.public:
                raise protocol.DrawProtocolError('identity_mismatch')
            metadata = next((c for c in s.repository.get(db, s.local_id)['capabilities'] if c['capability'] == CAPABILITY), {})
            if metadata.get('policy_disabled'):
                raise protocol.DrawProtocolError('capability_unavailable')
            if PermissionService.evaluate_device(record['permissions'], CAPABILITY) != PermissionDecision.ALLOW:
                raise protocol.DrawProtocolError('permission_off')
        protocol.check_fresh(request, int(s.clock()))

    # --- receiving (channel thread) ----------------------------------------------
    def receive(self, raw, channel, write):
        request_id = None
        try:
            request = protocol.decode_request(raw)
            request_id = request['request_id']
            with self.lock:
                self.announced.add(channel.peer)
                self.unsupported.discard(channel.peer)
            self._authorize(request, channel)
            if self.draw.unavailable:
                raise protocol.DrawProtocolError('draw_unavailable')
            result = self.engine.handle(channel.peer, request)
            write(protocol.encode_response(request_id, result=result))
        except protocol.DrawProtocolError as failure:
            write(protocol.encode_response(request_id, error=str(failure)))
            return
        except ConnectError:
            write(protocol.encode_response(request_id, error='device_not_paired'))
            return
        except Exception:
            logger.warning('Draw sync request failed (%s)', 'storage')
            write(protocol.encode_response(request_id, error='draw_unavailable'))
            return
        self.kick(channel.peer)

    # --- channel lifecycle ----------------------------------------------------------
    def channel_ready(self, peer):
        channel = self._channel(peer)
        with self.lock:
            pump = self.pumps.setdefault(peer, _Pump())
            pump.hello = False
            pump.failures = 0
            probe = channel is not None and channel.outbound and peer not in self.announced and peer not in self.probing
            if probe:
                self.probing.add(peer)
        if probe:
            threading.Thread(target=self._probe, args=(peer, channel), name='olive-draw-probe', daemon=True).start()
        self.kick(peer)

    def _probe(self, peer, channel):
        """Ask a desktop we dialed which optional protocols it speaks (read-only)."""
        try:
            now = int(self.connect.clock())
            raw = canonical(dict(request_id=str(uuid.uuid4()), protocol_version=CONNECT_PROTOCOL,
                                 source_device_id=self.connect.local_id, target_device_id=peer,
                                 capability='connect.ping', operation='protocols', arguments={},
                                 timestamp=now, expires_at=now + 60))
            response = channel.request(raw, timeout=15)
            result = response.get('result') if response.get('state') == 'completed' else None
            supported = isinstance(result, dict) and isinstance(result.get('protocols'), list) and PROTOCOL in result['protocols']
            with self.lock:
                (self.announced if supported else self.unsupported).add(peer)
            if supported:
                self.kick(peer)
            else:
                self.engine.set_state(peer, 'unsupported')
                self.on_status()
        except Exception:
            logger.info('Draw protocol probe did not complete')
        finally:
            with self.lock:
                self.probing.discard(peer)

    def channel_closed(self, peer):
        self.engine.set_state(peer, 'offline')
        self.on_status()

    def permission_changed(self, peer):
        if self.permitted(peer):
            self.channel_ready(peer)   # Newly allowed: catch-up starts now.
        else:
            self.engine.forget(peer)
            self.engine.set_state(peer, 'off')
            self.on_status()

    def _local_change(self, drawing_id, source_peer):
        network = self.connect.network
        if network is None:
            return
        with network.lock:
            online = [p for p, channel in network.channels.items() if not channel.stop.is_set()]
        for device in online:
            if device != source_peer or drawing_id is None:
                self.kick(device)
        self.on_status()

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
            pump.thread = threading.Thread(target=self._run, args=(peer, pump), name='olive-draw-sync', daemon=True)
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
            except (DrawSyncError, ConnectError, protocol.DrawProtocolError) as failure:
                code = str(failure)
                self.engine.set_state(peer, 'offline' if code in SENDER_ERRORS else 'error', error=code)
                self.on_status()
                if code in ('permission_off', 'device_not_paired', 'identity_mismatch', 'unsupported_protocol'):
                    continue
                pump.failures += 1
                if pump.failures > len(BACKOFF) or self._channel(peer) is None:
                    continue
                with self.lock:
                    pump.dirty = True
                if self.stopping.wait(BACKOFF[pump.failures - 1]):
                    return
            except Exception:
                logger.warning('Draw sync pump failed (%s)', 'internal')
                self.engine.set_state(peer, 'error', error='draw_unavailable')
                self.on_status()

    def _send(self, channel, peer, operation, arguments):
        s = self.connect
        raw = protocol.encode_request(str(uuid.uuid4()), s.local_id, peer, operation, arguments, int(s.clock()))
        response = channel.draw_request(raw)
        if response['state'] != 'completed':
            raise DrawSyncError(response['error'])
        return response['result']

    # --- status ------------------------------------------------------------------------
    def status(self, peer):
        state = self.engine.state(peer)
        with self.lock:
            unsupported = peer in self.unsupported
        if not self.permitted(peer):
            state['state'] = 'off'
        elif unsupported:
            state['state'] = 'unsupported'
        elif self._channel(peer) is None and state.get('state') != 'error':
            state['state'] = 'offline'
        try:
            state['pending'] = self.engine.pending(peer) if not self.draw.unavailable else 0
            state['pending_assets'] = self.engine.pending_assets() if not self.draw.unavailable else 0
            state['last_sync'] = self.engine.peer(peer)['last_sync']
            state['refused'] = len(self.engine.refused.get(peer, {}))
        except Exception:
            state['pending'] = None
        if state.get('state') == 'synced' and (state.get('pending') or state.get('pending_assets')):
            state['state'] = 'syncing'
        state.pop('updated', None)
        return state

    def close(self):
        self.stopping.set()
        with self.lock:
            threads = [p.thread for p in self.pumps.values() if p.thread is not None]
        deadline = time.monotonic() + 4
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(max(0, deadline - time.monotonic()))
