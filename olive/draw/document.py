"""The OLIVE Draw document model: a replicated set of immutable records.

A drawing is a grow-only set of records. Each record has a globally unique id,
the device that made it, and a Lamport clock value. Every replica orders
records by the same key, ``(lamport, device, record_id)``, so any two replicas
holding the same set render the same picture. Wall-clock time never decides
order or conflicts; it is kept for display only (``at``).

Record kinds:

  create      {width, height, background, title, created_at}    once per drawing
  op          one drawing operation (below); body.id == record_id
  visibility  {target, hidden}   Undo/Redo: only the target's own device may emit these
  meta        {field: 'title'|'trashed', value}                 last-writer by record order

Drawing operations (document schema):

  v1  stroke      {type, id, tool:'pen', color:'#rrggbb', width, opacity, pressure, points}
      erase       {type, id, width, points}
      clear       {type, id}
      background  {type, id, value:'#ffffff'|'transparent'}
  v2  image       {type, id, asset_id, x, y, width, height, opacity}

``points`` is a flat list: x, y (document pixels) for each point, plus a
pressure value in [0, 1] when ``pressure`` is true. An image operation carries
only the SHA-256 of an OLIVE-owned asset, never bytes or a file path. A drawing
is document schema 1 until its first image operation, then schema 2; opening a
drawing never rewrites it. A reader refuses operation types it does not know.

Everything a renderer, a file or a peer hands us is untrusted data: each field
is validated and nothing in a record can name a file, URL, script or tool.
"""
import json
import math
import re
from pathlib import Path

SPEC = json.loads(Path(__file__).with_name('drawing_schema.json').read_text(encoding='utf-8'))
SCHEMA_VERSION = SPEC['schema_version']
LIMITS = SPEC['limits']
OPERATIONS_BY_SCHEMA = {int(k): frozenset(v) for k, v in SPEC['operations'].items()}
OPERATIONS = OPERATIONS_BY_SCHEMA[SCHEMA_VERSION]
RECORD_KINDS = frozenset(SPEC['record_kinds'])
META_FIELDS = frozenset(SPEC['meta_fields'])
TOOLS = frozenset(SPEC['tools'])
BACKGROUNDS = tuple(SPEC['backgrounds'])
IMAGE_TYPES = tuple(SPEC['image_types'])

OP_ID = re.compile(r'^[a-z0-9]{8,32}$')
RECORD_ID = re.compile(r'^[0-9a-f]{32}$')
ASSET_ID = re.compile(r'^[0-9a-f]{64}$')
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
COLOR = re.compile(r'^#[0-9a-f]{6}$')
AT = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$')
MAX_LAMPORT = 2 ** 53


class DrawingFormatError(ValueError):
    """An operation, record or document that this version cannot accept."""


def _number(value, low, high):
    # bool is an int subclass in Python; JSON true/false are never numbers here.
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise DrawingFormatError('invalid_number')
    return value


def _points(value, stride):
    limit = LIMITS['max_points']
    if type(value) is not list or not value or len(value) % stride or len(value) // stride > limit:
        raise DrawingFormatError('invalid_points')
    # Points may run past the page edge (a stroke that leaves the canvas); they
    # are clipped when rendered. The bound only rejects absurd coordinates.
    reach = LIMITS['max_canvas'] * 3
    for index, item in enumerate(value):
        if stride == 3 and index % 3 == 2:
            _number(item, 0, 1)
        else:
            _number(item, -reach, reach)
    return value


def validate_operation(op):
    """Return ``op`` if it is a valid operation of the current document schema."""
    if type(op) is not dict or type(op.get('type')) is not str:
        raise DrawingFormatError('invalid_operation')
    kind = op['type']
    if kind not in OPERATIONS:
        raise DrawingFormatError('unsupported_operation')
    if type(op.get('id')) is not str or not OP_ID.fullmatch(op['id']):
        raise DrawingFormatError('invalid_operation')
    keys = set(op)
    if kind == 'stroke':
        if keys != {'type', 'id', 'tool', 'color', 'width', 'opacity', 'pressure', 'points'}:
            raise DrawingFormatError('invalid_operation')
        if op['tool'] not in TOOLS or type(op['color']) is not str or not COLOR.fullmatch(op['color']):
            raise DrawingFormatError('invalid_operation')
        if type(op['pressure']) is not bool:
            raise DrawingFormatError('invalid_operation')
        _number(op['width'], LIMITS['min_width'], LIMITS['max_width'])
        _number(op['opacity'], 0.01, 1)
        _points(op['points'], 3 if op['pressure'] else 2)
    elif kind == 'erase':
        if keys != {'type', 'id', 'width', 'points'}:
            raise DrawingFormatError('invalid_operation')
        _number(op['width'], LIMITS['min_width'], LIMITS['max_width'])
        _points(op['points'], 2)
    elif kind == 'clear':
        if keys != {'type', 'id'}:
            raise DrawingFormatError('invalid_operation')
    elif kind == 'background':
        if keys != {'type', 'id', 'value'} or op['value'] not in BACKGROUNDS:
            raise DrawingFormatError('invalid_operation')
    elif kind == 'image':
        if keys != {'type', 'id', 'asset_id', 'x', 'y', 'width', 'height', 'opacity'}:
            raise DrawingFormatError('invalid_operation')
        if type(op['asset_id']) is not str or not ASSET_ID.fullmatch(op['asset_id']):
            raise DrawingFormatError('invalid_operation')
        reach = LIMITS['max_canvas'] * 3
        _number(op['x'], -reach, reach)
        _number(op['y'], -reach, reach)
        _number(op['width'], 1, reach)
        _number(op['height'], 1, reach)
        _number(op['opacity'], 0.01, 1)
    return op


