import { personalDate } from "./format";
import {
  CheckCircle2,
  Circle,
  Search,
  Sun,
  CalendarClock,
  ListChecks,
  CheckCheck,
  Folder,
  Plus,
  CalendarPlus,
  Pencil,
  Trash2,
  ClipboardList,
} from "lucide-react";
import { useEffect, useMemo, useState, useRef } from "react";
import {
  WorkspacePage,
  Rail,
  Main,
  Side,
  Seg,
  Panel,
  EmptyState,
  SectionHead,
  Pill,
  Facts,
  Pager,
} from "../../components/WorkspacePage";
import { Sheet } from "../../components/Sheet";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import {
  body,
  type PersonalTask,
  type Page,
  type Profile,
  type CalendarEvent,
} from "./types";
import {
  Field,
  Feedback,
  ProjectSelect,
  ContactLinks,
  AgentAttemptLink,
  RecordSource,
  useOperation,
} from "./shared";
const empty = {
  id: "",
  uid: "",
  kind: "task",
  revision: 0,
  created_at: "",
  updated_at: "",
  title: "",
  description: "",
  status: "open",
  priority: "normal",
  due: "",
  due_kind: "date",
  timezone: "Africa/Johannesburg",
  project_id: "",
  event_id: "",
  contact_ids: [],
  completed_at: "",
} satisfies PersonalTask;
const VIEWS: { value: string; label: string; icon: typeof Sun; hint: string }[] = [
  { value: "Today", label: "Today", icon: Sun, hint: "Due today and overdue" },
  { value: "Upcoming", label: "Upcoming", icon: CalendarClock, hint: "Due in the coming days" },
  { value: "All", label: "All", icon: ListChecks, hint: "Every open task" },
  { value: "Completed", label: "Completed", icon: CheckCheck, hint: "Done" },
  { value: "Project", label: "By project", icon: Folder, hint: "Tasks of one project" },
];
const GROUPS = ["Overdue", "Today", "Tomorrow", "This week", "Later", "No deadline", "Completed"] as const;
type Group = (typeof GROUPS)[number];
// Buckets by calendar day in the local zone; times are ignored on purpose.
function groupOf(task: PersonalTask, now: Date): Group {
  if (task.status === "completed") return "Completed";
  if (!task.due) return "No deadline";
  const due = new Date(task.due.length === 10 ? task.due + "T12:00:00" : task.due);
  if (Number.isNaN(due.getTime())) return "No deadline";
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.floor((new Date(due.getFullYear(), due.getMonth(), due.getDate()).getTime() - start.getTime()) / 86400000);
  if (days < 0) return "Overdue";
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days < 7) return "This week";
  return "Later";
}
export default function Tasks({
  target,
  createRequest = 0,
}: {
  target?: { id: string; revision: number };
  createRequest?: number;
}) {
  const [view, setView] = useState("Today"),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [project, setProject] = useState(""),
    [edit, setEdit] = useState<PersonalTask>(),
    [schedule, setSchedule] = useState<PersonalTask>(),
    [slot, setSlot] = useState<{ start: string; end: string }>(),
    [duration, setDuration] = useState(60),
    [selectedId, setSelectedId] = useState("");
  const r = useResource(
    () =>
      call<Page<PersonalTask>>("tasks.search", {
        query,
        project_id: view === "Project" ? project : "",
        view,
        limit: 50,
        offset: page * 50,
      }),
    ["personal.changed"],
    query + project + page + view,
  );
  const profile = useResource(
    () => call<Profile>("profile.get", {}),
    ["personal.changed"],
  );
  const handledCreate = useRef(0);
  useEffect(() => {
    if (
      createRequest &&
      createRequest !== handledCreate.current &&
      profile.data
    ) {
      handledCreate.current = createRequest;
      setEdit({ ...empty, timezone: profile.data.timezone });
    }
  }, [createRequest, profile.data]);
  const events = useResource(
    () => call<Page<CalendarEvent>>("calendar.search", { limit: 100 }),
    ["personal.changed"],
  );
  const [slots, setSlots] = useState<{ start: string; end: string }[]>([]);
  const op = useOperation(r.refresh);
  const [targetError, setTargetError] = useState("");
  useEffect(() => {
    if (!target) return;
    let active = true;
    void call<PersonalTask>("tasks.get", { record_id: target.id })
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

  const rows = r.data?.items || [];
  const selected = rows.find((t) => t.id === selectedId);
  const grouped = useMemo(() => {
    const now = new Date();
    const buckets = new Map<Group, PersonalTask[]>();
    for (const task of rows) {
      const group = groupOf(task, now);
      buckets.set(group, [...(buckets.get(group) || []), task]);
    }
    return GROUPS.filter((g) => buckets.has(g)).map((g) => [g, buckets.get(g)!] as const);
  }, [rows]);
  const projects = useResource(
    () => call<{ id: string; title: string }[]>("data.projects", {}),
    ["projects"],
  );
  const projectTitle = (id: string) => projects.data?.find((p) => p.id === id)?.title;
  const current = VIEWS.find((v) => v.value === view) || VIEWS[0];
  const newTask = () =>
    setEdit({
      ...empty,
      timezone: profile.data?.timezone || empty.timezone,
    });
  const toggle = (t: PersonalTask) =>
    void op.run(
      () =>
        call(
          t.status === "completed" ? "tasks.reopen" : "tasks.complete",
          { record_id: t.id, revision: t.revision },
        ),
      t.status === "completed"
        ? "Task reopened."
        : "Task completed. Future pending reminders cancelled.",
    );
  const remove = (t: PersonalTask) =>
    void op.run(
      () =>
        call("tasks.delete", {
          record_id: t.id,
          revision: t.revision,
        }),
      "Task deleted.",
    );
  const openSchedule = (t: PersonalTask) => {
    setSchedule(t);
    setSlots([]);
    setSlot(undefined);
  };
  const count = rows.length;
  return (
    <WorkspacePage
      layout="fill"
      className="tasks"
      icon={<ListChecks size={18} />}
      title="Tasks"
      description="Personal commitments. Completing a task does not run or complete an Agent attempt."
      actions={
        <button className="primary" onClick={newTask}>
          <Plus size={16} aria-hidden="true" />
          New Task
        </button>
      }
      rail={
        <Rail title="Views" label="Task views">
          <Seg
            vertical
            label="Task view"
            value={view}
            onChange={(v) => {
              setView(v);
              setPage(0);
              setSelectedId("");
            }}
            options={VIEWS.map((v) => ({
              value: v.value,
              label: v.label,
              icon: <v.icon size={15} aria-hidden="true" />,
              title: v.hint,
            }))}
          />
          {view === "Project" && (
            <div className="tasks-rail-project">
              <ProjectSelect value={project} onChange={setProject} />
            </div>
          )}
        </Rail>
      }
      side={
        <Side title={selected ? "Task" : "Details"} label="Task details">
          {selected ? (
            <>
              <div className="tasks-detail-head">
                <button
                  aria-label={`${selected.status === "completed" ? "Reopen" : "Complete"} ${selected.title}`}
                  className="task-check"
                  data-done={selected.status === "completed"}
                  title={selected.status === "completed" ? "Reopen" : "Complete"}
                  onClick={() => toggle(selected)}
                >
                  {selected.status === "completed" ? (
                    <CheckCircle2 size={20} aria-hidden="true" />
                  ) : (
                    <Circle size={20} aria-hidden="true" />
                  )}
                </button>
                <h3>{selected.title}</h3>
              </div>
              {selected.description ? (
                <p className="tasks-detail-description">{selected.description}</p>
              ) : (
                <p className="tasks-detail-description muted">No description.</p>
              )}
              <Facts
                items={[
                  ["Due", selected.due ? personalDate(selected.due, profile.data) : "No deadline"],
                  ["Priority", <Pill tone={selected.priority === "high" ? "warning" : undefined}>{selected.priority}</Pill>],
                  ["Status", selected.status === "completed" ? "Completed" : "Open"],
                  ["Project", selected.project_id ? projectTitle(selected.project_id) || "Linked project" : "None"],
                  ["Calendar", selected.event_id ? "Work block linked" : "Not scheduled"],
                ]}
              />
              <div className="tasks-detail-actions">
                <button className="primary" onClick={() => setEdit(selected)}>
                  <Pencil size={14} aria-hidden="true" />
                  Edit task
                </button>
                <button onClick={() => openSchedule(selected)}>
                  <CalendarPlus size={14} aria-hidden="true" />
                  Find a work block
                </button>
                <button className="quiet danger-action" onClick={() => remove(selected)}>
                  <Trash2 size={14} aria-hidden="true" />
                  Delete task
                </button>
              </div>
            </>
          ) : (
            <EmptyState compact icon={<ClipboardList size={20} />} title="Nothing selected" headingLevel={3}>
              Choose a task to see its description, deadline and links here.
            </EmptyState>
          )}
        </Side>
      }
    >
      <Main className="tasks-main" label="Task list">
        <div className="tasks-toolbar">
          <div className="tasks-toolbar-title">
            <h2>{current.label}</h2>
            <span>{r.loading ? "Loading…" : `${count}${r.data?.has_more ? "+" : ""} task${count === 1 ? "" : "s"}`}</span>
          </div>
          <label className="search">
            <Search size={15} aria-hidden="true" />
            <input
              aria-label="Search tasks"
              placeholder="Search personal tasks"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </label>
        </div>
        <Feedback
          error={targetError || op.error || r.error}
          notice={op.notice}
        />
        <div className="personal-task-list tasks-groups">
          {rows.length ? (
            grouped.map(([group, tasks]) => (
              <section className="tasks-group" key={group} aria-label={group}>
                <SectionHead>
                  {group} · {tasks.length}
                </SectionHead>
                <Panel tight>
                  {tasks.map((t) => (
                    <article
                      className={`personal-task ${t.id === selectedId ? "selected" : ""}`}
                      key={t.id}
                      data-group={group}
                    >
                      <button
                        aria-label={`${t.status === "completed" ? "Reopen" : "Complete"} ${t.title}`}
                        onClick={() => toggle(t)}
                        className="task-check"
                        data-done={t.status === "completed"}
                        title={t.status === "completed" ? "Reopen" : "Complete"}
                      >
                        {t.status === "completed" ? (
                          <CheckCircle2 size={18} aria-hidden="true" />
                        ) : (
                          <Circle size={18} aria-hidden="true" />
                        )}
                      </button>
                      <button
                        className="personal-task-title"
                        aria-pressed={t.id === selectedId}
                        onClick={() => {
                          setSelectedId(t.id);
                          if (window.innerWidth <= 1180) setEdit(t);
                        }}
                      >
                        <strong>{t.title}</strong>
                        <span className="muted">
                          {t.due ? personalDate(t.due, profile.data) : "No deadline"}{" "}
                          ·{" "}
                          <span
                            className={t.priority === "normal" ? "" : "badge"}
                            data-tone={t.priority === "high" ? "warning" : "neutral"}
                          >
                            {t.priority}
                          </span>
                          {t.project_id && projectTitle(t.project_id) ? ` · ${projectTitle(t.project_id)}` : ""}
                          {t.event_id ? " · Calendar block linked" : ""}
                        </span>
                      </button>
                      <button className="quiet" onClick={() => openSchedule(t)}>
                        Schedule
                      </button>
                      <button
                        className="quiet"
                        aria-label={`Delete ${t.title}`}
                        onClick={() => remove(t)}
                      >
                        Delete…
                      </button>
                    </article>
                  ))}
                </Panel>
              </section>
            ))
          ) : (
            !r.loading && (
              <EmptyState
                className="personal-empty"
                icon={<current.icon size={24} />}
                title={
                  query
                    ? "No task matches that search"
                    : view === "Completed"
                      ? "Nothing completed yet"
                      : view === "Today"
                        ? "A clear day"
                        : "A little clarity for your day"
                }
                actions={
                  <>
                    <button className="primary" onClick={newTask}>
                      <Plus size={14} aria-hidden="true" />
                      Create a task
                    </button>
                    {view !== "All" && !query && (
                      <button className="quiet" onClick={() => setView("All")}>
                        Show all tasks
                      </button>
                    )}
                  </>
                }
              >
                {query
                  ? "Try a different word, or clear the search."
                  : view === "Completed"
                    ? "Completed tasks land here, with their completion date."
                    : view === "Today"
                      ? "Nothing is due today. Create a personal task or look at what is upcoming. Unscheduled tasks stay tasks."
                      : "Create a personal task or choose another view. Unscheduled tasks stay tasks."}
              </EmptyState>
            )
          )}
        </div>
        <Pager
          page={page + 1}
          pages={r.data?.has_more ? page + 2 : page + 1}
          onPrevious={() => setPage(page - 1)}
          onNext={() => setPage(page + 1)}
        />
      </Main>
      <Sheet
        open={!!edit}
        onOpenChange={(open) => {
          if (!open) setEdit(undefined);
        }}
        title={edit?.id ? "Edit Task" : "New Task"}
        description="Save a personal commitment. No code or Agent action is executed."
      >
        {edit && (
          <form
            className="personal-form"
            onSubmit={(e) => {
              e.preventDefault();
              void op.run(async () => {
                await call(edit.id ? "tasks.update" : "tasks.create", {
                  body: body(edit),
                  ...(edit.id
                    ? { record_id: edit.id, revision: edit.revision }
                    : {}),
                });
                if (!edit.id) {
                  setView("All");
                  setPage(0);
                }
                setEdit(undefined);
              }, "Task saved locally.");
            }}
          >
            <Field label="Task title">
              <input
                required
                aria-label="Task title"
                value={edit.title}
                onChange={(e) => setEdit({ ...edit, title: e.target.value })}
              />
            </Field>
            <Field label="Task description">
              <textarea
                aria-label="Task description"
                value={edit.description}
                onChange={(e) =>
                  setEdit({ ...edit, description: e.target.value })
                }
              />
            </Field>
            <div className="personal-form-grid">
              <Field label="Priority">
                <select
                  aria-label="Priority"
                  value={edit.priority}
                  onChange={(e) =>
                    setEdit({ ...edit, priority: e.target.value })
                  }
                >
                  {["low", "normal", "high"].map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </Field>
              <Field label="Deadline type">
                <select
                  aria-label="Deadline type"
                  value={edit.due_kind}
                  onChange={(e) =>
                    setEdit({ ...edit, due_kind: e.target.value, due: "" })
                  }
                >
                  <option value="date">Date only</option>
                  <option value="time">Date and time</option>
                </select>
              </Field>
            </div>
            <Field label="Due">
              <input
                aria-label="Task due"
                type={edit.due_kind === "date" ? "date" : "datetime-local"}
                value={edit.due.slice(0, edit.due_kind === "date" ? 10 : 16)}
                onChange={(e) => setEdit({ ...edit, due: e.target.value })}
              />
            </Field>
            <Field label="Task timezone">
              <input
                aria-label="Task timezone"
                value={edit.timezone}
                onChange={(e) => setEdit({ ...edit, timezone: e.target.value })}
              />
            </Field>
            <ProjectSelect
              value={edit.project_id}
              onChange={(project_id) => setEdit({ ...edit, project_id })}
            />
            <Field label="Linked calendar block">
              <select
                aria-label="Linked calendar block"
                value={edit.event_id}
                onChange={(e) => setEdit({ ...edit, event_id: e.target.value })}
              >
                <option value="">No calendar block</option>
                {events.data?.items.map((event) => (
                  <option value={event.id} key={event.id}>
                    {event.title} · {event.start}
                  </option>
                ))}
              </select>
            </Field>
            <AgentAttemptLink
              value={edit.agent_task_id || ""}
              onChange={(agent_task_id) => setEdit({ ...edit, agent_task_id })}
            />
            <RecordSource record={edit} />
            <ContactLinks
              values={edit.contact_ids}
              onChange={(contact_ids) => setEdit({ ...edit, contact_ids })}
            />
            <Feedback error={op.error} />
            <button className="primary" disabled={op.busy}>
              Save Task
            </button>
          </form>
        )}
      </Sheet>
      <Sheet
        open={!!schedule}
        onOpenChange={(open) => {
          if (!open) setSchedule(undefined);
        }}
        title="Find a work block"
        description="Candidates use native calendar intervals and working hours. Nothing is booked until you save."
      >
        <Field label="Minutes needed">
          <input
            aria-label="Minutes needed"
            type="number"
            min={5}
            max={1440}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
        </Field>
        <button
          disabled={op.busy}
          onClick={() =>
            void op.run(async () => {
              const now = new Date(),
                end = new Date(now);
              end.setDate(end.getDate() + 7);
              const result = await call<Page<{ start: string; end: string }>>(
                "calendar.free_busy",
                {
                  after: now.toISOString(),
                  before: end.toISOString(),
                  duration,
                },
              );
              setSlots(result.items);
            }, "Free-time candidates calculated; not booked.")
          }
        >
          Find free time this week
        </button>
        {slots.map((s) => (
          <label className="personal-check" key={s.start}>
            <input
              type="radio"
              name="slot"
              checked={slot?.start === s.start}
              onChange={() => setSlot(s)}
            />
            {new Date(s.start).toLocaleString()} –{" "}
            {new Date(s.end).toLocaleTimeString()}
          </label>
        ))}
        <Feedback error={op.error} />
        <button
          className="primary"
          disabled={!slot || op.busy}
          onClick={() =>
            void op.run(async () => {
              if (!slot || !schedule || !profile.data) return;
              await call("tasks.schedule", {
                record_id: schedule.id,
                revision: schedule.revision,
                event_body: {
                  calendar_id: profile.data.default_calendar,
                  title: schedule.title,
                  start: slot.start,
                  end: slot.end,
                  timezone: profile.data.timezone,
                },
              });
              setSchedule(undefined);
            }, "Calendar block saved and linked to the task.")
          }
        >
          Save linked work block
        </button>
      </Sheet>
    </WorkspacePage>
  );
}
