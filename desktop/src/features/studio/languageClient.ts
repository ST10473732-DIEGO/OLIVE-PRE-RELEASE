// Monaco ↔ language-server glue. All requests go through the validated
// `lsp.*` bridge methods; the servers themselves run inside the Python
// runtime as owned child processes. Results that arrive after the editor has
// moved on (cancelled tokens, newer document versions) are discarded.
import * as monaco from "monaco-editor";
import { call } from "../../services/api";
import {
  tooling,
  type Diagnostic,
  type Position,
  type Range,
  type WorkspaceEdit,
} from "./tooling";

export const LANGUAGE_FOR_SUFFIX: Record<string, string> = {
  cs: "csharp",
  py: "python",
};
export interface LanguageHooks {
  openFile: (
    workspaceId: string,
    path: string,
    line?: number,
    column?: number,
  ) => Promise<void>;
  proposeEdit: (workspaceId: string, edit: WorkspaceEdit) => void;
  rootFor: (workspaceId: string) => string;
}
let hooks: LanguageHooks | null = null;
let registered = false;
const starting = new Map<string, Promise<void>>();

export function modelLocation(model: monaco.editor.ITextModel) {
  const uri = model.uri;
  if (uri.scheme !== "olive-source") return null;
  const [, workspaceId, ...rest] = uri.path.split("/");
  return { workspaceId, path: rest.join("/") };
}
export function modelUri(workspaceId: string, path: string) {
  return monaco.Uri.parse(`olive-source://workspace/${workspaceId}/${path}`);
}
export const languageFor = (path: string) =>
  LANGUAGE_FOR_SUFFIX[path.split(".").pop()?.toLowerCase() || ""] || "";

export function toLspPosition(position: monaco.IPosition): Position {
  return { line: position.lineNumber - 1, character: position.column - 1 };
}
export function toMonacoRange(range: Range): monaco.IRange {
  return {
    startLineNumber: range.start.line + 1,
    startColumn: range.start.character + 1,
    endLineNumber: range.end.line + 1,
    endColumn: range.end.character + 1,
  };
}
export function toLspRange(range: monaco.IRange): Range {
  return {
    start: { line: range.startLineNumber - 1, character: range.startColumn - 1 },
    end: { line: range.endLineNumber - 1, character: range.endColumn - 1 },
  };
}

// Starting a server is an explicit, audited runtime action; concurrent
// callers share one start.
export async function ensureLanguage(workspaceId: string, language: string) {
  const key = `${workspaceId}:${language}`;
  const current = tooling.slice(workspaceId).languages[language];
  if (current && ["starting", "ready"].includes(current.state)) return;
  let pending = starting.get(key);
  if (!pending) {
    pending = call("lsp.start", { workspace_id: workspaceId, language })
      .then(() => undefined)
      .finally(() => starting.delete(key));
    starting.set(key, pending);
  }
  await pending;
}

export async function request<T>(
  workspaceId: string,
  feature: string,
  path: string,
  params: Record<string, unknown>,
  language?: string,
): Promise<T> {
  const response = await call<{ result: T }>("lsp.request", {
    workspace_id: workspaceId,
    feature,
    path,
    params,
    ...(language ? { language } : {}),
  });
  return response.result;
}

/** Editor intelligence is advisory. A server that errors, lags behind a fast
 *  edit or answers about a position it has not seen yet must never surface as
 *  an application error: the editor keeps working without that one answer. */
async function ask<T>(
  workspaceId: string,
  feature: string,
  path: string,
  params: Record<string, unknown>,
  language?: string,
): Promise<T | null> {
  try {
    return await request<T>(workspaceId, feature, path, params, language);
  } catch {
    return null;
  }
}

