# OLIVE Connect C4 — Devices workspace

C4 adds the Devices workspace to the accepted desktop application, using real
C1–C3 state and OLIVE's existing local confirmation architecture. The exposed
network capabilities remain exactly `connect.ping`, `device.status`, and
`chat.metadata.read`. No remote content, file, model, Studio or control access
was added.

## Design and routes

Source of truth: [accepted exported artifact](design/olive-connect-c4-artifact.html),
“OLIVE Connect Devices workspace”, originally
[the accepted Claude artifact](https://claude.ai/artifact/F5skTscnCC83SsYTtb3pvV).
The complete local export was available and read. Its master/detail structure,
300-pixel device rail, centered detail column, panels, segmented permissions,
comparison dialog, activity and revocation presentation informed the implementation.
Existing OLIVE tokens supply dark/light colors, typography and focus treatment.
Prototype scenarios, random QR cells, fake devices, fake latency and timer-driven
pairing/discovery are excluded from production.

One primary route, `devices`, is registered in `desktop/src/navigation/features.ts`.
Aliases include devices, connect, pair and paired devices. No duplicate Connect
workspace is registered. `features/devices/Devices.tsx`, `Pairing.tsx`, `types.ts`
and scoped `devices.css` implement the workspace. The existing `Sheet` supports a
centered variant for Connect's trusted approval; other sheets retain their layout.

## Local state and networking

This Device reads persistent C1 metadata, OS information and the existing public
fingerprint, without accessing the vault merely to open the workspace. Core
availability means the local application service is available; it does not claim
an Ollama model is running. Display-name changes preserve UUID and key identity.
Private keys, vault references and standalone certificates never enter the snapshot.
The public C2 offer necessarily includes its reviewed public certificate.

Connect remains Off after every application restart. No startup option or persisted
network-enable preference was added. The UI requires explicit selection from C3's
real approved interface candidates and calls `enable_network` only after the user
chooses Turn Connect on. Nearby discovery is a separate opt-in checkbox, off by
default. Changing interface/discovery requires disabling first. Service lifecycle
locking serializes enable/disable/shutdown so an in-progress enable cannot leak a
listener after shutdown.

Starting, On, Off and Failed derive from the local enable operation and actual
network owner. Failed startup retains a bounded category. The UI provides scoped
Connect TCP/mDNS guidance; it does not modify firewalls. Interface metadata is not
a trust decision. Nearby entries remain visibly Discovered/Unpaired/Untrusted.
A discovered endpoint can be selected for an existing paired identity, but C3
still verifies that exact identity. There is no discovery-to-pairing conversion.

Device details distinguish offline, connecting, authenticating, online, failed and
revoked. Only authenticated live local channels show “Encrypted · TLS 1.3”.
Measure latency performs a real Connect ping. A denied ping shows an error, not
an invented latency. C3 clears its measurement on disconnect. Recorded last-seen
and paired timestamps remain separate from current connection state.

## Pairing and current limitation

Create pairing calls real C2 `create_offer`. Pinned `qrcode.react` renders the exact
strict offer string; no permissions or private material are added. The displayed
expiry derives from the backend expiry, with an independent display clock and
backend monotonic expiry enforcement. Expiry hides the QR and prevents confirmation.
Regeneration cancels the old active offer and creates a new session UUID.

The new C2 `presentation` accessor exposes only session state, expiry, candidate
UUID, public fingerprint, full session comparison and completed device UUID. It
never serializes the TLS object. Candidate names/platforms are not in the reviewed
C2 offer, so the UI does not invent them. Paired metadata remains “unknown” where
C2 did not record it.

Both devices must compare the complete C2 value. The user enters/pastes the value
observed on the other device; the backend's unchanged exact comparison enforces
mismatch failure. There is no skip or auto-confirm. Local confirmation waits for
the other side's authenticated confirmation before the real record is completed.
All permissions start Off. Pairing never claims the device is currently online.

**Ordinary desktop-to-desktop pairing transport is not implemented in C2/C3.** C2
exchanges in-memory TLS bytes; C3 accepts already-paired identities only. C4 does
not silently add an unauthenticated pairing listener or expose TLS exchange to the
renderer. Production explicitly explains this limitation while presenting real C2
offers. The existing compatible synthetic C2 peer drives complete acceptance over
private test-process pipes. There is no Mobile app, scanner or camera access. This
is a real pairing UI over C2, not a claim that two ordinary desktop installations
can yet exchange pairing traffic without a compatible peer adapter.

## Permissions and trusted Ask

Rows combine artifact categories with the local capability registry and current
per-device permissions. Connection and Personal rows present the three actual safe operations;
Personal, Files, Development and System retain the future vocabulary as Unavailable.
Unavailable has no actionable Allow/Ask buttons. The facade also refuses unsupported
changes, even if a renderer bypasses its controls. Off maps to existing `deny`;
Allow and Ask persist through the normal deterministic setter. Permission changes
produce privacy-bounded activity events.

`ConnectApprovals` is an adapter to `Host.confirm`/`ConfirmationRequest`, not a new
confirmation UI engine. Authenticated Ask requests receive `confirmation_required`
promptly. The trusted local approval appears using the existing pending registry,
ID/fingerprint matching, event stream and `approval.respond` route. It shows the
source device, requested safe operation, target device, Deny and Allow once. It
contains no raw protocol JSON or executable remote markup. Remember is omitted.

To preserve C3's five-second request and 60-second idle bounds, the peer retries
**the identical envelope** after local approval. Measure latency retains its pending
envelope (bounded to 32, at most 120 seconds) and explicitly tells the user to
retry after approval; it does not create a new request ID on that retry. The initial pending request does
not execute. Approval binds authenticated public fingerprint, source/request IDs,
complete canonical envelope digest (target, operation, arguments and times), and
paired-record revision. Changed duplicates invalidate the approval. Permission
writes/revocation invalidate it immediately. Execution still passes both C3
transactional authority checks and the durable replay claim/result ledger.

Allow once authorizes only that request, leaves the saved rule at Ask, and cannot
cause a second execution: identical retries return the durable result after current
authority checks. New request IDs need new approval. Approval entries are bounded
to 32 and expire no later than the request's remaining lifetime (maximum 120 seconds,
with monotonic bounds). Disable/revoke/shutdown cancel pending local prompts. No
remote approved/confirmed/allow/remember field is accepted. No C3 timeout, connection
limit or capability was broadened.

