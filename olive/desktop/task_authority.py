"""Finite authority derived only from the literal local user request.

Literal fast paths and validated semantic interpretations share one authority.
Unresolved effects never receive a permissive fallback.
Observations and action JSON cannot create or extend a grant.
"""
from dataclasses import dataclass, replace
import hashlib
import json
import re
import threading
import time
import uuid


@dataclass(frozen=True)
class TaskScope:
    application: str
    effect: str
    content: str = ''
    destination: str = ''
    account: str = ''
    server: str = ''
    path: str = ''
    predicate: str = ''  # Literal user domain predicate for a result-derived location.
    handle: str = ''     # A person's username beside a shared display name (for example '4818').


def interpreted_scope(request, steps):
    """Validate a semantic proposal against original local-user bytes.

    A planner can recognize paraphrases, but cannot supply new text, applications,
    recipients, side effects or approval fields. Observations never enter here.
    """
    if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
        raise ValueError('One bounded desktop effect is required')
    app, effect, content = '', 'open', ''
    for step in steps:
        intent, entities = step.get('intent'), step.get('entities', {})
        if step.get('references') or not isinstance(entities, dict):
            raise ValueError('Resolve the explicit application and content first')
        if intent in {'application.launch', 'application.activate'}:
            if set(entities) != {'application'}:
                raise ValueError('Unexpected application scope fields')
        elif intent == 'application.search':
            expected = {'query'} if app and 'application' not in entities else {'application', 'query'}
            if set(entities) != expected or effect != 'open':
                raise ValueError('Unexpected or repeated search effect')
            effect, content = 'search', entities['query']
        elif intent == 'application.control':
            if set(entities) != {'application', 'action', 'target'} or entities['action'] not in {'click', 'invoke'} or effect != 'open':
                raise ValueError('This interpreted control needs a resolved ordinary click')
            effect, content = 'click', entities['target']
        else:
            raise ValueError('This interpreted desktop effect is not implemented')
        # A compound request can name the app in its launch step and omit it
        # from the following search. Inherit only this proposal's verified app,
        # never a prior conversation, observation, or model-supplied reference.
        candidate = entities.get('application', app)
        if not isinstance(candidate, str) or not candidate or candidate.casefold() not in request.casefold() or app and app.casefold() != candidate.casefold():
            raise ValueError('The proposed application is outside the original request')
        app = candidate
    if not isinstance(content, str) or content and content not in request:
        raise ValueError('The proposed text was not present in the original request')
    if re.search(r'\b(?:without|do not|never|delete|purchase|pay|password|terminal|shell)\b|don[\'’]t', request, re.I):
        raise ValueError('Additional constraints need resolution before input')
    return TaskScope(app, effect, content)


def literal_path(path):
    """One destination path, never a trailing clause captured by a greedy pattern."""
    return bool(path) and not re.search(r'[\n\x00,;]|\s(?:but|and|then|without|unless|except|do not|never)\b|don[\'’]t',
                                        path, re.I)


def split_handle(destination):
    """'@diego (4818)' or '@diego with username 4818' -> ('@diego', '4818')."""
    match = (re.fullmatch(r'(.+?)\s*\(\s*@?([\w.#-]{1,40})\s*\)', destination) or
             re.fullmatch(r'(.+?)\s+with username\s+@?([\w.#-]{1,40})', destination, re.I))
    if match:
        return match.group(1).strip(), match.group(2)
    if '(' in destination or ')' in destination:
        raise ValueError('Give the person as @name (username); no message was sent')
    return destination, ''


MESSAGING_APPS = r'(discord|slack|telegram|whatsapp|signal|element|skype|(?:microsoft )?teams)'
APP_NAMES = {'discord': 'Discord', 'slack': 'Slack', 'telegram': 'Telegram', 'whatsapp': 'WhatsApp', 'signal': 'Signal',
             'element': 'Element', 'skype': 'Skype', 'teams': 'Teams', 'microsoft teams': 'Microsoft Teams'}
