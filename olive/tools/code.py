from __future__ import annotations

import asyncio
from pathlib import Path
import re

from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition
from ..services.code_index_service import CodeIndexService, extract_symbols, CODE_SUFFIXES, IGNORED_PARTS
from ..services.editing_service import EditingService, file_hash
from ..workspace import Workspace
from ..services.workspace_service import require_approved_workspace

MAX_LINES=500


class CodeTool:
    def __init__(self,action:str,workspace_repository=None,checkpoints=None):
        self.action=action;self.workspace_repository=workspace_repository;self.checkpoints=checkpoints; writing=action in {"replace_exact","replace_range","create_file"}
        required=["workspace","path"] if action not in {"search_text","search_symbol","find_references"} else ["workspace","query"]
        if action=="replace_exact":required += ["old","new","expected_hash"]
        elif action=="replace_range":required += ["start_line","end_line","text","expected_hash"]
        self.definition=ToolDefinition(f"code.{action}",f"Code {action.replace('_',' ')}","code",{"type":"object","required":required},
            risk_level="medium" if writing else "low",required_permissions=(("filesystem.write",) if writing else ("filesystem.read",)),
            confirmation_required=writing,timeout_seconds=60)

    async def execute(self,a,context): return await asyncio.to_thread(self._execute,a,context.task_id)

    def _execute(self,a,task_id):
        workspace=require_approved_workspace(self.workspace_repository,a["workspace"])
        if self.action in {"read_file","read_range"}:
            path=workspace.resolve(a["path"]); start=max(1,int(a.get("start_line",1))); count=min(MAX_LINES,max(1,int(a.get("line_count",200))))
            lines=path.read_text(encoding="utf-8",errors="replace").splitlines(); selected=lines[start-1:start-1+count]
            return ToolResult(True,f"Read {len(selected)} lines from {path.name}",{"path":str(path),"start_line":start,
                "end_line":start+len(selected)-1,"lines":[{"number":start+i,"text":line} for i,line in enumerate(selected)],
                "content_hash":file_hash(path),"truncated":start-1+len(selected)<len(lines)})
        if self.action=="list_symbols":
            path=workspace.resolve(a["path"]); language=CODE_SUFFIXES.get(path.suffix.lower(),"text")
            values=[item.__dict__ if hasattr(item,"__dict__") else {name:getattr(item,name) for name in item.__slots__}
                    for item in extract_symbols(path.read_text(encoding="utf-8",errors="replace"),path.relative_to(Path(workspace.root_path)).as_posix(),language)]
            return ToolResult(True,f"Found {len(values)} symbols",{"symbols":values})
        if self.action in {"search_text","find_references"}:
            query=str(a["query"]); regex=re.compile(re.escape(query),re.IGNORECASE); matches=[]; limit=min(1000,max(1,int(a.get("limit",200))))
            for path in CodeIndexService.iter_source_files(Path(workspace.root_path)):
                for number,line in enumerate(path.read_text(encoding="utf-8",errors="replace").splitlines(),1):
                    if regex.search(line): matches.append({"path":path.relative_to(Path(workspace.root_path)).as_posix(),"line":number,"text":line[:500]})
                    if len(matches)>=limit: break
                if len(matches)>=limit: break
            return ToolResult(True,f"Found {len(matches)} references",{"matches":matches})
        if self.action=="search_symbol":
            index=CodeIndexService().index(workspace.root_path); values=CodeIndexService().search_symbols(a["query"],index)
            return ToolResult(True,f"Found {len(values)} symbols",{"symbols":values[:200]})
        editing=EditingService(workspace)
        if not self.checkpoints: raise RuntimeError("Checkpoint service is required for code modifications")
        self.checkpoints.create(workspace,task_id,[a["path"]])
        if self.action=="replace_exact": record=editing.replace_exact(a["path"],a["old"],a["new"],task_id,a.get("expected_hash"))
        elif self.action=="replace_range": record=editing.replace_range(a["path"],int(a["start_line"]),int(a["end_line"]),a["text"],task_id,a.get("expected_hash"))
        elif self.action=="create_file": record=editing.create_file(a["path"],a.get("text",""),task_id)
        else: raise ValueError(self.action)
        return ToolResult(True,f"Edited {Path(record.path).name}",{"edit":{name:getattr(record,name) for name in record.__slots__}})


def code_tools(workspace_repository=None,checkpoints=None):
    return [CodeTool(name,workspace_repository,checkpoints) for name in ("read_file","read_range","search_text","search_symbol","list_symbols",
                                        "find_references","replace_exact","replace_range","create_file")]
