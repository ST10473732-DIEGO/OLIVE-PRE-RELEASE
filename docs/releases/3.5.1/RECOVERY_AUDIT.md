# DMDO 3.5.1 recovery audit — 2026-09-10

> Initial findings below are historical. Source and runtime recovery has since
> completed; see [RECOVERY_REPORT.md](RECOVERY_REPORT.md). Some historical Git
> objects remain missing. No original edits were discarded.

The current user master brief governs this release. Work is limited to M0/M1
until the user approves the real application's visual direction. This audit is
not M0 completion or a substitute for the missing requirement ledgers.

## Actual starting point

- Branch: `development/3.5.1-electron-experience` (already selected).
- HEAD: `3e166ca`, direct Studio actions and named Java project starters.
- Earlier recorded commit: `4c8c64a`, Electron M1 prototype and review evidence.
- `7007fe9` resolves to a commit; its full release contents are not verified.
- `pyproject.toml` declares `3.5.1.dev1`.
- `git tag --list` returns no tags in this checkout. No tags were changed.
- Initial status: 503 deleted tracked files, 22 modified tracked files and one
  untracked Python module. These changes predate this audit and are preserved.
- No Git remote is configured.

## Blocking evidence

`git fsck --full --no-reflogs` reports missing blobs, missing trees, broken
commit/tree links and invalid cache-tree pointers. `git diff --stat` fails with
an unreadable object. The index references missing objects for the frontend
manifest and the previous release plan. A normal checkout cannot reliably
recover this baseline.

Missing working files include backend modules, Qt fallback modules, all Python
test source files, frontend build configuration/lockfile, olive assets, and the
3.5 and 3.5.1 release ledgers. Remaining source fragments are not evidence of a
working or secure application. Historical logs are not fresh validation.

## Fresh validation

- Both required commands were attempted: `python -m compileall -q .` and
  `python -m unittest discover -s tests -v`.
- Neither could start: the resolved WindowsApps Python executable is inaccessible.
- The repository virtual environment has no available Scripts/python executable.
- Frontend checks cannot run with the package manifest and test sources absent.
- Live streaming, saving, output, launch, screenshots and performance: not tested.
- No release commit, tag, default-launcher switch or visual approval occurred.

## Recovery and delivery sequence

1. Obtain a complete checkout/backup or repository source containing this current
   checkpoint, missing Git objects, release ledgers and test harnesses. Preserve
   all surviving local edits; inspect differences before any reconciliation.
2. Restore a usable local Python and frontend toolchain. Do not replace the
   existing backend with newly invented implementations of missing modules.
3. Read the restored 3.5 requirements and reconcile each stable ID with the new
   master brief. Restore/update PLAN, STATUS, REQUIREMENTS, PARITY and ACCEPTANCE;
   do not silently replace their lost contents with an abbreviated ledger.
4. Re-run backend and frontend baseline checks. Audit the surviving Electron
   connection against the security, lifecycle and approval requirements.
5. Finish M0/M1: Welcome, Home, All Spaces, Chat and Monaco Studio connected to
   real Python services; isolated-profile streaming/cancellation, hash-checked
   saves, actual test output and conflict protection.
6. Capture the real application and measurements, then stop for user visual
   approval. Remaining feature migration, Native Personal Core and final
   parity/security/performance/packaging gates remain mandatory afterwards.

The surviving PERSONAL_CORE.md and MAIL_TRANSPORTS.md explicitly describe those
domains as planned, not implemented. Their historical milestone numbers must be
reconciled with the current brief (Personal Core in M3, final validation in M4).
No implementation or feature parity is certified by this recovery audit.
