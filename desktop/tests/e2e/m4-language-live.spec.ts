import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

test("M4 installed local interpreter searches drafts corrects and cancels through Electron", async () => {
  test.skip(
    process.env.OLIVE_M4_LIVE_LANGUAGE !== "1",
    "Opt-in installed-model Mail evaluation; no external Mail or accounts.",
  );
  test.setTimeout(600000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m4-language-"));
  const evidence = path.resolve("../artifacts/ui-review/M4/language-ui");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:11434",
    },
  });
  const outcomes: unknown[] = [];
  try {
    const page = await app.firstWindow();
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (
            (await page.evaluate(() =>
              window.olive.call("runtime.snapshot", {}),
            )) as { initializing: boolean }
          ).initializing,
        { timeout: 60000 },
      )
      .toBe(false);
    await page.evaluate(() =>
      window.olive.call("contacts.create", {
        body: {
          display_name: "Sarah Fixture",
          emails: [{ label: "fixture", value: "sarah@example.invalid" }],
        },
      }),
    );
    const raw =
      "From: sarah@example.invalid\r\nTo: local@example.invalid\r\nSubject: M4 planning fixture\r\nMessage-ID: <language@example.invalid>\r\n\r\nOur synthetic planning session is Friday at 10:00. Please bring the agenda.\r\n";
    const source = path.join(profile, "language.eml");
    await writeFile(source, raw);
    await app.evaluate(({ dialog }, source) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [source],
      });
    }, source);
    const preview = (await page.evaluate(() =>
      window.olive.fileAction({ action: "mail-import" }),
    )) as { preview_id: string; hash: string };
    const imported = page.evaluate(
      (p) =>
        window.olive.call("mail.import_commit", {
          preview_id: p.preview_id,
          expected_hash: p.hash,
        }),
      preview,
    );
    const approve = async (parts: string[]) => {
      const dialog = page
        .getByRole("dialog")
        .filter({
          has: page.getByRole("button", {
            name: "Approve this action",
            exact: true,
          }),
        });
      await expect(dialog).toBeVisible({ timeout: 150000 });
      const text = await dialog.innerText();
      for (const part of parts) expect(text).toContain(part);
      outcomes.push({ delegated_approval: true, scope: text, profile });
      await dialog
        .getByRole("button", { name: "Approve this action", exact: true })
        .click();
    };
    await approve(["Import commit", preview.hash]);
    await imported;
    const snapshot = (await page.evaluate(() =>
      window.olive.call("runtime.snapshot", {}),
    )) as { chat: { id: string } };
    const chatId = snapshot.chat.id;
    const chat = () =>
      page.evaluate(
        (id) => window.olive.call("chat.get", { chat_id: id }),
        chatId,
      ) as Promise<{ messages: { role: string; content: string }[] }>;
    let count = 0;
    const request = async (text: string, approval?: string[]) => {
      const started = Date.now();
      if (count === 0) {
        await page
          .getByRole("textbox", { name: "Ask OLIVE anything", exact: true })
          .fill(text);
        await page
          .getByRole("button", { name: "Submit request", exact: true })
          .click();
      } else {
        await page
          .getByRole("textbox", { name: "Message OLIVE", exact: true })
          .fill(text);
        await page
          .getByRole("button", { name: "Send message", exact: true })
          .click();
      }
      if (approval) await approve(approval);
      await expect
        .poll(
          async () =>
            (await chat()).messages.filter((m) => m.role === "assistant")
              .length,
          { timeout: 160000 },
        )
        .toBeGreaterThan(count);
      const result = await chat();
      count = result.messages.filter((m) => m.role === "assistant").length;
      const interpretation = await page.evaluate(
        (id) => window.olive.call("interaction.inspect", { chat_id: id }),
        chatId,
      );
      outcomes.push({
        request: text,
        elapsed_ms: Date.now() - started,
        result,
        interpretation,
      });
      await writeFile(
        path.join(evidence, "results.json"),
        JSON.stringify(outcomes, null, 2),
      );
      return result.messages.filter((m) => m.role === "assistant").at(-1)!
        .content;
    };
    const found = await request(
      "Find the local email from sarah@example.invalid about M4 planning.",
    );
    expect(found).toContain("M4 planning fixture");
    const summary = await request("Summarise that email.");
    expect(summary.toLowerCase()).toContain("friday");
    expect(summary.toLowerCase()).toContain("agenda");
    await request(
      "Create an unsent email draft to sarah@example.invalid with subject Friday response and body Friday works. Do not send it.",
      ["Save draft", "sarah@example.invalid", "Friday works"],
    );
    let drafts = (await page.evaluate(() =>
      window.olive.call("mail.search", { folder: "Drafts" }),
    )) as { items: { id: string }[] };
    expect(drafts.items).toHaveLength(1);
    const id = drafts.items[0].id;
    await request(
      "Change only the recipient of that draft to james@example.invalid. Keep the subject and body.",
      ["Save draft", "james@example.invalid", "Friday works"],
    );
    const current = (await page.evaluate(
      (id) => window.olive.call("mail.get", { record_id: id }),
      id,
    )) as { to: string[]; text: string };
    expect(current.to).toEqual(["james@example.invalid"]);
    expect(current.text).toContain("Friday works");
    await request("Do not send it yet. Keep my local draft.");
    const outbox = (await page.evaluate(() =>
      window.olive.call("mail.outbox", {}),
    )) as { items: unknown[] };
    expect(outbox.items).toHaveLength(0);
    drafts = (await page.evaluate(() =>
      window.olive.call("mail.search", { folder: "Drafts" }),
    )) as { items: { id: string }[] };
    expect(drafts.items[0].id).toBe(id);
    await page.screenshot({ path: path.join(evidence, "local-language.png") });
  } finally {
    await writeFile(
      path.join(evidence, "results.json"),
      JSON.stringify(outcomes, null, 2),
    );
    await app.close();
  }
});
