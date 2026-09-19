import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace } from "./shell";
test("Studio Git review keeps approval binding and dirty history protection", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-git-"));
  const seed = spawnSync(
    path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
    [path.join(root, "scripts/seed_electron_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const workspace = path.join(profile, "fixture-workspace");
  const git = (...args: string[]) => {
    const result = spawnSync("git", args, {
      cwd: workspace,
      encoding: "utf8",
      windowsHide: true,
    });
    expect(result.status, result.stderr).toBe(0);
    return result.stdout;
  };
  git("init", "--initial-branch=fixture-main");
  git("config", "user.name", "OLIVE fixture");
  git("config", "user.email", "fixture@example.invalid");
  git("add", "main.py", "tests/test_main.py");
  git("commit", "-m", "Fixture baseline");
  await writeFile(
    path.join(workspace, "main.py"),
    'print("Fixture Git change")\n',
  );
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
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Studio");
    await page
      .getByRole("button", {
        name: "Fixture · local Python project",
        exact: true,
      })
      .click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    const tools = async () => {
      await page.getByText("Workspace actions", { exact: true }).click();
      await page
        .getByRole("button", { name: "Workspace tools", exact: true })
        .click();
    };
    await tools();
    await page.getByRole("button", { name: "Refresh Git status" }).click();
    await expect(page.getByRole("dialog")).toContainText(
      "Branch: fixture-main",
      { timeout: 20000 },
    );
    await page
      .getByRole("button", { name: "Working changes", exact: true })
      .click();
    await expect(page.getByRole("dialog").locator("pre").first()).toContainText(
      "Fixture Git change",
      { timeout: 20000 },
    );
    const approval = page
      .getByRole("dialog")
      .filter({
        has: page.getByRole("heading", { name: "Your approval is needed" }),
      });
    await page
      .getByRole("button", { name: "Review staging selected file" })
      .click();
    await expect(approval).toBeVisible();
    await approval.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(git("diff", "--cached")).toBe("");
    await expect(page.getByRole("dialog")).toContainText(
      "cancelled before execution",
    );
    await page
      .getByRole("button", { name: "Review staging selected file" })
      .click();
    await expect(approval).toBeVisible();
    await approval
      .getByRole("button", { name: "Approve this action", exact: true })
      .click();
    await expect
      .poll(() => git("diff", "--cached"), { timeout: 20000 })
      .toContain("Fixture Git change");
    await page.getByText("Commit staged changes", { exact: true }).click();
    await page
      .getByRole("textbox", { name: "Commit message" })
      .fill("Fixture reviewed commit");
    await page
      .getByRole("button", { name: "Review commit", exact: true })
      .click();
    await expect(approval).toBeVisible();
    await approval
      .getByRole("button", { name: "Approve this action", exact: true })
      .click();
    await expect
      .poll(() => git("log", "-1", "--format=%s").trim(), { timeout: 20000 })
      .toBe("Fixture reviewed commit");
    await page
      .getByRole("button", { name: "Recent commits", exact: true })
      .click();
    await expect(
      page
        .getByRole("dialog")
        .getByText("Fixture reviewed commit", { exact: true }),
    ).toBeVisible({ timeout: 20000 });
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Close", exact: true })
      .click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("# dirty fixture buffer");
    await tools();
    await page.getByText("Create or switch branch", { exact: true }).click();
    await page
      .getByRole("textbox", { name: "Branch name" })
      .fill("fixture-other");
    await page
      .getByRole("button", { name: "Review new branch", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toContainText(
      "unsaved editor buffers before changing workspace history",
    );
    await expect(approval).toHaveCount(0);
    expect(git("branch", "--show-current").trim()).toBe("fixture-main");
  } finally {
    await app.close();
  }
});
