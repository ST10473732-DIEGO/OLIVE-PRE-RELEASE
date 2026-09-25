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
                self.switcher, self.query = True, ''
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

        def ocr(frame, box):
            left, top, right, bottom = box
            if client.panel and left == 0 and right <= 300 and top < 600 < bottom:
                return client.lines('panel')
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
                patch.object(visual_messaging, 'unchanged_outside', lambda before, after, box: unchanged):
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
