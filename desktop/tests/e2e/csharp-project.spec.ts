import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp, readFile, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { openSpace } from "./shell";

test("C# starter edits and runs through Studio and presentation omits implementation captions", async () => {
  test.setTimeout(120000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-csharp-"));
  const evidence = path.resolve("../artifacts/core/studio-cleanup");
  await mkdir(evidence, { recursive: true });
  await mkdir(path.join(profile, "projects"), { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      DOTNET_CLI_TELEMETRY_OPTOUT: "1",
      DOTNET_SKIP_FIRST_TIME_EXPERIENCE: "1",
      DOTNET_CLI_HOME: profile,
    },
  });
  try {
    const page = await app.firstWindow();
    await expect(
      page.getByRole("button", { name: "Enter OLIVE", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("YOUR IDEAS. YOUR TOOLS. YOUR SPACE."),
    ).toHaveCount(0);
    await page.screenshot({ path: path.join(evidence, "welcome.png") });
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    await openSpace(page, "Studio");
    await app.evaluate(({ dialog }, dir) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [dir] });
    }, path.join(profile, "projects"));
    await page.getByRole("button", { name: "New project", exact: true }).first().click();
    // Toolchain discovery is bounded but real: a cold .NET CLI home rebuilds
    // its template cache before `dotnet new list` answers.
    await expect(page.locator('.language-card[data-language="csharp"]')).toBeEnabled({
      timeout: 120000,
    });
    await page.locator('.language-card[data-language="csharp"]').click();
    await page.getByLabel("Project name", { exact: true }).fill("CSharp Fixture");
    await page.getByRole("button", { name: "Browse", exact: true }).click();
    await page.getByRole("button", { name: "Create project", exact: true }).click();
    await expect(page.locator(".wizard-done p[role=status]")).toContainText("Created", { timeout: 300000 });
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await expect(
      page.getByRole("button", { name: /Workspace: CSharp Fixture/ }),
    ).toBeVisible({ timeout: 30000 });
    await page
      .getByRole("treeitem", { name: "Program.cs", exact: true })
      .click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await expect(editor).toBeVisible();
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("// Edited in Studio");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect
      .poll(() =>
        readFile(
          path.join(profile, "projects/CSharp Fixture/Program.cs"),
          "utf8",
        ),
      )
      .toContain("// Edited in Studio");
    await expect(page.locator(".save-status")).not.toBeEmpty();
    await expect(
      page.getByText("Monaco · local assets", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByText("Workspace access controlled by Python", { exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await page.getByRole("button", { name: "Show Output", exact: true }).click();
    const runs = () =>
      page.evaluate(
        async () =>
          (
            (await window.olive.call("runtime.snapshot", {})) as {
              runs: {
                state: string;
                stdout: string;
                stderr: string;
                exit_code: number;
              }[];
            }
          ).runs,
      );
    await expect
      .poll(
        async () =>
          (await runs()).some((r) =>
            ["completed", "failed", "timed_out"].includes(r.state),
          ),
        { timeout: 60000 },
      )
      .toBe(true);
    const run = (await runs()).at(-1)!;
    await writeFile(
      path.join(evidence, "run.json"),
      JSON.stringify(run, null, 2),
    );
    expect(run, run.stderr).toMatchObject({ state: "completed", exit_code: 0 });
    expect(run.stdout).toContain("Hello, World!");
    await expect
      .poll(() => page.locator(".output-terminal").innerText(), {
        timeout: 60000,
      })
      .toContain("Hello, World!");
    await page.screenshot({ path: path.join(evidence, "csharp-running.png") });
  } finally {
    await app.close();
  }
});
