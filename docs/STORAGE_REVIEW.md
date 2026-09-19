# Storage inventory and disposal proposal

Read-only inventory is implemented by `scripts/functionality_storage_inventory.py`.
The local JSON contains exact paths, logical file bytes, installed model tags,
digests and quantisation metadata. Links/junctions are skipped. Tag sizes are not
unique blob sizes or promised reclaimed capacity. The 2026-09-13 measurement found
105,299,098,201 logical bytes in the model store and 814,599,712,768 free bytes on
the repository volume. These are different volumes on this machine.

| Material | Logical bytes | Decision |
| --- | ---: | --- |
| `build/` | 1,447,063,367 | Keep verified current-source backup and historical recovery material |
| `.venv/` | 989,205,831 | Keep active Python runtime |
| `desktop/` | 767,069,767 | Keep source, active tooling, build and test dependencies |
| `artifacts/` | 337,518,146 | Keep evidence; do not infer disposable status from age |
| `.toolchains/` | 292,991,780 | Keep installed Studio tooling |
| `.experience-351/` | 95,115,681 | Keep historical evidence, still referenced by acceptance scripts |
| `.experience-350/` | 18,388,239 | Keep historical evidence |
| `.git/` | 8,889,266 | Keep; no prune, repack, repair or rewrite |

The active public presets use qwen3:8b, gpt-oss:20b, qwen3-coder:30b and qwen3-vl:8b.
Keep qwen3-embedding:0.6b for retrieval and devstral:24b for the existing coding
fallback. No weight aliases or duplicated weights were created.

The **optional disposal proposal** in local `.functionality-cleanup-manifest.json`
contains exact tags, store path, sizes, digests, dependencies and supported removal
commands. It proposes only `llava:34b` (20,166,497,526 tag bytes) and
`dolphin-mixtral:8x7b` (26,443,614,406 tag bytes). Neither is selected by current
presets or active coding policy. They were not benchmarked for replacement parity;
old user chats may retain these model choices. Their records would remain, and
the missing model would need setup if selected again.

Diego explicitly approved these two tags on 2026-09-14. Both were removed through
`ollama rm`, each returned success, and `/api/tags` verified their absence. All six
remaining model digests were unchanged. No shared blobs were deleted manually.
The exact local manifest is intentionally uncommitted because it includes a
personal absolute store path. It can be regenerated with
`scripts/functionality_cleanup_manifest.py` after running the inventory.

The model store decreased from 105,299,098,201 to 58,689,007,024 logical bytes:
**46,610,091,177 logical bytes removed**. Volume free space increased from
458,201,481,216 to 504,811,806,720 bytes: **46,610,325,504 bytes observed reclaimed**
(46.61 GB). The small difference can include concurrent filesystem activity.
Exact command outcomes and measurements are retained locally in
`.functionality-cleanup-result.json`. No source, toolchain, backup or user records
were deleted. No broad cleanup was run. Moving files within one volume does not
count as reclaimed capacity. The separately approved media installation consumes
space on the repository volume, not the model-store volume.

Four task-owned one-time authoring helpers (`.functionality-update-language.py`,
`.functionality-update-ledger.py`, `.functionality-update-tests.py`, and
`.functionality-update-workflows.py`) were removed after verifying their exact
repository-root paths. Their combined logical size was 17,007 bytes. No physical
free-space increase is attributed to these tiny files during active testing;
the model-disposal proposal and recovery evidence remain intact.
