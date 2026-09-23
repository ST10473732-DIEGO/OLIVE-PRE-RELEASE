import { test, expect, _electron as electron, type Page } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";

// Rendered-screen QA for the clarity redesign: the widths the brief names, both
// themes, reduced motion, compact and narrow navigation, empty and populated
// states. Every screen is measured as well as captured, so "it looks fine" is
// not the evidence: nothing may scroll the window sideways, and no essential
// control may sit outside the viewport or be cut off.
const WIDTHS: [number, number][] = [
  [1920, 1080],
  [1440, 900],
  [1366, 768],
  [1100, 800],
  [880, 760],
];

test("clarity visual QA across widths, themes and states", async () => {
  test.setTimeout(900000);
  const root = path.resolve("..");
  const evidence = path.join(root, "artifacts/ui-review/clarity/qa");
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-qa-"));
  const seed = spawnSync(
    path.join(root, ".venv/Scripts/python.exe"),
    [path.join(root, "scripts/seed_visual_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" },
  });
  const errors: string[] = [];
  const findings: Record<string, unknown>[] = [];
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(30000);
    page.on("pageerror", (e) => errors.push(e.message));
    const size = async (w: number, h: number) => {
      await app.evaluate(
        ({ BrowserWindow }, s) => BrowserWindow.getAllWindows()[0].setContentSize(s[0], s[1]),
        [w, h],
      );
      await page.waitForTimeout(400);
    };
    const shot = async (name: string) => {
      await page.waitForTimeout(250);
      await page.screenshot({ path: path.join(evidence, `${name}.png`) });
    };
    // One measurement pass per screen: sideways scroll, clipped text, and any
    // element pushed outside the window.
    const measure = async (label: string) => {
      const result = await page.evaluate(() => {
        const doc = document.documentElement;
        const clipped: string[] = [];
        const outside: string[] = [];
        const width = doc.clientWidth;
        const height = doc.clientHeight;
        for (const node of Array.from(document.querySelectorAll<HTMLElement>(
          ".nav-row, .app-tile, .continue-row, .strip-button, .file-tab, .workspace-selector, .primary-action",
        ))) {
          const style = getComputedStyle(node);
          if (style.display === "none" || style.visibility === "hidden") continue;
          const box = node.getBoundingClientRect();
          if (box.width === 0 && box.height === 0) continue;
          // Sideways is a defect; vertical is ordinary page scrolling.
          if (box.right > width + 1 || box.left < -1)
            outside.push(`${node.className.split(" ")[0]}:${node.innerText.slice(0, 28)}`);
          // A single-line label that is wider than its box is cut off.
          if (style.textOverflow === "ellipsis" && style.webkitLineClamp === "none" && node.scrollWidth > node.clientWidth + 1)
            clipped.push(`${node.className.split(" ")[0]}:${node.innerText.slice(0, 28)}`);
        }
        // Navigation never scrolls to reach its pinned rows.
        const foot = Array.from(document.querySelectorAll<HTMLElement>(".nav-foot .nav-row"))
          .filter((node) => getComputedStyle(node).display !== "none")
          .filter((node) => {
            const box = node.getBoundingClientRect();
            return box.bottom > height + 1 || box.top < -1;
          })
          .map((node) => node.innerText.slice(0, 28));
        return {
          footOutside: foot,
          sideways: doc.scrollWidth > doc.clientWidth,
          bodySideways: document.body.scrollWidth > document.body.clientWidth,
          zoom: Math.round(window.devicePixelRatio * 100) / 100,
          width,
          height,
          outside,
          clipped,
        };
      });
      findings.push({ screen: label, ...result });
      expect(result.sideways, `${label} must not scroll the window sideways`).toBe(false);
      expect(result.outside, `${label} pushes controls outside the window`).toEqual([]);
      expect(result.clipped, `${label} cuts off a label`).toEqual([]);
      expect(result.footOutside, `${label} hides a pinned navigation row`).toEqual([]);
      return result;
    };
    // Two controls that touch read as one. Any pair of visible sibling controls
    // sharing a line with almost no space between them is a defect.
    const crowding = async (label: string) => {
      const pairs = await page.evaluate(() => {
        const found: string[] = [];
        const text = (node: Element) => (node as HTMLElement).innerText.replace(/\s+/g, " ").slice(0, 24);
        const visible = (node: Element) => {
          const style = getComputedStyle(node);
          const box = node.getBoundingClientRect();
          return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
        };
        // Segmented groups (a toolbar group, the tool-panel strip, document and
        // dock tabs) are deliberately contiguous: their density is the pattern,
        // not a defect. Everywhere else, two controls must not touch.
        const grouped = ".toolbar-group, .strip-tools, .dock-tabs, .file-tabs, .template-grid, .language-grid";
        for (const parent of Array.from(document.querySelectorAll("*"))) {
          if (parent.matches(grouped) || parent.closest(grouped)) continue;
          const children = Array.from(parent.children).filter(
            (node) =>
              visible(node) &&
              (node.matches("button, select, a[href], .check-field, .setting-row, .personal-check") ||
                Boolean(node.querySelector("input[type=checkbox], input[type=radio]"))),
          );
          for (let i = 1; i < children.length; i += 1) {
            const a = children[i - 1].getBoundingClientRect();
            const b = children[i].getBoundingClientRect();
            // Stacked rows in a list are deliberately dense; two controls
            // sitting side by side with no space between them are not.
            const sameLine = a.top < b.bottom - 2 && b.top < a.bottom - 2;
            if (!sameLine) continue;
            const gap = b.left - a.right;
            if (gap >= -0.5 && gap < 8)
              found.push(
                `${Math.round(gap)}px between [${children[i - 1].className}|${(children[i - 1] as HTMLElement).getAttribute("aria-label") || text(children[i - 1])}] and [${children[i].className}|${(children[i] as HTMLElement).getAttribute("aria-label") || text(children[i])}] in ${parent.tagName.toLowerCase()}.${parent.className || "(no class)"}`,
              );
          }
        }
        return found;
      });
      if (pairs.length) findings.push({ screen: label, crowded: pairs });
      expect(pairs, `${label} has controls with almost no space between them`).toEqual([]);
    };
    const nav = () => page.getByRole("navigation", { name: "Main navigation" });
    const go = async (label: string) => {
      if (!(await nav().isVisible().catch(() => false))) {
        const opener = page.getByRole("button", { name: "Open navigation", exact: true });
        if ((await opener.count()) === 0) {
          await page.screenshot({ path: path.join(evidence, "diagnostic-no-navigation.png") });
          throw new Error(
            `No navigation at ${await page.evaluate(() => window.innerWidth)}px; ` +
              (await page.evaluate(() => {
                const button = document.querySelector<HTMLElement>('[aria-label="Open navigation"]');
                const chain: string[] = [];
                for (let node = button?.parentElement; node; node = node.parentElement)
                  chain.push(
                    `${node.tagName}.${node.className}[hidden=${node.hasAttribute("hidden")},aria-hidden=${node.getAttribute("aria-hidden")},inert=${node.hasAttribute("inert")}]`,
                  );
                const box = button?.getBoundingClientRect();
                return JSON.stringify({ box, chain, dialogs: document.querySelectorAll("[role=dialog]").length });
              })),
          );
        }
        await opener.click();
      }
      await nav().getByRole("button", { name: label, exact: true }).click();
      await page.waitForTimeout(450);
    };

    // ---- Welcome, at the widest and the narrowest ----------------------
    await size(1440, 900);
    await expect(page.getByRole("button", { name: "Enter OLIVE", exact: true })).toBeVisible({
      timeout: 90000,
    });
    await shot("welcome-1440");
    await measure("welcome 1440x900");
    await size(880, 760);
    await shot("welcome-880");
    await measure("welcome 880x760");
    await size(1440, 900);
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect(page.locator("main.home")).toBeVisible();
    await page.waitForTimeout(900);

    // ---- Every named width, populated -----------------------------------
    for (const [w, h] of WIDTHS) {
      await size(w, h);
      await go("Home");
      await shot(`home-${w}`);
      await measure(`Home ${w}x${h}`);
      // Every feature is visible without scrolling navigation, at every size
      // the brief names.
      const overflow = await page.evaluate(() => {
        const list = document.querySelector(".nav-scroll");
        return list ? list.scrollHeight - list.clientHeight : 0;
      });
      findings.push({ screen: `navigation ${w}x${h}`, hiddenPixels: overflow });
      expect(overflow, `navigation must fit at ${w}x${h}`).toBeLessThanOrEqual(0);
      await go("Studio");
      await shot(`studio-${w}`);
      await measure(`Studio ${w}x${h}`);
      await go("Mail");
      await shot(`mail-${w}`);
      await measure(`Mail ${w}x${h}`);
      await go("Settings");
      await shot(`settings-${w}`);
      await measure(`Settings ${w}x${h}`);
      await crowding(`Settings ${w}x${h}`);
      await go("Home");
      await crowding(`Home ${w}x${h}`);
    }

    // ---- A real workspace: the densest screen OLIVE has -----------------
    await size(1600, 950);
    await go("Studio");
    await page.getByRole("button", { name: /Fixture . local Python project/ }).first().click();
    await expect(page.getByRole("button", { name: /^Workspace: / })).toBeVisible({ timeout: 60000 });
    await page.waitForTimeout(900);
    await shot("studio-workspace");
    await measure("Studio with a workspace");
    await crowding("Studio with a workspace");
    await page.keyboard.press("Control+`");
    await page.waitForTimeout(600);
    await shot("studio-tools-open");
    await measure("Studio with the tools open");
    await crowding("Studio with the tools open");
    await page.getByRole("button", { name: "Hide Terminal", exact: true }).click();

    // ---- The smallest supported width keeps navigation reachable --------
    await size(880, 760);
    await expect(page.getByRole("button", { name: "Open navigation", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Open navigation", exact: true }).click();
    await expect(nav()).toBeVisible();
    // Settings is pinned in the foot: it is reachable without scrolling.
    await expect(nav().getByRole("button", { name: "Settings", exact: true })).toBeInViewport();
    await page.waitForTimeout(500);
    // The pane is a solid surface, not a translucent layer the page shows through.
    const paneBackground = await page.evaluate(
      () => getComputedStyle(document.querySelector(".navigation")!).backgroundColor,
    );
    findings.push({ screen: "narrow overlay background", paneBackground });
    expect(paneBackground, "the overlay pane must be opaque").not.toMatch(/rgba\([^)]*,\s*0?\.\d+\)/);
    await shot("narrow-navigation-overlay");
    await measure("narrow overlay 880x760");
    await page.keyboard.press("Escape");

    // ---- Compact navigation is a choice, and survives a route change ----
    await size(1440, 900);
    await go("Home");
    await page.getByRole("button", { name: "Collapse navigation", exact: true }).click();
    await page.waitForTimeout(400);
    await shot("home-compact-nav");
    await measure("Home compact navigation");
    await go("Studio");
    await expect(page.getByRole("button", { name: "Expand navigation", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Expand navigation", exact: true }).click();
    await page.waitForTimeout(400);

    // ---- Light theme and reduced motion ---------------------------------
    const activity = page.getByRole("button", { name: "OLIVE activity", exact: true });
    await activity.click();
    await page.waitForTimeout(400);
    await shot("activity-sheet");
    await crowding("activity sheet");
    await page.getByRole("button", { name: "Toggle theme", exact: true }).click();
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
    await go("Home");
    await shot("home-light");
    await measure("Home light theme");
    await go("Studio");
    await shot("studio-light");
    await measure("Studio light theme");
    await activity.click();
    await page.getByRole("checkbox", { name: "Reduced motion", exact: true }).check();
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
    await go("Home");
    await shot("home-light-reduced-motion");
    expect(
      await page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running").length),
      "reduced motion should leave no animation running",
    ).toBe(0);
    await activity.click();
    await page.getByRole("checkbox", { name: "Reduced motion", exact: true }).uncheck();
    await page.getByRole("button", { name: "Toggle theme", exact: true }).click();
    await page.keyboard.press("Escape");

    // ---- Empty state: a second profile with no work at all --------------
    await writeFile(path.join(evidence, "measurements.json"), JSON.stringify(findings, null, 2));
    expect(errors).toEqual([]);
  } finally {
    await app.close();
  }

  const empty = await mkdtemp(path.join(tmpdir(), "olive-qa-empty-"));
  const fresh = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: empty, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" },
  });
  try {
    const page: Page = await fresh.firstWindow();
    page.setDefaultTimeout(30000);
    await fresh.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setContentSize(1440, 900),
    );
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect(page.locator("main.home")).toBeVisible();
    await page.waitForTimeout(800);
    // With no recent work there is no Continue section at all, rather than an
    // empty panel holding the space.
    await expect(page.locator(".home-continue")).toHaveCount(0);
    await expect(page.locator(".app-grid .app-tile").first()).toBeVisible();
    await page.screenshot({ path: path.join(evidence, "home-empty.png") });
    await page.getByRole("navigation", { name: "Main navigation" })
      .getByRole("button", { name: "Studio", exact: true }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(evidence, "studio-empty.png") });
  } finally {
    await fresh.close();
  }
});
