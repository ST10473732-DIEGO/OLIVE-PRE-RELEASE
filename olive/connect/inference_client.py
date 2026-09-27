"""Explicit requester; an unavailable chosen peer never invokes a local model."""
import asyncio
import time

from .contracts import ConnectError, identifier
from .inference_protocol import MAX_MESSAGES, PRESETS, TERMINAL, digest, input_size, request

MESSAGES = {
    'permission_denied': 'Remote AI is Off or this request was denied on the selected device.',
    'device_revoked': 'The selected device is revoked.',
    'device_unavailable': 'The selected device is offline or Connect is Off.',
    'model_unavailable': 'This preset is unavailable on the selected device. Remote DEEP and REIMAGINE are unavailable.',
    'busy': 'The selected device is busy. Try again later.',
    'rate_limited': 'Remote AI request limit reached. Try again later.',
    'input_too_large': 'Remote AI context exceeds its text limit. Start a shorter conversation.',
    'output_limit': 'Remote AI reached its output limit. The partial answer is incomplete.',
    'generation_timeout': 'Remote generation timed out. The partial answer is incomplete.',
    'cancelled': 'Remote generation stopped. The partial answer is incomplete.',
    'connection_lost': 'Connection lost. Remote generation stopped; the partial answer is incomplete.',
}


def channel_for(service, peer):
    identifier(peer)
    record = service.device(peer)
    if record['trust_state'] != 'paired':
        raise ConnectError('device_revoked')
    network = service.network
    if network is None:
        raise ConnectError('device_unavailable')
    with network.lock:
        channel = network.channels.get(peer)
    if channel is None or channel.stop.is_set():
        raise ConnectError('device_unavailable')
    return channel


class RemoteInferenceClient:
    def __init__(self, service):
        self.service = service

    def make(self, peer, operation, **kwargs):
        return request(self.service.local_id, peer, operation, now=int(self.service.clock()), **kwargs)

    async def exchange(self, channel, req):
        try:
            value = await asyncio.to_thread(channel.inference_request, req.encode())
        except ConnectError as error:
            if str(error) in ('busy', 'rate_limited'):
                raise
            raise ConnectError('connection_lost') from None
        if value['error']:
            raise ConnectError(value['error'])
        return value['result']

    async def targets(self):
        result = []
        for record in self.service.listed_devices()[:256]:
            value = dict(device_id=record['device_id'], display_name=record['display_name'],
                         state='offline', permission='deny', busy=False, presets={p: False for p in PRESETS})
            try:
                channel = channel_for(self.service, record['device_id'])
                status = await self.exchange(channel, self.make(record['device_id'], 'status'))
                value.update(status, state='online')
            except ConnectError as error:
                value['state'] = 'revoked' if str(error) == 'device_revoked' else 'offline'
            result.append(value)
        return result

    def prepare(self, peer, preset, messages):
        channel = channel_for(self.service, peer)
        if preset not in PRESETS:
            raise ConnectError('model_unavailable')
        # Only visible turns. Hidden summaries, product prompts and attachments
        # cannot enter this contract. Old history outside the window is omitted.
        messages = [dict(role=m.role, content=m.content) for m in messages
                    if m.role in ('user', 'assistant') and m.completion_state == 'complete'][-MAX_MESSAGES:]
        input_size(messages)
        req = self.make(peer, 'start', arguments=dict(preset=preset, messages=messages,
            input_fingerprint=digest(messages), max_tokens=2048, max_output_bytes=64000, seconds=120))
        provider = dict(runtime='OLIVE Connect', preset=preset, device_id=peer,
                        device_name=self.service.device(peer)['display_name'], request_id=req.job_id)
        return self.stream(channel, req), provider

    async def stream(self, channel, req):
        sequence, total, done = 0, 0, False
        deadline = time.monotonic() + 155  # approval/queue also bounded by immutable request expiry
        try:
            while True:
                if time.monotonic() >= deadline:
                    raise ConnectError('generation_timeout')
                result = await self.exchange(channel, req)
                if result['state'] != 'awaiting_approval':
                    break
                await asyncio.sleep(.25)
            # A repeated terminal start returns status only and never reruns.
            if result['state'] in TERMINAL:
                raise ConnectError(result['error'] or 'request_indeterminate')
            deadline = time.monotonic() + 155
            while True:
                if time.monotonic() >= deadline:
                    raise ConnectError('generation_timeout')
                result = await self.exchange(channel, self.make(channel.peer, 'poll',
                    job_id=req.job_id, arguments={'after': sequence}))
                for event in result['events']:
                    if event['sequence'] != sequence + 1:
                        raise ConnectError('stream_invalid')
                    sequence += 1
                    total += len(event['text'].encode('utf-8'))
                    if total > req.arguments['max_output_bytes']:
                        raise ConnectError('output_limit')
                    yield event['text']
                if result['state'] in TERMINAL:
                    if result['state'] != 'completed':
                        raise ConnectError(result['error'] or 'inference_failed')
                    if not total:
                        raise ConnectError('request_indeterminate')
                    done = True
                    return
                await asyncio.sleep(.25)
        finally:
            if not done and not channel.stop.is_set():
                try:
                    await asyncio.wait_for(self.exchange(channel, self.make(channel.peer, 'cancel', job_id=req.job_id)), 5)
                except ConnectError as error:
                    if str(error) not in ('unknown_request', 'permission_denied', 'device_revoked', 'device_unavailable'):
                        channel.close()
                except (Exception, asyncio.CancelledError):
                    # Channel close is the bounded final cancellation mechanism.
                    channel.close()
