"""Strict allowlisted wire contracts. No model prose or arbitrary attributes execute."""
import json
import re
from .m2_contracts import SPEC, MAIN_ONLY
from .m2_validation import validate_arguments
from .connect_routes import SPEC as CONNECT_SPEC
from ..personal.contracts import SPEC as PERSONAL_SPEC, MAIN_ONLY as PERSONAL_MAIN, validate as validate_personal
from ..mail.contracts import SPEC as MAIL_SPEC, MAIN_ONLY as MAIL_MAIN, validate as validate_mail
from ..studio_tooling.contracts import SPEC as TOOLING_SPEC, validate as validate_tooling
from ..notes.contracts import SPEC as NOTES_SPEC, MAIN_ONLY as NOTES_MAIN, validate as validate_notes
from ..draw.contracts import SPEC as DRAW_SPEC, validate as validate_draw

VERSION = 1
MAX_FRAME = 1_048_576
ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')

# Required fields and optional fields. Strings are bounded below, booleans exact.
METHODS = {
    'runtime.snapshot': ({}, {}),
    'media.status': ({}, {}),
    'media.import': ({'path':str}, {}),
    'media.configure': ({'url':str}, {}),
    'media.disconnect': ({}, {}),
    'media.start': ({'request':dict}, {}),
    'media.cancel': ({'job_id':str}, {}),
    'media.preview': ({'artifact_id':str}, {}),
    'media.export': ({'artifact_id':str,'path':str}, {}),
    'media.artifact_file': ({'artifact_id':str}, {}),  # Electron main only (inline playback/open).
    'media.reuse': ({'chat_id':str,'artifact_id':str}, {}),
    'media.engines': ({}, {}),
    'media.voices': ({}, {}),
    'media.select_voice': ({'voice':str}, {}),
    'media.video_plan': ({'text':str}, {'duration':(int, float),'images':int}),
    'connections.discord_status': ({}, {}),
    'connections.discord_destinations': ({}, {'guild_id':str}),
    'connections.discord_select': ({'guild_id':str,'channel_id':str}, {}),
    'connections.discord_configure': ({'token':str,'guild_id':str,'channel_id':str}, {}),
    'connections.discord_disconnect': ({'remove_credentials':bool}, {}),
    'runtime.shutdown': ({}, {}),
    'desktop.stop': ({}, {}),
    'chat.new': ({}, {}),
    'chat.get': ({'chat_id': str}, {}),
    'chat.select': ({'chat_id': str}, {}),
    'chat.warm': ({'chat_id': str}, {}),
    'chat.draft': ({'chat_id': str, 'text': str}, {}),
    'chat.rename': ({'chat_id': str, 'title': str}, {}),
    'chat.model': ({'chat_id': str, 'model': str}, {}),
    'chat.preset': ({'chat_id': str, 'preset': str}, {}),
    'chat.run_on': ({'chat_id': str, 'device_id': str}, {}),
    'chat.regenerate': ({'chat_id': str}, {}),
    'chat.branch': ({'chat_id': str, 'user_index': int, 'direction': int}, {}),
    'interaction.submit': ({'chat_id': str, 'text': str}, {'research_mode': str, 'workspace_id': str,
                           'video_duration_seconds': (int, float)}),
    'interaction.cancel': ({'chat_id': str}, {}),
    'context.clear': ({'chat_id': str}, {}),
    'workspace.open': ({'path': str}, {}),
    'studio.create_project': ({'name': str, 'language': str}, {}),
    'studio.install_package': ({'workspace_id': str, 'manager': str, 'package': str}, {}),
    'studio.cancel_install': ({'workspace_id': str}, {}),
    'studio.tree': ({'workspace_id': str}, {}),
    'studio.open': ({'workspace_id': str, 'path': str}, {}),
    'studio.create': ({'workspace_id': str, 'path': str}, {}),
    'studio.compare': ({'workspace_id': str, 'path': str}, {}),
    'studio.rebase': ({'workspace_id': str, 'path': str, 'expected_hash': str, 'disk_hash': str}, {}),
    'studio.save': ({'workspace_id': str, 'path': str, 'text': str, 'expected_hash': str}, {}),
    'studio.buffer': ({'workspace_id': str, 'path': str, 'text': str, 'expected_hash': str}, {}),
    'studio.run': ({'workspace_id': str}, {}),
    'studio.restart': ({'workspace_id': str}, {'session_id': str}),
    'studio.validate': ({'workspace_id': str}, {'review': bool}),
    'studio.cancel_validation': ({'validation_id': str}, {}),
    'studio.stop': ({'session_id': str}, {}),
    'studio.input': ({'workspace_id': str, 'session_id': str, 'text': str, 'eof': bool}, {}),
    'studio.diff': ({'workspace_id': str}, {}),
    'studio.ask': ({'workspace_id': str, 'request': str}, {'path': str, 'selection': str}),
    'approval.respond': ({'approval_id': str, 'fingerprint': str, 'approved': bool}, {}),
}


