import {test,expect,_electron as electron} from '@playwright/test';
import {mkdtemp,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {openSpace} from './shell';

test('Linux L3 reminder closes before due, reopens, fires once through Plasma, and survives another restart',async()=>{
  test.skip(process.platform!=='linux','Native Linux notification journey');
  test.setTimeout(120000);
  const profile=await mkdtemp(path.join(tmpdir(),'olive-l3-reminder-'));
  const launch=()=>electron.launch({args:[path.resolve('.'),'--ozone-platform=wayland'],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  let app=await launch();
  try {
    let page=await app.firstWindow();await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    const task=await page.evaluate(()=>window.olive.call('tasks.create',{body:{title:'L3 synthetic reminder'}})) as {id:string};
    await page.evaluate(async({id,at})=>window.olive.call('reminders.create',{body:{target_kind:'task',target_id:id,at,timezone:'Africa/Johannesburg'}}),{id:task.id,at:new Date(Date.now()+15000).toISOString()});
    await app.close();app=await launch();
    await app.evaluate(({Notification})=>{
      const host=globalThis as typeof globalThis & {l3Notices:unknown[]};host.l3Notices=[];
      const show=Notification.prototype.show;
      Notification.prototype.show=function(){this.on('show',()=>host.l3Notices.push({title:this.title,body:this.body}));return show.call(this);};
    });
    page=await app.firstWindow();await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await expect.poll(()=>app.evaluate(()=> (globalThis as typeof globalThis & {l3Notices:unknown[]}).l3Notices),{timeout:30000}).toEqual([{title:'OLIVE — Reminders',body:'1 reminders are ready in your activity centre.'}]);
    const history=await page.evaluate(()=>window.olive.call('reminders.history',{})) as {items:unknown[]};expect(history.items).toHaveLength(1);
    const claims=await readFile(path.join(profile,'native-notification-claims.json'),'utf8');
    for(const space of ['Mail','Studio','Agent','Desktop Control','Settings','Chat'])await openSpace(page,space);
    const capabilities=await page.evaluate(()=>window.olive.call('desktop.status',{})) as {available:boolean;platform_capabilities:{session:string}};
    expect(capabilities.available).toBe(false);expect(capabilities.platform_capabilities.session).toBe('wayland');
    await app.close();app=await launch();page=await app.firstWindow();await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await expect.poll(async()=>((await page.evaluate(()=>window.olive.call('reminders.history',{}))) as {items:unknown[]}).items.length).toBe(1);
    await page.waitForTimeout(6000);
    expect(await readFile(path.join(profile,'native-notification-claims.json'),'utf8')).toBe(claims);
    const duplicate=spawnSync(path.resolve('node_modules/electron/dist/electron'),[path.resolve('.')],{env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'},timeout:15000,encoding:'utf8'});
    expect(duplicate.status,duplicate.stderr).toBe(0);
    await app.evaluate(({app})=>app.getAppMetrics());
    await page.waitForTimeout(5000);
    const idle=await app.evaluate(({app,webContents})=>({metrics:app.getAppMetrics(),webContents:webContents.getAllWebContents().length}));
    const probe=spawnSync(path.resolve('../.venv/bin/python'),['-c','import psutil,json,sys; p=psutil.Process(int(sys.argv[1])); print(json.dumps([dict(pid=c.pid,created=c.create_time()) for c in [p,*p.children(recursive=True)]]))',String(app.process().pid)],{encoding:'utf8'});
    expect(probe.status).toBe(0);
    await writeFile(test.info().outputPath('native-evidence.json'),JSON.stringify({history,capabilities,idle,owned:JSON.parse(probe.stdout)},null,2));
    await app.close();
    await expect.poll(()=>spawnSync(path.resolve('../.venv/bin/python'),['-c','import psutil,json,sys; alive=[]\nfor x in json.loads(sys.argv[1]):\n try:\n  p=psutil.Process(x["pid"])\n  if p.create_time()==x["created"] and p.status()!=psutil.STATUS_ZOMBIE:alive.append(x["pid"])\n except psutil.NoSuchProcess:pass\nprint(json.dumps(alive))',probe.stdout],{encoding:'utf8'}).stdout.trim(),{timeout:15000}).toBe('[]');
  }finally{await app.close();}
});
