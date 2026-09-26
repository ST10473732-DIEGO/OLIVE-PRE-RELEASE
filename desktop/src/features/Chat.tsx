import { GrowingComposer } from "../components/GrowingComposer";
import { useWarmModel } from "../services/warm";
import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  Square,
  Plus,
  Search,
  RotateCcw,
  Paperclip,
  SlidersHorizontal,
  MoreHorizontal,
  ChevronLeft,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  X,
  Sparkles,
  FileText,
  Lightbulb,
  ListChecks,
  Globe,
  Paperclip as Clip,
  Info,
  AlertTriangle,
  Trash2,
} from "lucide-react";
import { call, type Chat as ChatRecord, type Snapshot } from "../services/api";
import { Markdown } from "../components/Markdown";
import { CopyButton } from "../components/CopyButton";
import { Core } from "../components/Core";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ConversationOptions } from "./chat/ConversationOptions";
import { useResource } from "../services/useResource";
import { Sheet } from "../components/Sheet";
import { Details } from "../components/WorkspacePage";
import {NativeProposals} from './personal/Proposals';
import { ResearchEvidence } from "./chat/ResearchEvidence";
import { MediaTools } from './chat/MediaTools';
import { RemoteTarget, RemoteAttribution, messageAttribution } from './chat/RemoteTarget';
import { OliveLogo } from "../components/OliveLogo";

const HISTORY_KEY = "olive.chat.history";
// The conversation rail is docked open on a wide window and remembered;
// on a narrow one it overlays the conversation and closes on selection.
function initialHistory() {
  try {
    const stored = localStorage.getItem(HISTORY_KEY);
    if (stored === "1" || stored === "0") return stored === "1";
  } catch {
    /* private mode or blocked storage: fall through */
  }
  return window.innerWidth >= 1180;
}
const overlaying = () => window.innerWidth <= 800;

// Starting points shown while a conversation is still empty. Choosing one
// only fills the composer; nothing is sent until the person sends it.
const STARTERS: { icon: typeof FileText; label: string; text: string }[] = [
  { icon: FileText, label: "Summarise a document", text: "Summarise the attached document in five bullet points, then list any open questions it raises." },
  { icon: ListChecks, label: "Plan my day", text: "Help me plan today. Here is what I need to get done: " },
  { icon: Lightbulb, label: "Explain a concept", text: "Explain this concept as if I were new to the field, with one concrete example: " },
  { icon: Globe, label: "Research a topic", text: "Research the current state of this topic and give me a short, sourced overview: " },
];

