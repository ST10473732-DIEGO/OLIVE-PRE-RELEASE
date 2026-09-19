"""Language Server Protocol client sessions per approved workspace.

OmniSharp (C#) and python-lsp-server (Python) run as owned child processes.
Open buffers are versioned and re-asserted after project reloads so results
reflect the editor text, not the file on disk. Results are returned to the
renderer as plain LSP JSON; diagnostics are pushed as bridge events.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import time
from urllib.parse import quote, unquote, urlparse

from .toolchain import PINNED, python_executable
from .transport import ProcessTransport

REQUEST_TIMEOUT = 45.0
CLIENT_CAPABILITIES = {
    "textDocument": {
        "synchronization": {"dynamicRegistration": True, "didSave": True},
        "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True, "resolveSupport": {"properties": ["documentation", "detail", "additionalTextEdits"]},
                                                                        "documentationFormat": ["markdown", "plaintext"]}, "contextSupport": True},
        "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
        "signatureHelp": {"dynamicRegistration": True, "signatureInformation": {"documentationFormat": ["markdown", "plaintext"], "parameterInformation": {"labelOffsetSupport": True}}},
        "definition": {"dynamicRegistration": True}, "references": {"dynamicRegistration": True},
        "documentSymbol": {"dynamicRegistration": True, "hierarchicalDocumentSymbolSupport": True},
        "formatting": {"dynamicRegistration": True}, "rangeFormatting": {"dynamicRegistration": True},
        "rename": {"dynamicRegistration": True, "prepareSupport": True},
        "codeAction": {"dynamicRegistration": True, "codeActionLiteralSupport": {"codeActionKind": {"valueSet": ["quickfix", "refactor", "refactor.extract", "refactor.inline", "refactor.rewrite", "source", "source.organizeImports"]}}, "resolveSupport": {"properties": ["edit"]}},
        "publishDiagnostics": {"relatedInformation": True, "codeDescriptionSupport": True},
    },
    "workspace": {"workspaceEdit": {"documentChanges": True, "resourceOperations": ["create", "rename", "delete"]}, "configuration": True,
                  "symbol": {"dynamicRegistration": True}, "applyEdit": True, "workspaceFolders": True},
    "window": {"workDoneProgress": True},
}
FEATURES = ("completion", "hover", "signatureHelp", "definition", "references", "documentSymbol",
            "workspaceSymbol", "formatting", "rename", "codeAction", "diagnostics")


def path_to_uri(path: str | Path) -> str:
    text = Path(path).resolve().as_posix()
    if len(text) > 1 and text[1] == ":":
        return "file:///" + text[0].lower() + "%3A" + quote(text[2:], safe="/")
    return "file://" + quote(text, safe="/")


def uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return uri
    text = unquote(parsed.path)
    if len(text) > 2 and text[0] == "/" and text[2] == ":":
        text = text[1:]
    # Servers may lower-case the drive letter; canonicalise so keys match editor paths.
    try:
        return str(Path(text).resolve())
    except OSError:
        return str(Path(text))


class LanguageSession:
    """One language server for one workspace root."""

    def __init__(self, workspace_id: str, root: str, language: str, command: list[str], env: dict[str, str], publish):
        self.workspace_id = workspace_id
        self.root = str(Path(root).resolve())
        self.language = language
        self.command = command
        self.env = env
        self.publish = publish
        self.transport: ProcessTransport | None = None
        self.state = "starting"
        self.detail = ""
        self.started_at = time.time()
        self.capabilities: dict = {}
        self.registered: set[str] = set()
        self.documents: dict[str, dict] = {}  # path -> {version, text, language_id}
        self.diagnostics: dict[str, list] = {}
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._ready = asyncio.Event()
        self._restarts = 0
        self._reassert_task: asyncio.Task | None = None
        self.project_events = 0

    # ---- lifecycle -----------------------------------------------------
    async def start(self):
        self.state = "starting"
        self._publish_state()
        self.transport = ProcessTransport(self.command, self.root, self.env, self._on_message, self._on_exit)
        await self.transport.start()
        try:
            result = await self.request("initialize", {
                "processId": None, "rootUri": path_to_uri(self.root), "rootPath": self.root,
                "capabilities": CLIENT_CAPABILITIES, "clientInfo": {"name": "OLIVE Studio", "version": "3.5.1"},
                "workspaceFolders": [{"uri": path_to_uri(self.root), "name": Path(self.root).name}],
                "initializationOptions": {},
            }, timeout=45)
            self.capabilities = (result or {}).get("capabilities", {})
            await self.notify("initialized", {})
            # OmniSharp registers document sync dynamically after initialized;
            # a didOpen sent before that registration is dropped. Wait for it.
            if self.language == "csharp":
                for _ in range(60):
                    if "textDocument/didOpen" in self.registered:
                        break
                    await asyncio.sleep(0.25)
            self.state = "ready"
            self._ready.set()
            self._publish_state()
        except Exception as error:
            self.state = "error"
            self.detail = f"{type(error).__name__}: {error}"[:300]
            self._publish_state()
            raise

    async def stop(self, graceful: bool = True):
        """Stop the server. `graceful` asks it to shut down over the protocol
        first, which is right when a workspace closes. On application exit the
        polite round-trip is skipped: OLIVE has seconds to quit, and a server
        that is still negotiating when the host dies is left orphaned on the
        machine."""
        if self.transport and self.transport.alive:
            if graceful:
                try:
                    await asyncio.wait_for(self.request("shutdown", None, timeout=5), timeout=6)
                    await self.notify("exit", None)
                except Exception:
                    pass
            await self.transport.stop(grace=3.0 if graceful else 1.5)
        self.state = "stopped"
        self._publish_state()

    async def _on_exit(self, code):
        if self.state == "stopped":
            return
        self.state = "crashed"
        self.detail = f"The language server exited with code {code}." + (" " + " | ".join(self.transport.stderr_tail[-2:]) if self.transport and self.transport.stderr_tail else "")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Language server exited"))
        self._pending.clear()
        self._publish_state()

    async def restart(self):
        self._restarts += 1
        documents = dict(self.documents)
        await self.stop()
        self.registered.clear()
        self._ready = asyncio.Event()
        self.documents = {}
        await self.start()
        for path, item in documents.items():
            await self.open(path, item["text"], item["language_id"])

    def _publish_state(self):
        self.publish("lsp.state", self.status())

    def status(self) -> dict:
        return {"workspace_id": self.workspace_id, "language": self.language, "state": self.state, "detail": self.detail,
                "features": list(FEATURES) if self.state == "ready" else [], "documents": len(self.documents),
                "restarts": self._restarts, "provider": self.command[0].rsplit("\\", 1)[-1]}

    # ---- messaging -----------------------------------------------------
    async def request(self, method: str, params, timeout: float = REQUEST_TIMEOUT):
        if not self.transport or not self.transport.alive:
            raise ConnectionError("The language server is not running")
        identity = self._next_id
        self._next_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[identity] = future
        await self.transport.send({"jsonrpc": "2.0", "id": identity, "method": method, "params": params})
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(identity, None)
            try:
                await self.transport.send({"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": identity}})
            except Exception:
                pass
            raise TimeoutError(f"{method} did not answer within {timeout:g}s")

    async def notify(self, method: str, params):
        if self.transport and self.transport.alive:
            await self.transport.send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _on_message(self, message: dict):
        if "method" in message and "id" in message:
            await self._server_request(message)
        elif "method" in message:
            self._notification(message["method"], message.get("params") or {})
        elif "id" in message:
            future = self._pending.pop(message["id"], None)
            if future and not future.done():
                if "error" in message:
                    error = message["error"] or {}
                    future.set_exception(RuntimeError(str(error.get("message", "Language server error"))[:400]))
                else:
                    future.set_result(message.get("result"))

    async def _server_request(self, message: dict):
        method, params = message["method"], message.get("params") or {}
        result = None
        if method == "client/registerCapability":
            self.registered.update(item.get("method", "") for item in params.get("registrations", []))
        elif method == "client/unregisterCapability":
            for item in params.get("unregisterations", []):
                self.registered.discard(item.get("method", ""))
        elif method == "workspace/configuration":
            result = [None] * len(params.get("items", []))
        elif method == "workspace/workspaceFolders":
            result = [{"uri": path_to_uri(self.root), "name": Path(self.root).name}]
        elif method == "workspace/applyEdit":
            # Servers never write files themselves: the edit goes to Studio as
            # an editor-buffer proposal the person reviews before saving.
            edit = self.workspace_edit(params.get("edit"))
            self.publish("lsp.apply_edit", {"workspace_id": self.workspace_id, "language": self.language,
                                            "label": str(params.get("label", ""))[:200], **edit})
            result = {"applied": bool(edit["total"])}
        await self.transport.send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def _notification(self, method: str, params: dict):
        if method == "textDocument/publishDiagnostics":
            path = uri_to_path(params.get("uri", ""))
            items = [self._diagnostic(item) for item in params.get("diagnostics", [])][:500]
            self.diagnostics[path] = items
            self.publish("lsp.diagnostics", {"workspace_id": self.workspace_id, "path": path,
                                             "version": params.get("version"), "diagnostics": items})
        elif method in ("o#/projectadded", "o#/projectchanged", "o#/projectremoved"):
            self.project_events += 1
            if self._reassert_task is None or self._reassert_task.done():
                self._reassert_task = asyncio.create_task(self._reassert_buffers())
        elif method == "window/showMessage":
            self.detail = str(params.get("message", ""))[:300]

    @staticmethod
    def _diagnostic(item: dict) -> dict:
        code = item.get("code")
        return {"range": item.get("range"), "severity": item.get("severity", 1), "code": str(code) if code is not None else "",
                "source": item.get("source", ""), "message": str(item.get("message", ""))[:2000]}

    async def _reassert_buffers(self):
        """OmniSharp drops didOpen text while its project (re)loads; push it again."""
        await asyncio.sleep(1.0)
        for path, item in list(self.documents.items()):
            item["version"] += 1
            await self.notify("textDocument/didChange", {
                "textDocument": {"uri": path_to_uri(path), "version": item["version"]},
                "contentChanges": [{"text": item["text"]}]})

    # ---- documents -----------------------------------------------------
    async def open(self, path: str, text: str, language_id: str):
        await self._ready.wait()
        path = str(Path(path).resolve())
        if path in self.documents:
            return await self.change(path, text)
        self.documents[path] = {"version": 1, "text": text, "language_id": language_id}
        await self.notify("textDocument/didOpen", {"textDocument": {"uri": path_to_uri(path), "languageId": language_id, "version": 1, "text": text}})

    async def change(self, path: str, text: str) -> int:
        path = str(Path(path).resolve())
        item = self.documents.get(path)
        if item is None:
            raise ValueError("Open the document before changing it")
        if item["text"] == text:
            return item["version"]
        item["version"] += 1
        item["text"] = text
        await self.notify("textDocument/didChange", {"textDocument": {"uri": path_to_uri(path), "version": item["version"]},
                                                     "contentChanges": [{"text": text}]})
        return item["version"]

    async def close(self, path: str):
        path = str(Path(path).resolve())
        if self.documents.pop(path, None) is not None:
            await self.notify("textDocument/didClose", {"textDocument": {"uri": path_to_uri(path)}})
            self.diagnostics.pop(path, None)
            self.publish("lsp.diagnostics", {"workspace_id": self.workspace_id, "path": path, "version": None, "diagnostics": []})

    async def saved(self, path: str):
        path = str(Path(path).resolve())
        if path in self.documents:
            await self.notify("textDocument/didSave", {"textDocument": {"uri": path_to_uri(path)}})

    # ---- features ------------------------------------------------------
    def _document(self, path: str) -> dict:
        return {"uri": path_to_uri(path)}

    async def feature(self, name: str, path: str, params: dict):
        """Dispatch one editor request; positions are zero-based LSP positions."""
        await self._ready.wait()
        path = str(Path(path).resolve()) if path else ""
        position = params.get("position")
        if name == "completion":
            result = await self.request("textDocument/completion", {"textDocument": self._document(path), "position": position,
                                                                     "context": params.get("context") or {"triggerKind": 1}})
            items = result.get("items", []) if isinstance(result, dict) else (result or [])
            return {"items": items[:300], "isIncomplete": bool(isinstance(result, dict) and result.get("isIncomplete"))}
        if name == "completionResolve":
            return await self.request("completionItem/resolve", params.get("item") or {})
        if name == "hover":
            return await self.request("textDocument/hover", {"textDocument": self._document(path), "position": position})
        if name == "signatureHelp":
            return await self.request("textDocument/signatureHelp", {"textDocument": self._document(path), "position": position})
        if name == "definition":
            return self._locations(await self.request("textDocument/definition", {"textDocument": self._document(path), "position": position}))
        if name == "references":
            return self._locations(await self.request("textDocument/references", {"textDocument": self._document(path), "position": position,
                                                                                    "context": {"includeDeclaration": True}}))
        if name == "documentSymbol":
            return await self.request("textDocument/documentSymbol", {"textDocument": self._document(path)})
        if name == "workspaceSymbol":
            return [self._symbol(item) for item in (await self.request("workspace/symbol", {"query": str(params.get("query", ""))}) or [])[:200]]
        if name == "formatting":
            return await self.request("textDocument/formatting", {"textDocument": self._document(path), "options": params.get("options") or {"tabSize": 4, "insertSpaces": True}})
        if name == "prepareRename":
            return await self.request("textDocument/prepareRename", {"textDocument": self._document(path), "position": position})
        if name == "rename":
            edit = await self.request("textDocument/rename", {"textDocument": self._document(path), "position": position, "newName": str(params.get("newName", ""))})
            return self.workspace_edit(edit)
        if name == "codeAction":
            actions = await self.request("textDocument/codeAction", {"textDocument": self._document(path), "range": params.get("range"),
                                                                      "context": {"diagnostics": params.get("diagnostics") or [], "only": params.get("only")}})
            return [self._code_action(item) for item in (actions or [])[:60]]
        if name == "codeActionResolve":
            resolved = await self.request("codeAction/resolve", params.get("action") or {})
            return self._code_action(resolved or {})
        if name == "executeCommand":
            return await self.request("workspace/executeCommand", {"command": params.get("command"), "arguments": params.get("arguments") or []})
        raise ValueError("Unsupported language feature")

    def _locations(self, result) -> list[dict]:
        items = result if isinstance(result, list) else [result] if result else []
        locations = []
        for item in items:
            if not isinstance(item, dict):
                continue
            uri = item.get("uri") or item.get("targetUri")
            span = item.get("range") or item.get("targetSelectionRange") or item.get("targetRange")
            if uri and span:
                locations.append({"path": uri_to_path(uri), "range": span})
        return locations[:500]

    def _symbol(self, item: dict) -> dict:
        location = item.get("location") or {}
        return {"name": item.get("name", ""), "kind": item.get("kind", 0), "containerName": item.get("containerName", ""),
                "path": uri_to_path(location.get("uri", "")), "range": location.get("range")}

    def _code_action(self, item: dict) -> dict:
        if "command" in item and "title" in item and "kind" not in item and "edit" not in item and isinstance(item.get("command"), str):
            return {"title": item["title"], "kind": "", "command": {"command": item["command"], "arguments": item.get("arguments", [])}, "edit": None, "raw": item}
        edit = item.get("edit")
        return {"title": item.get("title", ""), "kind": item.get("kind", ""), "isPreferred": bool(item.get("isPreferred")),
                "command": item.get("command"), "edit": self.workspace_edit(edit) if edit else None, "raw": item,
                "diagnostics": item.get("diagnostics")}

    def workspace_edit(self, edit) -> dict:
        """Normalise an LSP WorkspaceEdit into per-file edit lists for review."""
        files: dict[str, list] = {}
        if not isinstance(edit, dict):
            return {"files": [], "total": 0}
        for uri, edits in (edit.get("changes") or {}).items():
            files.setdefault(uri_to_path(uri), []).extend(edits)
        for change in edit.get("documentChanges") or []:
            if isinstance(change, dict) and "textDocument" in change:
                files.setdefault(uri_to_path(change["textDocument"].get("uri", "")), []).extend(change.get("edits", []))
        result = []
        for path, edits in files.items():
            ordered = sorted((e for e in edits if isinstance(e, dict) and e.get("range")),
                             key=lambda e: (e["range"]["start"]["line"], e["range"]["start"]["character"]))
            result.append({"path": path, "edits": ordered[:2000], "open": path in self.documents})
        return {"files": result, "total": sum(len(item["edits"]) for item in result)}


def csharp_command() -> list[str] | None:
    executable = PINNED["omnisharp"]["executable"]
    if not executable.is_file():
        return None
    return [str(executable), "-lsp", "--loglevel", "warning"]


def python_command(root: str) -> list[str] | None:
    from .toolchain import module_available
    import sys as _sys
    # Prefer the project interpreter so the server sees the project's packages;
    # fall back to the runtime's own interpreter, which always has pylsp.
    for python in (python_executable(root), _sys.executable):
        if python and module_available(python, "pylsp"):
            return [python, "-m", "pylsp"]
    return None


class LanguageServices:
    """Sessions keyed by (workspace_id, language)."""

    def __init__(self, publish):
        self.publish = publish
        self.sessions: dict[tuple[str, str], LanguageSession] = {}

    def get(self, workspace_id: str, language: str) -> LanguageSession | None:
        return self.sessions.get((workspace_id, language))

    async def ensure(self, workspace_id: str, root: str, language: str, env: dict[str, str]) -> LanguageSession:
        key = (workspace_id, language)
        session = self.sessions.get(key)
        if session and session.state in ("starting", "ready"):
            return session
        if session:
            # A previous session crashed, errored, timed out or was stopped;
            # drop it so the editor recovers cleanly on the next open.
            try:
                await session.stop()
            except Exception:
                pass
            self.sessions.pop(key, None)
        if language == "csharp":
            command = csharp_command()
            if not command:
                raise FileNotFoundError("The C# language server (OmniSharp) is not provisioned. Run scripts/provision_studio_tooling.py.")
            command = command[:2] + ["-s", root] + command[2:]
        elif language == "python":
            command = python_command(root)
            if not command:
                raise FileNotFoundError("python-lsp-server is not installed in the project interpreter.")
        else:
            raise ValueError("No language server is available for this language")
        session = LanguageSession(workspace_id, root, language, command, env, self.publish)
        self.sessions[key] = session
        await session.start()
        return session

    async def stop(self, workspace_id: str, language: str | None = None):
        for key in list(self.sessions):
            if key[0] == workspace_id and (language is None or key[1] == language):
                session = self.sessions.pop(key)
                await session.stop()

    async def stop_all(self):
        """Application exit: stop every server at once and do not wait politely.
        Sequential graceful stops took longer than the host is given to quit,
        which left language servers running after OLIVE had gone."""
        sessions = [self.sessions.pop(key) for key in list(self.sessions)]
        if not sessions:
            return
        await asyncio.gather(*(session.stop(graceful=False) for session in sessions),
                             return_exceptions=True)

    def status(self, workspace_id: str) -> list[dict]:
        return [session.status() for key, session in self.sessions.items() if key[0] == workspace_id]
