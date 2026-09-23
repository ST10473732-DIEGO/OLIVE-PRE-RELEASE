# OLIVE unified local agent — implementation and acceptance

## Status

Normal Chat now performs verified, visible Linux desktop tasks without visiting a
control workspace, enabling each task, testing a shortcut, or accepting a portal
dialog. This was exercised on the owner's unlocked KDE session, including a launch
through OLIVE's installed desktop entry. Firefox search, page reading/scrolling/tab
navigation, Kate new-document save, Dolphin copy/move, owned-messenger sends, and
KCalc input have real production-path evidence. Chat Stop, named-grant revocation,
and an independent heartbeat watchdog were also exercised.

**This is a useful bounded operator, not completion of every requested general
workflow.** Freeform interpretation supports launch/search/named clicks. More
complex freeform plans, arbitrary visual messaging clients, selecting arbitrary
browser results, and broad system-settings changes are not accepted. The GUI
model's missing-target performance and the conservative visual verifier remain
material blockers to unrestricted visual operation. No external message was sent.

## Baseline, scope and recovery

- `BASELINE_HEAD`: `7b19f1d658bdada456f3725147b9c026cd7207af`.
- Verified starting branch: `feature/olive-desktop-control-linux-v1`; the initial
  worktree was clean. No later commit was reset, stashed or discarded.
- Recoverable reference: `baseline/olive-unified-agent-7b19f1d`.
- Implementation branch: `feature/olive-unified-agent`.
- Implementation commit: `416f35d2e31775cb412b902fa4b3f3bf36e067f0`.
- Final live freeform correction: `63a24d6` (verified application inheritance
  within one compound request). A subsequent documentation commit records evidence.

The owner explicitly superseded the old page, physical shortcut, per-task enable,
reset-latch and renderer-freeze requirements for this milestone. The new
[scope ledger](evidence/unified-agent-scope.json) records **11 formerly frozen
paths**, their baseline/current hashes and the authority for each change. It covers
Chat/navigation wiring, Settings diagnostics, Electron tray cancellation and seven
replaced control-workspace files. No typography, colour, spacing, CSS, icon asset,
Studio or GO redesign was performed. Historical freeze manifests and their checker
are unchanged. `scripts/check_unified_scope.py` checks this new scope against the
exact desktop baseline; it does not make the historical zero-change check pass.

The seven deleted renderer modules were reachable only through the removed
workspace. Import searches, frontend compilation and replacement tests precede
removal. Backend session/history repositories, Windows adapters, Connect contracts,
journey reports and Git history remain. The old `desktop` navigation identifier
redirects to Chat; stored records are not deleted.

## KDE setup actually provisioned

The stable compatibility identity is **`local.dmdo.desktop`**, from
`olive/identity.json` and Electron packaging. Product-facing names remain OLIVE.
The matching managed desktop file is installed in the owner's applications folder.

Observed versions: Plasma/kwin **6.7.5**, xdg-desktop-portal **1.22.1**, KDE portal
**6.7.5**, Flatpak **1.18.3**, libei **1.6.0**, PipeWire **1.6.9**, Tesseract **5.5.3**.
Although the earlier fish command failed, inspection during implementation found
`/usr/bin/flatpak`. The installer used its verified absolute path and a validated,
nonempty identity. It did not assume an `OLIVE_APP_ID` environment variable.

The installer first created the actual helper-style D-Bus connection and called
`org.freedesktop.host.portal.Registry.Register` on it. Only after registration and
lookup did it set:

```text
kde-authorized / remote-desktop / local.dmdo.desktop -> ["yes"]
```

The old named entry was absent. Its exclusive mode-0600 receipt is
`~/.local/state/olive/setup/kde-unified-agent.json`. Only this named entry was backed
up and changed. A pre-existing anonymous grant was observed and **left untouched**;
OLIVE independently requires its named grant, so that unrelated entry cannot mask
revocation. A live revocation test proved this boundary.

`scripts/provision_olive_kde.py` also implements the session-bus fallback using
`PermissionStore.SetPermission` with signature `(sbssas)`, table `kde-authorized`,
create `true`, ID `remote-desktop`, the same verified app ID, and `["yes"]`.
The installed PermissionStore interface was inspected; fallback and exact-entry
rollback are covered by boundary tests with no Flatpak CLI. The live setup used
Flatpak, not the mocked fallback.

