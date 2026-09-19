import { ArrowRight, Bell, CalendarDays, CheckSquare } from "lucide-react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import type { CalendarEvent, PersonalTask, Delivery, Profile } from "./types";
import { personalDate } from "./format";
export default function Today({
  navigate,
  openRecord,
  compact = false,
  showEmpty = false,
}: {
  navigate: (route: string) => void;
  openRecord?: (route: string, id: string) => void;
  compact?: boolean;
  showEmpty?: boolean;
}) {
  const r = useResource(
    () =>
      call<{
        events: CalendarEvent[];
        tasks: PersonalTask[];
        reminders: Delivery[];
        display_name: string;
        format: Pick<
          Profile,
          "timezone" | "locale" | "date_format" | "time_format"
        >;
      }>("personal.today", {}),
    ["personal.changed", "personal.reminders"],
  );
  const data = r.data;
  const empty =
    !data ||
    (compact
      ? !data.reminders.length
      : !data.events.length && !data.tasks.length && !data.reminders.length);
  if (empty) {
    // Only Home shows a quiet empty state; loading and compact callers stay silent.
    if (!showEmpty || !data) return null;
    return (
      <section className="personal-today" aria-label="Today">
        <div className="section-heading">
          <h2>Today</h2>
        </div>
        <div className="today-empty">
          <p className="muted">Nothing scheduled. Your day is clear.</p>
          <div className="row wrap">
            <button className="quiet" onClick={() => navigate("calendar")}>
              <CalendarDays size={15} aria-hidden="true" />
              Calendar
            </button>
            <button className="quiet" onClick={() => navigate("tasks")}>
              <CheckSquare size={15} aria-hidden="true" />
              Tasks
            </button>
            <button className="quiet" onClick={() => navigate("reminders")}>
              <Bell size={15} aria-hidden="true" />
              Reminders
            </button>
          </div>
        </div>
      </section>
    );
  }
  return (
    <section className="personal-today" aria-label="Native Today">
      <div className="section-heading">
        <h2>{compact ? "Personal reminders" : "Today"}</h2>
        <button className="quiet" onClick={() => navigate("reminders")}>
          <Bell size={14} aria-hidden="true" />
          Reminders ({data.reminders.length})
        </button>
      </div>
      <div className="personal-today-items">
        {!compact &&
          data.events.slice(0, 3).map((e) => (
            <button
              className="recent-row"
              key={e.id + e.occurrence_id}
              onClick={() =>
                openRecord ? openRecord("calendar", e.id) : navigate("calendar")
              }
            >
              <span className="recent-icon">
                <CalendarDays size={15} aria-hidden="true" />
              </span>
              <strong>{e.title}</strong>
              <span>
                {e.all_day ? "All day" : personalDate(e.start, data.format)}
              </span>
            </button>
          ))}
        {!compact &&
          data.tasks.slice(0, 3).map((t) => (
            <button
              className="recent-row"
              key={t.id}
              onClick={() =>
                openRecord ? openRecord("tasks", t.id) : navigate("tasks")
              }
            >
              <span className="recent-icon">
                <CheckSquare size={15} aria-hidden="true" />
              </span>
              <strong>{t.title}</strong>
              <span>{t.due ? personalDate(t.due, data.format) : "Task"}</span>
            </button>
          ))}
        {data.reminders.slice(0, compact ? 5 : 2).map((r) => (
          <button
            className="recent-row"
            key={r.id}
            onClick={() => navigate("reminders")}
          >
            <span className="recent-icon">
              <Bell size={15} aria-hidden="true" />
            </span>
            <strong>{r.title}</strong>
            <span>Reminder ready</span>
          </button>
        ))}
        {!compact && (
          <button className="recent-row today-more" onClick={() => navigate("calendar")}>
            <span className="grow muted small">Open Calendar</span>
            <ArrowRight size={14} aria-hidden="true" />
          </button>
        )}
      </div>
    </section>
  );
}
