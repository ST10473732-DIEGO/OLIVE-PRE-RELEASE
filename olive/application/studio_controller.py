"""Shared workspace/editor/run state and permission-controlled actions."""

import asyncio
from dataclasses import asdict
from collections import OrderedDict
import uuid

from ..services.studio_service import StudioService
from ..services.workspace_service import require_approved_workspace
from .studio_tools import StudioAccessTool


def bounded_validation_results(results, limit=12000):
    """Retain the latest output within a fixed snapshot budget, without losing step states."""
    bounded = [dict(item) for item in results]
    remaining = limit
    for item in reversed(bounded):
        for key in ("stderr", "stdout"):
            text = str(item.get(key, ""))
            retained = text[-remaining:] if remaining else ""
            if len(retained) < len(text):
                item["output_truncated"] = True
            item[key] = retained
            remaining -= len(retained)
    return bounded


class StudioController:
    def __init__(self, services):
        self.s = services
        self.services = {}
        self.locks = {}
        self.monitors = set()
        self.terminal_ids = {}
        self.launching = set()
        self.package_cancellations = {}
        self.validations = OrderedDict()
        self.validation_cancellations = {}
        from .package_tool import PackageInstallTool
        self.s.tool_registry.register(PackageInstallTool(self))
        from ..tools.studio import StudioInputTool
        self.s.tool_registry.register(StudioInputTool(self.s))
        for action in ("tree", "open", "create", "save", "search", "rollback", "compare", "rebase"):
            self.s.tool_registry.register(StudioAccessTool(self, action))

    def service(self, workspace):
        approved = require_approved_workspace(self.s.workspace_repo, workspace)
        if approved.id not in self.services:
            self.services[approved.id] = StudioService(approved, self.s.checkpoints)
        return self.services[approved.id]

    async def install_package(self, workspace_id, manager, package):
        workspace = require_approved_workspace(self.s.workspace_repo, workspace_id)
        if workspace.id in self.package_cancellations:
            raise ValueError('A package installation is already running in this workspace.')
        cancellation = asyncio.Event()
        self.package_cancellations[workspace.id] = cancellation
        try:
            async with self.locks.setdefault(workspace.id, asyncio.Lock()):
                return await self.s.agent.tool('studio.install_package',
                    {'workspace':workspace.root_path, 'manager':manager, 'package':package},
                    f'Install {package} in {workspace.title}', retain_failure=True, direct_user_action=True,
                    cancellation_event=cancellation)
        finally:
            self.package_cancellations.pop(workspace.id, None)

    def cancel_install(self, workspace_id):
        cancellation = self.package_cancellations.get(workspace_id)
        if cancellation:
            cancellation.set()
        return {'cancellation_requested': bool(cancellation)}

    async def access(self, workspace_id, action, *, direct_user_action=False, **arguments):
        if action not in {"tree", "open", "create", "save", "search", "rollback", "compare", "rebase"}:
            raise ValueError("Unknown Studio action")
        workspace = require_approved_workspace(self.s.workspace_repo, workspace_id)
        arguments["workspace"] = workspace.root_path
        async with self.locks.setdefault(workspace.id, asyncio.Lock()):
            result = await self.s.agent.tool(
                f"studio.{action}", arguments, f"{action.title()} {arguments.get('path', workspace.title)}",
                direct_user_action=direct_user_action,
            )
            if action == "open" and hasattr(self.s, "interaction"):
                self.s.interaction.selected_workspace = workspace.id
                self.s.interaction.selected_file = str(workspace.resolve(arguments["path"]))
            return result

    async def git(self, workspace_id, action="status", *, direct_user_action=False, **arguments):
        if action not in {
            "status",
            "diff",
            "log",
            "branch_list",
            "add",
            "commit",
            "create_branch",
            "checkout",
        }:
            raise ValueError("Unsupported Git action")
        workspace = require_approved_workspace(self.s.workspace_repo, workspace_id)
        return await self.s.agent.tool(f"git.{action}", dict(arguments, workspace=workspace.root_path), direct_user_action=direct_user_action)

    async def run(self, workspace_id, *, direct_user_action=False):
        workspace = require_approved_workspace(self.s.workspace_repo, workspace_id)
        if workspace.id in self.launching or any(
            s.workspace_id == workspace.id and s.state in {"starting", "running"}
            for s in self.s.run_service.sessions.values()
        ):
            raise ValueError("This workspace already has a running program")
        self.launching.add(workspace.id)
        try:
            result = await self.s.agent.tool(
                "studio.run", {"workspace": workspace.root_path}, f"Run {workspace.title}",
                direct_user_action=direct_user_action,
            )
        finally:
            self.launching.discard(workspace.id)
        task = asyncio.create_task(self.observe(result["session_id"]))
        self.monitors.add(task)
        task.add_done_callback(self.monitors.discard)
        return result

    async def observe(self, session_id):
        while self.s.run_service.sessions[session_id].state == "running":
            self.s.publish("run", self.s.run_service.sessions[session_id].to_dict())
            await asyncio.sleep(0.15)
        session = await self.s.run_service.wait(session_id)
        combined = session.stderr + "\n" + session.stdout
        self.s.publish("run", session.to_dict())
        self.s.publish(
            "problems",
            {
                "workspace_id": session.workspace_id,
                "items": [asdict(p) for p in self.s.problem_service.parse(combined)],
            },
        )
        self.s.publish(
            "tests",
            {
                "workspace_id": session.workspace_id,
                "items": [asdict(t) for t in self.s.test_results.parse_unittest(combined)],
            },
        )

    async def stop(self, session_id):
        return (await self.s.run_service.stop(session_id)).to_dict()

    async def input(self, workspace_id, session_id, text, eof=False):
        workspace = require_approved_workspace(self.s.workspace_repo, workspace_id)
        return await self.s.agent.tool("studio.input", {"workspace": workspace.root_path,
            "session_id": session_id, "text": text, "eof": eof}, "Send program input", direct_user_action=True)

    async def restart(self, workspace_id, session_id=None, *, direct_user_action=False):
        if session_id:
            await self.stop(session_id)
        return await self.run(workspace_id, direct_user_action=direct_user_action)

    async def terminal(self, workspace_id, command, shell="powershell", *, cancellation_event=None, progress=None, return_outcome=False):
        workspace = require_approved_workspace(self.s.workspace_repo, workspace_id)
        if workspace.trust_level == "untrusted":
            raise PermissionError("Untrusted terminal execution requires an isolated terminal provider")
        result = await self.s.agent.tool(
            "terminal.run",
            {
                "command": command,
                "environment": shell,
                "working_directory": workspace.root_path,
                "timeout": 120,
            },
            f"Run terminal command: {command}",
            retain_failure=True,
            progress=progress or (lambda value: self.s.publish("terminal_stream", dict(value, workspace_id=workspace.id))),
            cancellation_event=cancellation_event,
            return_outcome=return_outcome,
        )
        if workspace.id not in self.terminal_ids:
            self.terminal_ids[workspace.id] = self.s.terminal_sessions.create(workspace, environment=shell).id
        self.s.terminal_sessions.record(
            self.terminal_ids[workspace.id], shell + " command", result.get("exit_code", -1), 0
        )
        self.s.publish("terminal", dict(result, workspace_id=workspace.id))
        return result

    def cancel_validation(self, validation_id):
        cancellation = self.validation_cancellations.get(validation_id)
        if cancellation is None:
            raise ValueError("This validation is no longer running")
        cancellation.set()
        record = self.validations[validation_id]
        record["state"] = "cancelling"
        self.s.publish("studio.validation", dict(record))
        return {"requested": True}

    async def validate(self, workspace_id, *, direct_user_action=False):
        workspace = require_approved_workspace(self.s.workspace_repo, workspace_id)
        if workspace.trust_level == "untrusted":
            raise PermissionError("Untrusted validation requires an isolated validation provider")
        if any(self.validations[key]["workspace_id"] == workspace.id for key in self.validation_cancellations):
            raise ValueError("Validation is already running in this workspace")
        from ..services.build_test_service import BuildAndTestService
        commands = [asdict(c) for c in BuildAndTestService().detect(workspace.root_path) if c.source == "known_standard"]
        identity = str(uuid.uuid4())
        cancellation = asyncio.Event()
        record = {"id": identity, "workspace_id": workspace.id, "state": "running" if direct_user_action else "awaiting_approval",
                  "summary": "Running project checks" if direct_user_action else "Waiting for permission to run project checks", "results": []}
        self.validations[identity] = record
        self.validation_cancellations[identity] = cancellation
        for key in list(self.validations):
            if len(self.validations) <= 8: break
            if key not in self.validation_cancellations: self.validations.pop(key)
        self.s.publish("studio.validation", dict(record))
        def progress(value):
            record.update(state="running", summary=value["summary"], results=bounded_validation_results(value.get("results", [])))
            self.s.publish("studio.validation", dict(record))
        try:
            result = await self.s.agent.tool(
                "workspace.run_validation", {"workspace": workspace.root_path, "commands": commands},
                f"Run project checks in {workspace.title}", retain_failure=True,
                direct_user_action=direct_user_action, cancellation_event=cancellation,
                return_outcome=True, progress=progress,
            )
            record.update(result)
            record["results"] = bounded_validation_results(record["results"])
            attempted = {r["name"] for r in record["results"]}
            record["results"] = [*record["results"], *[{"name": c["name"], "state": "not_attempted"} for c in commands if c["name"] not in attempted]]
            text = "\n".join(str(r.get("stdout", "")) + "\n" + str(r.get("stderr", "")) for r in result.get("results", []))
            self.s.publish("tests", {"workspace_id": workspace.id,
                "items": [asdict(t) for t in self.s.test_results.parse_unittest(text)]})
            return dict(record)
        except BaseException:
            record.update(state="outcome_uncertain", summary="Validation was interrupted. Inspect output before running again.")
            raise
        finally:
            self.validation_cancellations.pop(identity, None)
            self.s.publish("studio.validation", dict(record))

    async def ask(self, workspace_id, request, path="", selection=""):
        context = {"active_file": path[:500], "selection": selection[:12000]}
        # File contents remain untrusted context, not authorization or executable metadata.
        bounded = f"{request}\n<untrusted_editor_context>\n{context}\n</untrusted_editor_context>"
        return await self.s.agent.run(bounded, workspace_id)

    async def rollback_latest(self, workspace_id):
        workspace = require_approved_workspace(self.s.workspace_repo, workspace_id)
        tasks = [
            task
            for task in self.s.agent_task_repo.load_all().values()
            if (
                task.workspace_id == workspace.id
                or any(
                    call.get("arguments", {}).get("workspace") == workspace.root_path
                    for call in task.tool_calls
                )
            )
            and self.s.checkpoints.exists(task.id)
        ]
        if not tasks:
            raise ValueError("No OLIVE checkpoint is available for this workspace")
        task = max(tasks, key=lambda item: item.updated_at)
        return await self.access(workspace.id, "rollback", task_id=task.id)
