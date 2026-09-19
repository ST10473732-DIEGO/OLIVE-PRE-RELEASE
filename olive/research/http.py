"""Bounded public HTTP transport with DNS-address pinning and normal TLS checks."""

import asyncio
import http.client
import ipaddress
import socket
from urllib.parse import urlsplit
from .urls import normalize_url


def public_addresses(host, port):
    records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Research destination is not public")
    return addresses


def fetch_public(
    url, timeout=20, max_bytes=2 * 1024 * 1024, accept="text/html,text/plain,application/xhtml+xml"
):
    visited = set()
    for _ in range(6):
        url = normalize_url(url)
        if url in visited:
            raise ValueError("Redirect loop")
        visited.add(url)
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        address = public_addresses(parts.hostname, port)[0]
        connection_type = (
            http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_type(parts.hostname, port, timeout=timeout)
        # HTTPSConnection retains the original hostname for certificate verification/SNI.
        connection._create_connection = lambda destination, timeout, source_address=None: (
            socket.create_connection((address, port), timeout, source_address)
        )
        try:
            connection.request(
                "GET",
                (parts.path or "/") + ("?" + parts.query if parts.query else ""),
                headers={"User-Agent": "OLIVE-Research/3.3", "Accept": accept, "Accept-Encoding": "identity"},
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Redirect missing destination")
                url = normalize_url(location, url)
                continue
            if response.status >= 400:
                raise OSError(f"HTTP {response.status}: source unavailable or access restricted")
            length = response.getheader("Content-Length")
            if length and int(length) > max_bytes:
                raise ValueError("Response exceeds size limit")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("Response exceeds size limit")
            return url, response.getheader("Content-Type", "application/octet-stream"), body
        finally:
            connection.close()
    raise ValueError("Too many redirects")


async def fetch(
    url, timeout=20, max_bytes=2 * 1024 * 1024, accept="text/html,text/plain,application/xhtml+xml"
):
    return await asyncio.wait_for(
        asyncio.to_thread(fetch_public, url, timeout, max_bytes, accept), timeout + 1
    )
