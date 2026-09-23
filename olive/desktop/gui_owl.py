"""GUI-Owl computer_use protocol, never Python execution.

Conventions: X-PLUG/MobileAgent Mobile-Agent-v3.5/computer_use (MIT).
Coordinates are 0..1000 relative to the supplied image, including cropped images.
"""
import json
import math
import re

# Canonical upstream computer_use tool description and response convention.
# Parser below deliberately accepts only the implemented subset.
from pathlib import Path
SYSTEM = Path(__file__).with_name('gui_owl_prompt.txt').read_text(encoding='utf-8')



def parse_action(raw):
    if not isinstance(raw, str) or len(raw) > 12000:
        raise ValueError('Invalid GUI output size')
    blocks = re.findall(r'<tool_call>\s*(.*?)\s*</tool_call>', raw, re.S)
    if len(blocks) != 1:
        raise ValueError('Exactly one GUI action required')
    def pairs(items):
        value = {}
        for k, v in items:
            if k in value:
                raise ValueError('Duplicate action field')
            value[k] = v
        return value
    call = json.loads(blocks[0], object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite action')))
    if not isinstance(call, dict) or set(call) != {'name', 'arguments'} or call['name'] != 'computer_use':
        raise ValueError('Unknown GUI tool')
    args = call['arguments']
    fields = {'left_click': {'coordinate'}, 'key': {'keys'}, 'type': {'text'},
              'scroll': {'pixels'}, 'wait': {'time'}, 'terminate': {'status'}, 'interact': {'text'}}
    if not isinstance(args, dict) or args.get('action') not in fields or set(args) != fields[args['action']] | {'action'}:
        raise ValueError('Unknown GUI action or fields')
    action = args['action']
    if action == 'left_click':
        point = args['coordinate']
        if not isinstance(point, list) or len(point) != 2 or any(type(n) not in (float, int) or not math.isfinite(n) or not 0 <= n < 1000 for n in point):
            raise ValueError('Invalid GUI coordinates')
    if action == 'key' and (not isinstance(args['keys'], list) or not 1 <= len(args['keys']) <= 3 or any(k not in {
            'CTRL', 'ALT', 'SHIFT', 'ENTER', 'TAB', 'ESC', 'L', 'T', 'N', 'S', 'F', 'C', 'V', 'A',
            'UP', 'DOWN', 'LEFT', 'RIGHT', 'PAGEUP', 'PAGEDOWN'} for k in args['keys'])):
        raise ValueError('Unsupported GUI keys')
    if action in {'type', 'interact'} and (not isinstance(args['text'], str) or not 1 <= len(args['text']) <= 4000 or '\x00' in args['text']):
        raise ValueError('Invalid GUI text')
    if action in {'scroll', 'wait'}:
        n = args['pixels'] if action == 'scroll' else args['time']
        if type(n) not in (int, float) or not math.isfinite(n) or not (-600 <= n <= 600 if action == 'scroll' else 0 <= n <= 3):
            raise ValueError('Invalid GUI distance/duration')
    if action == 'terminate' and args['status'] not in {'success', 'failure'}:
        raise ValueError('Invalid GUI outcome')
    return args


def compositor_point(point, resized_size, crop, frame_size, region):
    from .linux.geometry import pixel_point, rectangle
    x, y, width, height = rectangle(crop)
    rw, rh = resized_size
    if rw <= 0 or rh <= 0 or x < 0 or y < 0 or x+width > frame_size[0] or y+height > frame_size[1]:
        raise ValueError('Invalid resized/cropped image geometry')
    # Normalized -> resized pixel -> crop pixel -> original frame -> compositor.
    px, py = point[0] * rw / 1000, point[1] * rh / 1000
    return pixel_point(region, frame_size, (x + px * width/rw, y + py * height/rh))
