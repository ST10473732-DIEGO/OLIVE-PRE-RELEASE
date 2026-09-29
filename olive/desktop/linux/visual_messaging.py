"""Visible-UI messaging for clients without usable accessibility semantics.

Where a client's layout is declared (adapter regions), labels are read directly
by OCR in those areas; otherwise GUI-Owl only proposes where a region is. Each proposal is verified from an
independent OCR read of a small crop around it before any input, and every input
is followed by a fresh frame. The destination and content come solely from the
user's request. Enter is sent once, only after destination, workspace, account,
composer and exact draft are verified, and never retried after an uncertain
result. No message pane is read beyond the band just above the composer.
"""
import asyncio
import base64
import io
import time

from ..messaging_context import (AMBIGUOUS, MISMATCH, NOT_VISIBLE, VERIFIED, Layer, MessagingContext, adapter_for, bare,
                                 composer_state, observed_account, resolve_destination, resolve_exact,
                                 echo_rows, exact_segment, rows, segments, switcher_candidates, typed_exactly)
from ..visual_ocr import band, normalize, ocr_lines, ocr_rows, ocr_words, unchanged_outside

SETTLE_READS, SETTLE_SECONDS = 3, .3
OPEN_SECONDS = .8  # The switcher's opening animation; reading earlier wastes a read.
CARET_READS = 2  # Extra reads of the caret-off frame when the first read fails.
CARET_SPAN = .6  # Longer than one caret blink phase.
VERIFY_SPAN, VERIFY_GAP = 1.6, .15  # Typed-text read-back: about three caret blinks.
QUERY_SPAN = 1.5  # Switcher query read-back, across caret blinks and result loading.
SIZES = {'composer': (32, None), 'header': (22, 260), 'server': (20, 150), 'account': (24, 130),
         'switcher': (30, 300)}


# The switcher's text caret sits right after the typed query and OCR often reads
# it as one more glyph ("gen-chat|", "diegol"). Only a single caret-shaped glyph
# is forgiven; the row that is finally selected must still match exactly.
CARET_GLYPHS = '|lI1!'


def typed_query(text, query):
    """The search box shows exactly the typed query (ignoring one trailing caret)."""
    if bare(text) == bare(query):
        return True
    text = str(text).rstrip()
    return len(text) > 1 and text[-1] in CARET_GLYPHS and bare(text[:-1]) == bare(query)


