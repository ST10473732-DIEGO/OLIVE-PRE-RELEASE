import {test, expect, _electron as electron} from '@playwright/test';
import path from 'node:path';
import {mkdtemp, mkdir, readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {record} from './recording';

test('M2 direct Studio tools preserve actual output and Monaco across navigation',async()=>{
  const root=path.resolve('..');
  const profile=await mkdtemp(path.join(tmpdir(),'olive-m2-closeout-'));
  const seed=spawnSync(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/seed_m2_live_workspace.py'),profile],{cwd:root,encoding:'utf8'});
  expect(seed.status,seed.stderr).toBe(0);
  const evidence=path.join(root,'artifacts/ui-review/M2-closeout');
  await mkdir(evidence,{recursive:true});
  const app=await electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  try {
    const page=await app.firstWindow();
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    const go=async(name:string)=>{await page.getByRole('button',{name:'Find anything',exact:true}).click();await page.getByRole('button',{name:`Open ${name}`,exact:true}).click();};
    await go('Projects');
    await expect(page.getByText('No projects yet. Create a project to bring your work together.',{exact:true})).toBeVisible();
    await expect(page.getByText('Loading projects…',{exact:true})).toHaveCount(0);
    await page.screenshot({path:path.join(evidence,'projects-settled-empty.png')});
    await go('Studio');
    await page.getByRole('button',{name:'Isolated live acceptance',exact:true}).click();
    await page.getByRole('treeitem',{name:'main.py',exact:true}).click();
    const finish=await record(page,evidence,'m2-closeout-tools.mp4');
    await page.getByRole('button',{name:'Test',exact:true}).click();
    await expect(page.locator('.task-result[data-task-state="completed"]')).toBeVisible({timeout:30000});
    await expect(page.locator('.output-terminal')).toContainText('OK');
    const validationBefore=await page.evaluate(async()=>(await window.olive.call('runtime.snapshot',{}) as {validations:unknown[]}).validations);
    const channel=await page.getByRole('combobox',{name:'Output channel'}).inputValue();
    await page.screenshot({path:path.join(evidence,'studio-direct-tools.png')});
    // Structured Problems, Tests and Git are reachable both as bottom-dock
    // panels and inside the Workspace tools sheet; verify the sheet tabs here.
    for (const tool of ['Problems','Tests','Git']) {
      await page.getByText('Workspace actions',{exact:true}).click();
      await page.getByRole('button',{name:'Workspace tools',exact:true}).click();
      await page.getByRole('dialog').getByRole('button',{name:tool,exact:true}).click();
      await expect(page.getByRole('dialog').getByRole('button',{name:tool,exact:true})).toHaveClass('selected');
      if (tool === 'Tests') await expect(page.getByRole('dialog')).toContainText('test_add');
      await page.waitForTimeout(500);
      await page.screenshot({path:path.join(evidence,`studio-${tool.toLowerCase()}.png`)});
      await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();
    }
    const editor=page.getByRole('textbox',{name:'Source editor'});
    await editor.press('Control+End');await editor.press('Enter');
    await editor.pressSequentially('# Local acceptance: save retains the test output.',{delay:55});
    await page.getByRole('button',{name:'Save',exact:true}).click();
    await expect.poll(()=>readFile(path.join(profile,'local-acceptance/main.py'),'utf8')).toContain('save retains the test output');
    await expect(page.locator('.output-terminal')).toContainText('OK');
    expect(await page.evaluate(async()=>(await window.olive.call('runtime.snapshot',{}) as {validations:unknown[]}).validations)).toEqual(validationBefore);
    await expect(page.getByRole('combobox',{name:'Output channel'})).toHaveValue(channel);
    await page.screenshot({path:path.join(evidence,'studio-output-after-save.png')});
    await go('Home');await page.waitForTimeout(700);await go('Studio');
    await expect(page.locator('.monaco-editor')).toContainText('save retains the test output');
    await expect(page.locator('.output-terminal')).toContainText('OK');
    expect(await page.evaluate(async()=>(await window.olive.call('runtime.snapshot',{}) as {validations:unknown[]}).validations)).toEqual(validationBefore);
    await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1366,768));
    await page.waitForTimeout(500);
    await expect(page.getByRole('button',{name:'Show Tests',exact:true})).toBeInViewport();
    await page.screenshot({path:path.join(evidence,'studio-retained-1366.png')});
    await finish();
  } finally {await app.close();}
});
