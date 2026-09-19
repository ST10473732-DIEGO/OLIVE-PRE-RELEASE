from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
import subprocess

from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition
from ..services.build_test_service import BuildAndTestService
from ..services.workspace_service import require_approved_workspace
from ..services.run_service import RunService, ExecutionPolicy


class WorkspaceValidationTool:
    definition=ToolDefinition("workspace.run_validation","Run detected standard build and test commands","workspace",
        {"type":"object","required":["workspace"]},risk_level="high",required_permissions=("filesystem.read","terminal.execute"),
        confirmation_required=True,timeout_seconds=300)

    def __init__(self,service=None,workspace_repository=None):self.service=service or BuildAndTestService();self.workspace_repository=workspace_repository

    async def execute(self,a,context):
        workspace=require_approved_workspace(self.workspace_repository,a["workspace"])
        commands=self.service.detect(workspace.root_path); selected=[c for c in commands if c.source=="known_standard"]
        if "commands" in a and a["commands"] != [asdict(c) for c in selected]:
            return ToolResult.failure("Detected commands changed; review the test run again", "StaleApproval")
        results=[]
        for command in selected:
            if context.cancellation_event and context.cancellation_event.is_set(): return ToolResult.failure("Validation cancelled","Cancelled",results=results)
            if context.progress_callback:
                context.progress_callback({"summary": f"Running {command.name}", "results": list(results)})
            runner = RunService()
            session = await runner.start(workspace, [command.executable, *command.arguments], 'validation',
                ExecutionPolicy(trust_level=workspace.trust_level, max_runtime_seconds=min(240,float(a.get("timeout",120)))))
            try:
                completed = await runner.wait_cancellable(session.id, context.cancellation_event)
            finally:
                if session.state in {'starting', 'running'}:
                    await runner.stop(session.id)
            result={"name":command.name,"session_id":session.id,"exit_code":completed.exit_code,
                    "stdout":completed.stdout[-100_000:],"stderr":completed.stderr[-100_000:],
                    "state":"cancelled" if completed.state == 'stopped' else "failed" if completed.exit_code or completed.state == 'timed_out' else "completed"}
            results.append(result)
            if completed.state == 'timed_out':
                return ToolResult.failure(f"{command.name} timed out","Timeout",results=results)
            if completed.state == 'stopped':
                return ToolResult.failure("Validation cancelled","Cancelled",results=results)
            if completed.exit_code:return ToolResult.failure(f"{command.name} failed","ValidationFailed",results=results)
        if not selected:return ToolResult.failure("No known standard validation commands were detected","ValidationUnavailable")
        return ToolResult(True,f"Passed {len(results)} validation steps",{"results":results})


class ProjectTemplateTool:
    definition=ToolDefinition("workspace.create_template","Create a small approved project template","workspace",
        {"type":"object","required":["workspace","template","name"]},risk_level="high",required_permissions=("filesystem.write","terminal.execute"),
        confirmation_required=True,timeout_seconds=120)

    def __init__(self,workspace_repository=None):self.workspace_repository=workspace_repository
    async def execute(self,a,context):
        root=Path(require_approved_workspace(self.workspace_repository,a["workspace"]).root_path);name=str(a["name"]);template=str(a["template"]).casefold()
        if not name.replace("_","").replace("-","").isalnum():raise ValueError("Invalid project name")
        target=(root/name).resolve(strict=False)
        try:target.relative_to(root)
        except ValueError as exc:raise PermissionError("Template path escapes workspace") from exc
        if target.exists():return ToolResult.failure("Project directory already exists","TargetExists")
        if template in {"csharp_console","csharp_webapi"}:
            kind="console" if template=="csharp_console" else "webapi"
            completed=await asyncio.to_thread(subprocess.run,["dotnet","new",kind,"-n",name,"-o",str(target)],cwd=str(root),capture_output=True,text=True,timeout=110)
            if completed.returncode:return ToolResult.failure("dotnet project creation failed","TemplateFailed",stderr=completed.stderr[-20_000:])
        elif template in {"python_application","python_library"}:
            target.mkdir(); package=target/(name.replace("-","_") if template=="python_library" else "")
            if template=="python_library":package.mkdir();(package/"__init__.py").write_text("",encoding="utf-8")
            else:(target/"main.py").write_text('def main():\n    print("Hello from OLIVE")\n\n\nif __name__ == "__main__":\n    main()\n',encoding="utf-8")
            (target/"README.md").write_text(f"# {name}\n",encoding="utf-8");(target/".gitignore").write_text(".venv/\n__pycache__/\n",encoding="utf-8")
        else:raise ValueError("Unsupported built-in template")
        return ToolResult(True,f"Created {name}",{"path":str(target),"template":template})


def workspace_tools(workspace_repository=None):return [WorkspaceValidationTool(workspace_repository=workspace_repository),ProjectTemplateTool(workspace_repository)]
