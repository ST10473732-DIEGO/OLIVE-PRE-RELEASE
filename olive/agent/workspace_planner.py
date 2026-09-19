from __future__ import annotations

import re

from .planner import PlannedAction


class WorkspacePlanner:
    """Deterministic outcome planner for trusted, registered workspaces."""
    def __init__(self,workspace_repository):self.workspaces=workspace_repository

    async def create_plan(self,request,tools):
        text=request.casefold(); matches=[]
        for workspace in self.workspaces.load_all().values():
            if workspace.title.casefold() in text or __import__("pathlib").Path(workspace.root_path).name.casefold() in text:matches.append(workspace)
        if len(matches)!=1:return []
        workspace=matches[0]; actions=[]
        if re.search(r"\b(open|launch)\b",text):
            actions.append(PlannedAction("ide.open_workspace",{"path":workspace.root_path,"workspace":workspace.id,"ide":workspace.preferred_ide},"Open approved workspace in IDE"))
        if re.search(r"\b(run|execute)\b.*\b(test|tests|validation|build)\b",text):
            actions.append(PlannedAction("workspace.run_validation",{"workspace":workspace.id},"Run detected standard validation"))
        elif re.search(r"\b(run|launch|start)\b.*\b(program|application|project)\b",text):
            actions.append(PlannedAction("studio.run",{"workspace":workspace.id},"Run detected workspace application"))
        if re.search(r"\b(status|changes)\b",text):actions.append(PlannedAction("git.status",{"workspace":workspace.id},"Inspect repository status"))
        return actions

    async def next_action(self,task,observations):return None


class CompositePlanner:
    def __init__(self,*planners):self.planners=planners;self.active=None;self.last_plan=None
    async def create_plan(self,request,tools):
        for planner in self.planners:
            actions=await planner.create_plan(request,tools)
            if actions:
                self.active=planner;self.last_plan=getattr(planner,"last_plan",None);return actions
        return []
    async def next_action(self,task,observations):
        return await self.active.next_action(task,observations) if self.active else None
