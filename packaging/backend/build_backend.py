"""Build the self-contained OLIVE Python backend for the host platform.

Output: desktop/backend-artifact/ (ignored by Git), which electron-builder copies
to resources/backend. Layout:

    Linux / macOS                 Windows
    bin/python3                   python.exe
    lib/python3.14/...            Lib/..., DLLs/...
    olive/                        olive/
    olive-backend.json            olive-backend.json

Inputs are all pinned in this directory:
  * python-runtime.json  - the relocatable CPython (python-build-standalone) asset,
                           URL and SHA-256 per target;
  * locks/<target>.txt   - hash-locked backend dependencies (`uv pip compile`
                           of pyproject.toml `dependencies`, binary wheels only).

The build verifies every download, installs nothing outside the artefact, never
uses the system Python's site-packages or the repository .venv, excludes the Qt
fallback (olive/ui_qt, PySide6), the dmdo compatibility package, Playwright and
pip, and finishes with an import + bridge start smoke test in a throwaway
profile. Run it with any Python >= 3.11 on the target operating system:

    python packaging/backend/build_backend.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
DEFAULT_OUTPUT = REPOSITORY / 'desktop' / 'backend-artifact'
DEFAULT_CACHE = HERE / '.cache'
MANIFEST = 'olive-backend.json'

# Never shipped in the Electron backend (source-only or development-only).
EXCLUDED_SOURCE = ('olive/ui_qt', 'olive/__main__.py')
FORBIDDEN_DISTRIBUTIONS = ('pyside6', 'shiboken6', 'playwright', 'pip', 'setuptools')
# Interpreter parts that the backend never uses (GUI toolkit, test suite, IDLE,
# headers and static/import libraries for building extensions).
PRUNE_POSIX = ('include', 'share', 'lib/itcl4*', 'lib/tcl9*', 'lib/tk9*', 'lib/thread3*', 'lib/tcl8*', 'lib/tk8*',
               'lib/python3.14/test', 'lib/python3.14/idlelib', 'lib/python3.14/tkinter',
               'lib/python3.14/turtledemo', 'lib/python3.14/ensurepip', 'lib/python3.14/config-3.14-*',
               'lib/python3.14/lib-dynload/_tkinter*', 'lib/python3.14/turtle.py', 'lib/pkgconfig',
               'bin/idle3*', 'bin/pydoc3*', 'bin/pip*', 'bin/2to3*', 'bin/python3*-config')
# The Linux interpreter is statically linked (verified by the smoke test importing every
# module), so the embedding library is unused there; macOS's interpreter links it.
PRUNE_LINUX = ('lib/libpython3*.so*', 'lib/libtcl*', 'lib/libtk*')
PRUNE_MACOS = ('lib/libtcl*', 'lib/libtk*')
PRUNE_WINDOWS = ('include', 'libs', 'tcl', 'Scripts', 'Lib/test', 'Lib/idlelib', 'Lib/tkinter', 'Lib/turtledemo',
                 'Lib/ensurepip', 'Lib/turtle.py', 'DLLs/_tkinter.pyd', 'DLLs/tcl*.dll', 'DLLs/tk*.dll')


def host_target() -> str:
    machine = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(machine, machine)
    system = {'linux': 'linux', 'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, sys.platform)
    return f'{system}-{arch}'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def fetch(spec: dict, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / spec['asset']
    if target.is_file() and sha256(target) == spec['sha256']:
        return target
    partial = target.with_suffix(target.suffix + '.part')
    print(f'Downloading {spec["asset"]}', flush=True)
    with urllib.request.urlopen(spec['url'], timeout=120) as response, partial.open('wb') as output:
        shutil.copyfileobj(response, output, 1 << 20)
    actual = sha256(partial)
    if actual != spec['sha256']:
        partial.unlink()
        raise SystemExit(f'SHA-256 mismatch for {spec["asset"]}: {actual}; the download was discarded')
    partial.replace(target)
    return target


def extract(archive: Path, stage: Path) -> None:
    """Extract the distribution's top-level `python/` directory into `stage`."""
    with tarfile.open(archive) as bundle:
        members = []
        for member in bundle.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] != 'python' or len(parts) == 1:
                continue
            member.name = str(Path(*parts[1:]))
            members.append(member)
        try:
            bundle.extractall(stage, members=members, filter='data')
        except TypeError:  # Python without extraction filters (< 3.11.4).
            for member in members:
                if member.name.startswith(('/', '..')) or '..' in Path(member.name).parts:
                    raise SystemExit(f'Unsafe archive member: {member.name}')
            bundle.extractall(stage, members=members)