def operation_schema(op):
    """The lowest document schema that contains this operation type."""
    return min(version for version, kinds in OPERATIONS_BY_SCHEMA.items() if op['type'] in kinds)


def _dumps(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=True, allow_nan=False, sort_keys=True)


def encode_operation(op):
    """Canonical compact JSON for one validated operation."""
    data = _dumps(validate_operation(op))
    if len(data) > LIMITS['max_operation_bytes']:
        raise DrawingFormatError('operation_too_large')
    return data


def _reject_constant(name):
    raise DrawingFormatError('invalid_number')


def _loads(data, limit):
    if type(data) is not str or len(data) > limit:
        raise DrawingFormatError('invalid_operation')
    try:
        return json.loads(data, parse_constant=_reject_constant)
    except ValueError as failure:
        raise DrawingFormatError('invalid_operation') from failure


def decode_operation(data):
    """Parse and re-validate a stored operation (stored data is untrusted too)."""
    return validate_operation(_loads(data, LIMITS['max_operation_bytes']))


def validate_canvas(width, height):
    if type(width) is not int or type(height) is not int:
        raise DrawingFormatError('invalid_canvas')
    low, high = LIMITS['min_canvas'], LIMITS['max_canvas']
    if not (low <= width <= high and low <= height <= high) or width * height > LIMITS['max_canvas_pixels']:
        raise DrawingFormatError('canvas_too_large')
    return width, height


def validate_background(value):
    if value not in BACKGROUNDS:
        raise DrawingFormatError('invalid_background')
    return value


def clean_title(value):
    """Titles are plain text: control characters dropped, whitespace collapsed."""
    if type(value) is not str:
        raise DrawingFormatError('invalid_title')
    text = ''.join(c if c.isprintable() else ' ' for c in value)
    text = ' '.join(text.split())
    return text[:LIMITS['max_title_chars']]


# --- replicated records ------------------------------------------------------------
RECORD_FIELDS = {'record_id', 'drawing_id', 'device', 'lamport', 'kind', 'at', 'body'}


def order_key(record):
    """The one total order every replica uses. Never wall-clock time."""
    return (record['lamport'], record['device'], record['record_id'])


def validate_record(record):
    """Strictly validate one replicated record (from a renderer, the store or a peer)."""
    if type(record) is not dict or set(record) != RECORD_FIELDS:
        raise DrawingFormatError('invalid_record')
    if type(record['record_id']) is not str or not RECORD_ID.fullmatch(record['record_id']):
        raise DrawingFormatError('invalid_record')
    for key in ('drawing_id', 'device'):
        if type(record[key]) is not str or not UUID.fullmatch(record[key]):
            raise DrawingFormatError('invalid_record')
    if type(record['lamport']) is not int or not 1 <= record['lamport'] <= MAX_LAMPORT:
        raise DrawingFormatError('invalid_record')
    if type(record['at']) is not str or not AT.fullmatch(record['at']):
        raise DrawingFormatError('invalid_record')
    kind, body = record['kind'], record['body']
    if kind not in RECORD_KINDS or type(body) is not dict:
        raise DrawingFormatError('invalid_record')
    if kind == 'create':
        if set(body) != {'width', 'height', 'background', 'title', 'created_at'}:
            raise DrawingFormatError('invalid_record')
        validate_canvas(body['width'], body['height'])
        validate_background(body['background'])
        if type(body['title']) is not str or clean_title(body['title']) != body['title']:
            raise DrawingFormatError('invalid_title')
        if type(body['created_at']) is not str or not AT.fullmatch(body['created_at']):
            raise DrawingFormatError('invalid_record')
    elif kind == 'op':
        validate_operation(body)
        if body['id'] != record['record_id']:
            raise DrawingFormatError('invalid_record')
    elif kind == 'visibility':
        if set(body) != {'target', 'hidden'} or type(body['hidden']) is not bool:
            raise DrawingFormatError('invalid_record')
        if type(body['target']) is not str or not RECORD_ID.fullmatch(body['target']):
            raise DrawingFormatError('invalid_record')
    elif kind == 'meta':
        if set(body) != {'field', 'value'} or body['field'] not in META_FIELDS:
            raise DrawingFormatError('invalid_record')
        if body['field'] == 'title' and (type(body['value']) is not str or clean_title(body['value']) != body['value']):
            raise DrawingFormatError('invalid_title')
        if body['field'] == 'trashed' and type(body['value']) is not bool:
            raise DrawingFormatError('invalid_record')
    return record


def encode_record(record):
    data = _dumps(validate_record(record))
    if len(data) > LIMITS['max_operation_bytes'] + 1024:
        raise DrawingFormatError('operation_too_large')
    return data


def decode_record(data):
    return validate_record(_loads(data, LIMITS['max_operation_bytes'] + 1024))
