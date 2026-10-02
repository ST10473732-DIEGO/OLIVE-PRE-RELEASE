# Archive

Historical milestone, acceptance and repair reports. Their content is kept as
written. Each describes the product at its own date, so version numbers, the Qt
shell, `run_dmdo.bat` and other superseded details are accurate for that time and
not for OLIVE 1.0. Only relative links were adjusted so they still resolve.

| Folder | Contents |
| --- | --- |
| `3.1/`, `3.4/`, `3.5/` | Release-era reports (Windows, Qt, early Electron) |
| `releases/3.3/`, `releases/3.4/`, `releases/3.4.1/` | DMDO release acceptance reports, original names kept |
| `qt/` | Qt migration and release records |
| `linux/` | Linux port L1–L3, CI repair, desktop backend and control acceptance |
| `agent/` | Backend V3 and unified-agent implementation and closeouts |
| `connect/` | Connect C1 foundation |
| `mobile-c9/` | iPhone C9.1–C9.3 reports and the completed C9.3 checklist |
| `repairs/` | Connect and toolchain repair logs |
| `design/` | Superseded design notes and the V2 implementation report |
| `models/` | Repository and text-model review |
| `ROADMAP-3.5.md` | The 3.5.1-era roadmap |
| `README-pre-1.0.md` | The repository README as it stood at `b026b60`, before the OLIVE 1.0 rewrite |

The frozen release records in [`docs/releases/`](../releases/) and the manifests in
[`docs/evidence/`](../evidence/) stayed in place because scripts read and write
those paths. They still name pre-1.0 paths (for example `ARCHITECTURE_3.md` or
`docs/OLIVE_DESIGN_V2_IMPLEMENTATION.md`); those names are historical evidence,
not live links. Use the table below to find a file today. The one exception: ten
clickable links in four 3.5.1 records (`ARCHITECTURE.md`, `PARITY.md`, `PLAN.md`,
`STATUS.md`) had only their link targets updated so they still open; their text is
unchanged. No generator writes those files and no manifest hashes them.

The historical freeze gates (`scripts/check_design_freeze.py`,
`scripts/check_linux_desktop_freeze.py`) list `docs/OLIVE_DESIGN_V2_IMPLEMENTATION.md`
among their frozen roots. At `b026b60` the design-freeze gate already reported
52 added, 9 deleted and 63 changed files. After PASS 2A it reports one more
deletion (that moved report) and four more changes: link and path edits in
`docs/design/OLIVE_DESIGN_SYSTEM_V2.md`, `OLIVE_GO_REPORT.md` and `OLIVE_STUDIO_V2.md`,
and the 1.0.0 version in `olive/identity.json`. These gates describe superseded
milestones and are not OLIVE 1.0 release checks.

## Where files moved (OLIVE 1.0 PASS 2A, 2026-10-02)

### Root documents now under `docs/`

| Old path | New path |
| --- | --- |
| `ACCOUNT_SECURITY.md` | [`docs/security/credentials.md`](../security/credentials.md) |
| `ARCHITECTURE_3.md` | [`docs/architecture/overview.md`](../architecture/overview.md) |
| `DESKTOP_CONTROL.md` | [`docs/features/desktop-control-windows.md`](../features/desktop-control-windows.md) |
| `MAIL_TRANSPORTS.md` | [`docs/features/mail.md`](../features/mail.md) |
| `MODEL_ROUTING.md` | [`docs/architecture/model-routing.md`](../architecture/model-routing.md) |
| `NATURAL_LANGUAGE_ARCHITECTURE.md` | [`docs/architecture/natural-language.md`](../architecture/natural-language.md) |
| `PERSONAL_CORE.md` | [`docs/features/personal.md`](../features/personal.md) |
| `RESEARCH_ARCHITECTURE.md` | [`docs/architecture/research.md`](../architecture/research.md) |

### Root documents archived