The owner-authorized profile migration is separately recorded in
`~/.local/state/olive/setup/unified-profile.json`. It updated only desktop-task flags
and keyboard/mouse policy, preserving scoped permission rules. It used the existing
resolved profile (`~/.local/share/olive`) in place; fresh-profile defaults and
legacy-profile resolution were not changed. Unrelated installations/profiles do
not silently receive this enabled policy. Accessibility flags changed for this
session have a separate `accessibility.json` receipt.

Provisioning scripts are not runtime imports or model tools. Launch, failure,
revocation and model suggestions cannot recreate the grant. Optional rollback,
within the owner's session, is:

```sh
/usr/bin/python3 scripts/provision_olive_kde.py --receipt "$HOME/.local/state/olive/setup/kde-unified-agent.json" --restore
.venv/bin/python scripts/provision_olive_unified_profile.py --receipt "$HOME/.local/state/olive/setup/unified-profile.json" --restore
/usr/bin/python3 scripts/restore_olive_accessibility.py --receipt "$HOME/.local/state/olive/setup/accessibility.json"
```

Rollback refuses to overwrite a subsequently changed entry/settings. The original
absence of OLIVE's grant is restored with `DeletePermission` for OLIVE alone.
Receipts and model configuration contain local paths and remain outside Git.

This is KDE-specific pre-authorisation, not capture/input authority on other
compositors. A host app ID is attribution, **not a strong sandbox boundary against
malicious same-user processes**. Registry-unavailable/systemd-identity fallback
has not been implemented or certified; the installed Registry path works.