_STOP = r'(?:in|on|via|using|through|saying|says|with|to|that)'
_NAME = r'([@#]?(?:(?!' + _STOP + r'\b)[\w.\'-]+)(?: (?!' + _STOP + r'\b)[\w.\'-]+){0,3}(?: ?\(@?[\w.#-]{1,40}\))?)'
_PLACE = r'(?:\s+(?:in|on)\s+' + _NAME + r')?'
_APP = r'\s+(?:in|on|via|using|through)\s+' + MESSAGING_APPS
_SAYING = r'\s*(?:,\s*)?(?:saying|that says|which says|with the message|with|:)\s*'
_RISKY = re.compile(r'[\n\x00]|\b(?:then|without|unless|except|never|do not)\b|don[\'’]t', re.I)


def _canonical(content, destination, server, app, quoted):
    """One ordinary send in the literal form `direct_scope` already trusts."""
    if not content or not quoted and (_RISKY.search(content) or '"' in content):
        return None
    quote = '"' if '"' not in content else "'" if "'" not in content else None
    if quote is None:
        return None
    if server and re.fullmatch(MESSAGING_APPS, server, re.I):
        if app and app.casefold() != server.casefold():
            return None  # two different applications named
        app, server = server, ''  # 'to diego on Discord saying hi': the place was the app
    if not app:
        return None
    app = APP_NAMES.get(app.casefold(), app)
    if app == 'Discord' and destination[0] not in '#@':
        destination = ('#' if server else '@') + destination
    return (f'Send {quote}{content}{quote} to {destination}' + (f' in {server}' if server else '') + f' in {app}')


def natural_message(text):
    """Common ways of asking to send one message, rewritten to the literal
    form: 'message diego on Discord saying hi', 'DM @diego on discord "hi"',
    'send a discord message to diego saying hi', 'post "hi" in #general on
    D SERVER in Discord', 'send hi to gen-chat in D SERVER on discord'.

    Only named messaging applications qualify, the message text is always
    taken verbatim from the request, and anything ambiguous (two readings,
    an unquoted message carrying a further instruction) returns None so the
    request asks for clarification instead of guessing.
    """
    text = re.sub(r'[“”]', '"', text.strip()).rstrip('.!')
    if not re.search(r'\b' + MESSAGING_APPS + r'\b', text, re.I):
        return None
    quoted = r'"([^"\n]+)"'
    rest = r'(.+)'
    forms = [
        # send/post "hi" to|in DEST [in|on SERVER] in|on APP
        (r'(?:send|post|write)\s+' + quoted + r'\s+(?:to|in|into)\s+' + _NAME + _PLACE + _APP, 'q'),
        # message|dm DEST [in|on SERVER] on APP [saying] "hi"
        (r'(?:message|dm|msg|text)\s+' + _NAME + _PLACE + _APP + r'(?:' + _SAYING + r'|\s+)' + quoted, 'dq'),
        (r'(?:message|dm|msg|text)\s+' + _NAME + _PLACE + _APP + _SAYING + rest, 'd'),
        # message|dm DEST [saying] "hi" on APP
        (r'(?:message|dm|msg|text)\s+' + _NAME + r'(?:' + _SAYING + r'|\s+)' + quoted + _PLACE + _APP, 'dq2'),
        # send a [APP] message|dm to DEST [in|on SERVER] [on APP] saying hi
        (r'send\s+(?:a\s+|an\s+)?(?:' + MESSAGING_APPS + r'\s+)?(?:message|msg|dm|text)\s+to\s+' + _NAME + _PLACE +
         r'(?:' + _APP + r')?' + _SAYING + r'(?:' + quoted + r'|' + rest + r')', 's'),
        # send hi to DEST [in|on SERVER] in|on APP (unquoted, one reading only)
        (r'(?:send|post)\s+([^"\n]+?)\s+to\s+' + _NAME + _PLACE + _APP, 'u'),
    ]
    for pattern, kind in forms:
        match = re.fullmatch(pattern, text, re.I | re.S)
        if not match:
            continue
        g = match.groups()
        if kind == 'q':
            content, dest, server, app, is_quoted = g[0], g[1], g[2], g[3], True
        elif kind in {'dq', 'd'}:
            dest, server, app, content, is_quoted = g[0], g[1], g[2], g[3], kind == 'dq'
        elif kind == 'dq2':
            dest, content, server, app, is_quoted = g[0], g[1], g[2], g[3], True
        elif kind == 's':
            named, dest, server, app, q, plain = g
            if named and app and named.casefold() != app.casefold():
                return None
            app = app or named or ''
            content, is_quoted = (q, True) if q else (plain, False)
        else:
            content, dest, server, app = g
            is_quoted = False
            greedy = re.fullmatch(pattern.replace('([^"\\n]+?)', '([^"\\n]+)', 1), text, re.I | re.S)
            if not greedy or greedy.groups() != g or re.search(r'^(?:a|an|the)?\s*(?:message|msg|dm|text)\b', content, re.I):
                return None
        return _canonical(content.strip(), dest.strip(), (server or '').strip(), app, is_quoted)
    return None


