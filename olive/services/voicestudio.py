"""Loopback client for a separately installed VoiceStudio speech service.

VoiceStudio stays an independent local service (its source is not copied
into OLIVE). OLIVE only calls its documented HTTP API, and refuses to
synthesize unless the active engine's model is already installed locally,
because VoiceStudio would otherwise download it on first use.
"""
import asyncio
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import wave
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx

from .media_errors import MediaError


def loopback(url):
    parts = urlsplit(url)
    try:
        local = parts.hostname == 'localhost' or ip_address(parts.hostname or '').is_loopback
    except ValueError:
        local = False
    if parts.scheme != 'http' or not local or not parts.port or parts.username or parts.password or parts.path not in ('', '/') or parts.query:
        raise ValueError('Use a loopback-only VoiceStudio address such as http://127.0.0.1:3900')
    return url.rstrip('/')


def listener_scope(port):
    """'loopback' | 'network' | 'none' | 'unknown' for the TCP listeners on port.

    OLIVE only talks to a loopback URL, but a service bound to 0.0.0.0 would
    also accept speech text from the LAN, so AUDIO is not ready unless every
    listener on the port is loopback-only."""
    import psutil
    try:
        connections = psutil.net_connections(kind='tcp')
    except (psutil.AccessDenied, OSError):
        return 'unknown'
    addresses = {c.laddr.ip for c in connections if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port}
    if not addresses:
        return 'none'
    def local(address):
        try:
            return ip_address(address.split('%')[0]).is_loopback
        except ValueError:
            return False
    return 'loopback' if all(local(a) for a in addresses) else 'network'


