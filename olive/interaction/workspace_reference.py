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
        return await function(self, text, chat_id, *args, **kwargs)
    return invoke
