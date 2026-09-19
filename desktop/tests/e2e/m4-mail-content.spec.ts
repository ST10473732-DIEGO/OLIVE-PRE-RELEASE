import { captureMail } from "./m4-capture";
import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";

test("M4 real EML isolation, source-linked proposals, export and cancelled draft", async () => {
  test.setTimeout(120000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m4-content-"));
  const evidence = path.resolve("../artifacts/ui-review/M4/content-ui");
  await mkdir(evidence, { recursive: true });
  const plain =
    "Synthetic planning meeting on 3 June 2030 at 10:00 in Africa/Johannesburg, ending at 11:00. Café fixture.";
  const html =
    '<h2>Café fixture</h2><p>Planning meeting.</p><img src="cid:fixture-pixel"><img src="https://tracking.example.invalid/pixel"><script>parent.mailInjected=true</script><form action="https://tracking.example.invalid/form"><input name="secret"></form><a href="https://example.invalid/fixture">Read documentation</a>';
  const raw = Buffer.from(
    [
      "From: Fixture Sender <fixture@example.invalid>",
      "To: recipient@example.invalid",
      "Reply-To: reply@example.invalid",
      "Subject: =?UTF-8?B?" +
        Buffer.from("Café planning fixture").toString("base64") +
        "?=",
      "Message-ID: <m4-content@example.invalid>",
      "MIME-Version: 1.0",
      'Content-Type: multipart/mixed; boundary="outer"',
      "",
      "--outer",
      'Content-Type: multipart/alternative; boundary="inner"',
      "",
      "--inner",
      "Content-Type: text/plain; charset=utf-8",
      "Content-Transfer-Encoding: base64",
      "",
      Buffer.from(plain).toString("base64"),
      "--inner",
      "Content-Type: text/html; charset=utf-8",
      "Content-Transfer-Encoding: base64",
      "",
      Buffer.from(html).toString("base64"),
      "--inner--",
      "--outer",
      "Content-Type: image/png",
      "Content-ID: <fixture-pixel>",
      'Content-Disposition: inline; filename="pixel.png"',
      "Content-Transfer-Encoding: base64",
      "",
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII=",
      "--outer",
      "Content-Type: text/plain; charset=utf-8",
      'Content-Disposition: attachment; filename="fixture.txt"',
      "",
      "Synthetic attachment only.",
      "--outer--",
      "",
    ].join("\r\n"),
  );
  const source = path.join(profile, "fixture.eml");
  await writeFile(source, raw);
  const digest = createHash("sha256").update(raw).digest("hex");
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  const approvals: unknown[] = [];
  try {
    const page = await app.firstWindow();
    const remote: string[] = [];
    page.context().on("request", (r) => {
      if (r.url().includes("tracking.example.invalid")) remote.push(r.url());
    });
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page.getByRole("button", { name: "Open Mail", exact: true }).click();
    await app.evaluate(({ dialog }, source) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [source],
      });
    }, source);
    await page.getByRole("button", { name: "Import EML", exact: true }).click();
    const preview = page.getByRole("dialog", { name: "Review EML import" });
    await expect(preview).toContainText("Café planning fixture");
    await expect(preview).toContainText("2 attachments");
    const approve = async (expected: string[], deny = false) => {
      const dialog = page.getByRole("dialog").filter({
        has: page.getByRole("button", {
          name: "Approve this action",
          exact: true,
        }),
      });
      await expect(dialog).toBeVisible();
      const value = await dialog.innerText();
      for (const part of expected) expect(value).toContain(part);
      approvals.push({
        delegated: true,
        isolated_profile: profile,
        scope: value,
        decision: deny ? "cancel" : "approve once",
      });
      await dialog
        .getByRole("button", {
          name: deny ? "Cancel" : "Approve this action",
          exact: true,
        })
        .click();
    };
    await preview
      .getByRole("button", { name: "Import this message", exact: true })
      .click();
    await approve(["Import commit", digest]);
    await expect(preview).not.toBeVisible();
    await page
      .getByRole("button", { name: "Safe formatted view", exact: true })
      .click();
    const frame = page.frameLocator('iframe[title="Untrusted email body"]');
    await expect(
      frame.getByRole("heading", { name: "Café fixture" }),
    ).toBeVisible();
    await expect(frame.locator("script,form,input,iframe")).toHaveCount(0);
    await expect(frame.locator("img")).toHaveCount(1);
    await expect(frame.locator("img")).toHaveAttribute(
      "src",
      /^data:image\/png;base64,/,
    );
    expect(
      await frame.locator("body").evaluate(() => ({
        bridge: typeof (window as unknown as { olive?: unknown }).olive,
        origin: location.origin,
      })),
    ).toEqual({ bridge: "undefined", origin: "null" });
    expect(
      await page.evaluate(() =>
        Object.prototype.hasOwnProperty.call(window, "mailInjected"),
      ),
    ).toBe(false);
    expect(remote).toEqual([]);
    await captureMail(page, app, path.join(evidence, "safe-message.png"));
    const records = (await page.evaluate(() =>
      window.olive.call("mail.search", { query: "Café" }),
    )) as { items: { id: string }[] };
    expect(records.items).toHaveLength(1);
    const messageId = records.items[0].id;
    await page.getByText("More actions", { exact: true }).click();
    const exported = path.join(profile, "export.eml");
    await app.evaluate(({ dialog }, file) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
    }, exported);
    await page.getByRole("button", { name: "Export EML", exact: true }).click();
    await expect
      .poll(async () => {
        try {
          return createHash("sha256")
            .update(await readFile(exported))
            .digest("hex");
        } catch {
          return "";
        }
      })
      .toBe(digest);
    await page
      .getByRole("button", { name: "Review Add to Knowledge", exact: true })
      .click();
    await approve(["Add knowledge", messageId]);
    await expect
      .poll(async () => {
        const rows = (await page.evaluate(() =>
          window.olive.call("knowledge.list", {}),
        )) as { chat_id: string }[];
        return rows.length;
      })
      .toBe(1);
    await page
      .getByRole("button", { name: "Create Calendar proposal", exact: true })
      .click();
    const event = page.getByRole("dialog", { name: "Mail to Calendar" });
    await event.getByLabel("Title", { exact: true }).fill("M4 fixture meeting");
    await event.getByLabel("Start", { exact: true }).fill("2030-06-03T10:00");
    await event.getByLabel("End", { exact: true }).fill("2030-06-03T11:00");
    await captureMail(page, app, path.join(evidence, "calendar-proposal.png"));
    await event
      .getByRole("button", { name: "Review local event", exact: true })
      .click();
    await approve([
      "Create event",
      "M4 fixture meeting",
      "2030-06-03T10:00",
      "2030-06-03T11:00",
    ]);
    await expect(event).not.toBeVisible();
    await expect
      .poll(
        async () =>
          (
            (await page.evaluate(() =>
              window.olive.call("calendar.search", {
                query: "M4 fixture meeting",
              }),
            )) as { items: unknown[] }
          ).items.length,
      )
      .toBe(1);
    const events = (await page.evaluate(() =>
      window.olive.call("calendar.search", { query: "M4 fixture meeting" }),
    )) as { items: { id: string; title: string; start: string }[] };
    expect(events.items).toHaveLength(1);
    await page
      .getByRole("button", { name: "Create Task proposal", exact: true })
      .click();
    const task = page.getByRole("dialog", { name: "Mail to Tasks" });
    await task
      .getByLabel("Title", { exact: true })
      .fill("M4 fixture follow-up");
    await task
      .getByRole("button", { name: "Review local task", exact: true })
      .click();
    await approve(["Create task", "M4 fixture follow-up"]);
    await expect(task).not.toBeVisible();
    // Closing the approval overlay is not proof that the native transaction
    // committed. Wait for the actual scoped result, preserving ID/content checks.
    await expect
      .poll(
        async () =>
          (
            (await page.evaluate(() =>
              window.olive.call("tasks.search", {
                query: "M4 fixture follow-up",
              }),
            )) as { items: unknown[] }
          ).items.length,
      )
      .toBe(1);
    const tasks = (await page.evaluate(() =>
      window.olive.call("tasks.search", { query: "M4 fixture follow-up" }),
    )) as { items: { id: string }[] };
    expect(tasks.items).toHaveLength(1);
    await page.getByRole("button", { name: "Reply", exact: true }).click();
    await expect(page.getByLabel("To", { exact: true })).toHaveValue(
      "reply@example.invalid",
    );
    await page
      .getByLabel("Message", { exact: true })
      .fill("Friday works. This stays a local draft.");
    await page
      .getByLabel("To", { exact: true })
      .fill("different@example.invalid");
    await page.getByRole("button", { name: "Save draft", exact: true }).click();
    await expect(
      page
        .getByRole("status")
        .filter({ hasText: "Saved locally. Drafts remain" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Close composer", exact: true })
      .click();
    const outbox = (await page.evaluate(() =>
      window.olive.call("mail.outbox", {}),
    )) as { items: unknown[] };
    expect(outbox.items).toHaveLength(0);
    await page
      .getByRole("button", { name: "Draft from Calendar", exact: true })
      .click();
    await page
      .getByLabel("Calendar event", { exact: true })
      .selectOption(events.items[0].id);
    await page
      .getByRole("button", { name: "Create draft from event", exact: true })
      .click();
    await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
      "M4 fixture meeting",
    );
    await expect(page.getByLabel("To", { exact: true })).toHaveValue("");
    await expect(page.getByLabel("Message", { exact: true })).toHaveValue(
      /2030/,
    );
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1366, 768),
    );
    await captureMail(page, app, path.join(evidence, "mail-small.png"));
    await writeFile(
      path.join(evidence, "result.json"),
      JSON.stringify(
        {
          classification:
            "live local Electron/Python; controlled native chooser; delegated synthetic approvals; model unavailable",
          profile,
          messageId,
          event: events.items[0],
          task: tasks.items[0],
          html_remote_requests: remote,
          eml_exact_roundtrip: true,
          approvals,
        },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
