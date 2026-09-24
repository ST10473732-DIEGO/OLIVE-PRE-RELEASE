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


class OwnerPolicy:
    def __init__(self, settings, clock=time.monotonic):
        self.settings,self.clock=settings,clock
        self.epochs={};self.active={};self.used=set();self.lock=threading.RLock()

    def enabled(self):
        settings=self.settings();identity=settings.get('owner_installation',{})
        return settings.get('owner_mode') is True and identity.get('owner')==owner_identity() and bool(identity.get('id'))

    @contextmanager
    def request(self, text, chat_id, *, local, selected_path='', workspace='', creation_root=''):
        grant=None
        if local and self.enabled():
            from ..interaction.deliverable import instruction_text, direct_deliverable
            instruction=instruction_text(text)
            answer_only = direct_deliverable(text, {}) is not None
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
                if Path(destination).is_dir():
                    destination = str(Path(destination) / Path(source).name)
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
            with self.lock:
                epoch=self.epochs.get(chat_id,0)
                grant=OwnerGrant(uuid.uuid4().hex,chat_id,owner_identity(),self.settings()['owner_installation']['id'],
                    hashlib.sha256(text.encode()).hexdigest(),effect,frozenset(capabilities),paths,
                    str(Path(workspace).resolve()) if workspace else '',source,destination,self.clock()+600,epoch,project_spec,content_sha256)
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
                    self.used.discard(grant.id)

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
        """Reserve one mutation before dispatch; uncertain effects never replay."""
        if not self.authorize(tool, arguments):return False
        if tool in READ_TOOLS:return True
        grant = _current.get()[1]
        with self.lock:
            if grant.id in self.used:return False
            self.used.add(grant.id)
            return True

    def authorize(self,tool,arguments):
        current=_current.get()
        if not current or current[0] is not self or not self.enabled():return False
        grant=current[1]
        with self.lock:
            if self.active.get(grant.id) is not grant or self.epochs.get(grant.chat_id,0)!=grant.cancellation_epoch or self.clock()>=grant.expiry:return False
        if tool not in READ_TOOLS and grant.id in self.used:return False
        if tool not in grant.capabilities or FORBIDDEN_FIELDS & arguments.keys():return False
        if tool in {'git.status', 'git.diff', 'git.log', 'git.branch_list'}:
            if not grant.workspace or str(Path(arguments.get('workspace','')).resolve()) != grant.workspace:return False
            allowed = {'workspace'} | ({'staged'} if tool == 'git.diff' else {'limit'} if tool == 'git.log' else set())
            return (set(arguments) <= allowed and
                    ('staged' not in arguments or type(arguments['staged']) is bool) and
                    ('limit' not in arguments or type(arguments['limit']) is int and 1 <= arguments['limit'] <= 100))
        if tool == 'filesystem.write_text' and grant.content_sha256:
            if not isinstance(arguments.get('text'),str) or hashlib.sha256(arguments['text'].encode()).hexdigest() != grant.content_sha256:return False
        if tool == 'studio.new_project':
            if not grant.project_spec:return False
            name, language, location = grant.project_spec
            return arguments == {'name':name, 'language':language, 'template':'console', 'location':location} and not (Path(location)/name).exists()
        if tool in {'studio.run','workspace.run_validation'}:
            if not grant.workspace or str(Path(arguments.get('workspace','')).resolve())!=grant.workspace:return False
            # Validation commands must come from the existing controller's detector;
            # Owner Mode does not authorize arbitrary shell or model command strings.
            allowed = {'workspace','timeout'}
            if tool == 'workspace.run_validation' and 'commands' in arguments:
                from dataclasses import asdict
                from ..services.build_test_service import BuildAndTestService
                expected = [asdict(c) for c in BuildAndTestService().detect(grant.workspace) if c.source == 'known_standard']
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
                            creation_root=str(self.s.data_dir)):
            return await function(self,text,chat_id,*args,**kwargs)
    return invoke
