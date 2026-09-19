import {test, expect, _electron as electron} from '@playwright/test';
import path from 'node:path';
import {mkdtemp, mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {openSpace, toggleTheme} from '../e2e/shell';

// Light-theme sanity capture for the redesigned pages. Evidence only.
test('workspaces light theme', async()=>{
  test.setTimeout(300000);
  const evidence=path.resolve('../artifacts/core/functionality/workspaces/qa');
  await mkdir(evidence,{recursive:true});
  const profile=await mkdtemp(path.join(tmpdir(),'olive-ws-light-'));
  const app=await electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  try {
    const page=await app.firstWindow(); page.setDefaultTimeout(30000);
    await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1440,900));
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await expect(page.locator('main.home')).toBeVisible();
    await expect.poll(()=>page.evaluate(async()=>Boolean(await window.olive.call('runtime.snapshot',{}))),{timeout:60000}).toBe(true);
    await page.evaluate(async()=>{
      const call=(method:string,args:Record<string,unknown>)=>(window.olive.call as (m:string,a:unknown)=>Promise<Record<string,string>>)(method,args);
      await call('data.create_project',{title:'Greenhouse irrigation controller',description:'Firmware and the field trial.'});
      await call('tasks.create',{body:{title:'Review the firmware notes',due:new Date().toISOString().slice(0,10),priority:'high'}});
      await call('data.memory_save',{content:'Uses metric units throughout.',category:'fact'});
    });
    await toggleTheme(page);
    for(const name of ['Chat','Mail','Tasks','Projects','Memory','Agent']){
      await openSpace(page,name);
      await page.waitForTimeout(700);
      await page.screenshot({path:path.join(evidence,`light-${name.toLowerCase()}-1440.png`)});
    }
    await page.getByRole('button',{name:'OLIVE activity',exact:true}).click();
    await page.waitForTimeout(400);
    await page.screenshot({path:path.join(evidence,'light-activity-1440.png')});
  } finally {await app.close();}
});
