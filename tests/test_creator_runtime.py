"""Creator runtime: definitions and locks are pinned; a fixture build is deterministic and installs
through the normal verified archive path (no network, no real PyTorch)."""
import asyncio
import base64
import csv
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
EPOCH = 1788930166  # Committer time of the pinned ComfyUI v0.35.0 commit (the definitions' source_date_epoch).


def wheel(name='olivefixture', version='1.0') -> bytes:
    """A minimal valid pure-Python wheel."""
    files = {f'{name}/__init__.py': b'VALUE = 1\n',
             f'{name}-{version}.dist-info/METADATA': (f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n'
                                                     'License-Expression: MIT\n\n').encode(),
             f'{name}-{version}.dist-info/licenses/LICENSE': b'MIT fixture licence text\n',
             f'{name}-{version}.dist-info/WHEEL': b'Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
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

    async def asyncTearDown(self):
        self.temp.cleanup()

    def build(self, output, source_commit='0' * 40, definition=None):
        output.mkdir(parents=True, exist_ok=True)
        return builder.build(definition or self.definition, output, self.root / 'cache', fixture_python=self.python,
                             fixture_comfyui=self.comfy, wheelhouse=self.wheelhouse, source_commit=source_commit)

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
