"""Strict shared Mail methods. Credential entry is never a model tool."""
import json

SPEC={
 'mail.folders':({},{'connection_id':str}),
 'mail.recipients':({'query':str},{'connection_id':str}),
 'mail.search':({},{'query':str,'folder':str,'connection_id':str,'limit':int,'offset':int,'filters':dict}),
 'mail.get':({'record_id':str},{}),
 'mail.thread':({'record_id':str},{}),
 'mail.create_folder':({'name':str},{}),
 'mail.discard':({'record_id':str,'revision':int},{}),
 'mail.inline_images':({'record_id':str},{}),
 'mail.save_draft':({'body':dict},{'record_id':str,'revision':int}),
 'mail.update':({'record_id':str,'revision':int,'changes':dict},{}),
 'mail.reply':({'record_id':str,'mode':str},{'connection_id':str,'sender':str}),
 'mail.import_commit':({'preview_id':str,'expected_hash':str},{}),
 'mail.import_cancel':({'preview_id':str},{}),
 'mail.prepare':({'record_id':str,'revision':int},{}),
 'mail.send':({'submission_id':str,'expected_fingerprint':str,'preview':dict},{}),
 'mail.cancel':({'submission_id':str},{}),
 'mail.outbox':({},{}),
 'mail.sent_copy':({'submission_id':str},{}),
 'mail.retry_rejected':({'submission_id':str},{}),
 'mail.connections':({},{}),
 'mail.sync':({'connection_id':str},{'folder':str,'limit':int}),
 'mail.cancel_sync':({'connection_id':str},{}),
 'mail.fetch_body':({'record_id':str},{}),
 'mail.remote_action':({'record_id':str,'revision':int,'action':str,'arguments':dict},{}),
 'mail.server_search':({'connection_id':str,'folder':str,'query':str},{}),
 'mail.folder_action':({'connection_id':str,'action':str,'name':str},{'new_name':str}),
 'mail.cache_remove':({'connection_id':str,'revision':int},{}),
 'mail.proposal_prepare':({'record_id':str,'revision':int,'kind':str,'body':dict},{}),
 'mail.create_event':({'proposal_id':str,'revision':int,'body':dict},{}),
 'mail.create_task':({'proposal_id':str,'revision':int,'body':dict},{}),
 'mail.proposal_cancel':({'proposal_id':str,'revision':int},{}),
 'mail.from_event':({'event_id':str,'contact_ids':list},{'connection_id':str}),
 'mail.calendar_draft':({'event_id':str,'recipients':list},{'connection_id':str}),
 'mail.add_knowledge':({'record_id':str,'revision':int},{'attachment_id':str}),
}
MAIN_ONLY={
 'mail.google_status':({},{}),
 'mail.google_import':({'path':str},{}),
 'mail.google_begin':({},{'connection_id':str}),
 'mail.google_cancel':({},{}),
 'mail.connection_save':({'body':dict},{'record_id':str,'revision':int}),
 'mail.connection_state':({'record_id':str,'revision':int,'enabled':bool},{'remove_credentials':bool}),
 'mail.connection_test':({'record_id':str},{}),
 'mail.credential_store':({'record_id':str,'revision':int,'secret':str},{}),
 'mail.import_preview':({'path':str},{}),
 'mail.export':({'record_id':str,'path':str},{}),
 'mail.attach':({'record_id':str,'revision':int,'path':str},{}),
 'mail.save_attachment':({'record_id':str,'attachment_id':str,'path':str},{}),
}


def validate(method,args):
    if method not in SPEC|MAIN_ONLY:raise ValueError('Unknown Mail method')
    required,optional=(SPEC|MAIN_ONLY)[method]
    if not isinstance(args,dict) or not set(required)<=set(args) or set(args)-(required.keys()|optional.keys()):raise ValueError('Invalid Mail arguments')
    for key,value in args.items():
        if type(value) is not (required|optional)[key]:raise ValueError('Invalid Mail argument type')
    if len(json.dumps(args,allow_nan=False).encode())>500000:raise ValueError('Mail request exceeds its bound')
    def bounded(value,depth=0):
        if depth>8:raise ValueError('Mail request nesting exceeds its bound')
        if isinstance(value,str) and ('\0' in value or len(value)>160000):raise ValueError('Mail text exceeds its bound')
        if isinstance(value,(list,dict)):
            if len(value)>500:raise ValueError('Mail collection exceeds its bound')
            for item in (value.values() if isinstance(value,dict) else value):bounded(item,depth+1)
    bounded(args)
    if 'revision' in args and args['revision']<1:raise ValueError('Invalid Mail revision')
    if method=='mail.credential_store' and len(args['secret'].encode())>2500:raise ValueError('Credential exceeds supported size')
    return args


def permissions(method):
    if method.startswith('mail.google_'):return ('mail.connections','mail.credentials')+(('filesystem.read',) if method=='mail.google_import' else ())
    if method in {'mail.create_folder','mail.discard'}:return ('mail.modify',)
    if method=='mail.create_event':return ('mail.read','calendar.write')
    if method=='mail.create_task':return ('mail.read','tasks.write')
    if method=='mail.from_event':return ('mail.draft','calendar.read','contacts.read')
    if method=='mail.calendar_draft':return ('mail.draft','calendar.read')
    if method=='mail.add_knowledge':return ('mail.read','knowledge.write')
    if method in {'mail.send'}:return ('communication.send','mail.send')
    if method=='mail.sent_copy':return ('mail.read','mail.remote_modify','mail.connect')
    if method=='mail.retry_rejected':return ('mail.read','mail.draft')
    if method in {'mail.connection_save','mail.connection_state','mail.connection_test'}:return ('mail.connections',)
    if method=='mail.credential_store':return ('mail.connections','mail.credentials')
    if method in {'mail.sync','mail.fetch_body','mail.server_search'}:return ('mail.read','mail.connect')
    if method in {'mail.remote_action','mail.folder_action'}:return ('mail.read','mail.remote_modify','mail.connect')
    if method=='mail.cache_remove':return ('mail.connections','mail.modify')
    if method in {'mail.attach','mail.import_preview'}:return ('mail.draft','filesystem.read')
    if method in {'mail.export','mail.save_attachment'}:return ('mail.read','mail.export','filesystem.write')
    if method=='mail.import_commit':return ('mail.import',)
    if method in {'mail.save_draft','mail.reply','mail.prepare'}:return ('mail.read','mail.draft')
    if method=='mail.update':return ('mail.modify',)
    return ('mail.read',)
