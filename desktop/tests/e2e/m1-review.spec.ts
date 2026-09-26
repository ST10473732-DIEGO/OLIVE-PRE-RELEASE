import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, readFile, writeFile, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { record } from "./recording";
import { goHome, mainNav, openFromHome, openSpace } from "./shell";

test("M1 corrected layout, retained output, real approval cancellation and process Stop", async () => {
  const root = path.resolve("..");
  const evidence = path.join(root, ".experience-351/m1-corrections/review");
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m1-corrections-"));
  const seed = spawnSync(
    path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
    [path.join(root, "scripts/seed_electron_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const ids = JSON.parse(seed.stdout);
  const workspace = path.join(profile, "fixture-workspace");
  const treeHashes = async (): Promise<Record<string, string>> => {
    const values: Record<string, string> = {};
    const visit = async (folder: string) => {
      for (const entry of await readdir(folder, { withFileTypes: true })) {
        const file = path.join(folder, entry.name);
        if (entry.isDirectory()) await visit(file);
        else
          values[path.relative(workspace, file)] = createHash("sha256")
            .update(await readFile(file))
            .digest("hex");
      }
    };
    await visit(workspace);
    return values;
  };
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile },
  });
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(15000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const shot = async (name: string) => {
      const home = page.locator("main.home");
      if (await home.isVisible()) await expect(home).toHaveCSS("opacity", "1");
      await page.screenshot({ path: path.join(evidence, `${name}.png`) });
    };
    const nav = (name: string) =>
      page.getByRole("button", { name, exact: true }).first();
    const dimensions = () =>
      app.evaluate(({ BrowserWindow }) => {
        const w = BrowserWindow.getAllWindows()[0];
        return {
          outer: w.getSize(),
          content: w.getContentSize(),
          zoom: w.webContents.getZoomFactor(),
        };
      });
    await expect(
      page.getByText(/Ready to open/),
    ).toBeVisible({ timeout: 30000 });
    await page.evaluate(
      async (id) => window.olive.call("chat.select", { chat_id: id }),
      ids.chat_id,
    );
    await shot("00-welcome");
    await nav("Enter OLIVE").click();
    await expect(page.locator(".continue-row").first()).toBeVisible();
    const normal = await dimensions();
    await page.waitForTimeout(800); // Allow the Welcome Core handoff to settle for the still image.
    await shot("01-home-normal");
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1366, 768),
    );
    await page.waitForTimeout(400);
    const small = await dimensions();
    const recent = await page
      .locator(".home .continue-row")
      .first()
      .boundingBox();
    expect(recent).not.toBeNull();
    expect(recent!.y + recent!.height).toBeLessThanOrEqual(small.content[1]);
    await shot("02-home-1366x768");
    const composer = page.getByRole("textbox", { name: "Ask OLIVE anything" });
    const before = await composer.boundingBox();
    await composer.fill("One line\nTwo lines\nThree lines\nFour lines");
    expect((await composer.boundingBox())!.height).toBeGreaterThan(
      before!.height,
    );
    await composer.fill("");
    await app.evaluate(
      ({ BrowserWindow }, size) =>
        BrowserWindow.getAllWindows()[0].setSize(size[0], size[1]),
      normal.outer,
    );
    await goHome(page);
    // Home V2 has no launcher grid; every shipped space is a navigation row
    // and a palette entry, and unshipped ones (Contacts) are neither.
    await expect(mainNav(page).getByRole("button", { name: "Contacts", exact: true })).toHaveCount(0);
    await shot("03-home-launcher");
    await openSpace(page, "Studio");
    await nav("Fixture · local Python project").click();
    const folder = page.getByRole("treeitem", { name: "tests", exact: true });
    await expect(folder).toHaveAttribute("aria-expanded", "true");
    await folder.focus();
    await page.keyboard.press("ArrowLeft");
    await expect(
      page.getByRole("treeitem", { name: "test_main.py", exact: true }),
    ).toHaveCount(0);
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowDown");
    await expect(
      page.getByRole("treeitem", { name: "test_main.py", exact: true }),
    ).toBeFocused();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await expect(editor).toBeVisible();
    await nav("Test").click();
    await expect(
      page.locator('.task-result[data-task-state="completed"]'),
    ).toBeVisible({ timeout: 30000 });
    await expect(page.locator(".output-terminal")).toContainText("OK");
    await shot("04-studio-populated");
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("# M1 review: save preserves test output");
    await nav("Save").click();
    await expect(page.locator(".save-status")).toContainText("Saved");
    await expect(page.locator(".output-terminal")).toContainText("OK");
    await shot("05-studio-output-after-save");
    await goHome(page);
    await openSpace(page, "Studio");
    await expect(page.locator(".output-terminal")).toContainText("OK");
    await expect(editor).toBeVisible();
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1366, 768),
    );
    await page.waitForTimeout(400);
    await shot("06-studio-1366x768");
    await app.evaluate(
      ({ BrowserWindow }, size) =>
        BrowserWindow.getAllWindows()[0].setSize(size[0], size[1]),
      normal.outer,
    );
    const unchanged = await treeHashes();
    await page.getByText("Workspace actions", {exact:true}).click();
    await nav("Review tests").click();
    await expect(
      page.getByRole("heading", { name: "Your approval is needed" }),
    ).toBeVisible();
    await expect(page.locator(".approval-content")).toContainText("unittest");
    await expect(page.locator(".core-transit-stage .core")).toHaveAttribute("data-state", "Approval required");
    await expect(
      page.getByText("Technical details", { exact: true }),
    ).toBeVisible();
    expect(
      await page.locator(".approval-summary + details").getAttribute("open"),
    ).toBeNull();
    await shot("07-real-approval-collapsed");
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    await expect(
      page.locator('.task-result[data-task-state="cancelled"]'),
    ).toBeVisible();
    await expect(
      page.getByText("Test commands were not started.", { exact: true }),
    ).toBeVisible();
    expect(await treeHashes()).toEqual(unchanged);
    await shot("08-real-cancelled-task-no-change");
    const testFile = path.join(workspace, "tests/test_main.py");
    const originalTest = await readFile(testFile, "utf8");
    await writeFile(
      testFile,
      "import time, unittest\nfrom pathlib import Path\nclass Slow(unittest.TestCase):\n def test_stop(self):\n  Path('started').write_text('started')\n  time.sleep(30)\n  Path('finished').write_text('finished')\n",
    );
    const finish = await record(page, evidence);
    const recordingStart = performance.now();
    await goHome(page);
    await page.waitForTimeout(1500);
    await page.waitForTimeout(300);
    await openFromHome(page, "Chat");
    await page.waitForTimeout(1200);
    await openSpace(page, "Studio");
    await page.waitForTimeout(1000);
    await nav("Test").click();
    await expect
      .poll(
        async () =>
          await readFile(path.join(workspace, "started"), "utf8").catch(
            () => "",
          ),
      )
      .toBe("started");
    await expect(nav("Stop tests")).toBeEnabled();
    await shot("09-running-tests-stop-enabled");
    await nav("Stop tests").focus();
    await page.waitForTimeout(1500);
    await page.keyboard.press("Enter");
    await expect(
      page.locator('.task-result[data-task-state="cancelled"]'),
    ).toBeVisible();
    expect(
      await readFile(path.join(workspace, "finished"), "utf8").catch(
        () => null,
      ),
    ).toBeNull();
    await shot("10-real-stopped-tests");
    await writeFile(testFile, originalTest);
    await nav("Test").click();
    await expect(
      page.locator('.task-result[data-task-state="completed"]'),
    ).toBeVisible();
    await nav("Save").click();
    await expect(page.locator(".output-terminal")).toContainText("OK");
    await page.waitForTimeout(1000);
    await goHome(page);
    await page.waitForTimeout(1200);
    await openSpace(page, "Studio");
    await expect(page.locator(".output-terminal")).toContainText("OK");
    await page.waitForTimeout(
      Math.max(0, 26000 - (performance.now() - recordingStart)),
    );
    const recording = await finish();
    const snapshot = (await page.evaluate(() =>
      window.olive.call("runtime.snapshot", {}),
    )) as { validations: unknown[] };
    await page.reload();
    // Renderer reload retains backend validation records without replaying commands.
    await expect(
      page.getByRole("button", { name: "Enter OLIVE", exact: true }),
    ).toBeVisible();
    const restored = (await page.evaluate(() =>
      window.olive.call("runtime.snapshot", {}),
    )) as { validations: unknown[] };
    expect(restored.validations).toEqual(snapshot.validations);
    expect(errors).toEqual([]);
    await writeFile(
      path.join(evidence, "evidence.json"),
      JSON.stringify(
        {
          normal,
          small,
          recent,
          recording,
          errors,
          approvalCancelledWithoutFileChanges: true,
          stoppedBeforeMarker: true,
          outputRetainedAfterSaveAndNavigation: true,
          snapshotRetainedWithoutReplay: true,
          data: "Synthetic isolated workspace and chat; actual Python approvals and subprocesses",
          externalActions: 0,
          validations: snapshot.validations,
        },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
