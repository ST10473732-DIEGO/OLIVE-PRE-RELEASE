"""Request-scoped consent for routine operations, never a persistent permission.

Only the actual user front door opens this context. Model output cannot set it.
The semantic capability narrows an allowlist; all DENY rules remain authoritative.
Consequential actions and unclassified desktop input are deliberately excluded.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps

_user = ContextVar('olive_actual_user_request', default=False)
_intent = ContextVar('olive_requested_capability', default='')

READ_TOOLS = {
    "now.answer": {"web.search", "web.open", "web.weather"},
    'filesystem.search': {'filesystem.search', 'filesystem.stat', 'knowledge.find_files'},
    'knowledge.query': {'filesystem.read_text', 'filesystem.stat'},
    'code.inspect': {'filesystem.read_text', 'filesystem.stat', 'studio.open', 'studio.tree'},
}
GATEWAY_PERMISSIONS = {
    'application.launch': {'system.open_application', 'desktop.inspect_application'},
    'application.activate': {'system.open_application', 'desktop.inspect_application'},
    'application.navigate': {'system.open_application', 'desktop.inspect_application', 'app.windows_settings.navigate', 'app.file_explorer.navigate', 'filesystem.read'},
    'media.play': {'desktop.inspect_application', 'application.media'},
    'media.pause': {'desktop.inspect_application', 'application.media'},
    'media.next': {'desktop.inspect_application', 'application.media'},
    'media.previous': {'desktop.inspect_application', 'application.media'},
}


def actual_user_request(function):
    @wraps(function)
    async def invoke(*args, **kwargs):
        token = _user.set(True)
        try:
            return await function(*args, **kwargs)
        finally:
            _user.reset(token)
    return invoke


@contextmanager
def requested_capability(intent):
    token = _intent.set(intent if _user.get() else '')
    try:
        yield
    finally:
        _intent.reset(token)


def requested_tool(tool):
    return _user.get() and tool in READ_TOOLS.get(_intent.get(), set())


def requested_gateway_permission(permission):
    return _user.get() and permission in GATEWAY_PERMISSIONS.get(_intent.get(), set())