METHODS.update(CONNECT_SPEC)

def validate(value):
    if not isinstance(value, dict) or set(value) != {'v', 'id', 'method', 'args'}:
        raise ValueError('Invalid request envelope')
    if type(value['v']) is not int or value['v'] != VERSION:
        raise ValueError('Unsupported protocol version')
    if not isinstance(value['id'], str) or not ID.fullmatch(value['id']):
        raise ValueError('Invalid request identity')
    if isinstance(value['method'], str) and (value['method'] in NOTES_SPEC or value['method'] in NOTES_MAIN):
        validate_notes(value['method'], value['args'])
        return value
    if isinstance(value['method'], str) and value['method'] in DRAW_SPEC:
        validate_draw(value['method'], value['args'])
        return value
    if not isinstance(value['method'], str) or value['method'] not in METHODS and value['method'] not in SPEC and value['method'] not in MAIN_ONLY and value['method'] not in PERSONAL_SPEC and value['method'] not in PERSONAL_MAIN and value['method'] not in MAIL_SPEC and value['method'] not in MAIL_MAIN and value['method'] not in TOOLING_SPEC:
        raise ValueError('Unsupported method')
    args = value['args']
    if value['method'] in TOOLING_SPEC:
        validate_tooling(value['method'], args)
        return value
    if value['method'] in MAIL_SPEC or value['method'] in MAIL_MAIN:
        validate_mail(value['method'],args)
        return value
    if value['method'] in PERSONAL_SPEC or value['method'] in PERSONAL_MAIN:
        validate_personal(value['method'], args)
        return value
    if value['method'] in SPEC or value['method'] in MAIN_ONLY:
        validate_arguments(value['method'], args)
        return value
    required, optional = METHODS[value['method']]
    if not isinstance(args, dict) or not set(required) <= set(args) or set(args) - (required.keys() | optional.keys()):
        raise ValueError('Invalid arguments')
    for key, item in args.items():
        expected = (required | optional)[key]
        if type(item) not in (expected if isinstance(expected, tuple) else (expected,)):
            raise ValueError('Invalid argument type')
        if type(item) is float and not (item == item and abs(item) != float('inf')):
            raise ValueError('Invalid argument type')
        limit = 400_000 if key == 'text' and value['method'].startswith('studio.') else 32_000 if key in ('text','request','selection') else 4096
        if isinstance(item, str) and (len(item) > limit or '\x00' in item):
            raise ValueError('Argument exceeds supported bounds')
    if value['method'] in CONNECT_SPEC:
        from .connect_routes import validate_arguments as validate_connect
        validate_connect(value['method'], args)
    return value


def decode(raw):
    if len(raw) > MAX_FRAME:
        raise ValueError('Frame exceeds supported size')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return validate(json.loads(raw, object_pairs_hook=pairs))
