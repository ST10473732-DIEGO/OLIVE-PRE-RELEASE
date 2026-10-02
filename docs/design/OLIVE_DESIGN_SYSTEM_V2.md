# OLIVE Design System V2

**Status:** DESIGN APPROVED (2026-09-23) · IMPLEMENTED in the desktop app on
`feature/olive-design-v2` (2026-09-23), except the items marked *not
implemented* below. The implementation changed no backend contract, security
model, IPC name, persistence format or architecture. Implementation details,
deviations and regression evidence:
[`../archive/design/OLIVE_DESIGN_V2_IMPLEMENTATION.md`](../archive/design/OLIVE_DESIGN_V2_IMPLEMENTATION.md).

| Part | Design | Implementation |
| --- | --- | --- |
| Tokens, type, spacing, radii, components (§3–§11) | Approved | Implemented |
| Title bar and navigation (§13, §15) | Approved | Implemented; window controls inside the title bar (C) not implemented — the OS frame is kept |
| Home, Chat, Core, GO, Devices, Files, Tasks, Calendar, Reminders, Settings (§14) | Approved | Implemented; Settings › About (C) and Devices "last used" (C) not implemented |
| Studio (see `OLIVE_STUDIO_V2.md`) | Approved | Implemented; C items not implemented |
| Class D items | Approved as *not supported* | Not shown in the product |

| Deliverable | File |
| --- | --- |
| This handoff (system, shell, every workspace, classes) | `docs/design/OLIVE_DESIGN_SYSTEM_V2.md` |
| Studio specification (the largest redesign) | [`OLIVE_STUDIO_V2.md`](OLIVE_STUDIO_V2.md) |
| Interactive artifact: audit, system, components, every workspace and state | [`olive-design-v2-artifact.html`](olive-design-v2-artifact.html) |
| Interactive artifact: Studio | [`olive-studio-v2-artifact.html`](olive-studio-v2-artifact.html) |
| Shared tokens and primitives used by both artifacts | `v2-assets/olive-v2.css` |
| Baseline captures of the current app (redacted) | `v2-baseline/*.jpg` |

The baseline was captured on 2026-09-23 from `feature/olive-connect-c9`
(`418cbf9`) with the Electron build in `desktop/out`, an isolated temporary
profile seeded by `scripts/seed_visual_fixture.py`, and Ollama deliberately
unreachable. Absolute interpreter paths and the LAN address were redacted
before saving. The Connect C4 and GO captures under `artifacts/` and the
approved C9 artifact were reviewed as well.

## Implementation classes

| Class | Meaning |
| --- | --- |
| **A** | Visual only. The backend already supports it. |
| **B** | Frontend behaviour change using existing APIs. |
| **C** | Requires a small backend/IPC integration. |
| **D** | Future / not currently supported. Never presented as working. |

Both artifacts have an **A/B/C/D classes** toggle that badges every element.
Class-D elements are drawn only while the toggle is on, with a dashed outline.

---

## 1. Design philosophy

OLIVE should look like serious software that happens to be beautiful.

1. **Hierarchy over decoration.** Surfaces step from back to front (base →
   panel → surface → elevated → raised). The work surface is the brightest area.
   Structure comes from hairlines, not cards and shadows.
2. **Colour carries meaning.** Blue is interaction, cyan is OLIVE computing,
   olive green is identity, success green is outcomes, amber is "your
   decision", red is terminal. Nothing is coloured for atmosphere.
3. **Truth in every pixel.** Progress only for real bytes or steps. Status
   only from real state. Remote work is always attributed to the device that did it.
   Unsupported features don't appear.
4. **Desktop density.** 28 px controls, 30–34 px rows, 13 px body. Studio is
   denser still. Mobile keeps its own touch scale.
5. **Familiar where it helps, OLIVE where it matters.** Standard desktop and
   IDE conventions for layout and shortcuts. OLIVE identity comes from the mark,
   the Core, the attribution language and the permission model, not from paint.
6. **One environment.** One title bar, one navigation, one palette, one
   status vocabulary, so the product could grow into OLIVE Desktop and OLIVE OS.

## 2. Audit — keep, refine, replace

"Newer" was not treated as "better". Verdicts come from the running app and the source.

