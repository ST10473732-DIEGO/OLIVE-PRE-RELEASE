"""Narrow trusted desktop-only Connect routes, never exposed by network dispatch."""
import asyncio
from ..connect.workspace import DevicesWorkspace

SPEC = {
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
    for key in ('device_id', 'session_id'):
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
        if args['capability'] not in SAFE_OPERATIONS or args['decision'] not in {'allow', 'ask', 'deny'}:
            raise ValueError('Unsupported Connect permission')
    if 'compared_value' in args and not (1 <= len(args['compared_value']) <= 256 and args['compared_value'].isascii()):
        raise ValueError('Invalid comparison value')


async def call(host, method, args):
    service = host.services.connect
    if not hasattr(host, 'devices_workspace'):
        host.devices_workspace = DevicesWorkspace(service)
    workspace = host.devices_workspace
    routes = {
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
