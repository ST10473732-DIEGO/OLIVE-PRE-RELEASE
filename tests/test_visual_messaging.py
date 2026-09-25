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

    def __init__(self, current=0, draft='', account='fixture-owner', echo=True):
        self.current, self.drafts, self.account, self.echo = current, {current: draft}, account, echo
        self.switcher, self.query, self.focus = False, '', False
        self.sent, self.calls = [], []

    def lines(self, role):
        server, channel = self.CHANNELS[self.current]
        draft = self.drafts.get(self.current, '')
        if role == 'composer':
            return [line(draft, 600)] if draft else [line('Message #' + channel, 600)]
        if role == 'server':
            return [line(server, 20)]
        if role == 'account':
            return [line(self.account, 660)]
        if role == 'header':
            return [line('# ' + channel, 20)]
        if role == 'switcher':
            return [line(self.query or 'Where would you like to go?', 150)]
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
    async def run_task(self, request, client):
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

        class Gui:
            async def action(self, frame, prompt):
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
            middle = (top + bottom) / 2
            if bottom - top > 200:
                return client.lines('wide')
            center = (left + right) / 2
            for role, (x, y) in roles.items():
                if abs(middle - y) < 3 and (right - left > 900 or abs(center - x) < 3):
                    return client.lines(role)
            if bottom < 600 and top > 400:
                return client.lines('above')
            return []
        with patch.object(visual_messaging, 'ocr_lines', ocr), patch.object(visual_messaging.asyncio, 'sleep',
                                                                             return_value=None):
            outcome = await visual_messaging.visual_message(runtime, grant, 1, scope.application)
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
        self.assertFalse([c for c in client.calls if c[0] == 'visual_text'])

    async def test_requested_account_must_match_visible_account(self):
        client = Client(current=0, account='someone-else')
        with self.assertRaisesRegex(ValueError, 'ACCOUNT_UNVERIFIED'):
            await self.run_task('Send "hi" to #general in Osprey Workshop in Visual Messenger using account fixture-owner',
                                client)
        self.assertFalse([c for c in client.calls if c[0] == 'visual_text'])

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
