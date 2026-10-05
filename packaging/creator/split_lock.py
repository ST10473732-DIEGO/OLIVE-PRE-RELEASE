"""Split a Creator runtime lock into the OLIVE archive set and the direct-download set.

    python packaging/creator/split_lock.py            # resolve from PyPI metadata and write
    python packaging/creator/split_lock.py --check    # offline: verify the committed split

Engineering/distribution decision (OLIVE 1.0, "Option B+"): OLIVE's Creator runtime archive
never contains (a) NVIDIA-published wheels (`nvidia-*`, `cuda-*` unless explicitly allowed with
an open licence) or (b) other wheels shown to bundle NVIDIA components (policy
"bundles_nvidia", each with its evidence). First-run setup downloads those exact pinned files
from PyPI (files.pythonhosted.org) and unpacks them into the OLIVE-owned runtime before it is
registered. This is an engineering choice, not a legal determination.

For each definition with a "direct_download" policy this writes, beside locks/<id>.txt (the
complete hash lock, unchanged):

  locks/<id>.archive.txt          the lock's own blocks (every hash kept) for packages OLIVE may
                                  place in its archive; the builder installs exactly this file
  locks/<id>.wheels.json          every locked package with the one wheel the target installs: file
                                  name, URL, SHA-256 (one of the lock's hashes), size, and whether
                                  it is "archive" or "direct"; direct records carry why, the
                                  wheel's own METADATA licence and attribution fields, its layout
                                  and its licence/NOTICE files (path, SHA-256, size)
  locks/<id>.direct-licences.json the text of those licence/NOTICE files, keyed by SHA-256, each
                                  checked against the wheel's own RECORD

Only metadata is fetched: PyPI's JSON API and, for direct wheels, HTTP Range reads of the zip
central directory, METADATA, RECORD and licence files. No wheel body is downloaded. Attribution
is what each wheel's METADATA says (Author, Maintainer, Project-URL); nothing is inferred. The
selection follows pip's tag order for the definition's interpreter and the oldest supported
glibc builder, so the same wheel is chosen on any build machine. --check recomputes the split
offline and fails on any drift, which the builder also does before every build.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import email.parser
import fnmatch
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
WHEELS_SCHEMA = 'olive-creator-wheels/1'
ARCHIVE, DIRECT = 'archive', 'direct'
LICENCES_SCHEMA = 'olive-creator-direct-licences/1'
LICENCE_NAME = re.compile(r'(^|/)(licen[cs]e|copying|notice|authors)[^/]*$', re.I)
REQUIREMENT = re.compile(r'^([a-z0-9][a-z0-9._-]*)==([^\s\\]+)', re.M)
HASH = re.compile(r'--hash=sha256:([0-9a-f]{64})')
# A licence the archive may carry must be stated as an SPDX expression in the wheel metadata.
OPEN_LICENCES = {'Apache-2.0', 'MIT', 'BSD-3-Clause'}


def normalise(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def parse_lock(text: str) -> dict[str, dict]:
    """{name: {'version', 'hashes', 'block'}} in lock order; block is the verbatim requirement text."""
    lines = text.splitlines(keepends=True)
    body = [i for i, line in enumerate(lines) if REQUIREMENT.match(line)]
    result = {}
    for index, start in enumerate(body):
        end = body[index + 1] if index + 1 < len(body) else len(lines)
        block = ''.join(lines[start:end])
        match = REQUIREMENT.match(lines[start])
        name = normalise(match[1])
        if name in result:
            raise ValueError(f'{name} appears twice in the lock')
        result[name] = {'version': match[2], 'hashes': set(HASH.findall(block)), 'block': block}
    return result


def header(text: str) -> str:
    lines = text.splitlines(keepends=True)
    first = next(i for i, line in enumerate(lines) if REQUIREMENT.match(line))
    return ''.join(lines[:first])


def direct_reason(name: str, policy: dict) -> str | None:
    """Why a package is a direct download (None when it belongs in the archive)."""
    name = normalise(name)
    if name in policy.get('bundles_nvidia', {}):
        return 'bundles-nvidia-components'
    if any(fnmatch.fnmatchcase(name, pattern) for pattern in policy['patterns']):
        allowed = policy.get('archive_allowed', {}).get(name)
        return None if allowed and allowed.get('spdx') in OPEN_LICENCES else 'nvidia-package'
    return None


def classify(name: str, policy: dict) -> str:
    """archive | direct. Packages that bundle NVIDIA components go direct; anything matching a
    publisher pattern goes direct unless the policy allows it with an open SPDX licence."""
    return DIRECT if direct_reason(name, policy) else ARCHIVE


def archive_lock(full: str, policy: dict, definition: dict) -> str:
    packages = parse_lock(full)
    kept = [p['block'] for name, p in packages.items() if classify(name, policy) == ARCHIVE]
    note = (f"# Archive subset of {Path(definition['lock']).name} (derived by packaging/creator/split_lock.py; "
            'do not edit).\n# Direct-download packages are omitted here: setup fetches them from PyPI, see '
            f"{Path(definition['wheels']).name}.\n")
    return header(full) + note + ''.join(kept)


def wheel_platforms(target: str, max_glibc: str) -> list[str]:
    if target != 'linux-x86_64':
        raise ValueError(f'Creator wheel selection is defined for linux-x86_64 only, not {target}')
    major, minor = (int(part) for part in max_glibc.split('.'))
    return ([f'manylinux_{major}_{n}_x86_64' for n in range(minor, 16, -1)]
            + ['manylinux2014_x86_64', 'manylinux2010_x86_64', 'manylinux1_x86_64', 'linux_x86_64'])


def _packaging():
    # The repository's own packaging/ folder shadows the PyPI 'packaging' project; use pip's copy.
    from pip._vendor.packaging import tags, utils
    return tags, utils


def tag_rank(definition: dict) -> dict:
    tags, _ = _packaging()
    python = tuple(int(part) for part in definition['wheel_selection']['python'].split('.'))
    platforms = wheel_platforms(definition['target'], definition['wheel_selection']['max_glibc'])
    abi = f'cp{python[0]}{python[1]}'
    order = list(tags.cpython_tags(python, platforms=platforms)) + list(tags.compatible_tags(python, abi, platforms=platforms))
    return {tag: index for index, tag in enumerate(order)}


class _RangeFile(io.RawIOBase):
    """A seekable, read-only view of a remote file through HTTP Range requests, so zipfile can
    read a wheel's central directory and METADATA without downloading the wheel."""
    BLOCK = 256 * 1024

    def __init__(self, client, url: str, size: int):
        self.client, self.url, self.size, self.position, self.blocks = client, url, size, 0, {}
        self.fetched = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.size}[whence]
        self.position = max(0, base + offset)
        return self.position

    def _block(self, index):
        if index not in self.blocks:
            start = index * self.BLOCK
            end = min(start + self.BLOCK, self.size) - 1
            response = self.client.get(self.url, headers={'Range': f'bytes={start}-{end}'})
            if response.status_code != 206 or len(response.content) != end - start + 1:
                raise OSError(f'{self.url}: range request answered HTTP {response.status_code}')
            self.blocks[index] = response.content
            self.fetched += len(response.content)
        return self.blocks[index]

    def readinto(self, buffer):
        if self.position >= self.size:
            return 0
        count = min(len(buffer), self.size - self.position)
        written = 0
        while written < count:
            index, offset = divmod(self.position + written, self.BLOCK)
            chunk = self._block(index)[offset:offset + count - written]
            buffer[written:written + len(chunk)] = chunk
            written += len(chunk)
        self.position += written
        return written


