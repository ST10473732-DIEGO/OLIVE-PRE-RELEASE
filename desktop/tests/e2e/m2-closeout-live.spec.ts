import {test, expect, _electron as electron} from '@playwright/test';
import path from 'node:path';
import {mkdtemp, mkdir, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';

test('M2 close-out actual Agent front door and bounded public Research', async () => {
  test.skip(process.env.OLIVE_M2_LIVE !== '1', 'Opt-in local inference and one public documentation page.');
  test.setTimeout(420000);
  const root = path.resolve('..');
  const profile = await mkdtemp(path.join(tmpdir(), 'olive-m2-live-'));
  const seed = spawnSync(path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'), [path.join(root,'scripts/seed_m2_live_workspace.py'), profile], {cwd:root,encoding:'utf8'});
  expect(seed.status, seed.stderr).toBe(0);
  const evidence = path.join(root,'artifacts/ui-review/M2-closeout');
  await mkdir(evidence,{recursive:true});
  const app = await electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile}});
  try {
    const page = await app.firstWindow();
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await expect.poll(()=>page.evaluate(async()=>!(await window.olive.call('runtime.snapshot',{}) as {initializing:boolean}).initializing),{timeout:30000}).toBe(true);
    const timings: {ms:number;topic:string;stage?:string}[] = [];
    let started = performance.now();
    await page.exposeFunction('acceptanceTiming',(topic:string,stage?:string)=>timings.push({ms:performance.now()-started,topic,stage}));
    await page.evaluate(()=>window.olive.subscribe(e=>{
      if (['interaction_activity','chat_stream','agent','research','run'].includes(e.topic)) {
        const d=e.data as {message?:string;activity?:string};
        void (window as unknown as {acceptanceTiming:(topic:string,stage?:string)=>Promise<void>}).acceptanceTiming(e.topic,d.message||d.activity);
      }
    }));
    const go=async(name:string)=>{await page.getByRole('button',{name:'Find anything',exact:true}).click();await page.getByRole('button',{name:`Open ${name}`,exact:true}).click();};
    await go('Agent');
    await page.getByRole('combobox',{name:'Agent workspace'}).selectOption({label:'Isolated live acceptance'});
    await page.getByRole('textbox',{name:'Agent objective'}).fill('Run the existing automated tests in my selected workspace. Do not edit any files.');
    started=performance.now();
    await page.getByRole('button',{name:'Start objective',exact:true,includeHidden:true}).click();
    await expect(page.getByRole('button',{name:'Cancel current request',exact:true})).toBeVisible();
    const acknowledgementMs=performance.now()-started;
    // Only this explicitly authorised temporary validation may be approved.
    const deadline=Date.now()+180000;
    while (!(await page.getByRole('button',{name:'Start objective',exact:true,includeHidden:true}).isEnabled()) && Date.now()<deadline) {
      const approval=page.getByRole('dialog');
      if (await approval.isVisible()) {
        const summary=await approval.innerText();
        expect(summary).toContain('Run the detected project checks');
        expect(summary).toContain('local-acceptance');
        await page.screenshot({path:path.join(evidence,'agent-live-local-approval.png')});
        await approval.getByRole('button',{name:'Approve this action',exact:true}).click();
      }
      await page.waitForTimeout(200);
    }
    await expect(page.getByRole('button',{name:'Start objective',exact:true,includeHidden:true})).toBeEnabled({timeout:180000});
    const agent = await page.evaluate(async()=>({history:await window.olive.call('agent.history',{}),snapshot:await window.olive.call('runtime.snapshot',{})}));
    await page.getByRole('button',{name:/Run project checks in Isolated live acceptance/}).click();
    await page.screenshot({path:path.join(evidence,'agent-live-local-result.png')});
    await writeFile(path.join(evidence,'agent-live-local.json'),JSON.stringify({classification:'live local; real NLO, no injected results',acknowledgementMs,timings,agent},null,2));
    await go('Studio');
    await page.getByRole('treeitem',{name:'main.py',exact:true}).click();
    await page.screenshot({path:path.join(evidence,'agent-live-validation-output.png')});
    await go('Research');
    timings.length=0; started=performance.now();
    await page.getByRole('textbox',{name:'Research question'}).fill('Read only https://docs.python.org/3/library/unittest.html and explain what assertEqual checks. Use this public documentation as the sole source. site:docs.python.org');
    await page.getByRole('button',{name:'Start research',exact:true,includeHidden:true}).click();
    const researchDeadline=Date.now()+210000;
    while (!(await page.getByRole('button',{name:'Start research',exact:true,includeHidden:true}).isEnabled()) && Date.now()<researchDeadline) {
      const approval=page.getByRole('dialog');
      if (await approval.isVisible()) {
        const summary=await approval.innerText();
        expect(summary).toContain('https://docs.python.org/3/library/unittest.html');
        await page.screenshot({path:path.join(evidence,'research-live-public-approval.png')});
        await approval.getByRole('button',{name:'Approve this action',exact:true}).click();
      }
      await page.waitForTimeout(200);
    }
    await expect(page.getByRole('button',{name:'Start research',exact:true,includeHidden:true})).toBeEnabled({timeout:210000});
    const history=await page.evaluate(()=>window.olive.call('research.history',{})) as {id:string}[];
    const research=history[0] ? await page.evaluate(id=>window.olive.call('research.get',{session_id:id}),history[0].id) : null;
    await page.screenshot({path:path.join(evidence,'research-live-public-result.png')});
    await writeFile(path.join(evidence,'research-live-public.json'),JSON.stringify({classification:'live external attempt; inspect source/evidence state for outcome',timings,research},null,2));
  } finally {await app.close();}
});