| Area | Verdict | Observation | V2 action |
| --- | --- | --- | --- |
| Colour tokens | **Keep** | The "quiet instrument" palette is right: near-black navy, restrained blue, olive/pimento kept separate from interface colour, native light theme | Keep values; add semantic names, a panel layer and a computing accent; fix muted-on-raised contrast (3.71:1 → 4.69:1) |
| Iconography | **Keep** | One family (lucide outline) | Standardise sizes and strokes (§9) |
| Navigation | **Refine** | Labelled groups are clear and accessible. At 232 px it costs 16% of a 1440 window in Studio | 216 px; brand and status move to the title bar; Studio collapses or hides it |
| Window chrome | **Replace** | No shared title region; each workspace invents a header (Studio adds a 42 px row for two buttons) | A 34 px title bar (§13) |
| Home | **Replace** | A 15-tile app grid repeats the navigation; the page does not answer "what matters now" | Attention · working · continue · Today (§14.1) |
| Chat | **Refine** | Good bones (rail, olive mark, right-aligned user turns, research evidence). The header wraps to two rows; the preset select truncates ("Previous selection · Advance…"); "Run on" is detached from the model | §14.2 |
| Model selection | **Refine** | Truthful presets and "Unavailable remotely" labelling exist, hidden in a wide select | Compact picker with status |
| OLIVE Core | **Refine** | Distinctive and well engineered, and stops when hidden; the compact Core sits in the brand slot and reads as a logo | Title-bar activity indicator (§14.3) |
| Studio | **Replace** | Real capability inside toolbar-and-dock ergonomics | See `OLIVE_STUDIO_V2.md` |
| OLIVE GO | **Keep** | Compact integrated chrome, native web content, truthful private wording | Small refinements only (§14.4) |
| Devices / Connect | **Refine** | Correct model; Off/Ask/Allow segmented. "Pair device" floats detached; five "Unavailable" pills; trust and connection mixed in one pill row | §14.5 |
| Pairing | **Keep** | Code comparison and QR (C2/C4) are clear | Restyle only |
| Tasks | **Refine** | Rail · list · detail is right; card-in-card empty state; 44–48 px rows | §14.6 |
| Calendar | **Refine** | Professional grid, four views; toolbar spreads over two rows; no mini-month | §14.7 |
| Reminders | **Refine** | Honest limitation copy; two big empty cards plus an explainer card | §14.8 |
| Files / Inbox | **Refine** | Inert-by-default semantics and exact states; per-device text lists | §14.9 |
| Settings | **Refine** | Category nav and search are right; native checkboxes and 400 px selects in a wide column; a global save far from the change | §14.10 |
| Empty states | **Refine** | Icon + heading + sentence + actions (from GO) is good; often nested inside cards | Flat, left-aligned in lists |
| Loading states | **Keep** | Honest pending text, no fake progress | Codified in §12 |
| Dialogs / sheets | **Keep** | Radix dialogs; confirmations outside model authority | Radius 12, 440 px default width |
| Permission UX | **Keep** | Off / Ask / Allow and approval dialogs are the backbone | Always ordered Off · Ask · Allow |
| Typography | **Refine** | Segoe UI Variable with system fallback; 22 px page titles are large for productivity; Linux falls back to a generic sans; Monaco defaults to Consolas | §5 |
| Spacing / density | **Refine** | Consistent 4/8 scale; 34–36 px controls, 44–48 px rows everywhere | §6 |
| Status indicators | **Refine** | Dots with glow rings; "AI offline" only under the brand | Plain dots plus text; model and Connect in the title bar |

## 3. Colour tokens

### 3.1 Dark (default)

| V2 token | Value | Role | Contrast |
| --- | --- | --- | --- |
| `background.base` | `#0b0f16` | Window ground, title bar, rails, status bar | — |
| `background.panel` | `#0f141b` | Sidebars, workspace chrome, bottom panels | — |
| `background.surface` | `#11171f` | Primary work surface: editor, chat thread, detail | — |
| `background.elevated` | `#182029` | Selected rows, chips, inactive controls | — |
| `background.raised` | `#1f2933` | Menus, popovers, palette, dialogs, toasts | — |
| `background.hover` | `rgba(197,216,240,.06)` | Hover wash | — |
| `background.active` | `rgba(197,216,240,.10)` | Pressed / current navigation item | — |
| `background.selected` | `rgba(124,196,255,.13)` | Selected row, current palette item | — |
| `background.field` | `#0b1018` | Inputs | — |
| `border.subtle` | `rgba(197,216,240,.09)` | Region separators | — |
| `border.default` | `rgba(197,216,240,.13)` | Control outlines | — |
| `border.strong` | `rgba(197,216,240,.20)` | Overlays, focused containers | — |
| `border.active` | `#7cc4ff` | Focus edge | — |
| `text.primary` | `#e8eef7` | Primary text | 16.45:1 on base |
| `text.secondary` | `#9db0c7` | Secondary text | 8.12:1 on surface, 6.65:1 on raised |
| `text.muted` | `#8093aa` | Metadata | 6.10 (base) … 4.69:1 (raised) |
| `text.disabled` | `#4d596b` | Disabled, non-essential only | — |
| `accent.blue` | `#7cc4ff` | Links, focus ring, selection edge, text-level accents | 10.23:1 on base |
| `accent.blue.fill` | `#2f74d0` | Primary button fill with white text | 4.64:1 |
| `accent.cyan` | `#5ad1e0` | Computing: streaming, running jobs, context that will be sent to a model | 10.63:1 on base |
| `accent.green` | `#9ab534` | OLIVE identity: mark, active-space indicator, OLIVE author mark, trusted identity | 8.26:1 on base |
| `pimento` | `#c0232a` | Icon only | — |
| `status.online` / `status.success` | `#7fd8a8` | Online, verified, passed, Allow in effect | 10.54:1 on surface |
| `status.offline` | `#8093aa` | Offline, off, declined (hollow dot) | — |
| `status.warning` | `#f0c36b` | Recoverable issue, interrupted, stale | 10.91:1 on surface |
| `status.ask` | `#f0c36b` | Your decision needed (always with "Ask" or a hand icon) | — |
| `status.busy` | `#f0c36b` | A device or resource is occupied | — |
| `status.error` | `#ff8f8f` | Failed, blocked, revoked | 8.21:1 on surface |
| `status.computing` | `#5ad1e0` | OLIVE is working (not a warning) | — |
| `focus.ring` | `#7cc4ff` | 2 px outline, offset 2 (inset 1 px in dense lists) | — |

