"""Typed OLIVE Notes bridge methods. No SQL, file or eval surface is exposed."""
import re

UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
TOKEN = re.compile(r'^[0-9a-f]{32}$')
B64 = re.compile(r'^[A-Za-z0-9+/]*={0,2}$')

SPEC = {
    'notes.list': ({}, {'view': str}),
    'notes.get': ({'note_id': str}, {}),
    'notes.create': ({}, {'title': str, 'text': str}),
    'notes.open': ({'note_id': str}, {}),
    'notes.state_chunk': ({'token': str, 'index': int}, {}),
    'notes.state_since': ({'note_id': str, 'state_vector': str}, {}),
    'notes.apply': ({'note_id': str, 'update': str}, {'view': str, 'upload': dict}),
    'notes.rename': ({'note_id': str, 'title': str}, {}),
    'notes.pin': ({'note_id': str, 'pinned': bool}, {}),
    'notes.trash': ({'note_id': str}, {}),
    'notes.restore': ({'note_id': str}, {}),
    'notes.purge': ({'note_id': str, 'confirmed': bool}, {}),
    'notes.duplicate': ({'note_id': str}, {}),
    'notes.search': ({'query': str}, {'include_trash': bool}),
    'notes.history': ({'note_id': str}, {}),
    'notes.history_get': ({'history_id': str}, {}),
    'notes.history_restore': ({'note_id': str, 'history_id': str}, {}),
    'notes.status': ({}, {}),
}
# Paths come only from the Electron main process's own file dialogs.
MAIN_ONLY = {
    'notes.export': ({'note_id': str, 'path': str, 'format': str}, {}),
    'notes.import': ({'path': str}, {}),
}
# Keystroke-rate and read-only calls: CRDT applies are idempotent, so they do
# not need (and must not fill) the non-evicting bridge replay ledger.
UNLEDGERED = frozenset({'notes.list', 'notes.get', 'notes.open', 'notes.state_chunk', 'notes.state_since',
                        'notes.apply', 'notes.search', 'notes.history', 'notes.history_get', 'notes.status',
                        'notes.rename', 'notes.pin', 'notes.trash', 'notes.restore'})
LIMITS = {'update': 900_000, 'text': 200_000, 'title': 200, 'query': 500, 'path': 4096, 'view': 16}


def validate(method, args):
    required, optional = (SPEC | MAIN_ONLY)[method]
    if not isinstance(args, dict) or not set(required) <= set(args) or set(args) - (required.keys() | optional.keys()):
        raise ValueError('Invalid Notes arguments')
    for key, value in args.items():
        if type(value) is not (required | optional)[key]:
            raise ValueError('Invalid Notes argument type')
        if isinstance(value, str):
            limit = LIMITS.get(key, 4096) if key not in ('update',) else LIMITS['update']
            if key in ('note_id', 'history_id') and not UUID.fullmatch(value):
                raise ValueError('Invalid note reference')
            if len(value) > limit or '\x00' in value:
                raise ValueError('Notes argument exceeds supported bounds')
    if 'token' in args and not TOKEN.fullmatch(args['token']):
        raise ValueError('Invalid Notes transfer')
    for key in ('update', 'state_vector'):
        if key in args and not B64.fullmatch(args[key]):
            raise ValueError('Invalid Notes data')
    if args.get('view') not in (None, 'notes', 'trash') and method == 'notes.list':
        raise ValueError('Unknown Notes view')
    if method == 'notes.apply' and 'view' in args and len(args['view']) > 64:
        raise ValueError('Invalid Notes view')
    if method == 'notes.export' and args['format'] not in ('txt', 'md'):
        raise ValueError('Export as .txt or .md')
    if 'index' in args and not 0 <= args['index'] < 64:
        raise ValueError('Invalid Notes transfer')
    return args
