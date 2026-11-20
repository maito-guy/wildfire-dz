// The fire map (DESIGN.md §9), MapLibre GL. Draw order: basemap → fire history → risk today → 2 h zone →
// 1 h zone → burning cells → next pass → alert areas → detections → pins. Pins are HTML markers that
// always carry the status word, never colour alone. A click picks a detection or history cell and opens
// its details; in Demo mode the click starts a fire instead.
import "maplibre-gl/dist/maplibre-gl.css";
import type { GeoJSONSource, MapGeoJSONFeature, MapMouseEvent, StyleSpecification } from "maplibre-gl";
import * as maplibregl from "maplibre-gl";
// MapLibre 6 looks for its worker next to its own file, which the bundle moves. Vite builds the worker
// (with its imports) as its own chunk and gives us the URL.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { ReactNode } from "react";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import type { Alert, DetectionsResponse, HistoryResponse, LatLon, PredictResponse, Village } from "../../api/client";
import { DETECTION_COLOR } from "../../api/fireMap";
import type { RiskResponse } from "../../api/risk";
import { RISK_COLOR, RISK_WORD } from "../../api/risk";
import { fmtMinutesLeft, statusWord } from "../../format";
import { mapColors, statusMapColor } from "../../map/colors";
import * as geo from "../../map/geo";
import { cn } from "@/lib/utils";

export type LayerKey =
  | "burning"
  | "zone1h"
  | "zone2h"
  | "villages"
  | "alertAreas"
  | "nextPass"
  | "detections"
  | "history"
  | "risk";

export type LayerVisibility = Record<LayerKey, boolean>;

export interface MapView {
  center: [number, number]; // lat, lon
  zoom: number;
  seq: number; // bump to re-apply the same view
}

interface Props {
  prediction: PredictResponse | null;
  burning: LatLon[];
  truth: LatLon[];
  villages: Village[];
  alerts: Alert[];
  detections: DetectionsResponse | undefined;
  history: HistoryResponse | undefined;
  risk: RiskResponse | undefined;
  layers: LayerVisibility;
  view: MapView | null;
  demo: boolean; // a click starts a fire
  onMapClick: (p: LatLon) => void;
  /** Overlay cards (layers, weather, hint), positioned by their own classes. */
  children?: ReactNode;
}

maplibregl.setWorkerUrl(workerUrl);

const HOME: [number, number] = [4.1, 36.6]; // lon, lat
// Light, low-saturation basemap so red and orange stay the loudest things on screen.
const BASEMAP = "https://tiles.openfreemap.org/styles/positron";
const STYLE_TIMEOUT_MS = 4000;
// Offline (a hall with no internet): plain land, the fire layers still draw.
const OFFLINE_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": mapColors.land } }],
};

async function loadStyle(): Promise<string | StyleSpecification> {
  try {
    const ctl = new AbortController();
    const t = window.setTimeout(() => ctl.abort(), STYLE_TIMEOUT_MS);
    const r = await fetch(BASEMAP, { signal: ctl.signal });
    window.clearTimeout(t);
    if (!r.ok) return OFFLINE_STYLE;
    return (await r.json()) as StyleSpecification;
  } catch {
    return OFFLINE_STYLE;
  }
}

// Which style layers each toggle drives.
const LAYER_IDS: Record<Exclude<LayerKey, "villages">, string[]> = {
  history: ["history"],
  risk: ["risk"],
  zone2h: ["zone2h-fill", "zone2h-line"],
  zone1h: ["zone1h-fill", "zone1h-line"],
  burning: ["burning"],
  nextPass: ["next-pass"],
  alertAreas: ["alert-areas"],
  detections: ["detections"],
};

const PICK_PX = 8;

