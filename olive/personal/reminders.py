"""One runtime-owned scheduler; durable in-app history, no OS service or sends."""
import asyncio
import hashlib
import sqlite3
from datetime import datetime,timedelta,timezone,time
from . import validation as v
from .calendar import occurrences,bounds
from .store import timestamp

UTC=timezone.utc


def validate_reminder(value):
    v.fields(value,{'target_kind','target_id','at','offset_minutes','timezone'})
    if value.get('target_kind') not in {'event','task'}:raise ValueError('Reminders link to an event or personal task')
    result=dict(target_kind=value['target_kind'],target_id=v.text(value.get('target_id',''),100,True),
                at=v.text(value.get('at',''),80),offset_minutes=value.get('offset_minutes',30),timezone=value.get('timezone','Africa/Johannesburg'))
    v.zone(result['timezone']);v.integer(result['offset_minutes'],0,525600)
    if result['at']:
        parsed=datetime.fromisoformat(v.text(result['at'],80,True))
        # Persistence stores an absolute UTC instant while retaining the user's
        # timezone for subsequent local edits. Revalidation must accept that
        # canonical representation, not reinterpret it as a local wall clock.
        zone='UTC' if parsed.tzinfo is not None and parsed.utcoffset()==timedelta(0) else result['timezone']
        result['at']=v.instant(result['at'],zone).astimezone(UTC).isoformat()
    return result


