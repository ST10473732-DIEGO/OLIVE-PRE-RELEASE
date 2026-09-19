"""Shared native tools: one policy/execution path for UI and language requests."""
import asyncio
from datetime import datetime,timedelta,time,timezone
from pathlib import Path
from .contracts import SPEC,MAIN_ONLY,DOMAINS,validate
from .service import PersonalService
from .interchange import Interchange,MAX_BYTES
from .reminders import ReminderScheduler
from ..agent.agent_task import AgentTask
from ..agent.planner import PlannedAction
from ..agent.tool_schema import ToolDefinition,ToolContext
from ..agent.tool_result import ToolResult
from ..agent.direct_action import DirectAction
from ..agent.permission_service import PermissionDecision


def permission(method,args):
 prefix,action=method.split('.')
 if method=='personal.import_cancel':return 'personal.read'
 if prefix=='personal':prefix='contacts' if args.get('kind')=='contact' else 'calendar' if args.get('kind')=='event' else 'personal'
 verb='read' if action in {'get','search','resolve','duplicates','merge_preview','range','free_busy','calendars','history','today'} else 'delete' if action.startswith('delete') else 'merge' if action=='merge' else 'import' if action.startswith('import') else 'export' if action=='export' else 'write'
 return prefix+'.'+verb


class PersonalTool:
 def __init__(self,controller,name):
  self.controller=controller;self.name=name
  self.internal_only=name.startswith(('contacts.','profile.'))
  self.definition=ToolDefinition(name,'Local '+name.replace('.',' '),'personal',{'required':list((SPEC|MAIN_ONLY)[name][0])},
   required_permissions=(permission(name,{}),)+(('calendar.write',) if name=='tasks.schedule' else ())+ (('filesystem.read',) if name in {'personal.import_preview','profile.avatar'} else ('filesystem.write',) if name=='personal.export' else ()),confirmation_required=name.endswith(('.delete','.merge','delete_calendar','delete_occurrence','import_commit')),timeout_seconds=30)

 async def execute(self,arguments,context):
  validate(self.name,arguments)
  if context.cancellation_event and context.cancellation_event.is_set():raise asyncio.CancelledError()
  # Recheck deterministic Deny immediately before database/file work.
  key=permission(self.name,arguments)
  if self.controller.s.permissions.evaluate(key).decision==PermissionDecision.DENY:raise PermissionError('Permission denied: '+key)
  if self.name=='personal.import_commit':
   preview=self.controller.interchange.previews.get(arguments['preview_id'])
   if not preview:raise ValueError('Import preview expired or was already committed')
   key=('contacts' if preview['kind']=='contact' else 'calendar')+'.import'
   if self.controller.s.permissions.evaluate(key).decision==PermissionDecision.DENY:raise PermissionError('Permission denied: '+key)
  if self.name=='calendar.update':
   old=self.controller.records.get('event',arguments['record_id']);body=arguments['body']
   if body.get('status')=='cancelled' and old['status']!='cancelled':raise ValueError('Use the reviewed event deletion action to cancel a series')
   if any(p.get('cancelled') and not old['exceptions'].get(k,{}).get('cancelled') for k,p in body.get('exceptions',{}).items()):raise ValueError('Use the reviewed occurrence deletion action')
  from .store import WRITE_GUARD,WRITE_SOURCE
  def guard():
   if context.cancellation_event and context.cancellation_event.is_set():raise asyncio.CancelledError()
   for required in {key,*self.definition.required_permissions}:
    if self.controller.s.permissions.evaluate(required).decision==PermissionDecision.DENY:raise PermissionError('Permission denied: '+required)
  token=WRITE_GUARD.set(guard)
  source_token=WRITE_SOURCE.set({'origin':'direct_form' if context.direct_action else 'reviewed_tool','method':self.name})
  try:result=await asyncio.to_thread(self.controller.execute,self.name,arguments)
  except asyncio.CancelledError:
   if context.cancellation_event:context.cancellation_event.set()
   raise
  finally:WRITE_GUARD.reset(token);WRITE_SOURCE.reset(source_token)
  if not permission(self.name,arguments).endswith('.read'):
   self.controller.scheduler.changed()
   self.controller.s.publish('personal.changed',{'domain':self.name.split('.')[0]})
  return ToolResult(True,'Local operation completed',result if isinstance(result,dict) else {'items':result})


