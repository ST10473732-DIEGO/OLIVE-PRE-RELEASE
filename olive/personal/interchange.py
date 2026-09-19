"""Bounded passive CSV/vCard/ICS parsing and explicit staged commits."""
import csv
import hashlib
import io
import json
import uuid
from datetime import date,datetime,timedelta,timezone
import vobject
from icalendar import Calendar,Event
from . import validation as v

MAX_BYTES=2_000_000
MAX_RECORDS=2000


def safe_csv(value):
    value=str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value


class Interchange:
    def __init__(self,personal):self.personal=personal;self.previews={}

    def parse(self,kind,format,text,calendar_id=''):
        if not isinstance(text,str) or len(text.encode())>MAX_BYTES or '\x00' in text:raise ValueError('Import is malformed or exceeds 2 MB')
        if format not in ({'csv','vcf'} if kind=='contact' else {'ics'} if kind=='event' else set()):raise ValueError('Unsupported import format')
        if format=='csv':raw=self.csv_records(text)
        elif format=='vcf':raw=self.vcards(text)
        else:raw=self.ical(text,calendar_id or self.personal.profile()['default_calendar'])
        rows=[];errors=[]
        try:
            for index,(uid,body,warnings) in enumerate(raw):
                if index>=MAX_RECORDS:raise ValueError('Import exceeds 2000 records')
                try:
                    body=self.personal.validate(kind,body)
                    uid=uid or 'content-'+hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
                    v.text(uid,500,True)
                    with self.personal.store.transaction() as db:
                        self.personal._relationships(db,kind,body)
                        old=db.execute('SELECT * FROM records WHERE kind=? AND uid=?',(kind,uid)).fetchone()
                        previous=self.personal.store.unpack(old) if old and not old['deleted'] else None
                    action='skip' if old and old['deleted'] or previous and self.personal.store.body(previous)==body else 'update' if previous else 'create'
                    rows.append({'index':index,'uid':uid,'body':body,'warnings':warnings,'action':action,
                                 'record_id':previous['id'] if previous else None,'revision':previous['revision'] if previous else None,
                                 'deleted_source':bool(old and old['deleted'])})
                except (ValueError,TypeError,KeyError) as error:errors.append({'row':index+1,'message':str(error)[:300]})
        except (ValueError,TypeError,KeyError,AttributeError) as error:
            errors.append({'row':len(rows)+len(errors)+1,'message':str(error)[:300]})
        if len(self.previews)>=20:raise ValueError('Too many staged imports; cancel an earlier preview')
        token=uuid.uuid4().hex
        preview={'id':token,'kind':kind,'format':format,'source_hash':hashlib.sha256(text.encode()).hexdigest(),'rows':rows,'errors':errors}
        if len(json.dumps(preview,ensure_ascii=False).encode())>500000:raise ValueError('Preview exceeds 500 KB; split the source into smaller reviewed batches')
        self.previews[token]=preview
        return preview

    @staticmethod
    def csv_records(text):
        reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
        allowed={'uid','display_name','name','emails','email','phones','phone','organization','aliases','notes','external_ids','project_ids','dmdo_csv_escape'}
        if not reader.fieldnames or len(reader.fieldnames)>30:raise ValueError('CSV needs a header row')
        warnings=['Ignored unsupported CSV column (values not retained): '+k for k in reader.fieldnames if k not in allowed]
        for row in reader:
            if None in row:raise ValueError('CSV row has more fields than its header')
            if row.get('dmdo_csv_escape')=='1':
                row={k:(value[1:] if value and value.startswith("'") and safe_csv(value[1:])==value else value) for k,value in row.items()}
            body={k:row.get(k,'') for k in ('organization','notes')};body['display_name']=row.get('display_name') or row.get('name','')
            for key in ('emails','phones','aliases','external_ids','project_ids'):
                body[key]=json.loads(row[key]) if row.get(key) else []
            for key,singular in [('emails','email'),('phones','phone')]:
                if row.get(singular):body[key].append({'label':'other','value':row[singular]})
            body['unsupported']=warnings
            yield row.get('uid',''),body,warnings

    @staticmethod
    def vcards(text):
        for card in vobject.readComponents(text):
            if card.name!='VCARD':raise ValueError('Expected a vCard component')
            known={'version','uid','fn','n','email','tel','org','nickname','note','x-dmdo-project','x-dmdo-external','x-dmdo-aliases'}
            warnings=['Retained a bounded excerpt of unsupported vCard field (not re-exported): '+key for key in card.contents if key not in known]
            unsupported=[child.serialize()[:1000] for key,children in card.contents.items() if key not in known for child in children]
            body={'display_name':str(getattr(card,'fn',None).value) if hasattr(card,'fn') else '',
                  'organization':' / '.join(card.org.value) if hasattr(card,'org') else '',
                  'notes':str(card.note.value) if hasattr(card,'note') else '',
                  'aliases':([str(card.nickname.value)] if hasattr(card,'nickname') else []),'unsupported':unsupported}
            if card.contents.get('x-dmdo-aliases'):body['aliases']=json.loads(card.contents['x-dmdo-aliases'][0].value)
            for key,prop in [('emails','email'),('phones','tel')]:
                body[key]=[{'label':','.join(c.params.get('TYPE',['other'])),'value':str(c.value)} for c in card.contents.get(prop,[])]
            body['project_ids']=[str(c.value) for c in card.contents.get('x-dmdo-project',[])]
            body['external_ids']=[json.loads(c.value) for c in card.contents.get('x-dmdo-external',[])]
            yield str(card.uid.value) if hasattr(card,'uid') else '',body,warnings

    @staticmethod
    def ical(text,calendar_id):
        parsed=Calendar.from_ical(text);masters={};exceptions=[]
        for item in parsed.walk('VEVENT'):
            uid=str(item.get('UID',''))
            if item.get('RECURRENCE-ID'):exceptions.append(item);continue
            identity=uid or 'content-'+hashlib.sha256(item.to_ical()).hexdigest()
            if identity in masters:raise ValueError('Duplicate event UID in source; resolve before importing')
            masters[identity]=item
        for uid,item in masters.items():
            start=item.decoded('DTSTART');end=item.decoded('DTEND',None)
            all_day=isinstance(start,date) and not isinstance(start,datetime)
            if end is None:end=start+item.decoded('DURATION',timedelta(days=1) if all_day else timedelta(hours=1))
            tz=str(item['DTSTART'].params.get('TZID','')) or (str(getattr(start.tzinfo,'key','')) if not all_day else '') or 'Africa/Johannesburg'
            if not all_day and start.tzinfo is not None and start.utcoffset()==timedelta(0) and not item['DTSTART'].params.get('TZID'):tz='UTC'
            rule=item.get('RRULE');rule=rule.to_ical().decode() if rule else ''
            known={'UID','DTSTART','DTEND','DURATION','SUMMARY','DESCRIPTION','LOCATION','STATUS','TRANSP','RRULE','EXDATE','DTSTAMP','CREATED','LAST-MODIFIED','SEQUENCE','X-DMDO-PROJECT','X-DMDO-CONTACT'}
            warnings=['Unsupported ICS field retained in original material: '+str(key) for key in item.keys() if key not in known]
            body=dict(calendar_id=calendar_id,title=str(item.get('SUMMARY','Untitled event')),description=str(item.get('DESCRIPTION','')),
                      location=str(item.get('LOCATION','')),start=start.isoformat(),end=end.isoformat(),timezone=tz,all_day=all_day,
                      recurrence=rule,status=str(item.get('STATUS','CONFIRMED')).lower(),transparent=str(item.get('TRANSP','OPAQUE'))=='TRANSPARENT',
                      project_id=str(item.get('X-DMDO-PROJECT','')),contact_ids=json.loads(str(item.get('X-DMDO-CONTACT','[]'))),exceptions={},unsupported=warnings,original_ics=item.to_ical().decode())
            exdates=item.get('EXDATE',[]);exdates=exdates if isinstance(exdates,list) else [exdates]
            for entry in exdates:
                for d in entry.dts:body['exceptions'][d.dt.isoformat()]={'cancelled':True}
            for changed in exceptions:
                if str(changed.get('UID',''))!=uid:continue
                key=changed.decoded('RECURRENCE-ID').isoformat()
                patch={'cancelled':str(changed.get('STATUS',''))=='CANCELLED'}
                for name,keyname in [('SUMMARY','title'),('LOCATION','location'),('DESCRIPTION','description')]:
                    if name in changed:patch[keyname]=str(changed[name])
                if 'DTSTART' in changed and 'DTEND' in changed:patch.update(start=changed.decoded('DTSTART').isoformat(),end=changed.decoded('DTEND').isoformat())
                body['exceptions'][key]=patch
            yield uid,body,warnings

    def commit(self,token,choices,allow_partial=False):
        preview=self.previews.get(token)
        if not preview:raise ValueError('Import preview expired or was already committed')
        if preview['errors'] and not allow_partial:raise ValueError('Import has errors; explicitly select valid rows or cancel')
        if not isinstance(choices,dict) or set(choices)-{str(r['index']) for r in preview['rows']}:raise ValueError('Invalid import selection')
        results=[]
        with self.personal.store.transaction() as db:
            for row in preview['rows']:
                action=choices.get(str(row['index']),row['action'])
                if action not in {'skip','create','update'}:raise ValueError('Invalid import choice')
                if action=='skip':continue
                if row['deleted_source']:raise ValueError('Previously deleted source cannot be silently reactivated')
                if (action=='update')!=(row['record_id'] is not None):raise ValueError('Review the correct duplicate/update choice')
                results.append(self.personal._save(db,preview['kind'],row['body'],row['record_id'],row['revision'],row['uid'],source={'origin':'local_import','format':preview['format'],'source_hash':preview['source_hash'],'source_uid':row['uid']}))
        self.previews.pop(token)
        return {'status':'partial' if preview['errors'] else 'saved','saved_count':len(results),'skipped_count':len(preview['rows'])-len(results),'records':[{'id':r['id'],'revision':r['revision']} for r in results],'errors':preview['errors']}

    def export(self,kind,format):
        with self.personal.store.transaction() as db:
            rows=list(db.execute('SELECT * FROM records WHERE kind=? AND deleted=0 LIMIT 2001',(kind,)))
            if len(rows)>2000:raise ValueError('Export exceeds 2000 records; use a bounded selection')
            records=[self.personal.store.unpack(r) for r in rows]
        if kind=='contact' and format=='csv':
            out=io.StringIO(newline='');keys=['uid','display_name','emails','phones','organization','aliases','notes','external_ids','project_ids'];writer=csv.DictWriter(out,fieldnames=keys+['dmdo_csv_escape']);writer.writeheader()
            for r in records:writer.writerow({**{k:safe_csv(json.dumps(r[k],ensure_ascii=False) if isinstance(r[k],list) else r[k]) for k in keys},'dmdo_csv_escape':'1'})
            return out.getvalue()
        if kind=='contact' and format=='vcf':
            cards=[]
            for r in records:
                card=vobject.vCard();card.add('uid').value=r['uid'];card.add('fn').value=r['display_name'];card.add('n').value=vobject.vcard.Name(family=r['display_name'])
                card.add('org').value=[r['organization']];card.add('note').value=r['notes']
                if r['aliases']:card.add('nickname').value=r['aliases'][0]
                card.add('x-dmdo-aliases').value=json.dumps(r['aliases'])
                for key,name in [('emails','email'),('phones','tel')]:
                    for entry in r[key]:c=card.add(name);c.value=entry['value'];c.params['TYPE']=[entry['label']]
                for project in r['project_ids']:card.add('x-dmdo-project').value=project
                for external in r['external_ids']:card.add('x-dmdo-external').value=json.dumps(external)
                cards.append(card.serialize())
            return ''.join(cards)
        if kind=='event' and format=='ics':
            calendar=Calendar();calendar.add('prodid','-//OLIVE//Local Personal Core//EN');calendar.add('version','2.0')
            for r in records:
                def component(patch=None,occurrence=None):
                    item=Event();item.add('uid',r['uid']);item.add('dtstamp',datetime.now(timezone.utc));values={**r,**(patch or {})}
                    decode=v.day if r['all_day'] else lambda value:datetime.fromisoformat(value).astimezone(v.zone(r['timezone']))
                    if occurrence and not (patch or {}).get('start'):
                        point=decode(occurrence);duration=decode(r['end'])-decode(r['start'])
                        values.update(start=point.isoformat(),end=(point+duration).isoformat())
                    item.add('dtstart',decode(values['start']));item.add('dtend',decode(values['end']))
                    for key,prop in [('title','summary'),('description','description'),('location','location')]:item.add(prop,values[key])
                    item.add('status','CANCELLED' if values.get('cancelled') else values['status'].upper());item.add('transp','TRANSPARENT' if r['transparent'] else 'OPAQUE')
                    if occurrence:item.add('recurrence-id',decode(occurrence))
                    elif r['recurrence']:
                        from icalendar import vRecur
                        item.add('rrule',vRecur.from_ical(r['recurrence']))
                    if r['project_id']:item.add('x-dmdo-project',r['project_id'])
                    if r['contact_ids']:item.add('x-dmdo-contact',json.dumps(r['contact_ids']))
                    return item
                calendar.add_component(component())
                for key,patch in r['exceptions'].items():calendar.add_component(component(patch,key))
            return calendar.to_ical().decode()
        raise ValueError('Unsupported export format')
