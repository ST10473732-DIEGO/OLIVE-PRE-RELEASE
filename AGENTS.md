# OLIVE coding instructions

## Product
- The product is **OLIVE**, formerly DMDO. Use OLIVE for new product-facing work. Retain DMDO only for documented compatibility or historical accuracy. Current shared identity is `olive/identity.json`.
- OLIVE is a **local-first desktop AI assistant**. Ollama is the default inference provider.
- Do not add a paid cloud/API dependency unless the user explicitly asks for it.
- Preserve compatibility with Windows and normal local Python installations.

## Architecture
- Keep `main.py` tiny. Product logic belongs in the `olive/` package.
- Keep model/inference work in `olive/services/ollama_service.py` and orchestration in service modules.
- Keep document parsing separate from retrieval/indexing.
- Keep persistence behind repository/store classes.
- Prefer small focused modules over a multi-thousand-line application file.
- Avoid circular imports and global mutable application state.

## Data safety
- Fresh user data defaults to `~/.olive`; existing `~/.dmdo` profiles are reused in place. Explicit configured paths are authoritative; conflicting locations require an explicit choice.
- Never delete or overwrite legacy user data during migrations. Copy/import it and leave the source intact.
- Never commit user chat files, local model files, API keys, tokens, or absolute personal file paths.
- Changes to persistence formats need a migration path.

## Local AI / RAG
- Documents should be chunked and retrieved; do not inject entire large documents into every model request.
- Hybrid retrieval should degrade gracefully: semantic embeddings when the configured embedding model exists, lexical retrieval otherwise.
- Do not fabricate document citations. Source labels must come from retrieved chunks.
- Native image attachments should only be sent to models that support vision.

## Quality bar
Before considering a change complete, run from the repository root:
1. `python -m compileall -q -x "(^|[/\\])\.venv[/\\]" .`
   (the exclusion skips a development virtual environment inside the checkout; third-party
   templates in it do not compile)
2. `python -m unittest discover -s tests -v`
   (use a throwaway profile, e.g. a temporary `HOME`/`OLIVE_DATA_DIR`; never real user data)
3. Desktop, from `desktop/`:
   - `npm run typecheck`
   - `npm run lint`
   - `npm test` (vitest)
   - `npm run build` when Electron main, preload or renderer code changed
4. Review `git diff` for accidental branding regressions, secrets, renamed legacy state
   identifiers (see `docs/architecture/legacy-dmdo-compatibility.md`) or user-data changes.

When changing behaviour, add or update a test where practical.
