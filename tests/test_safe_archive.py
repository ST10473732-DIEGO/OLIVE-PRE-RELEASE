"""Malicious and malformed archives never write outside staging, and modes are normalised."""
import io
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest

from olive.services import safe_archive
from olive.services.safe_archive import ArchiveError
from tests.setup_installer_fixture import tar_bytes, zip_bytes

LIMIT = 10 * 1024 * 1024


class SafeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.outside = self.root / 'outside.txt'

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def extract(self, data, fmt='tar.gz', name='a', **kw):
        archive = self.write(name + '.' + fmt.replace('.', '-'), data)
        staging = self.root / ('staging-' + name)
        kw.setdefault('max_bytes', LIMIT)
        safe_archive.extract(archive, fmt, staging, **kw)
        return staging

    def refuses(self, data, fmt='tar.gz', **kw):
        with self.assertRaises(ArchiveError):
            self.extract(data, fmt, name='bad', **kw)
        self.assertFalse((self.root / 'staging-bad').exists(), 'staging must be removed on failure')
        self.assertFalse(self.outside.exists())

    def test_ordinary_tar_with_internal_links_extracts(self):
        data = tar_bytes({'bin/ollama': b'#!/bin/sh\n', 'lib/ollama/libx.so.0.1': b'elf'},
                         links={'lib/ollama/libx.so.0': 'libx.so.0.1', 'lib/ollama/libx.so': 'libx.so.0'},
                         executable={'bin/ollama', 'lib/ollama/libx.so.0.1'})
        staging = self.extract(data, executables=['bin/ollama'])
        self.assertEqual((staging / 'lib/ollama/libx.so').read_bytes(), b'elf')

    def test_parent_traversal_is_refused(self):
        self.refuses(tar_bytes({'../outside.txt': b'x'}))
        self.refuses(tar_bytes({'bin/../../outside.txt': b'x'}))
        self.refuses(zip_bytes({'../outside.txt': b'x'}), 'zip')

    def test_absolute_paths_are_refused(self):
        self.refuses(tar_bytes({str(self.outside): b'x'}))
        self.refuses(zip_bytes({'/etc/passwd-olive': b'x'}), 'zip')
        self.refuses(zip_bytes({'C:/Windows/x': b'x'}), 'zip')
        self.refuses(zip_bytes({'dir\\..\\..\\outside.txt': b'x'}), 'zip')

    def test_symlink_escape_is_refused(self):
        self.refuses(tar_bytes({}, links={'escape': '../outside.txt'}))
        self.refuses(tar_bytes({}, links={'escape': str(self.outside)}))
        self.refuses(tar_bytes({}, links={'a/b/escape': '../../../outside.txt'}))

    def test_writing_through_a_link_is_refused(self):
        # A link to an in-tree folder, then a member written "through" it.
        data = tar_bytes({'real/.keep': b''}, links={'alias': 'real'})
        buffer = io.BytesIO(data)
        with tarfile.open(fileobj=buffer) as tar:
            members = [(m, tar.extractfile(m).read() if m.isreg() else None) for m in tar.getmembers()]
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as tar:
            for member, body in members:
                tar.addfile(member, io.BytesIO(body) if body is not None else None)
            info = tarfile.TarInfo('alias/payload')
            info.size = 1
            tar.addfile(info, io.BytesIO(b'x'))
        self.refuses(out.getvalue())

    def test_hardlinks_devices_and_fifos_are_refused(self):
        self.refuses(tar_bytes({'a': b'x'}, hardlinks={'b': 'a'}))
        for kind in (tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE):
            out = io.BytesIO()
            with tarfile.open(fileobj=out, mode='w:gz') as tar:
                info = tarfile.TarInfo('device')
                info.type = kind
                tar.addfile(info)
            self.refuses(out.getvalue())

    def test_zip_symlinks_are_refused(self):
        self.refuses(zip_bytes({'ok': b'x'}, symlinks={'link': '../outside.txt'}), 'zip')

    def test_duplicate_member_never_overwrites(self):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as tar:
            for body in (b'first', b'second'):
                info = tarfile.TarInfo('file')
                info.size = len(body)
                tar.addfile(info, io.BytesIO(body))
        self.refuses(out.getvalue())

    def test_size_and_member_limits(self):
        self.refuses(tar_bytes({'big': b'x' * 5000}), max_bytes=4000)
        self.refuses(tar_bytes({f'f{i}': b'' for i in range(20)}), max_members=10)
        self.refuses(zip_bytes({'big': b'\0' * 50_000}), 'zip', max_bytes=10_000)

    def test_zip_member_inflating_beyond_its_declared_size_is_refused(self):
        data = bytearray(zip_bytes({'bomb': b'\0' * 100_000}))
        # Lie about the uncompressed size in the central directory (zip bomb pattern).
        index = data.rfind(b'PK\x01\x02')
        data[index + 24:index + 28] = (100).to_bytes(4, 'little')
        self.refuses(bytes(data), 'zip')

    def test_declared_executable_must_exist(self):
        self.refuses(tar_bytes({'bin/other': b'x'}), executables=['bin/ollama'])

    @unittest.skipIf(os.name == 'nt', 'POSIX modes')
    def test_only_declared_executables_keep_an_executable_bit(self):
        data = tar_bytes({'bin/ollama': b'#!', 'bin/helper.sh': b'#!', 'lib/x.so': b'elf'},
                         executable={'bin/ollama', 'bin/helper.sh', 'lib/x.so'})
        staging = self.extract(data, executables=['bin/ollama'])
        safe_archive.normalise_modes(staging, ['bin/ollama'])
        mode = lambda p: stat.S_IMODE((staging / p).stat().st_mode)
        self.assertEqual(mode('bin/ollama'), 0o755)
        self.assertEqual(mode('bin/helper.sh'), 0o644)
        self.assertEqual(mode('lib/x.so'), 0o644)

    @unittest.skipIf(os.name == 'nt', 'POSIX modes')
    def test_setuid_bits_never_survive(self):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as tar:
            info = tarfile.TarInfo('bin/ollama')
            info.size, info.mode = 2, 0o4755
            tar.addfile(info, io.BytesIO(b'#!'))
        staging = self.extract(out.getvalue(), executables=['bin/ollama'])
        safe_archive.normalise_modes(staging, ['bin/ollama'])
        self.assertFalse((staging / 'bin/ollama').stat().st_mode & stat.S_ISUID)

    def test_zstd_tar_is_supported(self):
        import importlib.util
        if importlib.util.find_spec('compression') is None or importlib.util.find_spec('compression.zstd') is None:
            self.skipTest('No zstd in this Python (3.14+)')
        data = tar_bytes({'bin/ollama': b'#!'}, mode='w:zst')
        staging = self.extract(data, 'tar.zst', executables=['bin/ollama'])
        self.assertTrue((staging / 'bin/ollama').is_file())

    def test_wheel_layout_installs_purelib_and_skips_scripts(self):
        data = zip_bytes({'pkg/__init__.py': b'', 'pkg-1.dist-info/METADATA': b'Name: pkg',
                          'pkg-1.data/purelib/extra/__init__.py': b'', 'pkg-1.data/scripts/run': b'#!'})
        staging = self.extract(data, 'wheel')
        self.assertTrue((staging / 'pkg/__init__.py').is_file())
        self.assertTrue((staging / 'extra/__init__.py').is_file())
        self.assertFalse(any('scripts' in str(p) for p in staging.rglob('*')))

    def test_unknown_format_and_corrupt_archives(self):
        self.refuses(b'not an archive', 'tar.gz')
        self.refuses(b'not an archive', 'zip')
        with self.assertRaises(ArchiveError):
            self.extract(b'x', 'rar', name='rar')

    def test_cancellation_stops_extraction_and_cleans_staging(self):
        import threading
        from olive.services.secure_download import Cancelled
        cancel = threading.Event()
        cancel.set()
        archive = self.write('c.tgz', tar_bytes({'a': b'x'}))
        with self.assertRaises(Cancelled):
            safe_archive.extract(archive, 'tar.gz', self.root / 'staging-c', max_bytes=LIMIT, cancel=cancel)
        self.assertFalse((self.root / 'staging-c').exists())


if __name__ == '__main__':
    unittest.main()
