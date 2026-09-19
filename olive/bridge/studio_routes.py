"""Remaining workspace operations retain the existing editing/tool policies."""
from dataclasses import asdict
from pathlib import Path
from ..services.workspace_service import require_approved_workspace


def clean_buffers(host, workspace_id):
    if any(value['workspace_id'] == workspace_id for value in host.buffers.values()):
        raise ValueError('Save or reconcile unsaved editor buffers before changing workspace history')


async def git(host, workspace_id, action, **args):
    if action in {'checkout', 'create_branch'}:
        clean_buffers(host, workspace_id)
    return await host.services.studio.git(workspace_id, action, direct_user_action=action in {'status','diff','log','branch_list'}, **args)


async def rollback(host, workspace_id):
    clean_buffers(host, workspace_id)
    return await host.services.studio.rollback_latest(workspace_id)


def discard(host, workspace_id, path):
    service = host.services.studio.service(workspace_id)
    lock = host.services.studio.locks.get(workspace_id)
    if lock and lock.locked():
        raise ValueError('Wait for the current file operation before discarding its buffer')
    service.workspace.resolve(path)
    if path not in service.open_files:
        raise ValueError('This file is not open')
    host.buffers.pop(workspace_id + ':' + path, None)
    service.open_files.pop(path)
    return {'discarded': True}


def diagnostics(s, workspace_id):
    workspace = require_approved_workspace(s.workspace_repo, workspace_id)
    runs = [run for run in s.run_service.sessions.values() if run.workspace_id == workspace.id][-12:]
    def relative(problem):
        value = asdict(problem)
        if value.get('file'):
            try:
                value['file'] = workspace.resolve(value['file']).relative_to(Path(workspace.root_path)).as_posix()
            except (ValueError, PermissionError, OSError):
                value['file'] = None
        return value
    results = [{'session_id':run.id, 'state':run.state, 'exit_code':run.exit_code,
             'problems':[relative(p) for p in s.problem_service.parse((run.stderr+'\n'+run.stdout)[-200000:])],
             'tests':[asdict(t) for t in s.test_results.parse_unittest((run.stderr+'\n'+run.stdout)[-200000:])],
             'artifacts':[asdict(a) for a in run.artifacts], 'local_url':run.local_url} for run in runs]
    # Validation commands use their existing validation records, not run_service.sessions.
    # Present both sources through the same parser without creating another result store.
    seen = {item['session_id'] for item in results}
    for validation in s.studio.validations.values():
        if validation['workspace_id'] != workspace.id:
            continue
        for command in validation.get('results', []):
            identity = command.get('session_id')
            if not identity or identity in seen:
                continue
            seen.add(identity)
            output = (command.get('stderr', '') + '\n' + command.get('stdout', ''))[-200000:]
            results.append({'session_id': identity, 'state': command['state'], 'exit_code': command.get('exit_code'),
                'problems': [relative(p) for p in s.problem_service.parse(output)],
                'tests': [asdict(t) for t in s.test_results.parse_unittest(output)], 'artifacts': []})
    return results[-12:]


async def open_ide(s, workspace_id):
    workspace = require_approved_workspace(s.workspace_repo, workspace_id)
    return await s.agent.tool('ide.open_workspace', {'workspace':workspace.root_path,'path':workspace.root_path})


def routes(host):
    s = host.services
    return {
        'studio.git': lambda **args: git(host, **args),
        'studio.search': lambda workspace_id, query: s.studio.access(workspace_id, 'search', query=query, direct_user_action=True),
        'studio.rollback_latest': lambda workspace_id: rollback(host, workspace_id),
        'studio.discard_buffer': lambda **args: discard(host, **args),
        'studio.diagnostics': lambda workspace_id: diagnostics(s, workspace_id),
        'studio.open_ide': lambda workspace_id: open_ide(s, workspace_id),
    }