class LocalVoiceStudioRuntime:
    """OLIVE-owned, loopback-only VoiceStudio process, used only when none runs.

    Runs the installed venv's uvicorn directly (never `uv run`, which may sync
    packages) with Hugging Face offline mode, so it cannot download models."""

    def __init__(self, url, root):
        from .local_ollama_runtime import LocalOllamaRuntime
        self.url, self.root = url, root
        self.owned_process = LocalOllamaRuntime(url)  # Reuses its owned-process cleanup.
        self.lock = asyncio.Lock()

    @property
    def python(self):
        windows = Path(self.root, '.venv', 'Scripts', 'python.exe')
        return str(windows if sys.platform == 'win32' else Path(self.root, '.venv', 'bin', 'python'))

    def installed(self):
        return bool(self.root) and Path(self.root, 'backend', 'main.py').is_file() and Path(self.python).is_file()

    def owned(self):
        process = self.owned_process.process
        return process is not None and process.returncode is None

    async def healthy(self):
        try:
            async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                response = await client.get(self.url + '/health')
                return response.status_code == 200 and response.json().get('status') == 'ok'
        except (httpx.HTTPError, ValueError):
            return False

    async def start(self):
        from .gpu_probe import port_bound
        port = urlsplit(self.url).port
        async with self.lock:
            if port_bound(port) or not self.installed():
                return  # An existing service is never replaced.
            import psutil
            from ..runtime.processes import start_owned_process
            env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            runtime = self.owned_process
            runtime.process = await start_owned_process(
                [self.python, '-m', 'uvicorn', 'main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', str(port)],
                cwd=self.root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            runtime.owner = psutil.Process(runtime.process.pid)
            try:
                for _ in range(900):
                    if await self.healthy():
                        return
                    if runtime.process.returncode is not None:
                        raise RuntimeError('VoiceStudio exited during startup')
                    await asyncio.sleep(.2)
                raise TimeoutError('VoiceStudio startup timed out')
            except BaseException:
                await self.close()
                raise

    async def close(self):
        await self.owned_process.close()  # Only an OLIVE-started process is stopped.


class VoiceStudio:
    MAX_AUDIO = 64_000_000

    def __init__(self, url, root=''):
        self.url = loopback(url) if url else ''
        self.runtime = LocalVoiceStudioRuntime(self.url, root) if self.url else None
        self.last = {'state': 'not configured' if not url else 'unknown'}

    @property
    def port(self):
        return urlsplit(self.url).port

    async def request(self, method, path, *, timeout=10, **kwargs):
        async with httpx.AsyncClient(base_url=self.url, timeout=timeout, follow_redirects=False, trust_env=False) as client:
            async with client.stream(method, path, **kwargs) as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > self.MAX_AUDIO:
                        raise ValueError('Speech response exceeded its bound')
                return bytes(data), response.headers.get('content-type', '')

    async def json(self, method, path, **kwargs):
        data, _ = await self.request(method, path, **kwargs)
        return json.loads(data or b'{}')

    async def status(self):
        """Truthful readiness without loading or downloading anything."""
        if not self.url:
            self.last = {'state': 'not configured'}
            return self.last
        try:
            health = await self.json('GET', '/health', timeout=3)
            engines = await self.json('GET', '/engines/tts', timeout=5)
            models = await self.json('GET', '/models', timeout=5)
        except (httpx.HTTPError, ValueError, OSError):
            # Not running: OLIVE may start its own loopback-only instance on request.
            self.last = {'state': 'stopped' if self.runtime and self.runtime.installed() else 'unreachable'}
            return self.last
        binding = await asyncio.to_thread(listener_scope, self.port)
        active = engines.get('active')
        backend = next((b for b in engines.get('backends', []) if b.get('id') == active), {})
        checkpoint = engines.get('active_model') or ''
        model = next((m for m in models.get('models', []) if m.get('repo_id') == checkpoint), None)
        installed = bool(model and model.get('installed') and not model.get('incomplete'))
        usable = health.get('status') == 'ok' and backend.get('available') and installed
        self.last = {
            'state': ('exposed' if binding == 'network' else 'unverified' if binding != 'loopback' else 'ready') if usable else 'needs setup',
            'binding': binding, 'owned': bool(self.runtime and self.runtime.owned()),
            'service_version': str(health.get('version', ''))[:40],
            'engine': str(active or '')[:80], 'engine_label': str(backend.get('display_name', ''))[:120],
            'checkpoint': str(checkpoint)[:200], 'model_installed': installed,
            'missing': [] if installed else [str(checkpoint or 'an installed TTS model')[:200]],
            # Speech only. Cloning/emotion/music are not offered by OLIVE AUDIO.
            'capabilities': ['speech'] if installed else [],
        }
        return self.last

    async def voices(self):
        """Voices actually exposed by the service: its default plus saved profiles."""
        if not self.url:
            return []
        try:
            profiles = await self.json('GET', '/profiles', timeout=5)
        except (httpx.HTTPError, ValueError, OSError):
            return []
        rows = [{'id': 'default', 'name': 'VoiceStudio default'}]
        for profile in profiles if isinstance(profiles, list) else []:
            if isinstance(profile, dict) and isinstance(profile.get('id'), str) and isinstance(profile.get('name'), str):
                rows.append({'id': profile['id'][:80], 'name': profile['name'][:120]})
        return rows[:100]

    async def speech(self, text, voice, style, cancel, progress=lambda _: None):
        status = await self.status()
        if status['state'] == 'stopped':
            progress('Starting audio engine…')
            try:
                await self.runtime.start()
            except Exception as error:
                raise MediaError('engine_start_failed', str(error)) from None
            status = await self.status()
        if status['state'] in {'unreachable', 'stopped'}:
            raise MediaError('engine_unreachable', 'VoiceStudio unreachable')
        if not status.get('model_installed'):
            raise MediaError('audio_model_missing', status.get('checkpoint', ''))
        if status['state'] == 'exposed':
            raise MediaError('audio_exposed', 'VoiceStudio listens on a non-loopback address')
        if status['state'] != 'ready':
            raise MediaError('audio_unverified', status.get('binding', ''))
        body = {'model': status['engine'], 'input': text, 'voice': voice or 'default', 'response_format': 'wav'}
        if style:
            body['instructions'] = style
        task = asyncio.create_task(self.request('POST', '/v1/audio/speech', json=body, timeout=600))
        waiter = asyncio.create_task(cancel.wait())
        try:
            done, _ = await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
            if task not in done:
                # The HTTP synthesis call is atomic on the service side; dropping
                # the connection stops OLIVE from attaching a late result.
                task.cancel()
                raise asyncio.CancelledError()
            data, content_type = task.result()
        except asyncio.CancelledError:
            task.cancel()
            raise
        except httpx.HTTPStatusError as error:
            raise MediaError('generation_failed', f'VoiceStudio HTTP {error.response.status_code}') from None
        except (httpx.HTTPError, OSError) as error:
            raise MediaError('engine_unreachable', type(error).__name__) from None
        finally:
            waiter.cancel()
        try:
            with wave.open(io.BytesIO(data)) as clip:
                seconds = clip.getnframes() / float(clip.getframerate() or 1)
        except (wave.Error, EOFError):
            raise MediaError('no_artifact', 'VoiceStudio returned non-WAV audio: ' + content_type[:60]) from None
        if seconds <= 0:
            raise MediaError('no_artifact', 'empty audio')
        return data, {'engine': status['engine'], 'engine_label': status['engine_label'],
                      'service_version': status['service_version'], 'duration_seconds': round(seconds, 2)}

    async def release(self):
        """Unload the TTS model this request loaded; VoiceStudio keeps running."""
        try:
            await self.request('POST', '/model/unload/tts', timeout=30)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 400:  # 400: not loaded.
                raise

    async def close(self):
        if self.runtime:
            await self.runtime.close()
