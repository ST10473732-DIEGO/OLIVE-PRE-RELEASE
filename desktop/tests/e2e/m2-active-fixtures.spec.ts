import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";

test("controlled work fixtures exercise real Agent pause/cancel, desktop Stop and suggestion review", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-active-"));
  const shim = path.join(profile, "test-runtime");
  await mkdir(shim);
  // A test-only Python startup shim injects inert work. No product fixture API or policy bypass.
  await writeFile(
    path.join(shim, "sitecustomize.py"),
    `import sys, runpy\nsys.path.insert(0, ${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/m2_active_runtime.py"))})\n`,
  );
  const evidence = path.join(root, "artifacts/ui-review/M2-closeout");
  await mkdir(evidence, {recursive:true});
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      PYTHONPATH: shim,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    const go = async (name: string) => {
      await page
        .getByRole("button", { name: "Find anything", exact: true })
        .click();
      await page
        .getByRole("button", { name: `Open ${name}`, exact: true })
        .click();
    };
    await go("Agent");
    await expect(
      page.getByRole("heading", { name: "Active task", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Pause after current tool" })
      .click();
    await expect(
      page.getByRole("button", { name: "Resume task" }),
    ).toBeVisible();
    await expect(page.getByText('Pausing',{exact:true})).toBeVisible();
    await page.screenshot({path:path.join(evidence,'agent-pausing-controlled-fixture.png')});
    await expect.poll(()=>page.evaluate(async()=>(await window.olive.call('agent.current',{}) as {pause_state:string}).pause_state)).toBe('paused');
    await expect(page.getByText('This Agent task is paused. Other activity keeps the global state working.',{exact:true})).toBeVisible();
    await expect(page.locator(".core-transit-stage .core")).toHaveAttribute("data-state", "Working");
    await page.screenshot({
      path: path.join(evidence, "agent-active-paused-controlled-fixture.png"),
    });
    await go("Home");
    await go("Agent");
    await page.getByRole("button", { name: "Resume task" }).click();
    await expect(
      page.getByRole("button", { name: "Pause after current tool" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cancel Agent task" }).click();
    await expect(
      page.getByText(
        "Fixture wait cancelled. No tools or external actions executed.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(page.locator(".core-transit-stage .core")).toHaveAttribute("data-state", "Working");
    await go("Chat");
    // The legacy active fixture remains cancellable from the shared activity UI.
    await page.getByRole("button", { name: "OLIVE activity", exact: true }).click();
    await page.getByRole("button", { name: "Stop desktop control", exact: true }).click();
    await expect.poll(async () => (await page.evaluate(() => window.olive.call("desktop.status", {})) as {stopped:boolean}).stopped).toBe(true);
    await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();
    await go("Memory");
    await page.getByRole("button", { name: "Suggestions (2)" }).click();
    const cards = page.getByRole("dialog").locator(".record-card");
    await cards
      .first()
      .getByRole("textbox")
      .fill("Fixture corrected preference");
    await cards.first().getByRole("button", { name: "Approve memory" }).click();
    await expect(cards).toHaveCount(1);
    await cards
      .first()
      .getByRole("button", { name: "Reject", exact: true })
      .click();
    await expect(
      page.getByText("No pending suggestions.", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Close", exact: true })
      .click();
    await expect(
      page.getByText("Fixture corrected preference", { exact: true }),
    ).toBeVisible();
    const memories = (await page.evaluate(() =>
      window.olive.call("data.memories", {}),
    )) as { content: string; source_chat_id: string }[];
    expect(memories).toHaveLength(1);
    expect(memories[0].source_chat_id).toBeTruthy();
  } finally {
    await app.close();
  }
});
