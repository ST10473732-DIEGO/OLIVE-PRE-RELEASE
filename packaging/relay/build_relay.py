"""Build the standalone OLIVE Connect World relay release bundle (deterministic, unpublished).

    python packaging/relay/build_relay.py [--output DIR] [--epoch SECONDS]

Output (default dist/relay/, git-ignored):

  olive-world-relay-1.0.0.tar.gz         the bundle (sorted members, uid/gid 0, fixed mtimes,
                                         gzip header without a timestamp: same commit + same
                                         epoch => same bytes)
  olive-world-relay-1.0.0.tar.gz.sha256  its SHA-256

The bundle holds ONLY the relay modules (olive.world.wire, olive.world.websocket,
olive.world_relay) under a minimal package root, the deployment files and the licence and
notices. It needs no clone of the OLIVE source repository, embeds no secrets and has no
route database. The epoch defaults to SOURCE_DATE_EPOCH, else the source commit's time.
Nothing is uploaded anywhere: publication is a separate, owner-approved step.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
VERSION = '1.0.0'
NAME = f'olive-world-relay-{VERSION}'
# (bundle path, source path): the complete file list. Nothing else enters the bundle.
MODULES = [
    ('olive/__init__.py', HERE / 'bundle' / 'package_root.py'),
    ('olive/world/__init__.py', REPOSITORY / 'olive/world/__init__.py'),
    ('olive/world/wire.py', REPOSITORY / 'olive/world/wire.py'),
    ('olive/world/websocket.py', REPOSITORY / 'olive/world/websocket.py'),
    ('olive/world_relay/__init__.py', REPOSITORY / 'olive/world_relay/__init__.py'),
    ('olive/world_relay/__main__.py', REPOSITORY / 'olive/world_relay/__main__.py'),
    ('olive/world_relay/server.py', REPOSITORY / 'olive/world_relay/server.py'),
]
DEPLOYMENT = [
    ('Dockerfile', HERE / 'bundle/Dockerfile'), ('compose.yaml', HERE / 'bundle/compose.yaml'),
    ('README.md', HERE / 'bundle/README.md'), ('LICENSE-RELAY.md', HERE / 'bundle/LICENSE-RELAY.md'),
    ('THIRD_PARTY_NOTICES.md', HERE / 'bundle/THIRD_PARTY_NOTICES.md'),
    ('olive-world-relay', HERE / 'bundle/olive-world-relay'),
    ('olive-world-relay.service', HERE / 'bundle/olive-world-relay.service'),
    ('Caddyfile', REPOSITORY / 'world-relay/Caddyfile'), ('healthcheck.sh', REPOSITORY / 'world-relay/healthcheck.sh'),
    ('nginx.conf.example', REPOSITORY / 'world-relay/nginx.conf.example'),
    ('relay.env.example', REPOSITORY / 'world-relay/relay.env.example'),
]
EXECUTABLE = {'olive-world-relay', 'healthcheck.sh'}


def git(*args) -> str:
    return subprocess.run(['git', '-C', str(REPOSITORY), *args], capture_output=True, text=True).stdout.strip()


def relay_version() -> str:
    text = (REPOSITORY / 'olive/world_relay/server.py').read_text(encoding='utf-8')
    return next(line.split('=', 1)[1].strip().strip('\'"') for line in text.splitlines() if line.startswith('VERSION ='))


def contents(epoch: int, commit: str, dirty: bool) -> dict[str, bytes]:
    if relay_version() != VERSION:
        raise SystemExit(f'olive/world_relay/server.py says {relay_version()}, the bundle is {VERSION}')
    files = {path: source.read_bytes() for path, source in MODULES + DEPLOYMENT}
    info = {'schema': 'olive-relay-bundle/1', 'name': 'OLIVE Connect World relay', 'version': VERSION,
            'protocol': 'olive-world/1', 'source_commit': commit, 'source_tree_modified': dirty,
            'source_date_epoch': epoch, 'python': '>=3.11 (standard library only)',
            'files': {path: hashlib.sha256(data).hexdigest() for path, data in sorted(files.items())},
            'published': False}
    files['BUILD-INFO.json'] = (json.dumps(info, indent=2, sort_keys=True) + '\n').encode()
    return files


def pack(files: dict[str, bytes], epoch: int) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as tar:
        directories = sorted({str(Path(NAME, p).parent) for p in files} | {NAME})
        for directory in sorted(set(d for path in directories for d in [path] + [str(p) for p in Path(path).parents if str(p) != '.'])):
            info = tarfile.TarInfo(directory)
            info.type, info.mode, info.mtime = tarfile.DIRTYPE, 0o755, epoch
            tar.addfile(info)
        for path in sorted(files):
            info = tarfile.TarInfo(f'{NAME}/{path}')
            info.size, info.mtime = len(files[path]), epoch
            info.mode = 0o755 if path in EXECUTABLE else 0o644
            tar.addfile(info, io.BytesIO(files[path]))
    out = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=out, mtime=0, compresslevel=9) as stream:
        stream.write(raw.getvalue())
    return out.getvalue()


def build(output: Path, epoch: int | None = None, commit: str | None = None) -> dict:
    commit = commit or os.environ.get('OLIVE_SOURCE_COMMIT') or git('rev-parse', 'HEAD') or 'unknown'
    dirty = bool(git('status', '--porcelain', '--', 'olive/world', 'olive/world_relay', 'world-relay', 'packaging/relay'))
    if epoch is None:
        epoch = int(os.environ.get('SOURCE_DATE_EPOCH') or git('log', '-1', '--format=%ct') or 0)
    data = pack(contents(epoch, commit, dirty), epoch)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'{NAME}.tar.gz'
    archive.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (output / f'{NAME}.tar.gz.sha256').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    return {'archive': str(archive), 'sha256': digest, 'size_bytes': len(data), 'source_commit': commit,
            'source_tree_modified': dirty, 'source_date_epoch': epoch}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=REPOSITORY / 'dist' / 'relay')
    parser.add_argument('--epoch', type=int)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.output, args.epoch), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
