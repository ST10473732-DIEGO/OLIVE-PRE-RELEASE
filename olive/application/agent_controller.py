"""Task presentation, pause gates and explicit user tool actions."""

import asyncio

from ..agent.agent_task import AgentTask
from ..agent.planner import PlannedAction
from ..agent.tool_schema import ToolContext


class ObservedExecutor:
    def __init__(self, controller, executor):
        self.controller = controller
        self.executor = executor
        self.registry = executor.registry

    async def execute(self, task, action, context):
        owner = self.controller
        owner.current = task
        await owner.wait_for_resume(task)
        if context.cancellation_event and context.cancellation_event.is_set():
            from ..agent.tool_result import ToolResult
            task.transition("cancelled")
            return ToolResult.failure("Task cancelled", "Cancelled")
        owner.publish(task)
        result = await self.executor.execute(task, action, context)
        owner.publish(task)
        return result


class AgentController:
    def __init__(self, services):
        self.s = services
        self.current = None
        self.tool_cancellations = set()
        self.active = None
        self.desktop_active = False
        self.pause_effective = False
        self.cancel_event = asyncio.Event()
        self.gate = asyncio.Event()
        self.gate.set()
        self.s.agent_orchestrator.executor = ObservedExecutor(self, self.s.agent_executor)

    def publish(self, task):
        self.s.agent_task_repo.save(task)
        self.s.publish("agent", task.to_dict())

    def history(self):
        return [
            task.to_dict()
            for task in sorted(
                self.s.agent_task_repo.load_all().values(), key=lambda t: t.updated_at, reverse=True
            )
        ]

    def actions(self):
        return self.s.agent_audit.list_recent(200)

    async def run(self, request, workspace_id=None, project_id=None):
        if self.active:
            raise ValueError("An Agent task is already active. Pause or cancel it before starting another.")
        if not request.strip():
            raise ValueError("Enter an objective")
        if request.casefold().startswith("desktop:") and not workspace_id:
            task = AgentTask("User-directed desktop task", project_id=project_id)
            self.current = task
            self.active = asyncio.current_task()
            self.desktop_active = True
            try:
                task.transition("planning")
                self.publish(task)
                task.transition("running")
                self.publish(task)
                result = await self.s.desktop.run_request(request.split(":", 1)[1].strip())
                task.transition("completed")
                task.validation_status = "passed"
                task.completion_summary = result["session"]["verification"]
                self.publish(task)
                return task.to_dict()
            except asyncio.CancelledError:
                task.transition("cancelled")
                self.publish(task)
                raise
            except Exception as error:
                task.transition("failed")
                task.error = str(error)
                self.publish(task)
                raise
            finally:
                self.active = None
                self.desktop_active = False
        if workspace_id:
            workspace = self.s.workspace_repo.load_all()[workspace_id]
            request += f" in {workspace.title}"
            project_id = workspace.project_id
        self.cancel_event = asyncio.Event()
        self.gate.set()
        self.active = asyncio.current_task()
        try:
            task = await self.s.agent_orchestrator.run(request, project_id, self.cancel_event)
            self.current = task
            self.publish(task)
            return task.to_dict()
        finally:
            self.active = None
            self.s.publish("status", self.s.data.status())

    def pause(self):
        if self.desktop_active:
            self.s.desktop.pause()
        self.gate.clear()
        if self.current and self.active:
            self.publish(self.current)
        return "Pause requested; the current tool finishes safely before the next step."

    @property
    def pause_state(self):
        if not self.active or self.gate.is_set():
            return "none"
        return "paused" if self.pause_effective else "pausing"

    async def wait_for_resume(self, task):
        """Pause only at a safe boundary, never while a tool is executing."""
        if not self.gate.is_set():
            self.pause_effective = True
            task.transition("paused")
            self.publish(task)
        try:
            await self.gate.wait()
        finally:
            self.pause_effective = False
        if task.state == "paused" and not self.cancel_event.is_set():
            task.transition("running")
            self.publish(task)

    async def resume(self, task_id=None):
        if self.desktop_active:
            self.s.desktop.resume()
        if self.active:
            self.gate.set()
            if self.current:
                self.publish(self.current)
            return self.current.to_dict() if self.current else None
        if not task_id:
            raise ValueError("Select a paused task from history")
        task = self.s.agent_task_repo.load_all()[task_id]
        if task.state != "paused":
            raise ValueError("Only paused tasks may be resumed")
        if not task.plan:
            raise ValueError(
                "This task has no saved plan. Start a new objective after reviewing its history."
            )
        self.active = asyncio.current_task()
        self.current = task
        self.cancel_event = asyncio.Event()
        self.gate.set()
        try:
            task.transition("running")
            for step in task.plan:
                if step.state == "completed":
                    continue
                if self.cancel_event.is_set():
                    task.transition("cancelled")
                    break
                await self.wait_for_resume(task)
                if self.cancel_event.is_set():
                    task.transition("cancelled")
                    break
                result = await self.s.agent_executor.execute(
                    task,
                    PlannedAction(step.tool_name, step.arguments, "Resume saved step: " + step.description),
                    ToolContext(task.id, self.cancel_event),
                )
                step.result = result.to_dict()
                step.state = "completed" if result.success else "failed"
                task.tool_calls.append(
                    {"tool": step.tool_name, "arguments": step.arguments, "result": result.to_dict()}
                )
                if step.tool_name == "workspace.run_validation":
                    task.validation_status = "passed" if result.success else "failed"
                if not result.success:
                    task.error = result.summary
                    task.transition("cancelled" if result.error_type == "Cancelled" else "failed")
                self.publish(task)
                if not result.success:
                    break
            else:
                task.transition("completed")
                task.completion_summary = "Saved task steps completed"
            self.publish(task)
            return task.to_dict()
        finally:
            self.active = None

    def cancel(self):
        if self.desktop_active:
            self.s.desktop.stop()
        self.cancel_event.set()
        self.gate.set()

    def cancel_tools(self):
        for cancellation in self.tool_cancellations:
            cancellation.set()

    async def tool(self, name, arguments, summary=None, retain_failure=False, progress=None, *, direct_user_action=False, cancellation_event=None, return_outcome=False):
        task = AgentTask(summary or name)
        self.s.agent_task_repo.save(task)
        cancellation = cancellation_event if cancellation_event is not None else asyncio.Event()
        self.tool_cancellations.add(cancellation)
        from ..agent.direct_action import DirectAction
        from ..interaction.request_consent import requested_tool
        consent = DirectAction(task.id, name, arguments) if direct_user_action or requested_tool(name) else None
        try:
            result = await self.s.agent_executor.execute(
                task,
                PlannedAction(name, arguments, summary or name),
                ToolContext(task.id, cancellation, progress_callback=progress, direct_action=consent),
            )
        except asyncio.CancelledError:
            task.transition('cancelled')
            task.completion_summary = 'The request was cancelled. Inspect its output for earlier completed work; cancellation does not roll back side effects.'
            self.s.agent_task_repo.save(task)
            raise
        finally:
            self.tool_cancellations.discard(cancellation)
        task.tool_calls.append({"tool": name, "arguments": arguments, "result": result.to_dict()})
        task.transition("completed" if result.success else "cancelled" if result.error_type == "Cancelled" else "failed")
        task.completion_summary = result.summary
        if name == "workspace.run_validation":
            task.validation_status = ("passed" if result.success else "cancelled" if result.error_type == "Cancelled"
                                      else "failed" if result.data.get("results") else "not_run")
        self.s.agent_task_repo.save(task)
        if return_outcome:
            state = ("completed" if result.success else "cancelled" if result.error_type == "Cancelled"
                     else "blocked" if result.error_type in {"PermissionDenied", "ConfirmationDenied", "StaleApproval"}
                     else "failed")
            return {**result.data, "task_id": task.id, "state": state,
                    "summary": result.summary, "error_type": result.error_type}
        if not result.success and (
            not retain_failure or result.error_type in {"PermissionDenied", "ConfirmationDenied", "Cancelled"}
        ):
            raise PermissionError(result.summary)
        return result.data
