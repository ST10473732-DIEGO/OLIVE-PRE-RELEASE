import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'linux', 'POSIX PTY ownership')
class DescriptorOwnershipTests(unittest.TestCase):
    def test_concurrent_close_transfers_descriptor_once(self):
        from olive.studio_tooling.posix_pty import PosixPTY
        terminal = PosixPTY.__new__(PosixPTY)
        terminal.fd_lock = threading.RLock()
        terminal.master = 1234
        entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
        def close(descriptor):
            self.assertEqual(descriptor, 1234)
            entered.set()
            self.assertTrue(release.wait(3))
        def second():
            second_started.set()
            terminal.close()
        with patch('olive.studio_tooling.posix_pty.os.close', side_effect=close) as closer, ThreadPoolExecutor(2) as pool:
            first = pool.submit(terminal.close)
            try:
                self.assertTrue(entered.wait(2))
                other = pool.submit(second)
                self.assertTrue(second_started.wait(2))
                self.assertEqual(terminal.master, -1)
            finally:
                release.set()
            first.result(2)
            other.result(2)
            closer.assert_called_once_with(1234)

    def test_closed_pty_never_reads_or_resizes_a_recycled_descriptor(self):
        from olive.studio_tooling.posix_pty import PosixPTY
        terminal = PosixPTY.__new__(PosixPTY)
        terminal.fd_lock = threading.RLock()
        terminal.master = os.open(os.devnull, os.O_RDONLY)
        terminal.close()
        self.assertEqual(terminal.read(), '')
        with self.assertRaisesRegex(ValueError, 'closed'):
            terminal.set_size(80, 24)
