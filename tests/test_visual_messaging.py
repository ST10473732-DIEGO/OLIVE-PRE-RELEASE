"""Visible-UI messaging: layer resolution and the executor against a simulated client."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from olive.desktop.messaging_context import (AMBIGUOUS, MISMATCH, VERIFIED, adapter_for, composer_state,
                                             resolve_destination, resolve_exact, switcher_matches)
from olive.desktop.task_authority import TaskScope, direct_scope
from olive.desktop.linux import visual_messaging


def line(text, top, left=10, confidence=95):
    return {'text': text, 'box': (left, top, left + 10 * len(text), top + 14), 'confidence': confidence}


class LayerTests(unittest.TestCase):
    adapter = adapter_for('Discord')

    def test_adapters_are_declared_not_inferred(self):
        self.assertEqual(adapter_for('discord').key, 'discord')
        self.assertEqual(adapter_for('Firefox', 'discord.com').key, 'discord')
        self.assertIsNone(adapter_for('Firefox', 'discord.com.evil.example'))
        self.assertIsNone(adapter_for('Kate'))

    def test_composer_placeholder_binds_destination_and_empty_draft(self):
        scope = TaskScope('Discord', 'send', 'hello', '#general', server='Osprey Workshop')
        state = composer_state([line('Message #general', 100)], self.adapter)
        self.assertEqual(state[0], 'empty')
        self.assertEqual(resolve_destination(scope, state).state, VERIFIED)
        other = composer_state([line('Message #releases', 100)], self.adapter)
        self.assertEqual(resolve_destination(scope, other).state, MISMATCH)
        dm = composer_state([line('Message @general', 100)], self.adapter)
        self.assertEqual(resolve_destination(scope, dm).state, MISMATCH)
        draft = composer_state([line('half written reply', 100)], self.adapter)
        self.assertEqual(draft[0], 'draft')
        low = composer_state([line('Message #general', 100, confidence=20)], self.adapter)
        self.assertNotEqual(low[0], 'empty')

    def test_duplicate_and_hierarchical_names(self):
        self.assertEqual(resolve_exact([line('Osprey Workshop', 10)], 'Osprey Workshop', 'workspace').state, VERIFIED)
        self.assertEqual(resolve_exact([line('Heron Lab', 10)], 'Osprey Workshop', 'workspace').state, MISMATCH)
        self.assertEqual(resolve_exact([line('# general', 10), line('general', 40)], '#general', 'x').state, AMBIGUOUS)
        results = [line('# general', 100), line('Osprey Workshop', 100, left=300),
                   line('# general', 140), line('Heron Lab', 140, left=300), line('# general-chat', 180)]
        self.assertEqual(len(switcher_matches(results, '#general')), 2)
        self.assertEqual(len(switcher_matches(results, '#general', 'Heron Lab')), 1)
        self.assertEqual(len(switcher_matches(results, '#general', 'Other')), 0)

    def test_request_scopes_for_native_server_and_official_web_route(self):
        native = direct_scope('Send "hello" to #general in Heron Lab in Visual Messenger')
        self.assertEqual((native.application, native.server, native.predicate), ('Visual Messenger', 'Heron Lab', ''))
        web = direct_scope('Draft "hello" to #general in My Server in Discord in Firefox')
        self.assertEqual((web.application, web.server, web.predicate), ('Firefox', 'My Server', 'discord.com'))


class Client:
    """A minimal simulated chat client driven only through the visual worker calls."""
    CHANNELS = [('Osprey Workshop', 'general'), ('Osprey Workshop', 'releases'), ('Heron Lab', 'general')]

    def __init__(self, current=0, draft='', account='fixture-owner', echo=True, panel_beside_composer=False):
        self.current, self.drafts, self.account, self.echo = current, {current: draft}, account, echo
        self.panel = panel_beside_composer  # Discord-like: the user panel sits left of the composer.
        self.switcher, self.query, self.focus = False, '', False
        self.sent, self.calls = [], []

    def lines(self, role):
        server, channel = self.CHANNELS[self.current]
        draft = self.drafts.get(self.current, '')
        if role == 'composer':
            left = 300 if self.panel else 10
            return [line(draft, 600, left=left)] if draft else [line('Message #' + channel, 600, left=left)]
        if role == 'panel':
            return [line(self.account, 596), line('Online', 612, confidence=80)]
        if role == 'server':
            return [line(server, 20)]
        if role == 'account':
            return [line(self.account, 660)]
        if role == 'header':
            return [line('# ' + channel, 20)]
        if role == 'switcher':
            if getattr(self, 'toggles', False) and not self.switcher:
                return []  # Closed: no prompt on screen.
            return [line(self.query or 'Where would you like to go?', 150, left=300)]
        if role == 'wide':
            rows = [(s, c) for s, c in self.CHANNELS if not self.query or self.query in c]
            return [x for i, (s, c) in enumerate(rows)
                    for x in (line('# ' + c, 200 + 40 * i), line(s, 200 + 40 * i, left=300))]
        if role == 'above':
            return [line(text, 540) for s, c, text in self.sent[-1:] if (s, c) == (server, channel)]
        return []

    async def call(self, method, args=None, timeout=None):
        self.calls.append((method, dict(args or {})))
        if method == 'visual_observe':
            return {'png': '', 'width': 1000, 'height': 680, 'revision': str(len(self.calls)), 'window': {}}
        if method == 'visual_key':
            if args['value'] == 'ctrl+k':
                # Real clients toggle the switcher with its shortcut.
                self.switcher, self.query = (not self.switcher) if getattr(self, 'toggles', False) else True, ''
            elif args['value'] == 'Escape':
                self.switcher = False
            elif args['value'] == 'Enter' and self.switcher:
                # The switcher opens its highlighted (first) matching result.
                rows = [i for i, (s, c) in enumerate(self.CHANNELS) if not self.query or self.query in c]
                self.current, self.switcher, self.focus = rows[0], False, True
            elif args['value'] == 'Enter' and self.focus and self.drafts.get(self.current):
                if self.echo:
                    self.sent.append((*self.CHANNELS[self.current], self.drafts[self.current]))
                    self.drafts[self.current] = ''
            return {'dispatched': True}
        if method == 'visual_text':
            if self.switcher and getattr(self, 'drop_typing', 0):
                self.drop_typing -= 1       # Keystrokes lost while the switcher takes focus.
                return {'dispatched': True}
            if self.switcher:
                self.query = args['value']
            elif self.focus:
                self.drafts[self.current] = self.drafts.get(self.current, '') + args['value']
            return {'dispatched': True}
        if method == 'visual_click':
            x, y = args['point']
            if self.switcher:
                rows = [i for i, (s, c) in enumerate(self.CHANNELS) if not self.query or self.query in c]
                index = int((y - 200) // 40)
                self.current, self.switcher, self.focus = rows[index], False, True
            elif y >= 590:
                self.focus = True
            return {'dispatched': True}
        raise AssertionError(method)


class ExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def run_task(self, request, client, unchanged=False, open_reads=0, adapter=None, highlight=None):
        scope = direct_scope(request)
        record = SimpleNamespace(history=[], application=scope.application, current_action='', status='running',
                                 verification='')
        reserved = []

        class Ledger:
            def verified(self, grant):
                reserved.append('verified')

        async def reserve(grant):
            reserved.append('reserved')
            return Ledger()
        roles = {'composer': (500, 600), 'server': (150, 20), 'account': (150, 660), 'header': (400, 20),
                 'switcher': (500, 150)}

        self.model_calls = 0
        test = self

        class Gui:
            async def action(self, frame, prompt):
                test.model_calls += 1
                for role, key in (('composer', 'message input'), ('header', 'title of the current'),
                                  ('server', 'server or workspace'), ('account', 'own name'),
                                  ('switcher', 'quick switcher')):
                    if key in prompt:
                        x, y = roles[role]
                        return {'action': 'left_click', 'coordinate': [x, y * 1000 / 680]}
                wanted = prompt.split('named ')[1].rstrip('.')
                rows = [i for i, (s, c) in enumerate(client.CHANNELS) if not client.query or client.query in c]
                index = next(i for i, r in enumerate(rows) if client.CHANNELS[r][1] == wanted)
                return {'action': 'left_click', 'coordinate': [100, (207 + 40 * index) * 1000 / 680]}
        desktop = SimpleNamespace(record=record, publish=lambda: None, s=SimpleNamespace(publish=lambda *a: None))
        runtime = SimpleNamespace(desktop=desktop, gui=Gui(), native=SimpleNamespace(call=client.call), chat_id=None,
                                  check_task=lambda grant: None, reserve_effect=reserve)
        grant = SimpleNamespace(scope=scope)

        def ocr(frame, box, *options):
            left, top, right, bottom = box
            if client.panel and left == 0 and right <= 300 and top < 600 < bottom:
                return client.lines('panel')
            if top <= 600 <= bottom and right - left > 600 and bottom - top < 40:
                return client.lines('composer')  # The composer's text strip.
            middle = (top + bottom) / 2
            if bottom - top > 150:  # the switcher results read
                return client.lines('wide')
            center = (left + right) / 2
            for role, (x, y) in roles.items():
                if abs(middle - y) < 3 and (right - left > 900 or abs(center - x) < 3):
                    return client.lines(role)
            if bottom < 600 and top > 400:
                return client.lines('above')
            return []
        remaining, checked = {'open': open_reads}, []
        self.closing_checks = checked

        def words(frame, box, scale=4):
            # The search box row after selection: the query stays visible while the
            # switcher is (simulated as) still closing.
            if box[3] - box[1] < 40 and box[1] < 200 and client.switcher and not client.focus:
                return client.lines('switcher')  # The search box: typed query or empty prompt.
            closing = box[3] - box[1] < 40 and box[1] < 200 and client.focus
            if closing:
                checked.append(box)
            if closing and remaining['open']:
                remaining['open'] -= 1
                return [{'text': client.query or 'x', 'confidence': 90, 'box': (20, box[1], 90, box[3])}]
            return ocr(frame, box)
        with patch.object(visual_messaging, 'ocr_lines', ocr), \
                patch.object(visual_messaging, 'ocr_words', words), \
                patch.object(visual_messaging, 'ocr_rows', lambda frame, box, *options: ocr(frame, box)), \
                patch.object(visual_messaging.asyncio, 'sleep',
                                                                             return_value=None), \
                patch.object(visual_messaging, 'unchanged_outside', lambda before, after, box, within=None: unchanged if within is None else False):
            if adapter is None:
                outcome = await visual_messaging.visual_message(runtime, grant, 1, scope.application)
            else:
                with patch.object(visual_messaging, 'highlighted_row', lambda frame, listed, left, right: highlight(listed)):
                    outcome = await visual_messaging.VisualMessaging(runtime, grant, 1, adapter).run()
        return outcome, reserved

    def keys(self, client, value):
        return [c for c in client.calls if c == ('visual_key', {'revision': c[1].get('revision'), 'value': value})]

    async def test_navigates_hierarchy_types_once_and_verifies_send(self):
        client = Client(current=0)
        outcome, reserved = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Heron Lab', 'general', 'field update')])
        self.assertEqual(len(self.keys(client, 'Enter')), 1)
        self.assertEqual(reserved, ['reserved', 'verified'])

    async def test_draft_only_never_presses_enter(self):
        client = Client(current=0)
        outcome, reserved = await self.run_task('Draft "later" to #releases in Osprey Workshop in Visual Messenger', client)
        self.assertIn('not sent', outcome)
        self.assertEqual(client.sent, [])
        self.assertFalse(self.keys(client, 'Enter'))
        self.assertEqual(reserved, [])

    async def test_ambiguous_destination_selects_and_types_nothing(self):
        client = Client(current=1)
        with self.assertRaisesRegex(ValueError, 'TARGET_AMBIGUOUS'):
            await self.run_task('Send "hi" to general in Visual Messenger', client)
        self.assertFalse([c for c in client.calls if c[0] == 'visual_click'])
        self.assertEqual(client.sent, [])

    def no_message_effect(self, client):
        self.assertEqual(client.sent, [])
        self.assertFalse(self.keys(client, 'Enter'))
        self.assertFalse([c for c in client.calls if c[0] == 'visual_click'])
        self.assertFalse(any(client.drafts.values()))

    async def test_channel_without_server_asks_first(self):
        client = Client(current=1)
        with self.assertRaisesRegex(ValueError, 'TARGET_AMBIGUOUS'):
            await self.run_task('Send "hi" to #general in Visual Messenger', client)
        self.no_message_effect(client)

    async def test_current_view_match_is_not_enough_when_name_repeats(self):
        client = Client(current=2)  # Already showing Heron Lab #general.
        with self.assertRaisesRegex(ValueError, 'TARGET_AMBIGUOUS'):
            await self.run_task('Send "status ok" to general in Visual Messenger', client)
        self.no_message_effect(client)

    async def test_globally_unique_name_needs_no_server(self):
        client = Client(current=0)
        outcome, _ = await self.run_task('Send "notes" to #releases in Visual Messenger', client)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Osprey Workshop', 'releases', 'notes')])

    async def test_existing_draft_is_preserved(self):
        client = Client(current=0, draft='unrelated draft')
        with self.assertRaisesRegex(ValueError, 'COMPOSER_UNVERIFIED'):
            await self.run_task('Send "hi" to #general in Osprey Workshop in Visual Messenger', client)
        self.assertEqual(client.drafts[0], 'unrelated draft')
        # Only the destination name was typed (into the switcher); never the message.
        self.assertEqual([c[1]['value'] for c in client.calls if c[0] == 'visual_text'], ['general'])

    async def test_requested_account_must_match_visible_account(self):
        client = Client(current=0, account='someone-else')
        with self.assertRaisesRegex(ValueError, 'ACCOUNT_UNVERIFIED'):
            await self.run_task('Send "hi" to #general in Osprey Workshop in Visual Messenger using account fixture-owner',
                                client)
        self.assertEqual([c[1]['value'] for c in client.calls if c[0] == 'visual_text'], ['general'])
        self.assertFalse(any(client.drafts.values()))

    async def test_navigate_only_verifies_destination_and_never_types_a_message(self):
        client = Client(current=0)
        outcome, reserved = await self.run_task('Open Visual Messenger and go to #releases in Osprey Workshop', client)
        self.assertIn('Nothing was typed and nothing was sent', outcome)
        self.assertEqual(client.CHANNELS[client.current], ('Osprey Workshop', 'releases'))
        self.assertEqual([c[1]['value'] for c in client.calls if c[0] == 'visual_text'], ['releases'])
        self.assertEqual(client.sent, [])
        self.assertFalse(any(client.drafts.values()))
        self.assertEqual(reserved, [], 'navigation reserves no send effect')

    async def test_navigate_only_ambiguous_destination_selects_nothing(self):
        client = Client(current=1)
        with self.assertRaisesRegex(ValueError, 'TARGET_AMBIGUOUS'):
            await self.run_task('Go to general in Visual Messenger', client)
        self.no_message_effect(client)

    async def test_navigate_only_preserves_an_existing_draft(self):
        client = Client(current=0, draft='unrelated draft')
        outcome, _ = await self.run_task('Open Visual Messenger and go to #general in Osprey Workshop', client)
        self.assertIn('Nothing was typed', outcome)
        self.assertEqual(client.drafts[0], 'unrelated draft')
        self.assertEqual(client.sent, [])

    def test_navigate_request_cannot_smuggle_a_message(self):
        for request in ('Open Discord and go to #general and send hi', 'Open Discord and go to #general then type hello',
                        'Go to #general in X in Discord; send "hi"'):
            with self.assertRaises(ValueError):
                direct_scope(request)
        scope = direct_scope('Open Discord and go to #gen-chat in D SERVER')
        self.assertEqual((scope.effect, scope.destination, scope.server, scope.content), ('go', '#gen-chat', 'D SERVER', ''))
        scope = direct_scope('Open Discord and go to the general channel on my RaceDay server')
        self.assertEqual((scope.effect, scope.destination, scope.server), ('go', '#general', 'RaceDay'))
        with self.assertRaisesRegex(ValueError, 'Which server'):
            direct_scope('Open Discord and go to the general channel on my server')

    async def test_uncertain_submission_is_never_retried(self):
        client = Client(current=0, echo=False)
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            await self.run_task('Send "once" to #general in Osprey Workshop in Visual Messenger', client)
        self.assertEqual(len(self.keys(client, 'Enter')), 1)


if __name__ == '__main__':
    unittest.main()


class ComposerClassificationTests(unittest.TestCase):
    def test_many_unrelated_rows_are_not_a_composer(self):
        adapter = adapter_for('Discord')
        rows = [line('Friends', 10), line('Nitro', 40), line('Shop', 70), line('Direct Messages', 100)]
        self.assertEqual(composer_state(rows, adapter)[0], 'unknown')


class AccountBandTests(unittest.TestCase):
    def test_clipped_composer_text_is_not_account_identity(self):
        from olive.desktop.messaging_context import observed_account
        composer = (250, 420, 420, 440)
        rows = [line('Mess', 424, left=250), line('fixture-owner', 430, left=40)]
        self.assertEqual(observed_account(rows).state, AMBIGUOUS)
        account = observed_account(rows, composer)
        self.assertEqual((account.state, account.value), (VERIFIED, 'fixture-owner'))
        rows.append(line('second-owner', 450, left=40))
        self.assertEqual(observed_account(rows, composer).state, AMBIGUOUS)


class PresendIdentityTests(unittest.IsolatedAsyncioTestCase):
    """A misread header cannot block a send whose surroundings are provably unchanged, nor allow a changed one."""
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys

    async def test_unchanged_surroundings_confirm_the_verified_destination(self):
        client = Client(current=0)
        client.lines = (lambda original: lambda role: [line('# fleld-notes', 20)] if role == 'header'
                        else original(role))(client.lines)
        outcome, reserved = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger',
                                                client, unchanged=True)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Heron Lab', 'general', 'field update')])
        self.assertEqual(reserved, ['reserved', 'verified'])

    async def test_changed_surroundings_need_the_exact_header(self):
        client = Client(current=0)
        client.lines = (lambda original: lambda role: [line('# fleld-notes', 20)] if role == 'header'
                        else original(role))(client.lines)
        with self.assertRaisesRegex(ValueError, 'DESTINATION_UNVERIFIED'):
            await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertEqual(client.sent, [])
        self.assertFalse(self.keys(client, 'Enter'))


class UnchangedOutsideTests(unittest.TestCase):
    def frame(self, draw=None):
        import base64, io
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (200, 120), (40, 42, 48))
        ImageDraw.Draw(image).text((10, 10), '# general', fill=(230, 230, 230))
        if draw:
            draw(ImageDraw.Draw(image))
        data = io.BytesIO()
        image.save(data, format='PNG')
        return {'png': base64.b64encode(data.getvalue()).decode(), 'width': 200, 'height': 120}

    def test_only_changes_inside_the_region_are_ignored(self):
        from olive.desktop.visual_ocr import unchanged_outside
        composer = (0, 90, 200, 120)
        before = self.frame()
        typed = self.frame(lambda d: d.text((10, 100), 'hello', fill=(255, 255, 255)))
        self.assertTrue(unchanged_outside(before, typed, composer))
        switched = self.frame(lambda d: d.rectangle((10, 10, 80, 22), fill=(40, 42, 48)))
        self.assertFalse(unchanged_outside(before, switched, composer))
        self.assertFalse(unchanged_outside(before, dict(typed, width=201), composer))


class SettleTests(unittest.IsolatedAsyncioTestCase):
    """Animated switchers and asynchronously loaded results get bounded, read-only re-reads."""
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys

    def delay(self, client, role, reads):
        original, seen = client.lines, {'n': 0}
        def lines(r):
            if r == role and seen['n'] < reads:
                seen['n'] += 1
                return []
            return original(r)
        client.lines = lines

    async def test_switcher_opening_on_a_later_read_still_navigates(self):
        client = Client(current=0)
        self.delay(client, 'switcher', 1)
        outcome, _ = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Heron Lab', 'general', 'field update')])

    async def test_switcher_that_never_opens_types_nothing(self):
        client = Client(current=0)
        self.delay(client, 'switcher', 99)
        with self.assertRaisesRegex(ValueError, 'quick switcher did not open'):
            await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertEqual(client.sent, [])
        self.assertFalse([c for c in client.calls if c[0] == 'visual_text'])

    async def test_duplicate_loading_late_is_still_ambiguous(self):
        client = Client(current=1)
        original, seen = client.lines, {'n': 0}
        def lines(role):
            rows = original(role)
            if role == 'wide':
                seen['n'] += 1
                if seen['n'] == 1:
                    return rows[:2]  # Only the first 'general' row has rendered yet.
            return rows
        client.lines = lines
        with self.assertRaisesRegex(ValueError, 'TARGET_AMBIGUOUS'):
            await self.run_task('Send "hi" to general in Visual Messenger', client)
        self.assertEqual(client.sent, [])


class SwitcherRowTests(unittest.TestCase):
    """Rows as Discord lists them: icon, channel, category, right-aligned server (word-level OCR)."""

    def words(self, top, *items):
        return [{'text': text, 'confidence': conf, 'box': (left, top, left + 8 * len(text), top + 12)}
                for text, conf, left in items]

    def test_category_between_channel_and_server_is_ignored(self):
        row = self.words(184, ('3?', 20, 200), ('gen-chat', 86, 223), ('TEXT', 12, 280), ('CHANNELS', 5, 310),
                         ('D', 88, 590), ('SERVER', 90, 602))
        decorated = self.words(208, ('#', 91, 200), ('®gen-chat+"+', 44, 223), ('CHAT', 30, 300),
                               ('perrito', 90, 560), ('boni', 78, 600))
        self.assertEqual(len(switcher_matches(row + decorated, '#gen-chat', 'D SERVER')), 1)
        self.assertEqual(len(switcher_matches(row + decorated, '#gen-chat')), 1)
        self.assertEqual(switcher_matches(row, '#gen-chat', 'C SERVER'), [])

    def test_a_readable_prefix_word_is_never_skipped(self):
        row = self.words(184, ('#', 91, 200), ('old', 50, 214), ('gen-chat', 86, 240), ('D', 88, 590), ('SERVER', 90, 602))
        self.assertEqual(switcher_matches(row, '#gen-chat', 'D SERVER'), [])

    def test_server_words_must_be_read_confidently(self):
        row = self.words(184, ('#', 91, 200), ('gen-chat', 86, 223), ('D', 88, 590), ('SERVER', 40, 602))
        self.assertEqual(switcher_matches(row, '#gen-chat', 'D SERVER'), [])

    def test_results_band_starts_below_the_search_box(self):
        from olive.desktop.linux.visual_messaging import results_band
        frame = {'width': 900, 'height': 480}
        self.assertEqual(results_band(frame, (324, 190), 207, 160, 693), (207, 160, 693, 330))


@unittest.skipUnless(__import__('shutil').which('tesseract'), 'tesseract OCR')
class RowReadingTests(unittest.TestCase):
    def test_rows_are_read_as_strips_and_matched_exactly(self):
        import base64, io, subprocess
        from PIL import Image, ImageDraw, ImageFont
        from olive.desktop.visual_ocr import ocr_rows
        font_path = subprocess.run(['fc-match', '-f', '%{file}', 'sans'], capture_output=True, text=True).stdout
        font, small = ImageFont.truetype(font_path, 14), ImageFont.truetype(font_path, 9)
        image = Image.new('RGB', (440, 90), (43, 45, 49))
        draw = ImageDraw.Draw(image)
        for y, name, server in ((10, 'gen-chat', 'D SERVER'), (40, 'gen-chat', 'OTHER PLACE')):
            draw.text((12, y), '# ' + name, fill=(220, 221, 222), font=font)
            draw.text((110, y + 4), 'TEXT CHANNELS', fill=(140, 142, 148), font=small)
            draw.text((330, y + 2), server, fill=(180, 182, 186), font=font)
        data = io.BytesIO()
        image.save(data, format='PNG')
        frame = {'png': base64.b64encode(data.getvalue()).decode(), 'width': 440, 'height': 90}
        words = ocr_rows(frame, (0, 0, 440, 90))
        self.assertEqual(len(switcher_matches(words, '#gen-chat', 'D SERVER')), 1)
        self.assertEqual(len(switcher_matches(words, '#gen-chat')), 2)  # Same name in two servers: ambiguous.
        self.assertEqual(switcher_matches(words, '#gen-chat', 'C SERVER'), [])


class UnreadServerLabelTests(unittest.IsolatedAsyncioTestCase):
    """A switcher server label too small to read defers the server check to the opened conversation."""
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys

    def unread_servers(self, client):
        original = client.lines
        def lines(role):
            rows = original(role)
            if role == 'wide':
                return [dict(l, confidence=20) if l['box'][0] >= 300 else l for l in rows]
            return rows
        client.lines = lines

    async def test_single_exact_row_navigates_then_the_server_is_verified_before_typing(self):
        client = Client(current=1)
        client.CHANNELS = [('Osprey Workshop', 'general'), ('Osprey Workshop', 'releases')]
        self.unread_servers(client)
        outcome, _ = await self.run_task('Send "hello" to #general in Osprey Workshop in Visual Messenger', client)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Osprey Workshop', 'general', 'hello')])

    async def test_wrong_server_found_after_navigation_types_nothing(self):
        client = Client(current=1)
        client.CHANNELS = [('Osprey Workshop', 'general'), ('Osprey Workshop', 'releases')]
        self.unread_servers(client)
        with self.assertRaisesRegex(ValueError, 'DESTINATION_UNVERIFIED'):
            await self.run_task('Send "hello" to #general in Heron Lab in Visual Messenger', client)
        self.assertEqual(client.sent, [])
        self.assertFalse(any(client.drafts.values()))

    async def test_two_exact_rows_with_unread_servers_stay_ambiguous(self):
        client = Client(current=1)
        self.unread_servers(client)
        with self.assertRaisesRegex(ValueError, 'TARGET_AMBIGUOUS'):
            await self.run_task('Send "hello" to #general in Heron Lab in Visual Messenger', client)
        self.assertEqual(client.sent, [])


class ServerStateTests(unittest.TestCase):
    words = SwitcherRowTests.words

    def test_server_states(self):
        from olive.desktop.messaging_context import switcher_candidates
        unread = self.words(184, ('##', 20, 397), ('gen-chat', 89, 411), ('DSFRVER', 0, 766), ('|', 74, 815))
        other = self.words(208, ('#', 87, 397), ('gen-chat', 88, 411), ('perrito', 87, 752), ('bonito', 90, 782))
        right = self.words(232, ('#', 87, 397), ('gen-chat', 88, 411), ('D', 84, 766), ('SERVER', 84, 780))
        states = [r['server'] for r in switcher_candidates(unread + other + right, '#gen-chat', 'D SERVER')]
        self.assertEqual(states, ['unread', 'other', 'confirmed'])
        self.assertEqual(len(switcher_matches(unread + other + right, '#gen-chat', 'D SERVER')), 1)


class ScrollbarGlyphTests(unittest.TestCase):
    def test_a_scrollbar_read_as_a_letter_does_not_end_the_row(self):
        from olive.desktop.messaging_context import switcher_candidates
        row = [{'text': t, 'confidence': c, 'box': b} for t, c, b in (
            ('##*', 31, (396, 324, 406, 334)), ('gen-chat', 89, (411, 324, 452, 335)), ('rexr', 68, (455, 323, 470, 336)),
            ('D', 81, (766, 326, 771, 332)), ('SERVER', 81, (774, 326, 807, 332)), ('I', 92, (816, 316, 820, 340)))]
        self.assertEqual([r['server'] for r in switcher_candidates(row, '#gen-chat', 'D SERVER')], ['confirmed'])
        two = row[:3] + [{'text': 'Server', 'confidence': 90, 'box': (760, 324, 795, 335)},
                         {'text': '2', 'confidence': 90, 'box': (798, 324, 804, 335)}] + row[5:]
        self.assertEqual([r['server'] for r in switcher_candidates(two, '#gen-chat', 'Server 2')], ['confirmed'])


class SelectionSettleTests(unittest.IsolatedAsyncioTestCase):
    """The opened conversation is checked only after the switcher has closed."""
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys

    async def test_switcher_closing_slowly_is_waited_for(self):
        client = Client(current=0)
        outcome, _ = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client,
                                         open_reads=1)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Heron Lab', 'general', 'field update')])

    async def test_switcher_that_never_closes_types_nothing(self):
        client = Client(current=0)
        with self.assertRaisesRegex(ValueError, 'did not open its conversation'):
            await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client,
                                open_reads=99)
        self.assertEqual(client.sent, [])
        self.assertFalse(any(client.drafts.values()))
        self.assertTrue(self.keys(client, 'Escape'))


class CaretTests(unittest.IsolatedAsyncioTestCase):
    """A blinking caret spoiling one read of the composer is re-read, never guessed."""
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys
    delay = SettleTests.delay

    async def test_caret_hidden_placeholder_is_read_on_the_next_frame(self):
        client = Client(current=2)  # Already in Heron Lab #general.
        self.delay(client, 'composer', 1)
        outcome, _ = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Heron Lab', 'general', 'field update')])

    async def test_composer_never_readable_types_nothing(self):
        client = Client(current=2)
        self.delay(client, 'composer', 99)
        with self.assertRaisesRegex(ValueError, 'UNVERIFIED'):
            await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertEqual(client.sent, [])
        self.assertFalse(any(client.drafts.values()))

    async def test_closing_check_stays_inside_the_dialog(self):
        client = Client(current=0)
        await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertTrue(self.closing_checks)
        for left, _, right, _ in self.closing_checks:
            self.assertGreater(left, 0)           # Not the channel list on the left.
            self.assertLess(right, 1000)          # Not panels on the right.


class ChannelViewReadingTests(unittest.TestCase):
    """Real Discord readings: a placeholder split into touching fragments, and the server chevron."""

    def test_touching_fragments_form_the_placeholder(self):
        from olive.desktop.messaging_context import resolve_destination
        pieces = [{'text': t, 'confidence': c, 'box': b} for t, c, b in (
            ('&', 82, (219, 636, 231, 649)), ('+', 83, (269, 637, 280, 648)), ('-+', 80, (269, 637, 280, 648)),
            ('M', 96, (299, 638, 306, 646)), ('essag', 76, (308, 640, 332, 648)),
            ('e #gen-chat', 91, (333, 638, 387, 648)))]
        state = composer_state(pieces, adapter_for('Discord'))
        self.assertEqual(state[:3], ('empty', '#', 'gen-chat'))
        scope = TaskScope('Discord', 'draft', 'hi', '#gen-chat', server='D SERVER')
        self.assertEqual(resolve_destination(scope, state).state, VERIFIED)
        self.assertEqual(resolve_destination(TaskScope('Discord', 'draft', 'hi', '#general'), state).state, MISMATCH)

    def test_distant_text_is_not_joined(self):
        pieces = [line('deeayygoo', 630, left=40), line('Message #gen-chat', 638, left=299)]
        self.assertEqual(composer_state(pieces, adapter_for('Discord'))[:3], ('empty', '#', 'gen-chat'))

    def test_declared_server_chevron_is_ignored_only_for_its_client(self):
        header = [line('D SERVER v', 29)]
        self.assertEqual(resolve_exact(header, 'D SERVER', 'workspace', None,
                                       adapter_for('Discord').header_decorations).state, VERIFIED)
        self.assertEqual(resolve_exact(header, 'D SERVER', 'workspace').state, MISMATCH)
        self.assertEqual(resolve_exact(header, 'C SERVER', 'workspace', None,
                                       adapter_for('Discord').header_decorations).state, MISMATCH)
        self.assertEqual(resolve_exact([line('D SERVER V v', 29)], 'D SERVER', 'workspace', None,
                                       adapter_for('Discord').header_decorations).state, MISMATCH)


class DeclaredLayoutTests(unittest.IsolatedAsyncioTestCase):
    """A client with a declared layout is read by OCR alone and navigated by keyboard when verified."""
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys

    def adapter(self):
        from dataclasses import replace
        # Areas centred on the simulated client's labels (frame 1000 x 680).
        area = lambda x, y, half: ((x - half) / 1000, (y - 10) / 680, (x + half) / 1000, (y + 10) / 680)
        return replace(adapter_for('Visual Messenger'), switcher_enter_opens=True, account_first_line=True,
                       regions={'composer': area(500, 600, 500), 'server': area(150, 20, 50),
                                'header': area(400, 20, 100), 'account': area(150, 660, 50),
                                'switcher': area(500, 150, 300)})

    async def test_declared_layout_needs_no_vision_model_and_selects_by_keyboard(self):
        client = Client(current=2, panel_beside_composer=True)
        # The client highlights its first matching result: Osprey Workshop's #general.
        first = lambda listed: next(i for i, row in enumerate(listed) if 'general' in row['text'])
        outcome, _ = await self.run_task('Send "field update" to #general in Osprey Workshop in Visual Messenger',
                                         client, adapter=self.adapter(), highlight=first)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Osprey Workshop', 'general', 'field update')])
        switcher_clicks = [c for c in client.calls if c[0] == 'visual_click' and c[1]['point'][1] < 590]
        self.assertEqual(switcher_clicks, [])  # Selected with Enter, not the pointer.
        self.assertEqual(self.model_calls, 0)   # Every label was read in its declared area.

    async def test_enter_is_never_used_when_another_row_is_highlighted(self):
        client = Client(current=0, panel_beside_composer=True)
        first = lambda listed: next(i for i, row in enumerate(listed) if 'general' in row['text'])
        outcome, _ = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client,
                                         adapter=self.adapter(), highlight=first)
        self.assertEqual(client.sent, [('Heron Lab', 'general', 'field update')])
        self.assertTrue([c for c in client.calls if c[0] == 'visual_click' and c[1]['point'][1] < 590])

    async def test_unverified_highlight_falls_back_to_the_verified_row_click(self):
        client = Client(current=0, panel_beside_composer=True)
        outcome, _ = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client,
                                         adapter=self.adapter(), highlight=lambda listed: None)
        self.assertIn('appears once', outcome)
        self.assertTrue([c for c in client.calls if c[0] == 'visual_click' and c[1]['point'][1] < 590])


class HighlightTests(unittest.TestCase):
    def frame(self, shades):
        import base64, io
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (400, 30 * len(shades)), (43, 45, 49))
        draw = ImageDraw.Draw(image)
        for i, shade in enumerate(shades):
            draw.rectangle((0, 30 * i, 399, 30 * i + 29), fill=shade)
            draw.text((20, 30 * i + 10), 'row %d' % i, fill=(220, 220, 220))
        data = io.BytesIO()
        image.save(data, format='PNG')
        return {'png': base64.b64encode(data.getvalue()).decode(), 'width': 400, 'height': 30 * len(shades)}

    def test_only_a_clearly_brighter_row_counts(self):
        from olive.desktop.linux.visual_messaging import highlighted_row
        listed = [{'box': (20, 30 * i + 10, 80, 30 * i + 20)} for i in range(3)]
        self.assertEqual(highlighted_row(self.frame([(43, 45, 49), (64, 66, 72), (43, 45, 49)]), listed, 0, 400), 1)
        self.assertIsNone(highlighted_row(self.frame([(43, 45, 49), (44, 46, 50), (43, 45, 49)]), listed, 0, 400))
        self.assertIsNone(highlighted_row({'png': '', 'width': 400, 'height': 90}, listed, 0, 400))

    async def test_account_panel_name_is_verified_for_a_named_account(self):
        client = Client(current=2, panel_beside_composer=True, account='someone-else')
        with self.assertRaisesRegex(ValueError, 'ACCOUNT_UNVERIFIED'):
            await self.run_task('Send "hi" to #general in Osprey Workshop in Visual Messenger using account fixture-owner',
                                client, adapter=self.adapter(), highlight=lambda listed: None)
        self.assertEqual(client.sent, [])
        self.assertFalse(any(client.drafts.values()))


class ExactDraftTests(unittest.IsolatedAsyncioTestCase):
    """A draft that is exactly the requested text satisfies the request; any other draft is preserved."""
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys

    def typed(self, client):
        return [c[1]['value'] for c in client.calls if c[0] == 'visual_text']

    async def test_identical_draft_completes_a_draft_request_without_typing(self):
        client = Client(current=2, draft='field update')
        outcome, _ = await self.run_task('Draft "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertIn('already in the verified', outcome)
        self.assertEqual(self.typed(client), ['general'])  # Only the switcher query.
        self.assertEqual(client.sent, [])

    async def test_identical_draft_is_sent_once_without_retyping(self):
        client = Client(current=2, draft='field update')
        outcome, reserved = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Heron Lab', 'general', 'field update')])
        self.assertEqual(self.typed(client), ['general'])
        self.assertEqual(reserved, ['reserved', 'verified'])

    async def test_different_draft_is_never_sent_or_overwritten(self):
        client = Client(current=2, draft='something else')
        with self.assertRaisesRegex(ValueError, 'COMPOSER_UNVERIFIED'):
            await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertEqual(client.sent, [])
        self.assertEqual(client.drafts[2], 'something else')


class WithinAreaTests(unittest.TestCase):
    frame = UnchangedOutsideTests.frame

    def test_comparison_limited_to_an_area(self):
        from olive.desktop.visual_ocr import unchanged_outside
        before = self.frame()
        elsewhere = self.frame(lambda d: d.rectangle((150, 100, 190, 118), fill=(255, 0, 0)))
        self.assertTrue(unchanged_outside(before, elsewhere, (0, 0, 0, 0), (0, 0, 140, 90)))
        self.assertFalse(unchanged_outside(before, elsewhere, (0, 0, 0, 0), (0, 0, 200, 120)))
        inside = self.frame(lambda d: d.rectangle((10, 40, 60, 60), fill=(255, 0, 0)))
        self.assertFalse(unchanged_outside(before, inside, (0, 0, 0, 0), (0, 0, 140, 90)))


class CaretFrameTests(unittest.IsolatedAsyncioTestCase):
    def frame(self, caret):
        import base64, io
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (300, 40), (56, 58, 64))
        draw = ImageDraw.Draw(image)
        draw.text((10, 12), 'hello from OLIVE', fill=(220, 221, 222))
        if caret:
            draw.line((112, 8, 112, 30), fill=(230, 230, 230), width=2)
        data = io.BytesIO()
        image.save(data, format='PNG')
        return {'png': base64.b64encode(data.getvalue()).decode(), 'width': 300, 'height': 40, 'caret': caret}

    async def test_the_caret_off_frame_is_read(self):
        import itertools
        frames = itertools.cycle([self.frame(True), self.frame(False)])  # A blinking caret.
        messaging = visual_messaging.VisualMessaging.__new__(visual_messaging.VisualMessaging)
        async def next_frame():
            return next(frames)
        messaging.frame = next_frame
        self.assertFalse((await messaging.quiet_frame(lambda f: (0, 0, 300, 40)))['caret'])
        self.assertFalse((await messaging.quiet_frame(lambda f: (0, 0, 300, 40)))['caret'])


class SwitcherToggleTests(unittest.IsolatedAsyncioTestCase):
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys

    async def test_switcher_left_open_is_reopened_once_before_typing(self):
        client = Client(current=0)
        client.toggles, client.switcher = True, True  # Left open by the user.
        outcome, _ = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Heron Lab', 'general', 'field update')])
        self.assertEqual(len(self.keys(client, 'ctrl+k')), 2)
        self.assertEqual(len(self.keys(client, 'Escape')), 1)

    async def test_switcher_left_open_with_an_old_query_is_reopened_empty(self):
        client = Client(current=0)
        client.switcher, client.query = True, 'stale query'   # Ctrl+K does not clear it.
        original = client.call
        async def call(method, args=None, timeout=None):
            if method == 'visual_key' and args['value'] == 'ctrl+k' and client.switcher and client.query:
                client.calls.append((method, dict(args)))
                return {'dispatched': True}                    # Ignored while open with text.
            return await original(method, args, timeout)
        client.call = call
        outcome, _ = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertIn('appears once', outcome)
        self.assertEqual(client.sent, [('Heron Lab', 'general', 'field update')])


class EchoTests(unittest.TestCase):
    """The sent message as Discord shows it: alone, or after time, name and badge."""

    def test_group_start_and_continuation_rows(self):
        from olive.desktop.messaging_context import echo_rows
        words = lambda top, *texts: [{'text': t, 'confidence': 92, 'box': (10 + 60 * i, top, 60 + 60 * i, top + 12)}
                                     for i, t in enumerate(texts)]
        first = words(100, '4:50', 'PM', 'deeayygoo', 'win', 'hello', 'from', 'OLIVE')
        continued = words(130, 'hello', 'from', 'OLIVE')
        self.assertEqual(len(echo_rows(first, 'hello from OLIVE', 'deeayygoo')), 1)
        self.assertEqual(len(echo_rows(continued, 'hello from OLIVE', 'deeayygoo')), 1)
        self.assertEqual(echo_rows(first, 'hello from OLIVE', 'someone-else'), [])      # Another sender.
        truncated = words(160, 'deeayy', 'hello')                                      # Coloured name cut short.
        self.assertEqual(len(echo_rows(truncated, 'hello', 'deeayygoo')), 1)
        self.assertEqual(echo_rows(words(160, 'dee', 'hello'), 'hello', 'deeayygoo'), [])
        self.assertEqual(echo_rows(words(160, 'deeayx', 'hello'), 'hello', 'deeayygoo'), [])
        self.assertEqual(echo_rows(words(100, 'say', 'hello', 'from', 'OLIVE'), 'hello from OLIVE', 'deeayygoo'), [])
        self.assertEqual(echo_rows(words(100, 'hello', 'from', 'OLIVE', 'again'), 'hello from OLIVE', ''), [])


class RightAlignedLabelTests(unittest.TestCase):
    """A real Discord row: '# nepali-jerk-circle CHAT ... guaplings', the label read as 'u'."""

    def row(self, *label):
        base = [('#*', 66, 397), ('nepali-jerk-circle', 90, 412), ('CMAT', 78, 494)]
        return [{'text': t, 'confidence': c, 'box': (x, 278, x + 8 * len(t), 290)} for t, c, x in base + list(label)]

    def states(self, words, server):
        from olive.desktop.messaging_context import switcher_candidates
        return [r['server'] for r in switcher_candidates(words, '#nepali-jerk-circle', server, 600)]

    def test_glyph_sized_misreading_is_not_another_server(self):
        self.assertEqual(self.states(self.row(('u', 84, 774)), 'guaplings'), ['unread'])

    def test_category_is_never_the_server_label(self):
        self.assertEqual(self.states(self.row(), 'guaplings'), ['unread'])

    def test_readable_labels_confirm_or_disqualify(self):
        self.assertEqual(self.states(self.row(('guaplings', 88, 760)), 'guaplings'), ['confirmed'])
        self.assertEqual(self.states(self.row(('perrito', 90, 720), ('bonito', 91, 760)), 'guaplings'), ['other'])


class QueryTypingTests(unittest.IsolatedAsyncioTestCase):
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys

    def typed(self, client):
        return [c[1]['value'] for c in client.calls if c[0] == 'visual_text']

    async def test_dropped_query_is_typed_once_more(self):
        client = Client(current=0)
        client.drop_typing = 1
        outcome, _ = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertIn('appears once', outcome)
        self.assertEqual(self.typed(client), ['general', 'general', 'field update'])

    async def test_query_that_never_appears_stops_before_selection(self):
        client = Client(current=0)
        client.drop_typing = 9
        with self.assertRaisesRegex(ValueError, 'did not appear in the quick switcher'):
            await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertEqual(self.typed(client), ['general', 'general'])
        self.assertEqual(client.sent, [])
        self.assertFalse([c for c in client.calls if c[0] == 'visual_click'])


class RowHeightTests(unittest.TestCase):
    def test_small_caps_labels_never_drop_the_channel_name(self):
        from olive.desktop.messaging_context import switcher_candidates
        row = [{'text': t, 'confidence': c, 'box': b} for t, c, b in (
            ('#*', 66, (396.8, 278.0, 406.2, 287.5)), ('nepali-jerk-circle', 90, (411.5, 278.0, 490.5, 288.5)),
            ('CMAT', 78, (494.0, 282.0, 508.2, 286.0)), ('u', 84, (774.2, 282.2, 777.8, 285.8)),
            ('nge', 5, (794.0, 282.0, 806.5, 287.8)), ('I', 92, (816.0, 272.0, 820.0, 296.0)))]
        self.assertEqual([r['server'] for r in switcher_candidates(row, '#nepali-jerk-circle', 'guaplings', 600)],
                         ['unread'])


class ReadingMergeTests(unittest.TestCase):
    """Two OCR passes over the same glyphs: whole words beat fragments; garbage never wins."""

    def word(self, text, confidence, left, right):
        return {'text': text, 'confidence': confidence, 'box': (left, 32, right, 42)}

    def merged(self, *readings):
        from olive.desktop.visual_ocr import merge_reading
        found = []
        for reading in readings:
            merge_reading(found, reading)
        return sorted(w['text'] for w in found)

    def test_credible_whole_word_replaces_its_fragments(self):
        whole = self.word('#nepali-jerk-circle', 85, 340, 424)
        parts = [self.word('#nepali', 62, 340, 374), self.word('jerk', 76, 378, 395), self.word('circle', 88, 400, 424)]
        self.assertEqual(self.merged(whole, *parts), ['#nepali-jerk-circle'])
        self.assertEqual(self.merged(*parts, whole), ['#nepali-jerk-circle'])

    def test_garbled_wide_reading_never_displaces_confident_words(self):
        garbage = self.word('N', 4, 300, 800)
        words = [self.word('nepali-jerk-circle', 90, 412, 490), self.word('guaplings', 84, 760, 800)]
        self.assertEqual(self.merged(garbage, *words), ['guaplings', 'nepali-jerk-circle'])
        self.assertEqual(self.merged(*words, garbage), ['guaplings', 'nepali-jerk-circle'])

    def test_same_glyphs_keep_the_more_confident_reading(self):
        self.assertEqual(self.merged(self.word('Messaqe', 70, 299, 338), self.word('Message', 92, 299, 337)), ['Message'])


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys

    async def test_garbled_placeholder_after_sending_still_confirms_delivery(self):
        client = Client(current=0)
        original = client.lines
        def lines(role):
            if role == 'composer' and client.sent and not client.drafts.get(client.current):
                return [line('2ssape #general', 600)]  # Caret over the placeholder's first letters.
            return original(role)
        client.lines = lines
        outcome, _ = await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertIn('appears once', outcome)

    async def test_text_still_in_the_composer_is_never_reported_delivered(self):
        client = Client(current=0)
        original = client.call
        async def call(method, args=None, timeout=None):
            result = await original(method, args, timeout)
            if method == 'visual_key' and args['value'] == 'Enter' and client.sent:
                client.drafts[client.current] = client.sent[-1][2]   # Echo shown but text still present.
            return result
        client.call = call
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            await self.run_task('Send "field update" to #general in Heron Lab in Visual Messenger', client)
        self.assertEqual(len(self.keys(client, 'Enter')), 1)


@unittest.skipUnless(__import__('shutil').which('tesseract'), 'tesseract OCR')
class UsernameTests(unittest.IsolatedAsyncioTestCase):
    """Several people share a display name; only the exact username selects one."""

    async def test_exact_username_selects_one_person(self):
        import base64, io, subprocess
        from dataclasses import replace
        from PIL import Image, ImageDraw, ImageFont
        font_path = subprocess.run(['fc-match', '-f', '%{file}', 'sans'], capture_output=True, text=True).stdout
        big, small = ImageFont.truetype(font_path, 15), ImageFont.truetype(font_path, 12)
        image = Image.new('RGB', (440, 120), (43, 45, 49))
        draw = ImageDraw.Draw(image)
        for y, handle in ((10, '4818'), (40, 'cuhcrzzz'), (70, 'knownwarfare9246')):
            draw.text((20, y), 'diego', fill=(220, 221, 222), font=big)
            draw.text((70, y + 3), handle, fill=(150, 152, 158), font=small)
        data = io.BytesIO()
        image.save(data, format='PNG')
        frame = {'png': base64.b64encode(data.getvalue()).decode(), 'width': 440, 'height': 120}
        from olive.desktop.visual_ocr import ocr_rows
        words = ocr_rows(frame, (0, 0, 440, 120))
        for handle, expected in (('4818', 1), ('cuhcrzzz', 1), ('9999', 0)):
            messaging = visual_messaging.VisualMessaging.__new__(visual_messaging.VisualMessaging)
            messaging.adapter, messaging.record = adapter_for('Discord'), lambda entry: None
            messaging.scope = TaskScope('Discord', 'send', 'hello', '@diego', handle=handle)
            self.assertEqual(len(await messaging.candidates_in(frame, words)), expected, handle)


class LookalikeTests(unittest.TestCase):
    def test_typed_text_tolerates_ocr_lookalikes_but_names_do_not(self):
        from olive.desktop.messaging_context import echo_rows, exact_segment, typed_exactly
        words = [line('OLIVE', 600, left=310), line('Ul', 600, left=366), line('test', 600, left=392)]
        self.assertTrue(typed_exactly(words, 'OLIVE UI test', adapter_for('Discord')))
        self.assertIsNotNone(exact_segment(words, 'OLIVE UI test'))
        self.assertFalse(typed_exactly(words, 'OLIVE UX test', adapter_for('Discord')))
        self.assertEqual(len(echo_rows([line('OLlVE', 500), ], 'OLIVE', '')), 1)
        # Destination identity stays exact.
        self.assertEqual(resolve_exact([line('generaI', 10)], '#general', 'x').state, MISMATCH)


class SplitDestinationTests(unittest.TestCase):
    def test_hyphen_dropped_by_ocr_rejoins_only_to_the_requested_name(self):
        def word(text, left, confidence=90):
            return {'text': text, 'confidence': confidence, 'box': (left, 640, left + 8 * len(text), 650)}
        live = [word('-+', 269, 83), word('Message', 299, 55), word('#gen', 358, 85), word('chat', 393, 93)]
        adapter = adapter_for('Discord')
        self.assertEqual(composer_state(live, adapter, '#gen-chat')[:3], ('empty', '#', 'gen-chat'))
        scope = TaskScope('Discord', 'send', 'hi', '#genchat')
        self.assertEqual(resolve_destination(scope, composer_state(live, adapter, '#genchat')).state, MISMATCH)


class SpacingTests(unittest.TestCase):
    def test_typed_text_ignores_ocr_word_spacing_on_word_boundaries(self):
        from olive.desktop.messaging_context import echo_rows, exact_segment
        def word(text, left):
            return {'text': text, 'confidence': 90, 'box': (left, 10, left + 7 * len(text), 20)}
        self.assertIsNotNone(exact_segment([word('OLIVEdelivery', 56), word('check', 150)], 'OLIVE delivery check'))
        row = [word('deeayygoo', 10), word('win', 80), word('OLIVEdelivery', 120), word('check', 215)]
        self.assertEqual(len(echo_rows(row, 'OLIVE delivery check', 'deeayygoo')), 1)
        self.assertEqual(echo_rows([word('xOLIVE', 10), word('delivery', 60), word('check', 130)],
                                   'OLIVE delivery check', ''), [])


class TypedQueryTests(unittest.TestCase):
    def test_one_trailing_caret_is_forgiven_and_nothing_else(self):
        from olive.desktop.linux.visual_messaging import typed_query
        for seen in ['gen-chat', 'gen-chat|', 'gen-chatl', 'gen-chatI', '#gen-chat']:
            self.assertTrue(typed_query(seen, '#gen-chat'), seen)
        for seen in ['gen-cha', 'gen-chatx', 'gen-chatll', 'xgen-chat']:
            self.assertFalse(typed_query(seen, '#gen-chat'), seen)
        self.assertTrue(typed_query('diegoI', '@diego'))
        self.assertFalse(typed_query('dieg|', '@diego'))


class DirectMessageReadTests(unittest.TestCase):
    """Readings logged from a real Discord DM view (user profile panel open)."""

    def test_account_ignores_panel_junk_and_a_stray_status_glyph(self):
        from olive.desktop.messaging_context import observed_account
        W = lambda t, c, b: {'text': t, 'confidence': c, 'box': b}
        junk = [W('Wy,', 80, [59, 614, 80, 623]), W('deeayygoo', 91, [40, 632, 88, 642]), W('Imisible', 53, [40, 645, 67, 651])]
        self.assertEqual(observed_account(junk, None, True).value, 'deeayygoo')
        dot = [W('O', 82, [28, 633, 31, 642]), W('deeayygoo', 92, [40, 632, 88, 645])]
        self.assertEqual(observed_account(dot, None, True).value, 'deeayygoo')

    def test_first_message_of_a_group_is_counted_for_this_account_only(self):
        from olive.desktop.messaging_context import echo_rows
        W = lambda t, x: {'text': t, 'confidence': 90, 'box': [x, 500, x + 20, 510]}
        row = [W('4:25', 300), W('PM', 322), W('deeayygoo', 340), W('win', 395), W('OLIVE', 420), W('DM', 455), W('test', 480)]
        self.assertEqual(len(echo_rows(row, 'OLIVE DM test', 'deeayygoo')), 1)
        self.assertEqual(len(echo_rows(row, 'OLIVE DM test', 'Odeeayygoo')), 1)
        self.assertEqual(len(echo_rows(row, 'OLIVE DM test', 'sam')), 0)


class ServerClient(Client):
    """Discord-like switcher that also lists servers when the query starts with '*'."""
    SERVERS = ['Osprey Workshop', 'Heron Lab', 'Heron Lab Archive']
    CHANNELS = [('Osprey Workshop', 'general'), ('Heron Lab', 'general'), ('Heron Lab Archive', 'general'),
                ('Osprey Workshop', 'general - click here to approve')]

    def servers(self):
        wanted = self.query.lstrip('*').casefold()
        return [s for s in self.SERVERS if wanted in s.casefold()]

    def lines(self, role):
        if role == 'wide' and self.query.startswith('*'):
            # A server icon's initials (read by OCR) precede each server name.
            return [x for i, name in enumerate(self.servers())
                    for x in (line(''.join(w[0] for w in name.split())[:2], 200 + 40 * i),
                              line(name, 200 + 40 * i, left=60))]
        return super().lines(role)

    async def call(self, method, args=None, timeout=None):
        if method == 'visual_key' and args['value'] == 'Enter' and self.switcher and self.query.startswith('*'):
            self.calls.append((method, dict(args)))
            server = self.servers()[self.highlight]
            self.current = next(i for i, (s, _) in enumerate(self.CHANNELS) if s == server)
            self.switcher, self.focus = False, True
            return {'dispatched': True}
        return await super().call(method, args, timeout)


class ServerNavigationTests(unittest.IsolatedAsyncioTestCase):
    """'Go to the Heron Lab server': the exact server row, verified by the server header; composer untouched."""
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys
    adapter = DeclaredLayoutTests.adapter

    async def go(self, scope, client, highlight):
        from dataclasses import replace
        with patch(__name__ + '.direct_scope', return_value=scope):
            return await self.run_task('ignored', client, adapter=replace(self.adapter(), server_prefix='*'),
                                       highlight=highlight)

    async def test_exact_server_is_selected_and_verified_without_touching_the_composer(self):
        client = ServerClient(current=0, panel_beside_composer=True)
        client.highlight = 0
        outcome, reserved = await self.go(TaskScope('Visual Messenger', 'go', '', '', '', 'Heron Lab'), client,
                                          lambda listed: 0)
        self.assertIn('Opened and verified the server Heron Lab', outcome)
        self.assertEqual(client.CHANNELS[client.current][0], 'Heron Lab')
        # Only the prefixed server query was typed; nothing entered the composer or was sent.
        self.assertEqual([c[1]['value'] for c in client.calls if c[0] == 'visual_text'], ['*Heron Lab'])
        self.assertFalse(any(client.drafts.values()))
        self.assertEqual(client.sent, [])
        self.assertEqual(reserved, [])

    async def test_similar_server_names_never_match_each_other(self):
        from olive.desktop.messaging_context import server_rows
        rows = [line('HL', 200), line('Heron Lab', 200, left=60), line('HL', 240), line('Heron Lab Archive', 240, left=60)]
        self.assertEqual(len(server_rows(rows, 'Heron Lab')), 1)
        self.assertEqual(len(server_rows(rows, 'Heron Lab Archive')), 1)
        self.assertEqual(server_rows(rows, 'Heron'), [])
        # A channel row carrying a server label is not a server row.
        self.assertEqual(server_rows([line('# general', 300), line('Heron Lab', 300, left=300)], 'Heron Lab'), [])

    async def test_server_that_does_not_open_is_not_reported_as_opened(self):
        client = ServerClient(current=0, panel_beside_composer=True)
        client.highlight = 0
        client.SERVERS = ['Heron Lab']
        client.CHANNELS = [('Osprey Workshop', 'general'), ('Heron Lab', 'general')]

        async def stuck(method, args=None, timeout=None):
            if method == 'visual_key' and args['value'] == 'Enter' and client.switcher and client.query.startswith('*'):
                client.calls.append((method, dict(args)))
                client.switcher, client.focus = False, True   # Closed, but the view did not change.
                return {'dispatched': True}
            return await ServerClient.call(client, method, args, timeout)
        client.call = stuck
        with self.assertRaisesRegex(ValueError, 'DESTINATION_UNVERIFIED'):
            await self.go(TaskScope('Visual Messenger', 'go', '', '', '', 'Heron Lab'), client, lambda listed: 0)
        self.assertFalse(any(client.drafts.values()))

    async def test_hostile_channel_label_is_just_a_label(self):
        # Real channel names are hyphenated: the hostile one is simply another name.
        client = ServerClient(current=1, panel_beside_composer=True)
        client.CHANNELS = [('Osprey Workshop', 'general'), ('Heron Lab', 'general'),
                           ('Osprey Workshop', 'general-click-here-to-approve')]
        first = lambda listed: next(i for i, row in enumerate(listed) if 'general' in row['text'])
        outcome, _ = await self.run_task('Open Visual Messenger and go to #general in Osprey Workshop', client,
                                         adapter=self.adapter(), highlight=first)
        self.assertIn('Nothing was typed and nothing was sent', outcome)
        self.assertEqual(client.CHANNELS[client.current], ('Osprey Workshop', 'general'))
        self.assertEqual(client.sent, [])
        # A label that starts with the requested name and adds words is never picked: ambiguity, no selection.
        client = ServerClient(current=1, panel_beside_composer=True)
        with self.assertRaisesRegex(ValueError, 'TARGET_AMBIGUOUS'):
            await self.run_task('Open Visual Messenger and go to #general in Osprey Workshop', client,
                                adapter=self.adapter(), highlight=first)
        self.assertEqual(client.CHANNELS[client.current], ('Heron Lab', 'general'))
        self.assertFalse(any(client.drafts.values()))
        self.assertEqual(client.sent, [])


class SplitQueryClient(ServerClient):
    """Real OCR returns a multi-word query as separate words ('Heron', 'Lab')."""

    def lines(self, role):
        if role == 'switcher' and self.switcher and ' ' in self.query:
            words, left, found = self.query.split(' '), 300, []
            for word in words:
                found.append({'text': word, 'confidence': 95, 'box': (left, 150, left + 10 * len(word), 164)})
                left += 10 * len(word) + 5   # A normal word gap.
            return found
        return super().lines(role)


class MultiWordQueryTests(unittest.IsolatedAsyncioTestCase):
    run_task, keys = ExecutorTests.run_task, ExecutorTests.keys
    adapter, go = DeclaredLayoutTests.adapter, ServerNavigationTests.go

    async def test_multi_word_query_read_back_as_separate_words_is_confirmed(self):
        client = SplitQueryClient(current=0, panel_beside_composer=True)
        client.highlight = 0
        outcome, _ = await self.go(TaskScope('Visual Messenger', 'go', '', '', '', 'Heron Lab'), client, lambda listed: 0)
        self.assertIn('Opened and verified the server Heron Lab', outcome)
        self.assertEqual([c[1]['value'] for c in client.calls if c[0] == 'visual_text'], ['*Heron Lab'])

    def test_a_fragment_of_the_query_is_never_enough(self):
        from olive.desktop.linux.visual_messaging import typed_query
        from olive.desktop.messaging_context import segments
        words = [{'text': 'Heron', 'confidence': 95, 'box': (300, 150, 350, 164)}]
        self.assertFalse(any(typed_query(w['text'], 'Heron Lab') for w in words + segments(words)))
