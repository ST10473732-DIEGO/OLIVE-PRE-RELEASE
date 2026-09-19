import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from olive.desktop.browser_focus import BrowserFocusGuard
from olive.desktop.emergency_stop import EmergencyStop


class BrowserFocusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = Mock(call=AsyncMock())
        self.stop = EmergencyStop()
        self.guard = BrowserFocusGuard(self.provider, self.stop)
        self.target = {"hwnd": 100, "pid": 200}
        self.foreground = Mock(return_value=100)
        self.owner = Mock(return_value=(1, 200))
        self.catalog = self.enterContext(patch("olive.desktop.browser_focus.profile_windows", return_value=[self.target]))
        self.verify = self.enterContext(patch("olive.desktop.windows_observation.verify_identity"))
        self.enterContext(patch.dict("sys.modules", {
            "win32gui": Mock(GetForegroundWindow=self.foreground),
            "win32process": Mock(GetWindowThreadProcessId=self.owner)}))

    async def test_foreground_browser_does_not_steal_focus(self):
        self.assertEqual(await self.guard.prepare("profile"), self.target)
        self.provider.call.assert_not_awaited()
        self.verify.assert_called_once_with(self.target, foreground=True)

    async def test_confirmation_window_handoff_is_identity_bound(self):
        self.foreground.return_value = 300
        self.owner.return_value = (1, os.getpid())
        await self.guard.prepare("profile")
        self.provider.call.assert_awaited_once_with("activate", self.target,
            expected_foreground={"hwnd": 300, "pid": os.getpid()})

    async def test_unrelated_foreground_pauses_without_activation(self):
        self.foreground.return_value = 300
        self.owner.return_value = (1, os.getpid() + 1)
        with self.assertRaisesRegex(PermissionError, "focus changed"):
            await self.guard.prepare("profile")
        self.provider.call.assert_not_awaited()

    async def test_supervised_electron_handoff_still_rejects_user_takeover(self):
        self.guard.ui_owner = lambda pid: pid == 91234
        self.foreground.return_value = 300
        self.owner.return_value = (1, 91234)
        await self.guard.prepare('fixture-profile')
        self.provider.call.assert_awaited_once_with('activate', self.target, expected_foreground={'hwnd':300,'pid':91234})
        self.provider.call.reset_mock()
        self.owner.return_value = (1, 81234)
        with self.assertRaisesRegex(PermissionError, 'focus changed'):
            await self.guard.prepare('fixture-profile')
        self.provider.call.assert_not_awaited()

    async def test_explicit_application_switch_is_bound_to_approved_foreground(self):
        self.foreground.return_value = 300
        self.owner.return_value = (1, os.getpid() + 1)
        approved = {"hwnd": 300, "pid": os.getpid() + 1}
        await self.guard.prepare("profile", approved_foreground=approved)
        self.provider.call.assert_awaited_once()
        self.provider.call.reset_mock()
        self.foreground.return_value = 301
        with self.assertRaisesRegex(PermissionError, "focus changed"):
            await self.guard.prepare("profile", approved_foreground=approved)
        self.provider.call.assert_not_awaited()

    async def test_ambiguous_browser_windows_are_not_guessed(self):
        self.catalog.return_value = [self.target, {"hwnd": 301, "pid": 200}]
        with self.assertRaisesRegex(PermissionError, "ambiguous"):
            await self.guard.prepare("profile")
        self.provider.call.assert_not_awaited()

    async def test_stop_blocks_focus_handoff(self):
        self.stop.set()
        with self.assertRaises(InterruptedError):
            await self.guard.prepare("profile")
        self.catalog.assert_not_called()
