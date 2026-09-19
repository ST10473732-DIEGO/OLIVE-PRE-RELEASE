import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { goHome, openSpace } from "./shell";
test("Studio workspace search dirty close and retained output use the real backend", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-studio-"));
  const seed = spawnSync(
    path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
    [path.join(root, "scripts/seed_electron_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const evidence = path.join(root, "artifacts/ui-review/M2");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({
    chromiumSandbox: true,
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
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Studio");
    await page
      .getByRole("button", {
        name: "Fixture · local Python project",
        exact: true,
      })
      .click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await expect(editor).toBeVisible();
    const original = await readFile(
      path.join(profile, "fixture-workspace/main.py"),
      "utf8",
    );
    await page.getByRole("button", { name: "Test", exact: true }).click();
    await expect(
      page.locator('.task-result[data-task-state="completed"]'),
    ).toBeVisible({ timeout: 30000 });
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("# unsaved M2 fixture");
    await page
      .getByRole("button", { name: "Close main.py", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Unsaved changes" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Keep editing" }).click();
    await goHome(page);
    await openSpace(page, "Studio");
    await expect(page.locator(".output-terminal")).toContainText("OK");
    await expect(page.locator(".monaco-editor")).toContainText(
      "unsaved M2 fixture",
    );
    await page
      .getByRole("button", { name: "Close main.py", exact: true })
      .click();
    await page.getByRole("button", { name: "Discard buffer" }).click();
    await expect(
      page.getByRole("heading", { name: "Unsaved changes" }),
    ).toHaveCount(0);
    expect(
      await readFile(path.join(profile, "fixture-workspace/main.py"), "utf8"),
    ).toBe(original);
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("# saved M2 fixture");
    await page
      .getByRole("button", { name: "Close main.py", exact: true })
      .click();
    await page.getByRole("button", { name: "Save and close" }).click();
    await expect(
      page.getByRole("heading", { name: "Unsaved changes" }),
    ).toHaveCount(0);
    expect(
      await readFile(path.join(profile, "fixture-workspace/main.py"), "utf8"),
    ).toContain("saved M2 fixture");
    await page.getByText("Workspace actions", { exact: true }).click();
    await page
      .getByRole("button", { name: "Workspace tools", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Find in files", exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Find in workspace" })
      .fill("saved M2 fixture");
    await page.getByRole("button", { name: "Search files" }).click();
    await page.getByRole("button", { name: /main.py:\d+/ }).click();
    await expect(editor).toBeVisible();
    await expect(page.locator(".output-terminal")).toContainText("OK");
    await page.screenshot({
      path: path.join(evidence, "studio-workspace-tools-retention.png"),
    });
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1366, 768),
    );
    await page.screenshot({
      path: path.join(evidence, "studio-workspace-tools-1366.png"),
    });

    await page.getByText("Workspace actions", { exact: true }).click();
    await page
      .getByRole("button", { name: "Workspace tools", exact: true })
      .click();
    await page.getByRole("button", { name: "Command", exact: true }).click();
    await page
      .getByRole("textbox", { name: "Reviewed command", exact: true })
      .fill(
        process.platform === "win32" ? "Set-Content -LiteralPath 'cancelled-command.txt' -Value 'must not execute'" : "open('cancelled-command.txt', 'w').write('must not execute')",
      );
    await page
      .getByRole("button", { name: "Review command", exact: true })
      .click();
    const approval = page
      .getByRole("dialog")
      .filter({
        has: page.getByRole("heading", { name: "Your approval is needed" }),
      });
    await expect(approval).toBeVisible();
    await expect(approval.locator(".approval-content")).toContainText(
      "cancelled-command.txt",
    );
    await approval.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(approval).toHaveCount(0);
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Close", exact: true })
      .click();
    await expect(page.locator(".output-terminal")).toContainText("cancelled");
    await expect(
      readFile(path.join(profile, "fixture-workspace/cancelled-command.txt")),
    ).rejects.toThrow();
    await page.screenshot({
      path: path.join(evidence, "studio-command-cancelled-no-change.png"),
    });
    await page.getByText('Workspace actions',{exact:true}).click();await page.getByRole('button',{name:'Workspace tools',exact:true}).click();await page.getByRole('button',{name:'Command',exact:true}).click();
    await page.getByRole('textbox',{name:'Reviewed command',exact:true}).fill(process.platform === "win32" ? "Write-Output 'M2 command started'; Start-Sleep -Seconds 20; Set-Content -LiteralPath 'command-finished.txt' -Value 'unexpected'" : "import time; print('M2 command started', flush=True); time.sleep(20); open('command-finished.txt', 'w').write('unexpected')");await page.getByRole('button',{name:'Review command',exact:true}).click();await expect(approval).toBeVisible();await approval.getByRole('button',{name:'Approve this action',exact:true}).click();
    await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();await expect(page.locator('.output-terminal')).toContainText('M2 command started');await page.getByRole('button',{name:'Stop command',exact:true}).click();await expect(page.locator('.output-terminal')).toContainText('cancelled');
    await expect(readFile(path.join(profile,'fixture-workspace/command-finished.txt'))).rejects.toThrow();
    await goHome(page);await openSpace(page, 'Studio');await expect(page.locator('.output-terminal')).toContainText('M2 command started');await expect(page.locator('.output-terminal')).toContainText('cancelled');
    expect(errors).toEqual([]);
  } finally {
    await app.close();
  }
});
