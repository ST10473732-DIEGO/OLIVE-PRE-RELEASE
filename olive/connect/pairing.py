"""Explicit local pairing orchestration; never a Connect action authority."""
from copy import deepcopy
import hmac
import time
import uuid
from threading import RLock

from .contracts import ConnectError, canonical, display_name
from .identity import digest, fingerprint
from .pairing_wire import PROTOCOL, DESKTOP_PROTOCOL, LIFETIME, PairingTLS, decode_offer, encode_offer

TERMINAL = {'completed', 'cancelled', 'expired', 'failed', 'interrupted'}


class PairingService:
    def __init__(self, device_service, identities, *, monotonic=time.monotonic):
        self.devices, self.identities = device_service, identities
        self.repository = device_service.repository
        self.clock, self.monotonic = device_service.clock, monotonic
        self._sessions = {}
        self._lock = RLock()
        self.closed = False
        from .pairing_completion import PairingCompletion
        self.completion = PairingCompletion(device_service)

    def _audit(self, session, state):
        with self.repository.transaction() as db:
            self.repository.audit(db, self.devices.local_id, session, None, int(self.clock()), 'pairing_' + state)

    def _new(self, offer, *, server):
        if self.closed or self.devices.closed:
            raise ConnectError('pairing_closed')
        self.expire()
        self._sessions = {sid: session for sid, session in self._sessions.items()
                          if session['state'] not in TERMINAL}
        if len(self._sessions) >= 32:
            raise ConnectError('pairing_capacity_reached')
        sid = offer['session_id']
        with self.repository.transaction() as db:
            if db.execute('SELECT 1 FROM pairing_ledger WHERE session_id=?', (sid,)).fetchone():
                raise ConnectError('pairing_replayed')
            if db.execute('SELECT COUNT(*) FROM pairing_ledger').fetchone()[0] >= 10000:
                raise ConnectError('pairing_capacity_reached')
            db.execute('INSERT INTO pairing_ledger(session_id,state) VALUES(?,?)', (sid, 'consumed'))
        self._sessions[sid] = dict(state='offer_ready', offer=deepcopy(offer), reply=None,
            expires_at=offer['expires_at'],
            server=server, deadline=self.monotonic() + min(LIFETIME, offer['expires_at'] - self.clock()),
            tls=None, local_confirmed=False, peer_confirmed=False, confirmation=b'', peer=None)
        self._audit(sid, 'created')
        return sid

    def create_offer(self, *, endpoint=None):
        with self._lock:
            if self.closed or self.devices.closed:
                raise ConnectError('pairing_closed')
            now = int(self.clock())
            offer = dict(protocol=PROTOCOL, session_id=str(uuid.uuid4()), created_at=now,
                         expires_at=now + LIFETIME, identity=self.identities.ensure())
            if endpoint is not None:
                offer.update(protocol=DESKTOP_PROTOCOL, endpoint=endpoint,
                             display_name=self.devices.this_device()['display_name'])
                encode_offer(offer, now)
            self._new(offer, server=True)
            return encode_offer(offer, now)

    def accept_offer(self, raw):
        with self._lock:
            if self.closed or self.devices.closed:
                raise ConnectError('pairing_closed')
            offer = decode_offer(raw, self.clock())
            public = self.identities.ensure()
            sid = self._new(offer, server=False)
            reply = dict(offer, identity=public)
            if offer['protocol'] == DESKTOP_PROTOCOL:
                reply['display_name'] = self.devices.this_device()['display_name']
            self._sessions[sid]['reply'] = reply
            self._start(sid)
            return encode_offer(reply, self.clock())

    def receive_reply(self, raw):
        with self._lock:
            reply = decode_offer(raw, self.clock())
            sid = reply['session_id']
            session = self._active(sid)
            if not session['server'] or session['reply'] is not None:
                raise ConnectError('pairing_replayed')
            if any(reply[k] != session['offer'][k] for k in ('protocol', 'created_at', 'expires_at') + (('endpoint',) if reply['protocol'] == DESKTOP_PROTOCOL else ())):
                self._finish(sid, 'failed')
                raise ConnectError('pairing_transcript_mismatch')
            session['reply'] = reply
            self._start(sid)

    def _start(self, sid):
        session = self._sessions[sid]
        offer, reply = session['offer'], session['reply']
        local, remote = (offer, reply) if session['server'] else (reply, offer)
        try:
            if local['identity']['device_id'] == remote['identity']['device_id']:
                raise ConnectError('pairing_self_identity')
            self._check_candidate(remote['identity'])
            binding = digest(canonical([offer, reply]))
            session['tls'] = PairingTLS(self.identities.key_store.load(local['identity']),
                local['identity'], remote['identity'], server=session['server'], binding=binding)
            session['peer'] = deepcopy(remote['identity'])
            session['state'] = 'peer_received'
        except Exception:
            self._finish(sid, 'failed')
            raise ConnectError('pairing_identity_rejected') from None

    def _check_candidate(self, public):
        with self.repository.transaction() as db:
            existing = self.repository.get(db, public['device_id'])
            # Also prohibit a revoked key reappearing under a new device ID.
            from .identity import validate_public
            key = validate_public(public).public_key()
            for record in self.repository.devices_from_db(db):
                if record.get('public_identity') and validate_public(record['public_identity']).public_key() == key:
                    if record['trust_state'] == 'revoked':
                        raise ConnectError('device_revoked')
            if existing:
                raise ConnectError('identity_already_known')

    def _active(self, sid):
        if self.closed or self.devices.closed:
            raise ConnectError('pairing_closed')
        session = self._sessions.get(sid)
        if session is None or session['state'] in TERMINAL:
            raise ConnectError('pairing_not_active')
        if self.clock() >= session['offer']['expires_at'] or self.monotonic() >= session['deadline']:
            self._finish(sid, 'expired')
            raise ConnectError('pairing_expired')
        return session

    def exchange(self, sid, incoming=b''):
        with self._lock:
            session = self._active(sid)
            tls = session['tls']
            if tls is None:
                raise ConnectError('pairing_not_ready')
            try:
                outgoing = tls.step(incoming)
                if tls.ready:
                    session['state'] = 'confirmed' if session['local_confirmed'] else 'fingerprint_pending'
                    part = tls.receive_confirmation(8192 if session['offer']['protocol'] == DESKTOP_PROTOCOL else 128)
                    session['confirmation'] += part
                    if session['offer']['protocol'] == DESKTOP_PROTOCOL:
                        for _ in range(4):
                            part = tls.receive_confirmation(8192)
                            if not part:
                                break
                            session['confirmation'] += part
                    expected = b'OLIVE-CONFIRM/1:' + tls.binding
                    received = session['confirmation']
                    if session['offer']['protocol'] == DESKTOP_PROTOCOL:
                        if len(received) > len(expected) + 90:
                            raise ConnectError('pairing_confirmation_invalid')
                        if not expected.startswith(received[:len(expected)]):
                            raise ConnectError('pairing_confirmation_invalid')
                        if len(received) >= len(expected):
                            session['peer_confirmed'] = True
                        proof = received[len(expected):]
                        if proof and (proof[:1] != b'\n' or (len(proof) == 90 and proof[-1:] != b'\n')):
                            raise ConnectError('pairing_confirmation_invalid')
                        if len(proof) == 90 and session['local_confirmed']:
                            self.completion.receive(sid, proof[1:-1].decode('ascii'))
                            session['receipt_received'] = True
                    else:
                        if not expected.startswith(received):
                            raise ConnectError('pairing_confirmation_invalid')
                        if received == expected:
                            session['peer_confirmed'] = True
                return outgoing
            except Exception:
                self._finish(sid, 'failed')
                raise ConnectError('pairing_authentication_failed') from None

    def preview(self, sid):
        with self._lock:
            session = self._active(sid)
            if not session['tls'] or not session['tls'].ready:
                raise ConnectError('pairing_not_authenticated')
            return dict(session_id=sid, state=session['state'], candidate=deepcopy(session['peer']),
                        fingerprint=fingerprint(session['peer']), expires_at=session['offer']['expires_at'],
                        comparison=session['tls'].comparison())

    def presentation(self, sid):
        """Renderer-safe state only. No certificate, TLS object or private material."""
        with self._lock:
            self.expire()
            session = self._sessions.get(sid)
            if session is None:
                raise ConnectError('pairing_not_active')
            result = dict(session_id=sid, state=session['state'], expires_at=session['expires_at'])
            if session['state'] not in TERMINAL:
                result['expires_at'] = session['offer']['expires_at']
            if session['state'] in {'fingerprint_pending', 'confirmed'}:
                preview = self.preview(sid)
                result.update(comparison=preview['comparison'], fingerprint=preview['fingerprint'],
                              candidate_id=preview['candidate']['device_id'])
                if session['offer']['protocol'] == DESKTOP_PROTOCOL:
                    remote = session['reply'] if session['server'] else session['offer']
                    result['candidate_name'] = remote['display_name']
                if session['offer']['protocol'] == PROTOCOL and session['local_confirmed'] and session['peer_confirmed']:
                    record = self.complete(sid)
                    result = dict(session_id=sid, state='completed', device_id=record['device_id'])
            return result

    def confirm(self, sid, compared_value):
        """Local human input only. Never called by a protocol message or model tool."""
        with self._lock:
            session = self._active(sid)
            expected = self.preview(sid)['comparison']
            if (type(compared_value) is not str or not compared_value.isascii()
                    or not hmac.compare_digest(compared_value, expected)):
                self._finish(sid, 'failed')
                raise ConnectError('pairing_comparison_mismatch')
            if not session['local_confirmed']:
                if session['offer']['protocol'] == DESKTOP_PROTOCOL:
                    receipt = self.completion.record_local_confirmation(session)
                session['tls'].confirm()
                if session['offer']['protocol'] == DESKTOP_PROTOCOL:
                    session['tls'].connection.send(b'\n' + receipt.encode('ascii') + b'\n')
                session['local_confirmed'] = True
                session['state'] = 'confirmed'
                self._audit(sid, 'local_confirmed')

    def complete(self, sid, *, name='Paired device'):
        with self._lock:
            session = self._sessions.get(sid)
            if session and session.get('offer') and session['offer']['protocol'] == DESKTOP_PROTOCOL:
                return self.complete_desktop(sid)
            with self.repository.transaction() as db:
                desktop = db.execute('SELECT 1 FROM pairing_completion_v1 WHERE session_id=?', (sid,)).fetchone()
            if desktop:
                return self.complete_desktop(sid)
            # Durable idempotent local completion; wire/session reuse stays rejected.
            if self.closed or self.devices.closed:
                raise ConnectError('pairing_closed')
            name = display_name(name)
            completion_hash = digest(canonical({'name': name})).hex()
            with self.repository.transaction() as db:
                saved = db.execute('SELECT state,peer_id,completion_hash FROM pairing_ledger WHERE session_id=?',
                                   (sid,)).fetchone()
                if saved and saved[0] == 'completed':
                    if saved[2] != completion_hash:
                        raise ConnectError('changed_duplicate')
                    record = self.repository.get(db, saved[1])
                    if not record or record.get('trust_state') != 'paired':
                        raise ConnectError('device_not_paired')
                    return record
            session = self._active(sid)
            if not session['local_confirmed'] or not session['peer_confirmed']:
                raise ConnectError('pairing_confirmation_required')
            peer = session['peer']
            record = dict(device_id=peer['device_id'], display_name=display_name(name), platform='unknown',
                device_class='unknown', trust_state='paired', paired_at=int(self.clock()), last_seen=None,
                connection_state='offline', connection_kind='none', capabilities=[], permissions=[],
                revision=1, revoked_at=None, public_identity=deepcopy(peer), identity_fingerprint=fingerprint(peer))
            with self.repository.transaction() as db:
                if self.repository.get(db, peer['device_id']):
                    raise ConnectError('identity_already_known')
                # Recheck revoked key aliases atomically with trust creation.
                from .identity import validate_public
                key = validate_public(peer).public_key()
                for old in self.repository.devices_from_db(db):
                    if old.get('public_identity') and old['trust_state'] == 'revoked' and validate_public(old['public_identity']).public_key() == key:
                        raise ConnectError('device_revoked')
                # SQLite contention and candidate validation must not extend expiry.
                if (self.clock() >= session['offer']['expires_at']
                        or self.monotonic() >= session['deadline']):
                    raise ConnectError('pairing_expired')
                self.repository.put(db, record)
                db.execute("UPDATE pairing_ledger SET state='completed',peer_id=?,completion_hash=? WHERE session_id=?",
                           (peer['device_id'], completion_hash, sid))
                self.repository.audit(db, peer['device_id'], sid, None, int(self.clock()), 'pairing_completed')
            self._finish(sid, 'completed', audit=False)
            return record

    def complete_desktop(self, sid):
        with self._lock:
            record = self.completion.complete(sid)
            if sid in self._sessions and self._sessions[sid]['state'] != 'completed':
                self._finish(sid, 'completed', audit=False)
            return record

    def interrupt(self, sid):
        with self._lock:
            session = self._sessions.get(sid)
            if session and session['state'] not in TERMINAL:
                self._finish(sid, 'interrupted')

    def _finish(self, sid, state, *, audit=True):
        session = self._sessions[sid]
        if state == 'expired' and session['local_confirmed'] and session['offer']['protocol'] == DESKTOP_PROTOCOL:
            state = 'interrupted'
        if session['tls']:
            session['tls'].close()
        session.update(state=state, tls=None, peer=None, offer=None, reply=None, confirmation=b'')
        with self.repository.transaction() as db:
            db.execute('UPDATE pairing_ledger SET state=? WHERE session_id=?', (state, sid))
        if audit:
            self._audit(sid, state)

    def cancel(self, sid):
        with self._lock:
            self._active(sid)
            self._finish(sid, 'cancelled')

    def expire(self):
        with self._lock:
            for sid, session in list(self._sessions.items()):
                if session['state'] not in TERMINAL:
                    try:
                        self._active(sid)
                    except ConnectError:
                        pass

    def close(self):
        with self._lock:
            for sid, session in self._sessions.items():
                if session['state'] not in TERMINAL:
                    self._finish(sid, 'interrupted' if session['local_confirmed'] else 'cancelled')
            self._sessions.clear()
            self.closed = True
