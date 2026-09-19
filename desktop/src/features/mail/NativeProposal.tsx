import { useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Field, Feedback, useOperation } from "../personal/shared";
import type { MailRecord } from "./types";

export default function NativeProposal({
  source,
  kind,
  done,
}: {
  source: MailRecord;
  kind: "event" | "task";
  done: () => void;
}) {
  const [title, setTitle] = useState(source.subject),
    [description, setDescription] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [due, setDue] = useState("");
  const profile = useResource(() =>
    call<{ timezone: string; default_calendar: string }>("profile.get", {}),
  );
  const op = useOperation();
  return (
    <form
      className="mail-native-proposal"
      onSubmit={(e) => {
        e.preventDefault();
        if (!profile.data) return;
        void op.run(async () => {
          const body = {
            title,
            description,
            timezone: profile.data!.timezone,
            ...(kind === "event"
              ? { calendar_id: profile.data!.default_calendar, start, end }
              : { due }),
          };
          const p = await call<{
            id: string;
            revision: number;
            body: Record<string, unknown>;
          }>("mail.proposal_prepare", {
            record_id: source.id,
            revision: source.revision,
            kind,
            body,
          });
          await call(
            kind === "event" ? "mail.create_event" : "mail.create_task",
            { proposal_id: p.id, revision: p.revision, body: p.body },
          );
          done();
        }, "Created locally. No message or invitation was sent.");
      }}
    >
      <p>
        Source: <strong>{source.subject || "(No subject)"}</strong>
        <br />
        {source.from}
      </p>
      <p className="muted">
        Review the details. This creates a linked local{" "}
        {kind === "event" ? "Calendar event" : "Personal Task"}; it does not
        notify anyone.
      </p>
      <Field label="Title">
        <input
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
        />
      </Field>
      <Field label="Description">
        <textarea
          aria-label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={8000}
        />
      </Field>
      {kind === "event" ? (
        <>
          <Field label="Start">
            <input
              required
              type="datetime-local"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </Field>
          <Field label="End">
            <input
              required
              type="datetime-local"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </Field>
          <p>Timezone: {profile.data?.timezone}</p>
        </>
      ) : (
        <Field label="Due date (optional)">
          <input
            type="date"
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </Field>
      )}
      <Feedback error={op.error || profile.error} notice={op.notice} />
      <button className="primary" disabled={op.busy || !profile.data}>
        Review local {kind === "event" ? "event" : "task"}
      </button>
    </form>
  );
}

export function FromCalendar({
  selected,
}: {
  selected: (r: MailRecord) => void;
}) {
  const events = useResource(() =>
    call<{ items: { id: string; title: string; start: string }[] }>(
      "calendar.search",
      { limit: 100 },
    ),
  );
  const [event, setEvent] = useState("");
  const op = useOperation();
  return (
    <section>
      <p>
        Select an existing local event. Its details become an unsent draft;
        attendees are not notified.
      </p>
      <Field label="Calendar event">
        <select
          aria-label="Calendar event"
          value={event}
          onChange={(e) => setEvent(e.target.value)}
        >
          <option value="">Choose event</option>
          {events.data?.items.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title} · {e.start}
            </option>
          ))}
        </select>
      </Field>
      <Feedback error={op.error || events.error} loading={events.loading} />
      <button
        disabled={!event || op.busy}
        onClick={() =>
          void op.run(
            async () =>
              selected(
                await call<MailRecord>("mail.calendar_draft", {
                  event_id: event,
                  recipients: [],
                }),
              ),
            "Unsent draft created.",
          )
        }
      >
        Create draft from event
      </button>
    </section>
  );
}
