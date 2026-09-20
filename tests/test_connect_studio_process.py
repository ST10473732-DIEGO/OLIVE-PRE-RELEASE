import json
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest

from olive.connect.contracts import canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.connect.studio_protocol import request
from tests.test_connect_network import pair
from tests.test_connect_pairing import MemoryVault
from tests.connect_studio_process_fixture import worker


class StudioProcessTests(unittest.TestCase):
    live = False

    def test_two_process_workspace_approval_revision_jobs_and_revocation(self):
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vaults = [MemoryVault(), MemoryVault()]
            endpoints = [DesktopDeviceService(root / str(i), key_store=DeviceKeyStore(v)) for i, v in enumerate(vaults)]
            pair(*endpoints)
            ids = [s.local_id for s in endpoints]
            for s in endpoints: s.close()
            pipes, children, info = [], [], []
            def call(index, *args):
                pipes[index].send(args)
                self.assertTrue(pipes[index].poll(90 if self.live else 15), args[0])
                value = pipes[index].recv()
                self.assertFalse(isinstance(value, dict) and 'fixture_error' in value, value)
                return value
            try:
                for i in range(2):
                    parent, child = context.Pipe()
                    process = context.Process(target=worker, args=(child, str(root / str(i)), vaults[i].values, self.live))
                    process.start(); child.close(); pipes.append(parent); children.append(process)
                    self.assertTrue(parent.poll(60 if self.live else 10)); info.append(parent.recv())
                call(0, 'connect', ids[1], info[1]['port'])
                share = call(1, 'share', ids[0])[0]
                def policy(capability, decision):
                    nonlocal share
                    share = call(1, 'permission', ids[0], share['workspace_id'], 'studio.' + capability, decision)[0]
                def make(op, args=None):
                    return request(ids[0], ids[1], op, None if op == 'workspaces' else share['workspace_id'],
                                   0 if op == 'workspaces' else share['share_revision'], args)
                def send(raw): return call(0, 'request', ids[1], raw)
                def finish(start):
                    deadline = time.monotonic() + (60 if self.live else 10)
                    while time.monotonic() < deadline:
                        v = send(make('run_status', {'job_id': start['result']['job_id']}))
                        self.assertIsNone(v['error'], v)
                        if v['result']['state'] not in ('starting', 'running', 'cancelling'): return v['result']
                        time.sleep(.05)
                    self.fail('job did not release')
                self.assertEqual(send(make('workspaces'))['result']['workspaces'], [])
                self.assertEqual(send(make('read', {'path': 'main.py'}))['error'], 'permission_denied')
                policy('view', 'ask')
                raw = make('read', {'path': 'main.py'})
                self.assertEqual(send(raw)['error'], 'confirmation_required')
                call(1, 'approve', False)
                self.assertEqual(send(raw)['error'], 'permission_denied')
                raw = make('read', {'path': 'main.py'}); send(raw); call(1, 'approve', True)
                read = send(raw)['result']; self.assertIn('REMOTE OK', read['text'])
                policy('view', 'allow')
                self.assertIn('main.py', str(send(make('tree'))))
                policy('edit', 'ask')
                raw = make('save', {'path': 'main.py', 'text': 'print("saved")\r\n', 'expected_hash': read['revision']})
                send(raw); call(1, 'approve', False)
                self.assertEqual(send(raw)['error'], 'permission_denied')
                self.assertEqual(call(1, 'bytes'), read['text'].encode())
                raw = make('save', json.loads(raw)['arguments']); send(raw); call(1, 'approve', True)
                saved = send(raw)
                self.assertEqual(saved['result']['state'], 'saved')
                self.assertEqual(call(1, 'bytes'), b'print("saved")\r\n')
                self.assertEqual(send(raw), saved)
                duplicate = json.loads(raw); duplicate['arguments']['text'] = 'changed duplicate'
                self.assertEqual(send(canonical(duplicate))['error'], 'changed_duplicate')
                call(1, 'edit_local', b'print("local")\n')
                self.assertEqual(send(make('save', {'path': 'main.py', 'text': 'stale', 'expected_hash': saved['result']['revision']}))['error'], 'revision_conflict')
                latest = send(make('read', {'path': 'main.py'}))['result']
                valid = make('save', {'path': 'main.py', 'text': 'print("rebased")\n', 'expected_hash': latest['revision']})
                send(valid); call(1, 'approve', True)
                self.assertEqual(send(valid)['result']['state'], 'saved')
                self.assertEqual(call(1, 'bytes'), b'print("rebased")\n')
                for op in ('build', 'test', 'run'):
                    self.assertEqual(send(make(op))['error'], 'permission_denied')
                    policy(op, 'ask')
                    raw = make(op); send(raw); call(1, 'approve', False)
                    starts = call(1, 'counts')['starts']
                    self.assertEqual(send(raw)['error'], 'permission_denied')
                    self.assertEqual(call(1, 'counts')['starts'], starts)
                    raw = make(op); send(raw); call(1, 'approve', True)
                    started = send(raw); result = finish(started)
                    self.assertEqual(result['state'], 'completed', result)
                    send(raw)
                    self.assertEqual(call(1, 'counts')['starts'], starts + 1)
                if self.live:
                    self.assertEqual(call(1, 'dotnet_fixture', 'net10.0')['exit_code'], 0)
                    self.assertIn('REMOTE CSHARP OK', send(make('read', {'path': 'Program.cs'}))['result']['text'])
                    for op in ('build', 'run'):
                        raw = make(op); send(raw); call(1, 'approve', True)
                        result = finish(send(raw)); self.assertEqual(result['state'], 'completed', result)
                        if op == 'run': self.assertIn('REMOTE CSHARP OK', result['output'])
                    # No external test packages: .NET test is truthfully unavailable.
                policy('run', 'allow')
                if not self.live:  # Python long-running fixture owns no external resources.
                    call(1, 'edit_local', b'import time\nprint("running", flush=True)\ntime.sleep(60)\n')
                    started = send(make('run'))
                    deadline = time.monotonic() + 5
                    while call(1, 'counts')['active'] == 0 and time.monotonic() < deadline: time.sleep(.02)
                    call(1, 'revoke', ids[0])
                    deadline = time.monotonic() + 5
                    while call(1, 'counts')['active'] and time.monotonic() < deadline: time.sleep(.02)
                    self.assertEqual(call(1, 'counts')['active'], 0)
                self.assertEqual(call(0, 'counts')['starts'], 0)
            finally:
                for pipe, process in zip(pipes, children):
                    if process.is_alive():
                        pipe.send(('stop',))
                        if pipe.poll(15):
                            result = pipe.recv()
                            self.assertEqual(result, {'active': 0, 'tasks': 0})
                        process.join(10)
                    if process.is_alive(): process.terminate(); process.join(3)
                    pipe.close()
                for process in children: self.assertEqual(process.exitcode, 0)
