"""Visible-UI messaging for clients without usable accessibility semantics.

GUI-Owl only proposes where a region is. Each proposal is verified from an
independent OCR read of a small crop around it before any input, and every input
is followed by a fresh frame. The destination and content come solely from the
user's request. Enter is sent once, only after destination, workspace, account,
composer and exact draft are verified, and never retried after an uncertain
result. No message pane is read beyond the band just above the composer.
"""
import asyncio

from ..messaging_context import (AMBIGUOUS, MISMATCH, VERIFIED, Layer, MessagingContext, adapter_for, bare,
                                 composer_state, observed_account, resolve_destination, resolve_exact,
                                 switcher_matches)
from ..visual_ocr import band, normalize, ocr_lines

SIZES = {'composer': (32, None), 'header': (22, 260), 'server': (20, 150), 'account': (24, 130),
         'switcher': (30, 300)}


class VisualMessaging:
    def __init__(self, runtime, grant, pid, adapter, web=False):
        self.runtime, self.grant, self.pid, self.adapter, self.web = runtime, grant, pid, adapter, web
        self.scope = grant.scope
        self.context = MessagingContext(runtime.desktop.record.application, adapter.key, self.scope.content,
                                        submit=adapter.submit)
        self.history = runtime.desktop.record.history

    def progress(self, text):
        d = self.runtime.desktop
        d.record.current_action = text
        d.publish()
        if self.runtime.chat_id:
            d.s.publish('interaction_activity', {'chat_id': self.runtime.chat_id, 'message': text})

    async def frame(self):
        self.runtime.check_task(self.grant)
        frame = await self.runtime.native.call('visual_observe', {'pid': self.pid}, timeout=5)
        if not self.web:
            return {**frame, 'offset': (0, 0)}
        # Browser route: only the verified page document is seen by the model/OCR,
        # so the address bar or browser search can never pass as the composer.
        locations = await self.runtime.native.call('document_locations', {'pid': self.pid})
        return crop_document(frame, [d for d in locations.get('documents', []) if d.get('ready')])

    async def click(self, frame, point):
        dx, dy = frame.get('offset', (0, 0))
        await self.runtime.native.call('visual_click', {'revision': frame['revision'],
                                                        'point': [point[0] + dx, point[1] + dy]})

    async def region(self, frame, role, label=''):
        """Model proposal -> bounded crop -> OCR lines (frame pixels)."""
        if self.runtime.gui is None:
            from ...services.gui_model_service import GuiModelService
            self.runtime.gui = GuiModelService(self.runtime.desktop.s.model_residency)
        prompt = self.adapter.prompts[role].format(label=label)
        action = await self.runtime.gui.action(frame, prompt)
        self.runtime.check_task(self.grant)
        if action['action'] != 'left_click':
            return None, []
        x, y = action['coordinate']
        point = (x * frame['width'] / 1000, y * frame['height'] / 1000)
        half_height, half_width = SIZES.get(role, (18, 280))
        if half_width is None:
            half_width = frame['width'] * .4  # The composer, not side panels at the same height.
        lines = await asyncio.to_thread(ocr_lines, frame, band(frame, point, half_height, half_width))
        self.diagnose(role, point, lines)
        return point, lines

    def diagnose(self, role, point, lines):
        """Owned fixtures only: keep OCR text for debugging. Real clients record states, never text."""
        entry = {'operation': 'visual_region', 'role': role, 'point': [round(v) for v in point] if point else None,
                 'lines': len(lines)}
        if self.adapter.key.endswith('fixture'):
            entry['text'] = [(l['text'], round(l['confidence'])) for l in lines][:12]
        self.history.append(entry)

    async def resolve(self):
        frame = await self.frame()
        point, lines = await self.region(frame, 'composer')
        composer = composer_state(lines, self.adapter)
        ctx = self.context
        ctx.destination = resolve_destination(self.scope, composer)
        ctx.draft = '' if composer[0] == 'empty' else composer[2] if composer[0] == 'draft' else None
        if composer[0] == 'draft':
            # A draft hides the placeholder; confirm the conversation from its header instead.
            anchor, lines = await self.region(frame, 'header')
            ctx.destination = resolve_exact(lines, self.scope.destination, 'destination header', anchor)
        ctx.composer = (Layer(VERIFIED, 'composer', composer[3]['box'], 'placeholder/draft read in proposed band')
                        if composer[0] in {'empty', 'draft'} else Layer(evidence='composer band not readable'))
        if self.scope.server:
            anchor, lines = await self.region(frame, 'server')
            ctx.workspace = resolve_exact(lines, self.scope.server, 'workspace', anchor)
        _, lines = await self.region(frame, 'account')
        observed = observed_account(lines)
        if self.scope.account:
            ctx.account = (Layer(VERIFIED, self.scope.account, observed.box, 'requested account visible')
                           if observed.state == VERIFIED and bare(observed.value) == bare(self.scope.account)
                           else Layer(MISMATCH if observed.state == VERIFIED else observed.state,
                                      evidence='requested account not verified'))
        else:
            ctx.account = observed
        self.history.append({'operation': 'visual_messaging_resolve', 'context': ctx.summary()})
        return frame, point

    async def navigate(self, select=True):
        """One bounded quick-switcher attempt; exact unique row or no click.

        With select=False it only proves the destination name is unique in this
        client (the current view alone is not evidence: names repeat across servers).
        """
        self.progress('Finding ' + self.scope.destination + '…')
        frame = await self.frame()
        await self.runtime.native.call('visual_key', {'revision': frame['revision'], 'value': self.adapter.switcher_key})
        frame = await self.frame()
        _, lines = await self.region(frame, 'switcher')
        if not any(self.adapter.switcher_prompt in normalize(l['text']) for l in lines):
            await self.escape()
            raise ValueError('DESTINATION_UNVERIFIED: the quick switcher did not open as expected; nothing was typed')
        frame = await self.frame()
        await self.runtime.native.call('visual_text', {'revision': frame['revision'],
                                                       'value': self.scope.destination.lstrip('#@')})
        frame = await self.frame()
        point, lines = await self.region(frame, 'result', label=self.scope.destination.lstrip('#@'))
        if point is None:
            await self.escape()
            raise ValueError('TARGET_NOT_VISIBLE: no matching destination was proposed; nothing was selected')
        # Uniqueness is judged from a wide band around the proposal, so a second
        # visible row with the same name (other server) stays ambiguous.
        wide = await asyncio.to_thread(ocr_lines, frame, band(frame, point, 140, 300))
        candidates = switcher_matches(wide, self.scope.destination, self.scope.server)
        if len(candidates) != 1:
            await self.escape()
            where = self.scope.destination + (' in ' + self.scope.server if self.scope.server else '')
            raise ValueError('TARGET_AMBIGUOUS: several destinations are named ' + where +
                             '. Tell me which one; nothing was selected or sent.' if candidates else
                             'TARGET_NOT_VISIBLE: no exact destination row for ' + where +
                             ' was found; nothing was selected or sent.')
        if not select:
            await self.escape()
            self.history.append({'operation': 'visual_uniqueness', 'status': 'destination name unique in client'})
            return
        # The model only anchored the search band; the click targets the row that
        # OCR independently verified as the unique exact destination.
        left, top, right, bottom = candidates[0]['box']
        fresh = await self.frame()
        if (fresh['width'], fresh['height']) != (frame['width'], frame['height']):
            raise ValueError('WINDOW_CHANGED: the window changed before selection; nothing was selected')
        target = ((left + right) / 2, (top + bottom) / 2)
        await self.click(fresh, target)
        self.history.append({'operation': 'visual_navigation', 'status': 'selected exact destination row'})

    async def escape(self):
        frame = await self.frame()
        await self.runtime.native.call('visual_key', {'revision': frame['revision'], 'value': 'Escape'})

    async def run(self):
        scope, ctx = self.scope, self.context
        sending = scope.effect == 'send'
        self.progress('Checking the conversation…')
        frame, point = await self.resolve()
        needs_navigation = ctx.destination.state != VERIFIED or scope.server and ctx.workspace.state != VERIFIED
        if not scope.server:
            # Without a server, the name must be unique across the whole client.
            await self.navigate(select=needs_navigation)
            frame, point = await self.resolve()
        elif needs_navigation:
            await self.navigate()
            frame, point = await self.resolve()
        if ctx.draft and ctx.destination.state == VERIFIED:
            raise ValueError('COMPOSER_UNVERIFIED: the composer already contains a draft; it was preserved '
                             'and nothing was typed.')
        blocker = ctx.blocker(scope, sending)
        if blocker:
            raise ValueError(blocker + ': ' + self.describe() + '. No text was entered.')
        if ctx.draft:
            raise ValueError('COMPOSER_UNVERIFIED: the composer already contains a draft; it was preserved '
                             'and nothing was typed.')
        if ctx.draft != '':
            raise ValueError('COMPOSER_UNVERIFIED: the empty composer was not verified. No text was entered.')
        # Focus the verified composer, then enter the literal requested text once.
        self.progress('Typing message…')
        fresh = await self.frame()
        if (fresh['width'], fresh['height']) != (frame['width'], frame['height']):
            raise ValueError('WINDOW_CHANGED: the window changed after verification; no text was entered')
        left, top, right, bottom = ctx.composer.box
        await self.click(fresh, ((left + right) / 2, (top + bottom) / 2))
        fresh = await self.frame()
        await self.runtime.native.call('visual_text', {'revision': fresh['revision'], 'value': scope.content})
        self.progress('Verifying…')
        after = await self.frame()
        typed = await asyncio.to_thread(ocr_lines, after, band(after, point, 32, after['width'] * .4))
        state = composer_state(typed, self.adapter)
        if state[0] != 'draft' or normalize(state[2]) != normalize(scope.content):
            raise ValueError('COMPOSER_UNVERIFIED: the exact requested text was not verified in the composer; '
                             'the draft was left for you to inspect and nothing was sent.')
        self.history.append({'operation': 'visual_draft', 'status': 'exact text verified in composer'})
        if not sending:
            d = self.runtime.desktop
            d.record.status = 'completed'
            d.record.verification = ('Exact requested draft is visible in the verified ' + scope.destination +
                                     ' composer; it was not sent.')
            return d.record.verification
        if self.adapter.submit != 'enter':
            raise PermissionError('READY_TO_SEND: this client has no verified submission contract; the exact draft '
                                  'is ready and was not sent.')
        # Pre-send re-verification of the destination from the conversation header.
        header_point, lines = await self.region(after, 'header')
        header = resolve_exact(lines, scope.destination, 'destination header')
        if header.state != VERIFIED:
            raise ValueError('DESTINATION_UNVERIFIED: the conversation header did not confirm ' + scope.destination +
                             ' before sending; the draft is ready and nothing was sent.')
        del header_point
        self.baseline = await self.echoes(after, point)
        ledger = await self.runtime.reserve_effect(self.grant)
        self.progress('Sending…')
        final = await self.frame()
        if (final['width'], final['height']) != (after['width'], after['height']):
            raise ValueError('WINDOW_CHANGED: the window changed before sending; nothing was sent')
        await self.runtime.native.call('visual_key', {'revision': final['revision'], 'value': 'Enter'})
        return await self.verify_delivery(point, ledger)

    async def verify_delivery(self, point, ledger):
        ctx, scope = self.context, self.scope
        for _ in range(3):
            await asyncio.sleep(.4)
            frame = await self.frame()
            composer = composer_state(await asyncio.to_thread(ocr_lines, frame, band(frame, point, 32, frame['width'] * .4)),
                                      self.adapter)
            echoed = await self.echoes(frame, point)
            if composer[0] == 'empty' and echoed == self.baseline + 1:
                ctx.delivery = 'SENT_UI'
                await asyncio.to_thread(ledger.verified, self.grant)
                d = self.runtime.desktop
                d.record.status = 'completed'
                d.record.verification = ('The exact message appears once as the latest outgoing row in the verified '
                                         + scope.destination + ' conversation and the composer is empty. This is UI '
                                         'evidence of submission, not protocol delivery confirmation.')
                self.history.append({'operation': 'visual_send', 'status': 'submitted once; UI echo observed'})
                return d.record.verification
        ctx.delivery = 'UNCERTAIN'
        raise ValueError('Submission outcome uncertain: Enter was sent once but the outgoing message was not '
                         'verified. It will not be retried; check the conversation.')

    async def echoes(self, frame, point):
        """Exact copies of the requested text in the band just above the composer only."""
        left = max(0, (self.context.composer.box or (0,))[0] - 40)
        lines = await asyncio.to_thread(ocr_lines, frame, (left, point[1] - 150, frame['width'], point[1] - 34))
        return sum(normalize(l['text']) == normalize(self.scope.content) for l in lines)

    def describe(self):
        ctx = self.context
        return ', '.join(f'{name} {layer.state.lower()}' for name, layer in
                         (('destination', ctx.destination), ('workspace', ctx.workspace),
                          ('composer', ctx.composer), ('account', ctx.account)))


