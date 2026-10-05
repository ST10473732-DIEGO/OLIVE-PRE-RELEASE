"""Creator runtime Option B: the NVIDIA lock split, safe wheel unpacking, the installer's direct
downloads into the staged runtime, its runtime probe, rollback, storage planning and the
manifest entry. Fixture servers only; no real wheel, runtime or GPU is used."""
import asyncio
import copy
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import unittest
from unittest import mock

from olive.services import runtime_manifest, safe_archive
from olive.services.runtime_discovery import RuntimeDiscovery
from olive.services.runtime_installer import MARKER, InstallError, RuntimeInstaller
from olive.services.secure_download import Downloader
from olive.storage.setup_state_repository import SetupStateRepository
from tests.creator_fixture import (DIRECT_LICENCE, SITE, creator_entry, direct_wheel, probe_line, runtime_archive,
                                   wheel_bytes)
from tests.setup_installer_fixture import FakeOllama, FileServer, approve, fixture_manifest, sha, tar_bytes

ROOT = Path(__file__).resolve().parents[1]
CREATOR = ROOT / 'packaging' / 'creator'
sys.path.insert(0, str(CREATOR))
import split_lock  # noqa: E402

IMAGE = 'creator-image-comfyui-0.35.0-linux-x86_64'
RELEASE_URL = 'https://github.com/ST10473732-DIEGO/get-olive'
BUNDLING = {'triton', 'torchvision', 'comfy-kitchen', 'cuda-bindings'}
PROPRIETARY = {'nvidia-cublas', 'nvidia-cuda-cupti', 'nvidia-cuda-nvrtc', 'nvidia-cuda-runtime', 'nvidia-cudnn-cu13',
               'nvidia-cufft', 'nvidia-cufile', 'nvidia-curand', 'nvidia-cusolver', 'nvidia-cusparse',
               'nvidia-cusparselt-cu13', 'nvidia-nccl-cu13', 'nvidia-nvjitlink', 'nvidia-nvshmem-cu13'}


def definition(name=IMAGE):
    return json.loads((CREATOR / 'definitions' / f'{name}.json').read_text())


