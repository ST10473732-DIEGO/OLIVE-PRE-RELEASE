import { RemoteStudio } from "./studio/RemoteStudio";
import type { ComponentProps, ReactNode } from "react";
import { readPanelLayout, savePanelLayout, panelBounds } from "./studio/panelLayout";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
import JsonWorker from "monaco-editor/language/json/json.worker?worker";
import CssWorker from "monaco-editor/language/css/css.worker?worker";
import HtmlWorker from "monaco-editor/language/html/html.worker?worker";
import TsWorker from "monaco-editor/language/typescript/ts.worker?worker";
import {
  FolderOpen,
  FileCode2,
  Play,
  Square,
  FlaskConical,
  Save,
  GitCompare,
  X,
  ChevronsUpDown,
  FilePlus2,
  Bug,
  Hammer,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  AlertTriangle,
  MonitorSmartphone,
  Sparkles,
} from "lucide-react";
import { call, type Workspace, type FileBuffer, type Chat, type Snapshot } from "../services/api";
import { StudioAssistant, type AssistantSeed, type StudioSubmit } from "./studio/Assistant";
import { ActionMenu } from "../components/ActionMenu";
import { Sheet } from "../components/Sheet";
import { LocalPreview } from "./studio/LocalPreview";
import { WorkspaceTools } from "./studio/WorkspaceTools";
import { Explorer } from "../components/Explorer";
import type { OutputChannel } from "../services/studioOutput";
import { Compare } from "./Compare";
import { NewProjectWizard } from "./studio/NewProjectWizard";
import { WinFormsDesigner } from "./studio/WinFormsDesigner";
import { TitleBarPortal, OliveMark } from "../app/TitleBar";
import { usePaletteProvider, type PaletteItem } from "../app/commands";
import { ActivityBar } from "./studio/ActivityBar";
import { StudioPanel } from "./studio/StudioPanel";
import { StatusBar } from "./studio/StatusBar";
import { OutputView } from "./studio/OutputView";
import { SearchView } from "./studio/SearchView";
import { SourceControlView, useGitStatus } from "./studio/SourceControlView";
import { RunDebugView, DebugToolbar, DebugConsole, debugStateText } from "./studio/RunDebugView";
import {
  activityAvailability,
  assistantDocks,
  clampPanelHeight,
  cursorLabel,
  gitDecorations,
  indentLabel,
  languageName,
  languageServerLabel,
  normaliseSymbols,
  panelTabs,
  problemCounts,
  problemsByFile,
  runtimeLabel,
  studioLayout,
  symbolPath,
  symbolTag,
  type OutlineSymbol,
  type PanelTab,
  type StudioView,
} from "./studio/studioModel";
import {
  forgetSession,
  loadOpenWorkspaces,
  saveOpenWorkspaces,
  sessionUi,
  updateSessionUi,
} from "./studio/sessions";
import { Packages } from "./Packages";
import { NewFile } from "./NewFile";
import { tooling, useTooling, relativePath, absolutePath, samePath, type WorkspaceEdit } from "./studio/tooling";
import {
  applyDiagnostics,
  documentSaved,
  request as lspRequest,
  findReferences,
  languageFor,
  modelUri,
  prepareRename,
  registerLanguageProviders,
  renameSymbol,
  syncDocument,
  workspaceSymbols,
  type Reference,
} from "./studio/languageClient";
import { decorateModel, useDebugger } from "./studio/debugClient";
import { TerminalPanel } from "./studio/TerminalPanel";
import { ProblemsPanel, useProblems } from "./studio/ProblemsPanel";
import { TestsPanel } from "./studio/TestsPanel";
import { WebPanel } from "./studio/WebPanel";
import { EditPreview } from "./studio/EditPreview";
import { ProjectPanel, useProjectScan } from "./studio/ProjectPanel";
self.MonacoEnvironment = {
  getWorker: (_id, label) =>
    label === "json"
      ? new JsonWorker()
      : ["css", "scss", "less"].includes(label)
        ? new CssWorker()
        : ["html", "handlebars", "razor"].includes(label)
          ? new HtmlWorker()
          : ["typescript", "javascript"].includes(label)
            ? new TsWorker()
            : new EditorWorker(),
};
interface OpenFile {
  path: string;
  workspace: string;
  model: monaco.editor.ITextModel;
  hash: string;
  saved: string;
  view?: monaco.editor.ICodeEditorViewState | null;
  unsync?: () => void;
}
const retained = new Map<string, OpenFile>();
const lastPaths = new Map<string, string>();
// Buffers discarded or saved in this session must not be restored from a
// runtime snapshot taken before the discard; the host no longer holds them.
const discarded = new Set<string>();
interface FileState {
  relative_path: string;
  text: string;
  loaded_hash: string;
  saved_text: string;
}
type DockTab = PanelTab;
/** Panel state saved before V2 used tool names that are now sidebar views. */
function migrateDock(value: string): { dock: PanelTab | ""; view?: StudioView } {
  if (value === "tests") return { dock: "", view: "testing" };
  if (value === "git") return { dock: "", view: "scm" };
  if (value === "debug") return { dock: "console", view: "debug" };
  return { dock: (["problems", "output", "terminal", "console", "web", "references"].includes(value) ? value : "") as PanelTab | "" };
}
// OLIVE Night (Studio V2 §17): Monaco colours read the same CSS tokens.
const SYNTAX: [string, string, string?][] = [
  ["comment", "--syn-comment", "italic"],
  ["keyword", "--syn-keyword"],
  ["keyword.control", "--syn-control"],
  ["string", "--syn-string"],
  ["string.escape", "--syn-decorator"],
  ["number", "--syn-number"],
  ["type", "--syn-type"],
  ["type.identifier", "--syn-type"],
  ["identifier", "--syn-text"],
  ["delimiter", "--syn-punct"],
  ["operator", "--syn-punct"],
  ["tag", "--syn-keyword"],
  ["attribute.name", "--syn-param"],
  ["attribute.value", "--syn-string"],
  ["key", "--syn-param"],
  ["string.key.json", "--syn-param"],
  ["string.value.json", "--syn-string"],
  ["annotation", "--syn-decorator"],
  ["predefined", "--syn-function"],
  ["constant", "--syn-constant"],
];
const MONO_STACK = '"Cascadia Code", "Cascadia Mono", "JetBrains Mono", "Fira Code", Consolas, "DejaVu Sans Mono", monospace';
/** The person's editor font keeps priority; the V2 stack follows it so a
 *  machine without that face (Linux has no Consolas) still gets a code face. */
