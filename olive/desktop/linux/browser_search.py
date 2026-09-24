"""Visible-browser semantic search through the same portal/EIS session.

New tabs preserve unrelated pages and drafts. Each native step is followed by a
fresh scoped frame; text is checked before Enter and results are read afterward.
"""
import asyncio
import base64
import io
import re
import subprocess
import time
from PIL import Image


def read_frame(frame, toolbar=False):
    data = base64.b64decode(frame['png'], validate=True)
    with Image.open(io.BytesIO(data)) as image:
        output = io.BytesIO()
        crop = image.crop((0, 0, image.width, min(image.height, 180))) if toolbar else image
        crop.resize((crop.width*2, crop.height*2)).save(output, format='PNG')
        data = output.getvalue()
    result = subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', '11'], input=data,
                            capture_output=True, timeout=8, check=True)
    return result.stdout.decode('utf-8', errors='replace')[:12000]


async def search(runtime, grant, app, processes):
    import configparser
    config = configparser.ConfigParser(interpolation=None)
    config.read(app.entry)
    if 'WebBrowser' not in config['Desktop Entry'].get('Categories', '').split(';'):
        raise PermissionError('This visible search route requires an installed browser entry')
    d = runtime.desktop
    runtime.check_task(grant)
    pid = processes[0][0]
    visiting = grant.scope.effect == 'visit'
    await runtime.native.call('browser_visit' if visiting else 'browser_begin',
                              {'pid': pid, 'url' if visiting else 'query': grant.scope.content})
    history = []
    for step, label in [('new_tab', 'Opening a new browser tab'), ('address', 'Focusing the search field'),
                        ('type_query', 'Entering the requested search'), ('submit', 'Searching')]:
        runtime.check_task(grant)
        d.record.current_action = label
        d.publish()
        await runtime.native.call('browser_step', {'step': step})
        frame = await runtime.native.call('visual_observe', {'pid': pid}, timeout=5)
        history.append({'operation': step, 'status': 'dispatched; fresh scoped frame observed'})
        if step == 'type_query':
            semantic_match = False
            try:
                observation = await runtime.native.call('observe', {'pid': pid})
                semantic_match = any(c.get('editable') and c.get('focused') and c.get('value') in {
                    grant.scope.content, '? '+grant.scope.content} for c in observation['controls'])
            except RuntimeError:
                pass
            visible = '' if semantic_match else await asyncio.to_thread(read_frame, frame, True)
            normalized = lambda value: re.sub(r'\s+', ' ', value).casefold().strip()
            if not semantic_match and normalized(grant.scope.content) not in normalized(visible):
                raise ValueError('Search text was entered but not visually verified; Enter was not sent')
        d.record.history[:] = history
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        runtime.check_task(grant)
        d.record.current_action = 'Verifying the visible results'
        d.publish()
        frame = await runtime.native.call('visual_observe', {'pid': pid}, timeout=5)
        text = (await asyncio.to_thread(read_frame, frame)).casefold()
        title = frame['window'].get('title', '').casefold()
        if any(term in text for term in ('unusual traffic', 'captcha', 'verify you are human', 'problem loading page')):
            raise PermissionError('The browser requires human attention; search was not retried')
        if visiting:
            from urllib.parse import urlsplit
            wanted = urlsplit(grant.scope.content)
            try:
                observation = await runtime.native.call('observe', {'pid': pid})
                urls = [urlsplit(doc['uri']) for doc in observation.get('documents', [])]
                matched = any((u.scheme,u.netloc,u.path.rstrip('/'),u.query)==(wanted.scheme,wanted.netloc,wanted.path.rstrip('/'),wanted.query) for u in urls)
            except RuntimeError:
                matched = False
            if matched and len(text.strip()) > 20:
                d.record.status = 'completed'
                d.record.verification = 'The requested URL is exposed by the visible browser document and a fresh rendered page was read.'
                return d.record.verification
        elif grant.scope.content.casefold() in title and len(text) > 200 and any(term in text for term in ('search', 'results', 'images', 'videos')):
            d.record.status = 'completed'
            d.record.verification = 'The requested search is visible in the browser title and the rendered results page was read from a fresh desktop frame.'
            return d.record.verification
        await asyncio.sleep(.25)
    raise TimeoutError('Search submitted once; visible results were not verified')
