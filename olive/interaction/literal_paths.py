"""Literal absolute paths in a person's own request, including paths that contain spaces.

The earlier extraction stopped every path at the first space, so a request naming
"/Volumes/Data Drive/report.txt" (or "~/My Documents/a.txt") referred to
"/Volumes/Data". A path written without spaces is still read exactly as before.
A path is only extended across a space when the filesystem confirms the longer
reading: the longer path exists, or (for something about to be created, moved or
copied to) its parent folder exists and is deeper than the shorter reading's.
Connecting words ("to", "and", "then", ...) never become part of a new name.

These helpers only find text. Authority stays with the owner policy and broker,
which still bind each granted capability to the exact resolved path.
"""
from __future__ import annotations

import re
from pathlib import Path

_START = re.compile(r'(?<![\w/])(?:~/|/)')
_TOKEN = re.compile(r'[^\s\'";,\x00]+')
_GAP = re.compile(r'[ \t]+')
_CONNECTORS = frozenset(
    'to into onto in inside from and then as with containing saying called named or but if so at for of on by'.split())
_MAX_WORDS = 16


def _exists(candidate: str) -> bool:
    try:
        return Path(candidate).expanduser().exists()
    except (OSError, RuntimeError, ValueError):
        return False


def _parent_depth(candidate: str) -> int:
    try:
        parent = Path(candidate).expanduser().parent
        return len(parent.parts) if parent.is_dir() else -1
    except (OSError, RuntimeError, ValueError):
        return -1


def _quoted_ranges(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in re.finditer(r'([\'"])(?:(?!\1).)*?\1', text, flags=re.S)]


def path_spans(text: str, *, skip_quoted: bool = False) -> list[tuple[int, int, str]]:
    """(start, end, path) for each literal absolute path, in order."""
    quoted = _quoted_ranges(text) if skip_quoted else []
    spans: list[tuple[int, int, str]] = []
    position = 0
    while match := _START.search(text, position):
        start = match.start()
        if any(a <= start < b for a, b in quoted):
            position = start + 1
            continue
        first = _TOKEN.match(text, start)
        if not first:
            position = start + 1
            continue
        ends = [first.end()]
        cursor = first.end()
        while len(ends) < _MAX_WORDS:
            gap = _GAP.match(text, cursor)
            if not gap or _START.match(text, gap.end()) or any(a <= gap.end() < b for a, b in quoted):
                break
            word = _TOKEN.match(text, gap.end())
            if not word:
                break
            ends.append(word.end())
            cursor = word.end()
        candidates = [text[start:end] for end in ends]
        # The reading the filesystem confirms most deeply wins: an existing path counts
        # its own depth, a new name its existing parent's. Ties keep the existing,
        # then the shorter, reading, so "/a/x.txt please" stays "/a/x.txt". Connecting
        # words may appear in existing names but never in a new one.
        chosen, best = candidates[0], (-1, False)
        for index, candidate in enumerate(candidates):
            plain = candidate[:-1] if candidate.endswith('.') and not _exists(candidate) else candidate
            if _exists(plain):
                score = (len(Path(plain).expanduser().parts), True)
            else:
                # Only the new last name is unconfirmed; folders above it exist as typed.
                if index and any(word.casefold().strip('.') in _CONNECTORS for word in Path(plain).name.split()):
                    continue
                score = (_parent_depth(plain), False)
            if score > best:
                chosen, best = candidate, score
        if chosen is not candidates[0] and chosen.endswith('.') and not _exists(chosen):
            chosen = chosen[:-1]  # Sentence punctuation after an extended path.
        spans.append((start, start + len(chosen), chosen))
        position = start + len(chosen)
    return spans


def literal_paths(text: str, *, skip_quoted: bool = False) -> list[str]:
    return [path for _, _, path in path_spans(text, skip_quoted=skip_quoted)]


def mask_paths(text: str, *, skip_quoted: bool = False, marker: str = ' [path] ') -> tuple[str, list[str]]:
    """Replace each literal path with `marker` (it may contain {index}); returns (masked, paths)."""
    pieces, paths, last = [], [], 0
    for start, end, path in path_spans(text, skip_quoted=skip_quoted):
        pieces.append(text[last:start])
        pieces.append(marker.format(index=len(paths)))
        paths.append(path)
        last = end
    pieces.append(text[last:])
    return ''.join(pieces), paths
