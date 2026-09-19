import type { Profile } from "./types";
export function personalDate(
  value: string,
  profile?: Pick<
    Profile,
    "timezone" | "locale" | "date_format" | "time_format"
  >,
) {
  if (!value) return "No date";
  const timed = value.includes("T");
  const instant = new Date(timed ? value : value + "T12:00:00Z");
  if (Number.isNaN(instant.getTime())) return value;
  const zone = timed ? profile?.timezone || "Africa/Johannesburg" : "UTC";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(instant);
  const part = (type: string) =>
    parts.find((p) => p.type === type)?.value || "";
  const date = (profile?.date_format || "dd/MM/yyyy")
    .replace("yyyy", part("year"))
    .replace("MM", part("month"))
    .replace("dd", part("day"));
  return (
    date +
    (timed
      ? " " +
        new Intl.DateTimeFormat(profile?.locale || "en-ZA", {
          timeZone: zone,
          hour: "2-digit",
          minute: "2-digit",
          hour12: profile?.time_format === "12h",
        }).format(instant)
      : "")
  );
}
