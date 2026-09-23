"""Live authorization boundary shared by generic desktop workflows and manual UI."""

import asyncio
from dataclasses import asdict
import hashlib
import json
import secrets
import os
import re

from ..agent.confirmation_service import ConfirmationRequest
from ..agent.permission_service import PermissionDecision
from ..agent.tool_schema import ToolDefinition, ToolContext
from ..agent.tool_result import ToolResult
from .target_resolver import DesktopTargetResolver


class DesktopOperationTool:
    def __init__(self, provider, stop, action):
        self.provider, self.stop, self.action = provider, stop, action
        permission = "desktop.inspect_application" if action == "observe" else "desktop.view_screen" if action == "capture" else "desktop.control_application"
        self.definition = ToolDefinition("desktop." + action, "Authorized semantic Windows operation", "desktop",
            {"required": ["window"]}, required_permissions=(permission,))

    async def execute(self, arguments, context):
        # This internal tool requires a capability installed by the gateway, not a model argument.
        if context.progress_callback is not self or self.stop.is_set():
            raise PermissionError("Desktop gateway authorization required")
        if self.action == 'observe':
            from ..runtime.request_diagnostics import stage
            stage('observation_provider', provider=True)
        value = await self.provider.call(self.action, **arguments)
        return ToolResult(True, "Windows operation returned; verification pending", value)