class VisualMessaging:
    def __init__(self, runtime, grant, pid, adapter, web=False):
        self.runtime, self.grant, self.pid, self.adapter, self.web = runtime, grant, pid, adapter, web
        self.scope = grant.scope
        self.context = MessagingContext(runtime.desktop.record.application, adapter.key, self.scope.content,
                                        submit=adapter.submit)
        self.history = runtime.desktop.record.history
        self.started = time.monotonic()

    def record(self, entry):
        self.history.append({**entry, 'at': round(time.monotonic() - self.started, 2)})

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

    async def quiet_frame(self, area):
        """The frame with the least contrast in `area` among frames spanning one caret
        blink (about 0.53 s): a blinking caret adds contrast in either theme, so the
        quietest frame is caret-free. A static screen has no blinking caret.
        """
        frames = [await self.frame()]
        if frames[0].get('static'):
            return frames[0]
        until = time.monotonic() + CARET_SPAN
        while time.monotonic() < until:
            await asyncio.sleep(.2)
            frame = await self.frame()
            if (frame['width'], frame['height']) != (frames[0]['width'], frames[0]['height']):
                return frame
            frames.append(frame)
        return min(reversed(frames), key=lambda f: contrast(f, area(f)))

    async def click(self, frame, point):
        dx, dy = frame.get('offset', (0, 0))
        await self.runtime.native.call('visual_click', {'revision': frame['revision'],
                                                        'point': [point[0] + dx, point[1] + dy]})

    def area(self, frame, role):
        """The client's declared layout area for a role, in frame pixels, or None."""
        fractions = self.adapter.regions.get(role)
        if not fractions:
            return None
        left, top, right, bottom = fractions
        left, top, right, bottom = (left * frame['width'], top * frame['height'], right * frame['width'],
                                    bottom * frame['height'])
        bounds = (frame.get('window') or {}).get('bounds')
        if role == 'composer' and self.adapter.composer_left_logical and bounds and bounds[2] > 0:
            # Fixed-width panels (logical px) beside the composer are not part of it.
            left = max(left, self.adapter.composer_left_logical * frame['width'] / bounds[2])
        return (left, top, right, bottom)

    def composer_area(self, frame, point):
        return self.area(frame, 'composer') or band(frame, point, 32, frame['width'] * .4)

    def read_composer(self, frame, point):
        """The composer area: words where the layout is declared, lines otherwise."""
        if self.area(frame, 'composer'):
            return ocr_words(frame, self.composer_area(frame, point), 3)
        return ocr_lines(frame, self.composer_area(frame, point))

    async def composer_text(self, frame, point):
        """Words from where the verified placeholder text started (buttons to its left
        such as '+' are excluded); whole composer area when that is not known."""
        box = self.context.composer.box
        if box is None:
            return await asyncio.to_thread(ocr_lines, frame, self.composer_area(frame, point))
        # OCR often misses the placeholder's first capital ('essage @diego'), so the
        # typed text can start up to a glyph or two left of where the read began.
        # Two line-heights covers that; a button further left reads as its own word
        # and never joins the exact-text segment.
        margin = max(3, 2 * (box[3] - box[1]))
        return await asyncio.to_thread(ocr_words, frame, (max(0, box[0] - margin), max(0, box[1] - 6), frame['width'],
                                                           min(frame['height'], box[3] + 6)))

    async def region(self, frame, role, label=''):
        """Declared area or model proposal -> bounded crop -> OCR lines (frame pixels)."""
        box = self.area(frame, role)
        if box:
            if role == 'composer':
                lines = await asyncio.to_thread(ocr_words, frame, box, 3)
            else:
                lines = await asyncio.to_thread(ocr_lines, frame, box, 2 if role == 'switcher' else 3)
            point = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            self.diagnose(role, point, lines)
            return point, lines
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
        self.record(entry)

    async def resolve(self):
        frame = await self.frame()
        # The server header is independent of the composer: read both concurrently
        # when the layout is declared (OCR runs in separate processes).
        server_read = (asyncio.ensure_future(self.region(frame, 'server'))
                       if self.scope.server and self.area(frame, 'server') else None)
        point, lines = await self.region(frame, 'composer')
        for attempt in range(CARET_READS + 1):
            if attempt:
                # A blinking caret can hide the placeholder's first letter: re-read
                # the same area on the caret-off frame of the next blink.
                frame = await self.quiet_frame(lambda f: self.composer_area(f, point))
                lines = await asyncio.to_thread(self.read_composer, frame, point)
            composer = composer_state(lines, self.adapter, self.scope.destination)
            if composer[0] == 'empty' or point is None:
                break
            # A draft that is exactly the requested text (for example from an
            # earlier Draft request) is recognised; any other draft is preserved.
            words = lines if self.area(frame, 'composer') else await asyncio.to_thread(
                ocr_words, frame, self.composer_area(frame, point))
            same = exact_segment(words, self.scope.content) if self.scope.content else None
            if same:
                composer = ('draft', '', self.scope.content, same)
                break
        ctx = self.context
        ctx.destination = resolve_destination(self.scope, composer)
        ctx.draft = '' if composer[0] == 'empty' else composer[2] if composer[0] == 'draft' else None
        if composer[0] == 'draft':
            # A draft hides the placeholder; confirm the conversation from its header instead.
            ctx.destination = await self.header_destination(frame)
        ctx.composer = (Layer(VERIFIED, 'composer', composer[3]['box'], 'placeholder/draft read in proposed band')
                        if composer[0] in {'empty', 'draft'} else Layer(evidence='composer band not readable'))
        if self.scope.server:
            anchor, lines = await (server_read or self.region(frame, 'server'))
            ctx.workspace = resolve_exact(lines, self.scope.server, 'workspace', anchor,
                                          self.adapter.header_decorations)
        if not (self.scope.effect == 'send' or self.scope.account):
            self.record({'operation': 'visual_messaging_resolve', 'context': ctx.summary()})
            return frame, point
        composer_box = ctx.composer.box if ctx.composer.state == VERIFIED else None
        if self.adapter.account_first_line and composer_box:
            # The user panel sits beside the composer, at its height, to its left.
            left, top, _, bottom = composer_box
            # Word-level: the avatar beside the name spoils a whole-line reading.
            lines = await asyncio.to_thread(ocr_words, frame, (0, max(0, top - 22), max(8, left - 30), bottom + 8))
            self.diagnose('account', ((left - 30) / 2, top), lines)
        else:
            _, lines = await self.region(frame, 'account')
        observed = observed_account(lines, composer_box, self.adapter.account_first_line)
        if self.scope.account:
            ctx.account = (Layer(VERIFIED, self.scope.account, observed.box, 'requested account visible')
                           if observed.state == VERIFIED and bare(observed.value) == bare(self.scope.account)
                           else Layer(MISMATCH if observed.state == VERIFIED else observed.state,
                                      evidence='requested account not verified'))
        else:
            ctx.account = observed
        self.record({'operation': 'visual_messaging_resolve', 'context': ctx.summary()})
        return frame, point

    async def header_destination(self, frame):
        """The conversation header names exactly the requested destination."""
        header = self.area(frame, 'header')
        if not header:
            anchor, lines = await self.region(frame, 'header')
            return resolve_exact(lines, self.scope.destination, 'destination header', anchor)
        words = await asyncio.to_thread(ocr_words, frame, header, 3)
        self.diagnose('header', ((header[0] + header[2]) / 2, header[3] / 2), words)
        wanted = bare(self.scope.destination)
        # A one-word name is matched as its own word (a channel icon read as a
        # glyph may sit right beside it); longer names as runs of words.
        pieces = [w for w in words if w['confidence'] >= 60] if ' ' not in wanted else segments(words)
        runs = [r for r in pieces if bare(r['text']) == wanted]
        if len(runs) == 1:
            return Layer(VERIFIED, self.scope.destination, runs[0]['box'], 'conversation header run')
        return Layer(AMBIGUOUS if runs else NOT_VISIBLE, evidence='conversation header not exact')

    async def navigate(self, select=True):
        """One bounded quick-switcher attempt; exact unique row or no click.

        With select=False it only proves the destination name is unique in this
        client (the current view alone is not evidence: names repeat across servers).
        """
        self.progress('Finding ' + self.scope.destination + '…')
        frame = await self.frame()
        await self.runtime.native.call('visual_key', {'revision': frame['revision'], 'value': self.adapter.switcher_key})
        # Clients animate the switcher open; re-read (read-only, bounded) until it settles.
        await asyncio.sleep(OPEN_SECONDS)
        for attempt in range(SETTLE_READS + 1):
            if attempt == SETTLE_READS - 1:
                # A switcher left open (possibly holding an old query, which hides the
                # prompt) or just toggled closed: close it with Escape and open a fresh,
                # empty one (bounded to one retry), then re-check before typing anything.
                await self.escape()
                await asyncio.sleep(SETTLE_SECONDS)
                frame = await self.frame()
                await self.runtime.native.call('visual_key', {'revision': frame['revision'],
                                                              'value': self.adapter.switcher_key})
                await asyncio.sleep(OPEN_SECONDS)
            elif attempt:
                await asyncio.sleep(SETTLE_SECONDS)
            frame = await self.frame()
            _, lines = await self.region(frame, 'switcher')
            prompt = [l for l in lines if self.adapter.switcher_prompt in normalize(l['text'])]
            if prompt:
                # Results are listed below the search box (which will hold the typed
                # query). The switcher is centred, so the prompt's first word bounds
                # the dialog on both sides; panels behind it are excluded.
                box = (min(l['box'][0] for l in prompt) - 4, min(l['box'][1] for l in prompt) - 4,
                       max(l['box'][2] for l in prompt) + 4, max(l['box'][3] for l in prompt) + 4)
                first = [w for w in await asyncio.to_thread(ocr_words, frame, box)
                         if normalize(w['text']) == self.adapter.switcher_prompt.split()[0]]
                anchored = len(first) == 1
                left = (first[0]['box'][0] if anchored else min(l['box'][0] for l in prompt)) - 16
                results = self.results = (max(0, left), max(l['box'][3] for l in prompt) + 6,
                                          frame['width'] - max(0, left))
                search_box = box
                break
        else:
            await self.escape()
            raise ValueError('DESTINATION_UNVERIFIED: the quick switcher did not open as expected; nothing was typed')
        await self.type_query(search_box)
        # Results load asynchronously after the query; wait (bounded) for an exact row.
        candidates, point = [], None
        for attempt in range(SETTLE_READS):
            if attempt:
                await asyncio.sleep(SETTLE_SECONDS)
            frame = await self.frame()
            if self.area(frame, 'switcher'):
                # Declared layout: results fill the dialog below the search box.
                point = ((results[0] + results[2]) / 2, results[1] + frame['height'] * .2)
            else:
                point, lines = await self.region(frame, 'result', label=self.scope.destination.lstrip('#@'))
            if point is None:
                continue
            # Uniqueness is judged from a wide band around the proposal, so a second
            # visible row with the same name (other server) stays ambiguous.
            if not anchored:
                anchored = True
                # The typed query starts exactly where the dialog's content starts;
                # it is the most precise anchor for the dialog bounds when readable.
                query = [w for w in await asyncio.to_thread(ocr_words, frame, (0, search_box[1], frame['width'],
                                                                                 search_box[3]))
                         if typed_query(w['text'], self.scope.destination) and w['confidence'] >= 60]
                if len(query) == 1:
                    left = max(0, query[0]['box'][0] - 16)
                    results = self.results = (left, results[1], frame['width'] - left)
            wide = await asyncio.to_thread(ocr_rows, frame, results_band(frame, point, *results), 4, 12,
                                           self.detail_rows(), 11, 3)
            candidates = await self.candidates_in(frame, wide)
            if candidates:
                # One quick confirmation: an unchanged list loaded nothing new;
                # otherwise a late-loading row with the same name triggers a full
                # re-read, so it is still counted.
                await asyncio.sleep(SETTLE_SECONDS)
                again = await self.frame()
                named = len(switcher_candidates(wide, self.scope.destination))
                area = results_band(again, point, *results)
                if await asyncio.to_thread(unchanged_outside, frame, again, (0, 0, 0, 0), area):
                    coarse = wide
                else:
                    coarse = await asyncio.to_thread(ocr_words, again, area)
                if len(switcher_candidates(coarse, self.scope.destination)) > named:
                    frame = again
                    wide = await asyncio.to_thread(ocr_rows, frame, results_band(frame, point, *results), 4, 12,
                                                   self.detail_rows(), 11, 3)
                    candidates = await self.candidates_in(frame, wide)
                break
        if point is None:
            await self.escape()
            raise ValueError('TARGET_NOT_VISIBLE: no matching destination was proposed; nothing was selected')
        if len(candidates) != 1:
            await self.escape()
            where = self.scope.destination + (' in ' + self.scope.server if self.scope.server else '')
            hint = (' Add the username, for example "to ' + self.scope.destination + ' (username)".'
                    if self.scope.destination.startswith('@') and not getattr(self.scope, 'handle', '') else
                    ' Tell me which one.')
            raise ValueError('TARGET_AMBIGUOUS: several destinations are named ' + where + '.' + hint +
                             ' Nothing was selected or sent.' if candidates else
                             'TARGET_NOT_VISIBLE: no exact destination row for ' + where +
                             ' was found; nothing was selected or sent.')
        if not select:
            await self.escape()
            self.record({'operation': 'visual_uniqueness', 'status': 'destination name unique in client'})
            return
        fresh = await self.frame()
        if (fresh['width'], fresh['height']) != (frame['width'], frame['height']):
            raise ValueError('WINDOW_CHANGED: the window changed before selection; nothing was selected')
        listed = rows([w for w in wide if w['confidence'] >= 30], minimum=0)
        chosen = next((i for i, row in enumerate(listed) if _same_row(row, candidates[0])), None)
        if (self.adapter.switcher_enter_opens and chosen is not None and
                await asyncio.to_thread(highlighted_row, frame, listed, results[0], results[2]) == chosen):
            # The verified exact row is the one the client highlights: Enter opens it
            # (keyboard selection; no pointer involved).
            await self.runtime.native.call('visual_key', {'revision': fresh['revision'], 'value': 'Enter'})
            method = 'keyboard'
        else:
            # The click targets the row that OCR independently verified as the
            # unique exact destination.
            left, top, right, bottom = candidates[0]['box']
            await self.click(fresh, ((left + right) / 2, (top + bottom) / 2))
            method = 'pointer'
        # The switcher closes and the conversation opens asynchronously; the
        # destination is only checked once the typed query has left the screen.
        for _ in range(SETTLE_READS):
            await asyncio.sleep(SETTLE_SECONDS)
            after = await self.frame()
            # Only inside the dialog: the opened channel list may show the same name.
            still = await asyncio.to_thread(ocr_words, after, (results[0], search_box[1], results[2], search_box[3]))
            if not any(bare(w['text']) == bare(self.scope.destination) for w in still):
                break
        else:
            await self.escape()
            raise ValueError('DESTINATION_UNVERIFIED: the selected row did not open its conversation; nothing was typed')
        self.record({'operation': 'visual_navigation', 'status': 'selected exact destination row',
                             'method': method,
                             'server_in_switcher': candidates[0]['server'] if self.scope.server else 'not requested'})

    def detail_rows(self):
        """Which coarse rows get a detailed re-read: rows naming the destination when a
        server label must be read; none for a person with a username (the username
        gets its own tight read in candidates_in)."""
        return (lambda words: False) if getattr(self.scope, 'handle', '') else self.names_destination

    def names_destination(self, words):
        """A coarse result row that may name the destination (then re-read in detail)."""
        wanted = bare(self.scope.destination)
        return any(wanted and wanted in bare(w['text']) for w in words)

    async def type_query(self, search_box):
        """Type the destination into the switcher and confirm it appears there.

        A client can drop keystrokes while its switcher is still taking focus. While
        the empty prompt is still shown nothing was entered, so the query is typed
        once more (bounded); anything else in the box stops the task.
        """
        query = self.scope.destination.lstrip('#@')
        area = (self.results[0], search_box[1], self.results[2], search_box[3])
        prompt_word = self.adapter.switcher_prompt.split()[0]
        for attempt in range(2):
            frame = await self.frame()
            await self.runtime.native.call('visual_text', {'revision': frame['revision'], 'value': query})
            empty, strangers = False, 0
            deadline = time.monotonic() + QUERY_SPAN
            while True:
                frame = await self.frame()  # A frame after the typing (the helper waits for one).
                words = [w for w in await asyncio.to_thread(ocr_words, frame, area, 3) if w['confidence'] >= 60]
                if any(typed_query(w['text'], query) for w in words):
                    self.record({'operation': 'visual_query', 'status': 'query visible', 'attempt': attempt + 1})
                    return
                # A blinking caret read on its own ('|', 'l') is neither the prompt nor other text.
                words = [w for w in words if bare(w['text']) and w['text'].strip() not in CARET_GLYPHS]
                empty = any(prompt_word in normalize(w['text']).split() for w in words)
                partial = any(bare(query).startswith(bare(w['text'])) for w in words)
                # Other text twice in a row (not a frame caught mid-render) stops the task.
                strangers = strangers + 1 if words and not empty and not partial else 0
                if strangers >= 2 or time.monotonic() >= deadline:
                    break
                await asyncio.sleep(VERIFY_GAP)
            if not empty:
                break
        await self.escape()
        raise ValueError('DESTINATION_UNVERIFIED: the destination name did not appear in the quick switcher; '
                         'nothing was selected or sent')

    async def candidates_in(self, frame, words):
        """Selectable rows: exact name (and server); with a username, each row whose
        display name matches has the text right after the name re-read on its own
        tight line crop (small grey usernames), and must equal the username."""
        handle = getattr(self.scope, 'handle', '')
        if not handle:
            return self.row_candidates(words)
        wanted = bare(self.scope.destination).split()
        wanted_handle = normalize(handle).lstrip('@').split()
        confirmed = []
        for row in switcher_candidates(words, self.scope.destination):
            names = [w for w in row['lines'] if bare(w['text']) == wanted[-1]]
            if not names:
                continue
            name = names[0]
            crop = (name['box'][2] + 2, row['box'][1] - 4, min(frame['width'], name['box'][2] + 200), row['box'][3] + 4)
            try:
                read = await asyncio.to_thread(ocr_words, frame, crop, 4, 7)
            except ValueError:
                continue
            tokens = [normalize(w['text']).lstrip('@') for w in sorted(read, key=lambda w: w['box'][0])
                      if w['confidence'] >= 60 and normalize(w['text'])]
            if tokens[:len(wanted_handle)] == wanted_handle:
                confirmed.append(dict(row, server='not requested'))
        self.record({'operation': 'visual_rows', 'display_name_rows': len(switcher_candidates(words, self.scope.destination)),
                     'username_confirmed': len(confirmed)})
        return confirmed

    def row_candidates(self, words):
        rows_ = self._row_candidates(words)
        # States only (never names): how each exact-name row's server label was judged.
        named = switcher_candidates(words, self.scope.destination, self.scope.server, self.label_from(),
                                    getattr(self.scope, 'handle', ''))
        self.record({'operation': 'visual_rows', 'exact_name_rows': [r['server'] for r in named],
                     'label_from': self.label_from()})
        return rows_

    def label_from(self):
        results = getattr(self, 'results', None)
        return (results[0] + results[2]) / 2 if self.adapter.switcher_label_right and results else None

    def _row_candidates(self, words):
        """Exact-name rows not contradicting the requested server.

        The switcher only navigates. A server label too small to read there does
        not disqualify the single exact row: after selection the destination and
        server must still read exactly in the opened conversation before any text
        is entered. A confidently read different server always disqualifies.
        """
        return [row for row in switcher_candidates(words, self.scope.destination, self.scope.server, self.label_from(),
                                                   getattr(self.scope, 'handle', ''))
                if row['server'] != 'other']

    async def escape(self):
        frame = await self.frame()
        await self.runtime.native.call('visual_key', {'revision': frame['revision'], 'value': 'Escape'})

    async def run(self):
        scope, ctx = self.scope, self.context
        sending = scope.effect == 'send'
        # Go straight to the named destination (the switcher also proves the name is
        # unique across the client), then verify the opened conversation once.
        await self.navigate()
        self.progress('Checking the conversation…')
        frame, point = await self.resolve()
        if scope.effect == 'go':
            # Navigation only: verify where we are; never touch the composer.
            if ctx.destination.state != VERIFIED:
                raise ValueError(('TARGET_AMBIGUOUS' if ctx.destination.state == AMBIGUOUS else 'DESTINATION_UNVERIFIED') +
                                 ': ' + self.describe() + '. Nothing was typed.')
            if scope.server and ctx.workspace.state != VERIFIED:
                raise ValueError('DESTINATION_UNVERIFIED: ' + self.describe() + '. Nothing was typed.')
            self.record({'operation': 'visual_navigate', 'status': 'destination verified'})
            d = self.runtime.desktop
            d.record.status = 'completed'
            d.record.verification = ('Opened and verified ' + scope.destination + (' in ' + scope.server if scope.server else '') +
                                     '. Nothing was typed and nothing was sent.')
            return d.record.verification
        prepared = bool(ctx.draft) and normalize(ctx.draft) == normalize(scope.content)
        if ctx.draft and not prepared and ctx.destination.state == VERIFIED:
            raise ValueError('COMPOSER_UNVERIFIED: the composer already contains a draft; it was preserved '
                             'and nothing was typed.')
        blocker = ctx.blocker(scope, sending)
        if blocker:
            raise ValueError(blocker + ': ' + self.describe() + '. No text was entered' +
                             ('; the existing draft was preserved.' if ctx.draft else '.'))
        if ctx.draft and not prepared:
            raise ValueError('COMPOSER_UNVERIFIED: the composer already contains a draft; it was preserved '
                             'and nothing was typed.')
        if ctx.draft != '' and not prepared:
            raise ValueError('COMPOSER_UNVERIFIED: the empty composer was not verified. No text was entered.')
        if prepared:
            # The exact requested text is already drafted in the verified conversation.
            self.record({'operation': 'visual_draft', 'status': 'exact requested text already in composer'})
            if not sending:
                d = self.runtime.desktop
                d.record.status = 'completed'
                d.record.verification = ('The exact requested draft is already in the verified ' + scope.destination +
                                         ' composer; nothing was typed and it was not sent.')
                return d.record.verification
            return await self.submit(frame, frame, point)
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
        # The caret blinks right after the typed text and OCR can read it as one
        # more glyph ("1|" as "{"). Every read is a real observation of the
        # finished input, so reads continue across several blinks until one frame
        # shows exactly the requested text (and nothing else) or time runs out.
        deadline = time.monotonic() + VERIFY_SPAN
        while True:
            after = await self.frame()
            typed = await self.composer_text(after, point)
            self.diagnose('typed', point, typed)
            verified = typed_exactly(typed, scope.content, self.adapter)
            if verified or time.monotonic() >= deadline:
                break
            await asyncio.sleep(VERIFY_GAP)
        if not verified:
            raise ValueError('COMPOSER_UNVERIFIED: the exact requested text was not verified in the composer; '
                             'the draft was left for you to inspect and nothing was sent.')
        self.record({'operation': 'visual_draft', 'status': 'exact text verified in composer'})
        if sending:
            return await self.submit(frame, after, point)
        d = self.runtime.desktop
        d.record.status = 'completed'
        d.record.verification = ('Exact requested draft is visible in the verified ' + scope.destination +
                                 ' composer; it was not sent.')
        return d.record.verification

    async def submit(self, frame, after, point):
        """Send the exact verified draft once: `frame` is the verified conversation,
        `after` the frame showing the exact draft."""
        scope = self.scope
        if self.adapter.submit != 'enter':
            raise PermissionError('READY_TO_SEND: this client has no verified submission contract; the exact draft '
                                  'is ready and was not sent.')
        # Pre-send re-verification that the destination has not changed: either
        # nothing outside the composer changed since the verified observation, or
        # the conversation header names the exact destination.
        composer_band = self.composer_area(after, point)
        if await asyncio.to_thread(unchanged_outside, frame, after, composer_band):
            self.record({'operation': 'visual_presend', 'status': 'only the composer changed since verification'})
        else:
            header = await self.header_destination(after)
            if header.state != VERIFIED:
                raise ValueError('DESTINATION_UNVERIFIED: the conversation changed or its header did not confirm ' +
                                 scope.destination + ' before sending; the draft is ready and nothing was sent.')
            self.record({'operation': 'visual_presend', 'status': 'destination header re-read exactly'})
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
        for _ in range(4):
            await asyncio.sleep(.25)
            # Whether the text left the composer does not depend on the caret.
            frame = await self.frame()
            words = await asyncio.to_thread(self.read_composer, frame, point)
            # Delivery means the exact text left the composer (placeholder or not;
            # a caret beside the placeholder may garble it) and appears once more in
            # the conversation just above.
            cleared = composer_state(words, self.adapter)[0] == 'empty' or exact_segment(words, scope.content) is None
            echoed = await self.echoes(frame, point)
            self.record({'operation': 'visual_delivery_check', 'cleared': cleared, 'echoed': echoed,
                         'baseline': self.baseline})
            if cleared and echoed == self.baseline + 1:
                ctx.delivery = 'SENT_UI'
                await asyncio.to_thread(ledger.verified, self.grant)
                d = self.runtime.desktop
                d.record.status = 'completed'
                d.record.verification = ('The exact message appears once as the latest outgoing row in the verified '
                                         + scope.destination + ' conversation and has left the composer. This is UI '
                                         'evidence of submission, not protocol delivery confirmation.')
                self.record({'operation': 'visual_send', 'status': 'submitted once; UI echo observed'})
                return d.record.verification
        ctx.delivery = 'UNCERTAIN'
        raise ValueError('Submission outcome uncertain: Enter was sent once but the outgoing message was not '
                         'verified. It will not be retried; check the conversation.')

    async def echoes(self, frame, point):
        """Exact copies of the requested text in the band just above the composer only."""
        box = self.context.composer.box or (0, point[1] - 14, 0, point[1])
        left = max(0, box[0] - 40)
        words = await asyncio.to_thread(ocr_words, frame, (left, box[1] - 120, frame['width'], box[1] - 4), 3)
        account = self.context.account.value if self.context.account.state == VERIFIED else ''
        return len(echo_rows(words, self.scope.content, account))

    def describe(self):
        ctx = self.context
        return ', '.join(f'{name} {layer.state.lower()}' for name, layer in
                         (('destination', ctx.destination), ('workspace', ctx.workspace),
                          ('composer', ctx.composer), ('account', ctx.account)))


