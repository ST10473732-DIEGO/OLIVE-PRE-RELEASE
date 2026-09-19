import {test, expect, _electron as electron} from '@playwright/test';
import path from 'node:path';
import {mkdtemp, mkdir, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {openSpace} from '../e2e/shell';

// Captures every page the workspaces redesign covers, populated and empty, at
// 1440x900 and 1920x1080, before and after. Evidence only.
const PAGES=(process.env.OLIVE_CAPTURE_PAGES||'Chat,Agent,Desktop Control,Projects,Knowledge,Memory,Mail,Tasks,Reminders').split(',');
const ACTIVITY=!process.env.OLIVE_CAPTURE_PAGES||process.env.OLIVE_CAPTURE_PAGES.includes('Activity');
const SEEDS=process.env.OLIVE_CAPTURE_SEEDED==='only'?[true]:process.env.OLIVE_CAPTURE_SEEDED==='none'?[false]:[true,false];

const EML=(from:string,subject:string,body:string,date:string)=>`From: ${from}\r\nTo: you@example.invalid\r\nSubject: ${subject}\r\nDate: ${date}\r\nMessage-ID: <${Math.random().toString(36).slice(2)}@example.invalid>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n${body}\r\n`;

test('workspaces capture', async()=>{
  test.setTimeout(600000);
  const root=path.resolve('..');
  const label=process.env.OLIVE_CAPTURE_LABEL||'after';
  const evidence=path.join(root,'artifacts/core/functionality/workspaces',label);
  await mkdir(evidence,{recursive:true});
  for(const seeded of SEEDS){
    const profile=await mkdtemp(path.join(tmpdir(),'olive-ws-'));
    if(seeded){const seed=spawnSync(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/seed_visual_fixture.py'),profile],{cwd:root,encoding:'utf8',windowsHide:true});expect(seed.status,seed.stderr).toBe(0);}
    const emls:string[]=[];
    if(seeded){
      const mail=path.join(profile,'fixture-mail');await mkdir(mail,{recursive:true});
      const items:[string,string,string,string][]=[
        ['Mara Ostrowski <mara@example.invalid>','Irrigation controller: firmware review notes','Hi,\n\nI went through the scheduling model. Two things stand out: the per-zone minutes table should keep history, and the night window needs a hard cap.\n\nCan we talk on Thursday?\n\nMara','Tue, 15 Sep 2026 09:12:00 +0200'],
        ['Greenhouse Supply <orders@example.invalid>','Order 4471 has shipped','Your order of 12 drip emitters and 2 solenoid valves has shipped.\n\nTracking: SYN-4471-XX','Mon, 14 Sep 2026 16:40:00 +0200'],
        ['Tomas Lind <tomas@example.invalid>','Re: weekend test run','Ran the 40-zone schedule overnight. No overlaps, but zone 17 logged twice. Log attached in the next mail.','Sun, 13 Sep 2026 21:05:00 +0200'],
      ];
      for(const [i,item] of items.entries()){const file=path.join(mail,`fixture-${i}.eml`);await writeFile(file,EML(...item));emls.push(file);}
      const seedMail=spawnSync(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/seed_visual_mail.py'),profile,...emls],{cwd:root,encoding:'utf8',windowsHide:true});expect(seedMail.status,seedMail.stderr).toBe(0);
    }
    const app=await electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
    try {
      const page=await app.firstWindow(); page.setDefaultTimeout(30000);
      const size=async(w:number,h:number)=>{await app.evaluate(({BrowserWindow},s)=>BrowserWindow.getAllWindows()[0].setContentSize(s[0],s[1]),[w,h]);await page.waitForTimeout(400);};
      await size(1440,900);
      await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
      await expect(page.locator('main.home')).toBeVisible();
      if(seeded){
        await expect.poll(()=>page.evaluate(async()=>Boolean(await window.olive.call('runtime.snapshot',{}))),{timeout:60000}).toBe(true);
        // Records the pages should show, created through the same IPC the UI uses.
        await page.evaluate(async()=>{
          const call=(method:string,args:Record<string,unknown>)=>(window.olive.call as (m:string,a:unknown)=>Promise<Record<string,string>>)(method,args);
          const project=await call('data.create_project',{title:'Greenhouse irrigation controller',description:'Firmware, scheduling model and the field trial for the 40-zone controller.'});
          await call('data.create_project',{title:'Thesis reading list',description:'Sources and notes for the literature review.'});
          const today=new Date();const iso=(d:number,h:number)=>{const t=new Date(today);t.setDate(t.getDate()+d);t.setHours(h,0,0,0);return t.toISOString();};const day=(d:number)=>iso(d,12).slice(0,10);
          const tasks=[
            {title:'Review Mara\'s firmware notes',description:'Per-zone minutes history and the night-window cap.',project_id:project.id,due:day(0),priority:'high'},
            {title:'Cap the night window at 40 minutes',project_id:project.id,due:day(0)},
            {title:'Re-run the 40-zone overnight schedule',description:'Zone 17 logged twice on the last run.',project_id:project.id,due:day(2)},
            {title:'Order replacement solenoid for zone 17',due:day(4)},
            {title:'Write the literature review outline',due:day(6)},
            {title:'Read chapter 3 of the scheduling survey'},
          ];
          const created:Record<string,string>[]=[];
          for(const body of tasks){created.push(await call('tasks.create',{body}));}
          const last=created[created.length-1];await call('tasks.complete',{record_id:last.id,revision:Number(last.revision)});
          await call('reminders.create',{body:{target_kind:'task',target_id:created[0].id,at:iso(0,10)}});
          await call('reminders.create',{body:{target_kind:'task',target_id:created[2].id,at:iso(2,8)}});
          for(const [content,category] of [
            ['Prefers concise answers with a short summary first, then detail.','preference'],
            ['Works on a greenhouse irrigation controller with 40 zones; firmware is written in Rust.','project'],
            ['Thursday afternoons are reserved for field trials; avoid scheduling then.','preference'],
            ['Uses metric units throughout.','fact'],
          ]){await call('data.memory_save',{content,category}).catch(()=>call('data.memory_save',{content,category:'general'}));}
          await call('mail.save_draft',{body:{to:['mara@example.invalid'],subject:'Thursday works — firmware notes',text:'Thursday at 14:00 works for me. I will bring the zone 17 log.'}});
        }).catch(error=>{console.error('seed via IPC failed',error);});
      }
      const tag=seeded?'populated':'empty';
      for(const name of PAGES.filter(n=>n!=='Activity')){
        await openSpace(page,name);
        await page.waitForTimeout(900);
        if(seeded && name==='Knowledge'){
          // Only the native picker is a double; the real indexer ingests the fixtures.
          const docs=path.join(profile,'fixture-docs');await mkdir(docs,{recursive:true});
          const files=[['Irrigation scheduling model.md','# Scheduling model\n\nForty zones, per-day minutes, history retained. The night window is capped at 40 minutes.\n'],['Field trial notes.txt','Zone 17 logged twice on the overnight run. Solenoid replacement ordered.\n']];
          for(const [file,text] of files){
            const full=path.join(docs,file);await writeFile(full,text);
            await app.evaluate(({dialog},chosen)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[chosen]});},full);
            await page.getByRole('button',{name:'Add source',exact:true}).click();
            await expect(page.getByRole('heading',{name:file,exact:true})).toBeVisible({timeout:60000});
          }
          await page.waitForTimeout(1200);
        }
        await page.screenshot({path:path.join(evidence,`${name.toLowerCase().replace(/ /g,'-')}-${tag}-1440.png`)});
        if(seeded && ['Mail','Chat','Agent','Knowledge','Projects'].includes(name)){
          await size(1920,1080);await page.waitForTimeout(400);
          await page.screenshot({path:path.join(evidence,`${name.toLowerCase().replace(/ /g,'-')}-${tag}-1920.png`)});
          await size(1440,900);
        }
        if(seeded && name==='Mail'){
          const first=page.locator('.mail-list-item').first();
          if(await first.count()){await first.click();await page.waitForTimeout(700);await page.screenshot({path:path.join(evidence,`mail-reading-${tag}-1440.png`)});}
        }
        if(seeded && name==='Projects'){
          const first=page.locator('.project-card').first();
          if(await first.count()){await first.click();await page.waitForTimeout(700);await page.screenshot({path:path.join(evidence,`projects-detail-${tag}-1440.png`)});}
        }
      }
      if(ACTIVITY){
        await page.getByRole('button',{name:'OLIVE activity',exact:true}).click();
        await page.waitForTimeout(500);
        await page.screenshot({path:path.join(evidence,`activity-${tag}-1440.png`)});
        await page.keyboard.press('Escape');
      }
    } finally {await app.close();}
  }
});
