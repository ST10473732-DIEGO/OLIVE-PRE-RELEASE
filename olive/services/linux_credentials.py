"""KDE/GNOME Secret Service adapter. No files, unlock prompts or fallback stores."""
from contextlib import contextmanager
from functools import partial
from ..platform_support import PlatformUnavailable

UNAVAILABLE = ('Secure credential storage is unavailable or locked. Unlock the desktop '
               'keyring and retry. No plaintext fallback was used.')


@contextmanager
def collection():
    connection = None
    try:
        import secretstorage
        connection = secretstorage.dbus_init()
        connection.send_and_get_reply = partial(connection.send_and_get_reply, timeout=5)
        receive = connection.recv_until_filtered
        connection.recv_until_filtered = lambda queue, timeout=None: receive(queue, timeout=min(timeout or 5, 5))
        # Do not create a wallet or prompt to unlock it during background work.
        value = secretstorage.Collection(connection)
        if value.is_locked():
            raise PlatformUnavailable(UNAVAILABLE)
        from secretstorage.util import open_session
        value.session = open_session(connection)
        if not value.session.encrypted:
            raise PlatformUnavailable(UNAVAILABLE)
        yield value
    except Exception:
        raise PlatformUnavailable(UNAVAILABLE) from None
    finally:
        if connection is not None:
            connection.close()


def available():
    try:
        with collection():
            return True
    except PlatformUnavailable:
        return False


def operate(action, target, secret=None):
    attributes = {'application': 'OLIVE', 'credential': target}
    with collection() as store:
        if action == 'put':
            store.create_item('OLIVE credential', attributes, secret.encode('utf-8'), replace=True)
            return
        items = list(store.search_items(attributes))
        if action == 'contains':
            if len(items) > 1 or any(item.is_locked() for item in items):
                raise PlatformUnavailable(UNAVAILABLE)
            return bool(items)
        if action == 'remove':
            for item in items:
                item.delete()
            return
        if len(items) != 1 or items[0].is_locked():
            raise PlatformUnavailable(UNAVAILABLE)
        return items[0].get_secret().decode('utf-8')
