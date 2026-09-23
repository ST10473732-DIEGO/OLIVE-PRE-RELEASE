import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, readFile, mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { openSpace, showPanel } from "./shell";

test("new named Java project saves and runs in its OLIVE projects folder", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-electron-java-"));
  await mkdir(path.join(profile, "projects"), { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile },
  });
  try {
    const page = await app.firstWindow();
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
    await openSpace(page, "Studio");
    await app.evaluate(({ dialog }, dir) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [dir] });
    }, path.join(profile, "projects"));
    await page.getByRole("button", { name: "New project", exact: true }).first().click();
    await page.locator('.language-card[data-language="java"]').click({ timeout: 120000 });
    await page.getByLabel("Project name", { exact: true }).fill("Java Fixture");
    await page.getByRole("button", { name: "Browse", exact: true }).click();
    await page.getByRole("button", { name: "Create project", exact: true }).click();
    await expect(page.locator(".wizard-done p[role=status]")).toContainText("Created", { timeout: 120000 });
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await expect(
      page.getByRole("button", { name: /Workspace: Java Fixture/ }),
    ).toBeVisible({ timeout: 30000 });
    // A harmless locally built library proves the project classpath, without downloads.
    const project = path.join(profile, "projects/Java Fixture");
    const classes = path.join(profile, "library-fixture");
    await mkdir(classes);
    await writeFile(
      path.join(classes, "Greeting.java"),
      'public class Greeting { public static String message() { return "Hello from a local library!"; } }',
    );
    const compiled = spawnSync("javac", ["Greeting.java"], {
      cwd: classes,
      encoding: "utf8",
    });
    expect(compiled.status, compiled.stderr).toBe(0);
    const packed = spawnSync(
      path.resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python"),
      [
        "-c",
        'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1],"w"); z.write("Greeting.class","Greeting.class"); z.close()',
        path.join(project, "lib/greeting.jar"),
      ],
      { cwd: classes, encoding: "utf8" },
    );
    expect(packed.status, packed.stderr).toBe(0);
    await writeFile(
      path.join(project, "Main.java"),
      "public class Main { public static void main(String[] args) { System.out.println(Greeting.message()); } }\n",
    );
    await page.getByRole("treeitem", { name: "Main.java", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await expect(editor).toBeVisible();
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("// Saved from Monaco");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect
      .poll(() =>
        readFile(path.join(profile, "projects/Java Fixture/Main.java"), "utf8"),
      )
      .toContain("// Saved from Monaco");
    await page.getByRole("button", { name: "Test", exact: true }).click();
    await expect
      .poll(() => page.locator(".output-terminal").innerText(), {
        timeout: 30000,
      })
      .toContain("Java compile");
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await showPanel(page, "Output");
    await expect
      .poll(() => page.locator(".output-terminal").innerText(), {
        timeout: 30000,
      })
      .toContain("Hello from a local library!");
    await expect(
      page.getByRole("button", { name: "Approve this action", exact: true }),
    ).toHaveCount(0);
    const evidence = path.resolve("../.experience-351/electron");
    await mkdir(evidence, { recursive: true });
    await page.screenshot({
      path: path.join(evidence, "studio-java-project.png"),
    });
  } finally {
    await app.close();
  }
});