class LockSplitTests(unittest.TestCase):
    def setUp(self):
        self.definition = definition()
        self.full = split_lock.parse_lock((CREATOR / self.definition['lock']).read_text())
        self.archive = split_lock.parse_lock((CREATOR / self.definition['archive_lock']).read_text())
        self.wheels = json.loads((CREATOR / self.definition['wheels']).read_text())
        self.records = {r['name']: r for r in self.wheels['packages']}

    def test_committed_split_is_consistent_for_every_definition(self):
        for _, value in split_lock.definitions():
            self.assertEqual(split_lock.check(value), [], value['id'])

    def direct(self):
        return {n for n, r in self.records.items() if r['distribution'] == 'direct'}

    def test_direct_packages_are_excluded_from_the_archive(self):
        direct = self.direct()
        # Option B+: the 14 proprietary wheels, nvtx (contradictory licence metadata), the cuda-toolkit
        # metadata package, and the four wheels found to bundle NVIDIA components. No version change.
        self.assertEqual(direct, PROPRIETARY | {'nvidia-nvtx', 'cuda-toolkit'} | BUNDLING)
        self.assertFalse(set(self.archive) & direct)
        self.assertFalse([n for n in self.archive if n.startswith('nvidia-')])
        self.assertEqual({n for n in self.archive if n.startswith('cuda-')}, {'cuda-pathfinder'})
        self.assertEqual(self.wheels['counts'], {'archive': 83, 'direct': 20})
        self.assertEqual(self.wheels['bytes'], {'archive': 1_229_508_551, 'direct': 2_518_725_343})
        self.assertEqual(len(self.archive), 83)

    def test_direct_packages_remain_required_for_the_final_runtime(self):
        direct = self.direct()
        self.assertEqual(set(self.archive) | direct, set(self.full))  # Lock union = the complete runtime set.
        self.assertEqual(len(set(self.archive)) + len(direct), len(self.full))  # No duplicate, nothing missing.
        pins = (CREATOR / self.definition['pins']).read_text()
        for name in direct:
            self.assertIn(f'{name}=={self.full[name]["version"]}', pins)  # Still part of the validated environment.
        manifest = runtime_manifest.load('1.0.0', environ={})
        entry = next(e for e in manifest['entries'] if e['id'] == 'comfyui-0.35.0-image-linux')
        listed = {w['package']: w for w in entry['direct_wheels']['linux-x86_64']}
        self.assertEqual(set(listed), direct)
        for name, wheel in listed.items():
            record = self.records[name]
            self.assertEqual((wheel['name'], wheel['url'], wheel['sha256'], wheel['size_bytes'], wheel['version']),
                             (record['filename'], record['url'], record['sha256'], record['size_bytes'], record['version']))

    def test_bundling_wheels_keep_their_exact_pins(self):
        expected = {'triton': ('3.8.0', 247_972_313), 'torchvision': ('0.29.0', 7_430_722),
                    'comfy-kitchen': ('0.2.33', 66_069_599), 'cuda-bindings': ('13.4.2', 6_972_509)}
        for name, (version, size) in expected.items():
            record = self.records[name]
            self.assertEqual((record['version'], record['size_bytes'], record['direct_reason']),
                             (version, size, 'bundles-nvidia-components'), name)
            self.assertTrue(record['direct_evidence'])
            self.assertIn(record['sha256'], self.full[name]['hashes'])
            self.assertTrue(record['filename'].endswith('.whl') and 'x86_64' in record['filename'], name)

    def test_every_hash_is_still_pinned(self):
        for name, record in self.records.items():
            self.assertIn(record['sha256'], self.full[name]['hashes'], name)
            self.assertTrue(record['url'].startswith('https://files.pythonhosted.org/'), name)
            self.assertTrue(record['url'].endswith('/' + record['filename']))
            self.assertGreater(record['size_bytes'], 0)
        for name, block in self.archive.items():
            self.assertEqual(block['hashes'], self.full[name]['hashes'])  # Verbatim blocks: every hash kept.
            self.assertEqual(block['block'], self.full[name]['block'])

    def test_direct_wheels_are_plain_site_packages_layouts(self):
        for name in self.direct():
            record = self.records[name]
            self.assertEqual(record['layout']['data_dirs'], [], name)  # No scripts/headers/data step.
            self.assertFalse([top for top in record['layout']['top_level'] if top.startswith('.') or top == '..'])
            self.assertIn('wheel_metadata_licence', record)
        self.assertEqual(self.wheels['direct_shared_paths'], [])

    def test_attribution_comes_from_each_wheel_never_one_publisher(self):
        texts = json.loads((CREATOR / self.definition['direct_licences']).read_text())['texts']
        for name in self.direct():
            record = self.records[name]
            self.assertNotIn('publisher', record)  # PASS 2F's inferred "NVIDIA Corporation" label is gone.
            self.assertIn('wheel_metadata_attribution', record)
            self.assertEqual(record['pypi_project'], f'https://pypi.org/project/{name}/{record["version"]}/')
            for licence_file in record['licence_files']:
                self.assertEqual(hashlib.sha256(texts[licence_file['sha256']].encode()).hexdigest(), licence_file['sha256'])
        self.assertIn('Philippe Tillet', self.records['triton']['wheel_metadata_attribution']['Author'])
        self.assertEqual(self.records['torchvision']['wheel_metadata_attribution']['Author'], 'PyTorch Core Team')
        self.assertIn('NOTICE', {Path(f['path']).name for f in self.records['comfy-kitchen']['licence_files']})
        manifest = runtime_manifest.load('1.0.0', environ={})
        entry = next(e for e in manifest['entries'] if e['id'] == 'comfyui-0.35.0-image-linux')
        self.assertNotIn('direct_publisher', entry)
        self.assertEqual(entry['direct_source'], 'PyPI')
        bad = copy.deepcopy(manifest)
        bad.pop('_approvals'), bad.pop('_source')
        next(e for e in bad['entries'] if e['id'] == entry['id'])['direct_publisher'] = 'NVIDIA (PyPI)'
        self.assertTrue(any('one publisher' in p for p in runtime_manifest.validate(bad)))

    def test_policy_routes_new_nvidia_packages_to_direct_download(self):
        policy = self.definition['direct_download']
        self.assertEqual(split_lock.classify('nvidia-new-thing', policy), 'direct')
        self.assertEqual(split_lock.classify('cuda_toolkit', policy), 'direct')
        self.assertEqual(split_lock.classify('cuda-pathfinder', policy), 'archive')
        self.assertEqual(split_lock.classify('torch', policy), 'archive')
        loose = copy.deepcopy(policy)
        loose['archive_allowed']['cuda-pathfinder']['spdx'] = 'LicenseRef-NVIDIA-Proprietary'
        self.assertEqual(split_lock.classify('cuda-pathfinder', loose), 'direct')  # Only open licences stay.

    def test_bundling_wheels_cannot_regress_to_the_archive(self):
        for name in sorted(BUNDLING):
            with self.subTest(name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                value = copy.deepcopy(self.definition)
                for key in ('lock', 'archive_lock', 'wheels', 'direct_licences'):
                    (root / Path(value[key]).name).write_bytes((CREATOR / value[key]).read_bytes())
                    value[key] = str(root / Path(value[key]).name)
                self.assertEqual(split_lock.classify(name, value['direct_download']), 'direct')
                self.assertEqual(split_lock.check(value), [])
                # Its block put back into the archive lock.
                archive = Path(value['archive_lock'])
                archive.write_text(archive.read_text() + self.full[name]['block'])
                self.assertTrue(any('archive lock contains direct-download' in p or 'differs' in p
                                    for p in split_lock.check(value)))
                archive.write_bytes((CREATOR / self.definition['archive_lock']).read_bytes())
                # Its record relabelled as archive.
                wheels = json.loads(Path(value['wheels']).read_text())
                next(r for r in wheels['packages'] if r['name'] == name)['distribution'] = 'archive'
                Path(value['wheels']).write_text(json.dumps(wheels))
                self.assertTrue(any('policy says direct' in p for p in split_lock.check(value)))
                # The policy entry removed: the committed split no longer matches it.
                Path(value['wheels']).write_bytes((CREATOR / self.definition['wheels']).read_bytes())
                value['direct_download']['bundles_nvidia'].pop(name)
                self.assertTrue(split_lock.check(value))

    def test_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = copy.deepcopy(self.definition)
            for key in ('lock', 'archive_lock', 'wheels', 'direct_licences'):
                (root / Path(value[key]).name).write_bytes((CREATOR / value[key]).read_bytes())
                value[key] = str(root / Path(value[key]).name)
            self.assertEqual(split_lock.check(value), [])
            # Moving a proprietary wheel back into the archive lock.
            archive = Path(value['archive_lock'])
            archive.write_text(archive.read_text() + self.full['nvidia-cublas']['block'])
            problems = split_lock.check(value)
            self.assertTrue(any('archive lock contains direct-download' in p or 'differs' in p for p in problems))
            archive.write_bytes((CREATOR / self.definition['archive_lock']).read_bytes())
            # Reclassifying it in the wheel records.
            wheels = json.loads(Path(value['wheels']).read_text())
            next(r for r in wheels['packages'] if r['name'] == 'nvidia-cudnn-cu13')['distribution'] = 'archive'
            Path(value['wheels']).write_text(json.dumps(wheels))
            self.assertTrue(any('policy says direct' in p for p in split_lock.check(value)))
            # An unpinned hash.
            next(r for r in wheels['packages'] if r['name'] == 'nvidia-cudnn-cu13').update(distribution='direct',
                                                                                            sha256='0' * 64)
            Path(value['wheels']).write_text(json.dumps(wheels))
            self.assertTrue(any('not one of the lock hashes' in p for p in split_lock.check(value)))
            # An inferred publisher label.
            wheels = json.loads((CREATOR / self.definition['wheels']).read_text())
            next(r for r in wheels['packages'] if r['name'] == 'triton')['publisher'] = 'NVIDIA Corporation'
            Path(value['wheels']).write_text(json.dumps(wheels))
            self.assertTrue(any('inferred publisher' in p for p in split_lock.check(value)))
            # A licence text that does not match its hash.
            Path(value['wheels']).write_bytes((CREATOR / self.definition['wheels']).read_bytes())
            licences = json.loads(Path(value['direct_licences']).read_text())
            first = next(iter(licences['texts']))
            licences['texts'][first] += 'tampered'
            Path(value['direct_licences']).write_text(json.dumps(licences))
            self.assertTrue(any('does not match its SHA-256' in p for p in split_lock.check(value)))

    def test_builder_refuses_a_definition_without_the_split(self):
        spec = importlib.util.spec_from_file_location('build_creator_runtime_b', CREATOR / 'build_creator_runtime.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as directory:
            value = self.definition.copy()
            value.pop('direct_download')
            path = Path(directory) / 'd.json'
            path.write_text(json.dumps(value))
            with self.assertRaises(SystemExit) as caught:
                builder.load_definition(path)
            self.assertIn('NVIDIA', str(caught.exception))


class WheelUnpackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.site = self.root / 'site'
        self.site.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def unpack(self, data, name='w.whl'):
        path = self.root / name
        path.write_bytes(data)
        return safe_archive.install_wheel(path, self.site, max_bytes=1 << 24)

    def test_installs_like_an_installer(self):
        name, data = direct_wheel()
        installed = self.unpack(data, name)
        library = self.site / 'nvidia/fixture/lib/libfixture.so.1'
        self.assertTrue(library.is_file())
        self.assertEqual(stat.S_IMODE(library.stat().st_mode) & 0o111, 0o111)  # The wheel's own exec bit.
        info = self.site / 'nvidia_fixture_cu13-1.0.dist-info'
        self.assertEqual((info / 'INSTALLER').read_text(), 'olive-setup\n')
        self.assertIn('nvidia_fixture_cu13-1.0.dist-info/INSTALLER,sha256=', (info / 'RECORD').read_text())
        self.assertIn('nvidia/fixture/lib/libfixture.so.1', installed)
        # importlib.metadata reads it like a pip-installed distribution.
        from importlib.metadata import distributions
        found = {d.metadata['Name']: d for d in distributions(path=[str(self.site)])}
        self.assertEqual(found['nvidia-fixture-cu13'].version, '1.0')
        self.assertIn('LicenseRef-NVIDIA-Proprietary', found['nvidia-fixture-cu13'].metadata['License-Expression'])

    def test_record_mismatch_is_refused(self):
        data = wheel_bytes('nvidia-bad', '1.0', {'nvidia/bad/x.so': b'real'},
                           record_override={'nvidia/bad/x.so': 'sha256=' + 'A' * 43})
        with self.assertRaises(safe_archive.ArchiveError):
            self.unpack(data)

    def test_unrecorded_member_is_refused(self):
        data = wheel_bytes('nvidia-bad', '1.0', {'nvidia/bad/x.so': b'real'}, unrecorded={'nvidia/bad/x.so'})
        with self.assertRaisesRegex(safe_archive.ArchiveError, 'not recorded'):
            self.unpack(data)

    def test_path_traversal_is_refused(self):
        data = wheel_bytes('nvidia-evil', '1.0', {'nvidia/evil/x.so': b'x'}, extra_members={'../../escape.so': b'x'})
        with self.assertRaises(safe_archive.ArchiveError):
            self.unpack(data)
        self.assertFalse((self.root.parent / 'escape.so').exists())

    def test_scripts_and_data_parts_are_refused_not_guessed(self):
        for part in ('scripts', 'headers', 'data'):
            data = wheel_bytes('nvidia-data', '1.0', {f'nvidia_data-1.0.data/{part}/x': b'#!/bin/sh\n'})
            with self.assertRaisesRegex(safe_archive.ArchiveError, 'install step'):
                self.unpack(data, f'{part}.whl')

    def test_purelib_and_platlib_parts_land_in_site_packages(self):
        data = wheel_bytes('nvidia-pl', '1.0', {'nvidia_pl-1.0.data/platlib/nvidia/pl/x.so': b'x',
                                                'nvidia_pl-1.0.data/purelib/nvidia/pl/y.py': b'y'})
        self.unpack(data)
        self.assertTrue((self.site / 'nvidia/pl/x.so').is_file())
        self.assertTrue((self.site / 'nvidia/pl/y.py').is_file())

    def test_never_overwrites_or_writes_through_a_link(self):
        (self.site / 'nvidia/fixture/lib').mkdir(parents=True)
        (self.site / 'nvidia/fixture/lib/libfixture.so.1').write_bytes(b'existing')
        name, data = direct_wheel()
        with self.assertRaisesRegex(safe_archive.ArchiveError, 'replace an existing file'):
            self.unpack(data, name)
        self.assertEqual((self.site / 'nvidia/fixture/lib/libfixture.so.1').read_bytes(), b'existing')
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        site2 = self.root / 'site2'
        site2.mkdir()
        (site2 / 'nvidia').symlink_to(other.name)
        path = self.root / name
        with self.assertRaisesRegex(safe_archive.ArchiveError, 'through a link'):
            safe_archive.install_wheel(path, site2, max_bytes=1 << 24)
        self.assertEqual(os.listdir(other.name), [])


class CreatorInstallCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home, self.profile = self.root / 'home', self.root / 'profile'
        self.home.mkdir()
        self.profile.mkdir()
        self.env = {'XDG_DATA_HOME': str(self.root / 'xdg'), 'OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP': '1'}
        self.files = FileServer().__enter__()
        self.ollama = FakeOllama().__enter__()
        self.probe = self.root / 'probe-output.txt'
        self.probe.write_text(probe_line() + '\n')
        self.direct = [direct_wheel('nvidia-cublas-fixture'), direct_wheel('nvidia-cudnn-fixture')]
        self.archive = runtime_archive(self.probe, self.direct)
        self.registered = []
        self.write_manifest()

    def write_manifest(self, entry=None):
        manifest = fixture_manifest(self.files, self.ollama, tar_bytes({'bin/ollama': b'#!/bin/sh\n'}, executable={'bin/ollama'}))
        manifest['entries'] = [e for e in manifest['entries'] if e['provides'] != 'image-engine']
        manifest['entries'].append(entry or creator_entry(self.files, self.archive, self.direct))
        approve(manifest, ['fixture-creator-image'])
        self.manifest_path = self.root / 'manifest.json'
        self.manifest_path.write_text(json.dumps(manifest))
        self.installer = self.make()

    def make(self, disk=None, mounts=None):
        self.discovery = RuntimeDiscovery(self.profile, environ=self.env, platform='linux', home=self.home,
                                          install_root=self.root / 'install', which=lambda name: None)
        installer = RuntimeInstaller(self.profile, self.discovery, ollama_host=self.ollama.base, environ=self.env,
                                     platform='linux', home=self.home, target='linux-x86_64',
                                     manifest=runtime_manifest.load(environ=self.env, path=self.manifest_path),
                                     disk_usage=disk or (lambda p: type('U', (), {'free': 10 ** 12})()),
                                     runtime_registered=lambda n, l: self.registered.append(n),
                                     **({'mounts': mounts} if mounts else {}))
        installer.module_available = lambda name: False
        return installer

    async def asyncTearDown(self):
        await self.installer.close()
        await asyncio.to_thread(self.files.__exit__, None, None, None)
        await asyncio.to_thread(self.ollama.__exit__, None, None, None)
        self.temp.cleanup()

    @property
    def runtime(self):
        return self.root / 'xdg/olive/runtime/comfy'

    @property
    def downloads(self):
        return self.root / 'xdg/olive/temp/downloads'

    async def install(self, entries=('fixture-creator-image',)):
        job = await self.installer.start('creator', list(entries))
        await self.installer.jobs[job['job_id']].task
        return self.installer.progress(job['job_id'])['items'][0]

    def leftovers(self):
        parent = self.root / 'xdg/olive/runtime'
        return sorted(p.name for p in parent.iterdir()) if parent.exists() else []


class OptionBInstallTests(CreatorInstallCase):
    async def test_archive_plus_direct_wheels_become_one_registered_runtime(self):
        plan = await self.installer.plan('creator')
        self.assertIn('fixture-creator-image', plan['offered'])
        public = next(i for i in plan['items'] if i['slot'] == 'image-engine')['entry']
        self.assertEqual([d['package'] for d in public['direct_downloads']], ['nvidia-cublas-fixture', 'nvidia-cudnn-fixture'])
        self.assertEqual(public['download_bytes'], len(self.archive) + sum(len(d) for _, d in self.direct))
        item = await self.install()
        self.assertEqual(item['state'], 'done', item)
        site = self.runtime / SITE
        self.assertTrue((site / 'nvidia/cublas/lib/libcublas.so.1').is_file())  # Beside torch, as its RPATH expects.
        self.assertTrue((site / 'torch/__init__.py').is_file())
        self.assertEqual(stat.S_IMODE((site / 'torch/bin/torch_shm_manager').stat().st_mode), 0o755)  # Archive modes kept.
        self.assertEqual(stat.S_IMODE((self.runtime / 'ComfyUI/main.py').stat().st_mode), 0o644)
        marker = json.loads((self.runtime / MARKER).read_text())
        self.assertEqual(marker['archive']['sha256'], sha(self.archive))
        self.assertEqual(sorted(w['sha256'] for w in marker['direct_wheels']), sorted(sha(d) for _, d in self.direct))
        self.assertEqual(marker['comfyui']['commit'], '40c4fcdf513a4523e39d54a9d391908af8df8171')
        self.assertEqual(marker['product_version'], '1.0.0')
        self.assertEqual(marker['platform'], 'linux-x86_64')
        self.assertTrue(marker['verified']['cuda_available'])
        self.assertNotIn(str(self.root), json.dumps(marker))  # Portable: no personal paths.
        self.assertEqual(self.registered, ['comfy'])
        located = self.discovery.resolve()['comfy']
        self.assertEqual(located.paths['python'], str(self.runtime / 'python/bin/python3'))
        state, _ = SetupStateRepository(self.profile).load()
        self.assertEqual(len(state['installed']['fixture-creator-image']['direct_wheels']), 2)
        self.assertEqual(list(self.downloads.iterdir()), [])  # Everything verified and unpacked was removed.
        self.assertEqual(self.leftovers(), ['comfy'])

    async def test_install_marker_records_inputs_and_only_external_provenance(self):
        self.assertEqual((await self.install())['state'], 'done')
        marker = json.loads((self.runtime / MARKER).read_text())
        self.assertNotIn('olive_source_commit', marker)  # The fixture manifest supplies none; none is invented.
        self.assertNotIn('olive_source_commit', marker['runtime'])
        self.assertEqual(marker['inputs']['definition_sha256'], 'd' * 64)
        self.assertEqual(marker['inputs']['source_date_epoch'], 1788930166)
        # A release manifest that records the build's source commit passes it through.
        await self.installer.uninstall('fixture-creator-image')
        entry = creator_entry(self.files, self.archive, self.direct)
        entry['source']['olive_source_commit'] = 'e' * 40
        self.write_manifest(entry)
        self.assertEqual((await self.install())['state'], 'done')
        self.assertEqual(json.loads((self.runtime / MARKER).read_text())['olive_source_commit'], 'e' * 40)

    async def test_direct_wheels_use_only_their_own_host_list(self):
        seen = []
        real = Downloader.fetch

        def fetch(downloader, artefact, **kwargs):
            seen.append((artefact.name, artefact.hosts))
            return real(downloader, artefact, **kwargs)
        with mock.patch.object(Downloader, 'fetch', fetch):
            self.assertEqual((await self.install())['state'], 'done')
        entry = self.installer.entry('fixture-creator-image')
        hosts = dict(seen)
        self.assertEqual(hosts['creator-image.tar.gz'], tuple(entry['source']['hosts']))
        for name, _ in self.direct:
            self.assertEqual(hosts[name], tuple(entry['direct_hosts']))
        # The release manifest pins PyPI as the only direct host, separate from the archive's.
        release = runtime_manifest.load('1.0.0', environ={})
        image = next(e for e in release['entries'] if e['id'] == 'comfyui-0.35.0-image-linux')
        self.assertEqual(image['direct_hosts'], ['files.pythonhosted.org'])
        bad = copy.deepcopy(image)
        bad['direct_wheels']['linux-x86_64'][0]['url'] = bad['direct_wheels']['linux-x86_64'][0]['url'].replace(
            'files.pythonhosted.org', 'olive.example')
        self.assertFalse(runtime_manifest._direct_complete(bad, 'linux-x86_64'))

    async def test_archive_hash_mismatch_installs_nothing(self):
        entry = creator_entry(self.files, self.archive, self.direct)
        entry['sha256'] = sha(b'other')
        self.write_manifest(entry)
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'checksum_mismatch'))
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(self.registered, [])

    async def test_one_wheel_hash_mismatch_installs_nothing_and_keeps_the_archive(self):
        entry = creator_entry(self.files, self.archive, self.direct)
        entry['direct_wheels']['linux-x86_64'][1]['sha256'] = sha(b'other')
        self.write_manifest(entry)
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'checksum_mismatch'))
        self.assertEqual(self.leftovers(), [])
        self.assertTrue((self.downloads / sha(self.archive)).is_file())  # Verified bytes stay for a retry.

    async def test_interrupted_wheel_download_resumes_on_retry(self):
        name, data = self.direct[1]
        self.files.drop_after['/pypi/' + name] = 100
        with mock.patch('olive.services.secure_download.RETRIES', 1):
            item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'network'))
        self.assertEqual(self.leftovers(), [])
        job = await self.installer.retry(self.installer.progress()['job_id'])
        await self.installer.jobs[job['job_id']].task
        self.assertEqual(self.installer.progress(job['job_id'])['items'][0]['state'], 'done')
        ranges = [r for p, r in self.files.requests if p == '/pypi/' + name]
        self.assertTrue(any(r and not r.startswith('bytes=0-') for r in ranges), ranges)  # Resumed, not restarted.

    async def test_partial_archive_is_refused(self):
        entry = creator_entry(self.files, self.archive, self.direct)
        self.files.files['/creator-image.tar.gz'] = self.archive[:len(self.archive) // 2]
        entry['sha256'], entry['size_bytes'] = sha(self.archive[:len(self.archive) // 2]), len(self.archive) // 2
        self.write_manifest(entry)  # A truncated archive with a matching pin: verification passes, extraction must not.
        self.files.files['/creator-image.tar.gz'] = self.archive[:len(self.archive) // 2]
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'unsafe_archive'))
        self.assertEqual(self.leftovers(), [])

    async def test_disk_full_before_install_refuses_to_start(self):
        self.installer = self.make(disk=lambda p: type('U', (), {'free': 1000})())
        with self.assertRaises(InstallError) as caught:
            await self.installer.start('creator', ['fixture-creator-image'])
        self.assertEqual(caught.exception.code, 'insufficient_space')
        self.assertFalse(self.downloads.exists() and list(self.downloads.iterdir()))

    async def test_disk_full_while_staging_rolls_back(self):
        real = safe_archive._copy
        calls = []

        def copy_(source, target, limit, budget, digest=None):
            if 'nvidia' in str(target):
                calls.append(target)
                raise OSError(errno.ENOSPC, 'No space left on device')
            return real(source, target, limit, budget, digest)
        with mock.patch.object(safe_archive, '_copy', copy_):
            item = await self.install()
        self.assertTrue(calls)
        self.assertEqual((item['state'], item['error']), ('failed', 'unsafe_archive'))
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(self.registered, [])

    async def test_cancel_then_restart_completes(self):
        self.files.slow = 0.02
        job = await self.installer.start('creator', ['fixture-creator-image'])
        for _ in range(200):
            if self.installer.progress(job['job_id'])['items'][0]['state'] == 'downloading':
                break
            await asyncio.sleep(.01)
        self.installer.cancel(job['job_id'])
        await self.installer.jobs[job['job_id']].task
        self.assertEqual(self.installer.progress(job['job_id'])['state'], 'cancelled')
        self.assertEqual(self.leftovers(), [])
        self.files.slow = 0
        retried = await self.installer.retry(job['job_id'])
        await self.installer.jobs[retried['job_id']].task
        self.assertEqual(self.installer.progress(job['job_id'])['items'][0]['state'], 'done')

    async def test_malicious_wheel_path_traversal_is_refused(self):
        evil = ('nvidia_evil-1.0-py3-none-any.whl',
                wheel_bytes('nvidia-evil', '1.0', {'nvidia/evil/x.so': b'x'}, extra_members={'../../../evil.so': b'x'}))
        self.direct = [self.direct[0], evil]
        self.archive = runtime_archive(self.probe, self.direct)
        self.write_manifest()
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'unsafe_archive'))
        self.assertEqual(self.leftovers(), [])
        self.assertFalse(list(self.root.rglob('evil.so')))

    async def test_an_archive_that_already_carries_nvidia_wheels_is_refused(self):
        self.archive = runtime_archive(self.probe, self.direct, extra={
            f'{SITE}/nvidia_cublas_fixture-1.0.dist-info/METADATA': b'Name: nvidia-cublas-fixture\n'})
        self.write_manifest()
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'unsafe_archive'))
        self.assertIn('already contains', item['message'])
        self.assertEqual(self.leftovers(), [])

    async def test_an_archive_built_for_other_cuda_wheels_is_refused(self):
        self.archive = runtime_archive(self.probe, self.direct, declared=[('nvidia_other-1.0.whl', '0' * 64)])
        self.write_manifest()
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'archive_mismatch'))
        self.assertEqual(self.leftovers(), [])

    async def test_symlink_destination_is_never_followed(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.root / 'xdg/olive/runtime').mkdir(parents=True)
        self.runtime.symlink_to(outside, target_is_directory=True)
        plan = await self.installer.plan('creator')
        self.assertEqual(next(i for i in plan['items'] if i['slot'] == 'image-engine')['action'], 'choose')
        self.assertEqual(os.listdir(outside), [])

    async def test_an_existing_user_runtime_is_never_replaced(self):
        (self.runtime / 'ComfyUI').mkdir(parents=True)
        (self.runtime / 'ComfyUI/my-workflow.json').write_text('{}')
        plan = await self.installer.plan('creator')
        row = next(i for i in plan['items'] if i['slot'] == 'image-engine')
        self.assertEqual(row['action'], 'choose')
        self.assertNotIn('fixture-creator-image', plan['offered'])
        with self.assertRaises(InstallError):
            await self.installer.start('creator', ['fixture-creator-image'])
        self.assertEqual(os.listdir(self.runtime / 'ComfyUI'), ['my-workflow.json'])

    async def test_cuda_unavailable_fails_truthfully_and_retry_reuses_the_downloads(self):
        self.probe.write_text(probe_line(cuda_available=False) + '\n')
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'cuda_unavailable'))
        self.assertIn('NVIDIA GPU', item['message'])
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(self.registered, [])
        self.assertFalse(self.discovery.resolve()['comfy'].found)
        before = len(self.files.requests)
        self.probe.write_text(probe_line() + '\n')
        job = await self.installer.retry(self.installer.progress()['job_id'])
        await self.installer.jobs[job['job_id']].task
        self.assertEqual(self.installer.progress(job['job_id'])['items'][0]['state'], 'done')
        self.assertEqual(len(self.files.requests), before)  # Verified downloads were kept: nothing fetched again.

    async def test_torch_import_failure(self):
        self.probe.write_text(probe_line(stage='torch', error='ImportError') + '\n')
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'runtime_unhealthy'))
        self.assertIn('PyTorch', item['message'])
        self.assertEqual(self.leftovers(), [])

    async def test_comfyui_health_failure(self):
        self.probe.write_text(probe_line(stage='comfyui', error='ModuleNotFoundError') + '\n')
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'runtime_unhealthy'))
        self.assertIn('comfyui', item['message'])

    async def test_imports_from_outside_the_runtime_fail(self):
        self.probe.write_text(probe_line(leaks=['/usr/lib/python3/site-packages/numpy/__init__.py']) + '\n')
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'runtime_unhealthy'))
        self.assertIn('outside', item['message'])

    async def test_an_interpreter_that_prints_nothing_fails(self):
        self.probe.write_text('')
        item = await self.install()
        self.assertEqual((item['state'], item['error']), ('failed', 'runtime_unhealthy'))

    async def test_probe_runs_isolated_without_inherited_python_settings(self):
        captured = {}
        real = __import__('subprocess').Popen

        def popen(arguments, **kwargs):
            captured.update(arguments=arguments, env=kwargs.get('env'), cwd=kwargs.get('cwd'))
            return real(arguments, **kwargs)
        with mock.patch.dict(os.environ, {'PYTHONPATH': '/somewhere', 'LD_LIBRARY_PATH': '/x'}), \
                mock.patch('olive.services.runtime_installer.subprocess.Popen', popen):
            self.assertEqual((await self.install())['state'], 'done')
        self.assertEqual(captured['arguments'][1:3], ['-I', '-B'])
        self.assertNotIn('PYTHONPATH', captured['env'])
        self.assertNotIn('LD_LIBRARY_PATH', captured['env'])
        self.assertEqual(captured['env']['PYTHONNOUSERSITE'], '1')

    async def test_flux_model_absent_keeps_reimagine_not_ready(self):
        self.assertEqual((await self.install())['state'], 'done')
        plan = await self.installer.plan('creator')
        reimagine = next(f for f in plan['features'] if f['id'] == 'reimagine')
        self.assertEqual(reimagine['missing'], ['image-model'])
        self.assertNotEqual(reimagine['state'], 'ready')

    async def test_uninstall_removes_only_the_owned_runtime(self):
        self.assertEqual((await self.install())['state'], 'done')
        neighbour = self.root / 'xdg/olive/runtime/video-comfy/keep.txt'
        neighbour.parent.mkdir(parents=True)
        neighbour.write_text('user')
        models = self.root / 'xdg/olive/models/comfy/diffusion_models/m.safetensors'
        models.parent.mkdir(parents=True)
        models.write_text('weights')
        outside = self.root / 'outside.txt'
        outside.write_text('keep')
        (self.runtime / 'link-out').symlink_to(outside)
        result = await self.installer.uninstall('fixture-creator-image')
        self.assertEqual(result, {'removed': 'fixture-creator-image'})
        self.assertFalse(self.runtime.exists())
        self.assertEqual(neighbour.read_text(), 'user')
        self.assertEqual(models.read_text(), 'weights')
        self.assertEqual(outside.read_text(), 'keep')  # A link inside is removed, never followed.
        self.assertFalse(self.discovery.resolve()['comfy'].found)
        state, _ = SetupStateRepository(self.profile).load()
        self.assertNotIn('fixture-creator-image', state['installed'])