### 3.2 Light (native, not inverted)

| V2 token | Value |
| --- | --- |
| `background.base / panel / surface / elevated / raised` | `#e9edf3 / #f1f4f8 / #ffffff / #e6ebf2 / #ffffff` |
| `border.subtle / default / strong` | `rgba(20,32,47,.08 / .13 / .20)` |
| `text.primary / secondary / muted / disabled` | `#14202f / #46566b / #5f6f85 (5.12:1 on white) / #9aa6b6` |
| `accent.blue / fill` | `#1e63c8` (white text 5.72:1) |
| `accent.cyan` | `#0b7285` (5.59:1 on white) |
| `accent.green` | `#5f7016` (5.50:1) |
| `status.success / warning / error` | `#1c7a4c / #8a5a0b / #b3303a` |

The light muted value changes from `#76869b`, which measures 4.38:1 on white and fails, to `#5f6f85`.

### 3.3 Colour rules

- Blue = interaction. Cyan = computation. Olive = identity. Success green = outcomes.
  These four never substitute for each other. (Same rule as C9 §10.)
- Amber means "your decision" or "recoverable". Red means terminal or blocking. Grey means
  off / offline / declined. Offline turns red only when it blocks the action
  the user is attempting (C9 rule).
- **Status is never colour alone.** Every status carries an icon or a word.
- Avoid: gradients (except the olive mark), glow rings, neon, glassmorphism,
  purple AI gradients, colour used as decoration.

## 4. Token migration map (`desktop/src/design/tokens.css`)

Keep the existing variable names working as aliases (Monaco and components
read them). Introduce the V2 names alongside them. Values change only where marked.

| Current | V2 | Change |
| --- | --- | --- |
| `--bg` | `background.base` | — |
| *(none)* | `background.panel` `#0f141b` | **new** |
| `--surface` | `background.surface` | — |
| `--elevated` | `background.elevated` | — |
| `--raised` | `background.raised` | — |
| `--hover` | `background.hover` | — |
| `--accent-soft` | `background.selected` | .12 → .13 |
| `--field` | `background.field` | translucent → opaque `#0b1018` |
| `--line` | `border.subtle` | — |
| `--line-strong` | `border.default` / `border.strong` | split: controls .13, overlays .20 |
| `--text` | `text.primary` | — |
| `--muted` | `text.secondary` | — |
| `--faint` | `text.muted` | **`#6f819a` → `#8093aa`** (contrast fix) |
| `--accent` | `accent.blue` | — |
| `--accent-strong` | `accent.blue.fill` | **`#3d9cf5` → `#2f74d0`**; primary buttons become blue fill with white text instead of pastel fill with dark text |
| `--on-accent` | `text.on-fill` | `#06131f` → `#ffffff` |
| `--accent-glow` | `::selection` only | no glow on hover |
| `--olive`, `--olive-glow`, `--pimento` | `accent.green`, `accent.green.soft`, `pimento` | — |
| `--success`, `--warning`, `--error`, `--danger` | `status.success`, `status.warning`, `status.error` | — |
| *(none)* | `accent.cyan`, `status.ask`, `status.busy`, `status.computing`, `status.offline`, `text.disabled`, `focus.ring` | **new** |
| `--go-*` | GO aliases of the V2 tokens | — |
| `--shadow` | `shadow.overlay` | overlays only |
| `--shadow-soft` | retired | panels have no shadow |
| `--radius-sm` 8 / `--radius` 12 / `--radius-lg` 16 | `r.md` 6 (controls) / `r.lg` 8 (menus, grouped rows) / `r.xl` 12 (dialogs, composer) | controls 8 → 6; 16 retired |
| `--space-*` | spacing scale | adds 2, 6, 20 |
| `--nav` 232 / `--nav-compact` 58 | 216 / 48 | narrower |
| `--fast` 140 / `--page` 160 | `dur.fast` 120 / `dur.panel` 160 / `dur.sheet` 200 | hover faster |
| `--mono` | mono stack | adds JetBrains Mono, Fira Code, DejaVu Sans Mono before `monospace` |

