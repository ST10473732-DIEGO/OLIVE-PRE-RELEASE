import asyncio
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from olive.bridge.host import Host
from olive.connect.approvals import ConnectApprovals
from olive.connect.contracts import ConnectError, canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.connect.studio_protocol import StudioRequest, request, MAX_FILE
from tests.connect_studio_fixture import graph
from tests.test_connect_network import pair
from tests.test_connect_pairing import MemoryVault


class StudioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.a, self.b, self.c = [DesktopDeviceService(self.root / name, key_store=DeviceKeyStore(MemoryVault())) for name in ('a', 'b', 'c')]
        pair(self.a, self.b); pair(self.c, self.b)
        self.s, self.workspace = graph(self.b, self.root / 'b')
        self.host = Host(lambda _: None); self.host.activity = lambda: None
        self.b.approvals = ConnectApprovals(self.b, self.host.confirm, asyncio.get_running_loop())
        self.share = self.b.studio.share(self.a.local_id, self.workspace.id)[0]
        networks = [s.enable_network('127.0.0.1', discovery=False) for s in (self.a, self.b, self.c)]
        self.channel = await asyncio.to_thread(networks[0].connect, self.b.local_id, '127.0.0.1', networks[1].port)
        self.third = await asyncio.to_thread(networks[2].connect, self.b.local_id, '127.0.0.1', networks[1].port)

    async def asyncTearDown(self):
        await self.b.studio.shutdown()
        await self.s.studio_tooling.shutdown()
        for s in (self.a, self.b, self.c):
            await asyncio.to_thread(s.close)
        self.temp.cleanup()

    def make(self, op, args=None, **kwargs):
        return request(self.a.local_id, self.b.local_id, op,
            None if op == 'workspaces' else self.share['workspace_id'],
            0 if op == 'workspaces' else self.share['share_revision'], args, **kwargs)

    async def send(self, raw, channel=None):
        return await asyncio.to_thread((channel or self.channel).studio_request, raw)

    async def permission(self, capability, decision):
        reference = self.share['workspace_id']
        shares = await asyncio.to_thread(self.b.studio.permission, self.a.local_id,
            reference, 'studio.' + capability, decision)
        self.share = next(s for s in shares if s['workspace_id'] == reference)

    async def approve(self, value):
        async with asyncio.timeout(3):
            while not self.host.pending:
                await asyncio.sleep(.01)
        p, _ = next(iter(self.host.pending.values()))
        await self.host.execute('approval.respond', dict(approval_id=p['id'], fingerprint=p['fingerprint'], approved=value))
        await asyncio.sleep(.01)

    async def finished(self, start):
        job_id = start['result']['job_id']
        async with asyncio.timeout(8):
            while True:
                result = await self.send(self.make('run_status', {'job_id': job_id}))
                self.assertIsNone(result['error'], result)
                if result['result']['state'] not in ('starting', 'running', 'cancelling'):
                    return result['result']
                await asyncio.sleep(.05)

    async def test_default_off_and_third_peer_and_domain_independence(self):
        self.assertEqual((await self.send(self.make('workspaces')))['result']['workspaces'], [])
        for op, args in [('read', {'path': 'main.py'}), ('tree', {}), ('save', {'path': 'main.py', 'expected_hash': '0' * 64, 'text': 'x'}), ('build', {}), ('test', {}), ('run', {})]:
            self.assertEqual((await self.send(self.make(op, args)))['error'], 'permission_denied')
            v = json.loads(self.make(op, args)); v['source_device_id'] = self.c.local_id
            self.assertEqual((await self.send(canonical(v), self.third))['error'], 'workspace_not_shared')
        self.assertEqual(self.b.permission(self.a.local_id, 'models.remote').value, 'deny')
        await asyncio.to_thread(self.b.set_permission, self.a.local_id, 'studio.view', 'allow')
        self.assertEqual((await self.send(self.make('tree')))['error'], 'permission_denied')
        await self.permission('view', 'allow')
        self.assertEqual(len((await self.send(self.make('workspaces')))['result']['workspaces']), 1)
        with self.b.repository.transaction() as db:
            local = self.b.repository.get(db, self.b.local_id)
            for capability in local['capabilities']:
                if capability['capability'] == 'studio.view':
                    capability['policy_disabled'] = True
            self.b.repository.put(db, local)
        for operation in ('workspaces', 'tree'):
            self.assertEqual((await self.send(self.make(operation)))['error'], 'permission_denied')

    async def test_view_ask_exact_and_edit_conflict_and_replay(self):
        await self.permission('view', 'ask')
        read = self.make('read', {'path': 'main.py'})
        self.assertEqual((await self.send(read))['error'], 'confirmation_required')
        await self.approve(False)
        self.assertEqual((await self.send(read))['error'], 'permission_denied')
        read = self.make('read', {'path': 'main.py'})
        await self.send(read); await self.approve(True)
        data = (await self.send(read))['result']
        self.assertIn('REMOTE OK', data['text'])
        self.assertEqual(self.b.studio.shared(self.a.local_id)[0]['permissions']['studio.view'], 'ask')
        await self.permission('view', 'allow'); await self.permission('edit', 'ask')
        save = self.make('save', {'path': 'main.py', 'expected_hash': data['revision'], 'text': 'print("changed")\r\n'})
        self.assertEqual((await self.send(save))['error'], 'confirmation_required')
        await self.approve(False)
        self.assertEqual((await self.send(save))['error'], 'permission_denied')
        save = self.make('save', json.loads(save)['arguments'])
        await self.send(save); await self.approve(True)
        result = await self.send(save)
        self.assertEqual(result['result']['state'], 'saved')
        self.assertEqual(Path(self.workspace.root_path, 'main.py').read_bytes(), b'print("changed")\r\n')
        self.assertEqual(await self.send(save), result)
        changed = json.loads(save); changed['arguments']['text'] = 'different'
        self.assertEqual((await self.send(canonical(changed)))['error'], 'changed_duplicate')
        self.assertEqual(self.b.studio.shared(self.a.local_id)[0]['permissions']['studio.edit'], 'ask')
        Path(self.workspace.root_path, 'main.py').write_text('local user edit', encoding='utf-8')
        save = self.make('save', {'path': 'main.py', 'expected_hash': result['result']['revision'], 'text': 'stale'})
        self.assertEqual((await self.send(save))['error'], 'revision_conflict')
        self.assertEqual(Path(self.workspace.root_path, 'main.py').read_text(), 'local user edit')

    async def test_build_test_run_real_structured_controllers(self):
        for op in ('build', 'test', 'run'):
            await self.permission(op, 'ask')
            raw = self.make(op)
            self.assertEqual((await self.send(raw))['error'], 'confirmation_required')
            await self.approve(False)
            self.assertEqual((await self.send(raw))['error'], 'permission_denied')
            self.assertFalse(self.s.run_service._processes)
            raw = self.make(op)
            await self.send(raw); await self.approve(True)
            start = await self.send(raw)
            self.assertIsNone(start['error'], start)
            done = await self.finished(start)
            self.assertEqual(done['state'], 'completed', done)
            self.assertEqual(done['exit_code'], 0)
            if op == 'test': self.assertEqual(done['tests']['passed'], 1)
            if op == 'run':
                self.assertIn('warning', done['output'])
                self.assertIn('REMOTE OK', done['output'])
            count = len(self.s.run_service.sessions)
            await self.send(raw)
            self.assertEqual(len(self.s.run_service.sessions), count)
            self.assertEqual(self.b.studio.shared(self.a.local_id)[0]['permissions']['studio.' + op], 'ask')

    async def test_stop_disconnect_and_revocation_release_actual_process(self):
        await self.permission('run', 'allow')
        Path(self.workspace.root_path, 'main.py').write_text('import time\nprint("running", flush=True)\ntime.sleep(60)\n')
        start = await self.send(self.make('run'))
        jid = start['result']['job_id']
        async with asyncio.timeout(3):
            while not self.s.run_service._processes: await asyncio.sleep(.01)
        await self.send(self.make('run_cancel', {'job_id': jid}))
        await self.finished(start)
        self.assertFalse(self.s.run_service._processes)
        start = await self.send(self.make('run'))
        async with asyncio.timeout(3):
            while not self.s.run_service._processes: await asyncio.sleep(.01)
        await asyncio.to_thread(self.b.revoke, self.a.local_id)
        job = self.b.studio.jobs[(self.a.local_id, start['result']['job_id'])]
        self.assertTrue(await asyncio.to_thread(job.released.wait, 5))
        self.assertFalse(self.s.run_service._processes)
        with self.assertRaises(ConnectError):
            await asyncio.to_thread(self.a.network.connect, self.b.local_id, '127.0.0.1', self.b.network.port)

    async def test_containment_binary_size_ignored_and_privacy(self):
        await self.permission('view', 'allow')
        root = Path(self.workspace.root_path)
        (root / '.env').write_text('TOKEN=private')
        (root / 'binary').write_bytes(b'\0')
        (root / 'large').write_bytes(b'x' * (MAX_FILE + 1))
        (root / 'node_modules').mkdir(); (root / 'node_modules' / 'secret').write_text('secret')
        for path in ('.env', 'binary', 'large', 'node_modules/secret'):
            value = await self.send(self.make('read', {'path': path}))
            self.assertEqual(value['error'], 'unsupported_file', value)
            self.assertNotIn(str(root), str(value))
        try:
            (root / 'link').symlink_to(self.root / 'a', target_is_directory=True)
        except OSError:
            pass
        else:
            self.assertEqual((await self.send(self.make('read', {'path': 'link/connect/devices.sqlite3'})))['error'], 'unsupported_file')
        tree = await self.send(self.make('tree'))
        self.assertNotIn('.env', str(tree)); self.assertNotIn('node_modules', str(tree))
        self.assertNotIn(str(root), str(tree))

    async def test_unshare_and_source_spoof_and_config_change(self):
        await self.permission('run', 'ask')
        raw = self.make('run'); await self.send(raw); await self.approve(True)
        self.s.studio_tooling.config_save(self.workspace.id, {'arguments': ['changed']})
        self.assertEqual((await self.send(raw))['error'], 'changed_duplicate')
        await self.permission('view', 'allow')
        raw = json.loads(self.make('tree')); raw['source_device_id'] = self.c.local_id
        from olive.connect.network_wire import STUDIO_REQUEST
        # Bypass the requester's honest source check; target still rejects spoofing.
        channel = next(c for c in self.b.network.channels.values() if c.peer == self.a.local_id)
        values = []
        await asyncio.to_thread(self.b.studio.receive, canonical(raw), channel, lambda x: values.append(json.loads(x)))
        self.assertEqual(values[0]['error'], 'invalid_request')
        await asyncio.to_thread(self.b.studio.unshare, self.a.local_id, self.share['workspace_id'])
        self.assertEqual((await self.send(self.make('tree')))['error'], 'workspace_not_shared')

    async def test_permission_change_between_claim_and_effect_denies_save(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        await self.permission('view', 'allow'); await self.permission('edit', 'allow')
        read = (await self.send(self.make('read', {'path': 'main.py'})))['result']
        raw = self.make('save', {'path': 'main.py', 'expected_hash': read['revision'], 'text': 'unauthorized'})
        transaction = self.b.repository.transaction
        claim = self.b.studio.store.claim
        injected = [False, False]
        def claimed(db, req):
            claim(db, req); injected[0] = True
        @contextmanager
        def boundary(**kwargs):
            with transaction(**kwargs) as db: yield db
            if injected[0] and not injected[1]:
                injected[1] = True
                self.b.set_permission(self.a.local_id, 'studio.edit', 'deny', scope=self.share['workspace_id'])
        with patch.object(self.b.repository, 'transaction', boundary), patch.object(self.b.studio.store, 'claim', claimed):
            result = await self.send(raw)
        self.assertEqual(result['error'], 'permission_denied')
        self.assertEqual(Path(self.workspace.root_path, 'main.py').read_text(), read['text'])

    async def test_local_dirty_buffer_and_staging_race_cannot_be_overwritten(self):
        from unittest.mock import patch
        await self.permission('view', 'allow'); await self.permission('edit', 'allow')
        read = (await self.send(self.make('read', {'path': 'main.py'})))['result']
        local = self.s.studio.service(self.workspace.id)
        local.open_file('main.py'); local.update('main.py', 'local draft')
        def save(): return self.make('save', {'path': 'main.py', 'expected_hash': read['revision'], 'text': 'remote'})
        self.assertEqual((await self.send(save()))['error'], 'revision_conflict')
        local.update('main.py', read['text'])
        write = Path.write_text
        def race(path, text, **kwargs):
            result = write(path, text, **kwargs)
            if path.name.startswith('main.py.') and path.suffix == '.tmp':
                write(Path(self.workspace.root_path, 'main.py'), 'concurrent local edit', encoding='utf-8')
            return result
        with patch.object(Path, 'write_text', race):
            self.assertEqual((await self.send(save()))['error'], 'revision_conflict')
        self.assertEqual(Path(self.workspace.root_path, 'main.py').read_text(), 'concurrent local edit')

    async def test_disconnect_stops_job_and_original_request_never_resumes(self):
        await self.permission('run', 'allow')
        Path(self.workspace.root_path, 'main.py').write_text('import time\ntime.sleep(60)\n')
        raw = self.make('run'); start = await self.send(raw)
        job = self.b.studio.jobs[(self.a.local_id, start['result']['job_id'])]
        async with asyncio.timeout(3):
            while job.handle is None: await asyncio.sleep(.01)
        await asyncio.to_thread(self.a.network.disconnect, self.b.local_id)
        self.assertTrue(await asyncio.to_thread(job.released.wait, 5))
        self.assertFalse(self.s.run_service._processes)
        count = len(self.s.run_service.sessions)
        self.channel = await asyncio.to_thread(self.a.network.connect, self.b.local_id, '127.0.0.1', self.b.network.port)
        await self.send(raw)
        self.assertEqual(len(self.s.run_service.sessions), count)

    async def test_run_permission_removed_and_unpolled_job_cancel(self):
        await self.permission('run', 'allow')
        Path(self.workspace.root_path, 'main.py').write_text('import time\ntime.sleep(60)\n')
        started = await self.send(self.make('run'))
        job = self.b.studio.jobs[(self.a.local_id, started['result']['job_id'])]
        async with asyncio.timeout(3):
            while job.handle is None: await asyncio.sleep(.01)
        await self.permission('run', 'deny')
        self.assertTrue(await asyncio.to_thread(job.released.wait, 5))
        self.assertFalse(self.s.run_service._processes)
        await self.permission('run', 'allow')
        started = await self.send(self.make('run'))
        job = self.b.studio.jobs[(self.a.local_id, started['result']['job_id'])]
        job.last_poll -= 16  # Advance existing monotonic acknowledgement expiry.
        self.assertTrue(await asyncio.to_thread(job.released.wait, 5))
        self.assertFalse(self.s.run_service._processes)

    async def test_output_bounds_stderr_success_and_no_secret_environment(self):
        import os
        from unittest.mock import patch
        await self.permission('run', 'allow')
        Path(self.workspace.root_path, 'main.py').write_text('import os,sys\nprint(os.environ.get("C8_SECRET_TOKEN", "absent"))\nprint("x"*20000)\nprint("warning", file=sys.stderr)\n')
        with patch.dict(os.environ, {'C8_SECRET_TOKEN': 'never-leak-this'}):
            done = await self.finished(await self.send(self.make('run')))
        self.assertEqual(done['state'], 'completed')
        self.assertTrue(done['truncated']); self.assertLessEqual(len(done['output'].encode()), 12000)
        self.assertNotIn('never-leak-this', str(done))
        self.assertIn('warning', done['output'])

    async def test_tree_bounds_workspace_repoint_and_duplicate_name_identity(self):
        from olive.services.workspace_service import WorkspaceService
        await self.permission('view', 'allow')
        root = Path(self.workspace.root_path)
        for i in range(540): (root / f'file{i}.py').write_text('x')
        deep = root.joinpath(*(['nested'] * 10)); deep.mkdir(parents=True); (deep / 'secret.py').write_text('hidden')
        value = (await self.send(self.make('tree')))['result']
        self.assertLessEqual(len(value['entries']), 512); self.assertTrue(value['truncated'])
        self.assertTrue(all(len(v['path'].split('/')) <= 8 for v in value['entries']))
        other = self.root / 'other'; other.mkdir(); (other / 'main.py').write_text('private')
        other_workspace = WorkspaceService(self.s.workspace_repo).create(self.workspace.title, other)
        self.assertNotEqual(other_workspace.id, self.workspace.id)
        self.workspace.root_path = str(other); self.s.workspace_repo.save(self.workspace)
        self.assertEqual((await self.send(self.make('read', {'path': 'main.py'})))['error'], 'workspace_unavailable')

    async def test_replay_survives_restart_metadata_only_and_changed_save_denied(self):
        from olive.connect.studio_store import StudioStore
        await self.permission('view', 'allow'); await self.permission('edit', 'allow')
        read = (await self.send(self.make('read', {'path': 'main.py'})))['result']
        raw = self.make('save', {'path': 'main.py', 'expected_hash': read['revision'], 'text': 'print("PRIVATE_SOURCE_MARKER")\n'})
        value = await self.send(raw)
        self.b.studio.store = StudioStore(self.b.repository)
        self.assertEqual(await self.send(raw), value)
        self.assertNotIn(b'PRIVATE_SOURCE_MARKER', self.b.repository.path.read_bytes())
        self.assertNotIn(str(self.workspace.root_path).encode(), self.b.repository.path.read_bytes())

    async def test_local_execution_denial_and_untrusted_workspace_are_preserved(self):
        await self.permission('build', 'allow')
        self.workspace.trust_level = 'untrusted'; self.s.workspace_repo.save(self.workspace)
        result = await self.finished(await self.send(self.make('build')))
        self.assertEqual(result['state'], 'failed'); self.assertFalse(self.s.run_service._processes)
        self.workspace.trust_level = 'approved'; self.s.workspace_repo.save(self.workspace)
        self.s.permissions.save({'terminal.execute': 'deny'})
        result = await self.finished(await self.send(self.make('build')))
        self.assertEqual(result['error'], 'permission_denied'); self.assertFalse(self.s.run_service._processes)

    async def test_pending_approval_changed_file_requires_new_authority(self):
        await self.permission('view', 'allow'); await self.permission('edit', 'ask')
        read = (await self.send(self.make('read', {'path': 'main.py'})))['result']
        raw = self.make('save', {'path': 'main.py', 'expected_hash': read['revision'], 'text': 'remote'})
        await self.send(raw); await self.approve(True)
        Path(self.workspace.root_path, 'main.py').write_text('changed on target')
        self.assertEqual((await self.send(raw))['error'], 'revision_conflict')
        self.assertEqual(Path(self.workspace.root_path, 'main.py').read_text(), 'changed on target')


    async def test_cancel_reaps_owned_descendant_and_duplicate_cannot_spawn(self):
        import psutil
        await self.permission('run', 'allow')
        Path(self.workspace.root_path, 'main.py').write_text('import subprocess,sys,time\np = subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])\nprint(p.pid, flush=True)\ntime.sleep(60)\n')
        raw = self.make('run'); start = await self.send(raw)
        self.assertEqual((await self.send(raw))['result']['job_id'], start['result']['job_id'])
        self.assertEqual((await self.send(self.make('run')))['error'], 'busy')
        jid = start['result']['job_id']
        async with asyncio.timeout(5):
            while True:
                status = (await self.send(self.make('run_status', {'job_id': jid})))['result']
                if status.get('output', '').strip().isdigit(): break
                await asyncio.sleep(.05)
        child = psutil.Process(int(status['output'].strip()))
        changed = json.loads(raw); changed['expires_at'] -= 1
        self.assertEqual((await self.send(canonical(changed)))['error'], 'changed_duplicate')
        self.assertEqual(len(self.s.run_service.sessions), 1)
        await self.send(self.make('run_cancel', {'job_id': jid})); await self.finished(start)
        await asyncio.to_thread(child.wait, 3)
        self.assertFalse(self.s.run_service._processes)

    async def test_share_count_and_pending_approval_bounds(self):
        from olive.services.workspace_service import WorkspaceService
        for i in range(7):
            root = self.root / f'extra{i}'; root.mkdir()
            w = WorkspaceService(self.s.workspace_repo).create('Same title', root)
            self.b.studio.share(self.a.local_id, w.id)
        root = self.root / 'last'; root.mkdir()
        w = WorkspaceService(self.s.workspace_repo).create('Same title', root)
        with self.assertRaises(ConnectError): self.b.studio.share(self.a.local_id, w.id)
        await self.permission('view', 'ask')
        for _ in range(16):
            self.assertEqual((await self.send(self.make('read', {'path': 'main.py'})))['error'], 'confirmation_required')
        self.assertEqual((await self.send(self.make('read', {'path': 'main.py'})))['error'], 'busy')


    async def test_missing_toolchain_does_not_leave_invisible_session_or_job(self):
        await self.permission('run', 'allow'); await self.permission('test', 'allow')
        missing = str(self.root / 'not-installed' / 'python')
        self.s.studio_tooling.config_save(self.workspace.id, {'interpreter': missing})
        for operation in ('run', 'test'):
            result = await self.finished(await self.send(self.make(operation)))
            self.assertEqual(result['error'], 'toolchain_unavailable')
            self.assertFalse(self.s.run_service._processes)
            self.assertFalse(self.s.run_service.sessions)
            self.assertFalse(self.s.studio_tooling.jobs)
        self.s.studio_tooling.config_save(self.workspace.id, {})
        self.assertEqual((await self.finished(await self.send(self.make('run'))))['state'], 'completed')

    async def test_shared_third_peer_cannot_poll_or_cancel_another_owned_job(self):
        await self.permission('run', 'allow')
        Path(self.workspace.root_path, 'main.py').write_text('import time\ntime.sleep(60)\n')
        started = await self.send(self.make('run'))
        shared = (await asyncio.to_thread(self.b.studio.share, self.c.local_id, self.workspace.id))[0]
        shared = (await asyncio.to_thread(self.b.studio.permission, self.c.local_id, shared['workspace_id'], 'studio.run', 'allow'))[0]
        for operation in ('run_status', 'run_cancel'):
            raw = request(self.c.local_id, self.b.local_id, operation, shared['workspace_id'], shared['share_revision'],
                {'job_id': started['result']['job_id']})
            self.assertEqual((await self.send(raw, self.third))['error'], 'workspace_unavailable')
        job = self.b.studio.jobs[(self.a.local_id, started['result']['job_id'])]
        self.assertFalse(job.cancelled)
        await self.send(self.make('run_cancel', {'job_id': started['result']['job_id']}))
        await self.finished(started)

class StudioProtocolTests(unittest.TestCase):
    def test_rejects_unknown_operations_fields_paths_and_commands(self):
        base = json.loads(request(str(uuid.uuid4()), str(uuid.uuid4()), 'read', str(uuid.uuid4()), 1, {'path': 'main.py'}))
        for path in ('/etc/passwd', '../secret', 'C:\\Users\\secret', 'a/../b', 'a//b', 'a\x00b'):
            value = {**base, 'arguments': {'path': path}}
            with self.assertRaises(ConnectError): StudioRequest.decode(canonical(value))
        for op in ('terminal', 'shell.remote', 'install', 'debug', 'git', 'mail', 'browser', 'models.remote', 'share', 'permission', 'unrevoke'):
            with self.assertRaises(ConnectError): StudioRequest.decode(canonical({**base, 'operation': op}))
        for operation in ('build', 'test', 'run'):
            for arguments in ({'command': 'bash -c whoami'}, {'executable': 'powershell'}, {'arguments': ['-c', 'evil']}, {'install': True}, {'configuration': 'changed'}):
                with self.assertRaises(ConnectError):
                    StudioRequest.decode(canonical({**base, 'operation': operation, 'arguments': arguments}))
        for extra in ({'command': 'bash -c whoami'}, {'approved': True}, {'path': '/etc'}):
            with self.assertRaises(ConnectError): StudioRequest.decode(canonical({**base, **extra}))
