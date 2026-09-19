"""Validated local recurrence and deterministic half-open interval arithmetic."""
from datetime import datetime, timedelta, timezone, time
from itertools import islice
from dateutil.rrule import rrulestr
from dateutil.tz import datetime_exists
from . import validation as v

UTC=timezone.utc
RULE_KEYS={'FREQ','INTERVAL','BYDAY','BYMONTHDAY','BYMONTH','COUNT','UNTIL','WKST'}


def validate_rule(rule,start):
    v.text(rule,500)
    if not rule:return ''
    parts=rule.upper().split(';')
    fields={}
    for part in parts:
        key,sep,value=part.partition('=')
        if not sep or key not in RULE_KEYS or key in fields:raise ValueError('Unsupported recurrence field')
        fields[key]=value
    if fields.get('FREQ') not in {'DAILY','WEEKLY','MONTHLY','YEARLY'}:raise ValueError('Unsupported recurrence frequency')
    if 'COUNT' in fields and 'UNTIL' in fields:raise ValueError('Use Count or Until, not both')
    for key,limit in [('INTERVAL',366),('COUNT',10000)]:
        if key in fields:v.integer(int(fields[key]),1,limit)
    rrulestr(';'.join(parts),dtstart=start)
    return ';'.join(parts)


def event(value):
    v.fields(value,{'calendar_id','title','description','location','start','end','timezone','all_day','start_fold','end_fold',
                    'recurrence','exceptions','contact_ids','project_id','status','transparent','unsupported','original_ics'})
    result={k:v.text(value.get(k,''),8000 if k=='description' else 300,k in {'calendar_id','title'})
            for k in ('calendar_id','title','description','location','project_id')}
    result.update(timezone=value.get('timezone','Africa/Johannesburg'),all_day=v.boolean(value.get('all_day',False)),
                  status=value.get('status','confirmed'),transparent=v.boolean(value.get('transparent',False)),
                  contact_ids=v.strings(value.get('contact_ids',[])),unsupported=v.strings(value.get('unsupported',[]),100),
                  original_ics=v.text(value.get('original_ics',''),32000))
    zone=v.zone(result['timezone'])
    if result['status'] not in {'confirmed','tentative','cancelled'}:raise ValueError('Invalid event status')
    if result['all_day']:
        start,end=v.day(value.get('start')),v.day(value.get('end'))
        rule_start=datetime.combine(start,time.min)
    else:
        start=v.instant(value.get('start'),result['timezone'],value.get('start_fold'))
        end=v.instant(value.get('end'),result['timezone'],value.get('end_fold'))
        rule_start=start
    if (end<=start if result['all_day'] else end.astimezone(UTC)<=start.astimezone(UTC)):raise ValueError('End must be after start (all-day end is exclusive)')
    if (end-start).days>366:raise ValueError('Event duration exceeds one year')
    result.update(start=start.isoformat(),end=end.isoformat(),recurrence=validate_rule(value.get('recurrence',''),rule_start))
    exceptions=value.get('exceptions',{})
    if not isinstance(exceptions,dict) or len(exceptions)>500:raise ValueError('Too many recurrence exceptions')
    result['exceptions']={}
    for occurrence,patch in exceptions.items():
        (v.day(occurrence) if result['all_day'] else v.instant(occurrence,result['timezone']))
        v.fields(patch,{'start','end','title','location','description','cancelled'})
        for key in ('title','location','description'):
            if key in patch:v.text(patch[key],8000 if key=='description' else 300,key=='title')
        if 'cancelled' in patch:v.boolean(patch['cancelled'])
        if ('start' in patch)!=('end' in patch):raise ValueError('Occurrence start and end must change together')
        if 'start' in patch:
            validated=event({**result,'exceptions':{},'recurrence':'',**{k:x for k,x in patch.items() if k!='cancelled'}})
            patch={**patch,'start':validated['start'],'end':validated['end']}
        result['exceptions'][occurrence]=patch
    if exceptions:
        remaining=set(exceptions)
        latest=max(v.day(x) if result['all_day'] else datetime.fromisoformat(x).astimezone(UTC) for x in remaining)
        for point in recurrence_points(result):
            key=point.date().isoformat() if result['all_day'] else point.isoformat()
            remaining.discard(key)
            if not remaining:break
            if (point.date() if result['all_day'] else point.astimezone(UTC))>latest:break
        if remaining:raise ValueError('Exception does not identify an original occurrence in this series')
    return result


