"""Opt-in real local-model C7 acceptance. No downloads; owned temporary profiles.

Run with the project Python and existing Ollama on PATH. OLIVE_START_OLLAMA=1
opts into the existing application-owned, loopback-only process lifecycle.
"""
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_network import pair
from tests.test_connect_pairing import MemoryVault
from tests.connect_inference_process_fixture import worker


def main():
    context = multiprocessing.get_context('spawn')
    with tempfile.TemporaryDirectory(prefix='olive-c7-live-') as directory:
        root = Path(directory)
        vaults = [MemoryVault(), MemoryVault()]
        services = [DesktopDeviceService(root / str(i), key_store=DeviceKeyStore(v)) for i, v in enumerate(vaults)]
        for i, service in enumerate(services):
            service.rename(service.local_id, 'C7 requester' if i == 0 else 'C7 target')
        pair(*services)
        ids = [s.local_id for s in services]
        for service in services:
            service.close()
        pipes, children, ports = [], [], []
        def call(index, *args):
            pipes[index].send(args)
            if not pipes[index].poll(160):
                raise TimeoutError(args[0])
            result = pipes[index].recv()
            if isinstance(result, dict) and 'fixture_error' in result:
                raise RuntimeError((args[0], result))
            return result
        try:
            for i in range(2):
                parent, child = context.Pipe()
                process = context.Process(target=worker, args=(child, str(root / str(i)), vaults[i].values, True))
                process.start(); child.close()
                pipes.append(parent); children.append(process)
                if not parent.poll(90):
                    raise TimeoutError('ordinary backend initialization')
                ports.append(parent.recv())
            call(0, 'connect', ids[1], ports[1])
            status = call(0, 'targets')[0]
            print(json.dumps({'status': status}), flush=True)
            call(1, 'permission', ids[0], 'ask')
            call(0, 'send', ids[1], 'fast', 'Reply with the exact words: OLIVE remote inference works.')
            call(1, 'pending'); call(1, 'approve', False)
            denied = call(0, 'wait_chat')
            assert denied['error'] and call(1, 'counts')['invocations'] == 0
            print(json.dumps({'deny': 'passed', 'invocations': 0}), flush=True)
            for preset in ('fast', 'normal', 'max'):
                if not status['presets'][preset]:
                    print(json.dumps({'preset': preset, 'state': 'model_unavailable'}), flush=True)
                    continue
                call(0, 'send', ids[1], preset, 'Reply with the exact words: OLIVE remote inference works.')
                call(1, 'pending'); call(1, 'approve', True)
                result = call(0, 'wait_chat')
                message = result['chat']['messages'][-1]
                print(json.dumps({'preset': preset, 'error': result['error'],
                    'completion': message.get('completion_state'), 'provider': message.get('provider'),
                    'visible_text': message['content'], 'target': call(1, 'counts'),
                    'permission': call(1, 'policy', ids[0])}), flush=True)
                assert result['error'] is None
                assert message['completion_state'] == 'complete'
                assert message['provider']['device_id'] == ids[1]
                assert message['provider']['preset'] == preset
                assert call(1, 'policy', ids[0]) == 'ask'
                assert call(1, 'counts')['messages'] == 0
            assert call(0, 'counts')['invocations'] == 0
        finally:
            for pipe, process in reversed(list(zip(pipes, children))):
                if process.is_alive():
                    pipe.send(('stop',))
                    if pipe.poll(20):
                        pipe.recv()
                    process.join(20)
                if process.is_alive():
                    process.terminate(); process.join(5)
                pipe.close()
            assert all(p.exitcode == 0 for p in children), 'unclean backend shutdown'
            print(json.dumps({'shutdown': 'passed'}), flush=True)


if __name__ == '__main__':
    main()
