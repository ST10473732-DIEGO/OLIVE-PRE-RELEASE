from __future__ import annotations

import asyncio
import time

from .agent_task import AgentStep, AgentTask
from .tool_schema import ToolContext


class AgentOrchestrator:
    def __init__(self, planner, executor, task_repository=None, max_iterations: int = 8, max_runtime_seconds: float = 300):
        self.planner, self.executor, self.tasks = planner, executor, task_repository
        self.max_iterations = min(25, max(1, max_iterations)); self.max_runtime_seconds = max(1, max_runtime_seconds)

    async def run(self, request: str, project_id: str | None = None, cancellation_event=None) -> AgentTask:
        task = AgentTask(request, project_id); self._save(task); task.transition("planning")
        try:
            actions = await self.planner.create_plan(request, self.executor.registry.definitions())
            structured=getattr(self.planner,"last_plan",None)
            if structured:
                task.completion_conditions=list(structured.completion_conditions)
                task.reasoning_summary=structured.reasoning_summary
            task.plan = [AgentStep(a.rationale or a.tool_name, a.tool_name, dict(a.arguments)) for a in actions]
            self._save(task); observations = []; started = time.monotonic()
            for index in range(self.max_iterations):
                if cancellation_event and cancellation_event.is_set(): task.transition("cancelled"); break
                if time.monotonic() - started >= self.max_runtime_seconds:
                    task.error = "Maximum task runtime reached"; task.transition("failed"); break
                action = actions[index] if index < len(actions) else await self.planner.next_action(task, observations)
                if action is None: task.completion_summary = "Task completed"; task.transition("completed"); break
                if action.arguments.get("workspace") and not task.workspace_id: task.workspace_id=str(action.arguments["workspace"])
                if index >= len(task.plan): task.plan.append(AgentStep(action.rationale or action.tool_name, action.tool_name, dict(action.arguments)))
                result = await self.executor.execute(task, action, ToolContext(task.id, cancellation_event))
                task.plan[index].result, task.plan[index].state = result.to_dict(), "completed" if result.success else "failed"
                task.tool_calls.append({"tool": action.tool_name, "arguments": action.arguments, "result": result.to_dict()})
                if action.tool_name.startswith("code.") and result.success:
                    edit=(result.data or {}).get("edit",{}); path=edit.get("path")
                    if path and path not in task.files_changed: task.files_changed.append(path)
                    task.implementation_status="complete"
                if action.tool_name=="workspace.run_validation": task.validation_status="passed" if result.success else "failed"
                observations.append(result)
                self._save(task)
                if task.state == "cancelled": break
                if not result.success:
                    task.error = result.summary
                    replacement=await self.planner.next_action(task,observations)
                    if replacement is not None:
                        actions.append(replacement);continue
                    task.transition("failed"); break
            else:
                task.error = "Maximum tool iterations reached"; task.transition("failed")
            if task.state == "running":
                if task.completion_conditions and task.validation_status!="passed":
                    task.completion_summary="Implementation finished; validation is incomplete"
                    task.transition("failed")
                else:
                    task.completion_summary="Task completed";task.transition("completed")
        except Exception as exc:
            task.error = str(exc); task.transition("failed")
        self._save(task); return task

    def _save(self, task):
        if self.tasks: self.tasks.save(task)
