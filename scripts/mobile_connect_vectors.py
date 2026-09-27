"""Canonical public C2/C3/C7 vectors from production encoders; never user keys.

Generate: python scripts/mobile_connect_vectors.py --write
Check: python scripts/mobile_connect_vectors.py
Swift reverse output: --swift-output /tmp/olive-swift-vectors.json
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.connect.contracts import canonical
from olive.connect.identity import fingerprint, validate_public
from olive.connect.pairing_wire import decode_offer
from olive.connect.pairing_completion import PairingCompletion
from olive.connect.inference_protocol import InferenceRequest, response
from olive.connect.network_wire import frame, header

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/mobile_connect/vectors.json'

def admission_vectors(v):
    return {code: dict(protocol_version='olive-inference/1',
                       request_id=v['start']['request_id'], job_id=v['start']['job_id'],
                       result=None, error=code)
            for code in ('busy', 'rate_limited', 'model_unavailable', 'unknown_request')}

def check(v):
    offer, reply = v['offer'], v['reply']
    for part in (offer, reply):
        decode_offer(canonical(part), offer['created_at'])
        validate_public(part['identity'])
    assert v['fingerprint'] == fingerprint(offer['identity'])
    assert v['binding'] == hashlib.sha256(canonical([offer, reply])).hexdigest()
    assert v['receipt_message'] == PairingCompletion.message(offer, reply, reply['identity']['device_id']).decode()
    for name, kind in [('start', 9), ('poll', 9), ('cancel', 9), ('status', 9), ('response', 10), ('capabilities', 10)]:
        raw = canonical(v[name])
        (InferenceRequest.decode if kind == 9 else response)(raw)
        encoded = frame(kind, raw)
        assert v[name + '_frame'] == encoded.hex()
        assert header(encoded[:6]) == (len(raw), kind)
    assert v['hello_frame'] == frame(4).hex()
    assert v['admission_errors'] == admission_vectors(v)
    for code, value in v['admission_errors'].items():
        raw = canonical(value)
        assert response(raw)['error'] == code
        assert v['admission_error_frames'][code] == frame(10, raw).hex()

def generate():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from olive.connect.identity import public_identity
    from olive.connect.inference_protocol import digest
    # Random synthetic keys discarded immediately. Only public signed certificates
    # are committed; fixtures are never enrolled in production.
    now = 1780000000
    source = '11111111-1111-4111-8111-111111111111'
    target = '22222222-2222-4222-8222-222222222222'
    job = '33333333-3333-4333-8333-333333333333'
    sid = '44444444-4444-4444-8444-444444444444'
    offer = dict(protocol='olive-pairing-tls13/2', session_id=sid, created_at=now, expires_at=now+120,
                 identity=public_identity(target, Ed25519PrivateKey.generate(), now),
                 endpoint={'address': '192.168.1.2', 'port': 54321}, display_name='OLIVE fixture 🫒')
    reply = dict(offer, identity=public_identity(source, Ed25519PrivateKey.generate(), now), display_name='OLIVE iPhone')
    messages = [{'role': 'user', 'content': 'Swift / café 🫒\n\t"17 × 23"'}]
    args = dict(preset='normal', messages=messages, input_fingerprint=digest(messages), max_tokens=2048, max_output_bytes=64000, seconds=120)
    v = dict(offer=offer, reply=reply, fingerprint=fingerprint(offer['identity']),
             binding=hashlib.sha256(canonical([offer, reply])).hexdigest(),
             receipt_message=PairingCompletion.message(offer, reply, source).decode())
    for name in ('start','poll','cancel','status'):
        req = InferenceRequest(job if name == 'start' else sid, 'olive-inference/1', source, target, job, name,
                               args if name == 'start' else {'after': 0} if name == 'poll' else {}, now, now+120)
        v[name] = json.loads(req.encode())
    v['response'] = dict(protocol_version='olive-inference/1', request_id=sid, job_id=job,
                         result=dict(state='streaming', events=[dict(sequence=1,text='391 🫒')], error=None), error=None)
    v['capabilities'] = dict(protocol_version='olive-inference/1', request_id=sid, job_id=job,
                             result=dict(presets=dict(fast=True,normal=True,max=False),permission='allow',busy=False),error=None)
    for name in ('start','poll','cancel','status','response','capabilities'):
        v[name+'_frame'] = frame(10 if name in ('response','capabilities') else 9, canonical(v[name])).hex()
    v['hello_frame'] = frame(4).hex()
    v['admission_errors'] = admission_vectors(v)
    v['admission_error_frames'] = {code: frame(10, canonical(value)).hex()
                                   for code, value in v['admission_errors'].items()}
    return v

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--write', action='store_true'); parser.add_argument('--swift-output')
    args = parser.parse_args()
    if args.write:
        FIXTURE.write_bytes(canonical(generate()) + b'\n')
    value = json.loads(FIXTURE.read_bytes()); check(value)
    if args.swift_output:
        reverse = json.loads(Path(args.swift_output).read_bytes())
        for name in ('start','poll','cancel','status'):
            assert InferenceRequest.decode(canonical(reverse[name])) == InferenceRequest.decode(canonical(value[name]))
        for name in ('response','capabilities'):
            assert response(canonical(reverse[name])) == response(canonical(value[name]))
        for code, expected in value['admission_errors'].items():
            assert response(canonical(reverse['admission_errors'][code])) == response(canonical(expected))
    print('Production Python vectors passed; SHA-256:', hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
