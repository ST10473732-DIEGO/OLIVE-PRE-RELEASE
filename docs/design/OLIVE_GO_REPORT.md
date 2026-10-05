# OLIVE GO — implementation report and handoff

**Branch** `design/olive-go` · **worktree** `D:\OLIVE` (clean) · base `3e1f349`.
Commits, oldest first: `ccc87fe` build, `fe93335` overlay assertion, `ed2e2e2`
report, `e0a073d` control treatment and connection badge, `df2a315` report,
`252aa8b` handoff checks, `acb383e` report, `0ed9639` popovers over a still of
the page, native page context menu and two more search engines, and the
commit that names it here.

## Final pass

- **Popovers no longer drop the page.** The menu, suggestions, Clear, Site
  information and the tab context menu used to push the native view down,
  leaving a blank band. The page is now captured (`snapshot` action, JPEG)
  and shown as a still in the holder while the popover is open, with the
  native view hidden; the popover floats over it and the live page returns on
  close. `browser.spec.ts` asserts the still is present and full-height while
  suggestions are open, the native view is hidden, and both revert on Escape.
- **Page context menu.** Right-clicking a page now opens a native menu with
  link, image, media, edit, selection, navigation and page actions (see the
  parity ledger). Saves use the existing will-download save dialog; "Ask
  OLIVE about this selection" hands the selected text to Chat as quoted,
  untrusted material through a new preload listener `onBrowserAsk`.
  `browser.spec.ts` exercises the menu template for an image-link-selection
  right-click and the Ask OLIVE hand-off.
- **Search engines.** Brave Search, Ecosia and Ahmia added to the fixed map;
  Customise lists the six engines as radio rows. Ahmia searches .onion sites
  over the normal web and has no suggestion endpoint (nothing is fetched for
  it); its results need the Tor network, which OLIVE GO does not provide, and
  the row says so. Firefox
  is a browser, not a search provider, so it is not offered as one.
