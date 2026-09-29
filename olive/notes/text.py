"""Plain-text rules shared by every Notes path. Canonical line ending is LF."""
import re

UNTITLED = 'Untitled Note'
MAX_DISPLAY_TITLE = 80


def normalize(text):
    """LF only, no NUL. Applied to every inserted string, never to stored history."""
    if type(text) is not str:
        raise ValueError('Note text must be text')
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\x00', '')


def display_title(title, body):
    """Explicit title wins; otherwise the first non-empty line; otherwise Untitled."""
    title = (title or '').strip()
    if title:
        return title[:200]
    for line in (body or '').split('\n'):
        line = line.strip()
        if line:
            return line[:MAX_DISPLAY_TITLE]
    return UNTITLED


def preview(title, body, limit=160):
    lines = [line.strip() for line in (body or '').split('\n') if line.strip()]
    if not (title or '').strip() and lines:
        lines = lines[1:]  # The first line is already shown as the title.
    return re.sub(r'\s+', ' ', ' '.join(lines))[:limit]


def diff(old, new):
    """Minimal single replacement (index, delete_count, insert) in code points."""
    if old == new:
        return None
    limit = min(len(old), len(new))
    start = 0
    while start < limit and old[start] == new[start]:
        start += 1
    end = 0
    while end < limit - start and old[len(old) - 1 - end] == new[len(new) - 1 - end]:
        end += 1
    return start, len(old) - start - end, new[start:len(new) - end]


def byte_size(text):
    return len(text.encode('utf-8'))
