# OLIVE design system

## Electron application (design/olive-complete-ui-refresh)

The post-entry application uses the "quiet instrument" token set in
`desktop/src/design/tokens.css`. Shell, page and feature styles live in
`desktop/src/design/app.css` and `desktop/src/design/workspaces.css`; Personal
Core and Mail keep feature stylesheets next to their components. The rationale,
information architecture and parity record are in
`docs/releases/3.5.1/DESIGN_REFRESH.md` and `PARITY_CHECKLIST.md`.

Semantic tokens: `--bg` (ground), `--surface` (panel), `--elevated` (hover,
chips), `--raised` (menus, toasts); `--text`, `--muted`, `--faint`; one accent
`--accent` with `--accent-soft` selection wash and `--accent-glow`; `--line`
and `--line-strong` hairlines; `--success`, `--warning`, `--error` with `-soft`
washes; `--radius`/`--radius-sm`/`--radius-lg`; `--fast` 140ms and `--page`
160ms with `--ease`; `--rail` 68px and `--rail-expanded` 232px. Light mode is a
native token set. Monaco and the read-only terminal read the same tokens.

Type: Segoe UI Variable with system fallback, no bundled fonts. Root 14px;
page titles 22px, section titles 16px, meta 12–13px. Controls: buttons 34px
(primary 36px, compact toolbars 30px), inputs 34px, list rows 44–48px, spine
items 30px (27px below 740px window height).

The pre-entry Welcome keeps its baseline presentation; its colours and type
are pinned in `app.css` on purpose and are not part of the token system.

## Historical Qt tokens

Current presentation tokens are in `desktop/src/design/tokens.css`, with shared React Core, cards, dialogs, Markdown and route components. Monaco derives editor surface colours from the same CSS tokens. The Qt tokens below remain fallback implementation. M1 and final visual approval are still required.

M1 implementation is in `olive/ui_qt/experience`; open Appearance → Component
gallery in the actual app. Gallery content is explicitly synthetic and cannot
send a message. The real confirmation dialog remains the policy-bearing UI.

Measured token-pair contrast ratios: dark primary/background 17.44:1,
secondary/background 9.58:1, muted/surface 5.43:1, on-accent/accent 7.91:1;
light equivalents 14.75:1, 6.93:1, 5.63:1 and 6.14:1. This is a token audit,
not accessibility certification or an audit of every disabled/hover control.

Source: `olive/ui_qt/experience/tokens.json`; consumed by Qt Widgets and QML.
Near-black background, restrained navy surfaces, blue accent, readable neutral
text, semantic success/warning/error/approval tones. Light equivalents are native
tokens, not an inverted screenshot. Installed Segoe UI Variable/Segoe UI is used
with system fallback; no font files are redistributed.

Spacing 4/8/12/16/24/32/48; compact navigation 72, expanded 240; controls 44,
dense Studio 32; radius 12 / feature 20; body 16, title 32. Tokens can change at
the visual gate; do not scatter colours/timings through individual surfaces.

Motion uses bounded opacity/position or a small Core's rotation. Reduced Motion
removes ambient/entry movement. Hidden/minimized surfaces stop animation.
QML is presentation and cannot approve consequences or access secrets/files.

Component gallery and real-window screenshots are M1 deliverables. Visual review
and user approval are separate from automated rendering checks.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
