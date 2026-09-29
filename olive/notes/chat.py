"""OLIVE Notes from Chat: a literal request grammar plus typed Notes tools.

Only the user's own words select an action; note text is data and never
becomes instructions, permissions or tool calls. Notes are never injected into
Chat unless the request names a note. Titles resolve by exact match; duplicate
titles are asked about, never guessed. Nothing here reaches web search.
"""
import asyncio
import re
import time

from ..agent.permission_service import PermissionDecision
from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition
from .service import NotesError

MAX_READ_CHARS = 6000
MAX_EVIDENCE_CHARS = 48000
_Q = r'["“”\'‘’]?'
_OWNER = r'(?:my\s+|the\s+|our\s+)?'
_POLITE = r'(?:(?:please|can you|could you|would you)\s+)?'

PATTERNS = [
    ('open_all', re.compile(rf'^{_POLITE}(?:open|show|go to|launch)\s+{_OWNER}(?:olive\s+)?notes(?:\s+app)?$', re.I)),
    ('open', re.compile(rf'^{_POLITE}(?:open|show)\s+{_OWNER}(?:note\s+(?:called|named|titled)\s+{_Q}(?P<title>.+?){_Q}|{_Q}(?P<title2>.+?){_Q}\s+note)$', re.I)),
    ('create', re.compile(rf'^{_POLITE}(?:create|make|start|new)\s+(?:a\s+)?(?:new\s+)?note\s+(?:called|named|titled)\s+{_Q}(?P<title>.+?){_Q}'
                          rf'(?:\s*,?\s+(?:and\s+(?:add|write|put)|with(?:\s+the\s+text)?|containing|saying)\s+{_Q}(?P<body>.+?){_Q})?$', re.I | re.S)),
    ('append', re.compile(rf'^{_POLITE}(?:add|append|put|write)\s+{_Q}(?P<body>.+?){_Q}\s+(?:to|in|into|on)\s+{_OWNER}{_Q}(?P<title>.+?){_Q}\s+note$', re.I | re.S)),
    ('summarize', re.compile(rf'^{_POLITE}(?:summari[sz]e|give me a summary of)\s+{_OWNER}{_Q}(?P<title>.+?){_Q}\s+note$', re.I)),
    ('read', re.compile(rf'^{_POLITE}(?:read|show me|what(?:\'s| is) in)\s+{_OWNER}{_Q}(?P<title>.+?){_Q}\s+note\??$', re.I)),
    ('search', re.compile(rf'^{_POLITE}(?:search|look through|find in)\s+(?:my\s+)?(?:olive\s+)?notes\s+for\s+{_Q}(?P<query>.+?){_Q}$', re.I)),
    ('search', re.compile(rf'^{_POLITE}find\s+{_Q}(?P<query>.+?){_Q}\s+in\s+my\s+notes$', re.I)),
    ('purge', re.compile(rf'^{_POLITE}permanently\s+delete\s+{_OWNER}{_Q}(?P<title>.+?){_Q}\s+note$', re.I)),
    ('purge', re.compile(rf'^{_POLITE}delete\s+{_OWNER}{_Q}(?P<title>.+?){_Q}\s+note\s+permanently$', re.I)),
    ('trash', re.compile(rf'^{_POLITE}(?:delete|remove|trash)\s+{_OWNER}{_Q}(?P<title>.+?){_Q}\s+note$', re.I)),
    ('restore', re.compile(rf'^{_POLITE}(?:restore|recover|undelete)\s+{_OWNER}{_Q}(?P<title>.+?){_Q}\s+note$', re.I)),
    ('rename', re.compile(rf'^{_POLITE}rename\s+{_OWNER}{_Q}(?P<title>.+?){_Q}\s+note\s+to\s+{_Q}(?P<new>.+?){_Q}$', re.I)),
]


def parse(text):
    """A literal Notes request, or None. Never interprets note content."""
    if type(text) is not str or len(text) > 4000:
        return None
    value = text.strip().rstrip('.!')
    for action, pattern in PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            groups = {k: v.strip() for k, v in match.groupdict().items() if v}
            if 'title2' in groups:
                groups['title'] = groups.pop('title2')
            if groups.get('title', '').casefold() in ('olive notes', 'notes'):
                return {'action': 'open_all'} if action == 'open' else None
            return dict(groups, action=action)
    return None


def _when(value):
    return value.replace('T', ' ')[:16] if value else ''


