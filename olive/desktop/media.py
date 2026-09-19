"""Application-neutral Windows media sessions; no simulated global media keys."""

import asyncio
import os
import time
import uuid
from .application_discovery import identity
from .application_sessions import ApplicationSession
from ..agent.tool_schema import ToolContext, ToolDefinition
from ..agent.tool_result import ToolResult


class WindowsMediaProvider:
    name = "windows_system_media_sessions"

    def __init__(self, stop):
        self.stop = stop
        self.manager = None
        self.apartment = False

    async def sessions(self):
        if os.name != "nt":
            raise RuntimeError("Windows media sessions are unavailable")
        if self.stop.is_set():
            raise InterruptedError("Desktop control stopped")
        if self.manager is None:
            from winrt.runtime import init_apartment, ApartmentType
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
            init_apartment(ApartmentType.MULTI_THREADED)
            self.apartment = True
            self.manager = await asyncio.wait_for(GlobalSystemMediaTransportControlsSessionManager.request_async(), 5)
        return list(self.manager.get_sessions())[:30]

    async def list(self):
        async def describe(session):
            value = {"application_id": session.source_app_user_model_id,
                     "state": session.get_playback_info().playback_status.name.lower()}
            try:
                properties = await asyncio.wait_for(session.try_get_media_properties_async(), 5)
                value["title"] = properties.title[:300] if properties else ""
            except (TimeoutError, OSError):
                value.update(title="", metadata_state="unavailable")
            return value
        return await asyncio.gather(*(describe(session) for session in await self.sessions()))

    async def act(self, application_id, action):
        operations = {"play": "try_play_async", "pause": "try_pause_async", "next": "try_skip_next_async", "previous": "try_skip_previous_async"}
        if action not in operations:
            raise ValueError("Unsupported media command")
        sessions = [session for session in await self.sessions() if session.source_app_user_model_id == application_id]
        if len(sessions) != 1:
            raise ValueError("Select an unambiguous active media application")
        session = sessions[0]
        before = await asyncio.wait_for(session.try_get_media_properties_async(), 5)
        old_title = before.title if before else ""
        if self.stop.is_set():
            raise InterruptedError("Desktop control stopped")
        if not await asyncio.wait_for(getattr(session, operations[action])(), 5):
            raise RuntimeError("The media application declined the command")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.stop.is_set():
                raise InterruptedError("Desktop control stopped")
            state = session.get_playback_info().playback_status.name.lower()
            if action in {"play", "pause"} and state == {"play": "playing", "pause": "paused"}[action]:
                return {"application_id": application_id, "state": state, "verified": True}
            if action in {"next", "previous"}:
                current = await asyncio.wait_for(session.try_get_media_properties_async(), 5)
                if current and current.title and current.title != old_title:
                    return {"application_id": application_id, "state": state, "verified": True}
            await asyncio.sleep(.1)
        raise TimeoutError("Media command was requested, but its state change was not verified")

    def close(self):
        self.manager = None
        if self.apartment:
            from winrt.runtime import uninit_apartment
            uninit_apartment()
            self.apartment = False


class MediaTool:
    def __init__(self, provider, action):
        self.provider, self.action = provider, action
        self.definition = ToolDefinition("desktop.media_" + action, "Authorized system media operation", "desktop", {})

    async def execute(self, arguments, context):
        if context.progress_callback is not self:
            raise PermissionError("Media gateway authorization required")
        value = await self.provider.list() if self.action == "list" else await self.provider.act(**arguments)
        return ToolResult(True, "Media observation returned", value)


class MediaController:
    def __init__(self, desktop):
        self.desktop = desktop
        self.provider = WindowsMediaProvider(desktop.stop_event)
        for action in ("list", "act"):
            desktop.s.tool_registry.register(MediaTool(self.provider, action))

    async def run(self, action="list", application_id="", command=""):
        session = ApplicationSession(identity(application_id or "Windows media", "app_id", application_id or "system-media"), str(uuid.uuid4()))
        await self.desktop.gateway.approval(session, "desktop.inspect_application" if action == "list" else "application.media",
            "Inspect active media sessions" if action == "list" else "Media " + command,
            {"application": application_id or "Windows media", "action": command or "list"}, always=True)
        tool = self.desktop.s.tool_registry.require("desktop.media_" + action)
        result = await tool.execute({"application_id": application_id, "action": command}, ToolContext(session.task_id, progress_callback=tool))
        return result.data
