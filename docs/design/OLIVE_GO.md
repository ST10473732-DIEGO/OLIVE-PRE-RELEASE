# OLIVE GO — browser redesign brief

The full design direction, with rendered mockups of every screen, is the
artifact "OLIVE GO" (published from this session). This file is the part an
implementer needs open beside the code: what stays, what changes, the contract
additions, the layout numbers, and the build order.

Reference: `browser-idea.mp4` (the DuckDuckGo desktop browser). OLIVE GO keeps
its silhouette — one-band chrome, a single centred address field, a nearly
empty new tab page, side panels instead of dialogs — and rebuilds it in OLIVE's
material. No DuckDuckGo branding anywhere. The mark is the OLIVE icon
(`assets/branding/olive-*.png`); the name is **OLIVE GO**.

## What stays

`desktop/electron/main/browser.ts` and the contract in `desktop/electron/browser.ts`:
one `WebContentsView` per tab, persistent + throwaway private sessions, sandboxed
pages, downloads that always ask, bookmarks, history, reopen, find, zoom, the
zod-validated action union, and the renderer's layout effect that positions the
native view over a holder and hides it behind dialogs.

## What is replaced

`desktop/src/features/Browser.tsx` and `browser.css` → `desktop/src/features/go/`:

```
Go.tsx            route component: BrowserState, layout effect, panel/popover state
TabStrip.tsx      tabs, pinned, drag reorder, context menu, overflow scroll
Toolbar.tsx       home/back/forward/reload-stop, AddressField, menu, progress line
AddressField.tsx  input, site badge, star, Ask OLIVE, suggestions
useSuggestions.ts local ranking (tabs/history/favourites) + optional engine suggest
NewTab.tsx        mark, field, chips, favourite tiles, recent rows, Customize
SidePanel.tsx     segmented History / Favourites / Downloads, and Customize
ErrorPage.tsx     did-fail-load code → sentence, Try again, Open in system browser
ClearPopover.tsx  New private tab / Clear browsing data
go.css            the component system, scoped under .go
```

Registry (`desktop/src/navigation/features.ts`): id stays `browser`;
`label: 'OLIVE GO'`, `description: 'Browse the web in your own browser.'`,
aliases `['browser','web','tabs','favourites','downloads']`.

## Layout numbers

| Region | Size | Rule |
| --- | --- | --- |
| Tab strip | 40px, 6px top inset | tabs 34px, min 120 / max 220, pinned 40; overflow scrolls, never wraps |
| Toolbar | 50px | grid `auto minmax(0,1fr) auto`; field centred, max 940px |
| Address field | 36px, radius 18 | focus: 2px accent ring, fill lifts one step, suggestions same width |
| Page area | remaining | native view bounds; width −320 while a side panel is open (page stays visible) |
| Side panel | 320px | slides from the right; one at a time; Escape closes |
| New tab column | 640px | mark 84px at 74px from top; field 44px; tiles 64px on 22px gap |

Radii: 18 field/chips · 9 tabs, buttons, rows · 14 panels, popovers, tiles · 4–5 favicons.
Hit targets ≥ 32×32. Chrome type is the system face (`Segoe UI Variable Text`).

Tokens (both themes, in `tokens.css`): `--go-ink` (= `--bg`), `--go-chrome`
(= `--surface`), `--go-raised` (= `--elevated`), `--go-field` (new: `#1a2330`
dark / `#e3e9f1` light). Accent for focus/progress/primary; olive only for the
mark, private markers and the saved star; semantic colours from `--error` /
`--warning`. Private tabs darken ink, chrome and field one step.

## Contract additions (all additive)

```ts
// BrowserTab gains
favicon: string;  progress: number;  secure: 'https'|'http'|'none';  pinned: boolean;
// BrowserRecord (favourites) gains
favicon: string;  order: number;  pinned: boolean;
// New actions
{action:'pin', id, pinned:boolean}
{action:'move', id, index:number}
{action:'favourite-reorder', urls:string[]}
{action:'clear-data', history:boolean, cookies:boolean, cache:boolean}
{action:'suggest', text:string}           // main-process net.fetch, only when enabled
{action:'home'}                           // active tab → about:blank (new tab page)
{action:'set-search', engine:'google'|'duckduckgo'|'bing'}
{action:'open-external', id}              // shell.openExternal via the existing approval
```

