"""Build a checksum-pinned OLIVE Creator runtime archive (ComfyUI image or video engine).

Release engineering runs this on the target operating system (private CI); first-run setup
never builds anything and never runs pip. The user's wizard downloads the archive this
script produces, verifies its SHA-256, unpacks it with the existing safe extractor, then
downloads the direct-download wheels from PyPI and unpacks them into the same staged
runtime before it is registered (the "Option B+" split, see split_lock.py).

    python packaging/creator/build_creator_runtime.py packaging/creator/definitions/<definition>.json \
        [--output DIR] [--cache DIR] [--wheelhouse DIR]

Inputs are all pinned by the definition:

  * CPython        - the python-build-standalone asset in packaging/backend/python-runtime.json
                     (URL + SHA-256), the same interpreter the OLIVE backend ships;
  * ComfyUI        - a git commit, fetched by hash and checked after checkout;
  * custom nodes   - git commits (the video engine's reviewed GGUF loader only);
  * Python wheels  - locks/<id>.archive.txt: the archive subset of the hash lock (pip
                     --require-hashes --only-binary=:all: --no-deps --no-index), each file first
                     fetched from the exact URL and SHA-256 in locks/<id>.wheels.json;
  * compressor     - compression.json: the pinned interpreter's built-in libzstd version and the
                     fixed zstd parameters (its SHA-256 is recorded with the inputs).

Direct-download wheels (NVIDIA packages and wheels that bundle NVIDIA components) are never
fetched, installed or packed here. Before building,
the committed split is re-derived from the complete lock (split_lock.check), and before the
archive is written the staged tree is audited: no direct-download distribution, and every
file under site-packages belongs to the RECORD of an archive distribution. Either failure
stops the build.

Output (in --output):

  <id>.tar.zst                          deterministic archive: sorted members, uid/gid 0, mtimes = the
                                        definition's source_date_epoch
  <id>.tar.zst.sha256                   its SHA-256
  <id>.manifest-entry.json              sizes, digests and the direct-download records a release
                                        manifest entry needs, plus build provenance (the OLIVE source
                                        commit); the URL stays null until the owner publishes the archive
  <id>.THIRD_PARTY-direct-downloads.txt the wheels setup fetches from PyPI (not in the archive)
  <id>.inventory.json                   every distribution in the archive and every direct download

Reproducibility: the archive's bytes depend only on the runtime inputs (definition, locks,
split files, interpreter, ComfyUI commit, wheels, OLIVE's notices generator) and the pinned
compressor (compression.json): pack_archive.py writes the tar and compresses it under the pinned
python-build-standalone interpreter, whose libzstd is compiled in, with fixed parameters
(single-threaded), so the build machine's Python, zstd, CPU count and locale never matter. The OLIVE
repository commit is build PROVENANCE: it is recorded in the sidecar files beside the archive
(manifest-entry.json and inventory.json), never inside it, and the mtimes come from the
definition's pinned source_date_epoch rather than SOURCE_DATE_EPOCH or the OLIVE commit time. A
metadata-only OLIVE commit therefore rebuilds the identical archive.

Inside the archive: ComfyUI/, python/, OLIVE-RUNTIME.json (definition, ComfyUI commit, lock,
split, licence-text and interpreter digests, and the direct-download list), THIRD_PARTY-creator.txt (generated from the archive's
own wheel metadata) and THIRD_PARTY-creator-direct-downloads.txt (the list of what setup
fetches separately). No models are included.

Tests use --fixture-* inputs (a fake interpreter tree, a fake ComfyUI tree and a local
wheelhouse), so no network and no large download is involved; they pack with the real pinned
interpreter when it is cached, otherwise with --fixture-compressor-python.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
sys.path.insert(0, str(REPOSITORY / 'packaging' / 'legal'))
sys.path.insert(0, str(HERE))
import collect_notices  # noqa: E402
import split_lock  # noqa: E402

SCHEMA = 'olive-creator-runtime/1'
COMPRESSION = HERE / 'compression.json'
COMPRESSION_SCHEMA = 'olive-creator-compression/1'
# The parameters a compression spec may set (compression.zstd CompressionParameter names).
COMPRESSION_PARAMETERS = {'compression_level', 'nb_workers', 'checksum_flag', 'content_size_flag'}
MARKER = 'OLIVE-RUNTIME.json'
NOTICES = 'THIRD_PARTY-creator.txt'
DIRECT_NOTICES = 'THIRD_PARTY-creator-direct-downloads.txt'
# Components whose redistribution inside an OLIVE-hosted archive needs an owner/legal decision.
REVIEW = {
    'torch': 'PyTorch (BSD-3-Clause and bundled third-party notices in torch/ and its dist-info).',
    'comfyui-frontend-package': 'ComfyUI frontend (GPL-3.0); ships compiled web assets whose corresponding source '
                                'is the upstream Comfy-Org/ComfyUI_frontend repository at the pinned version.',
    'comfyui-embedded-docs': 'GPL-3.0.',
    'cuda-pathfinder': 'cuda-python path finder (METADATA Author-email: NVIDIA Corporation), License-Expression '
                       'Apache-2.0, pure Python (kept in the archive).',
    'av': 'PyAV wheels bundle FFmpeg libraries (LGPL/GPL depending on the build); keep their notices.',
}
GPL_NOTE = ('ComfyUI is GPL-3.0-only. Distributing this archive means distributing ComfyUI: keep LICENSE, '
            'and the corresponding source is the pinned public commit recorded in OLIVE-RUNTIME.json.')
# pip's console-script launchers: a direct shebang, or (long paths) its own /bin/sh trampoline.
SHEBANG = re.compile(rb'^#!(/[^\n]*?/bin/python[0-9.]*)[ \t]*\n'
                     rb'|^#!/bin/sh\n\'\'\'exec\' "?(/[^"\n]*?/bin/python[0-9.]*)"? "\$0" "\$@"\n\' \'\'\'\n')


class AuditError(SystemExit):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def clean_environment(cache: Path | None = None) -> dict:
    keep = ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP', 'HOME', 'USERPROFILE', 'LANG', 'SSL_CERT_FILE')
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update(PYTHONNOUSERSITE='1', PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_NO_INPUT='1', PIP_NO_CACHE_DIR='1')
    return env


def load_definition(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if value.get('schema') != SCHEMA:
        raise SystemExit(f'{path}: not an {SCHEMA} definition')
    for key in ('id', 'version', 'target', 'role', 'comfyui', 'lock', 'layout', 'register'):
        if key not in value:
            raise SystemExit(f'{path}: missing {key}')
    if type(value.get('source_date_epoch')) is not int or value['source_date_epoch'] <= 0:
        # The archive's mtimes must come from a pinned runtime input, not the build machine or the OLIVE commit.
        raise SystemExit(f'{path}: missing a pinned integer source_date_epoch')
    for key in ('direct_download', 'archive_lock', 'wheels'):
        if key not in value:
            # OLIVE never builds a Creator archive with direct-download wheels inside (Option B+).
            raise SystemExit(f'{path}: missing {key}; every Creator definition must split its NVIDIA direct downloads')
    return value


def fetch(url: str, expected: str, cache: Path, name: str | None = None) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (name or url.rsplit('/', 1)[-1].replace('%2B', '+'))
    if target.is_file() and sha256(target) == expected:
        return target
    partial = target.with_suffix(target.suffix + '.partial')
    with urllib.request.urlopen(url, timeout=120) as response, open(partial, 'wb') as out:
        shutil.copyfileobj(response, out, 1024 * 1024)
    if sha256(partial) != expected:
        partial.unlink()
        raise SystemExit(f'SHA-256 mismatch for {url}; nothing was used')
    partial.replace(target)
    return target


def checkout(repository: str, commit: str, destination: Path, cache: Path, expected_time: int | None = None):
    """Export exactly one commit (no .git) into destination, verifying the commit hash (and, for the
    ComfyUI commit, that its committer time is the definition's pinned source_date_epoch)."""
    mirror = cache / 'git' / hashlib.sha256(repository.encode()).hexdigest()[:16]
    if not (mirror / 'HEAD').exists():
        subprocess.run(['git', 'init', '--bare', '-q', str(mirror)], check=True)
    cached = subprocess.run(['git', '-C', str(mirror), 'cat-file', '-e', f'{commit}^{{commit}}'],
                            capture_output=True).returncode == 0
    if not cached:  # A commit already in the cache is used as is (still verified below): no network.
        subprocess.run(['git', '-C', str(mirror), 'fetch', '-q', '--depth', '1', repository, commit], check=True)
    resolved = subprocess.run(['git', '-C', str(mirror), 'rev-parse', f'{commit}^{{commit}}'], check=True,
                              capture_output=True, text=True).stdout.strip()
    if resolved != commit:
        raise SystemExit(f'{repository}: fetched {resolved}, expected {commit}')
    if expected_time is not None:
        committed = int(subprocess.run(['git', '-C', str(mirror), 'log', '-1', '--format=%ct', commit], check=True,
                                       capture_output=True, text=True).stdout.strip())
        if committed != expected_time:
            raise SystemExit(f'{repository}@{commit}: committer time {committed} is not the definition\'s '
                             f'source_date_epoch {expected_time}')
    archive = subprocess.run(['git', '-C', str(mirror), 'archive', '--format=tar', commit], check=True,
                             capture_output=True).stdout
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(destination, filter='data')


def wheel_records(definition: dict) -> list[dict]:
    return json.loads((HERE / definition['wheels']).read_text(encoding='utf-8'))['packages']


def prepare_wheelhouse(definition: dict, cache: Path) -> Path:
    """Fetch exactly the archive wheels (URL + SHA-256 from wheels.json) into a wheelhouse."""
    house = cache / 'wheels'
    for record in wheel_records(definition):
        if record['distribution'] == split_lock.ARCHIVE:
            fetch(record['url'], record['sha256'], house, record['filename'])
    return house


def install_wheels(python: Path, lock: Path, wheelhouse: Path, site_packages: Path | None = None):
    """Hash-locked binary wheels from the wheelhouse only. With site_packages (fixture builds,
    whose interpreter is a stub) the builder's pip installs into that folder instead."""
    options = ['--isolated', '--no-index', '--find-links', str(wheelhouse), '--no-deps', '--require-hashes',
               '--only-binary=:all:', '--no-compile', '--no-warn-script-location', '-r', str(lock)]
    if site_packages is not None:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--target', str(site_packages), *options],
                       check=True, env=clean_environment(), stdout=subprocess.DEVNULL)
        return
    subprocess.run([str(python), '-s', '-m', 'pip', 'install', *options], check=True, env=clean_environment())
    subprocess.run([str(python), '-s', '-m', 'pip', 'uninstall', '--isolated', '-y', 'pip'], check=True,
                   env=clean_environment(), stdout=subprocess.DEVNULL)


