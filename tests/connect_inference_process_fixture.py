"""Ordinary device/Chat owners in isolated spawned processes; engine-only fixture."""
import asyncio
from pathlib import Path

from olive.bridge.host import Host
from olive.connect.approvals import ConnectApprovals
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault
from tests.connect_inference_fixture import model_graph


def worker(pipe, profile, values, live=False):
    async def run():
        vault = MemoryVault(); vault.values = values
        service = DesktopDeviceService(Path(profile), key_store=DeviceKeyStore(vault))
        events = []
        partial = asyncio.Event()
        def publish(topic, value):
            events.append((topic, value))
            if topic == 'chat_stream':
                partial.set()
        pending = asyncio.Event()
        def output(value):
            if value.get('topic') == 'approval':
                pending.set()
        host = Host(output); host.activity = lambda: None
        if live:
            # Opt-in host acceptance uses the ordinary complete service container.
            # Observation wraps the existing method; no inference is substituted.
            from types import SimpleNamespace
            from olive.application.service_container import ServiceContainer
            service.close()
            services = ServiceContainer(publish, host.confirm, data_dir=Path(profile), migrate=False)
            service = services.connect
            service.identities.key_store = DeviceKeyStore(vault)
            await services.initialize()
            engine = SimpleNamespace(calls=[], started=asyncio.Event(), stopped=asyncio.Event())
            original = services.ollama.chat_stream
            async def observed(model, *args, **kwargs):
                engine.calls.append({'model': model})
                engine.started.set()
                stream = original(model, *args, **kwargs)
                try:
                    async for text in stream:
                        yield text
                finally:
                    await stream.aclose()
                    engine.stopped.set()
            services.ollama.chat_stream = observed
        else:
            services, engine = await model_graph(service, Path(profile), publish=publish)
        host.services = services
        service.approvals = ConnectApprovals(service, host.confirm, asyncio.get_running_loop())
        task = None
        try:
            network = service.enable_network('127.0.0.1', discovery=False)
            pipe.send(network.port)
            while True:
                op, *args = await asyncio.to_thread(pipe.recv)
                try:
                    if op == 'stop':
                        if task and not task.done():
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                        await service.inference.shutdown()
                        if live:
                            await services.shutdown()
                        await asyncio.to_thread(service.close)
                        pipe.send(True); return
                    if op == 'connect':
                        result = bool(await asyncio.to_thread(network.connect, args[0], '127.0.0.1', args[1]))
                    elif op == 'permission':
                        result = await asyncio.to_thread(service.set_permission, args[0], 'models.remote', args[1])
                    elif op == 'policy':
                        result = service.permission(args[0], 'models.remote').value
                    elif op == 'send':
                        services.chat.run_on(services.current_chat_id, args[0])
                        services.presets.apply(services.chats[services.current_chat_id], args[1])
                        partial.clear()
                        task = asyncio.create_task(services.chat.send(services.current_chat_id, args[2]))
                        result = True
                    elif op == 'wait_chat':
                        try:
                            await asyncio.wait_for(asyncio.shield(task), 150 if live else 10)
                            result = {'error': None}
                        except ValueError as error:
                            result = {'error': str(error)}
                        result['chat'] = services.chat.get()
                    elif op == 'wait_partial':
                        await asyncio.wait_for(partial.wait(), 5)
                        result = services.chat.get()
                    elif op == 'pending':
                        await asyncio.wait_for(pending.wait(), 5)
                        result = [p[0] for p in host.pending.values()]
                    elif op == 'approve':
                        value, _ = next(iter(host.pending.values()))
                        result = await host.execute('approval.respond', dict(approval_id=value['id'], fingerprint=value['fingerprint'], approved=args[0]))
                        pending.clear()
                    elif op == 'mode':
                        engine.mode = args[0]; engine.started.clear(); engine.stopped.clear(); result = True
                    elif op == 'cancel':
                        services.chat.stop(services.current_chat_id); result = True
                    elif op == 'wait_stopped':
                        await asyncio.wait_for(engine.stopped.wait(), 5); result = True
                    elif op == 'counts':
                        result = dict(invocations=len(engine.calls), messages=len(services.chat.get()['messages']),
                            streams=sum(t == 'chat_stream' for t, _ in events), active=bool(service.inference.active),
                            models=[c['model'] for c in engine.calls])
                    elif op == 'stored':
                        result = [c.to_dict() for c in services.chat_repo.load_all().values()]
                    elif op == 'targets':
                        result = await services.remote_inference.targets()
                    else:
                        raise ValueError('fixture_command')
                    pipe.send(result)
                except Exception as error:
                    pipe.send({'fixture_error': type(error).__name__})
        finally:
            await service.inference.shutdown()
            await asyncio.to_thread(service.close)
            pipe.close()
    asyncio.run(run())
