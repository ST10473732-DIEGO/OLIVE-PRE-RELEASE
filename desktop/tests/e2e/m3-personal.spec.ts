import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { toggleTheme } from "./shell";

test("M3 real offline native forms persist through renderer reload", async () => {
  test.setTimeout(180000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m3-native-"));
  const evidence =
    process.env.OLIVE_M3_EVIDENCE ||
    path.resolve("../artifacts/ui-review/M3/forms-" + Date.now());
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
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1440, 920),
    );
    const dimensions: unknown[] = [],
      navigationTimings: unknown[] = [];
    const capture = async (options: { path: string }) => {
      await page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all(
          document
            .getAnimations()
            .filter((a) =>
              Number.isFinite(a.effect?.getComputedTiming().endTime),
            )
            .map((a) => a.finished.catch(() => undefined)),
        );
        // Native capturePage can otherwise return the compositor frame from
        // before a just-completed scroll. Wait for browser paint, not a sleep.
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        );
      });
      dimensions.push({
        screen: path.basename(options.path),
        layout: await page.evaluate(() => ({
          width: innerWidth,
          height: innerHeight,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        })),
        window: await app.evaluate(({ BrowserWindow }) =>
          BrowserWindow.getAllWindows()[0].getBounds(),
        ),
      });
      const png = await app.evaluate(async ({ BrowserWindow }) =>
        (await BrowserWindow.getAllWindows()[0].capturePage())
          .toPNG()
          .toString("base64"),
      );
      await writeFile(options.path, Buffer.from(png, "base64"));
    };
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    const go = async (name: string) => {
      const started = performance.now();
      await page
        .getByRole("button", { name: "Find anything", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Open " + name, exact: true })
        .click();
      if (name === "Home")
        await expect(
          page.getByRole("textbox", { name: "Ask OLIVE anything", exact: true }),
        ).toBeVisible();
      else
        await expect(
          page.getByRole("heading", { name, exact: true }),
        ).toBeVisible();
      navigationTimings.push({
        route: name,
        toVisibleHeadingMs: Math.round(performance.now() - started),
      });
    };
    // The removed presentation is not restored to satisfy old navigation tests.
    const identity = await page.evaluate(() => window.olive.call("profile.get", {}));
    const legacy = await page.evaluate(() => window.olive.call("contacts.create", {body:{display_name:"Alex Synthetic"}})) as {id:string};
    await go("Settings");
    await page.getByRole("navigation", {name:"Settings categories"}).getByRole("button", {name:"General",exact:true}).click();
    await expect(page.getByRole("textbox", {name:"Preferred name",exact:true})).toHaveValue("Diego");
    await capture({path:path.join(evidence,"general-preferences.png")});
    await go("Calendar");
    await page.getByRole("button", { name: "New Event", exact: true }).click();
    await page
      .getByRole("textbox", { name: "Event title", exact: true })
      .fill("M3 Synthetic Event");
    await page.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(
      page.getByRole("button", { name: /M3 Synthetic Event/ }),
    ).toBeVisible();
    for (const view of ["Month", "Week", "Agenda"]) {
      await page.getByRole("button", { name: view, exact: true }).click();
      await capture({
        path: path.join(evidence, "calendar-" + view.toLowerCase() + ".png"),
      });
    }
    await go("Tasks");
    await page.getByRole("button", { name: "New Task", exact: true }).click();
    await page
      .getByRole("textbox", { name: "Task title", exact: true })
      .fill("M3 Synthetic Task");
    await page
      .getByLabel("Task due", { exact: true })
      .fill(new Date().toISOString().slice(0, 10));
    await page.getByRole("button", { name: "Save Task", exact: true }).click();
    await expect(
      page.getByRole("button", { name: /M3 Synthetic Task.*normal/ }),
    ).toBeVisible();
    await capture({ path: path.join(evidence, "tasks.png") });
    await go("Reminders");
    await page
      .getByRole("button", { name: "New Reminder", exact: true })
      .click();
    await page
      .getByLabel("Reminder domain", { exact: true })
      .selectOption("task");
    await page
      .getByLabel("Reminder target", { exact: true })
      .selectOption({ label: "M3 Synthetic Task" });
    await page
      .getByLabel("Explicit reminder time", { exact: true })
      .fill("2026-01-01T10:00");
    await page
      .getByRole("button", { name: "Save Reminder", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Dismiss", exact: true }),
    ).toBeVisible({ timeout: 15000 });
    await capture({ path: path.join(evidence, "reminder.png") });
    await page.getByRole("button", { name: "Dismiss", exact: true }).click();
    await expect(page.getByText(/dismissed/).first()).toBeVisible();
    await go("Home");
    await expect(
      page.getByRole("region", { name: "Native Today" }),
    ).toBeVisible();
    await expect(
      page
        .getByRole("region", { name: "Native Today" })
        .getByText("M3 Synthetic Task", { exact: true }),
    ).toBeVisible();
    await capture({ path: path.join(evidence, "home-native.png") });
    await page.reload();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    expect(await page.evaluate(() => window.olive.call("profile.get", {}))).toEqual(identity);
    expect(await page.evaluate(id => window.olive.call("contacts.get", {record_id:id}),legacy.id)).toMatchObject({display_name:"Alex Synthetic"});
    await go("Settings");
    await page.getByRole("navigation", {name:"Settings categories"}).getByRole("button", {name:"General",exact:true}).click();
    await expect(page.getByRole("textbox", {name:"Preferred name",exact:true})).toHaveValue("Diego");
    await app.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].setSize(1366,768));
    await go("Calendar");
    await expect(
      page.getByRole("button", { name: /M3 Synthetic Event/ }),
    ).toBeVisible();
    await capture({ path: path.join(evidence, "calendar-1366.png") });
    await toggleTheme(page);
    await capture({ path: path.join(evidence, "calendar-light-1366.png") });
    await go("Home");
    await capture({ path: path.join(evidence, "home-light-1366.png") });
    await page
      .getByRole("region", { name: "Native Today" })
      .getByText("M3 Synthetic Task", { exact: true })
      .scrollIntoViewIfNeeded();
    await expect(
      page
        .getByRole("region", { name: "Native Today" })
        .getByText("M3 Synthetic Task", { exact: true }),
    ).toBeInViewport({ ratio: 1 });
    await capture({ path: path.join(evidence, "home-today-1366.png") });
    await go("Settings");
    await page.getByRole("navigation", {name:"Settings categories"}).getByRole("button", {name:"Appearance",exact:true}).click();
    await page.getByLabel("Reduce motion", { exact: true }).check();
    await page
      .getByLabel("Text and interface size", { exact: true })
      .selectOption("1.25");
    await go("Tasks");
    await capture({path:path.join(evidence,"tasks-enlarged-light.png")});
    await page.getByRole("button", {name:"New Task",exact:true}).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("textbox", {name:"Task title",exact:true})).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", {name:"New Task",exact:true})).not.toBeVisible();
    await go("Calendar");
    await page.getByRole("button", { name: "Agenda", exact: true }).click();
    await capture({
      path: path.join(evidence, "agenda-enlarged-reduced-motion.png"),
    });
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page
      .getByRole("button", { name: "New task", exact: true })
      .click();
    await expect(
      page.getByRole("textbox", { name: "Task title", exact: true }),
    ).toBeVisible();
    await writeFile(
      path.join(evidence, "result.json"),
      JSON.stringify(
        {
          classification:
            "live local Electron forms, real Python services; Ollama configured unavailable",
          profile,
          passed: true,
          dimensions,
          navigationTimings,
          approvals:
            "Ordinary explicit form consent only; no permission state injected",
        },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
