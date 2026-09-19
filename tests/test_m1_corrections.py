"""Approval integrity and actual local validation cancellation; isolated workspaces only."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from olive.agent.agent_task import AgentTask
from olive.agent.confirmation_service import ConfirmationResponse
from olive.agent.executor import ToolExecutor
from olive.agent.permission_service import PermissionService
from olive.agent.planner import PlannedAction
from olive.agent.tool_schema import ToolContext, ToolDefinition
from olive.tools.workspace import WorkspaceValidationTool
from olive.workspace import Workspace


class ApprovalIntegrityTests(unittest.IsolatedAsyncioTestCase):
    def test_output_budget_retains_step_status_and_latest_output(self):
        from olive.application.studio_controller import bounded_validation_results
        original = [{"name": "compile", "state": "completed", "stdout": "a" * 20000},
                    {"name": "tests", "state": "cancelled", "stderr": "b" * 20000}]
        bounded = bounded_validation_results(original)
        self.assertEqual(sum(len(r["stdout"]) + len(r["stderr"]) for r in bounded), 12000)
        self.assertEqual(bounded[-1]["state"], "cancelled")
        self.assertEqual(bounded[-1]["stderr"], "b" * 12000)
        self.assertTrue(bounded[0]["output_truncated"])
        self.assertEqual(len(original[0]["stdout"]), 20000)

    def test_validation_stop_is_bound_to_the_active_identity(self):
        from olive.application.studio_controller import StudioController
        controller = StudioController.__new__(StudioController)
        event = asyncio.Event()
        controller.validation_cancellations = {"current": event}
        controller.validations = {"current": {"id": "current", "state": "running"}}
        controller.s = SimpleNamespace(publish=Mock())
        with self.assertRaises(ValueError): controller.cancel_validation("old")
        self.assertFalse(event.is_set())
        controller.cancel_validation("current")
        self.assertTrue(event.is_set())
        self.assertEqual(controller.validations["current"]["state"], "cancelling")

    async def test_nested_action_change_invalidates_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            permissions = PermissionService(Path(directory) / "permissions.json")
            permissions.save({"filesystem.write": "ask"})
            definition = ToolDefinition("test.write", "Write", "test", {}, required_permissions=("filesystem.write",), confirmation_required=True)
            registry = Mock(); registry.require.return_value.definition = definition
            action = PlannedAction("test.write", {"path": "fixture.txt", "content": {"text": "before"}})
            async def approve(request):
                action.arguments["content"]["text"] = "changed"
                self.assertEqual(request.arguments["content"]["text"], "before")
                return ConfirmationResponse(True)
            host = Mock(execute=AsyncMock())
            executor = ToolExecutor(registry, permissions, SimpleNamespace(request=approve), Mock(), host)
            task = AgentTask("Write fixture")
            result = await executor.execute(task, action, ToolContext(task.id))
            self.assertEqual(result.error_type, "StaleApproval")
            host.execute.assert_not_awaited()

    async def test_real_validation_stop_terminates_command_before_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("# harmless validation fixture\n")
            (root / "tests").mkdir()
            (root / "tests/test_slow.py").write_text(
                "import time, unittest\nfrom pathlib import Path\n"
                "class Slow(unittest.TestCase):\n def test_wait(self):\n"
                "  Path('started').write_text('started')\n  time.sleep(30)\n  Path('finished').write_text('finished')\n")
            workspace = Workspace("Fixture", str(root))
            repo = Mock(); repo.load_all.return_value = {workspace.id: workspace}
            cancellation = asyncio.Event()
            tool = WorkspaceValidationTool(workspace_repository=repo)
            running = asyncio.create_task(tool.execute({"workspace": str(root)}, ToolContext("fixture", cancellation)))
            try:
                async with asyncio.timeout(15):
                    while not (root / "started").exists():
                        if running.done(): self.fail(str(running.result()))
                        await asyncio.sleep(.05)
                cancellation.set()
                result = await asyncio.wait_for(running, 5)
                self.assertEqual(result.error_type, "Cancelled")
                self.assertEqual(result.data["results"][-1]["state"], "cancelled")
                self.assertFalse((root / "finished").exists())
            finally:
                cancellation.set()
                await asyncio.gather(running, return_exceptions=True)
