import { useState } from "react";
import { call } from "../../services/api";
import { Sheet } from "../../components/Sheet";
import {
  Field,
  Feedback,
  ProjectSelect,
  ContactLinks,
  RecordSource,
  useOperation,
} from "./shared";
import { body, type CalendarEvent, type LocalCalendar } from "./types";

export default function EventEditor({
  initial,
  calendars,
  onClose,
  onSaved,
}: {
  initial: CalendarEvent;
  calendars: LocalCalendar[];
  onClose: () => void;
  onSaved: () => Promise<unknown>;
}) {
  const [edit, setEdit] = useState(initial),
    [scope, setScope] = useState(
      initial.occurrence_id && initial.recurrence ? "occurrence" : "series",
    );
  const [rule, setRule] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      initial.recurrence
        .split(";")
        .filter(Boolean)
        .map((x) => x.split("=")),
    ),
  );

  const op = useOperation(onSaved);
  const change = (patch: Partial<CalendarEvent>) =>
    setEdit({ ...edit, ...patch });
  const changeScope = async (value: string) => {
    if (value === "series" && initial.occurrence_id) {
      const series = await call<CalendarEvent>("calendar.get", {
        record_id: initial.id,
      });
      if (series.revision !== initial.revision)
        throw Error("The series changed; reopen it before editing.");
      setEdit(series);
    } else setEdit(initial);
    setScope(value);
  };
  const save = async () => {
    const recurrence = rule.FREQ
      ? Object.entries(rule)
          .filter(([, value]) => value)
          .map(([key, value]) => `${key}=${value}`)
          .join(";")
      : "";
    const payload = body({ ...edit, recurrence });
    delete (payload as Record<string, unknown>).occurrence_id;
    if (scope === "occurrence" && initial.occurrence_id) {
      const series = await call<CalendarEvent>("calendar.get", {
        record_id: initial.id,
      });
      if (series.revision !== initial.revision)
        throw Error(
          "This series changed. Close and reopen the event to compare.",
        );
      await call("calendar.update", {
        record_id: initial.id,
        revision: initial.revision,
        body: {
          ...body(series),
          exceptions: {
            ...series.exceptions,
            [initial.occurrence_id]: {
              title: edit.title,
              start: edit.start,
              end: edit.end,
              description: edit.description,
              location: edit.location,
            },
          },
        },
      });
    } else
      await call(edit.id ? "calendar.update" : "calendar.create", {
        body: payload,
        ...(edit.id ? { record_id: edit.id, revision: edit.revision } : {}),
      });
    onClose();
  };
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={edit.id ? "Edit event" : "New event"}
      description="A local calendar event. Contact references do not send invitations."
    >
      <form
        className="personal-form"
        onSubmit={(e) => {
          e.preventDefault();
          void op.run(save);
        }}
      >
        {initial.recurrence && initial.id && (
          <Field label="Edit scope">
            <select
              aria-label="Edit scope"
              value={scope}
              onChange={(e) =>
                void op.run(
                  () => changeScope(e.target.value),
                  "Editing scope changed; no event saved.",
                )
              }
            >
              <option value="occurrence">This occurrence</option>
              <option value="series">Entire series</option>
            </select>
          </Field>
        )}
        <Field label="Event title">
          <input
            required
            aria-label="Event title"
            value={edit.title}
            onChange={(e) => change({ title: e.target.value })}
          />
        </Field>
        <Field label="Calendar">
          <select
            aria-label="Calendar"
            disabled={scope === "occurrence"}
            value={edit.calendar_id}
            onChange={(e) => change({ calendar_id: e.target.value })}
          >
            {calendars.map((c) => (
              <option value={c.id} key={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </Field>
        <label>
          <input
            aria-label="All day"
            type="checkbox"
            checked={edit.all_day}
            onChange={(e) =>
              change({
                all_day: e.target.checked,
                start: e.target.checked
                  ? edit.start.slice(0, 10)
                  : edit.start.slice(0, 10) + "T09:00",
                end: e.target.checked
                  ? edit.end.slice(0, 10) > edit.start.slice(0, 10)
                    ? edit.end.slice(0, 10)
                    : new Date(
                        new Date(
                          edit.start.slice(0, 10) + "T12:00:00Z",
                        ).getTime() + 86400000,
                      )
                        .toISOString()
                        .slice(0, 10)
                  : edit.end.slice(0, 10) + "T10:00",
              })
            }
          />
          All day
        </label>
        <div className="personal-form-grid">
          <Field label="Start">
            <input
              required
              aria-label="Event start"
              type={edit.all_day ? "date" : "datetime-local"}
              value={edit.start.slice(0, edit.all_day ? 10 : 16)}
              onChange={(e) => change({ start: e.target.value })}
            />
          </Field>
          <Field label={edit.all_day ? "End (exclusive date)" : "End"}>
            <input
              required
              aria-label="Event end"
              type={edit.all_day ? "date" : "datetime-local"}
              value={edit.end.slice(0, edit.all_day ? 10 : 16)}
              onChange={(e) => change({ end: e.target.value })}
            />
          </Field>
        </div>
        {!edit.all_day && (
          <details>
            <summary>Ambiguous clock changes</summary>
            <p>
              For a time that occurs twice during a timezone transition, choose
              which occurrence you mean.
            </p>
            {(["start_fold", "end_fold"] as const).map((key) => (
              <Field
                key={key}
                label={
                  key === "start_fold"
                    ? "Start clock occurrence"
                    : "End clock occurrence"
                }
              >
                <select
                  aria-label={
                    key === "start_fold"
                      ? "Start clock occurrence"
                      : "End clock occurrence"
                  }
                  value={edit[key] ?? ""}
                  onChange={(e) =>
                    change({
                      [key]:
                        e.target.value === ""
                          ? undefined
                          : Number(e.target.value),
                    })
                  }
                >
                  <option value="">Ask if ambiguous</option>
                  <option value="0">First occurrence</option>
                  <option value="1">Second occurrence</option>
                </select>
              </Field>
            ))}
          </details>
        )}
        <Field label="Event timezone">
          <input
            aria-label="Event timezone"
            value={edit.timezone}
            disabled={scope === "occurrence"}
            onChange={(e) => change({ timezone: e.target.value })}
          />
        </Field>
        <Field label="Location">
          <input
            aria-label="Location"
            value={edit.location}
            onChange={(e) => change({ location: e.target.value })}
          />
        </Field>
        <Field label="Description">
          <textarea
            aria-label="Event description"
            value={edit.description}
            onChange={(e) => change({ description: e.target.value })}
          />
        </Field>
        {scope !== "occurrence" && (
          <>
            <fieldset>
              <legend>Repeat</legend>
              <div className="personal-form-grid">
                <Field label="Frequency">
                  <select
                    aria-label="Repeat frequency"
                    value={rule.FREQ || ""}
                    onChange={(e) =>
                      setRule(
                        e.target.value
                          ? { FREQ: e.target.value, INTERVAL: "1" }
                          : {},
                      )
                    }
                  >
                    <option value="">Does not repeat</option>
                    {["DAILY", "WEEKLY", "MONTHLY", "YEARLY"].map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                  </select>
                </Field>
                {rule.FREQ && (
                  <>
                    <Field label="Interval">
                      <input
                        aria-label="Repeat interval"
                        type="number"
                        min={1}
                        max={366}
                        value={rule.INTERVAL || "1"}
                        onChange={(e) =>
                          setRule({ ...rule, INTERVAL: e.target.value })
                        }
                      />
                    </Field>
                    <Field label="Ends">
                      <select
                        aria-label="Repeat ending"
                        value={
                          rule.COUNT ? "count" : rule.UNTIL ? "until" : "never"
                        }
                        onChange={(e) => {
                          const next = { ...rule };
                          delete next.COUNT;
                          delete next.UNTIL;
                          if (e.target.value === "count") next.COUNT = "5";
                          if (e.target.value === "until")
                            next.UNTIL =
                              edit.start.slice(0, 10).replaceAll("-", "") +
                              (edit.all_day ? "" : "T235959Z");
                          setRule(next);
                        }}
                      >
                        <option value="never">No ending</option>
                        <option value="count">After count</option>
                        <option value="until">Until date</option>
                      </select>
                    </Field>
                    {rule.COUNT && (
                      <Field label="Occurrences">
                        <input
                          aria-label="Repeat count"
                          type="number"
                          min={1}
                          max={10000}
                          value={rule.COUNT}
                          onChange={(e) =>
                            setRule({ ...rule, COUNT: e.target.value })
                          }
                        />
                      </Field>
                    )}
                    {rule.UNTIL && (
                      <Field label="Until">
                        <input
                          aria-label="Repeat until"
                          type="date"
                          value={`${rule.UNTIL.slice(0, 4)}-${rule.UNTIL.slice(4, 6)}-${rule.UNTIL.slice(6, 8)}`}
                          onChange={(e) =>
                            setRule({
                              ...rule,
                              UNTIL:
                                e.target.value.replaceAll("-", "") +
                                (edit.all_day ? "" : "T235959Z"),
                            })
                          }
                        />
                      </Field>
                    )}
                  </>
                )}
              </div>
              {rule.FREQ === "WEEKLY" && (
                <div className="row">
                  {["MO", "TU", "WE", "TH", "FR", "SA", "SU"].map((day) => (
                    <label key={day}>
                      <input
                        type="checkbox"
                        checked={(rule.BYDAY || "").split(",").includes(day)}
                        onChange={(e) => {
                          const selected = (rule.BYDAY || "")
                            .split(",")
                            .filter(Boolean);
                          setRule({
                            ...rule,
                            BYDAY: (e.target.checked
                              ? [...selected, day]
                              : selected.filter((x) => x !== day)
                            ).join(","),
                          });
                        }}
                      />
                      {day}
                    </label>
                  ))}
                </div>
              )}
            </fieldset>
            <ProjectSelect
              value={edit.project_id}
              onChange={(project_id) => change({ project_id })}
            />
            <details>
              <summary>Contacts and availability</summary>
              <ContactLinks
                values={edit.contact_ids}
                onChange={(contact_ids) => change({ contact_ids })}
              />
              <label className="personal-check">
                <input
                  type="checkbox"
                  checked={edit.transparent}
                  onChange={(e) => change({ transparent: e.target.checked })}
                />
                Does not block availability
              </label>
            </details>
          </>
        )}
        {edit.id && <RecordSource record={initial} />}
        <Feedback error={op.error} />
        <div className="row">
          <button className="primary" disabled={op.busy}>
            Save Event
          </button>
          {edit.id && (
            <button
              type="button"
              disabled={op.busy}
              onClick={() =>
                void op.run(async () => {
                  if (scope === "occurrence" && initial.occurrence_id) {
                    const series = await call<CalendarEvent>("calendar.get", {
                      record_id: initial.id,
                    });
                    if (series.revision !== initial.revision)
                      throw Error("Series changed; review again");
                    await call("calendar.delete_occurrence", {
                      record_id: series.id,
                      revision: series.revision,
                      occurrence_id: initial.occurrence_id,
                    });
                  } else
                    await call("calendar.delete", {
                      record_id: edit.id,
                      revision: edit.revision,
                    });
                  onClose();
                }, "Event removed locally.")
              }
            >
              Delete {scope === "occurrence" ? "occurrence" : "event"}…
            </button>
          )}
        </div>
      </form>
    </Sheet>
  );
}
