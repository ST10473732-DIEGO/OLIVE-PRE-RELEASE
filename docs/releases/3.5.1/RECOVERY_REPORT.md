# DMDO 3.5.1 recovered working checkpoint

Fresh verification: 10 September 2026. This is an M1 review checkpoint, not a
completed release. The latest master brief requires visual approval before
continuing the remaining workspace migration or Native Personal Core UI.

## Baseline and recovery

The existing branch was `development/3.5.1-electron-experience`, HEAD `3e166ca`.
The initial checkout had 503 missing tracked files, 22 modified files and one
untracked module. Git also lacked objects and release-tag references, and the
Python/Node environments contained missing files.

- Restored 421 missing files directly from their exact indexed Git blobs.
- Replayed the earlier DMDO development patches in an isolated staging folder;
  restored 80 more source/document files, including companion modules required
  by the surviving changes. Existing source files were not overwritten during
  recovery. The remaining 16 missing evidence files were replaced with explicitly
  fresh isolated demonstrations; the original historical media was not recovered.
- Preserved the initial tracked files and Git metadata under ignored
  `build/recovery/original`, alongside recovery inventories and scripts.
- Restored 96 missing Git objects by verifying their original content hashes,
  including the exact HEAD directory tree. Rebuilt the damaged multi-pack index.
- Restored the original annotated v3.2.5, v3.3.0, v3.4.0 and v3.4.1 references to
  their surviving tag objects; no existing tag target or commit was rewritten.
- Restored checksum-verified Node 24.21.0 and a Python 3.14.5 virtual environment.
  Reinstalled declared dependencies. Direct frontend pins are preserved; the
  missing lockfile was regenerated and installed with `npm ci`.
- Recovered all 1,612 requirement IDs, including inherited 3.5 obligations and
  prior Studio revisions. Historical evidence/approval is separated from current
  verification. No current visual approval is inferred from the old session.

**Git limitation:** some historical blobs (including old evidence and the old
lockfile) and two earlier commit trees remain missing. `git fsck` is therefore
not clean. A new working checkpoint does not repair those historical snapshots;
full historical recovery requires their original bytes from another backup.
The original damaged metadata is retained. No release tag is created.

## Fresh results

| Check | Result | Class |
| --- | --- | --- |
| `python -m compileall -q .` | Passed using the restored environment | Static |
| `python -m unittest discover -s tests -v` | 548 passed | Unit / mocked integration |
| TypeScript, ESLint, Vite production build | Passed; all subprocess exit codes zero | Static / build |
| Vitest | 5 passed | Component / contract |
| Ordinary Electron suite | 5 passed, live-model test explicitly skipped | Isolated live local |
| Explicit Ollama streaming test | 1 passed; real qwen3:8b, cancel and route-state retention | Live local |
| Qt fallback smoke | 49 passed, clean shutdown | Isolated live local |
| External messaging | No real messages sent | Not tested externally |

The tests exposed an incomplete recovered Discord pre-submission authorization
hook and two older fixture shapes without application display names. The hook
was restored from the recorded patch; fixture identities now match the existing
application contract. Permission revocation blocks submission before a write.

The Electron demonstrations exercised Welcome, Enter, Home, Chat, All Spaces,
Monaco edits and hash-checked saves, real Python test output, Java compilation
and local library output, dirty-buffer conflicts, responsive resizing, keyboard
navigation, renderer restrictions and refresh state retention. These are bounded
demonstrations, not full lifecycle/security certification or feature parity.

## Application and boundary

One Electron window renders React/strict TypeScript, the olive application icon,
blue Core, shared Home/Chat orchestration, and locally bundled Monaco/xterm.
The sandboxed renderer uses a narrow preload; Electron validates calls and
supervises Python over private versioned process pipes. Python services remain
authoritative for permissions, workspace editing, execution and model inference.
There is no hidden Qt GUI and no new public HTTP API.

The recovered Studio/package/connection revisions remain development features.
The supported Discord transport was tested with mocks only; no account was
configured and no external delivery was attempted. Output is read-only, not an
interactive shell. Language-server/debugger support is not claimed.

Qt remains the tested default fallback. Existing user profiles were not migrated
or opened by these demonstrations; synthetic profiles and temporary workspaces
were used. No user-data format, model assignment or default launcher was changed.

## Evidence and measured limits

- [Welcome](evidence/welcome.png), [Home](evidence/home-populated-fixture.png),
  [All Spaces](evidence/all-spaces.png), [live Chat](evidence/chat-live-stream.png).
- [Monaco and real test output](evidence/studio-monaco-output.png),
  [conflict comparison](evidence/studio-conflict-comparison.png),
  [Java project](evidence/studio-java-project.png).
- [Actual interaction recording](evidence/m1-interaction.mp4).
- [Launch metrics](evidence/launch-metrics.json),
  [stream metrics](evidence/stream-result.json),
  [renderer/resource checks](evidence/visual-security-metrics.json),
  [Qt checks](evidence/recovery-qt-results.json).

Welcome appeared in 418 ms in one local run. The separate appearance run measured
400 ms startup and navigation automation intervals of 149 ms and 28 ms.
The real inference request took 21.94 seconds to show the streaming state; that
includes interpretation/model readiness and is not a raw decoder latency metric.
Cancellation and retained output passed. The sampled application process tree
used approximately 503 MiB RSS; this is not steady-state idle memory or combined
Ollama/GPU consumption. Physical GPU usage was not measured.

Qt's fresh smoke harness finished in 5.2 seconds, but that measures a whole test
sequence. No comparable fresh Qt startup/idle benchmark was collected, so an
Electron-versus-Qt performance conclusion would be unsupported. True cold-start,
physical DPI/multiple-monitor checks and sustained typing/output benchmarks remain.

## Remaining delivery gates

Agent, Research, Desktop Control, Projects, Knowledge, Memory and Settings still
need complete Electron action parity. Identity, Contacts, Calendar, Personal
Tasks, Reminders and native Mail/SMTP/IMAP remain mandatory unfinished scope.
Their full UI, natural-language composition, migrations and backup/restore
acceptance have not been implemented or claimed during recovery.

Production assets run without Vite or a CDN. A self-contained packaged Python
artifact, clean-machine packaging, full interruption/recovery checks and final
security/performance/visual acceptance remain open. No installer is published,
default switch performed or v3.5.1 tag created.

Launch the isolated review application with
`powershell -ExecutionPolicy Bypass -File scripts/launch_electron_preview.ps1`.
Current visual approval is pending. Continue with the same master brief after
that approval; recovery does not remove any remaining requirement.
