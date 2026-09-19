"""Agent presentation and explicit context selection around the shared language core."""
from copy import deepcopy


def history(s, query="", offset=0):
    from .history_page import summary_page
    keys = ('id', 'user_request', 'state', 'project_id', 'workspace_id', 'updated_at', 'validation_status')
    return summary_page(s.agent.history(), keys, "user_request", query, offset)


def get_task(s, task_id):
    if s.agent.current and s.agent.current.id == task_id:
        return s.agent.current.to_dict()
    return s.agent_task_repo.load_all()[task_id].to_dict()


async def launch(s, chat_id, text, workspace_id='', project_id='', path=None, selection=''):
    interaction = s.interaction
    if chat_id in interaction.active or interaction.interpreting.get(chat_id) or chat_id in s.chat.generations:
        raise ValueError('Stop the current request before changing its objective or context.')
    context = interaction.context(chat_id)
    workspace = s.workspace_repo.load_all().get(workspace_id) if workspace_id else None
    if workspace_id and not workspace:
        raise ValueError('Unknown approved workspace')
    if project_id and project_id not in s.project_repo.load_all():
        raise ValueError('Unknown project')
    if workspace and project_id and workspace.project_id and workspace.project_id != project_id:
        raise ValueError('The selected workspace belongs to a different project.')
    if path is not None:
        if not workspace:
            raise ValueError('Choose an approved Studio workspace')
        from ..services.workspace_service import require_approved_workspace
        workspace = require_approved_workspace(s.workspace_repo, workspace_id)
        if path and path not in s.studio.service(workspace_id).open_files:
            raise ValueError('Open the selected file through Studio first')
        selected_path = str(workspace.resolve(path)) if path else None
    if (workspace_id or None) != interaction.selected_workspace:
        interaction.clear_context(chat_id)
        interaction.select_workspace(workspace_id or None)
    context.workspace_id = workspace_id or None
    if path is not None:
        interaction.selected_file = selected_path
        context.editor_context = {'active_file': path[:500], 'selection': selection[:12000]}
    context.project_id = project_id or (workspace.project_id if workspace else None)
    if interaction.selected_file:
        context.entities['path'] = interaction.selected_file
    elif path is not None:
        context.entities.pop('path', None)
    if context.project_id:
        context.entities['project'] = s.project_repo.load_all()[context.project_id].title
    else:
        context.entities.pop('project', None)
    context.studio_selection = (interaction.selected_workspace, interaction.selected_file)
    # No model hint, keyword prefix, alternate planner or permission override.
    return await interaction.submit(text, chat_id)


def routes(s):
    return {
        'agent.history': lambda **args: history(s, **args),
        'agent.get': lambda task_id: get_task(s, task_id),
        'agent.current': lambda: {'task': s.agent.current.to_dict() if s.agent.current else None,
                                 'active': bool(s.agent.active), 'paused': s.agent.pause_state == 'paused',
                                 'pause_state': s.agent.pause_state},
        'agent.actions': lambda: deepcopy(s.agent.actions()),
        'agent.pause': s.agent.pause,
        'agent.resume': s.agent.resume,
        'agent.cancel': s.agent.cancel,
        'interaction.launch': lambda **a: launch(s, **a),
        'interaction.studio': lambda **a: launch(s, **a),
    }
