import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from olive.desktop.media import WindowsMediaProvider, MediaTool
from olive.desktop.emergency_stop import EmergencyStop
from olive.agent.tool_schema import ToolContext


class MediaControlTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = WindowsMediaProvider(EmergencyStop())
        self.state = "PLAYING"
        self.session = Mock(source_app_user_model_id="UnknownMediaApp")
        self.session.get_playback_info.side_effect = lambda: SimpleNamespace(playback_status=SimpleNamespace(name=self.state))
        self.session.try_get_media_properties_async = AsyncMock(return_value=SimpleNamespace(title="Fixture"))
        async def pause():
            self.state = "PAUSED"
            return True
        self.session.try_pause_async = AsyncMock(side_effect=pause)
        self.provider.sessions = AsyncMock(return_value=[self.session])

    async def test_generic_media_pause_verifies_state_without_adapter(self):
        result = await self.provider.act("UnknownMediaApp", "pause")
        self.assertTrue(result["verified"])
        self.assertEqual(result["state"], "paused")

    async def test_emergency_stop_prevents_media_command(self):
        self.provider.stop.set()
        with self.assertRaises(InterruptedError):
            await self.provider.act("UnknownMediaApp", "pause")
        self.session.try_pause_async.assert_not_awaited()

    async def test_ambiguous_media_sessions_are_not_guessed(self):
        self.provider.sessions.return_value = [self.session, self.session]
        with self.assertRaises(ValueError):
            await self.provider.act("UnknownMediaApp", "pause")
        self.session.try_pause_async.assert_not_awaited()

    async def test_model_cannot_invoke_media_tool_directly(self):
        with self.assertRaises(PermissionError):
            await MediaTool(self.provider, "act").execute({}, ToolContext("task"))
