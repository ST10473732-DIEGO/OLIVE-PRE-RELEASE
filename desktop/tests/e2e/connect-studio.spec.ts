import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile, rename } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";

test("C8 native sharing, approval, remote editor conflicts, jobs and offline draft", async () => {
  test.setTimeout(180000);
  const root = path.resolve(".."), profile = await mkdtemp(path.join(tmpdir(), "olive-c8-ui-")), shim = path.join(profile, "shim");
  await mkdir(shim);
  await writeFile(path.join(shim, "sitecustomize.py"), `import sys,runpy\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/connect_studio_ui_runtime.py"))})\n`);
  const app = await electron.launch({args: [path.resolve(".")], env: {...process.env, OLIVE_DATA_DIR: profile, PYTHONPATH: shim, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1"}});
  try {
    const page = await app.firstWindow(); page.setDefaultTimeout(20000);
    const errors: string[] = []; page.on("pageerror", e => errors.push(e.message));
    const control = async (action: string, value = "") => {
      const id = crypto.randomUUID();
      await writeFile(path.join(profile, "fixture-command.tmp"), JSON.stringify({id, action, value}));
      await rename(path.join(profile, "fixture-command.tmp"), path.join(profile, "fixture-command.json"));
      await expect.poll(async () => {try {return JSON.parse(await readFile(path.join(profile, "fixture-result.json"), "utf8")).id;} catch {return null;}}).toBe(id);
      return JSON.parse(await readFile(path.join(profile, "fixture-result.json"), "utf8")).result;
    };
    await page.getByRole("button", {name: "Enter OLIVE", exact: true}).click();
    await openSpace(page, "Devices");
    await page.getByRole("button", {name: /127\.0\.0\.1/}).click();
    await page.getByRole("button", {name: "Turn Connect on", exact: true}).click();
    const connected = await control("connect");
    await page.getByRole("button", {name: /^C8 paired desktop.*Online/}).click();
    const sharing = page.getByRole("region", {name: "Remote Studio sharing"});
    await sharing.getByLabel("Local workspace to share").selectOption({label: "Target fixture"});
    await sharing.getByRole("button", {name: "Share workspace", exact: true}).click();
    await expect(sharing.getByLabel("Target fixture studio.view")).toHaveValue("deny");
    await sharing.getByLabel("Target fixture studio.view").selectOption("ask");
    // The select event starts an async permission/revision update. Wait for
    // committed state before constructing the independent peer request; a
    // request using the preceding revision must remain rejected as stale.
    await expect.poll(async () => (await control("local_shares"))[0]?.permissions["studio.view"]).toBe("ask");
    expect((await control("incoming")).error).toBe("confirmation_required");
    await expect(page.getByText("One guarded operation on this shared workspace.")).toBeVisible();
    await page.getByRole("button", {name: "Deny", exact: true}).click();
    expect((await control("retry")).error).toBe("permission_denied");
    await control("incoming");
    await page.getByRole("button", {name: "Allow once", exact: true}).click();
    expect((await control("retry")).result.text).toContain("target");
    await expect(sharing.getByLabel("Target fixture studio.view")).toHaveValue("ask");
    await openSpace(page, "Studio");
    await page.getByRole("group", {name: "Studio workspace location"}).getByRole("button", {name: "Remote", exact: true}).click();
    const remote = page.getByLabel("Remote Studio workspace", {exact: true});
    await remote.getByLabel("Remote Studio device").selectOption(connected.peer);
    await remote.getByRole("button", {name: "Load shared workspaces"}).click();
    await remote.getByLabel("Remote workspace", {exact: true}).selectOption(connected.share.workspace_id);
    await remote.getByRole("button", {name: "Files", exact: true}).click();
    await remote.getByRole("button", {name: "main.py", exact: true}).click();
    await expect(remote.getByText("main.py · Saved remote revision", {exact: true})).toBeVisible();
    const input = remote.getByRole("textbox", {name: "Remote source editor"});
    await input.focus(); await page.keyboard.press("Control+a"); await page.keyboard.insertText('print("UI saved")\n');
    await expect(remote.getByText("main.py · Unsaved local draft", {exact: true})).toBeVisible();
    await remote.getByRole("button", {name: "Save remotely"}).click();
    await expect(remote.getByText("Saved remotely.", {exact: true})).toBeVisible();
    expect(await control("bytes")).toBe('print("UI saved")\n');
    await remote.getByRole("button", {name: "Test remotely"}).click();
    await expect(remote.getByText("1 passed · 0 failed · 0 skipped")).toBeVisible();
    await control("edit", 'import time\nprint("owned", flush=True)\ntime.sleep(60)\n');
    await remote.getByRole("button", {name: "Run remotely"}).click();
    await expect.poll(async () => (await control("counts")).active).toBe(1);
    await remote.getByRole("button", {name: "Stop", exact: true}).click();
    await expect.poll(async () => (await control("counts")).active).toBe(0);
    await input.focus(); await page.keyboard.press("Control+a"); await page.keyboard.insertText('print("offline draft")\n');
    await control("disconnect");
    await expect(remote.getByText(/Remote · C8 paired desktop · Offline/)).toBeVisible();
    await expect(remote.getByText("main.py · Unsaved local draft", {exact: true})).toBeVisible();
    await control("connect");
    await expect(remote.getByRole("button", {name: "Save remotely"})).toBeEnabled();
    await remote.getByRole("button", {name: "Save remotely"}).click();
    await expect(remote.getByRole("status")).toContainText("revision_conflict");
    expect(await control("bytes")).toContain('time.sleep(60)');
    expect(errors).toEqual([]);
    // Explicitly discard the owned draft before the ordinary app close.
    page.once("dialog", dialog => dialog.accept());
    await remote.getByRole("button", {name: "Reload", exact: true}).click();
    await expect(remote.getByText("Reloaded remote revision.")).toBeVisible();
  } finally { await app.close(); }
});
