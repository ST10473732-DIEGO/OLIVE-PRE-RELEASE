"""Strict native records. Imported text is data, never executable markup."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dateutil.tz import datetime_exists, datetime_ambiguous
import re


def fields(value, allowed):
    if not isinstance(value, dict) or set(value)-set(allowed):
        raise ValueError('Unknown or invalid personal record fields')


def text(value, maximum=200, required=False):
    if not isinstance(value,str) or len(value)>maximum or '\x00' in value:
        raise ValueError('Invalid or oversized text')
    if required and not value.strip():
        raise ValueError('A name or title is required')
    return value.strip() if required else value


def strings(value, maximum=30, text_limit=200):
    if not isinstance(value,list) or len(value)>maximum:
        raise ValueError('Too many linked values')
    return list(dict.fromkeys(text(x,text_limit,True) for x in value))


def zone(value):
    text(value,100,True)
    try:return ZoneInfo(value)
    except (ZoneInfoNotFoundError,ValueError):raise ValueError('Choose a valid IANA timezone') from None


def instant(value, tz='Africa/Johannesburg', fold=None):
    parsed=datetime.fromisoformat(text(value,80,True))
    local=parsed.replace(tzinfo=zone(tz)) if parsed.tzinfo is None else parsed.astimezone(zone(tz))
    if parsed.tzinfo is not None and parsed.replace(tzinfo=None)!=local.replace(tzinfo=None):
        raise ValueError('Time offset does not match the selected timezone')
    if not datetime_exists(local):raise ValueError('This local time does not exist during the timezone transition')
    if parsed.tzinfo is None and datetime_ambiguous(local):
        if fold not in (0,1):raise ValueError('This local time occurs twice; choose the first or second occurrence')
        local=local.replace(fold=fold)
    return local


def day(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('Use a date in YYYY-MM-DD format')
    return date.fromisoformat(value)


def integer(value, low, high):
    if type(value) is not int or not low<=value<=high:raise ValueError('Number is outside its supported range')
    return value


def boolean(value):
    if type(value) is not bool:raise ValueError('Expected a true/false value')
    return value


def profile(value):
    fields(value, {'display_name','timezone','locale','working_hours','default_calendar','avatar','date_format','time_format'})
    result=dict(display_name=text(value.get('display_name',''),120),timezone=value.get('timezone','Africa/Johannesburg'),
                locale=text(value.get('locale','en-ZA'),20),default_calendar=text(value.get('default_calendar',''),100),
                avatar=text(value.get('avatar',''),40000),date_format=value.get('date_format','dd/MM/yyyy'),time_format=value.get('time_format','24h'))
    zone(result['timezone'])
    if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z]{2,8}){0,2}',result['locale']):raise ValueError('Invalid locale')
    if result['date_format'] not in {'dd/MM/yyyy','yyyy-MM-dd','MM/dd/yyyy'} or result['time_format'] not in {'12h','24h'}:raise ValueError('Invalid date/time preference')
    if result['avatar'] and not re.fullmatch(r'data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=]+',result['avatar']):raise ValueError('Use an imported local image avatar')
    hours=value.get('working_hours',{'days':[0,1,2,3,4],'start':'09:00','end':'17:00'})
    fields(hours,{'days','start','end'})
    if not isinstance(hours.get('days'),list) or len(hours['days'])>7:raise ValueError('Invalid working days')
    for d in hours['days']:integer(d,0,6)
    for k in ('start','end'):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',hours.get(k,'')):raise ValueError('Invalid working time')
    if hours['end']<=hours['start']:raise ValueError('Working hours must end after they start')
    result['working_hours']=dict(hours,days=sorted(set(hours['days'])))
    return result


def contact(value):
    fields(value,{'display_name','emails','phones','organization','aliases','notes','external_ids','project_ids','unsupported'})
    result={k:text(value.get(k,''),8000 if k=='notes' else 200,k=='display_name') for k in ('display_name','organization','notes')}
    result.update(aliases=strings(value.get('aliases',[])),project_ids=strings(value.get('project_ids',[])),unsupported=strings(value.get('unsupported',[]),100,1000))
    for key in ('emails','phones','external_ids'):
        entries=value.get(key,[])
        if not isinstance(entries,list) or len(entries)>20:raise ValueError('Too many contact identifiers')
        result[key]=[]
        for item in entries:
            fields(item,{'label','value'})
            entry={'label':text(item.get('label','other'),60,True),'value':text(item.get('value',''),300,True)}
            if '\r' in entry['value'] or '\n' in entry['value']:raise ValueError('Identifiers cannot contain newlines')
            if key=='emails' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',entry['value']):raise ValueError('Invalid email address')
            result[key].append(entry)
    return result


def calendar(value):
    fields(value,{'title','colour','visible'})
    colour=value.get('colour','#5b9bff')
    if not isinstance(colour,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',colour):raise ValueError('Invalid calendar colour')
    return dict(title=text(value.get('title',''),120,True),colour=colour,visible=boolean(value.get('visible',True)))


def task(value):
    fields(value,{'title','description','status','priority','due','due_kind','timezone','project_id','event_id','agent_task_id','contact_ids','completed_at'})
    result={k:text(value.get(k,''),8000 if k=='description' else 200,k=='title') for k in ('title','description','project_id','event_id','agent_task_id')}
    result.update(status=value.get('status','open'),priority=value.get('priority','normal'),due=value.get('due',''),due_kind=value.get('due_kind','date'),
                  timezone=value.get('timezone','Africa/Johannesburg'),contact_ids=strings(value.get('contact_ids',[])),completed_at=value.get('completed_at',''))
    if result['status'] not in {'open','completed'} or result['priority'] not in {'low','normal','high'} or result['due_kind'] not in {'date','time'}:raise ValueError('Invalid task state')
    zone(result['timezone'])
    if result['due']:
        result['due']=day(result['due']).isoformat() if result['due_kind']=='date' else instant(result['due'],result['timezone']).isoformat()
    text(result['completed_at'],80)
    return result
