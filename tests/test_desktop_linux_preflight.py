import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from olive.desktop.linux.preflight import classify, inspect


class PreflightTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.caps = {name: {'version': 5} for name in ('RemoteDesktop', 'ScreenCast', 'GlobalShortcuts')}
        self.client = SimpleNamespace(call=AsyncMock(return_value=self.caps), close=AsyncMock(), process=None)
        self.apps = SimpleNamespace(discover=Mock(), resolve=Mock())

    async def test_unattended_check_never_requests_consent_or_input(self):
        with patch('olive.desktop.linux.preflight.dependencies', return_value={'libei': {'available': True}}), patch('sys.platform', 'linux'):
            result = await inspect(self.client, self.apps)
        self.client.call.assert_awaited_once_with('probe', timeout=12)
        self.client.close.assert_awaited_once_with()
        self.assertEqual(result['status'], 'DEPENDENCIES_READY')
        self.assertFalse(result['consent_requested'])
        self.assertFalse(result['live_input_attempted'])

    async def test_probe_failure_still_closes_exact_owned_helper(self):
        self.client.call.side_effect = TimeoutError('private bus details')
        with patch('olive.desktop.linux.preflight.dependencies', return_value={}), patch('sys.platform', 'linux'):
            result = await inspect(self.client, self.apps)
        self.assertEqual(result['probe_error'], 'TimeoutError')
        self.assertEqual(result['status'], 'BLOCKED_SETUP')
        self.client.close.assert_awaited_once_with()
        self.assertNotIn('private', str(result))

    async def test_missing_dependency_does_not_become_a_human_consent_issue(self):
        result = classify({'pipewiresrc': {'available': False}}, self.caps)
        self.assertEqual(result['status'], 'BLOCKED_SETUP')
        self.assertEqual(result['missing'], ['pipewiresrc'])
