import type { Method, Arguments } from "../../electron/contracts";
export interface WireEvent {
  v: number;
  kind: string;
  seq: number;
  topic: string;
  data: unknown;
}
export interface Preset {
  id: "fast" | "normal" | "max" | "deep" | "reimagine";
  name: string;
  model: string;
  digest: string;
  runtime: string;
  description: string;
  pipeline: string;
  status: string;
  capabilities: string[];
  resource_policy: string;
}
export interface Message {
  provider?: { runtime?: string; preset?: string; device_id?: string; device_name?: string; request_id?: string };
  completion_state?: "complete" | "incomplete" | "unverified";
  id: string;
  role: string;
  content: string;
  sources: { label?: string; name?: string }[];
}
export interface Chat {
  run_on?: string;
  remote_provider?: Message["provider"];
  preset?: string;
  research_session_ids?: string[];
  id: string;
  title: string;
  model: string;
  draft: string;
  messages: Message[];
  partial: string;
  generating: boolean;
  notes?: string;
  summary?: string;
  project_id?: string;
  response_branches?: Record<string, string[]>;
  branch_index?: Record<string, number>;
  images?: { name: string }[];
  pending_draft?: { state: string; entities?: Record<string, unknown> };
  native_proposals?: {id:string;revision:number;method:string;body:Record<string,unknown>}[];
  documents: { id: string; name: string; unreadable_pages?: number[] }[];
}
export interface Workspace {
  id: string;
  title: string;
  root_path: string;
  /** Recorded when the folder was approved: it had a .git directory. */
  git_repository?: boolean;
}
export interface Approval {
  id: string;
  fingerprint: string;
  summary: string;
  tool_name: string;
  risk_level: string;
  targets: string[];
  arguments: Record<string, unknown>;
  presentation?: {
    targets?: string[];
    action: string;
    content: string;
    scope: string;
    consequence: string;
  };
}
export interface FileBuffer {
  workspace_id: string;
  path: string;
  text: string;
  expected_hash: string;
}
export interface Snapshot {
  presets?: Preset[];
  initializing?: boolean;
  activity?: {
    state: string;
    summary?: string;
    items: { id: string; method: string; chat_id?: string }[];
    count: number;
  };
  chat: Chat;
  chats: { id: string; title: string; updated_at?: string; last?: string }[];
  models: { name: string; alias: string }[];
  workspaces: Workspace[];
  approvals: Approval[];
  buffers: FileBuffer[];
  commands?: import("./studioOutput").CommandOutput[];
  validations?: import("./studioOutput").Validation[];
  runs?: {
    accepts_input?: boolean;
    id: string;
    workspace_id: string;
    stdout: string;
    stderr: string;
    state: string;
  }[];
  sequence: number;
  home: {
    recent: {
      key: string;
      title: string;
      subtitle: string;
      feature: string;
      kind: string;
    }[];
    context: { workspace?: string; file?: string };
    status: { ollama: string };
  };
}
export interface DesktopAPI {
  copyText(text: string): Promise<void>;
  browser(input: import('../../electron/browser').BrowserAction): Promise<unknown>;
  onBrowserState(listener: (state: import('../../electron/browser').BrowserState) => void): () => void;
  onBrowserAsk(listener: (text: string) => void): () => void;
  fileAction(
    input: import("../../electron/file-actions").FileAction,
  ): Promise<unknown>;
  stopControl(): Promise<void>;
  call<M extends Method>(method: M, args: Arguments<M>): Promise<unknown>;
  attachFiles(chat_id: string, files: File[]): Promise<unknown>;
  chooseDirectory(): Promise<string | null>;
  openWorkspace(): Promise<Workspace | null>;
  setInterfaceScale(factor: number): Promise<number>;
  preview(input: import("../../electron/preview").PreviewAction): Promise<void>;
  onPreviewClosed(listener: () => void): () => void;
  openExternal(url: string): Promise<void>;
  subscribe(listener: (event: WireEvent) => void): () => void;
}
declare global {
  interface Window {
    olive: DesktopAPI;
  }
}
export async function call<T, M extends Method = Method>(
  method: M,
  args: Arguments<M>,
): Promise<T> {
  try {
    return (await window.olive.call(method, args)) as T;
  } catch (error) {
    throw new Error(
      error instanceof Error
        ? error.message.replace(
            /^Error invoking remote method '[^']+': Error: /,
            "",
          )
        : "The request could not complete.",
      { cause: error },
    );
  }
}