def remove(stage: Path, patterns) -> list[str]:
    removed = []
    for pattern in patterns:
        for path in sorted(stage.glob(pattern)):
            removed.append(path.relative_to(stage).as_posix())
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    return removed


def prune_records(site_packages: Path, stage: Path) -> None:
    """Drop RECORD rows for files the build removed (console scripts carry the build path)."""
    for record in site_packages.glob('*.dist-info/RECORD'):
        kept = []
        for line in record.read_text(encoding='utf-8').splitlines():
            relative = line.split(',', 1)[0]
            target = (site_packages / relative).resolve()
            if '__pycache__' in relative or not (target.exists() or target.is_symlink()):
                continue
            if stage.resolve() not in target.parents and target != stage.resolve():
                continue
            kept.append(line)
        record.write_text('\n'.join(kept) + '\n', encoding='utf-8')


def clean_environment(**extra) -> dict:
    keep = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'HOME',
            'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'COMSPEC', 'PATHEXT'}
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
               PIP_NO_INPUT='1', **extra)
    return env


def olive_sources() -> list[Path]:
    """Files of the olive package that Git does not ignore (fallback: a filtered walk without Git)."""
    try:
        listed = subprocess.run(['git', '-C', str(REPOSITORY), 'ls-files', '-z', '--cached', '--others',
                                 '--exclude-standard', 'olive'], check=True,
                                capture_output=True).stdout.decode().split('\0')
        files = [Path(name) for name in listed if name]
    except (OSError, subprocess.CalledProcessError):
        files = [p.relative_to(REPOSITORY) for p in (REPOSITORY / 'olive').rglob('*') if p.is_file()]
    chosen = []
    for relative in files:
        text = relative.as_posix()
        if any(text == item or text.startswith(item + '/') for item in EXCLUDED_SOURCE):
            continue
        if '__pycache__' in relative.parts or relative.suffix in {'.pyc', '.pyo', '.save'}:
            continue
        if (REPOSITORY / relative).is_file():
            chosen.append(relative)
    return sorted(chosen)


def source_revision() -> dict:
    try:
        head = subprocess.run(['git', '-C', str(REPOSITORY), 'rev-parse', 'HEAD'], check=True,
                              capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(['git', '-C', str(REPOSITORY), 'status', '--porcelain', '--', 'olive'],
                                    check=True, capture_output=True, text=True).stdout.strip())
        return {'commit': head, 'olive_tree_modified': dirty}
    except (OSError, subprocess.CalledProcessError):
        return {'commit': None, 'olive_tree_modified': None}


def installed_distributions(python: Path) -> list[dict]:
    script = ('import importlib.metadata as m,json;'
              'print(json.dumps(sorted([{"name":d.metadata["Name"],"version":d.version} for d in m.distributions()],'
              'key=lambda x:x["name"].lower())))')
    output = subprocess.run([str(python), '-s', '-c', script], check=True, capture_output=True, text=True,
                            env=clean_environment()).stdout
    return json.loads(output)


def directory_size(path: Path) -> int:
    return sum(p.lstat().st_size for p in path.rglob('*') if p.is_file() or p.is_symlink())


