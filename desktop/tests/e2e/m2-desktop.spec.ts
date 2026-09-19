import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { goHome, openSpace } from "./shell";
test("Desktop route stays inert until requested and Stop reaches the real backend latch", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-desktop-"));
  const evidence = path.resolve("../artifacts/ui-review/M2");
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
    await openSpace(page, "Desktop Control");
    await expect(
      page.getByRole("heading", { name: "No active application workflow" }),
    ).toBeVisible();
    const state = (await page.evaluate(() =>
      window.olive.call("desktop.status", {}),
    )) as { session: unknown; active: boolean };
    expect(state.session).toBeNull();
    expect(state.active).toBe(false);
    await page.screenshot({ path: path.join(evidence, "desktop-empty.png") });
    await page
      .getByRole("button", { name: "Emergency stop desktop control" })
      .click();
    await expect(
      page.getByText("Control stopped", { exact: true }),
    ).toBeVisible();
    expect(
      (
        (await page.evaluate(() => window.olive.call("desktop.status", {}))) as {
          stopped: boolean;
        }
      ).stopped,
    ).toBe(true);
    const cancellation = await page.evaluate(async () => {
      try {
        await window.olive.call("desktop.open_application", {
          application_id: "fixture-never-opened",
        });
        return "unexpected success";
      } catch (e) {
        return (e as Error).message;
      }
    });
    expect(cancellation).toContain("cancelled");
    await page.getByRole("button", { name: "Reset Stop", exact: true }).click();
    await expect(
      page.getByText("Control stopped", { exact: true }),
    ).toBeHidden();
    await page.getByText("Developer Details", { exact: true }).click();
    await page
      .getByRole("button", { name: "List running windows", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "OLIVE does not have permission for this action",
    );
    await page.getByRole("button", { name: "Dismiss notice" }).click();
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1366, 768),
    );
    await page.screenshot({
      path: path.join(evidence, "desktop-inspector-disabled-1366.png"),
    });
    await page
      .getByRole("textbox", { name: "Desktop objective" })
      .fill("Retained harmless fixture objective");
    await goHome(page);
    await openSpace(page, "Desktop Control");
    await expect(
      page.getByRole("textbox", { name: "Desktop objective" }),
    ).toHaveValue("Retained harmless fixture objective");
  } finally {
    await app.close();
  }
});
