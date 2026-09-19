import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { goHome, openSpace } from "./shell";

test("real isolated Electron welcomes, enters, navigates and retains one window", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-electron-"));
  const evidence = path.resolve("../.experience-351/electron");
  await mkdir(evidence, { recursive: true });
  const started = performance.now();
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile },
  });
  try {
    const page = await app.firstWindow();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await expect(
      page.getByRole("button", { name: "Enter OLIVE", exact: true }),
    ).toBeVisible();
    const welcomeMs = performance.now() - started;
    await page.screenshot({ path: path.join(evidence, "welcome.png") });
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect(
      page.getByRole("textbox", { name: "Ask OLIVE anything" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Submit request" }),
    ).toBeDisabled();
    await expect
      .poll(
        () =>
          page.evaluate(async () => {
            try {
              return Boolean(await window.olive.call("runtime.snapshot", {}));
            } catch {
              return false;
            }
          }),
        { timeout: 30000 },
      )
      .toBe(true);
    await page.screenshot({ path: path.join(evidence, "home-empty.png") });
    await page.screenshot({ path: path.join(evidence, "home-launcher.png") });
    await openSpace(page, "Chat");
    await expect(
      page.getByRole("textbox", { name: "Message OLIVE" }),
    ).toBeVisible();
    await page
      .getByRole("textbox", { name: "Message OLIVE" })
      .fill("An unsent local draft");
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(evidence, "chat-empty.png") });
    await openSpace(page, "Studio");
    await expect(
      page.getByRole("button", { name: "Open Workspace", exact: true }),
    ).toBeVisible({ timeout: 30000 });
    await page.screenshot({ path: path.join(evidence, "studio-empty.png") });
    await openSpace(page, "Chat");
    await expect(
      page.getByRole("textbox", { name: "Message OLIVE" }),
    ).toHaveValue("An unsent local draft");
    await goHome(page);
    await expect(
      page.getByRole("button", { name: "Enter OLIVE", exact: true }),
    ).toHaveCount(0);
    expect(app.windows()).toHaveLength(1);
    expect(errors).toEqual([]);
    await writeFile(
      path.join(evidence, "launch-metrics.json"),
      JSON.stringify(
        {
          evidence: "LIVE LOCAL isolated Electron",
          welcomeMs,
          errors,
          profileStoredInEvidence: false,
        },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
