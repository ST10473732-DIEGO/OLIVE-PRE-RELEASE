"""Narrow trusted desktop-only Connect routes, never exposed by network dispatch."""
import asyncio
from ..connect.workspace import DevicesWorkspace

SPEC = {
    'connect.file_prepare': ({'device_id': str, 'path': str}, {}),
    'connect.file_start': ({'transfer_id': str}, {}),
    'connect.file_cancel': ({'transfer_id': str}, {}),
    'connect.file_export': ({'transfer_id': str, 'path': str}, {}),
    'connect.file_dismiss': ({'transfer_id': str}, {}),
    'connect.sync_chats': ({'device_id': str}, {}),
    'connect.sync_select': ({'device_id': str, 'conversation_id': str, 'selected': bool}, {}),
    'connect.sync_now': ({'device_id': str}, {}),
    'connect.sync_cancel': ({}, {}),
    'connect.sync_conflicts': ({}, {}),
    'connect.sync_resolve': ({'conflict_id': str, 'choice': str}, {}),
    'connect.snapshot': ({}, {}),
    'connect.enable': ({'address': str, 'discovery': bool}, {}),
    'connect.disable': ({}, {}),
    'connect.rename': ({'name': str}, {}),
    'connect.permission': ({'device_id': str, 'capability': str, 'decision': str}, {}),
    'connect.revoke': ({'device_id': str}, {}),
    'connect.open': ({'device_id': str, 'address': str, 'port': int}, {}),
    'connect.disconnect': ({'device_id': str}, {}),
    'connect.ping': ({'device_id': str}, {}),
    'connect.pair_create': ({}, {}),
    'connect.pair_accept': ({'offer': str}, {}),
    'connect.pair_status': ({'session_id': str}, {}),
    'connect.pair_confirm': ({'session_id': str, 'compared_value': str}, {}),
    'connect.pair_cancel': ({'session_id': str}, {}),
}


def validate_arguments(method, args):
    """Match the preload's narrow types even for a direct private-pipe caller."""
    import ipaddress
    from ..connect.contracts import identifier, display_name, SAFE_OPERATIONS
    for key in ('device_id', 'session_id', 'transfer_id'):
        if key in args:
            identifier(args[key])
    if 'offer' in args and not 1 <= len(args['offer'].encode('utf-8')) <= 12288:
        raise ValueError('Invalid pairing code size')
    if 'name' in args:
        display_name(args['name'])
    if 'address' in args:
        if len(args['address']) > 64 or '%' in args['address']:
            raise ValueError('Invalid local address')
        ipaddress.ip_address(args['address'])
    if 'port' in args and not 1 <= args['port'] <= 65535:
        raise ValueError('Invalid Connect port')
    if method == 'connect.permission':
        if args['capability'] not in (set(SAFE_OPERATIONS) | {'sync.tasks', 'sync.calendar', 'sync.reminders', 'sync.chat', 'files.send', 'files.receive'}) or args['decision'] not in {'allow', 'ask', 'deny'}:
            raise ValueError('Unsupported Connect permission')
    if 'conversation_id' in args:
        from ..sync.records import record_id
        record_id(args['conversation_id'])
    if method == 'connect.sync_resolve':
        identifier(args['conflict_id'])
        if args['choice'] not in ('local', 'incoming'):
            raise ValueError('Invalid conflict choice')
    if 'compared_value' in args and not (1 <= len(args['compared_value']) <= 256 and args['compared_value'].isascii()):
        raise ValueError('Invalid comparison value')


async def call(host, method, args):
    service = host.services.connect
    if not hasattr(host, 'devices_workspace'):
        host.devices_workspace = DevicesWorkspace(service)
    workspace = host.devices_workspace
    def resolve_sync(conflict_id, choice):
        result = service.sync.store.resolve(conflict_id, choice)
        service.sync.store.flush()
        service.sync.changed()
        return result
    routes = {
        'connect.file_prepare': service.files.prepare,
        'connect.file_start': service.files.start,
        'connect.file_cancel': service.files.cancel,
        'connect.file_export': service.files.export,
        'connect.file_dismiss': service.files.dismiss,
        'connect.sync_chats': lambda device_id: service.sync.owned(lambda: service.sync.store.chat.selections(device_id)),
        'connect.sync_select': lambda device_id, conversation_id, selected: service.sync.owned(lambda: service.sync.store.chat.select(device_id, conversation_id, selected)),
        'connect.sync_now': service.sync.start if service.sync else None,
        'connect.sync_cancel': service.sync.cancel if service.sync else None,
        'connect.sync_conflicts': service.sync.store.conflicts if service.sync else None,
        'connect.sync_resolve': lambda conflict_id, choice: service.sync.owned(lambda: resolve_sync(conflict_id, choice)),
        'connect.snapshot': workspace.snapshot,
        'connect.enable': workspace.enable,
        'connect.disable': workspace.disable,
        'connect.rename': lambda name: service.rename(service.local_id, name),
        'connect.permission': workspace.permission,
        'connect.revoke': service.revoke,
        'connect.open': workspace.connect,
        'connect.disconnect': lambda device_id: service.network.disconnect(device_id) if service.network else None,
        'connect.ping': workspace.ping,
        'connect.pair_create': workspace.create_pairing,
        'connect.pair_accept': workspace.accept_pairing,
        'connect.pair_status': workspace.pairing_status,
        'connect.pair_confirm': workspace.confirm_pairing,
        'connect.pair_cancel': lambda session_id: service.pairing_transport.cancel(session_id),
    }
    result = await asyncio.to_thread(routes[method], **args)
    if method == 'connect.revoke':
        return {'revoked': result['trust_state'] == 'revoked'}
    return result