function addLayers(map: maplibregl.Map) {
  // Quiet the basemap: our land and sea, so the fire colours stay the loudest.
  for (const l of map.getStyle().layers ?? []) {
    if (l.type === "background") map.setPaintProperty(l.id, "background-color", mapColors.land);
    if (l.type === "fill" && /water|ocean|sea/i.test(l.id)) map.setPaintProperty(l.id, "fill-color", mapColors.sea);
  }
  const src = (id: string) => map.addSource(id, { type: "geojson", data: geo.EMPTY });
  ["history", "risk", "zones", "burning", "next-pass", "alert-areas", "detections"].forEach(src);

  map.addLayer({
    id: "history",
    type: "fill",
    source: "history",
    paint: { "fill-color": ["get", "color"], "fill-opacity": 0.55 },
  });
  map.addLayer({
    id: "risk",
    type: "fill",
    source: "risk",
    paint: {
      "fill-color": [
        "match",
        ["get", "level"],
        "very_high",
        RISK_COLOR.very_high,
        "high",
        RISK_COLOR.high,
        "moderate",
        RISK_COLOR.moderate,
        RISK_COLOR.low,
      ],
      "fill-opacity": 0.4,
    },
  });
  map.addLayer({
    id: "zone2h-fill",
    type: "fill",
    source: "zones",
    filter: ["==", ["get", "horizon"], 120],
    paint: { "fill-color": mapColors.zone2hFill },
  });
  map.addLayer({
    id: "zone2h-line",
    type: "line",
    source: "zones",
    filter: ["==", ["get", "horizon"], 120],
    paint: { "line-color": mapColors.zone2hLine, "line-width": 2, "line-dasharray": [4, 3] },
  });
  map.addLayer({
    id: "zone1h-fill",
    type: "fill",
    source: "zones",
    filter: ["==", ["get", "horizon"], 60],
    paint: { "fill-color": mapColors.zone1hFill },
  });
  map.addLayer({
    id: "zone1h-line",
    type: "line",
    source: "zones",
    filter: ["==", ["get", "horizon"], 60],
    paint: { "line-color": mapColors.zone1hLine, "line-width": 2.5 },
  });
  map.addLayer({
    id: "burning",
    type: "fill",
    source: "burning",
    paint: {
      "fill-color": [
        "match",
        ["get", "part"],
        "core",
        mapColors.burningCore,
        "edge",
        mapColors.burningEdge,
        mapColors.burning,
      ],
      "fill-outline-color": "#ffffff",
    },
  });
  map.addLayer({
    id: "next-pass",
    type: "line",
    source: "next-pass",
    paint: { "line-color": mapColors.nextPassLine, "line-opacity": 0.7, "line-width": 1.5, "line-dasharray": [1, 2] },
  });
  map.addLayer({
    id: "alert-areas",
    type: "line",
    source: "alert-areas",
    paint: { "line-color": mapColors.alertArea, "line-opacity": 0.6, "line-width": 1.5, "line-dasharray": [2, 2] },
  });
  map.addLayer({
    id: "detections",
    type: "circle",
    source: "detections",
    paint: {
      "circle-color": ["match", ["get", "age"], "day", DETECTION_COLOR.day, DETECTION_COLOR.week],
      "circle-radius": ["match", ["get", "age"], "day", 4.5, 3],
      "circle-stroke-color": mapColors.ink,
      "circle-stroke-width": 1,
      "circle-opacity": 0.9,
    },
  });
}

// ---- popups (built with textContent, never innerHTML: values come from data files) ----

function popupNode(title: string, lines: [string, string][]): HTMLElement {
  const div = document.createElement("div");
  div.className = "font-sans text-xs leading-snug text-ink";
  const b = document.createElement("div");
  b.className = "label-mono mb-1";
  b.textContent = title;
  div.append(b);
  for (const [k, v] of lines) {
    const row = document.createElement("div");
    row.className = "tabular-nums";
    row.textContent = `${k}: ${v}`;
    div.append(row);
  }
  return div;
}

function detectionPopup(f: MapGeoJSONFeature, stub: boolean): HTMLElement {
  const p = f.properties as { t: string; satellite: string; frp: number; confidence: string };
  const lines: [string, string][] = [
    ["Time", new Date(p.t).toUTCString()],
    ["Satellite", p.satellite || "unknown"],
    ["FRP", p.frp >= 0 ? `${p.frp} MW` : "unknown"],
  ];
  if (p.confidence) lines.push(["Confidence", p.confidence === "h" ? "high" : "nominal"]);
  return popupNode(stub ? "Detection · stub data" : "Satellite detection", lines);
}

function historyPopup(f: MapGeoJSONFeature, stub: boolean): HTMLElement {
  const p = f.properties as { count: number; years: number; last_year: number };
  const lines: [string, string][] = [["Detections", String(p.count)]];
  if (p.years >= 0) lines.push(["Years with fire", String(p.years)]);
  if (p.last_year >= 0) lines.push(["Last fire", String(p.last_year)]);
  return popupNode(stub ? "Fire history · stub data" : "Fire history", lines);
}

