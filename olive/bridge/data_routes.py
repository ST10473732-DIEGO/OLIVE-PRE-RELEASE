"""Explicit adapters for local data and settings. Domain services retain policy."""
from . import settings


def save_permissions(s, permissions, scopes):
    if set(permissions) - s.permissions.DEFAULTS.keys() or any(
        not isinstance(value, str) or value not in {'allow', 'ask', 'deny'} for value in permissions.values()
    ):
        raise ValueError('Unknown permission or decision')
    for scope in scopes:
        if not isinstance(scope, dict) or set(scope) - {'permission', 'decision', 'path', 'application'} or any(
            not isinstance(value, str) for value in scope.values()
        ):
            raise ValueError('Invalid scoped permission fields')
    return s.data.save_permissions(permissions, scopes)


def routes(s):
    return {
        'settings.schema': settings.schema,
        'data.settings': lambda **a: settings.visible(s.data.settings(**a)),
        'data.save_settings': lambda **a: settings.save(s, **a),
        'data.diagnostics': s.data.diagnostics,
        'data.maintenance': s.data.maintenance,
        'data.permissions': s.data.permissions,
        'data.save_permissions': lambda **a: save_permissions(s, **a),
        'data.clear_approvals': s.data.clear_approvals,
        'data.models': s.data.models,
        'data.refresh_models': s.data.refresh_models,
        'data.pull_model': s.data.pull_model,
        'models.status': s.models.status,
        'models.refresh': s.models.refresh,
        'models.save': s.models.save,
        'models.benchmark': s.models.benchmark,
        'models.stop_benchmark': s.models.stop_benchmark,
        'data.projects': s.data.projects,
        'data.project_detail': s.data.project_detail,
        'data.create_project': s.data.create_project,
        'data.workspaces': s.data.workspaces,
        'data.create_workspace': s.data.create_workspace,
        'data.memories': s.data.memories,
        'data.suggestions': s.data.suggestions,
        'data.memory_save': s.data.memory_save,
        'data.memory_delete': s.data.memory_delete,
        'data.review_suggestion': s.data.review_suggestion,
        'data.backup': s.data.backup,
        'data.restore': s.data.restore,
        'data.export': s.data.export,
        'knowledge.list': s.knowledge.list,
        'knowledge.attach': s.knowledge.attach,
        'knowledge.relink': s.knowledge.relink,
        'knowledge.reindex': s.knowledge.reindex,
        'knowledge.remove': s.knowledge.remove,
        'knowledge.retrieve': s.knowledge.retrieve,
        'knowledge.jobs': s.knowledge.jobs,
        'knowledge.job_action': s.knowledge.job_action,
        'knowledge.upgrade': lambda: s.knowledge.upgrade(return_status=True),
        'knowledge.upgrade_status': lambda: dict(s.knowledge.upgrade_state),
        'knowledge.cancel_upgrade': s.knowledge.cancel_upgrade,
    }