def inspect_wheel(client, url: str, size: int) -> tuple[dict, set[str], dict[str, str], int]:
    """(layout, METADATA licence and attribution fields, licence files), member paths, licence
    texts by SHA-256, bytes fetched. Each licence text is checked against the wheel's RECORD."""
    import base64
    import csv
    import hashlib
    import zipfile
    stream = _RangeFile(client, url, size)
    texts = {}
    with zipfile.ZipFile(io.BufferedReader(stream, buffer_size=_RangeFile.BLOCK)) as wheel:
        infos = [i for i in wheel.infolist() if not i.is_dir()]
        dist_info = next(i.filename.split('/')[0] for i in infos if i.filename.endswith('.dist-info/METADATA')
                         and i.filename.count('/') == 1)
        metadata = email.parser.Parser().parsestr(wheel.read(f'{dist_info}/METADATA').decode('utf-8', 'replace'),
                                                  headersonly=True)
        record = {row[0]: row[1] for row in csv.reader(wheel.read(f'{dist_info}/RECORD').decode('utf-8').splitlines())
                  if row and len(row) > 1}
        files = []
        for info in infos:
            if not info.filename.startswith(dist_info + '/') or not LICENCE_NAME.search(info.filename):
                continue
            data = wheel.read(info)
            digest = hashlib.sha256(data).hexdigest()
            recorded = 'sha256=' + base64.urlsafe_b64encode(bytes.fromhex(digest)).rstrip(b'=').decode()
            if record.get(info.filename) != recorded:
                raise SystemExit(f'{url}: {info.filename} does not match the wheel RECORD')
            texts[digest] = data.decode('utf-8', 'replace')
            files.append({'path': info.filename, 'sha256': digest, 'bytes': len(data)})
    names = {i.filename for i in infos}
    layout = {
        'files': len(infos), 'installed_bytes': sum(i.file_size for i in infos),
        'data_dirs': sorted({i.filename.split('/')[1] for i in infos if i.filename.split('/')[0].endswith('.data')}),
        'executables': sorted(i.filename for i in infos if (i.external_attr >> 16) & 0o111),
        'top_level': sorted({i.filename.split('/')[0] for i in infos}),
        'entry_points': f'{dist_info}/entry_points.txt' in names,
    }
    licence = {'License-Expression': metadata.get('License-Expression'), 'License': (metadata.get('License') or '')[:200] or None,
               'Classifier': sorted(c for c in metadata.get_all('Classifier') or [] if c.startswith('License ::')),
               'License-File': sorted(metadata.get_all('License-File') or [])}
    # Attribution exactly as the wheel states it; no publisher is inferred.
    attribution = {key: metadata.get(key) for key in ('Author', 'Author-email', 'Maintainer', 'Maintainer-email', 'Home-page')
                   if metadata.get(key)}
    attribution['Project-URL'] = sorted(metadata.get_all('Project-URL') or [])
    return ({'layout': layout, 'wheel_metadata_licence': licence, 'wheel_metadata_attribution': attribution,
             'licence_files': sorted(files, key=lambda f: f['path'])}, names, texts, stream.fetched)


