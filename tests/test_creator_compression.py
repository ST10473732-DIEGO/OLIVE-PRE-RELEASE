"""Creator archive compression (PASS 2F-D): the .tar.zst is written by the pinned interpreter's own
compression.zstd (libzstd compiled into python-build-standalone) with fixed, single-threaded
parameters, so the build machine's zstd, CPU count and paths cannot change a byte. Also the build
provenance flag working_tree_clean, which must describe the source checkout, not the build's output."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from tests.test_creator_runtime import CREATOR, PINNED_PYTHON, builder, cached_pinned_interpreter

PACK = CREATOR / 'pack_archive.py'
# Packing golden_stage() with the pinned compressor (CPython 3.14.8 python-build-standalone 20261001,
# built-in libzstd 1.5.7, compression.json parameters). Any machine with that interpreter must
# reproduce these bytes. libzstd 1.5.7 with its block pre-splitter disabled (how the hosted
# runner's Python compressed in PASS 2F-C) gives 0a322fdf... instead.
GOLDEN_ARCHIVE = '89a3c1a15b17e344913dd8ae0315fba3d7af90fbe9d017ee3713347af0df0c63'
GOLDEN_TAR = '3b9e6d5f8f2e04dc94bcc7262cb2eb681f755c3ca059dcfa58a6e67debbee2d2'
EPOCH = 1788930166


def golden_stage(root: Path):
    """A fixed tree: compressible text, an incompressible executable, a link and folders."""
    (root / 'ComfyUI/sub').mkdir(parents=True)
    words = [hashlib.sha256(str(i).encode()).hexdigest()[:2 + i % 7] for i in range(400)]
    text = ' '.join(words[int.from_bytes(hashlib.sha256(str(i).encode()).digest()[:2], 'big') % 400]
                    for i in range(120000))
    (root / 'ComfyUI/main.py').write_text(text)
    noise = b''.join(hashlib.sha256(i.to_bytes(4, 'big')).digest() for i in range(4096))
    (root / 'python/bin').mkdir(parents=True)
    (root / 'python/bin/python3.14').write_bytes(noise)
    (root / 'python/bin/python3.14').chmod(0o755)
    (root / 'python/bin/python3').symlink_to('python3.14')


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CompressionSpecTests(unittest.TestCase):
    def test_the_committed_spec_pins_the_interpreter_version_and_single_thread(self):
        spec = builder.load_compression(builder.COMPRESSION)
        self.assertEqual(spec['format'], 'zstd')
        self.assertEqual(spec['zstd_version'], '1.5.7')
        self.assertEqual(spec['parameters'], {'compression_level': 12, 'nb_workers': 0, 'checksum_flag': 0,
                                              'content_size_flag': 0})
        # The compressor is the runtime's own pinned interpreter: no extra download, one pin to bump.
        self.assertEqual(spec['interpreters'], {'linux-x86_64': PINNED_PYTHON['sha256']})
        for path in sorted((CREATOR / 'definitions').glob('*.json')):
            definition = builder.load_definition(path)
            builder.check_compressor_pin(definition, PINNED_PYTHON, spec)

    def test_specs_that_are_not_fixed_are_refused(self):
        base = json.loads(builder.COMPRESSION.read_text())
        bad = {'multithreaded': {'nb_workers': 1}, 'auto threads': {'nb_workers': None},
               'unknown parameter': {'window_log': 22}, 'not an integer': {'compression_level': '12'}}
        with tempfile.TemporaryDirectory() as directory:
            for name, change in bad.items():
                with self.subTest(name):
                    spec = json.loads(json.dumps(base))
                    for key, value in change.items():
                        if value is None:
                            spec['parameters'].pop(key)
                        else:
                            spec['parameters'][key] = value
                    path = Path(directory) / 'spec.json'
                    path.write_text(json.dumps(spec))
                    with self.assertRaises(SystemExit):
                        builder.load_compression(path)
            spec = dict(base, format='xz')
            path.write_text(json.dumps(spec))
            with self.assertRaises(SystemExit):
                builder.load_compression(path)

    def test_a_different_interpreter_pin_is_a_deliberate_compression_change(self):
        definition = builder.load_definition(CREATOR / 'definitions/creator-image-comfyui-0.35.0-linux-x86_64.json')
        spec = builder.load_compression(builder.COMPRESSION)
        with self.assertRaises(SystemExit) as caught:
            builder.check_compressor_pin(definition, dict(PINNED_PYTHON, sha256='0' * 64), spec)
        self.assertIn('update compression.json deliberately', str(caught.exception))

    def test_a_release_build_cannot_pack_with_another_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit) as caught:
                builder.build(CREATOR / 'definitions/creator-image-comfyui-0.35.0-linux-x86_64.json', Path(directory),
                              Path(directory) / 'cache', fixture_compressor=Path(sys.executable))
        self.assertIn('fixture builds only', str(caught.exception))

    def test_the_host_compressor_must_match_the_declared_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'stage').mkdir()
            (root / 'stage/file.txt').write_text('payload\n')
            spec = dict(builder.load_compression(builder.COMPRESSION), zstd_version='0.0.0')
            archive = root / 'a.tar.zst'
            with self.assertRaises(SystemExit) as caught:
                builder.pack(root / 'stage', archive, EPOCH, spec, Path(sys.executable), fixture=True)
            self.assertIn('the pinned compressor is 0.0.0', str(caught.exception))
            self.assertFalse(archive.exists())  # Nothing is written by the wrong compressor.


@unittest.skipIf(cached_pinned_interpreter() is None, 'the pinned python-build-standalone archive is not cached '
                 '(packaging/creator/.cache or packaging/backend/.cache); tests never download it')
class PinnedCompressorTests(unittest.TestCase):
    """The real pinned compressor, extracted exactly as the builder does."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cache = cls.root / 'cache'
        cache.mkdir()
        (cache / PINNED_PYTHON['asset']).symlink_to(cached_pinned_interpreter())
        definition = builder.load_definition(CREATOR / 'definitions/creator-image-comfyui-0.35.0-linux-x86_64.json')
        cls.python = builder.compressor_python(definition, PINNED_PYTHON, cache, cls.root / 'tools')
        cls.spec = builder.load_compression(builder.COMPRESSION)
        cls.stage = cls.root / 'stage'
        golden_stage(cls.stage)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def pack(self, name, **run) -> tuple[dict, Path]:
        archive = self.root / name
        spec = {'epoch': EPOCH, 'zstd_version': self.spec['zstd_version'], 'parameters': self.spec['parameters']}
        result = subprocess.run([str(self.python), '-I', '-B', '-S', '-X', 'utf8', str(PACK), str(self.stage),
                                 str(archive), json.dumps(spec)], capture_output=True, text=True, check=True, **run)
        return json.loads(result.stdout), archive

    def test_libzstd_is_compiled_into_the_pinned_interpreter(self):
        report = builder.pack(self.stage, self.root / 'builder.tar.zst', EPOCH, self.spec, self.python)
        self.assertTrue(report['builtin'])  # No system libzstd can be loaded instead.
        self.assertEqual(report['zstd_version'], '1.5.7')
        self.assertEqual(report['implementation'], 'CPython 3.14.8 compression.zstd')
        self.assertEqual(report['parameters'], self.spec['parameters'])

    def test_golden_bytes(self):
        report, archive = self.pack('golden.tar.zst')
        self.assertEqual(sha(archive), GOLDEN_ARCHIVE)
        self.assertEqual(report['tar_sha256'], GOLDEN_TAR)
        with archive.open('rb') as stream:
            frame = stream.read(6)
        # One frame: magic, no checksum, no content size, no dictionary; window 4 MiB (level 12).
        self.assertEqual(frame, bytes.fromhex('28b52ffd0060'))

    def test_cpu_count_locale_cwd_and_system_zstd_are_irrelevant(self):
        fake = self.root / 'fake-bin'
        fake.mkdir(exist_ok=True)
        (fake / 'zstd').write_text('#!/bin/sh\necho "system zstd must not be used" >&2\nexit 97\n')
        (fake / 'zstd').chmod(0o755)
        environments = {
            'plain': {},
            'one-cpu': {'preexec_fn': lambda: os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})},
            'hostile-env': {'env': {'PATH': f'{fake}{os.pathsep}{os.environ.get("PATH", "")}', 'LANG': 'C',
                                    'LC_ALL': 'C', 'ZSTD_CLEVEL': '19', 'ZSTD_NBTHREADS': '8',
                                    'PYTHONPATH': str(fake), 'PYTHONUTF8': '0'}},
            'other-cwd': {'cwd': str(fake)},
        }
        digests = {}
        for name, run in environments.items():
            with self.subTest(name):
                report, archive = self.pack(f'{name}.tar.zst', **run)
                digests[name] = sha(archive)
                self.assertEqual(report['tar_sha256'], GOLDEN_TAR)
        self.assertEqual(set(digests.values()), {GOLDEN_ARCHIVE}, digests)

    def test_the_parameters_are_effective(self):
        """A different level changes the archive but not the tar: the compressor alone is pinned here."""
        spec = dict(self.spec, parameters=dict(self.spec['parameters'], compression_level=3))
        report = builder.pack(self.stage, self.root / 'level3.tar.zst', EPOCH, spec, self.python)
        self.assertEqual(report['tar_sha256'], GOLDEN_TAR)
        self.assertNotEqual(sha(self.root / 'level3.tar.zst'), GOLDEN_ARCHIVE)
        with tarfile.open(self.root / 'level3.tar.zst', 'r:zst') as tar:
            self.assertEqual(tar.getnames(), ['ComfyUI', 'ComfyUI/main.py', 'ComfyUI/sub', 'python', 'python/bin',
                                              'python/bin/python3', 'python/bin/python3.14'])


