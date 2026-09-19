import {test, expect, _electron as electron} from "@playwright/test";
import {spawn} from "node:child_process";
import {mkdtemp, mkdir, readFile, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import path from "node:path";
import {captureMail} from "./m4-capture";

test("real UI unified and separate accounts, received-account reply and honest Google setup", async () => {
  test.setTimeout(120000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-mail-accounts-"));
  const evidence = path.resolve("../artifacts/core/functionality/mail-accounts");
  await mkdir(evidence, {recursive: true});
  const peers: {directory: string; process: ReturnType<typeof spawn>}[] = [];
  const ids: string[] = [];
  let app: Awaited<ReturnType<typeof electron.launch>> | undefined;
  try {
    for (let index = 0; index < 2; index++) {
      const directory = await mkdtemp(path.join(tmpdir(), "olive-m4-sink-"));
      const process = spawn(path.resolve("../.venv/Scripts/python.exe"), [path.resolve("../scripts/run_m4_mail_sink.py"), "--directory", directory, "--imap"], {windowsHide: true, stdio: "ignore"});
      peers.push({directory, process});
      await expect.poll(async () => {
        try { const r = JSON.parse(await readFile(path.join(directory, "ready.json"), "utf8")); return r.pid === process.pid || r.parent_pid === process.pid; } catch { return false; }
      }, {timeout: 15000}).toBeTruthy();
    }
    app = await electron.launch({args: [path.resolve(".")], env: {...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1"}});
    const page = await app.firstWindow();
    await page.getByRole("button", {name: "Enter OLIVE", exact: true}).click();
    for (const [index, peer] of peers.entries()) {
      const ready = JSON.parse(await readFile(path.join(peer.directory, "ready.json"), "utf8"));
      expect(ready.connection.imap.host).toBe("127.0.0.1");
      const c = await page.evaluate(async body => {
        let c = await window.olive.call("mail.connection_save", {body}) as {id: string; revision: number};
        c = await window.olive.call("mail.credential_store", {record_id: c.id, revision: c.revision, secret: "fixture-secret"}) as typeof c;
        return window.olive.call("mail.connection_state", {record_id: c.id, revision: c.revision, enabled: true});
      }, {...ready.connection, name: `Synthetic account ${index + 1}`, sender: `account${index + 1}@example.invalid`}) as {id: string};
      ids.push(c.id);
    }
    await page.getByRole("button", {name: "Find anything", exact: true}).click();
    await page.getByRole("button", {name: "Open Mail", exact: true}).click();
    for (const id of ids) {
      await page.getByLabel("Mail connection", {exact: true}).selectOption(id);
      await page.getByRole("button", {name: "Refresh server", exact: true}).click();
      const dialog = page.getByRole("dialog").filter({has: page.getByRole("button", {name: "Approve this action", exact: true})});
      await expect(dialog).toContainText(id);
      const snapshot = await page.evaluate(() => window.olive.call("runtime.snapshot", {})) as {approvals: {tool_name: string; arguments: {connection_id: string; folder: string; limit: number}}[]};
      expect(snapshot.approvals).toHaveLength(1);
      expect(snapshot.approvals[0].tool_name).toBe("mail.sync");
      expect(snapshot.approvals[0].arguments).toMatchObject({connection_id: id, folder: "Inbox", limit: 50});
      await dialog.getByRole("button", {name: "Approve this action", exact: true}).click();
      await expect(page.locator(".mail-list-item")).toHaveCount(1);
    }
    await page.getByLabel("Mail connection", {exact: true}).selectOption("");
    await expect(page.getByRole("button", {name: /^All Inboxes/})).toBeVisible();
    await expect(page.locator(".mail-list-item")).toHaveCount(2);
    const rows = await page.evaluate(() => window.olive.call("mail.search", {folder: "Inbox"})) as {items: {id: string; connection_id: string}[]};
    expect(new Set(rows.items.map(r => r.id)).size).toBe(2);
    expect(new Set(rows.items.map(r => r.connection_id)).size).toBe(2);
    await captureMail(page, app, path.join(evidence, "all-inboxes.png"));
    await page.locator(".mail-list-item").filter({hasText: "Synthetic account 2"}).click();
    await page.getByRole("button", {name: "Reply", exact: true}).click();
    await expect(page.getByLabel("From / sending identity", {exact: true})).toHaveValue(ids[1]);
    await expect(page.getByLabel("From / sending identity").locator("option:checked")).toContainText("account2@example.invalid");
    await page.getByRole("button", {name: "Close composer", exact: true}).click();
    await page.getByRole("button", {name: "Mail connections", exact: true}).click();
    await expect(page.getByRole("button", {name: "Authorize Gmail account", exact: true})).toBeDisabled();
    await expect(page.getByText("Needs setup: registered Google Desktop app client", {exact: true})).toBeVisible();
    await page.getByRole("button", {name: "Add iCloud Mail", exact: true}).click();
    await expect(page.getByLabel("IMAP server", {exact: true})).toHaveValue("imap.mail.me.com");
    await expect(page.getByLabel("SMTP server", {exact: true})).toHaveValue("smtp.mail.me.com");
    await app.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].setSize(1024, 720));
    await captureMail(page, app, path.join(evidence, "icloud-setup-small.png"));
    await writeFile(path.join(evidence, "result.json"), JSON.stringify({classification: "real Electron controls, two independent scripted loopback IMAP peers; no personal provider login", ids, rows, correctReplyAccount: ids[1], googleNeedsSetup: true}, null, 2));
  } finally {
    if (app) {
      const page = await app.firstWindow();
      await page.evaluate(async ids => {
        const result = await window.olive.call("mail.connections", {}) as {items: {id: string; revision: number; credential_ref?: string}[]};
        for (const c of result.items.filter(c => ids.includes(c.id) && c.credential_ref)) await window.olive.call("mail.connection_state", {record_id: c.id, revision: c.revision, enabled: false, remove_credentials: true});
      }, ids);
      await app.close();
    }
    for (const peer of peers) {
      await writeFile(path.join(peer.directory, "stop"), "owned fixture stop");
      await expect.poll(() => peer.process.exitCode, {timeout: 15000}).toBe(0);
    }
  }
});
