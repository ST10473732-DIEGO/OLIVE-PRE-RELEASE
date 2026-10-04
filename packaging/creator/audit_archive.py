"""Audit a built Creator runtime archive before it leaves the builder.

    python packaging/creator/audit_archive.py out/<id>.tar.zst packaging/creator/definitions/<id>.json \
        [--forbid TEXT ...] [--json REPORT] [--direct-site SITE_PACKAGES]

Fails (exit 1) when:

  * any member lies under site-packages/nvidia/ or is the .dist-info of a direct-download
    package (Option B+: those wheels are fetched by setup from PyPI);
  * any member is not a regular file, folder or in-archive symbolic link, or has an
    absolute or parent-escaping name;
  * OLIVE-RUNTIME.json does not list exactly the definition's direct-download wheels
    (name and SHA-256 from wheels.json), or names a different ComfyUI commit;
  * a --forbid string (the build folder, the builder's home) occurs in any member's bytes;
  * NVIDIA-origin content bundled inside an archive wheel differs from the reviewed list in
    vendored_nvidia.json (empty for the Option B+ image archive): CUDA library or toolkit file
    names, NVIDIA header/tool folders, or an ELF binary that embeds the CUDA runtime (the
    cudart_static signature "/cudart.shm.", found in comfy-kitchen and cuda-bindings), or a
    member carrying NVIDIA proprietary licence markers (outside OLIVE's own notices files);
  * with --direct-site (the site-packages of an assembled runtime), any archive payload file is
    byte-identical to a file of an installed direct-download wheel (.dist-info metadata such as a
    shared Apache-2.0 LICENSE text is reported, not failed).

It also REPORTS, without failing, files whose text carries an NVIDIA copyright line: NVIDIA-
authored open-source code (Apache/BSD/MIT) inside ComfyUI, torch, transformers and others.

Only the archive is read; nothing is extracted or downloaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import split_lock  # noqa: E402

DIST_INFO = re.compile(r'/site-packages/([^/]+)\.dist-info/')
# File names and folders that identify NVIDIA CUDA components bundled inside other wheels.
VENDORED = re.compile(r'(libcudart|libcublas|libcudnn|libnccl|libnvrtc|libnvjitlink|libcufft|libcurand|libcusolver|libcusparse|'
                      r'libcupti|libnvToolsExt|libnvjpeg|libnpp|libnvperf|libcufile|libnvshmem|ptxas|cuobjdump|nvdisasm|'
                      r'nvlink|fatbinary|/nvcc$|/cicc$|libdevice|/backends/nvidia/|cuda_runtime|/include/cuda[^/]*\.h$|'
                      r'/include/cu(blas|dnn|fft|rand|solver|sparse|pti)[^/]*\.h$)', re.I)
STATIC_RUNTIME = b'/cudart.shm.'  # Internal to the CUDA runtime; absent from code that only links libcudart.
PROPRIETARY = re.compile(rb'LicenseRef-NVIDIA|CUDA Toolkit End User License|NVIDIA Software License Agreement|'
                         rb'NVIDIA Proprietary Software')
COPYRIGHT = re.compile(rb'Copyright[^\n]{0,40}NVIDIA|NVIDIA CORPORATION', re.I)
OWN_NOTICES = {'THIRD_PARTY-creator.txt', 'THIRD_PARTY-creator-direct-downloads.txt', 'OLIVE-RUNTIME.json'}


def _package(name: str) -> str:
    parts = name.split('/')
    if len(parts) > 4 and parts[1] == 'lib' and parts[3] == 'site-packages':
        return parts[4].split('.libs')[0] if parts[4].endswith('.libs') else parts[4]
    return parts[0]


def direct_file_hashes(site: Path, direct: set[str]) -> dict[str, str]:
    """{urlsafe sha256: path} of every non-empty file the installed direct-download wheels recorded."""
    import csv
    found = {}
    for info in site.glob('*.dist-info'):
        name = re.search(r'^Name: (.+)$', (info / 'METADATA').read_text(errors='replace'), re.M)
        if not name or split_lock.normalise(name[1].strip()) not in direct:
            continue
        for row in csv.reader((info / 'RECORD').read_text().splitlines()):
            if len(row) == 3 and row[1].startswith('sha256=') and row[2] not in ('', '0'):
                found[row[1]] = row[0]
    return found


def _link_inside(name: str, linkname: str) -> bool:
    if not linkname or linkname.startswith('/'):
        return False
    depth = len(PurePosixPath(name).parts) - 1
    for part in PurePosixPath(linkname).parts:
        if part == '..':
            depth -= 1
            if depth < 0:
                return False
        elif part not in ('', '.'):
            depth += 1
    return True


def audit(archive: Path, definition: dict, forbid: list[str], direct_site: Path | None = None) -> dict:
    import base64
    from compression import zstd
    policy = definition['direct_download']
    records = json.loads((HERE / definition['wheels']).read_text(encoding='utf-8'))['packages']
    direct = {r['name'] for r in records if r['distribution'] == split_lock.DIRECT}
    needles = [f.encode() for f in forbid if f]
    overlap = max((len(n) for n in needles), default=1)
    problems, members, regular, total, dists, marker = [], 0, 0, 0, set(), None
    vendored: dict[str, dict] = {}
    copyrights: dict[str, dict] = {}
    identical: list[tuple[str, str]] = []
    identical_metadata: list[tuple[str, str]] = []
    known = direct_file_hashes(direct_site, direct) if direct_site else {}
    digest = hashlib.sha256()
    with open(archive, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    with zstd.open(archive, 'rb') as raw, tarfile.open(fileobj=raw, mode='r|') as tar:
        for member in tar:
            members += 1
            name = member.name
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts:
                problems.append(f'unsafe member name {name}')
            if '/site-packages/nvidia/' in '/' + name + '/' or name.endswith('/site-packages/nvidia'):
                problems.append(f'NVIDIA library folder inside the archive: {name}')
            match = DIST_INFO.search('/' + name + '/')
            if match:
                dist = split_lock.normalise(match[1].rsplit('-', 1)[0])
                dists.add(dist)
                message = f'direct-download distribution inside the archive: {match[1]}'
                if (dist in direct or split_lock.classify(dist, policy) == split_lock.DIRECT) and message not in problems:
                    problems.append(message)
            if member.issym():
                if not _link_inside(name, member.linkname):
                    problems.append(f'link leaves the archive: {name}')
                continue
            if member.isdir():
                continue
            if not member.isreg():
                problems.append(f'unsupported member type: {name}')
                continue
            regular += 1
            total += member.size
            package = _package(name)
            kinds = set()
            if VENDORED.search('/' + name):
                kinds.add('cuda-file-name')
            source = tar.extractfile(member)
            tail, data, found, head = b'', b'', False, b''
            member_hash = hashlib.sha256()
            text_like = member.size < 16 * 1024 * 1024
            copyright_hit = False
            while chunk := source.read(1 << 20):
                window = tail + chunk
                if not head:
                    head = chunk[:4]
                if not found and any(needle in window for needle in needles):
                    problems.append(f'{name} contains a forbidden build path')
                    found = True
                if STATIC_RUNTIME in window and head == b'\x7fELF':
                    kinds.add('embedded-cuda-runtime')
                if name.split('/')[-1] not in OWN_NOTICES and PROPRIETARY.search(window):
                    kinds.add('nvidia-proprietary-licence-marker')
                if text_like and not copyright_hit and b'\0' not in chunk[:4096] and COPYRIGHT.search(window):
                    copyright_hit = True
                tail = window[-max(overlap, 64):]
                member_hash.update(chunk)
                if name == 'OLIVE-RUNTIME.json':
                    data += chunk
            if kinds:
                row = vendored.setdefault(package, {'files': 0, 'bytes': 0, 'kinds': set(), 'examples': []})
                row['files'] += 1
                row['bytes'] += member.size
                row['kinds'] |= kinds
                if len(row['examples']) < 8:
                    row['examples'].append(name)
            if copyright_hit and name.split('/')[-1] not in OWN_NOTICES:
                row = copyrights.setdefault(package, {'files': 0, 'bytes': 0, 'examples': []})
                row['files'] += 1
                row['bytes'] += member.size
                if len(row['examples']) < 4:
                    row['examples'].append(name)
            if known and member.size:
                key = 'sha256=' + base64.urlsafe_b64encode(member_hash.digest()).rstrip(b'=').decode()
                if key in known:
                    (identical_metadata if '.dist-info/' in name else identical).append((name, known[key]))
            if name == 'OLIVE-RUNTIME.json':
                marker = json.loads(data)
    if marker is None:
        problems.append('OLIVE-RUNTIME.json is missing')
    else:
        declared = sorted((w['name'], w['sha256']) for w in marker.get('direct_downloads', {}).get('wheels', []))
        expected = sorted((r['filename'], r['sha256']) for r in records if r['distribution'] == split_lock.DIRECT)
        if declared != expected:
            problems.append('OLIVE-RUNTIME.json does not list exactly the direct-download wheels of wheels.json')
        if (marker.get('comfyui') or {}).get('commit') != definition['comfyui']['commit']:
            problems.append('OLIVE-RUNTIME.json names a different ComfyUI commit')
    reviewed = json.loads((HERE / 'vendored_nvidia.json').read_text(encoding='utf-8'))['archives'].get(definition['id'], {})
    for package in sorted(set(vendored) | set(reviewed)):
        found, expected = vendored.get(package), reviewed.get(package)
        if found is None or expected is None or (found['files'], found['bytes']) != (expected['files'], expected['bytes']):
            problems.append(f'NVIDIA-origin content in {package} differs from vendored_nvidia.json '
                            f'(found {found and {k: found[k] for k in ("files", "bytes", "examples")}}, '
                            f'reviewed {expected and {k: expected[k] for k in ("files", "bytes")}})')
    for name, other in identical:
        problems.append(f'{name} is byte-identical to {other} from a direct-download wheel')
    for row in vendored.values():
        row['kinds'] = sorted(row['kinds'])
    archive_set = {r['name'] for r in records if r['distribution'] == split_lock.ARCHIVE}
    missing = sorted(archive_set - dists)
    if missing:
        problems.append('archive distributions missing: ' + ', '.join(missing))
    return {'archive': archive.name, 'sha256': digest.hexdigest(), 'bytes': archive.stat().st_size,
            'members': members, 'regular_files': regular, 'unpacked_bytes': total,
            'distributions': sorted(dists), 'direct_downloads_absent': not (dists & direct),
            'vendored_nvidia': vendored, 'vendored_nvidia_bytes': sum(v['bytes'] for v in vendored.values()),
            'nvidia_copyright_text_files': copyrights,
            'direct_files_compared': len(known), 'identical_to_direct_files': len(identical),
            'identical_metadata_files': identical_metadata,
            'problems': problems}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('archive', type=Path)
    parser.add_argument('definition', type=Path)
    parser.add_argument('--forbid', action='append', default=[], help='text that must not occur in any member')
    parser.add_argument('--json', type=Path, help='also write the report here')
    parser.add_argument('--direct-site', type=Path, help='site-packages of an assembled runtime: compare file contents')
    args = parser.parse_args(argv)
    definition = json.loads(args.definition.read_text(encoding='utf-8'))
    report = audit(args.archive, definition, args.forbid, args.direct_site)
    if args.json:
        args.json.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('distributions', 'nvidia_copyright_text_files')}, indent=1))
    return 1 if report['problems'] else 0


if __name__ == '__main__':
    sys.exit(main())
