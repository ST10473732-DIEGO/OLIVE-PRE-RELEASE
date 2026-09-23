import {test,expect,_electron as electron} from '@playwright/test';
import {createServer} from 'node:http';
import {mkdtemp,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {openSpace} from './shell';

test('native find remains correct during initial layout and menu visibility',async()=>{
  test.setTimeout(120000);
  const profile=await mkdtemp(path.join(tmpdir(),'olive-find-trace-'));
  const server=createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end('<title>Owned native find</title><h1>Olive evidence</h1><p>Olive searchable text.</p>');});
  await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
  const base=`http://127.0.0.1:${(server.address() as {port:number}).port}`;
  const app=await electron.launch({args:[path.resolve('.'),'--ozone-platform=wayland'],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  type Trace={kind:string;id:number;matches?:number;final?:boolean;text?:string;findNext?:boolean};
  try{
    const page=await app.firstWindow();
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await openSpace(page,'OLIVE GO');
    await page.locator('.go-ntp input').fill(base+'/first');await page.locator('.go-ntp input').press('Enter');
    await expect.poll(()=>app.evaluate(({webContents},url)=>webContents.getAllWebContents().some(w=>w.getURL().startsWith(url)&&!w.isLoading()),base)).toBe(true);
    await app.evaluate(({webContents},url)=>{
      const wc=webContents.getAllWebContents().find(w=>w.getURL().startsWith(url))!;
      const state=globalThis as unknown as {findTrace:Trace[]};state.findTrace=[];
      wc.on('found-in-page',(_event,result)=>state.findTrace.push({kind:'result',id:result.requestId,matches:result.matches,final:result.finalUpdate}));
      const original=wc.findInPage.bind(wc);
      wc.findInPage=(text,options)=>{const id=original(text,options);state.findTrace.push({kind:'request',id,text,findNext:options?.findNext});return id;};
    },base);
    const state=await page.evaluate(()=>window.olive.browser({action:'state'})) as {active:string};
    const id=state.active;
    // Fixed trials, no retry-until-green. Native completion events are the clock.
    for(const hidden of [false,true]){
      if(hidden) await page.getByRole('button',{name:'OLIVE GO menu',exact:true}).click();
      for(let trial=0;trial<10;trial++){
        await page.evaluate(id=>window.olive.browser({action:'find',id,text:''}),id);
        await page.evaluate(id=>window.olive.browser({action:'find',id,text:'NoSuchFixtureText'}),id);
        await page.evaluate(id=>window.olive.browser({action:'find',id,text:'Olive'}),id);
        await expect.poll(()=>app.evaluate(()=>{
          const trace=(globalThis as unknown as {findTrace:Trace[]}).findTrace;
          const last=trace.filter(e=>e.kind==='request').at(-1)!;
          return trace.some(e=>e.kind==='result'&&e.id===last.id&&e.final);
        })).toBe(true);
      }
    }
    const trace=await app.evaluate(()=>(globalThis as unknown as {findTrace:Trace[]}).findTrace);
    await writeFile(path.join(profile,'native-find-trace.json'),JSON.stringify(trace,null,2));
    console.log('Owned find trace:',path.join(profile,'native-find-trace.json'));
    const finalRequests=trace.filter(e=>e.kind==='request'&&e.text==='Olive');
    const zero=finalRequests.filter(q=>trace.some(e=>e.kind==='result'&&e.id===q.id&&e.final&&e.matches===0));
    console.log(JSON.stringify({trials:finalRequests.length,finalZero:zero.length,events:trace.length}));
    expect(finalRequests).toHaveLength(20);
    expect(zero).toHaveLength(0);
  }finally{await app.close();await new Promise<void>(r=>server.close(()=>r()));}
});
