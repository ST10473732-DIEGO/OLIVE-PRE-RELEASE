import identity from "../../../../olive/identity.json";
import { useEffect, useState } from "react";
import { WorkspacePage } from "../../components/WorkspacePage";
import { useResource } from "../../services/useResource";
import { call } from "../../services/api";
import { Field, Feedback, useOperation } from "./shared";
import { body, type Profile, type LocalCalendar, type Page } from "./types";
export default function ProfilePage() {
  const r = useResource(
    () => call<Profile>("profile.get", {}),
    ["personal.changed"],
  );
  const calendars = useResource(
    () => call<Page<LocalCalendar>>("calendar.calendars", {}),
    ["personal.changed"],
  );
  const [edit, setEdit] = useState<Profile>();
  const op = useOperation(r.refresh);
  useEffect(() => {
    if (r.data && !edit) setEdit(r.data);
  }, [r.data, edit]);
  const change = (patch: Partial<Profile>) =>
    setEdit((value) => (value ? { ...value, ...patch } : value));
  return (
    <WorkspacePage
      title="Profile"
      description="Your local preferences. No registration or online account required."
    >
      <Feedback
        error={op.error || r.error}
        notice={op.notice}
        loading={r.loading}
      />
      {edit && (
        <form
          className="personal-profile"
          onSubmit={(e) => {
            e.preventDefault();
            void op.run(async () => {
              const saved = await call<Profile>("profile.update", {
                record_id: edit.id,
                revision: edit.revision,
                body: body(edit),
              });
              setEdit(saved);
            });
          }}
        >
          {edit.recovery_warning && <p role="alert">{edit.recovery_warning}</p>}
          <div className="row">
            {edit.avatar ? (
              <img
                className="personal-avatar"
                src={edit.avatar}
                alt="Local profile avatar"
              />
            ) : (
              <div className="personal-avatar">
                {edit.display_name.slice(0, 1) || identity.name.slice(0, 1)}
              </div>
            )}
            <button
              type="button"
              onClick={() =>
                void op.run(async () => {
                  const picked = (await window.olive.fileAction({
                    action: "profile-avatar",
                  })) as { avatar: string } | null;
                  if (picked) change(picked);
                }, "Avatar selected. Save Profile to keep it.")
              }
            >
              Choose avatar
            </button>
            <button type="button" onClick={() => change({ avatar: "" })}>
              Remove avatar
            </button>
          </div>
          <Field label="Display name">
            <input
              aria-label="Display name"
              value={edit.display_name}
              onChange={(e) => change({ display_name: e.target.value })}
              maxLength={120}
            />
          </Field>
          <div className="personal-form-grid">
            <Field label="Timezone">
              <input
                aria-label="Timezone"
                list="profile-timezones"
                value={edit.timezone}
                onChange={(e) => change({ timezone: e.target.value })}
              />
              <datalist id="profile-timezones">
                {[
                  "Africa/Johannesburg",
                  "UTC",
                  "Europe/London",
                  "America/New_York",
                  "Australia/Sydney",
                ].map((z) => (
                  <option key={z}>{z}</option>
                ))}
              </datalist>
            </Field>
            <Field label="Locale">
              <input
                aria-label="Locale"
                value={edit.locale}
                onChange={(e) => change({ locale: e.target.value })}
              />
            </Field>
            <Field label="Date format">
              <select
                aria-label="Date format"
                value={edit.date_format}
                onChange={(e) => change({ date_format: e.target.value })}
              >
                {["dd/MM/yyyy", "yyyy-MM-dd", "MM/dd/yyyy"].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </Field>
            <Field label="Time format">
              <select
                aria-label="Time format"
                value={edit.time_format}
                onChange={(e) => change({ time_format: e.target.value })}
              >
                <option>24h</option>
                <option>12h</option>
              </select>
            </Field>
            <Field label="Working day starts">
              <input
                aria-label="Working day starts"
                type="time"
                value={edit.working_hours.start}
                onChange={(e) =>
                  change({
                    working_hours: {
                      ...edit.working_hours,
                      start: e.target.value,
                    },
                  })
                }
              />
            </Field>
            <Field label="Working day ends">
              <input
                aria-label="Working day ends"
                type="time"
                value={edit.working_hours.end}
                onChange={(e) =>
                  change({
                    working_hours: {
                      ...edit.working_hours,
                      end: e.target.value,
                    },
                  })
                }
              />
            </Field>
          </div>
          <fieldset>
            <legend>Working days</legend>
            <div className="row">
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
                (day, index) => (
                  <label key={day}>
                    <input
                      type="checkbox"
                      checked={edit.working_hours.days.includes(index)}
                      onChange={(e) =>
                        change({
                          working_hours: {
                            ...edit.working_hours,
                            days: e.target.checked
                              ? [...edit.working_hours.days, index]
                              : edit.working_hours.days.filter(
                                  (d) => d !== index,
                                ),
                          },
                        })
                      }
                    />
                    {day}
                  </label>
                ),
              )}
            </div>
          </fieldset>
          <Field label="Default calendar">
            <select
              aria-label="Default calendar"
              value={edit.default_calendar}
              onChange={(e) => change({ default_calendar: e.target.value })}
            >
              {calendars.data?.items.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </Field>
          <button className="primary" disabled={op.busy}>
            Save Profile
          </button>
          <p className="muted">
            Setup is optional. Africa/Johannesburg and South African English are
            offered as defaults; change them whenever you need.
          </p>
        </form>
      )}
    </WorkspacePage>
  );
}
