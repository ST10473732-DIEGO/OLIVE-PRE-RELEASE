"""One conservative runtime-owned read-sync loop, never an outbox worker."""
import asyncio
import time
from ..agent.permission_service import PermissionDecision


class BackgroundSync:
    def __init__(self,mail):
        self.m=mail;self.task=None;self.closed=False;self.next_due={};self.active=None

    def start(self):
        if not self.task:self.task=asyncio.create_task(self.run())

    async def tick(self):
        if self.closed or getattr(self.m.s,'restart_required',False):return
        # An enabled preference is not a new permission grant. Ask/Deny remain
        # interactive; only an existing explicit Allow permits unattended reads.
        if any(self.m.s.permissions.evaluate(k).decision!=PermissionDecision.ALLOW for k in ('mail.read','mail.connect')):return
        for connection in self.m.connections.list()['items']:
            if self.closed:return
            if not connection['enabled'] or not connection['imap'] or not connection['sync_enabled']:continue
            identity=connection['id']
            if time.monotonic()<self.next_due.get(identity,0) or identity in self.m.sync.active:continue
            self.next_due[identity]=time.monotonic()+300
            self.active=identity;self.m.s.publish('mail.background',{'active':True,'connection_id':identity})
            try:
                await self.m.call('mail.sync',{'connection_id':identity,'folder':'INBOX','limit':50})
            except Exception as error:
                self.m.s.publish('mail.attention',{'connection_id':identity,'category':type(error).__name__,'message':'Automatic cache refresh did not complete. Local Mail remains available.'})
            finally:
                self.active=None;self.m.s.publish('mail.background',{'active':False,'connection_id':identity})

    async def run(self):
        while not self.closed:
            await asyncio.sleep(15)
            await self.tick()

    async def close(self):
        self.closed=True
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
