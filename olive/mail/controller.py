"""One Mail controller for Electron and shared capabilities, using existing gates."""
import asyncio
import threading
from ..agent.agent_task import AgentTask
from ..agent.planner import PlannedAction
from ..agent.tool_schema import ToolDefinition, ToolContext
from ..agent.tool_result import ToolResult
from ..agent.direct_action import DirectAction
from ..agent.permission_service import PermissionDecision
from ..services.credential_vault import CredentialVault
from .contracts import SPEC,MAIN_ONLY,validate,permissions
from .store import MailStore, WRITE_GUARD
from .local import LocalMail
from .connections import Connections
from .submission import Submissions
from .sync import Sync
from .smtp import Cancelled
from .composition import Composition


class MailTool:
    def __init__(self,controller,name):
        self.c=controller;self.name=name
        self.internal_only=name=='mail.from_event'
        self.definition=ToolDefinition(name,'Native '+name.replace('.',' '),'mail',
            {'required':list((SPEC|MAIN_ONLY)[name][0])},required_permissions=permissions(name),
            confirmation_required=name in {'mail.send','mail.sent_copy','mail.import_commit','mail.remote_action','mail.folder_action','mail.cache_remove','mail.create_event','mail.create_task','mail.add_knowledge'},timeout_seconds=120)

    async def execute(self,args,context):
        validate(self.name,args)
        if self.name in {'mail.connection_save','mail.connection_state','mail.connection_test'} and not isinstance(context.direct_action,DirectAction):
            raise PermissionError('Connection configuration requires a direct application action')
        cancel=threading.Event()
        def guard():
            if cancel.is_set() or context.cancellation_event and context.cancellation_event.is_set():raise Cancelled('Mail operation cancelled')
            for permission in permissions(self.name):
                target=args.get('path') if permission.startswith('filesystem.') else None
                if self.c.s.permissions.evaluate(permission,target).decision==PermissionDecision.DENY:raise PermissionError('Permission denied: '+permission)
        guard();token=WRITE_GUARD.set(guard)
        self.c.active.add(cancel)
        loop=asyncio.get_running_loop()
        notify=lambda value:loop.call_soon_threadsafe(self.c.s.publish,'mail.progress',value)
        future=asyncio.create_task(self.c.composition.add_knowledge(**args,guard=guard) if self.name=='mail.add_knowledge' else asyncio.to_thread(self.c.execute,self.name,args,cancel,guard,notify))
        try:
            result=await asyncio.shield(future)
        except asyncio.CancelledError:
            cancel.set()
            try:await asyncio.shield(future)
            except BaseException:pass
            raise
        finally:
            WRITE_GUARD.reset(token);self.c.active.discard(cancel)
        if self.name not in {'mail.folders','mail.recipients','mail.search','mail.get','mail.thread','mail.inline_images','mail.connections','mail.outbox'}:
            self.c.s.publish('mail.changed',{'method':self.name})
        if self.name in {'mail.create_event','mail.create_task'}:
            self.c.s.publish('personal.changed',{'domain':'calendar' if self.name=='mail.create_event' else 'tasks'})
        return ToolResult(True,'Mail operation completed',result)


