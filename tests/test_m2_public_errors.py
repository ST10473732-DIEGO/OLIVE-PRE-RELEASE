import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from olive.bridge.public_errors import public_error
from olive.services.repository_service import RepositoryService


class PublicBoundaryTests(unittest.TestCase):
    def test_common_failures_give_safe_guidance_without_provider_text(self):
        for error, guidance in (
            (FileNotFoundError('private-token-123'), 'not found'),
            (TimeoutError('private-token-123'), 'timed out'),
            (ConnectionError('private-token-123'), 'connection'),
            (PermissionError('private-token-123'), 'permission'),
            (RuntimeError('File changed since it was read'), 'Reload'),
        ):
            with self.subTest(kind=type(error).__name__):
                message = public_error(error)['message']
                self.assertIn(guidance.lower(), message.lower())
                self.assertNotIn('private-token-123', message)

    def test_only_exact_known_guidance_is_returned(self):
        self.assertIn('cancelled before execution', public_error(PermissionError('Task cancelled by user'))['message'])
        for error in (RuntimeError('private-token-123'), ValueError('Task cancelled by user private-token-123')):
            self.assertNotIn('private-token-123', public_error(error)['message'])

    def test_git_cannot_consume_application_protocol_input(self):
        with patch('olive.services.repository_service.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess(['git'], 0, '', '')
            RepositoryService()._run(Path.cwd(), 'status')
            self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
            self.assertNotIn('shell', run.call_args.kwargs)
