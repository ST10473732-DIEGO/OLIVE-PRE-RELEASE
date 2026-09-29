"""Local Owner Mode: finite requests, narrow tool effects, persistent Deny wins.

The private renderer/bridge authenticates the local process. This is not a
sandbox boundary against hostile processes already running as the same OS user.
Remote services never enter this request context. No model/wire grant importer.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import hashlib
import os
from pathlib import Path
import re
import threading
import time
import uuid

_current = ContextVar('olive_owner_task', default=None)
FORBIDDEN_FIELDS = {'approved','owner_mode','permission','ignore_user_policy','disable_stop','grant_root','extra_recipient'}
SCOPED_EFFECTS = {'filesystem.copy','filesystem.move','filesystem.write_text','filesystem.trash','filesystem.delete','code.apply_patch',
                  'studio.run','workspace.run_validation','studio.new_project'}
READ_TOOLS = {'filesystem.stat', 'filesystem.read_text', 'git.status', 'git.diff', 'git.log', 'git.branch_list'}
from .owner_scope import CODE_READ, CODE_WRITE, FS_READ, RESEARCH_READ
from .owner_scope import SYSTEM_READ
NON_RESERVING = READ_TOOLS | FS_READ | CODE_READ | RESEARCH_READ | SYSTEM_READ | {'system.list_running_applications'}


def starter_request(text):
    match = re.fullmatch(r'(?:Please )?Create (?:a )?(Python|C#|CSharp|Java|JavaScript) project (?:named|called) ([A-Za-z][A-Za-z0-9_-]{0,79}) in Studio[.]?', text.strip(), re.I)
    if not match:
        return None
    language, name = match.groups()
    return name, {'c#': 'csharp'}.get(language.lower(), language.lower())


def owner_identity():
    if hasattr(os,'getuid'):
        return 'uid:'+str(os.getuid())
    import getpass
    return 'user:'+getpass.getuser()


@dataclass(frozen=True)
class OwnerGrant:
    id: str
    chat_id: str
    owner_identity: str
    installation_id: str
    original_request_digest: str
    effect: str
    capabilities: frozenset
    paths: frozenset
    workspace: str
    source: str
    destination: str
    expiry: float
    cancellation_epoch: int
    project_spec: tuple = ()
    content_sha256: str = ''
    bindings: dict = None


class OwnerPolicy:
    def __init__(self, settings, clock=time.monotonic):
        self.settings,self.clock=settings,clock
        self.epochs={};self.active={};self.used={};self.lock=threading.RLock()
        self.created={}
        self.workspace_repo=None

    def enabled(self):
        settings=self.settings();identity=settings.get('owner_installation',{})
        return settings.get('owner_mode') is True and identity.get('owner')==owner_identity() and bool(identity.get('id'))

    @contextmanager
    def request(self, text, chat_id, *, local, selected_path='', workspace='', creation_root='', code_target=False):
        grant=None
        if local and self.enabled():
            from ..interaction.deliverable import instruction_text, direct_deliverable
            instruction=instruction_text(text)
            answer_only = direct_deliverable(text, {}) is not None
            negated = frozenset(re.findall(r"\b(?:do not|don't|never)\s+(\w+)", instruction))
            forbidden_verbs = set(re.findall(r"\b(?:do not|don't|never)\s+(copy|move|rename|save|edit|fix|run|test|build|create|delete|trash)\b", instruction))
            # Negations constrain authority before capability extraction.
            instruction=re.sub(r"\b(?:do not|don't|never)\s+[^.;\n]+",'',instruction)
            capabilities=set();effect='answer'
            verbs={
                'copy':{'filesystem.copy'},'move':{'filesystem.move'},'rename':{'filesystem.move'},
                'delete':{'filesystem.trash'},'trash':{'filesystem.trash'},
                'save':{'filesystem.write_text'},'edit':{'filesystem.write_text','code.apply_patch'},
                'fix':{'filesystem.write_text','code.apply_patch'},
                'run':{'studio.run'},'test':{'workspace.run_validation'},
                'build':{'workspace.run_validation'},
            }
            for verb,tools in verbs.items():
                if re.search(r'(?:^|\bthen\s+|\band\s+|[.;]\s*)'+verb+r'\b',instruction):
                    capabilities.update(tools);effect=verb
            if re.search(r'\brun\b.*\btests?\b', instruction):
                capabilities.discard('studio.run');capabilities.add('workspace.run_validation');effect='test'
            if re.search(r'\bcreate\b.*\bfile\b',instruction):
                capabilities.add('filesystem.write_text');effect='create_file'
            if answer_only or forbidden_verbs.intersection({effect, 'create' if effect == 'create_file' else effect}):
                capabilities.clear()
            # Source payloads cannot introduce resources. Preserve path case.
            path_text = re.sub(r'```[^\n]*\n.*?(?:```|$)', '', text, flags=re.S)
            path_text = re.sub(r'([\'"])(?:(?!\1).)*?\1',
                lambda m: m.group()[1:-1] if re.fullmatch(r'(?:~/|/)[^\n]+', m.group()[1:-1]) else '', path_text, flags=re.S)
            path_text = re.sub(r"\b(?:do not|don't|never)\s+[^.;\n]+", '', path_text, flags=re.I)
            references = re.findall(r'(?<!\w)(?:~/|/)[^\s\'";,]+', path_text)
            paths=set(references)
            source = destination = ''
            if effect in {'copy', 'move', 'rename'} and len(references) == 2:
                source, destination = [str(Path(p).expanduser().resolve()) for p in references]
                folder_requested = re.search(r'\b(?:copy|move)\s+(?:the\s+)?(?:folder|directory)\b', instruction)
                if Path(source).is_dir() and not folder_requested:
                    # "Find report.pdf in DIR and copy it": resolve the literal file
                    # inside the named folder; never grant the folder itself.
                    names = {n for n in re.findall(r'(?<![\w/.-])([\w][\w.-]{0,120}\.[A-Za-z0-9]{1,8})\b', path_text)
                             if (Path(source) / n).is_file()}
                    if len(names) == 1:
                        paths.discard(source)
                        source = str((Path(source) / names.pop()).resolve())
                        paths.add(source)
                    else:
                        capabilities.clear()
                        source = destination = ''
                if destination and Path(destination).is_dir():
                    destination = str(Path(destination) / Path(source).name)
                if destination:
                    paths.add(destination)
            elif effect in {'copy', 'move', 'rename'}:
                capabilities.clear()  # Resolve exact directional targets first.
            if selected_path and re.search(r'\b(?:this|selected|current|that) (?:file|code)\b',instruction):
                paths.add(selected_path)
            paths=frozenset(str(Path(p).expanduser().resolve()) for p in paths)
            if effect in {'edit', 'fix', 'save', 'create_file', 'delete', 'trash'} and len(paths) != 1:
                capabilities.clear()  # A typed single-file operation needs one target.
            if capabilities:capabilities.update({'filesystem.stat','filesystem.read_text'})
            # Existing read-only Git controllers stay bound to one selected,
            # approved repository. A model cannot turn this into Git mutation.
            if workspace and not forbidden_verbs and re.search(r'\bgit\b', instruction):
                for word, capability in {'status':'git.status', 'diff':'git.diff',
                                         'log':'git.log', 'branches':'git.branch_list'}.items():
                    if re.search(r'\b'+word+r'\b', instruction) and re.search(r'\b(?:show|read|check|inspect|list)\b', instruction):
                        capabilities.add(capability)
            from .owner_scope import extend
            extra, bindings = extend(text, instruction, workspace=workspace, answer_only=answer_only, forbidden=negated,
                                     code_target=code_target)
            capabilities.update(extra)
            if 'rename' in bindings and effect in {'rename', 'answer'}:
                effect = 'rename'
            project_spec = ()
            from ..interaction.ordinary_requests import file_transfer
            literal = file_transfer(text)
            content_sha256 = ''
            if literal and literal['steps'][0]['intent'] in {'filesystem.create_file','filesystem.edit_file'}:
                content_sha256 = hashlib.sha256(literal['steps'][0]['entities']['text'].encode()).hexdigest()
            starter = starter_request(text)
            if starter and creation_root:
                effect = 'create_project'
                capabilities = {'studio.new_project'}
                project_spec = (*starter, str(Path(creation_root).resolve()))
            elif creation_root and not answer_only:
                from ..interaction.project_request import project_request, resolve_name
                spec = project_request(text)
                if spec:
                    # Explicit build-me-a-project request: create one new folder, then
                    # edit, validate and (if asked) run only inside that new workspace.
                    location = str(Path(creation_root).resolve())
                    effect = 'create_project'
                    capabilities = {'studio.new_project', 'workspace.run_validation'} | CODE_READ | CODE_WRITE
                    if spec['run']:
                        capabilities.add('studio.run')
                    project_spec = (resolve_name(spec, location), spec['language'], location, spec['template'])
            with self.lock:
                epoch=self.epochs.get(chat_id,0)
                # A creation grant covers only the folder it creates, never a previously selected workspace.
                scoped = '' if effect == 'create_project' else workspace
                grant=OwnerGrant(uuid.uuid4().hex,chat_id,owner_identity(),self.settings()['owner_installation']['id'],
                    hashlib.sha256(text.encode()).hexdigest(),effect,frozenset(capabilities),paths,
                    str(Path(scoped).resolve()) if scoped else '',source,destination,self.clock()+600,epoch,project_spec,content_sha256,
                    bindings)
                self.active[grant.id]=grant
            from ..interaction.trace import event
            event('owner_task_grant', task_id=grant.id, effect=effect, capabilities=sorted(capabilities),
                  cancellation_epoch=epoch, authorized_by='owner_task_policy')
        token=_current.set((self,grant) if grant else None)
        try:yield grant
        finally:
            _current.reset(token)
            if grant:
                with self.lock:
                    self.active.pop(grant.id,None)
                    self.created.pop(grant.id,None)
                    for key in [k for k in self.used if k[0]==grant.id]:self.used.pop(key,None)

    def _workspace(self, grant):
        """The grant's selected workspace, or the one this very grant created."""
        return grant.workspace or self.created.get(grant.id, '')

    def bind_created_workspace(self, root):
        """After an authorized studio.new_project, scope later effects to that new folder only."""
        current = _current.get()
        if not current or current[0] is not self or not current[1]:
            return False
        grant = current[1]
        if grant.effect != 'create_project' or len(grant.project_spec) < 3 or grant.workspace:
            return False
        name, _, location = grant.project_spec[:3]
        target = (Path(location) / name).resolve()
        try:
            if Path(root).resolve() != target or not target.is_dir() or target.is_symlink():
                return False
        except (OSError, RuntimeError, ValueError):
            return False
        with self.lock:
            if self.active.get(grant.id) is not grant or self.used.get((grant.id, 'studio.new_project'), 0) < 1:
                return False
            self.created[grant.id] = str(target)
        return True

    def cancel(self,chat_id):
        with self.lock:
            self.epochs[chat_id]=self.epochs.get(chat_id,0)+1
            for key,g in list(self.active.items()):
                if g.chat_id==chat_id:self.active.pop(key,None)

    def revoke(self):
        with self.lock:
            for grant in self.active.values():
                self.epochs[grant.chat_id] = self.epochs.get(grant.chat_id, 0) + 1
            self.active.clear()
            self.used.clear()

    def rejection(self, tool, arguments):
        current = _current.get()
        if not current or current[0] is not self:return ''
        grant = current[1]
        if FORBIDDEN_FIELDS & arguments.keys():return 'Model fields cannot grant authority'
        with self.lock:
            if not self.enabled() or self.active.get(grant.id) is not grant or self.clock() >= grant.expiry:
                return 'The owner task was cancelled, revoked or expired'
            if tool in SCOPED_EFFECTS and tool not in grant.capabilities:
                return 'This effect is not represented by the original owner task'
            if tool in grant.capabilities and not self.authorize(tool, arguments):
                return 'This effect is outside the owner task or was already attempted'
        return ''

    def consume(self, tool, arguments):
        """Reserve a bounded mutation before dispatch; uncertain effects never replay."""
        if not self.authorize(tool, arguments):return False
        if tool in NON_RESERVING:return True
        grant = _current.get()[1]
        from .owner_scope import BUDGETS
        with self.lock:
            key=(grant.id,tool)
            if self.used.get(key,0) >= BUDGETS.get(tool,1):return False
            self.used[key]=self.used.get(key,0)+1
            return True

    def _family(self, grant, tool, arguments):
        """Validate extended owner families; None means use the file/Studio rules below."""
        from . import owner_scope as scope
        bindings = grant.bindings or {}
        def owned_target(raw):
            raw = Path(raw).expanduser()
            path = raw.resolve()
            if any(p.is_symlink() for p in (raw, *raw.parents)):return False
            if any(part in {'.ssh', '.gnupg', '.pki'} for part in path.parts):return False
            existing = path
            while not existing.exists() and existing != existing.parent:existing = existing.parent
            return not hasattr(os, 'getuid') or existing.stat().st_uid == os.getuid()
        if tool in scope.FS_READ and bindings.get('read_roots'):
            path = arguments.get('path')
            if isinstance(path, str) and scope.within(path, bindings['read_roots']) and owned_target(path):
                return True
            if tool in {'filesystem.list', 'filesystem.search'}:return False
            return None
        if tool == 'filesystem.create_directory':
            path = arguments.get('path')
            return (isinstance(path, str) and str(Path(path).expanduser().resolve()) in bindings.get('directories', ())
                    and set(arguments) <= {'path', 'parents'} and owned_target(path)
                    and not Path(path).expanduser().exists())
        if tool == 'filesystem.move' and bindings.get('rename') and not grant.source:
            source, destination = bindings['rename']
            return (set(arguments) == {'path', 'destination'} and
                    str(Path(str(arguments['path'])).expanduser().resolve()) == source and
                    str(Path(str(arguments['destination'])).expanduser().resolve()) == destination and
                    Path(source).exists() and not Path(destination).exists() and
                    owned_target(source) and owned_target(destination))
        workspace_argument = arguments.get('workspace', arguments.get('workspace_id'))
        if tool in scope.CODE_READ | scope.CODE_WRITE | {'studio.build', 'studio.debug'}:
            if not scope.workspace_matches(workspace_argument, self._workspace(grant), self.workspace_repo):return False
            path = arguments.get('path', '')
            if not isinstance(path, str) or '..' in Path(path).parts:return False
            if path and Path(path).is_absolute() and not scope.within(path, {self._workspace(grant)}):return False
            return True
        if tool in scope.GIT_WRITE:
            if not scope.workspace_matches(workspace_argument, self._workspace(grant), self.workspace_repo):return False
            bound = bindings.get('git', {}).get(tool)
            if tool == 'git.commit':
                message = arguments.get('message')
                return (set(arguments) == {'workspace', 'message'} and isinstance(message, str) and
                        1 <= len(message.strip()) <= 200 and not any(ord(c) < 32 for c in message) and
                        (not bound or message == bound))
            if tool == 'git.add':
                files = arguments.get('files')
                return (set(arguments) == {'workspace', 'files'} and isinstance(files, list) and 1 <= len(files) <= 200 and
                        all(isinstance(f, str) and f and not Path(f).is_absolute() and '..' not in Path(f).parts
                            and not f.startswith('-') for f in files))
            return set(arguments) == {'workspace', 'name'} and arguments['name'] == bound
        if tool in {'system.open_application', 'system.close_application'}:
            name = bindings.get('open' if tool == 'system.open_application' else 'close', '')
            value = arguments.get('application')
            return (set(arguments) == {'application'} and isinstance(value, str) and bool(name) and
                    value.strip().casefold().removesuffix('.exe') == name.casefold())
        if tool in {'system.open_path', 'ide.open_file', 'ide.open_workspace'}:
            if tool == 'ide.open_workspace' and scope.workspace_matches(workspace_argument or arguments.get('path'),
                                                                        self._workspace(grant), self.workspace_repo):
                return True
            path = arguments.get('path')
            roots = set(grant.paths) | set(bindings.get('read_roots', ()))
            return isinstance(path, str) and (scope.within(path, roots) or
                   bool(self._workspace(grant)) and tool == 'ide.open_file' and scope.workspace_matches(
                       workspace_argument, self._workspace(grant), self.workspace_repo))
        if tool == 'system.list_running_applications':
            return not arguments
        if tool in scope.SYSTEM_READ:
            return not arguments
        if tool in {'system.audio_set_volume', 'system.audio_set_mute', 'system.bluetooth_set_power',
                    'system.bluetooth_set_discoverable', 'system.display_set_brightness'}:
            bound = bindings.get('system', {})
            key = {'system.audio_set_volume': 'percent', 'system.audio_set_mute': 'muted',
                   'system.bluetooth_set_power': 'powered', 'system.bluetooth_set_discoverable': 'discoverable',
                   'system.display_set_brightness': 'percent'}[tool]
            return tool in bound and set(arguments) == {key} and arguments[key] == bound[tool] and \
                type(arguments[key]) is type(bound[tool])
        if tool in scope.RESEARCH_READ:
            return True
        if tool == 'mail.send':
            bound = bindings.get('mail')
            preview = arguments.get('preview')
            if not bound or set(arguments) != {'submission_id', 'expected_fingerprint', 'preview'} or not isinstance(preview, dict):
                return False
            from email.utils import getaddresses
            fields = [preview.get(k) for k in ('to', 'cc', 'bcc')]
            values = [v for f in fields for v in (f if isinstance(f, list) else [f] if f else [])]
            recipients = {address.casefold() for _, address in getaddresses([str(v) for v in values]) if address}
            body_ok = bound['body'] is None or str(preview.get('body', '')).strip() == bound['body'].strip()
            return bool(recipients) and recipients <= bound['recipients'] and not preview.get('attachments') and body_ok
        if tool in {'mail.save_draft', 'mail.reply', 'mail.prepare'}:
            return True
        if tool in scope.PERSONAL_WRITE:
            return set(arguments) <= {'body', 'record_id', 'revision', 'delivery_id', 'minutes'}
        return None

    def authorize(self,tool,arguments):
        current=_current.get()
        if not current or current[0] is not self or not self.enabled():return False
        grant=current[1]
        with self.lock:
            if self.active.get(grant.id) is not grant or self.epochs.get(grant.chat_id,0)!=grant.cancellation_epoch or self.clock()>=grant.expiry:return False
        if tool not in NON_RESERVING:
            from .owner_scope import BUDGETS
            if self.used.get((grant.id,tool),0) >= BUDGETS.get(tool,1):return False
        if tool not in grant.capabilities or FORBIDDEN_FIELDS & arguments.keys():return False
        family = self._family(grant, tool, arguments)
        if family is not None:return family
        if tool in {'git.status', 'git.diff', 'git.log', 'git.branch_list'}:
            if not self._workspace(grant) or str(Path(arguments.get('workspace','')).resolve()) != self._workspace(grant):return False
            allowed = {'workspace'} | ({'staged'} if tool == 'git.diff' else {'limit'} if tool == 'git.log' else set())
            return (set(arguments) <= allowed and
                    ('staged' not in arguments or type(arguments['staged']) is bool) and
                    ('limit' not in arguments or type(arguments['limit']) is int and 1 <= arguments['limit'] <= 100))
        if tool == 'filesystem.write_text' and grant.content_sha256:
            if not isinstance(arguments.get('text'),str) or hashlib.sha256(arguments['text'].encode()).hexdigest() != grant.content_sha256:return False
        if tool == 'studio.new_project':
            if not grant.project_spec:return False
            name, language, location = grant.project_spec[:3]
            template = grant.project_spec[3] if len(grant.project_spec) > 3 else 'console'
            return arguments == {'name':name, 'language':language, 'template':template, 'location':location} and not (Path(location)/name).exists()
        if tool in {'studio.run','workspace.run_validation'}:
            if not self._workspace(grant) or str(Path(arguments.get('workspace','')).resolve())!=self._workspace(grant):return False
            # Validation commands must come from the existing controller's detector;
            # Owner Mode does not authorize arbitrary shell or model command strings.
            allowed = {'workspace','timeout'}
            if tool == 'workspace.run_validation' and 'commands' in arguments:
                from dataclasses import asdict
                from ..services.build_test_service import BuildAndTestService
                expected = [asdict(c) for c in BuildAndTestService().detect(self._workspace(grant)) if c.source == 'known_standard']
                if arguments['commands'] != expected:return False
                allowed.add('commands')
            return set(arguments)<=allowed
        if tool in {'filesystem.move','filesystem.copy'} and (str(Path(arguments.get('path','')).expanduser().resolve()) != grant.source or str(Path(arguments.get('destination','')).expanduser().resolve()) != grant.destination):return False
        keys={'path','destination'} if tool in {'filesystem.move','filesystem.copy'} else {'path'}
        if not all(isinstance(arguments.get(k),str) for k in keys):return False
        for key in keys:
            raw=Path(arguments[key]).expanduser()
            path=raw.resolve()
            allowed=str(path) in grant.paths
            if not allowed or any(p.is_symlink() for p in (raw, *raw.parents)):return False
            # Security credentials have a separate explicit high-impact path.
            if any(part in {'.ssh', '.gnupg', '.pki'} for part in path.parts):return False
            existing=path
            while not existing.exists() and existing!=existing.parent:existing=existing.parent
            if hasattr(os,'getuid') and existing.stat().st_uid!=os.getuid():return False
        if arguments.get('overwrite') and not (tool == 'filesystem.write_text' and grant.effect in {'edit','fix'}):return False  # Changed/colliding target needs separate resolution.
        return True


def current_policy():
    """The active local owner policy for this request context, or None."""
    current = _current.get()
    return current[0] if current else None


def owner_request(function):
    @wraps(function)
    async def invoke(self,text,chat_id=None,*args,**kwargs):
        policy=getattr(self.s,'owner_policy',None)
        if policy is None:return await function(self,text,chat_id,*args,**kwargs)
        chat_id=chat_id or self.s.current_chat_id
        context=self.context(chat_id)
        workspace=self.s.workspace_repo.load_all().get(context.workspace_id or self.selected_workspace)
        with policy.request(text,chat_id,local=not getattr(self.s.chat,'targets',{}).get(chat_id),
                            selected_path=(None if kwargs.get('workspace_id') else self.selected_file) or context.entities.get('path',''),workspace=workspace.root_path if workspace else '',
                            creation_root=str(self.s.data_dir),
                            code_target=bool(getattr(context, 'coding_follow_up', False))):
            return await function(self,text,chat_id,*args,**kwargs)
    return invoke
