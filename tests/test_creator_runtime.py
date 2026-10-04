"""Creator runtime: definitions and locks are pinned; a fixture build is deterministic and installs
through the normal verified archive path (no network, no real PyTorch)."""
import asyncio
import base64
import csv
import functools
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile

from olive.services import runtime_manifest
from olive.services.runtime_discovery import RuntimeDiscovery, valid
from olive.services.runtime_installer import MARKER, RuntimeInstaller
from tests.creator_fixture import probe_line
from tests.setup_installer_fixture import FakeOllama, FileServer, approve, fixture_manifest, tar_bytes

ROOT = Path(__file__).resolve().parents[1]
CREATOR = ROOT / 'packaging' / 'creator'
sys.path.insert(0, str(CREATOR))
import split_lock  # noqa: E402
spec = importlib.util.spec_from_file_location('build_creator_runtime', CREATOR / 'build_creator_runtime.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
HAS_PIP = importlib.util.find_spec('pip') is not None
HAS_ENSUREPIP = importlib.util.find_spec('ensurepip') is not None
EPOCH = 1788930166  # Committer time of the pinned ComfyUI v0.35.0 commit (the definitions' source_date_epoch).
PINNED_PYTHON = json.loads((ROOT / 'packaging/backend/python-runtime.json').read_text())['targets']['linux-x86_64']


@functools.cache
def cached_pinned_interpreter() -> Path | None:
    """The pinned python-build-standalone archive (the real compressor) when a local build cache
    already holds it; tests never download it."""
    import platform
    if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'AMD64'):
        return None
    for folder in (CREATOR / '.cache', ROOT / 'packaging/backend/.cache'):
        path = folder / PINNED_PYTHON['asset']
        if path.is_file() and builder.sha256(path) == PINNED_PYTHON['sha256']:
            return path
    return None


def host_compression(folder: Path) -> Path:
    """The pinned spec with this Python's libzstd version, for packing with --fixture-compressor-python
    where the pinned interpreter is not cached (the parameters stay the pinned ones)."""
    from compression import zstd
    spec = json.loads(builder.COMPRESSION.read_text())
    spec['zstd_version'] = zstd.zstd_version
    path = folder / 'compression-host.json'
    path.write_text(json.dumps(spec))
    return path


def wheel(name='olivefixture', version='1.0', extra: dict[str, bytes] | None = None) -> bytes:
    """A minimal valid pure-Python wheel (extra adds files, e.g. entry_points.txt)."""
    files = {f'{name}/__init__.py': b'VALUE = 1\n',
             f'{name}-{version}.dist-info/METADATA': (f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n'
                                                     'License-Expression: MIT\n\n').encode(),
             f'{name}-{version}.dist-info/licenses/LICENSE': b'MIT fixture licence text\n',
             f'{name}-{version}.dist-info/WHEEL': b'Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
             **(extra or {})}
    record = io.StringIO()
    writer = csv.writer(record, lineterminator='\n')
    for path, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
        writer.writerow([path, f'sha256={digest}', len(data)])
    writer.writerow([f'{name}-{version}.dist-info/RECORD', '', ''])
    files[f'{name}-{version}.dist-info/RECORD'] = record.getvalue().encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for path, data in files.items():
            info = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            archive.writestr(info, data)
    return buffer.getvalue()


class DefinitionTests(unittest.TestCase):
    def test_definitions_pin_sources_and_locks(self):
        definitions = sorted((CREATOR / 'definitions').glob('*.json'))
        self.assertEqual({d.stem for d in definitions}, {'creator-image-comfyui-0.35.0-linux-x86_64',
                                                         'creator-video-comfyui-0.35.0-linux-x86_64'})
        manifest = runtime_manifest.load('1.0.0', environ={})
        for path in definitions:
            definition = builder.load_definition(path)
            self.assertRegex(definition['comfyui']['commit'], r'^[0-9a-f]{40}$')
            for node in definition['custom_nodes']:
                self.assertRegex(node['commit'], r'^[0-9a-f]{40}$')
            lock = (CREATOR / definition['lock']).read_text()
            pins = [l for l in (CREATOR / definition['pins']).read_text().splitlines() if l and not l.startswith('#')]
            locked = dict(re.findall(r'^([a-z0-9._-]+)==(\S+)', lock, re.M))
            for pin in pins:
                name, version = pin.split('==')
                self.assertEqual(locked.get(name), version, pin)  # The lock is exactly the validated environment.
            requirements = re.split(r'\n(?=[a-z0-9])', lock.split('\n', 3)[3].strip())
            for requirement in requirements:
                self.assertIn('--hash=sha256:', requirement, requirement[:60])
            self.assertIn('torch==2.14.0', lock)
            # The manifest entry it feeds names the same destination and runtime registration.
            role = definition['role']
            entry = next(e for e in manifest['entries'] if e['id'] == f'comfyui-0.35.0-{role}-linux')
            self.assertEqual(entry['install']['destination'], definition['destination'])
            self.assertEqual(entry['install']['register'], definition['register'])
            self.assertFalse(entry['enabled'])  # Not built, verified or published yet.
            self.assertIsNone(entry['source']['url'])
        video = builder.load_definition(CREATOR / 'definitions/creator-video-comfyui-0.35.0-linux-x86_64.json')
        self.assertEqual([n['name'] for n in video['custom_nodes']], ['ComfyUI-GGUF-Loader'])
        image = builder.load_definition(CREATOR / 'definitions/creator-image-comfyui-0.35.0-linux-x86_64.json')
        self.assertEqual(image['custom_nodes'], [])