## Bridge and privacy

`olive/bridge/connect_routes.py` and `desktop/electron/connect-contracts.ts` define
strict allowlisted methods through the existing isolated Electron preload/IPC and
Python bridge. The namespace is local IPC only; C3 does not dispatch these methods.

| Methods | Purpose |
| --- | --- |
| `connect.snapshot` | Public local/paired state, candidate interfaces, untrusted nearby entries, bounded activity |
| `connect.enable`, `connect.disable` | Explicit local network lifecycle |
| `connect.rename` | Local display name only |
| `connect.permission`, `connect.revoke` | Deterministic grants and permanent revocation |
| `connect.open`, `connect.disconnect`, `connect.ping` | Explicit paired endpoint, disconnect, measured ping |
| `connect.pair_create`, `connect.pair_status`, `connect.pair_confirm`, `connect.pair_cancel` | Public C2 presentation and local ceremony actions |

No database, vault, socket, arbitrary service object or Python invocation is exposed.
Snapshot polling is sequential (1.5 seconds) and ends on unmount. The fixed read-only
snapshot bypasses the Host's action-deduplication cache so leaving Devices open does
not consume all 2,048 action entries. Mutations retain that cache and its guard.
Pairing polling stops in terminal states. Interface and provider exceptions are
represented by bounded categories, not raw secret-bearing exception strings.

Revocation persists C1's tombstone, clears permissions, cancels approval/reconnect
intent and closes live C3 channels. Revoked views offer no reconnect or delete.
C2 does not support pairing the same revoked identity again. The UI states this
rather than promising that a new QR removes revocation.

Activity uses the existing latest-1,000 bounded audit, with the latest 200 returned
per snapshot. It shows timestamps and known connection, pairing, permission and
request outcomes, never message/file contents, offers, comparison values or keys.
Discovery refreshes do not write activity.

## Accessibility and responsive behavior

Semantic buttons, labelled inputs, visible inherited focus, text state labels and
`aria-pressed` permission groups support keyboard/screen-reader use. Radix dialogs
trap/restore focus; Escape cancels pairing/revocation or denies an approval. Copy
controls copy only the public offer/comparison. Long UUIDs/fingerprints wrap.
Reduced-motion styling avoids animation. Dark/light use the same global tokens.

Wide layouts retain the full rail/detail structure. At workspace width 900 pixels
or below (including the requested 1100-pixel application window with navigation),
the list and selected detail occupy separate full-width views with Back to devices.
Small permission layouts wrap controls, retaining 32-pixel button heights. The
application never relies on horizontal scrolling to fit Devices.

