import { threadAfter, withStudioContext, type ConversationAnchor } from "../../services/conversation";
import { useEffect, useRef, useState } from "react";
import { ArrowUp, Check, SquarePen, Square, X } from "lucide-react";
import { GrowingComposer } from "../../components/GrowingComposer";
import { Markdown } from "../../components/Markdown";
import type { Chat, Snapshot } from "../../services/api";
import { messageAttribution } from "../chat/RemoteTarget";
import { OliveLogo } from "../../components/OliveLogo";

// Drafts and threads survive the panel being closed or Studio leaving the
// screen; they are keyed by workspace, not by mount.
const drafts = new Map<string, string>();
const threads = new Map<string, ConversationAnchor>();
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
  /** Context chips a quick action switches on. */
  context?: Partial<Record<ContextChip, boolean>>;
}
export type ContextChip = "file" | "selection" | "problems" | "test" | "changes";
export interface ContextSource {
  /** What the chip shows; empty means the context does not exist right now. */
  label: string;
  available: boolean;
  /** Text appended to the request when the chip is on (problems, tests, changes). */
  load?: () => Promise<string> | string;
}

// Studio V2 §11: the OLIVE secondary sidebar. Context is explicit: a chip that
// is on (solid, cyan) is sent with the next message; a chip that is off
// (dashed) is not. The assistant answers; it cannot save, run, stage, commit
// or change permissions. Proposed file changes go through the existing
// workspace permission review outside the model.
export function StudioAssistant({
  workspaceId,
  path,
  selection,
  sources,
  chat,
  snapshot,
  busy,
  submit,
  cancel,
  seed,
  close,
  quick,
}: {
  workspaceId: string;
  path: string;
  selection: () => string;
  sources: Record<Exclude<ContextChip, "file" | "selection">, ContextSource>;
  chat: Chat;
  snapshot: Snapshot | null;
  busy: boolean;
  submit: StudioSubmit;
  cancel: () => void;
  seed?: AssistantSeed;
  close: () => void;
  quick: { label: string; title: string; disabled?: boolean; run: () => void }[];
}) {
  const [request, setRequest] = useState(drafts.get(workspaceId) || "");
  const [anchor, setAnchor] = useState(threads.get(workspaceId));
  const [chips, setChips] = useState<Record<ContextChip, boolean>>({ file: true, selection: true, problems: false, test: false, changes: false });
  const [selectionText, setSelectionText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  useEffect(() => {
    const read = () => setSelectionText(selectionRef.current());
    read();
    const timer = setInterval(read, 800);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (seed && seed.text) {
      setRequest(seed.text);
      drafts.set(workspaceId, seed.text);
      if (seed.context) setChips((current) => ({ ...current, ...seed.context }));
      input.current?.focus();
    }
  }, [seed?.revision]);
  const thread = threadAfter(chat, anchor);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [thread.length, chat.partial]);
  const preset = snapshot?.presets?.find((p) => p.id === chat.preset);
  const selectionLines = selectionText ? selectionText.split("\n").length : 0;
  const chipList: { id: ContextChip; label: string; available: boolean }[] = [
    { id: "file", label: path ? path.split("/").pop()! : "No file open", available: Boolean(path) },
    { id: "selection", label: selectionText ? `Selection · ${selectionLines} ${selectionLines === 1 ? "line" : "lines"}` : "No selection", available: Boolean(selectionText) },
    { id: "problems", label: sources.problems.label, available: sources.problems.available },
    { id: "test", label: sources.test.label, available: sources.test.available },
    { id: "changes", label: sources.changes.label, available: sources.changes.available },
  ];
  const sending = chipList.filter((chip) => chip.available && chips[chip.id]).length;
  const send = async () => {
    if (!request.trim() || busy) return;
    const next = anchor && anchor.chatId === chat.id ? anchor : { chatId: chat.id, after: chat.messages.at(-1)?.id || "" };
    setAnchor(next);
    threads.set(workspaceId, next);
    while (threads.size > 12) threads.delete(threads.keys().next().value!);
    const on = (id: ContextChip) => chips[id] && chipList.find((chip) => chip.id === id)?.available;
    const text = withStudioContext(request, {
      problems: on("problems") ? String(await sources.problems.load?.()) : "",
      failingTest: on("test") ? String(await sources.test.load?.()) : "",
      changes: on("changes") ? String(await sources.changes.load?.()) : "",
    });
    setRequest("");
    drafts.set(workspaceId, "");
    void submit(text, {
      workspace_id: workspaceId,
      project_id: "",
      path: on("file") ? path : "",
      selection: on("selection") ? selectionText : "",
    });
  };
  return (
    <div className="assistant-panel">
      <div className="assistant-head">
        <OliveLogo className="olive-mark" />
        <strong>OLIVE</strong>
        <span className="assistant-model" title={chat.run_on ? "Runs on the paired device chosen in Chat" : "Runs on this device"}>
          {preset ? preset.name : "Previous selection"} · {chat.run_on ? "paired device" : "This device"}
        </span>
        <span className="grow" />
        <button
          className="icon-button"
          aria-label="New thread"
          title="New thread"
          onClick={() => {
            const next = { chatId: chat.id, after: chat.messages.at(-1)?.id || "" };
            setAnchor(next);
            threads.set(workspaceId, next);
          }}
        >
          <SquarePen size={14} aria-hidden="true" />
        </button>
        <button className="icon-button" aria-label="Close assistant" title="Close (drafts are kept) · Ctrl+Alt+B" onClick={close}>
          <X size={15} aria-hidden="true" />
        </button>
      </div>
      <div className="assistant-context">
        <div className="assistant-context-head">
          <span>Context sent with your next message</span>
          <span aria-live="polite">{sending} of {chipList.filter((c) => c.available).length}</span>
        </div>
        <div className="context-chips" role="group" aria-label="Context sent with your next message">
          {chipList.map((chip) => (
            <button
              key={chip.id}
              className="context-chip"
              aria-pressed={chip.available && chips[chip.id]}
              disabled={!chip.available}
              title={chip.available ? (chips[chip.id] ? "Will be sent · click to leave out" : "Not sent · click to include") : "Not available right now"}
              onClick={() => setChips((current) => ({ ...current, [chip.id]: !current[chip.id] }))}
            >
              {chip.available && chips[chip.id] && <Check size={11} aria-hidden="true" />}
              {chip.label}
            </button>
          ))}
        </div>
        <div className="assistant-quick" role="group" aria-label="Quick requests">
          {quick.map((item) => (
            <button key={item.label} className="ws-chip" disabled={item.disabled || busy} title={item.title} onClick={item.run}>
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <div className="assistant-thread" aria-label="Assistant conversation" role="log">
        {thread.length === 0 && !chat.partial && (
          <p className="side-note">
            Ask about this workspace. Answers stay answers; file changes are proposals you review, and saving stays yours.
          </p>
        )}
        {thread.map((message) =>
          message.role === "user" ? (
            <div className="assistant-turn user" key={message.id}>
              <p>{message.content.split("\n\nProblems reported in this workspace:")[0].split("\n\nFailing test:")[0].split("\n\nUncommitted changes:")[0]}</p>
            </div>
          ) : (
            <div className="assistant-turn olive" key={message.id}>
              <div className="message-attribution">
                <OliveLogo className="olive-mark" />
                <b>OLIVE</b>
                {messageAttribution(message.provider) && <span className="attribution-meta">{messageAttribution(message.provider)}</span>}
              </div>
              <Markdown text={message.content} />
              {message.completion_state === "incomplete" && <span className="ws-pill" data-tone="warning">Stopped · partial answer kept</span>}
            </div>
          ),
        )}
        {busy && anchor?.chatId === chat.id && (
          <div className="assistant-turn olive">
            <div className="message-attribution message-writing">
              <OliveLogo className="olive-mark" />
              <span>OLIVE · writing</span>
            </div>
            {chat.partial ? <Markdown text={chat.partial} /> : null}
            <span className="stream-caret" aria-hidden="true" />
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="assistant-compose composer">
        <GrowingComposer
          ref={input}
          aria-label="Ask Studio assistant"
          value={request}
          placeholder={path ? `Ask about ${path.split("/").pop()}…` : "What are we working on?"}
          onChange={(e) => {
            setRequest(e.target.value);
            drafts.set(workspaceId, e.target.value);
            while (drafts.size > 12) drafts.delete(drafts.keys().next().value!);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <div className="composer-bottom">
          <span className="composer-hint">Ctrl+Enter to send · only the marked context is sent</span>
          {busy ? (
            <button className="send" aria-label="Stop response" onClick={cancel}>
              <Square size={13} aria-hidden="true" />
            </button>
          ) : (
            <button className="send" aria-label="Send to OLIVE" disabled={!request.trim()} onClick={() => void send()}>
              <ArrowUp size={15} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
