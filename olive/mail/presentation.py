"""Human-readable trusted Mail previews, with no secret entry values."""
def approval(method,args,services=None):
    if method=='mail.send':
        p=args['preview']
        attachments='\n'.join(f"{a['name']} ({a['size']} bytes; {a['hash'][:12]})" for a in p['attachments']) or 'None'
        return {'action':'Submit the reviewed email','targets':[f"{p['server']['host']}:{p['server']['port']} ({p['server']['tls']})",*p['to'],*p['cc'],*p['bcc']],
                'content':f"From: {p['from']}\nTo: {', '.join(p['to'])}\nCC: {', '.join(p['cc'])}\nBCC: {', '.join(p['bcc'])}\nSubject: {p['subject']}\n\n{p['body']}\n\nAttachments:\n{attachments}\nSize: {p['size']} bytes",
                'scope':f"One submission through {p['connection_name']}, configuration revision {p['connection_revision']}, draft revision {p['draft_revision']}.",
                'consequence':p['consequence']}
    content='\n'.join(f'{k}: {v}' for k,v in args.items() if k not in {'secret','ca_pem'})
    targets=[]
    if method in {'mail.create_event','mail.create_task'}:
        content='\n'.join(k.replace('_',' ').capitalize()+': '+str(v) for k,v in args['body'].items() if v not in ('',[],{}))
        content+=f"\nProposal: {args['proposal_id']} · revision {args['revision']}\nCreates a local record only; no invitation is sent."
    mail=getattr(services,'mail',None)
    if mail:
      try:
        if method=='mail.import_commit':
            raw,record=mail.local.previews[args['preview_id']]
            content=f"One local message\nFrom: {record['from']}\nSubject: {record['subject']}\nSize: {len(raw)} bytes\nAttachments: "+', '.join(a['name'] for a in record['attachments'])+f"\nSource SHA-256: {args['expected_hash']}\nRepeated unchanged imports retain their existing identity."
        if method in {'mail.remote_action','mail.add_knowledge','mail.discard','mail.fetch_body'}:
            record=mail.local.get(args['record_id']);targets=[record['subject'] or '(No subject)',record['from']]
            content=f"Message: {record['id']} · revision {record['revision']}\n"+content
            if args.get('attachment_id'):
                attachment=next(a for a in record['attachments'] if a['id']==args['attachment_id'])
                content+=f"\nAttachment: {attachment['name']} · {attachment['size']} bytes\nSHA-256: {attachment['hash']}"
        if method in {'mail.sync','mail.server_search','mail.folder_action','mail.cache_remove'}:
            c=mail.connections.get(args['connection_id']);endpoint=c.get('imap')
            targets=[c['name']]+([f"{endpoint['host']}:{endpoint['port']} ({endpoint['tls']})"] if endpoint else [])
            content+=f"\nConnection revision: {c['revision']}"
            if method=='mail.cache_remove':content+='\nRemoves downloaded bodies and attachments. Stable message references, native drafts and imported messages remain.'
        if method=='mail.sent_copy':
            with mail.store.transaction() as db:r=mail.store.get(db,'submission',args['submission_id'])
            c=mail.connections.get(r['connection_id']);targets=[c['name'],c['sent_folder']]
            content+=f"\nSubject: {r['preview']['subject']}\nAppend a copy of the already submitted bytes. SMTP submission is not repeated."
      except (LookupError,ValueError,KeyError,StopIteration):
        content+='\nThe selected record is no longer available; execution will revalidate it.'
    return {'action':method.replace('mail.','').replace('_',' ').capitalize(),'targets':targets,
            'content':content,
            'scope':'One reviewed native Mail operation in the active profile.',
            'consequence':'Changes and remote access are limited to the displayed operation. Imported content grants no permissions.'}
