"""OLIVE Notes bridge routes. Every data operation runs on the Notes owner thread."""
import asyncio
import os
from pathlib import Path
import tempfile

from ..notes.contracts import validate
from ..notes.service import NotesError


def _write_text(path, text):
    target = Path(path)
    if not target.is_absolute() or target.suffix.lower() not in ('.txt', '.md'):
        raise NotesError('Export as .txt or .md')
    handle, temporary = tempfile.mkstemp(prefix='.olive-note-', dir=target.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as output:
            output.write(text)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return {'exported': True, 'name': target.name}


def _read_text(path):
    source = Path(path)
    if not source.is_absolute() or source.suffix.lower() not in ('.txt', '.md', '.markdown', '.text'):
        raise NotesError('Import a .txt or .md file')
    data = source.read_bytes()
    if len(data) > 1_500_000:
        raise NotesError('Note too large. Notes can hold up to about 1.5 MB of text.')
    if b'\x00' in data:
        raise NotesError('Only plain text files can be imported.')
    try:
        return source.stem[:200], data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise NotesError('Only UTF-8 text files can be imported.') from None


async def status(s):
    notes = s.notes
    if notes.unavailable:
        from ..notes.service import MESSAGES
        return {'available': False, 'message': MESSAGES.get(notes.unavailable, MESSAGES['notes_unavailable']), 'peers': []}
    local = await notes.call(notes.status)
    remote = s.connect.notes
    peers = []
    if remote is not None:
        def collect():
            items = []
            for device in s.connect.listed_devices():
                if device.get('trust_state') != 'paired' or device.get('revoked_at') is not None:
                    continue
                if not remote.permitted(device['device_id']):
                    continue
                items.append(dict(remote.status(device['device_id']), device_id=device['device_id'],
                                  name=device['display_name'], platform=device.get('platform', '')))
            return items
        peers = await asyncio.to_thread(collect)
    return dict(local, peers=peers, connect=bool(s.connect.network))


async def call(s, method, args):
    args = validate(method, args)
    notes = s.notes
    if method == 'notes.status':
        return await status(s)
    if method == 'notes.purge' and not args['confirmed']:
        raise NotesError('Permanent deletion needs confirmation.')
    if method == 'notes.export':
        text = await notes.call(notes.export_text, args['note_id'], args['format'])
        return await asyncio.to_thread(_write_text, args['path'], text)
    if method == 'notes.import':
        title, body = await asyncio.to_thread(_read_text, args['path'])
        return await notes.call(notes.import_text, title, body)
    actions = {
        'notes.list': lambda: notes.list_notes(args.get('view', 'notes')),
        'notes.get': lambda: notes.get(args['note_id']),
        'notes.create': lambda: notes.create(args.get('title', ''), args.get('text', '')),
        'notes.open': lambda: notes.open(args['note_id']),
        'notes.state_chunk': lambda: notes.state_chunk(args['token'], args['index']),
        'notes.state_since': lambda: notes.state_since(args['note_id'], args['state_vector']),
        'notes.apply': lambda: notes.apply_update(args['note_id'], args['update'], view=args.get('view'),
                                                  upload=args.get('upload')),
        'notes.rename': lambda: notes.rename(args['note_id'], args['title']),
        'notes.pin': lambda: notes.set_pinned(args['note_id'], args['pinned']),
        'notes.trash': lambda: notes.trash(args['note_id']),
        'notes.restore': lambda: notes.restore(args['note_id']),
        'notes.purge': lambda: notes.purge(args['note_id']),
        'notes.duplicate': lambda: notes.duplicate(args['note_id']),
        'notes.search': lambda: notes.search(args['query'], include_trash=args.get('include_trash', False)),
        'notes.history': lambda: notes.history(args['note_id']),
        'notes.history_get': lambda: notes.history_text(args['history_id']),
        'notes.history_restore': lambda: notes.restore_history(args['note_id'], args['history_id']),
    }
    return await notes.call(actions[method])
