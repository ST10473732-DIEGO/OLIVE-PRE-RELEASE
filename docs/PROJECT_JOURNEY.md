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
