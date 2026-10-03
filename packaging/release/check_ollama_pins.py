"""Check the Ollama registry digests pinned in the runtime manifest for drift (read-only).

    python packaging/release/check_ollama_pins.py [--manifest PATH] [--json REPORT.json]

For every ollama-model entry with a pinned manifest digest, fetch the registry manifest
(bounded, TLS verified, nothing installed) and compare its SHA-256 with the pin. The result
is printed for human review, optionally written as JSON, and the exit status is 1 when any
pin drifted or could not be checked. The manifest is NEVER rewritten: a changed digest
means a different model build, which needs fresh engineering review, a new pin and a new
owner release approval (the old approval stops matching automatically).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from olive.services import runtime_manifest  # noqa: E402

ACCEPT = 'application/vnd.docker.distribution.manifest.v2+json'
LIMIT = 1024 * 1024


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={'Accept': ACCEPT, 'User-Agent': 'olive-release-pin-check'})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(LIMIT + 1)
    if len(body) > LIMIT:
        raise ValueError('oversized registry manifest')
    return body


def check(manifest: dict, fetcher=fetch) -> list[dict]:
    rows = []
    for entry in manifest['entries']:
        pinned = (entry.get('ollama') or {}).get('manifest_digest')
        url = (entry.get('source') or {}).get('url')
        if entry['kind'] != 'ollama-model' or not pinned or not url:
            continue
        row = {'id': entry['id'], 'model': entry['ollama']['model'], 'enabled': entry['enabled'], 'pinned': pinned,
               'current': None, 'status': 'unchecked', 'detail': ''}
        if not runtime_manifest.url_allowed(url, entry['source'].get('hosts') or []):
            row.update(status='error', detail='source URL is not an allowed HTTPS registry host')
        else:
            try:
                body = fetcher(url)
                row['current'] = hashlib.sha256(body).hexdigest()
                row['status'] = 'unchanged' if row['current'] == pinned else 'DRIFTED'
                if row['status'] == 'DRIFTED':
                    row['detail'] = 'the registry serves a different build; review it before changing the pin'
            except (OSError, ValueError, urllib.error.URLError) as error:
                row.update(status='error', detail=type(error).__name__)
        rows.append(row)
    return rows


def main(argv=None, fetcher=fetch):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args(argv)
    path = args.manifest or runtime_manifest.DIRECTORY / '1.0.0.json'
    before = path.read_bytes()
    manifest = json.loads(before)
    rows = check(manifest, fetcher)
    for row in rows:
        current = (row['current'] or '-')[:12]
        print(f"{row['status']:<9} {row['model']:<46} pinned {row['pinned'][:12]} now {current} {row['detail']}")
    if args.json:
        args.json.write_text(json.dumps({'manifest': str(path), 'results': rows}, indent=2) + '\n', encoding='utf-8')
    assert path.read_bytes() == before  # Read-only by design.
    return 0 if rows and all(r['status'] == 'unchanged' for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
