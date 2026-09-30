"""Remote Chat v2 (``olive-chat/1``): every OLIVE Chat mode for a paired phone.

Frames 17/18 carry one packet each: a 4-byte big-endian JSON length, strict
canonical JSON, then an optional raw binary tail (attachment or artifact bytes).
The layout is the olive-files/1 packet generalised; nothing is base64-encoded.

The protocol grants content operations only (inference, research, document
reading, media generation). It has no tool, file-path, desktop-control or
permission vocabulary. A desktop advertises it in the ``protocols`` probe; a
phone never sends frame 17 to a desktop that did not list it.
"""
import hashlib
import json
import re
import struct
import unicodedata

from .contracts import ConnectError, canonical, identifier, timestamp, _unique_object

PROTOCOL = 'olive-chat/1'
CAPABILITY = 'models.remote'
MODES = ('fast', 'normal', 'max', 'uncensored', 'now', 'deep', 'reimagine', 'audio', 'video')
TEXT_MODES = ('fast', 'normal', 'max', 'uncensored')
MEDIA_MODES = {'reimagine': 'image', 'audio': 'audio', 'video': 'video'}
ATTACHMENT_KINDS = ('image', 'document', 'note')
SOURCE_KINDS = ('photo', 'camera', 'file', 'note', 'draw')

