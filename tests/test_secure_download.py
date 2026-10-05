"""Pinned, resumable downloads: HTTPS/source policy, hash and size enforcement, resume, cancel."""
import os
from pathlib import Path
import tempfile
import threading
import unittest

from olive.services import secure_download
from olive.services.secure_download import Artefact, Cancelled, DownloadError, Downloader
from tests.setup_installer_fixture import FileServer, sha


class SecureDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.server = FileServer().__enter__()
        self.body = os.urandom(3 * 1024 * 1024 + 123)
        self.url = self.server.add('/artefact.bin', self.body)
        self.downloader = Downloader(self.root / 'downloads', allow_loopback_http=True, sleep=lambda s: None)
        self.original_range = secure_download.RANGE
        secure_download.RANGE = 1024 * 1024  # Several ranges per file.

    def tearDown(self):
        secure_download.RANGE = self.original_range
        self.server.__exit__(None, None, None)
        self.temp.cleanup()

    def artefact(self, **changes):
        values = dict(url=self.url, sha256=sha(self.body), size=len(self.body), hosts=('127.0.0.1',))
        values.update(changes)
        return Artefact(**values)

    def test_verified_download_uses_bounded_ranges(self):
        seen = []
        path = self.downloader.fetch(self.artefact(), progress=lambda done, total: seen.append(done))
        self.assertEqual(path.read_bytes(), self.body)
        self.assertEqual(path.name, sha(self.body))
        self.assertEqual(seen[-1], len(self.body))
        self.assertTrue(all(r and r.startswith('bytes=') for _, r in self.server.requests))
        self.assertEqual(len(self.server.requests), 4)
        self.assertFalse(list((self.root / 'downloads').glob('*.part')))

    def test_plain_http_is_refused_without_the_fixture_flag(self):
        strict = Downloader(self.root / 'strict', sleep=lambda s: None)
        with self.assertRaises(DownloadError) as caught:
            strict.fetch(self.artefact())
        self.assertEqual(caught.exception.code, 'source_not_allowed')
        self.assertEqual(self.server.requests, [])

    def test_https_to_an_unlisted_host_is_refused(self):
        with self.assertRaises(DownloadError) as caught:
            self.downloader.fetch(self.artefact(url='https://evil.example/artefact.bin', hosts=('github.com',)))
        self.assertEqual(caught.exception.code, 'source_not_allowed')
        with self.assertRaises(DownloadError):
            self.downloader.fetch(self.artefact(url='https://user:pw@github.com/x', hosts=('github.com',)))

    def test_redirect_to_a_host_outside_the_manifest_is_refused(self):
        self.server.redirects['/artefact.bin'] = 'http://192.0.2.1/elsewhere'
        with self.assertRaises(DownloadError) as caught:
            self.downloader.fetch(self.artefact())
        self.assertEqual(caught.exception.code, 'redirect_not_allowed')

    def test_redirect_within_allowed_hosts_is_followed(self):
        self.server.files['/moved.bin'] = self.body
        self.server.redirects['/artefact.bin'] = '/moved.bin'
        self.assertEqual(self.downloader.fetch(self.artefact()).read_bytes(), self.body)

    def test_hash_mismatch_is_rejected_and_bytes_deleted(self):
        with self.assertRaises(DownloadError) as caught:
            self.downloader.fetch(self.artefact(sha256='0' * 64))
        self.assertEqual(caught.exception.code, 'checksum_mismatch')
        self.assertEqual(list((self.root / 'downloads').iterdir()), [])

    def test_unpinned_artefact_is_refused(self):
        with self.assertRaises(DownloadError) as caught:
            self.downloader.fetch(self.artefact(sha256='not-a-hash'))
        self.assertEqual(caught.exception.code, 'unpinned')

    def test_interrupted_download_resumes_from_partial_bytes(self):
        self.server.drop_after['/artefact.bin'] = 300_000
        path = self.downloader.fetch(self.artefact())
        self.assertEqual(path.read_bytes(), self.body)
        ranges = [r for _, r in self.server.requests]
        self.assertIn('bytes=300000-1048575', ranges)

    def test_partial_from_a_previous_run_is_resumed_not_restarted(self):
        part, _ = self.downloader.paths(self.artefact())
        part.parent.mkdir(parents=True)
        part.write_bytes(self.body[:1_500_000])
        self.downloader.fetch(self.artefact())
        self.assertEqual(self.server.requests[0][1], 'bytes=1500000-2548575')

    def test_corrupt_partial_fails_the_checksum_instead_of_being_trusted(self):
        part, _ = self.downloader.paths(self.artefact())
        part.parent.mkdir(parents=True)
        part.write_bytes(b'\0' * 1_500_000)
        with self.assertRaises(DownloadError) as caught:
            self.downloader.fetch(self.artefact())
        self.assertEqual(caught.exception.code, 'checksum_mismatch')
        self.assertFalse(part.exists())

    def test_cancellation_keeps_partial_for_retry(self):
        cancel = threading.Event()

        def progress(done, total):
            if done > 1_200_000:
                cancel.set()
        with self.assertRaises(Cancelled):
            self.downloader.fetch(self.artefact(), cancel=cancel, progress=progress)
        part, final = self.downloader.paths(self.artefact())
        self.assertTrue(part.exists())
        self.assertFalse(final.exists())
        kept = part.stat().st_size
        self.assertGreater(kept, 1_200_000)
        self.assertEqual(self.downloader.fetch(self.artefact()).read_bytes(), self.body)

    def test_server_ignoring_ranges_is_accepted_only_for_the_exact_full_body(self):
        self.server.ignore_range = True
        self.assertEqual(self.downloader.fetch(self.artefact()).read_bytes(), self.body)
        other = Downloader(self.root / 'other', allow_loopback_http=True, sleep=lambda s: None)
        self.server.extra = b'appended'
        with self.assertRaises(DownloadError) as caught:
            other.fetch(self.artefact())
        self.assertIn(caught.exception.code, {'size_mismatch', 'oversize'})

    def test_bigger_than_pinned_size_is_rejected(self):
        with self.assertRaises(DownloadError) as caught:
            self.downloader.fetch(self.artefact(size=len(self.body) - 10))
        self.assertIn(caught.exception.code, {'bad_range', 'checksum_mismatch', 'size_mismatch', 'oversize'})

    def test_completed_download_is_reverified_before_reuse(self):
        _, final = self.downloader.paths(self.artefact())
        final.parent.mkdir(parents=True)
        final.write_bytes(b'x' * len(self.body))  # Right size, wrong bytes.
        self.assertEqual(self.downloader.fetch(self.artefact()).read_bytes(), self.body)

    @unittest.skipIf(os.name == 'nt', 'symlink semantics')
    def test_symlinked_partial_is_refused(self):
        part, _ = self.downloader.paths(self.artefact())
        part.parent.mkdir(parents=True)
        os.symlink(self.root / 'elsewhere', part)
        with self.assertRaises(DownloadError) as caught:
            self.downloader.fetch(self.artefact())
        self.assertEqual(caught.exception.code, 'unsafe_partial')


if __name__ == '__main__':
    unittest.main()
