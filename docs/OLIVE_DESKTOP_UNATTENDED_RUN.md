# Unattended Linux Desktop Control continuation

2026-09-23. Starting checkpoint `a84b035536f4cb2bf980398a3cd2f7005ecd5fdc`,
on `feature/olive-desktop-control-linux-v1`, with a clean worktree. The original
milestone BASELINE_HEAD remains `2df73b31ca11374978363a8f9d9c34ab052a74a4`.
No reset, new renderer exception, model migration or profile migration.

Implementation commits: `c608f29` (portal/capture), `df46d6c` (task adaptation and
readiness), `cb71fa0` (unattended preflight), `f6fbb4a` (PTY/SDK fixture), and
`0abec94` (Connect handshakes), and `0a07c9c` (app/policy checks before consent).
The final documentation commit records this report
and the content-free `evidence/linux-desktop-unattended.json` manifest.

**The milestone is still incomplete.** These changes repair independently
reproducible defects and prepare the next human-controlled acceptance. They do
not certify general desktop operation, Discord delivery or screenshot grounding.

## COMPLETED WITHOUT USER PRESENCE

### Consent failure cleanup

Tests reproduced retained session handles after denied/timed-out shortcut binding
and after failed RemoteDesktop device/source consent. A subsequent binding could
then fail with “Shortcut session already exists”. The portal adapter now closes
the exact failed session and clears its ownership. An empty assigned shortcut
is rejected and closed; a second control start cannot replace a live session.
Control-consent failure preserves an independently verified shortcut session.
No consent dialog was opened during this continuation.

### Native capture prerequisites and encoding

The new read-only preflight found an actual missing `pngenc` element, despite
GStreamer itself being installed. `gst-inspect-1.0 pngenc` reproduced the failure.
The matching package transaction would have installed `gst-plugins-good`
1.28.7-2.1 and wavpack 5.9.0-1.1 (3,511,075 bytes total download). `sudo -n -l`
reported that authentication was required. No password was requested, package
installed or OS protection changed.

Instead, capture now uses the already-installed GStreamer base conversion elements,
typed GstApp/GstVideo interfaces and distribution Pillow 12.3.0. RGBA frames are
encoded transiently to PNG with explicit dimensions, stride, offset, memory and
output limits. VideoMeta row padding overrides negotiated default layout. Native
testing also exposed a missing GstApp import: requiring its GI version alone did
not attach `try_pull_sample` to AppSink. The typed import fixes that defect.
Constructor failure now closes its transferred PipeWire descriptor.

The real installed pipeline encoded synthetic red/green/blue sources at 640×360,
641×359 and 1280×720 with exact dimensions and pixel values. A fourth padded-row,
nonzero-offset buffer verified VideoMeta handling. A construction-error check
verified descriptor release. No frame was captured from a display or persisted.
The sub-20ms synthetic encoding samples are **not desktop capture latency**.

### Bounded adaptation and task authority

Changed target geometry/identity now discards the old proposal and permits at most
three fresh replans within the existing 24-step/time/grant limits. A changed account
or destination still stops the task. A submission is never retried after uncertain
execution. Deterministic race tests cover both successful reacquisition after a
move and continuously moving controls that receive no input.

When native semantics already identify a unique empty search field/composer and
the literal requested content, ordinary code proposes the next focus/type/submit
step. The normal broker, fresh observation, policy checks and durable submission
reservation still validate every step. Completion uses deterministic evidence.
A test completes an exact send with zero confirmation calls and zero model calls.
This does not certify the semantics of any real third-party messenger.

Message content cannot be entered into an unresolved destination or unrelated
editable field. Enter cannot submit from an unrelated control simply because the
correct draft exists elsewhere. Unrelated drafts remain untouched. The semantic
fast path requires an actual Send button; it does not guess whether Enter sends
or inserts a newline in an unknown application.

Quoted send/draft requests can omit an account only when the scoped app exposes
one unambiguous current-account label. A trusted resolver narrows the finite grant
once; the original request digest, task ID, epoch and expiry remain unchanged.
The previous grant object becomes invalid. Duplicate/missing account evidence
requires clarification; a model cannot supply the account binding. Explicit
account selection never changes. “Please …” and “Search for … in APP” forms are
also recognized without an interpretation-model call.

This is still a bounded grammar, not arbitrary natural-language authorization.
Account/destination/composer evidence uses conservative native semantic conventions;
application-specific live validation is required before claiming real messaging.