`navigationURL(input, engine)` takes the engine; the three search templates
live in one map. Favicons are captured in main on `page-favicon-updated`,
downscaled to 32px data URIs, cached by host in the browser state file. The
renderer never talks to the network.

## Rendering over the native view

- Side panel open: `visible` stays true, `bounds.width -= 320` on the frame the
  panel starts animating.
- Suggestions / popovers: `bounds.y += 240` while open, restored on close.
- New tab (`about:blank`) and error pages are React inside the holder with the
  view hidden (`visible:false`).
- Closing the last tab opens a new tab page; there is no empty holder state.

## Behaviour that must hold

- Suggestions rank: open tabs + history prefix matches (first gets *Tab to
  complete*) → favourites → engine suggestions (only when the setting is on) →
  *Ask OLIVE* last, never auto-selected. Eight rows max. Private tabs use only
  their session and never call the engine.
- Loading: 2px accent line under the toolbar, indeterminate until first
  progress, fades 220ms after `did-stop-loading`; Reload becomes Stop.
- Favourite: star fills olive with a 180ms pop; toast "Saved to favourites"
  with Undo for 4s; the page never navigates.
- Private: chrome one step darker, "Private" pill leads the strip, green dot +
  "Private ·" prefix on tabs, favourites disabled with a tooltip reason, new tab
  page states what is and isn't kept (Ask OLIVE leaves a record in Chat).
- Errors: OLIVE GO's own page mapping `-105` `-106` `-118` `-501` to
  sentences, falling back to Chromium's description; raw code shown in mono.
- Customize (side panel): search engine, suggestions toggle, section toggles,
  theme shown not chosen — applies live, no Save. Persistent options live in
  OLIVE Settings → Browser through the existing settings service. One store.
- Motion: every animation ≤ 240ms, two easings, no hover transforms, no page
  crossfades; `prefers-reduced-motion` zeroes every duration and offset.
- Shortcuts scoped to the route: Ctrl+T/W/Shift+T/Tab/1–9/L/D/H/J/Shift+N/F, F5, Alt+←/→.
- Security unchanged: sandboxed pages, IPC-only network, save dialog on every
  download, blocked device permissions, http/https only, no credentials in
  URLs, Ask OLIVE hands page text to Chat as quoted untrusted material.

## Build order

1. **Tokens and registry** — `tokens.css`, `features.ts`. Done when navigation,
   Home tile and palette all read "OLIVE GO" from the one entry.
2. **Contract additions in main** — `electron/browser.ts`, `electron/main/browser.ts`.
   Done when URL-builder tests cover three engines and refuse credentials, and a
   Playwright test sees favicon + secure state and a restored active tab.
3. **Shell** — `Go.tsx`, `TabStrip.tsx`, `Toolbar.tsx`, `go.css`, `App.tsx`;
   delete `Browser.tsx`. Done when at 1920/1440/1366/1100 the strip never wraps,
   the field caps at 940 and centres, and the view sits exactly in the holder.
4. **AddressField and suggestions** — done when a GitHub favourite ranks second
   under a history match for "git", the engine row is absent with suggestions
   off, and the network log shows no request while off.
5. **New tab page** — done when a fresh profile shows mark / name / field /
   Add + four dashed tiles, and a populated one shows favourites and Recent.
6. **Side panel** — done when a started download opens the panel with progress,
   the page stays visible 320px narrower, Escape closes, and switching
   History → Favourites keeps the panel open.
7. **Private tabs and Clear** — done when private-session tests still pass, a
   private tab writes no history, and Clear removes normal history/cookies but
   leaves favourites and the open private tab.
8. **Error page and empty rules** — done when an unresolvable host shows the
   OLIVE GO error page with its code and closing the only tab never shows an
   empty holder.
9. **Customize and Settings → Browser** — done when a Customize toggle applies
   live and survives restart, and the same value shows in Settings.
10. **Motion and reduced motion** — done when the reduced-motion Playwright
    variant reports no running animations after tab open, panel open, save.
11. **Keyboard, ARIA, contrast** — done when the browser is operable end to end
    from the keyboard in a test and an axe pass reports no violations.
12. **Visual QA and parity** — `desktop/tests/visual/go-qa.spec.ts`,
    `docs/design/OLIVE_GO_PARITY.md`. Done when no old-Browser action is
    marked lost and the QA spec passes at four widths in both themes and private.

Steps 1–3 leave a usable browser with the new look; nothing later requires
rewriting them.