// ---- pins: white card with a 3 px status strip, name and status line (DESIGN.md §8) ----

const STATUS_TEXT: Record<string, string> = {
  leave_now: "text-fire-text",
  get_ready: "text-flame-text",
  safe: "text-safe",
};

function pinElement(name: string, statusLine: string, color: string, textClass: string, small: boolean): HTMLElement {
  const el = document.createElement("div");
  el.className = "flex items-center gap-1.5 pointer-events-none select-none";
  const dot = document.createElement("span");
  dot.className = cn("block shrink-0 rounded-full ring-[3px] ring-white shadow-1", small ? "size-3" : "size-3.5");
  dot.style.background = color;
  const card = document.createElement("div");
  card.className = "w-[150px] rounded-md border-l-[3px] bg-card px-2.5 py-1.5 shadow-1";
  card.style.borderLeftColor = color;
  const n = document.createElement("div");
  n.className = "truncate text-[13px] font-semibold leading-tight text-ink";
  n.textContent = name;
  const s = document.createElement("div");
  s.className = cn("status-word mt-0.5 tabular-nums", textClass);
  s.textContent = statusLine;
  card.append(n, s);
  el.append(dot, card);
  return el;
}

/** SAFE villages are a small grey dot: cards only for villages that must act, so the map stays readable. */
function safeDot(name: string, line: string): HTMLElement {
  const el = document.createElement("div");
  el.className = "flex items-center";
  const dot = document.createElement("span");
  dot.className = "block size-2.5 rounded-full bg-safe ring-2 ring-white";
  el.title = `${name}: ${line}`;
  el.append(dot);
  return el;
}

function villageStatusLine(v: Village): string {
  if (v.status === "safe") return `${statusWord(v.status)} · ${v.distance_km.toFixed(1)} km`;
  return `${statusWord(v.status)} · ${fmtMinutesLeft(v.minutes_left)}`;
}

interface PinItem {
  id: string;
  lat: number;
  lon: number;
  el: () => HTMLElement;
}

/** Keeps one marker per item. `dataKey` changes only when the items do, so markers are not rebuilt every render. */
function useMarkers(map: maplibregl.Map | null, dataKey: string, items: PinItem[], visible: boolean) {
  const markers = useRef(new Map<string, maplibregl.Marker>());
  const build = useEffectEvent(() => {
    if (!map) return;
    for (const m of markers.current.values()) m.remove();
    markers.current.clear();
    for (const i of items) {
      // The dot (first 14 px) sits on the point; the card hangs to its right.
      const el = i.el();
      const card = el.childElementCount > 1;
      const m = new maplibregl.Marker({ element: el, anchor: card ? "left" : "center", offset: card ? [-7, 0] : [0, 0] })
        .setLngLat([i.lon, i.lat])
        .addTo(map);
      markers.current.set(i.id, m);
    }
  });
  useEffect(() => {
    build();
  }, [map, dataKey]);
  useEffect(() => {
    for (const m of markers.current.values()) m.getElement().style.display = visible ? "" : "none";
  }, [map, dataKey, visible]);
  useEffect(() => {
    const all = markers.current;
    return () => {
      for (const m of all.values()) m.remove();
      all.clear();
    };
  }, [map]);
}

