"""Synthetic process harness. Local multiprocessing pipe is NOT Connect protocol."""
import multiprocessing
from pathlib import Path
import tempfile
import time

from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import pair, request
from olive.connect.contracts import canonical


def worker(pipe, profile, values, discovery):
    vault = MemoryVault()
    vault.values = values
    service = DesktopDeviceService(Path(profile), key_store=DeviceKeyStore(vault))
    try:
        net = service.enable_network('127.0.0.1', discovery=discovery)
        pipe.send(dict(port=net.port, instance=net.discovery.name if net.discovery else None))
        while True:
            command = pipe.recv()
            try:
                op = command[0]
                if op == 'stop':
                    service.close()
                    pipe.send({'stopped': True})
                    break
                if op == 'nearby':
                    result = net.discovery.nearby()
                elif op == 'connect':
                    _, peer, endpoint = command
                    if discovery:
                        net.connect_discovered(peer, endpoint)
                    else:
                        net.connect(peer, '127.0.0.1', endpoint)
                    result = net.status(peer)
                elif op == 'request':
                    _, peer, raw = command
                    result = net.channels[peer].request(raw)
                elif op == 'disconnect':
                    net.disconnect(command[1]); result = True
                elif op == 'revoke':
                    service.revoke(command[1]); result = True
                elif op == 'status':
                    result = net.status(command[1])
                else:
                    raise ValueError()
                pipe.send({'result': result})
            except Exception:
                pipe.send({'error': 'fixture_operation_failed'})
    finally:
        service.close()
        pipe.close()


def acceptance(discovery=False):
    context = multiprocessing.get_context('spawn')
    with tempfile.TemporaryDirectory(prefix='olive-c3-process-') as root:
        vaults = [MemoryVault() for _ in range(3)]
        services = [DesktopDeviceService(Path(root) / str(i), key_store=DeviceKeyStore(v))
                    for i, v in enumerate(vaults)]
        a, b, c = services
        pair(a, b)
        b.set_permission(a.local_id, 'connect.ping', 'allow')
        b.set_permission(a.local_id, 'device.status', 'allow')
        c.cryptographic_identity()
        ids = [s.local_id for s in services]
        raw = canonical(request(a, b))
        status_raw = canonical(request(a, b, 'device.status'))
        for service in services:
            service.close()
        children, pipes, endpoints = [], [], []
        def call(i, *command):
            pipes[i].send(command)
            if not pipes[i].poll(10):
                raise AssertionError('fixture process timeout')
            return pipes[i].recv()
        def wait(predicate, timeout=10):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if predicate():
                    return
                time.sleep(.05)
            raise AssertionError('acceptance condition timed out')
        try:
            for i in range(3):
                parent, child = context.Pipe()
                process = context.Process(target=worker,
                    args=(child, str(Path(root) / str(i)), vaults[i].values, discovery))
                process.start(); child.close()
                children.append(process); pipes.append(parent)
                assert parent.poll(10), 'startup timeout'
                endpoints.append(parent.recv())
            target = lambda i: endpoints[i]['instance' if discovery else 'port']
            if discovery:
                wait(lambda: any(e['instance'] == target(1) for e in call(0, 'nearby')['result']))
                wait(lambda: any(e['instance'] == target(0) for e in call(1, 'nearby')['result']))
                wait(lambda: any(e['instance'] == target(2) for e in call(0, 'nearby')['result']))
            assert call(0, 'connect', ids[1], target(1))['result']['encrypted']
            first = call(0, 'request', ids[1], raw)
            assert first['result']['result']['pong']
            assert call(0, 'request', ids[1], status_raw)['result']['result']['transport'] == 'local'
            call(0, 'disconnect', ids[1])
            wait(lambda: call(1, 'status', ids[0])['result']['state'] == 'offline')
            assert 'error' in call(0, 'connect', ids[1], target(2)), 'spoof accepted'
            assert call(0, 'connect', ids[1], target(1))['result']['encrypted']
            assert call(0, 'request', ids[1], raw) == first
            call(1, 'revoke', ids[0])
            wait(lambda: call(0, 'status', ids[1])['result']['state'] == 'offline')
            assert 'error' in call(0, 'connect', ids[1], target(1)), 'revoked accepted'
            for i in range(3):
                assert call(i, 'stop')['stopped']
            for process in children:
                process.join(5)
                assert process.exitcode == 0, 'unclean shutdown'
        finally:
            for process in children:
                if process.is_alive():
                    process.terminate()
                process.join(5)
            for pipe in pipes:
                pipe.close()
