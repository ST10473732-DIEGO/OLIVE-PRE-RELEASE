import { captureMail } from "./m4-capture";
import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { toggleTheme } from "./shell";

test("M4 real local Mail draft autosave, navigation and restart without a server or model", async () => {
  test.setTimeout(90000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m4-local-"));
  const evidence = path.resolve("../artifacts/ui-review/M4/local-ui");
  await mkdir(evidence, { recursive: true });
  const launch = () =>
    electron.launch({
      args: [path.resolve(".")],
      env: {
        ...process.env,
        OLIVE_DATA_DIR: profile,
        OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      },
    });
  let app = await launch();
  try {
    let page = await app.firstWindow();
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1440, 920),
    );
    const timings: Record<string, number> = {};
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    const go = async (name: string) => {
      await page
        .getByRole("button", { name: "Find anything", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Open " + name, exact: true })
        .click();
    };
    const openStart = Date.now();
    await go("Mail");
    await expect(
      page.getByRole("heading", { name: "Your inbox starts here" }),
    ).toBeVisible();
    timings.open_mail_ms = Date.now() - openStart;
    await captureMail(page, app, path.join(evidence, "mail-empty.png"));
    await page.getByRole("button", { name: "Compose", exact: true }).focus();
    await expect(
      page.getByRole("button", { name: "Compose", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await page
      .getByLabel("To", { exact: true })
      .fill("fixture@example.invalid");
    await page
      .getByLabel("Subject", { exact: true })
      .fill("M4 local acceptance fixture");
    const autosaveStart = Date.now();
    await page
      .getByLabel("Message", { exact: true })
      .fill("This synthetic draft stays local. No server is configured.");
    await expect(
      page
        .getByRole("status")
        .filter({ hasText: "Saved locally. Drafts remain" }),
    ).toBeVisible();
    timings.autosave_with_debounce_ms = Date.now() - autosaveStart;
    const result = (await page.evaluate(() =>
      window.olive.call("mail.search", { folder: "Drafts" }),
    )) as { items: { id: string; revision: number }[] };
    expect(result.items).toHaveLength(1);
    const identity = result.items[0].id;
    const stored = (await page.evaluate(
      (id) => window.olive.call("mail.get", { record_id: id }),
      identity,
    )) as { text: string; subject: string; submission_state: string };
    expect(stored.text).toContain("This synthetic draft stays local");
    expect(stored.submission_state).toBe("draft");
    await captureMail(page, app, path.join(evidence, "mail-draft.png"));
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1366, 768),
    );
    await expect(
      page.getByRole("button", { name: "Save draft", exact: true }),
    ).toBeInViewport();
    await captureMail(page, app, path.join(evidence, "composer-1366.png"));
    await toggleTheme(page);
    await captureMail(
      page,
      app,
      path.join(evidence, "composer-light-1366.png"),
    );
    await go("Settings");
    await page.getByLabel("Reduce motion", { exact: true }).check();
    await page
      .getByLabel("Text and interface size", { exact: true })
      .selectOption("1.25");
    await go("Mail");
    await expect(page.getByLabel("Message", { exact: true })).toHaveValue(
      stored.text,
    );
    await page.getByLabel("Message", { exact: true }).scrollIntoViewIfNeeded();
    await page
      .getByRole("button", { name: "Save draft", exact: true })
      .scrollIntoViewIfNeeded();
    await expect(
      page.getByRole("button", { name: "Save draft", exact: true }),
    ).toBeInViewport();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
    await captureMail(
      page,
      app,
      path.join(evidence, "composer-enlarged-light-reduced.png"),
    );
    await go("Settings");
    await page
      .getByLabel("Text and interface size", { exact: true })
      .selectOption("1");
    await page.getByLabel("Reduce motion", { exact: true }).uncheck();
    await toggleTheme(page);
    await go("Home");
    await go("Mail");
    await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
      stored.subject,
    );
    await app.close();
    app = await launch();
    page = await app.firstWindow();
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    await go("Mail");
    await page
      .getByRole("button", { name: /Drafts/ })
      .first()
      .click();
    await page
      .getByRole("button", { name: /Unsent draft M4 local acceptance fixture/ })
      .click();
    await expect(
      page.getByRole("region", { name: "Mail composer", exact: true }),
    ).toBeVisible({ timeout: 15000 });
    await writeFile(
      path.join(evidence, "reopen-label-diagnostic.json"),
      JSON.stringify(
        await page.evaluate(() => ({
          labels: [...document.querySelectorAll("label")].map(
            (l) => l.textContent,
          ),
          textareas: [...document.querySelectorAll("textarea")].map((t) => ({
            value: t.value,
            aria: t.getAttribute("aria-label"),
          })),
        })),
        null,
        2,
      ),
    );
    await expect(page.getByLabel("Message", { exact: true })).toHaveValue(
      stored.text,
    );
    const outbox = (await page.evaluate(() =>
      window.olive.call("mail.outbox", {}),
    )) as { items: unknown[] };
    expect(outbox.items).toHaveLength(0);
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Compose mail", exact: true })
      .click();
    await expect(page.getByLabel("Subject", { exact: true })).toHaveValue("");
    const previous = (await page.evaluate(
      (id) => window.olive.call("mail.get", { record_id: id }),
      identity,
    )) as { text: string };
    expect(previous.text).toBe(stored.text);
    await writeFile(
      path.join(evidence, "result.json"),
      JSON.stringify(
        {
          classification:
            "live local Electron/Python, synthetic data, model unavailable",
          profile,
          draft_id: identity,
          persisted: stored,
          outbox_count: 0,
          timings,
          visual_variants: [
            "1440x920 dark",
            "1366x768 dark/light",
            "1366x768 125% light reduced motion",
          ],
        },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
