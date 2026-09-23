// Pure layout for the V2 week/day time grid. Events are placed by their real
// start and end in the profile's time zone; overlapping events share the
// column side by side. Nothing is rounded into a different slot.

export interface TimedItem {
  id: string;
  start: string;
  end: string;
}
export interface PlacedItem<T> {
  item: T;
  /** Minutes from local midnight, clipped to the day. */
  top: number;
  bottom: number;
  lane: number;
  lanes: number;
}

/** Minutes since midnight of `instant` in `timeZone` (0–1439). */
export function minutesInZone(instant: Date, timeZone: string): number {
  try {
    const parts = new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(instant);
    const hour = Number(parts.find((p) => p.type === "hour")?.value || 0);
    const minute = Number(parts.find((p) => p.type === "minute")?.value || 0);
    return (hour % 24) * 60 + minute;
  } catch {
    return instant.getHours() * 60 + instant.getMinutes();
  }
}

/** YYYY-MM-DD of `instant` in `timeZone`. */
export function dayInZone(instant: Date, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone }).format(instant);
  } catch {
    return instant.toISOString().slice(0, 10);
  }
}

/** Place the timed items that intersect `day` (YYYY-MM-DD) on a 24 h column. */
export function placeDay<T extends TimedItem>(items: T[], day: string, timeZone: string): PlacedItem<T>[] {
  const placed = items
    .map((item) => {
      const start = new Date(item.start);
      const end = new Date(item.end);
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
      const startDay = dayInZone(start, timeZone);
      const endDay = dayInZone(new Date(end.getTime() - 1), timeZone);
      if (startDay > day || endDay < day) return null;
      const top = startDay < day ? 0 : minutesInZone(start, timeZone);
      const bottomRaw = endDay > day ? 1440 : minutesInZone(end, timeZone) || 1440;
      const bottom = Math.max(top + 15, bottomRaw);
      return { item, top, bottom, lane: 0, lanes: 1 };
    })
    .filter(Boolean) as PlacedItem<T>[];
  placed.sort((a, b) => a.top - b.top || b.bottom - a.bottom);
  // Greedy lanes inside clusters of overlapping events.
  let cluster: PlacedItem<T>[] = [];
  let clusterEnd = -1;
  const finish = () => {
    const lanes = Math.max(1, ...cluster.map((p) => p.lane + 1));
    cluster.forEach((p) => (p.lanes = lanes));
    cluster = [];
  };
  for (const entry of placed) {
    if (entry.top >= clusterEnd && cluster.length) finish();
    const used = new Set(cluster.filter((p) => p.bottom > entry.top).map((p) => p.lane));
    let lane = 0;
    while (used.has(lane)) lane++;
    entry.lane = lane;
    cluster.push(entry);
    clusterEnd = Math.max(clusterEnd, entry.bottom);
  }
  if (cluster.length) finish();
  return placed;
}

/** The range title for a view: "21 – 27 September 2026", "September 2026". */
export function rangeTitle(view: string, days: Date[], locale: string): string {
  const first = days[0];
  const last = days[days.length - 1];
  const format = (d: Date, options: Intl.DateTimeFormatOptions) => d.toLocaleDateString(locale, options);
  if (view === "Day") return format(first, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  if (view === "Week") {
    if (first.getMonth() === last.getMonth())
      return `${first.getDate()} – ${format(last, { day: "numeric", month: "long", year: "numeric" })}`;
    return `${format(first, { day: "numeric", month: "short" })} – ${format(last, { day: "numeric", month: "short", year: "numeric" })}`;
  }
  const middle = days[Math.floor(days.length / 2)];
  return format(middle, { month: "long", year: "numeric" });
}

/** A 6×7 mini-month for the rail, weeks starting Monday. */
export function miniMonth(anchor: Date): Date[] {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1, 12);
  const start = new Date(first);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    return d;
  });
}
