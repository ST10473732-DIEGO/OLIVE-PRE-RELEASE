import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";

test("OLIVE canonical shell preserves legacy profile and renderer state across restart", async () => {
  test.setTimeout(150000);
  const fixture = await mkdtemp(path.join(tmpdir(), "olive-rebrand-"));
  const profile = path.join(fixture, ".dmdo");
  const evidence = path.resolve("../artifacts/rebrand/screens");
  await mkdir(evidence, {recursive: true});
  const env: Record<string,string> = Object.fromEntries(Object.entries(process.env).filter((entry): entry is [string,string] => entry[1] !== undefined));
  // Exercise only the supported old configuration spelling, never the real profile.
  for (const key of Object.keys(env)) if (key.startsWith("DMDO_") || key.startsWith("OLIVE_")) delete env[key];
  env.DMDO_DATA_DIR = profile;
  env.DMDO_OLLAMA_HOST = "http://127.0.0.1:1";
  const launch = () => electron.launch({args:[path.resolve(".")], env});
  let app = await launch();
  try {
    let page = await app.firstWindow();
    await app.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].setSize(1440,920));
    await expect(page.getByRole("button", {name:"Enter OLIVE",exact:true})).toBeVisible();
    expect(await page.title()).toBe("OLIVE");
    expect(await page.evaluate(() => typeof window.olive.call)).toBe("function");
    expect(await page.evaluate(() => "dmdo" in window)).toBe(false);
    const paths = await app.evaluate(({app}) => ({name:app.getName(), user:app.getPath("userData"), session:app.getPath("sessionData")}));
    expect(paths).toEqual({name:"OLIVE",user:path.join(profile,"electron-shell"),session:path.join(profile,"electron-shell")});
    await page.screenshot({path:path.join(evidence,"welcome.png")});
    await page.getByRole("button", {name:"Enter OLIVE",exact:true}).click();
    await expect.poll(() => page.evaluate(async () => (await window.olive.call("runtime.snapshot",{}) as {initializing:boolean}).initializing)).toBe(false);
    const saved = await page.evaluate(async () => {
      localStorage.setItem("rebrandFixture", "legacy-origin-state");
      const contact = await window.olive.call("contacts.create", {body:{display_name:"Synthetic continuity contact"}}) as {id:string};
      const profile = await window.olive.call("profile.get",{}) as {id:string};
      return {contact:contact.id,profile:profile.id};
    });
    const go = async (name:string) => {
      await page.getByRole("button",{name:"Find anything",exact:true}).click();
      await page.getByRole("button",{name:"Open " + name,exact:true}).click();
      if (name === "Home") await expect(page.getByRole("textbox",{name:"Ask OLIVE anything",exact:true})).toBeVisible();
      else if (name === "Chat") await expect(page.getByRole("textbox",{name:"Message OLIVE",exact:true})).toBeVisible();
      else if (name === "Studio") await expect(page.getByRole("heading",{name:"Your next idea starts here.",exact:true})).toBeVisible();
      else await expect(page.getByRole("heading",{name,exact:true}).first()).toBeVisible();
      await page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all(document.getAnimations().filter(a => Number.isFinite(a.effect?.getComputedTiming().endTime)).map(a => a.finished.catch(() => undefined)));
        await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
      });
      expect(await page.locator("body").innerText()).not.toMatch(/\bDMDO\b/);
      await page.screenshot({path:path.join(evidence,name.toLowerCase().replaceAll(" ","-")+".png")});
    };
    for (const name of ["Home","Chat","Studio","Agent","Settings","Calendar","Tasks","Reminders"]) await go(name);
    await app.close();
    app = await launch();
    page = await app.firstWindow();
    await page.getByRole("button",{name:"Enter OLIVE",exact:true}).click();
    expect(await page.evaluate(() => localStorage.getItem("rebrandFixture"))).toBe("legacy-origin-state");
    expect(await page.evaluate(id => window.olive.call("contacts.get",{record_id:id}),saved.contact)).toMatchObject({id:saved.contact,display_name:"Synthetic continuity contact"});
    expect(await page.evaluate(() => window.olive.call("profile.get",{}))).toMatchObject({id:saved.profile});
    await writeFile(path.join(evidence,"continuity.json"),JSON.stringify({classification:"live local Electron/Python; synthetic records", paths, saved, restarted:true, legacyEnvironment:true, rendererStateRetained:true},null,2));
  } finally { await app.close(); }
});
