import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

// Opt in: uses only installed local models and an isolated temporary profile.
test("LIVE LOCAL UNCENSORED event-sourcing answer retains DEEP attribution", async () => {
  test.skip(process.env.OLIVE_LIVE_AI !== "1", "Requires installed local UNCENSORED models");
  test.setTimeout(360000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-uncensored-gui-"));
  const app = await electron.launch({ chromiumSandbox: true, args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile } });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect.poll(() => page.evaluate(async () => {
      const state = await window.olive.call("runtime.snapshot", {}) as { presets: { id: string; available: boolean }[] };
      return state.presets.some(p => p.id === "uncensored" && p.available);
    }), { timeout: 30000 }).toBe(true);
    await page.getByRole("button", { name: "Find anything", exact: true }).click();
    await page.getByRole("button", { name: "Open Chat", exact: true }).click();
    await page.getByRole("combobox", { name: "OLIVE preset", exact: true }).selectOption("uncensored");
    await page.getByRole("textbox", { name: "Message OLIVE", exact: true }).fill(
      "Analyse the architectural trade-offs between event sourcing and conventional CRUD for a large distributed application.");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await expect(page.getByText("UNCENSORED · DEEP · This device", { exact: true }).last()).toBeVisible({ timeout: 300000 });
    await expect(page.getByRole("button", { name: "Stop response", exact: true })).toBeHidden({ timeout: 300000 });
    const result = await page.evaluate(async () => {
      const state = await window.olive.call("runtime.snapshot", {}) as { chat: { id: string; messages: {
        role: string; content: string; completion_state: string; provider?: { model?: string; tier?: string; preset?: string }
      }[] } };
      const answer = state.chat.messages.at(-1)!;
      const inspect = await window.olive.call("interaction.inspect", { chat_id: state.chat.id }) as {
        request_traces: { events: { stage: string; model?: string; thinking?: boolean; finish_reason?: string }[] }[]
      };
      return { answer, trace: inspect.request_traces.at(-1) };
    });
    expect(result.answer.role).toBe("assistant");
    expect(result.answer.completion_state).toBe("complete");
    expect(result.answer.content.length).toBeGreaterThan(500);
    expect(result.answer.provider).toMatchObject({ preset: "uncensored", tier: "DEEP", model: "olive-uncensored-qwen38-hauhau:latest" });
    const requests = result.trace!.events.filter(e => e.stage === "model_request");
    expect(new Set(requests.map(e => e.model)).size).toBe(1);
    expect(requests.every(e => e.thinking === false)).toBe(true);
    expect(result.trace!.events.some(e => e.stage === "model_visible_response" && e.finish_reason === "stop")).toBe(true);
    await expect(page.locator(".messages")).not.toContainText("olive-uncensored-qwen38-hauhau");
  } finally {
    await app.close();
  }
});
