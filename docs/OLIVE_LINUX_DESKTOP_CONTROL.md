# Linux Desktop Control implementation ledger

2026-09-23. **Partial implementation; live Desktop Control is not accepted.**
Branch: `feature/olive-desktop-control-linux-v1`.
BASELINE_HEAD: `2df73b31ca11374978363a8f9d9c34ab052a74a4`.
Historical DESIGN_BASE: `50003790c42aff620d63d664dff89c0338347cab`.
The starting V3 worktree was clean and both checkpoints were verified as ancestors.
No reset, user-profile migration, model promotion, Connect expansion or C9 work.

## Implemented boundaries

The existing DesktopController/gateway owns a Linux runtime. Its native helper
uses distribution Python/GObject over private inherited pipes, not an automation
server. OLIVE's backend remains in `.venv`. The helper registers OLIVE's existing
`local.dmdo.desktop` identity before using application-side portals. A collision-
safe optional installer creates the corresponding per-user desktop launcher.

- GlobalShortcuts session, human BindShortcuts consent, actual assigned-key
  description, and a real `Activated` event are required before input. Registration
  without a key or activation is insufficient. Revocation clears verification.
- RemoteDesktop/ScreenCast request one human-selected display and keyboard/pointer,
  with no persistent grant. The portal FD supplies PipeWire and ConnectToEIS.
  Notify input is never mixed with EIS. Native consent has a 90-second bound.
- Capture is transient, reduced to width 1280 and 2 fps; frames are bounded,
  timestamp-checked and rejected when unavailable, black or dimensionally invalid.
  No desktop screenshot is written by this path or passed to the planner.
- AT-SPI traversal is scoped to one verified PID/lifetime, active window and approved
  monitor, with node/depth/time/text limits. Password nodes are excluded. Typing
  requires the exact focused control and unchanged geometry. Existing drafts are
  not replaced. EIS pointer regions must match the portal mapping ID and geometry.
- App discovery accepts bounded, root-owned, non-writable distribution desktop
  entries and executables; launch uses argument arrays. Shell/interpreter/terminal
  wrappers are rejected. User entries/Flatpak wrappers require further review.
- One local task owner, at most 24 actions, a 240-second planning-work budget,
  model calls capped at 90 seconds and remaining work time, and a 300-second grant.
  The existing Ollama registry/residency manager handles model calls.

The model proposes one strict JSON action; it cannot mint authority, widen scope,
edit policy or execute malformed output. Targets are re-observed after inference
and checked immediately before input. Input invalidates the observation revision.
Unknown actions/fields, stale targets, changed destinations, unsafe accessible
operations and explicit policy denies prevent execution. Repeated-state loops
handoff instead of blindly retrying. Native typing uses scoped AT-SPI editable
text, not clipboard replacement or guessed Unicode keycodes.

The direct-user front door creates a finite internal grant from the actual saved
user message. Trusted tasks remain **Off** by default. Existing keyboard/mouse
settings and central explicit denies remain authoritative. Recognized bounded
forms include opening an app, opening an app and searching, and quoted send/draft
requests naming the app, destination and account. Server/channel forms are also
parsed. This is deliberately a limited grammar: unrestricted English, implicit
accounts, “tell Alex…”, file moves and editor-save workflows are not complete.
Unresolved requests ask for clarification; no model interpretation grants access.

Send/draft have different effects. Submission requires exact text, one composer,
matching account/destination/server evidence and a durable content-free reservation
committed before input. Repeated submission under the same grant is blocked.
Completion needs a new matching outgoing row with a Sent/Delivered indicator;
an old identical message or composer echo does not establish completion. These
semantic conventions are tested with owned substitutions, **not certified for
Discord's actual UI**. Uncertain submissions remain outcome-unknown and are not
replayed or deleted as an automatic rollback.

## Stop and lifecycle

The existing private bridge reader recognizes only a fully validated Stop frame
before async dispatch. It sets the latch, invalidates grants and signals the owned
helper without waiting for model inference, the command pipe lock or persistence.
Async cancellation follows on the owning loop. EIS held inputs are released and
capture/control sessions closed on cleanup. EOF, lease expiry, portal revocation,
paused input and stale helper generations cannot resume work. Parent heartbeats
are 0.4 seconds with a two-second helper lease; these are configured bounds, **not
measured real-host emergency response times**. History recovery never restores a
grant or automatically replays unfinished input.

Logical Stop and completed worker cleanup remain distinct. Controller shutdown
awaits its native owner before closing repositories/helpers. A malformed/closed
reply channel signals native Stop directly. Capability probes are serialized so
concurrent status readers cannot poison availability by racing the single helper.

**Physical takeover detection is unavailable.** There is no root input monitor,
keylogger or tested global physical-input signal. Focus guards cannot detect every
human action and are not atomic with injection. Do not use this development route
while another person is interacting with the desktop. The approved settings copy
states this limitation. Native multi-monitor/fractional/rotated input remains
untested; deterministic coordinate conversion tests are not compositor acceptance.

## Real host and acceptance limits

