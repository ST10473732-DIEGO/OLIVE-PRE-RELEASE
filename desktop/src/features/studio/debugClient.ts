// Debug Adapter Protocol client state for one workspace. The adapter runs in
// the Python runtime; this hook turns its events into editor decorations
// (breakpoints, current line) and the call stack / variables the panel shows.
// Frame and variable references are only valid for one `generation` (between
// a stop and the next resume); anything older is discarded.
import * as monaco from "monaco-editor";
import { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../../services/api";
import {
  tooling,
  useTooling,
  absolutePath,
  relativePath,
  samePath,
  type Breakpoint,
  type DebugStatus,
} from "./tooling";

export interface StackFrame {
  id: number;
  name: string;
  line: number;
  column: number;
  source?: { path?: string; name?: string };
}
export interface Scope {
  name: string;
  variablesReference: number;
  expensive?: boolean;
}
export interface Variable {
  name: string;
  value: string;
  type?: string;
  variablesReference: number;
  evaluateName?: string;
}
export interface WatchResult {
  expression: string;
  result: string;
  type?: string;
  error?: string;
  variablesReference: number;
}
async function dapRequest<T>(
  sessionId: string,
  command: string,
  args: Record<string, unknown>,
  generation?: number,
): Promise<T> {
  const response = await call<{ body: T }>("dap.request", {
    session_id: sessionId,
    command,
    arguments: args,
    ...(generation === undefined ? {} : { generation }),
  });
  return response.body;
}
export function useDebugger(
  workspaceId: string,
  root: string,
  openFile: (path: string, line?: number) => Promise<void>,
  report: (error: unknown) => void,
) {
  const slice = useTooling(workspaceId);
  const status: DebugStatus | null = slice.debug;
  const active = status && ["starting", "running", "suspended"].includes(status.state) ? status : null;
  const [frames, setFrames] = useState<StackFrame[]>([]);
  const [frameId, setFrameId] = useState<number | null>(null);
  const [scopes, setScopes] = useState<Scope[]>([]);
  const [variables, setVariables] = useState<Record<number, Variable[]>>({});
  const [watches, setWatches] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(`studioWatches:${workspaceId}`) || "[]");
    } catch {
      return [];
    }
  });
  const [watchResults, setWatchResults] = useState<WatchResult[]>([]);
  const [current, setCurrent] = useState<{ path: string; line: number } | null>(null);
  const generation = useRef(-1);
  useEffect(() => {
    localStorage.setItem(`studioWatches:${workspaceId}`, JSON.stringify(watches));
  }, [watches, workspaceId]);
  const clearSuspended = useCallback(() => {
    setFrames([]);
    setFrameId(null);
    setScopes([]);
    setVariables({});
    setCurrent(null);
    setWatchResults((items) => items.map((item) => ({ ...item, result: "", error: "not paused" })));
  }, []);
  const loadFrame = useCallback(
    async (session: DebugStatus, frame: StackFrame, gen: number) => {
      setFrameId(frame.id);
      const scopeResult = await dapRequest<{ scopes: Scope[] }>(session.session_id, "scopes", { frameId: frame.id }, gen);
      if (generation.current !== gen) return;
      setScopes(scopeResult.scopes || []);
      const first = scopeResult.scopes?.find((scope) => !scope.expensive);
      if (first) {
        const vars = await dapRequest<{ variables: Variable[] }>(
          session.session_id,
          "variables",
          { variablesReference: first.variablesReference },
          gen,
        );
        if (generation.current !== gen) return;
        setVariables({ [first.variablesReference]: vars.variables || [] });
      }
    },
    [],
  );
  const evaluateWatches = useCallback(
    async (session: DebugStatus, frame: number | null, gen: number, expressions: string[]) => {
      const results: WatchResult[] = [];
      for (const expression of expressions) {
        try {
          const body = await dapRequest<{ result: string; type?: string; variablesReference: number }>(
            session.session_id,
            "evaluate",
            { expression, frameId: frame ?? undefined, context: "watch" },
            gen,
          );
          results.push({ expression, result: body.result, type: body.type, variablesReference: body.variablesReference || 0 });
        } catch (error) {
          results.push({ expression, result: "", error: error instanceof Error ? error.message : "unavailable", variablesReference: 0 });
        }
      }
      if (generation.current === gen) setWatchResults(results);
    },
    [],
  );
  // React to the adapter's actual stop/resume events.
  const lastEvent = slice.debugEvents.at(-1);
  useEffect(() => {
    if (!lastEvent || !status) return;
    if (lastEvent.event === "stopped" && lastEvent.session_id === status.session_id) {
      const gen = lastEvent.generation;
      generation.current = gen;
      const threadId = Number(lastEvent.body.threadId ?? status.thread_id ?? 1);
      void (async () => {
        try {
          const stack = await dapRequest<{ stackFrames: StackFrame[] }>(
            status.session_id,
            "stackTrace",
            { threadId, startFrame: 0, levels: 40 },
            gen,
          );
          if (generation.current !== gen) return;
          const list = stack.stackFrames || [];
          setFrames(list);
          const top = list.find((frame) => frame.source?.path) || list[0];
          if (top) {
            if (top.source?.path) {
              const rel = relativePath(root, top.source.path);
              setCurrent({ path: rel, line: top.line });
              await openFile(rel, top.line).catch(() => undefined);
            }
            await loadFrame(status, top, gen);
            await evaluateWatches(status, top.id, gen, watches);
          }
        } catch (error) {
          report(error);
        }
      })();
    } else if (["continued", "terminated", "exited"].includes(lastEvent.event)) {
      generation.current = -1;
      clearSuspended();
    }
  }, [lastEvent]);
  useEffect(() => {
    if (!active) {
      generation.current = -1;
      clearSuspended();
    }
  }, [active, clearSuspended]);
  const selectFrame = useCallback(
    async (frame: StackFrame) => {
      if (!active || !active.suspended) return;
      const gen = generation.current;
      if (frame.source?.path) {
        const rel = relativePath(root, frame.source.path);
        setCurrent({ path: rel, line: frame.line });
        await openFile(rel, frame.line).catch(report);
      }
      await loadFrame(active, frame, gen).catch(report);
      await evaluateWatches(active, frame.id, gen, watches);
    },
    [active, root, openFile, loadFrame, evaluateWatches, watches, report],
  );
  const expand = useCallback(
    async (reference: number) => {
      if (!active) return;
      const gen = generation.current;
      try {
        const body = await dapRequest<{ variables: Variable[] }>(active.session_id, "variables", { variablesReference: reference }, gen);
        if (generation.current === gen)
          setVariables((all) => ({ ...all, [reference]: body.variables || [] }));
      } catch (error) {
        report(error);
      }
    },
    [active, report],
  );
  const step = useCallback(
    async (command: "next" | "stepIn" | "stepOut" | "continue" | "pause") => {
      if (!active) return;
      try {
        await dapRequest(active.session_id, command, { threadId: active.thread_id ?? 1 });
      } catch (error) {
        report(error);
      }
    },
    [active, report],
  );
  const evaluate = useCallback(
    async (expression: string) => {
      if (!active) throw new Error("No debug session");
      return dapRequest<{ result: string; type?: string; variablesReference: number }>(
        active.session_id,
        "evaluate",
        { expression, frameId: frameId ?? undefined, context: "repl" },
        generation.current,
      );
    },
    [active, frameId],
  );
  const addWatch = useCallback(
    (expression: string) => {
      const next = [...watches.filter((item) => item !== expression), expression].slice(-30);
      setWatches(next);
      if (active?.suspended) void evaluateWatches(active, frameId, generation.current, next);
    },
    [watches, active, frameId, evaluateWatches],
  );
  const removeWatch = useCallback((expression: string) => {
    setWatches((items) => items.filter((item) => item !== expression));
    setWatchResults((items) => items.filter((item) => item.expression !== expression));
  }, []);
  const setExceptionFilters = useCallback(
    async (filters: string[]) => {
      if (!active) return;
      try {
        await dapRequest(active.session_id, "setExceptionBreakpoints", { filters });
      } catch (error) {
        report(error);
      }
    },
    [active, report],
  );
  const launch = useCallback(async () => {
    tooling.clearDebug(workspaceId);
    return call<DebugStatus>("dap.launch", { workspace_id: workspaceId });
  }, [workspaceId]);
  const stop = useCallback(async () => {
    if (!status) return;
    await call("dap.stop", { session_id: status.session_id });
  }, [status]);
  // Breakpoints are kept per absolute path; the editor works in relative paths.
  const toggleBreakpoint = useCallback(
    async (path: string, line: number) => {
      const abs = absolutePath(root, path);
      const existingKey = Object.keys(tooling.slice(workspaceId).breakpoints).find((key) => samePath(key, abs));
      const existing = existingKey ? tooling.slice(workspaceId).breakpoints[existingKey] : [];
      const has = existing.some((item) => item.line === line);
      const lines = has ? existing.filter((item) => item.line !== line) : [...existing, { line, verified: false, message: "", condition: "" }];
      try {
        const response = await call<{ breakpoints: Breakpoint[] }>("dap.breakpoints", {
          workspace_id: workspaceId,
          path,
          lines: lines.map((item) => ({ line: item.line, ...(item.condition ? { condition: item.condition } : {}) })),
        });
        tooling.setBreakpoints(workspaceId, existingKey || abs, response.breakpoints);
      } catch (error) {
        report(error);
      }
    },
    [workspaceId, root, report],
  );
  const breakpointsFor = useCallback(
    (path: string): Breakpoint[] => {
      const abs = absolutePath(root, path);
      const key = Object.keys(slice.breakpoints).find((item) => samePath(item, abs));
      return key ? slice.breakpoints[key] : [];
    },
    [slice.breakpoints, root],
  );
  return {
    status,
    active,
    frames,
    frameId,
    scopes,
    variables,
    watches,
    watchResults,
    current,
    console: slice.debugConsole,
    selectFrame,
    expand,
    step,
    evaluate,
    addWatch,
    removeWatch,
    setExceptionFilters,
    launch,
    stop,
    toggleBreakpoint,
    breakpointsFor,
    breakpoints: slice.breakpoints,
  };
}
export type Debugger = ReturnType<typeof useDebugger>;
// Editor decorations for breakpoints and the paused line.
export function decorateModel(
  editor: monaco.editor.IStandaloneCodeEditor,
  collection: monaco.editor.IEditorDecorationsCollection,
  breakpoints: Breakpoint[],
  current: { line: number } | null,
) {
  const decorations: monaco.editor.IModelDeltaDecoration[] = breakpoints.map((item) => ({
    range: new monaco.Range(item.line, 1, item.line, 1),
    options: {
      glyphMarginClassName: item.verified ? "olive-breakpoint" : "olive-breakpoint unverified",
      glyphMarginHoverMessage: {
        value: item.verified ? "Breakpoint" : item.message || "Breakpoint (not yet verified)",
      },
      stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
    },
  }));
  if (current)
    decorations.push({
      range: new monaco.Range(current.line, 1, current.line, 1),
      options: {
        isWholeLine: true,
        className: "olive-debug-line",
        glyphMarginClassName: "olive-debug-arrow",
        stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
      },
    });
  collection.set(decorations);
  void editor;
}
