# OLIVE project journey

Earlier REX/DMDO history is pending source recovery. This file was absent at
DESIGN_BASE; this entry does not reconstruct or replace earlier decisions.

## 2026-09-23 — backend V3, before C9

Started from the completed Design System V2 commit
`50003790c42aff620d63d664dff89c0338347cab`. Preserved V2 with a filesystem/hash
freeze and one explicitly approved New Project wizard state fix. Repaired
shared .NET/JDK discovery and normal-launch Studio readiness, installed the
approved local JDK, hardened inference completion/context/stream bounds, and
compared approved local model artifacts against existing baselines using
synthetic fixtures. No model default promotion or user-data migration.

Qwen Image 2.1 remains a research/evaluation preparation with licence,
download, runtime and hardware gates outstanding; SDXL remains available.
No Mobile/C10, cloud inference, Laya or redesign. See
[the implementation/acceptance report](OLIVE_BACKEND_V3_IMPLEMENTATION.md) for
measured results, unresolved host/design issues and rollback.

## 2026-09-23 — Linux desktop foundation and backend closeout, acceptance pending

Started from V3 `2df73b31ca11374978363a8f9d9c34ab052a74a4` on a separate branch.
Added finite local-task authority, consent-gated portal/PipeWire/EIS/AT-SPI adapters,
private helper lifecycle and immediate Stop handling. Applied only the separately
approved Studio state, GO timing and safety-copy exceptions; all 225 frozen paths
remain accounted for. Repaired Linux diagnostic/reviewed-launch boundaries and
owned Qt fixture disposal. Final regression: Python 1,154 tests/8 skips, Connect
240 passes, frontend 96 passes, Electron 55 passes/16 skips/0 failures.

Real installed vision trials failed the grounding gate despite repairing the
existing bounded retry contract (correct target center/label 1/6 to 2/6, with
higher latency). No public model mapping changed. Human global Stop activation
and portal input acceptance did not complete; no real GUI task or Discord message
was reported successful. Broad desktop workflows and remaining acceptance are
explicitly incomplete. See [the scoped closeout](OLIVE_DESKTOP_BACKEND_CLOSEOUT.md).
