import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { goHome, openSpace } from "./shell";
test("Settings uses Python validation, retains drafts, updates Monaco preferences and shows diagnostics", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-settings-"));
  const workspace = path.join(profile, "Fixture-workspace");
  await mkdir(workspace);
  await writeFile(
    path.join(workspace, "main.py"),
    '# Fixture: editor settings\nprint("local fixture")\n',
  );
  const evidence = path.resolve("../artifacts/ui-review/M2");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile },
  });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Open Settings", exact: true })
      .click();
    const nav = page.getByRole("navigation", { name: "Settings categories" });
    await expect(nav).toBeVisible();
    await page
      .getByLabel("Text and interface size", { exact: true })
      .selectOption("1.25");
    await expect
      .poll(() =>
        app.evaluate(({ BrowserWindow }) =>
          BrowserWindow.getAllWindows()[0].webContents.getZoomFactor(),
        ),
      )
      .toBe(1.25);
    await page.waitForTimeout(250); // Capture the compositor after the explicit zoom change.
    const scaledCapture=await app.evaluate(async({BrowserWindow})=>(await BrowserWindow.getAllWindows()[0].webContents.capturePage()).toPNG().toString("base64"));
    await writeFile(path.join(evidence,"settings-125-percent.png"),Buffer.from(scaledCapture,"base64"));
    const invalidScale = await page.evaluate(async () => {
      try {
        await window.olive.setInterfaceScale(0.5);
        return false;
      } catch {
        return true;
      }
    });
    expect(invalidScale).toBe(true);
    await page.getByText("Workspace layout", { exact: true }).click();
    await page
      .getByRole("button", { name: "Reset navigation layout and size" })
      .click();
    await page
      .getByLabel("Studio explorer size", { exact: true })
      .press("Home");
    for (let i = 0; i < 13; i++)
      await page
        .getByLabel("Studio explorer size", { exact: true })
        .press("ArrowRight");
    await expect
      .poll(() =>
        app.evaluate(({ BrowserWindow }) =>
          BrowserWindow.getAllWindows()[0].webContents.getZoomFactor(),
        ),
      )
      .toBe(1);

    await nav.getByRole("button", { name: "Studio", exact: true }).click();
    await page.getByLabel("Editor font size", { exact: true }).fill("18");
    await goHome(page);
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Open Settings", exact: true })
      .click();
    await expect(
      page.getByLabel("Editor font size", { exact: true }),
    ).toHaveValue("18");
    await page
      .getByRole("button", { name: "Save settings", exact: true })
      .click();
    await expect(
      page.getByText("Settings saved to the shared runtime.", { exact: true }),
    ).toBeVisible();
    expect(
      JSON.parse(await readFile(path.join(profile, "settings.json"), "utf8"))
        .editor_size,
    ).toBe(18);
    const rejected = await page.evaluate(async () => {
      const value = (await window.olive.call("data.settings", {})) as {
        chat_id: string;
      };
      try {
        await window.olive.call("data.save_settings", {
          chat_id: value.chat_id,
          settings: { editor_size: 200 },
          params: {},
          system_prompt: "",
        });
        return false;
      } catch {
        return true;
      }
    });
    expect(rejected).toBe(true);
    await page.getByLabel("Search settings").fill("OCR");
    await expect(
      page.getByLabel("OCR executable", { exact: false }),
    ).toBeVisible();
    await nav.getByRole("button", { name: "OCR", exact: true }).click();
    // Cancelling the native picker cannot create a backup or change the selected OCR path.
    await app.evaluate(({ dialog }) => {
      dialog.showOpenDialog = async () => ({ canceled: true, filePaths: [] });
    });
    await page.getByRole("button", { name: "Choose OCR executable" }).click();
    await expect(
      page.getByLabel("OCR executable", { exact: true }),
    ).toHaveValue("");
    await nav.getByRole("button", { name: "Permissions", exact: true }).click();
    await expect(
      page.getByRole("combobox", { name: "filesystem.write", exact: true }),
    ).toHaveValue("ask");
    await page.screenshot({
      path: path.join(evidence, "settings-permissions-1440.png"),
    });
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1366, 768),
    );
    await nav.getByRole("button", { name: "Research", exact: true }).click();
    await expect(page.getByLabel("Search limit", { exact: true })).toHaveValue(
      "3",
    );
    await page.screenshot({
      path: path.join(evidence, "settings-research-1366.png"),
    });
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Open Diagnostics", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Copy diagnostics" }),
    ).toBeEnabled({ timeout: 30000 });
    await page.screenshot({
      path: path.join(evidence, "diagnostics-1366.png"),
    });
    const exported = path.join(profile, "fixture-diagnostics.json");
    await app.evaluate(({ dialog }, file) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
    }, exported);
    await page
      .getByRole("button", { name: "Export diagnostics", exact: true })
      .click();
    await expect
      .poll(async () =>
        JSON.parse(await readFile(exported, "utf8").catch(() => "{}")),
      )
      .not.toEqual({});
    await app.evaluate(({ dialog }, folder) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [folder],
      });
    }, workspace);
    await openSpace(page, "Studio");
    await page
      .getByRole("button", { name: "Open Workspace", exact: true })
      .click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    await expect(page.locator(".explorer")).toHaveCSS("width", "280px");
    await expect
      .poll(() =>
        page
          .locator(".monaco-editor .view-lines")
          .first()
          .evaluate((node) => getComputedStyle(node).fontSize),
      )
      .toBe("18px");
    expect(await page.evaluate(() => Object.keys(window.olive).sort())).toEqual(
      [
        "setInterfaceScale",
      "attachFiles",
      "browser",
        "call",
        "copyText",
      "fileAction",
      "onBrowserAsk",
        "onBrowserState",
        "onPreviewClosed",
        "openExternal",
        "openWorkspace",
        "chooseDirectory",
        "preview",
        "stopControl",
        "subscribe",
      ].sort(),
    );
  } finally {
    await app.close();
  }
});
