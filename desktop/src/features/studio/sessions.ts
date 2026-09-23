// Per-workspace Studio UI state. Editor models, terminals, debug sessions and
// test results are already keyed by workspace (Monaco model map and the Python
// runtime); this keeps the *view* state per workspace too, so switching from A
// to B and back restores A exactly rather than resetting it.

export interface SessionUi {
  /** Relative path of the file shown in the editor. */
  activePath: string;
  /** Which bottom tool panel is open, "" for none. */
  dock: string;
  explorerOpen: boolean;
  assistantOpen: boolean;
  /** Studio V2 primary sidebar view (explorer, search, scm, debug, testing). */
  view: string;
}
const DEFAULTS: SessionUi = {
  activePath: "",
  dock: "",
  explorerOpen: true,
  assistantOpen: false,
  view: "explorer",
};
const sessions = new Map<string, SessionUi>();

export function sessionUi(workspaceId: string): SessionUi {
  const existing = sessions.get(workspaceId);
  if (existing) return existing;
  const created = { ...DEFAULTS };
  sessions.set(workspaceId, created);
  return created;
}
export function updateSessionUi(workspaceId: string, patch: Partial<SessionUi>) {
  sessions.set(workspaceId, { ...sessionUi(workspaceId), ...patch });
}
export function forgetSession(workspaceId: string) {
  sessions.delete(workspaceId);
}

const OPEN_KEY = "studioOpenWorkspaces";
/** Ids of the workspaces the person has open in Studio, in switcher order. */
export function loadOpenWorkspaces(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(OPEN_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((v): v is string => typeof v === "string").slice(0, 12) : [];
  } catch {
    return [];
  }
}
export function saveOpenWorkspaces(ids: string[]) {
  try {
    localStorage.setItem(OPEN_KEY, JSON.stringify(ids.slice(0, 12)));
  } catch {
    // Convenience only; the runtime still owns the workspace records.
  }
}

const ACTIVE_KEY = "studioActiveWorkspace";
/** The workspace Studio should show first after a restart. Restoring which
 *  folder was open is not the same as resuming what was running in it: no
 *  terminal, debug session or command is restarted. */
export function loadActiveWorkspace(): string {
  try {
    return localStorage.getItem(ACTIVE_KEY) || "";
  } catch {
    return "";
  }
}
export function saveActiveWorkspace(id: string) {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id);
    else localStorage.removeItem(ACTIVE_KEY);
  } catch {
    // Convenience only.
  }
}
