"""Synthetic process harness. Local multiprocessing pipe is NOT Connect protocol."""
import multiprocessing
from pathlib import Path
import tempfile
import time

from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import pair, request
from olive.connect.contracts import ConnectError, canonical


def failure(error, net, command):
    """Fixed labels and path-free diagnostics only; never arbitrary exception text."""
    detail = dict(op=command[0], exception=type(error).__name__,
                  code=str(error) if isinstance(error, ConnectError) else None,
                  sqlite=getattr(error, 'sqlite_errorname', None))
    if command[0] in ('connect', 'request', 'status') and len(command) > 1:
        try:
            detail.update(status=net.status(command[1]), diagnostics=net.debug_snapshot(command[1]))
        except Exception as nested:
            detail['diagnostics_unavailable'] = type(nested).__name__
    return detail


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
            except Exception as error:
                pipe.send({'error': 'fixture_operation_failed', 'detail': failure(error, net, command)})
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
        def result(i, *command):
            response = call(i, *command)
            # An error response still fails; it now says which error it was.
            assert 'result' in response, f'{command[0]} failed: {response}'
            return response['result']
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
                wait(lambda: any(e['instance'] == target(1) for e in result(0, 'nearby')))
                wait(lambda: any(e['instance'] == target(0) for e in result(1, 'nearby')))
                wait(lambda: any(e['instance'] == target(2) for e in result(0, 'nearby')))
            connected = result(0, 'connect', ids[1], target(1))
            assert connected['encrypted'], connected
            first = call(0, 'request', ids[1], raw)
            assert 'result' in first and first['result']['result']['pong'], first
            assert result(0, 'request', ids[1], status_raw)['result']['transport'] == 'local'
            call(0, 'disconnect', ids[1])
            wait(lambda: result(1, 'status', ids[0])['state'] == 'offline')
            assert 'error' in call(0, 'connect', ids[1], target(2)), 'spoof accepted'
            connected = result(0, 'connect', ids[1], target(1))
            assert connected['encrypted'], connected
            assert call(0, 'request', ids[1], raw) == first
            call(1, 'revoke', ids[0])
            wait(lambda: result(0, 'status', ids[1])['state'] == 'offline')
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