@unittest.skipUnless(HAS_PIP, 'pip is needed to install the fixture wheel')
class FixtureBuildTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        python = self.root / 'fixture-python'
        (python / 'bin').mkdir(parents=True)
        (python / 'lib/python3.14/site-packages').mkdir(parents=True)
        (python / 'lib/python3.14/LICENSE.txt').write_text('PSF fixture licence\n')
        stub = python / 'bin/python3'
        self.probe = self.root / 'probe.txt'
        self.probe.write_text(probe_line() + '\n')
        stub.write_text(f'#!/bin/sh\ncat "{self.probe}"\n')  # Answers setup's runtime check.
        stub.chmod(0o755)
        comfy = self.root / 'fixture-comfyui'
        comfy.mkdir()
        (comfy / 'main.py').write_text('print("fixture ComfyUI")\n')
        (comfy / 'comfyui_version.py').write_text('__version__ = "0.35.0"\n')
        (comfy / 'LICENSE').write_text('GNU GENERAL PUBLIC LICENSE Version 3 (fixture)\n')
        (comfy / 'tests').mkdir()
        (comfy / 'tests/test_x.py').write_text('')
        self.wheelhouse = self.root / 'wheels'
        self.wheelhouse.mkdir()
        data = wheel()
        (self.wheelhouse / 'olivefixture-1.0-py3-none-any.whl').write_bytes(data)
        # An NVIDIA-style wheel in the complete lock: the archive must leave it out.
        nvidia = wheel('nvidia_fixture_cu13', '1.0')
        (self.wheelhouse / 'nvidia_fixture_cu13-1.0-py3-none-any.whl').write_bytes(nvidia)
        self.nvidia = nvidia
        lock = self.root / 'lock.txt'
        lock.write_text('# fixture lock\n'
                        f'nvidia-fixture-cu13==1.0 \\\n    --hash=sha256:{hashlib.sha256(nvidia).hexdigest()}\n'
                        f'olivefixture==1.0 \\\n    --hash=sha256:{hashlib.sha256(data).hexdigest()}\n')
        definition = json.loads((CREATOR / 'definitions/creator-image-comfyui-0.35.0-linux-x86_64.json').read_text())
        definition.update(id='creator-image-fixture', lock=str(lock), archive_lock=str(self.root / 'lock.archive.txt'),
                          wheels=str(self.root / 'wheels.json'), direct_licences=str(self.root / 'licences.json'))
        licence_text = 'NVIDIA fixture licence text\n'
        licence_digest = hashlib.sha256(licence_text.encode()).hexdigest()
        (self.root / 'licences.json').write_text(json.dumps({'schema': split_lock.LICENCES_SCHEMA, 'id': 'creator-image-fixture',
                                                             'texts': {licence_digest: licence_text}}))
        (self.root / 'lock.archive.txt').write_text(split_lock.archive_lock(lock.read_text(), definition['direct_download'],
                                                                             definition))
        records = []
        for name, body in (('olivefixture', data), ('nvidia-fixture-cu13', nvidia)):
            filename = name.replace('-', '_') + '-1.0-py3-none-any.whl'
            records.append({'name': name, 'version': '1.0', 'distribution': split_lock.classify(name, definition['direct_download']),
                            'filename': filename, 'url': 'https://files.pythonhosted.org/packages/xx/' + filename,
                            'sha256': hashlib.sha256(body).hexdigest(), 'size_bytes': len(body),
                            **({'direct_reason': 'nvidia-package', 'pypi_project': f'https://pypi.org/project/{name}/1.0/',
                                'wheel_metadata_licence': {'License-Expression': 'LicenseRef-NVIDIA-Proprietary',
                                                           'License': None, 'Classifier': [], 'License-File': ['License.txt']},
                                'wheel_metadata_attribution': {'Author': 'Fixture CUDA team', 'Project-URL': []},
                                'licence_files': [{'path': 'nvidia_fixture_cu13-1.0.dist-info/licenses/License.txt',
                                                   'sha256': licence_digest, 'bytes': len(licence_text)}],
                                'layout': {'installed_bytes': 600}} if name.startswith('nvidia') else {})})
        (self.root / 'wheels.json').write_text(json.dumps(split_lock.wheels_document(definition, records)))
        self.definition = self.root / 'definition.json'
        self.definition.write_text(json.dumps(definition))
        self.python, self.comfy = python, comfy
        # Pack with the real pinned interpreter whenever it is cached; otherwise this Python is the
        # (declared) fixture compressor with the pinned parameters.
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        pinned = cached_pinned_interpreter()
        if pinned is not None:
            (self.cache / PINNED_PYTHON['asset']).symlink_to(pinned)
            self.packing = {}
        else:
            self.packing = {'fixture_compressor': Path(sys.executable), 'compression_path': host_compression(self.root)}

    async def asyncTearDown(self):
        self.temp.cleanup()

    def build(self, output, source_commit='0' * 40, definition=None, **packing):
        output.mkdir(parents=True, exist_ok=True)
        return builder.build(definition or self.definition, output, self.cache, fixture_python=self.python,
                             fixture_comfyui=self.comfy, wheelhouse=self.wheelhouse, source_commit=source_commit,
                             **{**self.packing, **packing})

    async def test_fixture_build_is_deterministic_and_installs_through_setup(self):
        first = await asyncio.to_thread(self.build, self.root / 'out1')
        second = await asyncio.to_thread(self.build, self.root / 'out2')
        self.assertEqual(first['sha256'], second['sha256'])  # Byte-reproducible.
        archive = self.root / 'out1' / first['archive']
        self.assertEqual(first['size_bytes'], archive.stat().st_size)
        self.assertEqual((self.root / 'out1' / (first['archive'] + '.sha256')).read_text().split()[0], first['sha256'])
        with tarfile.open(archive, 'r:zst') as tar:
            members = tar.getmembers()
        names = {m.name for m in members}
        self.assertIn('ComfyUI/main.py', names)
        self.assertNotIn('ComfyUI/tests/test_x.py', names)  # Pruned.
        self.assertIn('python/lib/python3.14/site-packages/olivefixture/__init__.py', names)
        self.assertFalse([n for n in names if 'nvidia' in n.lower()])  # Option B: never inside the archive.
        self.assertTrue({builder.MARKER, builder.NOTICES, builder.DIRECT_NOTICES} <= names)
        self.assertEqual([w['package'] for w in first['direct_wheels']['linux-x86_64']], ['nvidia-fixture-cu13'])
        self.assertEqual(first['install']['direct_wheels_target'], 'python/lib/python3.14/site-packages')
        self.assertEqual({(m.uid, m.gid, m.mtime) for m in members}, {(0, 0, EPOCH)})
        self.assertEqual(first['install']['executables'], ['python/bin/python3'])
        self.assertIsNone(first['url'])

        # Publish it on the loopback fixture server and install it exactly as setup would.
        home, profile = self.root / 'home', self.root / 'profile'
        home.mkdir()
        profile.mkdir()
        env = {'XDG_DATA_HOME': str(self.root / 'xdg'), 'OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP': '1'}
        with FileServer() as files, FakeOllama() as ollama:
            manifest = fixture_manifest(files, ollama, tar_bytes({'bin/ollama': b'#!/bin/sh\n'}, executable={'bin/ollama'}))
            manifest['entries'] = [e for e in manifest['entries'] if e['provides'] != 'image-engine']
            # The builder's NVIDIA record, served by the fixture "index" instead of PyPI.
            direct = [{**w, 'url': files.add('/pypi/' + w['name'], self.nvidia)} for w in first['direct_wheels']['linux-x86_64']]
            manifest['entries'].append({
                'id': 'fixture-creator-image', 'kind': 'archive', 'provides': 'image-engine', 'name': 'Fixture Creator image engine',
                'version': first['id'], 'platforms': ['linux-x86_64'], 'validated_platforms': [], 'enabled': True,
                'source': {'publisher': 'fixture', 'url': files.add('/' + first['archive'], archive.read_bytes()), 'hosts': ['127.0.0.1']},
                'sha256': first['sha256'], 'size_bytes': first['size_bytes'], 'install': first['install'],
                'direct_wheels': {'linux-x86_64': direct}, 'direct_hosts': ['127.0.0.1'],
                'licence': {'spdx': 'GPL-3.0-only', 'name': 'fixture', 'url': None, 'acceptance_required': False,
                            'distribution': 'olive-hosted-archive', 'identified': True, 'engineering_reviewed': True},
                'reason': None})
            approve(manifest, ['fixture-creator-image'])
            path = self.root / 'manifest.json'
            path.write_text(json.dumps(manifest))
            discovery = RuntimeDiscovery(profile, environ=env, platform='linux', home=home,
                                         install_root=self.root / 'install', which=lambda name: None)
            installer = RuntimeInstaller(profile, discovery, ollama_host=ollama.base, environ=env, platform='linux', home=home,
                                         target='linux-x86_64', manifest=runtime_manifest.load(environ=env, path=path),
                                         disk_usage=lambda p: type('U', (), {'free': 10 ** 12})())
            plan = await installer.plan('creator')
            self.assertIn('fixture-creator-image', plan['offered'])
            job = await installer.start('creator', ['fixture-creator-image'])
            await installer.jobs[job['job_id']].task
            result = installer.progress(job['job_id'])
            await installer.close()
        self.assertEqual(result['items'][0]['state'], 'done', result)
        installed = self.root / 'xdg/olive/runtime/comfy'
        self.assertTrue((installed / MARKER).is_file())
        python = installed / 'python/bin/python3'
        self.assertTrue(stat.S_IMODE(python.stat().st_mode) & 0o100)
        self.assertFalse(stat.S_IMODE((installed / 'ComfyUI/main.py').stat().st_mode) & 0o111)
        located = discovery.resolve()['comfy']
        self.assertTrue(located.found)
        self.assertEqual(located.origin, 'olive-owned')
        self.assertTrue(valid('comfy', located.paths))
        record = json.loads((installed / builder.MARKER).read_text())
        marker = json.loads((installed / MARKER).read_text())
        self.assertNotIn('olive_source_commit', record)  # Provenance lives beside the archive, not in it.
        self.assertEqual(first['build_provenance']['olive_source_commit'], '0' * 40)
        self.assertEqual(record['source_date_epoch'], EPOCH)
        self.assertNotIn('olive_source_commit', marker)  # The fixture manifest supplies none: none is invented.
        self.assertEqual(marker['inputs']['definition_sha256'], first['inputs']['definition_sha256'])
        self.assertEqual(marker['inputs']['wheels_sha256'], first['inputs']['wheels_sha256'])
        self.assertEqual(record['comfyui']['commit'], '40c4fcdf513a4523e39d54a9d391908af8df8171')
        site = installed / 'python/lib/python3.14/site-packages'
        self.assertTrue((site / 'nvidia_fixture_cu13-1.0.dist-info/INSTALLER').is_file())  # Fetched and unpacked by setup.
        self.assertEqual(marker['direct_wheels'][0]['sha256'], hashlib.sha256(self.nvidia).hexdigest())
        self.assertEqual(marker['archive']['sha256'], first['sha256'])
        notices = (installed / builder.NOTICES).read_text()
        self.assertNotIn('nvidia_fixture_cu13', notices.split('Distributions:')[1].split('---')[0])
        direct_notices = (installed / builder.DIRECT_NOTICES).read_text()
        self.assertIn('NOT included in the OLIVE archive', direct_notices)
        self.assertIn('NVIDIA fixture licence text', direct_notices)  # The wheel's own licence text is reproduced.
        self.assertIn('metadata:    Author: Fixture CUDA team', direct_notices)
        self.assertIn('source is PyPI', direct_notices.replace('\n', ' ').replace('The source is', 'source is'))
        self.assertIn('nvidia-fixture-cu13 1.0', direct_notices)
        self.assertIn('LicenseRef-NVIDIA-Proprietary', direct_notices)
        self.assertIn('olivefixture 1.0: MIT', notices)
        self.assertIn('ComfyUI is GPL-3.0-only', notices)
        self.assertIn('Libraries compiled into CPython', notices)


    async def test_the_olive_commit_never_changes_the_archive_bytes(self):
        """Regression (PASS 2F-C): the archive embedded the OLIVE HEAD and used its commit time."""
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {'SOURCE_DATE_EPOCH': '1234567890', 'OLIVE_SOURCE_COMMIT': 'c' * 40}):
            a = await asyncio.to_thread(self.build, self.root / 'commit-a', 'a' * 40)
        with mock.patch.dict(os.environ, {'SOURCE_DATE_EPOCH': '42'}):
            b = await asyncio.to_thread(self.build, self.root / 'commit-b', 'b' * 40)
        self.assertEqual(a['sha256'], b['sha256'])  # Same runtime inputs, different OLIVE commits and env.
        self.assertEqual(a['inputs'], b['inputs'])
        self.assertEqual((a['build_provenance']['olive_source_commit'], b['build_provenance']['olive_source_commit']),
                         ('a' * 40, 'b' * 40))  # The sidecar still tells them apart.
        sidecar = json.loads((self.root / 'commit-a' / 'creator-image-fixture.inventory.json').read_text())
        self.assertEqual(sidecar['build_provenance']['olive_source_commit'], 'a' * 40)
        with tarfile.open(self.root / 'commit-a' / a['archive'], 'r:zst') as tar:
            marker = tar.extractfile(builder.MARKER).read()
            mtimes = {m.mtime for m in tar.getmembers()}
        self.assertNotIn(b'a' * 40, marker)
        self.assertEqual(mtimes, {EPOCH})

    async def test_build_folder_cpu_count_and_system_zstd_never_change_the_archive(self):
        """Regression (PASS 2F-D): the hosted archive differed because the runner's Python compressed
        with its own libzstd. Every spelling of the build folder, a single CPU and a hostile system
        zstd on PATH must give the identical archive, packed by the pinned compressor."""
        import os
        from unittest import mock
        builds = {'short': self.root / 's', 'long': self.root / LONG_SEGMENT / 'deeper' / 'out'}
        results = {name: await asyncio.to_thread(self.build, path) for name, path in builds.items()}
        cwd = Path.cwd()
        try:
            for name, workspace in (('short-relative', self.root / 'ws'),
                                    ('long-relative', self.root / LONG_SEGMENT / 'ws')):
                workspace.mkdir(parents=True)
                os.chdir(workspace)
                results[name] = await asyncio.to_thread(self.build, Path('out'))  # The hosted CI's --output out.
        finally:
            os.chdir(cwd)
        if hasattr(os, 'sched_setaffinity') and len(os.sched_getaffinity(0)) > 1:
            def one_cpu():  # The build thread (and so the packer it starts) sees a single CPU.
                everything = os.sched_getaffinity(0)
                os.sched_setaffinity(0, {min(everything)})
                try:
                    return self.build(self.root / 'one-cpu')
                finally:
                    os.sched_setaffinity(0, everything)
            results['one-cpu'] = await asyncio.to_thread(one_cpu)
        fake = self.root / 'fake-bin'
        fake.mkdir()
        (fake / 'zstd').write_text('#!/bin/sh\necho "system zstd must not be used" >&2\nexit 97\n')
        (fake / 'zstd').chmod(0o755)
        with mock.patch.dict(os.environ, {'PATH': f'{fake}{os.pathsep}{os.environ.get("PATH", "")}',
                                          'ZSTD_CLEVEL': '19', 'ZSTD_NBTHREADS': '8'}):
            results['system-zstd'] = await asyncio.to_thread(self.build, self.root / 'fake-zstd')
        self.assertEqual(len({r['sha256'] for r in results.values()}), 1, {n: r['sha256'] for n, r in results.items()})
        self.assertEqual(len({r['compression']['tar_sha256'] for r in results.values()}), 1)
        self.assertEqual(len({json.dumps(r['inputs'], sort_keys=True) for r in results.values()}), 1)
        compression = results['short']['compression']
        self.assertEqual(compression['parameters']['nb_workers'], 0)
        self.assertEqual(compression['spec_sha256'], results['short']['inputs']['compression_sha256'])
        if not self.packing:  # The real pinned interpreter packed it.
            self.assertEqual((compression['zstd_version'], compression['builtin'], compression['interpreter_sha256']),
                             ('1.5.7', True, PINNED_PYTHON['sha256']))
            self.assertEqual(compression['implementation'], 'CPython 3.14.8 compression.zstd')
        for path in builds.values():
            self.assertEqual(sorted(p.name for p in path.iterdir() if p.name.endswith(('.staging', '.compressor'))), [])
        sidecar = json.loads((self.root / 's' / 'creator-image-fixture.inventory.json').read_text())
        self.assertEqual(sidecar['compression'], compression)

    async def test_compression_settings_are_a_deliberate_build_input(self):
        base = await asyncio.to_thread(self.build, self.root / 'base')
        spec_path = self.packing.get('compression_path', builder.COMPRESSION)
        spec = json.loads(Path(spec_path).read_text())
        spec['parameters']['compression_level'] = 3
        level = self.root / 'compression-level3.json'
        level.write_text(json.dumps(spec))
        changed = await asyncio.to_thread(self.build, self.root / 'level3', compression_path=level)
        self.assertNotEqual(changed['inputs']['compression_sha256'], base['inputs']['compression_sha256'])
        self.assertNotEqual(changed['sha256'], base['sha256'])
        # Only the compressed layer changed: the same payload, the same runtime-input digests.
        self.assertEqual(changed['compression']['tar_sha256'], base['compression']['tar_sha256'])
        self.assertEqual({k: v for k, v in changed['inputs'].items() if k != 'compression_sha256'},
                         {k: v for k, v in base['inputs'].items() if k != 'compression_sha256'})
        # A compressor that is not the declared libzstd version writes nothing. The mismatch must be an
        # impossible version: a real one such as 1.5.5 is the host's own libzstd on some runners, where
        # the fixture fallback packs with this Python and the "mismatch" would then match.
        spec['parameters']['compression_level'] = 12
        spec['zstd_version'] = '0.0.0'
        level.write_text(json.dumps(spec))
        with self.assertRaises(SystemExit) as caught:
            await asyncio.to_thread(self.build, self.root / 'other-version', compression_path=level)
        self.assertIn('the pinned compressor is 0.0.0', str(caught.exception))
        self.assertFalse((self.root / 'other-version' / base['archive']).exists())

    async def test_a_real_input_change_still_changes_the_archive(self):
        base = await asyncio.to_thread(self.build, self.root / 'base')
        definition = json.loads(self.definition.read_text())
        definition['version'] = definition['version'] + '.changed'
        changed_path = self.root / 'changed-definition.json'
        changed_path.write_text(json.dumps(definition))
        changed = await asyncio.to_thread(self.build, self.root / 'changed', definition=changed_path)
        self.assertNotEqual(base['inputs']['definition_sha256'], changed['inputs']['definition_sha256'])
        self.assertNotEqual(base['sha256'], changed['sha256'])
        # A different pinned epoch is a runtime input too.
        definition['source_date_epoch'] = EPOCH + 1
        changed_path.write_text(json.dumps(definition))
        epoch = await asyncio.to_thread(self.build, self.root / 'epoch', definition=changed_path)
        self.assertEqual(epoch['inputs']['source_date_epoch'], EPOCH + 1)
        self.assertNotEqual(epoch['sha256'], changed['sha256'])
        # And a wheel that changes changes the lock digests and the archive.
        lock = Path(definition['lock'])
        lock.write_text(lock.read_text().replace('# fixture lock', '# fixture lock, edited'))
        definition['source_date_epoch'] = EPOCH
        changed_path.write_text(json.dumps(definition))
        archive_lock = Path(definition['archive_lock'])
        archive_lock.write_text(split_lock.archive_lock(lock.read_text(), definition['direct_download'], definition))
        edited = await asyncio.to_thread(self.build, self.root / 'edited', definition=changed_path)
        self.assertNotEqual(edited['inputs']['lock_sha256'], changed['inputs']['lock_sha256'])
        self.assertNotEqual(edited['sha256'], changed['sha256'])


