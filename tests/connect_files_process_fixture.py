"""Ordinary C3 backend in a child process with trusted Host approval responses."""
import asyncio
from pathlib import Path
from olive.bridge.host import Host
from olive.connect.approvals import ConnectApprovals
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault


def worker(pipe, profile, values):
    async def run():
        vault=MemoryVault(); vault.values=values
        service=DesktopDeviceService(Path(profile),key_store=DeviceKeyStore(vault))
        host=Host(lambda _:None); host.activity=lambda:None
        service.approvals=ConnectApprovals(service,host.confirm,asyncio.get_running_loop())
        try:
            network=service.enable_network('127.0.0.1',discovery=False)
            pipe.send(network.port)
            while True:
                op,*args=await asyncio.to_thread(pipe.recv)
                try:
                    if op=='stop':
                        await asyncio.to_thread(service.close);pipe.send(True);return
                    if op=='connect':result=bool(await asyncio.to_thread(network.connect,args[0],'127.0.0.1',args[1]))
                    elif op=='permission':result=await asyncio.to_thread(service.set_permission,*args)
                    elif op=='prepare':result=await asyncio.to_thread(service.files.prepare,*args)
                    elif op=='start':result=await asyncio.to_thread(service.files.start,*args)
                    elif op=='list':result=await asyncio.to_thread(service.files.list)
                    elif op=='export':result=await asyncio.to_thread(service.files.export,*args)
                    elif op=='pending':result=[p[0] for p in host.pending.values()]
                    elif op=='approve':
                        value,_=next(iter(host.pending.values()))
                        result=await host.execute('approval.respond',dict(approval_id=value['id'],fingerprint=value['fingerprint'],approved=args[0]))
                    elif op=='policy':result=service.permission(*args).value
                    elif op=='disconnect':result=network.disconnect(*args)
                    elif op=='revoke':result=service.revoke(*args)
                    else:raise ValueError('fixture_command')
                    pipe.send(result)
                except Exception as error:pipe.send({'fixture_error':str(error)})
        finally:
            await asyncio.to_thread(service.close);pipe.close()
    asyncio.run(run())