def crop_document(frame, documents):
    import base64
    import io
    from PIL import Image
    from .geometry import contains
    candidates = [d for d in documents if contains(frame['window']['bounds'], d.get('bounds'))]
    if len(candidates) != 1:
        raise ValueError('DESTINATION_UNVERIFIED: the page region is not uniquely exposed; nothing was typed')
    x, y, w, h = frame['window']['bounds']
    dx, dy, dw, dh = candidates[0]['bounds']
    sx, sy = frame['width'] / w, frame['height'] / h
    box = (round((dx - x) * sx), round((dy - y) * sy), round((dx + dw - x) * sx), round((dy + dh - y) * sy))
    with Image.open(io.BytesIO(base64.b64decode(frame['png'], validate=True))) as image:
        output = io.BytesIO()
        image.crop(box).save(output, format='PNG')
    return {**frame, 'png': base64.b64encode(output.getvalue()).decode(), 'width': box[2] - box[0],
            'height': box[3] - box[1], 'offset': (box[0], box[1])}


async def visual_message(runtime, grant, pid, application, document_host='', documents=None):
    adapter = adapter_for(application, document_host)
    if adapter is None:
        from .messaging_observation import visual_candidates
        return await visual_candidates(runtime, grant, pid)
    runtime.check_task(grant)
    return await VisualMessaging(runtime, grant, pid, adapter, web=documents is not None).run()
