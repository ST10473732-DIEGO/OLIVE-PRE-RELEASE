import { useEffect, useRef, useState } from "react";
import {
  Plus,
  Search,
  Upload,
  Settings,
  ArrowLeft,
  RefreshCw,
  Inbox,
  FileText,
  Send,
  Archive,
  Trash2,
  Folder,
  Clock,
  CalendarDays,
  Paperclip,
  Mail as MailIcon,
  MailOpen,
  Star,
  SlidersHorizontal,
  Reply,
  ReplyAll,
  Forward,
  X,
} from "lucide-react";
const folderIcons: Record<string, typeof Inbox> = {
  Inbox,
  Drafts: FileText,
  Outbox: Clock,
  Sent: Send,
  Archive,
  Trash: Trash2,
};
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { WorkspacePage, Details, Rail, Main, EmptyState, Notice, Pager } from "../../components/WorkspacePage";
import { Sheet } from "../../components/Sheet";
import { Feedback, useOperation } from "../personal/shared";
import Composer from "./Composer";
import SafeBody from "./SafeBody";
import Thread from "./Thread";
import { RemoteMessageActions, ServerTools } from "./RemoteActions";
import { ProjectSelect } from "../personal/shared";
import MailConnections from "./MailConnections";
import NativeProposal, { FromCalendar } from "./NativeProposal";
import { outcomeLabel } from "./types";
import type {
  MailRecord,
  Connection,
  Submission,
  ImportPreview,
} from "./types";
import "./mail.css";

