import { captureMail } from "./m4-capture";
import { test, expect, _electron as electron } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

test("M4 Electron bounded IMAP header sync, explicit body read, restart and disconnect", async () => {
  test.setTimeout(90000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m4-imap-ui-")),
    directory = await mkdtemp(path.join(tmpdir(), "olive-m4-sink-"));
  const evidence = path.resolve("../artifacts/ui-review/M4/imap-ui");
  await mkdir(evidence, { recursive: true });
  const fixture = spawn(
    path.resolve("../.venv/Scripts/python.exe"),
    [
      path.resolve("../scripts/run_m4_mail_sink.py"),
      "--directory",
      directory,
      "--imap",
    ],
    { windowsHide: true, stdio: "ignore" },
  );
  const launch = () =>
    electron.launch({
      args: [path.resolve(".")],
      env: {
        ...process.env,
        OLIVE_DATA_DIR: profile,
        OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      },
    });
  let app: Awaited<ReturnType<typeof launch>> | undefined;
  let connectionId = "";
  try {
    await expect
      .poll(
        async () => {
          try {
            const r = JSON.parse(
              await readFile(path.join(directory, "ready.json"), "utf8"),
            );
            return r.pid === fixture.pid || r.parent_pid === fixture.pid;
          } catch {
            return false;
          }
        },
        { timeout: 15000 },
      )
      .toBe(true);
    const ready = JSON.parse(
      await readFile(path.join(directory, "ready.json"), "utf8"),
    );
    expect(ready.connection.imap.host).toBe("127.0.0.1");
    app = await launch();
    let page = await app.firstWindow();
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    // Controlled setup uses actual validated configuration/storage endpoints.
    // Sync/body retrieval below are actual Mail controls and approvals.
    let c = (await page.evaluate(
      (body) => window.olive.call("mail.connection_save", { body }),
      ready.connection,
    )) as { id: string; revision: number };
    connectionId = c.id;
    c = (await page.evaluate(
      (c) =>
        window.olive.call("mail.credential_store", {
          record_id: c.id,
          revision: c.revision,
          secret: "fixture-secret",
        }),
      c,
    )) as { id: string; revision: number };
    await page.evaluate(
      (c) =>
        window.olive.call("mail.connection_state", {
          record_id: c.id,
          revision: c.revision,
          enabled: true,
        }),
      c,
    );
    const go = async () => {
      await page
        .getByRole("button", { name: "Find anything", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Open Mail", exact: true })
        .click();
    };
    await go();
    await page
      .getByLabel("Mail connection", { exact: true })
      .selectOption(connectionId);
    const approvals: unknown[] = [];
    const approve = async (action: string, target: string) => {
      const dialog = page.getByRole("dialog").filter({
        has: page.getByRole("button", {
          name: "Approve this action",
          exact: true,
        }),
      });
      await expect(dialog).toBeVisible();
      const text = await dialog.innerText();
      expect(text).toContain(action);
      expect(text).toContain(target);
      approvals.push({ delegated: true, profile, text });
      await dialog
        .getByRole("button", { name: "Approve this action", exact: true })
        .click();
    };
    await page
      .getByRole("button", { name: "Refresh server", exact: true })
      .click();
    await approve("Sync", connectionId);
    await expect(
      page.getByRole("status").filter({ hasText: "Mailbox cache refreshed" }),
    ).toBeVisible();
    const r = (await page.evaluate(() =>
      window.olive.call("mail.search", {}),
    )) as { items: { id: string }[] };
    expect(r.items).toHaveLength(1);
    const id = r.items[0].id;
    const before = (await page.evaluate(
      (id) => window.olive.call("mail.get", { record_id: id }),
      id,
    )) as { body_cached: boolean };
    expect(before.body_cached).toBe(false);
    await page.getByRole("button", { name: /^Inbox/ }).click();
    await page
      .getByRole("button", { name: /fixture@example.invalid.*Cached fixture/ })
      .click();
    await page.getByRole("button", { name: "Fetch body", exact: true }).click();
    await approve("Fetch body", id);
    await expect(
      page.getByText("Body fetched only on demand.", { exact: true }),
    ).toBeVisible();
    await captureMail(page, app, path.join(evidence, "cached-body.png"));
    await app.close();
    app = await launch();
    page = await app.firstWindow();
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    const current = (await page.evaluate(
      (id) => window.olive.call("mail.get", { record_id: id }),
      id,
    )) as { id: string; body_cached: boolean; read: boolean };
    expect(current).toMatchObject({ id, body_cached: true, read: false });
    const configs = (await page.evaluate(() =>
      window.olive.call("mail.connections", {}),
    )) as { items: { id: string; revision: number }[] };
    const saved = configs.items.find((c) => c.id === connectionId)!;
    await page.evaluate(
      (c) =>
        window.olive.call("mail.connection_state", {
          record_id: c.id,
          revision: c.revision,
          enabled: false,
          remove_credentials: true,
        }),
      saved,
    );
    await writeFile(
      path.join(evidence, "result.json"),
      JSON.stringify(
        {
          classification: ready.classification,
          profile,
          connectionId,
          record: current,
          approvals,
          restart: true,
          disconnected: true,
        },
        null,
        2,
      ),
    );
  } finally {
    if (app) {
      const page = await app.firstWindow();
      if (connectionId)
        await page.evaluate(async (id) => {
          const r = (await window.olive.call("mail.connections", {})) as {
            items: { id: string; revision: number; credential_ref: string }[];
          };
          const c = r.items.find((c) => c.id === id);
          if (c?.credential_ref)
            await window.olive.call("mail.connection_state", {
              record_id: c.id,
              revision: c.revision,
              enabled: false,
              remove_credentials: true,
            });
        }, connectionId);
      await app.close();
    }
    await writeFile(path.join(directory, "stop"), "owned fixture stop");
    await expect.poll(() => fixture.exitCode, { timeout: 15000 }).toBe(0);
    await writeFile(
      path.join(evidence, "protocol-observations.json"),
      await readFile(path.join(directory, "imap-observations.json")),
    );
  }
});
