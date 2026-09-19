from __future__ import annotations

import asyncio

from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition
from ..services.ide_service import IDEService
from ..services.workspace_service import require_approved_workspace


class IDETool:
    def __init__(self,action:str,service=None,workspace_repository=None):
        self.action=action;self.service=service or IDEService();self.workspace_repository=workspace_repository
        self.definition=ToolDefinition(f"ide.{action}",f"Open {action.replace('_',' ')} in an installed IDE","ide",
            {"type":"object","required":["path"]},risk_level="medium",required_permissions=("system.open_application","filesystem.read"),
            confirmation_required=True)
    async def execute(self,a,context):
        workspace=require_approved_workspace(self.workspace_repository,a.get("workspace") or a["path"])
        path=workspace.root_path if self.action=="open_workspace" else str(workspace.resolve(a["path"]))
        target=await asyncio.to_thread(self.service.open_workspace if self.action=="open_workspace" else self.service.open_file,path,a.get("ide", ""))
        return ToolResult(True,f"Opened {target}",{"target":target,"ide":a.get("ide")})


def ide_tools(workspace_repository=None):return [IDETool("open_workspace",workspace_repository=workspace_repository),IDETool("open_file",workspace_repository=workspace_repository)]