const editorFont = (preferred: string) => (preferred ? `"${preferred.replace(/"/g, "")}", ${MONO_STACK}` : MONO_STACK);
const LANGUAGE_IDS: Record<string, string> = {
  py: "python",
  java: "java",
  xml: "xml",
  gradle: "groovy",
  c: "c",
  cpp: "cpp",
  rs: "rust",
  go: "go",
  yaml: "yaml",
  yml: "yaml",
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  json: "json",
  cs: "csharp",
  csproj: "xml",
  sln: "plaintext",
  slnx: "xml",
  props: "xml",
  targets: "xml",
  md: "markdown",
  css: "css",
  html: "html",
  cshtml: "html",
  razor: "html",
};
function LocalStudio({
  chat,
  submit,
  interactionBusy,
  workspaces,
  workspaceId,
  setWorkspaceId,
  selectRequest,
  newProjectRequest = 0,
  visible = true,
  output,
  channels,
  selectedOutput,
  selectOutput,
  setOutput,
  report,
  theme,
  buffers,
  snapshot,
  cancel,
  openSettings,
  location,
  openRemote,
}: {
  snapshot: Snapshot | null;
  cancel: () => void;
  openSettings: () => void;
  /** The Local / Remote switch, shown in the title bar by whichever mode is visible. */
  location: ReactNode;
  openRemote: () => void;
  chat: Chat | null;
  submit: StudioSubmit;
  interactionBusy: boolean;
  workspaces: Workspace[];
  workspaceId: string;
  setWorkspaceId: (id: string) => void;
  /** Bumped when something outside Studio asks for a specific workspace. */
  selectRequest?: { id: string; revision: number };
  /** Bumped when something outside Studio asks for the New project wizard. */
  newProjectRequest?: number;
  // Studio stays mounted while the route is visited; it re-measures on return.
  visible?: boolean;
  output: string;
  channels: OutputChannel[];
  selectedOutput: string;
  selectOutput: (id: string) => void;
  setOutput: (text: string) => void;
  report: (e: unknown) => void;
  theme: string;
  buffers: FileBuffer[];
}) {
  // Studio keeps its own set of open workspaces. Opening another one never
  // replaces the current session; both stay alive with their own state.
  const [openIds, setOpenIds] = useState<string[]>(() => {
    const stored = loadOpenWorkspaces();
    return workspaceId && !stored.includes(workspaceId) ? [...stored, workspaceId] : stored;
  });
  useEffect(() => {
    saveOpenWorkspaces(openIds);
  }, [openIds]);
  const openWorkspace = useCallback(
    (id: string) => {
      if (!id) return;
      setOpenIds((current) => (current.includes(id) ? current : [...current, id]));
      setWorkspaceId(id);
    },
    [setWorkspaceId],
  );
  useEffect(() => {
    if (workspaceId) setOpenIds((current) => (current.includes(workspaceId) ? current : [...current, workspaceId]));
  }, [workspaceId]);
  const [wizard, setWizard] = useState(false);
  const [designerOpen, setDesignerOpen] = useState(false);
  const [closingWorkspace, setClosingWorkspace] = useState<{
    id: string;
    title: string;
    dirty: number;
    running: string[];
  } | null>(null);
  useEffect(() => {
    if (newProjectRequest) setWizard(true);
  }, [newProjectRequest]);
  useEffect(() => {
    if (selectRequest?.id) openWorkspace(selectRequest.id);
  }, [selectRequest?.revision]);
  const [entries, setEntries] = useState<{ path: string; directory: boolean }[]>([]);
  const [active, setActive] = useState(() => sessionUi(workspaceId).activePath || lastPaths.get(workspaceId) || "");
  const [, render] = useState(0);
  const [busy, setBusy] = useState(false);
  const [closing, setClosing] = useState<OpenFile | null>(null);
  const [saveStatus, setSaveStatus] = useState("");
  const validation = [...channels]
    .reverse()
    .find((c) => c.validation && ["running", "cancelling"].includes(c.validation.state))?.validation;
  const [switching, setSwitching] = useState(false);
  const activeCommand = [...channels]
    .reverse()
    .find((channel) => ["running", "cancelling"].includes(channel.commandState || "") && !channel.id.startsWith("job:"));
  const latestRun = [...channels].reverse().find((c) => c.runState);
  const session = latestRun?.id || "";
  const activeRun = [...channels].reverse().find((c) => ["starting", "running"].includes(c.runState || ""));
  const [comparison, setComparison] = useState<{ disk_text: string; disk_hash: string; file: OpenFile } | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const decorations = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);
  const current = useRef("");
  const diagnostics = useRef<{ file?: string; line?: number; column?: number; severity: string; message: string }[]>([]);
  const workspace = workspaces.find((w) => w.id === workspaceId);
  const root = workspace?.root_path || "";
  const editorPreferences = useRef({ fontSize: 13, lineHeight: 20, fontFamily: editorFont("Consolas"), tabSize: 4 });
  const key = (path: string) => workspaceId + ":" + path;
  // ---- layout state (Studio V2 §3) ------------------------------------------
  // The primary sidebar, bottom panel and OLIVE sidebar are separate, sized
  // independently and remembered; the editor stays the primary surface.
  const [width, setWidth] = useState(() => window.innerWidth);
  useEffect(() => {
    const measure = () => setWidth(window.innerWidth);
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  const layout = studioLayout(width);
  useEffect(() => {
    // The minimap is shown only on wide windows, re-evaluated as the window resizes.
    editor.current?.updateOptions({ minimap: { enabled: layout.minimap } });
  }, [layout.minimap]);
  const [sizes, setSizes] = useState(() => readPanelLayout());
  const setSize = useCallback((key: "explorer" | "assistant" | "output", value: number) => {
    setSizes((current) => {
      const [min, max] = panelBounds[key];
      const next = { ...current, [key]: Math.max(min, Math.min(max, Math.round(value))) };
      savePanelLayout(next);
      return next;
    });
  }, []);
  const [explorer, setExplorer] = useState(localStorage.getItem("studioExplorer") !== "false");
  const [view, setView] = useState<StudioView>("explorer");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [dock, setDock] = useState<DockTab | "">("");
  const [panelMax, setPanelMax] = useState(false);
  useEffect(() => {
    if (dock && layout.sidebarOverlay) setExplorer(false);
  }, [dock, layout.sidebarOverlay]);
  const [terminalRequest, setTerminalRequest] = useState(0);
  const lastDock = useRef<DockTab>("problems");
  useEffect(() => {
    if (dock) lastDock.current = dock;
  }, [dock]);
  const [assistantSeed, setAssistantSeed] = useState<AssistantSeed>();
  const [searchSignal, setSearchSignal] = useState(0);
  const [collapseSignal, setCollapseSignal] = useState(0);
  const [cursor, setCursor] = useState({ line: 1, column: 1, lines: 0, chars: 0 });
  const [symbols, setSymbols] = useState<OutlineSymbol[]>([]);
  const [outlineOpen, setOutlineOpen] = useState(true);
  const [openEditorsOpen, setOpenEditorsOpen] = useState(true);
  const [treeOpen, setTreeOpen] = useState(true);
  const [panelColumn, setPanelColumn] = useState(600);
  useEffect(() => {
    localStorage.setItem("studioExplorer", String(explorer));
  }, [explorer]);
  const showView = useCallback((next: StudioView) => {
    setView(next);
    setExplorer(true);
  }, []);
  // ---- tooling state ---------------------------------------------------
  const slice = useTooling(workspaceId);
  const { scan, refresh: rescan } = useProjectScan(workspaceId, report);
  const isDotnet = scan?.kind === "dotnet";
  const structuredTests = isDotnet || scan?.kind === "python";
  useEffect(() => {
    if (workspaceId) void tooling.hydrate(workspaceId).catch(report);
  }, [workspaceId, report]);
  const [references, setReferences] = useState<{ symbol: string; items: Reference[] } | null>(null);
  const [renaming, setRenaming] = useState<{ position: monaco.IPosition; range: monaco.IRange; placeholder: string } | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [proposedEdit, setProposedEdit] = useState<WorkspaceEdit | null>(null);
  useEffect(() => {
    if (!proposedEdit && slice.proposedEdits.length) {
      const next = slice.proposedEdits[0];
      setProposedEdit(next);
      tooling.dismissEdit(workspaceId, next);
    }
  }, [slice.proposedEdits, proposedEdit, workspaceId]);
  const languageFailed = Object.values(slice.languages).some((s) => ["failed", "stopped"].includes(s.state));
  const problems = useProblems(workspaceId, root);
  const runningJobs = Object.values(slice.jobs).filter((job) => job.state === "running");
  const terminalCount = Object.keys(slice.terminals).length;
  const activeWebRun = Object.values(slice.runs).find((run) => run.local_url && ["starting", "running"].includes(run.state));
  // ---- editor plumbing (unchanged safety model) -------------------------
  const markProblems = () => {
    for (const file of retained.values())
      if (file.workspace === workspaceId)
        monaco.editor.setModelMarkers(
          file.model,
          "olive-run",
          diagnostics.current
            .filter((problem) => problem.file === file.path)
            .slice(0, 500)
            .map((problem) => ({
              startLineNumber: Math.max(1, problem.line || 1),
              endLineNumber: Math.max(1, problem.line || 1),
              startColumn: Math.max(1, problem.column || 1),
              endColumn: Math.max(2, (problem.column || 1) + 1),
              message: problem.message,
              severity: problem.severity === "warning" ? monaco.MarkerSeverity.Warning : monaco.MarkerSeverity.Error,
              source: "Run output",
            })),
        );
  };
  useEffect(() => {
    if (!workspaceId) return;
    let live = true;
    const refresh = () =>
      void call<{ problems: typeof diagnostics.current }[]>("studio.diagnostics", { workspace_id: workspaceId })
        .then((records) => {
          if (live) {
            diagnostics.current = records.at(-1)?.problems || [];
            markProblems();
          }
        })
        .catch(report);
    refresh();
    const unsubscribe = window.olive.subscribe((event) => {
      const data = event.data as { workspace_id?: string; state?: string };
      if (event.topic === "run" && data.workspace_id === workspaceId && !["running", "starting", "created"].includes(data.state || ""))
        refresh();
    });
    return () => {
      live = false;
      unsubscribe();
    };
  }, [workspaceId]);
  useEffect(() => {
    // Restore this workspace's own view state rather than resetting it.
    const ui = sessionUi(workspaceId);
    setActive(ui.activePath || lastPaths.get(workspaceId) || "");
    const migrated = migrateDock(ui.dock);
    setDock(migrated.dock);
    setView((migrated.view || ui.view || "explorer") as StudioView);
    setExplorer(ui.explorerOpen);
    setAssistantOpen(ui.assistantOpen);
    setEntries([]);
    setReferences(null);
  }, [workspaceId]);
  // Remember it as it changes, so a later switch back is exact.
  useEffect(() => {
    updateSessionUi(workspaceId, {
      activePath: active,
      dock,
      view,
      explorerOpen: explorer,
      assistantOpen,
    });
  }, [workspaceId, active, dock, view, explorer, assistantOpen]);
  const flushBuffers = async () => {
    for (const file of retained.values())
      if (file.workspace === workspaceId)
        await call("studio.buffer", {
          workspace_id: workspaceId,
          path: file.path,
          text: file.model.getValue(),
          expected_hash: file.hash,
        });
  };
  const refreshTree = useCallback(async () => {
    if (!workspaceId) return;
    const result = await call<{ entries: typeof entries }>("studio.tree", { workspace_id: workspaceId });
    setEntries(result.entries);
  }, [workspaceId]);
  useEffect(() => {
    if (!workspaceId) return;
    let stale = false;
    void call<{ entries: typeof entries }>("studio.tree", { workspace_id: workspaceId })
      .then((v) => {
        if (!stale) setEntries(v.entries);
      })
      .catch(report);
    return () => {
      stale = true;
    };
  }, [workspaceId]);
  useEffect(() => {
    if (!host.current) return;
    const instance = monaco.editor.create(host.current, {
      theme: theme === "light" ? "vs" : "vs-dark",
      automaticLayout: true,
      fontSize: editorPreferences.current.fontSize,
      lineHeight: editorPreferences.current.lineHeight,
      fontFamily: editorPreferences.current.fontFamily,
      // Studio V2 §7: minimap only on wide windows; calm brackets; full line highlight.
      minimap: { enabled: window.innerWidth >= 1600 },
      renderLineHighlight: "all",
      bracketPairColorization: { enabled: false },
      padding: { top: 8 },
      scrollBeyondLastLine: false,
      smoothScrolling: false,
      accessibilitySupport: "on",
      ariaLabel: "Source editor",
      glyphMargin: true,
      lightbulb: { enabled: monaco.editor.ShowLightbulbIconMode.OnCode },
      model: null,
    });
    editor.current = instance;
    decorations.current = instance.createDecorationsCollection();
    const cursorWatch = instance.onDidChangeCursorSelection((event) => {
      const selection = event.selection;
      // Character counts only for single-line selections; nothing is copied out.
      const chars = selection.isEmpty() ? 0 : selection.startLineNumber === selection.endLineNumber ? selection.endColumn - selection.startColumn : 1;
      setCursor({
        line: selection.positionLineNumber,
        column: selection.positionColumn,
        lines: selection.isEmpty() ? 0 : selection.endLineNumber - selection.startLineNumber + 1,
        chars,
      });
    });
    const glyph = instance.onMouseDown((event) => {
      if (event.target.type === monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN && event.target.position) {
        const model = instance.getModel();
        const location = model ? retained.get(current.current) : null;
        if (location && languageFor(location.path)) void debuggerRef.current?.toggleBreakpoint(location.path, event.target.position.lineNumber);
      }
    });
    instance.addAction({
      id: "olive.rename",
      label: "Rename symbol (with preview)",
      keybindings: [monaco.KeyCode.F2],
      contextMenuGroupId: "1_modification",
      contextMenuOrder: 1.1,
      run: async (ed) => {
        const model = ed.getModel();
        const position = ed.getPosition();
        if (!model || !position || !languageFor(retained.get(current.current)?.path || "")) return;
        const prepared = await prepareRename(model, position).catch((error) => {
          report(error);
          return null;
        });
        if (!prepared) return;
        setRenameDraft(prepared.placeholder);
        setRenaming({ position, ...prepared });
      },
    });
    instance.addAction({
      id: "olive.references",
      label: "Find all references (OLIVE)",
      keybindings: [monaco.KeyMod.Shift | monaco.KeyCode.F12],
      contextMenuGroupId: "navigation",
      contextMenuOrder: 1.6,
      run: async (ed) => {
        const model = ed.getModel();
        const position = ed.getPosition();
        if (!model || !position) return;
        const word = model.getWordAtPosition(position)?.word || "symbol";
        try {
          const items = await findReferences(model, position);
          setReferences({ symbol: word, items });
          setDock("references");
        } catch (error) {
          report(error);
        }
      },
    });
    return () => {
      const file = retained.get(current.current);
      if (file) file.view = instance.saveViewState();
      glyph.dispose();
      cursorWatch.dispose();
      decorations.current = null;
      instance.dispose();
      editor.current = null;
    };
  }, [Boolean(workspace)]);
  useEffect(() => {
    if (visible) editor.current?.layout();
  }, [visible]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const tokens = getComputedStyle(document.documentElement);
      const colour = (name: string) => tokens.getPropertyValue(name).trim();
      const hex = (name: string) => colour(name).replace("#", "");
      monaco.editor.defineTheme("olive", {
        base: theme === "light" ? "vs" : "vs-dark",
        inherit: true,
        rules: SYNTAX.map(([token, name, fontStyle]) => ({ token, foreground: hex(name), ...(fontStyle ? { fontStyle } : {}) })),
        colors: {
          "editor.background": colour("--bg-surface"),
          "editor.foreground": colour("--syn-text"),
          "editorLineNumber.foreground": colour("--editor-line"),
          "editorLineNumber.activeForeground": colour("--editor-line-active"),
          "editor.lineHighlightBackground": theme === "light" ? "#171a120a" : "#e2ecc80b",
          "editor.lineHighlightBorder": "#00000000",
          "editor.selectionBackground": theme === "light" ? "#55641e2e" : "#b9c67c38",
          "editor.inactiveSelectionBackground": theme === "light" ? "#55641e1a" : "#b9c67c1f",
          "editorCursor.foreground": colour("--accent-blue"),
          "editorWidget.background": colour("--bg-raised"),
          "editorWidget.border": theme === "light" ? "#171a1233" : "#e2ecc833",
          "editorHoverWidget.background": colour("--bg-raised"),
          "editorHoverWidget.border": theme === "light" ? "#171a1233" : "#e2ecc833",
          "editorSuggestWidget.background": colour("--bg-raised"),
          "editorSuggestWidget.selectedBackground": theme === "light" ? "#55641e1c" : "#b9c67c21",
          "editorError.foreground": colour("--status-error"),
          "editorWarning.foreground": colour("--status-warning"),
          "editorGutter.background": colour("--bg-surface"),
          "editorIndentGuide.background1": theme === "light" ? "#171a1214" : "#e2ecc814",
          "scrollbarSlider.background": theme === "light" ? "#171a1224" : "#e2ecc81f",
          "minimap.background": colour("--bg-surface"),
        },
      });
      monaco.editor.setTheme("olive");
    });
    return () => cancelAnimationFrame(frame);
  }, [theme, Boolean(workspace)]);
  useEffect(() => {
    let live = true;
    const apply = (value: { settings: Record<string, unknown> }) => {
      if (!live) return;
      const size = Number(value.settings.editor_size) || 13;
      editorPreferences.current = {
        fontSize: size,
        lineHeight: Math.round(size * 1.54),
        fontFamily: editorFont(String(value.settings.editor_font || "Consolas")),
        tabSize: Number(value.settings.editor_tab_width) || 4,
      };
      editor.current?.updateOptions(editorPreferences.current);
      for (const file of retained.values()) file.model.updateOptions({ tabSize: editorPreferences.current.tabSize });
    };
    void call<{ settings: Record<string, unknown> }>("data.settings", {}).then(apply).catch(report);
    const unsubscribe = window.olive.subscribe((event) => {
      if (event.topic === "settings") apply(event.data as { settings: Record<string, unknown> });
    });
    return () => {
      live = false;
      unsubscribe();
    };
  }, [theme, Boolean(workspace)]);
  useEffect(() => {
    const instance = editor.current;
    if (!instance) return;
    const previous = retained.get(current.current);
    if (previous) previous.view = instance.saveViewState();
    const file = retained.get(key(active));
    current.current = key(active);
    instance.setModel(file?.model || null);
    file?.model.updateOptions({ tabSize: editorPreferences.current.tabSize });
    if (file?.view) instance.restoreViewState(file.view);
    if (
      document.activeElement === document.body ||
      document.activeElement?.closest(".studio-sidebar,.file-tabs,.monaco-editor,.navigation,.titlebar,.problem-list,.test-list,.reference-list,.palette")
    )
      instance.focus();
  }, [active, workspaceId, Boolean(workspace)]);
  const open = useCallback(
    async (path: string, line?: number, column?: number) => {
      if (!retained.has(key(path))) {
        if (retained.size >= 32) throw new Error("Close a tab before opening more files.");
        const file = await call<FileState>("studio.open", { workspace_id: workspaceId, path });
        const extension = path.split(".").pop();
        const language = LANGUAGE_IDS[extension || ""] || "plaintext";
        const retainedBuffer = discarded.has(key(path)) ? undefined : buffers.find((b) => b.workspace_id === workspaceId && b.path === path);
        const model = monaco.editor.createModel(retainedBuffer?.text ?? file.text, language, modelUri(workspaceId, path));
        const record: OpenFile = {
          path,
          workspace: workspaceId,
          model,
          hash: retainedBuffer?.expected_hash ?? file.loaded_hash,
          saved: file.saved_text,
        };
        retained.set(key(path), record);
        let timer: ReturnType<typeof setTimeout>;
        model.onDidChangeContent(() => {
          render((n) => n + 1);
          clearTimeout(timer);
          timer = setTimeout(() => {
            discarded.delete(record.workspace + ":" + path);
            void call("studio.buffer", {
              workspace_id: record.workspace,
              path,
              text: model.getValue(),
              expected_hash: record.hash,
            }).catch(report);
          }, 300);
        });
        model.onWillDispose(() => clearTimeout(timer));
        // Code intelligence follows the buffer, not the file on disk.
        record.unsync = syncDocument(workspaceId, path, model, report);
        const known = Object.entries(tooling.slice(workspaceId).diagnostics).find(([abs]) => samePath(abs, absolutePath(root, path)));
        if (known) applyDiagnostics(model, known[1]);
      }
      lastPaths.set(workspaceId, path);
      markProblems();
      setActive(path);
      render((n) => n + 1);
      if (line)
        requestAnimationFrame(() => {
          editor.current?.setPosition({ lineNumber: line, column: column || 1 });
          editor.current?.revealLineInCenter(line);
          editor.current?.focus();
        });
    },
    [workspaceId, buffers, report, root],
  );
  const openRef = useRef(open);
  openRef.current = open;
  // Language-server diagnostics become editor markers for open buffers.
  useEffect(() => {
    for (const file of retained.values()) {
      if (file.workspace !== workspaceId || !languageFor(file.path)) continue;
      const entry = Object.entries(slice.diagnostics).find(([abs]) => samePath(abs, absolutePath(root, file.path)));
      applyDiagnostics(file.model, entry ? entry[1] : []);
    }
  }, [slice.diagnostics, workspaceId, root]);
  useEffect(() => {
    registerLanguageProviders({
      openFile: (ws, path, line, column) => (ws === workspaceId ? openRef.current(path, line, column) : Promise.resolve()),
      proposeEdit: (_ws, edit) => setProposedEdit(edit),
      rootFor: (ws) => (ws === workspaceId ? root : ""),
    });
  }, [workspaceId, root]);
  // ---- debugger --------------------------------------------------------
  const debug = useDebugger(workspaceId, root, (path, line) => openRef.current(path, line), report);
  const debuggerRef = useRef(debug);
  debuggerRef.current = debug;
  useEffect(() => {
    const instance = editor.current;
    const collection = decorations.current;
    if (!instance || !collection) return;
    const file = retained.get(key(active));
    if (!file) {
      collection.clear();
      return;
    }
    decorateModel(instance, collection, debug.breakpointsFor(file.path), debug.current && debug.current.path === file.path ? debug.current : null);
  }, [active, debug.breakpoints, debug.current, workspaceId]);
  useEffect(() => {
    if (debug.active && slice.debugEvents.at(-1)?.event === "stopped") showView("debug");
  }, [debug.active, slice.debugEvents, showView]);
  // ---- file operations ---------------------------------------------------
  const save = async (target?: OpenFile) => {
    const file = target || retained.get(key(active));
    if (!file || busy) return;
    setBusy(true);
    try {
      const state = await call<FileState>("studio.save", {
        workspace_id: workspaceId,
        path: file.path,
        text: file.model.getValue(),
        expected_hash: file.hash,
      });
      file.hash = state.loaded_hash;
      file.saved = state.saved_text;
      render((n) => n + 1);
      setSaveStatus("Saved · hash checked");
      documentSaved(workspaceId, file.path);
      return true;
    } catch (e) {
      report(e);
      setSaveStatus("Save blocked · editor changes retained");
    } finally {
      setBusy(false);
    }
  };
  const closeFile = async (file: OpenFile) => {
    await call("studio.discard_buffer", { workspace_id: file.workspace, path: file.path });
    file.unsync?.();
    file.model.dispose();
    retained.delete(file.workspace + ":" + file.path);
    discarded.add(file.workspace + ":" + file.path);
    if (active === file.path) {
      const next = [...retained.values()].find((item) => item.workspace === workspaceId)?.path || "";
      setActive(next);
      lastPaths.set(workspaceId, next);
    }
    setClosing(null);
    render((n) => n + 1);
  };
  const saveAll = async () => {
    for (const file of retained.values())
      if (file.workspace === workspaceId && file.saved !== file.model.getValue()) if (!(await save(file))) break;
  };
  const compare = async () => {
    const file = retained.get(key(active));
    if (!file) return;
    const disk = await call<{ disk_text: string; disk_hash: string }>("studio.compare", { workspace_id: workspaceId, path: active });
    setComparison({ ...disk, file });
  };
  const reconcile = async () => {
    if (!comparison) return;
    const file = comparison.file;
    await call("studio.rebase", { workspace_id: file.workspace, path: file.path, expected_hash: file.hash, disk_hash: comparison.disk_hash });
    file.hash = comparison.disk_hash;
    file.saved = comparison.disk_text;
    setComparison(null);
    render((n) => n + 1);
    setSaveStatus("Comparison accepted · save your unsaved editor changes");
  };
  const validate = async (review = false) => {
    setBusy(true);
    setDock("output");
    try {
      await call("studio.validate", { workspace_id: workspaceId, review });
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };
  // ---- tooling actions --------------------------------------------------
  const runJob = async (label: string, work: () => Promise<unknown>, tab: DockTab = "output") => {
    setBusy(true);
    setDock(tab);
    try {
      await work();
      setSaveStatus(label);
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };
  const build = (mode: string, target?: string) =>
    void runJob(`${mode[0].toUpperCase()}${mode.slice(1)} started`, () =>
      call("project.build", { workspace_id: workspaceId, mode, ...(target ? { target } : {}) }),
    );
  const runProgram = () =>
    void runJob(
      "Run started",
      () =>
        isDotnet
          ? call("project.run", { workspace_id: workspaceId })
          : call<{ session_id: string }>("studio.run", { workspace_id: workspaceId }),
      "terminal",
    );
  // The toolbar Test runs the reviewed validation (approval-bound, streamed to
  // Output). The Tests dock offers the structured runner (discover, run
  // all/failed/selected, click-to-source).
  const runTests = () => void validate();
  const startDebug = () => {
    showView("debug");
    void runJob(
      "Debugger starting",
      async () => {
        await saveAll();
        await debug.launch();
      },
      "console",
    );
  };
  // Builds that fail land the person in Problems, not in a log they have to scroll.
  const lastJobRef = useRef<string>("");
  useEffect(() => {
    const finished = Object.values(slice.jobs)
      .filter((job) => job.state !== "running" && job.kind === "build")
      .sort((a, b) => (a.ended_at || 0) - (b.ended_at || 0))
      .at(-1);
    if (finished && finished.id !== lastJobRef.current) {
      lastJobRef.current = finished.id;
      if (finished.state === "failed") setDock("problems");
    }
  }, [slice.jobs]);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (!visible || event.defaultPrevented) return;
      const ctrl = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      // Keys typed into the native terminal belong to the shell (Ctrl+B,
      // Ctrl+J, F-keys…). Only the terminal toggles themselves are Studio's.
      const inTerminal = Boolean((event.target as HTMLElement | null)?.closest?.(".terminal-view"));
      if (ctrl && event.key === "`") {
        event.preventDefault();
        if (event.shiftKey) {
          setDock("terminal");
          setTerminalRequest((value) => value + 1);
        } else setDock((value) => (value === "terminal" ? "" : "terminal"));
        return;
      }
      if (inTerminal) return;
      if (ctrl && !event.shiftKey && !event.altKey && key === "s") {
        event.preventDefault();
        void save();
      } else if (ctrl && event.shiftKey && key === "s") {
        event.preventDefault();
        void saveAll();
      } else if (ctrl && event.shiftKey && key === "b" && isDotnet) {
        event.preventDefault();
        build("build");
      } else if (event.key === "F5" && ctrl && !event.shiftKey) {
        event.preventDefault();
        if (!activeRun && !busy) runProgram();
      } else if (event.key === "F5" && !ctrl) {
        event.preventDefault();
        if (event.shiftKey) void debug.stop();
        else if (debug.active?.suspended) void debug.step("continue");
        else if (!debug.active && (isDotnet || scan?.kind === "python")) startDebug();
      } else if (event.key === "F9" && !ctrl) {
        const position = editor.current?.getPosition();
        const file = retained.get(workspaceId + ":" + active);
        if (position && file && languageFor(file.path) && editor.current?.hasTextFocus()) {
          event.preventDefault();
          void debug.toggleBreakpoint(file.path, position.lineNumber);
        }
      } else if (event.key === "F10" && debug.active?.suspended) {
        event.preventDefault();
        void debug.step("next");
      } else if (event.key === "F11" && debug.active?.suspended) {
        event.preventDefault();
        void debug.step(event.shiftKey ? "stepOut" : "stepIn");
      } else if (ctrl && event.altKey && key === "n") {
        event.preventDefault();
        setWizard(true);
      } else if (ctrl && event.altKey && key === "b") {
        event.preventDefault();
        setAssistantOpen((value) => !value);
      } else if (ctrl && event.altKey && key === "i") {
        event.preventDefault();
        askAssistant("Explain the selected code and anything surprising about it.", { selection: true, file: true });
      } else if (ctrl && !event.shiftKey && !event.altKey && key === "b") {
        event.preventDefault();
        setExplorer((value) => !value);
      } else if (ctrl && !event.shiftKey && !event.altKey && key === "j") {
        event.preventDefault();
        setDock((value) => (value ? "" : lastDock.current || "problems"));
      } else if (ctrl && event.shiftKey && key === "e") {
        event.preventDefault();
        showView("explorer");
      } else if (ctrl && event.shiftKey && key === "f") {
        event.preventDefault();
        showView("search");
        setSearchSignal((value) => value + 1);
      } else if (ctrl && event.shiftKey && key === "g") {
        event.preventDefault();
        showView("scm");
      } else if (ctrl && event.shiftKey && key === "d") {
        event.preventDefault();
        showView("debug");
      } else if (ctrl && event.shiftKey && key === "m") {
        event.preventDefault();
        setDock((value) => (value === "problems" ? "" : "problems"));
      } else if (ctrl && !event.shiftKey && !event.altKey && key === "p") {
        event.preventDefault();
        window.dispatchEvent(new CustomEvent("olive:palette", { detail: "" }));
      } else if (ctrl && !event.shiftKey && !event.altKey && key === "t") {
        event.preventDefault();
        window.dispatchEvent(new CustomEvent("olive:palette", { detail: "#" }));
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  });
  // Closing a workspace names what would be lost first; nothing is discarded
  // until the person chooses, and running work is stopped explicitly.
  const dropWorkspace = useCallback(
    (id: string) => {
      for (const [key, file] of [...retained.entries()]) {
        if (file.workspace !== id) continue;
        file.unsync?.();
        file.model.dispose();
        retained.delete(key);
      }
      lastPaths.delete(id);
      forgetSession(id);
      setClosingWorkspace(null);
      setOpenIds((current) => {
        const next = current.filter((item) => item !== id);
        if (id === workspaceId) setWorkspaceId(next[next.length - 1] || "");
        return next;
      });
    },
    [workspaceId, setWorkspaceId],
  );
  const requestCloseWorkspace = (id: string) => {
    const slice = tooling.slice(id);
    const dirty = [...retained.values()].filter(
      (f) => f.workspace === id && f.saved !== f.model.getValue(),
    ).length;
    const running: string[] = [];
    const terminals = Object.keys(slice.terminals).length;
    if (terminals) running.push(`${terminals} terminal ${terminals === 1 ? "session" : "sessions"} will be closed`);
    if (slice.debug && ["starting", "running", "suspended"].includes(slice.debug.state))
      running.push("A debug session will be stopped");
    const jobs = Object.values(slice.jobs).filter((job) => job.state === "running").length;
    if (jobs) running.push(`${jobs} running ${jobs === 1 ? "job" : "jobs"} will be cancelled`);
    if (!dirty && running.length === 0) {
      dropWorkspace(id);
      return;
    }
    const title = workspaces.find((w) => w.id === id)?.title || "This workspace";
    setSwitching(false);
    setClosingWorkspace({ id, title, dirty, running });
  };
  const finishCloseWorkspace = async (id: string, saveFirst: boolean) => {
    try {
      if (saveFirst) {
        for (const file of [...retained.values()]) {
          if (file.workspace !== id || file.saved === file.model.getValue()) continue;
          const state = await call<FileState>("studio.save", {
            workspace_id: file.workspace,
            path: file.path,
            text: file.model.getValue(),
            expected_hash: file.hash,
          });
          file.hash = state.loaded_hash;
          file.saved = state.saved_text;
        }
      }
      const slice = tooling.slice(id);
      for (const session of Object.values(slice.terminals))
        await call("terminal.close", { session_id: session.session_id }).catch(() => undefined);
      if (slice.debug && ["starting", "running", "suspended"].includes(slice.debug.state))
        await call("dap.stop", { session_id: slice.debug.session_id }).catch(() => undefined);
      for (const job of Object.values(slice.jobs))
        if (job.state === "running")
          await call("project.cancel", { job_id: job.id }).catch(() => undefined);
      dropWorkspace(id);
    } catch (e) {
      report(e);
    }
  };
  const selectionText = () => {
    const editorSelection = editor.current?.getSelection();
    return editorSelection ? editor.current?.getModel()?.getValueInRange(editorSelection).slice(0, 12000) || "" : "";
  };
  const askAssistant = (text: string, context?: AssistantSeed["context"]) => {
    setAssistantOpen(true);
    setAssistantSeed({ text, revision: Date.now(), context });
  };
  const openModelFor = async (path: string) => {
    await openRef.current(path);
    const file = retained.get(key(path));
    if (!file) throw new Error(`Could not open ${path}`);
    return file.model;
  };
  // ---- V2 derived state ------------------------------------------------------
  const stopTarget = validation ? "tests" : activeCommand ? "command" : activeRun ? "program" : debug.active ? "debugger" : runningJobs.length ? "job" : "";
  const stopLabel =
    validation ? "Stop tests" : activeCommand ? "Stop command" : debug.active && !activeRun ? "Stop debugging" : runningJobs.length && !activeRun ? "Stop job" : "Stop program";
  const stopActive = () =>
    validation
      ? void call("studio.cancel_validation", { validation_id: validation.id }).catch(report)
      : activeCommand
        ? void call("studio.cancel_command", { command_id: activeCommand.id }).catch(report)
        : activeRun
          ? void call("studio.stop", { session_id: activeRun.id }).catch(report)
          : debug.active
            ? void debug.stop().catch(report)
            : runningJobs[0] && void call("project.cancel", { job_id: runningJobs[0].id }).catch(report);
  const explainError = () => {
    const first = problems.find((p) => p.severity === "error") || problems[0];
    if (!first) return;
    askAssistant(`Explain this error and how to fix it:\n${first.file}:${first.line} ${first.message}`, { problems: true, file: true });
    if (first.file) void open(first.file, first.line || undefined).catch(report);
  };
  const git = useGitStatus(workspaceId, Boolean(workspace) && visible, Boolean(workspace?.git_repository));
  // Outline and breadcrumbs: documentSymbol from the running language server
  // for the active file, re-read shortly after edits. Files without a
  // language server simply have no outline.
  useEffect(() => {
    const file = retained.get(workspaceId + ":" + active);
    setSymbols([]);
    // Only ask a language server that reports ready: requests to a server that
    // is starting or stopped would only fail.
    const language = file ? languageFor(file.path) : "";
    if (!file || !language || slice.languages[language]?.state !== "ready") return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () =>
      void lspRequest<unknown[]>(workspaceId, "documentSymbol", file.path, {})
        .then((value) => {
          if (live) setSymbols(normaliseSymbols(value));
        })
        .catch(() => undefined);
    load();
    const change = file.model.onDidChangeContent(() => {
      clearTimeout(timer);
      timer = setTimeout(load, 1200);
    });
    return () => {
      live = false;
      clearTimeout(timer);
      change.dispose();
    };
  }, [active, workspaceId, Object.values(slice.languages).map((l) => `${l.language}:${l.state}`).join(",")]);
  const [newFileRequest, setNewFileRequest] = useState(0);
  const runEditorAction = (id: string) => {
    editor.current?.focus();
    void editor.current?.getAction(id)?.run();
  };
  // Only language servers that report ready are asked anything.
  const languageNames = Object.values(slice.languages)
    .filter((session) => session.state === "ready")
    .map((session) => session.language);
  const failedTests = (slice.tests?.results || []).filter((item) => item.state === "failed");
  const paletteOpen = (prefix: string) => window.dispatchEvent(new CustomEvent("olive:palette", { detail: prefix }));
  const studioCommands = (): PaletteItem[] => {
    if (!workspace) return [];
    const file = retained.get(workspaceId + ":" + active);
    const code = Boolean(file && languageFor(file.path) && languageNames.length);
    const debuggable = isDotnet || scan?.kind === "python";
    const items: (PaletteItem | false)[] = [
      { id: "file.save", title: "File: Save", group: "File", keys: "Ctrl+S", run: () => void save(), unavailable: active ? undefined : "No file is open" },
      { id: "file.saveAll", title: "File: Save All", group: "File", keys: "Ctrl+Shift+S", run: () => void saveAll() },
      { id: "file.compare", title: "File: Compare with Saved", group: "File", run: () => void compare().catch(report), unavailable: active ? undefined : "No file is open" },
      { id: "file.new", title: "File: New File…", group: "File", run: () => setNewFileRequest((value) => value + 1) },
      { id: "file.newProject", title: "File: New Project…", group: "File", keys: "Ctrl+Alt+N", run: () => setWizard(true) },
      { id: "file.openWorkspace", title: "File: Open Workspace…", group: "File", run: () => void window.olive.openWorkspace().then((w) => { if (w) openWorkspace(w.id); }).catch(report) },
      { id: "file.switchWorkspace", title: "File: Switch Workspace…", group: "File", run: () => setSwitching(true) },
      { id: "file.closeWorkspace", title: "File: Close Workspace", group: "File", run: () => requestCloseWorkspace(workspaceId) },
      { id: "file.ide", title: "File: Open in Installed IDE (review)", group: "File", run: () => void call("studio.open_ide", { workspace_id: workspaceId }).catch(report) },
      { id: "run.run", title: "Run: Run Project", group: "Run", keys: "Ctrl+F5", run: runProgram, unavailable: activeRun ? "A program is already running" : undefined },
      debuggable && { id: "run.debug", title: "Run: Start Debugging", group: "Run", keys: "F5", run: startDebug, unavailable: debug.active ? "A debug session is running" : undefined },
      Boolean(stopTarget) && { id: "run.stop", title: `Run: Stop ${stopTarget}`, group: "Run", keys: stopTarget === "debugger" ? "Shift+F5" : undefined, run: stopActive },
      debuggable && code && { id: "run.breakpoint", title: "Run: Toggle Breakpoint", group: "Run", keys: "F9", run: () => { const position = editor.current?.getPosition(); if (file && position) void debug.toggleBreakpoint(file.path, position.lineNumber); } },
      isDotnet && { id: "build.build", title: "Build: Build Solution", group: "Build", keys: "Ctrl+Shift+B", run: () => build("build") },
      isDotnet && { id: "build.rebuild", title: "Build: Rebuild Solution", group: "Build", run: () => build("rebuild") },
      isDotnet && { id: "build.clean", title: "Build: Clean Solution", group: "Build", run: () => build("clean") },
      isDotnet && { id: "build.restore", title: "Build: Restore Packages", group: "Build", run: () => build("restore") },
      structuredTests && { id: "test.all", title: "Test: Run All Tests", group: "Test", run: () => { showView("testing"); void call("project.test", { workspace_id: workspaceId, filters: [], list_only: false }).catch(report); } },
      structuredTests && failedTests.length > 0 && { id: "test.failed", title: "Test: Run Failed Tests", group: "Test", run: () => { showView("testing"); void call("project.test", { workspace_id: workspaceId, filters: failedTests.map((t) => t.full_name), list_only: false }).catch(report); } },
      structuredTests && { id: "test.discover", title: "Test: Discover Tests", group: "Test", run: () => { showView("testing"); void call("project.test", { workspace_id: workspaceId, filters: [], list_only: true }).catch(report); } },
      { id: "test.review", title: "Test: Review Test Commands…", group: "Test", run: () => void validate(true) },
      { id: "git.refresh", title: "Git: Refresh Status", group: "Git", run: () => { showView("scm"); void git.refresh(); } },
      Boolean(active) && { id: "git.stage", title: "Git: Stage Current File (review)", group: "Git", run: () => void call("studio.git", { workspace_id: workspaceId, action: "add", files: [active] }).then(git.refresh).catch(report) },
      { id: "git.commit", title: "Git: Commit Staged…", group: "Git", run: () => showView("scm") },
      { id: "git.branch", title: "Git: Create or Switch Branch…", group: "Git", run: () => showView("scm") },
      { id: "terminal.new", title: "Terminal: New Terminal", group: "Terminal", keys: "Ctrl+Shift+`", run: () => { setDock("terminal"); setTerminalRequest((value) => value + 1); } },
      { id: "terminal.focus", title: "Terminal: Focus Terminal", group: "Terminal", keys: "Ctrl+`", run: () => setDock("terminal") },
      { id: "goto.file", title: "Go to File…", group: "Go to", keys: "Ctrl+P", run: () => setTimeout(() => paletteOpen(""), 0) },
      languageNames.length > 0 && { id: "goto.workspaceSymbol", title: "Go to Symbol in Workspace…", group: "Go to", keys: "Ctrl+T", run: () => setTimeout(() => paletteOpen("#"), 0) },
      code && { id: "goto.symbol", title: "Go to Symbol in File…", group: "Go to", run: () => setTimeout(() => paletteOpen("@"), 0) },
      Boolean(active) && { id: "goto.line", title: "Go to Line…", group: "Go to", keys: "Ctrl+G", run: () => setTimeout(() => paletteOpen(":"), 0) },
      code && { id: "lang.rename", title: "Rename Symbol", group: "Code", keys: "F2", run: () => runEditorAction("olive.rename") },
      code && { id: "lang.references", title: "Find All References", group: "Code", keys: "Shift+F12", run: () => runEditorAction("olive.references") },
      code && { id: "lang.format", title: "Format Document", group: "Code", keys: "Shift+Alt+F", run: () => runEditorAction("editor.action.formatDocument") },
      code && { id: "lang.quickfix", title: "Quick Fix…", group: "Code", keys: "Ctrl+.", run: () => runEditorAction("editor.action.quickFix") },
      languageNames.length > 0 && { id: "lang.restart", title: "Restart Code Intelligence", group: "Code", run: () => { for (const language of languageNames) void call("lsp.restart", { workspace_id: workspaceId, language }).catch(report); } },
      { id: "search.files", title: "Search: Find in Files", group: "Search", keys: "Ctrl+Shift+F", run: () => { showView("search"); setSearchSignal((value) => value + 1); } },
      { id: "view.sidebar", title: "View: Toggle Primary Side Bar", group: "View", keys: "Ctrl+B", run: () => setExplorer((value) => !value) },
      { id: "view.panel", title: "View: Toggle Panel", group: "View", keys: "Ctrl+J", run: () => setDock((value) => (value ? "" : lastDock.current || "problems")) },
      { id: "view.olive", title: "View: Toggle OLIVE", group: "View", keys: "Ctrl+Alt+B", run: () => setAssistantOpen((value) => !value) },
      { id: "view.explorer", title: "View: Show Explorer", group: "View", keys: "Ctrl+Shift+E", run: () => showView("explorer") },
      { id: "view.scm", title: "View: Show Source Control", group: "View", keys: "Ctrl+Shift+G", run: () => showView("scm") },
      { id: "view.debug", title: "View: Show Run and Debug", group: "View", keys: "Ctrl+Shift+D", run: () => showView("debug") },
      { id: "view.testing", title: "View: Show Testing", group: "View", run: () => showView("testing") },
      { id: "view.problems", title: "View: Show Problems", group: "View", keys: "Ctrl+Shift+M", run: () => setDock("problems") },
      { id: "view.output", title: "View: Show Output", group: "View", run: () => setDock("output") },
      { id: "view.terminal", title: "View: Show Terminal", group: "View", keys: "Ctrl+`", run: () => setDock("terminal") },
      { id: "view.console", title: "View: Show Debug console", group: "View", run: () => setDock("console") },
      { id: "olive.selection", title: "OLIVE: Ask About Selection", group: "OLIVE", keys: "Ctrl+Alt+I", run: () => askAssistant("Explain the selected code and anything surprising about it.", { selection: true, file: true }) },
      problems.length > 0 && { id: "olive.error", title: "OLIVE: Explain Error", group: "OLIVE", run: () => explainError() },
      { id: "olive.review", title: "OLIVE: Review Changes", group: "OLIVE", run: () => askAssistant("Review the uncommitted changes for defects and risks.", { changes: true }) },
      failedTests.length > 0 && { id: "olive.fix", title: "OLIVE: Suggest Fix for Failing Test", group: "OLIVE", run: () => askAssistant("Suggest a fix for this failing test. Explain the cause first; propose a change I can review.", { test: true, file: true }) },
      Boolean(active) && { id: "olive.tests", title: "OLIVE: Generate Tests for File", group: "OLIVE", run: () => askAssistant("Write unit tests for this file. Propose them as a change I can review; do not assume anything is saved.", { file: true }) },
      { id: "remote.open", title: "Remote Studio: Open Shared Workspace…", group: "Remote Studio", run: openRemote },
    ];
    return items.filter(Boolean) as PaletteItem[];
  };
  usePaletteProvider("studio.commands", ">", studioCommands, visible && Boolean(workspace), 5);
  usePaletteProvider(
    "studio.files",
    "",
    (query) => {
      if (!workspace) return [];
      const files = query
        ? entries.filter((e) => !e.directory)
        : [...retained.values()].filter((f) => f.workspace === workspaceId).map((f) => ({ path: f.path, directory: false }));
      return files.slice(0, 2000).map((entry) => ({
        id: `file:${entry.path}`,
        title: entry.path.split("/").pop() || entry.path,
        detail: entry.path.split("/").slice(0, -1).join("/"),
        aliases: [entry.path],
        group: query ? "Files" : "Open editors",
        run: () => void open(entry.path).catch(report),
      }));
    },
    visible && Boolean(workspace),
    1,
  );
  usePaletteProvider(
    "studio.line",
    ":",
    (query) => {
      const model = editor.current?.getModel();
      const line = Number.parseInt(query, 10);
      if (!model) return [];
      if (!query) return [{ id: "line:hint", title: `Type a line number between 1 and ${model.getLineCount()}`, group: "Go to line", unavailable: "Type a number", run: () => undefined }];
      if (!Number.isFinite(line) || line < 1 || line > model.getLineCount()) return [];
      return [{ id: `line:${line}`, title: `Go to line ${line}`, group: "Go to line", run: () => { requestAnimationFrame(() => { editor.current?.setPosition({ lineNumber: line, column: 1 }); editor.current?.revealLineInCenter(line); editor.current?.focus(); }); } }];
    },
    visible && Boolean(workspace),
  );
  usePaletteProvider(
    "studio.symbols",
    "@",
    (query) => {
      const flat: OutlineSymbol[] = [];
      const walk = (items: OutlineSymbol[]) => items.forEach((item) => { flat.push(item); walk(item.children); });
      walk(symbols);
      return flat
        .filter((item) => !query || item.name.toLowerCase().includes(query.toLowerCase()))
        .map((item, index) => ({
          id: `sym:${index}:${item.name}`,
          title: item.name,
          detail: `${symbolTag(item.kind).label} · line ${item.line}`,
          group: "Symbols in file",
          run: () => { requestAnimationFrame(() => { editor.current?.setPosition({ lineNumber: item.line, column: 1 }); editor.current?.revealLineInCenter(item.line); editor.current?.focus(); }); },
        }));
    },
    visible && Boolean(workspace),
  );
  usePaletteProvider(
    "studio.workspaceSymbols",
    "#",
    async (query) => {
      if (!languageNames.length || query.length < 2) return [];
      const items = await workspaceSymbols(workspaceId, languageNames[0], query);
      return items.slice(0, 60).map((item, index) => {
        const path = relativePath(root, item.path);
        return {
          id: `ws-sym:${index}`,
          title: item.name,
          detail: `${item.containerName ? `${item.containerName} · ` : ""}${path}:${item.range.start.line + 1}`,
          group: "Workspace symbols",
          run: () => void open(path, item.range.start.line + 1).catch(report),
        };
      });
    },
    visible && Boolean(workspace),
  );
  const iconOnly = layout.iconOnlyRun;
  const locationControls = (
    <TitleBarPortal slot="context">
      {location}
      {workspace && (
        <button
          className="tb-workspace workspace-selector"
          aria-label={`Workspace: ${workspace.title}. Switch workspace`}
          aria-haspopup="dialog"
          title={`${workspace.title} · switch workspace`}
          onClick={() => setSwitching(true)}
        >
          <FolderOpen size={13} aria-hidden="true" />
          <span className="workspace-name">{workspace.title}</span>
          {openIds.length > 1 && <span className="count" data-tone="neutral" aria-hidden="true">{openIds.length}</span>}
          <ChevronsUpDown size={12} aria-hidden="true" />
        </button>
      )}
    </TitleBarPortal>
  );
  if (!workspace)
    return (
      <div className="studio studio-v2 studio-empty-shell">
        {visible && locationControls}
        <div className="studio-empty">
          <div className="studio-empty-head">
            <OliveMark size={20} />
            <h1>Studio</h1>
          </div>
          <h2 className="studio-empty-tagline">Your next idea starts here.</h2>
          <div className="studio-empty-columns">
            <section aria-label="Start">
              <h3>Start</h3>
              <button
                className="studio-start-row"
                aria-label="Open Workspace"
                onClick={() =>
                  void window.olive
                    .openWorkspace()
                    .then((w) => {
                      if (w) openWorkspace(w.id);
                    })
                    .catch(report)
                }
              >
                <FolderOpen size={15} aria-hidden="true" />
                <span>Open folder…</span>
              </button>
              <button className="studio-start-row" aria-label="New project" onClick={() => setWizard(true)}>
                <FilePlus2 size={15} aria-hidden="true" />
                <span>New project…</span>
                <kbd className="kbd">Ctrl+Alt+N</kbd>
              </button>
              <button className="studio-start-row" onClick={openRemote}>
                <MonitorSmartphone size={15} aria-hidden="true" />
                <span>Open a shared workspace on a paired device…</span>
              </button>
            </section>
            <section aria-label="Recent">
              <h3>Recent</h3>
              {workspaces.length === 0 && <p className="side-note">No approved folders yet.</p>}
              <div className="studio-recent">
                {workspaces.map((w) => (
                  <button className="studio-start-row" key={w.id} aria-label={w.title} title={w.title} onClick={() => openWorkspace(w.id)}>
                    <FolderOpen size={15} aria-hidden="true" />
                    <span>{w.title}</span>
                    <small>approved folder</small>
                  </button>
                ))}
              </div>
            </section>
          </div>
          <p className="side-note">Studio only opens folders you have approved.</p>
        </div>
        <NewProjectWizard open={wizard} onOpenChange={setWizard} workspaceId={workspaceId} onCreated={(created) => openWorkspace(created.id)} report={report} />
      </div>
    );
  const openFiles = [...retained.values()].filter((f) => f.workspace === workspaceId);
  const dirtyFiles = openFiles.filter((f) => f.saved !== f.model.getValue());
  const dirtyCount = dirtyFiles.length;
  const debugState = debug.status?.state || "";
  const counts = problemCounts(problems);
  const treeDecorations = {
    git: gitDecorations(git.status?.entries || []),
    problems: problemsByFile(problems),
    dirty: new Set(dirtyFiles.map((f) => f.path)),
  };
  const activeFile = retained.get(workspaceId + ":" + active);
  const model = activeFile?.model;
  const code = Boolean(activeFile && languageFor(activeFile.path));
  const breadcrumbSymbols = symbolPath(symbols, cursor.line);
  const tabs = panelTabs(false, {
    web: Boolean(activeWebRun || Object.values(slice.runs).some((run) => run.local_url)),
    references: Boolean(references),
  });
  const panelTab: DockTab = dock && tabs.includes(dock) ? dock : "problems";
  const sidebarWidth = sizes.explorer || layout.sidebarDefault;
  const assistantWidth = sizes.assistant || layout.assistantDefault;
  const docked = assistantDocks(width, explorer && !layout.sidebarOverlay ? sidebarWidth : 0, assistantWidth);
  const availability = activityAvailability(false);
  const scmCount = (git.status?.entries || []).length;
  const langState = languageServerLabel(Object.values(slice.languages));
  const runningText = activeRun
    ? "Running program"
    : validation
      ? "Running tests"
      : runningJobs[0]
        ? `${runningJobs[0].label || "Job"} running`
        : "";
  const launchable = isDotnet
    ? `${scan?.projects.find((p) => p.path.toLowerCase() === scan.run_configuration.startup_project.toLowerCase())?.name || "Startup project"} · netcoredbg`
    : scan?.kind === "python"
      ? `Python: ${scan.run_configuration.program || "main.py"} · debugpy`
      : "";
  const startSidebarDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const start = sidebarWidth;
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    const move = (e: PointerEvent) => setSize("explorer", start + (e.clientX - startX));
    const stop = () => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("pointerup", stop);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", stop);
  };
  const startAssistantDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const start = assistantWidth;
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    const move = (e: PointerEvent) => setSize("assistant", start - (e.clientX - startX));
    const stop = () => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("pointerup", stop);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", stop);
  };
  const section = (open: boolean, toggle: () => void, title: string, actions?: ReactNode, label?: string) => (
    <div className="side-section-head">
      <button className="side-section-toggle" aria-expanded={open} aria-label={label} onClick={toggle}>
        {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
        <span>{title}</span>
      </button>
      {actions}
    </div>
  );
  const renderOutline = (items: OutlineSymbol[], depth = 0): ReactNode =>
    items.map((item, index) => (
      <li key={`${depth}:${index}:${item.name}`}>
        <button
          className="outline-row"
          style={{ paddingLeft: 10 + depth * 12 }}
          title={`${symbolTag(item.kind).label} · line ${item.line}`}
          onClick={() => {
            editor.current?.setPosition({ lineNumber: item.line, column: 1 });
            editor.current?.revealLineInCenter(item.line);
            editor.current?.focus();
          }}
        >
          <span className="symbol-tag" data-kind={symbolTag(item.kind).tag} aria-hidden="true">{symbolTag(item.kind).tag}</span>
          <span className="scm-name">{item.name}</span>
          <span className="scm-folder">{item.line}</span>
        </button>
        {item.children.length > 0 && <ul>{renderOutline(item.children, depth + 1)}</ul>}
      </li>
    ));
  return (
    <div
      className="studio studio-v2"
      data-dock={dock || undefined}
      data-explorer={explorer}
      data-assistant={assistantOpen}
      data-sidebar-overlay={layout.sidebarOverlay || undefined}
    >
      {visible && locationControls}
      {visible && (
        <TitleBarPortal slot="actions">
          <div className="studio-run" role="group" aria-label="Run controls" data-icon-only={iconOnly || undefined}>
            {isDotnet && scan ? (
              <>
                <select
                  className="run-select"
                  aria-label="Startup project"
                  title="Startup project"
                  value={scan.run_configuration.startup_project}
                  onChange={(e) =>
                    void call("project.config_save", { workspace_id: workspaceId, config: { ...scan.run_configuration, startup_project: e.target.value, launch_profile: "" } })
                      .then(rescan)
                      .catch(report)
                  }
                >
                  {!scan.run_configuration.startup_project && <option value="">Startup project…</option>}
                  {scan.projects
                    .filter((p) => p.is_executable && !p.is_test)
                    .map((p) => (
                      <option key={p.path} value={p.path}>
                        {p.name}
                      </option>
                    ))}
                </select>
                <select
                  className="run-select"
                  aria-label="Build configuration"
                  title="Build configuration"
                  value={scan.run_configuration.configuration}
                  onChange={(e) =>
                    void call("project.config_save", { workspace_id: workspaceId, config: { ...scan.run_configuration, configuration: e.target.value } })
                      .then(rescan)
                      .catch(report)
                  }
                >
                  <option value="Debug">Debug</option>
                  <option value="Release">Release</option>
                </select>
                <button className="tb-run" aria-label="Build" onClick={() => build("build")} disabled={busy} title="Build the solution or startup project (Ctrl+Shift+B)">
                  <Hammer size={14} aria-hidden="true" />
                  <span className="tb-label">Build</span>
                </button>
              </>
            ) : scan?.kind === "python" ? (
              <span className="run-config" title="Run configuration (Workspace actions › Run configuration)">
                <FileCode2 size={13} aria-hidden="true" />
                {scan.run_configuration.program || "main.py"} · {runtimeLabel("python", scan.tooling.python.version)}
              </span>
            ) : null}
            <button className="tb-run" aria-label="Run" title="Run the project in the terminal (Ctrl+F5)" onClick={runProgram} disabled={busy || Boolean(activeRun)}>
              <Play size={14} aria-hidden="true" />
              <span className="tb-label">Run</span>
            </button>
            {(isDotnet || scan?.kind === "python") && (
              <button className="tb-run" aria-label="Debug" title="Start debugging (F5)" onClick={startDebug} disabled={busy || Boolean(debug.active)}>
                <Bug size={14} aria-hidden="true" />
                <span className="tb-label">Debug</span>
              </button>
            )}
            <button className="tb-run" aria-label="Test" onClick={runTests} disabled={busy} title={structuredTests ? "Run the tests (reviewed command)" : "Run the detected tests"}>
              <FlaskConical size={14} aria-hidden="true" />
              <span className="tb-label">Test</span>
            </button>
            {stopTarget && (
              <button
                className="tb-run tb-stop"
                aria-label={stopLabel}
                title={stopLabel}
                disabled={validation?.state === "cancelling" || activeCommand?.commandState === "cancelling"}
                onClick={stopActive}
              >
                <Square size={12} aria-hidden="true" />
                <span className="tb-label">{validation?.state === "cancelling" || activeCommand?.commandState === "cancelling" ? "Stopping…" : "Stop"}</span>
              </button>
            )}
          </div>
          <button
            className={`tb-run tb-olive ${assistantOpen ? "selected" : ""}`}
            aria-label="Ask OLIVE"
            aria-pressed={assistantOpen}
            title={assistantOpen ? "Hide OLIVE (drafts are kept) · Ctrl+Alt+B" : "Ask OLIVE about this workspace · Ctrl+Alt+B"}
            onClick={() => setAssistantOpen((value) => !value)}
          >
            <OliveMark size={12} />
            <span className="tb-label">OLIVE</span>
          </button>
        </TitleBarPortal>
      )}
      <div className="studio-body">
        <ActivityBar
          view={view}
          sidebarOpen={explorer}
          select={(next) => {
            if (explorer && view === next) setExplorer(false);
            else showView(next);
          }}
          availability={availability}
          badges={{
            scm: scmCount ? { count: scmCount, tone: "info", spoken: `${scmCount} changed ${scmCount === 1 ? "file" : "files"}` } : undefined,
            debug: debug.active?.suspended ? { text: "‖", tone: "warning", spoken: "paused" } : undefined,
            testing: slice.tests?.summary.failed ? { count: slice.tests.summary.failed, tone: "error", spoken: `${slice.tests.summary.failed} failed` } : undefined,
          }}
          openSettings={openSettings}
        />
        {explorer && layout.sidebarOverlay && <div className="studio-sidebar-scrim" aria-hidden="true" onClick={() => setExplorer(false)} />}
        <aside className="studio-sidebar explorer" hidden={!explorer} aria-label="Files and project" style={{ width: sidebarWidth }}>
          {view === "explorer" && (
            <div className="sidebar-view explorer-view">
              <div className="side-head">
                <h2>Explorer</h2>
                <button className="icon-button" aria-label="New project" title="New project (Ctrl+Alt+N)" onClick={() => setWizard(true)}>
                  <FilePlus2 size={14} aria-hidden="true" />
                </button>
              </div>
              <div className="side-scroll">
                <div className="side-section">
                  {section(openEditorsOpen, () => setOpenEditorsOpen((v) => !v), "Open editors")}
                  {openEditorsOpen && (
                    <ul className="open-editors" aria-label="Open editors">
                      {openFiles.length === 0 && <li className="side-note">No files open.</li>}
                      {openFiles.map((f) => (
                        <li key={f.path}>
                          <button className={f.path === active ? "selected" : ""} onClick={() => { setActive(f.path); lastPaths.set(workspaceId, f.path); }} title={f.path}>
                            <FileCode2 size={13} aria-hidden="true" />
                            <span className="scm-name">{f.path.split("/").pop()}</span>
                            <span className="scm-folder">{f.path.split("/").slice(0, -1).join("/")}</span>
                            {f.saved !== f.model.getValue() && <span className="tree-dirty" aria-label="unsaved changes">●</span>}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="side-section">
                  {section(treeOpen, () => setTreeOpen((v) => !v), workspace.title, (
                    <span className="side-actions">
                      <NewFile
                        workspaceId={workspaceId}
                        report={report}
                        openSignal={newFileRequest}
                        created={async (path) => {
                          await refreshTree();
                          await rescan();
                          await open(path);
                        }}
                      />
                      <button className="icon-button" aria-label="Refresh files" title="Re-read the workspace file tree" onClick={() => void refreshTree().then(rescan).then(git.refresh).catch(report)}>
                        <RefreshCw size={13} aria-hidden="true" />
                      </button>
                      <button className="icon-button" aria-label="Collapse folders" title="Collapse folders" onClick={() => setCollapseSignal((v) => v + 1)}>
                        <ChevronsDownUp size={13} aria-hidden="true" />
                      </button>
                    </span>
                  ), `Files in ${workspace.title}`)}
                  {treeOpen && (
                    <Explorer entries={entries} active={active} open={(path) => void open(path).catch(report)} decorations={treeDecorations} collapseSignal={collapseSignal} />
                  )}
                </div>
                {scan && (scan.kind === "dotnet" || scan.kind === "python") && (
                  <div className="side-section project-section">
                    <ProjectPanel workspaceId={workspaceId} scan={scan} refresh={rescan} openFile={(path) => void open(path).catch(report)} report={report} build={build} busy={busy} />
                  </div>
                )}
                {code && (
                  <div className="side-section">
                    {section(outlineOpen, () => setOutlineOpen((v) => !v), `Outline · ${active.split("/").pop()}`)}
                    {outlineOpen &&
                      (symbols.length ? (
                        <ul className="outline" aria-label="Outline">{renderOutline(symbols)}</ul>
                      ) : (
                        <p className="side-note">{languageNames.length ? "No symbols reported for this file." : "Outline appears when code intelligence is running."}</p>
                      ))}
                  </div>
                )}
              </div>
            </div>
          )}
          {view === "search" && (
            <SearchView workspaceId={workspaceId} root={root} languages={languageNames} openFile={(path, line) => void open(path, line).catch(report)} report={report} focusSignal={searchSignal} />
          )}
          {view === "scm" && (
            <SourceControlView workspaceId={workspaceId} activePath={active} git={git} report={report} beforeMutation={flushBuffers} openFile={(path) => void open(path).catch(report)} />
          )}
          {view === "debug" && (
            <RunDebugView debug={debug} root={root} launch={startDebug} busy={busy} launchable={launchable} openFile={(path, line) => void open(path, line).catch(report)} />
          )}
          {view === "testing" && (
            <div className="sidebar-view testing-view">
              <div className="side-head">
                <h2>Testing</h2>
              </div>
              <div className="side-scroll">
                <TestsPanel workspaceId={workspaceId} structured={Boolean(structuredTests)} openFile={(path, line) => void open(path, line).catch(report)} report={report} legacyRun={() => void validate()} />
              </div>
            </div>
          )}
          <div
            className="sidebar-resizer"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize sidebar"
            aria-valuenow={sidebarWidth}
            tabIndex={0}
            onPointerDown={startSidebarDrag}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft") setSize("explorer", sidebarWidth - 16);
              if (event.key === "ArrowRight") setSize("explorer", sidebarWidth + 16);
            }}
          />
        </aside>
        <section
          className="editor-stack"
          ref={(node) => {
            if (node && Math.abs(node.clientHeight - panelColumn) > 8) setPanelColumn(node.clientHeight);
          }}
        >
          <div className="editor-tabs-row">
            <div className="file-tabs" role="tablist" aria-label="Open files">
              {openFiles.map((f) => {
                const dirty = f.saved !== f.model.getValue();
                return (
                  <div className={f.path === active ? "file-tab active" : "file-tab"} key={f.path} data-dirty={dirty || undefined}>
                    <button
                      role="tab"
                      aria-selected={f.path === active}
                      onClick={() => {
                        setActive(f.path);
                        lastPaths.set(workspaceId, f.path);
                      }}
                      title={f.path}
                    >
                      <FileCode2 size={13} aria-hidden="true" />
                      {f.path.split("/").pop()}
                      {dirty && (
                        <span className="dirty" title="Unsaved changes" aria-label="unsaved changes">
                          ●
                        </span>
                      )}
                    </button>
                    <button
                      className="tab-close"
                      aria-label={`Close ${f.path}`}
                      title="Close"
                      onClick={() => {
                        if (f.saved !== f.model.getValue()) setClosing(f);
                        else void closeFile(f).catch(report);
                      }}
                    >
                      <X size={12} aria-hidden="true" />
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="editor-actions">
              {isDotnet && (
                <button className="compact quiet" disabled={busy} onClick={() => setDesignerOpen(true)}>
                  Design form
                </button>
              )}
              <button className="icon-button" aria-label="Compare" disabled={!active || busy} title="Compare the editor with the file on disk" onClick={() => void compare().catch(report)}>
                <GitCompare size={14} aria-hidden="true" />
              </button>
              <button className="icon-button" aria-label="Save" onClick={() => void save()} disabled={busy || !active} title="Save (Ctrl+S)">
                <Save size={14} aria-hidden="true" />
              </button>
              <ActionMenu>
                {isDotnet && (
                  <>
                    <button disabled={busy} onClick={() => build("rebuild")}>
                      Rebuild
                    </button>
                    <button disabled={busy} onClick={() => build("clean")}>
                      Clean
                    </button>
                    <button disabled={busy} onClick={() => build("restore")}>
                      Restore packages
                    </button>
                  </>
                )}
                <LocalPreview sessionId={activeRun?.id} report={report} />
                <Packages workspaceId={workspaceId} report={report} setOutput={setOutput} />
                <button disabled={busy} onClick={() => void validate(true)} title="Review the detected commands before approving a test run">
                  Review tests
                </button>
                <button
                  disabled={busy || !session}
                  onClick={() => {
                    setBusy(true);
                    void call<{ session_id: string }>("studio.restart", { workspace_id: workspaceId, session_id: session })
                      .catch(report)
                      .finally(() => setBusy(false));
                  }}
                >
                  Restart
                </button>
                <button disabled={busy || dirtyCount === 0} onClick={() => void saveAll()}>
                  Save all files{dirtyCount ? ` (${dirtyCount})` : ""}
                </button>
                <WorkspaceTools workspaceId={workspaceId} path={active} openFile={open} report={report} beforeMutation={flushBuffers} />
                <button
                  disabled={!Object.keys(slice.languages).length}
                  onClick={() => {
                    for (const language of Object.keys(slice.languages))
                      void call("lsp.restart", { workspace_id: workspaceId, language }).catch(report);
                  }}
                >
                  Restart code intelligence
                </button>
              </ActionMenu>
            </div>
          </div>
          {active && (
            <nav className="breadcrumbs" aria-label="Breadcrumbs">
              {active.split("/").map((part, index, parts) => (
                <span key={index} className="crumb" data-last={index === parts.length - 1 || undefined}>
                  {part}
                  {(index < parts.length - 1 || breadcrumbSymbols.length > 0) && <ChevronRight size={11} aria-hidden="true" />}
                </span>
              ))}
              {breadcrumbSymbols.map((item, index) => (
                <button
                  key={`${item.name}:${item.line}`}
                  className="crumb crumb-symbol"
                  onClick={() => {
                    editor.current?.setPosition({ lineNumber: item.line, column: 1 });
                    editor.current?.revealLineInCenter(item.line);
                    editor.current?.focus();
                  }}
                >
                  <span className="symbol-tag" data-kind={symbolTag(item.kind).tag} aria-hidden="true">{symbolTag(item.kind).tag}</span>
                  {item.name}
                  {index < breadcrumbSymbols.length - 1 && <ChevronRight size={11} aria-hidden="true" />}
                </button>
              ))}
            </nav>
          )}
          {languageFailed && (
            <div className="notice editor-notice" data-tone="warning" role="status">
              <AlertTriangle size={14} aria-hidden="true" />
              <span className="grow">Code intelligence stopped ({langState.text}). Editing, saving, build and run keep working.</span>
              <button
                className="compact"
                onClick={() => {
                  for (const language of Object.keys(slice.languages))
                    void call("lsp.restart", { workspace_id: workspaceId, language }).catch(report);
                }}
              >
                Restart code intelligence
              </button>
              <button className="compact quiet" onClick={() => setDock("problems")}>
                Show problems
              </button>
            </div>
          )}
          <div className="editor-area">
            <div className="editor-host" ref={host} />
            <DebugToolbar debug={debug} />
            {cursor.lines > 1 && !assistantOpen && code && (
              <button className="selection-ask" onClick={() => askAssistant("Explain the selected code and anything surprising about it.", { selection: true, file: true })} title="Ask OLIVE about the selection (Ctrl+Alt+I)">
                <Sparkles size={12} aria-hidden="true" />
                Ask OLIVE
                <kbd className="kbd">Ctrl+Alt+I</kbd>
              </button>
            )}
            {!active && (
              <div className="editor-empty" role="note">
                <FileCode2 size={20} aria-hidden="true" />
                <strong>No file open</strong>
                <p className="muted">Choose a file in the Explorer, or press Ctrl+P to go to a file. Unsaved editor buffers survive navigation.</p>
              </div>
            )}
          </div>
          <StudioPanel
            tabs={tabs}
            active={panelTab}
            select={(tab) => setDock(tab)}
            open={Boolean(dock)}
            close={() => setDock("")}
            height={clampPanelHeight(sizes.output || layout.panelDefault, panelColumn)}
            setHeight={(value) => setSize("output", clampPanelHeight(value, panelColumn))}
            maximised={panelMax}
            setMaximised={setPanelMax}
            counts={{
              problems: counts.errors + counts.warnings ? { count: counts.errors + counts.warnings, tone: counts.errors ? "error" : "warning", spoken: `${counts.errors} errors, ${counts.warnings} warnings` } : undefined,
              terminal: terminalCount ? { count: terminalCount, spoken: `${terminalCount} ${terminalCount === 1 ? "session" : "sessions"}` } : undefined,
            }}
          >
            <div hidden={panelTab !== "terminal"} className="dock-host">
              <TerminalPanel workspaceId={workspaceId} visible={panelTab === "terminal" && Boolean(dock) && visible} report={report} newSignal={terminalRequest} />
            </div>
            {panelTab === "problems" && (
              <div className="dock-host">
                <ProblemsPanel problems={problems} openFile={(path, line, column) => void open(path, line, column).catch(report)} languageState={langState.text} languageFailed={languageFailed} />
              </div>
            )}
            <div hidden={panelTab !== "output"} className="dock-host">
              <OutputView
                channels={channels}
                selected={selectedOutput}
                select={selectOutput}
                text={output}
                jobs={slice.jobs}
                tests={slice.tests}
                workspaceId={workspaceId}
                report={report}
                showProblems={() => setDock("problems")}
                rebuild={isDotnet ? () => build("rebuild") : undefined}
              />
            </div>
            {panelTab === "console" && (
              <div className="dock-host">
                <DebugConsole debug={debug} />
              </div>
            )}
            {panelTab === "web" && (
              <div className="dock-host">
                <WebPanel workspaceId={workspaceId} report={report} />
              </div>
            )}
            {panelTab === "references" && (
              <div className="dock-host">
                <div className="dock-panel references-panel">
                  <div className="dock-toolbar">
                    <span className="small">
                      {references ? `${references.items.length} ${references.items.length === 1 ? "reference" : "references"} to ${references.symbol}` : "Find all references from the editor (Shift+F12)."}
                    </span>
                  </div>
                  {references && (
                    <ul className="reference-list">
                      {references.items.map((item, index) => (
                        <li key={index}>
                          <button className="problem-row" onClick={() => void open(item.relative, item.range.start.line + 1, item.range.start.character + 1).catch(report)}>
                            <span className="problem-message">{item.text || item.relative}</span>
                            <span className="problem-where">
                              {item.relative}:{item.range.start.line + 1}:{item.range.start.character + 1}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </StudioPanel>
        </section>
        {assistantOpen && !docked && <div className="studio-sidebar-scrim" aria-hidden="true" onClick={() => setAssistantOpen(false)} />}
        <aside
          className="studio-assistant"
          hidden={!assistantOpen}
          aria-label="Assistant"
          data-overlay={!docked || undefined}
          style={{ width: assistantWidth }}
        >
          <div
            className="assistant-resizer"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize OLIVE sidebar"
            aria-valuenow={assistantWidth}
            tabIndex={0}
            onPointerDown={startAssistantDrag}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft") setSize("assistant", assistantWidth + 16);
              if (event.key === "ArrowRight") setSize("assistant", assistantWidth - 16);
            }}
          />
          {/* Mounted only while open: drafts and threads live outside the
              component, and a hidden assistant should not poll the editor. */}
          {chat && assistantOpen && (
            <StudioAssistant
              key={workspaceId}
              workspaceId={workspaceId}
              path={active}
              selection={selectionText}
              chat={chat}
              snapshot={snapshot}
              busy={interactionBusy}
              submit={submit}
              cancel={cancel}
              seed={assistantSeed}
              close={() => setAssistantOpen(false)}
              sources={{
                problems: {
                  label: problems.length ? `Problems · ${problems.length}` : "No problems",
                  available: problems.length > 0,
                  load: () => problems.slice(0, 40).map((p) => `${p.file}:${p.line}:${p.column} ${p.severity} ${p.message} [${p.source}]`).join("\n"),
                },
                test: {
                  label: failedTests.length ? `Failing test · ${failedTests.length}` : "No failing test",
                  available: failedTests.length > 0,
                  load: () => failedTests.slice(0, 3).map((t) => `${t.full_name}\n${t.message}\n${(t.stack_trace || "").slice(0, 3000)}`).join("\n\n"),
                },
                changes: {
                  label: scmCount ? `Uncommitted changes · ${scmCount}` : "No uncommitted changes",
                  available: scmCount > 0,
                  load: () => call<unknown>("studio.diff", { workspace_id: workspaceId }).then((value) => JSON.stringify(value, null, 2).slice(0, 12000)),
                },
              }}
              quick={[
                { label: "Explain", title: "Explain the selected code or this file", disabled: !active, run: () => askAssistant("Explain this code and anything surprising about it.", { file: true, selection: true }) },
                { label: "Find bug", title: "Look for defects in the selection or this file", disabled: !active, run: () => askAssistant("Look for bugs in this code. Answer only; do not change files.", { file: true, selection: true }) },
                { label: "Refactor", title: "Propose a refactor you can review", disabled: !active, run: () => askAssistant("Propose a refactor for this code. Show it as a change I can review; nothing is saved automatically.", { file: true, selection: true }) },
                { label: "Generate tests", title: "Propose unit tests you can review", disabled: !active, run: () => askAssistant("Write unit tests for this file. Propose them as a change I can review.", { file: true }) },
                { label: "Explain error", title: "Explain the first problem in Problems", disabled: problems.length === 0, run: explainError },
                { label: "Suggest fix", title: "Suggest a fix for the failing test", disabled: failedTests.length === 0, run: () => askAssistant("Suggest a fix for this failing test. Explain the cause first; propose a change I can review.", { test: true, file: true }) },
                { label: "Review changes", title: "Review the uncommitted Git changes", disabled: scmCount === 0, run: () => askAssistant("Review these uncommitted changes for defects and risks.", { changes: true }) },
              ]}
            />
          )}
        </aside>
      </div>
      <StatusBar
        branch={git.status?.branch}
        branchDirty={scmCount > 0}
        errors={counts.errors}
        warnings={counts.warnings}
        openProblems={() => setDock("problems")}
        debugText={
          debugState === "suspended"
            ? `Paused${debug.current ? ` · ${debug.current.path.split("/").pop()}:${debug.current.line}` : ""}`
            : debugState && ["starting", "running"].includes(debugState)
              ? debugStateText(debug)
              : undefined
        }
        debugPaused={debugState === "suspended"}
        openDebug={() => showView("debug")}
        running={runningText}
        cursor={model ? cursorLabel(cursor.line, cursor.column, cursor.lines, cursor.chars) : undefined}
        indentation={model ? indentLabel(model.getOptions().insertSpaces, model.getOptions().tabSize) : undefined}
        encoding={model ? "UTF-8" : undefined}
        eol={model ? (model.getEOL() === "\r\n" ? "CRLF" : "LF") : undefined}
        language={model ? languageName(model.getLanguageId()) : undefined}
        runtime={scan ? runtimeLabel(scan.kind, scan.tooling.python.version, scan.tooling.dotnet.version, scan.tooling.python.executable) : undefined}
        codeIntelligence={langState}
        openOutput={() => setDock("output")}
        saveStatus={saveStatus || (dirtyCount ? `${dirtyCount} unsaved` : "")}
      />
      <Sheet
        open={switching}
        onOpenChange={setSwitching}
        title="Workspaces"
        description="Each open workspace keeps its own files, terminals, tests and debug session. Switching never discards another one."
      >
        <div className="studio-recent">
          <span className="eyebrow">Open in Studio</span>
          {openIds
            .map((id) => workspaces.find((w) => w.id === id))
            .filter((w): w is Workspace => Boolean(w))
            .map((w) => (
              <div className="workspace-row" key={w.id}>
                <button
                  className={`recent-row ${w.id === workspaceId ? "selected" : ""}`}
                  aria-label={w.title}
                  aria-current={w.id === workspaceId ? "true" : undefined}
                  title={w.root_path}
                  onClick={() => {
                    setSwitching(false);
                    openWorkspace(w.id);
                  }}
                >
                  <span className="recent-icon">
                    <FolderOpen size={15} aria-hidden="true" />
                  </span>
                  <span>
                    <strong>{w.title}</strong>
                    <small>{w.root_path}</small>
                  </span>
                </button>
                {openIds.length > 1 && (
                  <button
                    className="icon-button"
                    aria-label={`Close ${w.title}`}
                    title="Close this workspace in Studio"
                    onClick={() => requestCloseWorkspace(w.id)}
                  >
                    <X size={15} aria-hidden="true" />
                  </button>
                )}
              </div>
            ))}
          {workspaces.filter((w) => !openIds.includes(w.id)).length > 0 && (
            <>
              <span className="eyebrow">Other approved folders</span>
              {workspaces
                .filter((w) => !openIds.includes(w.id))
                .map((w) => (
                  <button
                    className="recent-row"
                    key={w.id}
                    aria-label={w.title}
                    title={w.root_path}
                    onClick={() => {
                      setSwitching(false);
                      openWorkspace(w.id);
                    }}
                  >
                    <span className="recent-icon">
                      <FolderOpen size={15} aria-hidden="true" />
                    </span>
                    <span>
                      <strong>{w.title}</strong>
                      <small>{w.root_path}</small>
                    </span>
                  </button>
                ))}
            </>
          )}
        </div>
        <div className="row wrap" style={{ marginTop: 14 }}>
          <button
            className="primary"
            onClick={() => {
              setSwitching(false);
              setWizard(true);
            }}
          >
            <FilePlus2 size={16} aria-hidden="true" />
            New project
          </button>
          <button
            onClick={() =>
              void window.olive
                .openWorkspace()
                .then((w) => {
                  if (w) {
                    setSwitching(false);
                    openWorkspace(w.id);
                  }
                })
                .catch(report)
            }
          >
            <FolderOpen size={16} aria-hidden="true" />
            Open an existing folder
          </button>
        </div>
      </Sheet>
      <Sheet
        centered
        open={Boolean(closing)}
        onOpenChange={(value) => {
          if (!value) setClosing(null);
        }}
        title="Unsaved changes"
        description={closing ? `Keep, save, or discard your editor changes to ${closing.path}. Discard leaves the file on disk untouched.` : ""}
      >
        <div className="row">
          <button onClick={() => setClosing(null)}>Keep editing</button>
          <button
            disabled={busy}
            onClick={() => {
              if (closing) void closeFile(closing).catch(report);
            }}
          >
            Discard buffer
          </button>
          <button
            className="primary"
            disabled={busy}
            onClick={() => {
              if (closing)
                void save(closing)
                  .then((saved) => {
                    if (saved) return closeFile(closing);
                  })
                  .catch(report);
            }}
          >
            Save and close
          </button>
        </div>
      </Sheet>
      <Sheet
        centered
        open={Boolean(renaming)}
        onOpenChange={(value) => {
          if (!value) setRenaming(null);
        }}
        title="Rename symbol"
        description="The language server computes every affected location. You review the edits before they reach any buffer."
      >
        {renaming && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const model = editor.current?.getModel();
              if (!model || !renameDraft.trim() || renameDraft === renaming.placeholder) return;
              const position = renaming.position;
              setRenaming(null);
              void renameSymbol(model, position, renameDraft.trim())
                .then((edit) => {
                  if (!edit.total) {
                    setSaveStatus("The language server returned no edits for that rename");
                    return;
                  }
                  setProposedEdit({ ...edit, label: `Rename ${renaming.placeholder} to ${renameDraft.trim()}` });
                })
                .catch(report);
            }}
          >
            <label className="field">
              New name for <code>{renaming.placeholder}</code>
              <input aria-label="New symbol name" value={renameDraft} onChange={(e) => setRenameDraft(e.target.value)} autoFocus />
            </label>
            <div className="row">
              <button type="button" onClick={() => setRenaming(null)}>
                Cancel
              </button>
              <button type="submit" className="primary" disabled={!renameDraft.trim() || renameDraft === renaming.placeholder}>
                Preview edits
              </button>
            </div>
          </form>
        )}
      </Sheet>
      <NewProjectWizard
        open={wizard}
        onOpenChange={setWizard}
        workspaceId={workspaceId}
        onCreated={(created) => openWorkspace(created.id)}
        report={report}
      />
      <WinFormsDesigner key={workspaceId} workspaceId={workspaceId} open={designerOpen} onOpenChange={setDesignerOpen}
        openCode={async path => {await refreshTree(); await open(path);}}
        run={() => runJob("Native app started", async () => {await saveAll(); await call("project.run", {workspace_id: workspaceId});}, "output")} />
      <Sheet
        centered
        open={Boolean(closingWorkspace)}
        onOpenChange={(value) => {
          if (!value) setClosingWorkspace(null);
        }}
        title="Close workspace"
        description={
          closingWorkspace
            ? `${closingWorkspace.title} has work that would be lost. Nothing is discarded until you choose.`
            : ""
        }
      >
        {closingWorkspace && (
          <>
            <ul className="close-summary">
              {closingWorkspace.dirty > 0 && (
                <li>
                  {closingWorkspace.dirty} unsaved {closingWorkspace.dirty === 1 ? "file" : "files"}
                </li>
              )}
              {closingWorkspace.running.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <div className="row">
              <button onClick={() => setClosingWorkspace(null)}>Cancel</button>
              <button onClick={() => void finishCloseWorkspace(closingWorkspace.id, false)}>
                Close and discard
              </button>
              <button className="primary" onClick={() => void finishCloseWorkspace(closingWorkspace.id, true)}>
                Save and close
              </button>
            </div>
          </>
        )}
      </Sheet>
      <EditPreview edit={proposedEdit} root={root} workspaceId={workspaceId} openModel={openModelFor} close={() => setProposedEdit(null)} report={report} />
      {comparison && <Compare disk={comparison.disk_text} model={comparison.file.model} close={() => setComparison(null)} reconcile={() => void reconcile().catch(report)} />}
    </div>
  );
}

export default function Studio(props: Omit<ComponentProps<typeof LocalStudio>, "location" | "openRemote">) {
  const [remote, setRemote] = useState(false);
  const [remoteVisited, setRemoteVisited] = useState(false);
  const openRemote = useCallback(() => {
    setRemoteVisited(true);
    setRemote(true);
  }, []);
  // Local and Remote are separate security domains (Connect C8). The switch
  // lives in the title bar; each mode renders only its own capabilities.
  const location = (
    <div className="segmented tb-location" role="group" aria-label="Studio workspace location">
      <button aria-pressed={!remote} onClick={() => setRemote(false)}>
        Local
      </button>
      <button aria-pressed={remote} onClick={openRemote}>
        Remote
      </button>
    </div>
  );
  return (
    <div className="studio-host">
      <div style={{ display: remote ? "none" : "contents" }}>
        <LocalStudio {...props} location={location} openRemote={openRemote} visible={props.visible !== false && !remote} />
      </div>
      <div className="remote-host" hidden={!remote}>
        {remoteVisited && <RemoteStudio theme={props.theme} visible={props.visible !== false && remote} location={location} openSettings={props.openSettings} />}
      </div>
    </div>
  );
}
