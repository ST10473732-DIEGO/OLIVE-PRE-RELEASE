# OLIVE GO — parity ledger and deviations

Every action the previous Browser page offered, where it lives in OLIVE GO, and
how it is verified. "Kept" means the same `window.olive.browser` action and the
same main-process handler; only the presentation moved.

| Old Browser action | OLIVE GO | Status | Verified by |
| --- | --- | --- | --- |
| New tab / New private tab / Reopen tab buttons | `+` on the strip, **Clear → New private tab**, tab context menu → Reopen closed tab, Ctrl+T / Ctrl+Shift+N / Ctrl+Shift+T | Kept | `browser.spec.ts` |
| Tab select / close | Tab strip, hover ×, middle-click, Ctrl+W, Ctrl+Tab, Ctrl+1–9 | Kept | `browser.spec.ts`, `go-qa.spec.ts` |
| Address + Go | One address field; Enter navigates, Alt+Enter opens a new tab; the new tab page field is the same control | Kept | `browser.spec.ts` |
| Back / Forward / Reload / Stop | Toolbar; Alt+←/→, F5, Esc while loading | Kept | `browser.spec.ts` |
| Bookmark page / Remove bookmark | Star in the field, Ctrl+D; Favourites panel; new-tab tiles | Kept (renamed Favourites) | `browser.spec.ts` |
| History panel + Clear browser history | Side panel → History: search, day groups, remove one, clear with confirm | Kept | `browser.spec.ts` |
| Bookmarks panel | Side panel → Favourites: open, rename, remove, drag to reorder | Kept + extended | `browser.spec.ts`, `go-qa.spec.ts` |
| Downloads panel + cancel | Side panel → Downloads: real state and bytes, cancel, show in folder, clear finished; opens itself when a download starts | Kept + extended | `browser.spec.ts` |
| Site permissions text | Site badge in the field → Site information popover | Kept | `go-qa.spec.ts` |
| Find in page + Next match | Menu → Find field, Enter for next, match count | Kept | `browser.spec.ts` |
| Page zoom select | Menu → zoom −/+/Reset (50–200%) | Kept | `browser.spec.ts` |
| Summarize in Chat | **Ask OLIVE** (field glyph, new-tab chip, last suggestion row, Ctrl+Enter) — same `read` action and the same untrusted-page prompt | Kept (renamed) | `Go.tsx` `askPage` |
| Retry page on error | Error page → Try again; Open in system browser goes through the existing approval prompt | Kept + extended | `go-qa.spec.ts` |
| Session label (normal/private) | Private pill, tinted chrome, dot + prefix on private tabs, new-tab sentence | Kept | `browser.spec.ts`, `go-qa.spec.ts` |
| Native-view hiding behind app dialogs | Unchanged mechanism; OLIVE GO's own popovers push the page down instead | Kept | `browser.spec.ts` (modal check) |
| Restart restore | Tabs, order, pinned, active tab, favourites, history, preferences | Kept + extended | `browser.spec.ts` |

No row is lost.

## New in OLIVE GO

Pinned tabs, drag reorder, duplicate, close others / to the right, tab context
menu, favicons (captured through the page's own session, cached per host for
normal tabs only), connection badge, suggestions (local first; engine only when
the setting is on and never in private tabs), Clear browsing data with a shown
scope, Customise panel, Settings → Browser category, keyboard shortcuts scoped
to the route, the OLIVE GO error page.

## Deviations from the artifact, and why

- **Loading is indeterminate.** The artifact described a progress line that
  tracks page progress. Electron exposes no page-load progress, so the line is
  an indeterminate sweep driven by `did-start-loading` / `did-stop-loading`
  (brief §14: never pretend a timer is progress).
- **Overlays float over a still of the page.** A native view always paints
  above the DOM, so while one of OLIVE GO's own popovers (menu, suggestions,
  Clear, Site information, tab context menu) is open the main process captures
  the page (`snapshot`, JPEG) and the renderer shows that still in the holder
  with the native view hidden; the popover then sits on top exactly as drawn.
  Closing the popover restores the live view. The earlier approach — moving
  the view below the popover — left a blank band above the page and is gone.
- **Page context menu is native** (`Menu.popup`), because only a native menu
  can float above the page and reach the pointer's target: open link in new /
  private tab, copy link, save link; open / save / copy image and its address;
  save video or audio; cut / copy / paste in fields; copy selection, search
  the current engine for it, Ask OLIVE about it; Back / Forward / Reload; Save
  page as…, Print…, Copy page address. Every save goes through the same
  will-download save dialog; nothing is written or opened automatically.
- **Search engines:** Google (default), DuckDuckGo, Bing, Brave Search,
  Ecosia and Ahmia, each from the fixed URL map. Ahmia searches .onion sites
  over ordinary HTTPS and offers no suggestions; its results point into the
  Tor network, which OLIVE GO does not route through, so they open as
  unreachable pages here — the Customise row says so. Firefox was asked for: it is a browser,
  not a search provider, so there is no query endpoint to add; the two real
  engines above are the additions instead.
- **Customise sits bottom-left.** The artifact mockup placed it bottom-right
  like the reference; the implementation brief names bottom-left, and the brief
  is the later instruction.
- **Downloads show bytes, not speed or time left.** The service reports
  received/total bytes only; nothing is estimated (brief §9).
- **Preferences persist in `browser.json`**, the browser's own state file in
  the Electron main process, rather than the Python settings service, which is
  per-chat model configuration. Settings → Browser and the Customise panel edit
  the same record through the same IPC action, so there is still one store.
- **Not implemented, and not advertised anywhere in the product:** the
  long-press Back/Forward history list, and the "strip does not reflow until
  the pointer leaves" tab-close rule (tabs reflow immediately on close).
- **Connection badge.** A lock means only that the committed page was
  delivered over HTTPS; an open lock means plain HTTP; a globe means there is
  no connection to describe — the new tab page, or a page that failed to load
  (a failed HTTPS request never shows a lock). Site information says the same
  in words and never calls a site safe. Chromium exposes no mixed-content or
  certificate-detail state to Electron, so nothing beyond the transport is
  claimed.
- **Private is a tab state**, exactly as the artifact says; there is no separate
  private window.
