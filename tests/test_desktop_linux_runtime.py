"""Portable adaptive-loop tests: substitute inference/input, retain real authority/storage."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

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
        self.runtime.native.call = AsyncMock(side_effect=self.dispatch)
        app = SimpleNamespace(name='Owned messenger', executable=Path(sys.executable))
        self.runtime.apps = SimpleNamespace(discover=Mock(), resolve=Mock(return_value=app), launch=Mock(return_value=[(123, 1)]))
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
                         editable=True, value=self.value, bounds=[10, 10, 300, 40])]
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
        await self.run_message()
        self.assertEqual(self.actions, [])
        self.assertEqual(self.desktop.record.status, 'needs-human')

    async def test_destination_change_during_model_wait_prevents_input(self):
        async def changed(*args, **kwargs):
            response = await self.plan(*args, **kwargs)
            self.change_destination = True
            return response
        self.services.ollama.chat_once.side_effect = changed
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
        task = asyncio.create_task(self.run_message())
        await entered.wait()
        self.runtime.stop()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.actions, [])
        self.assertEqual(self.desktop.record.status, 'cancelled')
        self.assertIsNone(self.runtime.owner)
        self.runtime.native.call.assert_awaited_with('end', timeout=4)
