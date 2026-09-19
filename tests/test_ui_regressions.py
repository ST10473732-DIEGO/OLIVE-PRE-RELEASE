import tempfile
import unittest
from pathlib import Path

from olive.services.checkpoint_service import CheckpointService
from olive.services.studio_service import StudioService
from olive.workspace import Workspace


class StudioSafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = StudioService(Workspace('Test', str(self.root)), CheckpointService(self.root/'snapshots'))

    def test_save_preserves_windows_newlines(self):
        path = self.root/'a.py'
        path.write_bytes(b'one\r\ntwo\r\n')
        self.service.open_file('a.py')
        self.service.update('a.py', 'one\r\nthree\r\n')
        self.service.save('a.py')
        self.assertEqual(path.read_bytes(), b'one\r\nthree\r\n')

    def test_invalid_encoding_is_rejected_without_changing_file(self):
        path=self.root/'a.txt'; path.write_bytes(b'\xfftext')
        with self.assertRaises(UnicodeDecodeError): self.service.open_file('a.txt')
        self.assertEqual(path.read_bytes(), b'\xfftext')
        self.assertEqual(self.service.open_files, {})

    def test_search_limit_is_global_and_ignores_dependencies(self):
        for index in range(5):
            (self.root/f'{index}.py').write_text('needle\n'*10, encoding='utf-8')
        ignored=self.root/'node_modules'; ignored.mkdir()
        (ignored/'hidden.js').write_text('needle', encoding='utf-8')
        self.assertEqual(len(self.service.search_workspace('needle', 12)), 12)
        self.assertEqual(self.service.search_workspace(''), [])
        self.assertFalse(any('node_modules' in item['path'] for item in self.service.tree()))

    def test_editor_rejects_oversized_files(self):
        (self.root/'large.txt').write_bytes(b'a'*(2*1024*1024+1))
        with self.assertRaises(ValueError): self.service.open_file('large.txt')


if __name__ == '__main__':
    unittest.main()