class ReminderScheduler:
    def __init__(self,personal,publish,clock=lambda:datetime.now(UTC)):
        self.personal=personal;self.store=personal.store;self.publish=publish;self.clock=clock
        self.worker=None;self.stopping=False;self.last_rebuild=None;self.dirty=True
        self.error=''

    def changed(self):self.dirty=True

    def start(self):
        if self.worker is None:self.worker=asyncio.create_task(self.run())

    async def close(self):
        self.stopping=True
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker,return_exceptions=True)
            self.worker=None
        # Cancelling an asyncio waiter does not stop its database worker. Wait
        # for the store lock before backup replacement or runtime termination.
        await asyncio.to_thread(self.quiesce)

    def quiesce(self):
        with self.store.lock:pass

    async def run(self):
        while not self.stopping:
            try:
                summary=await asyncio.to_thread(self.tick)
                recovered=bool(self.error)
                self.error=''
                if summary['new_count'] or recovered:self.publish('personal.reminders',summary)
            except asyncio.CancelledError:raise
            except (ValueError,OSError,LookupError,sqlite3.Error):
                changed=not self.error
                self.error='Reminder scheduling is unavailable. Existing records are retained; review schedules and local storage in Diagnostics.'
                if changed:self.publish('personal.reminders',{'state':'degraded','message':self.error})
            await asyncio.sleep(5)

    def rebuild(self,db,now):
        rows=list(db.execute("SELECT * FROM records WHERE kind='reminder' AND deleted=0 LIMIT 10001"))
        if len(rows)>10000:raise ValueError('Reminder scheduling safety limit reached')
        definitions=[self.store.unpack(r) for r in rows]
        restored=db.execute("SELECT value FROM metadata WHERE key='restore_cutoff'").fetchone()
        cutoff=datetime.fromisoformat(restored[0]) if restored else None
        for reminder in definitions:
            try:target=self.store.get(db,reminder['target_kind'],reminder['target_id'])
            except LookupError:continue
            wanted=[]
            if target.get('status') not in {'completed','cancelled'}:
                if reminder['at']:wanted=[('explicit',datetime.fromisoformat(reminder['at']))]
                elif reminder['target_kind']=='event':
                    horizon=min(390,90+reminder['offset_minutes']//1440)
                    for item in occurrences(target,now-timedelta(days=7),now+timedelta(days=horizon)):
                        wanted.append((item['occurrence_id'],bounds(item)[0].astimezone(UTC)-timedelta(minutes=reminder['offset_minutes'])))
                elif target['due']:
                    due=(datetime.combine(v.day(target['due']),time(9),v.zone(target['timezone'])) if target['due_kind']=='date' else datetime.fromisoformat(target['due']))
                    wanted=[('task',due.astimezone(UTC)-timedelta(minutes=reminder['offset_minutes']))]
            occurrences_wanted=set()
            for occurrence,due in wanted:
                occurrences_wanted.add(occurrence)
                key=hashlib.sha256((reminder['id']+'\0'+occurrence).encode()).hexdigest()
                row=db.execute('SELECT state FROM deliveries WHERE id=?',(key,)).fetchone()
                if row is None:
                    state='restored' if cutoff and due.astimezone(UTC)<=cutoff and datetime.fromisoformat(reminder['created_at'])<=cutoff else 'pending'
                    db.execute('INSERT INTO deliveries(id,reminder_id,occurrence,due_at,state,updated_at) VALUES(?,?,?,?,?,?)',
                               (key,reminder['id'],occurrence,due.astimezone(UTC).isoformat(),state,timestamp()))
                elif row['state']=='pending':
                    db.execute('UPDATE deliveries SET due_at=?,updated_at=? WHERE id=?',(due.astimezone(UTC).isoformat(),timestamp(),key))
                elif row['state']=='cancelled' and due>now:
                    # Explicitly reopening a linked task can restore a future
                    # pending reminder, never replay past/dismissed deliveries.
                    db.execute("UPDATE deliveries SET state='pending',due_at=?,updated_at=? WHERE id=?",(due.astimezone(UTC).isoformat(),timestamp(),key))
            for row in list(db.execute("SELECT id,occurrence FROM deliveries WHERE reminder_id=? AND state IN ('pending','snoozed')",(reminder['id'],))):
                if row['occurrence'] not in occurrences_wanted:
                    db.execute("UPDATE deliveries SET state='cancelled',updated_at=? WHERE id=?",(timestamp(),row['id']))

    def tick(self,now=None):
        now=now or self.clock()
        if now.tzinfo is None:raise ValueError('Reminder clock must be timezone-aware')
        now=now.astimezone(UTC)
        with self.store.transaction() as db:
            if self.dirty or self.last_rebuild is None or now-self.last_rebuild>=timedelta(minutes=1):
                self.rebuild(db,now);self.last_rebuild=now;self.dirty=False
            count=db.execute("SELECT count(*) FROM deliveries WHERE state IN ('pending','snoozed') AND due_at<=?",(now.isoformat(),)).fetchone()[0]
            due=list(db.execute("SELECT id FROM deliveries WHERE state IN ('pending','snoozed') AND due_at<=? ORDER BY due_at LIMIT 50",(now.isoformat(),)))
            db.execute("UPDATE deliveries SET state='delivered',delivered_at=?,updated_at=? WHERE state IN ('pending','snoozed') AND due_at<=?",(now.isoformat(),now.isoformat(),now.isoformat()))
        return {'new_count':count,'message':f'{count} reminders are ready in your activity centre.' if count else '',
                'state':'ready','delivery_ids':[r['id'] for r in due]}

    def history(self,limit=50,offset=0):
        v.integer(limit,1,200);v.integer(offset,0,100000)
        with self.store.transaction() as db:
            result=[]
            for row in db.execute("SELECT * FROM deliveries WHERE state!='pending' ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",(limit,offset)):
                item=dict(row)
                try:
                    reminder=self.store.get(db,'reminder',row['reminder_id']);target=self.store.get(db,reminder['target_kind'],reminder['target_id'])
                    item.update(title=target['title'],target_kind=reminder['target_kind'],target_id=target['id'])
                except LookupError:item.update(title='Removed personal record',target_kind='',target_id='')
                result.append(item)
            return result

    def act(self,delivery_id,action,minutes=10):
        if action not in {'snooze','dismiss'}:raise ValueError('Unsupported reminder action')
        v.integer(minutes,1,10080)
        with self.store.transaction() as db:
            row=db.execute('SELECT * FROM deliveries WHERE id=?',(delivery_id,)).fetchone()
            if not row:raise LookupError('Reminder delivery not found')
            if row['state'] not in {'delivered','snoozed'}:raise ValueError('This reminder is no longer active')
            now=self.clock().astimezone(UTC)
            due=(now+timedelta(minutes=minutes)).isoformat() if action=='snooze' else row['due_at']
            db.execute('UPDATE deliveries SET state=?,due_at=?,updated_at=? WHERE id=?',
                       ('snoozed' if action=='snooze' else 'dismissed',due,now.isoformat(),delivery_id))
        return {'id':delivery_id,'status':'snoozed' if action=='snooze' else 'dismissed'}
