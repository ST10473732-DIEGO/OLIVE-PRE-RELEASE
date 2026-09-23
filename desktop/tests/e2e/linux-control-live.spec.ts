import {test,expect,_electron as electron} from '@playwright/test';
import path from 'node:path';
import {openSpace} from './shell';

test('owner-provisioned Linux normal Chat performs a visible browser search',async()=>{
  test.skip(process.env.OLIVE_LIVE_DESKTOP!=='1','Live acceptance uses an explicitly owner-provisioned unlocked profile');
  const app=await electron.launch({chromiumSandbox:true,args:[path.resolve('.'),'--ozone-platform=wayland'],env:{...process.env,OLIVE_LIVE_DESKTOP:'1'}});
  try{
    const page=await app.firstWindow();
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await openSpace(page,'Chat');
    await page.getByRole('button',{name:'New chat',exact:true}).first().click();
    await page.getByRole('textbox',{name:'Message OLIVE',exact:true}).fill('Open Firefox and search for KDE portal permissions documentation');
    await page.getByRole('button',{name:'Send message',exact:true}).click();
    await expect.poll(async()=>{
      const state=await page.evaluate(()=>window.olive.call('desktop.status',{})) as {session?:{status:string,verification:string}};
      if(state.session?.status==='needs-human') throw new Error(state.session.verification);
      return state.session?.status;
    },{timeout:45000}).toBe('completed');
    const state=await page.evaluate(()=>window.olive.call('desktop.status',{})) as {platform_capabilities:{last_session_evidence:{frame:{width:number,height:number},identity:{app_id:string,permission:string[],registered_on_portal_connection:boolean}}}};
    const evidence=state.platform_capabilities.last_session_evidence;
    expect(evidence.identity.app_id).toBe('local.dmdo.desktop');
    expect(evidence.identity.permission).toEqual(['yes']);
    expect(evidence.identity.registered_on_portal_connection).toBe(true);
    expect(evidence.frame.width).toBeGreaterThan(100);
    expect(evidence.frame.height).toBeGreaterThan(100);
  }finally{await app.close();}
});
