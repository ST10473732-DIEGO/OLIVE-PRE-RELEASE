# Development

## Layout

| Path | Contents |
| --- | --- |
| `olive/` | Python runtime. Electron starts it as `python -m olive.bridge` (JSON lines over stdin/stdout) |
| `desktop/` | Electron/React product shell ([desktop README](../../desktop/README.md)) |
| `mobile/ios/` | Native iPhone companion ([iOS README](../../mobile/ios/README.md)) |
| `world-relay/` | Self-hostable Connect World relay ([relay README](../../world-relay/README.md)) |
| `tests/` | Python test suite; desktop tests live in `desktop/tests/` |
| `scripts/` | Contract generators, provisioning, acceptance harnesses |
| `main.py`, `olive/ui_qt/` | Legacy Qt fallback UI, development only |
| `dmdo/` | Legacy import alias ([compatibility](../architecture/legacy-dmdo-compatibility.md)) |

## Running from source

Linux (Python 3.11+, Node 22.12+, npm on PATH):

```sh
./run_olive.sh
```

It creates `.venv`, installs `requirements.txt` when it changes, runs `npm ci` and
`npm run build` in `desktop/`, then starts Electron. It also discovers local runtimes
under `~/.local/share/olive/runtime`. `./run_olive.sh --enable-startup` adds an
autostart entry that points at this checkout.

Windows (Python 3.11+ and Node on PATH):

```bat
setup_windows.bat
cd desktop
npm ci
npm run build
cd ..
run_olive.bat
```

Ollama must be installed separately on Windows. Use `OLIVE_DATA_DIR` to select an
explicit profile; never point development runs at a profile you care about while
testing.

## Quality bar

From the repository root (see [AGENTS.md](../../AGENTS.md)):

```sh
python -m compileall -q -x "(^|[^A-Za-z0-9_.-])(\.venv|backend-artifact|dist|node_modules)[^A-Za-z0-9_.-]" .
python -m unittest discover -s tests -v
cd desktop && npm run typecheck && npm run lint && npm test && npm run build
```

Run the Python suite with a throwaway `HOME` (or at least `OLIVE_DATA_DIR`) so no
test can touch real data. No test downloads models or contacts real accounts.

## Dependencies

See [dependencies](dependencies.md).
