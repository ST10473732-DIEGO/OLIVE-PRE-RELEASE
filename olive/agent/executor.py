from __future__ import annotations

import asyncio
from copy import deepcopy
import time

from .confirmation_service import ConfirmationRequest
from .permission_service import PermissionDecision
from .tool_result import ToolResult


class ToolExecutor:
    def __init__(self, registry, permissions, confirmations, audit, tool_host=None):
        self.registry, self.permissions, self.confirmations, self.audit = registry, permissions, confirmations, audit
        if tool_host is None:
            from ..tools.host import InProcessToolHost
            tool_host = InProcessToolHost(registry)
        self.tool_host = tool_host

    async def execute(self, task, action, context) -> ToolResult:
        from ..interaction.trace import event
        event("tool_attempt", capability=action.tool_name)
        tool = self.registry.require(action.tool_name); definition = tool.definition
        definition.validate_arguments(action.arguments)
        target = _target_from(action.arguments)
        evaluations = [self.permissions.evaluate(permission, _target_for_permission(permission, action.arguments))
                       for permission in definition.required_permissions]
        if action.tool_name == "terminal.run":
            from ..tools.terminal import TerminalRunTool
            if TerminalRunTool.requires_admin(str(action.arguments.get("command", ""))):
                evaluations.append(self.permissions.evaluate("terminal.admin", target))
        denied = next((item for item in evaluations if item.decision == PermissionDecision.DENY), None)
        if denied:
            result = ToolResult.failure(f"Permission denied: {denied.permission}", "PermissionDenied")
            self._audit(task, action, result, "deny", None); return result
        from .direct_action import DirectAction
        direct = (isinstance(context.direct_action, DirectAction)
                  and context.direct_action.consume(task.id, action.tool_name, action.arguments))
        trusted = direct or self.permissions.is_action_trusted(action.tool_name, target)
        asks = [] if trusted else [item for item in evaluations if item.decision == PermissionDecision.ASK]
        confirmation = None
        if asks or (definition.confirmation_required and not trusted):
            task.transition("waiting_for_confirmation")
            confirmation_request = ConfirmationRequest(
                task.id, definition.name, action.rationale or f"Run {definition.name}", definition.risk_level,
                [target] if target else [], action.tool_name in {
                    "system.open_application", "system.close_application", "system.terminate_application"})
            approved_arguments = deepcopy(action.arguments)
            approved_tool = action.tool_name
            confirmation_request.arguments = deepcopy(approved_arguments)
            confirmation = await self.confirmations.request(confirmation_request)
            if confirmation.cancel_task:
                task.transition("cancelled")
                result = ToolResult.failure("Task cancelled by user", "Cancelled")
                self._audit(task, action, result, "ask", "cancelled"); return result
            if not confirmation.approved:
                result = ToolResult.failure("Action was not approved", "ConfirmationDenied")
                self._audit(task, action, result, "ask", "denied"); return result
            if action.tool_name != approved_tool or action.arguments != approved_arguments or confirmation_request.arguments != approved_arguments:
                result = ToolResult.failure("The action changed while approval was pending. Review it again.", "StaleApproval")
                self._audit(task, action, result, "ask", "stale"); return result
            if any(self.permissions.evaluate(permission, _target_for_permission(permission, action.arguments)).decision == PermissionDecision.DENY
                   for permission in definition.required_permissions):
                result = ToolResult.failure("Permission changed while approval was pending", "PermissionDenied")
                self._audit(task, action, result, "deny", "invalidated"); return result
            if confirmation_request.allow_remember and target:
                if confirmation.remember_all: self.permissions.trust_action(action.tool_name, "*")
                elif confirmation.remember: self.permissions.trust_action(action.tool_name, target)
        if context.cancellation_event and context.cancellation_event.is_set():
            return ToolResult.failure("Task cancelled", "Cancelled")
        task.transition("running"); started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.tool_host.execute(action.tool_name, action.arguments, context), definition.timeout_seconds)
            if not isinstance(result, ToolResult): raise TypeError("Tool returned an invalid result")
        except asyncio.TimeoutError:
            result = ToolResult.failure(f"Tool timed out after {definition.timeout_seconds:g}s", "Timeout")
        except Exception as exc:
            result = ToolResult.failure(str(exc) or type(exc).__name__, type(exc).__name__)
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        decision = "ask" if asks else "allow"
        self._audit(task, action, result, decision, "direct_user_action" if direct else "approved" if confirmation else None)
        return result

    def _audit(self, task, action, result, decision, confirmation):
        target = _target_from(action.arguments)
        metadata = f"argument keys: {', '.join(sorted(action.arguments))}" + (f"; target: {target}" if target else "")
        self.audit.record(task_id=task.id, tool=action.tool_name, requested_action=metadata,
                          result_status="success" if result.success else "failure",
                          permission_decision=decision, confirmation_result=confirmation)


def _target_from(arguments: dict) -> str | None:
    for key in ("path", "destination", "working_directory", "workspace", "application", "url"):
        if arguments.get(key): return str(arguments[key])
    if arguments.get("location") and arguments.get("name"):
        return str(__import__("pathlib").Path(arguments["location"]) / arguments["name"])
    return None


def _target_for_permission(permission: str, arguments: dict) -> str | None:
    if permission.startswith("network.") or permission == "knowledge.write":
        return None  # Web permissions are global rules, never filesystem path scopes.
    workspace=arguments.get("workspace")
    relative = (arguments.get("destination") or arguments.get("path")) if permission == "filesystem.write" else arguments.get("path")
    if not relative and arguments.get("location") and arguments.get("name"):
        relative = str(__import__("pathlib").Path(arguments["location"]) / arguments["name"])
    if workspace and relative and not __import__("pathlib").Path(str(relative)).is_absolute():
        relative=str(__import__("pathlib").Path(str(workspace))/str(relative))
    if permission == "filesystem.write": return str(relative or workspace or "") or None
    if permission in {"filesystem.read", "filesystem.delete"}: return str(relative or workspace or "") or None
    return _target_from(arguments)