References: [KDE owner provisioning](https://develop.kde.org/docs/administration/portal-permissions/),
[host Registry](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.host.portal.Registry.html),
[PermissionStore](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.impl.portal.PermissionStore.html).

## Real capture, input and identity evidence

The **helper**, not merely Electron or its shell, registers on the dedicated
connection subsequently used for portal calls. A filtered session-bus trace of
KDE's implementation `RemoteDesktop.Start` observed app ID `local.dmdo.desktop`,
portal sender `:1.38` and KDE backend destination `:1.49`. The empty string following
the app ID in that call is the parent-window argument, not an anonymous caller.
The content-free session evidence records the helper's unique peer, registration,
named permission, granted devices, stream mapping and frame dimensions.

One combined RemoteDesktop session selects keyboard/pointer and compatible
ScreenCast monitor sources. It does not use a separately authorised Screenshot or
ScreenCast session. KDE's multi-monitor `multiple=false` path returned an unmapped
workspace mosaic; selecting individually mapped outputs fixed that integration.
The requested app's output is selected by observed KWin metadata. Real captures
have source **1920×1080**, encoded **1280×720**, and matching compositor/EIS mappings.
An earlier **1280×1** negotiation bug was found and repaired; those early frames are
not counted as successful capture evidence.

Input uses only libei/EIS plus explicit AT-SPI semantic actions. No Notify input
fallback, clipboard text injection, RDP listener, device-node grant or security
notification suppression was introduced. KWin does not advertise EIS text input
on this installation: literal keyboard input uses its supplied XKB keymap, with
whole-string preflight and stop-aware pacing. Native editable fields use semantic
text insertion where reliable. Unsupported characters fail before typing.

Qt and GTK Wayland accessibility coordinates were window-local on this host;
they are bound to independently observed KWin client geometry. A GI `get_text`
name collision had silently omitted text controls; explicit `Atspi.Text.get_text`
fixed it. Electron's inherited `NO_AT_BRIDGE=1` is removed from requested app
launches. The fixed, typed KWin helper exposes PID-scoped observation/activation,
not model-supplied JavaScript. Its asynchronous script deletion/ID reuse race was
repaired by waiting for deletion of the exact owned script.

Live tasks used the production Chat composer, orchestrator, permission broker,
helper and executor. Playwright/CDP entered requests and read status; it did not
provide desktop input authority. Both terminal and installed `.desktop` launches
were exercised. For desktop-entry instrumentation, loopback debugging flags were
temporarily appended and the original entry bytes restored after startup. No
portal or shortcut dialog appeared. Restarting OLIVE produced a fresh registered
helper/session without reprovisioning. Actual shared portal restart was not forced;
restart identity invalidation/re-registration is tested at the D-Bus boundary.

## One Chat, authority and cancellation

Home Ask and Chat use the existing orchestrator. Ordinary answers retain their
normal model service. Local action requests enter the native task executor;
semantic model interpretations are checked against original user text. Remote Chat
and Studio contexts cannot acquire this local desktop scope. Models propose one
bounded action; observations, web text and `approved=true` cannot grant authority.
Malformed actions execute nothing. No GUI model is advertised as the source of an
answer generated by Ollama.

A live paraphrase (“Could you bring up Firefox and look up glacier monitoring
please?”) passed through normal Chat in **14.312 seconds**. The existing `qwen3:8b`
interpreter proposed launch followed by search; its semantic interpretation took
**2.195 seconds**. The first attempt exposed an integration mismatch: the search
omitted the application already named in the launch step. The broker initially
rejected it before input. It now inherits only the verified application within the
same proposal; references to previous tasks remain disallowed. The repaired run
verified the visible result without duplicate confirmation.

Fast paths are optimisations for supported ordinary tasks. They re-observe between
meaningful actions and validate exact text, focus, geometry and destination before
submission. Missing/duplicate targets stop rather than selecting the first match.
Draft-only does not submit, existing drafts are preserved, and security/payment/
credential/destructive confirmations are blocked from generic clicks/Enter. This
is not a universal semantic safety classifier; broad unsupported effects remain
unavailable rather than falling through to a terminal.

There is one input helper, protected by a private per-user lock and inherited
stdio IPC. Its model process cannot access that IPC. Chat Stop crosses the existing
private protocol reader before asyncio/model/storage work. The Activity control
and new tray menu use the same Stop route. Optional global shortcut registration
is retained; **no physical shortcut activation was performed or claimed**.

A new explicit command clears only transient cancellation and creates new authority.
Old cancellation epochs never revive. Persistent disable and named-grant revocation
remain authoritative. Every task has a 240-second helper input lease, a two-second
heartbeat limit and a separate watchdog thread. Lock checks and EIS pause stop
input. Queued requests recheck the stop event. Held keys/buttons are released during
cleanup; a stuck helper exits, closing its EIS/portal descriptors.

Measured production cancellation while Kate was the target: **3.65 ms** request
acknowledgement and **444.16 ms** task cleanup. These are different events, also
represented separately in capability status. Suspending the backend with SIGSTOP
caused the independent helper to exit after **1,819 ms**; the old task stayed
cancelled and a new explicit Chat task succeeded. Named-grant revocation cancelled
a live task and the next task was denied; the combined test took **923 ms**. The
owner's grant was explicitly restored by the acceptance harness, not by runtime.

No global physical-input monitor is claimed. Unexpected focus/geometry changes
invalidate targets; intentional initial app activation is supported. Lock-screen
security was not bypassed. Fractional display scale and multi-monitor transitions
beyond the observed mappings remain uncertified.

## GUI model and resource measurements

Primary only: **mPLUG/GUI-Owl-1.5-8B-Instruct**, Qwen3-VL architecture, MIT licence.
The official base repository was inspected at
`06d5faecff74840bab2be2425e9c42667a5d04fc`. Community derivative repository
`mradermacher/GUI-Owl-1.5-8B-Instruct-GGUF` was pinned at
`6737f9a6f2cf96d594062f31db421898b3a87bcd`.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `GUI-Owl-1.5-8B-Instruct.Q5_K_M.gguf` | 5,851,114,144 | `c8cabd3eca98f7d40eb583116f66648b465cf144cadb00258e661574e954da83` |
| `GUI-Owl-1.5-8B-Instruct.mmproj-f16.gguf` | 1,159,029,952 | `88969da9a3c92b3ecd1f735af3d3d88afb6c240cd14067766c421c08b5d940b2` |

Downloaded files were digest-verified. GGUF architecture, source URL, tokenizer
and chat template were checked against official configuration. The derivative
publisher does not identify an exact converter commit or cryptographically bind
its weights to the inspected base revision; that provenance gap remains. These
are local community-quantization measurements, not official benchmark results.

Runtime: official **llama.cpp b11147 / `fee39dd92`**, isolated CUDA 12.8 release,
explicit matching f16 projector, CUDA0, all layers on GPU, 8,192 context, one slot,
flash attention and a 2,048 image-token ceiling. The official computer-use prompt
is retained with its MIT licence; outputs are parsed as `computer_use` actions,
never executed as Python. Normalised 0–1000 coordinates, crop/resize dimensions and
compositor coordinates are distinct. Known-coordinate tests and a real EIS click
exercise the mapping.

The server binds loopback only with a random private API key. Bubblewrap supplies
read-only model/runtime/system-library mounts, private process/tmp namespaces,
required NVIDIA devices and no home directory. Environment credentials are cleared.
Built-in agents, web UI, MCP proxy and arbitrary media file paths are not enabled.
The shared model residency manager serialises GUI/Ollama/Connect consumers and
unloads OLIVE's previous managed model before switching. Unrelated clients are
preserved; insufficient free GPU memory refuses GUI startup. Ollama, its weights,
Chat/DEEP/C7 consumers and all public presets remain.

| Local test | Result |
|---|---|
| Initial shortened prompt, 50 synthetic cases | 13/50 correct; 13/40 present, 0/10 absent |
| Official cookbook prompt, same 50-case regression | 41/50; **40/40 present**, **1/10 absent** |
| Fresh resource run with canonical prompt | Same 41/50; median warm **1.426 s** |
| Untouched held-out seed 730951, 50 new cases after repairs | **40/50: 40/40 present, 0/10 absent**; median **1.491 s** |
| Sampled peak GUI process RAM / VRAM | **5,589,483,520 bytes / 8,306 MiB** |
| Initial CUDA smoke: cold total / warm cached inference | **3.46 s / 0.66 s** |
| Canonical-prompt smoke: initial / cached inference | **1.80 s / 0.78 s** |
| Live drawn-control inference | **1.257 s**, followed by real EIS click and changed frame |
| Additional conservative OCR/point gate on 50 cases | **2/40 present accepted; 10/10 absent rejected** |

The final untouched 50-case run was generated only after prompt/preprocessing changes,
with no subsequent tuning. Its absent-target failures reinforce the restriction.
The final run used 4,453,810,176 bytes sampled RAM and 8,306 MiB VRAM. The last
request reused 985 prompt tokens (933 newly evaluated), with 775 ms prompt processing
and 729 ms decoding.

The earlier fixture set varies dimensions, themes, positions and missing targets. It began
as held-out input; prompt/preprocessing repairs reused it, so its later scores are
regression results, not an untouched benchmark or general task-completion rate.
The point verifier deliberately accepts only points near a unique literal label;
it rejects most left-aligned labels when the model clicks the button centre. Its
low coverage is an outstanding engineering limit, not a lowered gate. The real
visual route is restricted accordingly. No full-screen reasoning transcript or
continuous screenshot archive is kept. The one inspected owned-fixture frame
remains outside Git.

No 4B challenger was acquired: the primary is compatible and meets the warm speed
target; its absence/verification limitations are not evidence that a smaller model
would solve them. No UI-TARS fallback, Transformers/vLLM environment, additional
quantization sweep, cloud dependency or Ollama removal was performed.

Sources: [official model](https://huggingface.co/mPLUG/GUI-Owl-1.5-8B-Instruct),
[computer-use cookbook](https://github.com/X-PLUG/MobileAgent/tree/main/Mobile-Agent-v3.5),
[community artifacts](https://huggingface.co/mradermacher/GUI-Owl-1.5-8B-Instruct-GGUF),
[llama.cpp](https://github.com/ggml-org/llama.cpp).

## Observed task outcomes

| Production Chat task | Live result |
|---|---|
| Freeform paraphrase through actual local interpreter | Launch/search proposal validated; visible result verified in 14.312 s |
| Launch/activate Firefox and fresh searches | Verified rendered results for several distinct queries; later desktop-entry launch also passed |
| Read visible search page, scroll, previous tab | Fresh-frame OCR/page changes observed; no hidden/headless browser |
| Kate create/edit/save supplied note at owned path | Two new files saved through the visible file picker; contents read back exactly |
| Dolphin find/copy/move owned note | Exact selection, native copy/cut/paste, destination hash and source state verified |
| Existing destination collision | Refused; original destination contents preserved |
| Owned messenger, varied servers/channels/text | Three sends passed with observed local delivery indicators, including after resize |
| Drawn control without accessibility target | GUI-Owl + independent OCR + mapped EIS click passed |
| KCalc numeric control | Generic semantic click and changed accessible state passed; no KCalc-specific production adapter |
| Resize owned messenger | Generic click, geometry re-observation and subsequent send passed |
| Chat Stop, revocation, watchdog, new task | Cancelled/denied old authority; fresh explicit task reacquired a new session |

These are task-specific outcomes, not a claimed general task-success percentage.
Earlier integration failures are retained in evidence/journey: text verification,
Save dialog labels, AT-SPI text interfaces, Dolphin completion, OCR polarity and
KWin script lifetime all required repairs. Existing-window drafts and documents
were not silently erased. No system-wide display scaling, lock-screen setting,
security setting, autologin or unrelated application state was changed.

Messaging uses app-neutral account/server/destination/composer/effect evidence and
a durable non-repeatable send reservation. “Sent/Delivered” is observed UI evidence,
not a protocol guarantee. Pending/unknown outcomes are not blindly retried. The
owned GTK fixture has no networking, private API or bot token. Its fixed synthetic
names occur only in the fixture, not the production resolver. Real Discord/account
navigation and delivery were not tested. Discord prohibits normal-account automation
and documents no GUI exemption; a visible-client route does not remove that
[account-policy risk](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots).
No token extraction, client modification, CAPTCHA bypass or bulk messaging exists.

## Validation and remaining work

Fresh aggregate totals and content-free live evidence are recorded in
`docs/evidence/unified-agent-results.json`. Raw verification logs are retained in
the ignored local `artifacts/unified-agent/` directory; the public manifest records
their SHA-256 digests:

- Python: **1,204 run, 8 skipped, 0 failures/errors** (137.887 seconds).
- Exact Connect: **241 passed** (88.894 seconds).
- Frontend: **96 tests / 18 files passed**.
- Typecheck, lint and production build: **passed**.
- Repository compilation: **718 Python sources passed**.
- New scoped freeze checker: **11 authorized changes**, historical manifests unchanged.
- Full Electron: **55 passed / 16 skipped / 0 failed** (7.5 minutes).

The initial Electron aggregate was 52 passed / 16 skipped / 3 failed. Two fixtures
spawned SDK executables without the provisioned SDK/JDK on PATH; the third used
an intentionally non-public RPC instead of the actual reviewed file-launch IPC.
The environment and test route were corrected before a full fresh aggregate.
Focused reruns are not added to that aggregate. The historical zero-byte freeze
check still fails for the 11 authorized changes, as expected.

Live KDE results are separate from mocks and controlled Electron fixtures. No hosted CI, native Windows/macOS,
other compositor, remote desktop peer, C9, C10 or Mobile acceptance is claimed.

The required literal `python -m compileall -q .` was run. It still reports the
ignored third-party PySide6 Android Jinja `__init__.tmpl.py` syntax error; repository
Python sources compile separately. Vendor files were not altered to hide it.

Outstanding work includes broad freeform multi-effect planning, stronger generic
visual target/postcondition verification, broader realistic held-out cases,
real-client messaging semantics, browser-result selection, reversible system
settings acceptance, Registry-unavailable identity fallback, actual portal restart
and locked-session/fractional-scale native tests. The user is not being asked to
press a shortcut or perform permission commands to unblock these engineering gaps.

Only isolated model/runtime downloads and owner setup were installed. No chat,
credentials, legacy profile, SDK, working model tag, Connect record or historical
report was removed. Action reservations finish before input; there is no SQLite
transaction across inference or UI waits. Cleanup closes owned helper/model jobs,
not the user's Firefox, Kate or Dolphin windows. The owned messenger and filtered
D-Bus monitor were closed; the fixture desktop entry was archived with the owned
acceptance artifacts. No input helper or GUI inference server remained after normal
application exit.

After review, the branch push command is:

```sh
git push -u origin feature/olive-unified-agent
```

That later push should run existing Linux portable and Connect portable workflows
(including the Windows Connect matrix). Inspect both hosted jobs and their artifacts;
headless hosted passes would not certify KDE capture/input. No push, merge, release,
tag or hosted run was performed during this implementation.
