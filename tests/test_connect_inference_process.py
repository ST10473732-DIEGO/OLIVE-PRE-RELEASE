import multiprocessing
from pathlib import Path
import tempfile
import unittest

from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_network import pair
from tests.test_connect_pairing import MemoryVault
from tests.connect_inference_process_fixture import worker


class InferenceProcessTests(unittest.TestCase):
    def test_two_process_off_deny_allow_once_allow_cancel_and_chat_ownership(self):
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vaults = [MemoryVault(), MemoryVault()]
            services = [DesktopDeviceService(root / str(i), key_store=DeviceKeyStore(v)) for i, v in enumerate(vaults)]
            pair(*services)
            ids = [s.local_id for s in services]
            for s in services:
                s.close()
            pipes, children, ports = [], [], []
            def call(index, *args):
                pipes[index].send(args)
                self.assertTrue(pipes[index].poll(15), args[0])
                result = pipes[index].recv()
                self.assertFalse(isinstance(result, dict) and 'fixture_error' in result, (args[0], result))
                return result
            try:
                for i in range(2):
                    parent, child = context.Pipe()
                    process = context.Process(target=worker, args=(child, str(root / str(i)), vaults[i].values))
                    process.start(); child.close()
                    pipes.append(parent); children.append(process)
                    self.assertTrue(parent.poll(10)); ports.append(parent.recv())
                call(0, 'connect', ids[1], ports[1])
                self.assertEqual(call(1, 'policy', ids[0]), 'deny')
                call(0, 'send', ids[1], 'fast', 'Give me code for a calculator.')
                self.assertIn('Off', call(0, 'wait_chat')['error'])
                self.assertEqual(call(1, 'counts')['invocations'], 0)
                call(1, 'permission', ids[0], 'ask')
                call(0, 'send', ids[1], 'fast', 'Explain a loop.')
                pending = call(1, 'pending')[0]
                self.assertNotIn('Explain a loop', str(pending))
                call(1, 'approve', False)
                self.assertIn('denied', call(0, 'wait_chat')['error'])
                self.assertEqual(call(1, 'counts')['invocations'], 0)
                call(0, 'send', ids[1], 'fast', 'Explain a function.')
                call(1, 'pending'); call(1, 'approve', True)
                answer = call(0, 'wait_chat')
                self.assertIsNone(answer['error'])
                messages = call(0, 'stored')[0]['messages']
                self.assertEqual(sum(m['role'] == 'assistant' for m in messages), 1)
                self.assertEqual(messages[-1]['provider']['device_id'], ids[1])
                self.assertEqual(messages[-1]['provider']['preset'], 'fast')
                self.assertEqual(call(1, 'policy', ids[0]), 'ask')
                self.assertEqual(call(1, 'counts')['messages'], 0)
                call(1, 'permission', ids[0], 'allow')
                call(0, 'send', ids[1], 'max', 'Explain a variable.')
                self.assertIsNone(call(0, 'wait_chat')['error'])
                call(1, 'mode', 'long')
                call(0, 'send', ids[1], 'normal', 'Explain an iterator.')
                self.assertTrue(call(0, 'wait_partial')['partial'])
                call(0, 'cancel')
                cancelled = call(0, 'wait_chat')['chat']['messages'][-1]
                self.assertEqual(cancelled['completion_state'], 'incomplete')
                call(1, 'wait_stopped')
                self.assertFalse(call(1, 'counts')['active'])
                self.assertEqual(call(0, 'counts')['invocations'], 0)
            finally:
                for pipe, process in zip(pipes, children):
                    if process.is_alive():
                        pipe.send(('stop',))
                        if pipe.poll(10):
                            pipe.recv()
                        process.join(10)
                    if process.is_alive():
                        process.terminate(); process.join(3)
                    pipe.close()
                for process in children:
                    self.assertEqual(process.exitcode, 0)
