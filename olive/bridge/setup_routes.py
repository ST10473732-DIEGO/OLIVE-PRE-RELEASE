"""First-run setup operations: desktop bridge only, never network dispatch, never a model tool.

Every install is started by the person in the setup wizard. The operations only accept
manifest entry ids; there is no way to pass a URL, a path to download to, or a command.
"""
import re

SPEC = {
    'runtime.setup_status': ({}, {}),
    'runtime.setup_update': ({}, {'step': str, 'profile': str, 'preferred_name': str, 'action': str, 'optional': list}),
    'runtime.system_check': ({}, {'refresh': bool}),
    'runtime.manifest': ({}, {}),
    'runtime.install_plan': ({'profile': str}, {'selected': list}),
    'runtime.install_start': ({'profile': str, 'entries': list}, {}),
    'runtime.install_progress': ({}, {'job_id': str}),
    'runtime.install_cancel': ({'job_id': str}, {}),
    'runtime.install_retry': ({'job_id': str}, {}),
    'runtime.uninstall': ({'entry_id': str}, {}),
    'runtime.choose': ({'name': str}, {'paths': dict, 'folder': str}),
    'runtime.forget': ({'name': str}, {}),
    'runtime.verify': ({'profile': str}, {'run_fast': bool, 'media_smoke': bool}),
}
# Read-only: they never enter the request replay ledger (progress is polled).
READ_ONLY = {'runtime.setup_status', 'runtime.system_check', 'runtime.manifest', 'runtime.install_plan',
             'runtime.install_progress'}
ENTRY = re.compile(r'^[a-z0-9][a-z0-9._-]{0,79}$')
JOB = re.compile(r'^[0-9a-f]{32}$')
PROFILES = {'core', 'creator', 'complete'}
ACTIONS = {'skip', 'reset', 'resume'}
PATH_KEYS = {'executable', 'models', 'root', 'python', 'url', 'path'}


def _entries(value, limit=64):
    if not isinstance(value, list) or len(value) > limit or not all(isinstance(v, str) and ENTRY.match(v) for v in value):
        raise ValueError('Invalid setup component list')


def validate_arguments(method, args):
    from ..storage.setup_state_repository import STEPS
    from ..services.runtime_discovery import NAMES
    if 'profile' in args and args['profile'] not in PROFILES:
        raise ValueError('Unknown OLIVE package')
    if 'step' in args and args['step'] not in STEPS:
        raise ValueError('Unknown setup step')
    if 'action' in args and args['action'] not in ACTIONS:
        raise ValueError('Unknown setup action')
    if 'preferred_name' in args and len(args['preferred_name']) > 120:
        raise ValueError('Your name can be at most 120 characters')
    for key in ('entries', 'selected', 'optional'):
        if key in args:
            _entries(args[key])
    if method == 'runtime.install_start' and not args['entries']:
        raise ValueError('Choose at least one component to install')
    if 'entry_id' in args and not ENTRY.match(args['entry_id']):
        raise ValueError('Invalid setup component')
    if 'job_id' in args and not JOB.match(args['job_id']):
        raise ValueError('Invalid setup job')
    if 'name' in args and args['name'] not in NAMES:
        raise ValueError('Unknown runtime')
    if method == 'runtime.choose':
        if ('paths' in args) == ('folder' in args):
            raise ValueError('Choose either detected paths or a folder')
        paths = args.get('paths', {})
        if (not isinstance(paths, dict) or len(paths) > 6 or set(paths) - PATH_KEYS
                or not all(isinstance(v, str) and 0 < len(v) <= 4096 and '\x00' not in v for v in paths.values())):
            raise ValueError('Invalid runtime location')


async def call(services, method, args):
    import asyncio
    s = services
    if method == 'runtime.setup_status':
        return await s.first_run.status()
    if method == 'runtime.setup_update':
        return s.first_run.update(**args)
    if method == 'runtime.system_check':
        return await s.first_run.system(refresh=args.get('refresh', False))
    if method == 'runtime.manifest':
        return s.runtime_installer.describe()
    if method == 'runtime.install_plan':
        return await s.runtime_installer.plan(args['profile'], args.get('selected'))
    if method == 'runtime.install_start':
        return await s.runtime_installer.start(args['profile'], args['entries'])
    if method == 'runtime.install_progress':
        return s.runtime_installer.progress(args.get('job_id'))
    if method == 'runtime.install_cancel':
        return s.runtime_installer.cancel(args['job_id'])
    if method == 'runtime.install_retry':
        return await s.runtime_installer.retry(args['job_id'])
    if method == 'runtime.uninstall':
        return await s.runtime_installer.uninstall(args['entry_id'])
    if method == 'runtime.choose':
        discovery = s.runtime_discovery
        paths = args.get('paths') or discovery.from_folder(args['name'], args['folder'])
        located = await asyncio.to_thread(discovery.choose, args['name'], paths)
        s.runtimes[args['name']] = located
        if args['name'] == 'ollama':
            s.local_ollama_runtime.executable = located.get('executable') or None
        # Media engines read their location when OLIVE starts.
        return {'runtime': located.to_dict(discovery.platform), 'restart_required': args['name'] != 'ollama'}
    if method == 'runtime.forget':
        discovery = s.runtime_discovery
        await asyncio.to_thread(discovery.forget, args['name'])
        located = (await asyncio.to_thread(discovery.resolve))[args['name']]
        s.runtimes[args['name']] = located
        return {'runtime': located.to_dict(discovery.platform), 'restart_required': args['name'] != 'ollama'}
    if method == 'runtime.verify':
        return await s.first_run.verify(args['profile'], args.get('run_fast', True), args.get('media_smoke', False))
    raise ValueError('Unsupported setup operation')
