> Historical 3.1 UI report. The current Qt migration mapping and validation evidence are in [QT_FEATURE_PARITY.md](../qt/QT_FEATURE_PARITY.md).

# OLIVE 3.1 UI feature-parity checklist

The Home shell is the main entry point. The legacy backend services remain shared rather than duplicated.

- Chat: Chat feature, including new/search/recent conversations and Chat settings.
- Model switching and streaming: Chat top bar and composer.
- Attachments, persistent chat knowledge, sources, and provenance: Chat composer/document strip/message actions.
- Memory: Memory Home feature opens the existing searchable review and suggestion manager.
- Agent: dedicated Agent feature; task and action-history controls are present there.
- Permissions: Settings feature opens global and path-scoped policies.
- Projects/workspaces: Projects feature and Studio workspace selector.
- Knowledge/indexing/retrieval inspector: Knowledge feature.
- Diagnostics: secondary Home action and common Settings access.
- Backup/restore, maintenance, OCR, RAG, themes, and generation settings: categorized Settings feature actions and validated existing dialogs.
- Studio: Explorer, tabs/editor, changed state, save, search, run/stop/restart, branch, Problems, Output, Tests, and assistant guidance.

The old mixins remain temporarily because they implement mature dialogs and Chat behaviors. They should be retired only after each listed capability has a dedicated page-level replacement and regression coverage.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](../../architecture/legacy-dmdo-compatibility.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
