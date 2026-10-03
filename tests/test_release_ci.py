"""The release CI builds privately and never publishes; build metadata carries the source commit."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/release-build.yml'


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding='utf-8')
        self.code = '\n'.join(l for l in self.text.splitlines() if not l.lstrip().startswith('#'))

    def test_build_only_with_read_only_permissions(self):
        self.assertRegex(self.code, r'(?m)^permissions:\n  contents: read\s*(#.*)?$')
        self.assertNotRegex(self.code, r'(?m)^[ ]+permissions:')  # No job widens it.
        for forbidden in ('gh release', 'action-gh-release', 'create-release', 'upload-release-asset', 'npm publish',
                          'docker push', 'push: true', '--publish always', '--publish onTag', 'packages: write',
                          'contents: write', 'git push'):
            self.assertNotIn(forbidden, self.code, forbidden)
        self.assertIn('push: false', self.code)
        self.assertEqual(self.code.count('--publish never'), 1)
        self.assertIn("CSC_IDENTITY_AUTO_DISCOVERY: 'false'", self.code)

    def test_every_action_is_pinned_to_a_commit(self):
        uses = re.findall(r'uses:\s*(\S+)', self.code)
        self.assertTrue(uses)
        for action in uses:
            self.assertRegex(action, r'^[\w.-]+/[\w.-]+@[0-9a-f]{40}$', action)

    def test_platform_jobs_and_gated_signing(self):
        for target in ('linux-x86_64', 'windows-x86_64', 'macos-arm64'):
            self.assertIn(f'target: {target}', self.code)
        self.assertIn('--linux AppImage --x64', self.code)
        self.assertIn('--win nsis --x64', self.code)
        self.assertIn('--mac dmg --arm64', self.code)
        self.assertIn('environment: release-signing', self.code)
        self.assertIn('inputs.macos_signing', self.code)
        self.assertIn('inputs.creator_runtimes', self.code)  # Multi-GB Creator builds are manual only.
        self.assertIn('retention-days', self.code)
        self.assertIn('extraMetadata.oliveSourceCommit=${{ github.sha }}', self.code)

    def test_pull_requests_to_main_build_without_secrets_or_heavy_jobs(self):
        on = self.code.split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertRegex(on, r'(?m)^  pull_request:\n    branches: \[main\]$')
        self.assertRegex(on, r"(?m)^  push:\n    tags: \['v1\.\*'\]$")  # Tags stay; no branch pushes.
        self.assertNotIn('branches:', on.split('pull_request:', 1)[0])
        self.assertIn('workflow_dispatch:', on)
        self.assertNotIn('pull_request_target', self.code)  # Would run with secrets and a write token.
        jobs = dict(re.findall(r'(?ms)^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)', self.code.split('\njobs:\n', 1)[1]))
        for heavy in ('creator', 'macos-signing'):  # Manual only: a PR can never reach them.
            self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.", jobs[heavy])
        for job in ('desktop', 'relay', 'checksums', 'creator'):
            self.assertNotIn('secrets.', jobs[job])
            self.assertNotIn('environment:', jobs[job])
        self.assertIn('environment: release-signing', jobs['macos-signing'])

    def test_build_info_records_commit_and_checksums(self):
        spec = importlib.util.spec_from_file_location('build_info', ROOT / 'packaging/release/build_info.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'a.bin').write_bytes(b'a')
            (folder / 'sub').mkdir()
            (folder / 'sub/b.bin').write_bytes(b'b')
            import os
            from unittest import mock
            with mock.patch.dict(os.environ, {'GITHUB_SHA': 'f' * 40, 'GITHUB_RUN_ID': '7'}, clear=False):
                os.environ.pop('OLIVE_SOURCE_COMMIT', None)
                info = module.write(folder, 'linux-x86_64', 'desktop')
            self.assertEqual(info['source_commit'], 'f' * 40)
            self.assertEqual((info['signed'], info['published']), (False, False))
            sums = (folder / 'SHA256SUMS').read_text().splitlines()
            self.assertEqual([line.split('  ')[1] for line in sums], ['a.bin', 'sub/b.bin'])
            self.assertEqual(json.loads((folder / 'BUILD-INFO.json').read_text())['ci_run']['id'], '7')



class OllamaPinDriftTests(unittest.TestCase):
    def test_drift_is_reported_never_rewritten(self):
        import contextlib
        import hashlib
        import io
        spec = importlib.util.spec_from_file_location('check_ollama_pins', ROOT / 'packaging/release/check_ollama_pins.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from olive.services import runtime_manifest
        manifest = json.loads((runtime_manifest.DIRECTORY / '1.0.0.json').read_text())
        pinned = [e for e in manifest['entries'] if e['kind'] == 'ollama-model' and (e.get('ollama') or {}).get('manifest_digest')]
        served = {e['source']['url']: f'registry manifest for {e["id"]}'.encode() for e in pinned}
        for entry in pinned:  # A manifest copy pinned to what the fake registry serves...
            entry['ollama']['manifest_digest'] = hashlib.sha256(served[entry['source']['url']]).hexdigest()
        served[pinned[0]['source']['url']] = b'a republished build'  # ...except one that changed upstream.
        with tempfile.TemporaryDirectory() as folder:
            copy, report = Path(folder) / 'manifest.json', Path(folder) / 'report.json'
            copy.write_text(json.dumps(manifest))
            before = copy.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                status = module.main(['--manifest', str(copy), '--json', str(report)], fetcher=served.__getitem__)
            self.assertEqual(copy.read_bytes(), before)  # Never rewritten.
            rows = {r['id']: r['status'] for r in json.loads(report.read_text())['results']}
        self.assertEqual(status, 1)
        self.assertEqual(rows.pop(pinned[0]['id']), 'DRIFTED')
        self.assertEqual(set(rows.values()), {'unchanged'})
        offline = module.check(manifest, fetcher=lambda url: (_ for _ in ()).throw(OSError('offline')))
        self.assertEqual({r['status'] for r in offline}, {'error'})


if __name__ == '__main__':
    unittest.main()
