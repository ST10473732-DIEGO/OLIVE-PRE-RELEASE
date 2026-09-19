import { useEffect, useState, useRef, useCallback } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { WorkspacePage } from "../../components/WorkspacePage";
import { Sheet } from "../../components/Sheet";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import {
  body,
  type CalendarEvent,
  type LocalCalendar,
  type Profile,
  type Page,
} from "./types";
import { Blank, Field, Feedback, useOperation } from "./shared";
import EventEditor from "./EventEditor";
import Interchange from "./Interchange";
const localDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export default function CalendarPage({
  target,
  createRequest = 0,
}: {
  target?: { id: string; revision: number };
  createRequest?: number;
}) {
  const [date, setDate] = useState(() => localDay(new Date())),
    [view, setView] = useState("Month"),
    [query, setQuery] = useState(""),
    [edit, setEdit] = useState<CalendarEvent>(),
    [manage, setManage] = useState(false),
    [newTitle, setNewTitle] = useState("");
  const profile = useResource(
    () => call<Profile>("profile.get", {}),
    ["personal.changed"],
  );
  const calendars = useResource(
    () => call<Page<LocalCalendar>>("calendar.calendars", {}),
    ["personal.changed"],
  );
  const handledCreate = useRef(0);
  const anchor = new Date(date + "T12:00:00"),
    first = new Date(anchor.getFullYear(), anchor.getMonth(), 1, 12),
    start = new Date(view === "Month" ? first : anchor);
  if (view !== "Day")
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  const days = Array.from(
    { length: view === "Month" ? 42 : view === "Day" ? 1 : 7 },
    (_, i) => {
      const d = new Date(start);
      d.setDate(d.getDate() + i);
      return d;
    },
  );
  const before = new Date(days.at(-1)!);
  before.setDate(before.getDate() + 1);
  const tz = profile.data?.timezone || "Africa/Johannesburg";
  const zonedDay = (d: Date) =>
    new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(d);
  const key = localDay(start) + localDay(before) + tz;
  const r = useResource(
    () =>
      call<Page<CalendarEvent>>("calendar.range", {
        after: localDay(start),
        before: localDay(before),
        timezone: tz,
      }),
    ["personal.changed"],
    key,
  );
  const op = useOperation(r.refresh);
  const [targetError, setTargetError] = useState("");
  useEffect(() => {
    if (!target) return;
    let active = true;
    void call<CalendarEvent>("calendar.get", { record_id: target.id })
      .then((value) => {
        if (active) setEdit(value);
      })
      .catch((error) => {
        if (active)
          setTargetError(
            error instanceof Error
              ? error.message
              : "The linked record could not be opened.",
          );
      });
    return () => {
      active = false;
    };
  }, [target]);
  const found = useResource(
    () =>
      query.trim()
        ? call<Page<CalendarEvent>>("calendar.search", { query, limit: 100 })
        : Promise.resolve({ items: [], has_more: false }),
    ["personal.changed"],
    query,
  );
  const rows = query.trim() ? found.data?.items || [] : r.data?.items || [];
  const openNew = useCallback(
    (day = date) =>
      setEdit({
        id: "",
        uid: "",
        kind: "event",
        revision: 0,
        created_at: "",
        updated_at: "",
        calendar_id:
          profile.data?.default_calendar || calendars.data?.items[0]?.id || "",
        title: "",
        description: "",
        location: "",
        start: day + "T09:00",
        end: day + "T10:00",
        timezone: profile.data?.timezone || "Africa/Johannesburg",
        all_day: false,
        recurrence: "",
        exceptions: {},
        contact_ids: [],
        project_id: "",
        status: "confirmed",
        transparent: false,
        unsupported: [],
        original_ics: "",
      }),
    [date, profile.data, calendars.data],
  );
  useEffect(() => {
    if (
      createRequest &&
      createRequest !== handledCreate.current &&
      profile.data
    ) {
      handledCreate.current = createRequest;
      openNew();
    }
  }, [createRequest, profile.data, openNew]);
  const move = (direction: number) => {
    const d = new Date(anchor);
    if (view === "Month") d.setMonth(d.getMonth() + direction, 1);
    else d.setDate(d.getDate() + direction * (view === "Day" ? 1 : 7));
    setDate(localDay(d));
  };
  const label = (item: CalendarEvent) =>
    item.all_day
      ? "All day"
      : new Intl.DateTimeFormat(profile.data?.locale || "en-ZA", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: profile.data?.timezone || "Africa/Johannesburg",
          hour12: profile.data?.time_format === "12h",
        }).format(new Date(item.start));
  const eventButton = (e: CalendarEvent) => (
    <button
      key={e.id + e.occurrence_id}
      className="calendar-event"
      style={{
        borderLeftColor: calendars.data?.items.find(
          (c) => c.id === e.calendar_id,
        )?.colour,
      }}
      onClick={() => setEdit(e)}
    >
      <span>{label(e)}</span>
      <strong>{e.title}</strong>
      {e.recurrence && <span aria-label="Recurring event">↻</span>}
    </button>
  );
  return (
    <WorkspacePage
      title="Calendar"
      description="Your schedule, locally owned. Attendee references send no invitations."
      actions={
        <>
          <button onClick={() => setManage(true)}>Calendars</button>
          <button
            className="primary"
            disabled={!profile.data}
            onClick={() => openNew()}
          >
            New Event
          </button>
        </>
      }
    >
      <div className="calendar-toolbar">
        <div className="row">
          <div className="toolbar-group">
            <button
              className="icon-button"
              aria-label="Previous calendar period"
              title="Previous"
              onClick={() => move(-1)}
            >
              <ChevronLeft size={16} aria-hidden="true" />
            </button>
            <button className="quiet" onClick={() => setDate(zonedDay(new Date()))}>
              Today
            </button>
            <button
              className="icon-button"
              aria-label="Next calendar period"
              title="Next"
              onClick={() => move(1)}
            >
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          </div>
          <h2>
            {anchor.toLocaleDateString(profile.data?.locale || "en-ZA", {
              month: "long",
              year: "numeric",
            })}
          </h2>
        </div>
        <div className="segmented" role="group" aria-label="Calendar view">
          {["Month", "Week", "Agenda", "Day"].map((v) => (
            <button
              aria-pressed={view === v}
              className={view === v ? "selected" : ""}
              key={v}
              onClick={() => setView(v)}
            >
              {v}
            </button>
          ))}
        </div>
      </div>
      <div className="calendar-filters">
        <label className="search">
          <Search size={15} aria-hidden="true" />
          <input
            aria-label="Search calendar"
            placeholder="Search all local events"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <input
          aria-label="Calendar date"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value || date)}
        />
        <div className="chips calendar-visibility" aria-label="Visible calendars">
          {calendars.data?.items.map((c) => (
            <label className="chip" key={c.id}>
              <input
                type="checkbox"
                checked={c.visible}
                onChange={(e) =>
                  void op.run(
                    () =>
                      call("calendar.save_calendar", {
                        record_id: c.id,
                        revision: c.revision,
                        body: { ...body(c), visible: e.target.checked },
                      }),
                    "Calendar visibility updated.",
                  )
                }
              />
              <span
                className="calendar-swatch"
                style={{ background: c.colour }}
                aria-hidden="true"
              />
              {c.title}
            </label>
          ))}
        </div>
        <div className="row calendar-interchange">
          <Interchange
            kind="event"
            calendarId={profile.data?.default_calendar}
            onChanged={r.refresh}
          />
        </div>
      </div>
      <Feedback
        error={targetError || op.error || r.error || found.error}
        notice={op.notice}
        loading={r.loading}
      />
      {view === "Month" && !query.trim() && (
        <div className="calendar-weekdays" aria-label="Weekday headings">
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>
      )}
      {view === "Agenda" || view === "Day" || query.trim() ? (
        <section aria-label="Calendar Agenda">
          {rows.length ? (
            rows.map((e) => (
              <div className="calendar-agenda-row" key={e.id + e.occurrence_id}>
                <time>
                  {e.all_day
                    ? e.start
                    : new Intl.DateTimeFormat(profile.data?.locale || "en-ZA", {
                        weekday: "short",
                        day: "numeric",
                        month: "short",
                        timeZone: tz,
                      }).format(new Date(e.start))}
                </time>
                {eventButton(e)}
              </div>
            ))
          ) : (
            <Blank title="Nothing scheduled here">
              Choose New Event, another date, or a different visible calendar.
            </Blank>
          )}
        </section>
      ) : (
        <div
          className={`calendar-grid ${view.toLowerCase()}`}
          aria-label={`Calendar ${view}`}
        >
          {days.map((d) => {
            const key = localDay(d);
            const items = rows.filter(
              (e) =>
                (e.all_day ? e.start : zonedDay(new Date(e.start))) <= key &&
                (e.all_day
                  ? e.end > key
                  : zonedDay(new Date(new Date(e.end).getTime() - 1)) >= key),
            );
            return (
              <section
                key={key}
                className={`calendar-day ${key === zonedDay(new Date()) ? "today" : ""} ${view === "Month" && d.getMonth() !== anchor.getMonth() ? "outside" : ""}`}
              >
                <button
                  className="calendar-day-number"
                  aria-label={`New event on ${key}`}
                  onClick={() => openNew(key)}
                >
                  {d.toLocaleDateString(
                    profile.data?.locale || "en-ZA",
                    view === "Week"
                      ? { weekday: "short", day: "numeric" }
                      : { day: "numeric" },
                  )}
                </button>
                {items.slice(0, view === "Month" ? 2 : 20).map(eventButton)}
                {view === "Month" && items.length > 2 && (
                  <button
                    onClick={() => {
                      setDate(key);
                      setView("Day");
                    }}
                  >
                    +{items.length - 2} more
                  </button>
                )}
              </section>
            );
          })}
        </div>
      )}
      {edit && (
        <EventEditor
          key={edit.id + edit.occurrence_id}
          initial={edit}
          calendars={calendars.data?.items || []}
          onClose={() => setEdit(undefined)}
          onSaved={r.refresh}
        />
      )}
      <Sheet
        open={manage}
        onOpenChange={setManage}
        title="Local calendars"
        description="Categories stay on this device. Move linked events before deleting a calendar."
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void op.run(async () => {
              await call("calendar.save_calendar", {
                body: { title: newTitle },
              });
              setNewTitle("");
            });
          }}
        >
          <Field label="Calendar name">
            <input
              required
              aria-label="Calendar name"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
            />
          </Field>
          <button>Create calendar</button>
        </form>
        {calendars.data?.items.map((c) => (
          <div className="personal-import-row" key={c.id}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const title = String(
                  new FormData(e.currentTarget).get("title") || "",
                );
                void op.run(
                  () =>
                    call("calendar.save_calendar", {
                      record_id: c.id,
                      revision: c.revision,
                      body: { ...body(c), title },
                    }),
                  "Calendar renamed.",
                );
              }}
            >
              <input
                key={c.title}
                name="title"
                required
                aria-label={`Name for ${c.title}`}
                defaultValue={c.title}
              />
              <button>Rename</button>
            </form>
            <input
              type="color"
              aria-label={`Colour for ${c.title}`}
              value={c.colour}
              onChange={(e) =>
                void op.run(() =>
                  call("calendar.save_calendar", {
                    record_id: c.id,
                    revision: c.revision,
                    body: { ...body(c), colour: e.target.value },
                  }),
                )
              }
            />
            <button
              onClick={() =>
                void op.run(
                  () =>
                    call("calendar.delete_calendar", {
                      record_id: c.id,
                      revision: c.revision,
                    }),
                  "Calendar deleted.",
                )
              }
            >
              Delete {c.title}
            </button>
          </div>
        ))}
        <Feedback error={op.error} />
      </Sheet>
    </WorkspacePage>
  );
}
