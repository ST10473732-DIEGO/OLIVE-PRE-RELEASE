import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { goHome, openSpace } from "./shell";

test("Research retains evidence, denies source saving and reads inert fixture downloads", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-research-"));
  const root = path.resolve("..");
  expect(
    spawnSync(
      path.join(root, ".venv/Scripts/python.exe"),
      [path.join(root, "scripts/seed_m2_research_fixture.py"), profile],
      { cwd: root },
    ).status,
  ).toBe(0);
  const evidence = path.join(root, "artifacts/ui-review/M2");
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
    await openSpace(page, "Research");
    await expect(
      page.getByText("Illustrative review data, not live research evidence.", {
        exact: true,
      }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "research-findings-fixture.png"),
    });
    await page
      .getByRole("button", { name: "Sources and evidence (1)" })
      .click();
    await page.getByRole("button", { name: "Save read web sources" }).click();
    const approval = page.getByRole("dialog").filter({has:page.getByRole("button",{name:/Deny|Cancel/,exact:false})});
    await expect(
      approval
        .getByText("https://example.invalid/fixture-testing", { exact: true })
        .first(),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "research-source-approval-fixture.png"),
    });
    await approval
      .getByRole("button", { name: /Deny|Cancel/, exact: false })
      .first()
      .click();
    await expect(approval).toBeHidden();
    expect(
      await page.evaluate(() => window.olive.call("research.web_sources", {})),
    ).toEqual([]);
    await page.getByRole("dialog", {name:"Research history"}).getByRole("button", {name:"Close",exact:true}).click();
    await page.getByRole("alert").getByRole("button").click();
    await openSpace(page, "Research");
    await page
      .getByRole("textbox", { name: "Research question" })
      .fill("A retained fixture question");
    await goHome(page);
    await openSpace(page, "Research");
    await expect(
      page.getByRole("textbox", { name: "Research question" }),
    ).toHaveValue("A retained fixture question");
    await page
      .getByText("Website learning and saved material", { exact: true })
      .click();
    await page.getByRole("button", { name: "Downloads", exact: true }).click();
    await page
      .getByRole("button", { name: "Read document", exact: true })
      .click();
    await expect(
      page.getByText(
        "Clearly labelled inert download fixture. No network request was made.",
        { exact: true },
      ),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "research-download-fixture.png"),
    });
    await page.getByRole("dialog").filter({has:page.getByText("Plain text from the saved source; embedded content does not execute.", {exact:true})}).getByRole("button",{name:"Close",exact:true}).click();
    await openSpace(page, "Research");
    await page
      .getByRole("button", { name: "New investigation", exact: true })
      .click();
    await page.screenshot({ path: path.join(evidence, "research-empty.png") });
  } finally {
    await app.close();
  }
});