export function Chat({
  snapshot,
  chat,
  setChat,
  busy,
  submit,
  cancel,
  report,
}: {
  snapshot: Snapshot;
  chat: ChatRecord;
  setChat: (c: ChatRecord) => void;
  busy: boolean;
  submit: (text: string, mode?: "Quick" | "Deep") => Promise<void>;
  cancel: () => void;
  report: (e: unknown) => void;
}) {
  const [draft, setDraft] = useState(chat.draft || "");
  const [mediaOpen,setMediaOpen]=useState(false);
  const [researchMode, setResearchMode] = useState<"" | "Quick" | "Deep">("");
  const latestDraft = useRef(draft);
  latestDraft.current = draft;
  const [search, setSearch] = useState("");
  const [historyOpen, setHistoryOpenState] = useState(initialHistory);
  const setHistoryOpen = (open: boolean) => {
    setHistoryOpenState(open);
    try {
      localStorage.setItem(HISTORY_KEY, open ? "1" : "0");
    } catch {
      /* storage unavailable */
    }
  };
  const switching = useRef(false);
  const [switchingChat, setSwitchingChat] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [options, setOptions] = useState(false);
  const deleting = useRef(false);
  const [doomed, setDoomed] = useState<{ id: string; title: string }>();
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [source, setSource] = useState<unknown>();
  const composer = useRef<HTMLTextAreaElement>(null);
  const warm = useWarmModel(chat.id);
  const results = useResource(
    () =>
      call<{ id: string; title: string; excerpt?: string }[]>("chat.search", {
        query: debouncedSearch,
      }),
    ["chats"],
    debouncedSearch,
  );
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 200);
    return () => clearTimeout(timer);
  }, [search]);
  const end = useRef<HTMLDivElement>(null);
  const conversations: { id: string; title: string; excerpt?: string; updated_at?: string; last?: string }[] =
    results.data || snapshot.chats;
  // Grove: the list is grouped by day (Today, Yesterday, weekday, date).
  const groups: { label: string; items: typeof conversations }[] = [];
  for (const c of conversations) {
    const label = debouncedSearch ? "Results" : dayGroup(c.updated_at);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(c);
    else groups.push({ label, items: [c] });
  }
  useEffect(
    () => () => {
      if (deleting.current) return;
      // Navigation must flush the last edit even before the debounce has fired.
      void call("chat.draft", {
        chat_id: chat.id,
        text: latestDraft.current,
      }).catch(report);
    },
    [],
  );
  useEffect(() => {
    setDraft(chat.draft || "");
  }, [chat.id]);
  useEffect(() => {
    const timer = setTimeout(() => {
      if (deleting.current) return;
      void call("chat.draft", { chat_id: chat.id, text: draft }).catch(report);
    }, 350);
    return () => clearTimeout(timer);
  }, [draft, chat.id]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [chat.partial, chat.messages.length]);
  const send = () => {
    if (!draft.trim() || busy || switching.current) return;
    const text = draft;
    setDraft("");
    latestDraft.current = "";
    setChat({ ...chat, draft: "" });
    void submit(text, researchMode || undefined);
  };
  const updateDraft = (text: string) => {
    setDraft(text);
    latestDraft.current = text;
    setChat({ ...chat, draft: text });
  };
  const changeConversation = async (method: "chat.new" | "chat.select", args: Record<string, unknown>, closeAfter: boolean) => {
    if (switching.current) return;
    switching.current = true;
    setSwitchingChat(true);
    try {
      const value = await call<ChatRecord>(method, args);
      setChat(value);
      if (closeAfter && overlaying()) setHistoryOpen(false);
    } catch (error) {
      report(error);
    } finally {
      switching.current = false;
      setSwitchingChat(false);
    }
  };
  const newChat = (closeAfter: boolean) => void changeConversation("chat.new", {}, closeAfter);
  // Deleting the open conversation must not flush its draft afterwards (the
  // view remounts for the next conversation), so the guard only lifts when
  // the delete fails.
  const deleteConversation = async (id: string) => {
    const current = id === chat.id;
    if (current) deleting.current = true;
    try {
      setChat(await call<ChatRecord>("chat.delete", { chat_id: id }));
    } catch (error) {
      if (current) deleting.current = false;
      throw error;
    }
  };
  const preset = snapshot.presets?.find((p) => p.id === chat.preset);
  const attachedCount = (chat.documents?.length || 0) + (chat.images?.length || 0);
  // Matches the runtime rule: images go only to DEEP or a vision-capable model.
  const visionBlocked =
    (chat.images?.length || 0) > 0 && chat.preset !== "deep" && Boolean(preset) && !preset?.capabilities?.includes("vision");
  return (
    <div className="chat-layout ws" data-history={historyOpen}>
      {historyOpen && (
        <div
          className="history-scrim"
          aria-hidden="true"
          onClick={() => setHistoryOpen(false)}
        />
      )}
      <aside className="conversation-list ws-rail" aria-label="Conversation history" hidden={!historyOpen}>
        <div className="ws-rail-head">
          <h2>Chats</h2>
          <button
            className="icon-button"
            aria-label="New chat"
            title="New conversation"
            onClick={() => newChat(true)}
          >
            <Plus size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="Close conversation history"
            title="Close"
            onClick={() => setHistoryOpen(false)}
          >
            <X size={17} />
          </button>
        </div>
        <div className="conversation-search">
          <label className="search">
            <Search size={15} />
            <input
              aria-label="Search conversations"
              placeholder="Search chats"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
        <div className="conversation-items ws-rail-scroll">
          {groups.map((group) => (
            <div className="conversation-group" key={group.label} role="group" aria-label={group.label}>
              <p className="conversation-day" aria-hidden="true">{group.label}</p>
              {group.items.map((c) => (
                <div className="conversation-row" key={c.id}>
                  <button
                    className={`conversation-open ${c.id === chat.id ? "selected" : ""}`}
                    aria-current={c.id === chat.id ? "true" : undefined}
                    aria-label={c.title}
                    aria-description={c.excerpt || c.last || undefined}
                    disabled={switchingChat}
                    onClick={() => void changeConversation("chat.select", { chat_id: c.id }, true)}
                  >
                    <span className="conversation-title" title={c.title}>{c.title}</span>
                    {(c.excerpt || c.last) && <span className="small muted">{c.excerpt || c.last}</span>}
                  </button>
                  <button
                    className="conversation-delete"
                    aria-label={`Delete ${c.title}`}
                    title="Delete chat"
                    disabled={switchingChat}
                    onClick={() => setDoomed({ id: c.id, title: c.title })}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
          ))}
          {!conversations.length && (
            <p className="conversation-none">
              {debouncedSearch ? "No conversation matches that search." : "No conversations yet."}
            </p>
          )}
        </div>
        <p className="ws-rail-foot">Your conversations stay on this device.</p>
      </aside>
      <section
        className={dragging ? "conversation file-drop-active" : "conversation"}
        onDragOver={(event) => {
          if (event.dataTransfer.types.includes("Files")) {
            event.preventDefault();
            event.dataTransfer.dropEffect = attaching || busy ? "none" : "copy";
            setDragging(true);
          }
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node))
            setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (attaching || busy) return;
          const files = Array.from(event.dataTransfer.files);
          if (!files.length) return;
          setAttaching(true);
          void window.olive
            .attachFiles(chat.id, files)
            .catch(report)
            .finally(() => setAttaching(false));
        }}
      >
        {(dragging || attaching) && (
          <p role="status" className="drop-notice">
            {attaching
              ? "Attaching local files…"
              : busy
                ? "Finish the current request before attaching files."
                : "Drop local files to attach to this conversation."}
          </p>
        )}
        <header className="workspace-header chat-head">
          <div className="chat-head-left">
            <button
              className="icon-button chat-history-toggle"
              aria-pressed={historyOpen}
              aria-label="Conversation history"
              title={historyOpen ? "Hide conversation history" : "Show conversation history"}
              onClick={() => setHistoryOpen(!historyOpen)}
            >
              {historyOpen ? <PanelLeftClose size={17} aria-hidden="true" /> : <PanelLeftOpen size={17} aria-hidden="true" />}
            </button>
            <button
              className="icon-button chat-new"
              aria-label="New chat"
              title="New conversation"
              onClick={() => newChat(false)}
            >
              <Plus size={17} aria-hidden="true" />
            </button>
            <div className="chat-title">
              <h2 title={chat.title}>{chat.title}</h2>
              <span className="small muted">
                {chat.messages.length
                  ? `${chat.messages.length} message${chat.messages.length === 1 ? "" : "s"}`
                  : "New conversation"}
                {attachedCount ? ` · ${attachedCount} attached` : ""}
                {preset ? ` · ${preset.name}` : ""}
              </span>
            </div>
          </div>
          <div className="row chat-tools">
            <button
              className="quiet"
              disabled={busy}
              title="Attach local files to this conversation"
              aria-label="Attach files"
              onClick={() =>
                void window.olive
                  .fileAction({ action: "attach", chat_id: chat.id })
                  .then(() => call<ChatRecord>("chat.get", { chat_id: chat.id }))
                  .then(setChat)
                  .catch(report)
              }
            >
              <Paperclip size={15} aria-hidden="true" />
              <span className="label">Attach files</span>
            </button>
            <button className="quiet" aria-label="Conversation options" title="Conversation options" onClick={() => setOptions(true)}>
              <SlidersHorizontal size={15} aria-hidden="true" />
              <span className="label">Conversation options</span>
            </button>
            <details>
              <summary aria-label="More attachment options" title="More">
                <MoreHorizontal size={15} aria-hidden="true" />
              </summary>
              <div>
                <button
                  disabled={busy}
                  onClick={() =>
                    void window.olive
                      .fileAction({
                        action: "attach",
                        chat_id: chat.id,
                        permanent: true,
                      })
                      .then(() =>
                        call<ChatRecord>("chat.get", { chat_id: chat.id }),
                      )
                      .then(setChat)
                      .catch(report)
                  }
                >
                  Add files to permanent Knowledge
                </button>
              </div>
            </details>
          </div>
        </header>
        {chat.run_on && (
          <div className="notice chat-notice" data-tone="ai" role="note">
            <Info size={14} aria-hidden="true" />
            <span className="grow">Remote AI shares up to 24 visible messages with the selected paired device. Text only; no attachments, tools or private context. Failures require an explicit retry or a change to This device.</span>
          </div>
        )}
        {chat.preset === "reimagine" && (
          <div className="notice chat-notice" role="note">
            <Info size={14} aria-hidden="true" />
            <span className="grow">REIMAGINE uses media tools. Raster edits are local; generation needs a configured engine.</span>
            <button className="compact" onClick={() => setMediaOpen(true)}>Open media tools</button>
          </div>
        )}
        {visionBlocked && preset && (
          <div className="notice chat-notice" data-tone="warning" role="status">
            <AlertTriangle size={14} aria-hidden="true" />
            <span className="grow">{preset.name} can&apos;t see images. OLIVE will not send the picture to it; sending is refused until you switch to a vision-capable preset or remove the image.</span>
            <button
              className="compact"
              disabled={busy}
              onClick={() =>
                void call<ChatRecord>("chat.preset", { chat_id: chat.id, preset: "deep" })
                  .then(setChat)
                  .catch(report)
              }
            >
              Use OLIVE DEEP
            </button>
            <button
              className="compact quiet"
              disabled={busy}
              onClick={() =>
                void Promise.all((chat.images || []).map((_, index, all) => call<ChatRecord>("chat.remove_image", { chat_id: chat.id, index: all.length - 1 - index })))
                  .then((values) => { const last = values.at(-1); if (last) setChat(last); })
                  .catch(report)
              }
            >
              Remove image
            </button>
          </div>
        )}
        <MediaTools open={mediaOpen} close={setMediaOpen}/>
        <div className="messages">
          {!chat.messages.length && (
            <div className="empty-chat">
              <Core />
              <h1>A place to think out loud.</h1>
              <p className="muted">
                Ask a question, explore an idea, or tell OLIVE what you want to
                do. Choose the preset and where it runs below the message box.
              </p>
              <div className="chat-starters" aria-label="Starting points">
                {STARTERS.map((starter) => (
                  <button
                    key={starter.label}
                    type="button"
                    className="ws-chip"
                    onClick={() => {
                      updateDraft(starter.text);
                      composer.current?.focus();
                    }}
                  >
                    <starter.icon size={14} aria-hidden="true" />
                    {starter.label}
                  </button>
                ))}
              </div>
              <p className="chat-starters-note">
                <Clip size={12} aria-hidden="true" />
                Drop files anywhere here to attach them to this conversation.
              </p>
            </div>
          )}
          {chat.messages.map((m, index) => (
            <article className={`message message-${m.role}`} key={m.id}>
              {m.role === "user" ? (
                <div className="message-label sr-only">You</div>
              ) : (
                <div className="message-label message-attribution">
                  <OliveLogo className="olive-mark" />
                  <b>OLIVE</b>
                  {messageAttribution(m.provider) && <span className="attribution-meta">{messageAttribution(m.provider)}</span>}
                </div>
              )}
              <div className="message-body">
                <Markdown text={m.content} />
                {m.completion_state === "incomplete" && <p className="message-partial" role="status"><span className="ws-pill" data-tone="warning">Stopped · partial answer kept</span> Incomplete response — generation stopped or failed. The partial text is retained; nothing was retried.</p>}
                {m.completion_state === "unverified" && <p className="small">Saved alternate response — completion status was not recorded.</p>}
              </div>
              {m.sources?.length > 0 && (
                <div className="chips">
                  {m.sources.map((s, i) => (
                    <button
                      className="chip"
                      key={i}
                      onClick={() => setSource(s)}
                    >
                      {s.label || s.name || `Source ${i + 1}`}
                    </button>
                  ))}
                </div>
              )}
              <div className="message-actions">
                <CopyButton text={m.content} label="Copy message" iconOnly />
                {m.role === "assistant" &&
                  index === chat.messages.length - 1 && (
                    <button
                      className="icon-button"
                      aria-label="Regenerate response"
                      disabled={busy}
                      onClick={() =>
                        void call("chat.regenerate", {
                          chat_id: chat.id,
                        }).catch(report)
                      }
                    >
                      <RotateCcw size={14} />
                    </button>
                  )}
                {m.role === "assistant" &&
                  (chat.response_branches?.[String(index - 1)]?.length || 0) >
                    1 && (
                    <>
                      <button
                        className="icon-button"
                        disabled={busy}
                        title="Previous response branch"
                        aria-label="Previous response branch"
                        onClick={() =>
                          void call<ChatRecord>("chat.branch", {
                            chat_id: chat.id,
                            user_index: index - 1,
                            direction: -1,
                          })
                            .then(setChat)
                            .catch(report)
                        }
                      >
                        <ChevronLeft size={14} aria-hidden="true" />
                      </button>
                      <span className="small muted">
                        {(chat.branch_index?.[String(index - 1)] ??
                          chat.response_branches![String(index - 1)].length -
                            1) + 1}{" "}
                        / {chat.response_branches![String(index - 1)].length}
                      </span>
                      <button
                        className="icon-button"
                        disabled={busy}
                        title="Next response branch"
                        aria-label="Next response branch"
                        onClick={() =>
                          void call<ChatRecord>("chat.branch", {
                            chat_id: chat.id,
                            user_index: index - 1,
                            direction: 1,
                          })
                            .then(setChat)
                            .catch(report)
                        }
                      >
                        <ChevronRight size={14} aria-hidden="true" />
                      </button>
                    </>
                  )}
              </div>
            </article>
          ))}
          {chat.partial && (
            <article className="message message-assistant">
              <div className="message-label message-attribution message-writing">
                <OliveLogo className="olive-mark" />
                <span>OLIVE · writing</span>
              </div>
              <div className="message-body">
                <Markdown text={chat.partial} />
                <span className="stream-caret" aria-hidden="true" />
              </div>
            </article>
          )}
          {chat.generating && <RemoteAttribution provider={chat.remote_provider} complete={false}/>}
          <div ref={end} />
        </div>
        <div className="chat-composer">
          <NativeProposals chat={chat} onChanged={setChat}/>
          <ResearchEvidence chatId={chat.id} sessionIds={chat.research_session_ids || []} report={report}/>
          {attachedCount > 0 && (
            <div className="chips chat-attachments" aria-label="Attachments">
              {chat.documents?.map((d) => (
                <span className="chip" key={d.id}>
                  <FileText size={12} aria-hidden="true" />
                  {d.name}
                  {!!d.unreadable_pages?.length && <span> · {d.unreadable_pages.length} pages without text; ask DEEP about a specific page</span>}
                  <button
                    disabled={busy}
                    aria-label={`Remove attachment ${d.name}`}
                    onClick={() =>
                      void call("knowledge.remove", {
                        chat_id: chat.id,
                        document_id: d.id,
                      })
                        .then(() =>
                          call<ChatRecord>("chat.get", { chat_id: chat.id }),
                        )
                        .then(setChat)
                        .catch(report)
                    }
                  >
                    Remove
                  </button>
                </span>
              ))}
              {chat.images?.map((image, index) => (
                <span className="chip" key={index}>
                  {image.name}
                  <button
                    disabled={busy}
                    aria-label={`Remove image ${image.name}`}
                    onClick={() =>
                      void call<ChatRecord>("chat.remove_image", {
                        chat_id: chat.id,
                        index,
                      })
                        .then(setChat)
                        .catch(report)
                    }
                  >
                    Remove image
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="composer">
            <GrowingComposer
              ref={composer}
              aria-label="Message OLIVE"
              placeholder={researchMode === "Deep" ? "What should OLIVE research?" : researchMode === "Quick" ? "Ask, and OLIVE will search the web…" : "Ask, explore, or get something done…"}
              value={draft}
              onChange={(e) => {
                updateDraft(e.target.value);
                warm();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <div className="composer-bottom">
              <div className="composer-tools">
                <button
                  className="icon-button"
                  disabled={busy}
                  aria-label="Attach files to this message"
                  title="Attach local files"
                  onClick={() =>
                    void window.olive
                      .fileAction({ action: "attach", chat_id: chat.id })
                      .then(() => call<ChatRecord>("chat.get", { chat_id: chat.id }))
                      .then(setChat)
                      .catch(report)
                  }
                >
                  <Paperclip size={16} aria-hidden="true" />
                </button>
                <div className="chat-tool-group" role="group" aria-label="Model and mode">
                  <label className="chat-tool">
                    <Globe size={14} aria-hidden="true" />
                    <select aria-label="Research mode" value={researchMode} disabled={busy} onChange={e => setResearchMode(e.target.value as "" | "Quick" | "Deep")}>
                      <option value="">Chat</option><option value="Quick">Search web</option><option value="Deep">Research thoroughly</option>
                    </select>
                  </label>
                  <label className="chat-tool">
                    <Sparkles size={14} aria-hidden="true" />
                    <select
                      aria-label="OLIVE preset"
                      title={preset?.description || "Previous provider selection is preserved; inspect it in Advanced Settings"}
                      value={chat.preset || ""}
                      disabled={busy}
                      onChange={(e) =>
                        void call<ChatRecord>("chat.preset", {
                          chat_id: chat.id,
                          preset: e.target.value as "fast" | "normal" | "max" | "deep" | "reimagine",
                        })
                          .then(setChat)
                          .catch(report)
                      }
                    >
                      {!chat.preset && <option value="" disabled>Previous selection · Advanced</option>}
                      {snapshot.presets?.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}{chat.run_on ? (["deep", "reimagine"].includes(m.id) ? " · Unavailable remotely" : "") : m.status !== "Ready" ? ` · ${m.status}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <span className="chat-tool-divider" aria-hidden="true" />
                <RemoteTarget chat={chat} busy={busy} changed={setChat} report={report}/>
              </div>
              <span className="composer-hint">
                {busy
                  ? chat.remote_provider ? `Thinking on ${chat.remote_provider.device_name}…` : "OLIVE is working…"
                  : chat.run_on
                    ? "DEEP and REIMAGINE are unavailable on paired devices"
                    : "Enter to send · Shift+Enter for a new line"}
              </span>
              <button
                className="send"
                aria-label={busy ? "Stop response" : "Send message"}
                disabled={!busy && (switchingChat || !draft.trim())}
                onClick={busy ? cancel : send}
              >
                {busy ? <Square size={14} aria-hidden="true" /> : <ArrowUp size={16} aria-hidden="true" />}
              </button>
            </div>
          </div>
          {chat.pending_draft && (
            <details className="chat-pending">
              <summary>
                Pending action · {chat.pending_draft.state.replaceAll("_", " ")}
              </summary>
              {Object.entries(chat.pending_draft.entities || {})
                .filter(([key]) =>
                  [
                    "application",
                    "recipient",
                    "destination",
                    "message",
                    "subject",
                    "path",
                  ].includes(key),
                )
                .map(([key, value]) => (
                  <p key={key}>
                    <strong>{key}: </strong>
                    {String(value)}
                  </p>
                ))}
              <p>
                Corrections and cancellation use the same conversation context.
                This preview does not authorise execution.
              </p>
              <Details value={chat.pending_draft} />
            </details>
          )}
        </div>
      </section>
      {options && (
        <ConversationOptions
          chat={chat}
          open={options}
          onOpenChange={setOptions}
          busy={busy}
          setChat={setChat}
          report={report}
          beforeDelete={(value) => {
            deleting.current = value;
          }}
        />
      )}
      <ConfirmDialog
        open={doomed !== undefined}
        onOpenChange={(open) => {
          if (!open) setDoomed(undefined);
        }}
        title="Delete this chat?"
        confirmLabel="Delete chat"
        onConfirm={() => deleteConversation(doomed!.id)}
      >
        <strong>{doomed?.title}</strong> and its document indexes will be removed from this device. Attached original files are kept.
      </ConfirmDialog>
      <Sheet
        open={source !== undefined}
        onOpenChange={(open) => {
          if (!open) setSource(undefined);
        }}
        title="Message source"
        description="Provenance recorded for this response."
      >
        <Details value={source} title="Source evidence" />
      </Sheet>
    </div>
  );
}

/** "Today", "Yesterday", a weekday within the week, otherwise a short date. */
export function dayGroup(value?: string, now = new Date()): string {
  if (!value) return "Earlier";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Earlier";
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((start(now) - start(date)) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return date.toLocaleDateString([], { weekday: "long" });
  return date.toLocaleDateString([], { day: "numeric", month: "short", ...(date.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }) });
}
