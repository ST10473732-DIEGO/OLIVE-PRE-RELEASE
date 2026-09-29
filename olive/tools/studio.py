from __future__ import annotations

from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition
from ..services.run_service import ExecutionPolicy
from ..services.workspace_service import require_approved_workspace


class StudioRunTool:
    definition=ToolDefinition("studio.run","Run a detected local workspace application","studio",
        {"type":"object","required":["workspace"]},risk_level="high",required_permissions=("filesystem.read","terminal.execute"),
        confirmation_required=True,timeout_seconds=30)

    def __init__(self,run_service,workspace_repository):self.run_service=run_service;self.workspace_repository=workspace_repository
    async def execute(self,a,context):
        workspace=require_approved_workspace(self.workspace_repository,a["workspace"]);command,kind=self.run_service.detect_command(workspace)
        from ..services.run_service import WEB_KINDS
        # A local web preview must outlive a console run's default, but stays bounded.
        limit,default=(1800,1800) if kind in WEB_KINDS else (600,120)
        policy=ExecutionPolicy(workspace.trust_level,min(limit,max(1,float(a.get("timeout",default)))),False,False)
        if kind == 'java_console':
            from ..services.build_test_service import BuildAndTestService
            checks = BuildAndTestService().detect(workspace.root_path)
            for check in checks:
                if check.name != 'Java compile':
                    continue
                compilation = await self.run_service.start(workspace, [check.executable, *check.arguments], 'java_build', policy)
                try:
                    result = await self.run_service.wait_cancellable(compilation.id, context.cancellation_event)
                finally:
                    if compilation.state in {'starting', 'running'}:
                        await self.run_service.stop(compilation.id)
                if result.state != 'completed':
                    return ToolResult.failure('Java compilation failed.\n' + result.stderr[-12000:], 'BuildFailed',
                                              stdout=result.stdout, stderr=result.stderr)
                if context.cancellation_event and context.cancellation_event.is_set():
                    return ToolResult.failure('Run cancelled before launching the program', 'Cancelled')
        session=await self.run_service.start(workspace,command,kind,policy,
                                            interactive=kind in {"python_console", "java_console", "javascript_console", "dotnet_application"})
        return ToolResult(True,f"Started {kind}",{"session_id":session.id,"process_id":session.process_id,"application_type":kind})


class StudioInputTool:
    definition = ToolDefinition("studio.input", "Send exact input to the selected running program", "studio",
        {"type": "object", "required": ["workspace", "session_id", "text", "eof"]},
        required_permissions=("terminal.execute",), confirmation_required=True)

    def __init__(self, services): self.s = services

    async def execute(self, args, context):
        workspace = require_approved_workspace(self.s.workspace_repo, args["workspace"])
        result = await self.s.run_service.input(workspace.id, args["session_id"], args["text"], args["eof"])
        return ToolResult(True, "Input sent to the selected program", result)
