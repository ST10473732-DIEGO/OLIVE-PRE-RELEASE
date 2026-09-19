from __future__ import annotations

import asyncio

from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition
from ..services.repository_service import RepositoryService
from ..services.workspace_service import require_approved_workspace


class GitTool:
    def __init__(self, action: str, repository: RepositoryService | None = None, workspace_repository=None):
        self.action=action; self.repository=repository or RepositoryService();self.workspace_repository=workspace_repository; writable=action in {"add","commit","create_branch","checkout"}
        self.definition=ToolDefinition(f"git.{action}",f"Git {action.replace('_',' ')}","git",
            {"type":"object","required":["workspace"] + (["message"] if action=="commit" else ["name"] if action in {"create_branch","checkout"} else ["files"] if action=="add" else [])},
            risk_level="medium" if writable else "low",required_permissions=(("filesystem.write",) if writable else ("filesystem.read",)),
            confirmation_required=writable,timeout_seconds=45)

    async def execute(self,a,context): return await asyncio.to_thread(self._execute,a)

    def _execute(self,a):
        from pathlib import Path
        workspace=require_approved_workspace(self.workspace_repository,a["workspace"])
        root=workspace.root_path
        repository_root=self.repository.root(root)
        if repository_root is None or repository_root != Path(root).resolve():
            raise PermissionError('Approve the repository root before using its Git operations')
        if self.action == 'add':
            for path in a.get('files', []):
                workspace.resolve(path)
        if self.action=="status": data=self.repository.status(root)
        elif self.action=="diff": data={"diff":self.repository.diff(root,bool(a.get("staged")))}
        elif self.action=="log": data={"commits":self.repository.log(root,int(a.get("limit",20)))}
        elif self.action=="branch_list": data={"branches":self.repository.branches(root)}
        elif self.action=="add": data={"result":self.repository.add(root,list(a.get("files",[]))).stdout}
        elif self.action=="commit": data={"result":self.repository.commit(root,a["message"]).stdout}
        elif self.action=="create_branch": data={"result":self.repository.create_branch(root,a["name"]).stdout}
        elif self.action=="checkout": data={"result":self.repository.checkout(root,a["name"]).stdout}
        else: raise ValueError(self.action)
        return ToolResult(True,f"Git {self.action.replace('_',' ')} completed",data)


def git_tools(repository=None,workspace_repository=None):
    return [GitTool(name,repository,workspace_repository) for name in ("status","diff","log","branch_list","add","commit","create_branch","checkout")]
