# OLIVE 3.4 desktop control

OLIVE 3.4 provides universal application control with optional specialized
accelerators. Compatible applications do not require a dedicated adapter.
See [final acceptance](DMDO_3_4_ACCEPTANCE.md) for measured release results.
Acceptance demonstrates bounded operations, not every task in every application.

## Supported and live tested

- One Qt main window with lazy cached workspaces, state persistence, tray navigation
  and explicit pop-outs. Studio-run applications and previews remain separate.
- Generic Windows discovery and UIA. Calculator and the independent Qt fixture
  require no adapter. Real text entry, invocation, search and switching pass.
- Explorer navigation verifies actual location; Settings verifies Bluetooth without
  changing configuration.
- Separate interactive Chrome: semantic DOM inspection, navigation, fill, click,
  select, scroll-to-control, tabs, uploads and quarantined downloads. Local fixture
  send previews and verified download-to-filesystem transfers pass.
- Gmail reaches LOGIN_REQUIRED. Credentials require manual takeover. No password,
  cookie or token store is inspected. No real email was sent.
- Windows system media transport pause/play/pause passes against Chrome's real local
  silent-audio playback. This is actual Chromium and Windows media-session state,
  not a mock. Apple Music session discovery passes; its playback was not validated.
- Microsoft Store search resolves QuickLook, publisher emako, explicit free search
  result evidence and its Get control. An installation preview is generated with
  READY_FOR_CONFIRMED_MANUAL_ACTION. No acquisition or purchase was executed.
- A real Explorer-to-Chrome workflow performs fresh observations, bounded input,
  download and verified filesystem save. Focus handoff is explicitly authorized.
- Emergency stop interrupts a running sequence. Intentional focus loss blocks input
  rather than repeatedly activating the target. Unknown browser modals pause actions
  until reviewed dismissal. Qt remains responsive.
- Authorized window capture and qwen3-vl visible-label verification pass on a custom
  painted Preview target. Guarded mouse input passes separately with a test-defined
  target; this is not counted as model localization success.

## Supported but not fully live tested

Generic media also supports next/previous and current title when published by the
application. The default Windows audio-player silent-file probe did not expose a
usable media session; Chrome provided the successful real playback acceptance.

Authenticated OLIVE browser sessions can be used after manual login. Real Gmail
Compose, recipient chips and server-side attachments were not tested because this
environment reached login. Normal personal Chrome profiles are not imported.

Native free-install/send/delete/submit previews bind visible evidence and recheck
it after confirmation. Real consequential execution was not exercised against
Store or accounts. Current price and identity require fresh review before a future
install; the acceptance preview uses explicitly observed search-result price
evidence. Purchase preview data exists, but native paid-purchase execution is
unsupported. Install approval is never purchase or subscription approval.

## Runtime and trust boundaries

The shared ServiceContainer owns controllers and inference. Qt uses its existing
worker bridge; navigation does not restart services. ApplicationSessions preserves
separate windows and bounded task-scoped observations with provenance.
UniversalWorkflow allows at most sixteen known provider operations. Simple Open
commands are deterministic. Other plans use strict JSON; ambiguity requires review.

UIA runs in a short-lived COM helper: 300 controls, sixteen levels and a four-second
traversal budget within a bounded helper lifetime. Store results were hidden beyond
the previous eight-level traversal limit. UWP normalization retains both the real
foreground frame and underlying application identity.

Actions authorize, act, wait, observe and verify. An existing label cannot prove
that a new click succeeded. Failed verification is not retried blindly. Interrupted
sessions recover as PAUSED_REVIEW_REQUIRED, never automatic input. Shutdown drains
cancelled tasks before closing resources. Studio stop also reaps a process when
its collector was cancelled before starting.

Web/application content is untrusted observation data, never permission or policy.
App identity is consistent between discovery and Explorer/Settings accelerators.
DENY is checked again after confirmation. Recognized consequential controls,
including punctuated Send/Get labels and Store acquisition IDs, require dedicated
previews. Misleading or unknown third-party UI semantics require manual review.

Keyboard fallback checks window/control focus before each character. Secret fields
require takeover. Browser launch may switch once from the specifically approved
foreground window; unrelated focus changes still stop input. Clipboard is separately
permissioned and does not feed history, Knowledge or memory.

## Vision root cause and coordinate contract

The installed qwen3-vl:8b is an 8.8B Q4_K_M model using qwen3-vl-thinking
renderer/parser under Ollama 0.33.3. The owned PNG is a valid 500 x 240 client-area
capture. A localization diagnostic generated 600 tokens and 2,100 reasoning-channel
characters, ended with done_reason=length, and returned zero final-content
characters. Earlier bounded 1,536/3,072-token attempts also failed to produce usable
localization. Disabling thinking did not remedy it. Reasoning text is neither
exposed nor treated as an executable answer.

The failure precedes JSON parsing and coordinate conversion; it is not evidence
of a DPI offset. On the same image a smaller label schema returned PREVIEW in 79
tokens, approximately 6.4 seconds, and finished normally. The actual authorized
capture/controller path independently passed label verification. The expected
answer is not supplied in the model question. A mismatch fails verification.
Qt's Verify visible label action cannot authorize a click.

Localization explicitly declares capture_pixels or normalized_0_1000.
coordinates.py converts once to capture pixels and then physical client/screen
coordinates. Negative monitor origins, resizing and client offsets are tested;
DPI is not applied twice. Unknown spaces and invalid bounds fail. Reviewed visual
input requires matching task/window, confidence, fresh capture, unchanged pixels,
permission, focus and a new postcondition.

Related upstream evidence: [Ollama renderer/parser issue](https://github.com/ollama/ollama/issues/13353).
General coordinate localization is not claimed reliable in this release.

## Architecture ready and known limitations

- The adapter registry remains a lightweight extension contract, not a large plugin
  runtime. Generic UIA, browser DOM and OS accelerators work without it.
- Plans are bounded, not universal adaptive recovery. Missing/ambiguous controls
  pause for review. Some shortcuts cannot be reliably matched to launched processes.
- General raw shortcuts, right/double-click macros, complex iframes and custom canvas
  applications have limited coverage. Exact pixel guards reject changed/animated
  screens. Visual-label verification is deliberately narrow.
- Discord navigation and Apple Music song search were not validated. No self-bot,
  email API, voice, Tor, trading or calendar integration was added.
- Capture is scoped and bounded, not continuous recording. UIA can be disabled
  independently of browser/media. No arbitrary JS or shell reaches the planner.
- Clean-machine and frozen-helper packaging remain post-release hardening; see
  [Windows packaging](PACKAGING_WINDOWS.md).


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
