import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { goHome, openSpace } from "./shell";
test("Agent shows structured fixture history, retains objectives and reaches the real offline backend", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-agent-"));
  const root = path.resolve("..");
  expect(
    spawnSync(
      path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
      [path.join(root, "scripts/seed_m2_agent_fixture.py"), profile],
      { cwd: root },
    ).status,
  ).toBe(0);
  const evidence = path.join(root, "artifacts/ui-review/M2");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Agent");
    await expect(
      page.getByRole("heading", { name: "Ready for an objective" }),
    ).toBeVisible();
    await page.screenshot({ path: path.join(evidence, "agent-idle.png") });
    await page
      .getByRole("button", { name: /Fixture: partial task record/ })
      .click();
    await expect(
      page.getByText("Not attempted", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Fixture record only; not live execution evidence.", {
        exact: true,
      }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "agent-history-fixture.png"),
    });
    await page
      .getByRole("textbox", { name: "Agent objective" })
      .fill("Explain what this local project does.");
    await goHome(page);
    await openSpace(page, "Agent");
    await expect(
      page.getByRole("textbox", { name: "Agent objective" }),
    ).toHaveValue("Explain what this local project does.");
    await page
      .getByRole("button", { name: "Start objective", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Response", exact: true }),
    ).toBeVisible({ timeout: 30000 });
    await expect(
      page.getByRole("button", { name: "Start objective", exact: true }),
    ).toBeEnabled();
    const history = (await page.evaluate(() =>
      window.olive.call("agent.history", {}),
    )) as { id: string }[];
    expect(history).toHaveLength(1);
    await page.screenshot({
      path: path.join(evidence, "agent-offline-result.png"),
    });
  } finally {
    await app.close();
  }
});
