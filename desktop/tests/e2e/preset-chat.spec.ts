import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";

test("LIVE LOCAL FAST NORMAL MAX DEEP FAST handoff without executing code", async () => {
  test.skip(process.env.OLIVE_LIVE_AI !== "1", "Requires installed local Ollama models");
  test.setTimeout(660000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-preset-chat-"));
  const app = await electron.launch({ args: [path.resolve(".")], env: { ...process.env, OLIVE_DATA_DIR: profile } });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Chat");
    const snapshot = () => page.evaluate(() => window.olive.call("runtime.snapshot", {})) as Promise<{
      presets: {id: string; available: boolean}[];
      chat: {model: string; messages: {role: string; content: string; completion_state: string}[]};
      workspaces: unknown[]; runs: unknown[]; activity: {items: unknown[]};
    }>;
    for (const [preset, model, prompt] of [
      ["fast", "qwen3:8b", "What is recursion? Answer in two short sentences."],
      ["normal", "gpt-oss:20b", "Explain Btrfs in two short sentences."],
      ["max", "orcarouter/Qwen3.8-27B-Uncensored:q3_K_M", "Give me Python code for a function that adds two numbers. Show the code here."],
      ["deep", "gpt-oss:20b", "Explain why a document answer needs evidence in two short sentences. No document is attached; do not invent a citation."],
      ["fast", "qwen3:8b", "Explain what a Python return statement does in two short sentences."],
    ]) {
      await expect.poll(async () => (await snapshot()).presets.find(p => p.id === preset)?.available, {timeout: 30000}).toBe(true);
      await page.getByRole("combobox", {name: "OLIVE preset"}).selectOption(preset);
      await expect.poll(async () => (await snapshot()).chat.model).toBe(model);
      const count = (await snapshot()).chat.messages.length;
      const started = Date.now();
      await page.getByRole("textbox", {name: "Message OLIVE", exact: true}).fill(prompt);
      await page.getByRole("button", {name: "Send message", exact: true}).click();
      await expect.poll(async () => {
        const s = await snapshot();
        return s.chat.messages.length > count && !s.activity.items.length && s.chat.messages.at(-1)?.role === "assistant"
          ? s.chat.messages.at(-1)!.content : "";
      }, {timeout: 300000}).toMatch(/\S.{20}/s);
      const state = await snapshot();
      expect(state.chat.messages.at(-1)?.completion_state).toBe('complete');
      console.log({ preset, model, elapsed_ms: Date.now() - started, completion: 'complete' });
      expect(state.workspaces).toEqual([]); expect(state.runs).toEqual([]);
      const resident = await (await fetch("http://127.0.0.1:11434/api/ps")).json() as { models: {name: string}[] };
      expect(resident.models.map(item => item.name)).toEqual([model]);
      if (preset === "max") await expect(page.locator('.message-assistant').last().locator('pre').first()).toBeVisible();
    }
  } finally { await app.close(); }
});
