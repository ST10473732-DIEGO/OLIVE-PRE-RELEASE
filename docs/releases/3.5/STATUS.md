# DMDO 3.5 status

Current milestone: M0 complete; working M1 prototype at the visual review gate.
M1 visual approval: **requested, not granted**. This is not a claim that all
M1-labelled polish and acceptance obligations are finished. See M1_REVIEW.md and
REQUIREMENTS.md for implemented and outstanding items.
Final visual approval: **not granted**. v3.5.0: **not created**.

Verified repository: HEAD 7007fe93f99657294315ffde702a480b9a3f507e;
v3.4.1 dereferences to that commit. Prior annotated tags remain unchanged.
Branch: development/3.5-personal-core, newly created from that baseline.
Starting worktree was not clean: user-supplied `assets/branding/olive-source.png`
was untracked. It was inspected and preserved, not discarded or overwritten.
Source SHA256: 2e26d64101d43d061ea6d128e90ba644b11b5ce8459337fa9919bf341c4e5145.
Source is RGB 840x800 with a baked checkerboard. A transparent derivative and
multi-resolution ICO/PNGs are now prepared; original bytes remain unchanged.

Independent baseline compile PASS; automated tests **514/514** (18.914 s).
Fresh Qt **49/49**, original **37/37**, expanded **145/145**, compounds **4/4**.
All these are reruns, not copied release claims. No desktop/account send test.

Installed: PySide6/Essentials/Addons/shiboken6 6.11.2; Pillow 12.3.0;
Ollama Python 0.6.2; psutil 7.2.2. No dependency upgrades made.

Resume: inspect Git status, this document and M1_REVIEW.md. If the user has not
approved the visual direction, make only requested M1 revisions; do not proceed
to M2 or Personal Core interfaces. After explicit approval, finish outstanding
M1 polish/acceptance and continue M2–M6 from the same master brief and individual
ledger. Do not infer approval from fixture success or old design discussions.

Development version: 3.5.0.dev1. Default presentation is Midnight; environment
DMDO_PRESENTATION=legacy retains the prior UI. No tag created. M0 commit: 17219ce.

Latest validation: targeted compile PASS; automated **523/523** (17.428 s);
legacy Qt **49/49** with localhost access; M1 actual local UI **17/17** at three
display configurations. Two restricted legacy runs were 48/49 due to localhost
WebEngine loading, resolved by the localhost-enabled run without changing expected
results. No new live-model Home workflow or external-account acceptance is claimed.

Actual screenshots and MP4 are in `docs/releases/3.5/evidence`; synthetic profile
only. Recorded first useful QQuickWidget paint approximately 2.020 s including Qt
imports; 5.17 ms mean cached navigation callbacks, 340.8 MiB RSS in that sample.
These are not display-FPS/GPU-VRAM measurements. See M1_REVIEW.md for exact limits.

Integration spike PASS: QQuickWidget + native editor/docks, twenty switches, one
primary window, retained buffer/cursor. Default Direct3D11: Quick construction
42.93 ms, RSS delta 85.38 MiB. OpenGL: 212.70 ms, 177.32 MiB. Direct3D11 with actual
local WebEngine preview also passes (43.32 ms, total delta 184.09 MiB). Select
Qt's default Direct3D11 on this Windows machine; no forced OpenGL override.
These measure a spike, not final application startup or GPU VRAM.

Addressed audit gaps: new Chat uses content-driven messages and additive durable
composer drafts; the Midnight shell replaces the navigation button wall. The
legacy UI remains available. Settings retains its old layout pending M2 approval.
Existing BackupService archives raw SQLite bytes
while RAG uses WAL, so consistent SQLite snapshot handling needs M5 work. No
production data was backed up/restored or migrated during this audit.

The image tool produced a transparent olive candidate with slight fill texture;
that candidate is not pixel-identical to the source. Original bytes remain intact.
Production icon visual fidelity remains subject to M1 review.