MAX_JSON = 96_000
CHUNK_BYTES = 128 * 1024
MAX_FRAME = 4 + MAX_JSON + CHUNK_BYTES
MAX_SECONDS = 120
MAX_MESSAGES = 24
MAX_MESSAGE = 16_000
MAX_INPUT = 48_000
MAX_OUTPUT = 64_000
MAX_TEXT_DELTA = 16_000
MAX_ATTACHMENTS = 4
MAX_SOURCES = 12
MAX_ARTIFACTS = 4
# Per-kind staged size limits. Images match desktop Chat attachment limits.
MAX_BYTES = {'image': 20 * 1024 * 1024, 'document': 32 * 1024 * 1024, 'note': 192 * 1024}
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MIMES = {
    'image': ('image/png', 'image/jpeg'),
    'document': ('application/pdf', 'text/plain', 'text/markdown', 'text/x-source',
                 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    'note': ('text/markdown',),
}

STATES = ('not_received', 'awaiting_approval', 'queued', 'running', 'completed', 'cancelled', 'failed', 'outcome_unknown')
TERMINAL = frozenset({'completed', 'cancelled', 'failed', 'outcome_unknown'})
# Factual progress the desktop actually observes; never a percentage.
PHASES = ('', 'approval', 'queued', 'thinking', 'retrieving', 'reading_documents', 'indexing', 'synthesizing',
          'releasing_gpu', 'preparing_image_engine', 'generating_image', 'preparing_audio_engine',
          'generating_speech', 'preparing_video_engine', 'generating_video', 'saving')
ERRORS = frozenset({
    'permission_denied', 'confirmation_required', 'device_revoked', 'device_unavailable', 'invalid_request',
    'expired_request', 'rate_limited', 'busy', 'ledger_full', 'changed_duplicate', 'unknown_request',
    'mode_unavailable', 'input_too_large', 'output_limit', 'inference_failed', 'generation_timeout', 'cancelled',
    'request_indeterminate', 'storage_full', 'computer_stopped',
    'unsupported_attachment', 'attachment_too_large', 'attachment_missing', 'attachment_corrupt',
    'too_many_attachments', 'artifact_unavailable',
    'document_unreadable', 'indexing_failed', 'vision_unavailable',
    # OLIVE NOW (desktop NowError codes).
    'synthesis_invalid', 'model_unavailable', 'local_required', 'search_unavailable', 'weather_unavailable',
    'no_fresh_evidence', 'page_failed', 'place_required', 'private_context', 'question_limit', 'weather_period',
    # OLIVE media (desktop MediaError codes).
    'image_not_configured', 'audio_not_configured', 'video_not_configured', 'audio_model_missing', 'audio_exposed',
    'audio_unverified', 'engine_start_failed', 'engine_unreachable', 'engine_busy', 'engine_incompatible',
    'workflow_missing', 'model_missing', 'attachment_unsupported_mode', 'too_many_references', 'no_artifact',
    'gpu_release_unverified', 'gpu_busy', 'generation_failed', 'timeout', 'prompt_required', 'prompt_too_long',
    'audio_unsupported', 'speech_text_required', 'speech_too_long',
})
_HEX64 = re.compile('[0-9a-f]{64}')
_HEX32 = re.compile('[0-9a-f]{32}')
_LABEL = re.compile(r'[A-Z0-9 ·.+-]{0,40}')


def _int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ConnectError('invalid_request')
    return value


def _text(value, low, high):
    if type(value) is not str or not low <= len(value.encode('utf-8')) <= high or '\0' in value:
        raise ConnectError('invalid_request')
    return value


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def display_name(value):
    """Display metadata only. Never a storage path; ambiguous names are rejected."""
    if (type(value) is not str or not value or len(value.encode('utf-8')) > 180 or value != value.strip()
            or any(c in '/\\:<>"|?*' or unicodedata.category(c).startswith('C') for c in value)
            or value in ('.', '..')):
        raise ConnectError('invalid_request')
    return value


def packet(value, binary=b''):
    raw = canonical(value)
    if len(raw) > MAX_JSON or len(binary) > CHUNK_BYTES:
        raise ConnectError('input_too_large')
    return struct.pack('!I', len(raw)) + raw + binary


def unpack(raw):
    if type(raw) is not bytes or not 4 <= len(raw) <= MAX_FRAME:
        raise ConnectError('invalid_request')
    size = struct.unpack('!I', raw[:4])[0]
    if not 2 <= size <= MAX_JSON or 4 + size > len(raw):
        raise ConnectError('invalid_request')
    try:
        value = json.loads(raw[4:4 + size].decode('utf-8'), object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ConnectError('invalid_request') from None
    return value, raw[4 + size:]


def messages_size(messages):
    if type(messages) is not list or not 1 <= len(messages) <= MAX_MESSAGES:
        raise ConnectError('input_too_large')
    total = 0
    for item in messages:
        if (type(item) is not dict or set(item) != {'role', 'content'} or item['role'] not in ('user', 'assistant')
                or type(item['content']) is not str or '\0' in item['content']):
            raise ConnectError('invalid_request')
        size = len(item['content'].encode('utf-8'))
        if not item['content'].strip():
            raise ConnectError('prompt_required')
        if size > MAX_MESSAGE:
            raise ConnectError('input_too_large')
        total += size
    if total > MAX_INPUT:
        raise ConnectError('input_too_large')
    if messages[-1]['role'] != 'user':
        raise ConnectError('invalid_request')
    return total


def attachment_ref(value):
    """Strict descriptor for a staged attachment. The id is the content address."""
    if type(value) is not dict or set(value) != {'attachment_id', 'kind', 'mime', 'size', 'name'}:
        raise ConnectError('invalid_request')
    if type(value['attachment_id']) is not str or not _HEX64.fullmatch(value['attachment_id']):
        raise ConnectError('invalid_request')
    if value['kind'] not in ATTACHMENT_KINDS or value['mime'] not in MIMES[value['kind']]:
        raise ConnectError('unsupported_attachment')
    if type(value['size']) is not int or not 1 <= value['size']:
        raise ConnectError('invalid_request')
    if value['size'] > MAX_BYTES[value['kind']]:
        raise ConnectError('attachment_too_large')
    display_name(value['name'])
    return value


REQUEST_KEYS = {'protocol_version', 'request_id', 'source_device_id', 'target_device_id', 'operation',
                'arguments', 'timestamp', 'expires_at'}
ARGUMENTS = {
    'capabilities': set(),
    'attachment_offer': {'attachment_id', 'kind', 'mime', 'size', 'name'},
    'attachment_chunk': {'attachment_id', 'offset'},
    'start': {'job_id', 'conversation_id', 'mode', 'voice', 'messages', 'attachments', 'input_fingerprint'},
    'poll': {'job_id', 'after'},
    'cancel': {'job_id'},
    'artifact_chunk': {'artifact_id', 'offset', 'length'},
}


def start_fingerprint(arguments):
    """Stable identity of a start: resending the same request is idempotent."""
    return digest({k: arguments[k] for k in ('conversation_id', 'mode', 'voice', 'messages', 'attachments')})


class ChatRequest:
    __slots__ = ('request_id', 'protocol_version', 'source_device_id', 'target_device_id', 'operation',
                 'arguments', 'timestamp', 'expires_at', 'binary')
    capability = CAPABILITY

    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)

    @classmethod
    def decode(cls, raw):
        value, binary = unpack(raw)
        if type(value) is not dict or set(value) != REQUEST_KEYS or value['protocol_version'] != PROTOCOL:
            raise ConnectError('invalid_request')
        for key in ('request_id', 'source_device_id', 'target_device_id'):
            identifier(value[key])
        timestamp(value['timestamp']); timestamp(value['expires_at'])
        _int(value['expires_at'] - value['timestamp'], 1, MAX_SECONDS)
        operation, a = value['operation'], value['arguments']
        if operation not in ARGUMENTS or type(a) is not dict or set(a) != ARGUMENTS[operation]:
            raise ConnectError('invalid_request')
        if binary and operation != 'attachment_chunk':
            raise ConnectError('invalid_request')
        if operation == 'attachment_offer':
            attachment_ref({**a})
        elif operation == 'attachment_chunk':
            if type(a['attachment_id']) is not str or not _HEX64.fullmatch(a['attachment_id']):
                raise ConnectError('invalid_request')
            _int(a['offset'], 0, max(MAX_BYTES.values()))
            if not 1 <= len(binary) <= CHUNK_BYTES:
                raise ConnectError('invalid_request')
        elif operation == 'start':
            identifier(a['job_id']); identifier(a['conversation_id'])
            if value['request_id'] != a['job_id']:
                raise ConnectError('invalid_request')
            if a['mode'] not in MODES:
                raise ConnectError('mode_unavailable')
            if a['voice'] is not None:
                _text(a['voice'], 1, 120)
            messages_size(a['messages'])
            if type(a['attachments']) is not list or len(a['attachments']) > MAX_ATTACHMENTS:
                raise ConnectError('too_many_attachments')
            seen = set()
            total = 0
            for item in a['attachments']:
                attachment_ref(item)
                if item['attachment_id'] in seen:
                    raise ConnectError('invalid_request')
                seen.add(item['attachment_id'])
                total += item['size']
            if total > MAX_REQUEST_BYTES:
                raise ConnectError('attachment_too_large')
            if a['input_fingerprint'] != start_fingerprint(a):
                raise ConnectError('invalid_request')
        elif operation in ('poll', 'cancel'):
            identifier(a['job_id'])
            if operation == 'poll':
                _int(a['after'], 0, MAX_OUTPUT)
        elif operation == 'artifact_chunk':
            if type(a['artifact_id']) is not str or not _HEX32.fullmatch(a['artifact_id']):
                raise ConnectError('invalid_request')
            _int(a['offset'], 0, 2 ** 40)
            _int(a['length'], 1, CHUNK_BYTES)
        return cls(**value, binary=binary)

    def fingerprint(self):
        """Approval binding: the exact content of this start (never timestamps)."""
        return self.arguments.get('input_fingerprint') or digest(self.arguments)


def request(source, target, operation, arguments, *, now, request_id=None, binary=b''):
    """Build a strict request (used by tests and the Swift interop harness)."""
    import uuid
    rid = request_id or (arguments['job_id'] if operation == 'start' else str(uuid.uuid4()))
    raw = packet(dict(protocol_version=PROTOCOL, request_id=rid, source_device_id=source, target_device_id=target,
                      operation=operation, arguments=arguments, timestamp=now, expires_at=now + MAX_SECONDS), binary)
    ChatRequest.decode(raw)
    return raw


def response(request_id, *, result=None, error=None, binary=b''):
    if error is not None and error not in ERRORS:
        error = 'invalid_request'
    return packet(dict(protocol_version=PROTOCOL, request_id=request_id,
                       result=None if error else result, error=error), binary if not error else b'')


# ---------------------------------------------------------------- result shapes

def source_item(source):
    """Structured evidence for the phone: titles, providers, links and dates only.

    Desktop evidence ids ([S1]/[D1]) are preserved so citations in the answer
    resolve. Private document excerpts are bounded; no desktop paths escape.
    """
    kind = source.get('kind', '')
    web = kind in ('page_excerpt', 'search_snippet', 'current_snapshot', 'structured_weather')
    url = source.get('url') if web else None
    if not (type(url) is str and re.fullmatch(r'https?://[^\s\0]{1,2000}', url)):
        url = None
    def text(key, limit):
        value = source.get(key)
        return value[:limit] if type(value) is str and value else None
    page = source.get('page_number')
    return {
        'id': text('id', 8) or '',
        'kind': 'weather' if kind == 'structured_weather' else 'web' if web else 'note' if kind == 'note' else 'document',
        'title': text('title', 300) or text('source', 300) or 'Source',
        'provider': text('source', 200) if web else text('filename', 200) or text('source', 200),
        'url': url,
        'published_at': text('published_at', 40),
        'updated_at': text('updated_at', 40),
        'retrieved_at': text('retrieved_at', 40),
        'page': page if type(page) is int and 0 < page < 1_000_000 else None,
        'snapshot': kind == 'current_snapshot',
        'excerpt': (text('evidence', 400) if not web else None),
    }


def artifact_item(artifact, mode):
    """Chat artifact descriptor from MediaService, without filesystem paths."""
    kind = artifact.get('kind')
    mime = {'image': 'image/png', 'audio': 'audio/wav', 'video': 'video/mp4'}.get(kind)
    if mime is None or artifact.get('mime_type') != mime or not _HEX32.fullmatch(str(artifact.get('id', ''))):
        raise ConnectError('artifact_unavailable')
    if not _HEX64.fullmatch(str(artifact.get('sha256', ''))) or type(artifact.get('size_bytes')) is not int:
        raise ConnectError('artifact_unavailable')
    def dimension(key):
        value = artifact.get(key)
        return value if type(value) is int and 0 < value <= 16384 else None
    seconds = artifact.get('duration_seconds')
    duration = int(round(seconds * 1000)) if type(seconds) in (int, float) and 0 < seconds < 86400 else None
    family = artifact.get('generator', {}).get('family', '') if type(artifact.get('generator')) is dict else ''
    label = family if type(family) is str and re.fullmatch(r'[A-Za-z0-9 .+-]{1,40}', family or '') else ''
    return {'artifact_id': artifact['id'], 'kind': kind, 'mime': mime, 'size': artifact['size_bytes'],
            'sha256': artifact['sha256'], 'width': dimension('width'), 'height': dimension('height'),
            'duration_ms': duration, 'has_audio': artifact.get('has_audio') if type(artifact.get('has_audio')) is bool else None,
            'completion_state': 'complete', 'mode': mode, 'label': label}


def attribution(mode, tier=''):
    tier = tier if type(tier) is str and _LABEL.fullmatch(tier) else ''
    name = mode.upper()
    return {'mode': mode, 'tier': tier, 'label': name + (' · ' + tier if tier else '')}
