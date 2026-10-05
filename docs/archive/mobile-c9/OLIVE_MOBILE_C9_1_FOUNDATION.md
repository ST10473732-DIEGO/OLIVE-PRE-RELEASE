# OLIVE Mobile C9.1 — native iPhone foundation

## Repository checkpoint

- `BASELINE_HEAD`: `dd1a041dc0353710be83f2f02a1fad913265faf6`.
- `BASELINE_BRANCH`: `feature/olive-mobile-c9`.
- `WORKTREE_STATUS`: clean before implementation.
- Local commits:
  - `5fa928c1c7f9c7a0f2502578c9437543d2d88f26` — native project, shell,
    design system, storage, Connect/Keychain interfaces and initial tests.
  - `2ba328acd1d994343ce89e35b91da5958d58b83b` — accessibility/layout refinements
    and real-iPhone acceptance checks (final validated implementation).
  - This report's documentation commit — foundation report and project journey.
- `FINAL_HEAD`: the documentation commit containing this report (resolve with
  `git log -1 --format=%H -- docs/OLIVE_MOBILE_C9_1_FOUNDATION.md`). A commit cannot
  embed its own hash; the final handoff reports that resolved hash explicitly.
- No reset, stash, branch switch, cherry-pick, merge, tag, release or push.

The starting point includes the completed unified-agent work and subsequent
Grove/Discord improvements. Only mobile sources, iOS ignore rules and milestone
documentation change. Desktop identity, Python, Electron, Connect C1–C8,
shared data and historical freeze artifacts remain intact.

## Project and toolchain

| Item | Value |
| --- | --- |
| Project | `mobile/ios/OLIVEMobile.xcodeproj` |
| Shared scheme / app target / module | `OLIVEMobile` |
| Test targets | `OLIVEMobileTests`, `OLIVEMobileUITests` |
| Display name | OLIVE |
| Bundle ID | `io.github.st10473732-diego.olive.mobile` |
| Version / build | 0.1.0 / 1 |
| Deployment target | iOS 17.0 |
| Language | Swift 6; installed compiler Swift 6.4 |
| Xcode | 27.0 (`27A266a`) |
| SDKs | iOS / iOS Simulator 27.0 |
| Host | macOS 26.7 (`25G229`), arm64 |
| Runtime dependencies | Apple frameworks only; no Swift packages |

The bundle ID uses the existing GitHub owner namespace from the repository
remote, rather than inventing an owned commercial domain. It is the stable
mobile signing/container identifier, with `.connect` appended for the default
Keychain service. It is independent of the historical desktop compatibility ID
`local.dmdo.desktop`. Team selection stays local; no personal account, device
identifier, provisioning profile or signing credential is committed. Future
App Store/TestFlight enrollment is not performed or certified here.

iOS 17 permits Observation, modern SwiftUI navigation, and growing multiline
input without requiring the newest installed OS. The native system font family
provides scalable display/body/monospaced type. The app targets iPhone and
supports both landscape orientations as well as portrait. No newer hardware API
is assumed. The Mac's active developer directory points to Command Line Tools;
commands select Xcode through `DEVELOPER_DIR` without changing `xcode-select`.

## Sources and design precedence

Read current `AGENTS.md`, `README.md`, `DESIGN_SYSTEM.md`, `pyproject.toml`,
`desktop/package.json`, shared identity, current source layout and the following
references. No `CLAUDE.md` was found in this checkout.

1. [OLIVE Grove](../../design/OLIVE_GROVE.md), approved 26 September 2026, plus current
   `desktop/src/design/tokens.css`, `grove.css`, Home and `OliveLogo`.
2. [Design System V2](../../design/OLIVE_DESIGN_SYSTEM_V2.md) and its HTML artifact.
3. [Historical mobile C9 specification](../../design/OLIVE_MOBILE_C9_DESIGN.md) and
   `olive-mobile-c9-artifact.html`.
4. [Core/app boundaries](../../architecture/core-app-boundaries.md), current desktop Chat
   contracts and C1–C8 documentation, especially [C4.1 pairing](../../connect/pairing.md).
5. `assets/branding/olive-mark.svg`, `olive-source.png`, `olive/identity.json`.

`git ls-tree`, `git show` and `git diff` inspected
`origin/feature/olive-connect-c9` without checking it out. The historical mobile
specification matches the current copy; it remains a design reference, not an
implementation or authority contract. The newest Grove document refers to a
phone prototype, but no separate newer phone prototype file exists in the
tracked current design directory. The implemented current Grove tokens and
canonical mark take precedence over the older navy/blue mobile artifact.

