import { useEffect, useState, useRef, useCallback } from "react";
import { ChevronLeft, ChevronRight, Lock, Plus, Search, Settings2 } from "lucide-react";
import { WorkspacePage, Rail, Main } from "../../components/WorkspacePage";
import { dayInZone, miniMonth, minutesInZone, placeDay, rangeTitle } from "./calendarModel";
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
    // Week is the V2 working view; the person's last choice is remembered.
    [view, setViewState] = useState(() => {
      try {
        const saved = localStorage.getItem("calendarView");
        return saved && ["Day", "Week", "Month", "Agenda"].includes(saved) ? saved : "Week";
      } catch {
        return "Week";
      }
    }),
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
  const setView = (next: string) => {
    setViewState(next);
    try {
      localStorage.setItem("calendarView", next);
    } catch {
      /* convenience only */
    }
  };
  const handledCreate = useRef(0);
  const grid = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(timer);
  }, []);
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
  const locale = profile.data?.locale || "en-ZA";
  const today = zonedDay(now);
  const colourOf = (e: CalendarEvent) => calendars.data?.items.find((c) => c.id === e.calendar_id)?.colour;
  const HOUR = 44;
  const timed = rows.filter((e) => !e.all_day);
  const allDay = (key: string) => rows.filter((e) => e.all_day && e.start <= key && e.end > key);
  const month = miniMonth(anchor);
  const selectedWeek = new Set(
    Array.from({ length: 7 }, (_, i) => {
      const d = new Date(anchor);
      d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + i);
      return localDay(d);
    }),
  );
  useEffect(() => {
    // Open the time grid at the working day, not at midnight.
    if ((view === "Week" || view === "Day") && grid.current) grid.current.scrollTop = 7 * HOUR - 10;
  }, [view]);
  return (
    <WorkspacePage
      layout="fill"
      className="calendar-v2"
      title="Calendar"
      description="Your schedule, locally owned. Attendee references send no invitations."
      rail={
        <Rail label="Calendar navigation">
          <div className="mini-month" aria-label="Month">
            <div className="mini-month-head">
              <strong>{anchor.toLocaleDateString(locale, { month: "long", year: "numeric" })}</strong>
              <button
                className="icon-button"
                aria-label="Previous month"
                onClick={() => {
                  const d = new Date(anchor);
                  d.setMonth(d.getMonth() - 1, 1);
                  setDate(localDay(d));
                }}
              >
                <ChevronLeft size={14} aria-hidden="true" />
              </button>
              <button
                className="icon-button"
                aria-label="Next month"
                onClick={() => {
                  const d = new Date(anchor);
                  d.setMonth(d.getMonth() + 1, 1);
                  setDate(localDay(d));
                }}
              >
                <ChevronRight size={14} aria-hidden="true" />
              </button>
            </div>
            <div className="mini-month-grid" role="grid" aria-label="Choose a date">
              {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => (
                <span key={i} className="mini-month-dow" aria-hidden="true">{d}</span>
              ))}
              {month.map((d) => {
                const key = localDay(d);
                return (
                  <button
                    key={key}
                    className="mini-month-day"
                    data-outside={d.getMonth() !== anchor.getMonth() || undefined}
                    data-week={view === "Week" && selectedWeek.has(key) ? true : undefined}
                    data-selected={key === date || undefined}
                    data-today={key === today || undefined}
                    aria-label={d.toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
                    aria-current={key === today ? "date" : undefined}
                    onClick={() => setDate(key)}
                  >
                    {d.getDate()}
                  </button>
                );
              })}
            </div>
          </div>
          <label className="calendar-go">
            <span>Go to date</span>
            <input aria-label="Calendar date" type="date" value={date} onChange={(e) => setDate(e.target.value || date)} />
          </label>
          <div className="calendar-rail-section">
            <div className="calendar-rail-head">
              <span className="ws-eyebrow">Calendars</span>
              <button className="icon-button" aria-label="Calendars" title="Manage local calendars" onClick={() => setManage(true)}>
                <Settings2 size={14} aria-hidden="true" />
              </button>
            </div>
            <div className="calendar-toggles" role="group" aria-label="Visible calendars">
              {calendars.data?.items.map((c) => (
                <label className="calendar-toggle" key={c.id}>
                  <input
                    type="checkbox"
                    checked={c.visible}
                    style={{ accentColor: c.colour }}
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
                  <span className="calendar-swatch" style={{ background: c.colour }} aria-hidden="true" />
                  {c.title}
                </label>
              ))}
            </div>
          </div>
          <p className="calendar-note">
            <Lock size={12} aria-hidden="true" /> Stored on this device. Attendees are references; no invitations are sent.
          </p>
        </Rail>
      }
    >
      <Main pad={false} scroll={false} className="calendar-main" label="Calendar">
        <div className="calendar-toolbar">
          <button className="compact" onClick={() => setDate(zonedDay(new Date()))}>
            Today
          </button>
          <button className="icon-button" aria-label="Previous calendar period" title="Previous" onClick={() => move(-1)}>
            <ChevronLeft size={16} aria-hidden="true" />
          </button>
          <button className="icon-button" aria-label="Next calendar period" title="Next" onClick={() => move(1)}>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
          <h2>{rangeTitle(view, view === "Agenda" ? [anchor] : days, locale)}</h2>
          <label className="search calendar-search">
            <Search size={14} aria-hidden="true" />
            <input aria-label="Search calendar" placeholder="Search events" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <div className="segmented" role="group" aria-label="Calendar view">
            {["Day", "Week", "Month", "Agenda"].map((v) => (
              <button aria-pressed={view === v} className={view === v ? "selected" : ""} key={v} onClick={() => setView(v)}>
                {v}
              </button>
            ))}
          </div>
          <div className="row calendar-interchange">
            <Interchange kind="event" calendarId={profile.data?.default_calendar} onChanged={r.refresh} />
          </div>
          <button className="primary" disabled={!profile.data} onClick={() => openNew()}>
            <Plus size={14} aria-hidden="true" />
            New Event
          </button>
        </div>
        <Feedback error={targetError || op.error || r.error || found.error} notice={op.notice} loading={r.loading} />
        {view === "Agenda" || query.trim() ? (
          <section aria-label="Calendar Agenda" className="calendar-agenda">
            {rows.length ? (
              rows.map((e) => (
                <div className="calendar-agenda-row" key={e.id + e.occurrence_id}>
                  <time>
                    {e.all_day
                      ? e.start
                      : new Intl.DateTimeFormat(locale, {
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
              <Blank title="Nothing scheduled here">Choose New Event, another date, or a different visible calendar.</Blank>
            )}
          </section>
        ) : view === "Month" ? (
          <div className="calendar-month">
            <div className="calendar-weekdays" aria-label="Weekday headings">
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
                <span key={day}>{day}</span>
              ))}
            </div>
            <div className="calendar-grid month" aria-label="Calendar Month">
              {days.map((d) => {
                const key = localDay(d);
                const items = rows.filter(
                  (e) =>
                    (e.all_day ? e.start : zonedDay(new Date(e.start))) <= key &&
                    (e.all_day ? e.end > key : zonedDay(new Date(new Date(e.end).getTime() - 1)) >= key),
                );
                return (
                  <section key={key} className={`calendar-day ${key === today ? "today" : ""} ${d.getMonth() !== anchor.getMonth() ? "outside" : ""}`}>
                    <button className="calendar-day-number" aria-label={`New event on ${key}`} onClick={() => openNew(key)}>
                      {d.getDate()}
                    </button>
                    {items.slice(0, 3).map(eventButton)}
                    {items.length > 3 && (
                      <button
                        className="calendar-more"
                        onClick={() => {
                          setDate(key);
                          setView("Day");
                        }}
                      >
                        +{items.length - 3} more
                      </button>
                    )}
                  </section>
                );
              })}
            </div>
          </div>
        ) : (
          <div className={`calendar-time ${view.toLowerCase()}`} aria-label={`Calendar ${view}`} style={{ ["--hour" as string]: `${HOUR}px`, ["--days" as string]: days.length }}>
            <div className="calendar-time-head">
              <span className="calendar-time-gutter" />
              {days.map((d) => {
                const key = localDay(d);
                return (
                  <button key={key} className="calendar-col-head" data-today={key === today || undefined} aria-label={`New event on ${key}`} onClick={() => openNew(key)}>
                    <span>{d.toLocaleDateString(locale, { weekday: "short" })}</span>
                    <b>{d.getDate()}</b>
                  </button>
                );
              })}
            </div>
            <div className="calendar-allday">
              <span className="calendar-time-gutter">all-day</span>
              {days.map((d) => {
                const key = localDay(d);
                return <div key={key} className="calendar-allday-cell">{allDay(key).map(eventButton)}</div>;
              })}
            </div>
            <div className="calendar-time-scroll" ref={grid}>
              <div className="calendar-time-body">
                <div className="calendar-hours" aria-hidden="true">
                  {Array.from({ length: 24 }, (_, h) => (
                    <span key={h} style={{ top: h * HOUR }}>{h ? `${String(h).padStart(2, "0")}:00` : ""}</span>
                  ))}
                </div>
                {days.map((d) => {
                  const key = localDay(d);
                  return (
                    <div key={key} className="calendar-time-col" data-today={key === today || undefined}>
                      {placeDay(timed, key, tz).map((placed) => (
                        <div
                          key={placed.item.id + placed.item.occurrence_id}
                          className="calendar-block"
                          data-short={placed.bottom - placed.top < 45 || undefined}
                          style={{
                            top: (placed.top / 60) * HOUR,
                            height: Math.max(18, ((placed.bottom - placed.top) / 60) * HOUR - 2),
                            left: `calc(${(placed.lane / placed.lanes) * 100}% + 2px)`,
                            width: `calc(${100 / placed.lanes}% - 4px)`,
                            ["--calendar" as string]: colourOf(placed.item) || "var(--accent-blue)",
                          }}
                        >
                          {eventButton(placed.item)}
                        </div>
                      ))}
                      {key === today && dayInZone(now, tz) === key && (
                        <span className="calendar-now" style={{ top: (minutesInZone(now, tz) / 60) * HOUR }} aria-label="Now" />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </Main>
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