The pre-entry Welcome keeps its pinned presentation (as documented in `docs/archive/design/DESIGN_SYSTEM.md`).

## 5. Typography

Fonts stay platform-native with no bundled font files: `Segoe UI Variable
Text/Display` → `Segoe UI` → `system-ui` → `-apple-system` → `Noto Sans` →
`Cantarell` → `sans-serif`. Mono: `Cascadia Code` → `Cascadia Mono` →
`JetBrains Mono` → `Fira Code` → `Consolas` → `DejaVu Sans Mono` →
`ui-monospace` → `monospace` (Linux/CachyOS gets a real code face). Monaco's
default font follows this stack instead of hard-coding `Consolas`.

| Role | Size / line / weight | Use |
| --- | --- | --- |
| `app.title` | 12.5 / 1 / 600 | Title-bar space name, "OLIVE" wordmark (letter-spaced .12em) |
| `workspace.title` | 17 / 1.2 / 600 (display) | Workspace header (was 22) |
| `page.title` | 18 / 1.2 / 600 (display) | Home greeting, settings category title |
| `section.heading` | 13 / 1.3 / 650 | "Needs attention", settings sections |
| `eyebrow` | 11 / 1 / 650, uppercase, +.07em | Studio sidebar headers, navigation groups |
| `body.reading` | 14 / 1.62 / 400, max 760 px | Chat answers, long text |
| `body` | 13 / 1.45 / 400 | Default UI text |
| `body.compact` | 12.5 / 1.4 / 400 | Dense lists, panels, tabs |
| `metadata` | 12 / 1.35 / 400, `text.muted` | Secondary lines, timestamps |
| `status` | 12 / 1 / 400 | Status bar, pills (11.5 / 600) |
| `tab` | 12.5 / 1 / 500 | Editor, GO and panel tabs (panel tabs uppercase 11 / 650) |
| `code` | 13 / 20 px mono | Editor, code blocks (12.5 / 20 in chat) |

Digits in columns use `font-variant-numeric: tabular-nums`.

## 6. Spacing and density

Scale (px): **2, 4, 6, 8, 12, 16, 20, 24, 32, 48**.

| Context | Spacing | Row height | Control height |
| --- | --- | --- | --- |
| Studio | 2–8 | 22 (tree, lists) | 24 / 28 |
| Workspaces | 8–24 | 30 (navigation), 34 (lists) | 28 (default), 24 (compact), 32 (one prominent action) |
| Page gutters | 20–32 | — | — |
| Mobile (C9) | unchanged | 44 pt targets | unchanged |

## 7. Radii

| Token | px | Use |
| --- | --- | --- |
| `r.xs` | 3 | Tags inside dense rows, tab close hover |
| `r.sm` | 4 | Compact buttons, segmented items, key caps |
| `r.md` | 6 | Buttons, inputs, selects, segmented control |
| `r.lg` | 8 | Menus, popovers, palette, grouped settings rows, code blocks |
| `r.xl` | 12 | Dialogs, the Chat/Home composer |
| pill | 999 | Status pills, badges, avatars only |

## 8. Borders and elevation

- Regions are separated by 1 px `border.subtle`. Controls have 1 px `border.default`.
  Overlays have 1 px `border.strong`.
- Shadows (`shadow.overlay: 0 12px 32px rgba(0,0,0,.5), 0 2px 6px rgba(0,0,0,.35)`)
  only on menus, popovers, the palette, dialogs and toasts.
- Panels and list rows never have a shadow. At most one level of
  "card" (a bordered group) per region; never cards inside cards.

## 9. Iconography

- One family: **lucide outline**, already bundled as `lucide-react`.
- Sizes: 12 (inline metadata), 14 (buttons, rows), 16 (navigation), 18–20 (rails, activity bar).
- Stroke 1.75 at 12–18 px, 1.5 at 20 px. No filled, two-tone or cartoon icons in the shell.
- Only the **olive mark** (the app icon) and the **Core** are expressive. OLIVE features
  use the olive mark, not the generic "sparkles" AI glyph.
- Status dots are 7 px, flat, and never glow.

## 10. Motion

| Situation | Rule |
| --- | --- |
| Hover / press | 120 ms colour/background; no scale; the 0.5 px press nudge is removed |
| Panels | 160 ms size change, `cubic-bezier(.2,.7,.2,1)`; content does not fade |
| Sheets, dialogs, palette | 200 ms opacity + 4 px rise; scrim fades |
| Streaming | Cyan block caret, 1 s steps; text appends; no per-token animation |
| Running job | 2 px indeterminate line at the top of the owning region, only while the job really runs |
| Success / failure | State changes in place (icon + text); a toast for background outcomes; no pulses, shakes or confetti |
| Core | Welcome rotation (as today). The compact Core animates only while working |
| Reduced motion | All of the above become instant; the Core rests; the app preference wins |

