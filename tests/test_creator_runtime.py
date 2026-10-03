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
import tarfile
import tempfile
import unittest
import zipfile

from olive.services import runtime_manifest
from olive.services.runtime_discovery import RuntimeDiscovery, valid
from olive.services.runtime_installer import MARKER, RuntimeInstaller
from tests.setup_installer_fixture import FakeOllama, FileServer, approve, fixture_manifest, tar_bytes

ROOT = Path(__file__).resolve().parents[1]
CREATOR = ROOT / 'packaging' / 'creator'
spec = importlib.util.spec_from_file_location('build_creator_runtime', CREATOR / 'build_creator_runtime.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
HAS_PIP = importlib.util.find_spec('pip') is not None


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
        stub.write_text('#!/bin/sh\nexit 0\n')
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
        lock = self.root / 'lock.txt'
        lock.write_text(f'olivefixture==1.0 \\\n    --hash=sha256:{hashlib.sha256(data).hexdigest()}\n')
        definition = json.loads((CREATOR / 'definitions/creator-image-comfyui-0.35.0-linux-x86_64.json').read_text())
        definition.update(id='creator-image-fixture', lock=str(lock))
        self.definition = self.root / 'definition.json'
        self.definition.write_text(json.dumps(definition))
        self.python, self.comfy = python, comfy

    async def asyncTearDown(self):
        self.temp.cleanup()

    def build(self, output):
        output.mkdir(parents=True, exist_ok=True)
        return builder.build(self.definition, output, self.root / 'cache', fixture_python=self.python,
                             fixture_comfyui=self.comfy, wheelhouse=self.wheelhouse, epoch=1767225600,
                             source_commit='0' * 40)

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
        self.assertTrue({builder.MARKER, builder.NOTICES} <= names)
        self.assertEqual({(m.uid, m.gid, m.mtime) for m in members}, {(0, 0, 1767225600)})
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
            manifest['entries'].append({
                'id': 'fixture-creator-image', 'kind': 'archive', 'provides': 'image-engine', 'name': 'Fixture Creator image engine',
                'version': first['id'], 'platforms': ['linux-x86_64'], 'validated_platforms': [], 'enabled': True,
                'source': {'publisher': 'fixture', 'url': files.add('/' + first['archive'], archive.read_bytes()), 'hosts': ['127.0.0.1']},
                'sha256': first['sha256'], 'size_bytes': first['size_bytes'], 'install': first['install'],
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
        self.assertEqual(record['olive_source_commit'], '0' * 40)
        self.assertEqual(record['comfyui']['commit'], '40c4fcdf513a4523e39d54a9d391908af8df8171')
        notices = (installed / builder.NOTICES).read_text()
        self.assertIn('olivefixture 1.0: MIT', notices)
        self.assertIn('ComfyUI is GPL-3.0-only', notices)
        self.assertIn('Libraries compiled into CPython', notices)


if __name__ == '__main__':
    unittest.main()
