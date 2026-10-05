"""Verified, resumable downloads of pinned setup artefacts.

Same contract as scripts/install_approved_media.py (bounded HTTP ranges, exact
Content-Range, SHA-256 before use), packaged as a service:

* HTTPS only, to hosts the manifest names, including every redirect hop. Loopback
  http:// is accepted only when the caller passes allow_loopback_http (test fixtures).
* TLS verification is always on; there is no switch to turn it off.
* The expected size is a hard ceiling: a server that sends more is rejected.
* Partial bytes live in <user data>/temp/downloads/<sha256>.part and are resumed
  with a Range request. A checksum mismatch deletes them; nothing unverified is
  ever returned.
* Cancellation is cooperative (a threading.Event checked between chunks) and keeps
  the partial file so a retry resumes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import threading
import time
from typing import Callable
from urllib.parse import urljoin

import httpx

from .runtime_manifest import url_allowed

RANGE = 32 * 1024 * 1024
CHUNK = 1024 * 1024
MAX_REDIRECTS = 5
RETRIES = 4
CONTENT_RANGE = re.compile(r'^bytes (\d+)-(\d+)/(\d+)$')


class DownloadError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Artefact:
    url: str
    sha256: str
    size: int
    hosts: tuple[str, ...]
    name: str = ''


def _client():
    # verify=True is httpx's default and is stated here so a reader never wonders.
    return httpx.Client(follow_redirects=False, verify=True, timeout=httpx.Timeout(60, connect=20),
                        headers={'User-Agent': 'OLIVE-setup/1.0', 'Accept-Encoding': 'identity'})


def _hash_file(path: Path, cancel: threading.Event | None = None) -> 'hashlib._Hash':
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(CHUNK * 8):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            digest.update(block)
    return digest


class Downloader:
    def __init__(self, directory: Path, *, allow_loopback_http=False, client_factory: Callable = _client,
                 sleep: Callable[[float], None] = time.sleep):
        self.directory = Path(directory)
        self.allow_loopback_http = allow_loopback_http
        self.client_factory = client_factory
        self.sleep = sleep

    def paths(self, artefact: Artefact) -> tuple[Path, Path]:
        return self.directory / f'{artefact.sha256}.part', self.directory / artefact.sha256

    def partial_bytes(self, artefact: Artefact) -> int:
        part, final = self.paths(artefact)
        for path in (final, part):
            try:
                if not path.is_symlink():
                    return path.stat().st_size
            except OSError:
                continue
        return 0

    def discard(self, artefact: Artefact) -> None:
        for path in self.paths(artefact):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def fetch(self, artefact: Artefact, *, cancel: threading.Event | None = None,
              progress: Callable[[int, int], None] | None = None) -> Path:
        """Return a local file whose bytes have the expected size and SHA-256."""
        if not url_allowed(artefact.url, artefact.hosts, self.allow_loopback_http):
            raise DownloadError('source_not_allowed', 'The download source is not an allowed HTTPS address')
        if not re.fullmatch(r'[0-9a-f]{64}', artefact.sha256) or artefact.size <= 0:
            raise DownloadError('unpinned', 'The artefact has no pinned checksum and size')
        cancel = cancel or threading.Event()
        progress = progress or (lambda done, total: None)
        self.directory.mkdir(parents=True, exist_ok=True)
        part, final = self.paths(artefact)
        for path in (part, final):
            if path.is_symlink():
                raise DownloadError('unsafe_partial', 'A download file is a link; it was not used')
        if final.exists():
            # Re-verify a completed download rather than trusting its name.
            if final.stat().st_size == artefact.size and _hash_file(final, cancel).hexdigest() == artefact.sha256:
                progress(artefact.size, artefact.size)
                return final
            final.unlink()
        offset = part.stat().st_size if part.exists() else 0
        if offset > artefact.size:
            part.unlink()
            offset = 0
        digest = _hash_file(part, cancel) if offset else hashlib.sha256()
        progress(offset, artefact.size)
        with self.client_factory() as client:
            while offset < artefact.size:
                if cancel.is_set():
                    raise Cancelled()
                end = min(offset + RANGE, artefact.size) - 1
                offset = self._range(client, artefact, part, digest, offset, end, cancel, progress)
        if digest.hexdigest() != artefact.sha256:
            part.unlink(missing_ok=True)
            raise DownloadError('checksum_mismatch', 'The downloaded file does not match its pinned SHA-256; it was deleted')
        os.replace(part, final)
        return final

    def _range(self, client, artefact, part, digest, offset, end, cancel, progress) -> int:
        failure: Exception | None = None
        for attempt in range(RETRIES):
            if cancel.is_set():
                raise Cancelled()
            try:
                return self._request(client, artefact, part, digest, offset, end, cancel, progress)
            except DownloadError:
                raise
            except (httpx.TransportError, httpx.RemoteProtocolError, _Retry) as error:
                failure = error
                # Bytes written before a dropped connection stay valid: continue from there.
                offset = part.stat().st_size if part.exists() else offset
                if offset > end:
                    return offset
                self.sleep(min(2 ** attempt, 8))
        raise DownloadError('network', f'The download failed after {RETRIES} attempts: {type(failure).__name__}')

    def _request(self, client, artefact, part, digest, offset, end, cancel, progress) -> int:
        url = artefact.url
        headers = {'Range': f'bytes={offset}-{end}'}
        for _ in range(MAX_REDIRECTS + 1):
            with client.stream('GET', url, headers=headers) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get('location', '')
                    url = urljoin(url, location)
                    if not url_allowed(url, artefact.hosts, self.allow_loopback_http):
                        raise DownloadError('redirect_not_allowed', 'The server redirected to a host this artefact does not allow')
                    continue
                if response.status_code >= 500 or response.status_code == 429:
                    raise _Retry()
                if response.status_code == 206:
                    match = CONTENT_RANGE.match(response.headers.get('content-range', ''))
                    if not match or (int(match[1]), int(match[2]), int(match[3])) != (offset, end, artefact.size):
                        raise DownloadError('bad_range', 'The server did not honour the verified download range')
                    limit = end - offset + 1
                elif response.status_code == 200 and offset == 0:
                    # A server without range support: accept only the exact full body.
                    length = response.headers.get('content-length')
                    if length is not None and int(length) != artefact.size:
                        raise DownloadError('size_mismatch', 'The server reported a different size than the pinned one')
                    limit = artefact.size
                else:
                    raise DownloadError('http_error', f'The download server answered HTTP {response.status_code}')
                written = 0
                with part.open('ab') as stream:
                    for block in response.iter_bytes():  # As received, so a dropped connection keeps its bytes.
                        if written + len(block) > limit:
                            raise DownloadError('oversize', 'The server sent more bytes than the pinned size')
                        stream.write(block)
                        digest.update(block)
                        written += len(block)
                        progress(offset + written, artefact.size)
                        if cancel.is_set():
                            stream.flush()
                            raise Cancelled()
                if written != limit:
                    raise _Retry()
                return offset + written
        raise DownloadError('too_many_redirects', 'Too many redirects')


class _Retry(Exception):
    pass
