"""Literal visible navigation; never JavaScript, credentials or privileged URLs."""
from urllib.parse import urlsplit


def validated_url(value):
    if not isinstance(value,str) or not 1 <= len(value) <= 2000 or any(c.isspace() or ord(c)<32 for c in value):
        raise ValueError('Provide one explicit http(s) URL')
    parsed=urlsplit(value)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:
        raise PermissionError('Only a credential-free http(s) page can be opened here')
    return value
