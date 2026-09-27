"""Synthetic public C5/C6/C8 interop vectors using production Python codecs."""
import argparse
import base64
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from olive.connect.contracts import canonical, ConnectError
from olive.connect.identity import public_identity
from olive.connect.file_protocol import FileRequest, response as file_response
from olive.connect.studio_protocol import StudioRequest, validate_result
from olive.sync.records import SyncRecord, SyncRequest
from olive.sync.provenance import sign
from olive.personal.validation import task, calendar
from olive.personal.calendar import event
from olive.personal.reminders import validate_reminder

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/mobile_connect/companion.json'
SOURCE = '11111111-1111-4111-8111-111111111111'
TARGET = '22222222-2222-4222-8222-222222222222'
REQUEST = '33333333-3333-4333-8333-333333333333'
WORKSPACE = '44444444-4444-4444-8444-444444444444'
NOW = 1780000000

def generate():
    key = Ed25519PrivateKey.generate()
    public = public_identity(SOURCE, key, NOW)
    payloads = [('task', task({'title':'Synthetic task 🫒'})), ('calendar', calendar({'title':'Synthetic calendar'})),
        ('event', event({'calendar_id':'a'*32,'title':'Synthetic event','start':'2026-09-28T09:00:00+00:00','end':'2026-09-28T10:00:00+00:00','timezone':'UTC'})),
        ('reminder', validate_reminder({'target_kind':'task','target_id':'b'*32,'at':'2026-09-28T08:00:00+00:00','timezone':'UTC'})),
        ('conversation', {'title':'Selected synthetic Chat','project_id':None,'created_at':'2026-09-27T10:00:00+00:00'}),
        ('message', {'conversation_id':'c'*32,'after':None,'role':'assistant','content':'Synthetic answer\n```swift\nlet n = 391\n```','created_at':'2026-09-27T10:00:00+00:00'})]
    records=[]
    for index,(kind,payload) in enumerate(payloads):
        value=dict(kind=kind,record_id=f'{index+10:032x}',schema_version=1,revision=f'{index+1:08x}-1111-4111-8111-111111111111',ancestry={SOURCE:1},origin_device_id=SOURCE,editor_device_id=SOURCE,updated_at='2026-09-27T10:00:00+00:00',deleted=False,payload=payload,editor_identity=public,signature='')
        records.append(sign(value,public,key))
    tombstone=dict(records[0],deleted=True,payload={},revision='77777777-1111-4111-8111-111111111111',ancestry={SOURCE:2})
    records.append(sign(tombstone,public,key))
    invalid=[]
    for updates in [dict(schema_version=2),dict(ancestry={SOURCE:True}),dict(deleted=True),dict(signature='A'*88),dict(payload=dict(payloads[0][1],status='invented')),dict(updated_at='not-a-date')]:
        value=dict(records[0],**updates)
        invalid.append(sign(value,public,key) if 'signature' not in updates else value)
    binary=b'Synthetic C6 bytes\x00\xff\x01'
    meta=dict(name='fixture.bin',size=len(binary),sha256=hashlib.sha256(binary).hexdigest(),mime='application/octet-stream')
    files={op:base64.b64encode(FileRequest(REQUEST,'olive-files/1',WORKSPACE,SOURCE,TARGET,op,meta if op=='offer' else {'offset':0} if op=='chunk' else {},NOW,NOW+120).encode(binary if op=='chunk' else b'')).decode() for op in ('offer','chunk','complete','cancel','status')}
    studio={}
    for op,args in [('workspaces',{}),('tree',{}),('read',{'path':'main.py'}),('save',{'path':'main.py','text':'print(391)\n','expected_hash':'a'*64}),('build',{}),('test',{}),('run',{}),('run_status',{'job_id':REQUEST}),('run_cancel',{'job_id':REQUEST})]:
        studio[op]=asdict(StudioRequest(REQUEST,'olive-studio/1',SOURCE,TARGET,None if op=='workspaces' else WORKSPACE,0 if op=='workspaces' else 1,op,args,NOW,NOW+120))
    return dict(records=records,invalid_records=invalid,files=files,studio=studio)

def check(v):
    for record in v['records']: SyncRecord.parse(record)
    for record in v['invalid_records']:
        try: SyncRecord.parse(record)
        except ConnectError: pass
        else: raise AssertionError('Malformed sync record accepted')
    for packet in v['files'].values(): FileRequest.decode(base64.b64decode(packet))
    for req in v['studio'].values(): StudioRequest.decode(canonical(req))

def reverse(v, expected):
    for kind, value in v['studio'].items():
        assert StudioRequest.decode(canonical(value)) == StudioRequest.decode(canonical(expected['studio'][kind]))
    for op, packet in v['files'].items():
        assert base64.b64decode(packet) == base64.b64decode(expected['files'][op])
        FileRequest.decode(base64.b64decode(packet))
    for record in v['records']: SyncRecord.parse(record)
    SyncRequest.decode(canonical(v['sync_request']))
    assert len(v['records']) == 1 and v['records'][0]['payload']['title'] == 'Swift authored fixture'

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');parser.add_argument('--swift-output');args=parser.parse_args()
    if args.write: FIXTURE.write_bytes(canonical(generate())+b'\n')
    value=json.loads(FIXTURE.read_bytes());check(value)
    if args.swift_output: reverse(json.loads(Path(args.swift_output).read_bytes()),value)
    print('C5/C6/C8 production Python vectors passed')
