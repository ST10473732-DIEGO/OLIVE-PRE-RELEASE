"""Explicit Personal Core tool/bridge methods and bounded argument contracts."""
import json

SPEC={
 'profile.get':({},{}), 'profile.update':({'record_id':str,'revision':int,'body':dict},{}),
 'contacts.resolve':({'query':str},{'project_id':str}),
 'contacts.duplicates':({'record_id':str},{}),
 'contacts.merge_preview':({'keep_id':str,'remove_id':str},{'choices':dict}),
 'contacts.merge':({'preview':dict},{}),
 'calendar.range':({'after':str,'before':str},{'calendar_ids':list,'timezone':str}),
 'calendar.free_busy':({'after':str,'before':str,'duration':int},{'calendar_ids':list}),
 'calendar.calendars':({},{}),
 'calendar.save_calendar':({'body':dict},{'record_id':str,'revision':int}),
 'calendar.delete_calendar':({'record_id':str,'revision':int},{}),
 'calendar.delete_occurrence':({'record_id':str,'revision':int,'occurrence_id':str},{}),
 'tasks.schedule':({'record_id':str,'revision':int,'event_body':dict},{}),
 'tasks.complete':({'record_id':str,'revision':int},{}),
 'tasks.reopen':({'record_id':str,'revision':int},{}),
 'reminders.history':({},{'limit':int,'offset':int}),
 'reminders.snooze':({'delivery_id':str},{'minutes':int}),
 'reminders.dismiss':({'delivery_id':str},{}),
 'personal.import_commit':({'preview_id':str,'choices':dict},{'allow_partial':bool}),
 'personal.import_cancel':({'preview_id':str},{}),
 'personal.today':({},{}),
 'personal.review':({'chat_id':str,'proposal_id':str,'revision':int,'decision':str},{}),
}
DOMAINS={'contacts':'contact','calendar':'event','tasks':'task','reminders':'reminder'}
for prefix in DOMAINS:
 SPEC[prefix+'.search']=({},dict(query=str,project_id=str,limit=int,offset=int))
 SPEC[prefix+'.get']=({'record_id':str},{})
 SPEC[prefix+'.create']=({'body':dict},{})
 SPEC[prefix+'.update']=({'record_id':str,'revision':int,'body':dict},{})
 SPEC[prefix+'.delete']=({'record_id':str,'revision':int},{})
SPEC['tasks.search'][1]['view']=str
MAIN_ONLY={
 'personal.import_preview':({'kind':str,'format':str,'path':str},{'calendar_id':str}),
 'personal.export':({'kind':str,'format':str,'path':str},{}),
 'profile.avatar':({'path':str},{}),
}


def validate(method,args):
 required,optional=(SPEC|MAIN_ONLY)[method]
 if not isinstance(args,dict) or not set(required)<=set(args) or set(args)-(required.keys()|optional.keys()):raise ValueError('Invalid Personal Core arguments')
 for key,value in args.items():
  if type(value) is not (required|optional)[key]:raise ValueError('Invalid Personal Core argument type')
 if len(json.dumps(args,allow_nan=False).encode())>300000:raise ValueError('Personal request exceeds bounds')
 def bounded(value,depth=0):
  if depth>8:raise ValueError('Personal request nesting exceeds bounds')
  if isinstance(value,str) and ('\x00' in value or len(value)>64000):raise ValueError('Personal text exceeds bounds')
  if isinstance(value,(list,dict)):
   if len(value)>2000:raise ValueError('Personal collection exceeds bounds')
   for x in (value.values() if isinstance(value,dict) else value):bounded(x,depth+1)
 bounded(args)
 if 'revision' in args and (type(args['revision']) is not int or args['revision']<1):raise ValueError('Invalid personal record revision')
 return args
