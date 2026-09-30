"""Typed OLIVE Draw bridge methods. No SQL, file path or eval surface is exposed.

Operation contents are validated again, field by field, by ``document`` before
anything is stored. Image bytes arrive only as bounded base64 chunks whose
SHA-256 must equal the asset id.
"""
import re

UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
B64 = re.compile(r'^[A-Za-z0-9+/]*={0,2}$')
ASSET = re.compile(r'^[0-9a-f]{64}$')

SPEC = {
    'draw.status': ({}, {}),
    'draw.list': ({}, {'view': str}),
    'draw.get': ({'drawing_id': str}, {}),
    'draw.create': ({}, {'title': str, 'width': int, 'height': int, 'background': str}),
    'draw.open': ({'drawing_id': str}, {}),
    'draw.since': ({'drawing_id': str, 'after': int}, {}),
    'draw.append': ({'drawing_id': str, 'op': dict}, {}),
    'draw.undo': ({'drawing_id': str}, {}),
    'draw.redo': ({'drawing_id': str}, {}),
    'draw.rename': ({'drawing_id': str, 'title': str}, {}),
    'draw.duplicate': ({'drawing_id': str}, {}),
    'draw.trash': ({'drawing_id': str}, {}),
    'draw.restore': ({'drawing_id': str}, {}),
    'draw.purge': ({'drawing_id': str, 'confirmed': bool}, {}),
    'draw.thumbnail_put': ({'drawing_id': str, 'revision': int, 'image': str}, {}),
    'draw.thumbnail_get': ({'drawing_id': str}, {}),
    'draw.asset_info': ({'asset_id': str}, {}),
    'draw.asset_upload': ({'asset_id': str, 'index': int, 'count': int, 'data': str}, {}),
    'draw.asset_chunk': ({'asset_id': str, 'index': int}, {}),
}
# Read, paging and stroke-rate calls stay out of the bridge's non-evicting
# replay ledger: appends carry their own idempotency key (the operation id),
# and Undo/Redo are human-rate edits that would otherwise fill it.
UNLEDGERED = frozenset({'draw.status', 'draw.list', 'draw.get', 'draw.open', 'draw.since', 'draw.append',
                        'draw.undo', 'draw.redo', 'draw.rename', 'draw.trash', 'draw.restore',
                        'draw.thumbnail_put', 'draw.thumbnail_get', 'draw.asset_info', 'draw.asset_upload',
                        'draw.asset_chunk'})
STRINGS = {'drawing_id': 36, 'view': 16, 'title': 400, 'background': 16, 'image': 130_000, 'asset_id': 64,
           'data': 600_004}
MAX_INT = 2**31 - 1


def validate(method, args):
    required, optional = SPEC[method]
    if not isinstance(args, dict) or not set(required) <= set(args) or set(args) - (required.keys() | optional.keys()):
        raise ValueError('Invalid Draw arguments')
    for key, value in args.items():
        if type(value) is not (required | optional)[key]:
            raise ValueError('Invalid Draw argument type')
        if isinstance(value, str) and (len(value) > STRINGS[key] or '\x00' in value):
            raise ValueError('Draw argument exceeds supported bounds')
        if isinstance(value, int) and not 0 <= value <= MAX_INT:
            raise ValueError('Draw argument exceeds supported bounds')
    if 'drawing_id' in args and not UUID.fullmatch(args['drawing_id']):
        raise ValueError('Invalid drawing reference')
    if 'asset_id' in args and not ASSET.fullmatch(args['asset_id']):
        raise ValueError('Invalid image reference')
    if method == 'draw.list' and args.get('view', 'drawings') not in ('drawings', 'trash'):
        raise ValueError('Unknown Draw view')
    for key in ('image', 'data'):
        if key in args and not B64.fullmatch(args[key]):
            raise ValueError('Invalid Draw data')
    return args
