"""Record the licence texts of the libraries python-build-standalone compiles into CPython.

The install_only_stripped archives the OLIVE backend (and the Creator runtimes) ship carry
only CPython's own LICENSE.txt. The matching "full" archive of the same release carries
PYTHON.json (which extension links which library, under which licence) and licenses/.
This tool copies exactly that evidence into packaging/legal/supplements/ so
collect_notices.py can append it to every artefact built on that interpreter.

    python packaging/legal/pbs_notices.py <full-archive.tar.zst> [<full-archive.tar.zst> ...]

Each archive must be the pinned release's "full" archive; its SHA-256 is recorded next to
the texts. Run it again whenever packaging/backend/python-runtime.json changes release.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'supplements' / 'python-build-standalone'
TRIPLES = {'x86_64-unknown-linux-gnu': 'linux-x86_64', 'x86_64-pc-windows-msvc': 'windows-x86_64',
           'aarch64-apple-darwin': 'macos-arm64'}


def record(archive: Path) -> dict:
    name = archive.name
    match = re.match(r'cpython-(?P<version>[0-9.]+)\+(?P<release>\d+)-(?P<triple>[a-z0-9_]+-[a-z0-9_]+-[a-z0-9_]+(?:-[a-z]+)?)-', name)
    if not match or match['triple'] not in TRIPLES:
        raise SystemExit(f'{name}: not a recognised python-build-standalone full archive')
    target = TRIPLES[match['triple']]
    texts, info = {}, None
    with tarfile.open(archive, 'r:zst') as tar:
        for member in tar:
            if member.name == 'python/PYTHON.json':
                info = json.load(tar.extractfile(member))
            elif member.name.startswith('python/licenses/') and member.isfile():
                texts[Path(member.name).name] = tar.extractfile(member).read().decode('utf-8', errors='replace')
    if info is None:
        raise SystemExit(f'{name}: no PYTHON.json')
    extensions = {}
    for extension, variants in sorted(info['build_info']['extensions'].items()):
        for variant in variants:
            if variant.get('licenses'):
                extensions[extension] = {'licences': variant['licenses'],
                                         'files': [Path(p).name for p in variant.get('license_paths') or []]}
    referenced = sorted({f for e in extensions.values() for f in e['files']})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, text in texts.items():
        (OUTPUT / filename).write_text(text, encoding='utf-8')
    return {'target': target, 'archive': name, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'python_version': match['version'], 'release': match['release'],
            'core_licences': info.get('licenses'), 'extensions': extensions,
            'missing_from_archive': [f for f in referenced if f not in texts]}


def main(argv=None):
    archives = [Path(a) for a in (argv if argv is not None else sys.argv[1:])]
    if not archives:
        raise SystemExit(__doc__)
    index = {'schema': 'olive-pbs-notices/1', 'targets': {}}
    for archive in archives:
        entry = record(archive)
        index['targets'][entry['target']] = entry
    (OUTPUT / 'index.json').write_text(json.dumps(index, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for target, entry in index['targets'].items():
        print(f"{target}: {len(entry['extensions'])} extensions; missing texts: {entry['missing_from_archive'] or 'none'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
