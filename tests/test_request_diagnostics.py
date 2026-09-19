"""Controlled failures; no window discovery or desktop interaction."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from olive.runtime.request_diagnostics import RequestDiagnostic, current, stage


class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_opaque_context_ids_enter_safe_diagnostics(self):
        diagnostic = RequestDiagnostic('request', 'studio.run')
        diagnostic.identify({'workspace_id': '84ad1940-73df-4633-a3bb-f75601b3e9df',
                             'session_id': 'private terminal content', 'text': 'secret'})
        with tempfile.TemporaryDirectory() as directory:
            safe = diagnostic.failure(ValueError('private error'), directory)
        self.assertEqual(safe['feature'], 'studio')
        self.assertEqual(safe['context_ids'], {'workspace_id': '84ad1940-73df-4633-a3bb-f75601b3e9df'})
        self.assertNotIn('private', json.dumps(safe))
        self.assertNotIn('secret', json.dumps(safe))

    async def test_thread_and_child_task_keep_request_and_failing_stage(self):
        diagnostic = RequestDiagnostic('request-123', 'desktop.attach_launch')
        token = current.set(diagnostic)
        def resolve():
            stage('owned_window_resolution')
            raise LookupError('controlled original exception')
        try:
            with self.assertRaisesRegex(LookupError, 'original exception'):
                await asyncio.create_task(asyncio.to_thread(resolve))
            self.assertEqual(diagnostic.request_id, 'request-123')
            self.assertEqual(diagnostic.stage, 'owned_window_resolution')
            self.assertFalse(diagnostic.provider_reached)
        finally:
            current.reset(token)
        self.assertIsNone(current.get())

    async def test_no_opt_in_means_no_exception_text_or_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, OLIVE_ATTACH_DIAGNOSTICS='0'):
            safe = RequestDiagnostic('id', 'desktop.attach_launch').failure(ValueError('private fixture'), directory)
            self.assertNotIn('private fixture', json.dumps(safe))
            self.assertFalse(safe['diagnostic_saved'])
            self.assertEqual(list(Path(directory).iterdir()), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI required')
    async def test_original_exception_and_stack_are_protected_and_bounded(self):
        import win32crypt
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, OLIVE_ATTACH_DIAGNOSTICS='1'):
            diagnostic = RequestDiagnostic('id', 'desktop.attach_launch')
            try:
                raise LookupError('controlled original failure')
            except LookupError as error:
                safe = diagnostic.failure(error, directory)
            self.assertTrue(safe['diagnostic_saved'])
            file = next((Path(directory) / 'developer-diagnostics').iterdir())
            self.assertNotIn(b'controlled original failure', file.read_bytes())
            payload = json.loads(win32crypt.CryptUnprotectData(file.read_bytes(), None, None, None, 1)[1])
            self.assertEqual(payload['exception'], 'controlled original failure')
            self.assertEqual(payload['traceback'][-1]['function'], self._testMethodName)
            self.assertNotIn('locals', str(payload))
            # An existing evidence file is never overwritten or a logging failure raised.
            self.assertFalse(diagnostic.failure(ValueError('later'), directory)['diagnostic_saved'])
