"""Natural desktop navigation requests and follow-ups, parsed deterministically.

Examples: "Open Firefox and go to GitHub", "Go back", "Open my GitHub tab",
"Go to the RaceDay server", "Open general", "Open Dolphin and go to Downloads",
"Switch back to Firefox", "No, the other Firefox window", "2".

Only the literal user message supplies new text (URLs, queries, names, message
bodies). The bounded conversational context may only supply the application
and the previously *verified* server/channel/window it already used. A model is
never consulted here and nothing here authorizes input: the result is a
TaskScope that the ordinary task authority issues as a fresh finite grant.
Unrecognized text returns None so the ordinary grammar/interpreter handles it;
recognized but unresolved requests raise NEEDS_USER_CLARIFICATION.
"""
from dataclasses import dataclass, replace
import re

from .task_authority import TaskScope
from .window_targets import WindowHint, parse_choice

BROWSERS = {'firefox': 'Firefox', 'mozilla firefox': 'Firefox', 'chromium': 'Chromium', 'chrome': 'Google Chrome',
            'google chrome': 'Google Chrome', 'brave': 'Brave', 'vivaldi': 'Vivaldi'}
MESSENGERS = {'discord': 'Discord'}
FILE_MANAGERS = {'dolphin': 'Dolphin', 'file manager': 'Dolphin', 'files': 'Dolphin'}
TERMINALS = {'konsole': 'Konsole', 'terminal': 'Konsole'}
ALIASES = {'settings': 'System Settings', 'system settings': 'System Settings', 'kate': 'Kate',
           'vs code': 'Visual Studio Code', 'vscode': 'Visual Studio Code', 'visual studio code': 'Visual Studio Code'}
# A reviewed, fixed map of well-known destinations. Anything else becomes a web
# search instead of an invented URL.
KNOWN_SITES = {'github': 'https://github.com/', 'gitlab': 'https://gitlab.com/', 'youtube': 'https://www.youtube.com/',
               'google': 'https://www.google.com/', 'wikipedia': 'https://www.wikipedia.org/',
               'reddit': 'https://www.reddit.com/', 'stack overflow': 'https://stackoverflow.com/',
               'stackoverflow': 'https://stackoverflow.com/', 'duckduckgo': 'https://duckduckgo.com/',
               'gmail': 'https://mail.google.com/', 'discord web': 'https://discord.com/app'}
FOLDERS = {'downloads': 'xdg:DOWNLOAD', 'documents': 'xdg:DOCUMENTS', 'pictures': 'xdg:PICTURES',
           'music': 'xdg:MUSIC', 'videos': 'xdg:VIDEOS', 'desktop': 'xdg:DESKTOP', 'home': '~',
           'home folder': '~'}
BROWSER_OPS = {'go back': 'back', 'back': 'back', 'go forward': 'forward', 'forward': 'forward',
               'reload': 'reload', 'refresh': 'reload', 'reload the page': 'reload', 'refresh the page': 'reload',
               'reload this page': 'reload', 'refresh this page': 'reload', 'open a new tab': 'new_tab',
               'open new tab': 'new_tab', 'new tab': 'new_tab', 'close this tab': 'close_tab',
               'close the tab': 'close_tab', 'close tab': 'close_tab', 'reopen the closed tab': 'reopen_tab',
               'reopen closed tab': 'reopen_tab', 'reopen the last closed tab': 'reopen_tab',
               'undo close tab': 'reopen_tab', 'restore the closed tab': 'reopen_tab'}
CONTINUE = re.compile(r"(?:ok(?:ay)?[, ]+)?(?:continue|carry on|go on|resume|proceed|done|i'?m done|"
                      r"i(?:'ve| have) (?:signed|logged) in|signed in|logged in|finished)(?: now)?(?:,? please)?", re.I)
DOMAIN = re.compile(r'(?:https?://)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}(?::\d{1,5})?(?:[/?#]\S*)?',
                    re.I)
