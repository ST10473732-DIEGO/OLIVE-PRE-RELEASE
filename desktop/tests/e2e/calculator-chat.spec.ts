import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";

test("LIVE LOCAL calculator code stays in Chat without an Agent task or workspace", async () => {
  test.skip(process.env.OLIVE_LIVE_AI !== "1", "Requires installed local Ollama model");
  test.setTimeout(240000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-calculator-chat-"));
  const evidence = path.resolve("../artifacts/core/functionality");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({ chromiumSandbox: true, args: [path.resolve(".")], env: { ...process.env, OLIVE_DATA_DIR: profile } });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect.poll(() => page.evaluate(async () => {
      const s = await window.olive.call("runtime.snapshot", {}) as { models: unknown[] };
      return s.models.length;
    }), { timeout: 30000 }).toBeGreaterThan(0);
    const before = await page.evaluate(async () => {
      const s = await window.olive.call("runtime.snapshot", {}) as { chat: { id: string } };
      await window.olive.call("chat.model", { chat_id: s.chat.id, model: "qwen3:8b" });
      return s;
    });
    const tasksBefore = await page.evaluate(() => window.olive.call("agent.history", { query: "", offset: 0 }));
    await page.getByRole("textbox", { name: "Ask OLIVE anything" }).fill("Give me code for a simple calculator app.");
    const started = performance.now();
    await page.getByRole("button", { name: "Submit request" }).click();
    await expect(page.locator(".messages pre").first()).toBeVisible({ timeout: 180000 });
    const firstCodeMs = performance.now() - started;
    await expect(page.getByRole("button", { name: "Stop response", exact: true })).toBeHidden({ timeout: 180000 });
    const after = await page.evaluate(() => window.olive.call("runtime.snapshot", {}));
    const tasksAfter = await page.evaluate(() => window.olive.call("agent.history", { query: "", offset: 0 }));
    expect(tasksAfter).toEqual(tasksBefore);
    const inspection = await page.evaluate((id) => window.olive.call("interaction.inspect", { chat_id: id }), before.chat.id);
    const answer = await page.locator(".messages").innerText();
    expect(answer).not.toContain("Which saved project workspace");
    expect(await page.locator(".messages pre").first().innerText()).toMatch(/.{100}/s);
    await page.screenshot({ path: path.join(evidence, "calculator-chat.png") });
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1000, 700));
    await page.screenshot({ path: path.join(evidence, "calculator-chat-small.png") });
    await writeFile(path.join(evidence, "calculator-chat.json"), JSON.stringify({ firstCodeMs, totalMs: performance.now() - started, before, after, tasksBefore, tasksAfter, inspection, answer }, null, 2));
    const state = after as Record<string, unknown>;
    const initial = before as unknown as Record<string, unknown>;
    for (const key of ["workspaces", "runs", "commands", "buffers", "approvals"]) {
      expect(state).toHaveProperty(key);
      expect(state[key]).toEqual(initial[key]);
    }
    expect(JSON.stringify(inspection)).toContain('"route":"direct"');
  } finally {
    await app.close();
  }
});
