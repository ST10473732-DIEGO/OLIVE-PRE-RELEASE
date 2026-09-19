import { personalDate } from "./format";
import { useState } from "react";
import { Bell, BellRing, BellOff, CalendarClock, Plus, History, Pencil, Trash2, X } from "lucide-react";
import { WorkspacePage, Panel, EmptyState, Pill, Notice } from "../../components/WorkspacePage";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Field, Feedback, useOperation } from "./shared";
import type {
  Delivery,
  Page,
  PersonalTask,
  CalendarEvent,
  Profile,
} from "./types";
export default function Reminders({
  openRecord,
}: {
  openRecord?: (kind: string, id: string) => void;
}) {
  type Schedule = {
    id: string;
    revision: number;
    target_kind: string;
    target_id: string;
    at: string;
    offset_minutes: number;
    timezone: string;
  };
  const [schedulePage, setSchedulePage] = useState(0),
    [historyPage, setHistoryPage] = useState(0),
    [recordQuery, setRecordQuery] = useState("");
  const schedules = useResource(
    () =>
      call<Page<Schedule>>("reminders.search", {
        limit: 50,
        offset: schedulePage * 50,
      }),
    ["personal.changed"],
    String(schedulePage),
  );
  const [editing, setEditing] = useState<Schedule>();
  const r = useResource(
    () =>
      call<Page<Delivery> & { error?: string }>("reminders.history", {
        limit: 50,
        offset: historyPage * 50,
      }),
    ["personal.reminders", "personal.changed"],
    String(historyPage),
  );
  const records = useResource(
    async () => ({
      events: (
        await call<Page<CalendarEvent>>("calendar.search", {
          limit: 100,
          query: recordQuery,
        })
      ).items,
      tasks: (
        await call<Page<PersonalTask>>("tasks.search", {
          limit: 100,
          query: recordQuery,
        })
      ).items,
      profile: await call<Profile>("profile.get", {}),
    }),
    ["personal.changed"],
    recordQuery,
  );
  const [kind, setKind] = useState("event"),
    [target, setTarget] = useState(""),
    [at, setAt] = useState(""),
    [offset, setOffset] = useState(30),
    [adding, setAdding] = useState(false);
  const op = useOperation(r.refresh);
  const selectedTarget = useResource(
    () =>
      target
        ? call<{ id: string; title: string }>(
            kind === "event" ? "calendar.get" : "tasks.get",
            { record_id: target },
          )
        : Promise.resolve(null),
    ["personal.changed"],
    kind + target,
  );
  const options = kind === "event" ? records.data?.events : records.data?.tasks;
  const scheduleCount = schedules.data?.items.length || 0;
  const titleOf = (id: string) =>
    [...(records.data?.events || []), ...(records.data?.tasks || [])].find((r) => r.id === id)?.title ||
    "Linked personal record";
  const startNew = () => {
    setEditing(undefined);
    setTarget("");
    setAt("");
    setOffset(30);
    setAdding(!adding);
  };
  const pending = r.data?.items.filter((item) => ["delivered", "snoozed"].includes(item.state)).length || 0;
  return (
    <WorkspacePage
      layout="flow"
      className="reminders"
      icon={<Bell size={18} />}
      title="Reminders"
      description="In-app reminders while OLIVE runs. They cannot alert you while the app or PC is off."
      status={pending ? `${pending} waiting` : scheduleCount ? `${scheduleCount} scheduled` : "None scheduled"}
      statusTone={pending ? "warning" : scheduleCount ? "live" : "idle"}
      actions={
        <button className="primary" onClick={startNew}>
          <Plus size={16} aria-hidden="true" />
          New Reminder
        </button>
      }
    >
      <Feedback
        error={
          op.error ||
          r.error ||
          r.data?.error ||
          records.error ||
          schedules.error ||
          selectedTarget.error
        }
        notice={op.notice}
      />
      <div className="ws-grid main-side reminders-grid">
        <div className="reminders-column">
          <Panel
            title="Upcoming"
            sub={scheduleCount ? `${scheduleCount} scheduled reminder${scheduleCount === 1 ? "" : "s"}` : "Scheduled reminders, before or at a set time"}
            icon={<CalendarClock size={15} />}
            label="Reminder schedules"
            tight={scheduleCount > 0}
          >
            {schedules.data?.items.length ? (
              <div className="personal-task-list reminders-list">
                {schedules.data.items.map((s) => (
                  <article className="personal-task" key={s.id}>
                    <span className="ws-row-icon" aria-hidden="true">
                      <Bell size={15} />
                    </span>
                    <div className="personal-task-title">
                      <strong>{titleOf(s.target_id)}</strong>
                      <span className="muted">
                        {s.at
                          ? personalDate(s.at, records.data?.profile)
                          : `${s.offset_minutes} minutes before`}
                        {" · "}
                        {s.target_kind === "event" ? "Calendar event" : "Personal task"}
                      </span>
                    </div>
                    <button
                      className="quiet"
                      onClick={() => {
                        setEditing(s);
                        setKind(s.target_kind);
                        setTarget(s.target_id);
                        setOffset(s.offset_minutes);
                        setAt(
                          s.at
                            ? new Intl.DateTimeFormat("sv-SE", {
                                timeZone: s.timezone,
                                year: "numeric",
                                month: "2-digit",
                                day: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                                hour12: false,
                              })
                                .format(new Date(s.at))
                                .replace(" ", "T")
                            : "",
                        );
                        setAdding(true);
                      }}
                    >
                      <Pencil size={14} aria-hidden="true" />
                      Edit schedule
                    </button>
                    <button
                      className="quiet"
                      onClick={() =>
                        void op.run(
                          () =>
                            call("reminders.delete", {
                              record_id: s.id,
                              revision: s.revision,
                            }),
                          "Reminder schedule deleted; linked record unchanged.",
                        )
                      }
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      Delete schedule…
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              !schedules.loading && (
                <EmptyState compact icon={<BellOff size={20} />} title="Nothing scheduled" headingLevel={3}
                  actions={
                    <button onClick={startNew}>
                      <Plus size={14} aria-hidden="true" />
                      Create a reminder
                    </button>
                  }
                >
                  Attach a reminder to a calendar event or a task. It fires here while OLIVE is open.
                </EmptyState>
              )
            )}
            {(schedulePage > 0 || schedules.data?.has_more) && (
              <div className="row personal-paging">
                <button
                  className="quiet"
                  disabled={!schedulePage}
                  onClick={() => setSchedulePage(schedulePage - 1)}
                >
                  Previous schedules
                </button>
                <button
                  className="quiet"
                  disabled={!schedules.data?.has_more}
                  onClick={() => setSchedulePage(schedulePage + 1)}
                >
                  Next schedules
                </button>
              </div>
            )}
          </Panel>
          <Panel
            title="Notification history"
            sub={r.data?.items.length ? `${r.data.items.length}${r.data.has_more ? "+" : ""} delivered, snoozed or dismissed` : "What has fired, and what you did with it"}
            icon={<History size={15} />}
            label="Notification history"
            tight={!!r.data?.items.length}
          >
            {r.loading && <p role="status" className="muted">Loading local records…</p>}
            {!r.loading && !r.data?.items.length && (
              <EmptyState compact icon={<BellRing size={20} />} title="No reminder history yet" headingLevel={3}>
                Create a reminder for an event or task. Due reminders appear here and
                in the activity centre.
              </EmptyState>
            )}
            {!!r.data?.items.length && (
              <div className="personal-task-list reminders-list">
                {r.data?.items.map((item) => (
                  <article className="personal-task" key={item.id} data-state={item.state}>
                    <span className="ws-row-icon" aria-hidden="true">
                      {item.state === "delivered" ? <BellRing size={15} /> : item.state === "dismissed" ? <BellOff size={15} /> : <Bell size={15} />}
                    </span>
                    <div className="personal-task-title">
                      <strong>{item.title}</strong>
                      <span className="muted">
                        {personalDate(item.due_at, records.data?.profile)} ·{" "}
                        <Pill tone={item.state === "delivered" ? "warning" : item.state === "snoozed" ? "accent" : undefined}>
                          {item.state}
                        </Pill>
                      </span>
                    </div>
                    {["delivered", "snoozed"].includes(item.state) && (
                      <>
                        <button
                          onClick={() =>
                            void op.run(
                              () =>
                                call("reminders.snooze", {
                                  delivery_id: item.id,
                                  minutes: 10,
                                }),
                              "Snoozed for ten minutes.",
                            )
                          }
                        >
                          Snooze 10 min
                        </button>
                        <button
                          onClick={() =>
                            void op.run(
                              () => call("reminders.dismiss", { delivery_id: item.id }),
                              "Reminder dismissed. The linked task remains unchanged.",
                            )
                          }
                        >
                          Dismiss
                        </button>
                      </>
                    )}
                    {item.target_id && (
                      <button
                        className="quiet"
                        onClick={() => openRecord?.(item.target_kind, item.target_id)}
                      >
                        Open
                      </button>
                    )}
                  </article>
                ))}
              </div>
            )}
            <div className="row personal-paging" hidden={!historyPage && !r.data?.has_more}>
              <button
                className="quiet"
                disabled={!historyPage}
                onClick={() => setHistoryPage(historyPage - 1)}
              >
                Previous notifications
              </button>
              <button
                className="quiet"
                disabled={!r.data?.has_more}
                onClick={() => setHistoryPage(historyPage + 1)}
              >
                Next notifications
              </button>
            </div>
          </Panel>
        </div>
        <div className="reminders-column">
          {adding ? (
            <Panel
              title={editing ? "Edit reminder" : "New reminder"}
              sub="Linked to one event or task"
              icon={<Bell size={15} />}
              actions={
                <button className="icon-button" aria-label="Close reminder form" title="Close" onClick={() => { setAdding(false); setEditing(undefined); }}>
                  <X size={16} aria-hidden="true" />
                </button>
              }
              raised
            >
              <form
                className="personal-profile reminders-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  void op.run(async () => {
                    await call(editing ? "reminders.update" : "reminders.create", {
                      ...(editing
                        ? { record_id: editing.id, revision: editing.revision }
                        : {}),
                      body: {
                        target_kind: kind,
                        target_id: target,
                        at,
                        offset_minutes: offset,
                        timezone:
                          records.data?.profile.timezone || "Africa/Johannesburg",
                      },
                    });
                    setAdding(false);
                    setEditing(undefined);
                  }, "Reminder schedule saved.");
                }}
              >
                <Field label="Remind me about">
                  <select
                    aria-label="Reminder domain"
                    value={kind}
                    onChange={(e) => {
                      setKind(e.target.value);
                      setTarget("");
                    }}
                  >
                    <option value="event">Calendar event</option>
                    <option value="task">Personal task</option>
                  </select>
                </Field>
                <Field label="Find a record">
                  <input
                    aria-label="Search reminder targets"
                    placeholder="Find an event or task"
                    value={recordQuery}
                    onChange={(e) => setRecordQuery(e.target.value)}
                  />
                </Field>
                <Field label="Linked record">
                  <select
                    required
                    aria-label="Reminder target"
                    value={target}
                    onChange={(e) => setTarget(e.target.value)}
                  >
                    <option value="">Choose a record</option>
                    {selectedTarget.data &&
                      !options?.some((r) => r.id === target) && (
                        <option value={target}>{selectedTarget.data.title}</option>
                      )}
                    {options?.map((record) => (
                      <option value={record.id} key={record.id}>
                        {record.title}
                      </option>
                    ))}
                  </select>
                </Field>
                <div className="personal-form-grid">
                  <Field label="Minutes before">
                    <input
                      aria-label="Minutes before"
                      type="number"
                      min={0}
                      max={525600}
                      value={offset}
                      onChange={(e) => setOffset(Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Or explicit local time">
                    <input
                      aria-label="Explicit reminder time"
                      type="datetime-local"
                      value={at}
                      onChange={(e) => setAt(e.target.value)}
                    />
                  </Field>
                </div>
                <p className="muted small">
                  Date-only task deadlines use 09:00 for relative reminders. An
                  explicit time takes precedence.
                </p>
                <div className="row">
                  <button className="primary" disabled={op.busy}>
                    Save Reminder
                  </button>
                  <button type="button" className="quiet" onClick={() => { setAdding(false); setEditing(undefined); }}>
                    Cancel
                  </button>
                </div>
              </form>
            </Panel>
          ) : (
            <Panel title="How reminders work" icon={<Bell size={15} />} label="About reminders">
              <ul className="reminders-notes">
                <li>A reminder belongs to one calendar event or one task, either a number of minutes before it or at an explicit time.</li>
                <li>It fires inside OLIVE and in the activity centre. Nothing leaves this device and nothing fires while the app is closed.</li>
                <li>Snoozing or dismissing a reminder never changes the linked record.</li>
              </ul>
              <Notice tone="accent" icon={<CalendarClock size={15} />} role="note">
                Completing a task cancels its pending reminders.
              </Notice>
            </Panel>
          )}
        </div>
      </div>
    </WorkspacePage>
  );
}