LOOPBACK = re.compile(r'(?:https?://)?(?:localhost|127\.0\.0\.1)(?::\d{1,5})?(?:[/?#]\S*)?', re.I)
# Words that could smuggle a second effect into a navigation target/query/place.
TARGET_RISK = re.compile(r'\b(?:then|send|draft|delete|without|do not|never)\b|don[\'’]t|[;\n]', re.I)
QUERY_RISK = re.compile(r'\b(?:then|but|without|do not|never)\b|don[\'’]t|[;\n]', re.I)
PLACE_RISK = re.compile(r'[,;\n]|\b(?:then|and|but|send|type|write|draft|without|do not|never)\b|don[\'’]t', re.I)


@dataclass(frozen=True)
class Parsed:
    scope: TaskScope
    kind: str = 'task'              # task | choice | correction | continue
    hint: WindowHint = WindowHint()
    status: str = ''                # compact first status line for Chat


def _clean(text):
    text = re.sub(r'[“”]', '"', re.sub(r"[‘’]", "'", (text or '').strip()))
    text = re.sub(r'^(?:hey olive[,:]?\s+|olive[,:]\s+)', '', text, flags=re.I)
    text = re.sub(r'^(?:please|can you|could you|would you)\s+', '', text, flags=re.I)
    text = re.sub(r'\s+please$', '', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).rstrip('.!?').strip()


def app_name(word):
    key = (word or '').strip().casefold()
    for table in (BROWSERS, MESSENGERS, FILE_MANAGERS, TERMINALS, ALIASES):
        if key in table:
            return table[key]
    return ''


def kind_of(application):
    key = (application or '').casefold()
    if key in {v.casefold() for v in BROWSERS.values()}:
        return 'browser'
    if key in {v.casefold() for v in MESSENGERS.values()}:
        return 'messaging'
    if key == 'dolphin':
        return 'file_manager'
    if key == 'konsole':
        return 'terminal'
    return ''


def url_for(target):
    """Explicit URL/domain -> validated URL; known site -> reviewed URL; else None."""
    from .browser_url import validated_url
    value = target.strip().strip('<>"\'')
    lowered = value.casefold()
    if re.match(r'(?:javascript|data|file|about|chrome|resource|view-source|moz-extension):', lowered):
        raise PermissionError('URL_REFUSED: only ordinary http(s) pages can be opened; nothing was opened')
    if lowered in KNOWN_SITES:
        return KNOWN_SITES[lowered]
    if re.match(r'https?://', lowered):
        return validated_url(value)  # Credentials, spaces and odd schemes are refused there.
    if DOMAIN.fullmatch(value) or LOOPBACK.fullmatch(value):
        url = value if re.match(r'https?://', lowered) else ('http://' if LOOPBACK.fullmatch(value) else 'https://') + value
        return validated_url(url)
    return None


def _browser_target(app, target, mode=''):
    """'github.com' / 'GitHub' -> visit; any other words -> a web search for them."""
    target = target.strip()
    if not target or len(target) > 300 or TARGET_RISK.search(target):
        raise ValueError('NEEDS_USER_CLARIFICATION: tell me the exact page or search; nothing was opened')
    url = url_for(target)
    if url:
        return Parsed(TaskScope(app, 'visit', url, mode=mode), status=f'Opening {target} in {app}…')
    return Parsed(TaskScope(app, 'search', target, mode=mode or 'new_tab'), status=f'Searching for {target}…')


def _folder(target):
    key = target.strip().casefold()
    key = re.sub(r'^(?:my|the)\s+', '', key)
    key = re.sub(r'\s+(?:folder|directory)$', '', key)
    if key in FOLDERS:
        return FOLDERS[key]
    raw = re.sub(r'\s+(?:folder|directory)$', '', target.strip(), flags=re.I).strip('"\'')
    if raw.startswith(('~/', '/')) or raw == '~':
        if '\x00' in raw or '\n' in raw or len(raw) > 1000:
            raise ValueError('Provide one folder path')
        return raw
    return None


