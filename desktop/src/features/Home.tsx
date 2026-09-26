import { GrowingComposer } from "../components/GrowingComposer";
import { useWarmModel } from "../services/warm";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUp,
  Bell,
  CalendarDays,
  Check,
  CheckCircle2,
  Circle,
  Code2,
  FilePenLine,
  Hand,
  Laptop,
  Library,
  Loader2,
  Mail as MailIcon,
  MessageSquare,
  Monitor,
  Smartphone,
  Square,
} from "lucide-react";
import { call, type Approval, type Chat as ChatRecord, type Snapshot } from "../services/api";
import { useResource } from "../services/useResource";
import type { ConnectSnapshotLike, RuntimeState } from "../services/runtimeState";
import type { CalendarEvent, PersonalTask, Profile } from "./personal/types";
import {
  activityLabel,
  attentionItems,
  countdown,
  firstRunSteps,
  greeting,
  type DueReminder,
} from "./home/homeModel";

interface Props {
  reduced: boolean;
  draft: string;
  setDraft: (text: string) => void;
  navigate: (id: string) => void;
  openRecord: (route: string, id: string) => void;
  submit: (text: string) => Promise<void>;
  snapshot: Snapshot | null;
  chat: ChatRecord | null;
  setChat: (chat: ChatRecord) => void;
  setActivity: (open: boolean) => void;
  busy: boolean;
  cancel: () => void;
  openChat: (chat: ChatRecord) => void;
  openStudio: (id: string) => void;
  report: (error: unknown) => void;
  approvals: Approval[];
  runtimeState: RuntimeState;
  connect: ConnectSnapshotLike | null;
}
type TodayData = {
  events: CalendarEvent[];
  tasks: PersonalTask[];
  reminders: DueReminder[];
  display_name: string;
  format: Pick<Profile, "timezone" | "locale" | "date_format" | "time_format">;
};
const RECENT_LIMIT = 4;
// Starting points that fill the composer for you to finish; none sends by itself.
const SUGGESTIONS: { icon: typeof Bell; text: string; fill: string }[] = [
  { icon: CalendarDays, text: "What does my week look like?", fill: "What does my week look like?" },
  { icon: Bell, text: "Remind me to…", fill: "Remind me to " },
  { icon: MailIcon, text: "Draft a reply to my latest email", fill: "Draft a reply to my latest email" },
  { icon: Library, text: "Search my documents for…", fill: "Search my documents for " },
];

