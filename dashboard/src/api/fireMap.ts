// Fire map data (#29): GET /detections and GET /history, and the colours shared by the
// map layers and the legend (components/FireLayers.tsx).
import { useQuery } from "@tanstack/react-query";
import type { Detection, DetectionsResponse } from "./client";
import { api } from "./client";

const DAY_MS = 24 * 3600 * 1000;
const REFRESH_MS = 5 * 60 * 1000;

// DESIGN.md palette: last 24 h in fire red, 1–7 days in flame orange.
export const DETECTION_COLOR = { day: "#E3262B", week: "#F26A21" } as const;

// History: one hue, light to dark (sequential). Light on purpose: it is background context.
export const HISTORY_RAMP = ["#E8E3D9", "#D6C3A8", "#B99A78", "#8C6E52", "#5F5A53"] as const;

/** Bucket 0..4 on a log scale of count / max (a few huge fires must not flatten everything else). */
export function historyBucket(count: number, max: number): number {
  if (max <= 1) return HISTORY_RAMP.length - 1;
  const f = Math.log1p(count) / Math.log1p(max);
  return Math.min(HISTORY_RAMP.length - 1, Math.floor(f * HISTORY_RAMP.length));
}

export function splitByAge(r: DetectionsResponse | undefined) {
  const day: Detection[] = [];
  const week: Detection[] = [];
  if (!r?.newest) return { day, week };
  const cut = Date.parse(r.newest) - DAY_MS;
  for (const d of r.detections) (Date.parse(d.t) >= cut ? day : week).push(d);
  return { day, week };
}

export function useFireData() {
  const detections = useQuery({ queryKey: ["detections"], queryFn: () => api.detections(), refetchInterval: REFRESH_MS });
  const history = useQuery({ queryKey: ["history"], queryFn: api.history, staleTime: Infinity });
  return { detections, history };
}
