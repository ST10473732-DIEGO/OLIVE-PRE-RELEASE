"""The standalone Connect World relay bundle: deterministic, minimal, and runnable without the repository."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_relay', ROOT / 'packaging/relay/build_relay.py')
build_relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_relay)


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class RelayBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, name):
        return build_relay.build(self.root / name, epoch=1767225600, commit='0' * 40)

    def test_bundle_is_deterministic_minimal_and_secret_free(self):
        first, second = self.build('a'), self.build('b')
        self.assertEqual(first['sha256'], second['sha256'])
        archive = Path(first['archive'])
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), first['sha256'])
        self.assertEqual(Path(str(archive) + '.sha256').read_text().split()[0], first['sha256'])
        with tarfile.open(archive) as tar:
            members = {m.name: m for m in tar.getmembers()}
            python = sorted(n for n in members if n.endswith('.py'))
            self.assertEqual(python, sorted('olive-world-relay-1.0.0/' + p for p, _ in build_relay.MODULES))
            for name in ('LICENSE-RELAY.md', 'THIRD_PARTY_NOTICES.md', 'Dockerfile', 'compose.yaml', 'BUILD-INFO.json'):
                self.assertIn('olive-world-relay-1.0.0/' + name, members)
            self.assertEqual({(m.uid, m.gid, m.mtime) for m in members.values()}, {(0, 0, 1767225600)})
            info = json.load(tar.extractfile('olive-world-relay-1.0.0/BUILD-INFO.json'))
            for path, digest in info['files'].items():
                self.assertEqual(hashlib.sha256(tar.extractfile('olive-world-relay-1.0.0/' + path).read()).hexdigest(), digest)
            text = b''.join(tar.extractfile(m).read() for m in members.values() if m.isfile())
        self.assertEqual((info['version'], info['source_commit'], info['published']), ('1.0.0', '0' * 40, False))
        for forbidden in (b'PRIVATE KEY', b'BEGIN CERTIFICATE', b'getolive.si', b'.sqlite', b'olive.connect', b'olive.services'):
            self.assertNotIn(forbidden, text, forbidden)
        dockerfile = (ROOT / 'packaging/relay/bundle/Dockerfile').read_text()
        self.assertRegex(dockerfile, r'FROM python:3\.12-slim@sha256:[0-9a-f]{64}')
        self.assertNotIn('context: ..', (ROOT / 'packaging/relay/bundle/compose.yaml').read_text())

    def test_unpacked_bundle_serves_unchanged_health_and_readiness(self):
        archive = Path(self.build('a')['archive'])
        with tarfile.open(archive) as tar:
            tar.extractall(self.root / 'run', filter='data')
        bundle = self.root / 'run/olive-world-relay-1.0.0'
        port = free_port()
        env = {'PATH': os.environ.get('PATH', ''), 'PYTHON': sys.executable}  # No PYTHONPATH: the repository is not used.
        process = subprocess.Popen([str(bundle / 'olive-world-relay'), '--host', '127.0.0.1', '--port', str(port), '--dev'],
                                   cwd=self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            health = None
            for _ in range(100):
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=1) as response:
                        health = json.loads(response.read())
                    break
                except OSError:
                    time.sleep(0.1)
            self.assertIsNotNone(health, process.stdout.read1(4096) if process.poll() is not None else 'no answer')
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/readiness', timeout=2) as response:
                self.assertEqual((response.status, json.loads(response.read())), (200, {'ready': True}))
            from olive.world_relay.server import Relay, Limits
            self.assertEqual(set(health), set(Relay(Limits()).health()))
            self.assertEqual((health['status'], health['protocol'], health['version']), ('ok', 'olive-world/1', '1.0.0'))
            for module in ('olive.world.wire', 'olive.world_relay.server'):
                origin = subprocess.run([sys.executable, '-E', '-s', '-c', f'import {module} as m; print(m.__file__)'],
                                        cwd=bundle, capture_output=True, text=True, check=True).stdout.strip()
                self.assertTrue(Path(origin).resolve().is_relative_to(bundle.resolve()), origin)
        finally:
            process.terminate()
            process.wait(10)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()
