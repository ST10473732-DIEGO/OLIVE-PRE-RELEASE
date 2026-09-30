"""One asyncio-owned service graph behind explicit protocol operations."""
import asyncio
from collections import OrderedDict
from dataclasses import asdict
import hashlib
import inspect
import json
from pathlib import Path
import time

from .contracts import validate, VERSION


class Host:
    def __init__(self, send, factory=None):
        self.send = send
        self.factory = factory
        self.services = None
        self.requests = OrderedDict()
        self.pending = {}
        self.buffers = OrderedDict()
        self.sequence = 0
        self.closed = False
        self.initialization = None
        self.activities = {}
        self.restoring = False
        self.summary_tasks = {}
        from .studio_commands import StudioCommands
        self.commands = StudioCommands(self)

    def activity_snapshot(self):
        running = [r for r in self.services.run_service.sessions.values() if r.state in {'starting','running'}] if self.services else []
        agent = self.services.agent if self.services else None
        desktop = self.services.desktop if self.services else None
        agent_active = bool(agent and agent.active)
        agent_paused = agent_active and agent.pause_state == 'paused'
        native = getattr(desktop, 'linux', None)
        desktop_active = bool(desktop and (desktop.operation or desktop.universal.owner or native and native.owner))
        methods = [value['method'] for value in self.activities.values()]
        unrelated = [m for m in methods if m not in {'interaction.submit', 'interaction.launch', 'agent.resume'}]
        state = ('Approval required' if self.pending else 'Researching' if any(m in {'interaction.research', 'research.resume', 'research.learn_urls'} for m in methods)
                 else 'Working' if desktop_active or agent_active and not agent_paused
                 else 'Paused' if agent_paused and not running and not unrelated
                 else 'Thinking' if any(m.startswith(('interaction.', 'chat.')) for m in methods)
                 else 'Working' if self.activities or running else 'Ready')
        detail = []
        if agent_active:
            detail.append('Agent: ' + (agent.pause_state if agent.pause_state != 'none' else 'working'))
        if desktop_active:
            detail.append('Desktop Control: active')
        if running:
            detail.append(f'{len(running)} active run session(s)')
        return {'state': state, 'summary': '. '.join(detail), 'items': list(self.activities.values()), 'count': max(len(self.activities) + len(running), int(agent_active) + int(desktop_active))}

    def activity(self):
        self.publish('runtime.activity', self.activity_snapshot())

    async def start(self, directory):
        if self.factory is None:
            from ..application.service_container import ServiceContainer
            self.factory = ServiceContainer
        self.services = self.factory(self.publish, self.confirm, data_dir=directory, migrate=False)
        if hasattr(self.services, 'connect'):
            from ..connect.approvals import ConnectApprovals
            self.services.connect.approvals = ConnectApprovals(self.services.connect, self.confirm, asyncio.get_running_loop())
        self.initialization = asyncio.create_task(self.services.initialize())
        self.initialization.add_done_callback(self.initialized)
        self.publish('runtime.ready', {'ready': True})

    def initialized(self, task):
        if not task.cancelled() and task.exception():
            self.publish('runtime.degraded', {'message': 'Optional services are unavailable. Local work remains available.'})
        elif not task.cancelled():
            self.publish('runtime.initialized', {})

    def publish(self, topic, value):
        if topic=='mail.background':
            key='mail-sync:'+value['connection_id']
            if value['active']:self.activities[key]={'id':key,'method':'mail.sync','started_at':time.time()}
            else:self.activities.pop(key,None)
        if topic == 'settings':
            from .settings import visible
            value = visible(value)
        self.sequence += 1
        self.send(dict(v=VERSION, kind='event', seq=self.sequence, topic=topic, data=value, time=time.time()))
        if topic in {'run', 'agent', 'desktop','mail.background'}:
            self.activity()

    async def confirm(self, request):
        from ..agent.confirmation_service import ConfirmationResponse
        value = asdict(request)
        fingerprint = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        value['fingerprint'] = fingerprint
        value['expires_at'] = time.time() + 300
        from .presentation import approval_presentation
        value['presentation'] = approval_presentation(value, self.services)
        future = asyncio.get_running_loop().create_future()
        self.pending[request.id] = (value, future)
        self.publish('approval', value)
        self.activity()
        try:
            approved = await asyncio.wait_for(future, 300)
            return ConfirmationResponse(approved, cancel_task=not approved)
        except (TimeoutError, asyncio.CancelledError):
            return ConfirmationResponse(False, cancel_task=True)
        finally:
            self.pending.pop(request.id, None)
            self.publish('approval.closed', {'id': request.id})
            self.activity()

    def emergency_stop(self):
        if self.services:
            # A running coding task stops with its conversation's request (cancellation token).
            runner = getattr(getattr(self.services, 'coding', None), 'runner', None)
            task = runner.current if runner else None
            if task is not None and not task.terminal and task.chat_id:
                self.services.interaction.cancel(task.chat_id)
            self.services.desktop.stop_event.set()
            native = getattr(self.services.desktop, 'linux', None)
            if native:
                native.authority.cancel()
                native.native.request_stop()  # OS signal; no database/asyncio wait.
                loop = native.native.loop
                if loop and not loop.is_closed():
                    loop.call_soon_threadsafe(native.stop)

    async def handle(self, request):
        validate(request)
        from ..notes.contracts import UNLEDGERED as notes_unledgered
        from ..draw.contracts import UNLEDGERED as draw_unledgered
        if request['method'] in notes_unledgered or request['method'] in draw_unledgered:
            if self.closed:
                raise RuntimeError('Runtime is shutting down')
            return await self.execute(request['method'], request['args'])
        # Read-only snapshots (including per-token Chat refreshes) must not fill
        # the non-evicting action replay ledger. Effects retain their identities.
        if (request['method'] in ('runtime.snapshot', 'chat.get', 'chat.search', 'chat.warm',
                                 'interaction.inspect', 'desktop.status',
                                 'connect.snapshot', 'connect.model_targets', 'connect.studio_local_workspaces')
                or request['method'] == 'connect.studio_request' and request['args']['operation'] in ('workspaces', 'tree', 'read', 'run_status')):
            if self.closed:
                raise RuntimeError('Runtime is shutting down')
            return await self.execute(request['method'], request['args'])
        key = request['id']
        canonical = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if key in self.requests:
            previous, task = self.requests[key]
            if previous != canonical:
                raise ValueError('Request identity reused with different arguments')
            return await asyncio.shield(task)
        if len(self.requests) >= 2048:
            # Fail closed rather than forgetting a consequential request identity.
            raise RuntimeError('Request history is full; finish work and restart OLIVE')
        if self.closed:
            raise RuntimeError('Runtime is shutting down')
        async def execute():
            from .research_routes import ACTIVE_METHODS
            tracked = request['method'] in {'interaction.submit','interaction.launch','interaction.research','research.resume','research.learn_urls','agent.resume','chat.regenerate','studio.save','studio.run','studio.restart','studio.validate','studio.ask','studio.install_package','studio.create','studio.create_project','connections.discord_configure'}
            tracked = tracked or request['method'] in ACTIVE_METHODS
            tracked = tracked or request['method'] in {'chat.summarize','knowledge.upgrade'}
            tracked = tracked or request['method'] in {'mail.send','mail.sync','mail.fetch_body','mail.connection_test','mail.remote_action','mail.server_search','mail.folder_action','mail.sent_copy','mail.add_knowledge'}
            tracked = tracked or request['method'] in {'interaction.studio','studio.command','studio.git','studio.rollback_latest','studio.open_ide'}
            tracked = tracked or request['method'] in {'project.build','project.test','project.run','project.new','project.create','project.add_existing','dap.launch','lsp.start'}
            tracked = tracked or (request['method'].startswith('desktop.') and request['method'] not in {
                'desktop.status', 'desktop.stop', 'desktop.pause', 'desktop.resume', 'desktop.reset',
                'desktop.configure', 'desktop.consequence_fields', 'desktop.capture_preview', 'desktop.launches',
            })
            if tracked:
                self.activities[key] = {'id': key, 'method': request['method'], 'chat_id': request['args'].get('chat_id'), 'started_at': time.time()}
                self.activity()
            try:
                return await self.execute(request['method'], request['args'])
            finally:
                if tracked:
                    self.activities.pop(key, None)
                    self.activity()
        task = asyncio.create_task(execute())
        self.requests[key] = (canonical, task)
        return await asyncio.shield(task)

    async def execute(self, method, args):
        s = self.services
        if self.restoring and method not in {'runtime.shutdown', 'desktop.stop'}:
            raise RuntimeError('Restore is in progress. Wait for it to finish.')
        if getattr(s, 'restart_required', False) and method not in {
            'runtime.shutdown', 'desktop.stop', 'data.diagnostics', 'approval.respond'
        }:
            raise RuntimeError('Restore complete. Restart OLIVE before further work.')
        from ..personal.contracts import SPEC as personal_spec, MAIN_ONLY as personal_main
        from ..mail.contracts import SPEC as mail_spec, MAIN_ONLY as mail_main
        from ..studio_tooling.contracts import SPEC as tooling_spec
        from .connect_routes import SPEC as connect_spec, call as connect_call
        if method.startswith('notes.'):
            from .notes_routes import call as notes_call
            return await notes_call(s, method, args)
        if method.startswith('draw.'):
            from .draw_routes import call as draw_call
            return await draw_call(s, method, args)
        if method in connect_spec:
            return await connect_call(self, method, args)
        if method in tooling_spec:
            from .tooling_routes import call as tooling_call
            return await tooling_call(s, method, args)
        if method in mail_spec or method in mail_main:
            return await s.mail.call(method,args,manual=True)
        if method in personal_spec or method in personal_main:
            return await s.personal.call(method, args, manual=True)
        if method == 'runtime.snapshot':
            return {'initializing': bool(self.initialization and not self.initialization.done()), 'home': s.data.home(), 'chat': s.chat.get(), 'chats': s.chat.list(),
                    'models': s.data.models(), 'workspaces': s.data.workspaces(),
                    'presets': s.presets.list(),
                    'approvals': [v for v, _ in self.pending.values()], 'buffers': list(self.buffers.values()),
                    'runs': [r.to_dict() for r in s.run_service.sessions.values()],
                    'commands': list(self.commands.records.values()), 'validations': list(s.studio.validations.values()), 'activity': self.activity_snapshot(), 'sequence': self.sequence}
        if method == 'runtime.shutdown':
            self.closed = True
            return {'closing': True}
        if method == 'desktop.stop':
            self.emergency_stop()
            return s.desktop.stop()
        if method == 'desktop.status':
            from .desktop_routes import status
            return status(s)
        if method.startswith('desktop.') and method not in {'desktop.pause','desktop.reset','desktop.launches','desktop.consequence_fields','desktop.configure'}:
            # Cancellation and deliberately disabled policy win on every platform,
            # including a route whose native provider is not yet available.
            s.desktop.gateway.check()
        if method.startswith('desktop.') and method not in {'desktop.pause','desktop.reset','desktop.launches','desktop.consequence_fields','desktop.configure','desktop.launch_local'}:
            from ..platform_support import require_windows
            require_windows('Desktop Control')
        if method == 'desktop.configure':
            return s.desktop.configure(**args)
        if method == 'data.restore':
            if self.buffers:
                raise ValueError('Save or reconcile unsaved Studio files before restoring.')
            if (self.initialization and not self.initialization.done()) or any(
                task is not asyncio.current_task() and not task.done()
                for _, task in self.requests.values()
            ):
                raise ValueError('Wait for current requests to finish before restoring.')
            self.restoring = True
            try:
                return await s.data.restore(**args)
            finally:
                self.restoring = False
        if method in {'connections.discord_configure','connections.discord_select','connections.discord_destinations'}:
            from ..platform_support import PlatformUnavailable
            unavailable = False
            try:
                from ..services.credential_vault import CredentialVault
                await asyncio.to_thread(CredentialVault(s.data_dir).require_available)
                action={'connections.discord_configure':s.discord_transport.configure,'connections.discord_select':s.discord_transport.select_destination,'connections.discord_destinations':s.discord_transport.destinations}[method]
                return await action(**args)
            except PlatformUnavailable:
                unavailable = True
            except Exception:
                # Do not retain provider exception tracebacks containing secret locals
                # in the deduplication task cache, or return secret-bearing errors.
                pass
            finally:
                if 'token' in args:args['token'] = ''
            if unavailable:
                from ..services.linux_credentials import UNAVAILABLE
                raise PlatformUnavailable(UNAVAILABLE)
            raise ValueError('Discord connection could not be verified. Check the bot token, server/channel IDs, bot access and network availability.')
        if method == 'approval.respond':
            value, future = self.pending.get(args['approval_id'], (None, None))
            if not value or future.done() or value['fingerprint'] != args['fingerprint'] or value['expires_at'] < time.time():
                raise ValueError('Approval is no longer valid')
            future.set_result(args['approved'])
            return {'recorded': True}
        if method == 'workspace.open':
            path = Path(args['path']).resolve(strict=True)
            if not path.is_dir():
                raise ValueError('Choose a workspace folder')
            existing = next((w for w in s.data.workspaces() if Path(w['root_path']).resolve() == path), None)
            return existing or s.data.create_workspace(path.name, str(path))
        if method == 'studio.buffer':
            service = s.studio.service(args['workspace_id'])
            if args['path'] not in service.open_files:
                raise ValueError('Open this file through Studio first')
            key = args['workspace_id'] + ':' + args['path']
            state = service.open_files[args['path']]
            # Retention is not a write. A delayed editor update may carry the previous
            # base while a save completes; preserve it for explicit reconciliation.
            if args['text'] == state.saved_text:
                self.buffers.pop(key, None)
                return {'retained': False}
            if key not in self.buffers and len(self.buffers) >= 32:
                raise ValueError('Close a retained file before opening more buffers')
            self.buffers[key] = dict(args)
            service.update(args['path'], args['text'])
            return {'retained': True}
        if args.get('chat_id') in self.summary_tasks and method in {'interaction.submit','interaction.launch','interaction.studio','interaction.research','chat.regenerate','chat.model','chat.rename','chat.metadata','chat.delete','chat.branch'}:
            raise ValueError('Stop conversation summarisation before changing its context')
        if method in {'chat.metadata','chat.search','chat.delete','chat.delete_all','chat.remove_image','chat.summarize','chat.cancel_summary','chat.summary_state','interaction.inspect'}:
            from .chat_routes import routes as chat_routes
            result = chat_routes(s, self.summary_tasks)[method](**args)
            return await result if inspect.isawaitable(result) else result
        if method == 'studio.preview_authorize':
            from .preview import authorize
            return await asyncio.to_thread(authorize,s,**args)
        if method == 'studio.command':
            return await self.commands.run(**args)
        if method == 'studio.cancel_command':
            return self.commands.cancel(**args)
        if method in {'studio.git','studio.search','studio.rollback_latest','studio.discard_buffer','studio.diagnostics','studio.open_ide'}:
            from .studio_routes import routes as studio_routes
            result = studio_routes(self)[method](**args)
            return await result if inspect.isawaitable(result) else result
        if method.startswith('desktop.'):
            from .desktop_routes import routes as desktop_routes
            function = desktop_routes(s).get(method)
            if function is None:
                raise ValueError('Unsupported Desktop Control operation')
            result = function(**args)
            return await result if inspect.isawaitable(result) else result
        if method.startswith('research.') or method == 'interaction.research':
            from .research_routes import routes as research_routes
            function = research_routes(s).get(method)
            if function is None:
                raise ValueError('Unsupported Research operation')
            result = function(**args)
            return await result if inspect.isawaitable(result) else result
        if method.startswith('agent.') or method in {'interaction.launch', 'interaction.studio'}:
            from .agent_routes import routes as agent_routes
            function = agent_routes(s).get(method)
            if function is None:
                raise ValueError('Unsupported Agent operation')
            result = function(**args)
            return await result if inspect.isawaitable(result) else result
        if method.startswith(('data.', 'models.', 'knowledge.', 'settings.')):
            from .data_routes import routes as data_routes
            function = data_routes(s).get(method)
            if function is None:
                raise ValueError('This operation has not been migrated yet')
            result = function(**args)
            return await result if inspect.isawaitable(result) else result
        routes = {
            'media.status': s.media.status, 'media.import': s.media.load,
            'media.configure': s.media.configure, 'media.start': s.media.start,
            'media.disconnect': s.media.disconnect,
            'media.cancel': s.media.cancel, 'media.preview': s.media.preview, 'media.export': s.media.export,
            'media.artifact_file': s.media.artifact_file, 'media.reuse': s.media.reuse,
            'media.engines': s.chat_media.refresh, 'media.voices': s.chat_media.voices,
            'media.select_voice': s.chat_media.select_voice,
            'media.video_plan': s.chat_media.video_plan,
            'connections.discord_status': s.discord_transport.status,
            'connections.discord_destinations': s.discord_transport.destinations,
            'connections.discord_select': s.discord_transport.select_destination,
            'connections.discord_disconnect': s.discord_transport.disconnect,
            'studio.install_package': s.studio.install_package,
            'studio.cancel_install': s.studio.cancel_install,
            'studio.create_project': s.data.create_coding_project,
            'chat.new': s.chat.new, 'chat.get': s.chat.get, 'chat.select': s.chat.select, 'chat.warm': s.chat.warm,
            'chat.draft': s.chat.save_draft,
            'chat.rename': s.chat.update, 'chat.model': s.chat.update,
            'chat.preset': s.chat.update,
            'chat.run_on': s.chat.run_on,
            'chat.regenerate': lambda **a: s.chat.send(**a, regenerate=True),
            'chat.branch': s.chat.branch,
            'interaction.submit': s.interaction.submit, 'interaction.cancel': s.interaction.cancel,
            'context.clear': s.interaction.clear_context,
            'studio.tree': lambda **a: s.studio.access(**a, action='tree', direct_user_action=True),
            'studio.open': lambda **a: s.studio.access(**a, action='open', direct_user_action=True),
            'studio.create': lambda **a: s.studio.access(**a, action='create', direct_user_action=True),
            'studio.compare': lambda **a: s.studio.access(**a, action='compare', direct_user_action=True),
            'studio.rebase': lambda **a: s.studio.access(**a, action='rebase', direct_user_action=True),
            'studio.save': lambda **a: s.studio.access(**a, action='save', direct_user_action=True),
            'studio.run': lambda **a: s.studio.run(**a, direct_user_action=True), 'studio.stop': s.studio.stop,
            'studio.input': s.studio.input,
            'studio.restart': lambda **a: s.studio.restart(**a, direct_user_action=True),
            'studio.validate': lambda workspace_id, review=False: s.studio.validate(workspace_id, direct_user_action=not review),
            'studio.cancel_validation': s.studio.cancel_validation,
            'studio.diff': lambda **a: s.studio.git(**a, action='diff'),
            'studio.ask': s.studio.ask,
        }
        result = routes[method](**args)
        result = await result if inspect.isawaitable(result) else result
        if method == 'studio.save':
            self.buffers.pop(args['workspace_id'] + ':' + args['path'], None)
        return result

    async def shutdown(self):
        self.closed = True
        self.emergency_stop()
        for _, future in list(self.pending.values()):
            if not future.done():
                future.set_result(False)
        if self.initialization and not self.initialization.done():
            self.initialization.cancel()
            await asyncio.gather(self.initialization, return_exceptions=True)
        tasks = [task for _, task in self.requests.values() if not task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.services:
            await self.services.shutdown()
