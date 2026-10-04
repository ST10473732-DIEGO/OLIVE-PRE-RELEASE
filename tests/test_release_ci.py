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
        for job in ('desktop', 'smoke', 'relay', 'checksums', 'creator'):
            self.assertNotIn('secrets.', jobs[job])
            self.assertNotIn('environment:', jobs[job])
        self.assertIn('environment: release-signing', jobs['macos-signing'])

    def test_creator_job_builds_the_archive_without_nvidia_wheels(self):
        jobs = dict(re.findall(r'(?ms)^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)', self.code.split('\njobs:\n', 1)[1]))
        creator = jobs['creator']
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.creator_runtimes", creator)
        self.assertIn('definition: [creator-image-comfyui-0.35.0-linux-x86_64]', creator)  # VIDEO is not built yet.
        self.assertIn('split_lock.py --check', creator)
        self.assertIn('audit_archive.py out/', creator)
        self.assertIn('OLIVE_SOURCE_COMMIT: ${{ github.sha }}', creator)  # Sidecar provenance only.
        # The archive's mtimes come from the definition's pinned epoch, never the OLIVE commit (PASS 2F-C).
        self.assertNotIn('SOURCE_DATE_EPOCH', creator)
        self.assertNotIn('git log', creator)
        # The pinned interpreter compresses (PASS 2F-D): the job never runs or installs the runner's zstd,
        # and logs the compressor identity, its parameters and both digests from the sidecar.
        self.assertNotRegex(creator, r'(?m)(^|[\s|;&(])(un)?zstd\s')
        self.assertNotRegex(creator, r'\bapt(-get)?\s+install')
        for logged in ("c['implementation']", "c['zstd_version']", "p['compression_level']", "p['nb_workers']",
                       "c['tar_sha256']", "entry['sha256']"):
            self.assertIn(logged, creator)
        self.assertLess(creator.index('build_creator_runtime.py'), creator.index('Compressor identity and digests'))
        # The NVIDIA assembly is an explicit, separate input; its output lives outside out/ and is deleted.
        self.assertIn('if: inputs.creator_assemble_nvidia', creator)
        self.assertIn('rm -rf "$RUNNER_TEMP/assembled"', creator)
        uploads = re.findall(r'path: (\S+)', creator)
        self.assertEqual(uploads, ['out/'])
        self.assertNotIn('assembled', creator.split('upload-artifact', 1)[1])
        self.assertLess(creator.index('audit_archive.py'), creator.index('upload-artifact'))
        for forbidden in ('codesign', 'notarytool', 'secrets.', 'docker', 'gh release', 'environment:'):
            self.assertNotIn(forbidden, creator.lower())

    def test_smoke_job_starts_the_packages_this_run_built(self):
        jobs = dict(re.findall(r'(?ms)^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)', self.code.split('\njobs:\n', 1)[1]))
        smoke = jobs['smoke']
        self.assertIn('needs: [desktop]', smoke)
        self.assertIn('target: windows-x86_64', smoke)
        self.assertIn('target: macos-arm64', smoke)
        self.assertIn('name: olive-desktop-${{ matrix.target }}', smoke)  # This run's artefact, never another build.
        self.assertIn("-ArgumentList '/S'", smoke)
        self.assertIn('node packaging/release/smoke_packaged.mjs "$OLIVE_EXE"', smoke)
        self.assertNotIn('upload-artifact', smoke)
        self.assertNotIn('smoke', jobs['checksums'].split('needs:', 1)[1].splitlines()[0])  # Never gates the build.
        script = (ROOT / 'packaging/release/smoke_packaged.mjs').read_text(encoding='utf-8')
        self.assertIn('main.setup[aria-label="OLIVE setup"]', script)
        self.assertIn('.setup-banner', script)  # A test runtime manifest fails the check.

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
