# DMDO 3.5 release plan

Sole scope: the user's fresh 55-section Experience 2.0 + Native Personal Core brief.
Earlier Google-oriented plans are superseded. No backend rewrite or new models.

| Milestone | Deliverable | Gate |
| --- | --- | --- |
| M0 | Verify 3.4.1, action inventory, requirements, QQuickWidget integration spike | Measured baseline and supported Qt boundary |
| M1 | Actual Welcome/Core/Enter/Home, redesigned Chat, retained native Studio shell, tokens/gallery | **User visual approval required before M2-M6** |
| M2 | Approved design across existing workspaces; complete action parity | Screenshots and action checks |
| M3 | Transactional native Identity/Contacts/Calendar/Tasks/Reminders | Offline CRUD, recurrence, restart and relationships |
| M4 | Native Mail, Windows vault, optional SMTP/IMAP and Connections | Local MIME/outbox, secure transport and uncertainty tests |
| M5 | Shared natural-language capabilities, corrections, imports/exports, backups | Cross-feature and approval/security demonstrations |
| M6 | Complete regression, performance, packaging, visual acceptance | Final user approval, clean commit, then v3.5.0 |

M1 architecture: one QApplication and QMainWindow; QQuickWidget presentation
surfaces; existing cached QWidget workspaces and real docked Studio; one existing
BackendBridge/QThread asyncio runtime. Narrow GUI-thread view models expose
explicit navigation, composer and appearance actions, never arbitrary dispatch.
Legacy presentation remains selectable throughout migration.

No external messages, private accounts, purchases or installations in unattended
validation. Synthetic profiles and owned local fixture windows only. Baseline
model evaluations interpret requests but execute no tools. Compilation targets
`dmdo`, `tests`, `scripts`, and `main.py`, excluding the virtual environment.

M1 must show empty/populated fixture states and real screen captures. Native
Personal Core interfaces and other workspace redesigns wait for visual approval.
Record omissions as remaining scope, not optional substitutions.
