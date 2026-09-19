import {test,expect,_electron as electron} from '@playwright/test';
import {mkdtemp,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {captureOwnedWindow} from './native-capture';
import {openSpace} from './shell';
import type {BrowserState} from '../../electron/browser';

test('real public Google search from OLIVE GO address text',async()=>{
  test.skip(process.env.OLIVE_LIVE_WEB!=='1','Explicit public-network acceptance');test.setTimeout(90000);
  const profile=await mkdtemp(path.join(tmpdir(),'olive-browser-public-'));
  const app=await electron.launch({chromiumSandbox:true,args:[path.resolve('.'),...(process.platform==='linux'?['--ozone-platform=wayland']:[])],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  try {
    const page=await app.firstWindow();await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();await openSpace(page,'OLIVE GO');
    await page.locator('.go-ntp input').fill('Python official documentation math sqrt');await page.locator('.go-ntp input').press('Enter');
    const state=()=>page.evaluate(()=>window.olive.browser({action:'state'})) as Promise<BrowserState>;
    await expect.poll(async()=>(await state()).tabs[0]?.url,{timeout:30000}).toContain('https://www.google.com/search?q=Python%20official%20documentation%20math%20sqrt');
    await expect.poll(()=>app.evaluate(({webContents})=>webContents.getAllWebContents().some(w=>/^https:\/\/(www|consent)\.google\.com\//.test(w.getURL())&&!w.isLoading())),{timeout:30000}).toBe(true);
    expect((await state()).tabs[0].error).toBe('');
    const actual=await app.evaluate(async({webContents})=>webContents.getAllWebContents().find(w=>/^https:\/\/(www|consent)\.google\.com\//.test(w.getURL()))!.executeJavaScript('document.body.innerText'));
    expect(String(actual).toLowerCase()).toContain('google');
    const evidence=path.resolve('../artifacts/core/functionality/browser');await mkdir(evidence,{recursive:true});
    await captureOwnedWindow(page,app,path.join(evidence,'google-native.png'));
    console.log('Public Google document loaded; provider response may include regional consent or bot checks. Actual page captured.');
  }finally{
    const page=await app.firstWindow();console.log('Public navigation outcome',(await page.evaluate(()=>window.olive.browser({action:'state'})) as BrowserState).tabs.map(({url,title,error})=>({url,title,error})));
    await app.close();
  }
});
