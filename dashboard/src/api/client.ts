// Every call to the API contract (docs/contracts.md). Types come from the
// generated schema.ts (`npm run gen:api`). URLs are relative: same origin in
// dev (Vite proxy) and in production (FastAPI serves dist/ at /dashboard/).
import { getOperatorToken } from "../operatorToken";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type PredictRequest = Schemas["PredictRequest"];
export type PredictResponse = Schemas["PredictResponse"];
export type VillagesResponse = Schemas["VillagesResponse"];
export type Village = Schemas["Village"];
export type Alert = Schemas["Alert"];
export type AlertCreate = Schemas["AlertCreate"];
export type LatLon = Schemas["LatLon"];
export type Wind = Schemas["Wind"];
export type Detection = Schemas["Detection"]; // fire map (#29)
export type DetectionsResponse = Schemas["DetectionsResponse"];
export type HistoryResponse = Schemas["HistoryResponse"];

// /replay and /replay/{id} have no response_model in FastAPI, so the schema
// types them as unknown. These mirror docs/contracts.md.
export interface ReplayFire {
  fire_id: string;
  name: string;
  n_passes: number;
  stub: boolean;
}
export interface ReplayPass {
  t: string;
  satellite?: string | null;
  burning: LatLon[];
}
export interface Replay {
  fire_id: string;
  name: string;
  stub: boolean;
  passes: ReplayPass[];
}

// /health has no response_model either. Mirrors docs/contracts.md.
export interface Health {
  ok: boolean;
  fires: number;
  phones_connected: number;
  dashboards_connected: number;
  pending_alerts: number;
  model_c_exported: boolean;
  places: "real" | "stub";
  replay: "real" | "stub";
}

// Zone features from /predict (`zones` is a GeoJSON FeatureCollection).
export interface ZoneFeature {
  type: "Feature";
  properties: { horizon_min: number };
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
}

// Model C's advice zones (`PredictResponse.ai.zones`, contract v0.6): B's zone shape plus a confidence level.
export interface AiZoneFeature {
  type: "Feature";
  properties: { horizon_min: number; confidence: "likely" | "possible" };
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
}

export class ApiError extends Error {
  readonly status: number;
  constructor(path: string, status: number, body: string) {
    super(`${path}: ${status} ${body}`);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, write = false): Promise<T> {
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

const HEALTH_TIMEOUT_MS = 10_000; // generous: one round trip on "Slow 3G" is about 2 s

const q = (fireId: string) => `?fire_id=${encodeURIComponent(fireId)}`;

export const api = {
  predict: (body: PredictRequest) =>
    request<PredictResponse>("/predict", { method: "POST", body: JSON.stringify(body) }),

  villagesAtRisk: (fireId: string) => request<VillagesResponse>(`/villages/at-risk${q(fireId)}`),

  alerts: (fireId: string) => request<Alert[]>(`/alerts${q(fireId)}`),

  sendAlert: (body: AlertCreate) =>
    request<Alert>("/alerts", { method: "POST", body: JSON.stringify(body) }, true),

  cancelAlert: (alertId: string) =>
    request<Alert>(`/alerts/${encodeURIComponent(alertId)}/cancel`, { method: "POST" }, true),

  // A hung server must count as unreachable, not as "still loading" forever.
  health: (signal: AbortSignal) =>
    request<Health>("/health", { signal: AbortSignal.any([signal, AbortSignal.timeout(HEALTH_TIMEOUT_MS)]) }),

  capUrl: (alertId: string) => `/alerts/${encodeURIComponent(alertId)}/cap.xml`,

  replays: () => request<ReplayFire[]>("/replay"),

  replay: (fireId: string) => request<Replay>(`/replay/${encodeURIComponent(fireId)}`),

  reset: () => request<{ ok: boolean }>("/reset", { method: "POST" }, true),

  // Fire map (#29). No `since`: the 7 days before the newest detection.
  detections: (since?: string) =>
    request<DetectionsResponse>(`/detections${since ? `?since=${encodeURIComponent(since)}` : ""}`),

  history: () => request<HistoryResponse>("/history"),
};

export function zoneFeatures(p: PredictResponse): ZoneFeature[] {
  const features = (p.zones as { features?: ZoneFeature[] }).features ?? [];
  // Draw the 2 h zone first so the 1 h zone sits on top.
  return [...features].sort((a, b) => b.properties.horizon_min - a.properties.horizon_min);
}