## 11. Components

| Component | Spec | Class |
| --- | --- | --- |
| Button | 28 px, `r.md`, 12.5/550. Variants: default (elevated), **primary** (`accent.blue.fill`, white), quiet, danger (text error), disabled (transparent, `text.disabled`). Compact 24, prominent 32 | A |
| Icon button | 26 px (22 compact), quiet until hover; `aria-pressed` for toggles | A |
| Field / select | 28 px, `background.field`, `border.default`, focus = `border.active` + 2 px `accent.blue` 13% ring | A |
| Segmented | Track `background.base`; selected item raised with a 1 px strong ring | A |
| Permission control | Segmented **Off · Ask · Allow**. Selected Ask: amber text and ring + hand icon. Selected Allow: success text and ring + check. Off: neutral | A |
| Switch | 30×17 compact; replaces native checkboxes in Settings; `role="switch"` | A |
| Status pill | 20 px, 11.5/600, dot or icon + word | A |
| Badge | 16 px count; blue (info), red `#c2413f` (errors, white 5.09:1), amber (Ask) | A |
| List row | 34 px (30 in navigation, 22 in Studio): icon, title + optional metadata line, trailing meta or actions | A |
| Notice | Inline, `background.surface`, 2 px inset left rule in the tone colour, icon + sentence + ≤2 actions | A |
| Toast | Raised, bottom centre, icon + one sentence ("Event saved to Calendar") | A |
| Dialog | 440 px, `r.xl`, eyebrow (tone) + title + body + right-aligned footer; destructive or authority actions always here | A |
| Empty state | Icon (20) + heading + one sentence + ≤2 actions, flat, left-aligned in lists | A |
| Title bar | §13 | B / C |
| Command palette | Raised overlay under the title bar, prefix modes | B |

## 12. State semantics

| State | Visual | Rule |
| --- | --- | --- |
| Normal | — | — |
| Hover | `background.hover` | Never the only affordance for an action on touch-capable Windows devices; row actions also appear on focus |
| Selected | `background.selected` (+ inset `border.active` when focused) | — |
| Loading | Muted text "Loading today…" with a small spinner icon | No shimmer skeletons; no progress bar without a real quantity |
| Progress | Bar only for real bytes or steps ("92.1 of 148 MB"), cyan fill | — |
| Running | Cyan dot / indeterminate line; Core turns cyan | Only while the job exists in `runtime.activity` |
| Empty | Empty-state component | Say what fills it and offer one action |
| Offline (device) | Hollow grey dot + "Offline · last seen …" | Red only when it blocks the attempted action |
| AI offline | Warning notice + title-bar "AI offline" | Everything that doesn't need a model keeps working and says so |
| Error | Red icon + what happened + how to fix | No apologies, no vague "something went wrong" |
| Permission required | Amber "Ask" / approval dialog | The model never approves; the dialog states the exact action |
| Partial | "Stopped · partial answer kept" | Never silently retried or completed elsewhere |

## 13. Desktop shell

```
┌ Title bar 34 ───────────────────────────────────────────────────────────────┐
│ ◖ OLIVE │ Home ▾  · context      [ Search or run a command  Ctrl Shift P ]  │
│                          ⁘ Working · 2   ● NORMAL ready   ▭ 2 devices   🔔3  – □ × │
├ Nav 216 ─┬ Workspace ───────────────────────────────────┬ Contextual (opt.) ┤
│ Home     │                                             │                   │
│ WORK     │                                             │                   │
│  Chat …  │                                             │                   │
│ Settings │                                             │                   │
└──────────┴─────────────────────────────────────────────┴───────────────────┘
```

| Element | Behaviour | Class |
| --- | --- | --- |
| Olive mark + "OLIVE" | Home / navigation | B |
| Space switcher | Current space; menu of spaces | B |
| Context crumb | Conversation title, workspace, category | B |
| Command centre | Opens the existing "Find anything" palette (`Ctrl+Shift+P`) | B |
| Activity (Core + text) | Opens the activity centre; text from `runtime.activity` | B |
| Model status | "NORMAL ready" / "AI offline" → Settings › Models | B |
| Connect status | "Connect off" / "2 devices" → Devices | B |
| Notifications | Bell with count → activity centre (approvals, reminders, transfers) | B |
| Window controls | Inside the bar (Electron `titleBarOverlay` on Windows; frameless with custom controls on Linux) | C |
| Navigation | 216 px, grouped (Work, Build, Knowledge, Personal, System), 30 px rows, olive 2 px active indicator, badges for attention, Settings and Collapse at the bottom; collapses to a 48 px icon rail | A |
| Right side | Contextual only (Chat none; Tasks detail; GO history; Studio OLIVE) | — |
| Bottom | No global status bar. Studio has its own | — |

