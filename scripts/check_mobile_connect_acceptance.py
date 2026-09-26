"""Read-only C9.2 desktop receipts, restricted to the selected OLIVE iPhone.

Does not start OLIVE, open sockets, load the vault, or inspect chat content.
Run: python scripts/check_mobile_connect_acceptance.py [--profile PATH] [--peer UUID]
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--peer')
    args = parser.parse_args()
    if args.profile:
        profile = args.profile.expanduser()
    elif os.environ.get('OLIVE_DATA_DIR'):
        profile = Path(os.environ['OLIVE_DATA_DIR']).expanduser()
    else:
        choices = [p for p in (Path.home()/'.olive', Path.home()/'.dmdo') if (p/'connect/devices.sqlite3').is_file()]
        if len(choices) != 1:
            parser.error('Use --profile with the desktop’s configured profile; no location was guessed.')
        profile = choices[0]
    path = profile/'connect/devices.sqlite3'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2) as db:
        db.execute('PRAGMA query_only=ON')
        peers = []
        for (raw,) in db.execute('SELECT record FROM devices WHERE local=0'):
            record = json.loads(raw)
            if (record['device_id'] == args.peer) if args.peer else (record['display_name'] == 'OLIVE iPhone'):
                peers.append(record)
        if len(peers) != 1:
            parser.error('Expected one OLIVE iPhone record. Use --peer with its UUID from Devices.')
        peer = peers[0]
        print(json.dumps({k: peer[k] for k in ('device_id','display_name','trust_state','revoked_at')}, indent=2))
        print('Remote AI rules:',json.dumps([r for r in peer['permissions'] if r.get('capability') == 'models.remote']))
        for row in db.execute('SELECT job,preset,input_bytes,output_bytes,state,error,duration_ms FROM remote_inference_v1 WHERE peer=? ORDER BY created DESC,rowid DESC LIMIT 10',(peer['device_id'],)):
            print(json.dumps(dict(zip(('job_id','preset','input_bytes','output_bytes','state','error','duration_ms'),row))))
        print('Metadata receipts only; terminal ledger state alone does not prove provider cleanup.')

if __name__ == '__main__':
    main()