Mobile adaptations:

- Grove near-black ground, olive-tinted sheets, muted olive interaction accent,
  green/pimento identity mark; blue reserved for information/computation.
- Native Home / Chat / Devices tabs. Settings is a dismissible sheet from Home
  or Devices, preserving the historical occasional-destination pattern.
- Today/Files and the desktop's seven-space navigation are deferred: the shell
  has no empty navigation machinery for unavailable product areas.
- One assistant and one Chat. No model/planner modes, fake histories, devices,
  connection strength, model labels, pending counts or generated responses.
- Native scalable text, 44-point controls, flexible scroll layouts, safe-area
  composer inset, portrait/landscape support and stable accessibility IDs.
- Solid surfaces, no ambient animation. Future message auto-scroll respects
  Reduce Motion. Code blocks use selectable monospaced text and horizontal scroll.
- App icon is the existing mark rendered on an opaque Grove background; its
  reproducible CoreGraphics renderer is included under `mobile/ios/scripts`.

## Architecture and state

`OLIVEMobileApp` is the composition root. A main-actor `@Observable AppState`
receives a `ShellStore`, `ConnectClient` and `PairingService`; it is scoped to
this app, not a global singleton. `RootView` owns native navigation and the
Settings sheet. Small feature views consume state; no view performs network or
Keychain operations. Reusable theme/components own presentation tokens.

`Destination` restores the selected tab from namespaced `UserDefaults`, with
unknown values falling back to Home. Drafts are preserved independently of
navigation in an atomic JSON envelope (`version: 1`, `text`) in Application
Support. The draft directory is excluded from backup and the file has complete
file protection. Save errors retain text in memory and display an honest notice.
Unreadable or newer-version files are preserved without overwrite; migrations
for future formats must explicitly import them. Scene inactivity requests a
save; changes are also saved as they occur. No desktop conversation database,
chat synchronization, model cache or paired-device record is copied.

Chat remains empty and Send disabled because C9.1 has no transport. Editing a
draft never creates a user message or an OLIVE response. The UI says what is
local and what requires a future connection. `ChatMessage` is a presentation
value with user/assistant attribution and text/code blocks; it is not a new wire
schema. The shell has no local demo backend or simulated streaming.

## Connect and security boundary

`ConnectTypes.swift` defines domain projections of public device identity,
paired-device display metadata, exact C1 connection-state/capability vocabulary,
and separate local not-paired presentation state. These types deliberately do
not conform to `Codable`: C9.1 does not claim an interoperable parser by omitting
strict validation. Capability advertisement alone never grants access.

`ConnectClient.pairedDevices()` is asynchronous; the disconnected implementation
returns an empty inventory. `PairingService.begin(publicOffer:)` reserves the
exact bounded C4.1 public-offer bytes as its input; the unavailable implementation
throws rather than simulating success. Cancellation is safe without a session.
No discovery, socket, network grant, credential or synthetic device is created.

`SecretStore` is an injectable asynchronous boundary. Its actor-backed Security
framework implementation uses an app-specific service, nonsynchronizing items
and `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`. Updates preserve item scope;
deletes affect only an exact service/account. C9.1 production does not call it
to create identity material. Tests use only synthetic bytes in UUID-scoped
services and remove them. Private keys, certificates and pairing material never
enter preferences or plist source files.