Responsive: navigation expanded ≥ 1280 px, rail below (user choice
persists). Studio collapses it to the rail at ≥ 1600 px and hides it below
(the title bar keeps every space reachable).

## 14. Workspaces

### 14.1 Home

Order: **Ask OLIVE** composer (with Chat mode, model preset, execution) →
**Needs attention** (approvals, Connect Ask requests, due reminders, failing
jobs, pending actions from Chat) → **OLIVE is working on** (`runtime.activity`)
→ **Continue** (recent conversations, workspaces, GO sessions, projects). The right
**Today** rail (340 px) holds the next event with a countdown, the remaining agenda, tasks due
(checkable), and the devices summary. Sections with nothing to show disappear.

States: normal; **first run** (a checklist: OLIVE running ✓, Start Ollama, install
the NORMAL model, pair a device (optional)); **AI offline** (a warning notice
that names the endpoint and says what still works); **loading** (text + spinner,
no skeletons). The app grid is removed (A). Composition is B.

### 14.2 Chat

- Rail 264: search, New, groups (Today / Earlier), project subtitle, and the footer
  "Conversations stay on this device" (A).
- Header 46, one row: title, project pill, *Research & evidence*, options,
  more (A).
- Thread column 760 max. User turns are quiet right-aligned bubbles. OLIVE turns
  have an attribution row: olive mark, **"OLIVE · OLIVE MAX · Gaming PC · 8.4 s"**
  (existing `RemoteAttribution`, A), plus hover actions (copy, regenerate, branch).
- Typography `body.reading`; headings 15/650; inline code chips.
- **Code blocks:** header with language and **Copy** (B). *Open in Studio* is **D**.
- **Tool results:** a row with an icon, what happened and one follow-up
  ("Open in Calendar") (A).
- **Pending actions:** an amber-ruled row, "awaiting your confirmation", and
  *Review…*, which opens the confirmation dialog (A; `pending_draft` exists).
- **Composer:** attach, mode (Chat / Search web / Research thoroughly), model
  preset, execution (This device / paired devices), send. It becomes **Stop** while
  generating. The hint line reports "Thinking on Gaming PC…" and "OLIVE DEEP
  and REIMAGINE are unavailable on paired devices" (A).
- States: **streaming** (cyan caret, Stop, activity "Thinking"); **remote went
  offline** (the partial answer is kept, with "OLIVE did not retry on this device" and
  explicit *Retry on Gaming PC* / *Ask on this device*: no silent fallback, A);
  **empty** (small resting Core, heading, one sentence, four starters);
  **image attached with a non-vision preset** ("OLIVE FAST can't see images.
  The picture would not be sent…" with *Use OLIVE DEEP* / *Remove image*, B).

It is not a ChatGPT clone because of the attribution row, the model/execution pair,
action rows that are visibly not prose, the olive author mark and the local-first footer.

### 14.3 OLIVE Core

| Where | Core? |
| --- | --- |
| Welcome | Yes: large, rotating (unchanged) |
| Title bar activity | Yes: 18 px; olive dots at rest, **cyan compute lighting only while real work runs**, amber while waiting for approval (B: renderer palette parameter) |
| Chat empty conversation | Yes: small, at rest |
| App icon, favicon, OS launcher | No: the solid green olive mark |
| Home hero, Studio editor chrome, GO pages, loading placeholders | Never |

Today's renderer draws a green/pimento dot olive (not blue). V2 keeps that
as the resting state, which keeps the Core recognisably OLIVE, and adds the
cyan state so it reads as computation while active.

### 14.4 OLIVE GO

Preserve the approved design. Refinements: a 36 px tab strip directly under the title
bar (B); tabs 210 px with hover `background.hover` and selected `background.panel`
joined to the toolbar; address bar `r.lg`, host in primary text and path in muted
text; a private tab marked in the tab (eye-off icon), the address bar (violet hairline)
and one truthful sentence (history, cookies and site data deleted on close;
websites, network and DNS provider can still see visits) (A); the new tab
page loses the dashed placeholder tiles, and with no favourites it shows one line of
guidance (A); side panel 320 px with a History / Favourites / Downloads segmented control and search (A);
an offline page with *Try again* ("did not retry through another device") (A). It must not
look like Chrome with green paint: GO keeps OLIVE's navy chrome, the olive
mark on the new tab, and *Ask OLIVE about this page*.

### 14.5 Devices / OLIVE Connect

Information hierarchy (top → bottom): **Device** (name, platform, version,
paired date) → **Connection** · **Trust** · **Encryption** as three separate
facts → the statement *"Pairing proves this is Gaming PC. It grants no access.
Each capability below starts Off and applies to what Gaming PC can do on this
PC. What this PC can do on Gaming PC is set on Gaming PC."* → **Capabilities**
table (Sync, Files, Remote AI, Remote Studio + share sub-permissions,
Connection checks), each with **Off · Ask · Allow** → the line "Not available yet:
sharing Tasks, Calendar, Reminders and Notifications" (replaces five
Unavailable pills) → **Revoke pairing** in a separated danger group with
confirmation. Tabs: Capabilities / Activity / Details. The list rail has This
device, Paired and Nearby sections, the *Pair a device* header action, and the Connect
status footer. States: paired online, device offline (permissions still
editable), incoming **Ask** request dialog, pairing code comparison, and Connect
off (interface choice, discovery switch, explicit *Turn Connect on*). All A
except a per-capability "last used" column (C).

