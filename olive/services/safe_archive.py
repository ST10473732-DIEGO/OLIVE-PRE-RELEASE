"""Extract verified setup archives into a private staging folder, refusing anything unsafe.

Every member is checked before a byte is written:

* names must be relative, without '..', drive letters, backslashes or NUL;
* only regular files and directories are written, plus (tar only) symbolic links
  whose target stays inside the staging folder; hard links, devices and FIFOs are
  refused, and zip links are refused outright;
* member count and total uncompressed bytes are bounded, and a zip member that
  inflates beyond its declared size is refused (zip bombs);
* nothing is written through a link, and no file is overwritten.

Afterwards every file is made non-executable except the paths the manifest names
(executables), and setuid/setgid/sticky bits never survive. An entry whose bytes are
pinned as a whole may instead keep its members' own executable bit (keep_exec), normalised
to 0755/0644. The caller moves the staging folder into place atomically; a failed
extraction leaves only staging.

install_wheel unpacks one verified wheel into an existing site-packages folder the way an
installer does for purelib/platlib wheels: every member must be listed in the wheel's
RECORD with a matching SHA-256 and size, .data parts other than purelib/platlib (scripts,
headers, data) are refused rather than guessed at, nothing is overwritten, and the
.dist-info gains an INSTALLER file. No code from the wheel runs.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import threading
import zipfile

MAX_MEMBERS = 200_000
MAX_NAME = 1024
CHUNK = 1024 * 1024


class ArchiveError(Exception):
    pass


def _clean(name: str) -> PurePosixPath:
    if not isinstance(name, str) or not name or len(name) > MAX_NAME or '\x00' in name or '\\' in name:
        raise ArchiveError(f'Unsafe archive member name: {name[:80]!r}')
    if name.startswith('/') or (len(name) > 1 and name[1] == ':'):
        raise ArchiveError(f'Archive member has an absolute path: {name[:80]!r}')
    path = PurePosixPath(name)
    parts = [p for p in path.parts if p not in ('', '.')]
    if not parts or any(p == '..' for p in parts):
        raise ArchiveError(f'Archive member escapes the destination: {name[:80]!r}')
    return PurePosixPath(*parts)


def _inside(root: Path, relative: PurePosixPath) -> Path:
    target = root.joinpath(*relative.parts)
    # No parent component may be a link: writing through one could leave the root.
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ArchiveError(f'Archive member would be written through a link: {relative}')
    return target


def _link_target_inside(relative: PurePosixPath, linkname: str) -> bool:
    if not linkname or linkname.startswith('/') or '\\' in linkname or '\x00' in linkname:
        return False
    depth = len(relative.parts) - 1
    for part in PurePosixPath(linkname).parts:
        if part == '..':
            depth -= 1
            if depth < 0:
                return False
        elif part not in ('', '.'):
            depth += 1
    return True


class _Budget:
    def __init__(self, max_bytes, max_members, cancel):
        self.max_bytes, self.max_members, self.cancel = max_bytes, max_members, cancel
        self.bytes = self.members = 0

    def member(self):
        self.members += 1
        if self.members > self.max_members:
            raise ArchiveError('The archive has more members than allowed')
        if self.cancel is not None and self.cancel.is_set():
            from .secure_download import Cancelled
            raise Cancelled()

    def add(self, count):
        self.bytes += count
        if self.bytes > self.max_bytes:
            raise ArchiveError('The archive expands beyond its allowed size')


def _copy(source, target: Path, limit: int, budget: _Budget, digest=None):
    written = 0
    with open(target, 'xb') as out:
        while block := source.read(CHUNK):
            written += len(block)
            if written > limit:
                raise ArchiveError(f'Archive member is larger than declared: {target.name}')
            budget.add(len(block))
            if digest is not None:
                digest.update(block)
            out.write(block)
    return written


def _mark_executable(target: Path, mode: int, keep_exec: bool):
    if keep_exec and os.name != 'nt' and mode & 0o111:
        os.chmod(target, 0o755)


def _extract_tar(archive: Path, mode: str, staging: Path, budget: _Budget, keep_exec=False):
    with tarfile.open(archive, mode) as tar:
        for member in tar:
            budget.member()
            relative = _clean(member.name)
            target = _inside(staging, relative)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if member.issym():
                if not _link_target_inside(relative, member.linkname):
                    raise ArchiveError(f'Archive link points outside the destination: {relative}')
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    raise ArchiveError(f'Archive member repeats a path: {relative}')
                os.symlink(member.linkname, target)
                continue
            if not member.isreg():
                raise ArchiveError(f'Archive member type is not allowed: {relative}')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise ArchiveError(f'Archive member repeats a path: {relative}')
            source = tar.extractfile(member)
            if source is None:
                raise ArchiveError(f'Archive member could not be read: {relative}')
            with source:
                if _copy(source, target, member.size, budget) != member.size:
                    raise ArchiveError(f'Archive member is truncated: {relative}')
            _mark_executable(target, member.mode, keep_exec)


def _wheel_name(relative: PurePosixPath) -> PurePosixPath | None:
    """Wheel layout: <dist>.data/{purelib,platlib}/x installs at x; other .data parts are skipped."""
    first = relative.parts[0]
    if first.endswith('.data'):
        if len(relative.parts) > 2 and relative.parts[1] in ('purelib', 'platlib'):
            return PurePosixPath(*relative.parts[2:])
        return None
    return relative


def _extract_zip(archive: Path, staging: Path, budget: _Budget, wheel=False):
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            budget.member()
            relative = _clean(info.filename.rstrip('/') if info.is_dir() else info.filename)
            if wheel:
                relative = _wheel_name(relative)
                if relative is None:
                    continue
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ArchiveError(f'Links are not allowed in zip archives: {relative}')
            if info.flag_bits & 0x1:
                raise ArchiveError(f'Encrypted archive members are not allowed: {relative}')
            target = _inside(staging, relative)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if mode and not (stat.S_ISREG(mode) or stat.S_IFMT(mode) == 0):
                raise ArchiveError(f'Archive member type is not allowed: {relative}')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise ArchiveError(f'Archive member repeats a path: {relative}')
            with bundle.open(info) as source:
                if _copy(source, target, info.file_size, budget) != info.file_size:
                    raise ArchiveError(f'Archive member is truncated: {relative}')


def normalise_modes(staging: Path, executables=(), keep_exec=False):
    """Only manifest-declared executables keep an executable bit (with keep_exec, also files that
    were extracted executable); nothing keeps setuid/setgid/sticky or group/other write."""
    if os.name == 'nt':
        return
    allowed = {PurePosixPath(e) for e in executables}
    for directory, folders, files in os.walk(staging):
        base = Path(directory)
        os.chmod(base, 0o755)
        for name in files:
            path = base / name
            if path.is_symlink():
                continue
            relative = PurePosixPath(path.relative_to(staging).as_posix())
            executable = relative in allowed or (keep_exec and path.stat().st_mode & 0o100)
            os.chmod(path, 0o755 if executable else 0o644)


def require_executables(staging: Path, executables=()):
    for executable in executables:
        path = _inside(Path(staging), _clean(executable))
        if not path.is_file() or path.is_symlink():
            raise ArchiveError(f'The archive does not contain its declared executable {executable}')


def extract(archive: Path, fmt: str, staging: Path, *, max_bytes: int, executables=(),
            max_members=MAX_MEMBERS, cancel: threading.Event | None = None, keep_exec=False) -> int:
    """Extract into staging (which must not exist yet). Returns the bytes written."""
    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=False)
    budget = _Budget(max_bytes, max_members, cancel)
    try:
        if fmt in ('tar.zst', 'tar.gz', 'tar.xz'):
            _extract_tar(Path(archive), {'tar.zst': 'r:zst', 'tar.gz': 'r:gz', 'tar.xz': 'r:xz'}[fmt], staging, budget,
                         keep_exec=keep_exec)
        elif fmt in ('zip', 'wheel'):
            _extract_zip(Path(archive), staging, budget, wheel=fmt == 'wheel')
        else:
            raise ArchiveError(f'Unsupported archive format: {fmt}')
        require_executables(staging, executables)
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError) as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise ArchiveError(f'The archive could not be extracted: {type(error).__name__}') from error
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return budget.bytes


def extract_more(archive: Path, fmt: str, staging: Path, *, max_bytes: int, cancel=None) -> int:
    """Add another archive (for example a further wheel) into an existing staging folder."""
    budget = _Budget(max_bytes, MAX_MEMBERS, cancel)
    try:
        if fmt == 'wheel':
            _extract_zip(Path(archive), Path(staging), budget, wheel=True)
        else:
            raise ArchiveError(f'Unsupported archive format: {fmt}')
    except (zipfile.BadZipFile, EOFError, OSError) as error:
        raise ArchiveError(f'The archive could not be extracted: {type(error).__name__}') from error
    return budget.bytes


def _record_rows(text: str) -> dict[str, tuple[str, str]]:
    rows = {}
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if len(row) != 3:
            raise ArchiveError('The wheel RECORD has a malformed line')
        rows[row[0]] = (row[1], row[2])
    return rows


def install_wheel(wheel: Path, site_packages: Path, *, max_bytes: int, cancel=None, installer='olive-setup',
                  keep_exec=True) -> list[str]:
    """Unpack one already-verified wheel into an existing site-packages folder (see the module
    docstring). Returns the installed paths relative to site_packages. On failure the caller
    discards the whole staging folder."""
    site = Path(site_packages)
    if not site.is_dir() or site.is_symlink():
        raise ArchiveError('The runtime has no site-packages folder for its direct downloads')
    budget = _Budget(max_bytes, MAX_MEMBERS, cancel)
    installed = []
    try:
        with zipfile.ZipFile(wheel) as bundle:
            infos = bundle.infolist()
            records = [i for i in infos if _clean(i.filename).name == 'RECORD'
                       and len(_clean(i.filename).parts) == 2 and _clean(i.filename).parts[0].endswith('.dist-info')]
            if len(records) != 1:
                raise ArchiveError('The wheel has no single .dist-info/RECORD')
            dist_info = _clean(records[0].filename).parts[0]
            record_name = records[0].filename
            if records[0].file_size > 64 * 1024 * 1024:
                raise ArchiveError('The wheel RECORD is too large')
            rows = _record_rows(bundle.read(records[0]).decode('utf-8'))
            for info in infos:
                budget.member()
                if info.is_dir():
                    continue
                relative = _clean(info.filename)
                if relative.parts[0].endswith('.data'):
                    if len(relative.parts) < 3 or relative.parts[1] not in ('purelib', 'platlib'):
                        raise ArchiveError(f'Wheel member needs an install step setup does not perform: {relative}')
                    placed = PurePosixPath(*relative.parts[2:])
                else:
                    placed = relative
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ArchiveError(f'Links are not allowed in wheels: {relative}')
                if info.flag_bits & 0x1:
                    raise ArchiveError(f'Encrypted archive members are not allowed: {relative}')
                if mode and not (stat.S_ISREG(mode) or stat.S_IFMT(mode) == 0):
                    raise ArchiveError(f'Archive member type is not allowed: {relative}')
                if info.filename == record_name:
                    continue
                expected = rows.get(info.filename)
                if expected is None or not expected[0].startswith('sha256=') or expected[1] != str(info.file_size):
                    raise ArchiveError(f'Wheel member is not recorded with its SHA-256 and size: {relative}')
                target = _inside(site, placed)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    raise ArchiveError(f'Wheel member would replace an existing file: {placed}')
                digest = hashlib.sha256()
                with bundle.open(info) as source:
                    if _copy(source, target, info.file_size, budget, digest) != info.file_size:
                        raise ArchiveError(f'Archive member is truncated: {relative}')
                actual = 'sha256=' + base64.urlsafe_b64encode(digest.digest()).rstrip(b'=').decode()
                if actual != expected[0]:
                    raise ArchiveError(f'Wheel member does not match its RECORD: {relative}')
                _mark_executable(target, mode, keep_exec)
                installed.append(placed.as_posix())
            missing = set(rows) - {i.filename for i in infos}
            if missing:
                raise ArchiveError('The wheel RECORD lists files the wheel does not contain')
            # What an installer adds: INSTALLER, and the rewritten RECORD that lists it.
            installer_path = _inside(site, PurePosixPath(dist_info, 'INSTALLER'))
            if installer_path.exists() or installer_path.is_symlink():
                raise ArchiveError(f'Wheel member would replace an existing file: {dist_info}/INSTALLER')
            data = (installer + '\n').encode()
            installer_path.write_bytes(data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
            record_path = _inside(site, PurePosixPath(*_clean(record_name).parts))
            text = bundle.read(record_name).decode('utf-8')
            text = (text if text.endswith('\n') or not text else text + '\n') + f'{dist_info}/INSTALLER,sha256={digest},{len(data)}\n'
            if record_path.exists() or record_path.is_symlink():
                raise ArchiveError(f'Wheel member would replace an existing file: {record_name}')
            record_path.write_text(text, encoding='utf-8')
            installed += [f'{dist_info}/INSTALLER', f'{dist_info}/RECORD']
    except (zipfile.BadZipFile, EOFError, UnicodeDecodeError) as error:
        raise ArchiveError(f'The wheel could not be unpacked: {type(error).__name__}') from error
    except OSError as error:
        raise ArchiveError(f'The wheel could not be unpacked: {type(error).__name__}') from error
    return installed
