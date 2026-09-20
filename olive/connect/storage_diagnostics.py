"""Private storage provenance with fixed labels, never SQL, paths or error text."""
from contextlib import contextmanager
import sqlite3

COMPONENTS = {'device_repository', 'permission_repository', 'studio_share_repository',
    'studio_receipt_repository', 'activity_repository', 'workspace_file', 'checkpoint',
    'file_receipt_repository', 'other'}
OPERATIONS = {'connect', 'begin_read', 'begin_write', 'read', 'write', 'commit', 'rollback',
    'authorize', 'claim', 'finish', 'audit', 'invalidate', 'other'}
SQLITE_NAMES = frozenset(name for name in vars(sqlite3) if name.startswith('SQLITE_'))


def number(value):
    return value if type(value) is int and -1 <= value <= 65535 else None


def details(error, component='other', operation='other'):
    provenance = getattr(error, '_connect_storage', ('other', 'other'))
    if provenance != ('other', 'other'):
        component, operation = provenance
    sqlite = isinstance(error, sqlite3.Error)
    os_error = isinstance(error, OSError)
    winerror = number(getattr(error, 'winerror', None)) if os_error else None
    name = getattr(error, 'sqlite_errorname', None) if sqlite else None
    classes = (sqlite3.OperationalError, sqlite3.IntegrityError, sqlite3.ProgrammingError,
        sqlite3.DatabaseError, sqlite3.Error, PermissionError, FileNotFoundError, OSError)
    cls = next((kind for kind in classes if isinstance(error, kind)), None)
    return dict(component=component if component in COMPONENTS else 'other',
        operation=operation if operation in OPERATIONS else 'other',
        namespace='sqlite' if sqlite else 'win32' if winerror is not None else 'posix' if os_error else 'application',
        exception_class=('sqlite3.' if sqlite else '') + cls.__name__ if cls else 'other',
        sqlite_errorcode=number(getattr(error, 'sqlite_errorcode', None)) if sqlite else None,
        sqlite_errorname=name if name in SQLITE_NAMES else None,
        errno=number(getattr(error, 'errno', None)) if os_error else None, winerror=winerror)


@contextmanager
def storage_operation(component, operation):
    try:
        yield
    except (sqlite3.Error, OSError) as error:
        if not hasattr(error, '_connect_storage'):
            error._connect_storage = (component if component in COMPONENTS else 'other',
                operation if operation in OPERATIONS else 'other')
        raise
