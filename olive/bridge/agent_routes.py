"""Agent presentation and explicit context selection around the shared language core."""
from copy import deepcopy

from ..agent.agent_task import ACTIVE_STATES


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


SUMMARY_KEYS = ('id', 'user_request', 'state', 'kind', 'chat_id', 'message_id', 'workspace_id', 'status_text',
                'timeline', 'changes', 'validation', 'preview', 'failure_category', 'error', 'completion_summary',
                'created_at', 'updated_at', 'plan', 'current_step', 'constraints', 'replans', 'validation_status', 'resume_state')


def task_view(task):
    """What the renderer shows. Receipts, tool arguments and raw output stay in the backend."""
    value = task.to_dict()
    view = {key: deepcopy(value.get(key)) for key in SUMMARY_KEYS}
    view['plan'] = [{'step_id': s['step_id'], 'description': s['description'], 'state': s['state'], 'expected': s['expected']}
                    for s in value.get('plan', [])]
    if view.get('validation'):
        view['validation'].pop('failure_excerpt', None)
    view['active'] = task.state in ACTIVE_STATES
    return view


def chat_tasks(s, chat_id):
    if chat_id not in s.chats:
        raise ValueError('Unknown conversation')
    return [task_view(t) for t in s.agent_task_repo.for_chat(chat_id) if t.kind in {'coding', 'desktop'}]


def workspace_task(s, workspace_id):
    tasks = [t for t in s.agent_task_repo.load_all().values() if t.kind == 'coding' and t.workspace_id == workspace_id]
    return task_view(max(tasks, key=lambda t: t.updated_at)) if tasks else None


def stop_task(s, task_id):
    runner = s.coding.runner
    task = runner.current
    if task and task.id == task_id and not task.terminal:
        if task.chat_id:
            s.interaction.cancel(task.chat_id)
        return {'stopped': True}
    # A desktop task card: Stop reaches the native loop first (no queued input).
    native = getattr(getattr(s, 'desktop', None), 'linux', None)
    record = getattr(native, 'task_record', None) if native else None
    desktop = getattr(record, 'task', None)
    if desktop is None or desktop.id != task_id or desktop.terminal:
        return {'stopped': False}
    native.stop()
    if desktop.chat_id:
        s.interaction.cancel(desktop.chat_id)
    return {'stopped': True}


def routes(s):
    return {
        'agent.chat_tasks': lambda chat_id: chat_tasks(s, chat_id),
        'agent.workspace_task': lambda workspace_id: workspace_task(s, workspace_id),
        'agent.task_diff': lambda task_id: s.coding.runner.diff(task_id),
        'agent.stop_task': lambda task_id: stop_task(s, task_id),
        'agent.stop_preview': lambda task_id: s.coding.runner.stop_preview(task_id),
        'agent.revert': lambda task_id: s.coding.runner.revert(task_id),
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
