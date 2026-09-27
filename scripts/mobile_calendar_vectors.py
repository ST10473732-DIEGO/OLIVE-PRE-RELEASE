"""C5 calendar vectors from the authoritative desktop validator/expander."""
import json
from pathlib import Path
from datetime import datetime
from olive.personal.calendar import event, occurrences

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/mobile_connect/calendar.json'

def generate():
    base = dict(calendar_id='a'*32, title='Synthetic calendar series', start='2026-01-01T09:00:00+00:00', end='2026-01-01T10:00:00+00:00', timezone='UTC')
    raw = [dict(base, recurrence=rule) for rule in [
        '', 'FREQ=DAILY;COUNT=5', 'FREQ=DAILY;INTERVAL=3;BYDAY=MO,WE,FR;COUNT=8',
        'FREQ=WEEKLY;INTERVAL=2;BYDAY=SU,TU;WKST=SU;COUNT=9',
        'FREQ=MONTHLY;BYDAY=2MO,-1FR;COUNT=12', 'FREQ=MONTHLY;BYMONTHDAY=-1;COUNT=12',
        'FREQ=MONTHLY;INTERVAL=2;BYMONTHDAY=29,30,31;COUNT=12',
        'FREQ=YEARLY;BYMONTH=2,6;BYDAY=-1SU;COUNT=6',
        'FREQ=YEARLY;BYDAY=20MO,-2FR;COUNT=6', 'FREQ=DAILY;UNTIL=20260109T090000Z',
        'FREQ=YEARLY;BYMONTHDAY=15;COUNT=12', 'FREQ=YEARLY;COUNT=3',
        'FREQ=WEEKLY;BYMONTHDAY=1,15;COUNT=5', 'FREQ=MONTHLY;BYMONTH=3,7;COUNT=4', 'FREQ=MONTHLY;BYMONTHDAY=0;COUNT=3', 'FREQ=YEARLY;BYMONTH=0', 'FREQ=MONTHLY;BYMONTHDAY=32', 'FREQ=MONTHLY;BYDAY=MO,-1FR;COUNT=6', 'FREQ=YEARLY;BYMONTH=3;BYDAY=MO,-1FR;COUNT=6', 'FREQ=WEEKLY;BYDAY=1MO;COUNT=3']]
    raw += [dict(base,start='2026-01-01T09:00:00.123456+00:00',end='2026-01-01T10:00:00.123456+00:00',recurrence='FREQ=DAILY;COUNT=2'), dict(base, start='2026-01-31T09:00:00+00:00', end='2026-01-31T10:00:00+00:00', recurrence='FREQ=MONTHLY;COUNT=6'),
        dict(base, all_day=True, start='2026-01-01', end='2026-01-03', recurrence='FREQ=WEEKLY;COUNT=5'),
        dict(base, start='2026-03-07T02:30:00-05:00', end='2026-03-07T03:30:00-05:00', timezone='America/New_York', recurrence='FREQ=DAILY;COUNT=4'),
        dict(base, start='2026-10-31T01:30:00-04:00', end='2026-10-31T02:30:00-04:00', timezone='America/New_York', recurrence='FREQ=DAILY;COUNT=4'),
        dict(base, recurrence='FREQ=DAILY;COUNT=3', exceptions={'2026-01-02T09:00:00+00:00': {'cancelled': True}, '2026-01-03T09:00:00+00:00': {'start':'2026-02-03T10:00:00+00:00','end':'2026-02-03T11:00:00+00:00','title':'Moved'}}),
        dict(base, all_day=True, start='2026-01-01', end='2026-01-02', recurrence='FREQ=DAILY;COUNT=3', exceptions={'2026-01-02': {'title':'Changed'}})]
    after='2026-01-01T00:00:00+00:00'; before='2027-01-01T00:00:00+00:00'
    valid=[]
    for value in raw:
        payload=event(value)
        result=occurrences(payload,datetime.fromisoformat(after),datetime.fromisoformat(before))
        valid.append(dict(payload=payload, after=after,before=before, occurrences=[{k:r[k] for k in ('start','end','title','occurrence_id')} for r in result]))
    invalid=[]
    for patch in [dict(recurrence='FREQ=DAILY;UNTIL=20260230T090000Z'),dict(recurrence='FREQ=DAILY;UNTIL=20260201T090000'),
                  dict(recurrence='FREQ=DAILY;COUNT=4;',), dict(recurrence='FREQ=DAILY;COUNT=0'),
                  dict(exceptions={'2026-01-02T09:00:00+00:00':{'title':'Not an occurrence'}}),
                  dict(exceptions={'2026-01-01T09:00:00+00:00':{'start':'2026-01-01T11:00:00+00:00'}}),
                  dict(exceptions={'2026-01-01T09:00:00+00:00':{'start':'2026-01-01T11:00:00+00:00','end':'2026-01-01T10:00:00+00:00'}})]:
        value=dict(event(base),**patch)
        try: event(value)
        except (ValueError,TypeError): invalid.append(value)
        else: raise AssertionError('Expected rejected calendar fixture')
    return dict(valid=valid,invalid=invalid)

if __name__ == '__main__':
    FIXTURE.write_text(json.dumps(generate(),ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
    print('Wrote synthetic desktop calendar vectors')