def _messaging_target(app, place, context, explicit_server=''):
    """Discord navigation from a follow-up: server, channel or both."""
    place = place.strip()
    if PLACE_RISK.search(place) or PLACE_RISK.search(explicit_server or ''):
        raise ValueError('Clarify the exact destination; navigation never types or sends a message')
    server = explicit_server.strip()
    # Only a lowercase kind word is dropped: "the RaceDay server" -> RaceDay, but a
    # server literally named "D SERVER" keeps its name.
    match = re.fullmatch(r"(?:the|my)\s+(.+?)\s+server", place) or re.fullmatch(r"(.+?)\s+server", place)
    if match and not server:
        name = match.group(1).strip()
        if name.casefold() in {'my', 'the', 'a', ''}:
            raise ValueError('Which server? Name it exactly; nothing was opened or typed.')
        return Parsed(TaskScope(app, 'go', '', '', '', name), status=f'Opening {name}…')
    if re.fullmatch(r'my server|the server|our server', place, re.I):
        raise ValueError('Which server? Name it exactly; nothing was opened or typed.')
    channel = re.fullmatch(r"(?:the\s+)?#?([\w-]{1,80})\s+channel", place, re.I)
    name = '#' + channel.group(1) if channel else place
    if server and re.match(r'(?:the|my)\s', server, re.I):
        server = re.sub(r'\s+server$', '', server.split(' ', 1)[1]).strip()
        if not server or server.casefold() == 'server':
            raise ValueError('Which server? Name it exactly; nothing was opened or typed.')
    elif server:
        server = re.sub(r'\s+server$', '', server).strip()
    if name.startswith(('#', '@')) or channel:
        if not server and not name.startswith('@'):
            server = context.server if context and context.kind == 'messaging' else ''
        from .task_authority import split_handle
        destination, handle = split_handle(name)
        return Parsed(TaskScope(app, 'go', '', destination, '', server, handle=handle),
                      status=f'Opening {destination}' + (f' in {server}' if server else '') + '…')
    # A bare name: with a verified server in context it is a channel there;
    # otherwise it is a server. Either way the result is verified exactly.
    if server or context and context.kind == 'messaging' and context.server:
        server = server or context.server
        return Parsed(TaskScope(app, 'go', '', '#' + name.lstrip('#'), '', server),
                      status=f'Opening #{name.lstrip("#")} in {server}…')
    return Parsed(TaskScope(app, 'go', '', '', '', name), status=f'Opening {name}…')


