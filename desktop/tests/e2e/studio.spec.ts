import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { record } from "./recording";
import { goHome, openSpace } from "./shell";

test("direct Monaco save and test need no duplicate approval and retain conflict checks", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-electron-studio-"));
  const seeded = spawnSync(
    path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
    [path.join(root, "scripts/seed_electron_fixture.py"), profile],
    { cwd: root, encoding: "utf8" },
  );
  expect(seeded.status, seeded.stderr).toBe(0);
  const evidence = path.join(root, ".experience-351/electron");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({
    chromiumSandbox: true,
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" },
  });
  try {
    const page = await app.firstWindow();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const finishRecording = await record(page, evidence);
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect(
      page.getByText("Fixture · a small Python idea", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "home-populated-fixture.png"),
    });
    await openSpace(page, "Chat");
    await expect(
      page.getByText("Start with one clear behaviour and a test."),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "chat-populated-fixture.png"),
    });
    await openSpace(page, "Studio");
    await page
      .getByRole("button", {
        name: "Fixture · local Python project",
        exact: true,
      })
      .click();
    const approvals: unknown[] = [];
    await page.exposeFunction("recordApproval", (value: unknown) =>
      approvals.push(value),
    );
    await page.evaluate(() =>
      window.olive.subscribe((event) => {
        if (event.topic === "approval")
          void (
            window as unknown as {
              recordApproval: (v: unknown) => Promise<void>;
            }
          ).recordApproval(event.data);
      }),
    );
    try {
      await page
        .getByRole("treeitem", { name: "main.py", exact: true })
        .click();
      const editor = page.getByRole("textbox", { name: "Source editor" });
      await expect(editor).toBeVisible();
      await editor.press("Control+End");
      await editor.press("Enter");
      await editor.pressSequentially("# Edited in the real Monaco editor", {
        delay: 5,
      });
      await goHome(page);
      await openSpace(page, "Studio");
      await expect(
        page
          .getByText("# Edited in the real Monaco editor", { exact: false })
          .first(),
      ).toBeVisible();
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect
        .poll(
          async () =>
            await readFile(
              path.join(profile, "fixture-workspace/main.py"),
              "utf8",
            ),
        )
        .toContain("# Edited in the real Monaco editor");
      await page.getByRole("button", { name: "Test", exact: true }).click();
      await expect
        .poll(
          async () => ({
            output: await page.locator(".output-terminal").innerText(),
            notice: await page.locator(".toast").allTextContents(),
          }),
          { timeout: 30000 },
        )
        .toMatchObject({ output: expect.stringContaining("OK") });
      await expect(page.locator(".toast")).toHaveCount(0);
      await page.screenshot({
        path: path.join(evidence, "studio-monaco-output.png"),
      });
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect(page.locator(".save-status")).toContainText("Saved");
      await expect(page.locator(".output-terminal")).toContainText("OK");
      await goHome(page);
      await openSpace(page, "Studio");
      await expect(page.locator(".output-terminal")).toContainText("OK");
      await expect(editor).toBeVisible();
      const recording = await finishRecording();
      await page.getByRole("button", { name: "Run", exact: true }).click();
      await expect(page.locator('.terminal-view:not([hidden])')).toContainText("Hello, OLIVE!", { timeout: 15000 });
      await page.getByRole("button", { name: "Show Output", exact: true }).click();
      await expect
        .poll(() => page.locator(".output-terminal").innerText(), {
          timeout: 15000,
        })
        .toContain("Hello, OLIVE!");
      await page.screenshot({
        path: path.join(evidence, "studio-run-output.png"),
      });
      await editor.press("Control+End");
      await editor.press("Enter");
      await editor.pressSequentially("# Unsaved human edit");
      const diskFile = path.join(profile, "fixture-workspace/main.py");
      const external =
        (await readFile(diskFile, "utf8")) + "\n# Simulated agent disk edit\n";
      await writeFile(diskFile, external);
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect(page.locator('.toast[role="alert"]')).toBeVisible();
      expect(await readFile(diskFile, "utf8")).toBe(external);
      await page.getByRole("button", { name: "Compare", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "Disk version ↔ your editor" }),
      ).toBeVisible();
      await page.screenshot({
        path: path.join(evidence, "studio-conflict-comparison.png"),
      });
      await page
        .getByRole("button", { name: "Close comparison", exact: true })
        .click();
      expect(errors).toEqual([]);
      await writeFile(
        path.join(evidence, "studio-result.json"),
        JSON.stringify(
          {
            evidence: "LIVE LOCAL synthetic workspace",
            saved: true,
            testsPassed: true,
            conflictProtected: true,
            errors,
            recording,
          },
          null,
          2,
        ),
      );
    } finally {
      expect(approvals).toEqual([]);
    }
  } finally {
    // This fixture deliberately ends with a conflicting dirty buffer. Exercise
    // the normal close guard with an explicit synthetic discard response.
    await app.evaluate(({ dialog }) => {
      dialog.showMessageBox = async (windowOrOptions: Electron.BaseWindow | Electron.MessageBoxOptions, providedOptions?: Electron.MessageBoxOptions) => {
        const options = providedOptions || (windowOrOptions as Electron.MessageBoxOptions);
        if (!options || !["Studio has unsaved changes.", "The Python runtime is unavailable."].includes(options.message))
          throw new Error("Unexpected teardown confirmation");
        return { response: 1, checkboxChecked: false };
      };
    });
    await app.close();
  }
});