def resolve(definition: dict, full: str, client=None) -> dict:
    """Pick, for every locked package, the wheel pip installs on the target (metadata only)."""
    import httpx
    parse_wheel_filename = _packaging()[1].parse_wheel_filename
    policy = definition['direct_download']
    rank = tag_rank(definition)
    packages = parse_lock(full)
    hosts = set(policy['hosts'])

    def one(item):
        name, locked = item
        with (client or httpx.Client(timeout=60, follow_redirects=False)) as http:
            response = http.get(f'https://pypi.org/pypi/{name}/{locked["version"]}/json')
            response.raise_for_status()
            data = response.json()
        best = None
        for candidate in data['urls']:
            if candidate['packagetype'] != 'bdist_wheel' or candidate['digests']['sha256'] not in locked['hashes']:
                continue
            _, _, _, wheel_tags = parse_wheel_filename(candidate['filename'])
            score = min((rank[tag] for tag in wheel_tags if tag in rank), default=None)
            if score is not None and (best is None or score < best[0]):
                best = (score, candidate)
        if best is None:
            raise SystemExit(f'{name}=={locked["version"]}: no locked wheel installs on {definition["target"]}')
        chosen = best[1]
        if urlsplit(chosen['url']).hostname not in hosts or not chosen['url'].startswith('https://'):
            raise SystemExit(f'{name}: {chosen["url"]} is not on an allowed HTTPS host')
        record = {'name': name, 'version': locked['version'], 'distribution': classify(name, policy),
                  'filename': chosen['filename'], 'url': chosen['url'], 'sha256': chosen['digests']['sha256'],
                  'size_bytes': int(chosen['size'])}
        if record['distribution'] == DIRECT:
            record['direct_reason'] = direct_reason(name, policy)
            if record['direct_reason'] == 'bundles-nvidia-components':
                record['direct_evidence'] = policy['bundles_nvidia'][name]
            record['pypi_project'] = f'https://pypi.org/project/{name}/{locked["version"]}/'
        return record

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        records = list(pool.map(one, packages.items()))
    # Direct downloads are unpacked by setup itself, so their layout is part of the pin:
    # read each wheel's central directory and METADATA (a few KB through Range requests).
    members, fetched, texts = {}, 0, {}
    with httpx.Client(timeout=60, follow_redirects=False) as http:
        for record in records:
            if record['distribution'] == DIRECT:
                details, names, found, used = inspect_wheel(http, record['url'], record['size_bytes'])
                record.update(details)
                members[record['name']] = names
                texts.update(found)
                fetched += used
    seen, shared = {}, set()
    for name, paths in members.items():
        for path in paths:
            if path in seen:
                shared.add(path)
            seen.setdefault(path, name)
    document = wheels_document(definition, records)
    document['direct_shared_paths'] = sorted(shared)
    print(f'{definition["id"]}: read {fetched:,} bytes of wheel metadata through Range requests', file=sys.stderr)
    return document, {'schema': LICENCES_SCHEMA, 'id': definition['id'], 'texts': dict(sorted(texts.items()))}


def wheels_document(definition: dict, records: list[dict]) -> dict:
    records = sorted(records, key=lambda r: r['name'])
    totals = {kind: sum(r['size_bytes'] for r in records if r['distribution'] == kind) for kind in (ARCHIVE, DIRECT)}
    return {'schema': WHEELS_SCHEMA, 'id': definition['id'], 'target': definition['target'],
            'wheel_selection': definition['wheel_selection'],
            'policy': definition['direct_download']['reason'],
            'counts': {kind: sum(1 for r in records if r['distribution'] == kind) for kind in (ARCHIVE, DIRECT)},
            'bytes': totals, 'packages': records}


