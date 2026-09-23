import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawn } from "node:child_process";

for (const nativeDialog of [false, true]) test(`M3/M4 ${nativeDialog ? "native dialog" : "controlled dialog"} restore preserves personal links, Mail drafts and reminder history without outbox replay`, async () => {
  test.skip(nativeDialog && process.env.OLIVE_NATIVE_DIALOGS !== "1", "Requires exclusive foreground desktop focus; controlled-dialog integrity coverage runs unattended");
  test.setTimeout(120000);
  const source = await mkdtemp(path.join(tmpdir(), "olive-m3-backup-source-"));
  const target = await mkdtemp(path.join(tmpdir(), "olive-m3-backup-target-"));
  const archive = path.join(target, "synthetic-backup.zip");
  const evidence =
    process.env.OLIVE_M3_EVIDENCE ||
    path.resolve("../artifacts/ui-review/M3/backup-" + Date.now());
  await mkdir(evidence, { recursive: true });
  const launch = (profile: string) =>
    electron.launch({
      args: [path.resolve(".")],
      env: {
        ...process.env,
        OLIVE_DATA_DIR: profile,
        OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      },
    });
  let app = await launch(source);
  const outcomes: unknown[] = [];
  const enter = async () => {
    const page = await app.firstWindow();
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    return page;
  };
  const settings = async () => {
    const page = await enter();
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Open Settings", exact: true })
      .click();
    await page
      .getByRole("navigation", { name: "Settings categories" })
      .getByRole("button", { name: "Backup & Data", exact: true })
      .click();
    return page;
  };
  try {
    let page = await settings();
    const ids = await page.evaluate(async () => {
      type RecordValue = {
        id: string;
        revision: number;
        [key: string]: unknown;
      };
      const profile = (await window.olive.call(
        "profile.get",
        {},
      )) as RecordValue;
      const project = (await window.olive.call("data.create_project", {
        title: "M3 Backup Project",
      })) as RecordValue;
      const contact = (await window.olive.call("contacts.create", {
        body: { display_name: "M3 Backup Contact", project_ids: [project.id] },
      })) as RecordValue;
      const event = (await window.olive.call("calendar.create", {
        body: {
          calendar_id: profile.default_calendar,
          title: "M3 Backup Event",
          start: "2026-09-14T10:00",
          end: "2026-09-14T11:00",
          project_id: project.id,
          contact_ids: [contact.id],
        },
      })) as RecordValue;
      const task = (await window.olive.call("tasks.create", {
        body: {
          title: "M3 Backup Task",
          project_id: project.id,
          event_id: event.id,
          contact_ids: [contact.id],
        },
      })) as RecordValue;
      const reminder = (await window.olive.call("reminders.create", {
        body: {
          target_kind: "task",
          target_id: task.id,
          at: "2026-01-01T10:00:00+02:00",
        },
      })) as RecordValue;
      const connection = (await window.olive.call("mail.connection_save", {
        body: {
          name: "M4 restore fixture",
          sender: "sender@example.invalid",
          smtp: { host: "127.0.0.1", port: 9, tls: "tls" },
        },
      })) as RecordValue;
      await window.olive.call("mail.connection_state", {
        record_id: connection.id,
        revision: connection.revision,
        enabled: true,
      });
      const draft = (await window.olive.call("mail.save_draft", {
        body: {
          connection_id: connection.id,
          to: ["fixture@example.invalid"],
          subject: "M4 backup fixture",
          text: "Local readable fixture",
          project_id: project.id,
        },
      })) as RecordValue;
      const submission = (await window.olive.call("mail.prepare", {
        record_id: draft.id,
        revision: draft.revision,
      })) as RecordValue;
      return {
        project: project.id,
        contact: contact.id,
        event: event.id,
        task: task.id,
        reminder: reminder.id,
        mail: draft.id,
        connection: connection.id,
        submission: submission.id,
      };
    });
    await expect
      .poll(
        async () =>
          (
            (await page.evaluate(() =>
              window.olive.call("reminders.history", {}),
            )) as { items: unknown[] }
          ).items.length,
        { timeout: 15000 },
      )
      .toBe(1);
    const delivery = await page.evaluate(async () => {
      const history = (await window.olive.call("reminders.history", {})) as {
        items: { id: string }[];
      };
      await window.olive.call("reminders.dismiss", {
        delivery_id: history.items[0].id,
      });
      return history.items[0].id;
    });
    await app.evaluate(({ dialog }, file) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
    }, archive);
    await page
      .getByRole("button", { name: "Create backup", exact: true })
      .click();
    await expect
      .poll(async () => {
        try {
          return (await stat(archive)).size;
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code === "ENOENT") return 0;
          throw error;
        }
      })
      .toBeGreaterThan(100);
    await app.close();
    app = await launch(target);
    page = await settings();
    await app.evaluate(({ dialog }, file) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [file],
      });
    }, archive);
    if (nativeDialog) {
    // Playwright can drive a background renderer. A native confirmation needs
    // an explicitly foregrounded, owned test window before opening it. Once
    // the modal opens the helper still aborts on focus loss; it never refocuses.
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].focus(),
    );
    await expect
      .poll(() =>
        app.evaluate(({ BrowserWindow }) =>
          BrowserWindow.getAllWindows()[0].isFocused(),
        ),
      )
      .toBe(true);
    const owned = await app.evaluate(({ BrowserWindow }) => ({
      pid: process.pid,
      window: Number(
        BrowserWindow.getAllWindows()[0]
          .getNativeWindowHandle()
          .readBigUInt64LE(),
      ),
    }));
    const helper = spawn(
      path.resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python"),
      [
        path.resolve("../scripts/m3_native_restore_approval.py"),
        "--pid",
        String(owned.pid),
        "--window",
        String(owned.window),
        "--profile",
        target,
        "--archive",
        archive,
      ],
      { windowsHide: true, cwd: path.resolve("..") },
    );
    let output = "",
      error = "";
    helper.stdout.on("data", (data) => {
      output += data;
    });
    helper.stderr.on("data", (data) => {
      error += data;
    });
    const completion = new Promise<number | null>((resolve, reject) => {
      helper.once("error", reject);
      helper.once("exit", resolve);
    });
    await page
      .getByRole("button", { name: "Restore backup", exact: true })
      .click();
    const code = await completion;
    outcomes.push({ native_dialog_helper: { code, output, error } });
    expect(code, error).toBe(0);
    expect(JSON.parse(output).invoked).toBe("Restore");
    } else {
      await app.evaluate(({ dialog }) => {
        dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false });
      });
      await page.getByRole("button", { name: "Restore backup", exact: true }).click();
      outcomes.push({ confirmation: "Controlled dialog response; real backup, restore and restart" });
    }
    await expect(
      page.getByText(/Restore complete. Restart OLIVE to reload all services/),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "native-restore-complete.png"),
    });
    await app.close();
    app = await launch(target);
    page = await enter();
    const restored = await page.evaluate(
      async (ids) => ({
        contact: await window.olive.call("contacts.get", {
          record_id: ids.contact,
        }),
        event: await window.olive.call("calendar.get", {
          record_id: ids.event,
        }),
        task: await window.olive.call("tasks.get", { record_id: ids.task }),
        history: await window.olive.call("reminders.history", {}),
        snapshot: await window.olive.call("runtime.snapshot", {}),
        mail: await window.olive.call("mail.get", { record_id: ids.mail }),
        connections: await window.olive.call("mail.connections", {}),
        outbox: await window.olive.call("mail.outbox", {}),
      }),
      ids,
    );
    expect(restored.contact).toMatchObject({
      id: ids.contact,
      project_ids: [ids.project],
    });
    expect(restored.event).toMatchObject({
      id: ids.event,
      contact_ids: [ids.contact],
    });
    expect(restored.task).toMatchObject({
      event_id: ids.event,
      project_id: ids.project,
    });
    expect(restored.history).toMatchObject({
      items: [{ id: delivery, state: "dismissed" }],
    });
    expect(restored.snapshot).toMatchObject({ approvals: [] });
    expect(restored.mail).toMatchObject({
      id: ids.mail,
      project_id: ids.project,
      text: "Local readable fixture",
      submission_state: "draft",
    });
    expect(restored.connections).toMatchObject({
      items: [
        {
          id: ids.connection,
          enabled: false,
          credential_ref: null,
          state: "review_required",
        },
      ],
    });
    expect(restored.outbox).toMatchObject({
      items: [{ id: ids.submission, state: "cancelled" }],
    });
    outcomes.push({ ids, restored });
  } catch (error) {
    outcomes.push({ primary_error: String(error) });
    try {
      const page = await app.firstWindow();
      outcomes.push({
        visible_alerts: await page.getByRole("alert").allTextContents(),
      });
      await page.screenshot({
        path: path.join(evidence, "backup-first-failure.png"),
      });
    } catch (secondary) {
      outcomes.push({ secondary_capture_error: String(secondary) });
    }
    throw error;
  } finally {
    await writeFile(
      path.join(evidence, "backup-result.json"),
      JSON.stringify(
        {
          classification: nativeDialog ? "Real backup/restore with native approval; controlled file chooser" : "Real backup/restore with controlled native dialog responses",
          source,
          target,
          outcomes,
        },
        null,
        2,
      ),
    );
    await app.close();
  }
});
