"""Separate ordinary C3 endpoint and Studio owners, with synthetic identities only."""
import asyncio
from pathlib import Path
from olive.bridge.host import Host
from olive.connect.approvals import ConnectApprovals
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.services.workspace_service import WorkspaceService
from tests.test_connect_pairing import MemoryVault
from tests.connect_studio_fixture import graph


def worker(pipe, profile, values, live=False):
    async def run():
        vault = MemoryVault(); vault.values = values
        host = Host(lambda _: None); host.activity = lambda: None
        service = DesktopDeviceService(Path(profile), key_store=DeviceKeyStore(vault))
        if live:
            from olive.application.service_container import ServiceContainer
            service.close()
            s = ServiceContainer(lambda *args: None, host.confirm, data_dir=Path(profile), migrate=False)
            service = s.connect
            service.identities.key_store = DeviceKeyStore(vault)
            await s.initialize()
            root = Path(profile) / 'fixture'; root.mkdir(exist_ok=True)
            (root / 'main.py').write_text('print("REMOTE OK")\n', encoding='utf-8')
            (root / 'tests').mkdir(exist_ok=True)
            (root / 'tests' / 'test_example.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
            workspace = WorkspaceService(s.workspace_repo).create('Fixture', root)
        else:
            s, workspace = graph(service, Path(profile))
        host.services = s
        service.approvals = ConnectApprovals(service, host.confirm, asyncio.get_running_loop())
        network = service.enable_network('127.0.0.1', discovery=False)
        pipe.send({'port': network.port, 'workspace': workspace.id})
        try:
            while True:
                op, *args = await asyncio.to_thread(pipe.recv)
                try:
                    if op == 'stop':
                        await service.studio.shutdown()
                        if live:
                            await s.shutdown()
                        else:
                            await s.studio_tooling.shutdown()
                        await asyncio.to_thread(service.close)
                        pipe.send({'active': len(s.run_service._processes), 'tasks': len(service.studio.tasks)})
                        return
                    if op == 'connect':
                        await asyncio.to_thread(network.connect, args[0], '127.0.0.1', args[1]); result = True
                    elif op == 'request':
                        channel = network.channels[args[0]]
                        result = await asyncio.to_thread(channel.studio_request, args[1])
                    elif op == 'share':
                        result = await asyncio.to_thread(service.studio.share, args[0], workspace.id)
                    elif op == 'permission':
                        result = await asyncio.to_thread(service.studio.permission, *args)
                    elif op == 'approve':
                        async with asyncio.timeout(5):
                            while not host.pending: await asyncio.sleep(.01)
                        value, _ = next(iter(host.pending.values()))
                        result = await host.execute('approval.respond', dict(approval_id=value['id'], fingerprint=value['fingerprint'], approved=args[0]))
                        await asyncio.sleep(.01)
                    elif op == 'edit_local':
                        (Path(workspace.root_path) / 'main.py').write_bytes(args[0]); result = True
                    elif op == 'bytes':
                        result = (Path(workspace.root_path) / 'main.py').read_bytes()
                    elif op == 'revoke':
                        await asyncio.to_thread(service.revoke, args[0]); result = True
                    elif op == 'disconnect':
                        await asyncio.to_thread(network.disconnect, args[0]); result = True
                    elif op == 'counts':
                        result = dict(active=len(s.run_service._processes), starts=len(s.run_service.sessions), tasks=len(service.studio.tasks))
                    elif op == 'dotnet_fixture':
                        # Existing SDK only; no install/download. Local fixture preparation.
                        import os
                        import subprocess
                        root = Path(workspace.root_path)
                        sdk = args[0]
                        (root / 'Fixture.csproj').write_text(f'<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>{sdk}</TargetFramework></PropertyGroup></Project>')
                        (root / 'Program.cs').write_text('System.Console.WriteLine("REMOTE CSHARP OK");')
                        from olive.services.run_service import RunService, ExecutionPolicy
                        env = RunService.dotnet_environment(root, ExecutionPolicy().environment())
                        completed = await asyncio.to_thread(subprocess.run, ['dotnet', 'restore', '--ignore-failed-sources'], cwd=root, env=env, capture_output=True, timeout=60)
                        result = {'exit_code': completed.returncode}
                    else:
                        raise ValueError('fixture operation')
                    pipe.send(result)
                except Exception as error:
                    pipe.send({'fixture_error': type(error).__name__, 'detail': str(error)[:300]})
        finally:
            await service.studio.shutdown()
            await asyncio.to_thread(service.close)
            pipe.close()
    asyncio.run(run())
