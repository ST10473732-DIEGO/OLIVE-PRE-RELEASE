"""Visible new-document/edit/save; final filesystem read verifies the GUI effect."""
import asyncio
import os
from pathlib import Path


def note_path(value):
    path = Path(value).expanduser()
    if (not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)) or path.exists() or
            not path.parent.is_dir() or path.parent.stat().st_uid != os.getuid()):
        raise PermissionError('Choose an unused file in an existing owned directory; no file was replaced')
    return path.parent.resolve() / path.name


async def save_note(runtime, grant, app, processes):
    import configparser
    config = configparser.ConfigParser(interpolation=None)
    config.read(app.entry)
    if 'TextEditor' not in config['Desktop Entry'].get('Categories', '').split(';'):
        raise PermissionError('This new-document route requires an installed text editor')
    d = runtime.desktop
    path = note_path(grant.scope.path)
    async def observe():
        runtime.check_task(grant)
        return await runtime.observe_app(app, processes)
    async def act(method, target, value=''):
        runtime.check_task(grant)
        await runtime.native.call(method, {'revision': observation['revision'], 'target': target['id'],
                                          'bounds': target['bounds'], 'value': value})
    d.record.current_action = 'Creating a new document'
    d.publish()
    await runtime.native.call('editor_key', {'step': 'new_document'})
    observation = await observe()
    editors = [c for c in observation['controls'] if c.get('editable') and c.get('role') in {'text', 'entry', 'document text'} and not c.get('value')]
    if grant.scope.effect == 'paste_save':
        # Explicit clipboard use, normal Ctrl+V into a fresh untitled document.
        # No clipboard read service is exposed to a model or remote peer.
        await runtime.native.call('editor_paste', {})
        observation = await observe()
        verified_text = True  # Exact saved contents are verified below; not claimed yet.
    elif len(editors) == 1:
        if not editors[0].get('focused'):
            await act('focus', editors[0])
            observation = await observe()
        editors = [c for c in observation['controls'] if c.get('editable') and c.get('focused') and not c.get('value')]
        if len(editors) != 1:
            raise ValueError('The new empty editor did not accept focus')
        await act('type', editors[0], grant.scope.content)
        observation = await observe()
        verified_text = any(c.get('editable') and c.get('value') == grant.scope.content for c in observation['controls'])
    elif len(editors) == 0:
        # Some Qt editors expose their text interface without visible geometry.
        # A newly created untitled document has a narrow native keyboard route.
        await runtime.native.call('editor_text', {'value': grant.scope.content})
        from .browser_search import read_frame
        verified_text = False
        for _ in range(3):
            runtime.check_task(grant)
            frame = await runtime.native.call('visual_observe', {'pid': processes[0][0]}, timeout=5)
            visible = await asyncio.to_thread(read_frame, frame)
            verified_text = ' '.join(grant.scope.content.split()) in ' '.join(visible.split())
            if verified_text:
                break
    else:
        raise ValueError('The new document has ambiguous empty editors')
    if not verified_text:
        raise ValueError('Entered document text was not verified; no save was attempted')
    await runtime.native.call('editor_key', {'step': 'save_as'})
    observation = await observe()
    fields = [c for c in observation['controls'] if c.get('editable') and any(
        label.strip().casefold().rstrip(':') in {'file name', 'filename', 'name'}
        for label in [c['name'], *c.get('labels', [])])]
    if len(fields) != 1:
        raise ValueError('The save dialog filename was not uniquely resolved')
    if not fields[0].get('focused'):
        await act('focus', fields[0])
        observation = await observe()
        fields = [c for c in observation['controls'] if c.get('editable') and c.get('focused')]
    if len(fields) != 1:
        raise ValueError('Save filename focus is ambiguous')
    await act('filename', fields[0], str(path))
    observation = await observe()
    if not any(c.get('value') == str(path) for c in observation['controls']):
        raise ValueError('The requested save path was not verified')
    buttons = [c for c in observation['controls'] if c['name'].casefold() == 'save' and c.get('enabled')]
    if len(buttons) != 1 or path.exists():
        raise PermissionError('Save target is ambiguous or a file already exists; no overwrite')
    d.record.current_action = 'Saving and verifying the document'
    d.publish()
    actions = [a for a in buttons[0].get('actions', []) if a.casefold() in {'press', 'click'}]
    if len(actions) != 1:
        raise ValueError('The save action was not uniquely exposed')
    ledger = await runtime.reserve_effect(grant)
    await act('invoke', buttons[0], actions[0])
    for _ in range(15):
        runtime.check_task(grant)
        if path.is_file():
            if path.is_symlink():
                raise PermissionError('The saved path became a symbolic link')
            if path.stat().st_size > 8_000_000:
                raise ValueError('Saved document exceeds the verification budget')
            saved = path.read_text()
            if grant.scope.content.endswith('\n') and path.read_bytes() != grant.scope.content.encode('utf-8'):
                raise ValueError('The saved bytes differ from the bound note text')
            if grant.scope.effect == 'paste_save' and not saved:
                raise ValueError('Clipboard paste produced an empty document')
            if grant.scope.effect != 'paste_save' and saved not in {grant.scope.content, grant.scope.content+'\n'}:
                raise ValueError('The GUI-created document differs from the requested text')
            await asyncio.to_thread(ledger.verified, grant)
            d.record.status = 'completed'
            d.record.verification = ('The visible editor pasted the system clipboard into a new document and saved the requested file; the saved text was read back. Exact clipboard equality is not independently known.' if grant.scope.effect == 'paste_save' else 'The visible editor saved the requested new file; its contents were read back and verified.')
            return d.record.verification
        await asyncio.sleep(.2)
    raise TimeoutError('Save was requested once; the new file was not observed')
