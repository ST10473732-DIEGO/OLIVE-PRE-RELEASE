"""OLIVE Draw and DrawNote from Chat: a small literal request grammar.

Only whole, literal requests match ("Open OLIVE Draw", "Open DrawNote and go to
Draw", "New drawing called Plan"). Ordinary sentences that merely contain the
word draw ("draw a conclusion", "draw a cat") never match. Chat gets no pixel
or stroke authority: it can navigate, create an empty drawing, open one by exact
title and list titles. Drawing titles are data and never become instructions.
"""
import asyncio
import re
import time

from .service import DrawError

_Q = r'["“”\'‘’]?'
_OWNER = r'(?:my\s+|the\s+|our\s+)?'
_POLITE = r'(?:(?:please|can you|could you|would you)\s+)?'
_GO = r'(?:open|show|go\s+to|switch\s+to|launch)'
_DRAWNOTE = r'(?:the\s+)?(?:olive\s+)?draw\s*note(?:\s+app)?'
_SECTION = r'(?:\s+(?:tab|section|view|app))?'

PATTERNS = [
    ('open_draw', re.compile(rf'^{_POLITE}{_GO}\s+(?:the\s+)?(?:olive\s+)?draw(?:ing)?(?:\s+app)?$', re.I)),
    ('open_draw', re.compile(rf'^{_POLITE}{_GO}\s+(?:my\s+)?drawings$', re.I)),
    ('open_draw', re.compile(rf'^{_POLITE}{_GO}\s+{_DRAWNOTE}\s*,?\s+(?:(?:and\s+)?then\s+|and\s+)?{_GO}\s+(?:the\s+)?draw{_SECTION}$', re.I)),
    ('open_notes', re.compile(rf'^{_POLITE}{_GO}\s+{_DRAWNOTE}\s*,?\s+(?:(?:and\s+)?then\s+|and\s+)?{_GO}\s+(?:the\s+)?(?:olive\s+)?notes{_SECTION}$', re.I)),
    ('open_drawnote', re.compile(rf'^{_POLITE}{_GO}\s+{_DRAWNOTE}$', re.I)),
    ('list', re.compile(rf'^{_POLITE}(?:list|show\s+me)\s+(?:all\s+)?(?:of\s+)?my\s+drawings$', re.I)),
    ('list', re.compile(r'^what\s+drawings\s+do\s+i\s+have\??$', re.I)),
    ('create', re.compile(rf'^{_POLITE}(?:create|make|start|new)\s+(?:a\s+)?(?:new\s+)?(?:blank\s+)?drawing'
                          rf'(?:\s+(?:called|named|titled)\s+{_Q}(?P<title>.+?){_Q})?$', re.I)),
    ('open', re.compile(rf'^{_POLITE}(?:open|show)\s+{_OWNER}(?:drawing\s+(?:called|named|titled)\s+{_Q}(?P<title>.+?){_Q}'
                        rf'|{_Q}(?P<title2>.+?){_Q}\s+drawing)$', re.I)),
]


def parse(text):
    """A literal Draw/DrawNote request, or None. Never interprets drawing content."""
    if type(text) is not str or len(text) > 2000:
        return None
    value = text.strip().rstrip('.!')
    for action, pattern in PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            groups = {k: v.strip() for k, v in match.groupdict().items() if v}
            if 'title2' in groups:
                groups['title'] = groups.pop('title2')
            return dict(groups, action=action)
    return None


class DrawChat:
    def __init__(self, services, orchestrator):
        self.s = services
        self.orchestrator = orchestrator
        self.pending = {}   # chat_id -> (expires, candidate ids)

    async def handle(self, chat_id, text):
        draw = getattr(self.s, 'draw', None)
        # A pending "which one?" question lasts for exactly the next message.
        pending = self.pending.pop(chat_id, None)
        request = parse(text) or self._choice(pending, text)
        if request is None:
            return None
        reply = lambda answer: self.orchestrator.reply(chat_id, text, answer)
        action = request['action']
        # Navigation never needs storage: DrawNote opens even if drawings cannot load.
        if action == 'open_notes':
            self.s.publish('notes.navigate', {})
            return reply('Opened OLIVE Notes in OLIVE DrawNote.')
        if action == 'open_drawnote':
            self.s.publish('drawnote.navigate', {'section': ''})
            return reply('Opened OLIVE DrawNote.')
        if action == 'open_draw':
            self.s.publish('drawnote.navigate', {'section': 'draw'})
            return reply('Opened OLIVE Draw.')
        if draw is None or draw.unavailable:
            return reply('Drawing storage unavailable. Your drawings were left untouched.')
        try:
            return await self._run(chat_id, request, reply)
        except DrawError as failure:
            return reply(str(failure))

    @staticmethod
    def _choice(pending, text):
        if not pending or pending[0] < time.monotonic():
            return None
        choice = text.strip().rstrip('.')
        if not choice.isdigit() or not 1 <= int(choice) <= len(pending[1]):
            return None
        return {'action': 'open', 'drawing_id': pending[1][int(choice) - 1]}

    async def _run(self, chat_id, request, reply):
        draw = self.s.draw
        action = request['action']
        if action == 'list':
            listing = await asyncio.to_thread(draw.list_drawings, 'drawings')
            items = listing['drawings']
            if not items:
                return reply('You have no drawings yet. Say “New drawing” to start one.')
            lines = [f'• {d["title"]} — {d["width"]} × {d["height"]}' for d in items[:12]]
            more = f'\n…and {len(items) - 12} more in OLIVE Draw.' if len(items) > 12 else ''
            return reply(f'You have {len(items)} drawing(s) on this device:\n' + '\n'.join(lines) + more)
        if action == 'create':
            created = await asyncio.to_thread(draw.create, request.get('title', ''))
            self.s.publish('drawnote.navigate', {'section': 'draw', 'drawing_id': created['drawing_id']})
            return reply(f'Created “{created["title"]}” ({created["width"]} × {created["height"]}) in OLIVE Draw.')
        if action == 'open':
            if request.get('drawing_id'):
                found = [await asyncio.to_thread(draw.get, request['drawing_id'])]
            else:
                title = request['title'].strip().strip('"“”\'‘’')
                found = await asyncio.to_thread(draw.find_by_title, title)
                if not found:
                    return reply(f'I couldn’t find a drawing called “{title}”. Nothing was changed.')
            if len(found) > 1:
                self.pending[chat_id] = (time.monotonic() + 600, [d['drawing_id'] for d in found[:9]])
                lines = [f'{i}. {d["title"]} — edited {d["updated_at"].replace("T", " ")[:16]}' for i, d in enumerate(found[:9], 1)]
                return reply(f'You have {len(found)} drawings called “{found[0]["title"]}”. Which one?\n' + '\n'.join(lines) +
                             '\nReply with the number.')
            drawing = found[0]
            self.s.publish('drawnote.navigate', {'section': 'draw', 'drawing_id': drawing['drawing_id']})
            return reply(f'Opened “{drawing["title"]}” in OLIVE Draw.')
        return None
