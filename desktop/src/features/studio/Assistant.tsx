import { responseAfter } from "../../services/conversation";
import { useEffect, useState } from "react";
import { FileCode2, Pin, PinOff, Sparkles, X } from "lucide-react";
import { GrowingComposer } from "../../components/GrowingComposer";
import { Markdown } from "../../components/Markdown";
import type { Chat } from "../../services/api";
// Drafts and the last request survive the panel being closed or Studio
// leaving the screen; they are keyed by workspace, not by mount.
const drafts = new Map<string, string>();
const requests = new Map<string, { chatId: string; after: string }>();
export type StudioSubmit = (
  text: string,
  context?: {
    workspace_id: string;
    project_id: string;
    path?: string;
    selection?: string;
  },
) => Promise<void>;
export interface AssistantSeed {
  text: string;
  revision: number;
}
export function StudioAssistant({
  workspaceId,
  path,
  selection,
  chat,
  busy,
  submit,
  seed,
  close,
  pinned,
  setPinned,
  quick,
}: {
  workspaceId: string;
  path: string;
  selection: () => string;
  chat: Chat;
  busy: boolean;
  submit: StudioSubmit;
  seed?: AssistantSeed;
  close: () => void;
  pinned: boolean;
  setPinned: (value: boolean) => void;
  quick: { label: string; title: string; disabled?: boolean; run: () => void }[];
}) {
  const [request, setRequest] = useState(drafts.get(workspaceId) || "");
  const [submitted, setSubmitted] = useState(requests.get(workspaceId));
  useEffect(() => {
    if (seed && seed.text) {
      setRequest(seed.text);
      drafts.set(workspaceId, seed.text);
    }
  }, [seed?.revision]);
  const latest = chat.messages.at(-1);
  const response = responseAfter(chat, submitted);
  return (
    <div className="assistant-panel">
      <div className="assistant-head">
        <span className="eyebrow">
          <Sparkles size={12} aria-hidden="true" /> Ask OLIVE
        </span>
        <div className="row">
          <button
            className="icon-button"
            aria-label={pinned ? "Unpin assistant" : "Pin assistant"}
            aria-pressed={pinned}
            title={pinned ? "Pinned: stays open in this workspace" : "Pin: keep open in this workspace"}
            onClick={() => setPinned(!pinned)}
          >
            {pinned ? <PinOff size={14} aria-hidden="true" /> : <Pin size={14} aria-hidden="true" />}
          </button>
          <button className="icon-button" aria-label="Close assistant" title="Close (drafts are kept)" onClick={close}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="assistant-quick" role="group" aria-label="Quick requests">
        {quick.map((item) => (
          <button key={item.label} className="quiet small" disabled={item.disabled || busy} title={item.title} onClick={item.run}>
            {item.label}
          </button>
        ))}
      </div>
      <div className="chip" title={path || "Current workspace"}>
        <FileCode2 size={13} aria-hidden="true" />
        <span>{path || "Current workspace"}</span>
      </div>
      <GrowingComposer
        aria-label="Ask Studio assistant"
        value={request}
        onChange={(e) => {
          setRequest(e.target.value);
          drafts.set(workspaceId, e.target.value);
          while (drafts.size > 12) drafts.delete(drafts.keys().next().value!);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && request.trim() && !busy) {
            e.preventDefault();
            (e.currentTarget.form?.querySelector("button.primary") as HTMLButtonElement | null)?.click();
          }
        }}
        placeholder="What are we working on?"
      />
      <button
        className="primary"
        disabled={busy || !request.trim()}
        onClick={() => {
          const next = { chatId: chat.id, after: latest?.id || "" };
          setSubmitted(next);
          requests.set(workspaceId, next);
          while (requests.size > 12) requests.delete(requests.keys().next().value!);
          void submit(request, {
            workspace_id: workspaceId,
            project_id: "",
            path,
            selection: selection(),
          });
        }}
      >
        Ask OLIVE
      </button>
      {busy && (
        <p role="status" className="small">
          OLIVE is working. Activity and approvals are available from the Core.
        </p>
      )}
      {response && (
        <section className="assistant-response">
          <h3>Response</h3>
          <Markdown text={response.content} />
        </section>
      )}
      <p className="small muted">
        The current file and selection travel with the request. Proposed changes
        go through workspace permissions and review.
      </p>
    </div>
  );
}