class NotesChat:
    def __init__(self, services, orchestrator):
        self.s = services
        self.orchestrator = orchestrator
        self.pending = {}   # chat_id -> (expires, request, candidate ids)

    def _allowed(self, permission):
        decision = self.s.permissions.evaluate(permission).decision
        if decision == PermissionDecision.DENY:
            raise PermissionError(f'Notes permission is Off: {permission}')
        return decision

    async def _confirm(self, action, title, consequence):
        from ..agent.confirmation_service import ConfirmationRequest
        response = await self.s.confirmations.request(ConfirmationRequest(
            task_id='notes', tool_name=action, summary=f'{consequence}: “{title}”', risk_level='high',
            targets=[title], arguments={'title': title, 'consequence': consequence}))
        return response.approved

    async def handle(self, chat_id, text):
        notes = getattr(self.s, 'notes', None)
        if notes is None:
            return None
        request = parse(text)
        if request is None:
            request = self._follow_up(chat_id, text)
            if request is None:
                return None
        reply = lambda answer: self.orchestrator.reply(chat_id, text, answer)
        if notes.unavailable:
            return reply('Notes storage unavailable. Your notes database was left untouched.')
        try:
            return await self._run(chat_id, text, request, reply)
        except PermissionError as failure:
            return reply(str(failure) + '. Change it in Settings › Permissions.')
        except NotesError as failure:
            return reply(str(failure))

    def _follow_up(self, chat_id, text):
        entry = self.pending.pop(chat_id, None)
        if not entry or entry[0] < time.monotonic():
            return None
        choice = text.strip().rstrip('.')
        if not choice.isdigit() or not 1 <= int(choice) <= len(entry[2]):
            return None
        return dict(entry[1], note_id=entry[2][int(choice) - 1])

    async def _resolve(self, chat_id, request, reply, *, trash=False):
        """Exact title (case-insensitive). None + a reply when ambiguous/missing."""
        if request.get('note_id'):
            return await self.s.notes.call(self.s.notes.get, request['note_id']), None
        title = request['title'].strip().strip('"“”\'‘’').casefold()
        views = ('trash',) if trash else ('notes',)
        candidates = []
        for view in views:
            listing = await self.s.notes.call(self.s.notes.list_notes, view)
            candidates += [n for n in listing['notes'] if n['display_title'].casefold() == title]
        if not candidates and not trash and request['action'] == 'purge':
            listing = await self.s.notes.call(self.s.notes.list_notes, 'trash')
            candidates = [n for n in listing['notes'] if n['display_title'].casefold() == title]
        if len(candidates) == 1:
            return candidates[0], None
        if not candidates:
            where = ' in Recently Deleted' if trash else ''
            return None, reply(f'I couldn’t find a note called “{request["title"]}”{where}. Nothing was changed.')
        self.pending[chat_id] = (time.monotonic() + 600, request, [n['note_id'] for n in candidates[:9]])
        lines = [f'{i}. {n["display_title"]} — edited {_when(n["edited_at"])}' for i, n in enumerate(candidates[:9], 1)]
        return None, reply(f'You have {len(candidates)} notes called “{request["title"]}”. Which one?\n' + '\n'.join(lines) +
                           '\nReply with the number.')

    async def _run(self, chat_id, text, request, reply):
        notes = self.s.notes
        action = request['action']
        if action == 'open_all':
            self.s.publish('notes.navigate', {})
            return reply('Opened OLIVE Notes.')
        if action == 'search':
            self._allowed('notes.read')
            found = await notes.call(notes.search, request['query'])
            if not found['results']:
                return reply(f'No notes match “{request["query"]}”. Searched on this device only.')
            lines = [f'• {n["display_title"]}' + (f' — “{n["snippet"][:100]}”' if n.get('snippet') else '') for n in found['results'][:8]]
            return reply(f'Found {len(found["results"])} note(s) on this device:\n' + '\n'.join(lines))
        if action == 'create':
            self._allowed('notes.write')
            created = await notes.call(notes.create, request['title'][:200], request.get('body', ''), origin='chat-tool')
            suffix = ' and added your text' if request.get('body') else ''
            return reply(f'Created “{created["display_title"]}”{suffix}. It is in OLIVE Notes.')
        note, answered = await self._resolve(chat_id, request, reply, trash=action == 'restore')
        if answered is not None:
            return answered
        nid = note['note_id']
        if action == 'open':
            self.s.publish('notes.navigate', {'note_id': nid})
            return reply(f'Opened “{note["display_title"]}” in OLIVE Notes.')
        if action == 'append':
            self._allowed('notes.write')
            if note['trashed']:
                return reply(f'“{note["display_title"]}” is in Recently Deleted. Restore it first.')
            await notes.call(notes.append_text, nid, request['body'], origin='chat-tool')
            return reply(f'Added to “{note["display_title"]}”.')
        if action == 'rename':
            self._allowed('notes.write')
            renamed = await notes.call(notes.rename, nid, request['new'][:200], origin='chat-tool')
            return reply(f'Renamed to “{renamed["display_title"]}”.')
        if action == 'read':
            self._allowed('notes.read')
            content = await notes.call(notes.read_text, nid)
            body = content['text']
            clipped = body[:MAX_READ_CHARS]
            more = '\n\n(Showing the first part. Open the note to see all of it.)' if len(body) > MAX_READ_CHARS else ''
            return reply(f'“{content["display_title"]}”:\n\n{clipped or "(empty note)"}{more}')
        if action == 'summarize':
            self._allowed('notes.read')
            if getattr(self.s.chat, 'targets', {}).get(chat_id):
                return reply('Note summaries run on This device only. Select This device, then ask again. The note was not shared.')
            if getattr(self.s.chats[chat_id], 'preset', '') == 'now':
                return reply('OLIVE NOW answers from the web, so it does not read private notes. Switch to FAST, NORMAL or MAX to summarise this note.')
            content = await notes.call(notes.read_text, nid)
            if len(content['text']) > MAX_EVIDENCE_CHARS:
                return reply('That note is too long to summarise in one answer. Open it and select a part, or split it into smaller notes.')
            evidence = {'note_id': nid, 'title': content['display_title'], 'revision': content['revision'],
                        'sha256': content['sha256'], 'text': content['text']}
            self.orchestrator.context(chat_id).remember_user(text)
            return await self.s.chat.send(chat_id, text, note_evidence=evidence)
        if action == 'trash':
            if self._allowed('notes.delete') == PermissionDecision.ASK:
                if not await self._confirm('notes.delete', note['display_title'], 'Move to Recently Deleted'):
                    return reply('Nothing was deleted.')
            await notes.call(notes.trash, nid, origin='chat-tool')
            return reply(f'Moved “{note["display_title"]}” to Recently Deleted. You can restore it from OLIVE Notes.')
        if action == 'restore':
            self._allowed('notes.write')
            await notes.call(notes.restore, nid, origin='chat-tool')
            return reply(f'Restored “{note["display_title"]}”.')
        if action == 'purge':
            self._allowed('notes.delete')
            # Permanent deletion always asks, whatever the saved policy says.
            if not await self._confirm('notes.purge', note['display_title'], 'Permanently delete on all your devices'):
                return reply('Nothing was deleted.')
            if not note['trashed']:
                await notes.call(notes.trash, nid, origin='chat-tool')
            await notes.call(notes.purge, nid, origin='chat-tool')
            return reply(f'Permanently deleted “{note["display_title"]}”.')
        return None


