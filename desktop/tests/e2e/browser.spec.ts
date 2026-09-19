import {test,expect,_electron as electron,type ElectronApplication,type Page} from '@playwright/test';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {mkdtemp,mkdir,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {openSpace} from './shell';
import {captureMail} from './m4-capture';
import type {BrowserState} from '../../electron/browser';

// OLIVE GO drives the same browser service the old Browser page did. Every
// assertion the old page had is kept; the new shell's behaviour is added.
test('OLIVE GO: real navigation, isolation, tabs, private storage, downloads, panels and restart',async()=>{
  test.setTimeout(240000);
  const profile=await mkdtemp(path.join(tmpdir(),'olive-browser-'));
  const suggestHits:string[]=[];
  const server=createServer((req,res)=>{
    if(req.url==='/download'){res.writeHead(200,{'Content-Type':'text/plain','Content-Disposition':'attachment; filename="fixture.txt"'});res.end('OLIVE synthetic browser download\n');return;}
    if(req.url?.startsWith('/suggest')){suggestHits.push(req.url);res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(['q',['fixture one','fixture two']]));return;}
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
    res.end(`<!doctype html><title>OLIVE Browser Fixture ${req.url}</title><h1>Real browser fixture</h1><p>Olive evidence on ${req.url}. Olive searchable text.</p><a href="/two">Next page</a><a href="/download">Download fixture</a><input type=password value="never-read-this"><script>document.body.dataset.bridge=typeof window.olive;document.body.dataset.node=typeof require;window.fixtureCookie=document.cookie;</script>`);
  });
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${(server.address() as {port:number}).port}`;
  let app:ElectronApplication|undefined;
  const launch=async()=>electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  // Native window captures are only permitted under the Browser evidence folder.
  const evidence=path.resolve('../artifacts/core/functionality/browser/olive-go');await mkdir(evidence,{recursive:true});
  const errors:string[]=[];
  const watch=(page:Page)=>{page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});};
  try {
    app=await launch();const page=await app.firstWindow();watch(page);
    // Count every outward fetch the main process makes, so "no request while suggestions are off" is measured, not assumed.
    await app.evaluate(({net})=>{const original=net.fetch.bind(net);(globalThis as unknown as {__fetches:number}).__fetches=0;net.fetch=((...args:Parameters<typeof net.fetch>)=>{(globalThis as unknown as {__fetches:number}).__fetches+=1;return original(...args);}) as typeof net.fetch;});
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();await openSpace(page,'OLIVE GO');
    const state=()=>page.evaluate(()=>window.olive.browser({action:'state'})) as Promise<BrowserState>;
    const activeTab=async()=>{const s=await state();return s.tabs.find(t=>t.id===s.active)!;};
    const navigate=async(url:string)=>{
      const display=page.locator('.go-field .go-field-display');
      if(await display.count()) await display.click();
      const input=page.locator('.go-field input');await input.fill(url);await input.press('Enter');
      await expect.poll(async()=>(await activeTab()).url).toBe(url);
      await expect.poll(async()=>(await activeTab()).loading).toBe(false);
    };
    // The fresh browser opens on one new tab, never an empty holder.
    await expect(page.locator('.go-ntp .go-wordmark')).toHaveText('OLIVE GO');
    expect((await state()).tabs.length).toBe(1);
    // Typing into the new tab page field navigates the same tab.
    await page.locator('.go-ntp input').fill(base+'/one');await page.locator('.go-ntp input').press('Enter');
    await expect.poll(async()=>(await activeTab()).url).toBe(base+'/one');
    const normal=(await state()).active;
    const remote=async(code:string)=>app!.evaluate(async({webContents},{base,code})=>{const wc=webContents.getAllWebContents().find(c=>c.getURL().startsWith(base));if(!wc)throw new Error('Fixture web contents missing');return wc.executeJavaScript(code);},{base,code});
    await expect.poll(()=>remote('document.body.dataset.bridge').catch(()=>null)).toBe('undefined');
    expect(await remote('document.body.dataset.node')).toBe('undefined');
    await remote('document.cookie="fixture=normal; path=/; max-age=3600"');
    const read=await page.evaluate(id=>window.olive.browser({action:'read',id}),normal) as {text:string};expect(read.text).toContain('Real browser fixture');expect(read.text).not.toContain('never-read-this');
    await remote("const hidden=document.createElement('p');hidden.style.display='none';hidden.textContent='hidden-fixture-secret';document.body.append(hidden)");
    const visible=await page.evaluate(id=>window.olive.browser({action:'read',id}),normal) as {text:string};expect(visible.text).not.toContain('hidden-fixture-secret');
    // Site badge reports the real connection state; the star saves a favourite.
    expect((await activeTab()).secure).toBe('http');
    await expect(page.getByRole('button',{name:/Connection is not encrypted/})).toBeVisible();
    await page.getByRole('button',{name:'Add to favourites',exact:true}).click();
    await expect(page.locator('.go-toast')).toContainText('Saved to favourites');
    expect((await state()).bookmarks.map(b=>b.url)).toEqual([base+'/one']);
    await navigate(base+'/two');
    await page.getByRole('button',{name:'Back',exact:true}).click();
    await expect.poll(async()=>(await activeTab()).url).toBe(base+'/one');
    await page.getByRole('button',{name:'Forward',exact:true}).click();
    await expect.poll(async()=>(await activeTab()).url).toBe(base+'/two');
    await expect.poll(async()=>(await activeTab()).loading).toBe(false);
    // History carries the real page title, not the address.
    await expect.poll(async()=>(await state()).history.find(h=>h.url===base+'/two')?.title).toContain('OLIVE Browser Fixture /two');
    await captureMail(page,app,path.join(evidence,'before-find.png'));
    // Find and zoom live in the menu.
    await page.getByRole('button',{name:'OLIVE GO menu',exact:true}).click();
    await page.getByLabel('Find in page',{exact:true}).fill('Olive');
    await expect.poll(async()=>(await activeTab()).matches).toBeGreaterThan(0);
    await page.getByRole('button',{name:'Zoom in',exact:true}).click();
    await expect.poll(async()=>(await activeTab()).zoom).toBe(1.1);
    await page.keyboard.press('Escape');
    await expect(page.locator('.go-pop')).toHaveCount(0);
    // Suggestions come from what this device knows; the engine is never asked while the setting is off.
    await page.locator('.go-field .go-field-display').click();
    await page.locator('.go-field input').fill('olive browser');
    await expect(page.locator('.go-suggest')).toBeVisible();
    // While OLIVE GO's own popover is open the page is a still of itself, so the list floats over it instead of pushing it down or leaving a blank band.
    await expect(page.locator('.go-snapshot')).toBeVisible();
    expect(await page.locator('.go-snapshot').getAttribute('src')).toMatch(/^data:image\/jpeg;base64,/);
    await expect.poll(()=>app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.some(v=>v.getVisible()))).toBe(false);
    expect(await page.evaluate(()=>{const r=document.querySelector('.go-snapshot')!.getBoundingClientRect();const h=document.querySelector('.go-page')!.getBoundingClientRect();return Math.abs(r.top-h.top)<1 && Math.abs(r.height-h.height)<1;})).toBe(true);
    await expect(page.locator('.go-suggest-row').first()).toContainText('OLIVE Browser Fixture');
    await expect(page.locator('.go-suggest-row.ai')).toContainText('Ask OLIVE about');
    await page.waitForTimeout(500);
    expect((await state()).preferences.suggestions).toBe(false);
    expect(await app.evaluate(()=>(globalThis as unknown as {__fetches:number}).__fetches||0)).toBe(0);
    await page.locator('.go-field input').press('Escape');
    await expect(page.locator('.go-snapshot')).toHaveCount(0);
    await expect.poll(()=>app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.some(v=>v.getVisible()))).toBe(true);
    // The page's own context menu is native, so it floats above the page; its items are the bounded browser operations.
    const template=await app.evaluate(async({webContents,Menu},{base})=>{
      const wc=webContents.getAllWebContents().find(c=>c.getURL().startsWith(base))!;
      const captured:{labels:string[]; clicks:Record<string,()=>void>}={labels:[],clicks:{}};
      const original=Menu.buildFromTemplate;
      (Menu as unknown as {buildFromTemplate:unknown}).buildFromTemplate=(items:Electron.MenuItemConstructorOptions[])=>{
        for(const item of items){if(item.label){captured.labels.push(item.label);if(item.click)captured.clicks[item.label]=item.click as ()=>void;}}
        return {popup:()=>undefined};
      };
      const params={x:10,y:10,linkURL:base+'/two',linkText:'Next',pageURL:wc.getURL(),frameURL:'',srcURL:base+'/pixel.png',mediaType:'image',hasImageContents:true,isEditable:false,selectionText:'Olive evidence',titleText:'',misspelledWord:'',dictionarySuggestions:[],frameCharset:'',inputFieldType:'none',spellcheckEnabled:false,menuSourceType:'mouse',mediaFlags:{},editFlags:{canUndo:false,canRedo:false,canCut:false,canCopy:true,canPaste:false,canDelete:false,canSelectAll:true,canEditRichly:false},formControlType:'none',altText:'',suggestedFilename:'',selectionRect:{x:0,y:0,width:0,height:0},selectionStartOffset:0,referrerPolicy:{url:'',policy:'default'}} as unknown as Electron.ContextMenuParams;
      wc.emit('context-menu',{},params);
      (globalThis as unknown as {__ask?:()=>void}).__ask=captured.clicks['Ask OLIVE about this selection'];
      (Menu as unknown as {buildFromTemplate:unknown}).buildFromTemplate=original;
      return captured.labels;
    },{base});
    for(const label of ['Open link in new tab','Copy link address','Save image as…','Copy image','Copy image address','Copy','Ask OLIVE about this selection','Back','Reload','Save page as…','Print…']) expect(template).toContain(label);
    expect(template.some(l=>l.startsWith('Search Google for'))).toBe(true);
    // Ask OLIVE from the menu hands the selection to Chat as quoted, untrusted text.
    await app.evaluate(()=>{(globalThis as unknown as {__ask:()=>void}).__ask();});
    await expect(page.getByRole('textbox',{name:'Message OLIVE',exact:true})).toBeVisible();
    await openSpace(page,'OLIVE GO');
    await expect.poll(async()=>(await activeTab()).url).toBe(base+'/two');
    // A failed HTTPS navigation never shows a lock: the error page carries a "no connection" badge.
    await page.locator('.go-field .go-field-display').click();
    await page.locator('.go-field input').fill('https://nonexistent.invalid/secure');await page.locator('.go-field input').press('Enter');
    await expect(page.locator('.go-error')).toBeVisible({timeout:20000});
    expect((await activeTab()).errorCode).toBe(-105);
    expect((await activeTab()).secure).toBe('none');
    await expect(page.getByRole('button',{name:/No connection to describe/})).toBeVisible();
    await expect(page.getByRole('button',{name:/encrypted connection/i})).toHaveCount(0);
    await page.getByRole('button',{name:/No connection to describe/}).click();
    await expect(page.getByRole('dialog',{name:'Site information'})).toContainText("didn't load, so there is no connection");
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'Back',exact:true}).click();
    await expect.poll(async()=>(await activeTab()).url).toBe(base+'/two');
    await expect.poll(async()=>(await activeTab()).secure).toBe('http');
    // Private tab: separate storage, no history, favourites off, tinted chrome.
    await page.getByRole('button',{name:'Clear',exact:true}).click();
    await page.getByRole('menuitem',{name:/New private tab/}).click();
    await expect(page.locator('.go.private')).toBeVisible();
    await page.locator('.go-ntp input').fill(base+'/private');await page.locator('.go-ntp input').press('Enter');
    await expect.poll(async()=>(await activeTab()).url).toBe(base+'/private');
    const privateId=(await state()).active;
    await expect.poll(()=>app!.evaluate(({webContents},url)=>webContents.getAllWebContents().some(c=>c.getURL()===url),base+'/private')).toBe(true);
    const privateCookie=await app.evaluate(async({webContents},url)=>webContents.getAllWebContents().find(c=>c.getURL()===url)!.executeJavaScript('document.cookie'),base+'/private');expect(privateCookie).toBe('');
    expect((await state()).history.some(h=>h.url.endsWith('/private'))).toBe(false);
    await expect(page.getByRole('button',{name:'Add to favourites',exact:true})).toBeDisabled();
    await page.evaluate(()=>window.olive.browser({action:'preferences',suggestions:true}));
    await page.locator('.go-field .go-field-display').click();
    await page.locator('.go-field input').fill('private query');
    await page.waitForTimeout(600);
    expect(await app.evaluate(()=>(globalThis as unknown as {__fetches:number}).__fetches||0),'a private tab never asks the engine').toBe(0);
    await page.locator('.go-field input').press('Escape');
    await page.evaluate(()=>window.olive.browser({action:'preferences',suggestions:false}));
    await captureMail(page,app,path.join(evidence,'private.png'));
    await page.evaluate(id=>window.olive.browser({action:'close',id}),privateId);
    await expect(page.locator('.go.private')).toHaveCount(0);
    expect((await state()).history.some(h=>h.url.endsWith('/private'))).toBe(false);
    // One delegated destination approval, bound to this exact fixture URL/name.
    const download=path.join(profile,'fixture.txt');
    await app.evaluate(({session},{url,destination})=>{session.fromPartition('persist:olive-browser').once('will-download',(event,item)=>{if(item.getURL()!==url || item.getFilename()!=='fixture.txt'){event.preventDefault();throw new Error('Unexpected fixture download');}item.setSavePath(destination);});},{url:base+'/download',destination:download});
    await page.evaluate(id=>window.olive.browser({action:'select',id}),normal);
    await remote(`document.querySelector('a[href="/download"]').click()`);
    await expect.poll(async()=>(await state()).downloads[0]?.state).toBe('completed');expect(await readFile(download,'utf8')).toBe('OLIVE synthetic browser download\n');
    // The Downloads panel opened itself and shows the real outcome.
    await expect(page.locator('.go-panel')).toContainText('fixture.txt');
    await expect(page.locator('.go-dl .meta')).toContainText('B');
    await captureMail(page,app,path.join(evidence,'downloads.png'));
    await page.getByRole('button',{name:'Show fixture.txt in folder'}).waitFor();
    await page.getByRole('button',{name:'Close panel',exact:true}).click();
    // Close the only normal tab: a fresh new tab appears; reopen brings the page back.
    await page.evaluate(id=>window.olive.browser({action:'close',id}),normal);
    await expect.poll(async()=>(await state()).tabs.length).toBe(1);
    await expect(page.locator('.go-ntp')).toBeVisible();
    await page.getByRole('tab').first().click({button:'right'});
    await page.getByRole('menuitem',{name:'Reopen closed tab',exact:true}).click();
    await expect.poll(async()=>(await activeTab()).url).toBe(base+'/two');
    // Pin, duplicate, reorder and close-others through the strip.
    await page.getByRole('tab').nth(1).click({button:'right'});
    await page.getByRole('menuitem',{name:'Pin',exact:true}).click();
    await expect.poll(async()=>(await state()).tabs[0]?.pinned).toBe(true);
    await page.getByRole('tab').first().click({button:'right'});
    await page.getByRole('menuitem',{name:'Duplicate',exact:true}).click();
    await expect.poll(async()=>(await state()).tabs.length).toBe(3);
    const ids=(await state()).tabs.map(t=>t.id);
    await page.evaluate(({id,index})=>window.olive.browser({action:'move',id,index}),{id:ids[2],index:1});
    expect((await state()).tabs.map(t=>t.id)).toEqual([ids[0],ids[2],ids[1]]);
    await page.getByRole('tab').nth(1).click({button:'right'});
    await page.getByRole('menuitem',{name:'Close others',exact:true}).click();
    await expect.poll(async()=>(await state()).tabs.length).toBe(2);
    expect((await state()).tabs[0].pinned).toBe(true);
    // Customise persists through the browser's own state file.
    await page.getByRole('button',{name:'OLIVE GO menu',exact:true}).click();
    await page.getByRole('menuitem',{name:'Customise',exact:true}).click();
    await expect(page.getByRole('radio')).toHaveCount(6);
    await page.getByRole('radio',{name:'DuckDuckGo',exact:true}).click();
    await page.getByRole('switch',{name:'Recent',exact:true}).click();
    await expect.poll(async()=>(await state()).preferences.engine).toBe('duckduckgo');
    expect((await state()).preferences.sections.recent).toBe(false);
    await page.getByRole('button',{name:'Close panel',exact:true}).click();
    // Clear browsing data touches only normal history and cookies; favourites stay.
    await page.getByRole('button',{name:'Clear',exact:true}).click();
    await page.getByRole('menuitem',{name:/Clear browsing data/}).click();
    await page.getByRole('button',{name:'Clear',exact:true}).last().click();
    await expect.poll(async()=>(await state()).history.length).toBe(0);
    expect((await state()).bookmarks.map(b=>b.url)).toEqual([base+'/one']);
    await expect.poll(()=>remote('document.cookie').catch(()=>'')).toBe('');
    await navigate(base+'/two');await remote('document.cookie="fixture=again; path=/; max-age=3600"');await captureMail(page,app,path.join(evidence,'normal.png'));
    await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].focus());
    const capture=spawn(path.resolve('../.venv/Scripts/python.exe'),[path.resolve('../scripts/capture_fixture_window.py'),'--pid',String(await app.evaluate(()=>process.pid)),'--output',path.join(evidence,'native-window.png')],{windowsHide:true});
    capture.stderr.on('data',value=>console.log(String(value)));
    await expect.poll(()=>capture.exitCode).toBe(0);
    await page.getByRole('button',{name:'Find anything',exact:true}).click();
    // App modal is real; compositor capture must show no native page over it.
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect.poll(()=>app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.some(v=>v.getVisible()))).toBe(false);
    await captureMail(page,app,path.join(evidence,'modal.png'));await page.keyboard.press('Escape');
    await expect.poll(()=>app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.some(v=>v.getVisible()))).toBe(true);
    // A side panel keeps the page visible beside it, narrower by the panel.
    const before=await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.find(v=>v.getVisible())!.getBounds());
    await page.getByRole('button',{name:'OLIVE GO menu',exact:true}).click();
    await page.getByRole('menuitem',{name:/History/}).click();
    await expect.poll(()=>app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.find(v=>v.getVisible())?.getBounds().width||0)).toBeLessThan(before.width-200);
    await expect.poll(()=>app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.some(v=>v.getVisible()))).toBe(true);
    await page.getByRole('button',{name:'Close panel',exact:true}).click();
    // Leaving for Studio hides the page and back again restores it, without a request flood.
    const errorsBefore=errors.length;
    await openSpace(page,'Studio');
    await expect.poll(()=>app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.some(v=>v.getVisible()))).toBe(false);
    await page.waitForTimeout(1500);
    await openSpace(page,'OLIVE GO');
    await expect.poll(()=>app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.some(v=>v.getVisible()))).toBe(true);
    await expect.poll(async()=>(await activeTab()).url).toBe(base+'/two');
    await page.waitForTimeout(1500);
    expect(errors.slice(errorsBefore)).toEqual([]);
    // A layout measured a frame before a resize finishes overshoots the window; it is clamped, never rejected with a toast.
    const oversized=await page.evaluate(()=>window.olive.browser({action:'layout',visible:true,bounds:{x:200,y:90,width:5000,height:5000}}).then(()=>'ok',e=>String(e)));
    expect(oversized).toBe('ok');
    const clamped=await app.evaluate(({BrowserWindow})=>{const w=BrowserWindow.getAllWindows()[0];const [cw,ch]=w.getContentSize();const b=w.contentView.children.find(v=>v.getVisible())!.getBounds();return b.x+b.width<=cw && b.y+b.height<=ch && b.y>=40;});
    expect(clamped).toBe(true);
    await expect(page.locator('.toast, [role="alert"]').filter({hasText:'content area'})).toHaveCount(0);
    // Interface scaling: the native view follows the scaled holder exactly, and nothing errors.
    await page.evaluate(()=>window.olive.setInterfaceScale(1.25));
    await expect.poll(async()=>{
      const holder=await page.evaluate(()=>{const r=document.querySelector('.go-page')!.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};});
      const view=await app!.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].contentView.children.find(v=>v.getVisible())?.getBounds());
      return view && Math.abs(view.x-holder.x*1.25)<=2 && Math.abs(view.y-holder.y*1.25)<=2 && Math.abs(view.width-holder.width*1.25)<=3;
    }).toBe(true);
    await page.evaluate(()=>window.olive.setInterfaceScale(1));
    await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1000,720));await captureMail(page,app,path.join(evidence,'small.png'));
    const smallCapture=spawn(path.resolve('../.venv/Scripts/python.exe'),[path.resolve('../scripts/capture_fixture_window.py'),'--pid',String(await app.evaluate(()=>process.pid)),'--output',path.join(evidence,'small-native.png')],{windowsHide:true});
    await expect.poll(()=>smallCapture.exitCode).toBe(0);
    // Restart: tabs, pinned state, the active tab and preferences come back; nothing replays.
    await app.close();app=await launch();const reopened=await app.firstWindow();watch(reopened);await reopened.getByRole('button',{name:'Enter OLIVE',exact:true}).click();await openSpace(reopened,'OLIVE GO');
    const restored=()=>reopened.evaluate(()=>window.olive.browser({action:'state'})) as Promise<BrowserState>;
    await expect.poll(async()=>(await restored()).tabs.map(t=>t.url)).toEqual([base+'/two',base+'/two']);
    expect((await restored()).tabs[0].pinned).toBe(true);
    expect((await restored()).preferences.engine).toBe('duckduckgo');
    expect((await restored()).downloads).toEqual([]);
    await expect.poll(()=>app!.evaluate(async({webContents},url)=>webContents.getAllWebContents().find(c=>c.getURL()===url)?.executeJavaScript('document.cookie'),base+'/two')).toContain('fixture=again');
    expect(suggestHits).toEqual([]);
    expect(errors).toEqual([]);
  } finally {if(app)await app.close();await new Promise<void>(resolve=>server.close(()=>resolve()));}
});
