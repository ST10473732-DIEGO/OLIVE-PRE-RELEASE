"""Small request inspector for a running local project's owned endpoint.

Requests are only sent to the origin a RunSession announced ("Now listening
on"); nothing else on the network is reachable through this path. Certificate
validation is never disabled: an untrusted development certificate is reported
as an error with guidance, not bypassed.
"""
from __future__ import annotations

import asyncio
import http.client
import json
import ssl
import time
from urllib.parse import urlparse

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
MAX_BODY = 512 * 1024
MAX_RESPONSE = 1024 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def owned_origin(session) -> str:
    url = getattr(session, "local_url", None)
    if not url:
        raise ValueError("The run has not announced a local listening address yet")
    parsed = urlparse(url)
    if parsed.hostname not in LOCAL_HOSTS or not parsed.port:
        raise ValueError("Only owned local endpoints can be inspected")
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"


def _perform(origin: str, method: str, path: str, headers: dict[str, str], body: str, timeout: float) -> dict:
    parsed = urlparse(origin)
    started = time.perf_counter()
    if parsed.scheme == "https":
        context = ssl.create_default_context()
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=timeout, context=context)
    else:
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    try:
        connection.request(method, path, body=body.encode("utf-8") if body else None, headers=headers)
        response = connection.getresponse()
        raw = response.read(MAX_RESPONSE + 1)
        truncated = len(raw) > MAX_RESPONSE
        text = raw[:MAX_RESPONSE].decode("utf-8", "replace")
        return {"ok": True, "status": response.status, "reason": response.reason, "headers": dict(response.getheaders()),
                "body": text, "truncated": truncated, "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "url": origin + path, "method": method}
    finally:
        connection.close()


async def inspect(session, method: str, path: str, headers: dict[str, str] | None, body: str, timeout: float = 20.0) -> dict:
    method = str(method).upper()
    if method not in METHODS:
        raise ValueError("Unsupported HTTP method")
    if not path.startswith("/") or len(path) > 4000 or any(c in path for c in "\r\n\0"):
        raise ValueError("Path must be an absolute local path")
    if len(body) > MAX_BODY:
        raise ValueError("Request body exceeds the supported size")
    clean_headers = {}
    for key, value in (headers or {}).items():
        key, value = str(key)[:100], str(value)[:4000]
        if not key.replace("-", "").isalnum() or "\n" in value or "\r" in value:
            raise ValueError("Invalid header")
        if key.casefold() in {"host", "content-length", "transfer-encoding"}:
            continue
        clean_headers[key] = value
    clean_headers.setdefault("User-Agent", "OLIVE-Studio-inspector")
    if body and "Content-Type" not in {k.title() for k in clean_headers}:
        clean_headers["Content-Type"] = "application/json"
    origin = owned_origin(session)
    try:
        return await asyncio.to_thread(_perform, origin, method, path, clean_headers, body, max(1.0, min(60.0, float(timeout))))
    except ssl.SSLCertVerificationError as error:
        return {"ok": False, "status": 0, "error": "The local HTTPS certificate is not trusted. Run `dotnet dev-certs https --trust` "
                                                  "yourself (OLIVE does not change certificate stores), or use the HTTP profile.",
                "detail": str(error)[:300], "url": origin + path, "method": method, "duration_ms": 0}
    except (OSError, http.client.HTTPException) as error:
        return {"ok": False, "status": 0, "error": f"{type(error).__name__}: {error}"[:300], "url": origin + path, "method": method, "duration_ms": 0}


def summarize(result: dict) -> dict:
    """Bounded record kept in the inspector history (no bodies larger than 64 KB)."""
    kept = dict(result)
    if isinstance(kept.get("body"), str) and len(kept["body"]) > 65536:
        kept["body"] = kept["body"][:65536]
        kept["truncated"] = True
    try:
        json.dumps(kept)
    except (TypeError, ValueError):
        kept = {"ok": False, "error": "Unserialisable response"}
    return kept
