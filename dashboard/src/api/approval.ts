// Approval queue calls (docs/contracts.md v0.2): pending flags, approve, reject.
// The manual alert reuses api.sendAlert from client.ts. Write calls send
// X-Operator-Token from the Settings panel (operatorToken.ts), like client.ts.
import { getOperatorToken } from "../operatorToken";
import type { Alert } from "./client";
import { ApiError } from "./client";
import type { components } from "./schema";

export type AlertApprove = components["schemas"]["AlertApprove"];

// Under the "alerts" prefix, so every existing invalidate/remove of ["alerts"]
// also covers the queue. The object part cannot collide with a fire id.
export const PENDING_KEY = ["alerts", { status: "pending" }] as const;

async function call<T>(path: string, init: RequestInit = {}, write = false): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  if (write) {
    const token = getOperatorToken();
    if (token) headers.set("X-Operator-Token", token);
  }
  const r = await fetch(path, { ...init, headers });
  if (!r.ok) throw new ApiError(path, r.status, await r.text());
  return (await r.json()) as T;
}

const alertPath = (id: string, action: string) => `/alerts/${encodeURIComponent(id)}/${action}`;

export const approval = {
  pending: () => call<Alert[]>("/alerts?status=pending"),

  approve: (id: string, body?: AlertApprove) =>
    call<Alert>(
      alertPath(id, "approve"),
      { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) },
      true,
    ),

  reject: (id: string, reason: string) =>
    call<Alert>(alertPath(id, "reject"), { method: "POST", body: JSON.stringify({ reason }) }, true),
};

/** Operator-facing words for a failed write. `stale` = the list must be refreshed. */
export function writeErrorText(e: unknown): { text: string; stale: boolean } {
  if (e instanceof ApiError) {
    if (e.status === 401) return { text: "Set the operator token in Settings.", stale: false };
    if (e.status === 409) return { text: "Already handled by someone else.", stale: true };
    if (e.status === 404) return { text: "This alert or village no longer exists.", stale: true };
    return { text: e.message, stale: false };
  }
  if (e instanceof TypeError) return { text: "Network error: check the connection and try again.", stale: false };
  return { text: e instanceof Error ? e.message : String(e), stale: false };
}

const SPREAD_FIRST = (a: Alert) => (a.level === "preventive" || a.source === "ai_risk" ? 1 : 0);

/** Spread flags first by minutes left (unknown last), then preventive; oldest first on ties. */
export function sortQueue(alerts: Alert[]): Alert[] {
  return [...alerts].sort(
    (a, b) =>
      SPREAD_FIRST(a) - SPREAD_FIRST(b) ||
      (a.minutes_left ?? Infinity) - (b.minutes_left ?? Infinity) ||
      a.created_at.localeCompare(b.created_at),
  );
}

export const SOURCE_WORD: Record<Alert["source"], string> = {
  ai_spread: "AI · spread",
  ai_risk: "AI · risk",
  manual: "Manual",
};

// Display order and names of the alert languages (docs/contracts.md: texts keys).
export const LANGS: { code: string; name: string; rtl: boolean }[] = [
  { code: "ary", name: "Darija", rtl: true },
  { code: "kab", name: "Kabyle", rtl: false },
  { code: "ar", name: "Arabic", rtl: true },
  { code: "fr", name: "French", rtl: false },
  { code: "en", name: "English", rtl: false },
];

/** The languages present in `texts`, known ones in display order, unknown ones after. */
export function langsOf(texts: Record<string, string>): { code: string; name: string; rtl: boolean }[] {
  const known = LANGS.filter((l) => l.code in texts);
  const other = Object.keys(texts)
    .filter((c) => !LANGS.some((l) => l.code === c))
    .map((code) => ({ code, name: code, rtl: false }));
  return [...known, ...other];
}
