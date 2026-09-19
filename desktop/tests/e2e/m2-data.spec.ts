import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { record } from "./recording";
test("isolated Projects Memory and Knowledge CRUD persists and retains route state", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-data-"));
  const source = path.join(profile, "Fixture-source.txt");
  await writeFile(
    source,
    "Fixture document. A blue notebook is stored on the library shelf. Local retrieval should find the notebook.",
  );
  const evidence = path.resolve("../artifacts/ui-review/M2");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    const stopRecording = await record(
      page,
      path.join(evidence, "data-navigation"),
      "m2-data-navigation.mp4",
    );
    const go = async (feature: string) => {
      await page
        .getByRole("button", { name: "Find anything", exact: true })
        .click();
      await page
        .getByRole("button", { name: `Open ${feature}`, exact: true })
        .click();
    };
    await go("Projects");
    await expect(
      page.getByRole("heading", { name: "Choose a project" }),
    ).toBeVisible();
    await expect(page.getByText("No projects yet. Create a project to bring your work together.", {exact:true})).toBeVisible();
    await expect(page.getByText("Loading projects…", {exact:true})).toHaveCount(0);
    await page.screenshot({ path: path.join(evidence, "projects-empty.png") });
    await page
      .getByRole("button", { name: "New project", exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Project title" })
      .fill("Fixture · M2 local project");
    await page
      .getByRole("textbox", { name: "Description" })
      .fill("Isolated review fixture. No private data.");
    await page
      .getByRole("button", { name: "Create project", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Fixture · M2 local project" }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "projects-populated-fixture.png"),
    });
    await go("Memory");
    await expect(
      page.getByRole("heading", { name: "Keep what matters" }),
    ).toBeVisible();
    await page.screenshot({ path: path.join(evidence, "memory-empty.png") });
    await page.getByRole("button", { name: "Add memory", exact: true }).click();
    await page
      .getByRole("textbox", { name: "Memory", exact: true })
      .fill("Fixture · prefer concise local project notes.");
    await page
      .getByRole("button", { name: "Save memory", exact: true })
      .click();
    await expect(
      page.getByText("Fixture · prefer concise local project notes.", {
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("textbox", { name: "Search memories" })
      .fill("Fixture");
    await page.waitForTimeout(1500);
    await page.screenshot({
      path: path.join(evidence, "memory-populated-fixture.png"),
    });
    await go("Home");
    await go("Memory");
    await page.waitForTimeout(1500);
    await expect(
      page.getByRole("textbox", { name: "Search memories" }),
    ).toHaveValue("Fixture");
    await go("Knowledge");
    await expect(
      page.getByRole("heading", { name: "Build on what you know" }),
    ).toBeVisible();
    await page.screenshot({ path: path.join(evidence, "knowledge-empty.png") });
    // Only the native picker is a test double. The chosen fixture is imported by real Python services.
    await app.evaluate(({ dialog }, file) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [file],
      });
    }, source);
    await page.getByRole("button", { name: "Add source", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Fixture-source.txt", exact: true }),
    ).toBeVisible({ timeout: 30000 });
    await page
      .getByRole("button", { name: "Retrieval inspector", exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Retrieval query" })
      .fill("blue notebook library");
    await page
      .getByRole("button", { name: "Inspect retrieval", exact: true })
      .click();
    await expect(page.getByText("Score", { exact: false }).first()).toBeVisible(
      { timeout: 30000 },
    );
    await page.keyboard.press("Escape");
    await page.screenshot({
      path: path.join(evidence, "knowledge-populated-fixture.png"),
    });
    await page.waitForTimeout(1500);
    await page.getByRole("button", { name: "Re-index", exact: true }).click();
    await expect
      .poll(async () => {
        const jobs = (await page.evaluate(() =>
          window.olive.call("knowledge.jobs", {}),
        )) as { state: string }[];
        return (
          jobs.length > 0 && jobs.every((job) => job.state === "completed")
        );
      })
      .toBe(true);
    const replacement = path.join(profile, "Fixture-relinked.txt");
    await writeFile(replacement, await readFile(source));
    await app.evaluate(({ dialog }, file) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [file],
      });
    }, replacement);
    await page.getByRole("button", { name: "Relink", exact: true }).click();
    await expect
      .poll(async () => {
        const sources = (await page.evaluate(() =>
          window.olive.call("knowledge.list", {}),
        )) as { original_path: string }[];
        return sources[0]?.original_path.toLowerCase();
      })
      .toBe(replacement.toLowerCase());
    await page.getByText("Index maintenance", { exact: true }).click();
    await page
      .getByRole("button", { name: "Upgrade lexical indexes", exact: true })
      .click();
    await expect(
      page.getByText(
        "Blocked / unavailable",
        { exact: true },
      ),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "knowledge-offline-upgrade.png"),
    });
    await page.getByRole("button", { name: "Remove", exact: true }).click();
    await page
      .getByRole("button", { name: "Remove source", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Build on what you know" }),
    ).toBeVisible();
    expect(await readFile(source, "utf8")).toContain("blue notebook");
    await go("Projects");
    await expect(
      page.getByRole("heading", { name: "Fixture · M2 local project" }),
    ).toBeVisible();
    await page.waitForTimeout(1500);
    await writeFile(
      path.join(evidence, "data-recording.json"),
      JSON.stringify(await stopRecording(), null, 2),
    );
    await page.reload();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await go("Memory");
    await expect(
      page.getByText("Fixture · prefer concise local project notes.", {
        exact: true,
      }),
    ).toBeVisible();
  } finally {
    await app.close();
  }
});
