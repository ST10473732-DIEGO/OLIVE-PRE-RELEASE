"""Read, scroll and tab operations on the user's visible browser."""
import asyncio
import configparser
from .browser_search import read_frame


async def navigate(runtime, grant, app, processes):
    config = configparser.ConfigParser(interpolation=None)
    config.read(app.entry)
    if 'WebBrowser' not in config['Desktop Entry'].get('Categories', '').split(';'):
        raise PermissionError('This navigation route requires an installed browser')
    d = runtime.desktop
    runtime.check_task(grant)
    before = await runtime.native.call('visual_observe', {'pid': processes[0][0]}, timeout=5)
    if grant.scope.effect != 'read':
        d.record.current_action = 'Scrolling' if grant.scope.effect == 'scroll' else 'Changing tabs'
        d.publish()
        await runtime.native.call('browser_navigation', {'operation': grant.scope.effect, 'direction': grant.scope.content})
        after = await runtime.native.call('visual_observe', {'pid': processes[0][0]}, timeout=5)
        if after['png'] == before['png']:
            raise ValueError('Navigation dispatched once; no visible change was verified')
    else:
        after = before
    runtime.check_task(grant)
    d.record.current_action = 'Reading the visible page'
    d.publish()
    text = await asyncio.to_thread(read_frame, after)
    if not text.strip():
        raise ValueError('The visible page text could not be read')
    d.record.status = 'completed'
    d.record.verification = 'The visible browser page was read from a fresh desktop frame. OCR text may contain transcription errors.'
    # Screen text is quoted data, never an instruction or a tool invocation.
    return d.record.verification + '\n\n' + '\n'.join('> '+line for line in text.strip()[:4000].splitlines())