// ---- document synchronisation ---------------------------------------
interface SyncState {
  timer: ReturnType<typeof setTimeout> | null;
  pending: Promise<unknown> | null;
  opened: boolean;
}
const syncStates = new Map<string, SyncState>();
const reportedFailures = new Set<string>();
export function syncDocument(
  workspaceId: string,
  path: string,
  model: monaco.editor.ITextModel,
  report: (error: unknown) => void,
) {
  const language = languageFor(path);
  if (!language) return () => undefined;
  const key = `${workspaceId}:${path}`;
  const state: SyncState = { timer: null, pending: null, opened: false };
  syncStates.set(key, state);
  let disposed = false;
  const send = () => {
    if (disposed || !state.opened) return;
    state.pending = call("lsp.change", {
      workspace_id: workspaceId,
      path,
      text: model.getValue(),
    })
      .catch(() => undefined)
      .finally(() => {
        state.pending = null;
      });
  };
  state.pending = ensureLanguage(workspaceId, language)
    .then(() => {
      const status = tooling.slice(workspaceId).languages[language];
      // A server that failed to start is shown in the status strip; the
      // editor keeps working without it and does not nag per file.
      if (disposed || !status || !["starting", "ready"].includes(status.state)) return;
      return call("lsp.open", {
        workspace_id: workspaceId,
        path,
        text: model.getValue(),
        language_id: language,
      }).then(() => {
        state.opened = true;
        // Text typed while the server was starting must not be lost.
        send();
      });
    })
    .catch((error) => {
      const marker = `${workspaceId}:${language}`;
      if (!reportedFailures.has(marker)) {
        reportedFailures.add(marker);
        report(error);
      }
    })
    .finally(() => {
      state.pending = null;
    });
  const change = model.onDidChangeContent(() => {
    if (state.timer) clearTimeout(state.timer);
    state.timer = setTimeout(() => {
      state.timer = null;
      send();
    }, 120);
  });
  return () => {
    disposed = true;
    change.dispose();
    if (state.timer) clearTimeout(state.timer);
    syncStates.delete(key);
    if (state.opened)
      void call("lsp.close", { workspace_id: workspaceId, path }).catch(
        () => undefined,
      );
  };
}
// Feature requests wait for the latest buffer to reach the server so answers
// describe what the person is looking at.
export async function flush(workspaceId: string, path: string) {
  const state = syncStates.get(`${workspaceId}:${path}`);
  if (!state) return;
  if (state.timer) {
    clearTimeout(state.timer);
    state.timer = null;
    await call("lsp.change", {
      workspace_id: workspaceId,
      path,
      text: monaco.editor.getModel(modelUri(workspaceId, path))?.getValue() || "",
    }).catch(() => undefined);
  }
  if (state.pending) await state.pending;
}
export function documentSaved(workspaceId: string, path: string) {
  if (!languageFor(path)) return;
  void call("lsp.saved", { workspace_id: workspaceId, path }).catch(
    () => undefined,
  );
}

// ---- diagnostics → markers -------------------------------------------
const severityMap: Record<number, monaco.MarkerSeverity> = {
  1: monaco.MarkerSeverity.Error,
  2: monaco.MarkerSeverity.Warning,
  3: monaco.MarkerSeverity.Info,
  4: monaco.MarkerSeverity.Hint,
};
export function applyDiagnostics(
  model: monaco.editor.ITextModel,
  items: Diagnostic[],
) {
  monaco.editor.setModelMarkers(
    model,
    "olive-lsp",
    items.slice(0, 500).map((item) => ({
      ...toMonacoRange(item.range),
      message: item.message,
      severity: severityMap[item.severity] || monaco.MarkerSeverity.Error,
      code: item.code || undefined,
      source: item.source || "language server",
    })),
  );
}

