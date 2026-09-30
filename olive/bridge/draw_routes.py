"""OLIVE Draw bridge routes. Storage work runs off the event loop."""
import asyncio

from ..draw.contracts import validate
from ..draw.service import DrawError


async def call(s, method, args):
    args = validate(method, args)
    draw = s.draw
    if method == 'draw.status':
        return await asyncio.to_thread(draw.status)
    if method == 'draw.purge' and not args['confirmed']:
        raise DrawError('Permanent deletion needs confirmation.')
    actions = {
        'draw.list': lambda: draw.list_drawings(args.get('view', 'drawings')),
        'draw.get': lambda: draw.get(args['drawing_id']),
        'draw.create': lambda: draw.create(args.get('title', ''), args.get('width', 1920), args.get('height', 1080),
                                           args.get('background', '#ffffff')),
        'draw.open': lambda: draw.open(args['drawing_id']),
        'draw.since': lambda: draw.since(args['drawing_id'], args['after']),
        'draw.append': lambda: draw.append(args['drawing_id'], args['op']),
        'draw.undo': lambda: draw.undo(args['drawing_id']),
        'draw.redo': lambda: draw.redo(args['drawing_id']),
        'draw.rename': lambda: draw.rename(args['drawing_id'], args['title']),
        'draw.duplicate': lambda: draw.duplicate(args['drawing_id']),
        'draw.trash': lambda: draw.trash(args['drawing_id']),
        'draw.restore': lambda: draw.restore(args['drawing_id']),
        'draw.purge': lambda: draw.purge(args['drawing_id']),
        'draw.thumbnail_put': lambda: draw.thumbnail_put(args['drawing_id'], args['revision'], args['image']),
        'draw.thumbnail_get': lambda: draw.thumbnail_get(args['drawing_id']),
        'draw.asset_info': lambda: draw.asset_info(args['asset_id']),
        'draw.asset_upload': lambda: draw.asset_upload(args['asset_id'], args['index'], args['count'], args['data']),
        'draw.asset_chunk': lambda: draw.asset_chunk(args['asset_id'], args['index']),
    }
    return await asyncio.to_thread(actions[method])
