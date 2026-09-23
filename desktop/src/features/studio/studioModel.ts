// Pure Studio V2 rules: layout collapse, the local/remote capability
// boundary, and presentation derived from real tooling records. Nothing here
// talks to the runtime; views call these so the rules are testable.

export type StudioView = "explorer" | "search" | "scm" | "debug" | "testing";
export type PanelTab = "problems" | "output" | "terminal" | "console" | "web" | "references";

export interface ActivityItem {
  id: StudioView;
  label: string;
  keys: string;
}
export const ACTIVITY_ITEMS: ActivityItem[] = [
  { id: "explorer", label: "Explorer", keys: "Ctrl+Shift+E" },
  { id: "search", label: "Search", keys: "Ctrl+Shift+F" },
  { id: "scm", label: "Source Control", keys: "Ctrl+Shift+G" },
  { id: "debug", label: "Run and Debug", keys: "Ctrl+Shift+D" },
  { id: "testing", label: "Testing", keys: "" },
];

/** Every Studio capability and where it exists. Remote Studio is Connect C8:
 *  shared workspaces, tree, read, revision-checked save, build, test, run,
 *  run status and run cancel — nothing else. The UI must never offer more. */
export type StudioCapability =
  | "tree"
  | "read"
  | "save"
  | "build"
  | "test"
  | "run"
  | "cancel"
  | "search"
  | "sourceControl"
  | "debug"
  | "terminal"
  | "interactiveInput"
  | "codeIntelligence"
  | "newProject"
  | "packages"
  | "reviewedCommand"
  | "assistant"
  | "externalIde";
export const REMOTE_CAPABILITIES: ReadonlySet<StudioCapability> = new Set([
  "tree",
  "read",
  "save",
  "build",
  "test",
  "run",
  "cancel",
]);
export function available(capability: StudioCapability, remote: boolean): boolean {
  return !remote || REMOTE_CAPABILITIES.has(capability);
}
export const REMOTE_UNAVAILABLE = "Not available for remote workspaces";
/** Activity bar views and whether each is usable for the current mode. */
export function activityAvailability(remote: boolean): Record<StudioView, boolean> {
  return {
    explorer: true,
    search: available("search", remote),
    scm: available("sourceControl", remote),
    debug: available("debug", remote),
    testing: !remote, // remote tests run as a job; results appear in Output › Remote
  };
}
/** Bottom panel tabs available for the mode (remote runs have no PTY). */
export function panelTabs(remote: boolean, extra: { web?: boolean; references?: boolean } = {}): PanelTab[] {
  if (remote) return ["output"];
  return [
    "problems",
    "output",
    "terminal",
    "console",
    ...(extra.web ? (["web"] as PanelTab[]) : []),
    ...(extra.references ? (["references"] as PanelTab[]) : []),
  ];
}
export const PANEL_LABELS: Record<PanelTab, string> = {
  problems: "Problems",
  output: "Output",
  terminal: "Terminal",
  console: "Debug console",
  web: "Preview",
  references: "References",
};

/** Studio collapse order (Studio V2 §3) for a window width. */
export interface StudioLayout {
  sidebarDefault: number;
  panelDefault: number;
  assistantDefault: number;
  /** Run-control labels become icon-only. */
  iconOnlyRun: boolean;
  /** The primary sidebar overlays the editor instead of docking. */
  sidebarOverlay: boolean;
  minimap: boolean;
}
export function studioLayout(width: number): StudioLayout {
  return {
    sidebarDefault: width >= 1900 ? 280 : width >= 1400 ? 256 : 240,
    panelDefault: width >= 1900 ? 280 : width >= 1400 ? 236 : 200,
    assistantDefault: width >= 1900 ? 380 : width >= 1400 ? 340 : 320,
    iconOnlyRun: width < 1440,
    sidebarOverlay: width < 1180,
    minimap: width >= 1600,
  };
}
export const EDITOR_MIN = 560;
/** Whether the OLIVE sidebar docks or becomes an overlay drawer so the editor
 *  never drops below 560 px. */
export function assistantDocks(width: number, sidebar: number, assistant: number, activityBar = 44): boolean {
  return width - activityBar - sidebar - assistant >= EDITOR_MIN;
}
export function clampPanelHeight(value: number, column: number): number {
  const max = Math.max(120, Math.floor(column * 0.4));
  return Math.max(100, Math.min(max, Math.round(value)));
}

