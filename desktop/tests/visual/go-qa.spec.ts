import {test, expect, _electron as electron} from '@playwright/test';
import {createServer} from 'node:http';
import path from 'node:path';
import {mkdtemp, mkdir, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {openSpace} from '../e2e/shell';
import type {BrowserState} from '../../electron/browser';

// OLIVE GO rendered-screen QA against docs/design/olive-go-artifact.html:
// every screen the reference draws, at the widths the brief names, in both
// themes, measured for sideways overflow and clipped labels as well as captured.
const WIDTHS:[number,number][]=[[1920,1080],[1440,900],[1366,768],[1100,760]];

test('OLIVE GO visual QA', async()=>{
  test.setTimeout(600000);
  const root=path.resolve('..');
  const evidence=path.join(root,'artifacts/core/functionality/olive-go/qa');
  await mkdir(evidence,{recursive:true});
  const profile=await mkdtemp(path.join(tmpdir(),'olive-go-qa-'));
  const server=createServer((req,res)=>{
    if(req.url==='/favicon.ico'){res.writeHead(200,{'Content-Type':'image/png'});res.end(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAdElEQVR4nGNgoBAw4pKIqpD7j8xf1vEIq1pGQhrRAbpBjMRqztvABWdb3LgB18dEqmYQOKGh8R/DAHIBEzH+xgZgepiIUTwp4BtOPguxNqIbQt0wWIYjkeADMD1MVHEBA4muQFaL4gJiDMGblJEBsZmJYgAAljssFUhmEWsAAAAASUVORK5CYII=','base64'));return;}
    if(req.url==='/slow'){setTimeout(()=>{res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end('<title>Slow fixture</title><h1>Slow</h1>');},4000);return;}
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
    const name=(req.url||'/').replace(/\W/g,' ').trim()||'home';
    res.end(`<!doctype html><title>Fixture ${name} — a deliberately long page title for the tab strip</title><link rel="icon" href="/favicon.ico"><body style="font:16px system-ui;padding:40px;color:#222"><h1>Fixture page ${name}</h1><p>Synthetic local content for OLIVE GO QA.</p><a href="/two">Two</a> <a href="/three">Three</a></body>`);
  });
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${(server.address() as {port:number}).port}`;
  const app=await electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  const errors:string[]=[];
  const findings:Record<string,unknown>[]=[];
  try {
    const page=await app.firstWindow();
    page.setDefaultTimeout(30000);
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error')errors.push('console: '+m.text());});
    const size=async(w:number,h:number)=>{await app.evaluate(({BrowserWindow},s)=>BrowserWindow.getAllWindows()[0].setContentSize(s[0],s[1]),[w,h]);await page.waitForTimeout(500);};
    const shot=async(name:string)=>{await page.waitForTimeout(350);await page.screenshot({path:path.join(evidence,`${name}.png`)});};
    const measure=async(label:string)=>{
      const result=await page.evaluate(()=>{
        const doc=document.documentElement, width=doc.clientWidth;
        const clipped:string[]=[], outside:string[]=[];
        for(const node of Array.from(document.querySelectorAll<HTMLElement>('.go-tab, .go-ib, .go-field, .go-chip, .go-tile, .go-row, .go-btn, .go-seg button, .go-panel-head h2'))){
          const style=getComputedStyle(node); if(style.display==='none'||style.visibility==='hidden')continue;
          const box=node.getBoundingClientRect(); if(!box.width && !box.height)continue;
          if(box.right>width+1||box.left<-1) outside.push(`${node.className.split(' ')[0]}:${node.innerText.slice(0,24)}`);
          if(style.textOverflow==='ellipsis' && node.scrollWidth>node.clientWidth+1 && !node.classList.contains('go-tab-title')) clipped.push(`${node.className.split(' ')[0]}:${node.innerText.slice(0,24)}`);
        }
        const go=document.querySelector('.go');
        return {sideways:doc.scrollWidth>doc.clientWidth, goSideways:!!go && go.scrollWidth>go.clientWidth+1, outside, clipped, width, field:(document.querySelector('.go-field') as HTMLElement|null)?.getBoundingClientRect().width||0};
      });
      findings.push({screen:label,...result});
      expect(result.sideways,`${label}: window must not scroll sideways`).toBe(false);
      expect(result.outside,`${label}: controls outside the window`).toEqual([]);
      return result;
    };
    const state=()=>page.evaluate(()=>window.olive.browser({action:'state'})) as Promise<BrowserState>;
    const go=page.locator('.go');
    const address=async(text:string)=>{
      await page.locator('.go-field .go-field-display').click();
      const input=page.locator('.go-field input');
      await input.fill(text);await input.press('Enter');
    };
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await size(1440,900);
    await openSpace(page,'OLIVE GO');
    await expect(go).toBeVisible();
    await expect(page.locator('.go-ntp .go-wordmark')).toHaveText('OLIVE GO');
    await shot('01-newtab-fresh-1440');
    await measure('fresh new tab 1440');
    // Fresh profile: one Add tile + four dashed placeholders, no recent, no invented sites.
    await expect(page.locator('.go-favs .box.add')).toHaveCount(1);
    await expect(page.locator('.go-favs .box.empty')).toHaveCount(4);
    await expect(page.locator('.go-recent')).toHaveCount(0);
    expect((await state()).bookmarks).toEqual([]);

    // Populate: visit pages, save favourites, so populated states are real records.
    for(const p of ['/one','/two','/three']){await address(base+p);await expect.poll(async()=>{const s=await state();return s.tabs.find(t=>t.id===s.active)?.url;}).toBe(base+p);await expect.poll(async()=>{const s=await state();return s.tabs.find(t=>t.id===s.active)?.loading;}).toBe(false);}
    await page.getByRole('button',{name:'Add to favourites',exact:true}).click();
    await expect(page.locator('.go-toast')).toContainText('Saved to favourites');
    await shot('02-active-page-saved-1440');
    await measure('active page 1440');
    await page.locator('.go-field .go-field-display').click();
    const input=page.locator('.go-field input');
    await input.fill('fixture');
    await expect(page.locator('.go-suggest')).toBeVisible();
    await shot('03-suggestions-1440');
    await measure('suggestions 1440');
    await input.press('Escape');
    // Multiple tabs incl. pinned and a loading one.
    await page.getByRole('button',{name:'New tab',exact:true}).click();
    await expect(page.locator('.go-ntp')).toBeVisible();
    await shot('04-newtab-populated-1440');
    await measure('populated new tab 1440');
    await expect(page.locator('.go-recent .go-row')).toHaveCount(3);
    await expect(page.locator('.go-favs .box.add')).toHaveCount(1);
    await expect(page.locator('.go-favs .box.empty')).toHaveCount(3);
    const tabs=page.getByRole('tab');
    await tabs.first().click({button:'right'});
    await page.getByRole('menuitem',{name:'Pin',exact:true}).click();
    await expect(page.locator('.go-tab.pinned')).toHaveCount(1);
    await page.locator('.go-ntp input').fill(base+'/slow');await page.locator('.go-ntp input').press('Enter');
    await expect(page.locator('.go-tab.loading')).toHaveCount(1);
    await expect(page.locator('.go-progress')).toBeVisible();
    await shot('05-tabs-loading-1440');
    await expect.poll(async()=>{const s=await state();return s.tabs.find(t=>t.id===s.active)?.loading;},{timeout:20000}).toBe(false);
    // The menu floats over a still of the page; no blank band appears above the page.
    await page.getByRole('button',{name:'OLIVE GO menu',exact:true}).click();
    await expect(page.locator('.go-snapshot')).toBeVisible();
    await shot('05b-menu-over-page-1440');
    await page.keyboard.press('Escape');
    await expect(page.locator('.go-snapshot')).toHaveCount(0);
    // Side panels.
    await page.getByRole('button',{name:'OLIVE GO menu',exact:true}).click();
    await page.getByRole('menuitem',{name:/History/}).click();
    await expect(page.locator('.go-panel')).toBeVisible();
    await shot('06-panel-history-1440');
    await measure('history panel 1440');
    await page.getByRole('tab',{name:'Favourites',exact:true}).click();
    await shot('07-panel-favourites-1440');
    await page.getByRole('tab',{name:'Downloads',exact:true}).click();
    await shot('08-panel-downloads-empty-1440');
    await page.getByRole('button',{name:'Close panel',exact:true}).click();
    // Customise from the new tab page.
    await page.getByRole('button',{name:'New tab',exact:true}).click();
    await page.getByRole('button',{name:'Customise',exact:true}).click();
    await expect(page.locator('.go-panel')).toContainText('Search engine');
    await expect(page.getByRole('radio')).toHaveCount(6);
    await shot('09-customize-1440');
    await measure('customize 1440');
    await page.getByRole('switch',{name:'Recent',exact:true}).click();
    await expect(page.locator('.go-recent')).toHaveCount(0);
    await page.getByRole('switch',{name:'Recent',exact:true}).click();
    await expect(page.locator('.go-recent')).toBeVisible();
    await page.getByRole('button',{name:'Close panel',exact:true}).click();
    // Clear popover and a private tab.
    await page.getByRole('button',{name:'Clear',exact:true}).click();
    await shot('10-clear-popover-1440');
    await page.getByRole('menuitem',{name:/New private tab/}).click();
    await expect(page.locator('.go.private')).toBeVisible();
    await expect(page.locator('.go-private-pill')).toBeVisible();
    await shot('11-private-newtab-1440');
    await measure('private new tab 1440');
    await page.locator('.go-ntp input').fill(base+'/private');await page.locator('.go-ntp input').press('Enter');
    await expect.poll(async()=>{const s=await state();return s.tabs.find(t=>t.id===s.active)?.url;}).toBe(base+'/private');
    await shot('12-private-page-1440');
    expect((await state()).history.some(h=>h.url.includes('/private'))).toBe(false);
    // Error page.
    await address('http://nonexistent.invalid/page');
    await expect(page.locator('.go-error')).toBeVisible({timeout:20000});
    await shot('13-error-1440');
    await measure('error page 1440');
    // Widths, on the populated new tab page and an active page.
    const active=(await state()).active;
    await page.evaluate(id=>window.olive.browser({action:'close',id}),active);
    for(const [w,h] of WIDTHS){
      await size(w,h);
      await page.getByRole('button',{name:'New tab',exact:true}).click();
      await expect(page.locator('.go-ntp')).toBeVisible();
      await shot(`20-newtab-${w}`);
      const m=await measure(`new tab ${w}x${h}`);
      expect(m.field,`field width at ${w}`).toBeLessThanOrEqual(940);
      const first=page.getByRole('tab').nth(1);
      await first.click();
      await expect(page.locator('.go-page.web')).toBeVisible();
      await shot(`21-page-${w}`);
      await measure(`page ${w}x${h}`);
      const activeId=(await state()).active;
      const s=await state(); const blankTab=s.tabs.find(t=>t.url==='about:blank' && t.id!==activeId);
      if(blankTab) await page.evaluate(id=>window.olive.browser({action:'close',id}),blankTab.id);
    }
    // Small window: Customise and every history entry stay reachable by ordinary scrolling.
    await size(1000,640);
    await page.getByRole('button',{name:'New tab',exact:true}).click();
    await expect(page.locator('.go-ntp')).toBeVisible();
    const customise=page.getByRole('button',{name:'Customise',exact:true});
    await customise.scrollIntoViewIfNeeded();
    await expect(customise).toBeInViewport();
    await shot('25-newtab-1000x640-scrolled');
    await measure('new tab 1000x640');
    await customise.click();
    await expect(page.locator('.go-panel')).toContainText('Search engine');
    await page.getByRole('button',{name:'Close panel',exact:true}).click();
    await page.getByRole('button',{name:'OLIVE GO menu',exact:true}).click();
    await page.getByRole('menuitem',{name:/History/}).click();
    const rows=page.locator('.go-panel-list .go-row .t');
    expect(await rows.count()).toBeGreaterThan(3);
    await rows.last().scrollIntoViewIfNeeded();
    await expect(rows.last()).toBeInViewport();
    await shot('26-history-1000x640-scrolled');
    expect(await page.evaluate(()=>{const go=document.querySelector('.go')!;return getComputedStyle(go).overflow;})).not.toBe('hidden');
    await page.getByRole('button',{name:'Close panel',exact:true}).click();
    // Light theme.
    await size(1440,900);
    await page.getByRole('button',{name:'OLIVE activity',exact:true}).click();
    await page.getByRole('button',{name:'Toggle theme',exact:true}).click();
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
    await shot('30-page-light-1440');
    await page.getByRole('button',{name:'New tab',exact:true}).click();
    await expect(page.locator('.go-ntp')).toBeVisible();
    await shot('31-newtab-light-1440');
    await measure('light new tab 1440');
    await page.getByRole('button',{name:'OLIVE GO menu',exact:true}).click();
    await page.getByRole('menuitem',{name:/History/}).click();
    await shot('32-panel-light-1440');
    await page.getByRole('button',{name:'Close panel',exact:true}).click();
    await page.getByRole('button',{name:'OLIVE activity',exact:true}).click();
    await page.getByRole('button',{name:'Toggle theme',exact:true}).click();
    await page.keyboard.press('Escape');
    // Reduced motion.
    await page.getByRole('button',{name:'OLIVE activity',exact:true}).click();
    await page.getByRole('checkbox',{name:'Reduced motion',exact:true}).check();
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'New tab',exact:true}).click();
    await page.waitForTimeout(300);
    expect(await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running' && (a.effect as KeyframeEffect)?.target && ((a.effect as KeyframeEffect).target as Element).closest('.go')).length),'reduced motion leaves no browser animation running').toBe(0);
    await writeFile(path.join(evidence,'measurements.json'),JSON.stringify({findings,errors},null,2));
    expect(errors.filter(e=>!e.includes('ERR_NAME_NOT_RESOLVED'))).toEqual([]);
  } finally {await app.close();await new Promise<void>(resolve=>server.close(()=>resolve()));}
});
