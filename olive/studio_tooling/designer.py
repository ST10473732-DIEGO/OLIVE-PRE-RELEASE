"""WinForms designer operations share Studio workspace, checkpoint and permission services."""
import asyncio
import json
from . import winforms
from ..agent.tool_schema import ToolDefinition
from ..agent.tool_result import ToolResult
from ..agent.permission_service import PermissionDecision
from ..services.editing_service import EditingService
from ..services.workspace_service import require_approved_workspace


class DesignerTool:
    def __init__(self,controller,write):
        self.c=controller;self.write=write
        self.definition=ToolDefinition('studio.designer_save' if write else 'studio.designer_read',
            'Save owned WinForms layout and new event stubs' if write else 'Inspect an owned WinForms layout without executing code',
            'studio',{'type':'object','required':['workspace','layout','revision'] if write else ['workspace']},
            required_permissions=('filesystem.read','filesystem.write') if write else ('filesystem.read',),
            confirmation_required=write,timeout_seconds=60)

    async def execute(self,args,context):
        workspace=require_approved_workspace(self.c.s.workspace_repo,args['workspace'])
        for path in (winforms.MANIFEST,winforms.GENERATED):
            if self.c.s.permissions.evaluate('filesystem.read',str(workspace.resolve(path))).decision==PermissionDecision.DENY:
                raise PermissionError('Designer source read was denied')
        async with self.c.s.studio.locks.setdefault(workspace.id,asyncio.Lock()):
            result=await asyncio.to_thread(self.c.save,workspace,args,context) if self.write else winforms.read(workspace)
        return ToolResult(True,'WinForms layout saved' if self.write else 'WinForms layout inspected',result)


class DesignerController:
    def __init__(self,services):
        self.s=services
        for write in (False,True):services.tool_registry.register(DesignerTool(self,write))

    async def call(self,workspace_id,layout=None,revision=''):
        workspace=require_approved_workspace(self.s.workspace_repo,workspace_id)
        args={'workspace':workspace.root_path}
        if layout is not None:args.update(layout=winforms.validate(layout),revision=revision)
        return await self.s.agent.tool('studio.designer_save' if layout is not None else 'studio.designer_read',args,
            'Save WinForms layout' if layout is not None else 'Open WinForms design',direct_user_action=True)

    def save(self,workspace,args,context):
        current=winforms.read(workspace)
        if not current.get('supported') or current.get('diverged'):raise ValueError(current.get('reason','Unsupported designer source'))
        if current['revision']!=args['revision']:raise ValueError('Layout changed since it was opened. Reopen and compare before saving.')
        layout=winforms.validate(args['layout'])
        files={winforms.GENERATED:winforms.generate(layout),winforms.MANIFEST:json.dumps(layout,indent=2)+'\n'}
        events={winforms.event_file(c['handler']):winforms.event_stub(c['handler']) for c in layout['controls'] if c['handler']}
        for path,stub in events.items():
            if not workspace.resolve(path).exists():files[path]=stub
        service=self.s.studio.service(workspace.id)
        for path in files:
            state=service.open_files.get(path)
            if state and state.unsaved:raise ValueError('Save or reconcile the dirty Code buffer before saving the design')
        def guard(path):
            if context.cancellation_event and context.cancellation_event.is_set():raise ValueError('Designer save cancelled')
            for key in ('filesystem.read','filesystem.write'):
                if self.s.permissions.evaluate(key,str(workspace.resolve(path))).decision==PermissionDecision.DENY:raise PermissionError('Designer file permission denied')
        for path in files:guard(path)
        self.s.checkpoints.create(workspace,context.task_id,list(files))
        editor=EditingService(workspace)
        # Event code is only ever exclusively created. Layout saves never rewrite it.
        for path,content in files.items():
            guard(path)
            expected=current['manifest_hash'] if path==winforms.MANIFEST else current['generated_hash'] if path==winforms.GENERATED else None
            if expected:editor.replace_content(path,content,context.task_id,expected)
            else:editor.create_file(path,content,context.task_id)
        return {**winforms.read(workspace),'event_files':list(events),'checkpoint':context.task_id}