def check(definition: dict) -> list[str]:
    """Offline consistency of the committed split; empty when everything matches."""
    problems = []
    policy = definition['direct_download']
    full = (HERE / definition['lock']).read_text(encoding='utf-8')
    packages = parse_lock(full)
    archive_path, wheels_path = HERE / definition['archive_lock'], HERE / definition['wheels']
    if not archive_path.is_file() or archive_path.read_text(encoding='utf-8') != archive_lock(full, policy, definition):
        problems.append(f'{definition["archive_lock"]} differs from the split of {definition["lock"]}')
    try:
        wheels = json.loads(wheels_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return problems + [f'{definition["wheels"]} is missing or unreadable']
    if wheels.get('schema') != WHEELS_SCHEMA or wheels.get('id') != definition['id']:
        problems.append(f'{definition["wheels"]} has the wrong schema or id')
    records = {r['name']: r for r in wheels.get('packages', [])}
    try:
        texts = json.loads((HERE / definition['direct_licences']).read_text(encoding='utf-8'))['texts']
    except (OSError, ValueError, KeyError):
        texts = {}
        problems.append(f'{definition["direct_licences"]} is missing or unreadable')
    import hashlib
    for digest, text in texts.items():
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != digest:
            problems.append(f'direct-licences text {digest[:12]} does not match its SHA-256')
    if set(records) != set(packages):
        problems.append('wheel records and lock name different package sets: '
                        + ', '.join(sorted(set(records) ^ set(packages))))
    for name, record in records.items():
        locked = packages.get(name)
        if locked is None:
            continue
        if record['version'] != locked['version']:
            problems.append(f'{name}: version {record["version"]} is not the locked {locked["version"]}')
        if record['sha256'] not in locked['hashes']:
            problems.append(f'{name}: {record["sha256"]} is not one of the lock hashes')
        if record['distribution'] != classify(name, policy):
            problems.append(f'{name}: recorded as {record["distribution"]}, policy says {classify(name, policy)}')
        if urlsplit(record['url']).scheme != 'https' or urlsplit(record['url']).hostname not in policy['hosts']:
            problems.append(f'{name}: URL is not on an allowed HTTPS host')
        if not record['url'].endswith('/' + record['filename']) or not record['filename'].endswith('.whl'):
            problems.append(f'{name}: URL and file name disagree')
        if type(record['size_bytes']) is not int or record['size_bytes'] <= 0:
            problems.append(f'{name}: no pinned size')
        if record['distribution'] == DIRECT:
            if not record.get('wheel_metadata_licence') or 'wheel_metadata_attribution' not in record:
                problems.append(f'{name}: direct download without the wheel\'s licence and attribution metadata')
            if record.get('direct_reason') != direct_reason(name, policy):
                problems.append(f'{name}: direct_reason does not match the policy')
            if 'publisher' in record:
                problems.append(f'{name}: carries an inferred publisher; attribution must come from the wheel')
            for licence_file in record.get('licence_files', []):
                if licence_file['sha256'] not in texts:
                    problems.append(f'{name}: licence text {licence_file["path"]} is missing from direct-licences')
    archive_names = set(parse_lock(archive_path.read_text(encoding='utf-8'))) if archive_path.is_file() else set()
    direct = {n for n, r in records.items() if r['distribution'] == DIRECT}
    if archive_names & direct:
        problems.append('the archive lock contains direct-download packages: ' + ', '.join(sorted(archive_names & direct)))
    if archive_names | direct != set(packages):
        problems.append('archive and direct-download sets do not add up to the complete lock')
    return problems


def definitions() -> list[tuple[Path, dict]]:
    found = []
    for path in sorted((HERE / 'definitions').glob('*.json')):
        definition = json.loads(path.read_text(encoding='utf-8'))
        if definition.get('direct_download'):
            found.append((path, definition))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='verify the committed split offline; write nothing')
    args = parser.parse_args(argv)
    failed = False
    for path, definition in definitions():
        if args.check:
            problems = check(definition)
            for problem in problems:
                print(f'{definition["id"]}: {problem}', file=sys.stderr)
            failed |= bool(problems)
            if not problems:
                print(f'{definition["id"]}: split OK')
            continue
        full = (HERE / definition['lock']).read_text(encoding='utf-8')
        (HERE / definition['archive_lock']).write_text(archive_lock(full, definition['direct_download'], definition),
                                                       encoding='utf-8')
        document, licences = resolve(definition, full)
        (HERE / definition['wheels']).write_text(json.dumps(document, indent=1) + '\n', encoding='utf-8')
        (HERE / definition['direct_licences']).write_text(json.dumps(licences, indent=1) + '\n', encoding='utf-8')
        print(f"{definition['id']}: {document['counts']} {document['bytes']}")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
