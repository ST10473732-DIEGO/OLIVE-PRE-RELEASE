/** A short, readable moment for lists: "Today 20:20", "Yesterday 14:44", "23 Sep 14:44". */
export function whenLabel(value: string, now = new Date()): string {
  const instant = new Date(value);
  if (!value || Number.isNaN(instant.getTime())) return value;
  const time = instant.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(now) - day(instant)) / 86_400_000);
  if (days === 0) return `Today ${time}`;
  if (days === 1) return `Yesterday ${time}`;
  const sameYear = instant.getFullYear() === now.getFullYear();
  const date = instant.toLocaleDateString([], { day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }) });
  return `${date} ${time}`;
}
