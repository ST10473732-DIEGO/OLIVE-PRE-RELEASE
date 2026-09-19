export type BaseRecord = {
  id: string;
  uid: string;
  revision: number;
  kind: string;
  created_at: string;
  updated_at: string;
  provenance?: Record<string, unknown>;
};
export type Profile = BaseRecord & {
  display_name: string;
  timezone: string;
  locale: string;
  avatar: string;
  date_format: string;
  time_format: string;
  default_calendar: string;
  working_hours: { days: number[]; start: string; end: string };
  recovery_warning?: string;
};
export type Labelled = { label: string; value: string };
export type Contact = BaseRecord & {
  display_name: string;
  emails: Labelled[];
  phones: Labelled[];
  organization: string;
  aliases: string[];
  notes: string;
  external_ids: Labelled[];
  project_ids: string[];
  unsupported: string[];
};
export type LocalCalendar = BaseRecord & {
  title: string;
  colour: string;
  visible: boolean;
};
export type CalendarEvent = BaseRecord & {
  calendar_id: string;
  title: string;
  description: string;
  location: string;
  start: string;
  end: string;
  timezone: string;
  all_day: boolean;
  start_fold?: number;
  end_fold?: number;
  recurrence: string;
  exceptions: Record<string, Partial<CalendarEvent> & { cancelled?: boolean }>;
  contact_ids: string[];
  project_id: string;
  status: string;
  transparent: boolean;
  unsupported: string[];
  original_ics: string;
  occurrence_id?: string;
};
export type PersonalTask = BaseRecord & {
  title: string;
  description: string;
  status: string;
  priority: string;
  due: string;
  due_kind: string;
  timezone: string;
  project_id: string;
  event_id: string;
  agent_task_id?: string;
  contact_ids: string[];
  completed_at: string;
};
export type Delivery = {
  id: string;
  reminder_id: string;
  occurrence: string;
  title: string;
  target_kind: string;
  target_id: string;
  due_at: string;
  state: string;
  delivered_at: string;
  updated_at: string;
};
export type Page<T> = { items: T[]; has_more?: boolean; offset?: number };
export type ProjectOption = { id: string; title: string };
export function body<T extends BaseRecord>(record: T) {
  const { id, uid, revision, kind, created_at, updated_at, ...data } = record;
  void [id, uid, revision, kind, created_at, updated_at];
  delete (data as Record<string, unknown>).provenance;
  delete (data as Record<string, unknown>).recovery_warning;
  delete (data as Record<string, unknown>).occurrence_id;
  return data;
}