// Home V2 answers "what matters now": ask, what needs you, what OLIVE is
// doing, where you left off, and today. Sections with nothing real to show
// disappear; nothing is estimated, padded or recommended.
export function HomePage({
  draft,
  setDraft,
  navigate,
  openRecord,
  submit,
  snapshot,
  chat,
  setChat,
  setActivity,
  busy,
  cancel,
  openChat,
  openStudio,
  report,
  approvals,
  runtimeState,
  connect,
}: Props) {
  const [showAllRecent, setShowAllRecent] = useState(false);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(timer);
  }, []);
  const today = useResource(() => call<TodayData>("personal.today", {}), ["personal.changed", "personal.reminders"]);
  const send = () => {
    if (!draft.trim() || !snapshot) return;
    setDraft("");
    navigate("chat");
    void submit(draft);
  };
  const recent = snapshot?.home.recent || [];
  const visibleRecent = showAllRecent ? recent : recent.slice(0, RECENT_LIMIT);
  const activityItems = snapshot?.activity?.items || [];
  const attention = attentionItems(approvals, today.data?.reminders || [], chat);
  const modelUnavailable =
    runtimeState.detail === "AI offline" || runtimeState.detail === "no model installed";
  const paired = (connect?.devices || []).filter((d) => d.trust_state === "paired");
  const steps = firstRunSteps(snapshot?.home.status.ollama, snapshot?.presets, paired.length);
  const firstRun = Boolean(snapshot) && !recent.length && steps.some((s) => !s.done && !s.optional);
  const preset = snapshot?.presets?.find((p) => p.id === chat?.preset);
  const warm = useWarmModel(chat?.id);
  const dateLine = now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
  return (
    <main className="home">
      <div className="home-main">
        <div className="home-column">
          <header className="home-top">
            <h1>{greeting(now)}{today.data?.display_name ? `, ${today.data.display_name}` : ""}</h1>
            <p>{dateLine}</p>
          </header>

          <section className="home-ask" aria-label="Ask OLIVE">
            <div className="composer home-composer grove-ask">
              <GrowingComposer
                aria-label="Ask OLIVE anything"
                placeholder="Ask OLIVE, or describe what you want done"
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
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
                {chat && snapshot?.presets && (
                  <label className="composer-picker">
                    <span className="sr-only">OLIVE preset</span>
                    <select
                      aria-label="OLIVE preset"
                      value={chat.preset || ""}
                      disabled={busy}
                      title={preset?.description}
                      onChange={(e) =>
                        void call<ChatRecord>("chat.preset", {
                          chat_id: chat.id,
                          preset: e.target.value as "fast" | "normal" | "max" | "deep" | "reimagine",
                        })
                          .then(setChat)
                          .catch(report)
                      }
                    >
                      {!chat.preset && <option value="" disabled>Previous selection</option>}
                      {snapshot.presets.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                          {p.status !== "Ready" && p.id !== "reimagine" ? ` · ${p.status}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <span className="composer-hint">
                  {modelUnavailable
                    ? `${runtimeState.detail} — replies need a local model`
                    : chat?.run_on
                      ? "Runs on the paired device chosen in Chat"
                      : "This device · Enter to send"}
                </span>
                <button
                  className="send"
                  aria-label={busy ? "Cancel request" : "Submit request"}
                  title={busy ? "Cancel request" : "Send (Enter)"}
                  disabled={!snapshot || (!busy && !draft.trim())}
                  onClick={() => (busy ? cancel() : send())}
                >
                  {busy ? <Square size={14} aria-hidden="true" /> : <ArrowUp size={16} aria-hidden="true" />}
                </button>
              </div>
            </div>
            <div className="home-suggest" aria-label="Suggestions">
              {SUGGESTIONS.map((item) => (
                <button
                  key={item.text}
                  onClick={() => {
                    setDraft(item.fill);
                    warm();
                    requestAnimationFrame(() => {
                      const box = document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Ask OLIVE anything"]');
                      box?.focus();
                      box?.setSelectionRange(item.fill.length, item.fill.length);
                    });
                  }}
                >
                  <item.icon size={14} aria-hidden="true" />
                  {item.text}
                </button>
              ))}
            </div>
          </section>

          {modelUnavailable && snapshot && (
            <div className="notice" data-tone="warning" role="status">
              <AlertTriangle size={15} aria-hidden="true" />
              <span className="grow">
                {runtimeState.full} Calendar, Tasks, Reminders, Studio, GO and Devices keep working.
              </span>
              <button className="compact" onClick={() => navigate("settings")}>
                Models
              </button>
            </div>
          )}

          {!snapshot && (
            <p className="home-loading" role="status">
              <Loader2 size={14} className="spin" aria-hidden="true" /> Loading your day…
            </p>
          )}

          {firstRun && (
            <section className="home-section" aria-label="Get started">
              <h2 className="home-heading">Get started</h2>
              <ul className="home-checklist">
                {steps.map((step) => (
                  <li key={step.id} data-done={step.done || undefined}>
                    {step.done ? <CheckCircle2 size={15} aria-hidden="true" /> : <Circle size={15} aria-hidden="true" />}
                    <span>{step.label}</span>
                    <span className="sr-only">{step.done ? "done" : "not done"}</span>
                    {!step.done && step.id === "model" && (
                      <button className="compact" onClick={() => navigate("settings")}>Models</button>
                    )}
                    {!step.done && step.id === "pair" && (
                      <button className="compact quiet" onClick={() => navigate("devices")}>Devices</button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {attention.length > 0 && (
            <section className="home-section" aria-label="Needs attention">
              <h2 className="home-heading">
                Needs attention <span className="count" data-tone="warning" aria-hidden="true">{attention.length}</span>
              </h2>
              <div className="home-rows">
                {attention.map((item) => (
                  <div className="home-row" key={item.id} data-kind={item.kind}>
                    <span className="home-row-icon" aria-hidden="true">
                      {item.kind === "approval" ? <Hand size={15} /> : item.kind === "reminder" ? <Bell size={15} /> : <FilePenLine size={15} />}
                    </span>
                    <span className="home-row-text">
                      <strong>{item.title}</strong>
                      <small>{item.detail}</small>
                    </span>
                    {item.kind === "approval" && (
                      <button className="compact" onClick={() => setActivity(true)}>Review…</button>
                    )}
                    {item.kind === "reminder" && (
                      <span className="home-row-actions">
                        <button
                          className="compact quiet"
                          onClick={() =>
                            void call("reminders.snooze", { delivery_id: item.id.slice(9), minutes: 10 }).then(today.refresh).catch(report)
                          }
                        >
                          Snooze 10 min
                        </button>
                        <button
                          className="compact"
                          onClick={() => void call("reminders.dismiss", { delivery_id: item.id.slice(9) }).then(today.refresh).catch(report)}
                        >
                          Dismiss
                        </button>
                      </span>
                    )}
                    {item.kind === "pending" && chat && (
                      <button className="compact" onClick={() => openChat(chat)}>Review…</button>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {activityItems.length > 0 && (
            <section className="home-section" aria-label="OLIVE is working on">
              <h2 className="home-heading">OLIVE is working on</h2>
              <div className="home-rows">
                {activityItems.map((item) => {
                  const label = activityLabel(item, snapshot?.chats || []);
                  return (
                    <button className="home-row" key={item.id} onClick={() => setActivity(true)}>
                      <span className="status-dot" data-tone="computing" aria-hidden="true" />
                      <span className="home-row-text">
                        <strong>{label.title}</strong>
                        <small>{label.detail} · running</small>
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {recent.length > 0 && (
            <section className="home-section" aria-label="Continue">
              <h2 className="home-heading">
                Continue
                {recent.length > RECENT_LIMIT && (
                  <button className="text-button" onClick={() => setShowAllRecent(!showAllRecent)}>
                    {showAllRecent ? "Show less" : `Show all ${recent.length}`}
                  </button>
                )}
              </h2>
              <div className="continue-grid">
                {visibleRecent.map((item) => (
                  <button
                    className="continue-row"
                    key={item.key}
                    title={item.title}
                    onClick={() => {
                      if (item.kind === "chat")
                        void call<ChatRecord>("chat.select", { chat_id: item.key })
                          .then(openChat)
                          .catch(report);
                      else openStudio(item.key);
                    }}
                  >
                    <span className="continue-kind">
                      {item.kind === "chat" ? <MessageSquare size={13} aria-hidden="true" /> : <Code2 size={13} aria-hidden="true" />}
                      {item.kind === "chat" ? "Chat" : "Studio"} · {item.subtitle}
                    </span>
                    <strong>{item.title}</strong>
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
      <TodayRail
        data={today.data}
        loading={!today.data && !today.error}
        error={today.error}
        now={now}
        navigate={navigate}
        openRecord={openRecord}
        refresh={today.refresh}
        report={report}
        connect={connect}
      />
    </main>
  );
}

function timeOf(value: string, format?: TodayData["format"]) {
  if (!value.includes("T")) return "All day";
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return value;
  try {
    return new Intl.DateTimeFormat(format?.locale || undefined, {
      timeZone: format?.timezone || undefined,
      hour: "2-digit",
      minute: "2-digit",
      hour12: format?.time_format === "12h",
    }).format(instant);
  } catch {
    return instant.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
}

function TodayRail({
  data,
  loading,
  error,
  now,
  navigate,
  openRecord,
  refresh,
  report,
  connect,
}: {
  data?: TodayData;
  loading: boolean;
  error: string;
  now: Date;
  navigate: (id: string) => void;
  openRecord: (route: string, id: string) => void;
  refresh: () => Promise<void>;
  report: (error: unknown) => void;
  connect: ConnectSnapshotLike | null;
}) {
  const events = useMemo(
    () => [...(data?.events || [])].sort((a, b) => (a.all_day === b.all_day ? a.start.localeCompare(b.start) : a.all_day ? -1 : 1)),
    [data?.events],
  );
  const timed = events.filter((e) => !e.all_day);
  const upcoming = timed.filter((e) => new Date(e.end || e.start).getTime() >= now.getTime());
  const next = upcoming.find((e) => new Date(e.start).getTime() > now.getTime()) || upcoming[0];
  const nowIndex = timed.findIndex((e) => new Date(e.start).getTime() > now.getTime());
  const tasks = data?.tasks || [];
  const devices = (connect?.devices || []).filter((d) => d.trust_state === "paired");
  return (
    <section className="home-today" aria-label="Native Today">
      <div className="home-today-head">
        <h2>Today</h2>
        <span>{now.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}</span>
      </div>
      {loading && (
        <p className="home-loading" role="status">
          <Loader2 size={14} className="spin" aria-hidden="true" /> Loading today…
        </p>
      )}
      {error && <p className="small muted">{error}</p>}
      {data && (
        <>
          {events.length ? (
            <ol className="today-timeline" aria-label="Agenda">
              {events.filter((e) => e.all_day).map((e) => (
                <li key={e.id + (e.occurrence_id || "")} className="tl-item" data-all-day="true">
                  <button onClick={() => openRecord("calendar", e.id)}>
                    <span className="tl-time">All day</span>
                    <span className="tl-rail" aria-hidden="true"><span className="tl-dot" /></span>
                    <span className="tl-text"><strong>{e.title}</strong>{e.location && <small>{e.location}</small>}</span>
                  </button>
                </li>
              ))}
              {timed.map((e, index) => {
                const past = new Date(e.end || e.start).getTime() < now.getTime();
                return (
                  <li key={e.id + (e.occurrence_id || "")} className="tl-group">
                    {index === (nowIndex < 0 ? -2 : nowIndex) && <NowMarker now={now} format={data.format} />}
                    <div className="tl-item" data-past={past || undefined}>
                      <button onClick={() => openRecord("calendar", e.id)}>
                        <span className="tl-time">{timeOf(e.start, data.format)}</span>
                        <span className="tl-rail" aria-hidden="true"><span className="tl-dot" /></span>
                        <span className="tl-text">
                          <strong>{e.title}</strong>
                          <small>
                            {e === next ? countdown(e.start, now) : `${timeOf(e.start, data.format)}${e.end ? `–${timeOf(e.end, data.format)}` : ""}`}
                            {e.location ? ` · ${e.location}` : ""}
                          </small>
                        </span>
                      </button>
                    </div>
                  </li>
                );
              })}
              {nowIndex < 0 && timed.length > 0 && (
                <li className="tl-group"><NowMarker now={now} format={data.format} /></li>
              )}
            </ol>
          ) : (
            <p className="today-empty-line">No events today.</p>
          )}
          {events.length > 0 && !upcoming.length && !events.some((e) => e.all_day) && (
            <p className="today-empty-line">No more events today.</p>
          )}
          <div className="today-group">
            <h3>
              Tasks due {tasks.length > 0 && <span className="count" data-tone="neutral" aria-hidden="true">{tasks.length}</span>}
            </h3>
            {tasks.length ? (
              <ul className="today-tasks" aria-label="Tasks due">
                {tasks.map((t) => {
                  const done = t.status === "completed";
                  return (
                    <li key={t.id} data-done={done || undefined}>
                      <button
                        className="today-check"
                        role="checkbox"
                        aria-checked={done}
                        aria-label={`${done ? "Reopen" : "Complete"} ${t.title}`}
                        onClick={() =>
                          void call(done ? "tasks.reopen" : "tasks.complete", { record_id: t.id, revision: t.revision })
                            .then(refresh)
                            .catch(report)
                        }
                      >
                        {done && <Check size={11} aria-hidden="true" />}
                      </button>
                      <button className="today-task" onClick={() => openRecord("tasks", t.id)}>
                        {t.title}
                      </button>
                      {t.due?.includes("T") && <span className="today-time">{timeOf(t.due, data.format)}</span>}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="today-empty-line">Nothing due today.</p>
            )}
          </div>
        </>
      )}
      <div className="today-group">
        <h3>Devices</h3>
        {!connect?.network ? (
          <p className="today-empty-line">Connect status unavailable.</p>
        ) : connect.network.state !== "on" ? (
          <p className="today-empty-line">
            Connect is off. <button className="inline-link" onClick={() => navigate("devices")}>Devices</button>
          </p>
        ) : devices.length === 0 ? (
          <p className="today-empty-line">
            No paired devices. <button className="inline-link" onClick={() => navigate("devices")}>Pair a device</button>
          </p>
        ) : (
          <ul className="today-devices" aria-label="Paired devices">
            {devices.map((d) => {
              const online = d.live?.state === "online";
              return (
                <li key={d.device_id}>
                  <button onClick={() => navigate("devices")}>
                    {d.device_class === "phone" || d.device_class === "tablet" ? <Smartphone size={14} aria-hidden="true" /> : d.device_class === "laptop" ? <Laptop size={14} aria-hidden="true" /> : <Monitor size={14} aria-hidden="true" />}
                    <span className="today-title">
                      {d.display_name}
                      <small>{online ? "Online" : "Offline"}</small>
                    </span>
                    <span className="status-dot" data-tone={online ? "online" : "offline"} aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="today-links">
        <button className="quiet compact" onClick={() => navigate("calendar")}><CalendarDays size={13} aria-hidden="true" /> Calendar</button>
        <button className="quiet compact" onClick={() => navigate("tasks")}><Check size={13} aria-hidden="true" /> Tasks</button>
        <button className="quiet compact" onClick={() => navigate("reminders")}><Bell size={13} aria-hidden="true" /> Reminders</button>
      </div>
    </section>
  );
}

function NowMarker({ now, format }: { now: Date; format?: TodayData["format"] }) {
  return (
    <div className="tl-now" aria-label={`Now, ${timeOf(now.toISOString(), format)}`}>
      <span className="tl-time">{timeOf(now.toISOString(), format)}</span>
      <span className="tl-now-dot" aria-hidden="true" />
      <span className="tl-now-line" aria-hidden="true" />
    </div>
  );
}
