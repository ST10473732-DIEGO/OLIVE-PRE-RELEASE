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
    # The fixed label may lose up to two leading characters to a caret or glyph
    # merge; the destination after it must still read exactly.
    placeholder: str = r'^(?:m|.{0,2})essage\s*([#@])\s*(.+?)$'
    switcher_key: str = 'ctrl+k'
    switcher_prompt: str = 'where would you like to go'
    submit: str = 'enter'
    submit_provenance: str = ''
    prompts: dict = field(default_factory=dict)
    # Icons the client always draws after the server name (read by OCR as a letter).
    header_decorations: tuple = ()
    # Fixed layout areas (fractions of the window: left, top, right, bottom) where
    # each label is read directly by OCR, instead of asking a vision model where it
    # is. Exact text is still required inside the area; roles without an area use
    # the model proposal. Empty for clients whose layout is not declared.
    regions: dict = field(default_factory=dict)
    # The account panel shows the user's name above a status line.
    account_first_line: bool = False
    # Enter in the switcher opens the highlighted result (verified from pixels).
    switcher_enter_opens: bool = False
    # Switcher rows show the server label right-aligned (in the right half of the row).
    switcher_label_right: bool = False
    # Fixed-width panels left of the composer (logical px), excluded from its area.
    composer_left_logical: int = 0


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
                     'not verified against a real send in this milestone', prompts=REGION_PROMPTS,
                     header_decorations=('v', 'x'),  # The server menu's chevron / close icon.
                     # The user panel (account) is read beside the verified composer.
                     regions={'composer': (0.0, 0.91, 1.0, 1.0), 'server': (0.0, 0.0, 0.34, 0.1),
                              'header': (0.12, 0.0, 0.85, 0.1), 'switcher': (0.25, 0.2, 0.75, 0.5)},
                     account_first_line=True, switcher_enter_opens=True, switcher_label_right=True,
                     composer_left_logical=320),  # Server rail + channel list / user panel.
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


def segments(lines):
    """Rejoin OCR fragments of one text run: touching pieces on a row are one word.

    Tesseract sometimes splits a clean line into abutting pieces ('M', 'essag',
    'e #gen-chat'). Pieces within a quarter of the text height (at least 2 px) are
    joined without a space, up to about half the height with a space; larger gaps
    keep separate runs (for example a user panel beside the composer). Two readings
    of the same glyphs (overlapping boxes) keep the more confident one. Confidence
    is the lowest of the joined pieces.
    """
    joined = []
    for row in rows(lines):
        run = None
        for line in row['lines']:
            height = line['box'][3] - line['box'][1]
            gap = line['box'][0] - run['box'][2] if run else None
            if run and gap < 0 and -gap > (line['box'][2] - line['box'][0]) / 2:
                # The same glyphs read twice: a single piece keeps the more confident reading.
                if run['pieces'] == 1 and line['confidence'] > run['confidence']:
                    run = joined[-1] = dict(line, pieces=1)
                continue
            if run and gap <= max(3, height * .6):
                glue = '' if gap <= max(2, height / 4) else ' '
                run = joined[-1] = {'text': run['text'] + glue + line['text'], 'pieces': run['pieces'] + 1,
                                    'confidence': min(run['confidence'], line['confidence']),
                                    'box': (run['box'][0], min(run['box'][1], line['box'][1]), line['box'][2],
                                            max(run['box'][3], line['box'][3]))}
            else:
                run = dict(line, pieces=1)
                joined.append(run)
    return joined


def composer_state(lines, adapter, expected=''):
    """(kind, sigil, name_or_text) from OCR lines of the composer band."""
    rows = [l for l in segments(lines) if len(l['text'].strip()) >= 2]
    placeholders = []
    for line in rows:
        match = re.match(adapter.placeholder, normalize(line['text']))
        if match:
            placeholders.append((match.group(1), match.group(2).strip(), line))
    if not placeholders:
        placeholders = label_pairs(lines, expected)
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


