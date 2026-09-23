"""One visible copy/move with exact paths, collision refusal and content verification."""
import asyncio
import configparser
import hashlib
import os
from pathlib import Path


def owned_file(source, destination):
    source, destination = Path(source).expanduser(), Path(destination).expanduser()
    if not source.is_absolute() or not destination.is_absolute() or source.is_symlink() or destination.is_symlink():
        raise PermissionError('Absolute owned paths without symlinks are required')
    if not source.is_file() or source.stat().st_uid != os.getuid() or source.stat().st_size > 10*1024*1024:
        raise PermissionError('The source must be an owned regular file within the verification budget')
    if not destination.is_dir() or destination.stat().st_uid != os.getuid():
        raise PermissionError('The destination must be an existing owned directory')
    source, destination = source.resolve(), destination.resolve()
    target = destination / source.name
    if target.exists() or target.is_symlink():
        raise FileExistsError('The destination already exists; no file was copied, moved or replaced')
    return source, destination, target


async def transfer(runtime, grant, app, processes):
    config = configparser.ConfigParser(interpolation=None)
    config.read(app.entry)
    if 'FileManager' not in config['Desktop Entry'].get('Categories', '').split(';'):
        raise PermissionError('Visible file transfer requires an installed file manager')
    source, destination, target = owned_file(grant.scope.content, grant.scope.path)
    digest = hashlib.sha256(source.read_bytes()).digest()
    d = runtime.desktop
    async def observe():
        runtime.check_task(grant)
        return await runtime.observe_app(app, processes)
    async def key(step, value=''):
        runtime.check_task(grant)
        await runtime.native.call('file_step', {'step': step, 'value': value})
        return await observe()
    async def folder(label, path):
        d.record.current_action = label
        d.publish()
        await key('address')
        observation = await key('path', str(path))
        # Qt location edits can expose their current value as accessible name.
        if not any(c.get('focused') and any(isinstance(value, str) and value.rstrip('/') == str(path).rstrip('/')
                   for value in (c.get('name'), c.get('value'))) for c in observation['controls']):
            raise ValueError('The requested folder path was not verified; Enter was not sent')
        await key('open')
        return await observe()
    await runtime.native.call('file_begin', {'source': str(source), 'destination': str(destination), 'operation': grant.scope.effect})
    await key('new_tab')
    observation = await folder('Finding the requested file', source.parent)
    matches = [c for c in observation['controls'] if c.get('name') == source.name and c.get('role') in {'icon', 'list item', 'table cell'}]
    if len(matches) != 1:
        raise ValueError('The requested file was not uniquely visible; no clipboard operation')
    c = matches[0]
    await runtime.native.call('click', {'revision': observation['revision'], 'target': c['id'], 'bounds': c['bounds'], 'value': ''})
    observation = await observe()
    selected = [c for c in observation['controls'] if c.get('selected') and c.get('role') in {'icon', 'list item', 'table cell'}]
    if len(selected) != 1 or selected[0]['name'] != source.name:
        raise ValueError('File selection is ambiguous; no clipboard operation')
    await key(grant.scope.effect)
    await folder('Opening the destination folder', destination)
    if target.exists() or target.is_symlink() or hashlib.sha256(source.read_bytes()).digest() != digest:
        raise PermissionError('The source or destination changed; paste was not sent')
    d.record.current_action = 'Moving the file' if grant.scope.effect == 'move' else 'Copying the file'
    d.publish()
    ledger = await runtime.reserve_effect(grant)
    await key('paste')  # Once only; an uncertain result must never repeat paste.
    for _ in range(15):
        runtime.check_task(grant)
        if target.is_file() and not target.is_symlink() and hashlib.sha256(target.read_bytes()).digest() == digest:
            if grant.scope.effect == 'move' and source.exists():
                raise ValueError('The destination exists but source removal was not verified')
            await asyncio.to_thread(ledger.verified, grant)
            d.record.status = 'completed'
            d.record.verification = 'The visible file manager transferred the exact file; destination contents and source state were verified.'
            return d.record.verification
        await asyncio.sleep(.2)
    raise TimeoutError('Paste dispatched once; the transfer outcome is unknown')