class ProvenanceTests(unittest.TestCase):
    """Regression (PASS 2F-D): CI builds into out/ inside the checkout, so the hosted sidecar said
    working_tree_clean: false for a clean commit. Only the builder's own output is left out."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / 'repo'
        self.repo.mkdir()
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid', GIT_COMMITTER_NAME='t',
                   GIT_COMMITTER_EMAIL='t@example.invalid')
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'src').mkdir()
        (self.repo / 'src/a.py').write_text('A = 1\n')
        (self.repo / 'README').write_text('r\n')
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-q', '-m', 'x'], check=True, env=env)
        self.cwd = Path.cwd()

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def clean(self, output, **kwargs):
        return builder.provenance('c' * 40, output, repository=self.repo, **kwargs)

    def test_the_builders_own_output_does_not_make_a_clean_checkout_dirty(self):
        out = self.repo / 'out'
        (out / 'x.staging/python').mkdir(parents=True)
        (out / 'x.tar.zst').write_bytes(b'archive')
        self.assertFalse(builder.provenance('c' * 40, None, repository=self.repo)['working_tree_clean'])  # The old bug.
        value = self.clean(out)
        self.assertEqual((value['working_tree_clean'], value['working_tree_excludes']), (True, ['out/']))
        os.chdir(self.repo)
        self.assertTrue(self.clean(Path('out'))['working_tree_clean'])  # CI's relative --output out.
        outside = Path(self.temp.name) / 'elsewhere'
        outside.mkdir()
        value = builder.provenance('c' * 40, outside, repository=Path(self.temp.name) / 'repo')
        self.assertNotIn('working_tree_excludes', value)

    def test_genuine_source_changes_are_still_reported(self):
        out = self.repo / 'out'
        out.mkdir()
        (out / 'x.tar.zst').write_bytes(b'archive')
        (self.repo / 'out-notes.txt').write_text('not the output folder\n')
        self.assertFalse(self.clean(out)['working_tree_clean'])  # An untracked file outside out/.
        (self.repo / 'out-notes.txt').unlink()
        (self.repo / 'src/a.py').write_text('A = 2\n')
        self.assertFalse(self.clean(out)['working_tree_clean'])  # A modified tracked file.
        # An --output folder that holds tracked files is source: it is never left out.
        value = self.clean(self.repo / 'src')
        self.assertFalse(value['working_tree_clean'])
        self.assertNotIn('working_tree_excludes', value)
        subprocess.run(['git', '-C', str(self.repo), 'checkout', '-q', '--', 'src/a.py'], check=True)
        (self.repo / 'src/new.py').write_text('')
        self.assertFalse(self.clean(self.repo / 'src')['working_tree_clean'])
        self.assertFalse(self.clean(self.repo)['working_tree_clean'])  # The checkout itself is never excluded.


if __name__ == '__main__':
    unittest.main()
