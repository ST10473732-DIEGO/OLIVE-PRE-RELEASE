import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { goHome, openSpace, toggleTheme } from "./shell";

test("isolated responsive appearance, keyboard, sandbox and reload evidence", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-electron-visual-"));
  const evidence = path.resolve("../.experience-351/electron");
  await mkdir(evidence, { recursive: true });
  const started = performance.now();
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile },
  });
  try {
    const page = await app.firstWindow();
    await expect(
      page.getByRole("button", { name: "Enter OLIVE", exact: true }),
    ).toBeVisible();
    const startupMs = performance.now() - started;
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("textbox", { name: "Ask OLIVE anything" }),
    ).toBeVisible();
    const options = await app.evaluate(({ BrowserWindow }) =>
      (
        BrowserWindow.getAllWindows()[0].webContents as unknown as {
          getLastWebPreferences: () => Record<string, boolean>;
        }
      ).getLastWebPreferences(),
    );
    expect(options.nodeIntegration).toBe(false);
    expect(options.contextIsolation).toBe(true);
    expect(options.sandbox).toBe(true);
    expect(options.webSecurity).toBe(true);
    expect(
      await page.evaluate(
        () => typeof (window as unknown as { require?: unknown }).require,
      ),
    ).toBe("undefined");
    expect(await page.evaluate(() => Object.keys(window.olive).sort())).toEqual([
      "attachFiles",
      "browser",
      "call",
      "chooseDirectory",
      "copyText",
      "fileAction",
      "onBrowserAsk",
      "onBrowserState",
      "onPreviewClosed",
      "openExternal",
      "openWorkspace",
      "preview",
      "setInterfaceScale",
      "stopControl",
      "subscribe",
    ]);
    expect(
      await page.evaluate(async () => {
        try {
          await window.olive.call("agent.tool" as never, {} as never);
          return false;
        } catch {
          return true;
        }
      }),
    ).toBe(true);
    expect(
      await page.evaluate(async () => {
        try {
          await window.olive.openExternal("javascript:alert(1)");
          return false;
        } catch {
          return true;
        }
      }),
    ).toBe(true);
    const navigation: number[] = [];
    for (const size of [
      [1366, 768],
      [1920, 1080],
    ]) {
      await app.evaluate(
        ({ BrowserWindow }, size) =>
          BrowserWindow.getAllWindows()[0].setContentSize(size[0], size[1]),
        size,
      );
      const before = performance.now();
      // Navigation is always visible; opening a feature is one labelled click.
      await openSpace(page, "Knowledge");
      navigation.push(performance.now() - before);
      await page.screenshot({
        path: path.join(evidence, `navigation-${size[0]}.png`),
      });
      await goHome(page);
    }
    await toggleTheme(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(page.locator("main.home")).toHaveCSS("opacity", "1");
    await page.screenshot({ path: path.join(evidence, "home-light.png") });
    await page.keyboard.press("Control+Shift+P");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "OLIVE activity" }).click();
    await page.getByRole("checkbox", { name: "Reduced motion" }).check();
    await expect(page.locator("html")).toHaveAttribute("data-reduced", "true");
    await page.screenshot({
      path: path.join(evidence, "activity-light-reduced.png"),
    });
    await page.keyboard.press("Escape");
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1.25),
    );
    await page.screenshot({
      path: path.join(evidence, "home-text-zoom-125.png"),
    });
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1.5),
    );
    await page.screenshot({
      path: path.join(evidence, "home-text-zoom-150.png"),
    });
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1),
    );
    await openSpace(page, "Chat");
    await page
      .getByRole("textbox", { name: "Message OLIVE" })
      .fill("Retain this draft across renderer refresh.");
    await page.waitForTimeout(500);
    const before = (await page.evaluate(
      async () => await window.olive.call("runtime.snapshot", {}),
    )) as { chat: { id: string; messages: unknown[] } };
    await page.reload();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Chat");
    await expect(
      page.getByRole("textbox", { name: "Message OLIVE" }),
    ).toHaveValue("Retain this draft across renderer refresh.");
    const after = (await page.evaluate(
      async () => await window.olive.call("runtime.snapshot", {}),
    )) as { chat: { id: string; messages: unknown[] } };
    expect(after.chat.id).toBe(before.chat.id);
    expect(after.chat.messages).toEqual(before.chat.messages);
    const processes = await app.evaluate(({ app }) =>
      app
        .getAppMetrics()
        .map((m) => ({ type: m.type, memory: m.memory, cpu: m.cpu })),
    );
    const rss = spawnSync(
      path.resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python"),
      [
        "-c",
        'import psutil,json,sys; p=psutil.Process(int(sys.argv[1])); rows=[p,*p.children(recursive=True)]; print(json.dumps({"rssMiB":sum(x.memory_info().rss for x in rows if x.is_running())/1048576,"processCount":len(rows)}))',
        String(app.process().pid),
      ],
      { encoding: "utf8" },
    );
    await writeFile(
      path.join(evidence, "visual-security-metrics.json"),
      JSON.stringify(
        {
          evidence: "LIVE LOCAL isolated Electron",
          startupMs,
          navigationAutomationMs: navigation,
          processes,
          combinedRss: rss.status === 0 ? JSON.parse(rss.stdout) : null,
          zoomIsNotOSDpi: true,
          physicalGpuUsage: "NOT MEASURED",
          sandbox: true,
          reloadPreservedDraft: true,
          noActionReplay: true,
        },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