def direct_scope(request):
    if not isinstance(request, str) or not 1 <= len(request) <= 4000:
        raise ValueError('Provide one bounded desktop request')
    text = request.strip()
    if text.casefold().startswith('please '):
        text = text[7:]
    text = natural_message(text) or text
    # Explicit web route; ordinary "Open Discord" remains native. The public
    # origin is reviewed navigation metadata, not login or sending authority.
    match = re.fullmatch(r'Open Discord in ([\w .+-]{1,80})', text, re.I)
    if match:
        return TaskScope(match.group(1), 'visit', 'https://discord.com/app')
    match = re.fullmatch(r'(Scroll (up|down)|(Next|Previous) tab|Read (?:the )?current page) in ([\w .+-]{1,80})', text, re.I)
    if match:
        _, scroll, tab, app = match.groups()
        return TaskScope(app, 'scroll' if scroll else 'tab' if tab else 'read', (scroll or tab or '').lower())
    match = re.fullmatch(r'(?:Open|Visit) (https?://\S+) in ([\w .+-]{1,80})', text, re.I)
    if match:
        from .browser_url import validated_url
        url, app = match.groups()
        return TaskScope(app, 'visit', validated_url(url))
    match = re.fullmatch(r'Paste (?:the )?(?:copied (?:text|code)|clipboard) in ([\w .+-]{1,80}) and save as (.+)', text, re.I)
    if match:
        app, path = match.groups()
        if not literal_path(path):
            raise ValueError('Provide one owned destination path')
        return TaskScope(app, 'paste_save', path=path)
    match = re.fullmatch(r'(Copy|Move) (.+?) to (.+?) in ([\w .+-]{1,80})', text, re.I)
    if match:
        operation, source, destination, app = match.groups()
        return TaskScope(app, operation.lower(), source.strip('\'"'), path=destination.strip('\'"'))
    match = re.fullmatch(r'Write ([\'\"])(.*?)\1 in ([\w .+-]{1,80}) and save (?:it )?as (.+?)[.]?', text, re.I | re.S)
    if match:
        _, content, app, path = match.groups()
        if not content or '\x00' in content or not literal_path(path):
            raise ValueError('Provide literal text and one owned destination path')
        return TaskScope(app, 'edit_save', content, path=path)
    match = re.fullmatch(r'Click ([\w .+-]{1,80}) in ([\w .+-]{1,80})', text, re.I)
    if match:
        target, app = match.groups()
        return TaskScope(app, 'click', target)
    match = re.fullmatch(r'Search for (.+) in ([\w .+-]{1,80})', text, re.I | re.S)
    if match:
        query, app = match.groups()
        text = 'Open ' + app + ' and search for ' + query
    # Navigate only: open a named channel/conversation and verify it. Nothing is typed
    # into the composer and nothing is sent; the destination binds exactly as for send.
    # "the general channel" is the literal channel name #general (no guessing).
    navigation = re.sub(r'\b((?:go|navigate|switch) to) (?:the )?#?([\w-]{1,80}) channel\b', r'\1 #\2', text, flags=re.I)
    match = (re.fullmatch(r'(?:Open|Launch) ([\w .+-]{1,80}?),? and (?:go|navigate|switch) to ([#@]?[\w .()+-]{1,100}?)'
                          r'(?: (?:in|on) ([\w .\'+-]{1,100}?))?[.]?', navigation, re.I)
             or re.fullmatch(r'(?:Go|Navigate|Switch) to ([#@]?[\w .()+-]{1,100}?)(?: (?:in|on) ([\w .\'+-]{1,100}?))?'
                             r' in ([\w .+-]{1,80}?)[.]?', navigation, re.I))
    if match:
        groups = match.groups()
        app, destination, server = (groups if match.re.pattern.startswith('(?:Open') else (groups[2], groups[0], groups[1]))
        if server and re.match(r'(?:the|my) ', server, re.I):
            # "on the RaceDay server" / "on my RaceDay server": the article and the
            # trailing kind word are not part of the name. "my server" names nothing.
            server = re.sub(r'\s+server$', '', server.split(' ', 1)[1], flags=re.I)
            if not server or server.casefold() == 'server':
                raise ValueError('Which server? Name it exactly; nothing was opened or typed.')
        if any(re.search(r'[,;\n]|\b(?:then|and|but|send|type|write|draft|without|do not|never)\b|don[\'’]t', field or '', re.I)
               for field in (app, destination, server)):
            raise ValueError('Clarify the exact destination; navigation never types or sends a message')
        destination, handle = split_handle(destination.strip())
        return TaskScope(app.strip(), 'go', '', destination, '', (server or '').strip(), handle=handle)
    match = re.fullmatch(r'(?:Open|Launch) ([\w .+-]{1,80}?)(?: and search for (.+))?', text, re.I | re.S)
    if match:
        app, query = match.groups()
        if query and re.search(r'\b(?:then|but|without|do not|never)\b|don[\'’]t', query, re.I):
            raise ValueError('The search text includes a possible task constraint; clarify the exact query before input')
        return TaskScope(app.strip(), 'search' if query else 'open', query or '')
    # Official web route for a named messaging service inside an explicit browser.
    match = re.fullmatch(r'(Send|Draft) ([\'\"])(.*?)\2 to ([\w .@#()+-]{1,100}?)(?: in ([\w .\'+-]{1,100}?))? '
                         r'in Discord (?:web )?in ([\w .+-]{1,60}?)(?: using account (.{1,100}))?', text, re.I | re.S)
    if match:
        verb, quote, content, destination, server, app, account = match.groups()
        if not content or any(re.search(r'[,;\n]|\b(?:then|but|without|do not|never)\b|don[\'’]t', field or '', re.I)
                              for field in (account, app, destination, server)):
            raise ValueError('Clarify the exact message, account and additional constraints')
        destination, handle = split_handle(destination)
        return TaskScope(app, verb.lower(), content, destination, account or '', server or '', predicate='discord.com',
                         handle=handle)
    match = re.fullmatch(r'(Send|Draft) ([\'\"])(.*?)\2 to ([\w .@#()+-]{1,100}?) in ([\w .\'+-]{1,100}?) in ([\w .+-]{1,80}?)(?: using account (.{1,100}))?', text, re.I | re.S)
    if match and not re.search(r'\bin\b', match.group(6), re.I):
        verb, quote, content, destination, server, app, account = match.groups()
        if not content or any(re.search(r'[,;\n]|\b(?:then|but|without|do not|never)\b|don[\'’]t', field or '', re.I)
                              for field in (account, app, destination, server)):
            raise ValueError('Clarify the exact message, account and additional constraints')
        destination, handle = split_handle(destination)
        return TaskScope(app, verb.lower(), content, destination, account or '', server, handle=handle)
    match = re.fullmatch(r'(Send|Draft) ([\'\"])(.*?)\2 to ([\w .@#()+-]{1,100}?) in ([\w .+-]{1,80}?)(?: using account (.{1,100}))?', text, re.I | re.S)
    if match:
        verb, quote, content, destination, app, account = match.groups()
        if not content:
            raise ValueError('The requested message is empty')
        account = account or ''
        if any(re.search(r'[,;\n]|\b(?:then|but|without|do not|never)\b|don[\'’]t', field, re.I) for field in (account, app, destination)):
            raise ValueError('Clarify the account and additional constraints before messaging')
        destination, handle = split_handle(destination)
        return TaskScope(app, verb.lower(), content, destination, account, handle=handle)
    match = re.fullmatch(r'Open ([\w .+-]{1,80}?), go to ([\w .#+-]{1,100}?), open ([\w .#+-]{1,100}?), (send|draft) ([\'\"])(.*?)\5(?: using account (.{1,100}))?', text, re.I | re.S)
    if match:
        app, server, channel, verb, quote, content, account = match.groups()
        account = account or ''
        if not content or any(re.search(r'[,;\n]|\b(?:then|but|without|do not|never)\b|don[\'’]t', field, re.I) for field in (account, app, server, channel)):
            raise ValueError('Clarify the exact message, account and additional constraints')
        return TaskScope(app, verb.lower(), content, channel, account, server)
    raise ValueError('NEEDS_USER_CLARIFICATION: specify the application and bounded effect. For messaging, provide exact text and destination; no message was sent.')


