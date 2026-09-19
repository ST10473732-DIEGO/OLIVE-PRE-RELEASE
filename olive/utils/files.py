from __future__ import annotations

from pathlib import Path
import hashlib
import mimetypes
import shutil

from ..config import ATTACHMENTS_DIR


def stable_file_id(path: Path) -> str:
    stat = path.stat()
    digest = hashlib.sha256(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()
    return digest[:24]


def cache_file(path: Path, file_id: str, cache_dir: Path | None = None) -> Path:
    suffix = path.suffix.lower()
    directory = cache_dir if cache_dir is not None else ATTACHMENTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{file_id}{suffix}"
    if not target.exists() or target.stat().st_size != path.stat().st_size:
        shutil.copy2(path, target)
    return target


def mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def content_hash(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()
