"""Write BUILD-INFO.json and SHA256SUMS for one folder of release-CI outputs.

    python packaging/release/build_info.py <folder> --target linux-x86_64 [--kind desktop]

BUILD-INFO.json records the exact source commit, the CI run that built the files, and the
SHA-256 of every file in the folder; SHA256SUMS lists the same digests in sha256sum format
(sorted, relative paths). Both are written; nothing is uploaded or signed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

OUTPUTS = ('BUILD-INFO.json', 'SHA256SUMS')


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def files(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): digest(p) for p in sorted(folder.rglob('*'))
            if p.is_file() and p.name not in OUTPUTS}


def source_commit() -> str:
    commit = os.environ.get('OLIVE_SOURCE_COMMIT') or os.environ.get('GITHUB_SHA')
    if commit:
        return commit
    return subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip() or 'unknown'


def write(folder: Path, target: str, kind: str) -> dict:
    listed = files(folder)
    info = {'schema': 'olive-build-info/1', 'product': 'OLIVE', 'version': '1.0.0', 'kind': kind, 'target': target,
            'source_commit': source_commit(), 'ref': os.environ.get('GITHUB_REF', ''),
            'ci_run': {k: os.environ.get(v, '') for k, v in (('id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT'),
                                                              ('workflow', 'GITHUB_WORKFLOW'), ('repository', 'GITHUB_REPOSITORY'))},
            'signed': False, 'published': False, 'files': listed}
    (folder / 'BUILD-INFO.json').write_text(json.dumps(info, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    (folder / 'SHA256SUMS').write_text(''.join(f'{d}  {p}\n' for p, d in sorted(listed.items())), encoding='utf-8')
    return info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--target', required=True)
    parser.add_argument('--kind', default='desktop')
    args = parser.parse_args(argv)
    info = write(args.folder, args.target, args.kind)
    print(f"{len(info['files'])} file(s), source {info['source_commit']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
