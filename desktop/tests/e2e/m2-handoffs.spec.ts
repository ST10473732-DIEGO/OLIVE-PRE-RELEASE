import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace } from "./shell";
test("Projects open actual linked contexts and Developer Mode changes only presentation", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-handoff-"));
  const seed = spawnSync(
    path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
    [path.join(root, "scripts/seed_m2_handoff_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
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
    page.setDefaultTimeout(15000);
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    const nav = page.getByRole("navigation", { name: "Main navigation" });
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page
      .getByRole("button", { name: "New OLIVE Project (group related work)", exact: true })
      .click();
    await expect(
      page.getByRole("textbox", { name: "Project title", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Close", exact: true })
      .click();
    const project = async () => {
      await openSpace(page, "Projects");
      await page
        .getByRole("button", { name: /Fixture linked project/ })
        .click();
    };
    await project();
    await page
      .getByRole("button", { name: "Continue in Chat", exact: true })
      .click();
    await expect(page.locator(".conversation")).toContainText(
      "Fixture context",
    );
    await project();
    await page
      .getByRole("navigation", { name: "Project relationships" })
      .getByRole("button", { name: "Tasks", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Continue in Agent", exact: true })
      .click();
    await expect(
      page
        .locator("p")
        .filter({ hasText: /^Fixture linked task \(no execution\)$/ }),
    ).toBeVisible();
    await project();
    await page
      .getByRole("navigation", { name: "Project relationships" })
      .getByRole("button", { name: "Research", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Continue in Research", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Fixture report", exact: true }),
    ).toBeVisible();
    await project();
    await page
      .getByRole("navigation", { name: "Project relationships" })
      .getByRole("button", { name: "Memories", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Continue in Memory", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toContainText(
      "Fixture project prefers outcome-based tests.",
    );
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Close", exact: true })
      .click();
    await project();
    await page
      .getByRole("navigation", { name: "Project relationships" })
      .getByRole("button", { name: "Knowledge", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Continue in Knowledge", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toContainText(
      "Fixture linked conversation",
    );
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Close", exact: true })
      .click();
    const before = await page.evaluate(() =>
      window.olive.call("data.permissions", {}),
    );
    await openSpace(page, "Settings");
    await page
      .getByRole("textbox", { name: "Search settings" })
      .fill("developer");
    await page
      .getByRole("navigation", { name: "Settings categories" })
      .getByRole("button", { name: "Appearance", exact: true })
      .click();
    await page
      .getByRole("switch", { name: "Developer Mode", exact: true })
      .check();
    await expect(
      nav.getByRole("button", { name: "Diagnostics", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(() => window.olive.call("data.permissions", {})),
    ).toEqual(before);
    await nav.getByRole("button", { name: "Diagnostics", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Diagnostics", exact: true }),
    ).toBeVisible();
    const evidence = path.join(root, "artifacts/ui-review/M2");
    await mkdir(evidence, { recursive: true });
    await page.screenshot({
      path: path.join(evidence, "settings-developer-diagnostics.png"),
    });
  } finally {
    await app.close();
  }
});