### Application readiness and initial focus

After exactly one launch, process discovery has a three-second finite startup
budget. Its 100ms metadata polling handles process creation, not action replay.
Browser subprocesses with a matching parent are excluded as independent app roots.
No user-owned app is killed. Tests use a controlled clock, not timing sleeps.

For a unique process lifetime and one window within the approved display, the
native adapter can make one supported AT-SPI focus request. It waits on native
window/activation events for at most five seconds and verifies ACTIVE state.
Multiple windows, dialogs, refused focus, Stop or expiry prevent input. This runs
only at task admission; it does not repeatedly steal focus after user takeover.
Event listeners and deadline sources are removed on every exit. Focus remains
non-atomic with later input, and global physical takeover detection remains absent.

### Unattended preflight and portable fixture repair

From the repository root:

```sh
.venv/bin/python scripts/check_linux_desktop_setup.py
/usr/bin/python3 scripts/check_linux_capture_pipeline.py
```

The first command imports installed native dependencies, checks actual GStreamer
factories/libei symbols, reads application portal interface versions and resolves
reviewed installed app entries. It does not enable policy, request consent, bind
shortcuts, capture, inject input or run inference. Its helper is closed on success
or failure. Optional `--output NEW_FILE.json` creates a private content-free report
and refuses to overwrite an existing file. Exit 0 means prerequisites were inspected;
the explicit result remains `BLOCKED_REQUIRES_LOCAL_HUMAN`, not a live-control pass.

Normal task admission also resolves the installed app and checks deliberate
policy denies before requesting compositor consent. A regression reproduced the
old unnecessary consent call for a missing app; the repaired route makes no consent
or launch call in that case and does not start a helper merely to clean up nothing.

The first full Python run reproduced three .NET fixture failures when the SDK was
installed locally but absent from the shell PATH. `_dotnet_solution` now uses the
same `developer_environment` resolver as normal OLIVE launch. Its real build,
OmniSharp and netcoredbg assertions remain intact; no target framework or skip
was changed. See the evidence manifest for the final fresh full-run totals.

### PTY and Connect shutdown races

A subsequent full run exposed a PTY `EBADF` when the natural reader exit and
user Stop both closed the master descriptor. Catching `EBADF` would not protect
a newly recycled descriptor. A short descriptor lock now serializes resize/read/
write/close, transfers ownership before close, and never spans process termination
waits. The read/select section is bounded to 50ms. Event-controlled concurrent-close
tests and the real owned child/terminal cleanup test pass; no unrelated process is
terminated. These are lifecycle protections, not a measured live emergency Stop result.

The same full run also exposed a Connect replacement channel lost while a real
receipt writer was held. A fixed twelve-trial diagnostic run reproduced it once;
diagnostics showed competing replacement generations, without authority-storage
failures. An event-gated test then proved that concurrent calls to the same peer
could create two same-direction outbound handshakes (`2 != 1`). Their independent
adoption can select different sockets at the two endpoints. This matters when a
manual connection races the existing automatic reconnect worker.

`LocalNetwork.connect` now shares the exact pending handshake for the same peer
and endpoint, under the existing network lock. A different pending endpoint fails
with existing backpressure behavior. TLS, paired-identity checks, cancellation,
connection deadlines, opposite-direction collision selection and commit-boundary
authority remain unchanged. No request/effect is replayed, no timeout is enlarged,
and file invalidation fences remain in place until durable receipt commit. The
event-gated regression failed before the repair and passed afterward. Diagnostic
trials and fresh complete Connect/Python runs are recorded separately in evidence.

## COMPLETED BUT REQUIRES LATER LIVE VERIFICATION

Portal failure cleanup, capture encoding, process/window readiness, initial focus,
bounded replanning and ordinary direct-message authorization have implementation
and deterministic/native-synthetic evidence. They still need actual KWin portal
and application acceptance. Current evidence does **not** prove live PipeWire
frames, EIS injection, real focus safety, real emergency Stop latency, fractional
display behavior, Firefox navigation or message delivery.

The earlier qwen3-vl:8b grounding result remains 2/6 correct. No model was promoted,
downloaded or re-benchmarked here. Screenshot-driven actions remain disabled.
Broad freeform planning, Kate create/save, Dolphin copy/move, settings changes,
selected downloads and real app-neutral messaging are not accepted capabilities.
They need further implementation calibrated against safely observed real controls;
the missing human consent is not represented as proof that this work is complete.

