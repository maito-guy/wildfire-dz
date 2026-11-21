import type { Alert, PredictResponse, Village } from "./api/client";

type Status = Village["status"] | Alert["level"];

const WORDS: Record<Status, string> = {
  leave_now: "Leave now",
  get_ready: "Get ready",
  safe: "Safe",
  update: "Update",
  preventive: "Preventive",
};

export const statusWord = (s: Status): string => WORDS[s];

export function fmtAge(min: number | null | undefined): string {
  if (min == null) return "no data yet";
  return min < 60
    ? `satellite pass ${min} min ago`
    : `satellite pass ${Math.floor(min / 60)} h ${min % 60} min ago`;
}

export const fmtMinutesLeft = (m: number | null): string => (m == null ? "> 2 h" : `${m} min`);

/** Arrival time for the B · AI line: "45 min", "1 h", "1 h 50"; "—" when the model has no time. */
export function fmtArrival(m: number | null | undefined): string {
  if (m == null) return "—";
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r === 0 ? `${h} h` : `${h} h ${String(r).padStart(2, "0")}`;
}

/** Both models' arrival side by side, e.g. "B: 45 min · AI: 1 h 50". B is the model of record; AI is advice. */
export const fmtBothTimes = (b: number | null | undefined, ai: number | null | undefined): string =>
  bothTimesParts(b, ai).join(" ");

/** The same line in two pieces ("B: 45 min ·", "AI: 1 h 50"), so a narrow column can wrap between them. */
export const bothTimesParts = (b: number | null | undefined, ai: number | null | undefined): [string, string] => [
  `B: ${fmtArrival(b)} ·`,
  `AI: ${fmtArrival(ai)}`,
];

/** Hover text for the B · AI line. C answers in steps (20, 30, 45 … 120), so 20 means "within 20 min". */
export const BOTH_TIMES_TITLE =
  "B: the spread model that makes the flags. AI: model C's estimate (advice only, check before acting); " +
  "its minutes are steps, so 20 means within 20 min. — = no time from that model.";

const RANK: Record<Village["status"], number> = { leave_now: 0, get_ready: 1, safe: 2 };

// Most urgent first: status, then minutes left (unknown last), then distance.
export function sortByUrgency(villages: Village[]): Village[] {
  return [...villages].sort(
    (a, b) =>
      RANK[a.status] - RANK[b.status] ||
      (a.minutes_left ?? Infinity) - (b.minutes_left ?? Infinity) ||
      a.distance_km - b.distance_km,
  );
}

const ALERT_STATUS: Record<Alert["status"], string> = {
  pending: "pending approval",
  sent: "sent",
  rejected: "rejected",
  cancelled: "cancelled",
};

export const alertStatusWord = (s: Alert["status"]): string => ALERT_STATUS[s];

const WIND_SOURCE: Record<PredictResponse["wind_source"], string> = {
  request: "set by operator",
  forecast: "forecast",
  reanalysis: "ERA5 archive",
  config_default: "default (offline)",
};

export const windSourceWord = (s: PredictResponse["wind_source"]): string => WIND_SOURCE[s];

// Local wall-clock time, 24 h, e.g. "14:05".
export const fmtClock = (t: string | number): string =>
  new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

// When the alert last changed state: the timestamp that matches its status.
export function lastChangeAt(a: Alert): string {
  switch (a.status) {
    case "sent":
      return a.approved_at ?? a.created_at;
    case "rejected":
      return a.rejected_at ?? a.created_at;
    case "cancelled":
      return a.cancelled_at ?? a.created_at;
    case "pending":
      return a.created_at;
  }
}

// Only published alerts have a CAP message (Alert for sent, Cancel for cancelled).
export const hasCap = (a: Alert): boolean => a.status === "sent" || a.status === "cancelled";
