import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace } from "./shell";

test("window resizing reflows Home Chat and Studio while retaining editor content", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-responsive-"));
  expect(
    spawnSync(
      path.join(root, ".venv/Scripts/python.exe"),
      [path.join(root, "scripts/seed_electron_fixture.py"), profile],
      { cwd: root },
    ).status,
  ).toBe(0);
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile },
  });
  const evidence = path.join(root, ".experience-351/responsive");
  await mkdir(evidence, { recursive: true });
  try {
    const page = await app.firstWindow();
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(640, 480),
    );
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect
      .poll(
        () =>
          page.evaluate(async () =>
            Boolean(await window.olive.call("runtime.snapshot", {})),
          ),
        { timeout: 30000 },
      )
      .toBe(true);
    await page.screenshot({ path: path.join(evidence, "home-640.png") });
    await openSpace(page, "Chat");
    const composer = page.getByRole("textbox", { name: "Message OLIVE" });
    await composer.fill("A retained resize draft");
    await expect(composer).toBeInViewport();
    await page
      .getByRole("button", { name: "Conversation history", exact: true })
      .click();
    await expect(
      page.getByRole("textbox", { name: "Search conversations" }),
    ).toBeVisible();
    await page.screenshot({ path: path.join(evidence, "chat-640.png") });
    await page
      .getByRole("button", { name: "Close conversation history", exact: true })
      .click();
    await openSpace(page, "Studio");
    await page
      .getByRole("button", {
        name: "Fixture · local Python project",
        exact: true,
      })
      .click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("# Preserved through resizing");
    // The tool dock is on-demand; open Output so it reflows with the window.
    await page.getByRole("button", { name: "Show Output", exact: true }).click();
    for (const [width, height] of [
      [1920, 1080],
      [1366, 768],
      [900, 600],
      [640, 480],
      [1600, 900],
    ]) {
      await app.evaluate(
        ({ BrowserWindow }, size) =>
          BrowserWindow.getAllWindows()[0].setSize(size[0], size[1]),
        [width, height],
      );
      await expect(
        page.getByRole("button", { name: "Save", exact: true }),
      ).toBeInViewport();
      await expect(
        page.getByRole("button", { name: "Run", exact: true }),
      ).toBeInViewport();
      await expect(
        page.getByRole("button", { name: "Stop program", exact: true }),
      ).toBeInViewport();
      await expect
        .poll(() =>
          page
            .locator(".editor-host")
            .evaluate((element) => element.getBoundingClientRect().width),
        )
        .toBeGreaterThan(180);
      await expect
        .poll(() =>
          page
            .locator(".editor-host")
            .evaluate((element) => element.getBoundingClientRect().height),
        )
        .toBeGreaterThan(65);
      await expect(page.locator(".studio-dock")).toBeInViewport();
      await expect(
        page
          .getByText("# Preserved through resizing", { exact: false })
          .first(),
      ).toBeVisible();
      await page.screenshot({
        path: path.join(evidence, `studio-${width}.png`),
      });
    }
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Approve this action", exact: true }),
    ).toHaveCount(0);
    await openSpace(page, "Chat");
    await expect(composer).toHaveValue("A retained resize draft");
  } finally {
    await app.close();
  }
});