def label_pairs(lines, expected=''):
    """Placeholders found token by token: a word ending in 'essage' (the fixed label,
    whose first letters a caret may hide) directly followed on the same line by a
    '#name' / '@name' token. Independent of how OCR fragments were joined.

    OCR may drop a thin hyphen and split the name ('#gen' 'chat'): adjacent pieces
    are rejoined only when that reproduces exactly the `expected` destination.
    """
    words = [w for w in lines if w['text'].strip()]
    found = []
    for label in words:
        # The label is fixed text and only marks the placeholder: a lower bar.
        if label['confidence'] < 40 or not normalize(label['text']).endswith('essage'):
            continue
        height = label['box'][3] - label['box'][1]
        same_line = lambda w: abs((w['box'][1] + w['box'][3]) - (label['box'][1] + label['box'][3])) / 2 <= max(4, height / 2)
        pieces = sorted((w for w in words if w is not label and w['confidence'] >= MIN_CONFIDENCE and same_line(w)
                         and w['box'][0] >= label['box'][2]), key=lambda w: w['box'][0])
        if not pieces or pieces[0]['box'][0] - label['box'][2] > max(6, 1.2 * height):
            continue
        run = [pieces[0]]
        for piece in pieces[1:]:
            if piece['box'][0] - run[-1]['box'][2] > max(4, .9 * height) or len(run) == 4:
                break
            run.append(piece)
        texts = [normalize(w['text']) for w in run]
        count = 1
        if expected:
            wanted = normalize(expected)
            count = next((k for k in range(1, len(run) + 1) if '-'.join(texts[:k]) == wanted), 1)
        text = '-'.join(texts[:count])
        match = re.fullmatch(r'([#@])(\S+)', text)
        if match:
            used = run[:count]
            found.append((match.group(1), match.group(2),
                          dict(run[0], text=text, box=(label['box'][0], min(label['box'][1], run[0]['box'][1]),
                                                        used[-1]['box'][2], max(label['box'][3], used[-1]['box'][3])))))
    return found


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


def resolve_exact(lines, expected, what, anchor=None, decorations=()):
    """One confident OCR line equal to the user's literal name (sigils ignored).

    `decorations` are icon glyphs the client always draws after this label; one
    trailing decoration token is ignored, nothing else is.
    """
    wanted = bare(expected)
    rows = confident(lines)
    def names(text):
        text = bare(text)
        parts = text.split()
        return {text, ' '.join(parts[:-1])} if len(parts) > 1 and parts[-1] in decorations else {text}
    matches = [l for l in rows if wanted in names(l['text'])]
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


def observed_account(lines, composer_box=None, first_line=False):
    rows = [l for l in segments(lines) if len(bare(l['text'])) >= 2]
    if composer_box:
        # Text inside the verified composer (its placeholder or draft, possibly
        # clipped by the account band) is never account identity.
        rows = [l for l in rows if not overlaps(l['box'], composer_box)]
    if first_line:
        # Icon glyphs read as punctuation plus one letter are not a name.
        rows = [l for l in rows if len(re.findall(r'[^\W_]', l['text'])) >= 2]
    if first_line and rows:
        # Declared panel structure: the name is the top-left run; a status line
        # follows below and panel buttons sit to its right.
        top = min(l['box'][1] for l in rows)
        name = min((l for l in rows if l['box'][1] - top <= 6), key=lambda l: l['box'][0])
        return Layer(VERIFIED, name['text'].strip(), name['box'], 'account name line of the user panel')
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


