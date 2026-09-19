"""UI-neutral Personal Core services. Policy is enforced by the shared tool layer."""
from datetime import datetime, timezone
from .store import PersonalStore, RevisionConflict, timestamp
from . import validation as v
from .calendar import event, occurrences, free_time, bounds
UTC=timezone.utc


class PersonalService:
    def __init__(self,path,projects=lambda:{},agent_tasks=lambda:{},clock=lambda:datetime.now(UTC)):
        self.store=PersonalStore(path);self.projects=projects;self.agent_tasks=agent_tasks;self.clock=clock
        with self.store.transaction() as db:
            calendars=self.store.list(db,'calendar')
            if not calendars:
                calendars=[self.store.save(db,'calendar',v.calendar({'title':'Personal'}),uid='dmdo-default-calendar')]
            if not self.store.list(db,'profile'):
                self._save(db,'profile',{'default_calendar':calendars[0]['id']},uid='dmdo-local-profile')

    def profile(self):
        with self.store.transaction() as db:
            value=self.store.list(db,'profile',limit=1)[0]
        try:v.profile(self.store.body(value));return value
        except (ValueError,TypeError,KeyError):
            # Recover only invalid optional fields in the presentation. Keep valid
            # preferences and the calendar relationship, without writing the source.
            recovered=v.profile({})
            for key in recovered:
                try:recovered[key]=v.profile({key:value[key]})[key]
                except (ValueError,TypeError,KeyError):pass
            return {**value,**recovered,'recovery_warning':'Some optional profile settings are invalid. Review and save to repair them.'}

    def get(self,kind,record_id):
        with self.store.transaction() as db:return self.store.get(db,kind,record_id)

    def search(self,kind,query='',project_id='',limit=50,offset=0,view=''):
        if kind not in {'contact','calendar','event','task','reminder'}:raise ValueError('Unknown searchable personal domain')
        v.text(query,200);v.text(project_id,100);v.integer(limit,1,200);v.integer(offset,0,100000)
        if view not in {'','All','Today','Upcoming','Completed','Project'} or view and kind!='task':raise ValueError('Invalid personal view')
        local_zone=v.zone(self.profile()['timezone']) if view else UTC
        today=self.clock().astimezone(local_zone).date().isoformat() if view else ''
        with self.store.transaction() as db:
            rows=db.execute('SELECT * FROM records WHERE kind=? AND deleted=0 AND instr(search_text,?)>0 ORDER BY updated_at DESC,id',
                            (kind,query.casefold()))
            items=[];matched=0
            for row in rows:
                record=self.store.unpack(row)
                if project_id and project_id not in record.get('project_ids',[record.get('project_id','')]):continue
                if view=='Completed' and record['status']!='completed':continue
                if view in {'Today','Upcoming','Project'} and record['status']!='open':continue
                due=record.get('due','')
                due_day=(datetime.fromisoformat(due).astimezone(local_zone).date().isoformat()
                         if due and record.get('due_kind')=='time' else due)
                if view=='Today' and (not due_day or due_day>today):continue
                if view=='Upcoming' and (not due_day or due_day<=today):continue
                if view=='Project' and not record['project_id']:continue
                if matched>=offset:items.append(record)
                matched+=1
                if len(items)>limit:break
            return {'items':items[:limit],'has_more':len(items)>limit,'offset':offset}

    def validate(self,kind,body):
        validators={'profile':v.profile,'contact':v.contact,'calendar':v.calendar,'event':event,'task':v.task}
        if kind=='reminder':
            from .reminders import validate_reminder
            return validate_reminder(body)
        if kind not in validators:raise ValueError('Unknown writable personal domain')
        return validators[kind](body)

    def _relationships(self,db,kind,body):
        ids=body.get('project_ids',[body.get('project_id','')])
        if any(p and p not in self.projects() for p in ids):raise ValueError('Linked project no longer exists')
        if kind=='task' and body.get('agent_task_id') and body['agent_task_id'] not in self.agent_tasks():raise ValueError('Linked Agent attempt no longer exists')
        links=[]
        if kind=='event':links.append(('calendar',body['calendar_id'],'calendar'))
        if kind=='profile' and body['default_calendar']:links.append(('calendar',body['default_calendar'],'default_calendar'))
        if kind in {'event','task'}:links.extend(('contact',x,'contact') for x in body.get('contact_ids',[]))
        if kind=='task' and body.get('event_id'):links.append(('event',body['event_id'],'calendar_block'))
        if kind=='reminder':links.append((body['target_kind'],body['target_id'],'reminder_target'))
        for target_kind,target_id,_ in links:self.store.get(db,target_kind,target_id)
        return links

    def _save(self,db,kind,body,record_id=None,revision=None,uid=None,source=None):
        body=self.validate(kind,body);links=self._relationships(db,kind,body)
        if kind=='task':
            previous=self.store.get(db,kind,record_id) if record_id else None
            body['completed_at']=(previous.get('completed_at') if previous and previous['status']=='completed' else timestamp()) if body['status']=='completed' else ''
        result=self.store.save(db,kind,body,record_id=record_id,revision=revision,uid=uid,source=source)
        db.execute('DELETE FROM links WHERE source=?',(result['id'],))
        db.executemany('INSERT INTO links(source,target,relation) VALUES(?,?,?)',[(result['id'],target,relation) for _,target,relation in links])
        if kind=='task' and body['status']=='completed':
            db.execute("UPDATE deliveries SET state='cancelled',updated_at=? WHERE reminder_id IN (SELECT source FROM links WHERE target=? AND relation='reminder_target') AND state IN ('pending','snoozed')",(timestamp(),result['id']))
        return result

    def save(self,kind,body,record_id=None,revision=None):
        with self.store.transaction() as db:return self._save(db,kind,body,record_id,revision)

    def delete_occurrence(self,record_id,revision,occurrence_id):
        with self.store.transaction() as db:
            record=self.store.get(db,'event',record_id);body=self.store.body(record)
            if not body['recurrence']:raise ValueError('Choose series deletion for a non-recurring event')
            body['exceptions']={**body['exceptions'],occurrence_id:{**body['exceptions'].get(occurrence_id,{}),'cancelled':True}}
            return self._save(db,'event',body,record_id,revision)

    def schedule_task(self,record_id,revision,event_body):
        with self.store.transaction() as db:
            task=self.store.get(db,'task',record_id)
            if task['revision']!=revision:raise RevisionConflict('Task changed; review scheduling again')
            if task['status']=='completed':raise ValueError('Reopen the task before scheduling a new work block')
            if task['event_id']:raise ValueError('Unlink the existing calendar block before scheduling another')
            block=self._save(db,'event',{**event_body,'project_id':task['project_id'],'contact_ids':task['contact_ids']})
            linked=self._save(db,'task',{**self.store.body(task),'event_id':block['id']},record_id,revision)
            return {'task':linked,'event':block,'status':'saved'}

    def delete(self,kind,record_id,revision):
        if kind=='profile':raise ValueError('The local profile cannot be deleted')
        with self.store.transaction() as db:
            linked=list(db.execute('SELECT source,relation FROM links WHERE target=?',(record_id,)))
            if kind=='calendar' and linked:raise ValueError('Move linked events and change the default calendar before deleting this calendar')
            for row in linked:
                source=db.execute('SELECT * FROM records WHERE id=? AND deleted=0',(row['source'],)).fetchone()
                if not source:continue
                record=self.store.unpack(source);body=self.store.body(record)
                if row['relation']=='reminder_target':
                    db.execute("UPDATE deliveries SET state='cancelled',updated_at=? WHERE reminder_id=? AND state IN ('pending','snoozed')",(timestamp(),record['id']))
                    self.store.delete(db,'reminder',record['id'],record['revision'])
                else:
                    if row['relation']=='contact':body['contact_ids']=[x for x in body['contact_ids'] if x!=record_id]
                    elif row['relation']=='calendar_block':body['event_id']=''
                    self._save(db,record['kind'],body,record['id'],record['revision'])
            if kind=='reminder':db.execute("UPDATE deliveries SET state='cancelled',updated_at=? WHERE reminder_id=? AND state IN ('pending','snoozed')",(timestamp(),record_id))
            return self.store.delete(db,kind,record_id,revision)

    def resolve_contact(self,query,project_id=''):
        candidates=self.search('contact',query,project_id,limit=20)['items']
        exact=[]
        for c in candidates:
            names=[c['display_name'],*c['aliases'],*[x['value'] for x in c['emails']]]
            if query.casefold() in [x.casefold() for x in names]:exact.append(c)
        found=exact or candidates
        # Only a bounded useful identity summary, never notes or the address book.
        return {'status':'resolved' if len(found)==1 else 'ambiguous' if found else 'not_found',
                'candidates':[{k:c[k] for k in ('id','revision','display_name','organization','project_ids')} for c in found[:10]]}

    def duplicates(self,record_id):
        original=self.get('contact',record_id);found=[]
        candidates={}
        for query in [original['display_name'],*[x['value'] for x in original['emails']]]:
            for c in self.search('contact',query,limit=200)['items']:candidates[c['id']]=c
        for c in candidates.values():
            if c['id']==record_id:continue
            emails={x['value'].casefold() for x in original['emails']}&{x['value'].casefold() for x in c['emails']}
            if emails or original['display_name'].casefold()==c['display_name'].casefold():
                found.append({'id':c['id'],'revision':c['revision'],'display_name':c['display_name'],'reason':'matching email' if emails else 'matching name'})
        return found[:20]

    def merge_preview(self,keep_id,remove_id,choices=None):
        if keep_id==remove_id:raise ValueError('Choose two different contacts')
        keep=self.get('contact',keep_id);remove=self.get('contact',remove_id);body=self.store.body(keep);conflicts=[]
        choices=choices or {};v.fields(choices,{'display_name','organization','notes'})
        for key in ('display_name','organization','notes'):
            if keep[key] and remove[key] and keep[key]!=remove[key]:conflicts.append({'field':key,'keep':keep[key],'remove':remove[key]})
            body[key]=choices.get(key,keep[key] or remove[key])
        for key in ('emails','phones','external_ids','aliases','project_ids','unsupported'):
            body[key]=keep[key]+[x for x in remove[key] if x not in keep[key]]
        return {'keep_id':keep_id,'remove_id':remove_id,'keep_revision':keep['revision'],'remove_revision':remove['revision'],
                'conflicts':conflicts,'proposed':self.validate('contact',body),'scope':'Merge these two contacts and update their local relationships. No communication is sent.'}

    def merge(self,preview):
        with self.store.transaction() as db:
            keep=self.store.get(db,'contact',preview['keep_id']);remove=self.store.get(db,'contact',preview['remove_id'])
            if (keep['revision'],remove['revision'])!=(preview['keep_revision'],preview['remove_revision']):raise RevisionConflict('Contacts changed; review a new merge')
            proposed=self.store.body(keep)
            conflicts=any(keep[k] and remove[k] and keep[k]!=remove[k] for k in ('display_name','organization','notes'))
            if conflicts and not preview.get('conflicts_reviewed'):raise ValueError('Review conflicting fields before merging')
            for key in ('display_name','organization','notes'):
                chosen=preview['proposed'].get(key)
                if chosen not in (keep[key],remove[key]):raise ValueError('Merge must explicitly select an existing conflicting value')
                proposed[key]=chosen
            for key in ('emails','phones','external_ids','aliases','project_ids','unsupported'):
                proposed[key]=keep[key]+[x for x in remove[key] if x not in keep[key]]
                if proposed[key]!=preview['proposed'].get(key):raise ValueError('Merge preview no longer preserves all identifiers and relationships')
            merged=self._save(db,'contact',proposed,keep['id'],keep['revision'])
            for row in list(db.execute('SELECT DISTINCT source FROM links WHERE target=?',(remove['id'],))):
                linked=self.store.unpack(db.execute('SELECT * FROM records WHERE id=?',(row['source'],)).fetchone());body=self.store.body(linked)
                body['contact_ids']=list(dict.fromkeys(keep['id'] if x==remove['id'] else x for x in body['contact_ids']))
                self._save(db,linked['kind'],body,linked['id'],linked['revision'])
            self.store.delete(db,'contact',remove['id'],remove['revision'])
            return merged

    def calendar_range(self,after,before,calendar_ids=None,timezone=None):
        if timezone:
            from datetime import time
            a=datetime.combine(v.day(after),time.min,v.zone(timezone));b=datetime.combine(v.day(before),time.min,v.zone(timezone))
        else:a=datetime.fromisoformat(after);b=datetime.fromisoformat(before)
        ids=calendar_ids if calendar_ids is not None else [c['id'] for c in self.search('calendar',limit=200)['items'] if c['visible']]
        v.strings(ids,200);result=[]
        with self.store.transaction() as db:
            rows=db.execute("SELECT * FROM records WHERE kind='event' AND deleted=0")
            for n,row in enumerate(rows):
                if n>=10000:raise ValueError('Calendar query safety limit reached')
                record=self.store.unpack(row)
                if record['calendar_id'] in ids:result.extend(occurrences(record,a,b,limit=1000))
                if len(result)>2000:raise ValueError('Too many events; narrow the calendar range')
        return sorted(result,key=lambda x:bounds(x)[0].astimezone(UTC))

    def availability(self,after,before,duration,calendar_ids=None):
        return free_time(self.calendar_range(after,before,calendar_ids),datetime.fromisoformat(after),datetime.fromisoformat(before),duration,self.profile())