@dataclass(frozen=True)
class TaskGrant:
    id: str
    message_id: str
    scope: TaskScope
    epoch: int
    expires: float
    request_digest: str
    authorized_by: str = "direct_user_request"


class TaskAuthority:
    def __init__(self, stopped, clock=time.monotonic):
        self.stopped, self.clock = stopped, clock
        self.epoch = 0
        self.grants = {}
        self.lock = threading.Lock()

    def issue(self, request, message_id, policy, *, local_user=False, interpretation=None,
              bound_step=None, results=None):
        if not local_user or not policy.get('enabled') or not policy.get('trusted_tasks'):
            raise PermissionError('Enable trusted local tasks in Settings first')
        if self.stopped.is_set():
            raise InterruptedError('Desktop control stopped')
        if bound_step is not None:
            from .freeform_plan import BoundStep
            if type(bound_step) is not BoundStep or interpretation is not None:
                raise PermissionError('Invalid internal task binding')
            scope = bound_step.resolve(request, results, results.epoch if results else None)
        else:
            scope = interpreted_scope(request, interpretation) if interpretation is not None else direct_scope(request)
        if scope.effect != 'open' and any(policy.get(key) == 'deny' or (policy.get(key) != 'allow' and not policy.get('owner_mode')) for key in ('keyboard_policy', 'mouse_policy')):
            raise PermissionError('Trusted input requires keyboard and mouse Allow; stricter policies are preserved')
        with self.lock:
            grant = TaskGrant(uuid.uuid4().hex, message_id, scope, self.epoch,
                              self.clock() + 300, hashlib.sha256(request.encode()).hexdigest(),
                              'owner_task_policy' if policy.get('owner_mode') else 'direct_user_request')
            self.grants[grant.id] = grant
            return grant

    def check(self, grant, policy):
        with self.lock:
            if self.stopped.is_set() or grant.epoch != self.epoch or self.grants.get(grant.id) is not grant:
                raise InterruptedError('Task grant was cancelled or replaced')
            if self.clock() >= grant.expires:
                raise PermissionError('Task lifetime expired; renewed scope is required')
            if grant.authorized_by == 'owner_task_policy' and not policy.get('owner_mode'):
                raise PermissionError('Owner Mode was revoked')
            if not policy.get('enabled') or not policy.get('trusted_tasks'):
                raise PermissionError('Trusted task policy was removed')
            if grant.scope.effect != 'open' and any(policy.get(key) == 'deny' or (policy.get(key) != 'allow' and not policy.get('owner_mode')) for key in ('keyboard_policy', 'mouse_policy')):
                raise PermissionError('Input policy was restricted')

    def cancel(self):
        # No persistence lock, inference or portal call on this path.
        with self.lock:
            self.epoch += 1
            self.grants.clear()

    def finish(self, grant):
        with self.lock:
            self.grants.pop(grant.id, None)

    def bind_account(self, grant, observation, policy):
        """Narrow an omitted account once from scoped native semantics, never a model field."""
        from .gui_evidence import current_account
        self.check(grant, policy)
        if grant.scope.effect not in {'send', 'draft'} or grant.scope.account:
            return grant
        account = current_account(observation)
        if not account:
            raise ValueError('MESSAGING_ACCOUNT_UNVERIFIED: the selected client does not expose one unambiguous current account. No message text was entered; specifying an account still requires visible verification.')
        with self.lock:
            if self.grants.get(grant.id) is not grant or grant.epoch != self.epoch or self.stopped.is_set():
                raise InterruptedError('Task grant was cancelled or replaced')
            narrowed = replace(grant, scope=replace(grant.scope, account=account))
            self.grants[grant.id] = narrowed
            return narrowed


