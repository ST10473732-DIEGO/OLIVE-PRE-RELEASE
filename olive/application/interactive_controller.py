"""Explicit, user-reviewed browser operations using an independent visible profile."""

from ..desktop.application_discovery import identity
from ..desktop.application_sessions import ApplicationSession
from ..desktop.interactive_browser import InteractiveBrowserProvider
from ..agent.tool_schema import ToolContext, ToolDefinition
from ..agent.tool_result import ToolResult
import uuid
import re


class InteractiveTool:
    def __init__(self, provider, operation):
        self.provider, self.operation = provider, operation
        self.definition = ToolDefinition("interactive." + operation, "Authorized visible browser operation", "desktop", {})

    async def execute(self, arguments, context):
        if context.progress_callback is not self:
            raise PermissionError("Interactive browser gateway authorization required")
        return ToolResult(True, "Browser observation returned", await getattr(self.provider, self.operation)(**arguments))


class InteractiveController:
    def __init__(self, desktop):
        self.desktop = desktop
        self.provider = InteractiveBrowserProvider(desktop.s.data_dir, desktop.stop_event)
        from ..desktop.browser_focus import BrowserFocusGuard
        self.focus = BrowserFocusGuard(desktop.provider, desktop.stop_event)
        from ..desktop.browser_consequences import BrowserConsequences
        self.consequences = BrowserConsequences(self)
        self.session = ApplicationSession(identity("OLIVE Interactive Browser", "profile", "interactive"), str(uuid.uuid4()))
        for operation in ("launch", "navigate", "observe", "act", "new_tab", "switch_tab", "close_tab", "field_value", "upload", "dialog_info", "dismiss_dialog"):
            desktop.s.tool_registry.register(InteractiveTool(self.provider, operation))
        desktop.s.tool_registry.register(InteractiveTool(self, "download_artifact"))

    async def execute(self, operation, **arguments):
        tool = self.desktop.s.tool_registry.require("interactive." + operation)
        result = await tool.execute(arguments, ToolContext(self.session.task_id, progress_callback=tool))
        return result.data

    async def launch(self, channel="chrome"):
        await self.desktop.gateway.approval(self.session, "desktop.control_application",
            "Open a visible OLIVE browser profile, separate from Research and your normal browser profile",
            {"application": channel}, always=True)
        import win32gui
        import win32process
        handle = win32gui.GetForegroundWindow()
        approved = {"hwnd": handle, "pid": win32process.GetWindowThreadProcessId(handle)[1]} if handle else None
        result = await self.execute("launch", channel=channel)
        await self.focus.prepare(self.provider.profile, approved_foreground=approved)
        return result

    async def navigate(self, tab_id, url):
        from ..desktop.interactive_browser import web_url
        web_url(url)
        await self.desktop.gateway.approval(self.session, "network.read", "Navigate the interactive browser",
                                            {"url": url}, always=True)
        window = await self.focus.prepare(self.provider.profile)
        result = await self.execute("navigate", tab_id=tab_id, url=url)
        self.focus.verify(window)
        return result

    async def observe(self, tab_id):
        await self.desktop.gateway.approval(self.session, "desktop.inspect_application", "Inspect the selected browser tab",
                                            {"application": "OLIVE Interactive Browser"})
        return await self.execute("observe", tab_id=tab_id)

    async def tab(self, action, tab_id="", url=""):
        if action not in {"new_tab", "switch_tab", "close_tab"}:
            raise ValueError("Unknown browser tab action")
        approved = None
        if action == "switch_tab":
            import win32gui
            import win32process
            handle = win32gui.GetForegroundWindow()
            approved = {"hwnd": handle, "pid": win32process.GetWindowThreadProcessId(handle)[1]} if handle else None
        from ..desktop.interactive_browser import web_url
        if action == "new_tab":
            if url != "about:blank":
                web_url(url)
                await self.desktop.gateway.approval(self.session, "network.read", "Navigate the new interactive browser tab",
                                                    {"url": url}, always=True)
        await self.desktop.gateway.approval(self.session, "desktop.control_application", "Browser " + action.replace("_", " "),
            {"action": action, "url": url or self.provider.pages[tab_id].url}, always=True)
        if action == "switch_tab":
            window = await self.focus.prepare(self.provider.profile, approved_foreground=approved)
            result = await self.execute(action, tab_id=tab_id)
            self.focus.verify(window)
            return result
        await self.focus.prepare(self.provider.profile)
        return await self.execute(action, **({"url": url} if action == "new_tab" else {"tab_id": tab_id}))

    async def action(self, target_id, action, value="", expected=""):
        target = self.provider.targets.get(target_id)
        if not target:
            raise ValueError("Inspect the browser again to select a current target")
        tab, url, element, observed = target
        from ..desktop.browser_semantics import accessible_name
        label = await accessible_name(element)
        if action == "click":
            words = re.findall(r"\w+", label.casefold())
            if any(word in words for word in ("get", "send", "install", "buy", "purchase", "delete", "submit", "subscribe", "upload", "pay", "confirm", "checkout", "post")):
                raise PermissionError("A dedicated consequence preview is required for this action")
            if not expected:
                raise ValueError("Specify an expected visible control to verify the click")
            if any(signature["label"] == expected for signature in self.provider.target_signatures.values()):
                raise ValueError("The expected browser state is already present; choose evidence of the click's result")
        elif action not in {"fill", "select", "scroll"}:
            raise ValueError("Unknown browser action")
        await self.desktop.gateway.approval(self.session, "desktop.control_application", "Review browser " + action,
            {"application": "Interactive browser", "url": url, "target": label, "action": action, "text": value}, always=True)
        if action == "fill":
            await self.desktop.gateway.approval(self.session, "desktop.keyboard_input", "Enter text into the browser field",
                                                {"target": label, "text": value})
            self.desktop.gateway.require_not_denied(self.session, "desktop.keyboard_input")
        self.desktop.gateway.require_not_denied(self.session, "desktop.control_application")
        window = await self.focus.prepare(self.provider.profile)
        self.provider.action_guard = lambda: self.focus.verify(window)
        result = await self.execute("act", target_id=target_id, action=action, value=value)
        self.focus.verify(window)
        if action == "click" and len([item for item in result["controls"] if item["name"] == expected]) != 1:
            raise ValueError("Click returned, but the expected browser state was not verified")
        result["verified"] = True
        return result

    async def shutdown(self):
        await self.provider.close()

    async def dialog_review(self, dismiss=False):
        await self.desktop.gateway.approval(self.session, "desktop.inspect_application", "Inspect the current browser dialog",
                                            {"application": "Interactive browser"})
        info = await self.execute("dialog_info")
        if dismiss and info["pending"]:
            await self.desktop.gateway.approval(self.session, "desktop.control_application", "Dismiss the current browser dialog",
                {"application": "Interactive browser", "dialog_type": info["type"], "message": info["message"]}, always=True)
            current = await self.execute("dialog_info")
            if current != info:
                raise PermissionError("Browser dialog changed after review")
            return await self.execute("dismiss_dialog")
        return info

    async def download(self, target_id):
        tab, _ = await self.provider.target(target_id)
        await self.desktop.gateway.approval(self.session, "network.download", "Download into OLIVE quarantine without opening or executing it",
            {"url": self.provider.pages[tab].url, "size_limit": "10 MiB", "runtime_limit": "20 seconds"}, always=True)
        window = await self.focus.prepare(self.provider.profile)
        self.provider.action_guard = lambda: self.focus.verify(window)
        return await self.execute("download_artifact", target_id=target_id)

    async def download_artifact(self, target_id):
        return await self.provider.downloads.read(target_id, self.desktop.s.research.quarantine)
