# Accessible local input acceptance — preparation

Baseline verified clean at `9c34eb71979cd7d19ebc6c5005723d4b92eba976` on
`development/3.5.1-electron-experience`. The accepted owned launch/inspection,
Stop and cleanup evidence remains in M2_LIVE_INSPECTION.md. The original Tk
fixture and all earlier evidence remain unchanged. The historical attachment
exception is unresolved, not retrospectively fixed.

**Prepared, not live-tested. New user initiation is required.** The previous
read-only scope is not treated as permission for this target or its input.

## Fixture

Inspected `scripts/desktop_test_app.py` and the original Tk acceptance script.
The existing Qt fixture has other return/search/message behaviours, so it is
preserved. The new `scripts/m2_accessible_acceptance_window.py` uses the same
already-installed PySide6 standard controls (installed version 6.11.2), without
adding a dependency, production adapter, network access, persistence or hidden
automation endpoint. The live target is an external Qt window; DMDO stays Electron.

- Title: **DMDO M2 accessible acceptance target**.
- QLineEdit: accessible name **Acceptance text**, initially empty.
- QPushButton: visible/accessibility name **Check text**.
- QLabel: initially **Not checked**, object name `acceptance_result`.
- Only the button's clicked handler reads the field and updates the label.
  The label's accessible name mirrors its real text. Exact matching input yields
  **Verified: DMDO local acceptance**; other input yields a mismatch result.
- No returnPressed/textChanged verification and no preloaded success.

Offscreen widget tests verify that contract. They do not verify Windows UIA,
Electron interaction, real input or external application state changes.

## User-initiated live procedure

1. After explicit user agreement, start
   `scripts/launch_desktop_acceptance.ps1 -AttachDiagnostics -AccessibleTarget`.
   It refuses administrator execution and creates a fresh temporary profile.
   It opens only Electron and prints the exact reviewed script for the native
   chooser. The optional developer capture port is loopback-only.
2. In that isolated profile, the user explicitly enables Desktop Control/UIA,
   selects **keyboard Ask**, leaves **mouse Deny**, **screen/vision off** and
   **unknown-app Ask**. No permanent Allow rules or real-profile changes.
   The gateway requires keyboard approval for semantic set_text; generic Invoke
   has its own control approval and does not require enabling pointer input.
3. Desktop Control → Developer Details → Launch and attach one target → Python
   script → native chooser → the new reviewed script. The user personally
   confirms matching launch approvals. Do not substitute approval API calls.
4. With the intended owned launch selected, use the existing capture helper:
   `node scripts/capture_desktop_attach.cjs ISOLATED_PROFILE NEW_OUTPUT --user-initiated --accessible-target`.
   It invokes the actual Attach button. On inspection approval pending, record
   and wait for the user. Observe that same request with `--observe-pending`
   and another new output directory; do not replay Attach.
5. Require the actual observation to identify the correct owned window, a named
   **Acceptance text** Edit control with set_text, a **Check text** Button with
   invoke, and the readable **Not checked** status. Record real names, types,
   actions and runtime IDs. Stop if these are absent or ambiguous. Qt declarations
   or the offscreen test do not substitute for this live preflight.
6. The inspection capture sets Stop after observation. Once the preflight is
   verified and the user is ready, reset that latch through the existing UI.
   Select the actually observed Edit control; choose set_text, enter exactly
   **DMDO local acceptance** in DMDO's action form and choose Review and perform
   action. The user approves the exact keyboard/control requests. The gateway
   retains focus/identity/takeover checks. Inspect the actual field read-back.
7. Select the observed **Check text** Button, choose invoke and expected visible
   control **Verified: DMDO local acceptance**. Review and perform action; the
   user confirms its approval. Verify the resulting external UIA observation,
   not the expected string supplied in the request. No coordinate/vision fallback.
8. Stop Control; record latch and active state honestly. Close only verified
   owned target/Electron/backend processes and preserve compact redacted evidence.

No automatic approval clicks, unrelated application inspection, installation,
accounts, messages or permanent permission broadening. Stop on ambiguity, focus
loss, unexpected dialogs or takeover. If controls are unavailable, record their
actual exposure and stop without a speculative provider rewrite.

## Acceptance boundary

The new live criterion remains pending. A future pass establishes only generic
Electron → Python → UIA input/invocation and observed verification on this
compatible external fixture. It does not establish universal application control,
Tk compatibility, general natural-language desktop competence or vision accuracy.
M2 remains pending sign-off; no release tag, default switch, Qt removal or M3 work.


## Fresh preparation checks

626 Python tests passed (25.525 s), including the offscreen fixture contract;
compileall passed. Five capture-helper unit tests passed; Node syntax and
PowerShell parser checks passed. No live target, UIA input or invocation was
performed. Frontend, full Electron and Qt fallback suites were not rerun because
no production frontend/backend behaviour changed; their earlier accepted results
remain historical. Diff review found no changes to earlier fixture/evidence,
production permissions, dependencies, user data or release tags.
