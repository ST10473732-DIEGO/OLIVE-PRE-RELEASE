"""Bounded reviewed command output, backed by the existing terminal tool policy."""
import asyncio
from collections import OrderedDict
import uuid

class StudioCommands:
    def __init__(self,host):
        self.host=host;self.records=OrderedDict();self.active={}
    def publish(self,record):self.host.publish('studio.command',dict(record))
    async def run(self,workspace_id,command,shell):
        if any(record['workspace_id']==workspace_id and identity in self.active for identity,record in self.records.items()):
            raise ValueError('Stop the current reviewed command in this workspace first')
        if len(self.active)>=12:raise ValueError('Finish an active command before starting another')
        identity=str(uuid.uuid4());cancellation=asyncio.Event()
        record={'id':identity,'workspace_id':workspace_id,'state':'running','summary':'Reviewing and executing the requested command.','stdout':'','stderr':'','shell':shell,'exit_code':None}
        self.records[identity]=record;self.active[identity]=(cancellation,asyncio.current_task())
        while len(self.records)>12:
            completed=next((key for key in self.records if key not in self.active),None)
            if completed is None:break
            self.records.pop(completed)
        self.publish(record)
        def progress(value):
            if value.get('channel') in {'stdout','stderr'}:
                record[value['channel']]=str(value.get('text',''))[-12000:];self.publish(record)
        try:
            result=await self.host.services.studio.terminal(workspace_id,command,shell,cancellation_event=cancellation,progress=progress,return_outcome=True)
            record.update({key:result[key] for key in ('state','summary','task_id','stdout','stderr','exit_code') if key in result})
            if cancellation.is_set() and record['state']=='blocked':record.update(state='cancelled',summary='Command cancelled before execution.')
        except asyncio.CancelledError:
            record.update(state='cancelled',summary='Command cancelled. Inspect output for any earlier completed work.')
            raise
        except Exception:
            record.update(state='failed',summary='The command could not complete. Review workspace trust and command configuration.')
            raise
        finally:
            self.active.pop(identity,None);record['stdout']=record['stdout'][-12000:];record['stderr']=record['stderr'][-12000:];self.publish(record)
        return dict(record)
    def cancel(self,command_id):
        active=self.active.get(command_id)
        if not active:raise ValueError('This command is no longer active')
        cancellation,task=active;cancellation.set()
        # Cancel the owned request also interrupts an outstanding approval; the tool
        # finally block terminates its process and drains its owned readers.
        task.cancel();self.records[command_id]['state']='cancelling';self.publish(self.records[command_id])
        return {'cancellation_requested':True}
