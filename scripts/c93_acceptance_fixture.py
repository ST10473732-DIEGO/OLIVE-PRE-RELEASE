#!/usr/bin/env python3
"""Owned C9.3 fixtures and metadata-only, read-only desktop timing capture.

No registration, sharing, permission, trust, firewall or profile mutation. Run
create on CachyOS, then open/share the printed workspace through OLIVE's UI.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time


def create():
    root = Path(tempfile.mkdtemp(prefix='olive-c93-acceptance-'))
    shared = root / 'C93 Acceptance Shared'
    unshared = root / 'C93 Acceptance Unshared'
    shared.mkdir()
    unshared.mkdir()
    (shared / 'tests').mkdir()
    (shared / 'main.py').write_text(
        'from pathlib import Path\nimport time\n'
        'root = Path(__file__).resolve().parent\n'
        'with (root / "acceptance-runs.txt").open("a") as log:\n'
        '    log.write("START\\n")\n'
        'print("C93 Acceptance running", flush=True)\n'
        'time.sleep(75)\n'
        'with (root / "acceptance-runs.txt").open("a") as log:\n'
        '    log.write("DONE\\n")\n'
        'print("C93 Acceptance finished", flush=True)\n', encoding='utf-8')
    (shared / 'notes.txt').write_text('C93 Acceptance original\n', encoding='utf-8')
    (shared / 'tests' / 'test_acceptance.py').write_text(
        'import unittest\nclass Acceptance(unittest.TestCase):\n'
        '    def test_owned_fixture(self):\n'
        '        self.assertEqual(17 * 23, 391)\n', encoding='utf-8')
    (unshared / 'private-fixture.txt').write_text('C93 Acceptance unshared synthetic content\n', encoding='utf-8')
    block = bytes(range(256)) * 4096
    for size in (5, 64):
        path = root / f'olive-c93-{size}MiB.bin'
        digest = hashlib.sha256()
        with path.open('xb') as stream:
            for _ in range(size):
                stream.write(block)
                digest.update(block)
        print(f'FILE {path}\nSHA256 {digest.hexdigest()}')
    # Sparse owned fixture: tests the existing limit without sending 65 MiB.
    with (root / 'C93-Acceptance-oversize.bin').open('xb') as stream:
        stream.truncate(65 * 1024 * 1024)
    (root / 'collision.bin').write_bytes(b'C93 Acceptance preserve existing target\n')
    print(f'FIXTURE_ROOT {root}\nSHARE_ONLY {shared}\nKEEP_UNSHARED {unshared}')


def observe(database, seconds):
    # Exact operator-supplied profile path; never guess between ~/.olive/.dmdo.
    database = database.expanduser().resolve(strict=True)
    db = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=.25)
    db.execute('PRAGMA query_only=ON')
    cursor = db.execute('SELECT COALESCE(MAX(id),0) FROM activity').fetchone()[0]
    started = time.monotonic()
    receipts, peers, seen = {}, set(), set()
    print('CAPTURE_START_UTC', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), flush=True)
    try:
        while time.monotonic() - started < seconds:
            # Read only explicitly named synthetic transfer metadata. Content,
            # identities, keys, chat, sync payloads and private paths are omitted.
            rows = db.execute('SELECT transfer_id, record FROM file_transfers_v1 WHERE '
                "json_extract(record, '$.metadata.name') IN "
                "('olive-c93-64MiB.bin','C93-Acceptance-invalid-hash.bin')").fetchall()
            for transfer, raw in rows:
                row = json.loads(raw)
                peers.add(row['peer_id'])
                status = (row['state'], row['received_size'])
                if receipts.get(transfer) != status:
                    receipts[transfer] = status
                    print(json.dumps(dict(elapsed=round(time.monotonic()-started, 3), transfer=transfer,
                        state=status[0], received_bytes=status[1], updated_at=row['updated_at'])), flush=True)
            events = db.execute('SELECT id, source_device_id, request_id, timestamp, result_state '
                'FROM activity WHERE id>? ORDER BY id', (cursor,)).fetchall()
            for event_id, peer, transfer, timestamp, state in events:
                if transfer in receipts or (peer in peers and state in ('connection_closed', 'connection_authenticated')):
                    print(json.dumps(dict(audit_id=event_id, timestamp=timestamp, transfer=transfer, event=state)), flush=True)
                cursor = event_id
            # Check only the synthetic failed-hash receipt's opaque artifact.
            for transfer, raw in rows:
                row = json.loads(raw)
                if row['metadata']['name'] == 'C93-Acceptance-invalid-hash.bin' and row['state'] == 'failed' and transfer not in seen:
                    import uuid
                    uuid.UUID(transfer)
                    inbox = database.parent.parent / 'quarantine' / 'connect-inbox'
                    print(json.dumps(dict(transfer=transfer, failed_hash_artifact_absent=
                        not (inbox / (transfer + '.bin')).exists() and not (inbox / (transfer + '.part')).exists())), flush=True)
                    seen.add(transfer)
            time.sleep(.25)
    finally:
        db.close()
    print('CAPTURE_END', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'observe'))
    parser.add_argument('--database', type=Path, help='exact configured Connect devices.sqlite3 path (observe only)')
    parser.add_argument('--seconds', type=int, default=180)
    args = parser.parse_args()
    if args.action == 'create':
        create()
    elif not args.database or not 1 <= args.seconds <= 600:
        parser.error('observe requires --database and --seconds between 1 and 600')
    else:
        observe(args.database, args.seconds)
