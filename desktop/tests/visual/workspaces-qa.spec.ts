import {test, expect, _electron as electron} from '@playwright/test';
import path from 'node:path';
import {mkdtemp, mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {openSpace} from '../e2e/shell';

// Responsive and interaction QA for the workspaces redesign: composing mail,
// the mail reading pane at laptop widths, the task editor, and every
// redesigned page at 1366, 1100 and 900 pixels. Evidence only.
test('workspaces responsive QA', async()=>{
  test.setTimeout(600000);
  const root=path.resolve('..');
  const evidence=path.join(root,'artifacts/core/functionality/workspaces/qa');
  await mkdir(evidence,{recursive:true});
  const profile=await mkdtemp(path.join(tmpdir(),'olive-ws-qa-'));
  const app=await electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  try {
    const page=await app.firstWindow(); page.setDefaultTimeout(30000);
    const size=async(w:number,h:number)=>{await app.evaluate(({BrowserWindow},s)=>BrowserWindow.getAllWindows()[0].setContentSize(s[0],s[1]),[w,h]);await page.waitForTimeout(400);};
    const shot=(name:string)=>page.screenshot({path:path.join(evidence,`${name}.png`)});
    await size(1440,900);
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await expect(page.locator('main.home')).toBeVisible();
    await expect.poll(()=>page.evaluate(async()=>Boolean(await window.olive.call('runtime.snapshot',{}))),{timeout:60000}).toBe(true);
    await page.evaluate(async()=>{
      const call=(method:string,args:Record<string,unknown>)=>(window.olive.call as (m:string,a:unknown)=>Promise<Record<string,string>>)(method,args);
      const project=await call('data.create_project',{title:'Greenhouse irrigation controller',description:'Firmware and the field trial.'});
      for(const body of [
        {title:'Review the firmware notes',description:'Per-zone minutes history and the night-window cap.',project_id:project.id,due:new Date().toISOString().slice(0,10),priority:'high'},
        {title:'Order a replacement solenoid'},
      ]) await call('tasks.create',{body});
      await call('mail.save_draft',{body:{to:['mara@example.invalid'],subject:'Thursday works',text:'Thursday at 14:00 works for me.'}});
    });
    // Mail: composing state and the draft list.
    await openSpace(page,'Mail');
    await page.getByRole('button',{name:'Compose',exact:true}).click();
    await expect(page.getByRole('region',{name:'Mail composer',exact:true})).toBeVisible();
    await page.waitForTimeout(500);
    await shot('mail-composing-1440');
    await page.getByRole('button',{name:'Close composer',exact:true}).click();
    await page.getByRole('button',{name:/Drafts/}).first().click();
    await page.waitForTimeout(600);
    await shot('mail-drafts-1440');
    // Tasks: the editor sheet and the selected detail.
    await openSpace(page,'Tasks');
    await page.getByRole('button',{name:'All',exact:true}).click();
    await page.locator('.personal-task-title').filter({hasText:'Review the firmware notes'}).click();
    await page.waitForTimeout(500);
    await shot('tasks-selected-1440');
    await page.getByRole('button',{name:'Edit task',exact:true}).click();
    await expect(page.getByRole('dialog',{name:'Edit Task'})).toBeVisible();
    await page.waitForTimeout(400);
    await shot('tasks-editor-1440');
    await page.keyboard.press('Escape');
    // Reminders: the inline form.
    await openSpace(page,'Reminders');
    await page.getByRole('button',{name:'New Reminder',exact:true}).click();
    await page.waitForTimeout(400);
    await shot('reminders-form-1440');
    // Pages the Blank change touches but the brief did not restructure.
    for(const name of ['Calendar','Contacts','Settings']){
      const row=page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});
      if(await row.count()){await row.click();await page.waitForTimeout(700);await shot(`${name.toLowerCase()}-1440`);}
    }
    // Widths.
    for(const [w,h] of [[1366,768],[1100,760],[900,700]] as const){
      await size(w,h);
      for(const name of ['Chat','Mail','Tasks','Projects','Knowledge','Agent','Desktop Control','Memory','Reminders']){
        await openSpace(page,name);
        await page.waitForTimeout(600);
        if(name==='Mail'){const close=page.getByRole('button',{name:'Close composer',exact:true});if(await close.isVisible())await close.click();const first=page.locator('.mail-list-item').first();if(await first.isVisible())await first.click();await page.waitForTimeout(400);}
        await shot(`${name.toLowerCase().replace(/ /g,'-')}-${w}`);
      }
    }
  } finally {await app.close();}
});
