"""Bounded, opt-in, user-protected attach diagnostics; never renderer content."""
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time
import traceback
import uuid

current = ContextVar('request_diagnostic', default=None)


@dataclass
class RequestDiagnostic:
    request_id: str
    method: str
    stage: str = 'protocol_dispatch'
    provider_reached: bool = False
    error_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    resolution: dict = field(default_factory=dict)
    context_ids: dict = field(default_factory=dict)

    def identify(self, arguments):
        # Only opaque UUID identities, never paths, titles, prompts or content.
        for key in ('workspace_id', 'session_id', 'chat_id', 'tab_id'):
            try:
                self.context_ids[key] = str(uuid.UUID(arguments[key]))
            except (KeyError, ValueError, TypeError, AttributeError):
                pass

    def failure(self, error, directory):
        safe = dict(request_id=self.request_id, method=self.method, stage=self.stage,
                    feature=self.method.split('.')[0],
                    provider_reached=self.provider_reached, error_id=self.error_id,
                    category=type(error).__name__, diagnostic_saved=False)
        safe['context_ids'] = self.context_ids
        if self.resolution:
            safe['resolution'] = self.resolution
        if os.environ.get('OLIVE_ATTACH_DIAGNOSTICS') == '1' and os.name == 'nt':
            try:
                import win32crypt
                # No arguments, locals, observations, or window metadata. Original
                # exception/stack stay DPAPI-protected for this Windows user only.
                frames = [dict(file=Path(f.filename).name, function=f.name, line=f.lineno)
                          for f in traceback.extract_tb(error.__traceback__)]
                payload = json.dumps(dict(**safe, timestamp=time.time(),
                                          exception=str(error)[:8192], traceback=frames)).encode()
                encrypted = win32crypt.CryptProtectData(payload, 'OLIVE attach diagnostic',
                                                       None, None, None, 1)
                folder = Path(directory) / 'developer-diagnostics'
                folder.mkdir(exist_ok=True)
                if folder.is_symlink():
                    raise OSError('Diagnostic directory must be local')
                # Refuse growth rather than removing earlier evidence.
                if len(list(folder.iterdir())) >= 32:
                    raise OSError('Diagnostic limit reached')
                with (folder / (self.error_id + '.dpapi')).open('xb') as output:
                    output.write(encrypted)
                safe['diagnostic_saved'] = True
            except Exception:
                pass  # Logging failure must not replace the first operation error.
        elif os.environ.get('OLIVE_ATTACH_DIAGNOSTICS') == '1' and os.name == 'posix':
            try:
                # Linux has no DPAPI equivalent here. Persist only the same
                # content-free metadata already returned to the local UI.
                # Never downgrade Windows exception payloads to plaintext.
                folder = Path(directory) / 'developer-diagnostics'
                folder.mkdir(mode=0o700, exist_ok=True)
                directory_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    info = os.fstat(directory_fd)
                    if info.st_uid != os.getuid() or info.st_mode & 0o077:
                        raise OSError('Diagnostic directory must be private')
                    if len(os.listdir(directory_fd)) >= 32:
                        raise OSError('Diagnostic limit reached')
                    descriptor = os.open(self.error_id + '.json',
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=directory_fd)
                    with os.fdopen(descriptor, 'w') as output:
                        json.dump(dict(**safe, timestamp=time.time()), output)
                    safe['diagnostic_saved'] = True
                finally:
                    os.close(directory_fd)
            except Exception:
                pass  # Optional diagnostics never replace the operation error.
        return safe


def stage(name, *, provider=False):
    value = current.get()
    if value is not None:
        value.stage = name
        value.provider_reached |= provider