// ---- providers ---------------------------------------------------------
const completionKinds: Record<number, monaco.languages.CompletionItemKind> = {
  1: monaco.languages.CompletionItemKind.Text,
  2: monaco.languages.CompletionItemKind.Method,
  3: monaco.languages.CompletionItemKind.Function,
  4: monaco.languages.CompletionItemKind.Constructor,
  5: monaco.languages.CompletionItemKind.Field,
  6: monaco.languages.CompletionItemKind.Variable,
  7: monaco.languages.CompletionItemKind.Class,
  8: monaco.languages.CompletionItemKind.Interface,
  9: monaco.languages.CompletionItemKind.Module,
  10: monaco.languages.CompletionItemKind.Property,
  11: monaco.languages.CompletionItemKind.Unit,
  12: monaco.languages.CompletionItemKind.Value,
  13: monaco.languages.CompletionItemKind.Enum,
  14: monaco.languages.CompletionItemKind.Keyword,
  15: monaco.languages.CompletionItemKind.Snippet,
  16: monaco.languages.CompletionItemKind.Color,
  17: monaco.languages.CompletionItemKind.File,
  18: monaco.languages.CompletionItemKind.Reference,
  19: monaco.languages.CompletionItemKind.Folder,
  20: monaco.languages.CompletionItemKind.EnumMember,
  21: monaco.languages.CompletionItemKind.Constant,
  22: monaco.languages.CompletionItemKind.Struct,
  23: monaco.languages.CompletionItemKind.Event,
  24: monaco.languages.CompletionItemKind.Operator,
  25: monaco.languages.CompletionItemKind.TypeParameter,
};
const symbolKinds: Record<number, monaco.languages.SymbolKind> = {
  1: monaco.languages.SymbolKind.File,
  2: monaco.languages.SymbolKind.Module,
  3: monaco.languages.SymbolKind.Namespace,
  4: monaco.languages.SymbolKind.Package,
  5: monaco.languages.SymbolKind.Class,
  6: monaco.languages.SymbolKind.Method,
  7: monaco.languages.SymbolKind.Property,
  8: monaco.languages.SymbolKind.Field,
  9: monaco.languages.SymbolKind.Constructor,
  10: monaco.languages.SymbolKind.Enum,
  11: monaco.languages.SymbolKind.Interface,
  12: monaco.languages.SymbolKind.Function,
  13: monaco.languages.SymbolKind.Variable,
  14: monaco.languages.SymbolKind.Constant,
  15: monaco.languages.SymbolKind.String,
  16: monaco.languages.SymbolKind.Number,
  17: monaco.languages.SymbolKind.Boolean,
  18: monaco.languages.SymbolKind.Array,
  19: monaco.languages.SymbolKind.Object,
  20: monaco.languages.SymbolKind.Key,
  21: monaco.languages.SymbolKind.Null,
  22: monaco.languages.SymbolKind.EnumMember,
  23: monaco.languages.SymbolKind.Struct,
  24: monaco.languages.SymbolKind.Event,
  25: monaco.languages.SymbolKind.Operator,
  26: monaco.languages.SymbolKind.TypeParameter,
};
interface LspCompletionItem {
  label: string;
  kind?: number;
  detail?: string;
  documentation?: string | { value: string };
  insertText?: string;
  insertTextFormat?: number;
  textEdit?: { range?: Range; newText: string; insert?: Range; replace?: Range };
  additionalTextEdits?: { range: Range; newText: string }[];
  sortText?: string;
  filterText?: string;
  preselect?: boolean;
  data?: unknown;
  commitCharacters?: string[];
}
type OliveCompletion = monaco.languages.CompletionItem & {
  raw: LspCompletionItem;
  location: { workspaceId: string; path: string };
};
function markdown(value: string | { value: string } | undefined) {
  if (!value) return undefined;
  return typeof value === "string" ? { value } : { value: value.value };
}
function locate(model: monaco.editor.ITextModel) {
  const location = modelLocation(model);
  if (!location || !languageFor(location.path)) return null;
  return location;
}
async function ready(model: monaco.editor.ITextModel) {
  const location = locate(model);
  if (!location) return null;
  await flush(location.workspaceId, location.path);
  return location;
}
export function registerLanguageProviders(next: LanguageHooks) {
  hooks = next;
  if (registered) return;
  registered = true;
  const languages = ["csharp", "python"];
  for (const language of languages) {
    monaco.languages.registerCompletionItemProvider(language, {
      triggerCharacters: language === "csharp" ? [".", " ", "(", "<"] : ["."],
      async provideCompletionItems(model, position, context, token) {
        const location = await ready(model);
        if (!location || token.isCancellationRequested) return null;
        const word = model.getWordUntilPosition(position);
        const fallback = new monaco.Range(
          position.lineNumber,
          word.startColumn,
          position.lineNumber,
          word.endColumn,
        );
        const result = await ask<{ items: LspCompletionItem[]; isIncomplete: boolean }>(
          location.workspaceId,
          "completion",
          location.path,
          {
            position: toLspPosition(position),
            context: {
              triggerKind: context.triggerKind === monaco.languages.CompletionTriggerKind.TriggerCharacter ? 2 : 1,
              triggerCharacter: context.triggerCharacter,
            },
          },
        );
        if (!result || token.isCancellationRequested) return null;
        const suggestions: OliveCompletion[] = result.items.map((item) => {
          const editRange = item.textEdit?.range || item.textEdit?.replace;
          return {
            label: item.label,
            kind: completionKinds[item.kind || 1] || monaco.languages.CompletionItemKind.Text,
            detail: item.detail,
            documentation: markdown(item.documentation),
            insertText: item.textEdit?.newText ?? item.insertText ?? item.label,
            insertTextRules:
              item.insertTextFormat === 2
                ? monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
                : undefined,
            range: editRange ? toMonacoRange(editRange) : fallback,
            sortText: item.sortText,
            filterText: item.filterText,
            preselect: item.preselect,
            commitCharacters: item.commitCharacters,
            additionalTextEdits: item.additionalTextEdits?.map((edit) => ({
              range: toMonacoRange(edit.range),
              text: edit.newText,
            })),
            raw: item,
            location,
          };
        });
        return { suggestions, incomplete: result.isIncomplete };
      },
      async resolveCompletionItem(item, token) {
        const { raw, location } = item as OliveCompletion;
        if (!raw || !location || (raw.documentation && raw.additionalTextEdits))
          return item;
        try {
          const resolved = await request<LspCompletionItem>(
            location.workspaceId,
            "completionResolve",
            location.path,
            { item: raw },
          );
          if (token.isCancellationRequested) return item;
          return {
            ...item,
            detail: resolved.detail ?? item.detail,
            documentation: markdown(resolved.documentation) ?? item.documentation,
            additionalTextEdits:
              resolved.additionalTextEdits?.map((edit) => ({
                range: toMonacoRange(edit.range),
                text: edit.newText,
              })) ?? item.additionalTextEdits,
          };
        } catch {
          return item;
        }
      },
    });
    monaco.languages.registerHoverProvider(language, {
      async provideHover(model, position, token) {
        const location = await ready(model);
        if (!location || token.isCancellationRequested) return null;
        const result = await ask<{
          contents: unknown;
          range?: Range;
        } | null>(location.workspaceId, "hover", location.path, {
          position: toLspPosition(position),
        });
        if (!result || token.isCancellationRequested) return null;
        const contents = Array.isArray(result.contents) ? result.contents : [result.contents];
        return {
          range: result.range ? toMonacoRange(result.range) : undefined,
          contents: contents
            .map((item) =>
              typeof item === "string"
                ? { value: item }
                : item && typeof item === "object" && "value" in item
                  ? {
                      value:
                        "language" in item
                          ? "```" + String((item as { language: string }).language) + "\n" + String((item as { value: string }).value) + "\n```"
                          : String((item as { value: string }).value),
                    }
                  : null,
            )
            .filter((item): item is { value: string } => Boolean(item && item.value)),
        };
      },
    });
    monaco.languages.registerSignatureHelpProvider(language, {
      signatureHelpTriggerCharacters: ["(", ","],
      signatureHelpRetriggerCharacters: [")"],
      async provideSignatureHelp(model, position, token) {
        const location = await ready(model);
        if (!location || token.isCancellationRequested) return null;
        const result = await ask<{
          signatures: {
            label: string;
            documentation?: string | { value: string };
            parameters?: { label: string | [number, number]; documentation?: string | { value: string } }[];
          }[];
          activeSignature?: number;
          activeParameter?: number;
        } | null>(location.workspaceId, "signatureHelp", location.path, {
          position: toLspPosition(position),
        });
        if (!result || token.isCancellationRequested || !result.signatures?.length) return null;
        return {
          value: {
            signatures: result.signatures.map((signature) => ({
              label: signature.label,
              documentation: markdown(signature.documentation),
              parameters: (signature.parameters || []).map((parameter) => ({
                label: parameter.label,
                documentation: markdown(parameter.documentation),
              })),
            })),
            activeSignature: result.activeSignature || 0,
            activeParameter: result.activeParameter || 0,
          },
          dispose() {},
        };
      },
    });
    monaco.languages.registerDefinitionProvider(language, {
      async provideDefinition(model, position, token) {
        const location = await ready(model);
        if (!location || token.isCancellationRequested) return null;
        const result = await ask<{ path: string; range: Range }[]>(
          location.workspaceId,
          "definition",
          location.path,
          { position: toLspPosition(position) },
        );
        if (!result || token.isCancellationRequested) return null;
        const root = hooks?.rootFor(location.workspaceId) || "";
        return result
          .filter((item) => inside(root, item.path))
          .map((item) => ({
            uri: modelUri(location.workspaceId, relative(root, item.path)),
            range: toMonacoRange(item.range),
          }));
      },
    });
    monaco.languages.registerDocumentSymbolProvider(language, {
      async provideDocumentSymbols(model, token) {
        const location = await ready(model);
        if (!location || token.isCancellationRequested) return null;
        const result = await ask<unknown[]>(
          location.workspaceId,
          "documentSymbol",
          location.path,
          {},
        );
        if (token.isCancellationRequested || !Array.isArray(result)) return null;
        return result.map((item) => symbol(item as Record<string, unknown>)).filter(Boolean) as monaco.languages.DocumentSymbol[];
      },
    });
    monaco.languages.registerDocumentFormattingEditProvider(language, {
      async provideDocumentFormattingEdits(model, options, token) {
        const location = await ready(model);
        if (!location || token.isCancellationRequested) return null;
        const result = await ask<{ range: Range; newText: string }[] | null>(
          location.workspaceId,
          "formatting",
          location.path,
          { options: { tabSize: options.tabSize, insertSpaces: options.insertSpaces } },
        );
        if (!result || token.isCancellationRequested) return null;
        return result.map((edit) => ({ range: toMonacoRange(edit.range), text: edit.newText }));
      },
    });
    monaco.languages.registerCodeActionProvider(language, {
      async provideCodeActions(model, range, context, token) {
        const location = await ready(model);
        if (!location || token.isCancellationRequested) return null;
        const diagnostics = (tooling.slice(location.workspaceId).diagnostics[
          absolute(hooks?.rootFor(location.workspaceId) || "", location.path)
        ] || []).filter((item) =>
          context.markers.some(
            (marker) =>
              marker.startLineNumber === item.range.start.line + 1 &&
              marker.message === item.message,
          ),
        );
        const result = await ask<
          {
            title: string;
            kind: string;
            isPreferred?: boolean;
            command?: { command: string; arguments?: unknown[] } | null;
            edit: WorkspaceEdit | null;
            raw: unknown;
          }[]
        >(location.workspaceId, "codeAction", location.path, {
          range: toLspRange(range),
          diagnostics,
        });
        if (!result || token.isCancellationRequested) return null;
        return {
          actions: result.map((action) => ({
            title: action.title,
            kind: action.kind || undefined,
            isPreferred: action.isPreferred,
            command: {
              id: "olive.codeAction",
              title: action.title,
              arguments: [location.workspaceId, location.path, action],
            },
          })),
          dispose() {},
        };
      },
    });
  }
  monaco.editor.registerCommand(
    "olive.codeAction",
    async (
      _accessor,
      workspaceId: string,
      path: string,
      action: {
        title: string;
        command?: { command: string; arguments?: unknown[] } | null;
        edit: WorkspaceEdit | null;
        raw: unknown;
      },
    ) => {
      let edit = action.edit;
      if (!edit && !action.command) {
        const resolved = await request<{ edit: WorkspaceEdit | null; command?: { command: string; arguments?: unknown[] } | null }>(
          workspaceId,
          "codeActionResolve",
          path,
          { action: action.raw },
        );
        edit = resolved.edit;
        if (!edit && resolved.command) action = { ...action, command: resolved.command };
      }
      if (edit && edit.total) {
        hooks?.proposeEdit(workspaceId, { ...edit, label: action.title });
        return;
      }
      if (action.command) {
        // Server-side commands answer with workspace/applyEdit, which the
        // runtime turns into a reviewed proposal (`lsp.apply_edit`).
        await request(workspaceId, "executeCommand", path, {
          command: action.command.command,
          arguments: action.command.arguments || [],
        });
      }
    },
  );
  monaco.editor.registerEditorOpener({
    openCodeEditor(_source, resource, selectionOrPosition) {
      if (resource.scheme !== "olive-source") return false;
      const [, workspaceId, ...rest] = resource.path.split("/");
      const line =
        selectionOrPosition && "lineNumber" in selectionOrPosition
          ? selectionOrPosition.lineNumber
          : selectionOrPosition && "startLineNumber" in selectionOrPosition
            ? selectionOrPosition.startLineNumber
            : undefined;
      const column =
        selectionOrPosition && "column" in selectionOrPosition
          ? selectionOrPosition.column
          : selectionOrPosition && "startColumn" in selectionOrPosition
            ? selectionOrPosition.startColumn
            : undefined;
      void hooks?.openFile(workspaceId, rest.join("/"), line, column);
      return true;
    },
  });
}
function symbol(item: Record<string, unknown>): monaco.languages.DocumentSymbol | null {
  const name = String(item.name || "");
  if (!name) return null;
  const range = (item.range || (item.location as { range?: Range } | undefined)?.range) as Range | undefined;
  if (!range) return null;
  const selection = (item.selectionRange as Range | undefined) || range;
  return {
    name,
    detail: String(item.detail || item.containerName || ""),
    kind: symbolKinds[Number(item.kind)] || monaco.languages.SymbolKind.Variable,
    range: toMonacoRange(range),
    selectionRange: toMonacoRange(selection),
    tags: [],
    children: Array.isArray(item.children)
      ? (item.children.map((child) => symbol(child as Record<string, unknown>)).filter(Boolean) as monaco.languages.DocumentSymbol[])
      : undefined,
  };
}
function inside(root: string, path: string) {
  const norm = (value: string) => value.replace(/\\/g, "/").toLowerCase().replace(/\/+$/, "");
  return norm(path).startsWith(norm(root) + "/");
}
function relative(root: string, path: string) {
  const norm = (value: string) => value.replace(/\\/g, "/");
  return norm(path).slice(norm(root).replace(/\/+$/, "").length + 1);
}
function absolute(root: string, path: string) {
  return root.replace(/[\\/]+$/, "") + "\\" + path.replace(/\//g, "\\");
}
// ---- explicit editor operations ----------------------------------------
export interface Reference {
  path: string;
  relative: string;
  range: Range;
  text: string;
}
export async function findReferences(
  model: monaco.editor.ITextModel,
  position: monaco.IPosition,
): Promise<Reference[]> {
  const location = await ready(model);
  if (!location) return [];
  const root = hooks?.rootFor(location.workspaceId) || "";
  const result = await ask<{ path: string; range: Range }[]>(
    location.workspaceId,
    "references",
    location.path,
    { position: toLspPosition(position) },
  );
  return (result || []).map((item) => {
    const rel = inside(root, item.path) ? relative(root, item.path) : item.path;
    const open = monaco.editor.getModel(modelUri(location.workspaceId, rel));
    return {
      path: item.path,
      relative: rel,
      range: item.range,
      text: open ? open.getLineContent(item.range.start.line + 1).trim() : "",
    };
  });
}
export async function prepareRename(
  model: monaco.editor.ITextModel,
  position: monaco.IPosition,
): Promise<{ range: monaco.IRange; placeholder: string } | null> {
  const location = await ready(model);
  if (!location) return null;
  const result = await request<
    | { range: Range; placeholder: string }
    | { start: Position; end: Position }
    | { defaultBehavior: boolean }
    | null
  >(location.workspaceId, "prepareRename", location.path, {
    position: toLspPosition(position),
  }).catch(() => null);
  const word = model.getWordAtPosition(position);
  const fallback = word
    ? {
        range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn),
        placeholder: word.word,
      }
    : null;
  if (!result) return fallback;
  if ("range" in result && "placeholder" in result)
    return { range: toMonacoRange(result.range), placeholder: result.placeholder };
  if ("start" in result) {
    const range = toMonacoRange(result as Range);
    return { range, placeholder: model.getValueInRange(range) };
  }
  return fallback;
}
export async function renameSymbol(
  model: monaco.editor.ITextModel,
  position: monaco.IPosition,
  newName: string,
): Promise<WorkspaceEdit> {
  const location = await ready(model);
  if (!location) return { files: [], total: 0 };
  return request<WorkspaceEdit>(location.workspaceId, "rename", location.path, {
    position: toLspPosition(position),
    newName,
  });
}
export async function workspaceSymbols(workspaceId: string, language: string, query: string) {
  return request<{ name: string; kind: number; containerName: string; path: string; range: Range }[]>(
    workspaceId,
    "workspaceSymbol",
    "",
    { query },
    language,
  );
}
