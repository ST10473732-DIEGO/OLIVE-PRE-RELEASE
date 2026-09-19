"""Downloaded bytes stay inert until an explicit read/export/import decision."""

import hashlib
import io
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote
import uuid
from ..storage.json_store import JsonStore
from .http import fetch
from .models import PageObservation, timestamp
from .extraction import content_hash, MAX_TEXT
from .urls import normalize_url


class DownloadQuarantine:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.store = JsonStore(self.directory / "manifest.json")

    def list(self):
        return self.store.read({"schema_version": 1, "downloads": []})["downloads"]

    def get(self, download_id):
        normalized = str(uuid.UUID(download_id))
        return next(value for value in self.list() if value["id"] == normalized)

    def bytes(self, download_id):
        value = self.get(download_id)
        data = (self.directory / (value["id"] + ".bin")).read_bytes()
        if hashlib.sha256(data).hexdigest() != value["content_hash"]:
            raise ValueError("Quarantined file changed since download")
        return value, data

    async def download(self, url, approved=False):
        if not approved:
            raise PermissionError("Downloads require an explicit user decision")
        if sum(item["size"] for item in self.list()) >= 100 * 1024 * 1024:
            raise ValueError("Quarantine is full; remove an existing download first")
        url, kind, data = await fetch(normalize_url(url), max_bytes=10 * 1024 * 1024, accept="*/*")
        if sum(item["size"] for item in self.list()) + len(data) > 100 * 1024 * 1024:
            raise ValueError("Download exceeds remaining quarantine capacity")
        filename = (
            re.sub(r"[^\w. -]", "_", unquote(urlsplit(url).path.rsplit("/", 1)[-1]))[:160] or "download"
        )
        return self.store_download(url, filename, kind, data, approved=True)

    def store_download(self, url, filename, kind, data, approved=False):
        """Shared inert ingestion for explicitly approved browser downloads."""
        if not approved:
            raise PermissionError("Downloads require an explicit user decision")
        if len(data) > 10 * 1024 * 1024 or sum(item["size"] for item in self.list()) + len(data) > 100 * 1024 * 1024:
            raise ValueError("Download exceeds quarantine capacity")
        filename = re.sub(r"[^\w. -]", "_", filename)[:160] or "download"
        record = {
            "id": str(uuid.uuid4()),
            "url": url,
            "filename": filename,
            "content_type": kind,
            "size": len(data),
            "content_hash": hashlib.sha256(data).hexdigest(),
            "downloaded_at": timestamp(),
            "state": "quarantined",
            "trust_label": "untrusted_download",
        }
        (self.directory / (record["id"] + ".bin")).write_bytes(data)
        self.store.write({"schema_version": 1, "downloads": [*self.list(), record]})
        return record

    def read_document(self, download_id):
        value, data = self.bytes(download_id)
        kind = value["content_type"].split(";", 1)[0].lower()
        if kind in {"text/plain", "text/markdown"}:
            text = data.decode("utf-8", errors="replace")[:MAX_TEXT]
        elif kind == "application/pdf" and data.startswith(b"%PDF-"):
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ValueError("Encrypted downloads require a separate authorized reader")
            pieces, length = [], 0
            for index, page in enumerate(reader.pages):
                if index >= 100 or length >= MAX_TEXT:
                    break
                piece = f"# Page {index + 1}\n" + (page.extract_text() or "")[: MAX_TEXT - length]
                pieces.append(piece)
                length += len(piece)
            text = "\n\n".join(pieces)[:MAX_TEXT]
        else:
            raise ValueError(
                "Executable, script, archive and unsupported downloads remain quarantined; no execution is offered"
            )
        return PageObservation(
            value["url"],
            value["filename"],
            text,
            content_hash(text),
            content_type=kind,
            metadata={"download_id": download_id, "quarantine_state": "quarantined"},
        )

    def export(self, download_id, destination, approved=False):
        if not approved:
            raise PermissionError("Saving a downloaded file requires explicit approval")
        _, data = self.bytes(download_id)
        # Exclusive creation avoids overwriting user data even after a file-dialog race.
        with Path(destination).open("xb") as stream:
            stream.write(data)
        return str(destination)

    def remove(self, download_id):
        record = self.get(download_id)
        (self.directory / (record["id"] + ".bin")).unlink(missing_ok=True)
        self.store.write(
            {"schema_version": 1, "downloads": [v for v in self.list() if v["id"] != record["id"]]}
        )