// ---- Git ----------------------------------------------------------------
export interface GitEntry {
  path: string;
  index: string;
  worktree: string;
}
export interface GitChange {
  path: string;
  /** Single decoration letter: M, A, D, R, U (untracked), C (conflict). */
  letter: string;
  label: string;
}
function letterFor(code: string): { letter: string; label: string } {
  switch (code) {
    case "M":
      return { letter: "M", label: "Modified" };
    case "A":
      return { letter: "A", label: "Added" };
    case "D":
      return { letter: "D", label: "Deleted" };
    case "R":
      return { letter: "R", label: "Renamed" };
    case "C":
      return { letter: "C", label: "Copied" };
    case "U":
      return { letter: "!", label: "Conflict" };
    case "?":
      return { letter: "U", label: "Untracked" };
    default:
      return { letter: code || "M", label: "Changed" };
  }
}
/** Split porcelain status into staged changes and working-tree changes. */
export function gitGroups(entries: GitEntry[]): { staged: GitChange[]; changes: GitChange[] } {
  const staged: GitChange[] = [];
  const changes: GitChange[] = [];
  for (const entry of entries) {
    const index = (entry.index || "").trim();
    const worktree = (entry.worktree || "").trim();
    if (index === "?" || worktree === "?") {
      changes.push({ path: entry.path, ...letterFor("?") });
      continue;
    }
    if (index) staged.push({ path: entry.path, ...letterFor(index) });
    if (worktree) changes.push({ path: entry.path, ...letterFor(worktree) });
  }
  return { staged, changes };
}
/** Explorer decoration per path; folders get a dot when something inside changed. */
export function gitDecorations(entries: GitEntry[]): Map<string, string> {
  const map = new Map<string, string>();
  const { staged, changes } = gitGroups(entries);
  for (const change of [...staged, ...changes]) {
    const path = change.path.replace(/\\/g, "/").replace(/\/$/, "");
    if (!map.has(path) || change.letter !== "M") map.set(path, change.letter);
    const parts = path.split("/");
    for (let i = 1; i < parts.length; i++) {
      const folder = parts.slice(0, i).join("/");
      if (!map.has(folder)) map.set(folder, "•");
    }
  }
  return map;
}
/** The unified diff for one file, cut from the repository diff the runtime
 *  returned. Returns "" when the file has no hunk in it. */
export function fileDiff(diff: string, path: string): string {
  const normal = path.replace(/\\/g, "/");
  const sections = diff.split(/^(?=diff --git )/m);
  return sections.find((section) => section.startsWith(`diff --git a/${normal} `) || section.startsWith(`diff --git "a/${normal}"`)) || "";
}

// ---- Status bar -------------------------------------------------------------
export function cursorLabel(line: number, column: number, selectedLines: number, selectedChars: number): string {
  if (!selectedChars) return `Ln ${line}, Col ${column}`;
  return selectedLines > 1
    ? `Ln ${line}, Col ${column} (${selectedLines} lines selected)`
    : `Ln ${line}, Col ${column} (${selectedChars} selected)`;
}
export function indentLabel(insertSpaces: boolean, size: number): string {
  return insertSpaces ? `Spaces: ${size}` : `Tab Size: ${size}`;
}
const LANGUAGE_NAMES: Record<string, string> = {
  python: "Python",
  csharp: "C#",
  typescript: "TypeScript",
  javascript: "JavaScript",
  json: "JSON",
  markdown: "Markdown",
  xml: "XML",
  html: "HTML",
  css: "CSS",
  yaml: "YAML",
  java: "Java",
  groovy: "Groovy",
  rust: "Rust",
  go: "Go",
  c: "C",
  cpp: "C++",
  plaintext: "Plain Text",
};
export function languageName(id: string): string {
  return LANGUAGE_NAMES[id] || id;
}
/** An interpreter or SDK is named, never shown as an absolute path. */
export function runtimeLabel(kind: string, pythonVersion?: string, dotnetVersion?: string, interpreter?: string): string {
  if (kind === "dotnet") return dotnetVersion ? `.NET ${dotnetVersion}` : ".NET";
  if (kind === "python") {
    const venv = interpreter && /[\\/]\.?venv[\\/]/i.test(interpreter) ? " (.venv)" : "";
    return pythonVersion ? `Python ${pythonVersion}${venv}` : "Python";
  }
  return "";
}
export function languageServerLabel(states: { language: string; provider: string; state: string }[]): { text: string; failed: boolean } {
  if (!states.length) return { text: "", failed: false };
  const failed = states.some((s) => ["failed", "stopped"].includes(s.state));
  const text = states
    .map((s) => {
      // Providers are reported as executables; show a name, never a path.
      const base = (s.provider.split(/[\\/]/).pop() || s.provider).replace(/\.exe$/i, "");
      const name =
        s.language === "python" && /^python/i.test(base)
          ? "pylsp"
          : /omnisharp|roslyn|csharp/i.test(base)
            ? "OmniSharp"
            : base;
      return s.state === "ready" ? name : `${name} ${s.state}`;
    })
    .join(" · ");
  return { text, failed };
}

