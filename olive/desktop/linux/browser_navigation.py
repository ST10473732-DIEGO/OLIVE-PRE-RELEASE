"""Read, scroll and tab operations on the user's visible browser."""
import asyncio
import configparser
import base64
import io
from PIL import Image
from .browser_search import read_frame


def document_frame(frame, documents):
    """Crop the verified current document; unrelated tab titles are not page data."""
    from .geometry import contains
    candidates = [d for d in documents if d.get('ready') and contains(frame['window']['bounds'], d.get('bounds'))]
    if len(candidates) != 1:
        raise ValueError('The visible page region is not uniquely exposed; browser chrome was not read')
    x,y,w,h = frame['window']['bounds']
    dx,dy,dw,dh = candidates[0]['bounds']
    sx,sy = frame['width']/w,frame['height']/h
    box = (round((dx-x)*sx),round((dy-y)*sy),round((dx+dw-x)*sx),round((dy+dh-y)*sy))
    with Image.open(io.BytesIO(base64.b64decode(frame['png'], validate=True))) as image:
        cropped = image.crop(box)
        output = io.BytesIO(); cropped.save(output, format='PNG')
    return {**frame, 'png':base64.b64encode(output.getvalue()).decode(), 'width':box[2]-box[0], 'height':box[3]-box[1]}


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
    locations = await runtime.native.call('document_locations', {'pid':processes[0][0]})
    if grant.scope.effect == 'read' and grant.scope.content:
        from ..browser_url import validated_url
        current = [d for d in locations.get('documents', []) if d.get('ready')]
        if len(current) != 1 or validated_url(current[0].get('uri','')) != validated_url(grant.scope.content):
            raise PermissionError('The current page differs from the verified task source')
    page = document_frame(after, locations.get('documents', []))
    text = await asyncio.to_thread(read_frame, page)
    if not text.strip():
        raise ValueError('The visible page text could not be read')
    d.record.status = 'completed'
    d.record.verification = 'The visible browser page was read from a fresh desktop frame. OCR text may contain transcription errors.'
    # Screen text is quoted data, never an instruction or a tool invocation.
    return d.record.verification + '\n\n' + '\n'.join('> '+line for line in text.strip()[:4000].splitlines())
