import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";

// Acceptance C-J: create a project while another is open, keep both workspaces
// independent, and verify unsaved work survives switching.
test("wip multi-project journey", async () => {
  test.setTimeout(600000);
  const root = path.resolve("..");
  const evidence = path.resolve(path.join(root, "artifacts/ui-review/clarity", "multiproject"));
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-multi-"));
  const projects = path.join(profile, "projects");
  await mkdir(projects, { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      DOTNET_CLI_TELEMETRY_OPTOUT: "1",
      DOTNET_NOLOGO: "1",
      DOTNET_CLI_HOME: profile,
    },
  });
  const errors: string[] = [];
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(45000);
    page.on("pageerror", (e) => errors.push(e.message));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1600, 950));
    const shot = async (n: string) => {
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(evidence, `${n}.png`) });
    };
    const nav = page.getByRole("navigation", { name: "Main navigation" });
    // The picker returns the temp projects folder for every wizard run.
    await app.evaluate(({ dialog }, dir) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [dir] });
    }, projects);

    await expect(page.getByRole("button", { name: "Enter OLIVE", exact: true })).toBeVisible({ timeout: 60000 });
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect(page.locator("main.home")).toBeVisible();

    // B: features are reachable by visible label, no commands typed.
    for (const label of ["Studio", "Mail", "Calendar", "Contacts", "Knowledge", "Settings"])
      await expect(nav.getByRole("button", { name: label, exact: true })).toBeVisible();
    await nav.getByRole("button", { name: "Studio", exact: true }).click();

    // C: create project A (C#) through the wizard.
    const createProject = async (language: string, name: string) => {
      await page.getByRole("dialog", { name: "New project" }).waitFor();
      await page.locator(`.language-card[data-language="${language}"]`).click({ timeout: 120000 });
      await page.getByLabel("Project name", { exact: true }).fill(name);
      await page.getByRole("button", { name: "Browse", exact: true }).click();
      await expect(page.getByText(path.join(projects, name), { exact: false })).toBeVisible();
      await page.getByRole("button", { name: "Create project", exact: true }).click();
      await expect(page.locator(".wizard-done p[role=status]")).toContainText("Created", { timeout: 300000 });
      await page.getByRole("button", { name: "Done", exact: true }).click();
    };
    await page.getByRole("button", { name: "New project", exact: true }).first().click();
    await shot("01-wizard");
    await createProject("csharp", "ProjectA");
    await expect(page.getByRole("button", { name: /Workspace: ProjectA/ })).toBeVisible({ timeout: 30000 });
    await shot("02-project-a");

    // Leave an unsaved change in A.
    await page.getByRole("treeitem", { name: "Program.cs", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await expect(editor).toBeVisible();
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("// unsaved marker in A");
    await expect(page.locator(".file-tab .dirty")).toBeVisible();

    // D+E: create Python project B without closing A.
    await page.getByRole("button", { name: "New project", exact: true }).first().click();
    await createProject("python", "ProjectB");
    await expect(page.getByRole("button", { name: /Workspace: ProjectB/ })).toBeVisible({ timeout: 30000 });
    await shot("03-project-b");
    // Both projects exist on disk.
    expect((await readdir(projects)).sort()).toEqual(["ProjectA", "ProjectB"]);

    // G: switch back to A; the unsaved buffer and file are still there.
    await page.getByRole("button", { name: /Workspace: ProjectB/ }).click();
    await page.getByRole("dialog", { name: "Workspaces" }).getByRole("button", { name: "ProjectA", exact: true }).click();
    await expect(page.getByRole("button", { name: /Workspace: ProjectA/ })).toBeVisible();
    await expect(page.locator(".monaco-editor .view-lines")).toContainText("unsaved marker in A", { timeout: 30000 });
    await expect(page.locator(".file-tab .dirty")).toBeVisible();
    await shot("04-back-in-a-unsaved");

    // H: switch to B again; it kept its own separate state.
    await page.getByRole("button", { name: /Workspace: ProjectA/ }).click();
    await page.getByRole("dialog", { name: "Workspaces" }).getByRole("button", { name: "ProjectB", exact: true }).click();
    await expect(page.getByRole("button", { name: /Workspace: ProjectB/ })).toBeVisible();
    // B never had a file open, so it shows its own empty state rather than A's
    // buffer: the two sessions do not share view state.
    await expect(page.locator(".editor-empty")).toBeVisible();
    await expect(page.locator(".file-tab")).toHaveCount(0);
    await shot("05-back-in-b");

    // J: cancelling a wizard changes nothing.
    await page.getByRole("button", { name: "New project", exact: true }).first().click();
    await page.getByLabel("Project name", { exact: true }).fill("Cancelled");
    await page.getByRole("dialog", { name: "New project" }).getByRole("button", { name: "Cancel", exact: true }).click();
    expect((await readdir(projects)).sort()).toEqual(["ProjectA", "ProjectB"]);
    await expect(page.getByRole("button", { name: /Workspace: ProjectB/ })).toBeVisible();
    await shot("06-after-cancel");
    expect(errors).toEqual([]);
  } finally {
    await app.close();
  }
});
