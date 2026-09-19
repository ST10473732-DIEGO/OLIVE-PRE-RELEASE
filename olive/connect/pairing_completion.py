"""Durable C2 confirmation receipts, never enrollment from an unsolicited offer.

Only the C2 local comparison handler can create a local receipt. Recovery needs
that exact durable local receipt AND the peer's signed receipt for the same C2
transcript. These public receipts use the existing C2 identity key; they neither
replace the TLS exporter comparison nor authorize Connect actions.
"""
import base64
from copy import deepcopy
import json

from .contracts import ConnectError, canonical, _unique_object
from .identity import digest, validate_public, fingerprint
from .pairing_wire import DESKTOP_PROTOCOL, decode_offer

RECOVERY_PROTOCOL = 'olive-pairing-completion/1'
MAX_COMPLETION = 12288


class PairingCompletion:
    def __init__(self, service):
        self.service = service
        self.repository = service.repository

    @staticmethod
    def message(offer, reply, device_id):
        return canonical(dict(protocol=RECOVERY_PROTOCOL, session_id=offer['session_id'],
            transcript=digest(canonical([offer, reply])).hex(), device_id=device_id,
            confirmed_before=offer['expires_at']))

    def record_local_confirmation(self, session):
        offer, reply = session['offer'], session['reply']
        local = offer if session['server'] else reply
        key = self.service.identities.key_store.load(local['identity'])
        receipt = base64.b64encode(key.sign(self.message(offer, reply, self.service.local_id))).decode('ascii')
        record = dict(protocol=RECOVERY_PROTOCOL, offer=offer, reply=reply,
                      receipts={self.service.local_id: receipt})
        sid = offer['session_id']
        with self.repository.transaction() as db:
            if self.service.clock() >= offer['expires_at'] or self.service.pairing.monotonic() >= session['deadline']:
                raise ConnectError('pairing_expired')
            db.execute('INSERT INTO pairing_completion_v1 VALUES(?,?)', (sid, canonical(record).decode()))
        return receipt

    def load(self, sid):
        with self.repository.transaction() as db:
            row = db.execute('SELECT record FROM pairing_completion_v1 WHERE session_id=?', (sid,)).fetchone()
        if not row:
            raise ConnectError('pairing_confirmation_required')
        return json.loads(row[0])

    def export(self, sid):
        record = self.load(sid)
        return canonical(record).decode()

    def receive(self, sid, receipt):
        record = self.load(sid)
        peer = next(v['identity'] for v in (record['offer'], record['reply'])
                    if v['identity']['device_id'] != self.service.local_id)
        record['receipts'][peer['device_id']] = receipt
        return self.import_receipts(canonical(record))

    def import_receipts(self, raw):
        try:
            if type(raw) is not bytes or len(raw) > MAX_COMPLETION:
                raise ValueError()
            value = json.loads(raw, object_pairs_hook=_unique_object)
            if type(value) is not dict or set(value) != {'protocol', 'offer', 'reply', 'receipts'}:
                raise ValueError()
            if value['protocol'] != RECOVERY_PROTOCOL:
                raise ValueError()
            offer, reply = value['offer'], value['reply']
            sid = offer['session_id']
            # Validate the original transcript at its original creation time.
            for part in (offer, reply):
                decode_offer(canonical(part), offer['created_at'])
                if part['protocol'] != DESKTOP_PROTOCOL:
                    raise ValueError()
            saved = self.load(sid)  # A remote receipt NEVER supplies local confirmation.
            if saved['offer'] != offer or saved['reply'] != reply:
                raise ValueError()
            identities = {p['identity']['device_id']: p['identity'] for p in (offer, reply)}
            if type(value['receipts']) is not dict or not set(value['receipts']) <= set(identities):
                raise ValueError()
            for device_id, receipt in value['receipts'].items():
                if type(receipt) is not str or len(receipt) != 88:
                    raise ValueError()
                validate_public(identities[device_id]).public_key().verify(
                    base64.b64decode(receipt, validate=True), self.message(offer, reply, device_id))
            receipts = dict(saved['receipts'], **value['receipts'])
            if receipts.get(self.service.local_id) != saved['receipts'].get(self.service.local_id):
                raise ValueError()
            saved['receipts'] = receipts
            with self.repository.transaction() as db:
                ledger = db.execute('SELECT state FROM pairing_ledger WHERE session_id=?', (sid,)).fetchone()
                if not ledger or ledger[0] in ('cancelled', 'failed', 'expired'):
                    raise ConnectError('pairing_not_active')
                db.execute('UPDATE pairing_completion_v1 SET record=? WHERE session_id=?',
                           (canonical(saved).decode(), sid))
            return sid
        except ConnectError:
            raise
        except Exception:
            raise ConnectError('invalid_pairing_completion') from None

    def complete(self, sid):
        if self.service.closed:
            raise ConnectError('pairing_closed')
        saved = self.load(sid)
        offer, reply = saved['offer'], saved['reply']
        peer_part = next(v for v in (offer, reply) if v['identity']['device_id'] != self.service.local_id)
        peer = peer_part['identity']
        with self.repository.transaction() as db:
            ledger = db.execute('SELECT state,peer_id FROM pairing_ledger WHERE session_id=?', (sid,)).fetchone()
            if ledger and ledger[0] == 'completed':
                record = self.repository.get(db, ledger[1])
                if not record or record['trust_state'] != 'paired' or record['public_identity'] != peer:
                    raise ConnectError('device_not_paired')
                return record
            if not ledger or ledger[0] not in ('consumed', 'interrupted'):
                raise ConnectError('pairing_not_active')
            if set(saved['receipts']) != {offer['identity']['device_id'], reply['identity']['device_id']}:
                raise ConnectError('pairing_confirmation_required')
            if self.repository.get(db, peer['device_id']):
                raise ConnectError('identity_already_known')
            key = validate_public(peer).public_key()
            for old in self.repository.devices_from_db(db):
                if old.get('public_identity') and old['trust_state'] == 'revoked' and validate_public(old['public_identity']).public_key() == key:
                    raise ConnectError('device_revoked')
            record = dict(device_id=peer['device_id'], display_name=peer_part['display_name'],
                platform='unknown', device_class='desktop', trust_state='paired',
                paired_at=int(self.service.clock()), last_seen=None, connection_state='offline',
                connection_kind='none', capabilities=[], permissions=[], revision=1, revoked_at=None,
                public_identity=deepcopy(peer), identity_fingerprint=fingerprint(peer))
            self.repository.put(db, record)
            db.execute("UPDATE pairing_ledger SET state='completed',peer_id=? WHERE session_id=?", (peer['device_id'], sid))
            self.repository.audit(db, peer['device_id'], sid, None, int(self.service.clock()), 'pairing_completed')
        return record
