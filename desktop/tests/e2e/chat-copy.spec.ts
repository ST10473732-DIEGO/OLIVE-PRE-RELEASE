import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace, openHistory } from "./shell";

test("Chat Copy uses the native clipboard, preserves blocks and rejects foreign callers", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-copy-"));
  const code = '\tconst greeting = "Olá <世界> & café";\n\n';
  const source = 'Owned reply.\n\n```javascript\n'+code+'```\n\n```python\nprint("second")\n```';
  const message = (content: string, incomplete = false) => ({id:crypto.randomUUID(),role:"assistant",content,
    completion_state:incomplete?"incomplete":"complete",provider:{runtime:"OLIVE Connect",preset:"fast",device_name:"Owned fixture"}});
  await writeFile(path.join(profile,"chats.json"),JSON.stringify({schema_version:2,chats:[
    {id:"copy-code",title:"Owned code copy",messages:[message(source)],created_at:"2026-09-24T00:00:00",updated_at:"2026-09-24T00:00:00"},
    {id:"copy-long",title:"Owned stopped copy",messages:[message("λ\t".repeat(100000)+"\n",true)],created_at:"2026-09-24T00:00:01",updated_at:"2026-09-24T00:00:01"},
  ]}));
  const app=await electron.launch({args:[path.resolve(".")],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:"http://127.0.0.1:1"}});
  try {
    const page=await app.firstWindow();
    await page.getByRole("button",{name:"Enter OLIVE",exact:true}).click();
    await openSpace(page,"Chat"); await openHistory(page);
    await page.locator(".conversation-items").getByRole("button",{name:"Owned code copy",exact:true}).click();
    const read=()=>app.evaluate(async({clipboard})=>await clipboard.readText());
    await page.getByRole("button",{name:"Copy javascript code",exact:true}).click();
    await expect.poll(read).toBe(code);
    const originalButton = await page.getByRole("button",{name:"Copy javascript code — copied",exact:true}).elementHandle();
    // A backend refresh rerenders Chat. It must preserve the native accessible
    // control and copied feedback rather than remount the Markdown block.
    await page.evaluate(()=>window.olive.call("chat.draft",{chat_id:"copy-code",text:"owned draft"}));
    await expect.poll(async()=>originalButton!.evaluate(node=>node.isConnected)).toBe(true);
    await expect(page.getByRole("button",{name:"Copy javascript code — copied",exact:true})).toBeVisible();
    await page.getByRole("button",{name:"Copy python code",exact:true}).click();
    await expect.poll(read).toBe('print("second")\n');
    await page.getByRole("button",{name:"Copy message",exact:true}).click();
    await expect.poll(read).toBe(source);
    // Repeated clicks on the same visible action still copy that message.
    await page.getByRole("button",{name:"Copy message — copied",exact:true}).click();
    await expect.poll(read).toBe(source);
    await page.locator(".conversation-items").getByRole("button",{name:"Owned stopped copy",exact:true}).click();
    await page.getByRole("button",{name:"Copy message",exact:true}).click();
    await expect.poll(read).toBe("λ\t".repeat(100000)+"\n");
    await expect(page.evaluate(()=>window.olive.copyText("x".repeat(2_000_001)))).rejects.toThrow();
    const foreign=await app.evaluate(async({BrowserWindow,app})=>{
      const window=new BrowserWindow({show:false,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false,
        preload:app.getAppPath()+"/out/electron/preload.cjs"}});
      try {await window.loadURL("about:blank");return await window.webContents.executeJavaScript("window.olive.copyText('foreign').then(()=> 'accepted',error=>error.message)");}
      finally {window.destroy();}
    });
    expect(foreign).toContain("Untrusted IPC sender");
    await expect.poll(read).toBe("λ\t".repeat(100000)+"\n");
    // Inject only the native API fault; click, IPC, validation and UI are real.
    await app.evaluate(({clipboard})=>{clipboard.writeText=async()=>{throw new Error("Owned clipboard failure");};});
    await page.getByRole("button",{name:/^Copy message/}).click();
    await expect(page.getByRole("alert").filter({hasText:"Could not copy"})).toBeVisible();
    await expect(page.getByRole("button",{name:"Copy message — copied",exact:true})).toHaveCount(0);
  } finally {await app.close();}
});
