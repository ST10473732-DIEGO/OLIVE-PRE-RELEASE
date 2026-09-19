import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { record } from "../e2e/recording";

// Captures the same representative screens with the same synthetic fixture and
// window sizes so before/after evidence is comparable. Isolated profile only.
// Edge cases: long titles/paths/addresses, Unicode, many rows, big code blocks,
// tables, empty lists, validation and offline errors, cancelled operations.
test("capture representative screens", async () => {
  test.setTimeout(900000);
  const root = path.resolve("..");
  const label = process.env.OLIVE_CAPTURE_LABEL || "capture";
  const evidence = path.resolve(
    process.env.OLIVE_CAPTURE_DIR ||
      path.join(root, "artifacts/ui-review/redesign", label),
  );
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-redesign-capture-"));
  const seed = spawnSync(
    path.join(root, ".venv/Scripts/python.exe"),
    [path.join(root, "scripts/seed_visual_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const ids = JSON.parse(seed.stdout) as {
    chat_id: string;
    workspace_id: string;
    long_chat_id: string;
    long_workspace_id: string;
  };
  const startedAt = performance.now();
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  const timings: Record<string, number> = {};
  const errors: string[] = [];
  const overflow: Record<string, unknown> = {};
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push("console: " + message.text());
    });
    const size = async (w: number, h: number) => {
      await app.evaluate(
        ({ BrowserWindow }, s) =>
          BrowserWindow.getAllWindows()[0].setContentSize(s[0], s[1]),
        [w, h],
      );
      await page.waitForTimeout(350);
    };
    const settle = async () => {
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
        await new Promise<void>((r) =>
          requestAnimationFrame(() => requestAnimationFrame(() => r())),
        );
      });
    };
    // Accidental overflow: elements extending past the viewport that are not
    // inside a scroll container, plus any page-wide horizontal scrollbar.
    const overflowCheck = async () =>
      page.evaluate(() => {
        const width = document.documentElement.clientWidth;
        const scrolls = (node: Element | null) => {
          while (node && node !== document.body) {
            const style = getComputedStyle(node);
            if (/(auto|scroll|hidden|clip)/.test(style.overflowX + style.overflow))
              return true;
            node = node.parentElement;
          }
          return false;
        };
        const offenders: string[] = [];
        for (const element of document.querySelectorAll("body *")) {
          if (element.closest(".core-transit-stage,.monaco-editor,.xterm")) continue;
          const rect = element.getBoundingClientRect();
          if (rect.width === 0 || rect.height === 0) continue;
          if (rect.right > width + 1 && !scrolls(element.parentElement)) {
            const el = element as HTMLElement;
            offenders.push(
              `${el.tagName.toLowerCase()}.${String(el.className).split(" ").filter(Boolean).slice(0, 2).join(".")} right=${Math.round(rect.right)}`,
            );
            if (offenders.length > 12) break;
          }
        }
        return {
          pageScrollX: document.documentElement.scrollWidth > width + 1,
          appScrollX: (document.querySelector(".app")?.scrollWidth || 0) > width + 1,
          offenders,
        };
      });
    const shot = async (name: string) => {
      await page.waitForTimeout(250);
      await settle();
      const png = await app.evaluate(async ({ BrowserWindow }) =>
        (await BrowserWindow.getAllWindows()[0].capturePage())
          .toPNG()
          .toString("base64"),
      );
      await writeFile(
        path.join(evidence, `${name}.png`),
        Buffer.from(png, "base64"),
      );
      overflow[name] = await overflowCheck();
    };
    const button = (name: string) =>
      page.getByRole("button", { name, exact: true }).first();
    const spine = page.getByRole("navigation", { name: "Main navigation" });
    const go = async (name: string) => {
      const started = performance.now();
      await button("Find anything").click();
      await button("Open " + name).click();
      await page.waitForTimeout(200);
      timings["navigate:" + name] = Math.round(performance.now() - started);
    };
    await size(1440, 900);
    await expect(
      page.getByText(/Ready to open/),
    ).toBeVisible({ timeout: 60000 });
    timings.startupToReadyMs = Math.round(performance.now() - startedAt);
    await page.evaluate(
      async (id) => window.olive.call("chat.select", { chat_id: id }),
      ids.chat_id,
    );
    // Synthetic personal data through the same authorised services the UI uses.
    await page.evaluate(async () => {
      type R = { id: string; revision?: number; default_calendar?: string };
      const profile = (await window.olive.call("profile.get", {})) as R;
      await window.olive
        .call("profile.update", {
          record_id: profile.id,
          revision: profile.revision || 1,
          body: { display_name: "Synthetic Reviewer" },
        })
        .catch(() => undefined);
      const project = (await window.olive.call("data.create_project", {
        title: "Fixture · Garden planner",
      })) as R;
      const longProject = (await window.olive.call("data.create_project", {
        title:
          "Fixture · a project with an unusually long title that should wrap gracefully in lists and selects",
      })) as R;
      const alex = (await window.olive.call("contacts.create", {
        body: {
          display_name: "Alex Synthetic",
          emails: [
            { value: "alex@example.invalid", label: "work" },
            { value: "alexandra.synthetic.personal.mailbox@a-rather-long-domain-name.example.invalid", label: "home" },
          ],
          phones: [{ value: "+27 21 555 0100", label: "mobile" }],
          organization: "Fixture Studio",
          project_ids: [project.id],
          notes: "Prefers mornings.\nSecond line of notes with Unicode: café, 東京, 🌱.",
        },
      })) as R;
      const sam = (await window.olive.call("contacts.create", {
        body: {
          display_name: "Sam Fixture",
          emails: [{ value: "sam@example.invalid", label: "home" }],
        },
      })) as R;
      const names = [
        "Zoë Ångström-Lindqvist de la Fuente y Rodríguez",
        "李 小龙",
        "Ahmed al-Rashid",
        "Q",
        "A person whose display name is genuinely far longer than any reasonable column width would allow",
        "María José",
        "Björk",
        "Oluwaseun Adebayo-Williams",
        "Nguyễn Thị Minh Khai",
        "Ivan Petrov",
        "Chidi Okonkwo",
        "Yuki Tanaka",
        "Priya Raghunathan",
        "Lars Nielsen",
        "Fatima Zahra",
        "Kwame Mensah",
        "Sofia Rossi",
        "Hans Müller",
        "Aisha Bello",
        "Diego Álvarez",
        "Mei Wong",
        "Tomás Ferreira",
        "Anya Kowalski",
        "Ravi Shankar",
        "Emeka Obi",
        "Leila Haddad",
        "Noah Cohen",
        "Ingrid Svensson",
      ];
      for (const [index, name] of names.entries())
        await window.olive.call("contacts.create", {
          body: {
            display_name: name,
            emails: [{ value: `person${index}@example.invalid`, label: "other" }],
            organization: index % 3 === 0 ? "Very Long Organisation Name Incorporated (Synthetic)" : "",
          },
        });
      const day = new Date();
      const iso = (d: Date, h: number) =>
        `${d.toISOString().slice(0, 10)}T${String(h).padStart(2, "0")}:00`;
      const plus = (n: number) => new Date(day.getTime() + n * 86400000);
      const events: [Date, number, number, string, Record<string, unknown>][] = [
        [day, 10, 11, "Design review", { project_id: project.id, contact_ids: [alex.id] }],
        [day, 9, 10, "Stand-up", {}],
        [day, 12, 13, "Lunch with the whole greenhouse irrigation firmware working group (long)", {}],
        [day, 14, 15, "1:1", {}],
        [day, 16, 17, "Retro", {}],
        [plus(1), 14, 16, "Focus block · Studio", {}],
        [plus(3), 9, 10, "Coffee with Sam", { contact_ids: [sam.id] }],
        [plus(5), 8, 18, "All-hands offsite planning session with an exceptionally long title 東京", {}],
      ];
      for (const [d, s, e, title, extra] of events)
        await window.olive.call("calendar.create", {
          body: { calendar_id: profile.default_calendar, title, start: iso(d, s), end: iso(d, e), ...extra },
        });
      const task = (await window.olive.call("tasks.create", {
        body: { title: "Write planting schedule", project_id: project.id, due: day.toISOString().slice(0, 10) },
      })) as R;
      const taskTitles = [
        ["Order seeds", "high", 2],
        ["Read soil report", "normal", 0],
        ["Fix the drip emitter on bed-07 which has been leaking since the last cold snap and needs a new washer", "high", 1],
        ["Call the nursery", "low", 4],
        ["Update firmware notes", "normal", 6],
        ["Renew tool insurance", "low", 9],
        ["Prune tomatoes", "normal", 1],
        ["Check pH", "high", 0],
        ["Label seed trays (東京 batch)", "normal", 3],
        ["Archive last season's logs", "low", 12],
        ["Compost turnover", "normal", 2],
        ["Buy shade cloth", "low", 7],
        ["Repair fence", "high", 5],
      ] as const;
      for (const [title, priority, offset] of taskTitles)
        await window.olive
          .call("tasks.create", {
            body: { title, priority, due: offset ? plus(offset).toISOString().slice(0, 10) : "" },
          })
          .catch(() => undefined);
      const done = (await window.olive.call("tasks.create", { body: { title: "Water the ferns" } })) as R;
      await window.olive
        .call("tasks.complete", { record_id: done.id, revision: done.revision || 1 })
        .catch(() => undefined);
      await window.olive
        .call("reminders.create", {
          body: { target_kind: "task", target_id: task.id, at: iso(plus(1), 9) + ":00" },
        })
        .catch(() => undefined);
      await window.olive.call("mail.save_draft", {
        body: {
          to: ["alex@example.invalid"],
          subject: "Garden planner · next steps",
          text: "Hi Alex,\n\nHere is the planting schedule draft we discussed. Nothing has been sent; this is a local draft.\n\n— Synthetic Reviewer",
          project_id: project.id,
        },
      });
      await window.olive.call("mail.save_draft", {
        body: {
          to: [
            "sam@example.invalid",
            "alexandra.synthetic.personal.mailbox@a-rather-long-domain-name.example.invalid",
            "person3@example.invalid",
            "person4@example.invalid",
          ],
          cc: ["person5@example.invalid", "person6@example.invalid"],
          subject:
            "Re: Fwd: [greenhouse] Irrigation controller firmware — scheduling model revision, emitter replacement and the 東京 batch labels (long subject)",
          text: "Sam,\n\nA longer local draft with several paragraphs.\n\n" +
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. ".repeat(6) +
            "\n\nhttps://example.invalid/documentation/irrigation/controllers/firmware/v2/scheduling-model/appendix/very-long-path-segment-that-does-not-break/index.html\n\n— Synthetic Reviewer",
          project_id: longProject.id,
        },
      });
      await window.olive.call("mail.save_draft", { body: { to: [], subject: "", text: "" } });
    });
    await shot("00-welcome-1440");
    await button("Enter OLIVE").click();
    await expect(page.locator("main.home")).toBeVisible();
    await page.waitForTimeout(900);
    await shot("01-home-1440");
    await button("Open activity centre").click();
    await shot("02-activity-sheet");
    await page.keyboard.press("Escape");
    await button("Find anything").click();
    await shot("03-command-palette");
    await page.keyboard.press("Escape");
    await spine.getByRole("button", { name: "All Spaces", exact: true }).click();
    await shot("04-all-spaces");
    await go("Chat");
    await expect(page.locator(".messages")).toBeVisible();
    await shot("05-chat");
    // Long conversation: big code block, wide table, Unicode, long URL.
    await page.getByRole("button", { name: /deliberately long conversation title/ }).click();
    await expect(page.locator(".messages")).toContainText("Weekly schedule");
    await page.locator(".messages").evaluate((node) => {
      node.scrollTop = 0;
    });
    await shot("05a-chat-long-content-top");
    await page.locator(".messages").evaluate((node) => {
      node.scrollTop = 900;
    });
    await shot("05b-chat-long-content");
    await page.locator(".messages").evaluate((node) => {
      node.scrollTop = node.scrollHeight;
    });
    await shot("05c-chat-long-content-end");
    // Real offline error: regenerate without a local model produces a toast.
    await page.getByRole("button", { name: "Regenerate response" }).click();
    await expect(page.locator(".toast")).toBeVisible({ timeout: 15000 });
    await shot("05d-chat-offline-error-toast");
    await page.getByRole("button", { name: "Dismiss notice" }).click();
    await go("Agent");
    await shot("06-agent");
    await go("Studio");
    await shot("06b-studio-empty");
    await button("Fixture · local Python project").click();
    await shot("06c-studio-no-file-open");
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    await expect(
      page.getByRole("textbox", { name: "Source editor" }),
    ).toBeVisible();
    const t = performance.now();
    await button("Test").click();
    await expect(
      page.locator('.task-result[data-task-state="completed"]'),
    ).toBeVisible({ timeout: 60000 });
    timings.studioTestToCompletedMs = Math.round(performance.now() - t);
    await shot("07-studio");
    // Monaco typing: 60 characters dispatched as fast as the driver allows.
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await editor.press("Control+End");
    await editor.press("Enter");
    const typingStarted = performance.now();
    await editor.pressSequentially("# capture: sixty characters typed into the real editor here", { delay: 0 });
    timings.monacoType60CharsMs = Math.round(performance.now() - typingStarted);
    await expect(page.locator(".monaco-editor")).toContainText("sixty characters");
    // A real approval from the backend (Review tests), then cancelled.
    await page.getByText("Workspace actions", { exact: true }).click();
    await button("Review tests").click();
    await expect(page.getByRole("heading", { name: "Your approval is needed" })).toBeVisible();
    await shot("07b-studio-approval");
    await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.locator('.task-result[data-task-state="cancelled"]')).toBeVisible();
    await shot("07c-studio-cancelled-tests");
    await page.getByRole("button", { name: "Close main.py", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Unsaved changes" })).toBeVisible();
    await shot("07d-studio-unsaved-sheet");
    await page.getByRole("button", { name: "Discard buffer" }).click();
    // Long workspace title, deep path, long file name and the tools sheet.
    await page.getByText("Workspace actions", { exact: true }).click();
    await button("Workspace tools").click();
    await shot("07e-studio-workspace-tools");
    await page.keyboard.press("Escape");
    await spine.getByRole("button", { name: "Home", exact: true }).click();
    await page
      .getByRole("button", { name: /greenhouse irrigation controller firmware.*Workspace/ })
      .first()
      .click();
    await page.getByRole("treeitem", { name: /a_very_long_module_name/ }).click();
    await expect(page.locator(".monaco-editor")).toContainText("Long path fixture");
    await shot("07f-studio-long-paths");
    await go("Research");
    await shot("08-research");
    await go("Desktop Control");
    await shot("09-desktop-control");
    await go("Projects");
    await shot("10-projects");
    await page.getByRole("button", { name: /unusually long title/ }).first().click();
    await shot("10b-projects-long-title");
    await go("Knowledge");
    await shot("11-knowledge");
    await go("Memory");
    await shot("12-memory");
    await go("Contacts");
    await page.getByRole("button", { name: /Alex Synthetic/ }).first().click();
    await shot("13-contacts");
    await page.getByRole("button", { name: /A person whose display name/ }).first().click();
    await shot("13b-contacts-long-name");
    // Validation error on a real form: invalid email is rejected by Python.
    await button("Add Contact").click();
    await page.getByRole("textbox", { name: "Contact name", exact: true }).fill("Invalid Email Fixture");
    await page.getByRole("button", { name: /Add email/i }).click().catch(() => undefined);
    const emailField = page.getByRole("dialog").getByRole("textbox", { name: /email/i }).first();
    if (await emailField.count()) await emailField.fill("not-an-email");
    await button("Save Contact").click();
    await page.waitForTimeout(500);
    await shot("13c-contacts-validation-error");
    await page.keyboard.press("Escape");
    await go("Calendar");
    await shot("14-calendar-month");
    await button("Week").click();
    await shot("15-calendar-week");
    await button("Agenda").click();
    await shot("16-calendar-agenda");
    await button("Month").click();
    await go("Tasks");
    await shot("17-tasks");
    await button("All").click();
    await shot("17b-tasks-all");
    await go("Reminders");
    await shot("18-reminders");
    await go("Mail");
    await page.waitForTimeout(400);
    await shot("19-mail");
    await page.getByRole("button", { name: /^Drafts/ }).first().click();
    await page.waitForTimeout(300);
    await shot("19b-mail-drafts");
    await page.getByRole("button", { name: /Garden planner/ }).first().click();
    await page.waitForTimeout(300);
    await shot("20-mail-thread");
    await page.getByRole("button", { name: /Irrigation controller firmware/ }).first().click();
    await page.waitForTimeout(300);
    await shot("20b-mail-long-draft");
    // Without a configured connection the review action is honestly disabled.
    if (await button("Review submission").isEnabled()) {
      await button("Review submission").click();
      await page.waitForTimeout(600);
      await shot("20c-mail-review-submission");
      await page.keyboard.press("Escape");
      await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click().catch(() => undefined);
    }
    await button("Compose").click().catch(() => undefined);
    await page.waitForTimeout(300);
    await shot("21-mail-compose");
    await go("Profile");
    await shot("22-profile");
    await go("Settings");
    await shot("23-settings");
    await page
      .getByRole("navigation", { name: "Settings categories" })
      .getByRole("button", { name: "Connections", exact: true })
      .click();
    await page.waitForTimeout(300);
    await shot("24-settings-connections");
    await page
      .getByRole("navigation", { name: "Settings categories" })
      .getByRole("button", { name: "Permissions", exact: true })
      .click();
    await page.waitForTimeout(300);
    await shot("24b-settings-permissions");
    await page.getByRole("textbox", { name: "Search settings" }).fill("motion");
    await page.waitForTimeout(300);
    await shot("24c-settings-search");
    await page.getByRole("textbox", { name: "Search settings" }).fill("");
    // Keyboard-only: palette by shortcut, type, Tab, Enter.
    await page.keyboard.press("Control+Shift+P");
    await page.keyboard.type("open calen");
    await page.keyboard.press("Tab");
    await shot("25-keyboard-palette-focus");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Calendar", exact: true })).toBeVisible();
    await spine.getByRole("button", { name: "Home", exact: true }).focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await shot("25b-keyboard-spine-focus");
    // 1920x1080.
    await size(1920, 1080);
    await go("Home");
    await shot("40-home-1920");
    await go("Chat");
    await shot("41-chat-1920");
    await go("Studio");
    await shot("42-studio-1920");
    await go("Calendar");
    await shot("43-calendar-1920");
    await go("Mail");
    await shot("44-mail-1920");
    // 1366x768.
    await size(1366, 768);
    await go("Home");
    await shot("30-home-1366");
    await go("Studio");
    await shot("31-studio-1366");
    await go("Mail");
    await shot("32-mail-1366");
    await go("Calendar");
    await shot("33-calendar-1366");
    await go("Chat");
    await shot("34-chat-1366");
    await go("Settings");
    await shot("35-settings-1366");
    await go("Contacts");
    await shot("36-contacts-1366");
    // Narrow resizable layout.
    await size(1000, 700);
    await go("Home");
    await shot("50-home-1000");
    await go("Chat");
    await shot("51-chat-1000");
    await go("Studio");
    await shot("52-studio-1000");
    await go("Mail");
    await shot("53-mail-1000");
    await go("Calendar");
    await shot("54-calendar-1000");
    await size(760, 560);
    await go("Chat");
    await shot("55-chat-760");
    await go("Studio");
    await shot("56-studio-760");
    // Light theme.
    await size(1440, 900);
    await button("Toggle theme").click();
    await go("Home");
    await shot("60-home-light");
    await go("Chat");
    await shot("61-chat-light");
    await go("Studio");
    await shot("62-studio-light");
    await go("Mail");
    await shot("63-mail-light");
    await go("Calendar");
    await shot("64-calendar-light");
    await go("Settings");
    await shot("65-settings-light");
    await button("Toggle theme").click();
    // Spine navigation cost: click to visible heading, no sheet involved.
    for (const [name, heading] of [
      ["Mail", "Mail"],
      ["Calendar", "Calendar"],
      ["Settings", "Settings"],
      ["Agent", "Agent"],
    ] as const) {
      const started = performance.now();
      await spine.getByRole("button", { name, exact: true }).click();
      await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
      timings["spine:" + name] = Math.round(performance.now() - started);
    }
    await app.evaluate(({ app }) => app.getAppMetrics());
    await page.waitForTimeout(3000);
    const memory = await app.evaluate(({ app }) =>
      app.getAppMetrics().map((m) => ({
        type: m.type,
        mb: Math.round(m.memory.workingSetSize / 1024),
        cpu: Math.round(m.cpu.percentCPUUsage * 100) / 100,
      })),
    );
    // Short real interaction recording at the end so it does not skew metrics.
    await spine.getByRole("button", { name: "Home", exact: true }).click();
    await page.waitForTimeout(400);
    const stopRecording = await record(page, evidence, "interaction.mp4");
    await page
      .getByRole("textbox", { name: "Ask OLIVE anything" })
      .pressSequentially("Plan my week around the garden", { delay: 20 });
    await page.waitForTimeout(300);
    await page.getByRole("textbox", { name: "Ask OLIVE anything" }).fill("");
    for (const name of ["Chat", "Mail", "Calendar", "Studio", "Home"]) {
      await spine.getByRole("button", { name, exact: true }).click();
      await page.waitForTimeout(700);
    }
    await button("Find anything").click();
    await page.waitForTimeout(600);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    const recording = await stopRecording();
    timings.recordingFrames = Number(recording.frames || 0);
    await writeFile(
      path.join(evidence, "measurements.json"),
      JSON.stringify(
        { label, capturedAt: new Date().toISOString(), timings, memory, errors, overflow },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
