"""Strict, bounded C8 messages. No paths to workspaces or commands on the wire."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import time
import uuid

from .contracts import ConnectError, canonical, identifier, timestamp, _unique_object

PROTOCOL = 'olive-studio/1'
MAX_FILE = 64_000
MAX_FRAME = 400_000  # JSON escaping of one bounded UTF-8 editor buffer
TREE_ENTRIES = 512
TREE_DEPTH = 8
OUTPUT_BYTES = 12_000
CAPABILITIES = frozenset('studio.' + name for name in ('view', 'edit', 'build', 'test', 'run', 'debug'))
OPERATIONS = {'workspaces': 'view', 'tree': 'view', 'read': 'view', 'save': 'edit',
              'build': 'build', 'test': 'test', 'run': 'run', 'run_status': None, 'run_cancel': None}
ERRORS = frozenset(('permission_denied confirmation_required workspace_unavailable workspace_not_shared '
    'file_not_found revision_conflict unsupported_file toolchain_unavailable build_failed test_failed '
    'run_failed busy cancelled connection_lost device_revoked invalid_request changed_duplicate '
    'expired_request request_indeterminate configuration_changed ledger_full').split())


def relative_path(value):
    if (type(value) is not str or not 1 <= len(value.encode('utf-8')) <= 500
            or '\\' in value or ':' in value or any(ord(c) < 32 for c in value)
            or any(p in ('', '.', '..') for p in value.split('/')) or value.startswith('/')):
        raise ConnectError('invalid_request')
    return value


def digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ConnectError('invalid_request')
    return value


@dataclass(frozen=True)
class StudioRequest:
    request_id: str
    protocol_version: str
    source_device_id: str
    target_device_id: str
    workspace_id: str | None
    share_revision: int
    operation: str
    arguments: dict
    timestamp: int
    expires_at: int

    @property
    def capability(self):
        return 'studio.' + (OPERATIONS[self.operation] or 'run')

    def fingerprint(self):
        return hashlib.sha256(canonical(asdict(self))).hexdigest()

    @classmethod
    def decode(cls, raw):
        try:
            if type(raw) is not bytes or len(raw) > MAX_FRAME:
                raise ValueError()
            v = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if type(v) is not dict or set(v) != set(cls.__dataclass_fields__):
                raise ValueError()
            for key in ('request_id', 'source_device_id', 'target_device_id'):
                identifier(v[key])
            if v['protocol_version'] != PROTOCOL or v['operation'] not in OPERATIONS:
                raise ValueError()
            op, a = v['operation'], v['arguments']
            if type(a) is not dict or type(v['share_revision']) is not int:
                raise ValueError()
            if op == 'workspaces':
                if v['workspace_id'] is not None or v['share_revision'] != 0:
                    raise ValueError()
            else:
                identifier(v['workspace_id'])
                if v['share_revision'] < 1:
                    raise ValueError()
            fields = {'read': {'path'}, 'save': {'path', 'text', 'expected_hash'},
                      'run_status': {'job_id'}, 'run_cancel': {'job_id'}}.get(op, set())
            if set(a) != fields:
                raise ValueError()
            if 'path' in a:
                relative_path(a['path'])
            if 'job_id' in a:
                identifier(a['job_id'])
            if op == 'save':
                digest(a['expected_hash'])
                if type(a['text']) is not str or '\0' in a['text'] or len(a['text'].encode('utf-8')) > MAX_FILE:
                    raise ValueError()
            timestamp(v['timestamp']); timestamp(v['expires_at'])
            if not 0 < v['expires_at'] - v['timestamp'] <= 120:
                raise ValueError()
            return cls(**v)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise ConnectError('invalid_request') from None


def request(source, target, operation, workspace_id=None, share_revision=0, arguments=None, request_id=None):
    now = int(time.time())
    return canonical(asdict(StudioRequest(request_id or str(uuid.uuid4()), PROTOCOL, source, target,
        workspace_id, share_revision, operation, arguments or {}, now, now + 120)))


def response(raw):
    try:
        if type(raw) is not bytes or len(raw) > MAX_FRAME:
            raise ValueError()
        v = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if (type(v) is not dict or set(v) != {'protocol_version', 'request_id', 'result', 'error'}
                or v['protocol_version'] != PROTOCOL):
            raise ValueError()
        identifier(v['request_id'])
        if v['error'] is not None:
            if v['error'] not in ERRORS or v['result'] is not None:
                raise ValueError()
        elif type(v['result']) is not dict:
            raise ValueError()
        return v
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        raise ConnectError('invalid_request') from None


def validate_result(req, value):
    """A paired target is still untrusted: validate every returned structure."""
    def exact(obj, keys):
        if type(obj) is not dict or set(obj) != set(keys):
            raise ConnectError('invalid_request')
    def bounded_text(text, limit):
        if type(text) is not str or len(text.encode('utf-8')) > limit or '\0' in text:
            raise ConnectError('invalid_request')
    try:
        if req.operation == 'workspaces':
            exact(value, {'workspaces'})
            if type(value['workspaces']) is not list or len(value['workspaces']) > 8:
                raise ValueError()
            seen = set()
            for item in value['workspaces']:
                exact(item, {'workspace_id', 'display_name', 'share_revision', 'permissions'})
                identifier(item['workspace_id'])
                if item['workspace_id'] in seen:
                    raise ValueError()
                seen.add(item['workspace_id'])
                bounded_text(item['display_name'], 400)
                if type(item['share_revision']) is not int or item['share_revision'] < 1:
                    raise ValueError()
                exact(item['permissions'], CAPABILITIES)
                if any(v not in ('allow', 'ask', 'deny') for v in item['permissions'].values()):
                    raise ValueError()
        elif req.operation == 'tree':
            exact(value, {'entries', 'truncated'})
            if type(value['truncated']) is not bool or type(value['entries']) is not list or len(value['entries']) > TREE_ENTRIES:
                raise ValueError()
            if len(canonical(value['entries'])) > 50000:
                raise ValueError()
            for item in value['entries']:
                exact(item, {'path', 'directory'}); relative_path(item['path'])
                if type(item['directory']) is not bool or len(item['path'].split('/')) > TREE_DEPTH:
                    raise ValueError()
        elif req.operation == 'read':
            exact(value, {'path', 'text', 'revision'}); relative_path(value['path']); digest(value['revision'])
            bounded_text(value['text'], MAX_FILE)
            if value['path'] != req.arguments['path'] or hashlib.sha256(value['text'].encode('utf-8')).hexdigest() != value['revision']:
                raise ValueError()
        elif req.operation == 'save':
            if value == {'state': 'request_indeterminate'}:
                return
            exact(value, {'state', 'revision'}); digest(value['revision'])
            if value['state'] != 'saved' or value['revision'] != hashlib.sha256(req.arguments['text'].encode('utf-8')).hexdigest():
                raise ValueError()
        else:
            allowed = {'state', 'job_id', 'error', 'exit_code', 'output', 'truncated', 'tests', 'diagnostics'}
            if type(value) is not dict or set(value) - allowed or 'state' not in value:
                raise ValueError()
            if value['state'] not in {'starting', 'running', 'completed', 'failed', 'cancelled', 'cancelling', 'request_indeterminate', 'connection_lost'}:
                raise ValueError()
            if 'job_id' in value:
                identifier(value['job_id'])
                if value['job_id'] != req.arguments.get('job_id', req.request_id):
                    raise ValueError()
            if value.get('error') is not None and value['error'] not in ERRORS:
                raise ValueError()
            if 'output' in value:
                bounded_text(value['output'], OUTPUT_BYTES)
            if 'truncated' in value and type(value['truncated']) is not bool:
                raise ValueError()
            if value.get('exit_code') is not None and type(value['exit_code']) is not int:
                raise ValueError()
            if 'diagnostics' in value:
                if type(value['diagnostics']) is not list or len(value['diagnostics']) > 32 or len(canonical(value['diagnostics'])) > 8100:
                    raise ValueError()
                for item in value['diagnostics']:
                    exact(item, {'path', 'line', 'severity', 'message'})
                    if item['path']:
                        relative_path(item['path'])
                    if type(item['line']) is not int or not 0 <= item['line'] <= 10000000 or item['severity'] not in {'warning', 'error'}:
                        raise ValueError()
                    bounded_text(item['message'], 2200)
            if 'tests' in value:
                exact(value['tests'], {'passed', 'failed', 'skipped', 'duration_seconds'})
                for key, number in value['tests'].items():
                    import math
                    if type(number) not in (int, float) or not math.isfinite(number) or number < 0 or (key != 'duration_seconds' and type(number) is not int):
                        raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ConnectError('invalid_request') from None
