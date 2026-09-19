# M4 Native Mail and secure connections

**M4 implementation and internal acceptance complete.** Final evidence is in
[M4_COMPLETION.md](M4_COMPLETION.md); actions are mapped in [M4_PARITY.md](M4_PARITY.md).
No release approval/tag, next milestone, Qt removal or default-launcher switch.

Actual baseline: clean `2eaabbd1f77432d17f5eb4c9d31f797205df7837`, branch
`development/3.5.1-electron-experience`. M3 schema 4, canonical olive package,
window.olive, current Core and C# Studio were preserved. Initial implementation
commit `15c89a2`; final coherent QA/documentation commit is identified by Git log.
Historical bad-tree Git maintenance warnings remain separate; no repair attempted.

## Completed internal checklist

These groups cover the user's M4 brief, not new approval gates. All 1,629 existing
requirement IDs and 125 original M2 action mappings remain; 190 applicable M4 rows
now point to classified evidence. Listed endpoints alone are not live evidence.

| ID / brief sections | Implementation / UI and tools | Evidence / limit |
| --- | --- | --- |
| M4-01 / 1?5 | Shared Mail controller, strict private bridge, existing policy/runtime | Python policy/security; ordinary Electron; no second writer |
| M4-02 / 6?10 | MailStore/local records, native folders/detail/drafts/composer/search/thread | local-ui/content-ui; controlled 200-message render-review; revision and forwarded-attachment regressions |
| M4-03 / 11?12,22 | Bounded MIME, snapshots, native dialogs, safe HTML/CID | content-ui real EML roundtrip/opaque frame/no tracking; MIME/security tests |
| M4-04 / 13?15 | Current-user Credential Manager and Settings Connections | actual dummy vault; masked UI; TLS tests; no external account |
| M4-05 / 16?17 | IMAP incremental UID/UIDVALIDITY, PEEK, flags/MOVE/search/folders/cache | real adapter + scripted TLS peer, imap-ui; independent IMAP engine unavailable |
| M4-06 / 18?21,25 | Immutable revision-bound submission, exact approvals, outcomes/Sent copies | independent SMTP TLS sink via Electron; accepted/partial/uncertain/cancel; recovery/security tests |
| M4-07 / 23?24,26 | Shared language, Contacts, Calendar/Tasks proposals, Projects/Knowledge | real installed-model workflow; native UI creations/unsent draft; selected local Knowledge indexing |
| M4-08 / 27?30 | Existing Core, optional read-sync, consistent backup/restore | actual native restore, M3 IDs/dismissed reminders, no send replay; cross-store validation and Knowledge snapshot rebind tests |
| M4-09 / 31?33 | Isolated synthetic approvals/protocol failures/local exchanges | 33 focused Mail tests within 732 Python; no Internet delivery, no independent full security audit |
| M4-10 / 34?36 | Rendered self-review, timing, final tests/current docs | 25 frontend, 37 ordinary Electron + 4 explained opt-ins, 7 harness, 49 Qt, 12 local-language cases; build/typecheck/lint/compilation passed |

Baseline-only results: 699 Python, 23 frontend, 31 ordinary Electron / 3 opt-ins.
Final results supersede those numbers; failed intermediate runs are retained in
ignored artifacts, not relabelled passes. Final Python: 732 / 59.624 s. Final
ordinary Electron: 37 / 5.3 min, four documented opt-ins; Mail live language passed
separately. See the completion record for exact log paths and warnings.

All test mail/accounts/credentials were synthetic. No real profile, personal
records, external account, OS certificate store or desktop-input target was used.
Owned test processes and dummy vault references were cleaned up. Ignored fixture
profiles/evidence remain for audit. No repeated review ZIP was produced.

## Boundary and follow-up

M4 is complete to its documented local milestone boundary. Final release packaging
still needs the self-contained Python artifact and clean-machine validation.
External-server interoperability, OAuth-only services, broader IMAP extensions,
GPU/combined-model measurements and physical DPI/multi-monitor variants are not
claimed. See MAIL_TRANSPORTS.md and ACCOUNT_SECURITY.md for supported limits.
Do not automatically begin the next milestone or create a release tag.
