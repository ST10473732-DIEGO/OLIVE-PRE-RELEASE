import {test,expect,_electron as electron} from '@playwright/test';
import {mkdtemp,mkdir,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {openSpace} from './shell';

test('LIVE LOCAL DEEP reads a real scanned PDF page and retains native page metadata',async()=>{
  test.skip(process.env.OLIVE_LIVE_AI!=='1','Requires the installed local vision and text models');
  test.setTimeout(240000);
  const profile=await mkdtemp(path.join(tmpdir(),'olive-deep-pdf-'));
  const pdf=path.join(profile,'mixed.pdf');
  const evidence=path.resolve('../artifacts/core/functionality/deep-pdf');await mkdir(evidence,{recursive:true});
  const fixture=spawnSync(path.resolve('../.venv/Scripts/python.exe'),[path.resolve('../scripts/create_deep_pdf_fixture.py'),pdf],{windowsHide:true,encoding:'utf8'});
  expect(fixture.status,fixture.stderr).toBe(0);
  const app=await electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile}});
  try {
    const page=await app.firstWindow();await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await openSpace(page,'Chat');
    const preset=page.getByRole('combobox',{name:'OLIVE preset'});await expect(preset).toBeEnabled({timeout:30000});await preset.selectOption('deep');
    await app.evaluate(({dialog},file)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[file]});},pdf);
    await page.getByRole('button',{name:'Attach files',exact:true}).click();
    await expect(page.getByRole('button',{name:'Remove attachment mixed.pdf'})).toBeVisible();
    await expect(page.getByText('1 pages without text; ask DEEP about a specific page',{exact:false})).toBeVisible();
    const attached=await page.evaluate(async()=>{
      const value=await window.olive.call('runtime.snapshot',{}) as {chat:{id:string}};
      return window.olive.call('chat.get',{chat_id:value.chat.id});
    }) as {documents:{page_count:number;unreadable_pages:number[]}[]};
    expect(attached.documents[0]).toMatchObject({page_count:2,unreadable_pages:[2]});
    await page.getByRole('textbox',{name:'Message OLIVE',exact:true}).fill('In the attached PDF, read the image on page 2. What is the pears total? Cite that page, and do not infer other pages.');
    await page.getByRole('button',{name:'Send message',exact:true}).click();
    await expect(page.locator('.message-assistant').last()).toContainText('37',{timeout:180000});
    await expect(page.getByRole('button',{name:'Stop response',exact:true})).toBeHidden({timeout:90000});
    const snapshot=await page.evaluate(async()=>{
      const value=await window.olive.call('runtime.snapshot',{}) as {chat:{id:string}};
      return {...value,chat:await window.olive.call('chat.get',{chat_id:value.chat.id})};
    }) as {chat:{documents:{page_count:number;unreadable_pages:number[]}[];messages:unknown[]};workspaces:unknown[];runs:unknown[]};
    // Normal temporary attachments leave Chat after one response; evidence stays
    // with the answer. Do not turn this fixture into a permanent user import.
    expect(snapshot.workspaces).toHaveLength(0);expect(snapshot.runs).toHaveLength(0);
    expect(JSON.stringify(snapshot.chat.messages)).toContain('vision_interpretation:qwen3-vl:8b');
    await writeFile(path.join(evidence,'result.json'),JSON.stringify(snapshot.chat,null,2));
    await page.screenshot({path:path.join(evidence,'answer.png')});
  } finally {await app.close();}
});
