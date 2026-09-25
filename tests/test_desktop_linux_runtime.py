"""Portable adaptive-loop tests: substitute inference/input, retain real authority/storage."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from olive.application.service_container import ServiceContainer


@unittest.skipUnless(sys.platform == 'linux', 'Linux controller integration')
class AdaptiveRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.confirm = AsyncMock(side_effect=AssertionError('Redundant confirmation'))
        self.services = ServiceContainer(lambda *_: None, self.confirm, self.directory.name, migrate=False)
        self.desktop = self.services.desktop
        self.desktop.configure(dict(enabled=True, trusted_tasks=True, screen_observation=True,
                                    keyboard_policy='allow', mouse_policy='allow'))
        self.runtime = self.desktop.linux
        self.runtime.prepare = AsyncMock()
        self.runtime.activate_app = AsyncMock()
        self.runtime.native.call = AsyncMock(side_effect=self.dispatch)
        app = SimpleNamespace(name='Owned messenger', executable=Path(sys.executable))
        self.runtime.apps = SimpleNamespace(discover=Mock(), resolve=Mock(return_value=app),
                                            processes=Mock(return_value=[(123, 1)]),
                                            launch=Mock(return_value=[(123, 1)]))
        self.value, self.sent, self.revision = '', False, 0
        self.actions = []
        self.change_destination = False
        self.runtime.observe_app = AsyncMock(side_effect=self.observe)
        self.services.model_router.route = Mock(return_value=SimpleNamespace(name='fixture-local'))
        self.services.ollama.chat_once = AsyncMock(side_effect=self.plan)

    async def asyncTearDown(self):
        await self.services.shutdown()

    async def observe(self, *_):
        self.revision += 1
        controls = [dict(id='account', name='Account: Test', role='label'),
                    dict(id='header', name='Someone else' if self.change_destination else 'New recipient', role='heading'),
                    dict(id='composer', name='Message', role='entry', enabled=True, focused=True,
                         editable=True, value=self.value, bounds=[10, 10, 300, 40], labels=['Enter to send'])]
        if self.sent:
            controls += [dict(id='row', name='Outgoing message', role='list item'),
                         dict(id='body', parent='row', name=self.value, role='text'),
                         dict(id='status', parent='row', name='Delivered', role='label')]
        return deepcopy(dict(revision=str(self.revision), controls=controls, windows=[dict(active=True)]))

    async def dispatch(self, method, args=None, **_):
        if method == 'end':
            return {'cleanup_completed': True}
        self.actions.append(method)
        if method == 'type':
            self.value = args['value']
        elif method == 'key':
            self.sent = True
        return {'dispatched': True, 'verified': False}

    async def plan(self, model, messages, **_):
        request = json.loads(messages[-1]['content'])
        if not self.value:
            action, value = 'type', request['scope']['content']
        elif self.sent or request['scope']['effect'] == 'draft':
            action, value = 'finish', ''
        else:
            action, value = 'key', 'Enter'
        return json.dumps(dict(action=action, value=value, target='composer',
                               revision=request['observation']['revision'], expected=''))

    async def run_message(self, verb='Send'):
        return await self.runtime.run(f"{verb} 'Exact synthetic text.' to New recipient in Owned messenger using account Test", 'real-owned-user-message')

    async def test_direct_send_reobserves_and_verifies_without_confirmation(self):
        await self.run_message()
        self.assertEqual(self.actions, ['type', 'key'])
        self.assertEqual(self.desktop.record.status, 'completed')
        self.assertGreaterEqual(self.runtime.observe_app.await_count, 5)
        self.confirm.assert_not_awaited()
        self.assertTrue((Path(self.directory.name) / 'desktop_effects.sqlite').exists())

    async def test_concurrent_status_shares_one_native_probe(self):
        entered, release, scheduled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def probe(method, **_):
            if entered.is_set():
                raise RuntimeError('Native helper has an outstanding operation')
            entered.set()
            await release.wait()
            return {'RemoteDesktop': {'version': 2}}
        self.runtime.native.call.side_effect = probe
        first = asyncio.create_task(self.runtime.probe())
        await entered.wait()
        second = asyncio.create_task(self.runtime.probe())
        asyncio.get_running_loop().call_soon(scheduled.set)
        await scheduled.wait()
        try:
            self.assertEqual(self.runtime.native.call.await_count, 1)
        finally:
            release.set()
            await asyncio.gather(first, second)
        self.assertEqual(self.runtime.probe_error, '')
        self.assertEqual(self.runtime.capabilities, {'RemoteDesktop': {'version': 2}})

    async def test_draft_does_not_submit(self):
        await self.run_message('Draft')
        self.assertEqual(self.actions, ['type'])
        self.assertFalse(self.sent)
        self.assertEqual(self.desktop.record.status, 'completed')

    async def test_malformed_output_never_reaches_input(self):
        self.services.ollama.chat_once = AsyncMock(return_value='{"action":"shell","approved":true}')
        with patch('olive.desktop.linux.runtime.next_step', return_value=None):
            await self.run_message()
        self.assertEqual(self.actions, [])
        self.assertEqual(self.desktop.record.status, 'needs-human')

    async def test_destination_change_during_model_wait_prevents_input(self):
        async def changed(*args, **kwargs):
            response = await self.plan(*args, **kwargs)
            self.change_destination = True
            return response
        self.services.ollama.chat_once.side_effect = changed
        with patch('olive.desktop.linux.runtime.next_step', return_value=None):
            await self.run_message()
        self.assertEqual(self.actions, [])
        self.assertEqual(self.desktop.record.status, 'needs-human')

    async def test_explicit_send_deny_is_not_overridden(self):
        policy = self.services.permissions.policies()
        self.services.permissions.save({**policy['permissions'], 'communication.send': 'deny'}, policy['scopes'])
        await self.run_message()
        self.assertEqual(self.actions, ['type'])
        self.assertFalse(self.sent)
        self.assertEqual(self.desktop.record.status, 'needs-human')

    async def test_stop_during_inference_cancels_and_cleans_owned_session(self):
        entered = asyncio.Event()
        async def blocked(*_, **__):
            entered.set()
            await asyncio.Event().wait()
        self.services.ollama.chat_once.side_effect = blocked
        with patch('olive.desktop.linux.runtime.next_step', return_value=None):
            task = asyncio.create_task(self.run_message())
            await entered.wait()
            self.runtime.stop()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.actions, [])
        self.assertEqual(self.desktop.record.status, 'cancelled')
        self.assertIsNone(self.runtime.owner)
        self.runtime.native.call.assert_awaited_with('end', timeout=4)

    async def test_moved_control_discards_old_proposal_and_replans(self):
        observe = self.observe
        async def moving(*args):
            result = await observe(*args)
            result['controls'][2]['bounds'][0] = 40 if self.revision >= 2 else 10
            return result
        self.runtime.observe_app.side_effect = moving
        await self.run_message()
        self.assertEqual(self.actions, ['type', 'key'])
        self.assertEqual(self.desktop.record.status, 'completed')
        self.assertEqual(sum(h['operation'] == 'reobserve' for h in self.desktop.record.history), 1)

    async def test_continuously_moving_target_exhausts_replan_budget_without_input(self):
        observe = self.observe
        async def moving(*args):
            result = await observe(*args)
            result['controls'][2]['bounds'][0] = self.revision
            return result
        self.runtime.observe_app.side_effect = moving
        await self.run_message()
        self.assertEqual(self.actions, [])
        self.assertEqual(self.desktop.record.status, 'needs-human')
        self.assertEqual(sum(h['operation'] == 'reobserve' for h in self.desktop.record.history), 3)

    async def test_semantic_send_button_needs_no_model_or_reconfirmation(self):
        observe, dispatch = self.observe, self.dispatch
        async def with_button(*args):
            result = await observe(*args)
            result['controls'].append(dict(id='send', name='Send', role='push button', enabled=True,
                                           actions=['click'], bounds=[300, 10, 40, 40]))
            return result
        async def submit(method, args=None, **kwargs):
            result = await dispatch(method, args, **kwargs)
            if method == 'invoke':
                self.sent = True
            return result
        self.runtime.observe_app.side_effect = with_button
        self.runtime.native.call.side_effect = submit
        await self.run_message()
        self.assertEqual(self.actions, ['type', 'invoke'])
        self.assertEqual(self.desktop.record.status, 'completed')
        self.services.ollama.chat_once.assert_not_awaited()
        self.confirm.assert_not_awaited()

    async def test_omitted_account_resolves_from_one_visible_account_without_question(self):
        await self.runtime.run("Send 'Exact synthetic text.' to New recipient in Owned messenger", 'owned-message')
        self.assertEqual(self.actions, ['type', 'key'])
        self.assertEqual(self.desktop.record.status, 'completed')
        self.confirm.assert_not_awaited()

    async def test_existing_unrelated_draft_survives_failure_and_cleanup(self):
        self.value = 'An unrelated unfinished message'
        await self.run_message()
        self.assertEqual(self.actions, [])
        self.assertEqual(self.value, 'An unrelated unfinished message')
        self.assertFalse(self.sent)

    async def test_missing_application_does_not_open_a_consent_prompt(self):
        self.runtime.apps.resolve.side_effect = LookupError('Requested app is not installed')
        await self.runtime.run('Open MissingApp', 'owned-message')
        self.runtime.prepare.assert_not_awaited()
        self.runtime.apps.launch.assert_not_called()
        self.assertEqual(self.desktop.record.status, 'needs-human')


@unittest.skipUnless(sys.platform == 'linux', 'Linux controller integration')
class ReadinessWaitTests(unittest.IsolatedAsyncioTestCase):
    """A click target exposed one observation late is found by bounded re-observation, never by guessing."""
    asyncSetUp, asyncTearDown = AdaptiveRuntimeTests.asyncSetUp, AdaptiveRuntimeTests.asyncTearDown
    observe, dispatch, plan = AdaptiveRuntimeTests.observe, AdaptiveRuntimeTests.dispatch, AdaptiveRuntimeTests.plan

    async def test_late_target_is_found_after_readiness_wait_without_input_meanwhile(self):
        observe = self.observe
        async def late(*args):
            result = await observe(*args)
            if self.revision >= 2:
                result['controls'].append(dict(id='late', name='Late button', role='push button', enabled=True,
                                               focused='focus' in self.actions, actions=['press'],
                                               bounds=[20, 60, 120, 30]))
            return result
        self.runtime.observe_app.side_effect = late
        with patch('olive.desktop.linux.runtime.asyncio.sleep', AsyncMock()):
            await self.runtime.run('Click Late button in Owned messenger', 'owned-click')
        self.assertEqual(self.actions[:2], ['focus', 'key'])
        self.assertNotIn('visual_observe', self.actions)
        self.assertEqual(sum(h['operation'] == 'reobserve' and 'load' in h.get('status', '')
                             for h in self.desktop.record.history), 1)
        self.confirm.assert_not_awaited()