ACTION_FIELDS = {'action', 'target', 'value', 'revision', 'expected'}
ACTIONS = {'focus', 'click', 'type', 'key', 'invoke', 'scroll', 'finish', 'handoff'}


def same_control_label(left, right):
    numbers = dict(zip('zero one two three four five six seven eight nine'.split(), '0123456789'))
    normalized = lambda text: numbers.get(text.strip().casefold(), text.strip().casefold())
    return normalized(left) == normalized(right)


def scroll_amount(value):
    if not isinstance(value, str) or not re.fullmatch(r'-?[1-9][0-9]{0,2}', value):
        raise ValueError('Scroll requires an integer distance')
    amount = int(value)
    if not -600 <= amount <= 600:
        raise ValueError('Scroll distance exceeds the step budget')
    return amount


def decode_action(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate action field')
            result[key] = value
        return result
    if not isinstance(raw, str) or len(raw) > 12000:
        raise ValueError('Invalid action response size')
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    if not isinstance(value, dict) or set(value) != ACTION_FIELDS or any(type(v) is not str for v in value.values()):
        raise ValueError('Invalid action schema')
    if value['action'] not in ACTIONS or len(value['value']) > 4000 or len(value['expected']) > 400:
        raise ValueError('Unknown action or excessive fields')
    return value


def validate_effect(grant, proposal, observation):
    if proposal['revision'] != observation['revision']:
        raise ValueError('Stale proposal')
    target = next((c for c in observation['controls'] if c['id'] == proposal['target']), None)
    if target is None or not target.get('enabled'):
        raise ValueError('Target missing or disabled')
    name = target['name'].strip().casefold()
    if re.search(r'password|sign in|log in|captcha|sudo|install|purchase|buy|delete|remove|upload|attach|permission|grant|security|checkout|payment|erase|format disk|execute', name):
        raise PermissionError('This control requires human participation')
    scope = grant.scope
    if scope.effect == 'click':
        containers = [c for c in observation['controls'] if c.get('role') in {'dialog', 'heading', 'frame'}]
        if any(re.search(r'password|sign in|log in|checkout|payment|firewall|security settings|authentication|overwrite|confirm deletion',
                         c.get('name', ''), re.I) for c in containers):
            raise PermissionError('This screen requires effect-specific human handling')
        if name in {'ok', 'yes', 'confirm', 'approve', 'accept', 'allow', 'submit', 'run'}:
            raise PermissionError('A generic click cannot authorize a consequential confirmation')
    if proposal['action'] == 'scroll':
        scroll_amount(proposal['value'])
    link_jump = (scope.effect == 'click' and target.get('role') == 'link' and
                 same_control_label(target.get('name',''), scope.content) and proposal['value'] == 'jump')
    if proposal['action'] == 'invoke' and proposal['value'].casefold() not in {'click', 'press', 'activate', 'select', 'invoke'} and not link_jump:
        raise PermissionError('Unsupported accessible action effect')
    if proposal['action'] == 'type':
        allowed = {scope.content, scope.destination, scope.server}
        if proposal['value'] not in allowed or not proposal['value'] or target.get('value'):
            raise PermissionError('Text is outside the request or would replace a draft')
        if not target.get('editable'):
            raise PermissionError('Target is not an editable control')
        if scope.effect in {'send', 'draft'} and proposal['value'] == scope.content:
            context = {'account': scope.account, 'destination': scope.destination, 'server': scope.server}
            if observation.get('destination') != context or not is_composer(target):
                raise PermissionError('Resolve the exact destination and message composer before entering content')
        elif not is_search_control(target):
            raise PermissionError('Navigation text requires an identified search or address control')
    submitting = (proposal['action'] in {'click', 'invoke'} and name in {'send', 'send message'}) or proposal['action'] == 'key' and proposal['value'] == 'Enter'
    if submitting:
        if scope.effect == 'search':
            if not is_search_control(target):
                raise PermissionError('Enter is not bound to a search control')
            if target.get('value') != scope.content:
                raise PermissionError('Search content changed')
        elif scope.effect == 'send':
            # This evidence is supplied by an app-neutral semantic resolver, not model JSON.
            context = observation.get('destination', {})
            if context != {'account': scope.account, 'destination': scope.destination, 'server': scope.server}:
                raise PermissionError('Account or destination is unresolved or changed')
            drafts = [c for c in observation['controls'] if is_composer(c) and c.get('value') == scope.content]
            if len(drafts) != 1:
                raise PermissionError('Exact authorized message is not uniquely present in the composer')
            if proposal['action'] == 'key' and target is not drafts[0]:
                raise PermissionError('Enter must target the verified composer, not another focused control')
            if proposal['action'] == 'key':
                from .gui_evidence import enter_sends
                if not enter_sends(target):
                    raise PermissionError('COMPOSER_SEMANTICS_UNVERIFIED: Enter-to-send is not established by this client')
        else:
            raise PermissionError('This task does not authorize submission')
    elif proposal['action'] in {'click', 'invoke'}:
        navigation = {'search', 'new tab', 'back', 'forward', 'menu', 'search messages', 'search channels'}
        exact_click = scope.effect == 'click' and same_control_label(name, scope.content)
        if scope.effect in {'send','draft'} and name == scope.destination.casefold():
            choices = [c for c in observation['controls'] if c.get('name','').casefold() == name
                       and c.get('role') != 'heading' and c.get('enabled')]
            if len(choices) != 1:
                raise PermissionError('The recipient is ambiguous; no destination was selected')
        if not exact_click and name not in navigation | {scope.destination.casefold(), scope.server.casefold()}:
            raise PermissionError('The effect of this control is not established by the task')
    if proposal['action'] == 'key' and proposal['value'] == 'Space':
        if scope.effect != 'click' or not same_control_label(name, scope.content) or target.get('role') not in {'button','push button'} or not target.get('focused'):
            raise PermissionError('Space requires the exact requested focused button')
    if proposal['action'] == 'key' and proposal['value'] not in {'Space', 'Enter', 'Tab', 'Escape', 'Down', 'Up', 'Left', 'Right'}:
        raise PermissionError('Unsupported key')
    return target, submitting


def is_composer(control):
    return bool(control.get('editable')) and control.get('name', '').strip().casefold() in {
        'message', 'message input', 'write a message', 'type a message', 'message composer'}


def is_search_control(control):
    name = control.get('name', '').strip().casefold()
    return bool(control.get('editable')) and ('search' in name or 'address' in name)
