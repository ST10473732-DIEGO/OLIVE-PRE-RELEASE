# OLIVE 3.5.1 - current identity

**M4 implementation and internal acceptance complete.** See
[M4_COMPLETION.md](M4_COMPLETION.md), [M4_STATUS.md](M4_STATUS.md) and the existing
individual ledger. Final release/packaging acceptance remains separate. Do not
start the next milestone, create a release tag, remove Qt or switch the launcher.
Earlier milestone notices below retain their original checkpoint scope.

The focused dot-matrix olive Core enhancement is complete before M4. It replaces the Electron ring/orb using the existing activity architecture, with internal rendered review and fresh regression evidence in [OLIVE_CORE.md](../../architecture/core.md). No new milestone features or release tag were added.

OLIVE was formerly named DMDO. Rebrand implementation/local acceptance is complete at source `ebe737e`: 697 Python, 18 frontend, 7 harness, 28 ordinary Electron passes (3 opt-in skips), 49 Qt checks; compilation/TypeScript/lint/build passed. Separate live local identity answered OLIVE. Packaging remains blocked by the existing missing self-contained backend artifact. M3 remains complete; M4 has not started. See [the rebrand map](../../architecture/legacy-dmdo-compatibility.md). Historical checkpoint text below retains its original naming. New code uses `olive`, `OLIVE_*` and `window.olive`; compatibility profiles and identities remain documented.

# OLIVE 3.5.1 delivery plan

**M3 implementation and internal acceptance complete.** See [M3_COMPLETION.md](M3_COMPLETION.md). Current authority remains the M3 end-to-end brief. M2 is accepted at `96fb78b`.
Complete Identity, Contacts, Calendar, Personal Tasks and in-app Reminders,
including language, Home/Projects, interchange, backup and internal QA. No
intermediate user review gates or review ZIP cycles. See [M3_STATUS.md](M3_STATUS.md).
Mail/SMTP/IMAP and related vault expansion are M4; final release gates remain
separate. Earlier milestone notices below are historical and superseded only
where the current user brief explicitly changes their scope/workflow.

> **M2 review checkpoint:** Implementation `b3554c3` is submitted for M2 user review. Fresh results, actual Electron captures, per-feature parity and remaining limitations are in [M2_REVIEW.md](M2_REVIEW.md). Stop before new Personal Core interfaces; no release tag, Qt removal or default switch. Earlier checkpoint notices below are historical.


> **M2 continuation:** The user explicitly approved corrected M1 at `d355f94` as the visual/interaction baseline and authorised M2 existing-feature migration. This supersedes the M1-awaiting-review notices below only. Full release and M3 interfaces are not approved. See [M2_PLAN.md](M2_PLAN.md), [M2_PARITY.md](M2_PARITY.md) and [M2_STATUS.md](M2_STATUS.md). All original requirement IDs remain in force.


> **Current M1 correction checkpoint, 10 September 2026:** The user recommended the Electron direction and requested focused corrections from `f4b107b`. See [M1_CORRECTIONS.md](M1_CORRECTIONS.md) for current implementation, stable M1C-01–09 obligations, fresh evidence and limitations. Updated M1 awaits user review; no M2/M3 work, Qt removal, launcher switch or release tag is authorised by this checkpoint. Historical evidence below remains historical.


Authority: the user's 36-section Electron master brief, with applicable unfinished native 3.5 requirements carried forward. No Google-dependent foundation. No scope reduction agreed.

- **M0:** verify 30cfdc9 and prior tags; retain Qt; audit actions; shared profile ownership; versioned private-pipe protocol; pinned Electron/React toolchain and design tokens.
- **M1:** real Welcome/Core/Enter/Home/All Spaces, shared natural-language Chat, locally bundled Monaco Studio, policy-bearing saves and runs, streamed output. Isolated live demonstrations, screenshots, recording and measured performance. **Stop for user visual approval.**
- **M2:** migrate remaining existing actions, retaining tested Qt fallback until parity. No unchanged Qt page counts as Electron migration.
- **M3:** complete Identity, Contacts, Calendar, Personal Tasks and in-app Reminders, imports/exports, native capabilities, cross-feature composition, backup and internal acceptance. No intermediate external review gates.
- **M4:** native Mail, optional SMTP/IMAP and credential-vault expansion needed for Mail. Do not start automatically after M3.
- **Final release gates:** full regression, lifecycle/security failures, accessibility/performance, packaging and final user approval remain mandatory before a default switch or v3.5.1 tag.

One primary BrowserWindow; sandboxed renderer; narrow preload; main validates requests; Python owns services and policy. Private inherited process pipes avoid a localhost listening API. Existing domain services remain authoritative; no hidden Qt application.

No unattended external sends. No default launcher change or release tag at M1. Milestone commits preserve prior history.