## BLOCKED_REQUIRES_LOCAL_HUMAN

**Reason:** no physical activation of OLIVE's assigned global Stop shortcut has
been received, and no capture/input source has been consented. The user previously
approved the acceptance session, but that does not supply compositor consent.
The new preflight confirms all inspected software prerequisites are now available.

**Minimum resume procedure:** on an idle display containing test apps, run
`./run_olive.sh` (or the installed OLIVE desktop entry). In Settings → Desktop
Control, deliberately enable the intended local policies. In Desktop Control,
submit `Open Kate`. Complete KDE's shortcut dialog yourself, assigning a free key.
Read the actual key shown in OLIVE's returned instruction; focus another app and
physically press it while OLIVE remains open. Once OLIVE reports Stop, use
**Reset Stop** and submit a new task; handle KDE's display/device selection yourself.
The stopped task never resumes automatically. No full milestone rerun is needed.

If consent times out or is denied, the failed session is closed. Do not repeatedly
retry while away. Close OLIVE to release the remaining shortcut/helper lifetime.
There is no system package/password blocker for the current capture implementation.

## NEEDS_USER_CLARIFICATION

No implementation preference is waiting for an answer. At execution time, duplicate
recipients/accounts/windows, unresolved destinations and changed task scope cause
a bounded handoff. A real Discord send additionally requires the user's exact
account/destination/content and platform-risk awareness. No such test was attempted.
Discord prohibits normal-account automation and provides no documented mouse/keyboard
exemption; this is not official platform support or a policy workaround.

## UNSUPPORTED / PLATFORM-LIMITED

Native WinForms remains Windows-only. Global physical-input takeover detection is
unavailable. Inaccessible/visual-only controls remain unsupported by the enabled
input route. AT-SPI focus may be refused by an app/compositor; OLIVE does not bypass
that refusal. Native Windows/macOS and hosted validation remain pending. C7 and
C8 gain no desktop, screen, vision, terminal or additional filesystem authority.

## Preservation, evidence and rollback

Fresh full Python: **1,184 run, 1,176 passed, 8 skipped, 0 failures**, 137.979s;
no uncollectable-object warning. Exact Connect suite: **241 passed**, 89.409s.
Frontend: **96 passed in 18 files**. Typecheck, lint and production build passed.
Repository Python compilation: **699 sources passed**. Literal full-tree
`compileall -q .` was also executed and still reports only the ignored third-party
PySide6 Android Jinja template syntax error, not an OLIVE Python failure.

The final complete Electron run against fixed checkpoint `0a07c9c` passed
**55 tests with 16 explicit skips and 0 failures** (71 total, 7.8 minutes).
Its opt-in live-control and native Windows skips are not live acceptance.
The earlier aggregates and newer focused passes are never added together.

The six inherited Electron cases retain their distinctions: attach-diagnostics,
m2-desktop and owned-launch exercise the implemented Linux diagnostics/policy/Stop
boundaries, with native control acceptance still pending; the approved GO timing
and responsive Explorer fixes remain in place; WinForms remains platform-limited.
These results do not establish Windows, macOS, hosted or real third-party GUI use.

The 225-path freeze still allows only the three previously approved milestone
exceptions. This continuation edits no frozen renderer, Electron, preload, asset
or design path. The V3 wizard fix and model defaults remain unchanged. No user
profile, chat, file, credential, pairing or index was migrated or deleted. Only
isolated test profiles and synthetic data were used. No new dependency was installed.

To undo only this continuation, close OLIVE and inspect a detached checkout with
`git switch --detach a84b035536f4cb2bf980398a3cd2f7005ecd5fdc` from a clean worktree.
To roll back the whole Linux milestone, use the preserved
`feature/olive-backend-models-v3` branch as documented in the backend closeout.
Reopen with `./run_olive.sh`. Keep all profiles, models, SDKs and indexes; do not
reset history or delete data. No push, merge, tag or release was performed.

Primary references checked for this continuation:
[GlobalShortcuts](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html),
[AT-SPI grab_focus](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/method.Component.grab_focus.html),
[GstVideoInfo](https://gstreamer.freedesktop.org/documentation/video/video-info.html),
[AppSink](https://gstreamer.freedesktop.org/documentation/app/appsink.html),
[Pillow Image.frombytes](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.frombytes).
Actual installed interfaces and synthetic execution, rather than newest documentation
alone, establish the reported native prerequisites.