def contrast(frame, box):
    """Total absolute deviation from the median luminance inside `box` (0 if unreadable)."""
    from PIL import Image, ImageStat
    try:
        with Image.open(io.BytesIO(base64.b64decode(frame['png'], validate=True))) as image:
            gray = image.convert('L').crop(tuple(int(v) for v in box))
    except Exception:
        return 0
    median = ImageStat.Stat(gray).median[0]
    return sum(abs(v - median) for v in gray.getdata())


def _same_row(a, b):
    return a['box'][1] < b['box'][3] and b['box'][1] < a['box'][3]


def highlighted_row(frame, listed, left, right):
    """Index of the one row drawn with a clearly brighter background, or None.

    The median luminance of each row's strip is its background (text pixels are a
    minority). Only a clear margin over every other row counts as highlighted.
    """
    from PIL import Image, ImageStat
    try:
        with Image.open(io.BytesIO(base64.b64decode(frame['png'], validate=True))) as image:
            gray = image.convert('L')
    except Exception:
        return None
    levels = []
    for row in listed:
        top, bottom = max(0, int(row['box'][1]) - 4), min(gray.height, int(row['box'][3]) + 4)
        if bottom - top < 4:
            return None
        levels.append(ImageStat.Stat(gray.crop((max(0, int(left)), top, min(gray.width, int(right)), bottom))).median[0])
    order = sorted(range(len(levels)), key=lambda i: -levels[i])
    if len(order) < 2 or levels[order[0]] - levels[order[1]] < 4:
        return None
    return order[0]


def results_band(frame, point, left, top, right):
    """Switcher results: below the search box, within the dialog's horizontal bounds."""
    _, _, _, bottom = band(frame, point, 140)
    return (max(0, left), max(0, top), max(left + 8, min(frame['width'], right)), max(top + 8, bottom))


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