def recurrence_points(record):
    """RFC 5545 invalid local dates/times neither occur nor consume COUNT."""
    start,_=bounds(record)
    fields=dict(p.split('=',1) for p in record['recurrence'].split(';')) if record['recurrence'] else {}
    count=int(fields.pop('COUNT')) if 'COUNT' in fields else None
    rule=';'.join(k+'='+x for k,x in fields.items())
    source=rrulestr(rule,dtstart=start.replace(tzinfo=None) if record['all_day'] else start) if rule else [start]
    emitted=0
    for index,point in enumerate(islice(source,100001)):
        if index==100000:raise ValueError('Recurrence expansion exceeds its safety limit')
        if point.tzinfo is None:point=point.replace(tzinfo=start.tzinfo)
        if not record['all_day'] and not datetime_exists(point):continue
        yield point
        emitted+=1
        if count is not None and emitted>=count:break


def bounds(record):
    zone=v.zone(record['timezone'])
    if record['all_day']:
        return tuple(datetime.combine(v.day(record[k]),time.min,zone) for k in ('start','end'))
    return tuple(datetime.fromisoformat(record[k]).astimezone(zone) for k in ('start','end'))


def occurrences(record, after, before, limit=1000):
    if after.tzinfo is None or before.tzinfo is None or before<=after or before-after>timedelta(days=400):raise ValueError('Query a bounded aware calendar range of at most 400 days')
    if record['status']=='cancelled':return []
    start,end=bounds(record)
    duration=end.replace(tzinfo=None)-start.replace(tzinfo=None)
    result=[];seen=set()
    def include(point,original):
        if not datetime_exists(point):return
        finish=point+duration
        if not datetime_exists(finish):return
        patch=record['exceptions'].get(original,{})
        if patch.get('cancelled'):return
        item={**record,**{k:x for k,x in patch.items() if k!='cancelled'},'occurrence_id':original}
        item.update(start=patch.get('start',point.date().isoformat() if record['all_day'] else point.isoformat()),
                    end=patch.get('end',finish.date().isoformat() if record['all_day'] else finish.isoformat()))
        a,b=bounds(item)
        if a.astimezone(UTC)<before.astimezone(UTC) and b.astimezone(UTC)>after.astimezone(UTC):result.append(item)
        if len(result)>limit:raise ValueError('Too many occurrences; narrow the date range')
    for point in recurrence_points(record):
        if point.astimezone(UTC)>=before.astimezone(UTC):break
        original=point.date().isoformat() if record['all_day'] else point.isoformat()
        seen.add(original);include(point,original)
    # Exceptions can move an occurrence into the range from outside it.
    for original,patch in record['exceptions'].items():
        if original not in seen and 'start' in patch:
            point=datetime.combine(v.day(original),time.min,v.zone(record['timezone'])) if record['all_day'] else datetime.fromisoformat(original)
            include(point,original)
    return sorted(result,key=lambda x:bounds(x)[0].astimezone(UTC))


def free_time(events,after,before,duration,profile,limit=20):
    v.integer(duration,5,1440)
    if before<=after or before-after>timedelta(days=62):raise ValueError('Search at most 62 days for availability')
    busy=[]
    for item in events:
        if not item['transparent'] and item['status']!='cancelled':
            a,b=bounds(item);busy.append((a.astimezone(UTC),b.astimezone(UTC)))
    merged=[]
    for a,b in sorted(busy):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    zone=v.zone(profile['timezone']);hours=profile['working_hours'];day=after.astimezone(zone).date();slots=[]
    while day<=before.astimezone(zone).date() and len(slots)<limit:
        if day.weekday() in hours['days']:
            start=max(datetime.combine(day,time.fromisoformat(hours['start']),zone).astimezone(UTC),after.astimezone(UTC))
            end=min(datetime.combine(day,time.fromisoformat(hours['end']),zone).astimezone(UTC),before.astimezone(UTC))
            cursor=start
            for a,b in merged+[(end,end)]:
                if b<=cursor:continue
                if a>cursor and min(a,end)-cursor>=timedelta(minutes=duration):
                    slots.append({'start':cursor.astimezone(zone).isoformat(),'end':(cursor+timedelta(minutes=duration)).astimezone(zone).isoformat(),'status':'proposed'})
                    if len(slots)>=limit:break
                cursor=max(cursor,b)
                if cursor>=end:break
        day+=timedelta(days=1)
    return slots
