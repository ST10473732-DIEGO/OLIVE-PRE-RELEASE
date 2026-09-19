"""Bounded source excerpts retaining definition ownership and adjacent conditions."""
import re

MAX_EXCERPT = 2400


def scoped_passages(page):
    sections = page.metadata.get('sections', [])
    for section in sections:
        start, end = section['start'], section['end']
        if section['kind'] != 'definition':
            continue
        # Do not cross into the next API's documentation to fill a context window.
        clipped = min(end, start + MAX_EXCERPT)
        if clipped < end:
            boundary = page.text.rfind('\n\n', start + 200, clipped)
            if boundary > start:
                clipped = boundary
        yield start, clipped, section['scope'], 'definition', clipped < end
    for match in re.finditer(r'\S[\s\S]*?(?=\n\n|\Z)', page.text):
        if any(s['kind'] == 'definition' and s['start'] <= match.start() < s['end'] for s in sections):
            continue
        section = next((s for s in sections if s['start'] <= match.start() < s['end']), {})
        end = min(match.end(), match.start() + MAX_EXCERPT)
        yield match.start(), end, section.get('scope', ''), 'paragraph', end < match.end()
