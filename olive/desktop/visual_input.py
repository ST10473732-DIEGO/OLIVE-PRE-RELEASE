"""Reviewed visual fallback bound to an unchanged window capture, not arbitrary XY."""

import asyncio
import hashlib
from pathlib import Path
import re
from .coordinates import screen_point

from ..agent.tool_schema import ToolDefinition, ToolContext
from ..agent.tool_result import ToolResult


class VisualClickTool:
    def __init__(self, desktop):
        self.desktop = desktop
        self.definition = ToolDefinition("desktop.visual_click", "Reviewed window-scoped visual fallback", "desktop", {})

    async def execute(self, arguments, context):
        if context.progress_callback is not self:
            raise PermissionError("Visual input gateway authorization required")
        self.desktop.gateway.check()
        result = await self.desktop.provider.call("visual_click", **arguments)
        return ToolResult(True, "Visual click requested; verification pending", result)


class VisualInput:
    def __init__(self, desktop):
        self.desktop = desktop
        self.proposals = {}
        desktop.s.tool_registry.register(VisualClickTool(desktop))

    def remember(self, result):
        self.proposals.clear()
        self.proposals[result["capture_id"]] = dict(result)

    async def click(self, capture_id, expected):
        d = self.desktop
        if not d.configuration()["vision_fallback"] or d.configuration()["mouse_policy"] == "deny":
            raise PermissionError("Enable vision fallback and reviewed mouse input first")
        proposal = self.proposals.get(capture_id)
        if not proposal or not proposal["target_found"] or proposal["confidence"] < .85:
            raise ValueError("A confident observed visual target is required")
        if not isinstance(expected, str) or not 1 <= len(expected.strip()) <= 300:
            raise ValueError("Specify the expected visible control after the click")
        words = set(re.findall(r"\w+", proposal["target_label"].casefold()))
        if words & {"get", "send", "install", "buy", "purchase", "delete", "submit", "subscribe", "upload", "pay", "confirm", "checkout", "post"}:
            raise PermissionError("Consequential visual actions require a supported semantic preview")
        session = d.sessions.sessions[d.sessions.current]
        old = d.screenshots.records[capture_id]
        old_hash = hashlib.sha256(Path(old["path"]).read_bytes()).digest()
        if old["task_id"] != session.task_id or old["window"]["hwnd"] != session.window["hwnd"]:
            raise PermissionError("Visual target belongs to another task or application")
        before = await d.gateway.observe(session)
        if any(control.get("name") == expected for control in before["controls"]):
            raise ValueError("Expected result is already visible; choose a new postcondition")
        if any(control.get("name", "").casefold() == proposal["target_label"].casefold() and "invoke" in control.get("actions", []) for control in before["controls"]):
            raise ValueError("This target exposes semantic invocation; use the accessible control")
        details = {"application": session.identity.display_name, "target": proposal["target_label"],
                   "action": "single visual click", "expected": expected}
        await d.gateway.approval(session, "desktop.control_application", "Review visual fallback", details, always=True)
        await d.gateway.approval(session, "desktop.mouse_input", "Click the reviewed visual target once", details, always=True)
        # A confirmation may take minutes. Recapture and require exact same pixels
        # rather than silently using coordinates from an old application state.
        capture = await d.screenshot()
        if (old.get("client_bounds") != capture.get("client_bounds") or
            old_hash != hashlib.sha256(Path(capture["path"]).read_bytes()).digest()):
            raise ValueError("Application pixels changed; locate and review the target again")
        d.screenshots.validate_target(capture["id"], session.window, proposal["bounds"])
        point = screen_point(capture, proposal["bounds"])
        d.gateway.require_not_denied(session, "desktop.control_application")
        d.gateway.require_not_denied(session, "desktop.mouse_input")
        # Focus can return only from OLIVE's own confirmation window.
        from .windows_observation import verify_identity
        import win32gui
        import win32process
        handle = win32gui.GetForegroundWindow()
        owner = win32process.GetWindowThreadProcessId(handle)[1]
        if handle != session.window["hwnd"] and d.gateway.ui_owner(owner):
            await d.provider.call("activate", session.window, expected_foreground={"hwnd": handle, "pid": owner})
        verify_identity(session.window, foreground=True)
        d.screenshots.validate_target(capture["id"], verify_identity(session.window), proposal["bounds"])
        tool = d.s.tool_registry.require("desktop.visual_click")
        self.proposals.pop(capture_id)
        await tool.execute({"window": capture["window"], "point": list(point), "client_bounds": capture["client_bounds"],
                            "image_hash": hashlib.sha256(Path(capture["path"]).read_bytes()).hexdigest()},
                           ToolContext(session.task_id, progress_callback=tool))
        for _ in range(30):
            observation = await d.gateway.observe(session)
            session.observe(observation)
            if len([control for control in observation["controls"] if control.get("name") == expected]) == 1:
                d.observation = observation
                d.record.verification = "Visual click followed by observed semantic postcondition"
                d.publish()
                return {"verified": True}
            await asyncio.sleep(.1)
        raise TimeoutError("Visual click was not verified; review the application before retrying")