### 14.6 Tasks

A rail with views and counts (Today, Upcoming, All, Completed, By project) and
projects. The list has a header, search and *New task*, an inline "Add a task…" row
(`N`), groups (Overdue in error text, Today, Tomorrow…) and 34 px rows (check,
title, project pill, priority flag, due). The detail pane is 340 px (title,
description, due, priority, project, reminder, linked event, Edit, *Find a work block*,
Delete). The keyboard hints footer shows N / ↑↓ / Space / Enter / Del (B). The empty state is flat (A).

### 14.7 Calendar

Week is the working view: a 56 px time column, 44 px hours, an all-day row, events
as tinted blocks with a 3 px calendar-colour rule, and a now-line on today.
The rail has a mini-month (week highlighted), calendar toggles (Personal, Work,
Imported ICS, …) and the local-storage note (B). The toolbar is one row: Today, ‹ ›,
range title, search, Day/Week/Month/Agenda, overflow (ICS import/export),
*New event*. Month and Agenda are the existing views, restyled (A).

### 14.8 Reminders

One list. **Due now** (amber-ruled row: Snooze ▾, Dismiss, *Mark task done*),
**Upcoming** (time, linked task or event, offset, edit, delete), **History** (outcome
pills). A footnote keeps today's truthful copy (fires only while OLIVE runs;
snooze and dismiss never change the linked record; completing a task cancels its
reminders). System notifications while the app is closed: **D**.

### 14.9 Files: OLIVE Inbox

One table across devices: file (icon, name, size) · device (direction arrow,
from/to) · **state pill** · progress · actions. State vocabulary (backend
state → label):

| Backend state | Label | Pill | Actions |
| --- | --- | --- | --- |
| `offered`, `awaiting_approval` | Waiting for you | amber, hand icon | Decline / Accept |
| `accepted`, `transferring` | Receiving / Sending | cyan, arrow | Cancel; progress = acknowledged bytes |
| `verifying` | Verifying | cyan, shield | — ("SHA-256 check") |
| `completed` | Complete · verified | success, check | **Save a copy…**, Dismiss. No Open |
| `interrupted` | Interrupted | amber | "Partial data removed"; *Send again…* starts a new transfer reviewed from zero |
| `failed` | Failed | red | Reason ("Checksum mismatch"), Dismiss |
| `declined` / `cancelled` | Declined / Cancelled | grey | — |
| `dismissed` | hidden from the list | — | — |

A notice explains the model once: received files are inert, never opened,
previewed or run by OLIVE; complete means byte count and SHA-256 matched;
transfers are never resumed automatically. The table is B; the states and actions are A. Resume is **D**.

### 14.10 Settings

Category navigation with search, grouped: (General, Appearance) · **AI**
(Models, Chat, Memory, Knowledge, Research, OCR) · **Workspaces** (Studio,
OLIVE GO, Desktop Control) · **Connect & accounts** (Devices → the Devices
workspace, Mail connections) · **Privacy & Security** (Permissions) · **Data**
(Backup & Data, Diagnostics, About). This maps the existing categories.
"Storage" is Backup & Data. **About** needs a version/licence view (C).
**Notifications** has no settings today (D, not shown).

Rows have the label and description on the left and the control on the right,
inside one bordered group per section: compact switches, segmented controls,
short selects. Examples in the artifact: Appearance (Theme Dark/Light, text
size, Reduce motion, Core animation Follow system / Animate Core / Pause,
Welcome on startup, Start on Home, Developer mode); Models (preset table with
installed model, purpose, Ready / Needs setup, *Default* on NORMAL, the
structured-interpretation role in Advanced); Permissions (Off · Ask · Allow
per action, approved workspaces). The explicit save stays; an **unsaved-changes
bar** appears at the bottom only when the draft differs (*Revert* / *Save settings*) (B).
Density "Comfortable" is a design candidate (D).

## 15. Responsive rules (shell)

| Width | Navigation | Contextual side | Notes |
| --- | --- | --- | --- |
| ≥ 1600 | expanded 216 | docked | Studio: OLIVE rail 48 |
| 1280–1599 | expanded 216 | docked | Studio: rail hidden |
| 1100–1279 | 48 rail | docked if main ≥ 640, else overlay | Title-bar labels shorten |
| < 1100 | overlay | overlay | Existing narrow bar behaviour |

## 16. Accessibility