class DesktopGateway:
    ACTIONS = ("invoke", "select", "expand", "collapse", "set_text", "focus", "scroll", "activate", "toggle", "observe", "capture", "search", "submit_message")

    def __init__(self, provider, registry, permissions, confirmations, audit, stop, settings):
        self.provider, self.registry, self.permissions = provider, registry, permissions
        self.confirmations, self.audit, self.stop, self.settings = confirmations, audit, stop, settings
        from .task_authority import TaskAuthority
        self.trusted_tasks = TaskAuthority(stop)
        self.permits = {}
        self.last_verified_window = None
        self.ui_owner = lambda pid: pid == os.getpid()
        for action in self.ACTIONS:
            registry.register(DesktopOperationTool(provider, stop, action))

    def check(self):
        if self.stop.is_set():
            raise asyncio.CancelledError("Desktop control stopped")
        if not self.settings()["enabled"]:
            raise PermissionError("Enable Desktop Control in settings first")

    def require_uia(self):
        self.check()
        if not self.settings()["uia"]:
            raise PermissionError("Enable UI Automation before inspecting or operating accessible controls")

    async def approval(self, session, permission, summary, details, *, always=False, explicit=False):
        self.check()
        if permission == 'communication.send':
            from .communication_policy import require_supported_ui_sender
            require_supported_ui_sender(session,details.get('url',''))
        if session.window:
            details = {**details,'window_identity':{key:session.window.get(key) for key in
                ('hwnd','pid','process_created','title','executable')}}
        decision = self.permissions.evaluate(permission, details.get("path"), application=session.identity.id).decision
        if decision == PermissionDecision.DENY:
            raise PermissionError("Permission denied: " + permission)
        from ..interaction.request_consent import requested_gateway_permission
        direct = not explicit and requested_gateway_permission(permission)
        if (always or decision == PermissionDecision.ASK) and not direct:
            request = ConfirmationRequest(session.task_id, permission, summary, "high" if always else "medium",
                [session.identity.display_name], arguments=details)
            response = await self.confirmations.request(request)
            self.check()
            if response.cancel_task:
                raise asyncio.CancelledError("Cancelled by user")
            if not response.approved:
                raise PermissionError("Action was not approved")
        # A policy may change while its confirmation dialog is open.
        self.require_not_denied(session, permission, details.get("path"))

    def require_not_denied(self, session, permission, path=None):
        """Recheck existing authorization at use time; this never grants approval."""
        self.check()
        if self.permissions.evaluate(permission, path, application=session.identity.id).decision == PermissionDecision.DENY:
            raise PermissionError("Permission was revoked: " + permission)

    async def observe(self, session, *, control_limit=300, depth_limit=16):
        from ..runtime.request_diagnostics import stage
        stage('inspection_permission')
        if type(control_limit) is not int or not 1 <= control_limit <= 1200 or type(depth_limit) is not int or not 1 <= depth_limit <= 24:
            raise ValueError("Accessibility observation exceeds its bounded budget")
        self.require_uia()
        unknown = not session.identity.adapter
        if unknown and self.settings()["unknown_app_policy"] == "deny":
            raise PermissionError("Generic application inspection is disabled by the unknown-app policy")
        if self.permissions.evaluate("desktop.inspect_application", application=session.identity.id).decision == PermissionDecision.DENY:
            raise PermissionError("Application inspection is denied")
        if "desktop.inspect_application" not in session.authorized_capabilities:
            stage('inspection_approval')
            await self.approval(session, "desktop.inspect_application", "Inspect this application's accessible controls",
                                {"application": session.identity.display_name},
                                always=unknown and self.settings()["unknown_app_policy"] == "ask")
            session.authorized_capabilities.add("desktop.inspect_application")
        tool = self.registry.require("desktop.observe")
        from .errors import ObservationUnavailable
        import asyncio
        for attempt in range(3):
            self.require_not_denied(session, "desktop.inspect_application")
            try:
                arguments = {"window": session.window}
                if control_limit != 300 or depth_limit != 16:
                    arguments.update(control_limit=control_limit, depth_limit=depth_limit)
                stage('observation_dispatch')
                result = await tool.execute(arguments, ToolContext(session.task_id, progress_callback=tool))
                return result.data
            except ObservationUnavailable:
                if attempt == 2:
                    raise
                await asyncio.sleep(.1)  # Retry only the read, never an input or submission.

    @staticmethod
    def fingerprint(session, step):
        content = {"task": session.task_id, "application": session.identity.id, "window": session.window,
                   "step": asdict(step)}
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()

    async def authorize(self, session, step):
        self.require_uia()
        if step.action == "submit_message":
            raise PermissionError("Message submission requires the dedicated consequence review")
        control = DesktopTargetResolver().resolve(session.observations[-1]["controls"], step.target)
        if control.get("password"):
            raise PermissionError("Secret input requires user takeover")
        if "expected_previous" in step.arguments and control.get("value", "") != step.arguments["expected_previous"]:
            raise PermissionError("The field changed before text-entry review")
        if step.arguments.get("pointer_focus"):
            if control.get("control_type") != "Edit" or self.settings()["mouse_policy"] == "deny":
                raise PermissionError("Reviewed mouse focus requires an accessible editor and enabled mouse input")
            await self.approval(session, "desktop.mouse_input", "Place the caret in the selected editor", {
                "application": session.identity.display_name, "target": control["name"]}, always=True)
        label = control.get("name", "").casefold()
        consequential = {"send": "communication.send", "install": "software.install", "buy": "software.purchase",
                         "purchase": "software.purchase", "delete": "application.delete", "submit": "application.submit",
                         "upload": "application.upload", "subscribe": "software.purchase", "pay": "software.purchase",
                         "confirm": "application.submit", "checkout": "software.purchase", "post": "communication.send"}
        words = set(re.findall(r"\w+", label))
        acquisition = control.get("automation_id", "").casefold() in {"acquirenewproduct", "installbutton", "purchasebutton"}
        if step.action in {"invoke", "select", "toggle"} and (acquisition or "get" in words or any(word in words for word in consequential)):
            raise PermissionError("This operation requires a dedicated semantic consequence preview")
        if step.action == "search":
            from .privacy import search_field
            if not search_field(control):
                raise PermissionError("Select a clearly identified accessible search field")
            await self.approval(session, "application.search", "Search within this application",
                                {"application": session.identity.display_name, "target": control["name"], "query": step.arguments["text"]}, always=True)
        if step.action in {"set_text", "search"}:
            if self.settings()["keyboard_policy"] == "deny":
                raise PermissionError("Keyboard input is disabled in Desktop Control settings")
            await self.approval(session, "desktop.keyboard_input", "Enter text in the selected control",
                                {"application": session.identity.display_name, "target": control["name"],
                                 "text": step.arguments.get("text", ""),
                                 **({"previous_text": step.arguments["expected_previous"]} if "expected_previous" in step.arguments else {})}, always=True)
        await self.approval(session, "desktop.control_application", "Perform " + step.action + " on " + control["name"],
                            {"application": session.identity.display_name, "target": control["name"], "action": step.action},
                            always=step.action != "set_text")
        token = secrets.token_hex(24)
        self.permits[token] = self.fingerprint(session, step)
        return token

    async def execute(self, session, step, permit, stop):
        self.require_uia()
        if step.permission == 'communication.send':
            from .communication_policy import require_supported_ui_sender
            require_supported_ui_sender(session)
        if self.permits.pop(permit, None) != self.fingerprint(session, step):
            raise PermissionError("Action changed after approval")
        self.require_not_denied(session, "desktop.control_application")
        if step.arguments.get("pointer_focus"):
            self.require_not_denied(session, "desktop.mouse_input")
            if self.settings()["mouse_policy"] == "deny":
                raise PermissionError("Mouse input is disabled")
        if step.action in {"set_text", "search", "submit_message"}:
            self.require_not_denied(session, "desktop.keyboard_input")
            if self.settings()["keyboard_policy"] == "deny":
                raise PermissionError("Keyboard input is disabled")
        if step.action == "search":
            self.require_not_denied(session, "application.search")
        if step.permission != "desktop.control_application":
            self.require_not_denied(session, step.permission)
        def focus_owner():
            import win32gui
            import win32process
            handle = win32gui.GetForegroundWindow()
            return handle, win32process.GetWindowThreadProcessId(handle)[1]
        handle, owner = await asyncio.to_thread(focus_owner)
        previous = self.last_verified_window
        from .window_identity import foreground_matches
        planned_switch = previous and foreground_matches(previous, handle, owner)
        if self.ui_owner(owner) or (planned_switch and handle != session.window["hwnd"]):
            # Return focus once from OLIVE's own approval UI; never override another app.
            await self.provider.call("activate", session.window, expected_foreground={"hwnd": handle, "pid": owner})
        elif not foreground_matches(session.window, handle, owner):
            raise PermissionError("Desktop control paused because focus changed")
        self.check()
        tool = self.registry.require("desktop." + step.action)
        result = await tool.execute({"window": session.window, "target": step.target, **step.arguments},
                                    ToolContext(session.task_id, cancellation_event=stop, progress_callback=tool))
        self.audit.record(task_id=session.task_id, tool=tool.definition.name,
            requested_action="application=" + session.identity.id + "; action=" + step.action,
            result_status="acted_unverified", permission_decision="allow", confirmation_result="approved")
        return result.data

    def verified(self, session, step):
        self.last_verified_window = dict(session.window)
