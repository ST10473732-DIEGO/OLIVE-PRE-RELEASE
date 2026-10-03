"""An existing service is never owned; automatic startup stays local and opt-in."""
import os
import unittest
from unittest.mock import AsyncMock, patch
from olive.services.local_ollama_runtime import LocalOllamaRuntime


class LocalOllamaRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_service_is_reused_and_never_stopped(self):
        runtime = LocalOllamaRuntime('http://127.0.0.1:11434')
        with patch.dict(os.environ, OLIVE_START_OLLAMA='1'), patch('sys.platform', 'linux'), patch.object(runtime, 'ready', AsyncMock(return_value=True)), patch('asyncio.create_subprocess_exec') as spawn:
            await runtime.start()
            await runtime.close()
            spawn.assert_not_called()
            self.assertIsNone(runtime.process)

    async def test_external_and_fixture_endpoints_never_auto_start(self):
        for host in ('http://example.test:11434', 'http://127.0.0.1:12345', 'https://localhost:11434'):
            runtime = LocalOllamaRuntime(host)
            with patch.dict(os.environ, OLIVE_START_OLLAMA='1'), patch('sys.platform', 'linux'), patch.object(runtime, 'ready', AsyncMock()) as ready, patch('asyncio.create_subprocess_exec') as spawn:
                await runtime.start()
                ready.assert_not_called()
                spawn.assert_not_called()

    async def test_opt_out_and_unsupported_platforms_leave_lifecycle_unchanged(self):
        for platform, enabled in [('win32', '0'), ('linux', '0'), ('darwin', '0'), ('freebsd14', '1')]:
            runtime = LocalOllamaRuntime('http://127.0.0.1:11434')
            with patch.dict(os.environ, OLIVE_START_OLLAMA=enabled), patch('sys.platform', platform), patch.object(runtime, 'ready', AsyncMock()) as ready:
                await runtime.start()
                ready.assert_not_called()

    async def test_windows_and_macos_reuse_an_existing_server_too(self):
        # The owned lifecycle is prepared on Windows/macOS; a running server is still never owned.
        for platform in ('win32', 'darwin'):
            runtime = LocalOllamaRuntime('http://127.0.0.1:11434')
            with patch.dict(os.environ, OLIVE_START_OLLAMA='1'), patch('sys.platform', platform), patch.object(runtime, 'ready', AsyncMock(return_value=True)) as ready, patch('asyncio.create_subprocess_exec') as spawn:
                await runtime.start()
                ready.assert_awaited()
                spawn.assert_not_called()
                self.assertIsNone(runtime.process)