- **"Browser bounds must stay inside its content area" toast.** The user's
  session log showed this rejection four times. A layout measured a frame
  before a window resize finishes can overshoot the new content size; the
  main process now clamps the rectangle to the content area (keeping the
  page below the application's own chrome) instead of rejecting it.
  `browser.spec.ts` sends an oversized layout and asserts it is clamped with
  no error. This is the closest thing found to the reported `olive:call`
  flood — it is an `olive:browser` rejection, not `olive:call`, so the
  historical flood is still not conclusively explained.
- **No white frame while a popover opens.** The still is decoded before the
  live view is hidden, so the two swap in the same frame. Nothing merged, published, tagged or rebased; launcher and OS default
browser unchanged. Not merged into the `functionality/*` branch: integration is
a deliberate step for whoever owns the backend work.

## Fresh checks at the final commit

| Check | Result |
| --- | --- |
| `tsc --noEmit` | clean |
| `eslint src electron` | clean |
| `vitest run` | 10 files, 29 tests passed |
| `vite build` + `build-electron.mjs` | clean |
| `tests/e2e/browser.spec.ts` (live local Electron, loopback HTTP) | passed — includes: the still under open suggestions and the hidden native view, both restored on Escape; the native context-menu template and the Ask OLIVE hand-off; five engine radios in Customise; a failed `https://` navigation reports `secure: 'none'`, shows the "No connection to describe" badge and no lock, Site information says the page didn't load; Back to the HTTP page restores the open-lock state; certificate policy untouched |
| `tests/e2e/visual-security.spec.ts`, `tests/e2e/m2-settings.spec.ts` | passed — the preload surface now includes `onBrowserAsk` and nothing else changed |
| `tests/visual/go-qa.spec.ts` | passed — includes 1000×640: Customise reachable by ordinary scrolling and clicked; every history row reachable inside the panel; the browser root is not `overflow: hidden` |
| Full Playwright suite | last complete run at `fe93335`: 43 passed, 10 skipped (opt-in live gates), 1 failed (`m3-backup`, below). Not re-run in full for the styling pass; the browser-owned specs above were. |
| Python suite | last run at `fe93335`: 814 passed, 1 failed (Studio terminal, below). No Python changed since. |

## Files and contracts changed (since `3e1f349`)

- **Renderer, new:** `desktop/src/features/go/` — `Go.tsx`, `TabStrip.tsx`,
  `Toolbar.tsx`, `AddressField.tsx`, `useSuggestions.ts`, `NewTab.tsx`,
  `SidePanel.tsx`, `Popovers.tsx`, `ErrorPage.tsx`, `BrowserSettings.tsx`,
  `shared.ts`, `go.css`.
- **Renderer, removed:** `desktop/src/features/Browser.tsx`, `browser.css`.
- **Renderer, touched:** `src/app/App.tsx` (route → `Go`, Settings → Browser
  request), `src/features/settings/Settings.tsx` (Browser category),
  `src/navigation/features.ts` (label OLIVE GO), `src/design/tokens.css`
  (`--go-*` tokens, both themes).
- **Bridge contract:** `desktop/electron/browser.ts` — `browserAction` gains
  `pin`, `move`, `duplicate`, `close-others`, `close-right`, `home`,
  `open-external`, `download-show`, `downloads-clear`, `history-remove`,
  `favourite-remove`/`-rename`/`-reorder`, `clear-data`, `suggest`,
  `snapshot`, `preferences` (strict); `new` gains `after`; `searchEngines`
  gains `brave` and `ecosia`; new type `BrowserSnapshot`. `BrowserTab` gains `favicon`,
  `secure`, `pinned`, `errorCode`; `BrowserRecord` gains `favicon?`;
  `BrowserDownload` gains `started`; `BrowserState` gains `preferences` and
  `closed`. New exports `searchEngines`, `searchLabel`, `suggestURL`,
  `describeLoadError`, `defaultPreferences`; `navigationURL(input, engine)`.
  All additive; every previous action keeps its shape.
- **Main process:** `desktop/electron/main/browser.ts` (the actions above,
  favicon capture, tab order, state file v2 with `active`, `favicons`,
  `preferences`), `desktop/electron/main/index.ts` (the external-link approval
  factored into `openExternalLink`, shared with the browser; the page
  context menu, `savePage`, `snapshot`). **Preload:** one addition,
  `onBrowserAsk(listener)` — a main→renderer message carrying only text a
  person chose from the context menu; no new renderer→main capability.
- **Tests:** `tests/browser.test.ts`, `tests/e2e/browser.spec.ts`,
  `tests/e2e/browser-public.spec.ts`, `tests/e2e/clarity-acceptance.spec.ts`
  (label), `tests/visual/go-qa.spec.ts`.
- **Docs:** `docs/design/olive-go-artifact.html` (reference, unchanged),
  `docs/design/OLIVE_GO.md`, `docs/design/OLIVE_GO_PARITY.md`, this file,
  `docs/archive/3.5/BROWSER_AND_MEDIA.md`.

Data: `browser.json` is read as before and written in a v2 shape that a v1
reader ignores gracefully; history, favourites and normal tabs carry over.

## Remaining browser limitations

- Loading is an indeterminate indicator: Electron reports no page progress.
- The connection badge describes transport only (committed HTTPS / HTTP /
  none). Chromium exposes no mixed-content or certificate detail to Electron;
  certificate failures surface as the error page and are never bypassed.
- Downloads show received/total bytes; no speed or time estimate.
- Engine suggestions depend on the provider answering; a timeout or refusal
  shows a note and keeps local suggestions.
- Not implemented: long-press Back/Forward history list; the "no reflow until
  the pointer leaves" tab-close rule. Neither is advertised in the product.
- While one of OLIVE GO's own popovers is open the page is a still: it does
  not scroll or play, and clicking it closes the popover first. Live content
  (video, timers) resumes when the popover closes.
- The page context menu is native and so follows the OS menu look, not the
  artifact's popover style.

## Unresolved issues outside this work

- **Studio interactive program input** (the reported palindrome-input problem)
  is not fixed by this browser work and was not touched.
- **`test_studio_tooling.TerminalTests.test_terminal_receives_input_resizes_and_cleans_up`**
  fails (`mode` not found inside the ConPTY child's environment). No Python
  was changed on this branch; it remains a backend hand-off item unless
  fresh evidence says otherwise.
- **`tests/e2e/m3-backup.spec.ts`** fails identically with OLIVE GO stashed
  (verified on the base build): its native restore dialog needs desktop
  foreground focus. Documented separately; not an all-green run.
- **`olive:call` error flood:** the Browser → Studio → Browser round trip in
  `browser.spec.ts` did not reproduce it (zero page and console errors). Its
  historical root cause was not conclusively identified. One "Content
  Modified" rejection (a language-server reply through the Python bridge)
  was seen once in a manual demo with Studio open; `main.cjs` logs each
  rejected `olive:call`, which is where a recurrence will show.

## Launch (Windows CMD)

```
cd /d D:\OLIVE\desktop
set PATH=D:\OLIVE\.toolchains\node-v24.21.0-win-x64;%PATH%
node node_modules\vite\bin\vite.js build
node scripts\build-electron.mjs
node node_modules\electron\cli.js .
```

To try it on a throwaway profile instead of your own data, add
`set OLIVE_DATA_DIR=%TEMP%\olive-go-demo` before the last line. (`npm run
build` only resolves `vite` when the toolchain's npm is the one on PATH; the
node invocations above do not depend on that.)

## Artifact used

`https://claude.ai/artifact/W6gaARvnTJucaQbzBHdBwz` ("OLIVE GO"), whose source
is preserved unchanged at `docs/design/olive-go-artifact.html`. It is the design
reference only; no part of the document page ships in the application.

## What was implemented

`desktop/src/features/go/` replaces `desktop/src/features/Browser.tsx`
(deleted) and is the `browser` route:

- **Shell** — `Go.tsx`, `TabStrip.tsx`, `Toolbar.tsx`, `go.css`: one-band tab
  strip (40px) and toolbar (50px), active tab with connected shoulders, muted
  inactive tabs, pinned tabs, favicon / spinner treatment, `+`, **Clear**,
  rounded address field capped at 940px, navigation glyphs, compact menu.
  Tabs create, select, close (×, middle-click, Ctrl+W), reopen, pin/unpin,
  duplicate, drag to reorder, close others, close to the right, and scroll
  when they overflow. Closing the last tab leaves a new tab page.
- **Address field** — `AddressField.tsx`, `useSuggestions.ts`: host/path
  display at rest, editing on click or Ctrl+L, connection badge (HTTPS lock,
  HTTP open lock) opening a Site information popover, star (Ctrl+D), Ask
  OLIVE. Suggestions rank open tabs and history, then favourites, then the
  engine (only when on), then an explicit *Ask OLIVE* row that is never
  auto-selected. Enter navigates or searches; Alt+Enter opens a new tab;
  Ctrl+Enter asks OLIVE; Tab completes the first address.
- **New tab page** — `NewTab.tsx`: olive mark, spaced OLIVE GO wordmark,
  focused central field with the same suggestions, Ask OLIVE / Private tab /
  Downloads chips, favourites tiles (favicon or letter tile; one Add tile;
  dashed placeholders up to four), Recent (six most recent distinct pages,
  never in private), Customise bottom-left. A fresh profile shows exactly
  mark, name, field, chips, Add + four dashed tiles. Nothing needs the model
  or the network.
- **Side panel** — `SidePanel.tsx`: History (search, day groups, open,
  remove, clear with confirm), Favourites (open, rename, remove, drag to
  reorder; first twelve become tiles), Downloads (real state and bytes,
  cancel, show in folder, clear finished; opens itself when a download
  starts; badge on the menu while one runs), Customise (search engine,
  suggestions with disclosure, four section toggles, theme shown as
  inherited, link to Settings → Browser). The page stays visible beside the
  panel, 320px narrower.
- **Private tabs and Clear** — `Popovers.tsx`: tinted chrome, PRIVATE pill,
  dot and prefix, favourites disabled with the reason, suggestions scoped to
  the session and never sent to the engine, the new tab page states what is
  and isn't kept. Clear browsing data shows its scope (history, cookies and
  site data, cache), touches only the normal session, keeps favourites and
  the open private tab, and calls itself ordinary cleanup.
- **Errors** — `ErrorPage.tsx`: the olive, a sentence per common Chromium
  code, Try again, Open in system browser through the existing approval
  prompt, and the raw code in mono. Cancelled navigation (-3) is not an
  error.
- **Settings → Browser** — `BrowserSettings.tsx`: the same preferences the
  Customise panel edits, plus the always-on protections stated plainly.
- **Registry** — `features.ts`: label OLIVE GO, description, aliases; the
  navigation row, Home tile and palette entry follow from that one entry.

Backend (`desktop/electron/browser.ts`, `desktop/electron/main/browser.ts`):
tab order with pinned first; `pin`, `move`, `duplicate`, `close-others`,
`close-right`, `home`, `open-external`, `history-remove`, `favourite-remove`
/ `-rename` / `-reorder`, `downloads-clear`, `download-show`, `clear-data`,
`suggest`, `preferences`; per-tab `favicon`, `secure`, `pinned`, `errorCode`;
favicons captured through the page's own session, bounded to 64 KB and 3 s,
cached per host for normal tabs only; history rows updated with the page's
real title; a fixed search-provider map; engine suggestions fetched by the
main process with a 2.5 s deadline, only when enabled and never for a
private tab; restore of tab order, pinned state, active tab and preferences.
The main window's external-link approval is shared with the browser's
*Open in system browser*.

## Visual match

`artifacts/core/functionality/olive-go/qa/` — 34 captures from
`tests/visual/go-qa.spec.ts` at 1920×1080, 1440×900, 1366×768, 1100×760 and 1000×640:
fresh and populated new tab, active page with the saved toast, suggestions,
multiple tabs with a pinned and a loading tab, History / Favourites /
Downloads / Customise panels, the Clear popover, private new tab and page,
the error page, light theme, and reduced motion. Each is measured for
sideways overflow, controls outside the window and clipped labels
(`measurements.json`). Native window captures with the real page inside the
chrome: `artifacts/core/functionality/browser/olive-go/native-window.png`,
`small-native.png`, and the live Google navigation
`artifacts/core/functionality/browser/google-native.png`.

Defects found by those captures and fixed before commit: the toolbar field
stayed in editing mode after a new tab navigated (a shared focus request);
the field's text was centred; the ring doubled on the new tab field; history
rows carried the address instead of the title; Customise overlapped Recent
on short windows; the error code inherited the app's code-box styling. In
the final pass (`e0a073d`): the quick-action chips, Customise and the error
buttons had lost their pill/raised treatment to the browser's own reset
outranking its component classes — fixed at the cascade, not with more
overrides — and a failed navigation showed a lock or open lock taken from the
address; it now shows a globe and says there is no connection to describe.

## Necessary deviations from the artifact

Listed with reasons in `docs/design/OLIVE_GO_PARITY.md`: indeterminate
loading (Electron reports no page progress); overlays push the native view by
measured geometry, not 240px; Customise bottom-left per the implementation
brief; downloads show bytes, never estimated speed or time; preferences live
in the browser's own `browser.json` (Electron main), which Settings → Browser
and Customise both edit — the Python settings service is per-chat model
configuration, not app preferences. Not implemented: long-press Back/Forward
history, and the "no reflow until the pointer leaves" close rule.
