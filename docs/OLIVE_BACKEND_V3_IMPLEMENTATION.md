# Backend V3 implementation ledger

Work in progress, 2026-09-23. DESIGN_BASE:
`50003790c42aff620d63d664dff89c0338347cab`. Both design-v2 and the existing
backend-models-v3 branch pointed here; worktree was clean. No branch reset,
stash or history replacement. No CLAUDE.md was present in tracked sources.

## Phases and gates

1. Verify baseline and freeze: complete. `backend-v3-frozen.json` records all
   renderer, Electron, assets, approved design and identity bytes. Run
   `python scripts/check_design_freeze.py`; additions (including ignored files),
   deletions and edits fail. Electron is included as a stricter freeze.
2. Repair toolchain discovery, truthful readiness and stale probes; validate
   real SDK/JDK fixtures through normal launch and existing Studio controls.
3. Commit a versioned 48-case benchmark with held-out cases and acceptance
   criteria before prompt/model tuning. Establish installed baselines first.
4. Repair demonstrated adapter/context/resource faults with regression tests.
5. Acquire only approved pinned artifacts; benchmark repeats at conservative
   contexts; promote only with quality, latency and headroom evidence.
6. Qwen Image remains licence/runtime gated. Research/evaluation scope requested
   by the user; licence review is still theirs. Existing SDXL remains default.
7. Run full Python, Connect, frontend, Electron and source compilation; report
   unresolved host/platform issues separately. No hosted results without a push.

## Boundaries

Public IDs remain fast, normal, max, deep, reimagine. HEAVY/PRO/IMAGINE are
planning terms only. Existing presets and user configuration remain unchanged.
DEEP retains native extraction, scoped retrieval and dedicated vision behavior.
C7 remains tool-free text inference; C8 retains its current no-install/no-shell
restrictions. Storage and transport retirement repairs remain authoritative.
No data migration, frontend change, mobile implementation or cloud inference.

The download manifest is `docs/evidence/backend-v3-acquisition.json`.