| Old path | New path |
| --- | --- |
| `APPLICATION_ADAPTERS.md` | [`docs/archive/3.4/APPLICATION_ADAPTERS.md`](3.4/APPLICATION_ADAPTERS.md) |
| `DEPLOYMENT_DESIGN.md` | [`docs/archive/3.4/DEPLOYMENT_DESIGN.md`](3.4/DEPLOYMENT_DESIGN.md) |
| `DESIGN_SYSTEM.md` | [`docs/archive/design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md) |
| `DISCORD_ADAPTER_DESIGN.md` | [`docs/archive/design/DISCORD_ADAPTER_DESIGN.md`](design/DISCORD_ADAPTER_DESIGN.md) |
| `DMDO_3_4_1_ACCEPTANCE.md` | [`docs/archive/releases/3.4.1/DMDO_3_4_1_ACCEPTANCE.md`](releases/3.4.1/DMDO_3_4_1_ACCEPTANCE.md) |
| `DMDO_3_4_ACCEPTANCE.md` | [`docs/archive/releases/3.4/DMDO_3_4_ACCEPTANCE.md`](releases/3.4/DMDO_3_4_ACCEPTANCE.md) |
| `EXPERIENCE_2.md` | [`docs/archive/3.5/EXPERIENCE_2.md`](3.5/EXPERIENCE_2.md) |
| `PACKAGING_WINDOWS.md` | [`docs/archive/3.4/PACKAGING_WINDOWS.md`](3.4/PACKAGING_WINDOWS.md) |
| `QT_FEATURE_PARITY.md` | [`docs/archive/qt/QT_FEATURE_PARITY.md`](qt/QT_FEATURE_PARITY.md) |
| `QT_MIGRATION.md` | [`docs/archive/qt/QT_MIGRATION.md`](qt/QT_MIGRATION.md) |
| `QT_RELEASE_REPORT.md` | [`docs/archive/qt/QT_RELEASE_REPORT.md`](qt/QT_RELEASE_REPORT.md) |
| `QT_WORKSPACE_SHELL.md` | [`docs/archive/qt/QT_WORKSPACE_SHELL.md`](qt/QT_WORKSPACE_SHELL.md) |
| `RESEARCH_RELEASE_REPORT.md` | [`docs/archive/releases/3.3/RESEARCH_RELEASE_REPORT.md`](releases/3.3/RESEARCH_RELEASE_REPORT.md) |
| `ROADMAP.md` | [`docs/archive/ROADMAP-3.5.md`](ROADMAP-3.5.md) |
| `UI_FEATURE_PARITY.md` | [`docs/archive/3.1/UI_FEATURE_PARITY.md`](3.1/UI_FEATURE_PARITY.md) |

### `docs/` reports archived

| Old path | New path |
| --- | --- |
| `docs/BROWSER_AND_MEDIA.md` | [`docs/archive/3.5/BROWSER_AND_MEDIA.md`](3.5/BROWSER_AND_MEDIA.md) |
| `docs/FUNCTIONAL_RELIABILITY.md` | [`docs/archive/3.5/FUNCTIONAL_RELIABILITY.md`](3.5/FUNCTIONAL_RELIABILITY.md) |
| `docs/LINUX_CI_REPAIR.md` | [`docs/archive/linux/LINUX_CI_REPAIR.md`](linux/LINUX_CI_REPAIR.md) |
| `docs/LINUX_L1_REPORT.md` | [`docs/archive/linux/LINUX_L1_REPORT.md`](linux/LINUX_L1_REPORT.md) |
| `docs/LINUX_L2_REPORT.md` | [`docs/archive/linux/LINUX_L2_REPORT.md`](linux/LINUX_L2_REPORT.md) |
| `docs/LINUX_L3_REPORT.md` | [`docs/archive/linux/LINUX_L3_REPORT.md`](linux/LINUX_L3_REPORT.md) |
| `docs/LINUX_PORT_READINESS.md` | [`docs/archive/linux/LINUX_PORT_READINESS.md`](linux/LINUX_PORT_READINESS.md) |
| `docs/OLIVE_AGENT_FREEFORM_CLOSEOUT.md` | [`docs/archive/agent/OLIVE_AGENT_FREEFORM_CLOSEOUT.md`](agent/OLIVE_AGENT_FREEFORM_CLOSEOUT.md) |
| `docs/OLIVE_BACKEND_V3_IMPLEMENTATION.md` | [`docs/archive/agent/OLIVE_BACKEND_V3_IMPLEMENTATION.md`](agent/OLIVE_BACKEND_V3_IMPLEMENTATION.md) |
| `docs/OLIVE_CHAT_AGENT_REPAIR.md` | [`docs/archive/agent/OLIVE_CHAT_AGENT_REPAIR.md`](agent/OLIVE_CHAT_AGENT_REPAIR.md) |
| `docs/OLIVE_CONNECT_C1.md` | [`docs/archive/connect/OLIVE_CONNECT_C1.md`](connect/OLIVE_CONNECT_C1.md) |
| `docs/OLIVE_CONNECT_C6_PORTABLE_REPAIR.md` | [`docs/archive/repairs/OLIVE_CONNECT_C6_PORTABLE_REPAIR.md`](repairs/OLIVE_CONNECT_C6_PORTABLE_REPAIR.md) |
| `docs/OLIVE_CONNECT_C8_PORTABLE_REPAIR.md` | [`docs/archive/repairs/OLIVE_CONNECT_C8_PORTABLE_REPAIR.md`](repairs/OLIVE_CONNECT_C8_PORTABLE_REPAIR.md) |
| `docs/OLIVE_CONNECT_C8_STORAGE_REPAIR.md` | [`docs/archive/repairs/OLIVE_CONNECT_C8_STORAGE_REPAIR.md`](repairs/OLIVE_CONNECT_C8_STORAGE_REPAIR.md) |
| `docs/OLIVE_CONNECT_PORTABLE_LOCK_REPAIR.md` | [`docs/archive/repairs/OLIVE_CONNECT_PORTABLE_LOCK_REPAIR.md`](repairs/OLIVE_CONNECT_PORTABLE_LOCK_REPAIR.md) |
| `docs/OLIVE_CONNECT_WINDOWS_LIFECYCLE_REPAIR.md` | [`docs/archive/repairs/OLIVE_CONNECT_WINDOWS_LIFECYCLE_REPAIR.md`](repairs/OLIVE_CONNECT_WINDOWS_LIFECYCLE_REPAIR.md) |
| `docs/OLIVE_DESIGN_V2_IMPLEMENTATION.md` | [`docs/archive/design/OLIVE_DESIGN_V2_IMPLEMENTATION.md`](design/OLIVE_DESIGN_V2_IMPLEMENTATION.md) |
| `docs/OLIVE_DESKTOP_BACKEND_CLOSEOUT.md` | [`docs/archive/linux/OLIVE_DESKTOP_BACKEND_CLOSEOUT.md`](linux/OLIVE_DESKTOP_BACKEND_CLOSEOUT.md) |
| `docs/OLIVE_DESKTOP_CONTROL_ACCEPTANCE.md` | [`docs/archive/linux/OLIVE_DESKTOP_CONTROL_ACCEPTANCE.md`](linux/OLIVE_DESKTOP_CONTROL_ACCEPTANCE.md) |
| `docs/OLIVE_DESKTOP_UNATTENDED_RUN.md` | [`docs/archive/linux/OLIVE_DESKTOP_UNATTENDED_RUN.md`](linux/OLIVE_DESKTOP_UNATTENDED_RUN.md) |
| `docs/OLIVE_MOBILE_C9_1_FOUNDATION.md` | [`docs/archive/mobile-c9/OLIVE_MOBILE_C9_1_FOUNDATION.md`](mobile-c9/OLIVE_MOBILE_C9_1_FOUNDATION.md) |
| `docs/OLIVE_MOBILE_C9_2_CONNECT_CHAT.md` | [`docs/archive/mobile-c9/OLIVE_MOBILE_C9_2_CONNECT_CHAT.md`](mobile-c9/OLIVE_MOBILE_C9_2_CONNECT_CHAT.md) |
| `docs/OLIVE_MOBILE_C9_3_ACCEPTANCE_CHECKLIST.md` | [`docs/archive/mobile-c9/OLIVE_MOBILE_C9_3_ACCEPTANCE_CHECKLIST.md`](mobile-c9/OLIVE_MOBILE_C9_3_ACCEPTANCE_CHECKLIST.md) |
| `docs/OLIVE_MOBILE_C9_3_FEATURES_BACKGROUND.md` | [`docs/archive/mobile-c9/OLIVE_MOBILE_C9_3_FEATURES_BACKGROUND.md`](mobile-c9/OLIVE_MOBILE_C9_3_FEATURES_BACKGROUND.md) |
| `docs/OLIVE_REPOSITORY_MODEL_REVIEW.md` | [`docs/archive/models/OLIVE_REPOSITORY_MODEL_REVIEW.md`](models/OLIVE_REPOSITORY_MODEL_REVIEW.md) |
| `docs/OLIVE_TOOLCHAIN_REPAIR.md` | [`docs/archive/repairs/OLIVE_TOOLCHAIN_REPAIR.md`](repairs/OLIVE_TOOLCHAIN_REPAIR.md) |
| `docs/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md` | [`docs/archive/agent/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md`](agent/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md) |
| `docs/OLIVE_UNIFIED_AGENT_IMPLEMENTATION.md` | [`docs/archive/agent/OLIVE_UNIFIED_AGENT_IMPLEMENTATION.md`](agent/OLIVE_UNIFIED_AGENT_IMPLEMENTATION.md) |
| `docs/STORAGE_REVIEW.md` | [`docs/archive/3.5/STORAGE_REVIEW.md`](3.5/STORAGE_REVIEW.md) |
| `docs/WINDOWS_STABLE_BASELINE.md` | [`docs/archive/3.5/WINDOWS_STABLE_BASELINE.md`](3.5/WINDOWS_STABLE_BASELINE.md) |

### `docs/` current documents reorganised

| Old path | New path |
| --- | --- |
| `docs/MOBILE_CROSS_DEVICE.md` | [`docs/architecture/cross-device.md`](../architecture/cross-device.md) |
| `docs/MODEL_PRESETS.md` | [`docs/features/chat-modes.md`](../features/chat-modes.md) |
| `docs/OLIVE_AGENT_WORKSPACE.md` | [`docs/features/agent-workspace.md`](../features/agent-workspace.md) |
| `docs/OLIVE_CONNECT_C2.md` | [`docs/connect/protocol/c2-identity-pairing.md`](../connect/protocol/c2-identity-pairing.md) |
| `docs/OLIVE_CONNECT_C3.md` | [`docs/connect/protocol/c3-transport.md`](../connect/protocol/c3-transport.md) |
| `docs/OLIVE_CONNECT_C4.md` | [`docs/connect/devices.md`](../connect/devices.md) |
| `docs/OLIVE_CONNECT_C4_PAIRING.md` | [`docs/connect/pairing.md`](../connect/pairing.md) |
| `docs/OLIVE_CONNECT_C5.md` | [`docs/connect/protocol/c5-sync.md`](../connect/protocol/c5-sync.md) |
| `docs/OLIVE_CONNECT_C6.md` | [`docs/connect/protocol/c6-files.md`](../connect/protocol/c6-files.md) |
| `docs/OLIVE_CONNECT_C7.md` | [`docs/connect/protocol/c7-remote-ai.md`](../connect/protocol/c7-remote-ai.md) |
| `docs/OLIVE_CONNECT_C8.md` | [`docs/connect/protocol/c8-remote-studio.md`](../connect/protocol/c8-remote-studio.md) |
| `docs/OLIVE_CONNECT_WORLD.md` | [`docs/connect-world/protocol.md`](../connect-world/protocol.md) |
| `docs/OLIVE_CORE.md` | [`docs/architecture/core.md`](../architecture/core.md) |
| `docs/OLIVE_CORE_APP_BOUNDARIES.md` | [`docs/architecture/core-app-boundaries.md`](../architecture/core-app-boundaries.md) |
| `docs/OLIVE_DESKTOP_NAVIGATION.md` | [`docs/features/desktop-navigation.md`](../features/desktop-navigation.md) |
| `docs/OLIVE_DRAWNOTE.md` | [`docs/features/draw.md`](../features/draw.md) |
| `docs/OLIVE_LINUX_DESKTOP_CONTROL.md` | [`docs/features/desktop-control-linux.md`](../features/desktop-control-linux.md) |
| `docs/OLIVE_LOCAL_MODEL_SELECTION.md` | [`docs/architecture/model-selection.md`](../architecture/model-selection.md) |
| `docs/OLIVE_MOBILE_CHAT.md` | [`docs/connect/protocol/olive-chat-1.md`](../connect/protocol/olive-chat-1.md) |
| `docs/OLIVE_NOTES.md` | [`docs/features/notes.md`](../features/notes.md) |
| `docs/OLIVE_NOW_CHAT_RESEARCH.md` | [`docs/features/research.md`](../features/research.md) |
| `docs/OLIVE_OWNER_MODE.md` | [`docs/security/owner-mode.md`](../security/owner-mode.md) |
| `docs/OLIVE_REBRAND.md` | [`docs/architecture/legacy-dmdo-compatibility.md`](../architecture/legacy-dmdo-compatibility.md) |
| `docs/OLIVE_REIMAGINE_QWEN_21.md` | [`docs/features/reimagine-qwen-image-2.1-gate.md`](../features/reimagine-qwen-image-2.1-gate.md) |
| `docs/OLIVE_VIDEO.md` | [`docs/features/video.md`](../features/video.md) |
| `docs/PROJECT_JOURNEY.md` | [`docs/history/PROJECT_JOURNEY.md`](../history/PROJECT_JOURNEY.md) |
| `docs/STUDIO_CSHARP.md` | [`docs/features/studio/csharp.md`](../features/studio/csharp.md) |
| `docs/WINFORMS_DESIGNER.md` | [`docs/features/studio/winforms-designer.md`](../features/studio/winforms-designer.md) |

`docs/PROJECT_DECISIONS.md` and `docs/PROJECT_HISTORY_SOURCES.md` from the
`docs/olive-project-journey` branch were added as
[`docs/history/PROJECT_DECISIONS.md`](../history/PROJECT_DECISIONS.md) and
[`docs/history/PROJECT_HISTORY_SOURCES.md`](../history/PROJECT_HISTORY_SOURCES.md).
`run_dmdo.bat` was retired ([compatibility map](../architecture/legacy-dmdo-compatibility.md#launchers)).