class MailController:
    def __init__(self,services):
        self.s=services;self.store=MailStore(services.data_dir/'mail.sqlite3');self.store.recover()
        self.local=LocalMail(self.store);self.connections=Connections(self.store,CredentialVault(services.data_dir))
        from .google_auth import GoogleAuth
        self.google=GoogleAuth(self.connections);self.connections.google=self.google
        self.submissions=Submissions(self.store,self.connections);self.sync=Sync(self.store,self.local,self.connections)
        self.composition=Composition(services,self)
        self.active=set();self.pending_sends={}
        from .background import BackgroundSync
        self.background=BackgroundSync(self)
        for method in SPEC|MAIN_ONLY:
            if method!='mail.credential_store' and not method.startswith('mail.google_'):services.tool_registry.register(MailTool(self,method))

    async def call(self,method,args=None,*,manual=False):
        args=validate(method,args or {})
        if method.startswith('mail.google_'):
            if not manual:raise PermissionError('Google authorization requires the explicit application interface')
            def guard():
                for key in permissions(method):
                    if self.s.permissions.evaluate(key,args.get('path') if key=='filesystem.read' else None).decision==PermissionDecision.DENY:
                        raise PermissionError('Google setup permission was denied')
            guard();category=None;result=None
            try:
                if method=='mail.google_status':result=await asyncio.to_thread(self.google.status)
                elif method=='mail.google_import':result=await asyncio.to_thread(self.google.import_client,args['path'],guard)
                elif method=='mail.google_begin':result=await asyncio.to_thread(self.google.begin,guard,args.get('connection_id',''))
                else:result=await asyncio.to_thread(self.google.cancel)
            except Exception as error:category=type(error).__name__
            if category:raise RuntimeError('Google authorization did not complete. Check desktop-client setup and permissions; credentials were not exposed.')
            if method!='mail.google_status':self.s.publish('mail.changed',{'method':method})
            return result
        if method in {'mail.connection_save','mail.connection_state','mail.connection_test','mail.credential_store'} and not manual:raise PermissionError('Connection configuration requires the explicit application interface')
        if method=='mail.credential_store':
            if self.connections.get(args['record_id']).get('auth_type')=='google_oauth':raise ValueError('Use Google authorization to refresh this account credential')
            # Secret is never passed into ToolRegistry, approval arguments, audit
            # records, snapshots or language context. Direct masked user entry is
            # explicit one-action consent; deterministic Deny still wins.
            if not manual:raise PermissionError('Use masked credential entry')
            for key in permissions(method):
                if self.s.permissions.evaluate(key).decision==PermissionDecision.DENY:raise PermissionError('Permission denied: '+key)
            def guard():
                for key in permissions(method):
                    if self.s.permissions.evaluate(key).decision==PermissionDecision.DENY:raise PermissionError('Credential storage permission was denied')
            token=WRITE_GUARD.set(guard)
            category=None;result=None
            try:result=await asyncio.to_thread(self.connections.store_secret,args['record_id'],args['revision'],args['secret'])
            except Exception as error:category=type(error).__name__
            finally:args['secret']='';WRITE_GUARD.reset(token)
            # Raise outside the handler so the cached protocol task does not keep
            # a chained provider traceback containing secret-bearing locals.
            if category:raise RuntimeError('Credential storage failed ('+category+'); no plaintext fallback was used')
            return result
        task=AgentTask('Native Mail operation');event=asyncio.Event()
        if method=='mail.cancel':
            pending=self.pending_sends.get(args['submission_id'])
            if pending and args['submission_id'] not in self.submissions.active:
                pending.cancel()
                await asyncio.gather(pending,return_exceptions=True)
        ordinary=method in {'mail.save_draft','mail.reply','mail.connection_save','mail.connection_state','mail.connection_test',
                            'mail.import_preview','mail.export','mail.attach','mail.save_attachment','mail.prepare','mail.from_event','mail.calendar_draft','mail.create_folder'}
        if method=='mail.update' and not set(args['changes'])-{'read','starred','project_id'}:ordinary=True
        direct=DirectAction(task.id,method,args) if manual and ordinary else None
        if method=='mail.send':self.pending_sends[args['submission_id']]=asyncio.current_task()
        try:
            result=await self.s.agent_executor.execute(task,PlannedAction(method,args,'Review '+method.replace('.',' ')),ToolContext(task.id,event,direct_action=direct))
        except asyncio.CancelledError:
            if method=='mail.send':self.submissions.cancel(args['submission_id'])
            raise
        finally:
            if method=='mail.send':self.pending_sends.pop(args['submission_id'],None)
        if not result.success:
            if method=='mail.send':self.submissions.cancel(args['submission_id'])
            raise ValueError(result.summary or 'Mail operation was not completed')
        return result.data

    def execute(self,method,args,cancel,guard,notify=lambda value:None):
        local=self.local
        if method=='mail.folders':return local.folders(**args)
        if method=='mail.recipients':return local.recipients(**args)
        if method=='mail.search':return local.search(**{k:v for k,v in args.items() if k!='filters'},**args.get('filters',{}))
        if method=='mail.get':return local.get(args['record_id'])
        if method=='mail.thread':return local.thread(**args)
        if method=='mail.create_folder':return local.create_folder(**args)
        if method=='mail.discard':return local.discard(**args)
        if method=='mail.inline_images':
            from .images import inline_images
            return inline_images(local,args['record_id'])
        if method=='mail.save_draft':
            project=args['body'].get('project_id')
            if project and project not in self.s.project_repo.load_all():raise ValueError('Selected project no longer exists')
            return local.save_draft(**args)
        if method=='mail.update':
            project=args['changes'].get('project_id')
            if project and project not in self.s.project_repo.load_all():raise ValueError('Selected project no longer exists')
            return local.update(**args)
        if method=='mail.reply':return local.reply(**args)
        if method=='mail.import_preview':return local.import_preview(**args)
        if method=='mail.import_commit':return local.import_commit(**args)
        if method=='mail.import_cancel':local.previews.pop(args['preview_id'],None);return {'state':'cancelled'}
        if method=='mail.export':return local.export(**args)
        if method=='mail.attach':return local.attach(**args)
        if method=='mail.save_attachment':return local.save_attachment(**args)
        if method=='mail.connections':return self.connections.list()
        if method=='mail.connection_save':return self.connections.save(**args)
        if method=='mail.connection_state':
            if not args['enabled']:self.sync.cancel(args['record_id'])
            return self.connections.change_state(**args)
        if method=='mail.connection_test':
            record=self.connections.get(args['record_id']);password=self.connections.secret(record);results={}
            try:
                for name,transport in [('smtp',self.submissions.transport),('imap',self.sync.transport)]:
                    if record.get(name):
                        guard()
                        try:results[name]=transport.test(record,password)
                        except Exception as error:results[name]={'status':'failed','category':type(error).__name__,'sent_message':False}
            finally:password=None
            self.connections.record_test(record,results)
            return results
        if method=='mail.prepare':return self.submissions.prepare(**args)
        if method=='mail.outbox':return self.submissions.list()
        if method=='mail.sent_copy':return self.submissions.sent_copy(**args,cancel=cancel,policy_guard=guard)
        if method=='mail.retry_rejected':return self.submissions.retry_rejected(**args)
        if method=='mail.send':return self.submissions.send(**args,cancel=cancel,policy_guard=guard)
        if method=='mail.cancel':return self.submissions.cancel(**args)
        if method=='mail.sync':return self.sync.refresh(**args,cancel=cancel,policy_guard=guard,progress=notify)
        if method=='mail.cancel_sync':return self.sync.cancel(**args)
        if method=='mail.fetch_body':return self.sync.fetch_body(**args,cancel=cancel,policy_guard=guard)
        if method=='mail.remote_action':return self.sync.remote_action(**args,cancel=cancel,policy_guard=guard)
        if method=='mail.server_search':return self.sync.search_server(**args,cancel=cancel,policy_guard=guard)
        if method=='mail.folder_action':return self.sync.folder_action(**dict({'new_name':''},**args),cancel=cancel,policy_guard=guard)
        if method=='mail.cache_remove':return self.connections.remove_cache(**args)
        if method=='mail.proposal_prepare':return self.composition.prepare(**args)
        if method in {'mail.create_event','mail.create_task'}:return self.composition.commit(**args,kind='event' if method=='mail.create_event' else 'task',guard=guard)
        if method=='mail.proposal_cancel':return self.composition.cancel(**args)
        if method=='mail.from_event':return self.composition.from_event(**args)
        if method=='mail.calendar_draft':return self.composition.calendar_draft(**args)
        raise ValueError('Unsupported Mail operation')

    async def close(self):
        self.google.close()
        await self.background.close()
        self.submissions.close();self.sync.close()
        for event in self.active:event.set()
        for task in list(self.pending_sends.values()):task.cancel()
