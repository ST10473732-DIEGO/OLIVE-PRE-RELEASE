"""Layered messaging target model: account, workspace, destination, composer, draft.

Each layer is resolved separately from independent evidence and carries its own
state. The user's literal request supplies authority; visual/semantic evidence
only confirms that the currently visible client matches it. Adapter conventions
(composer placeholder, quick switcher, submit key) are declared per client and
never inferred from a model answer. Nothing here performs input.
"""
from dataclasses import asdict, dataclass, field
import re

from .visual_ocr import MIN_CONFIDENCE, confident, normalize

VERIFIED, UNVERIFIED, AMBIGUOUS, NOT_VISIBLE, MISMATCH = 'VERIFIED', 'UNVERIFIED', 'AMBIGUOUS', 'NOT_VISIBLE', 'MISMATCH'


@dataclass(frozen=True)
class MessagingAdapter:
    key: str
    applications: tuple          # installed desktop ids / names (casefold)
    web_hosts: tuple = ()        # official web origin hosts for the browser route
    placeholder: str = r'^message\s*([#@])\s*(.+?)$'
    switcher_key: str = 'ctrl+k'
    switcher_prompt: str = 'where would you like to go'
    submit: str = 'enter'
    submit_provenance: str = ''
    prompts: dict = field(default_factory=dict)


REGION_PROMPTS = {
    'composer': 'Click inside the message input box at the bottom of the current conversation.',
    'header': 'Click the title of the current conversation or channel at the top of the window.',
    'server': 'Click the server or workspace name shown at the top of the channel list.',
    'account': "Click the current user's own name in the user panel at the bottom left.",
    'switcher': 'Click the search input of the open quick switcher dialog.',
    'result': 'Click the search result named {label}.',
}
ADAPTERS = (
    MessagingAdapter('discord', ('discord', 'com.discordapp.discord', 'discord canary', 'discord ptb'),
                     ('discord.com',), submit_provenance='Client convention (Enter sends, Shift+Enter newline); '
                     'not verified against a real send in this milestone', prompts=REGION_PROMPTS),
    MessagingAdapter('visual-messenger-fixture', ('visual messenger', 'olive-visual-messenger-fixture'),
                     submit_provenance='Owned fixture: Enter sends; verified by its owned sent log',
                     prompts=REGION_PROMPTS),
)


def adapter_for(application, document_host=''):
    name = (application or '').casefold().removesuffix('.desktop')
    host = (document_host or '').casefold()
    for adapter in ADAPTERS:
        if name in adapter.applications:
            return adapter
        if host and any(host == h or host.endswith('.' + h) for h in adapter.web_hosts):
            return adapter
    return None


@dataclass
class Layer:
    state: str = UNVERIFIED
    value: str = ''
    box: tuple | None = None
    evidence: str = ''


@dataclass
class MessagingContext:
    application: str
    adapter: str
    content: str
    account: Layer = field(default_factory=Layer)
    workspace: Layer = field(default_factory=Layer)
    destination: Layer = field(default_factory=Layer)
    composer: Layer = field(default_factory=Layer)
    draft: str | None = None          # '' means a verified empty composer
    submit: str = ''
    delivery: str = 'NOT_ATTEMPTED'   # SENT_UI | PENDING_UI | UNCERTAIN | NOT_ATTEMPTED

    def summary(self):
        # Reported evidence: states and the user's own bound names, never page text.
        value = asdict(self)
        value.pop('content', None)
        value['draft'] = 'empty' if self.draft == '' else 'present' if self.draft else 'unknown'
        for key in ('account', 'workspace', 'destination', 'composer'):
            value[key].pop('box', None)
        return value

    def blocker(self, scope, sending):
        """First unmet layer as an exact category, or '' when ready."""
        if self.destination.state != VERIFIED:
            return 'DESTINATION_UNVERIFIED' if self.destination.state != AMBIGUOUS else 'TARGET_AMBIGUOUS'
        if scope.server and self.workspace.state != VERIFIED:
            return 'DESTINATION_UNVERIFIED'
        if self.composer.state != VERIFIED:
            return 'COMPOSER_UNVERIFIED'
        if self.account.state != VERIFIED and (scope.account or sending):
            return 'ACCOUNT_UNVERIFIED'
        return ''


def bare(name):
    return normalize(str(name).lstrip('#@ '))


def composer_state(lines, adapter):
    """(kind, sigil, name_or_text) from OCR lines of the composer band."""
    rows = [l for l in confident(lines) if len(l['text'].strip()) >= 2]
    placeholders = []
    for line in rows:
        match = re.match(adapter.placeholder, normalize(line['text']))
        if match:
            placeholders.append((match.group(1), match.group(2).strip(), line))
    if len(placeholders) == 1:
        sigil, name, line = placeholders[0]
        return 'empty', sigil, name, line
    if len(placeholders) > 1:
        return 'ambiguous', '', '', None
    text = [l for l in rows if not re.fullmatch(r'[\W\d_]{1,3}', l['text'])]
    if len(text) == 1:
        return 'draft', '', text[0]['text'].strip(), text[0]
    # Several unrelated rows mean this band is not a composer (for example a
    # contacts/home view); never report that as a verified composer or draft.
    return 'unknown', '', '', None


