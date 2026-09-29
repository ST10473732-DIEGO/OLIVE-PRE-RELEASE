"""Trusted UI workspace references are data, never an implicit command/grant."""
from functools import wraps
import re
from .deliverable import code_action_requested, instruction_text
from .trace import event


def selected_workspace_reference(function):
    @wraps(function)
    async def invoke(self, text, chat_id=None, *args, **kwargs):
        chat_id = chat_id or self.s.current_chat_id
        reference = kwargs.get('workspace_id', '')
        local = not getattr(self.s.chat, 'targets', {}).get(chat_id)
        instruction = instruction_text(text)
        existing = re.search(r'\b(?:my|this|that|selected|current|existing|the) (?:project|workspace|repository)\b', instruction)
        routine = re.fullmatch(r'(?:please )?(?:run|build|test|compile) (?:the |my )?(?:project|tests|test suite)[.!]?', instruction)
        # A request to generate new code and run its preview does not refer to
        # an unrelated project merely because Studio currently displays one.
        eligible = local and code_action_requested(text) and (existing or routine)
        if reference and eligible:
            workspace = self.s.workspace_repo.load_all().get(reference)
            if not workspace:
                raise ValueError('The selected Studio workspace is no longer available')
            context = self.context(chat_id)
            if context.workspace_id != reference:
                context.entities.pop('path', None)
                context.editor_context = None
            context.workspace_id = reference
            context.project_id = workspace.project_id
            context.studio_selection = (reference, None)
            event('workspace_reference_bound', workspace_id=reference)
        else:
            kwargs['workspace_id'] = ''
            follow = coding_follow_up(self.s, chat_id, text) if local else None
            self.context(chat_id).coding_follow_up = follow is not None
            if follow is not None:
                context = self.context(chat_id)
                context.workspace_id = follow.id
                context.project_id = follow.project_id
                context.studio_selection = (follow.id, None)
                _select(self, follow.id, chat_id)
                event('workspace_reference_bound', workspace_id=follow.id, source='follow_up')
            named = named_workspace(self.s, text) if local and follow is None and code_action_requested(text) else None
            if named is not None:
                # The user named a registered workspace in their own words ("my
                # BrokenCalc project"): bind it, exactly as a Studio selection would.
                context = self.context(chat_id)
                if context.workspace_id != named.id:
                    context.entities.pop('path', None)
                    context.editor_context = None
                context.workspace_id = named.id
                context.project_id = named.project_id
                context.studio_selection = (named.id, None)
                _select(self, named.id, chat_id)
                event('workspace_reference_bound', workspace_id=named.id, source='named')
        return await function(self, text, chat_id, *args, **kwargs)
    return invoke


def named_workspace(services, text):
    """The single registered workspace the literal request names, else None."""
    from pathlib import Path
    repository = getattr(services, 'workspace_repo', None)
    if repository is None:
        return None
    instruction = instruction_text(text)
    matches = {}
    for workspace in repository.load_all().values():
        names = {getattr(workspace, 'title', '') or '', Path(getattr(workspace, 'root_path', '') or '.').name}
        for name in names:
            name = str(name).strip().casefold()
            if len(name) >= 3 and re.search(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', instruction):
                matches[workspace.id] = workspace
    return next(iter(matches.values())) if len(matches) == 1 else None


FOLLOW_UP = re.compile(r"^(?:(?:please|now|also|and|ok|okay|great|nice|thanks)[,!.]?\s+)*(?:can you\s+|could you\s+)?"
                       r"(?:change|make|add|remove|delete|rename|update|replace|use|set|put|fix|turn|give|increase|decrease|"
                       r"center|centre|align|style|restyle|swap|move|translate|include|show|hide)\b", re.I)
NOT_CODE = re.compile(r"\b(?:volume|brightness|bluetooth|wi-?fi|network|discord|firefox|browser|email|e-mail|mail|calendar|"
                      r"reminder|meeting|event|message|send|spotify|music|song|desktop|wallpaper|window|file manager|dolphin|"
                      r"memory|remember|research|search the web)\b", re.I)


def coding_follow_up(services, chat_id, text, window=4):
    """The workspace of this chat's coding task when `text` is a short follow-up edit to it.

    Bounded: the task must be this conversation's latest coding task, anchored to
    one of the last few user turns, still resolvable, and the text must read as a
    change request without naming another application or system setting.
    """
    if not isinstance(text, str) or len(text) > 600 or not FOLLOW_UP.search(text) or NOT_CODE.search(text):
        return None
    from .project_request import project_request
    if project_request(text):
        return None  # A new project request is never an edit to the previous one.
    repo = getattr(services, 'agent_task_repo', None)
    chats = getattr(services, 'chats', None)
    chat = chats.get(chat_id) if isinstance(chats, dict) else None
    if repo is None or chat is None or getattr(services, 'workspace_repo', None) is None:
        return None
    tasks = [t for t in repo.for_chat(chat_id, limit=5) if t.kind == 'coding' and t.workspace_id]
    if not tasks:
        return None
    task = tasks[-1]
    recent_users = [m.id for m in chat.messages if m.role == 'user'][-window:]
    if task.message_id not in recent_users or task.state in {'cancelled'}:
        return None
    return services.workspace_repo.load_all().get(task.workspace_id)


def _select(orchestrator, workspace_id, chat_id):
    """A workspace the user named (or is continuing) becomes the conversation's selection,
    so an older implicit Studio selection cannot silently replace it, and Studio follows."""
    if getattr(orchestrator, 'selected_workspace', None) != workspace_id:
        orchestrator.selected_workspace = workspace_id
        orchestrator.selected_file = None
        publish = getattr(orchestrator.s, 'publish', None)
        if publish:
            publish('studio.selection', {'workspace_id': workspace_id, 'chat_id': chat_id})