class NotesTool:
    """Typed Notes tools for the agent registry. Writes always need confirmation."""
    SCHEMAS = {
        'notes.list': ((), 'notes.read'), 'notes.read': (('note_id',), 'notes.read'),
        'notes.search': (('query',), 'notes.read'), 'notes.create': (('title',), 'notes.write'),
        'notes.append': (('note_id', 'text'), 'notes.write'), 'notes.replace': (('note_id', 'text'), 'notes.write'),
        'notes.rename': (('note_id', 'title'), 'notes.write'), 'notes.delete': (('note_id',), 'notes.delete'),
        'notes.restore': (('note_id',), 'notes.write'),
    }

    def __init__(self, services, name):
        self.s = services
        self.name = name
        required, permission = self.SCHEMAS[name]
        self.permission = permission
        self.internal_only = False
        self.definition = ToolDefinition(name, 'Local OLIVE Notes: ' + name.split('.')[1], 'notes', {'required': list(required)},
                                         required_permissions=(permission,),
                                         confirmation_required=permission != 'notes.read', timeout_seconds=30)

    async def execute(self, arguments, context):
        if not isinstance(arguments, dict) or not all(isinstance(v, (str, bool)) for v in arguments.values()):
            raise ValueError('Invalid Notes arguments')
        if context.cancellation_event and context.cancellation_event.is_set():
            raise asyncio.CancelledError()
        if self.s.permissions.evaluate(self.permission).decision == PermissionDecision.DENY:
            raise PermissionError('Permission denied: ' + self.permission)
        notes = self.s.notes
        name = self.name
        if name == 'notes.list':
            data = await notes.call(notes.list_notes, 'notes')
            data = {'items': [{k: n[k] for k in ('note_id', 'display_title', 'edited_at', 'pinned')} for n in data['notes'][:200]]}
        elif name == 'notes.read':
            data = await notes.call(notes.read_text, arguments['note_id'])
            data = {k: data[k] for k in ('note_id', 'display_title', 'text', 'revision')}
        elif name == 'notes.search':
            data = await notes.call(notes.search, str(arguments['query']))
        elif name == 'notes.create':
            data = await notes.call(notes.create, str(arguments['title']), str(arguments.get('text', '')), origin='chat-tool')
        elif name == 'notes.append':
            data = await notes.call(notes.append_text, arguments['note_id'], str(arguments['text']), origin='chat-tool')
        elif name == 'notes.replace':
            data = await notes.call(notes.replace_text, arguments['note_id'], str(arguments['text']), origin='chat-tool')
        elif name == 'notes.rename':
            data = await notes.call(notes.rename, arguments['note_id'], str(arguments['title']), origin='chat-tool')
        elif name == 'notes.delete':
            data = await notes.call(notes.trash, arguments['note_id'], origin='chat-tool')
        else:
            data = await notes.call(notes.restore, arguments['note_id'], origin='chat-tool')
        return ToolResult(True, 'Local Notes operation completed', data)


def register_tools(services):
    for name in NotesTool.SCHEMAS:
        services.tool_registry.register(NotesTool(services, name))
