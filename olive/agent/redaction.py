"""Conservative credential redaction before tool output reaches a model or a log.

This is not a complete secret detector. It removes well-known credential
shapes; anything it misses is still treated as untrusted data, never authority.
"""
import re

_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b[MN][A-Za-z\d]{23,25}\.[\w-]{6}\.[\w-]{27,}\b"),  # Discord-style bot token
)
_ASSIGNMENT = re.compile(r"(?i)\b([A-Z0-9_]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|credential)[A-Z0-9_]*)"
                         r"(\s*[:=]\s*)(\"[^\"\n]*\"|'[^'\n]*'|[^\s,;]+)")
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^/\s@]+)@")


def redact(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    for pattern in _PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    text = _ASSIGNMENT.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
    return _URL_CREDENTIALS.sub(lambda m: m.group(1) + "[REDACTED]@", text)
