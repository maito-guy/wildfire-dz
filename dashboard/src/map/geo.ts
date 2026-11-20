// API data → GeoJSON for the MapLibre sources (components/map/FireMap.tsx).
import type { Feature, FeatureCollection, Point, Polygon } from "geojson";
import type { Alert, DetectionsResponse, HistoryResponse, LatLon, PredictResponse } from "../api/client";
import { zoneFeatures } from "../api/client";
import type { RiskResponse } from "../api/risk";
import { HISTORY_RAMP, historyBucket, splitByAge } from "../api/fireMap";

export const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

const fc = <G extends Polygon | Point>(features: Feature<G>[]): FeatureCollection<G> => ({
  type: "FeatureCollection",
  features,
});

/** Square of half-size `hLat` degrees of latitude around a point, corrected for longitude. */
function square(lat: number, lon: number, hLat: number, hLon = hLat / Math.cos((lat * Math.PI) / 180)): Polygon {
  return {
    type: "Polygon",
    coordinates: [
      [
        [lon - hLon, lat - hLat],
        [lon + hLon, lat - hLat],
        [lon + hLon, lat + hLat],
        [lon - hLon, lat + hLat],
        [lon - hLon, lat - hLat],
      ],
    ],
  };
}

const CELL_KM = 0.375; // VIIRS cell
const KM_PER_DEG = 111.32;
const CELL_H = CELL_KM / KM_PER_DEG / 2;

/**
 * Burning 375 m cells (DESIGN.md §9): core cells (surrounded) are darker, edge cells orange.
 * `part` is core | burning | edge.
 */
export function burningCells(points: LatLon[]): FeatureCollection<Polygon> {
  const r2 = (1.6 * CELL_H * 2) ** 2;
  return fc(
    points.map((p) => {
      let n = 0;
      for (const q of points) {
        if (q === p) continue;
        const dLat = q.lat - p.lat;
        const dLon = (q.lon - p.lon) * Math.cos((p.lat * Math.PI) / 180);
        if (dLat * dLat + dLon * dLon <= r2) n++;
      }
      const part = n >= 6 ? "core" : n <= 2 ? "edge" : "burning";
      return { type: "Feature", properties: { part }, geometry: square(p.lat, p.lon, CELL_H) };
    }),
  );
}

/** Cells that really burned at the next pass (replay): drawn as dotted ink outlines. */
export function nextPassCells(points: LatLon[]): FeatureCollection<Polygon> {
  return fc(points.map((p) => ({ type: "Feature", properties: {}, geometry: square(p.lat, p.lon, CELL_H) })));
}

/** 1 h and 2 h zones from /predict, with `horizon` = 60 | 120. */
export function zones(p: PredictResponse | null): FeatureCollection {
  if (!p) return EMPTY;
  return {
    type: "FeatureCollection",
    features: zoneFeatures(p).map((f) => ({
      type: "Feature",
      properties: { horizon: f.properties.horizon_min },
      geometry: f.geometry,
    })),
  };
}

/** Circle polygon (64 steps) of `km` around a point: the alert areas. */
function circle(lat: number, lon: number, km: number): Polygon {
  const ring: [number, number][] = [];
  const dLat = km / KM_PER_DEG;
  const dLon = dLat / Math.cos((lat * Math.PI) / 180);
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return { type: "Polygon", coordinates: [ring] };
}

/** Areas of the alerts the phones have (sent only). */
export function alertAreas(alerts: Alert[]): FeatureCollection<Polygon> {
  return fc(
    alerts
      .filter((a) => a.status === "sent")
      .map((a) => ({
        type: "Feature",
        properties: { id: a.id, level: a.level },
        geometry: circle(a.area.lat, a.area.lon, a.area.radius_km),
      })),
  );
}

/** Detections as points, `age` = day | week (last 24 h before the newest, or 1–7 days). */
export function detections(r: DetectionsResponse | undefined): FeatureCollection<Point> {
  const { day, week } = splitByAge(r);
  const feat = (age: "day" | "week") => (d: (typeof day)[number]): Feature<Point> => ({
    type: "Feature",
    properties: {
      age,
      t: d.t,
      satellite: d.satellite ?? "",
      frp: d.frp ?? -1,
      confidence: d.confidence ?? "",
    },
    geometry: { type: "Point", coordinates: [d.lon, d.lat] },
  });
  // Oldest first, so the newest draw on top.
  return fc([...week.map(feat("week")).reverse(), ...day.map(feat("day")).reverse()]);
}

/** Fire history grid; `color` is the bucketed ramp colour (log scale). */
export function history(r: HistoryResponse | undefined): FeatureCollection<Polygon> {
  if (!r) return fc([]);
  const h = r.cell_deg / 2;
  return fc(
    r.cells.map((c) => ({
      type: "Feature",
      properties: {
        color: HISTORY_RAMP[historyBucket(c.count, r.max_count)],
        count: c.count,
        years: c.years ?? -1,
        last_year: c.last_year ?? -1,
      },
      geometry: square(c.lat, c.lon, h, h),
    })),
  );
}

/** Today's risk cells (square in lat/lon, as the API defines them). */
export function riskCells(r: RiskResponse | undefined): FeatureCollection<Polygon> {
  if (!r) return fc([]);
  const h = r.cell_deg / 2;
  return fc(
    r.cells.map((c) => ({
      type: "Feature",
      properties: { level: c.level, score: c.score },
      geometry: square(c.lat, c.lon, h, h),
    })),
  );
}
