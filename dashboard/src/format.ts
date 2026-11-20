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

export const STATUS_COLOR: Record<Status, string> = {
  leave_now: "#b00020",
  get_ready: "#e07000",
  safe: "#2e7d32",
  update: "#1565c0",
  preventive: "#6a1b9a",
};

export function fmtAge(min: number | null | undefined): string {
  if (min == null) return "no data yet";
  return min < 60
    ? `satellite pass ${min} min ago`
    : `satellite pass ${Math.floor(min / 60)} h ${min % 60} min ago`;
}

export const fmtMinutesLeft = (m: number | null): string => (m == null ? "> 2 h" : `${m} min`);

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

export function fmtWind(w: PredictResponse["wind"]): string {
  return `${Math.round(w.speed_kmh)} km/h from ${Math.round(w.from_deg)}°`;
}

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
