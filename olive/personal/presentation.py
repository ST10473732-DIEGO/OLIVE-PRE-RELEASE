"""Bounded readable native approval content from actual trusted arguments."""
def approval(method,args,controller):
    body=args.get('body') or args.get('event_body') or args.get('preview',{}).get('proposed',{})
    targets=[args['record_id']] if args.get('record_id') else []
    if method=='contacts.merge':
        preview=args.get('preview',{})
        for key,label in [('keep_id','Keep'),('remove_id','Merge and remove')]:
            record=controller.records.get('contact',preview[key])
            targets.append(label+': '+record['display_name']+' ['+record['id']+']; revision '+str(record['revision']))
    if not targets and body.get('calendar_id'):
        calendar=controller.records.get('calendar',body['calendar_id'])
        targets=['Local calendar: '+calendar['title']+' ['+calendar['id']+']']
    elif not targets and method.endswith('.create'):
        targets=[{'contacts':'Local Contacts','tasks':'Local Personal Tasks','reminders':'Local reminder schedule'}.get(method.split('.')[0],'Active local profile')]
    content=[]
    if method=='personal.import_commit':
        preview=controller.interchange.previews.get(args.get('preview_id'))
        if not preview:return {'action':'Expired import','content':'Cancel and choose the source again.','scope':'No valid staged source.','consequence':'This request cannot import records.'}
        selected=[r for r in preview['rows'] if args.get('choices',{}).get(str(r['index']),r['action'])!='skip']
        content=['Source fingerprint: '+preview['source_hash'],f"{len(selected)} selected {preview['kind']} records; {len(preview['errors'])} validation errors."]
        content += [r['body'].get('display_name',r['body'].get('title',''))+' — '+args.get('choices',{}).get(str(r['index']),r['action']) for r in selected[:50]]
        if len(selected)>50:content.append('Remaining selected records are in the import preview. Cancel to change the selection.')
        targets=[preview['id']]
    elif not body and args.get('record_id'):
        kind={'contacts':'contact','calendar':'event','tasks':'task','reminders':'reminder','profile':'profile'}.get(method.split('.')[0])
        if method=='calendar.delete_calendar':kind='calendar'
        try:body=controller.records.get(kind,args['record_id'])
        except LookupError:content=['The target no longer exists. Cancel this request.']
    for key in ('display_name','title','organization','emails','phones','aliases','external_ids','project_ids','start','end','timezone','all_day','recurrence','due','priority','target_kind','target_id','at','offset_minutes','project_id','contact_ids','event_id','agent_task_id','description','notes'):
        if key not in body:continue
        value=body[key]
        if isinstance(value,list):value=', '.join((x.get('label','')+': '+x.get('value','')) if isinstance(x,dict) else str(x) for x in value)
        content.append(key.replace('_',' ').capitalize()+': '+str(value)[:8000])
    for field,kind,label in [('event_id','event','Linked event'),('target_id',body.get('target_kind'),'Reminder target')]:
        if body.get(field) and kind in {'event','task'}:
            record=controller.records.get(kind,body[field]);content.append(label+': '+record['title'])
    for identity in body.get('contact_ids',[])[:30]:
        record=controller.records.get('contact',identity);content.append('Linked contact: '+record['display_name']+' ['+identity+']')
    if body.get('project_id'):
        project=controller.s.project_repo.load_all().get(body['project_id'])
        if project:content.append('Linked project: '+project.title)
    if args.get('occurrence_id'):content.append('Original occurrence: '+args['occurrence_id'])
    if args.get('revision'):content.append('Record revision: '+str(args['revision']))
    return {'action':method.replace('.',' ').replace('_',' ').capitalize(),'targets':targets,
            'content':'\n'.join(content) or 'The exact selected native operation.',
            'scope':'One reviewed operation in the active local profile. Linked records may be updated to retain valid relationships.',
            'consequence':'Changes local records only; no invitation or communication is sent. Deny or cancel prevents this operation. Changed records require a fresh review.'}
