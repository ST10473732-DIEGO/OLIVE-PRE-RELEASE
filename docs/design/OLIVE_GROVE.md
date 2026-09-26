# OLIVE Grove

Grove is the redesign the owner approved on 26 September 2026 from two working
prototypes, one for the desktop app and one for a phone companion. It builds on
Design System V2: the V2 token names, components and page structure stay, and
Grove changes what they look like and how the navigation is organised.

## Direction

- **Palette:** olive-tinted neutrals rather than blue-grey. A muted olive is the
  one interaction accent: primary buttons, selection, focus and the active
  space. Pimento red is kept for the mark and for live or attention states,
  such as badges, the now line and errors. Blue appears only for information.
- **Type:** Bricolage Grotesque for display, Onest for the interface and
  JetBrains Mono for times, code and data. All three are OFL fonts bundled
  through `@fontsource-variable`, so they load offline under the renderer's
  `font-src 'self'` policy.
- **Shape and motion:**
  - Radii are 6, 8, 10 and 14 px, and controls are 30 px tall.
  - Motion uses `--ease` for changes and `--spring` for things that travel,
    like the navigation highlight, sheets and toasts. It animates only
    transform and opacity.
  - Reduce Motion removes all of it.

## Shell

- **Layout:** one grid holds the navigation rail (full height), the title bar
  and the page, which sits on a rounded sheet over the ground.
- **Navigation:** seven spaces (Home, Chat, Plan, Mail, Library, Build and
  Web), with Devices and Settings pinned to the foot and Diagnostics added in
  Developer Mode.
  - A space owns existing routes; routes, handoffs and the palette are
    unchanged.
  - Plan holds Calendar, Tasks and Reminders; Library holds Knowledge, Memory
    and Projects; Build holds Agent and Studio.
  - Chat also owns Research and desktop tasks; Settings owns Connections and
    Diagnostics.
  - One highlight glides to the current space.
  - A space reopens the view you last used in it, remembered in
    `spaceViews`.
- **Title bar:** the space name, then a switcher for the space's views
  ("Plan views": Calendar, Tasks, Reminders). A centred **Search or ask OLIVE**
  field opens the palette, bound to Ctrl+K, which is left to Monaco and the
  terminal while they have focus, plus the existing Ctrl+Shift+P. The existing
  activity, model and Connect chips follow, then a theme toggle and the bell.
- **Narrow windows and Studio:** the navigation is an overlay and the title
  bar carries the brand and a space menu, as before.

The model lives in `navigation/features.ts` (`spaces`, `footSpaces` and
`spaceOf`). Tests reach views through `openSpace` in `tests/e2e/shell.ts`,
which maps a view to its space and the switcher.

## Pages

- **Welcome:**
  - the dot-matrix olive, which still lands in the title bar;
  - the wordmark and a one-line promise;
  - two honest checks (the local AI and where data lives);
  - **Enter OLIVE**, and a switch to open straight to Home next time.
- **Home:**
  - a large greeting and the ask composer;
  - suggestions that fill the composer and never send on their own;
  - the existing attention, activity and first-run sections;
  - Continue as cards in four columns;
  - the Today rail as a timeline with a live now marker.
- **Chat:** tinted user bubbles, the attributed OLIVE turn, and the ask
  composer shared with Home.
- **Other pages:** they keep their V2 structure and take Grove through the
  tokens. Drawers float with a spring; dialogs and toasts pop and rise.

## Token mapping (dark → light)

| Token | Dark | Light |
|---|---|---|
| `--bg-base` (ground) | `#0b0d09` | `#ecede6` |
| `--bg-surface` (page sheet) | `#121510` | `#fafaf6` |
| `--bg-raised` | `#20251b` | `#ffffff` |
| `--accent-blue*` (interaction) | olive `#b9c67c` | olive `#55641e` |
| `--accent-ink` (text on accent) | `#151a07` | `#ffffff` |
| `--pimento` | `#ef6e51` | `#c9432a` |
| `--accent-cyan` (information) | `#86b3ec` | `#2c68aa` |

The `--accent-blue` names are kept because hundreds of rules and Monaco read
them. In Grove they carry olive.