def resolve_destination(scope, composer):
    kind, sigil, name, line = composer
    wanted = bare(scope.destination)
    if kind == 'ambiguous':
        return Layer(AMBIGUOUS, evidence='several composer placeholders')
    if kind != 'empty':
        return Layer(UNVERIFIED, evidence='composer placeholder not visible (' + kind + ')')
    if bare(name) != wanted:
        return Layer(MISMATCH, bare(name), line['box'], 'composer placeholder names another destination')
    if scope.destination.startswith('#') and sigil != '#' or scope.destination.startswith('@') and sigil != '@':
        return Layer(MISMATCH, bare(name), line['box'], 'destination kind differs')
    return Layer(VERIFIED, name, line['box'], 'composer placeholder ' + sigil + name)


def resolve_exact(lines, expected, what, anchor=None):
    """One confident OCR line equal to the user's literal name (sigils ignored)."""
    wanted = bare(expected)
    rows = confident(lines)
    matches = [l for l in rows if bare(l['text']) == wanted]
    if len(matches) == 1:
        return Layer(VERIFIED, expected, matches[0]['box'], what + ' text matches')
    if len(matches) > 1:
        return Layer(AMBIGUOUS, evidence='duplicate ' + what + ' labels')
    observed = [l for l in rows if len(bare(l['text'])) >= 2]
    if anchor is not None and observed:
        # The label at the proposed region names something else.
        nearest = min(observed, key=lambda l: abs((l['box'][1] + l['box'][3]) / 2 - anchor[1]) +
                      max(0, l['box'][0] - anchor[0], anchor[0] - l['box'][2]))
        return Layer(MISMATCH, bare(nearest['text']), nearest['box'], 'another ' + what + ' is shown')
    if len(observed) == 1:
        return Layer(MISMATCH, bare(observed[0]['text']), observed[0]['box'], 'another ' + what + ' is shown')
    return Layer(NOT_VISIBLE, evidence=what + ' not read')


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def observed_account(lines, composer_box=None):
    rows = [l for l in confident(lines) if len(bare(l['text'])) >= 2]
    if composer_box:
        # Text inside the verified composer (its placeholder or draft, possibly
        # clipped by the account band) is never account identity.
        rows = [l for l in rows if not overlaps(l['box'], composer_box)]
    if len(rows) == 1:
        return Layer(VERIFIED, rows[0]['text'].strip(), rows[0]['box'], 'single visible account name')
    return Layer(AMBIGUOUS if rows else NOT_VISIBLE, evidence='account panel not uniquely readable')


def rows(lines, tolerance=8, minimum=None):
    """Group OCR lines into visual rows by vertical overlap."""
    grouped = []
    kept = confident(lines) if minimum is None else [l for l in lines if l['confidence'] >= minimum]
    for line in sorted(kept, key=lambda l: l['box'][1]):
        middle = (line['box'][1] + line['box'][3]) / 2
        for row in grouped:
            if abs(row['middle'] - middle) <= tolerance:
                row['lines'].append(line)
                break
        else:
            grouped.append({'middle': middle, 'lines': [line]})
    result = []
    for row in grouped:
        row['lines'].sort(key=lambda l: l['box'][0])
        boxes = [l['box'] for l in row['lines']]
        result.append({'text': ' '.join(l['text'] for l in row['lines']), 'lines': row['lines'],
                       'box': (min(b[0] for b in boxes), min(b[1] for b in boxes),
                               max(b[2] for b in boxes), max(b[3] for b in boxes))})
    return result


def switcher_candidates(entries, destination, server=''):
    """Result rows whose first confident label is exactly the destination.

    Each row carries the state of its right-aligned server label: 'confirmed'
    (exactly the requested server), 'unread' (no confidently read label there) or
    'other' (a confidently read label that is not the requested server). Words
    between name and server (for example a category such as "TEXT CHANNELS")
    identify neither and are ignored; glyph-only tokens (icons, scrollbars) carry
    nothing. Leading icon glyphs are skipped only when they carry no word
    characters or were not read confidently. Entries may be OCR words or whole
    lines; each is split into tokens that keep its confidence and box.
    """
    wanted, workspace = bare(destination).split(), bare(server).split() if server else []
    tokens = [{'text': part, 'confidence': entry['confidence'], 'box': entry['box']}
              for entry in entries for part in str(entry['text']).split()]
    found = []
    for row in rows(tokens, minimum=0):
        words = list(row['lines'])
        # Skip only sigils and short unreadable icon glyphs, never a word that
        # could be part of another channel's name.
        while words and (not bare(words[0]['text']) or
                         len(bare(words[0]['text'])) <= 2 and words[0]['confidence'] < MIN_CONFIDENCE):
            words.pop(0)
        name = words[:len(wanted)]
        if [bare(w['text']) for w in name] != wanted or any(w['confidence'] < MIN_CONFIDENCE for w in name):
            continue
        rest = [w for w in words[len(wanted):] if bare(w['text'])]
        tail = rest[-len(workspace):] if workspace and len(rest) >= len(workspace) else []
        if not workspace or not rest or rest[-1]['confidence'] < MIN_CONFIDENCE:
            row['server'] = 'unread'
        elif [bare(w['text']) for w in tail] == workspace and all(w['confidence'] >= MIN_CONFIDENCE for w in tail):
            row['server'] = 'confirmed'
        else:
            row['server'] = 'other'
        found.append(row)
    return found


def switcher_matches(entries, destination, server=''):
    """Rows exactly naming the destination and, when requested, confirming the server."""
    return [row for row in switcher_candidates(entries, destination, server)
            if not server or row['server'] == 'confirmed']