def build(target: str, output: Path, cache: Path, smoke: bool = True) -> dict:
    runtime = json.loads((HERE / 'python-runtime.json').read_text(encoding='utf-8'))
    if target not in runtime['targets']:
        reason = runtime.get('unsupported_targets', {}).get(target, 'no pinned runtime for this target')
        raise SystemExit(f'Cannot build the OLIVE backend for {target}: {reason}')
    spec = runtime['targets'][target]
    lock = HERE / spec['lock']
    identity = json.loads((REPOSITORY / 'olive' / 'identity.json').read_text(encoding='utf-8'))

    archive = fetch(spec, cache)
    stage = output.with_name(output.name + '.staging')
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    extract(archive, stage)
    python = stage / spec['python']
    if not python.is_file():
        raise SystemExit(f'The runtime archive has no {spec["python"]}')

    # Dependencies: exact hash-locked binary wheels into the artefact's own site-packages.
    subprocess.run([str(python), '-s', '-m', 'pip', 'install', '--isolated', '--no-deps', '--require-hashes',
                    '--only-binary=:all:', '--no-compile', '--no-warn-script-location', '-r', str(lock)],
                   check=True, env=clean_environment())
    subprocess.run([str(python), '-s', '-m', 'pip', 'uninstall', '--isolated', '-y', 'pip'], check=True,
                   env=clean_environment(), stdout=subprocess.DEVNULL)

    # OLIVE itself lives at the artefact root (olive/), next to the interpreter, so the
    # Linux desktop helpers that run under the distribution Python can import it alone.
    sources = olive_sources()
    for relative in sources:
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY / relative, destination)
    site_packages = stage / spec['site_packages']
    (site_packages / 'olive-backend.pth').write_text(os.path.relpath(stage, site_packages).replace('\\', '/') + '\n',
                                                     encoding='utf-8')

    if target.startswith('windows'):
        pruned = remove(stage, PRUNE_WINDOWS)
    else:
        pruned = remove(stage, PRUNE_POSIX + (PRUNE_LINUX if target.startswith('linux') else PRUNE_MACOS))
        # Console scripts carry the build machine's absolute shebang and are never used.
        for entry in sorted((stage / 'bin').iterdir()):
            if not entry.name.startswith('python'):
                pruned += remove(stage, [entry.relative_to(stage).as_posix()])
    for cache_dir in stage.rglob('__pycache__'):
        shutil.rmtree(cache_dir, ignore_errors=True)
    prune_records(site_packages, stage)
    # Byte-code is compiled once at build time. unchecked-hash .pyc stay valid after
    # installers rewrite file times, and the backend runs with PYTHONDONTWRITEBYTECODE.
    # -s strips the staging path, so no build-machine path is embedded. One process in
    # compileall's sorted order plus a fixed hash seed keeps marshal output (reference
    # flags, set order) stable, so builds in different directories produce identical files.
    subprocess.run([str(python), '-s', '-m', 'compileall', '-q', '-j', '1', '--invalidation-mode', 'unchecked-hash',
                    '-s', str(stage), str(stage)], check=True, env=clean_environment(PYTHONHASHSEED='0'))

    distributions = installed_distributions(python)
    forbidden = [d['name'] for d in distributions if d['name'].lower() in FORBIDDEN_DISTRIBUTIONS]
    if forbidden or (stage / 'olive' / 'ui_qt').exists() or (stage / 'dmdo').exists():
        raise SystemExit(f'Excluded components reached the artefact: {forbidden or "olive/ui_qt or dmdo"}')

    # Third-party notices from the artefact's own metadata (packaging/legal/collect_notices.py).
    sys.path.insert(0, str(REPOSITORY / 'packaging' / 'legal'))
    from collect_notices import NAME as NOTICES, notices
    (stage / NOTICES).write_text(notices(stage), encoding='utf-8')

    manifest = {
        'schema': 'olive-backend/1',
        'product': identity['name'],
        'version': identity['version'],
        'target': target,
        'layout': {'python': spec['python'], 'package': 'olive', 'site_packages': spec['site_packages']},
        'python': {'implementation': runtime['implementation'], 'version': runtime['version'],
                   'distribution': runtime['distribution'], 'release': runtime['release'],
                   'asset': spec['asset'], 'url': spec['url'], 'sha256': spec['sha256']},
        'dependencies': {'lock': f'packaging/backend/{spec["lock"]}', 'lock_sha256': sha256(lock),
                         'distributions': distributions},
        'source': {**source_revision(), 'olive_files': len(sources)},
        'notices': NOTICES,
        'excluded': {'source': list(EXCLUDED_SOURCE) + ['dmdo/'],
                     'distributions': ['PySide6', 'shiboken6', 'playwright (and browser binaries)', 'pip'],
                     'interpreter': pruned},
    }
    (stage / MANIFEST).write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    if smoke:
        subprocess.run([str(python), '-s', '-P', str(HERE / 'smoke_backend.py'), str(stage)], check=True,
                       env=clean_environment())

    if output.exists():
        retired = output.with_name(output.name + '.previous')
        if retired.exists():
            shutil.rmtree(retired)
        output.replace(retired)
        shutil.rmtree(retired)
    stage.replace(output)
    manifest['size_bytes'] = directory_size(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--target', default=host_target(), help='defaults to the host (cross builds are refused)')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    parser.add_argument('--skip-smoke', action='store_true', help='skip the post-build start test (not for releases)')
    args = parser.parse_args()
    if args.target != host_target():
        raise SystemExit(f'Build the {args.target} backend on that platform; this host is {host_target()}.')
    manifest = build(args.target, args.output.resolve(), args.cache.resolve(), smoke=not args.skip_smoke)
    print(f'OLIVE backend {manifest["version"]} for {manifest["target"]}: {args.output} '
          f'({manifest["size_bytes"] / 1048576:.1f} MiB, {len(manifest["dependencies"]["distributions"])} distributions)')


if __name__ == '__main__':
    main()