Read-only inspection found KDE Wayland/KWin 6.7.5, application portal 1.22.1,
KDE backend 6.7.5, RemoteDesktop v2, ScreenCast v5 and GlobalShortcuts v2.
PipeWire 1.6.9, libei 1.6.0, AT-SPI 2.60.7, GStreamer 1.28.7 and distribution
GObject are installed. These interfaces were introspected, not merely inferred
from packages. Firefox 156.0.1, Kate/Dolphin 26.08.1 and Discord are installed.
Displays include two 1920×1080 scale-1 outputs and one 2560×1600 scale-1.25 output.
NVIDIA reports RTX 3080 Ti Laptop, 16,384 MiB. No package/driver upgrade was made.

The user approved live acceptance. KDE showed shortcut consent, but no global Stop
activation was received. The user later confirmed the shortcut had not been
pressed. Subsequent attempts timed out or returned denied/cancelled. A scoped
read of KDE's saved shortcuts found no OLIVE assignment. **No approved portal
source, real capture/input, Firefox task, Kate/Dolphin task or live message was
exercised.** No test clicked OLIVE's own consent dialog. Broad desktop acceptance
cannot be claimed from the passing portable/Electron boundary tests.

Screenshot grounding was separately evaluated using the installed `qwen3-vl:8b`
on synthetic images, not user screenshots. It failed the grounding gate; the
Linux screenshot-action route remains disabled. See the acceptance report and
both content-free result manifests. The existing vision adapter's unreachable
bounded retry was repaired without promoting a model or authorizing input.

## Normal-launch setup and next human-controlled test

1. Keep the existing `.venv`, repository Node/.NET/JDK/Ollama toolchains and distro
   portal/GObject/libei/GStreamer packages. No new package installation is required
   on this inspected host. On another host, unavailable dependencies are reported.
2. Run `.venv/bin/python scripts/install_linux_desktop_entry.py` once if needed.
   It refuses a differing existing entry. Then use `./run_olive.sh` or the OLIVE
   desktop launcher. The launcher retains the normal V3 SDK/runtime discovery.
3. In Settings → Desktop Control, deliberately enable `enabled`, `trusted tasks`,
   `screen observation` and `uia`, and choose the intended input policies. Do not
   enable an input policy merely to bypass a deliberate deny.
4. On a test-only idle display, submit `Open Kate` in Desktop Control. Handle
   KDE's shortcut dialog yourself and assign a free key if the preferred key is
   unavailable. Read the returned runtime instruction, focus another app and
   physically press that key. This first task performs no capture or input.
5. Only after a received global Stop event, use Reset Stop and submit a **new**
   bounded task. Handle the display/device consent yourself. Do not automatically
   resume the stopped task. This phase is still pending real-host verification.
6. Use visible Stop or the verified global shortcut to end control. Turning policy
   Off revokes task authority. Restart requires a new helper/shortcut verification.

The opt-in `linux-control-live.spec.ts` test performs only steps through shortcut
verification. It does not silently proceed to consequential control afterward.
Normal-launch tests cover application/toolchain pages; they do not certify these
pending portal steps. Headless/Xvfb substitution would not establish KWin support.

## Compatibility, data and rollback

Public modes remain FAST/qwen3:8b, NORMAL/gpt-oss:20b, MAX/qwen3-coder:30b,
DEEP/gpt-oss:20b with existing extraction/retrieval/vision, and REIMAGINE/SDXL.
No saved override or conversation attribution is migrated. Qwen Image remains
blocked by licence review, separate acquisition approval and runtime gates.
C7 stays authenticated tool-free text inference; C8 remains bounded shared
workspace operations. Neither has an entry point to the new local task grants.
No protocol enum, remote screen, shell, terminal, vision or filesystem scope added.

Only disposable profiles and synthetic content were used. No real message,
credential, private screenshot or user index was read into the evaluator/commits.
A new effect ledger is additive and contains hashes/IDs/status, not message bodies.
No migration or model download. Existing Windows adapters remain in place.

To roll back the milestone, close OLIVE and switch to
`feature/olive-backend-models-v3` (verified baseline commit above); reopen with the
same normal launcher. Do not reset history or delete profiles/models/toolchains.
The optional launcher may remain: it starts the checked-out source. If removing
it, remove only the installer-created `local.dmdo.desktop.desktop` entry after
checking its `X-OLIVE-Managed=true` marker and exact current installer content;
preserve any user-modified entry. No autostart setting was added.

## Primary references

- [RemoteDesktop application portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)
- [ScreenCast application portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
- [GlobalShortcuts application portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html)
- [Registry application identity](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.host.portal.Registry.html)
- [libei](https://libinput.pages.freedesktop.org/libei/api/)
- [AT-SPI](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/)
- [Electron WebContents](https://www.electronjs.org/docs/latest/api/web-contents)
- [Discord account-automation policy](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots)

Discord prohibits ordinary-account automation outside its OAuth2/bot API and
warns of account termination; no documented GUI-control exemption exists. The
generic operator is not official Discord support or protection from bans. No
Discord login, navigation, token extraction, private API, CAPTCHA handling,
anti-detection or real send was exercised. A real send still needs the user's
chosen account/destination/content with platform-risk awareness.
