"""Show the release gate of every runtime manifest entry; print candidate owner approvals.

    python packaging/release/release_gate.py                     # every entry and its gate state
    python packaging/release/release_gate.py --check             # exit 1 if an approval no longer matches its pins
    python packaging/release/release_gate.py --record ID --by NAME [--date YYYY-MM-DD]

States: unidentified -> license_identified -> engineering_reviewed -> release_approved.
--record only PRINTS an approval record bound to the entry's current fingerprint. It never
writes olive/runtime_manifest/release-approvals-<version>.json: adding the record there is the
owner's deliberate decision. It refuses entries whose engineering evidence is incomplete.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from olive.services import runtime_manifest  # noqa: E402


def rows(manifest: dict) -> list[dict]:
    result = []
    for entry in manifest['entries']:
        approval = manifest['_approvals'].get(entry['id'])
        result.append({'id': entry['id'], 'enabled': entry['enabled'], 'state': runtime_manifest.release_state(entry, manifest),
                       'fingerprint': runtime_manifest.fingerprint(entry),
                       'approval': 'none' if approval is None else
                       ('current' if runtime_manifest.release_approved(entry, manifest) else 'STALE (pins changed)'),
                       'reason': entry.get('reason') or ''})
    for identifier in set(manifest['_approvals']) - {e['id'] for e in manifest['entries']}:
        result.append({'id': identifier, 'enabled': False, 'state': 'unknown entry', 'fingerprint': '',
                       'approval': 'STALE (no such entry)', 'reason': ''})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--record', metavar='ID')
    parser.add_argument('--by', metavar='NAME')
    parser.add_argument('--date', default=datetime.date.today().isoformat())
    args = parser.parse_args(argv)
    manifest = runtime_manifest.load(args.version, environ={})
    if args.record:
        entry = next((e for e in manifest['entries'] if e['id'] == args.record), None)
        if entry is None:
            parser.error(f'unknown entry {args.record}')
        if not args.by:
            parser.error('--by names the person approving the release')
        if not (entry['enabled'] and runtime_manifest.complete(entry)):
            parser.error(f'{args.record} is not enabled with complete engineering evidence '
                         f'(state {runtime_manifest.release_state(entry, manifest)}); it cannot be approved')
        print(json.dumps({'id': entry['id'], 'fingerprint': runtime_manifest.fingerprint(entry), 'scope': 'public-release',
                          'approved_by': args.by, 'date': args.date, 'product_version': manifest['product_version'],
                          'note': ''}, indent=2))
        return 0
    table = rows(manifest)
    for row in table:
        print(f"{row['id']:<34} {('enabled' if row['enabled'] else 'disabled'):<9} {row['state']:<22} approval={row['approval']}")
    if args.check:
        stale = [r['id'] for r in table if r['approval'].startswith('STALE')]
        if stale:
            print('Stale approvals: ' + ', '.join(stale), file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
