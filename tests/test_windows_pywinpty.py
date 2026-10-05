"""Windows packages carry pywinpty, so the Studio terminal is not artificially absent there."""
from pathlib import Path
import unittest
from unittest import mock

from olive.studio_tooling import toolchain

ROOT = Path(__file__).resolve().parents[1]


class WindowsTerminalCapabilityTests(unittest.TestCase):
    def test_terminal_is_offered_when_the_backend_has_pywinpty(self):
        available = lambda python, module: module == 'winpty'
        with mock.patch.object(toolchain.sys, 'platform', 'win32'), \
                mock.patch.object(toolchain, 'module_available', side_effect=available), \
                mock.patch.object(toolchain, 'dotnet_executable', return_value=None):
            terminal = toolchain.inventory(ROOT)['terminal']
        self.assertTrue(terminal['available'])
        self.assertEqual(terminal['provider'], 'pywinpty (ConPTY)')

    def test_missing_pywinpty_is_reported_truthfully(self):
        with mock.patch.object(toolchain.sys, 'platform', 'win32'), \
                mock.patch.object(toolchain, 'module_available', return_value=False), \
                mock.patch.object(toolchain, 'dotnet_executable', return_value=None):
            self.assertFalse(toolchain.inventory(ROOT)['terminal']['available'])

    def test_backend_build_installs_the_windows_lock_unfiltered(self):
        # build_backend installs locks/<target>.txt as a whole; no package filter can drop pywinpty.
        source = (ROOT / 'packaging/backend/build_backend.py').read_text(encoding='utf-8')
        self.assertIn('--require-hashes', source)
        self.assertNotIn('winpty', source)


if __name__ == '__main__':
    unittest.main()
