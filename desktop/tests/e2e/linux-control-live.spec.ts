import {test,expect,_electron as electron} from '@playwright/test';
import {mkdtemp,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {openSpace} from './shell';

test('consented Linux desktop Stop preparation through normal UI',async()=>{
  test.skip(process.env.OLIVE_LIVE_DESKTOP!=='1','Requires explicit human approval and KDE consent');
  test.setTimeout(600000);
  const profile=await mkdtemp(path.join(tmpdir(),'olive-desktop-live-'));
  const app=await electron.launch({chromiumSandbox:true,args:[path.resolve('.'),'--ozone-platform=wayland'],env:{...process.env,OLIVE_DATA_DIR:profile}});
  try{
    const page=await app.firstWindow();
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await openSpace(page,'Desktop Control');
    await page.getByRole('button',{name:'Control permissions',exact:true}).click();
    await page.getByRole('navigation',{name:'Settings categories'}).getByRole('button',{name:'Desktop Control',exact:true}).click();
    for(const name of ['enabled','trusted tasks','screen observation']) await page.getByRole('checkbox',{name,exact:true}).check();
    await page.getByRole('combobox',{name:/^keyboard policy/}).selectOption('allow');
    await page.getByRole('combobox',{name:/^mouse policy/}).selectOption('allow');
    await page.getByRole('button',{name:'Save desktop policies',exact:true}).click();
    await expect(page.getByText('Desktop policies saved.',{exact:true})).toBeVisible();
    await openSpace(page,'Desktop Control');
    if(await page.getByRole('button',{name:'Reset Stop',exact:true}).isVisible()) await page.getByRole('button',{name:'Reset Stop',exact:true}).click();
    await page.getByRole('textbox',{name:'Desktop objective'}).fill('Open Kate');
    await page.getByRole('button',{name:'Submit objective',exact:true}).click();
    console.log('Awaiting human KDE shortcut consent. Profile:',profile);
    await expect.poll(async()=>{
      const state=await page.evaluate(()=>window.olive.call('desktop.status',{})) as {session?:{verification?:string}};
      const value=state.session?.verification||'';
      if(value&&!value.includes('Press the compositor-bound emergency shortcut')) throw new Error(value);
      return value;
    },{timeout:100000}).toContain('Press the compositor-bound emergency shortcut');
    const binding=await page.evaluate(()=>window.olive.call('desktop.status',{})) as {platform_capabilities:{shortcut_trigger:string}};
    console.log('SHORTCUT_BOUND:',binding.platform_capabilities.shortcut_trigger,'— focus another app and press this shortcut. No input/capture has started.');
    await expect.poll(async()=>{
      const state=await page.evaluate(()=>window.olive.call('desktop.status',{})) as {platform_capabilities:{global_stop_tested:boolean}};
      return state.platform_capabilities.global_stop_tested;
    },{timeout:300000}).toBe(true);
    console.log('GLOBAL_STOP_VERIFIED');
    const state=await page.evaluate(()=>window.olive.call('desktop.status',{}));
    await writeFile(path.join(profile,'stop-result.json'),JSON.stringify(state,null,2));
    // End this first acceptance phase. No automatic reset or input after Stop.
  }finally{await app.close();}
});
