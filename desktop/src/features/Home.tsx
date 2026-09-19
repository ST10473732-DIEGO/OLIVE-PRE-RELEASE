import { GrowingComposer } from "../components/GrowingComposer";
import Today from "./personal/Today";
import { motion } from "motion/react";
import { useMemo, useState } from "react";
import {
  ArrowUp,
  Square,
  Search,
  MessageSquare,
  Code2,
  ChevronRight,
  AlertCircle,
} from "lucide-react";
import { launcherFeatures, searchFeatures } from "../navigation/features";
import { call, type Snapshot, type Chat as ChatRecord } from "../services/api";
import type { RuntimeState } from "../services/runtimeState";

interface Props {
  reduced: boolean;
  draft: string;
  setDraft: (text: string) => void;
  navigate: (id: string) => void;
  openRecord: (route: string, id: string) => void;
  submit: (text: string) => Promise<void>;
  snapshot: Snapshot | null;
  setActivity: (open: boolean) => void;
  busy: boolean;
  cancel: () => void;
  openChat: (chat: ChatRecord) => void;
  openStudio: (id: string) => void;
  report: (error: unknown) => void;
  approvals: number;
  runtimeState: RuntimeState;
}
const RECENT_LIMIT = 4;

// Home has one job: start a request, or open a feature. Each destination is
// represented once — the launcher is the way in, Continue is only real recent
// work, and activity appears only when there is something to act on.
export function HomePage({
  reduced,
  draft,
  setDraft,
  navigate,
  openRecord,
  submit,
  snapshot,
  setActivity,
  busy,
  cancel,
  openChat,
  openStudio,
  report,
  approvals,
  runtimeState,
}: Props) {
  const [query, setQuery] = useState("");
  const [showAllRecent, setShowAllRecent] = useState(false);
  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  const send = () => {
    if (!draft.trim() || !snapshot) return;
    setDraft("");
    navigate("chat");
    void submit(draft);
  };
  const apps = useMemo(() => searchFeatures(query, launcherFeatures), [query]);
  const recent = snapshot?.home.recent || [];
  const visibleRecent = showAllRecent ? recent : recent.slice(0, RECENT_LIMIT);
  const activityItems = snapshot?.activity?.items || [];
  const showActivity = approvals > 0 || activityItems.length > 0;
  // The composer invites a request, so say plainly when no model can answer it.
  const modelUnavailable =
    runtimeState.detail === "AI offline" || runtimeState.detail === "no model installed";
  return (
    <motion.main
      initial={reduced ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="home"
    >
      <div className="home-frame">
        <header className="home-top">
          <div className="home-greeting">
            <h1>{greeting}</h1>
            <p className="muted">{today}</p>
          </div>
        </header>

        <section className="home-ask" aria-label="Ask OLIVE">
          <div className="composer home-composer">
            <GrowingComposer
              aria-label="Ask OLIVE anything"
              placeholder="Ask, plan, draft, research, or build — in your own words"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <div className="composer-bottom">
              <span className="composer-hint">
                {modelUnavailable
                  ? `Enter to send · ${runtimeState.detail} — replies need a local model`
                  : "Enter to send · Shift+Enter for a new line"}
              </span>
              <button
                className="send"
                aria-label={busy ? "Cancel request" : "Submit request"}
                title={busy ? "Cancel request" : "Send (Enter)"}
                disabled={!snapshot || (!busy && !draft.trim())}
                onClick={() => (busy ? cancel() : send())}
              >
                {busy ? (
                  <Square size={15} aria-hidden="true" />
                ) : (
                  <ArrowUp size={19} aria-hidden="true" />
                )}
              </button>
            </div>
          </div>
        </section>

        {showActivity && (
          <section className="home-activity" aria-label="Current activity">
            <button className="activity-strip" onClick={() => setActivity(true)}>
              <AlertCircle size={15} aria-hidden="true" />
              <span>
                {approvals > 0
                  ? approvals === 1
                    ? "One action is waiting for your approval"
                    : `${approvals} actions are waiting for your approval`
                  : activityItems.length === 1
                    ? "One request is running"
                    : `${activityItems.length} requests are running`}
              </span>
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          </section>
        )}

        <section className="home-apps" aria-label="Your apps">
          <div className="section-heading">
            <h2>Your apps</h2>
            <label className="search app-search">
              <Search size={15} aria-hidden="true" />
              <input
                aria-label="Search your apps"
                placeholder="Find a feature…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
          </div>
          <div className="app-grid">
            {apps.map((feature) => (
              <button
                key={feature.id}
                className="app-tile"
                onClick={() => navigate(feature.id)}
              >
                <span className="app-icon">
                  <feature.icon size={18} aria-hidden="true" />
                </span>
                <span className="app-text">
                  <span className="app-name">{feature.label}</span>
                  <span className="app-description">{feature.description}</span>
                </span>
              </button>
            ))}
          </div>
          {apps.length === 0 && (
            <p className="muted small">No feature matches that search.</p>
          )}
        </section>

        {recent.length > 0 && (
          <section className="home-continue" aria-label="Continue">
            <div className="section-heading">
              <h2>Continue</h2>
              {recent.length > RECENT_LIMIT && (
                <button
                  className="text-button"
                  onClick={() => setShowAllRecent(!showAllRecent)}
                >
                  {showAllRecent ? "Show less" : `Show all ${recent.length}`}
                </button>
              )}
            </div>
            <div className="continue-list">
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
                  <span className="continue-icon">
                    {item.kind === "chat" ? (
                      <MessageSquare size={15} aria-hidden="true" />
                    ) : (
                      <Code2 size={15} aria-hidden="true" />
                    )}
                  </span>
                  <span className="continue-text">
                    <strong>{item.title}</strong>
                    <small>{item.subtitle}</small>
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        <Today navigate={navigate} openRecord={openRecord} />
      </div>
    </motion.main>
  );
}
