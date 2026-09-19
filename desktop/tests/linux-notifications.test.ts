import {expect,it} from 'vitest';
import {completionNotice,NoticeGate,type Notice} from '../electron/notifications';
it('delivers selected completions without leaking content or progress',()=>{
  expect(completionNotice('notification',{message:'secret'})).toBeNull();
  expect(completionNotice('agent',{id:'a',state:'running'})).toBeNull();
  for(const [topic,data] of Object.entries({'agent':{id:'a',state:'completed'},'build.result':{id:'b',state:'completed'},'personal.reminders':{new_count:2,delivery_ids:['r'],delivered_at:'now'},'mail.attention':{connection_id:'c'},'download.completed':{id:'d'}})){
    const notice=completionNotice(topic,{...data,secret:'private'});expect(notice?.title).toContain('OLIVE');expect(JSON.stringify(notice)).not.toContain('private');
  }
});
it('claims before showing, deduplicates across restart, and bounds storms',()=>{
  let persisted:string[]=[];const shown:Notice[]=[];
  const show=(n:Notice)=>{expect(persisted).toContain(n.key);shown.push(n);};
  const save=(keys:string[])=>{persisted=keys;};
  const gate=new NoticeGate([],save,show);
  const notice=(key:string)=>({key,title:'OLIVE',body:'done'});
  gate.deliver(notice('one'),0);gate.deliver(notice('one'),0);
  new NoticeGate(persisted,save,show).deliver(notice('one'),1);
  expect(shown).toHaveLength(1);
  for(let i=0;i<20;i++)gate.deliver(notice(String(i)),1);
  expect(shown).toHaveLength(4);
  gate.deliver(notice('later'),60001);expect(shown).toHaveLength(5);
  expect(()=>new NoticeGate([],()=>{throw Error('disk');},show).deliver(notice('failure'))).toThrow();
  expect(shown).toHaveLength(5);
});
