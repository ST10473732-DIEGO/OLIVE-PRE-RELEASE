"""Finite authority derived only from the literal local user request.

This deliberately recognizes bounded command forms, not model interpretations.
Unrecognized requests require clarification/review, never a permissive fallback.
Observations and action JSON cannot create or extend a grant.
"""
from dataclasses import dataclass
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


def direct_scope(request):
    if not isinstance(request, str) or not 1 <= len(request) <= 4000:
        raise ValueError('Provide one bounded desktop request')
    text = request.strip()
    match = re.fullmatch(r'(?:Open|Launch) ([\w .+-]{1,80}?)(?: and search for (.+))?', text, re.I | re.S)
    if match:
        app, query = match.groups()
        return TaskScope(app.strip(), 'search' if query else 'open', query or '')
    match = re.fullmatch(r'(Send|Draft) ([\'\"])(.*?)\2 to (.{1,100}?) in (.{1,80}?) using account (.{1,100})', text, re.I | re.S)
    if match:
        verb, quote, content, destination, app, account = match.groups()
        if not content:
            raise ValueError('The requested message is empty')
        return TaskScope(app, verb.lower(), content, destination, account)
    match = re.fullmatch(r'Open (.{1,80}?), go to (.{1,100}?), open (.{1,100}?), (send|draft) ([\'\"])(.*?)\5 using account (.{1,100})', text, re.I | re.S)
    if match:
        app, server, channel, verb, quote, content, account = match.groups()
        return TaskScope(app, verb.lower(), content, channel, account, server)
    raise ValueError('Specify the application and bounded effect. For messaging, provide exact text, destination and account; no message was sent.')


@dataclass(frozen=True)
class TaskGrant:
    id: str
    message_id: str
    scope: TaskScope
    epoch: int
    expires: float
    request_digest: str


class TaskAuthority:
    def __init__(self, stopped, clock=time.monotonic):
        self.stopped, self.clock = stopped, clock
        self.epoch = 0
        self.grants = {}
        self.lock = threading.Lock()

    def issue(self, request, message_id, policy, *, local_user=False):
        if not local_user or not policy.get('enabled') or not policy.get('trusted_tasks'):
            raise PermissionError('Enable trusted local tasks in Settings first')
        if self.stopped.is_set():
            raise InterruptedError('Desktop control stopped')
        scope = direct_scope(request)
        if scope.effect != 'open' and any(policy.get(key) != 'allow' for key in ('keyboard_policy', 'mouse_policy')):
            raise PermissionError('Trusted input requires keyboard and mouse Allow; stricter policies are preserved')
        with self.lock:
            grant = TaskGrant(uuid.uuid4().hex, message_id, scope, self.epoch,
                              self.clock() + 300, hashlib.sha256(request.encode()).hexdigest())
            self.grants[grant.id] = grant
            return grant

    def check(self, grant, policy):
        with self.lock:
            if self.stopped.is_set() or grant.epoch != self.epoch or self.grants.get(grant.id) is not grant:
                raise InterruptedError('Task grant was cancelled or replaced')
            if self.clock() >= grant.expires:
                raise PermissionError('Task lifetime expired; renewed scope is required')
            if not policy.get('enabled') or not policy.get('trusted_tasks'):
                raise PermissionError('Trusted task policy was removed')
            if grant.scope.effect != 'open' and any(policy.get(key) != 'allow' for key in ('keyboard_policy', 'mouse_policy')):
                raise PermissionError('Input policy was restricted')

    def cancel(self):
        # No persistence lock, inference or portal call on this path.
        with self.lock:
            self.epoch += 1
            self.grants.clear()

    def finish(self, grant):
        with self.lock:
            self.grants.pop(grant.id, None)


ACTION_FIELDS = {'action', 'target', 'value', 'revision', 'expected'}
ACTIONS = {'focus', 'click', 'type', 'key', 'invoke', 'scroll', 'finish', 'handoff'}


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
    if re.search(r'password|sign in|log in|captcha|sudo|install|purchase|buy|delete|remove|upload|attach|permission|grant|security', name):
        raise PermissionError('This control requires human participation')
    scope = grant.scope
    if proposal['action'] == 'type':
        allowed = {scope.content, scope.destination, scope.server}
        if proposal['value'] not in allowed or not proposal['value'] or target.get('value'):
            raise PermissionError('Text is outside the request or would replace a draft')
        if not target.get('editable'):
            raise PermissionError('Target is not an editable control')
    submitting = name in {'send', 'send message'} or proposal['action'] == 'key' and proposal['value'] == 'Enter'
    if submitting:
        if scope.effect == 'search':
            if 'search' not in name and 'address' not in name:
                raise PermissionError('Enter is not bound to a search control')
            if target.get('value') != scope.content:
                raise PermissionError('Search content changed')
        elif scope.effect == 'send':
            # This evidence is supplied by an app-neutral semantic resolver, not model JSON.
            context = observation.get('destination', {})
            if context != {'account': scope.account, 'destination': scope.destination, 'server': scope.server}:
                raise PermissionError('Account or destination is unresolved or changed')
            drafts = [c for c in observation['controls'] if c.get('editable') and c.get('value') == scope.content]
            if len(drafts) != 1:
                raise PermissionError('Exact authorized message is not uniquely present in the composer')
        else:
            raise PermissionError('This task does not authorize submission')
    elif proposal['action'] in {'click', 'invoke'}:
        navigation = {'search', 'new tab', 'back', 'forward', 'menu', 'search messages', 'search channels'}
        if name not in navigation | {scope.destination.casefold(), scope.server.casefold()}:
            raise PermissionError('The effect of this control is not established by the task')
    if proposal['action'] == 'key' and proposal['value'] not in {'Enter', 'Tab', 'Escape', 'Down', 'Up', 'Left', 'Right'}:
        raise PermissionError('Unsupported key')
    return target, submitting