class StoragePlanTests(CreatorInstallCase):
    """The Creator runtime's bytes against the reference machine's volume layouts (no real data)."""

    def layout(self, mounts, free):
        table = sorted(((os.path.realpath(p), d) for p, d in mounts.items()), key=lambda r: len(r[0]), reverse=True)
        for path in mounts:
            Path(path).mkdir(parents=True, exist_ok=True)

        def usage(path):
            real = os.path.realpath(path)
            device = next(d for point, d in table if real == point or real.startswith(point + '/'))
            return type('U', (), {'free': free[device]})()
        self.installer = self.make(disk=usage, mounts=lambda: table)

    def rows(self):
        return {r['label']: r for r in self.installer.space(['fixture-creator-image'])['volumes']}

    async def test_same_filesystem(self):
        self.layout({str(self.root): 'root'}, {'root': 10 ** 12})
        rows = self.rows()
        margin = __import__('olive.services.runtime_installer', fromlist=['MARGIN']).MARGIN
        download = len(self.archive) + sum(len(d) for _, d in self.direct)
        self.assertEqual(list(rows), ['Downloads and OLIVE runtimes'])
        self.assertEqual(rows['Downloads and OLIVE runtimes']['required_bytes'], margin + download + (1 << 20))

    async def test_separate_runtime_volume_and_bind_mount(self):
        data = self.root / 'xdg/olive'
        self.layout({str(self.root): 'root', str(data / 'runtime'): 'olive-data', str(data / 'models'): 'olive-data'},
                    {'root': 10 ** 12, 'olive-data': 10 ** 12})
        rows = self.rows()
        margin = __import__('olive.services.runtime_installer', fromlist=['MARGIN']).MARGIN
        download = len(self.archive) + sum(len(d) for _, d in self.direct)
        self.assertEqual(rows['Downloads']['required_bytes'], margin + download)  # Archive + NVIDIA wheels.
        self.assertEqual(rows['OLIVE runtimes']['required_bytes'], margin + (1 << 20))  # Archive + wheels, unpacked.

    async def test_low_space_runtime_volume_refuses_while_root_has_room(self):
        data = self.root / 'xdg/olive'
        self.layout({str(self.root): 'root', str(data / 'runtime'): 'olive-data'}, {'root': 10 ** 12, 'olive-data': 1000})
        plan = await self.installer.plan('creator', ['fixture-creator-image'])
        self.assertEqual([v['label'] for v in plan['totals']['volumes'] if not v['enough']], ['OLIVE runtimes'])
        with self.assertRaises(InstallError) as caught:
            await self.installer.start('creator', ['fixture-creator-image'])
        self.assertEqual(caught.exception.code, 'insufficient_space')

    async def test_staging_and_rename_stay_beside_the_bind_mounted_destination(self):
        renames, real = [], os.rename

        def rename(source, destination):
            renames.append((Path(source), Path(destination)))
            return real(source, destination)
        with mock.patch('olive.services.runtime_installer.os.rename', rename):
            self.assertEqual((await self.install())['state'], 'done')
        moved = [(s, d) for s, d in renames if d == self.runtime]
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0][0].parent, self.runtime.parent)  # Same folder, same filesystem: never EXDEV.
        self.assertTrue(moved[0][0].name.startswith('.comfy.olive-staging-'))


