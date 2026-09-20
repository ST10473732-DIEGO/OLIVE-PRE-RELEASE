"""Bounded developer diagnostics; never serialized into Connect frames or Activity."""
import sqlite3
import threading
import uuid

from OpenSSL import SSL

from .contracts import ConnectError


class ChannelDiagnostics:
    PHASES = {'created', 'connect', 'tls', 'hello', 'authority', 'write', 'read', 'dispatch', 'retirement'}
    CATEGORIES = {'peer_eof', 'peer_close', 'local_disconnect', 'device_revoked', 'protocol_violation',
        'write_failure', 'read_failure', 'tls_failure', 'idle_timeout', 'frame_timeout', 'request_timeout',
        'retirement_replaced', 'socket_terminal', 'worker_exception', 'storage_unavailable',
        'authority_denied', 'shutdown', 'rate_limited'}

    def __init__(self):
        self._generation = uuid.uuid4().hex
        self.lock = threading.Lock()
        self.phase = 'created'
        self.terminal = None

    @property
    def generation(self):
        return self._generation

    def at(self, phase):
        with self.lock:
            self.phase = phase if phase in self.PHASES else 'created'

    def closed(self, category, error=None):
        with self.lock:
            if self.terminal is not None:
                return
            kind = ('storage' if isinstance(error, sqlite3.Error)
                    else 'tls_want_write' if isinstance(error, SSL.WantWriteError)
                    else 'tls_want_read' if isinstance(error, SSL.WantReadError)
                    else 'tls_zero_return' if isinstance(error, SSL.ZeroReturnError)
                    else 'tls_syscall' if isinstance(error, SSL.SysCallError)
                    else 'tls' if isinstance(error, SSL.Error)
                    else 'socket' if isinstance(error, OSError) else 'connect' if isinstance(error, ConnectError)
                    else 'worker' if error is not None else None)
            code = getattr(error, 'sqlite_errorcode', getattr(error, 'errno', None))
            if isinstance(error, SSL.SysCallError) and error.args:
                code = error.args[0]
            self.terminal = dict(category=category if category in self.CATEGORIES else 'worker_exception',
                phase=self.phase, error_kind=kind, error_code=code if type(code) is int and -1 <= code <= 65535 else None)

    def failed(self, error, *, peer_closed=False):
        if peer_closed:
            category = 'peer_eof'
        elif isinstance(error, sqlite3.Error):
            category = 'storage_unavailable'
        elif isinstance(error, ConnectError):
            category = {'device_not_paired': 'authority_denied', 'identity_mismatch': 'authority_denied',
                'certificate_expired_or_not_yet_valid': 'authority_denied', 'connection_collision': 'retirement_replaced',
                'rate_limited': 'rate_limited', 'connection_closed': 'worker_exception',
                'connection_timeout': 'tls_failure'}.get(str(error), 'protocol_violation')
        elif isinstance(error, SSL.Error):
            category = 'tls_failure'
        elif isinstance(error, OSError):
            category = 'write_failure' if self.phase == 'write' else 'read_failure'
        else:
            category = 'worker_exception'
        self.closed(category, error)

    def snapshot(self):
        with self.lock:
            return dict(generation=self.generation, phase=self.phase, terminal=dict(self.terminal) if self.terminal else None)
