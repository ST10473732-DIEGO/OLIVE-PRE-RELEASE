"""Requester exchanges stay on their original authenticated channel; no action resume."""
import asyncio
import time
from .contracts import ConnectError
from .inference_client import channel_for
from .studio_protocol import request, StudioRequest


async def exchange(service, device_id, operation, workspace_id=None, share_revision=0, arguments=None):
    raw = request(service.local_id, device_id, operation, workspace_id, share_revision, arguments)
    StudioRequest.decode(raw)
    try:
        channel = channel_for(service, device_id)
    except ConnectError:
        return {'result': None, 'error': 'connection_lost'}
    deadline = time.monotonic() + 120
    while True:
        try:
            result = await asyncio.to_thread(channel.studio_request, raw)
        except (ConnectError, TimeoutError):
            return {'result': None, 'error': 'connection_lost'}
        if result['error'] != 'confirmation_required' or time.monotonic() >= deadline:
            return {'result': result['result'], 'error': result['error']}
        await asyncio.sleep(1)