| Topic | Finding today | V2 rule | Class |
| --- | --- | --- | --- |
| Contrast | Token audit passes except muted on raised (3.71:1) and light faint on white (4.38:1) | `text.muted` `#8093aa` / light `#5f6f85`; small text on raised uses `text.secondary` | A |
| Focus | One visible 2 px ring: good | Keep; inset 1 px ring in dense lists | A |
| Keyboard | Tree roles, dialogs, palette exist; Studio lacks view shortcuts | VS Code-compatible shortcuts; roving tabindex in rails, tabs, trees; Tasks keys | B |
| Target size | 34–36 px controls | 28 default, 24 minimum (WCAG 2.2 AA 2.5.8); Studio 22 with the spacing exception | A |
| Colour-only status | Test counts and the Ask highlight partly colour-only | Icon or word on every status | A |
| Ambiguous controls | Disabled Stop reads as a checkbox | Hide or explain controls that can't act | A |
| Screen readers | Stable accessible names (the e2e suite relies on them) | Keep names; status-bar items are labelled buttons; counts `aria-hidden` with a spoken total | B |
| Motion | Reduced motion respected, except the Welcome olive, which always rotates at the user's explicit earlier request | Everything else honours it; the Welcome exception is flagged for reconsideration, not changed here | A |
| Zoom | 125% / 150% evidence exists | Reflow; Studio keeps the editor ≥ 560 by collapsing sidebars first | B |

## 17. OLIVE Mobile C9: audit against V2

C9 already shares the colour values, Off/Ask/Allow semantics, the olive vs success
separation and the attribution wording. **No structural change is recommended.**
Mobile keeps its touch radii (14/20), 44 pt targets and SF system fonts by design.
Remote Studio stays a companion. Optional token-level alignment only:

| C9 element | Recommendation |
| --- | --- |
| Streaming cursor and "OLIVE is working" (accent blue in C9) | Optionally use `accent.cyan` (computing) for cross-device consistency; Busy (device occupied) stays amber |
| Token names | Adopt the V2 semantic names in the handoff; values unchanged |
| Everything else | Keep |

## 18. Toward OLIVE Desktop and OLIVE OS

Not an OS design, just a check that V2 scales:

| OS surface | V2 counterpart |
| --- | --- |
| Launcher | Command centre / palette |
| Dock | Collapsed 48 px navigation rail with olive indicator and badges |
| Quick Settings | Title-bar status cluster (model, Connect, activity), each opening a compact popover |
| Notifications | Toasts + activity centre, using the same rows as Home "Needs attention" |
| OLIVE Core | Activity indicator: olive at rest, cyan computing, amber waiting |
| Window chrome | The 34 px title bar with window controls |
| Desktop surfaces | Full-bleed workspaces without card chrome |
| Theming | One semantic token set with native light and dark |

## 19. Implementation classification summary

| Area | Element | Class |
| --- | --- | --- |
| Tokens | V2 names as aliases; muted contrast fix; panel layer; blue fill; mono stack | A |
| Shell | Title bar content (space, command centre, status cluster) | B |
| Shell | Window controls inside the title bar | C |
| Shell | 216 px nav, grouping, 48 px rail | A |
| Shell | Route-aware collapse in Studio | B |
| Home | New composition; app grid removed | B |
| Chat | Header consolidation, composer pickers, attribution on every turn | A |
| Chat | Code-block Copy; vision warning | B |
| Chat | Open code block in Studio | D |
| Core | Title-bar placement; cyan working palette | B |
| GO | Tab strip under title bar | B |
| GO | Favourites empty state, private indication, address bar | A |
| Devices | Header facts, trust statement, capability table, collapsed unavailable line | A |
| Devices | Per-capability "last used" | C |
| Files | Unified Inbox table | B |
| Files | Resume | D |
| Tasks | Row density, groups | A |
| Tasks | Inline add, keyboard | B |
| Calendar | Week styling, now-line, toolbar | A |
| Calendar | Rail mini-month and toggles | B |
| Reminders | Grouped list, inline actions | A |
| Reminders | OS notifications while closed | D |
| Settings | Row layout, switches, grouped nav | A |
| Settings | Unsaved-changes bar | B |
| Settings | About | C |
| Settings | Notifications, Density | D |
| Studio | See `OLIVE_STUDIO_V2.md` §19 | A–D |

### Suggested order

1. Tokens (§4) with aliases: no visual regressions, and the contrast fix lands first.
2. Title bar + navigation refinements (B), then window controls as a separate C change.
3. Studio V2 (its own phased plan).
4. Home, Chat, Devices/Files, Settings.
5. Tasks, Calendar, Reminders, GO refinements.

Keep every accessible name the Playwright suite depends on, or update the
spec in the same change. Run the repository quality bar (`python -m compileall
-q .`, `python -m unittest discover -s tests -v`) and the frontend checks
(`tsc --noEmit`, `eslint`, `vitest`, the affected Playwright specs) for each step.