def contextual_request(text, context=None, default_browser=None):
    """Parse one natural desktop request. Returns Parsed, None, or raises clarification."""
    default_browser = default_browser or getattr(context, 'default_browser', '') or 'Firefox'
    if not isinstance(text, str) or not 1 <= len(text) <= 1000 or '\n' in text.strip():
        return None
    raw = text.strip()
    text = _clean(raw)
    lowered = text.casefold()
    ctx = context if context is not None and (context.fresh() or context.pending_now()) else None
    current = ctx.application if ctx and ctx.fresh() else ''
    kind = ctx.kind if ctx and ctx.fresh() else ''

    # 1. Replies to OLIVE's own pending question.
    pending = ctx.pending_now() if ctx else None
    if pending and pending['kind'] == 'window_choice':
        chosen = parse_choice(text, pending['candidates'])
        if chosen is not None:
            return Parsed(pending['scope'], 'choice', WindowHint(choice_id=chosen.window_id),
                          status='Using the window you chose…')
    if pending and pending['kind'] == 'user_action' and CONTINUE.fullmatch(text):
        return Parsed(pending['scope'], 'continue', WindowHint(bound_id=pending.get('window_id', ''),
                      bound_pid=pending.get('pid', 0)), status='Checking the page again…')

    # 2. Corrections of the current target.
    if ctx and ctx.last_scope is not None and ctx.fresh():
        other = re.fullmatch(r"(?:no[,.]?\s+)?(?:i meant\s+|use\s+)?the other(?:\s+([\w ]{1,40}?))?\s*(?:one|window)?", text, re.I)
        if other and (not other.group(1) or other.group(1).strip().casefold() in
                      {current.casefold(), current.casefold() + ' window', 'window', ''}):
            if ctx.window is None:
                raise ValueError('NEEDS_USER_CLARIFICATION: which window do you mean? Nothing was done.')
            return Parsed(ctx.last_scope, 'correction', WindowHint(exclude_id=ctx.window.window_id),
                          status='Switching to the other window…')
        meant = re.fullmatch(r"(?:no[,.]?\s+)?i meant (?:the |my )?(.+?) server", text, re.I)
        if meant and kind == 'messaging':
            scope = ctx.last_scope
            if scope.effect != 'go':
                raise ValueError('NEEDS_USER_CLARIFICATION: nothing was changed. Repeat the full message request '
                                 'with the right server so I can verify it again.')
            return Parsed(replace(scope, server=meant.group(1).strip()), 'correction',
                          status=f'Opening {meant.group(1).strip()} instead…')

    # 3. Application-level requests.
    match = re.fullmatch(r'(?:switch|go|change) back to ([\w .+-]{1,60})|(?:switch|change) to ([\w .+-]{1,60})|'
                         r'(?:focus|bring up|show me) ([\w .+-]{1,60})', text, re.I)
    if match:
        target = next(g for g in match.groups() if g)
        name = app_name(target) or (current if target.casefold() == current.casefold() else '')
        if name and not re.search(r'\btab\b', target, re.I):
            return Parsed(TaskScope(name, 'focus'), status=f'Switching to {name}…')
    match = re.fullmatch(r'close (?:this|the|that) window', text, re.I)
    if match:
        if not current or not ctx.window:
            return None  # No desktop window in this conversation (it may mean OLIVE itself).
        return Parsed(TaskScope(current, 'close_window'), hint=WindowHint(bound_id=ctx.window.window_id,
                      bound_pid=ctx.window.pid), status=f'Closing the {current} window…')
    match = re.fullmatch(r'(?:open|launch|start) (?:the )?(settings|system settings|konsole|terminal|dolphin|file manager)',
                         text, re.I)
    if match:
        name = app_name(match.group(1))
        return Parsed(TaskScope(name, 'open'), status=f'Opening {name}…')

    # 4. Open APP and go to/search TARGET (browser, messaging, file manager).
    match = re.fullmatch(r'open (?:a )?new tab and (?:go to|open|visit|navigate to|search for|search) (.+)', text, re.I)
    if match:
        application = current if kind == 'browser' else default_browser
        target = match.group(1)
        if re.match(r'open (?:a )?new tab and search', text, re.I):
            return Parsed(TaskScope(application, 'search', _query(target), mode='new_tab'),
                          status=f'Searching for {_query(target)}…')
        return _browser_target(application, target, 'new_tab')
    match = re.fullmatch(r'(?:open|launch|start) ([\w .+-]{1,40}?),? and (?:then )?(go to|navigate to|open|visit|'
                         r'search for|search|switch to) (.+)', text, re.I)
    if match:
        name, verb, target = match.group(1), match.group(2).casefold(), match.group(3)
        application = app_name(name)
        if kind_of(application) == 'browser':
            if verb.startswith('search'):
                return Parsed(TaskScope(application, 'search', _query(target), mode='new_tab'),
                              status=f'Searching for {_query(target)}…')
            tab = re.fullmatch(r'(?:my|the) (.+?) tab', target, re.I)
            if tab:
                return Parsed(TaskScope(application, 'tab', 'select', tab.group(1).strip()), hint=WindowHint(title=tab.group(1).strip()), status=f'Selecting the {tab.group(1).strip()} tab…')
            return _browser_target(application, target)
        if kind_of(application) == 'file_manager':
            path = _folder(target)
            if path:
                return Parsed(TaskScope(application, 'folder', path=path), status=f'Opening {target}…')
        if kind_of(application) == 'messaging' and not verb.startswith('search'):
            place = re.fullmatch(r'(.+?) (?:in|on) ((?:the |my )?[\w .\'+-]{1,100}?)', target, re.I)
            if place and not place.group(1).casefold().endswith(' server'):
                return _messaging_target(application, place.group(1), ctx, place.group(2))
            return _messaging_target(application, target, ctx)

    match = re.fullmatch(r'(?:open|go to|visit) ([\w .]{1,40})', text, re.I)
    if match and match.group(1).strip().casefold() in KNOWN_SITES and not current:
        return _browser_target(default_browser, match.group(1))

    # 5. Folders (Dolphin): "Open Downloads", "Go to ~/Projects", "Open my Documents folder".
    match = re.fullmatch(r'(?:open|go to|show|show me|navigate to) (.+?)(?: in (dolphin|the file manager|files))?', text, re.I)
    if match:
        path = _folder(match.group(1))
        explicit = bool(match.group(2)) or kind == 'file_manager'
        folder_words = re.search(r'\b(?:folder|directory)\b', match.group(1), re.I)
        if path and (explicit or folder_words or path.startswith(('~', '/')) or
                     match.group(1).strip().casefold() in FOLDERS and kind != 'browser'):
            return Parsed(TaskScope('Dolphin', 'folder', path=path), status=f'Opening {match.group(1).strip()}…')

    # 6. Browser follow-ups and explicit-browser forms.
    in_app = re.fullmatch(r'(.+?) in ([\w .+-]{1,40})', text, re.I)
    explicit_app = app_name(in_app.group(2)) if in_app else ''
    if explicit_app and kind_of(explicit_app) == 'browser':
        body, application = in_app.group(1), explicit_app
    elif kind == 'browser':
        body, application = text, current
    else:
        body, application = text, ''
    op = BROWSER_OPS.get(body.casefold())
    if op:
        if not application:
            if op in {'back', 'forward'} and kind == 'file_manager':
                return Parsed(TaskScope(current, 'browse', op), status='Going ' + op + '…')
            if op in {'new_tab', 'open a new tab'} and body.casefold() != 'new tab':
                return Parsed(TaskScope(default_browser, 'browse', op), status='Opening a new tab…')
            return None  # Without a desktop context this is ordinary conversation.
        return Parsed(TaskScope(application, 'browse', op), status={'back': 'Going back…', 'forward': 'Going forward…',
                      'reload': 'Reloading…', 'new_tab': 'Opening a new tab…', 'close_tab': 'Closing the tab…',
                      'reopen_tab': 'Reopening the closed tab…'}[op])
    match = re.fullmatch(r'(?:switch to|open|go to|select|show) (?:my |the )?(.+?) tab', body, re.I)
    if match and (application or kind != 'messaging'):
        application = application or default_browser
        title = match.group(1).strip()
        if title.casefold() in {'next', 'previous', 'new', 'other'}:
            return None
        return Parsed(TaskScope(application, 'tab', 'select', title), hint=WindowHint(title=title),
                      status=f'Selecting the {title} tab…')
    match = re.fullmatch(r'(next|previous) tab', body, re.I)
    if match and application:
        return Parsed(TaskScope(application, 'tab', match.group(1).lower()), status='Changing tabs…')
    match = re.fullmatch(r'(?:search|search the web|look up|google) for (.+)|search (.+)', body, re.I)
    if match and (application or explicit_app):
        query = _query(match.group(1) or match.group(2))
        return Parsed(TaskScope(application, 'search', query, mode='new_tab'), status=f'Searching for {query}…')
    match = re.fullmatch(r'find (.+?)(?: on (?:this|the) page)?', body, re.I)
    if match and application:
        needle = _query(match.group(1))
        return Parsed(TaskScope(application, 'find', needle), status=f'Finding “{needle}” on the page…')
    match = re.fullmatch(r'(go to|navigate to|visit|open) (.+)', body, re.I)
    if match and application and (match.group(1).casefold() != 'open' or url_for_safe(match.group(2)) or
                                  match.group(2).strip().casefold() in KNOWN_SITES):
        # "Open X" in a browser context is a page only for a URL or a known site;
        # otherwise it stays an application request ("Open Gimp").
        return _browser_target(application, match.group(2))
    match = re.fullmatch(r'(?:go to|navigate to|visit|open) (.+)', body, re.I)
    if match and not application and kind != 'messaging':
        target = match.group(1).strip()
        if url_for_safe(target):
            return _browser_target(default_browser, target)

    # 7. Messaging follow-ups (Discord) with a verified context or an explicit app.
    messaging = kind == 'messaging'
    msg = re.fullmatch(r'(send|type|draft)\s*:\s*(.+)', raw.strip(), re.I | re.S)
    if msg and messaging:
        verb, content = msg.group(1).lower(), msg.group(2).strip()
        if len(content) >= 2 and content[0] == content[-1] and content[0] in '"\'':
            content = content[1:-1]
        if not content or '\n' in content or '\x00' in content:
            raise ValueError('Provide the exact one-line message text; nothing was typed.')
        if not ctx.destination:
            raise ValueError('NEEDS_USER_CLARIFICATION: which channel or person? Nothing was typed or sent.')
        effect = 'send' if verb == 'send' else 'draft'
        from .task_authority import split_handle
        destination, handle = split_handle(ctx.destination)
        return Parsed(TaskScope(current, effect, content, destination, '', ctx.server, handle=handle),
                      status=('Sending' if effect == 'send' else 'Typing') + f' in {ctx.destination}…')
    match = re.fullmatch(r'(?:go to|open|switch to|navigate to|take me to) (.+?)(?: in discord)?', text, re.I)
    if match and (messaging or re.search(r'\bin discord$', text, re.I)):
        target = match.group(1)
        place = re.fullmatch(r'(.+?) (?:in|on) ((?:the |my )?[\w .\'+-]{1,100}?)', target, re.I)
        if place and not place.group(1).casefold().endswith(' server'):
            return _messaging_target('Discord', place.group(1), ctx, place.group(2))
        return _messaging_target('Discord', target, ctx)

    # 8. Plain "Open APP." (punctuation-tolerant); the runtime reuses a bound window.
    match = re.fullmatch(r'(?:open|launch|start) ([\w.+-]+(?: [\w.+-]+){0,3})', text, re.I)
    if match and not re.search(r'\b(?:and|then|in|on|with|for|to)\b', match.group(1), re.I):
        name = app_name(match.group(1)) or match.group(1).strip()
        return Parsed(TaskScope(name, 'open'), status=f'Opening {name}…')

    # 9. Scrolling the bound window.
    match = re.fullmatch(r'scroll (up|down)(?: (?:the )?(page|channel list|server list|list|messages))?', text, re.I)
    if match:
        if not current:
            return None
        return Parsed(TaskScope(current, 'scroll', match.group(1).lower(), (match.group(2) or '').lower()), hint=WindowHint(bound_id=ctx.window.window_id if ctx.window else '',
                                 bound_pid=ctx.window.pid if ctx.window else 0), status='Scrolling…')
    return None


def url_for_safe(target):
    try:
        return url_for(target) if DOMAIN.fullmatch(target.strip()) or LOOPBACK.fullmatch(target.strip()) else None
    except (ValueError, PermissionError):
        return None


def _query(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        value = value[1:-1]
    if not value or len(value) > 300 or QUERY_RISK.search(value) or any(ord(c) < 32 for c in value):
        raise ValueError('The search text includes a possible task constraint; clarify the exact query before input')
    return value