export function FireMap(p: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<maplibregl.Map | null>(null); // set once the style and our layers are in

  const onClick = useEffectEvent((e: MapMouseEvent) => {
    if (!map) return;
    if (p.demo) {
      p.onMapClick({ lat: e.lngLat.lat, lon: e.lngLat.lng });
      return;
    }
    const { x, y } = e.point;
    const bbox: [[number, number], [number, number]] = [
      [x - PICK_PX, y - PICK_PX],
      [x + PICK_PX, y + PICK_PX],
    ];
    const det = p.layers.detections ? map.queryRenderedFeatures(bbox, { layers: ["detections"] })[0] : undefined;
    if (det) {
      const [lon, lat] = (det.geometry as GeoJSON.Point).coordinates;
      new maplibregl.Popup({ maxWidth: "260px" })
        .setLngLat([lon, lat])
        .setDOMContent(detectionPopup(det, !!p.detections?.stub))
        .addTo(map);
      return;
    }
    const cell = p.layers.history ? map.queryRenderedFeatures(e.point, { layers: ["history"] })[0] : undefined;
    if (cell) {
      new maplibregl.Popup({ maxWidth: "260px" })
        .setLngLat(e.lngLat)
        .setDOMContent(historyPopup(cell, !!p.history?.stub))
        .addTo(map);
    }
  });

  // Create the map once.
  useEffect(() => {
    let m: maplibregl.Map | null = null;
    let cancelled = false;
    void loadStyle().then((style) => {
      if (cancelled || !box.current) return;
      m = new maplibregl.Map({
        container: box.current,
        style,
        center: HOME,
        zoom: 10,
        maxZoom: 17,
        attributionControl: { compact: true, customAttribution: "Fire data NASA FIRMS" },
      });
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
      m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
      // Add our layers as soon as the style is parsed. "load" also waits for every basemap tile, so a slow
      // or blocked tile server would otherwise leave the fire layers and pins off the map.
      let ready = false;
      const init = () => {
        if (!m || ready || !m.isStyleLoaded()) return;
        ready = true;
        addLayers(m);
        setMap(m);
      };
      m.on("styledata", init);
      m.on("load", init);
      m.on("click", (e) => onClick(e));
    });
    return () => {
      cancelled = true;
      m?.remove();
      setMap(null);
    };
  }, []);

  // Data → sources.
  const setData = (id: string, data: GeoJSON.FeatureCollection) => (map?.getSource(id) as GeoJSONSource | undefined)?.setData(data);
  useEffect(() => void setData("zones", geo.zones(p.prediction)), [map, p.prediction]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void setData("burning", geo.burningCells(p.burning)), [map, p.burning]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void setData("next-pass", geo.nextPassCells(p.truth)), [map, p.truth]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void setData("alert-areas", geo.alertAreas(p.alerts)), [map, p.alerts]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void setData("detections", geo.detections(p.detections)), [map, p.detections]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void setData("history", geo.history(p.history)), [map, p.history]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void setData("risk", geo.riskCells(p.risk)), [map, p.risk]); // eslint-disable-line react-hooks/exhaustive-deps

  // Toggles → layer visibility.
  useEffect(() => {
    if (!map) return;
    for (const [k, ids] of Object.entries(LAYER_IDS) as [keyof typeof LAYER_IDS, string[]][]) {
      for (const id of ids) map.setLayoutProperty(id, "visibility", p.layers[k] ? "visible" : "none");
    }
  }, [map, p.layers]);

  // Requested view (replay start, a selected flag or place).
  useEffect(() => {
    if (map && p.view) map.easeTo({ center: [p.view.center[1], p.view.center[0]], zoom: p.view.zoom, duration: 600 });
  }, [map, p.view]);

  // Demo mode: crosshair.
  useEffect(() => {
    if (map) map.getCanvas().style.cursor = p.demo ? "crosshair" : "";
  }, [map, p.demo]);

  const villagePins: PinItem[] = p.villages.map((v) => ({
    id: `v-${v.id}`,
    lat: v.lat,
    lon: v.lon,
    el: () =>
      v.status === "safe"
        ? safeDot(v.name, villageStatusLine(v))
        : pinElement(v.name, villageStatusLine(v), statusMapColor[v.status], STATUS_TEXT[v.status], false),
  }));
  const riskPins: PinItem[] = p.layers.risk
    ? (p.risk?.places ?? []).map((r) => ({
        id: `r-${r.id}`,
        lat: r.lat,
        lon: r.lon,
        el: () => pinElement(r.name, `${RISK_WORD[r.level]} risk today`, RISK_COLOR[r.level], "text-fire-text", false),
      }))
    : [];
  const villageKey = JSON.stringify(p.villages.map((v) => [v.id, v.status, v.minutes_left, v.distance_km, v.lat, v.lon]));
  const riskKey = JSON.stringify(riskPins.map((r) => r.id));
  useMarkers(map, villageKey, villagePins, p.layers.villages);
  useMarkers(map, riskKey, riskPins, true);

  return (
    <div className="relative min-h-0 w-full flex-1 bg-map-land">
      {/* `absolute!`: maplibre-gl.css sets .maplibregl-map { position: relative } and loads after ours. */}
      <div ref={box} className="absolute! inset-0" aria-label="Fire map" role="region" />
      {p.children}
    </div>
  );
}