export default function Mail({
  target,
}: {
  target?: { id: string; revision: number };
}) {
  const [folder, setFolder] = useState("Inbox"),
    [connection, setConnection] = useState(""),
    [query, setQuery] = useState(""),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<MailRecord>(),
    [settings, setSettings] = useState(false),
    [preview, setPreview] = useState<ImportPreview>();
  const [proposal, setProposal] = useState<"event" | "task">(),
    [fromCalendar, setFromCalendar] = useState(false);
  const [localFolder, setLocalFolder] = useState("");
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [syncResult, setSyncResult] = useState<{
    state: string;
    message?: string;
    count?: number;
    category?: string;
  }>();
  const flush = useRef<(() => Promise<MailRecord>) | null>(null);
  const [handoffError, setHandoffError] = useState("");
  useEffect(() => window.olive.subscribe(event => {
    if (event.topic !== "mail.progress") return;
    const value = event.data as {connection_id: string; state: string; count: number; message: string};
    if (value.connection_id === connection) setSyncResult(value);
  }), [connection]);
  useEffect(() => {
    if (!target) return;
    let cancelled = false;
    void (async () => {
      await flush.current?.();
      const record = await call<MailRecord>("mail.get", {
        record_id: target.id,
      });
      if (!cancelled) {
        setSelected(record);
        setHandoffError("");
      }
    })().catch((e) => {
      if (!cancelled) setHandoffError(String(e));
    });
    return () => {
      cancelled = true;
    };
  }, [target]);
  const r = useResource(
    () =>
      call<{ items: MailRecord[]; total: number; scope: string }>(
        "mail.search",
        {
          folder,
          connection_id: connection,
          query,
          limit: 50,
          offset,
          filters,
        },
      ),
    ["mail.changed"],
    JSON.stringify([folder, connection, query, offset, filters]),
  );
  const folders = useResource(
    () =>
      call<{
        items: {
          id: string;
          name: string;
          connection_id: string;
          count?: number;
          role?: string;
        }[];
      }>("mail.folders", {connection_id: connection}),
    ["mail.changed"],
    connection,
  );
  const connections = useResource(
    () => call<{ items: Connection[] }>("mail.connections", {}),
    ["mail.changed"],
  );
  const outbox = useResource(
    () => call<{ items: Submission[] }>("mail.outbox", {}),
    ["mail.changed"],
  );
  const op = useOperation(r.refresh);
  const open = (id: string) =>
    void op.run(async () => {
      await flush.current?.();
      setSelected(await call<MailRecord>("mail.get", { record_id: id }));
    }, "");
  const update = (changes: Record<string, unknown>) => {
    if (selected)
      void op.run(
        async () =>
          setSelected(
            await call<MailRecord>("mail.update", {
              record_id: selected.id,
              revision: selected.revision,
              changes,
            }),
          ),
        "Local mail state updated.",
      );
  };
  const compose = () =>
    void op.run(async () => {
      await flush.current?.();
      setSelected(
        await call<MailRecord>("mail.save_draft", {
          body: {
            to: [],
            cc: [],
            bcc: [],
            subject: "",
            text: "",
            connection_id: connection,
          },
        }),
      );
      setFolder("Drafts");
    }, "Local draft created.");
  const reply = (mode: string) => {
    if (selected)
      void op.run(
        async () =>
          setSelected(
            await call<MailRecord>("mail.reply", {
              record_id: selected.id,
              mode,
            }),
          ),
        "Unsent draft created.",
      );
  };
  const total = r.data?.total ?? 0;
  const folderLabel = !connection && folder === "Inbox" ? "All Inboxes" : folder;
  const accountName = connection
    ? connections.data?.items.find((c) => c.id === connection)?.name || "Account"
    : "All accounts";
  const railFolders = folders.data?.items.filter(
    (f) => !f.connection_id || (f.connection_id === connection && !["Inbox", "Sent", "Drafts", "Archive", "Spam", "Trash"].includes(f.role || "")),
  );
  const listStatus = r.loading
    ? "Loading…"
    : `${total} message${total === 1 ? "" : "s"}${query ? " match" : ""}`;
  return (
    <WorkspacePage
      layout="fill"
      className={`mail ${selected ? "has-selection" : ""} ${selected?.kind === "draft" ? "composing" : ""} ${total > 0 ? "populated" : ""}`}
      icon={<MailIcon size={18} />}
      title="Mail"
      description="Local drafts, imports and cached mail. Server connections are optional."
      status={connections.data?.items.length ? `${connections.data.items.length} account${connections.data.items.length === 1 ? "" : "s"}` : "Local only"}
      statusTone={connections.data?.items.length ? "live" : "idle"}
      rail={
        <Rail title="Mailboxes" className="mail-folders" label="Mail folders">
          <select
            aria-label="Mail connection"
            value={connection}
            onChange={(e) => {
              setConnection(e.target.value);
              setSyncResult(undefined);
              setFolder("Inbox");
              setOffset(0);
            }}
          >
            <option value="">All accounts</option>
            {connections.data?.items.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <div className="mail-folder-list">
            {railFolders?.map((f) => (
              <button
                key={f.id}
                aria-current={folder === f.name ? "page" : undefined}
                className={`mail-folder ${folder === f.name ? "selected" : ""}`}
                onClick={() => {
                  setFolder(f.name);
                  setOffset(0);
                }}
              >
                {(() => {
                  const Icon = folderIcons[f.name] || Folder;
                  return <Icon size={15} aria-hidden="true" />;
                })()}
                <span className="grow">{!connection && f.name === "Inbox" ? "All Inboxes" : f.name}</span>
                {f.count !== undefined && f.count > 0 && (
                  <span className="mail-count">{f.count}</span>
                )}
              </button>
            ))}
          </div>
          {connection && (
            <div className="mail-server-actions">
              <p className="ws-eyebrow">Server</p>
              <button
                onClick={() =>
                  void op.run(
                    async () =>
                      setSyncResult(
                        await call("mail.sync", {
                          connection_id: connection,
                          folder,
                          limit: 50,
                        }),
                      ),
                    "",
                  )
                }
              >
                <RefreshCw size={14} aria-hidden="true" />
                Refresh server
              </button>
              <button
                className="quiet"
                onClick={() =>
                  void call("mail.cancel_sync", {
                    connection_id: connection,
                  })
                    .then((value) => setSyncResult(value as { state: string }))
                    .catch((e) => setHandoffError(String(e)))
                }
              >
                Stop sync
              </button>
            </div>
          )}
          <div className="mail-rail-more">
            <p className="ws-eyebrow">More</p>
            <button
              className="mail-folder"
              onClick={() =>
                void op.run(async () => {
                  await flush.current?.();
                  setFromCalendar(true);
                }, "")
              }
            >
              <CalendarDays size={15} aria-hidden="true" />
              <span className="grow">Draft from Calendar</span>
            </button>
            <details className="mail-local-folders">
              <summary>
                <Folder size={15} aria-hidden="true" />
                <span className="grow">Local folders</span>
              </summary>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void op.run(async () => {
                    await call("mail.create_folder", { name: localFolder });
                    setLocalFolder("");
                  }, "Local folder created.");
                }}
              >
                <input
                  aria-label="New local folder name"
                  placeholder="New folder name"
                  value={localFolder}
                  onChange={(e) => setLocalFolder(e.target.value)}
                  maxLength={100}
                />
                <button disabled={!localFolder.trim()}>Create folder</button>
              </form>
            </details>
          </div>
        </Rail>
      }
      side={
        <section className="ws-side mail-detail" aria-label="Mail detail">
          {selected ? (
            <>
              <button
                className="mail-back quiet"
                onClick={() =>
                  void op.run(async () => {
                    await flush.current?.();
                    setSelected(undefined);
                  }, "")
                }
              >
                <ArrowLeft size={16} />
                Back to messages
              </button>
              {selected.kind === "draft" ? (
                <Composer
                  key={selected.id}
                  initial={selected}
                  registerFlush={(fn) => {
                    flush.current = fn;
                  }}
                  connections={connections.data?.items || []}
                  onSaved={setSelected}
                  onClose={() => setSelected(undefined)}
                />
              ) : (
                <article className="mail-reading">
                  <header className="mail-reading-head">
                    <div className="mail-reading-title">
                      <h2>{selected.subject || "(No subject)"}</h2>
                      <div className="mail-reading-actions">
                        <button onClick={() => reply("reply")}>
                          <Reply size={14} aria-hidden="true" />
                          Reply
                        </button>
                        <button onClick={() => reply("reply_all")}>
                          <ReplyAll size={14} aria-hidden="true" />
                          Reply all
                        </button>
                        <button onClick={() => reply("forward")}>
                          <Forward size={14} aria-hidden="true" />
                          Forward
                        </button>
                        <button
                          className="icon-button"
                          aria-label="Close message"
                          title="Close"
                          onClick={() =>
                            void op.run(async () => {
                              await flush.current?.();
                              setSelected(undefined);
                            }, "")
                          }
                        >
                          <X size={16} aria-hidden="true" />
                        </button>
                      </div>
                    </div>
                    <dl className="mail-envelope">
                      <dt>From</dt>
                      <dd>{selected.from}</dd>
                      <dt>To</dt>
                      <dd>{selected.to.join(", ")}</dd>
                      {selected.cc.length > 0 && (
                        <>
                          <dt>CC</dt>
                          <dd>{selected.cc.join(", ")}</dd>
                        </>
                      )}
                      {!!selected.reply_to?.length && (
                        <>
                          <dt>Reply destination</dt>
                          <dd>{selected.reply_to?.join(", ")}</dd>
                        </>
                      )}
                      <dt>Account</dt>
                      <dd>{connections.data?.items.find(c => c.id === selected.connection_id)?.name || "Local import"}</dd>
                    </dl>
                    <Thread id={selected.id} open={open} />
                  </header>
                  <div className="mail-reading-tools">
                    <ProjectSelect
                      value={selected.project_id}
                      onChange={(project_id) => update({ project_id })}
                    />
                    <RemoteMessageActions
                      record={selected}
                      loaded={setSelected}
                    />
                    <details className="mail-actions">
                      <summary>
                        <SlidersHorizontal size={14} aria-hidden="true" />
                        More actions
                      </summary>
                      <div className="row wrap">
                        <button
                          onClick={() => update({ read: !selected.read })}
                        >
                          <MailOpen size={14} aria-hidden="true" />
                          Mark {selected.read ? "unread" : "read"}
                        </button>
                        <button
                          onClick={() => update({ starred: !selected.starred })}
                        >
                          <Star size={14} aria-hidden="true" />
                          {selected.starred ? "Unstar" : "Star"}
                        </button>
                        <button onClick={() => update({ folder: "Archive" })}>
                          <Archive size={14} aria-hidden="true" />
                          Archive locally
                        </button>
                        <button onClick={() => update({ folder: "Trash" })}>
                          <Trash2 size={14} aria-hidden="true" />
                          Move to local Trash
                        </button>
                        <label>
                          Move to local folder
                          <select
                            aria-label="Move to local folder"
                            value=""
                            onChange={(e) => {
                              if (e.target.value)
                                update({ folder: e.target.value });
                            }}
                          >
                            <option value="">Choose folder</option>
                            {folders.data?.items
                              .filter((f) => !f.connection_id)
                              .map((f) => (
                                <option key={f.id} value={f.name}>
                                  {f.name}
                                </option>
                              ))}
                          </select>
                        </label>
                        <button
                          onClick={() =>
                            void op.run(
                              () =>
                                call("mail.add_knowledge", {
                                  record_id: selected.id,
                                  revision: selected.revision,
                                }),
                              "Selected message added to local Knowledge; check index status.",
                            )
                          }
                        >
                          Review Add to Knowledge
                        </button>
                        <button
                          onClick={() =>
                            void op.run(
                              () =>
                                window.olive.fileAction({
                                  action: "mail-export",
                                  record_id: selected.id,
                                }),
                              "Exported readable personal mail content.",
                            )
                          }
                        >
                          Export EML
                        </button>
                      </div>
                    </details>
                  </div>
                  <SafeBody
                    key={selected.id}
                    record={selected}
                    onLoaded={setSelected}
                  />
                  <div className="mail-handoffs">
                    <p className="ws-eyebrow">Turn this into</p>
                    <div className="row wrap">
                      <button onClick={() => setProposal("event")}>
                        <CalendarDays size={14} aria-hidden="true" />
                        Create Calendar proposal
                      </button>
                      <button onClick={() => setProposal("task")}>
                        Create Task proposal
                      </button>
                    </div>
                  </div>
                  {!!selected.attachments.length && (
                    <section className="mail-attachment-list">
                      <h3>
                        <Paperclip size={14} aria-hidden="true" />
                        Attachments · {selected.attachments.length}
                      </h3>
                      {selected.attachments.map((a) => (
                        <div className="mail-attachment row spread" key={a.id}>
                          <span>
                            {a.name} · {a.size.toLocaleString()} bytes
                            <br />
                            <small>Untrusted content · {a.type}</small>
                          </span>
                          <button
                            onClick={() =>
                              void op.run(
                                () =>
                                  window.olive.fileAction({
                                    action: "mail-save-attachment",
                                    record_id: selected.id,
                                    attachment_id: a.id,
                                  }),
                                "Attachment saved. It was not opened or executed.",
                              )
                            }
                          >
                            Save as…
                          </button>
                          <button
                            onClick={() =>
                              void op.run(
                                () =>
                                  call("mail.add_knowledge", {
                                    record_id: selected.id,
                                    revision: selected.revision,
                                    attachment_id: a.id,
                                  }),
                                "Selected attachment added to local Knowledge; check index status.",
                              )
                            }
                          >
                            Add to Knowledge
                          </button>
                        </div>
                      ))}
                    </section>
                  )}
                  {!!selected.warnings?.length && (
                    <Details
                      title="Import limitations"
                      value={selected.warnings}
                    />
                  )}
                </article>
              )}
            </>
          ) : (
            <EmptyState
              className="mail-empty-detail"
              icon={<MailOpen size={24} />}
              title="Nothing open"
              actions={
                <>
                  <button onClick={compose}>
                    <Plus size={14} aria-hidden="true" />
                    New draft
                  </button>
                </>
              }
            >
              Choose a message from {folderLabel} to read it here. Nothing is sent without a reviewed submission.
            </EmptyState>
          )}
        </section>
      }
      actions={
        <>
          <button className="primary" onClick={compose}>
            <Plus size={16} aria-hidden="true" />
            Compose
          </button>
          <button
            onClick={() =>
              void op.run(async () => {
                await flush.current?.();
                const value = (await window.olive.fileAction({
                  action: "mail-import",
                })) as ImportPreview | null;
                if (value) setPreview(value);
              }, "")
            }
          >
            <Upload size={16} aria-hidden="true" />
            Import EML
          </button>
          <button
            className="icon-button"
            aria-label="Mail connections"
            title="Mail connections"
            onClick={() => setSettings(true)}
          >
            <Settings size={17} aria-hidden="true" />
          </button>
        </>
      }
    >
      <Main className="mail-list" label="Message list" pad={false}>
        <div className="mail-list-toolbar">
          <label className="search mail-search">
            <Search size={15} aria-hidden="true" />
            <input
              aria-label="Search local mail"
              placeholder={`Search ${folderLabel.toLowerCase()}`}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <details className="mail-filter">
            <summary>
              <SlidersHorizontal size={14} aria-hidden="true" />
              Search filters
              {Boolean(filters.read != null || filters.starred || filters.has_attachments || filters.after || filters.before) && <span className="ws-pill" data-tone="accent">on</span>}
            </summary>
            <div className="mail-filter-panel">
              <label>
                Read state
                <select
                  aria-label="Mail read filter"
                  value={filters.read == null ? "all" : String(filters.read)}
                  onChange={(e) => {
                    setOffset(0);
                    setFilters({
                      ...filters,
                      read:
                        e.target.value === "all"
                          ? null
                          : e.target.value === "true",
                    });
                  }}
                >
                  <option value="all">All</option>
                  <option value="true">Read</option>
                  <option value="false">Unread</option>
                </select>
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={filters.starred === true}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      starred: e.target.checked ? true : null,
                    })
                  }
                />
                Starred only
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={filters.has_attachments === true}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      has_attachments: e.target.checked ? true : null,
                    })
                  }
                />
                With attachments
              </label>
              <label>
                After
                <input
                  aria-label="Mail after date"
                  type="date"
                  onChange={(e) =>
                    setFilters({ ...filters, after: e.target.value })
                  }
                />
              </label>
              <label>
                Before
                <input
                  aria-label="Mail before date"
                  type="date"
                  onChange={(e) =>
                    setFilters({ ...filters, before: e.target.value })
                  }
                />
              </label>
            </div>
          </details>
        </div>
        <div className="mail-list-head">
          <h2>{folderLabel}</h2>
          <span className="mail-list-scope" title={r.data?.scope || "Local mail"}>
            {accountName} · {listStatus}
          </span>
        </div>
        <div className="mail-list-notices">
          <Feedback
            error={
              op.error ||
              r.error ||
              folders.error ||
              connections.error ||
              handoffError
            }
            notice={op.notice}
          />
          {syncResult && (
            <Notice tone="accent" icon={<RefreshCw size={15} />}>
              <p>
                <strong>{syncResult.state.replaceAll("_", " ")}</strong>
                {syncResult.message ? ` · ${syncResult.message}` : ""}
                {syncResult.count !== undefined
                  ? ` · ${syncResult.count} message${syncResult.count === 1 ? "" : "s"} cached`
                  : ""}
                {syncResult.category ? " · " + syncResult.category : ""}
              </p>
            </Notice>
          )}
          {connection && (
            <ServerTools
              connection={connection}
              folder={folder}
              query={query}
              open={open}
            />
          )}
        </div>
        <div className="mail-list-scroll">
          <Feedback loading={r.loading} />
          {!r.loading && r.data?.total === 0 && (
            <EmptyState
              className="mail-empty"
              icon={folder === "Inbox" ? <Inbox size={26} /> : <Folder size={26} />}
              title={
                folder === "Inbox"
                  ? "Your inbox starts here"
                  : `No messages in ${folder}`
              }
              actions={
                <>
                  <button className="primary" onClick={compose}>
                    <Plus size={14} aria-hidden="true" />
                    Compose a draft
                  </button>
                  <button
                    onClick={() =>
                      void op.run(async () => {
                        await flush.current?.();
                        const value = (await window.olive.fileAction({
                          action: "mail-import",
                        })) as ImportPreview | null;
                        if (value) setPreview(value);
                      }, "")
                    }
                  >
                    <Upload size={14} aria-hidden="true" />
                    Import an EML file
                  </button>
                  {!connections.data?.items.length && (
                    <button className="quiet" onClick={() => setSettings(true)}>
                      Connect an account
                    </button>
                  )}
                </>
              }
            >
              {query
                ? "Nothing here matches that search."
                : !connections.data?.items.length
                  ? "Local drafts and imported messages work without an account. Mail delivery is not configured."
                  : "Local drafts and imported messages work without an account."}
            </EmptyState>
          )}
          <div className="mail-items">
            {r.data?.items.map((m) => (
              <button
                key={m.id}
                className={`mail-list-item ${m.id === selected?.id ? "selected" : ""} ${m.read ? "" : "unread"}`}
                aria-current={m.id === selected?.id ? "true" : undefined}
                onClick={() => open(m.id)}
              >
                <span className="mail-item-mark" aria-hidden="true">
                  {m.kind === "draft" ? <FileText size={14} /> : m.read ? <MailOpen size={14} /> : <MailIcon size={14} />}
                </span>
                <span className="mail-item-text">
                  <span className="row spread">
                    <strong title={m.from || undefined}>
                      {m.kind === "draft" ? "Unsent draft" : m.from || "Unknown sender"}
                    </strong>
                    {!m.read && (
                      <span className="mail-unread" aria-label="Unread">
                        Unread
                      </span>
                    )}
                  </span>
                  <span className="mail-subject">{m.subject || "(No subject)"}</span>
                  <span className="mail-item-meta">
                    {m.connection_id && <small>{connections.data?.items.find(c => c.id === m.connection_id)?.name || "Account unavailable"}</small>}
                    {m.kind === "draft" && (m.to?.length ?? 0) > 0 && (
                      <small className="mail-recipients" title={"To: " + m.to.join(", ")}>
                        To: {m.to[0]}
                        {m.to.length > 1 ? ` +${m.to.length - 1}` : ""}
                      </small>
                    )}
                    {(m.attachments.length > 0 || m.remote_state) && (
                      <small>
                        {m.attachments.length > 0 && (
                          <>
                            <Paperclip size={11} aria-hidden="true" />{" "}
                            {m.attachments.length}
                          </>
                        )}
                        {m.remote_state
                          ? (m.attachments.length ? " · " : "") +
                            m.remote_state.replaceAll("_", " ")
                          : ""}
                      </small>
                    )}
                  </span>
                </span>
              </button>
            ))}
          </div>
          {r.data && r.data.total > 50 && (
            <Pager
              page={Math.floor(offset / 50) + 1}
              pages={Math.ceil(r.data.total / 50)}
              onPrevious={() => setOffset(Math.max(0, offset - 50))}
              onNext={() => setOffset(offset + 50)}
              total={r.data.total}
              noun="message"
            />
          )}
          {folder === "Outbox" &&
            outbox.data?.items.map((s) => (
              <article className="mail-outcome ws-card" key={s.id}>
                <h3>{outcomeLabel[s.state] || s.state}</h3>
                <p>{String(s.preview.subject || "(No subject)")}</p>
                <Details
                  value={{
                    accepted: s.accepted,
                    rejected: s.rejected,
                    category: s.category,
                  }}
                  title="Submission details"
                />
                <div className="ws-card-foot">
                  {Object.keys(s.rejected || {}).length > 0 &&
                    s.state !== "outcome_uncertain" && (
                      <button
                        onClick={() =>
                          void op.run(async () => {
                            await flush.current?.();
                            setSelected(
                              await call<MailRecord>("mail.retry_rejected", {
                                submission_id: s.id,
                              }),
                            );
                          }, "Unsent draft for rejected recipients only. Review before submitting.")
                        }
                      >
                        Draft retry for rejected recipients
                      </button>
                    )}
                  {["accepted", "partially_accepted"].includes(s.state) && (
                    <button
                      onClick={() =>
                        void op.run(
                          () => call("mail.sent_copy", { submission_id: s.id }),
                          "Sent-copy attempt recorded; submission was not repeated.",
                        )
                      }
                    >
                      Review Sent-folder copy
                    </button>
                  )}
                </div>
                {s.sent_copy_state && (
                  <p className="ws-card-sub">Sent copy: {s.sent_copy_state.replaceAll("_", " ")}</p>
                )}
              </article>
            ))}
        </div>
      </Main>
      <Sheet
        open={settings}
        onOpenChange={setSettings}
        title="Connections"
        description="Optional Mail infrastructure; no compulsory provider."
      >
        {settings && <MailConnections />}
      </Sheet>
      <Sheet
        open={!!proposal}
        onOpenChange={(open) => {
          if (!open) setProposal(undefined);
        }}
        title={proposal === "event" ? "Mail to Calendar" : "Mail to Tasks"}
        description="A reviewed, source-linked local record."
      >
        {proposal && selected && (
          <NativeProposal
            source={selected}
            kind={proposal}
            done={() => setProposal(undefined)}
          />
        )}
      </Sheet>
      <Sheet
        open={fromCalendar}
        onOpenChange={setFromCalendar}
        title="Calendar to Mail"
        description="Create an unsent local draft."
      >
        {fromCalendar && (
          <FromCalendar
            selected={(r) => {
              setSelected(r);
              setFromCalendar(false);
            }}
          />
        )}
      </Sheet>
      <Sheet
        open={!!preview}
        onOpenChange={(open) => {
          if (!open && preview) {
            void call("mail.import_cancel", { preview_id: preview.preview_id });
            setPreview(undefined);
          }
        }}
        title="Review EML import"
        description="Imported content is untrusted and cannot run actions or send messages."
      >
        {preview && (
          <>
            <h3>{preview.subject || "(No subject)"}</h3>
            <p>{preview.from}</p>
            <p>
              {preview.count} message · {preview.size.toLocaleString()} bytes ·{" "}
              {preview.attachments.length} attachments
            </p>
            {preview.duplicate_id && (
              <p>
                This exact message was already imported. It will not be
                duplicated.
              </p>
            )}
            {preview.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
            <button
              className="primary"
              disabled={op.busy}
              onClick={() =>
                void op.run(async () => {
                  const record = await call<MailRecord>("mail.import_commit", {
                    preview_id: preview.preview_id,
                    expected_hash: preview.hash,
                  });
                  setPreview(undefined);
                  setSelected(record);
                }, "Imported locally; nothing was sent.")
              }
            >
              Import this message
            </button>
            <Feedback error={op.error} />
          </>
        )}
      </Sheet>
    </WorkspacePage>
  );
}
