// Controlled synthetic corpus; real Electron reads/UI. No transport or approval injection.
const { _electron: electron, expect } = require('../desktop/node_modules/@playwright/test');
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {execFileSync}=require('node:child_process');
(async()=>{
 const root=path.resolve(__dirname,'..'),profile=await fs.mkdtemp(path.join(os.tmpdir(),'olive-m4-render-review-'));
 const evidence=path.join(root,'artifacts/ui-review/M4/render-review');await fs.mkdir(evidence,{recursive:true});
 const seed=`from pathlib import Path
import sys
from email.message import EmailMessage
from olive.mail.store import MailStore
from olive.mail.local import LocalMail
p=Path(sys.argv[1]);assert p.name.startswith('olive-m4-render-review-')
mail=LocalMail(MailStore(p/'mail.sqlite3'))
for i in range(200):
 m=EmailMessage();m['From']='fixture@example.invalid';m['To']='reader@example.invalid';m['Subject']=f'Bounded fixture {i:03}';m['Message-ID']=f'<bounded-{i}@example.invalid>'
 if i and i<35:m['In-Reply-To']='<bounded-0@example.invalid>'
 m.set_content('Synthetic local corpus. No private data. '+('Readable fixture content. '*60))
 mail.ingest(m.as_bytes(),source=f'fixture:{i}')
`;
 execFileSync(path.join(root,'.venv/Scripts/python.exe'),['-c',seed,profile],{cwd:root,windowsHide:true});
 const app=await electron.launch({args:[path.join(root,'desktop')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
 const results={classification:'Controlled 200-message fixture corpus, actual Electron/Python reads and rendered UI; no network/vault write',profile,timings:{}};
 try{
 const page=await app.firstWindow();await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1440,920));
 const capture=async name=>{await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));const png=await app.evaluate(async({BrowserWindow})=>(await BrowserWindow.getAllWindows()[0].capturePage()).toPNG().toString('base64'));await fs.writeFile(path.join(evidence,name+'.png'),Buffer.from(png,'base64'));};
 await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
 await page.getByRole('button',{name:'Command palette',exact:true}).click();const began=Date.now();
 await page.getByRole('button',{name:'Open Mail',exact:true}).click();await expect(page.locator('.mail-list-item')).toHaveCount(50);results.timings.open_populated_ms=Date.now()-began;
 await capture('populated');
 const queryStart=Date.now();await page.getByPlaceholder('Search local mail',{exact:true}).fill('Bounded fixture 00');await expect(page.locator('.mail-list-item')).toHaveCount(10);results.timings.search_to_render_ms=Date.now()-queryStart;
 await page.locator('.mail-list-item').first().click();await expect(page.locator('.mail-thread summary')).toContainText('35 related messages');
 const threadStart=Date.now();await page.locator('.mail-thread summary').click();await expect(page.locator('.mail-thread button')).toHaveCount(30);results.timings.bounded_thread_open_ms=Date.now()-threadStart;
 await capture('bounded-thread');
 await page.evaluate(()=>window.olive.call('mail.connection_save',{body:{name:'M4 masked entry fixture',sender:'sender@example.invalid',username:'fixture',smtp:{host:'127.0.0.1',port:9,tls:'tls'}}}));
 await page.getByRole('button',{name:'Mail connections',exact:true}).click();await page.getByRole('button',{name:'Store credentials',exact:true}).click();
 const secret=page.getByLabel('Password or app password',{exact:true});await expect(secret).toHaveAttribute('type','password');await secret.fill('dummy-never-stored');await capture('masked-credential-entry');await secret.fill('');
 results.credential_stored=false;results.rendered_list_bound=50;results.rendered_thread_bound=30;
 }catch(e){results.primary_error=String(e);throw e;}
 finally{await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify(results,null,2));await app.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