def _record_hash(data: bytes) -> str:
    return 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()


def _runtime_interpreter(interpreter: bytes, bin_folder: Path) -> bool:
    """Whether a launcher's interpreter is this runtime's own bin/python*. pip always writes the
    absolute path; the build folder may have been given relative, long or through a symlink, so
    the folder is compared by identity, not by spelling."""
    path = Path(os.fsdecode(interpreter))
    try:
        return path.is_absolute() and path.parent.samefile(bin_folder)
    except OSError:
        return False


def relocate_scripts(stage: Path, definition: dict) -> list[str]:
    """pip writes console scripts with the build folder's absolute interpreter path, as a direct
    shebang or (long paths) its own /bin/sh trampoline. Rewrite both to python-build-standalone's
    relocatable /bin/sh trampoline and fix their RECORD lines. Anything else is left for the audit."""
    python_root = stage / definition['layout']['python']
    interpreter = Path(definition['register']['paths']['python']).name
    changed = {}
    for path in sorted((python_root / 'bin').glob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        head = path.read_bytes()[:512]
        match = SHEBANG.match(head)
        if not match or not _runtime_interpreter(match[1] or match[2], python_root / 'bin'):
            continue
        body = path.read_bytes()[match.end():]
        trampoline = (b'#!/bin/sh\n'
                      b"'''exec' \"$(dirname -- \"$(realpath -- \"$0\")\")/" + interpreter.encode() + b'" "$0" "$@"\n'
                      b"' '''\n")
        data = trampoline + body
        path.write_bytes(data)
        changed[path.relative_to(python_root).as_posix()] = data
    if changed:
        site = collect_notices._site_packages(python_root)
        prefix = os.path.relpath(python_root, site).replace(os.sep, '/')
        for record in site.glob('*.dist-info/RECORD'):
            rows = list(csv.reader(record.read_text(encoding='utf-8').splitlines()))
            dirty = False
            for row in rows:
                if row and row[0].startswith(prefix + '/'):
                    relative = row[0][len(prefix) + 1:]
                    if relative in changed:
                        row[1], row[2] = _record_hash(changed[relative]), str(len(changed[relative]))
                        dirty = True
            if dirty:
                out = io.StringIO()
                csv.writer(out, lineterminator='\n').writerows(rows)
                record.write_text(out.getvalue(), encoding='utf-8')
    return sorted(changed)


def prune(root: Path):
    for path in sorted(root.rglob('__pycache__'), reverse=True):
        shutil.rmtree(path, ignore_errors=True)
    for pattern in ('ComfyUI/.git*', 'ComfyUI/tests', 'ComfyUI/tests-unit', 'ComfyUI/.ci', 'ComfyUI/.github'):
        for path in root.glob(pattern):
            shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink()


def audit(stage: Path, definition: dict, records: list[dict]) -> dict:
    """Refuse to pack anything that is not attributable to an archive distribution. Returns the
    archive's distribution inventory."""
    python_root = stage / definition['layout']['python']
    site = collect_notices._site_packages(python_root)
    direct = {split_lock.normalise(r['name']) for r in records if r['distribution'] == split_lock.DIRECT}
    expected = {split_lock.normalise(r['name']): r for r in records if r['distribution'] == split_lock.ARCHIVE}
    owned, inventory, problems = set(), [], []
    for info in sorted(site.glob('*.dist-info')):
        metadata = (info / 'METADATA').read_text(encoding='utf-8', errors='replace')
        name = split_lock.normalise(re.search(r'^Name: (.+)$', metadata, re.M)[1].strip())
        version = re.search(r'^Version: (.+)$', metadata, re.M)[1].strip()
        if name in direct or split_lock.classify(name, definition['direct_download']) == split_lock.DIRECT:
            problems.append(f'{info.name}: direct-download distribution inside the archive')
            continue
        if records and (name not in expected or expected[name]['version'] != version):
            problems.append(f'{info.name}: not in the archive lock at this version')
        for row in csv.reader((info / 'RECORD').read_text(encoding='utf-8').splitlines()):
            if row:
                owned.add(os.path.normpath(site / row[0]))
        inventory.append({'name': name, 'version': version})
    if records:
        missing = set(expected) - {i['name'] for i in inventory}
        if missing:
            problems.append('archive distributions missing after install: ' + ', '.join(sorted(missing)))
    for path in site.rglob('*'):
        if path.is_file() or path.is_symlink():
            if os.path.normpath(path) not in owned and path.name != 'README.txt':
                problems.append(f'{path.relative_to(stage).as_posix()}: not in any archive distribution RECORD')
    # The build folder's path must not leak into scripts, path files or metadata, however it is spelled.
    needles = {os.fsencode(spelling) for spelling in (stage, stage.absolute(), os.path.realpath(stage))}
    for path in [*(python_root / 'bin').glob('*'), *site.glob('*.pth'), *site.glob('*.dist-info/*')]:
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            if any(needle in data for needle in needles):
                problems.append(f'{path.relative_to(stage).as_posix()}: contains the build folder path')
    if problems:
        raise AuditError('Creator archive audit failed:\n  ' + '\n  '.join(problems[:50]))
    return {'distributions': inventory, 'files_attributed': len(owned)}


def runtime_notices(stage: Path, definition: dict) -> str:
    python_root = stage / definition['layout']['python']
    items = collect_notices.distributions(python_root)
    text = collect_notices.notices(python_root, title='OLIVE Creator runtime archive: third-party notices',
                                   review={}, generator='packaging/creator/build_creator_runtime.py',
                                   target=definition['target'])
    flagged = []
    for item in items:
        key = item['name'].lower().replace('_', '-')
        for prefix, note in REVIEW.items():
            if key == prefix or (prefix.endswith('-') and key.startswith(prefix)):
                flagged.append(f"  * {item['name']} {item['version']}: {note}")
                break
    head = ['This file covers ONLY what is inside this archive. The wheels that setup downloads separately from',
            f'PyPI (NVIDIA packages and wheels that bundle NVIDIA components) are listed, with their licence and',
            f'NOTICE texts, in {DIRECT_NOTICES}; they are not part of this archive.', '',
            'Creator-specific owner/legal review items:', '', f'  * ComfyUI {definition["comfyui"]["tag"]}: {GPL_NOTE}']
    for node in definition.get('custom_nodes', []):
        head.append(f"  * {node['name']} @ {node['commit']}: {node['licence']} (licence files kept in its folder)")
    head += flagged + ['']
    licence = stage / definition['layout']['comfyui'] / 'LICENSE'
    tail = ['', '-' * 78, f"ComfyUI {definition['comfyui']['tag']} ({definition['comfyui']['commit']})", '-' * 78,
            licence.read_text(encoding='utf-8', errors='replace') if licence.is_file() else 'LICENSE not found']
    return '\n'.join(head) + '\n' + text + '\n'.join(tail) + '\n'


def attribution(record: dict) -> str:
    """What the wheel's own METADATA says about who made it; nothing is inferred."""
    fields = record.get('wheel_metadata_attribution') or {}
    parts = [f'{key}: {fields[key]}' for key in ('Author', 'Author-email', 'Maintainer', 'Maintainer-email', 'Home-page')
             if fields.get(key)]
    parts += [f'Project-URL: {url}' for url in fields.get('Project-URL') or []]
    return '; '.join(parts) or 'not stated in the wheel metadata'


def direct_licence_texts(definition: dict) -> dict:
    return json.loads((HERE / definition['direct_licences']).read_text(encoding='utf-8'))['texts']


def direct_notices(definition: dict, records: list[dict], texts: dict | None = None) -> str:
    title = 'OLIVE Creator runtime: direct downloads from PyPI (NOT included in the OLIVE archive)'
    direct = [r for r in records if r['distribution'] == split_lock.DIRECT]
    lines = [title, '=' * len(title), '',
             'The packages below are not part of the OLIVE Creator runtime archive. OLIVE setup downloads each',
             'exact file from PyPI (files.pythonhosted.org), checks its pinned size and SHA-256, and unpacks it into',
             'the OLIVE-owned runtime folder on this computer. They are NVIDIA packages, or wheels from other',
             'projects that bundle NVIDIA components, so OLIVE does not host them. Each wheel brings its own licence',
             'files (in its .dist-info folder); their texts are reproduced at the end. The source is PyPI; the',
             'attribution and licence fields below are copied from each wheel\'s own METADATA, nothing is inferred.',
             'This is information, not a legal assessment.', '',
             f'Runtime: {definition["id"]} ({definition["target"]}); {len(direct)} packages, '
             f'{sum(r["size_bytes"] for r in direct):,} bytes', '']
    for record in direct:
        licence = record.get('wheel_metadata_licence') or {}
        declared = licence.get('License-Expression') or licence.get('License') or 'not declared'
        why = ('package name matches the NVIDIA package policy (nvidia-*, cuda-*)' if record.get('direct_reason') == 'nvidia-package'
               else 'bundles NVIDIA components: ' + (record.get('direct_evidence') or ''))
        lines += [f"{record['name']} {record['version']}",
                  f"  file:        {record['filename']}",
                  f"  source:      {record['url']}",
                  f"  project:     {record.get('pypi_project', '')}",
                  f"  sha256:      {record['sha256']}",
                  f"  bytes:       {record['size_bytes']}",
                  f"  why direct:  {why}",
                  f"  metadata:    {attribution(record)}",
                  f"  licence:     {declared}"
                  + (f" (classifiers: {'; '.join(licence['Classifier'])})" if licence.get('Classifier') else ''),
                  f"  licence files: {', '.join(f['path'] + ' [' + f['sha256'][:12] + ']' for f in record.get('licence_files', [])) or 'none in the wheel'}",
                  '']
    if texts is not None:
        seen = set()
        lines += ['-' * 78, 'Licence and NOTICE texts shipped inside these wheels (verified against each wheel\'s RECORD)',
                  '-' * 78, '']
        for record in direct:
            for licence_file in record.get('licence_files', []):
                digest = licence_file['sha256']
                if digest in seen:
                    lines += [f"[{record['name']} {record['version']}: {licence_file['path']}] same text as [{digest[:12]}] above", '']
                    continue
                seen.add(digest)
                lines += [f"[{record['name']} {record['version']}: {licence_file['path']}] [{digest[:12]}]", texts[digest], '']
    return '\n'.join(lines)


def load_compression(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if value.get('schema') != COMPRESSION_SCHEMA or value.get('format') != 'zstd':
        raise SystemExit(f'{path}: not an {COMPRESSION_SCHEMA} zstd spec')
    parameters = value.get('parameters')
    if (not isinstance(value.get('zstd_version'), str) or not isinstance(value.get('interpreters'), dict)
            or not isinstance(parameters, dict) or not set(parameters) <= COMPRESSION_PARAMETERS
            or any(type(v) is not int for v in parameters.values()) or 'compression_level' not in parameters):
        raise SystemExit(f'{path}: needs zstd_version, interpreters and integer parameters '
                         f'({", ".join(sorted(COMPRESSION_PARAMETERS))})')
    if parameters.get('nb_workers') != 0:
        # libzstd's multithreaded engine writes different bytes; only in-thread compression is pinned.
        raise SystemExit(f'{path}: nb_workers must be pinned to 0 (single-threaded)')
    return value


def check_compressor_pin(definition: dict, python_spec: dict, compression: dict):
    pinned = compression['interpreters'].get(definition['target'])
    if pinned != python_spec['sha256']:
        raise SystemExit(f"compression.json pins the {definition['target']} compressor interpreter {pinned}, but "
                         f"python-runtime.json pins {python_spec['sha256']}: changing the interpreter changes the "
                         'compressor, so update compression.json deliberately')


def compressor_python(definition: dict, python_spec: dict, cache: Path, output: Path) -> Path:
    """A private copy of the pinned interpreter (the same verified, cached asset the runtime is
    built from), so packing never executes anything inside the staged runtime."""
    folder = output / (definition['id'] + '.compressor')
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    with tarfile.open(fetch(python_spec['url'], python_spec['sha256'], cache)) as tar:
        tar.extractall(folder, filter='data')
    return folder / 'python' / python_spec['python']


def pack(stage: Path, archive: Path, epoch: int, compression: dict, python: Path, *, fixture: bool = False) -> dict:
    """Run pack_archive.py under the pinned interpreter; returns its compressor identity and tar digest."""
    spec = {'epoch': epoch, 'zstd_version': compression['zstd_version'], 'parameters': compression['parameters']}
    # -I -S: nothing from the build machine's environment or site-packages; -B: writes no bytecode;
    # -X utf8: file names are encoded the same under any locale.
    result = subprocess.run([str(python), '-I', '-B', '-S', '-X', 'utf8', str(HERE / 'pack_archive.py'),
                             str(stage.absolute()), str(archive.absolute()), json.dumps(spec)],
                            capture_output=True, text=True, env=clean_environment())
    if result.returncode != 0:
        archive.unlink(missing_ok=True)
        raise SystemExit('Packing the archive failed:\n' + (result.stderr or result.stdout).strip())
    report = json.loads(result.stdout)
    if report['zstd_version'] != compression['zstd_version'] or not (report['builtin'] or fixture):
        archive.unlink(missing_ok=True)
        raise SystemExit(f'the compressor is not the pinned built-in libzstd {compression["zstd_version"]}: {report}')
    return report


def executables(stage: Path, definition: dict) -> list[str]:
    """Regular executable files of the interpreter's bin/ (setup refuses links as executables);
    the registered interpreter path itself may be a link to one of them."""
    python = stage / definition['register']['paths']['python']
    interpreter = python.resolve() if python.is_symlink() else python
    if not interpreter.is_relative_to(stage.resolve() if python.is_symlink() else stage) or not interpreter.is_file():
        raise SystemExit(f"{definition['register']['paths']['python']} does not lead to an interpreter inside the runtime")
    found = {p.relative_to(stage).as_posix() for p in (stage / definition['layout']['python'] / 'bin').glob('*')
             if p.is_file() and not p.is_symlink() and os.access(p, os.X_OK)}
    return sorted(found)


def provenance(source_commit: str | None = None, output: Path | None = None, repository: Path = REPOSITORY) -> dict:
    """The OLIVE repository state this build ran from. Sidecar metadata only: it is never written
    into the archive, so recording it cannot change the archive's bytes. working_tree_clean is
    about the SOURCE checkout: the builder's own --output folder (CI builds into out/ inside the
    checkout) is left out of the status, and nothing else is. A folder holding tracked files is
    source, so it is never left out."""
    def git(*arguments):
        result = subprocess.run(['git', '-C', str(repository), *arguments], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    excluded = None
    if output is not None:
        try:
            excluded = Path(os.path.realpath(output)).relative_to(os.path.realpath(repository)).as_posix()
        except ValueError:
            pass  # Outside the checkout: nothing to leave out.
    if excluded not in (None, '.') and git('ls-files', '--', f':(top){excluded}') != '':
        excluded = None
    if excluded in (None, '.'):
        status, excluded = git('status', '--porcelain'), None
    else:
        status = git('status', '--porcelain', '--', ':/', f':(top,exclude){excluded}')
    value = {'olive_source_commit': source_commit or os.environ.get('OLIVE_SOURCE_COMMIT') or git('rev-parse', 'HEAD'),
             'working_tree_clean': None if status is None else not status,
             'builder': 'packaging/creator/build_creator_runtime.py'}
    if excluded:
        value['working_tree_excludes'] = [excluded + '/']  # The build's own output, not a source change.
    return value


def direct_entry(definition: dict, records: list[dict]) -> list[dict]:
    """The manifest's direct-download records: exactly the lock's direct wheels for this target."""
    out = []
    for record in records:
        if record['distribution'] != split_lock.DIRECT:
            continue
        licence = record.get('wheel_metadata_licence') or {}
        out.append({'name': record['filename'], 'package': record['name'], 'version': record['version'],
                    'url': record['url'], 'sha256': record['sha256'], 'size_bytes': record['size_bytes'],
                    'installed_bytes': (record.get('layout') or {}).get('installed_bytes'),
                    'licence': licence.get('License-Expression') or licence.get('License') or 'not declared',
                    'reason': record.get('direct_reason'), 'project': record.get('pypi_project'),
                    'metadata_attribution': attribution(record)})
    return out


def build(definition_path: Path, output: Path, cache: Path, *, fixture_python: Path | None = None,
          fixture_comfyui: Path | None = None, wheelhouse: Path | None = None, source_commit: str | None = None,
          compression_path: Path = COMPRESSION, fixture_compressor: Path | None = None) -> dict:
    definition = load_definition(definition_path)
    compression = load_compression(compression_path)
    if fixture_compressor is not None and fixture_python is None:
        raise SystemExit('--fixture-compressor-python is for fixture builds only; a release build packs with the '
                         'pinned interpreter')
    problems = split_lock.check(definition)
    if problems:
        raise SystemExit('The direct-download split is not consistent:\n  ' + '\n  '.join(problems))
    records = wheel_records(definition)
    epoch = definition['source_date_epoch']  # Pinned with the runtime inputs; never the OLIVE commit time.
    lock = (HERE / definition['archive_lock']).resolve()
    stage = output / (definition['id'] + '.staging')
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    layout = definition['layout']
    runtime = json.loads((REPOSITORY / 'packaging' / 'backend' / 'python-runtime.json').read_text(encoding='utf-8'))
    python_spec = runtime['targets'][definition['target']]
    if fixture_compressor is None:
        check_compressor_pin(definition, python_spec, compression)
    if fixture_python is not None:
        shutil.copytree(fixture_python, stage / layout['python'], symlinks=True)
    else:
        archive = fetch(python_spec['url'], python_spec['sha256'], cache)
        with tarfile.open(archive) as tar:  # python-build-standalone archives hold one top-level python/
            tar.extractall(stage, filter='data')
        if layout['python'] != 'python':
            (stage / 'python').rename(stage / layout['python'])
    if fixture_comfyui is not None:
        shutil.copytree(fixture_comfyui, stage / layout['comfyui'])
    else:
        checkout(definition['comfyui']['repository'], definition['comfyui']['commit'], stage / layout['comfyui'], cache,
                 expected_time=epoch)
        for node in definition.get('custom_nodes', []):
            checkout(node['repository'], node['commit'], stage / layout['comfyui'] / 'custom_nodes' / node['name'], cache)
    python = stage / definition['register']['paths']['python']
    site = None
    if fixture_python is not None:
        site = collect_notices._site_packages(stage / layout['python'])
    house = wheelhouse if wheelhouse is not None else prepare_wheelhouse(definition, cache)
    install_wheels(python, lock, house, site)
    relocated = relocate_scripts(stage, definition)
    prune(stage)
    # Fixture locks are not the release lock: their version check is skipped, the direct-download checks still run.
    inventory = audit(stage, definition, [] if fixture_python is not None else records)
    (stage / NOTICES).write_text(runtime_notices(stage, definition), encoding='utf-8')
    direct_text = direct_notices(definition, records, direct_licence_texts(definition))
    (stage / DIRECT_NOTICES).write_text(direct_text, encoding='utf-8')
    direct = direct_entry(definition, records)
    # Everything here is a runtime input or derived from one: no OLIVE commit, no build time.
    record = {
        'schema': SCHEMA, 'id': definition['id'], 'version': definition['version'], 'target': definition['target'],
        'role': definition['role'], 'definition_sha256': sha256(definition_path),
        'comfyui': definition['comfyui'], 'custom_nodes': definition.get('custom_nodes', []),
        'python': {'asset': python_spec['asset'], 'sha256': python_spec['sha256'], 'fixture': fixture_python is not None},
        'lock': {'path': definition['lock'], 'sha256': sha256(HERE / definition['lock'])},
        'archive_lock': {'path': definition['archive_lock'], 'sha256': sha256(lock)},
        'wheels': {'path': definition['wheels'], 'sha256': sha256(HERE / definition['wheels'])},
        'direct_licences': {'path': definition['direct_licences'], 'sha256': sha256(HERE / definition['direct_licences'])},
        'direct_downloads': {'policy': definition['direct_download']['reason'],
                             'site_packages': definition['direct_download']['site_packages'],
                             'wheels': [{k: w[k] for k in ('package', 'version', 'name', 'sha256', 'size_bytes')}
                                        for w in direct]},
        'source_date_epoch': epoch,
    }
    inputs = {'definition_sha256': record['definition_sha256'], 'python_sha256': python_spec['sha256'],
              'comfyui_commit': definition['comfyui']['commit'], 'lock_sha256': record['lock']['sha256'],
              'archive_lock_sha256': record['archive_lock']['sha256'], 'wheels_sha256': record['wheels']['sha256'],
              'direct_licences_sha256': record['direct_licences']['sha256'], 'source_date_epoch': epoch,
              # How the stable tar is compressed: changes the archive bytes, never the payload.
              'compression_sha256': sha256(compression_path)}
    (stage / MARKER).write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    installed = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file() and not p.is_symlink())
    archive = output / f"{definition['id']}.tar.zst"
    packer = fixture_compressor or compressor_python(definition, python_spec, cache, output)
    packed = pack(stage, archive, epoch, compression, packer, fixture=fixture_compressor is not None)
    if fixture_compressor is None:
        shutil.rmtree(output / (definition['id'] + '.compressor'))
    digest = sha256(archive)
    compressed = {'format': 'zstd', 'implementation': packed['implementation'], 'zstd_version': packed['zstd_version'],
                  'builtin': packed['builtin'], 'parameters': packed['parameters'],
                  'interpreter_sha256': 'fixture' if fixture_compressor is not None else python_spec['sha256'],
                  'spec': Path(compression_path).name, 'spec_sha256': inputs['compression_sha256'],
                  'tar_sha256': packed['tar_sha256'], 'tar_bytes': packed['tar_bytes']}
    (output / (archive.name + '.sha256')).write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    (output / f"{definition['id']}.{DIRECT_NOTICES.replace('THIRD_PARTY-creator-', 'THIRD_PARTY-')}").write_text(
        direct_text, encoding='utf-8')
    direct_installed = sum(w['installed_bytes'] or 0 for w in direct)
    entry = {
        'id': definition['id'], 'archive': archive.name, 'sha256': digest, 'size_bytes': archive.stat().st_size,
        'install': {'destination': definition['destination'], 'format': 'tar.zst',
                    'installed_bytes': installed + direct_installed, 'archive_installed_bytes': installed,
                    'executables': executables(stage, definition), 'modes': 'archive',
                    'register': definition['register'],
                    'direct_wheels_target': definition['direct_download']['site_packages'],
                    # Setup starts the staged runtime once with OLIVE's own probe before registering it.
                    'verify': 'comfyui-cuda'},
        'direct_wheels': {definition['target']: direct},
        'direct_hosts': definition['direct_download']['hosts'],
        'direct_source': definition['direct_download'].get('source_label', 'PyPI'),
        'direct_summary': definition['direct_download'].get('summary'),
        'url': None,
        'inputs': inputs,
        'compression': compressed,
        # Provenance of THIS build, outside the archive: it never changes the archive's bytes.
        'build_provenance': provenance(source_commit, output),
        'relocated_scripts': relocated,
        'note': 'url stays null until the owner publishes this archive; the release manifest entry also needs '
                'engineering review and an owner release approval.',
    }
    (output / f"{definition['id']}.manifest-entry.json").write_text(json.dumps(entry, indent=2) + '\n', encoding='utf-8')
    (output / f"{definition['id']}.inventory.json").write_text(json.dumps({
        'id': definition['id'], 'archive_sha256': digest, 'inputs': inputs, 'compression': compressed,
        'build_provenance': entry['build_provenance'],
        'archive_distributions': inventory['distributions'],
        'files_attributed_to_records': inventory['files_attributed'],
        'direct_downloads': [{k: w[k] for k in ('package', 'version', 'name', 'sha256', 'size_bytes', 'licence')}
                             for w in direct]}, indent=1) + '\n', encoding='utf-8')
    shutil.rmtree(stage)
    return entry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('definition', type=Path)
    parser.add_argument('--output', type=Path, default=REPOSITORY / 'desktop' / 'dist' / 'creator')
    parser.add_argument('--cache', type=Path, default=HERE / '.cache')
    parser.add_argument('--fixture-python', type=Path, help='tests only: a prepared interpreter tree')
    parser.add_argument('--fixture-comfyui', type=Path, help='tests only: a prepared ComfyUI tree')
    parser.add_argument('--fixture-compressor-python', type=Path,
                        help='tests only (with --fixture-python): pack with this interpreter instead of the pinned one')
    parser.add_argument('--wheelhouse', type=Path, help='install from this folder (default: fetch the archive '
                                                        'wheels from wheels.json into --cache)')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    entry = build(args.definition, args.output, args.cache, fixture_python=args.fixture_python,
                  fixture_comfyui=args.fixture_comfyui, wheelhouse=args.wheelhouse,
                  fixture_compressor=args.fixture_compressor_python)
    print(json.dumps({k: v for k, v in entry.items() if k != 'direct_wheels'}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