ECHO_ENTRY = b'''import json, sys


def main():
    print(json.dumps({'argv': sys.argv[1:], 'prefix': sys.prefix}))
    return 7
'''
LONG_SEGMENT = 'long-' + 'x' * 150  # Pushes pip's interpreter path past distlib's 127-byte shebang limit.


@unittest.skipIf(sys.platform == 'win32', 'POSIX console-script launchers')
@unittest.skipUnless(HAS_ENSUREPIP, 'ensurepip is needed to give the fixture runtime its own pip')
class ConsoleScriptRelocationTests(unittest.TestCase):
    """pip writes a direct shebang for a short build folder and its /bin/sh trampoline for a long one,
    and the hosted CI build passes a relative --output. Every combination must reach the same
    relocatable launcher through the builder's real install_wheels -> relocate_scripts -> audit."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.definition = json.loads((CREATOR / 'definitions/creator-image-comfyui-0.35.0-linux-x86_64.json').read_text())
        data = wheel('olive_echo', '1.0', {
            'olive_echo/__init__.py': ECHO_ENTRY,
            'olive_echo-1.0.dist-info/entry_points.txt': b'[console_scripts]\nolive-echo = olive_echo:main\n'})
        self.wheelhouse = self.root / 'wheels'
        self.wheelhouse.mkdir()
        (self.wheelhouse / 'olive_echo-1.0-py3-none-any.whl').write_bytes(data)
        self.lock = self.root / 'lock.txt'
        self.lock.write_text(f'olive-echo==1.0 --hash=sha256:{hashlib.sha256(data).hexdigest()}\n')
        self.cwd = Path.cwd()

    def tearDown(self):
        import os
        os.chdir(self.cwd)
        self.temp.cleanup()

    def install(self, output: Path, cwd: Path | None = None) -> dict:
        """A runtime with its own interpreter and pip in output/<id>.staging/python, built like the archive."""
        import os
        import venv
        if cwd is not None:
            cwd.mkdir(parents=True)
            os.chdir(cwd)
        stage = output / 'creator-image-fixture.staging'
        venv.EnvBuilder(with_pip=True).create(stage / 'python')
        for script in (stage / 'python/bin').glob('[Aa]ctivate*'):
            script.unlink()  # venv's own shell helpers, not pip console scripts.
        builder.install_wheels(stage / self.definition['register']['paths']['python'], self.lock, self.wheelhouse)
        script = stage / 'python/bin/olive-echo'
        raw, mode = script.read_bytes(), stat.S_IMODE(script.stat().st_mode)
        relocated = builder.relocate_scripts(stage, self.definition)
        builder.prune(stage)
        builder.audit(stage, self.definition, [])  # Raises on any build-folder path.
        final, final_mode = script.read_bytes(), stat.S_IMODE(script.stat().st_mode)
        site = next((stage / 'python/lib').glob('python3.*/site-packages'))
        rows = list(csv.reader((site / 'olive_echo-1.0.dist-info/RECORD').read_text().splitlines()))
        row = next(r for r in rows if r and r[0].endswith('/bin/olive-echo'))
        absolute = Path.cwd() / stage  # A relative interpreter path is made absolute against the physical cwd.
        os.chdir(self.cwd)
        return {'stage': absolute, 'raw': raw, 'final': final, 'mode': mode, 'final_mode': final_mode,
                'relocated': relocated, 'record': row, 'interpreter_length': len(str(absolute / 'python/bin/python3'))}

    def test_short_long_and_relative_build_folders_reach_one_canonical_launcher(self):
        cases = {
            'short': self.install(self.root / 's'),
            'long': self.install(self.root / LONG_SEGMENT / 'out'),
            'short-relative': self.install(Path('out'), cwd=self.root / 'ws'),  # The hosted CI's --output out.
            'long-relative': self.install(Path('out'), cwd=self.root / LONG_SEGMENT / 'ws'),
        }
        roots = [str(case['stage']).encode() for case in cases.values()]
        for name, case in cases.items():
            with self.subTest(name):
                # pip's own choice of launcher, before OLIVE normalises it.
                long_form = case['interpreter_length'] + 3 > 127
                self.assertEqual(name.startswith('long'), long_form)
                interpreter = str(case['stage']).encode() + b'/python/bin/python3'
                expected = b"#!/bin/sh\n'''exec' " + interpreter + b' "$0" "$@"\n' if long_form else b'#!' + interpreter + b'\n'
                self.assertTrue(case['raw'].startswith(expected), case['raw'][:300])
                # After normalisation: the canonical launcher, the same entry-point body, no build folder.
                self.assertEqual(case['relocated'], ['bin/olive-echo'])
                self.assertTrue(case['final'].startswith(
                    b'#!/bin/sh\n\'\'\'exec\' "$(dirname -- "$(realpath -- "$0")")/python3" "$0" "$@"\n\' \'\'\'\n'))
                self.assertEqual(case['raw'].split(b'\nimport sys\n', 1)[1], case['final'].split(b'\nimport sys\n', 1)[1])
                for root in roots:
                    self.assertNotIn(root, case['final'])
                self.assertEqual(case['final_mode'], case['mode'])
                self.assertTrue(case['mode'] & stat.S_IXUSR)
                self.assertEqual(case['record'][1:], [builder._record_hash(case['final']), str(len(case['final']))])
        self.assertEqual(len({case['final'] for case in cases.values()}), 1)  # Byte-identical everywhere.
        self.assertNotEqual(cases['short']['raw'][:12], cases['long']['raw'][:12])  # Both pip forms were exercised.
        # The relocated runtime still runs its own interpreter, with arguments and exit status intact.
        import subprocess
        for name in ('short', 'long-relative'):
            moved = self.root / 'moved' / name
            moved.parent.mkdir(exist_ok=True)
            cases[name]['stage'].rename(moved)
            result = subprocess.run([str(moved / 'python/bin/olive-echo'), 'a', 'b c', '', '$HOME'],
                                    capture_output=True, text=True, env={'PATH': '/usr/bin:/bin'})
            self.assertEqual(result.returncode, 7, result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual(value['argv'], ['a', 'b c', '', '$HOME'])
            self.assertEqual(Path(value['prefix']).resolve(), (moved / 'python').resolve())


@unittest.skipIf(sys.platform == 'win32', 'POSIX console-script launchers')
class UnrecognisedScriptTests(unittest.TestCase):
    """Only a launcher whose interpreter is the runtime's own python/bin is rewritten; anything else that
    still names the build folder, however it is spelled, fails the audit (fail closed)."""

    def test_unrecognised_executables_with_the_build_folder_fail_the_audit(self):
        definition = json.loads((CREATOR / 'definitions/creator-image-comfyui-0.35.0-linux-x86_64.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            real = Path(directory) / 'real'
            (real / 'creator-image-fixture.staging/python/bin').mkdir(parents=True)
            (Path(directory) / 'link').symlink_to(real, target_is_directory=True)
            stage = Path(directory) / 'link' / 'creator-image-fixture.staging'  # Reached through a symlink.
            bin_folder = stage / 'python/bin'
            (bin_folder / 'python3').write_bytes(b'')
            (stage / 'python/lib/python3.14/site-packages').mkdir(parents=True)
            scripts = {
                # Positively recognised: pip's direct shebang to this runtime, spelled through the resolved path.
                'tool': f'#!{real}/creator-image-fixture.staging/python/bin/python3\nimport sys\n'.encode(),
                # A launcher shape, but the interpreter is not the runtime's own bin folder.
                'other-python': f'#!{stage}/ComfyUI/bin/python3\nimport sys\n'.encode(),
                # Not a recognised launcher at all.
                'shell-helper': f'#!/bin/sh\nexec "{stage}/ComfyUI/run" "$@"\n'.encode(),
                # Only the resolved spelling of the build folder.
                'resolved-only': f'#!/bin/sh\nexec "{real}/creator-image-fixture.staging/x" "$@"\n'.encode(),
            }
            for name, data in scripts.items():
                (bin_folder / name).write_bytes(data)
                (bin_folder / name).chmod(0o755)
            self.assertEqual(builder.relocate_scripts(stage, definition), ['bin/tool'])
            for name in ('other-python', 'shell-helper', 'resolved-only'):
                self.assertEqual((bin_folder / name).read_bytes(), scripts[name])  # Never rewritten.
            with self.assertRaises(builder.AuditError) as caught:
                builder.audit(stage, definition, [])
            message = str(caught.exception)
            for name in ('other-python', 'shell-helper', 'resolved-only'):
                self.assertIn(f'python/bin/{name}: contains the build folder path', message)
            self.assertNotIn('python/bin/tool:', message)


class PinnedEpochTests(unittest.TestCase):
    def test_every_definition_pins_the_comfyui_commit_time(self):
        for path in sorted((CREATOR / 'definitions').glob('*.json')):
            definition = builder.load_definition(path)
            self.assertEqual(definition['source_date_epoch'], EPOCH, path.name)
            self.assertEqual(definition['comfyui']['commit'], '40c4fcdf513a4523e39d54a9d391908af8df8171')

    def test_a_definition_without_a_pinned_epoch_is_refused(self):
        definition = json.loads((CREATOR / 'definitions/creator-image-comfyui-0.35.0-linux-x86_64.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            for bad in (None, '1788930166', 0):
                value = dict(definition)
                if bad is None:
                    value.pop('source_date_epoch')
                else:
                    value['source_date_epoch'] = bad
                path = Path(directory) / 'd.json'
                path.write_text(json.dumps(value))
                with self.assertRaises(SystemExit):
                    builder.load_definition(path)

    def test_checkout_verifies_the_commit_time(self):
        import os
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'repo'
            repo.mkdir()
            env = dict(os.environ, GIT_AUTHOR_DATE='@1700000000 +0000', GIT_COMMITTER_DATE='@1700000000 +0000',
                       GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid', GIT_COMMITTER_NAME='t',
                       GIT_COMMITTER_EMAIL='t@example.invalid')
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / 'main.py').write_text('print(1)\n')
            subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(repo), 'commit', '-q', '-m', 'x'], check=True, env=env)
            commit = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                                    text=True).stdout.strip()
            builder.checkout(str(repo), commit, root / 'ok', root / 'cache', expected_time=1700000000)
            self.assertTrue((root / 'ok/main.py').is_file())
            with self.assertRaises(SystemExit):
                builder.checkout(str(repo), commit, root / 'bad', root / 'cache', expected_time=1700000001)


if __name__ == '__main__':
    unittest.main()