There are no ATS exceptions, permissive certificate delegates, LAN/Bonjour
entitlements, camera prompts, cloud APIs, analytics or relay code. The privacy
manifest declares only app-owned defaults access (`CA92.1`), matching
[Apple's required-reason documentation](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitypereasons).

## Reproduction and acceptance

Exact portable build/test/install commands are in
[mobile/ios/README.md](../../../mobile/ios/README.md). Build outputs and xcresults live
outside tracked source; `artifacts/mobile-c9-1/` is ignored for local evidence.
Personal signing information is intentionally excluded from this report.

- `xcodebuild -list`, `-showBuildSettings` and `-showdestinations`: passed.
- Simulator Debug app + both test bundles: built for arm64 and x86_64. No
  simulator runtime or simulator device was installed (`simctl list runtimes`
  and available devices were empty), so simulator launch/tests were not run.
- Generic iOS device: signed Debug test build and unsigned Release build passed.
- Actual device: Xcode detected **iPhone 15 Pro Max (iPhone16,2), iOS 27.0,
  build 24A437**, connected by USB, with Developer Mode enabled.
- Signing: the existing Apple Development identity/team provisioned the app and
  test runner automatically. The first generic profile contained only the Mac;
  rebuilding for the actual iPhone with device registration fixed the profile.
  Installation then succeeded. The owner unlocked the phone and explicitly
  trusted the developer certificate in iOS Settings; no credentials were changed.
- First live run: all **11 unit tests passed**, **6/7 UI tests passed**. The
  Settings test assumed its combined native version row had a separate text
  element. Added explicit accessibility label/value semantics and tested those.
  Review also shortened the pinned composer status at large text sizes and moved
  the long pairing explanation into the scrollable content. XCTest's app-window
  screenshots cropped rotated content; final captures use the screen only after
  asserting OLIVE is foreground, including its keyboard. No unrelated phone
  content is inspected.
- Final complete device run: **11 unit + 7 UI tests passed, 0 failures, 0 skips**,
  in `/tmp/olive-device-tests-4.xcresult`. UI suite: 66.092 s; overall test
  operation: 71.709 s. A separate focused keyboard rerun passed 1/1 after adding
  an explicit visible keyboard-height assertion and a before-typing capture.
  It is supplemental evidence, not an extra unique test in the aggregate.
- Final normal `devicectl device process launch` succeeded without test arguments.
  The installed application reports **OLIVE**, version **0.1.0**, build **1**.
  The canonical opaque 1024-pixel icon is bundled; the Home screen was not
  captured because it would include unrelated applications.
- The final changed Swift sources also passed simulator app/test compilation
  and generic iOS Release compilation. No Swift source warnings remain;
  Xcode's AppIntents extractor notes there are no AppIntents, as expected.
- No live model, pairing, remote Chat, file transfer or synchronization claim.

### Real-device acceptance matrix

| Check | Result / evidence |
| --- | --- |
| Launch | Passed unit/UI runner launches and separate normal launch |
| Identity | Exact installed bundle filter reports OLIVE 0.1.0 (1); canonical icon asset compiled |
| Home | Native screen rendered; real-device screenshot reviewed |
| Chat | Opens from Home and its tab; empty, no fabricated messages |
| Keyboard | Appears on tap; XCTest existence + height assertion, before-typing screenshot reviewed |
| Multiline | Two lines entered and retained; Send remains disabled |
| Navigation | Home / Chat / Devices and Settings dismissal passed |
| Devices | “No paired devices” and future pairing explanation verified |
| Settings | About, installed version/build, disconnected state and Done passed |
| Relaunch | Draft and selected Chat tab survive terminate/launch |
| Background / foreground | Synthetic local draft survives Home-button background and app activation; no observed crash |
| Safe areas / orientation | Portrait and landscape screenshots reviewed; controls usable, native insets preserved |
| Accessibility | Largest accessibility text size exercised, composer remains editable; labels/values/IDs tested |

The screenshot captures are under ignored `artifacts/mobile-c9-1/device-final/`;
`keyboard-check/` contains the visible keyboard evidence. Test-only launches use
isolated namespaces and never populate the normal user's draft. No unrelated
phone files, messages, photos or app content were read.

### Limits

- No simulator runtime was installed, so no simulator boot/launch/runtime test
  is claimed. Compilation of simulator app and test targets passed.
- Physical runtime verification is on this iPhone/iOS 27 only. The iOS 17
  deployment target compiled successfully but was not tested on an iOS 17 phone.
- VoiceOver identifiers/labels and large text were checked; a comprehensive
  manual VoiceOver or accessibility certification was not performed.
- The existing development team/certificate was used; this is a development
  installation with provisioning expiry, not TestFlight or App Store distribution.
  Signing team IDs and credentials are not stored in source. The required unlock
  and trust actions were completed by the owner; no current launch blocker remains.
- Pairing, remote answers/actions, live message streaming, C5 continuity, files,
  Today, Studio and C10 remain intentionally unavailable. Auto-scroll/message
  presentation is prepared, but no live network stream was tested.
- The desktop regression gate retains the four baseline Mac failures below.

### Desktop regression validation

The Mac initially had only Python 3.9 and no repository dependencies. A disposable
Python **3.13.15** environment under `/tmp` installed the declared runtime and
mail-test requirements. `OLIVE_DATA_DIR`, cache and temporary paths were isolated;
the real OLIVE profile was not used. The first sandboxed run could not create
Connect loopback sockets and is not presented as a valid regression pass.

`python -m compileall -q .` passed with a writable temporary bytecode cache.
`python -m unittest discover -s tests -v` then ran with loopback/subprocess access:
**1,430 tests, 1,369 passed, 57 skipped, 2 failures and 2 errors** (193.152 s).
The desktop gate is **not green on this Mac**. All four nonpassing tests reproduce
against a `git archive` export of unchanged `BASELINE_HEAD` in a separate `/tmp`
directory, without switching the worktree:

| Baseline test | Observed result on this Mac |
| --- | --- |
| `test_connect_studio.StudioTests.test_cancel_reaps_owned_descendant_and_duplicate_cannot_spawn` | Child-process wait exceeds 3 seconds (`psutil.TimeoutExpired`) |
| `test_desktop_linux_readiness.ProcessReadinessTests.test_window_binding_preserves_pid_lifetime_and_entry_identity` | Linux executable validation rejects the Mac's non-ELF binary |
| `test_owner_chat_files.OwnerChatFilesTests.test_selected_workspace_reference_runs_exact_owned_project_without_prompt` | Native project run reports `failed`, expected `completed` |
| `test_project_creation.DiscoveryTests.test_missing_toolchain_never_offers_creation` | Missing-toolchain detail reports `JDK detected`, expected `not found` |

These failures were preserved and not patched as part of Mobile. A diff against
the baseline confirms no desktop/Python/Connect/test sources changed. Existing
Electron/Linux live workflows were not rerun or certified on this Mac. Local
logs, including baseline reproductions and retained failed iPhone runs, are under
ignored `artifacts/mobile-c9-1/` or the documented `/tmp/olive-*` result paths.

## Exact C9.2 next steps

1. Prove Apple-platform interoperability with the unchanged desktop peer before
   building the pairing UI. Audit `identity.py`, `tls_identity.py`,
   `pairing_wire.py`, `pairing_completion.py`, `network_wire.py` and their tests.
   The Ed25519 self-signed X.509 identity, TLS 1.3 mutual authentication, exact
   certificate pins, arbitrary exporter label/context and receipt signing are
   required. Establish whether Apple transport/identity APIs expose all of
   those operations; do not silently substitute public-CA trust, a PIN, a new
   key algorithm or another handshake. Any dependency needed to bridge an API
   limitation needs a separately reviewed, bounded design.
2. Add bounded, strict C4.1 `olive-pairing-tls13/2` offer/reply validation against
   real Python fixtures: exact fields, canonical numeric local endpoint,
   identity validation, UUIDs, expiry, duplicate fields, limits and transcript
   canonicalization. Public discovery endpoints are untrusted routing hints.
3. Implement protected identity/repository storage and recovery using the
   Keychain boundary. Preserve pending completion receipts and revoked identity
   rules. Never repair a key mismatch by silently generating replacement keys.
4. Implement explicit opt-in local discovery with Apple Network/Bonjour support
   and correctly scoped local-network usage declarations. No Internet relay.
5. Implement native pairing screens with the **full 256-bit exporter
   comparison**, both users' confirmation, expiry/mismatch/cancel/loss states,
   and durable `olive-pairing-completion/1` receipts. The historical six-character
   mock and word fingerprint are not the current desktop trust protocol.
6. Establish a separate pinned C3 channel with its framed encrypted hello,
   replay/revocation checks and resource limits. Pairing itself leaves every
   capability Off. The phone never inherits desktop Owner Mode.
7. Bind normal Chat to C7 `olive-inference/1`: public preset availability,
   exact start/poll/status/cancel envelopes, content-only sequenced events,
   permission/approval states and bounded output. No invented streaming JSON,
   phantom messages, automatic retry after uncertain completion or fake model
   availability. Connect permissions remain authoritative for remote actions.
8. Only then connect conversation continuity through C5's signed, revisioned
   record contract. Drafts remain local; do not send desktop databases. Leave
   file transfers, Today, Studio and broader capabilities for their scoped steps.
9. Run Swift/Python interoperability fixtures and two-device acceptance, including
   expiry, mismatch, interrupted completion, deny/ask/allow, disconnect, revoke,
   cancellation, background/foreground and protected-data availability. Extend
   UI tests from the currently truthful disconnected shell.