def switcher_candidates(entries, destination, server='', label_from=None, handle=''):
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
        # A token much taller than the row's text is a scrollbar or divider, never a
        # label. The text height comes from confidently read words (small-caps
        # categories and tiny labels must not shrink it).
        texts = [w['box'][3] - w['box'][1] for w in row['lines']
                 if w['confidence'] >= MIN_CONFIDENCE and len(re.findall(r'[^\W_]', w['text'])) >= 2]
        typical = max(texts) if texts else max(w['box'][3] - w['box'][1] for w in row['lines'])
        words = [w for w in row['lines'] if w['box'][3] - w['box'][1] <= 1.8 * typical]
        # Skip only sigils and short unreadable icon glyphs, never a word that
        # could be part of another channel's name.
        while words and (not bare(words[0]['text']) or
                         len(bare(words[0]['text'])) <= 2 and words[0]['confidence'] < MIN_CONFIDENCE):
            words.pop(0)
        name = words[:len(wanted)]
        if [bare(w['text']) for w in name] != wanted or any(w['confidence'] < MIN_CONFIDENCE for w in name):
            continue
        if handle:
            # A person's username follows the shared display name on the same row;
            # it must read exactly, or the row is someone else.
            wanted_handle = normalize(handle).lstrip('@').split()
            after = [w for w in words[len(wanted):] if bare(w['text']) and w['confidence'] >= MIN_CONFIDENCE]
            if [normalize(w['text']).lstrip('@') for w in after[:len(wanted_handle)]] != wanted_handle:
                continue
        rest = [w for w in words[len(wanted):] if bare(w['text'])]
        if label_from is not None:
            # The server label is right-aligned; words nearer the name (a category
            # such as "CHAT") can never stand in for it.
            rest = [w for w in rest if w['box'][0] >= label_from]
        tail = rest[-len(workspace):] if workspace and len(rest) >= len(workspace) else []
        readable = [w for w in rest if w['confidence'] >= MIN_CONFIDENCE and len(re.findall(r'[^\W_]', w['text'])) >= 2]
        if workspace and [bare(w['text']) for w in tail] == workspace and all(w['confidence'] >= MIN_CONFIDENCE for w in tail):
            row['server'] = 'confirmed'
        elif workspace and readable:
            row['server'] = 'other'   # A readable, different label.
        else:
            row['server'] = 'unread'  # Absent, or only glyph-sized misreadings.
        found.append(row)
    return found


def switcher_matches(entries, destination, server=''):
    """Rows exactly naming the destination and, when requested, confirming the server."""
    return [row for row in switcher_candidates(entries, destination, server)
            if not server or row['server'] == 'confirmed']


# Glyphs OCR cannot tell apart in small UI text. Only used to recognise text OLIVE
# typed itself (exact key strokes); destination, server and account names are
# always compared exactly.
LOOKALIKE = str.maketrans({'i': 'l', '1': 'l', '|': 'l', '0': 'o'})


def lookalike(text):
    return normalize(text).translate(LOOKALIKE)


def typed_key(text):
    """Text OLIVE typed itself, as OCR can confirm it: look-alike glyphs equal and
    whitespace ignored (small UI text leaves word gaps as narrow as letter gaps)."""
    return lookalike(text).replace(' ', '')


def typed_exactly(lines, content, adapter):
    """The requested text is visible exactly once in the composer area and no placeholder is shown."""
    if composer_state(lines, adapter)[0] == 'empty':
        return False
    return sum(typed_key(l['text']) == typed_key(content) for l in segments(lines)) == 1


def exact_segment(lines, content):
    """The one run reading exactly the requested text, or None."""
    runs = [l for l in segments(lines) if typed_key(l['text']) == typed_key(content)]
    return runs[0] if len(runs) == 1 else None


def echo_rows(words, content, account=''):
    """Rows showing the sent text: the row ends with exactly the content (look-alike
    glyphs equal, spacing ignored) and either holds nothing else (a continued
    message) or shows the sender's account name before it (the first message of a
    group: time, name, badge, text)."""
    target = typed_key(content)
    name = typed_key(account) if account else ''
    found = []
    for row in rows(words):
        tokens = [token for w in row['lines'] for token in lookalike(w['text']).split()]
        if not target or not ''.join(tokens).endswith(target):
            continue
        # The content must start at a token boundary.
        count, length = 0, 0
        while count < len(tokens) and length < len(target):
            count += 1
            length += len(tokens[-count])
        if length != len(target):
            continue
        prefix = tokens[:len(tokens) - count]
        # The sender's name may be read truncated at its end (coloured names); a
        # leading fragment of at least four characters still names this account.
        if not prefix or name and (name in ''.join(prefix) or
                                   any(len(t) >= 4 and name.startswith(t) for t in prefix)):
            found.append(row)
    return found