## Validation and evidence

Tests and final run results are recorded below after acceptance. Tests use isolated
synthetic profiles. No personal keys/accounts, Ollama, GPU, KDE wallet, Internet or
multicast are required by the portable Connect suites.

- `tests/test_connect_workspace.py`: real C2 sessions, expiry/mismatch, interface
  lifecycle, privacy, exact Host approvals through real C3 TLS, Off/Ask/Allow once,
  denial, changed requests, revocation, disable and read-polling cache exhaustion.
- `desktop/tests/connect.test.ts`: route/aliases, strict bridge schemas, safe
  capability controls, truthful status/latency, real QR rendering and escaped
  approval presentation.
- `desktop/tests/e2e/connect.spec.ts`: actual Electron UI and a second Python C2/C3
  process. The test-only startup shim uses synthetic memory vaults; private pipes
  carry pairing TLS bytes between test peers. Production contains no fixture switch.
  Nearby visual coverage injects a controlled test directory; it is explicitly not
  a claim of physical multicast discovery. All connection/latency/approval results
  use real loopback TLS, not React fixture state.

Screenshots are captured under ignored `artifacts/connect-c4/`: This Device Off/On,
paired offline/online, Nearby empty/discovered, QR, full comparison, permissions at
1920×1080, 1440×900, 1366×768 and 1100×760, Ask approval, activity, narrow list/detail,
light mode, connection failure, revoke confirmation and revoked state. They contain
synthetic identities and host interface candidates; no user profiles are committed.

## Remaining limitations

In addition to pairing transport above, native Windows networking/vault acceptance
cannot be certified on this Linux host. Existing Windows contracts and portable
CI remain intact. Physical LAN/firewall and host mDNS acceptance remain separate;
C4 does not claim a physical second-machine run. No installer, release, push or
merge is included. Future capability work remains C5 structured record sync, C6
file transfer, C7 remote AI, C8 remote Studio, C9 Mobile, C10 remote/direct/relay.

## Recorded acceptance

Implementation commits: `c9c0f14` (backend/approval contracts) and `7bb9bfe`
(Devices UI and two-process acceptance), on `feature/olive-connect-c4`.

Final Linux checks on this branch:

| Check | Result |
| --- | --- |
| Complete Python regression suite | 956 total: **948 passed**, 8 Windows-only skips, zero failures/errors |
| Connect C1–C4, included above | **102 passed**, including 12 C4 cases |
| Frontend unit tests | **39 passed** in 13 files |
| TypeScript / ESLint / production renderer and Electron builds | Passed |
| Combined native desktop run | **9 passed**: two C4 cases, GO, Linux auto/Wayland, L3 reminder, two Studio cases, media import/edit |
| Final focused C4 UI rerun | **2 passed**, screenshots refreshed, exact-request approval and owned process cleanup verified |
| Repository-source compilation | Passed |
| Exact `python -m compileall -q .` | Existing ignored PySide6 Android Jinja `__init__.tmpl.py` syntax error; not marked passed |
| Dependency consistency and diff review | Passed |

The previous full-suite warning about 26 uncollectable Python objects remains.
Owned Connect and Electron process cleanup passed separately. These are local host
runs, not claimed GitHub runner results. No native Windows pass is inferred from
portable coverage. Earlier development failures (sandbox interface restrictions,
test selector expectations, a wrong test module name and a lint fix) were corrected
and are not counted as passes.

Logs: `/tmp/olive-c4-python-final.log`, `/tmp/olive-c4-desktop-final.log`,
`/tmp/olive-c4-ui-final.log`, `/tmp/olive-c4-build.log`, and
`/tmp/olive-c4-compile-final.log`. Reproduce the portable checks with the repository
Python/Node toolchains and the standard AGENTS.md commands; include
`tests.test_connect_workspace` in the dedicated Connect command. Run
`npx playwright test connect.spec.ts` from `desktop` after building for the isolated
UI acceptance. Headless Linux runners can provide their supported Xvfb display;
Wayland/Plasma smoke remains separate native-host acceptance.

Selected local evidence:
[This Device](../artifacts/connect-c4/this-device-on.png),
[permissions](../artifacts/connect-c4/permissions-1440.png),
[pairing comparison](../artifacts/connect-c4/pairing-comparison.png),
[Ask](../artifacts/connect-c4/ask-approval.png),
[narrow detail](../artifacts/connect-c4/narrow-detail.png),
[light mode](../artifacts/connect-c4/light-mode.png),
[revoked](../artifacts/connect-c4/revoked.png).
