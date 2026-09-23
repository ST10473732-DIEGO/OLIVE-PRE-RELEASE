"""Private llama.cpp GUI-Owl inference under the existing model resource lease.

The server has read-only model/runtime mounts, GPU devices and no home directory.
No built-in agent tools, media filesystem route, web UI, or remote-code loading.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import time

import httpx

MODEL = 'GUI-Owl-1.5-8B-Instruct-Q5_K_M'


class GuiModelService:
    def __init__(self, residency, config=None):
        self.residency = residency
        self.config = config or Path.home() / '.config/olive/gui-model.json'
        self.process = None
        self.client = None
        self.metrics = []
        self.residency.register_provider(MODEL, self.start, self.close)
        self.keyfile = None

    async def start(self):
        if self.process and self.process.returncode is None:
            return
        config = json.loads(self.config.read_text())
        runtime, cuda, models = (Path(config[key]).resolve(strict=True) for key in ('runtime', 'cuda', 'models'))
        if any(not p.is_dir() for p in (runtime, cuda, models)):
            raise ValueError('GUI runtime/model paths must be directories')
        # The shared manager has already released OLIVE's previous model. Do not
        # evict another client's work or attempt a known over-budget allocation.
        query = await asyncio.create_subprocess_exec('nvidia-smi', '--id=0',
            '--query-gpu=memory.free', '--format=csv,noheader,nounits',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            available, _ = await asyncio.wait_for(query.communicate(), 5)
        except BaseException:
            if query.returncode is None:
                query.kill()
                await query.wait()
            raise
        if query.returncode or int(available.strip()) < 9000:
            raise MemoryError('GUI inference needs 9000 MiB of free GPU memory; other workloads were preserved')
        import tempfile
        fd, filename = tempfile.mkstemp(prefix='olive-gui-key-', dir=os.environ['XDG_RUNTIME_DIR'])
        self.keyfile = Path(filename)
        key = secrets.token_urlsafe(32)
        with os.fdopen(fd, 'w') as output:
            output.write(key)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        args = ['bwrap', '--die-with-parent', '--new-session', '--unshare-all', '--share-net', '--clearenv',
                '--ro-bind', '/usr', '/usr', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib', '/lib64',
                '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--ro-bind', '/sys', '/sys',
                '--ro-bind', str(runtime), '/runtime', '--ro-bind', str(cuda), '/cuda',
                '--ro-bind', str(models), '/models', '--ro-bind', filename, '/key',
                '--setenv', 'LD_LIBRARY_PATH', '/runtime:/cuda', '--chdir', '/tmp']
        for device in ('/dev/nvidia0', '/dev/nvidiactl', '/dev/nvidia-uvm', '/dev/nvidia-uvm-tools'):
            if Path(device).exists():
                args += ['--dev-bind', device, device]
        args += ['/runtime/llama-server', '-m', '/models/GUI-Owl-1.5-8B-Instruct.Q5_K_M.gguf',
                 '--mmproj', '/models/GUI-Owl-1.5-8B-Instruct.mmproj-f16.gguf',
                 '--host', '127.0.0.1', '--port', str(port), '--api-key-file', '/key',
                 '--no-webui', '--no-agent', '--no-webui-mcp-proxy', '--jinja',
                 '--device', 'CUDA0', '-ngl', '99', '-c', '8192', '-np', '1', '-fa', 'on',
                 '--image-max-tokens', '2048', '--reasoning', 'off']
        try:
            self.process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL,
                                                              stderr=asyncio.subprocess.PIPE)
        except BaseException:
            self.keyfile.unlink(missing_ok=True)
            self.keyfile = None
            raise
        # Retain only bounded startup diagnostics; model outputs/screens never enter logs.
        self.startup_error = bytearray()
        async def drain():
            while chunk := await self.process.stderr.read(4096):
                if len(self.startup_error) < 64000:
                    self.startup_error.extend(chunk[:64000-len(self.startup_error)])
        self.drain_task = asyncio.create_task(drain())
        self.client = httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',
            headers={'Authorization': 'Bearer ' + key}, trust_env=False, timeout=60)
        deadline = time.monotonic() + 90
        try:
            while time.monotonic() < deadline:
                if self.process.returncode is not None:
                    raise RuntimeError('GUI model server exited: ' + self.startup_error.decode(errors='replace')[-1600:])
                try:
                    if (await self.client.get('/health')).status_code == 200:
                        return
                except httpx.TransportError:
                    pass
                await asyncio.sleep(.2)
            raise TimeoutError('GUI model startup exceeded 90 seconds')
        except BaseException:
            await self.close()
            raise

    async def infer(self, messages, max_tokens=256):
        async with self.residency.lease(MODEL):
            started = time.monotonic()
            try:
                response = await self.client.post('/v1/chat/completions', json={
                    'model': MODEL, 'messages': messages, 'temperature': 0,
                    'max_tokens': max_tokens, 'cache_prompt': True})
                response.raise_for_status()
                result = response.json()
                self.metrics.append({'seconds': time.monotonic()-started, 'usage': result.get('usage', {}),
                                     'timings': result.get('timings', {})})
                self.metrics[:] = self.metrics[-100:]
                choice = result['choices'][0]
                if choice.get('finish_reason') == 'length':
                    raise ValueError('GUI model output was truncated; no action accepted')
                # Never retain or show reasoning_content, logs or hidden reasoning.
                message = choice['message']
                if message.get('tool_calls'):
                    calls = message['tool_calls']
                    if len(calls) != 1 or calls[0].get('type') != 'function':
                        raise ValueError('Exactly one GUI function call required')
                    function = calls[0]['function']
                    arguments = function['arguments']
                    if not isinstance(arguments, str) or len(arguments) > 12000:
                        raise ValueError('Invalid GUI function arguments')
                    # Preserve duplicate fields for the strict downstream parser;
                    # ordinary json.loads here would silently discard them.
                    return '<tool_call>{"name":' + json.dumps(function['name']) + ',"arguments":' + arguments + '}</tool_call>'
                return message.get('content') or ''
            except BaseException:
                # HTTP cancellation alone is not proof the GPU request stopped.
                await self.close()
                raise

    async def action(self, frame, instruction, history=()):
        from ..desktop.gui_owl import SYSTEM, parse_action
        encoded = frame['png']
        if len(encoded) > 6 * 1024 * 1024:
            raise ValueError('GUI image too large')
        base64.b64decode(encoded, validate=True)
        raw = await self.infer([
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': 'Instruction: ' + instruction + '\nPrevious actions: ' + json.dumps(list(history)[-8:])},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}}]}])
        return parse_action(raw)

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None
        if self.process:
            if self.process.returncode is None:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), 3)
                except TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            if hasattr(self, 'drain_task'):
                await self.drain_task
            self.process = None
        if self.keyfile:
            self.keyfile.unlink(missing_ok=True)
            self.keyfile = None
