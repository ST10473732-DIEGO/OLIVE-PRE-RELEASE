"""Conservative web identities and public-network policy; no model decisions."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}


def normalize_url(value, base=None):
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value) or "\\" in value:
        raise ValueError("Invalid web URL")
    value = urljoin(base, value) if base else value
    parts = urlsplit(value.strip())
    if (
        parts.scheme.lower() not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("Only HTTP(S) URLs without credentials are allowed")
    host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    if host.endswith((".onion", ".local", ".localhost")) or host == "localhost":
        raise ValueError("Research only supports public web destinations")
    port = parts.port
    if port not in {None, 80, 443}:
        raise ValueError("Research supports standard web ports only")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host:
            raise ValueError("Research does not access intranet hostnames") from None
    else:
        if not address.is_global:
            raise ValueError("Research does not access private or reserved addresses")
        if address.version == 6:
            host = f"[{host}]"
    netloc = host + (f":{port}" if port and port != (443 if parts.scheme.lower() == "https" else 80) else "")
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING]
    )
    # Preserve slash and meaningful query distinctions; a canonical tag is only metadata.
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", query, ""))


async def validate_public_url(value, resolver=None):
    url = normalize_url(value)
    parts = urlsplit(url)
    if resolver is None:
        resolver = asyncio.get_running_loop().getaddrinfo
    records = await resolver(
        parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM
    )
    if not records or any(not ipaddress.ip_address(record[4][0]).is_global for record in records):
        raise ValueError("Research destination resolved to a private or reserved address")
    return url