class ReleaseManifestEntryTests(unittest.TestCase):
    def setUp(self):
        self.manifest = runtime_manifest.load('1.0.0', environ={})
        self.entry = next(e for e in self.manifest['entries'] if e['id'] == 'comfyui-0.35.0-image-linux')

    def test_entry_records_the_published_archive(self):
        entry = self.entry
        self.assertEqual(entry['artefact_state'], 'published')
        self.assertTrue(entry['enabled'])
        self.assertIsNone(entry['reason'])
        self.assertEqual(entry['source']['url'], RELEASE_URL + '/releases/download/creator-runtime-1.0.0-ecdb6702/'
                         + IMAGE + '.tar.zst')
        self.assertEqual(entry['source']['release'], RELEASE_URL + '/releases/tag/creator-runtime-1.0.0-ecdb6702')
        self.assertTrue(runtime_manifest.url_allowed(entry['source']['url'], entry['source']['hosts']))
        self.assertEqual(entry['sha256'], 'ecdb670232fc643a90e18acdd749763de43d9a4f277439f26cd35cf4cfff0d81')
        self.assertEqual(entry['size_bytes'], 1_121_452_201)
        self.assertGreater(entry['install']['installed_bytes'], entry['size_bytes'])
        self.assertEqual(entry['install']['direct_wheels_target'], SITE)
        self.assertEqual(entry['install']['verify'], 'comfyui-cuda')
        self.assertEqual(entry['validated_platforms'], ['linux-x86_64'])
        self.assertTrue(entry['licence']['identified'] and entry['licence']['engineering_reviewed'])
        self.assertEqual(runtime_manifest.release_state(entry, self.manifest), 'release_approved')
        self.assertTrue(runtime_manifest.offerable(entry, 'linux-x86_64', self.manifest))
        for target in ('windows-x86_64', 'macos-arm64'):  # Linux only: no Windows or macOS Creator engine.
            self.assertFalse(runtime_manifest.offerable(entry, target, self.manifest), target)
        self.assertEqual(self.manifest['_approvals'][entry['id']]['fingerprint'], runtime_manifest.fingerprint(entry))
        self.assertIn('LicenseRef-NVIDIA-Proprietary', {w['licence'] for w in entry['direct_wheels']['linux-x86_64']})
        public = runtime_manifest.public_entry(entry, 'linux-x86_64', False, self.manifest)
        self.assertTrue(public['installable'])
        self.assertTrue(public['validated'])
        self.assertEqual(public['artefact_state'], 'published')
        self.assertEqual(public['direct_download_bytes'], 2_518_725_343)
        self.assertEqual(public['download_bytes'], 1_121_452_201 + 2_518_725_343)  # Archive plus direct wheels.
        self.assertEqual(len(public['direct_downloads']), 20)
        self.assertEqual((public['direct_source'], public['direct_summary']), ('PyPI', 'including NVIDIA CUDA dependencies'))
        self.assertNotIn('direct_publisher', public)
        self.assertIsNone(public['reason'])

    def test_unpublished_cannot_be_enabled_or_given_a_url(self):
        for change in ({'enabled': True}, {'url': 'https://example.invalid/creator.tar.zst'}):
            bad = copy.deepcopy(self.manifest)
            bad.pop('_approvals'), bad.pop('_source')
            entry = next(e for e in bad['entries'] if e['id'] == 'comfyui-0.35.0-image-linux')
            entry.update(artefact_state='built_validated_unpublished', enabled=False, reason='Not yet published.')
            entry['source']['url'] = None
            if 'url' in change:
                entry['source']['url'] = change['url']
            entry.update({k: v for k, v in change.items() if k != 'url'})
            self.assertTrue(any('unpublished' in p for p in runtime_manifest.validate(bad)), change)

    def test_direct_wheels_are_part_of_the_release_fingerprint(self):
        published = copy.deepcopy(self.entry)
        before = runtime_manifest.fingerprint(published)
        published['direct_wheels']['linux-x86_64'][0]['sha256'] = '0' * 64
        self.assertNotEqual(runtime_manifest.fingerprint(published), before)
        # Entries without direct downloads keep the fingerprints the owner approved.
        for entry in self.manifest['entries']:
            if entry['id'] in self.manifest['_approvals']:
                self.assertTrue(runtime_manifest.release_approved(entry, self.manifest), entry['id'])

    def test_a_moved_archive_needs_a_new_owner_approval(self):
        manifest = copy.deepcopy(self.manifest)
        entry = next(e for e in manifest['entries'] if e['id'] == 'comfyui-0.35.0-image-linux')
        entry['source'].update(url='https://releases.example.invalid/' + IMAGE + '.tar.zst',
                               hosts=['releases.example.invalid'])
        self.assertTrue(runtime_manifest.complete(entry, 'linux-x86_64'))
        self.assertFalse(runtime_manifest.offerable(entry, 'linux-x86_64', manifest))  # The approval lapsed.
        manifest['_approvals'][entry['id']] = {'id': entry['id'], 'fingerprint': runtime_manifest.fingerprint(entry),
                                               'scope': 'public-release', 'approved_by': 'test', 'date': 'x',
                                               'product_version': '1.0.0'}
        self.assertTrue(runtime_manifest.offerable(entry, 'linux-x86_64', manifest))
        self.assertEqual(runtime_manifest.download_bytes(entry, 'linux-x86_64'), entry['size_bytes'] + 2_518_725_343)


if __name__ == '__main__':
    unittest.main()