// ---- Symbols (outline, breadcrumbs) ----------------------------------------------
export interface OutlineSymbol {
  name: string;
  kind: number;
  line: number;
  endLine: number;
  children: OutlineSymbol[];
}
/** Normalise LSP DocumentSymbol[] or SymbolInformation[] into a tree. */
export function normaliseSymbols(result: unknown): OutlineSymbol[] {
  if (!Array.isArray(result)) return [];
  const one = (item: Record<string, unknown>): OutlineSymbol | null => {
    if (typeof item?.name !== "string") return null;
    const range = (item.range || (item.location as Record<string, unknown> | undefined)?.range) as
      | { start: { line: number }; end: { line: number } }
      | undefined;
    if (!range) return null;
    return {
      name: item.name,
      kind: Number(item.kind) || 0,
      line: range.start.line + 1,
      endLine: range.end.line + 1,
      children: Array.isArray(item.children) ? (item.children.map((c) => one(c as Record<string, unknown>)).filter(Boolean) as OutlineSymbol[]) : [],
    };
  };
  return result.map((item) => one(item as Record<string, unknown>)).filter(Boolean) as OutlineSymbol[];
}
/** The chain of symbols that contain a line, outermost first. */
export function symbolPath(symbols: OutlineSymbol[], line: number): OutlineSymbol[] {
  for (const symbol of symbols)
    if (line >= symbol.line && line <= symbol.endLine) return [symbol, ...symbolPath(symbol.children, line)];
  return [];
}
/** LSP SymbolKind → a short tag for the outline icon. */
export function symbolTag(kind: number): { tag: string; label: string } {
  if (kind === 5 || kind === 23 || kind === 10 || kind === 11) return { tag: "C", label: kind === 11 ? "Interface" : kind === 10 ? "Enum" : kind === 23 ? "Struct" : "Class" };
  if (kind === 6 || kind === 9 || kind === 12) return { tag: "ƒ", label: kind === 9 ? "Constructor" : kind === 6 ? "Method" : "Function" };
  if (kind === 7 || kind === 8) return { tag: "◇", label: kind === 7 ? "Property" : "Field" };
  if (kind === 14) return { tag: "K", label: "Constant" };
  if (kind === 13) return { tag: "v", label: "Variable" };
  return { tag: "·", label: "Symbol" };
}

// ---- Problems ---------------------------------------------------------------------
export interface ProblemLike {
  file: string;
  line: number;
  column: number;
  severity: "error" | "warning" | "info";
  message: string;
  source: string;
}
export function groupProblems<T extends ProblemLike>(problems: T[]): { file: string; items: T[]; errors: number; warnings: number }[] {
  const groups = new Map<string, T[]>();
  for (const problem of problems) {
    const key = problem.file || "";
    groups.set(key, [...(groups.get(key) || []), problem]);
  }
  return [...groups.entries()].map(([file, items]) => ({
    file,
    items,
    errors: items.filter((p) => p.severity === "error").length,
    warnings: items.filter((p) => p.severity === "warning").length,
  }));
}
export function problemCounts(problems: ProblemLike[]): { errors: number; warnings: number } {
  return {
    errors: problems.filter((p) => p.severity === "error").length,
    warnings: problems.filter((p) => p.severity === "warning").length,
  };
}
/** Diagnostic counts per file path, for Explorer decoration. */
export function problemsByFile(problems: ProblemLike[]): Map<string, { errors: number; warnings: number }> {
  const map = new Map<string, { errors: number; warnings: number }>();
  for (const problem of problems) {
    if (!problem.file) continue;
    const current = map.get(problem.file) || { errors: 0, warnings: 0 };
    if (problem.severity === "error") current.errors++;
    else if (problem.severity === "warning") current.warnings++;
    map.set(problem.file, current);
  }
  return map;
}

// ---- Jobs (Output job header) ------------------------------------------------------
export interface JobLike {
  label: string;
  kind: string;
  state: string;
  started_at: number;
  ended_at: number | null;
  exit_code: number | null;
  command?: string[];
}
/** The job header title. Success and failure come from the recorded state
 *  and exit code, never from stderr text. */
export function jobTitle(job: JobLike): { title: string; tone: "running" | "success" | "error" | "neutral" } {
  const noun = job.kind === "test" || job.kind === "test-list" ? "Tests" : job.label || "Build";
  if (job.state === "running") return { title: `${noun} running`, tone: "running" };
  if (job.state === "cancelled") return { title: `${noun} cancelled`, tone: "neutral" };
  if (job.state === "succeeded" || job.state === "completed" || (job.exit_code === 0 && job.state !== "failed"))
    return { title: `${noun} succeeded`, tone: "success" };
  if (job.state === "failed" || (job.exit_code !== null && job.exit_code !== 0)) return { title: `${noun} failed`, tone: "error" };
  return { title: `${noun} · ${job.state}`, tone: "neutral" };
}
export function elapsed(startedAt: number, endedAt: number | null, now = Date.now() / 1000): string {
  if (!startedAt) return "";
  const seconds = Math.max(0, (endedAt ?? now) - startedAt);
  return seconds < 60 ? `${seconds.toFixed(1)} s` : `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}
