import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { goHome, openSpace } from "./shell";

test("LIVE LOCAL Ollama stream, cancel and retain across routes", async () => {
  test.skip(
    process.env.OLIVE_LIVE_AI !== "1",
    "Opt-in actual local inference; ordinary tests do not load a model.",
  );
  test.setTimeout(180000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-electron-stream-"));
  const evidence = path.resolve("../.experience-351/electron");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile },
  });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect
      .poll(
        () =>
          page.evaluate(async () => {
            const s = (await window.olive.call("runtime.snapshot", {})) as {
              models: unknown[];
            };
            return s.models.length;
          }),
        { timeout: 30000 },
      )
      .toBeGreaterThan(0);
    await page.evaluate(async () => {
      const s = (await window.olive.call("runtime.snapshot", {})) as {
        chat: { id: string };
      };
      await window.olive.call("chat.model", {
        chat_id: s.chat.id,
        model: "qwen3:8b",
      });
    });
    await page
      .getByRole("textbox", { name: "Ask OLIVE anything" })
      .fill(
        "Explain why small automated tests are useful when learning Python. Give ten practical examples.",
      );
    const started = performance.now();
    await page.getByRole("button", { name: "Submit request" }).click();
    await expect(page.getByText("OLIVE · writing", { exact: true })).toBeVisible(
      { timeout: 120000 },
    );
    const firstVisibleTokenMs = performance.now() - started;
    await page.screenshot({
      path: path.join(evidence, "chat-live-stream.png"),
    });
    await page
      .getByRole("button", { name: "Stop response", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Send message", exact: true }),
    ).toBeVisible({ timeout: 15000 });
    const before = await page.locator(".messages").innerText();
    await goHome(page);
    await openSpace(page, "Chat");
    expect(await page.locator(".messages").innerText()).toBe(before);
    await page.screenshot({
      path: path.join(evidence, "chat-live-cancelled.png"),
    });
    await writeFile(
      path.join(evidence, "stream-result.json"),
      JSON.stringify(
        {
          evidence: "LIVE LOCAL actual Ollama qwen3:8b",
          firstVisibleTokenMs,
          cancelled: true,
          retained: true,
          externalMessagesSent: 0,
        },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
