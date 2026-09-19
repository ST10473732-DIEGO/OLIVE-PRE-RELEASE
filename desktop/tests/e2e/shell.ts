import { expect, type Page } from "@playwright/test";

// Navigation helpers for the labelled navigation pane. Every shipped feature is
// a visible labelled row, so opening one is a single click with no launcher.
export const mainNav = (page: Page) =>
  page.getByRole("navigation", { name: "Main navigation" });

/** Open a feature by its visible navigation label. On narrow windows the same
 *  pane is an overlay, so open it first. */
export async function openSpace(page: Page, name: string) {
  const history = page.getByRole("dialog", { name: "Research history" });
  if (await history.isVisible())
    await history.getByRole("button", { name: "Close", exact: true }).click();
  if (name === "Research") {
    await openSpace(page, "Chat");
    await page.getByRole("button", { name: "Saved research & evidence", exact: true }).click();
    return;
  }
  if (!(await mainNav(page).isVisible().catch(() => false)))
    await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  await mainNav(page).getByRole("button", { name, exact: true }).click();
}

/** Make sure the Chat conversation rail is showing. It docks open by default
 *  on a wide window and is remembered, so the toggle is only pressed when the
 *  rail is currently hidden. */
export async function openHistory(page: Page) {
  const toggle = page.getByRole("button", { name: "Conversation history", exact: true });
  if ((await toggle.getAttribute("aria-pressed")) !== "true") await toggle.click();
  await expect(page.locator(".conversation-items")).toBeVisible();
}

export async function goHome(page: Page) {
  await openSpace(page, "Home");
  await expect(page.locator("main.home")).toBeVisible();
}

/** The Home launcher tile for a feature (an alternative route to navigation). */
export async function openFromHome(page: Page, name: string) {
  await goHome(page);
  await page.locator(".app-tile").filter({ hasText: name }).first().click();
}

export async function toggleTheme(page: Page) {
  await page
    .getByRole("button", { name: "OLIVE activity", exact: true })
    .click();
  await page.getByRole("button", { name: "Toggle theme", exact: true }).click();
  await page.keyboard.press("Escape");
}

/** The Studio workspace selector, labelled with the current workspace. */
export const workspaceSelector = (page: Page) =>
  page.getByRole("button", { name: /^Workspace: / });

export async function switchWorkspace(page: Page, title: string) {
  await workspaceSelector(page).click();
  await page
    .getByRole("dialog", { name: "Workspaces" })
    .getByRole("button", { name: title, exact: true })
    .click();
}
