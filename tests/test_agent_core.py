import asyncio
import tempfile
import unittest
from pathlib import Path

from olive.agent.agent_task import AgentTask
from olive.agent.audit_service import AuditService
from olive.agent.confirmation_service import ConfirmationResponse, ConfirmationService
from olive.agent.executor import ToolExecutor
from olive.agent.orchestrator import AgentOrchestrator
from olive.agent.permission_service import PermissionService
from olive.agent.planner import PlannedAction
from olive.agent.tool_registry import ToolRegistry
from olive.agent.tool_result import ToolResult
from olive.agent.tool_schema import ToolDefinition

class Tool:
    definition=ToolDefinition("test.echo","echo","test",{},required_permissions=("test.run",))
    async def execute(self,args,context): return ToolResult(True,"ok",args)
class AppTool:
    definition=ToolDefinition("system.open_application","open","system",{},required_permissions=("system.open_application",),confirmation_required=True)
    async def execute(self,args,context): return ToolResult(True,"opened",args)
class Planner:
    def __init__(self, actions): self.actions=actions
    async def create_plan(self,*args): return list(self.actions)
    async def next_action(self,*args): return None

class AgentCoreTests(unittest.IsolatedAsyncioTestCase):
    def services(self, decision="allow", confirm=True):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); root=Path(temp.name)
        registry=ToolRegistry(); registry.register(Tool())
        permissions=PermissionService(root/"permissions.json"); permissions.save({"test.run":decision})
        confirmations=ConfirmationService(lambda request: asyncio.sleep(0,result=ConfirmationResponse(confirm)))
        return registry, ToolExecutor(registry,permissions,confirmations,AuditService(root/"audit.jsonl"))
    async def test_plan_execute_observe_complete(self):
        registry,executor=self.services(); task=await AgentOrchestrator(Planner([PlannedAction("test.echo",{"x":1})]),executor).run("echo")
        self.assertEqual(task.state,"completed"); self.assertTrue(task.tool_calls[0]["result"]["success"])
    async def test_permission_denial_blocks_tool(self):
        registry,executor=self.services("deny"); task=await AgentOrchestrator(Planner([PlannedAction("test.echo",{})]),executor).run("no")
        self.assertEqual(task.tool_calls[0]["result"]["error_type"],"PermissionDenied")
        self.assertEqual(task.state,"failed")
    async def test_confirmation_denial_blocks_ask(self):
        registry,executor=self.services("ask",False); task=await AgentOrchestrator(Planner([PlannedAction("test.echo",{})]),executor).run("ask")
        self.assertEqual(task.tool_calls[0]["result"]["error_type"],"ConfirmationDenied")
    async def test_iteration_limit_and_cancellation(self):
        registry,executor=self.services(); planner=Planner([PlannedAction("test.echo",{})]*3)
        task=await AgentOrchestrator(planner,executor,max_iterations=2).run("loop")
        self.assertEqual(task.state,"failed"); self.assertIn("iterations",task.error)
        event=asyncio.Event(); event.set(); task=await AgentOrchestrator(planner,executor).run("cancel",cancellation_event=event)
        self.assertEqual(task.state,"cancelled")
    async def test_registry_rejects_duplicate(self):
        registry=ToolRegistry(); registry.register(Tool())
        with self.assertRaises(ValueError): registry.register(Tool())

    async def test_tool_schema_rejects_missing_required_arguments(self):
        definition=ToolDefinition("test.required","required","test",{"required":["path"]})
        with self.assertRaises(ValueError): definition.validate_arguments({})

    async def test_audit_does_not_record_argument_values(self):
        registry,executor=self.services(); await AgentOrchestrator(Planner([PlannedAction("test.echo",{"password":"never-log-me"})]),executor).run("audit")
        audit=executor.audit.list_recent()[0]
        self.assertNotIn("never-log-me",audit["requested_action"])
        self.assertIn("password",audit["requested_action"])

    async def test_remembered_confirmation_skips_future_prompt_for_same_tool_and_target(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); root=Path(temp.name)
        registry=ToolRegistry(); registry.register(AppTool())
        permissions=PermissionService(root/"permissions.json"); permissions.save({"system.open_application":"ask"})
        calls=0
        async def confirm(request):
            nonlocal calls; calls += 1; return ConfirmationResponse(True,remember=True)
        executor=ToolExecutor(registry,permissions,ConfirmationService(confirm),AuditService(root/"audit.jsonl"))
        action=PlannedAction("system.open_application",{"application":"Discord"})
        await AgentOrchestrator(Planner([action]),executor).run("one")
        await AgentOrchestrator(Planner([action]),executor).run("two")
        self.assertEqual(calls,1)

    async def test_tool_wide_app_confirmation_skips_other_app_prompts(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); root=Path(temp.name)
        registry=ToolRegistry(); registry.register(AppTool()); permissions=PermissionService(root/"p.json")
        permissions.save({"system.open_application":"ask"}); calls=0
        async def confirm(request):
            nonlocal calls; calls += 1; return ConfirmationResponse(True,remember_all=True)
        executor=ToolExecutor(registry,permissions,ConfirmationService(confirm),AuditService(root/"a.jsonl"))
        await AgentOrchestrator(Planner([PlannedAction("system.open_application",{"application":"Discord"})]),executor).run("one")
        await AgentOrchestrator(Planner([PlannedAction("system.open_application",{"application":"Chrome"})]),executor).run("two")
        self.assertEqual(calls,1)

    async def test_terminate_confirmation_can_be_remembered(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); root=Path(temp.name)
        registry=ToolRegistry(); tool=AppTool(); tool.definition=ToolDefinition(
            "system.terminate_application","terminate","system",{"required":["application"]},
            risk_level="critical",required_permissions=("system.terminate_application",),confirmation_required=True)
        registry.register(tool); permissions=PermissionService(root/"p.json")
        permissions.save({"system.terminate_application":"ask"}); calls=0
        async def confirm(request):
            nonlocal calls; calls += 1
            self.assertTrue(request.allow_remember)
            return ConfirmationResponse(True,remember_all=True)
        executor=ToolExecutor(registry,permissions,ConfirmationService(confirm),AuditService(root/"a.jsonl"))
        first=PlannedAction("system.terminate_application",{"application":"Discord"})
        second=PlannedAction("system.terminate_application",{"application":"Chrome"})
        await AgentOrchestrator(Planner([first]),executor).run("one")
        await AgentOrchestrator(Planner([second]),executor).run("two")
        self.assertEqual(calls,1)