class PersonalController:
 def __init__(self,services):
  self.s=services;self.records=PersonalService(services.data_dir/'personal.sqlite3',services.project_repo.load_all,lambda:services.agent_task_repo.load_all() if hasattr(services,'agent_task_repo') else {})
  self.interchange=Interchange(self.records);self.scheduler=ReminderScheduler(self.records,services.publish)
  self.active=set()
  for method in SPEC|MAIN_ONLY:
   if method!='personal.review':services.tool_registry.register(PersonalTool(self,method))

 async def call(self,method,args=None,*,manual=False):
  args=validate(method,args or {})
  if method=='personal.review':
   if not manual:raise ValueError('Use the conversation proposal review surface')
   return await self.s.interaction.review_native(**args)
  task=AgentTask('Local personal operation');cancel=asyncio.Event();self.active.add(cancel)
  ordinary=method.endswith(('.create','.update','.complete','.reopen','.snooze','.dismiss','.save_calendar','.schedule')) or method in MAIN_ONLY
  consent=DirectAction(task.id,method,args) if manual and ordinary else None
  try:
   result=await self.s.agent_executor.execute(task,PlannedAction(method,args,'Review '+method.replace('.',' ')),ToolContext(task.id,cancel,direct_action=consent))
  finally:self.active.discard(cancel)
  # Do not copy contact notes or event descriptions into persisted Agent task logs.
  if not result.success:
   from .errors import PersonalOperationError,guidance
   raise PersonalOperationError(guidance(result,self.s.permissions.DEFAULTS))
  return result.data

 async def close(self):
  for cancel in self.active:cancel.set()
  await self.scheduler.close()

 def execute(self,method,args):
  p=self.records;prefix,action=method.split('.')
  if method=='profile.get':return p.profile()
  if method=='profile.update':return p.save('profile',**args)
  if method=='contacts.resolve':return p.resolve_contact(**args)
  if method=='contacts.duplicates':return p.duplicates(**args)
  if method=='contacts.merge_preview':return p.merge_preview(**args)
  if method=='contacts.merge':return p.merge(args['preview'])
  if method=='calendar.calendars':return p.search('calendar')
  if method=='calendar.save_calendar':return p.save('calendar',**args)
  if method=='calendar.delete_calendar':return p.delete('calendar',**args)
  if method=='calendar.delete_occurrence':return p.delete_occurrence(**args)
  if method=='tasks.schedule':return p.schedule_task(**args)
  if method=='calendar.range':return {'items':p.calendar_range(**args)}
  if method=='calendar.free_busy':return {'items':p.availability(**args),'status':'proposed','message':'These slots are not booked.'}
  if method in {'tasks.complete','tasks.reopen'}:
   record=p.get('task',args['record_id']);body=p.store.body(record);body['status']='completed' if action=='complete' else 'open'
   return p.save('task',body,**args)
  if method=='reminders.history':
   items=self.scheduler.history(**args)
   return {'items':items,'has_more':len(items)==args.get('limit',50),'error':self.scheduler.error}
  if method in {'reminders.snooze','reminders.dismiss'}:return self.scheduler.act(action=action,**args)
  if method=='personal.import_cancel':return {'status':'cancelled','removed':self.interchange.previews.pop(args['preview_id'],None) is not None}
  if method=='personal.import_commit':return self.interchange.commit(args['preview_id'],args['choices'],args.get('allow_partial',False))
  if method=='personal.import_preview':
   path=Path(args['path']);size=path.stat().st_size
   if size>MAX_BYTES:raise ValueError('Import exceeds 2 MB')
   content=path.read_bytes()
   if len(content)>MAX_BYTES:raise ValueError('Import changed or exceeds 2 MB')
   return self.interchange.parse(args['kind'],args['format'],content.decode('utf-8-sig'),args.get('calendar_id',''))
  if method=='personal.export':
   from .files import save_export
   content=self.interchange.export(args['kind'],args['format'])
   save_export(args['path'],content)
   return {'status':'saved','message':'Local export saved. Unsupported fields may not round-trip.'}
  if method=='profile.avatar':
   import base64,io
   from PIL import Image,ImageOps
   path=Path(args['path'])
   if path.stat().st_size>4_000_000:raise ValueError('Choose an image smaller than 4 MB')
   with Image.open(path) as image:
    if image.width*image.height>16_000_000:raise ValueError('Avatar dimensions exceed the safe limit')
    image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((128,128));out=io.BytesIO();image.save(out,format='JPEG',quality=85)
   return {'avatar':'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()}
  if method=='personal.today':
   from .validation import zone
   profile=p.profile();now=datetime.now(zone(profile['timezone']));end=datetime.combine(now.date()+timedelta(days=1),time.min,now.tzinfo)
   allowed=lambda domain:self.s.permissions.evaluate(domain+'.read').decision==PermissionDecision.ALLOW
   return {'events':p.calendar_range(now.isoformat(),end.isoformat())[:5] if allowed('calendar') else [],
    'tasks':p.search('task',view='Today',limit=5)['items'] if allowed('tasks') else [],
    'reminders':[r for r in self.scheduler.history(50) if r['state']=='delivered'][:5] if allowed('reminders') else [],'display_name':profile['display_name'] if allowed('profile') else '',
    'format':{key:profile[key] for key in ('timezone','locale','date_format','time_format')} if allowed('profile') else {}}
  if prefix in DOMAINS:
   kind=DOMAINS[prefix]
   if action=='search':return p.search(kind,**args)
   if action=='get':return p.get(kind,**args)
   if action in {'create','update'}:return p.save(kind,**args)
   if action=='delete':return p.delete(kind,**args)
  raise ValueError('Unknown native operation')
