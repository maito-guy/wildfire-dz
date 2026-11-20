import type { Alert, Village } from "./api/client";

type Status = Village["status"] | Alert["level"];

const WORDS: Record<Status, string> = {
  leave_now: "Leave now",
  get_ready: "Get ready",
  safe: "Safe",
  update: "Update",
};

export const statusWord = (s: Status): string => WORDS[s];

export const STATUS_COLOR: Record<Status, string> = {
  leave_now: "#b00020",
  get_ready: "#e07000",
  safe: "#2e7d32",
  update: "#1565c0",
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
