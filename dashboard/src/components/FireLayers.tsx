// Fire map layers (#29): satellite detections (last 24 h, 1-7 days ago) and the fire history grid.
// Rendered inside <LayersControl> in FireMap. Thousands of points, so the layers are plain Leaflet
// canvas layers in their own panes. Those panes ignore the mouse, so the zones and villages below keep
// their tooltips; a map click picks the nearest detection (or history cell) and opens its popup.
import L from "leaflet";
import { useEffect, useState } from "react";
import { LayerGroup, LayersControl, useMap, useMapEvents } from "react-leaflet";
import type { Detection, DetectionsResponse, HistoryResponse } from "../api/client";
import { DETECTION_COLOR, HISTORY_RAMP, historyBucket, splitByAge } from "../api/fireMap";

const PICK_PX = 8; // click radius around a detection

const PANES = { history: ["fm-history", 350], detections: ["fm-detections", 450] } as const;

function pane(map: L.Map, which: keyof typeof PANES): L.Canvas {
  const [name, z] = PANES[which];
  if (!map.getPane(name)) {
    const el = map.createPane(name);
    el.style.zIndex = String(z);
    el.style.pointerEvents = "none";
  }
  return L.canvas({ pane: name });
}

function popupNode(lines: [string, string][], title: string): HTMLElement {
  // Built with textContent, never innerHTML: the values come from data files.
  const div = document.createElement("div");
  div.className = "fm-popup";
  const b = document.createElement("strong");
  b.textContent = title;
  div.append(b);
  for (const [k, v] of lines) {
    const row = document.createElement("div");
    row.textContent = `${k}: ${v}`;
    div.append(row);
  }
  return div;
}

function detectionPopup(d: Detection, stub: boolean): HTMLElement {
  return popupNode(
    [
      ["Time", `${new Date(d.t).toUTCString()}`],
      ["Satellite", d.satellite ?? "unknown"],
      ["FRP", d.frp != null ? `${d.frp} MW` : "unknown"],
      ...(d.confidence ? ([["Confidence", d.confidence === "h" ? "high" : "nominal"]] as [string, string][]) : []),
    ],
    stub ? "Detection (STUB DATA)" : "Satellite detection",
  );
}

function useFill(group: L.LayerGroup | null, fill: (g: L.LayerGroup) => void, deps: unknown[]) {
  useEffect(() => {
    if (!group) return;
    group.clearLayers();
    fill(group);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `fill` is rebuilt every render; deps list its inputs
  }, [group, ...deps]);
}

interface Props {
  detections: DetectionsResponse | undefined;
  history: HistoryResponse | undefined;
  suppressClick: boolean; // "start a fire here" mode owns the map click
}

export function FireLayers({ detections, history, suppressClick }: Props) {
  const map = useMap();
  const [dayG, setDayG] = useState<L.LayerGroup | null>(null);
  const [weekG, setWeekG] = useState<L.LayerGroup | null>(null);
  const [histG, setHistG] = useState<L.LayerGroup | null>(null);
  const { day, week } = splitByAge(detections);

  useFill(
    histG,
    (g) => {
      if (!history) return;
      const renderer = pane(map, "history");
      const h = history.cell_deg / 2;
      for (const c of history.cells) {
        const color = HISTORY_RAMP[historyBucket(c.count, history.max_count)];
        L.rectangle(
          [
            [c.lat - h, c.lon - h],
            [c.lat + h, c.lon + h],
          ],
          { renderer, interactive: false, stroke: false, fillColor: color, fillOpacity: 0.55 },
        ).addTo(g);
      }
    },
    [history, map],
  );

  const drawDots = (g: L.LayerGroup, list: Detection[], color: string, radius: number) => {
    const renderer = pane(map, "detections");
    // Oldest first, so the newest draw on top.
    for (let i = list.length - 1; i >= 0; i--) {
      const d = list[i];
      L.circleMarker([d.lat, d.lon], {
        renderer,
        interactive: false,
        radius,
        color: "#1b1b1b",
        weight: 1,
        fillColor: color,
        fillOpacity: 0.9,
      }).addTo(g);
    }
  };
  useFill(weekG, (g) => drawDots(g, week, DETECTION_COLOR.week, 3), [detections, map]);
  useFill(dayG, (g) => drawDots(g, day, DETECTION_COLOR.day, 4.5), [detections, map]);

  useMapEvents({
    click: (e) => {
      if (suppressClick) return;
      const p = map.latLngToContainerPoint(e.latlng);
      let best: Detection | null = null;
      let bestPx = PICK_PX;
      const visible = [
        ...(dayG && map.hasLayer(dayG) ? day : []),
        ...(weekG && map.hasLayer(weekG) ? week : []),
      ];
      for (const d of visible) {
        const dist = p.distanceTo(map.latLngToContainerPoint([d.lat, d.lon]));
        if (dist <= bestPx) {
          best = d;
          bestPx = dist;
        }
      }
      if (best) {
        L.popup().setLatLng([best.lat, best.lon]).setContent(detectionPopup(best, !!detections?.stub)).openOn(map);
        return;
      }
      if (history && histG && map.hasLayer(histG)) {
        const h = history.cell_deg / 2;
        const { lat, lng } = e.latlng;
        const c = history.cells.find((x) => Math.abs(x.lat - lat) <= h && Math.abs(x.lon - lng) <= h);
        if (c) {
          const lines: [string, string][] = [["Detections", String(c.count)]];
          if (c.years != null) lines.push(["Years with fire", String(c.years)]);
          if (c.last_year != null) lines.push(["Last fire", String(c.last_year)]);
          L.popup()
            .setLatLng([c.lat, c.lon])
            .setContent(popupNode(lines, history.stub ? "Fire history (STUB DATA)" : "Fire history"))
            .openOn(map);
        }
      }
    },
  });

  // Overlay names are fixed: react-leaflet reads `name` once, so counts and years live in FireLegend.
  return (
    <>
      <LayersControl.Overlay checked name="Fire history">
        <LayerGroup ref={setHistG} />
      </LayersControl.Overlay>
      <LayersControl.Overlay checked name="Detections, 1–7 days ago">
        <LayerGroup ref={setWeekG} />
      </LayersControl.Overlay>
      <LayersControl.Overlay checked name="Detections, last 24 h">
        <LayerGroup ref={setDayG} />
      </LayersControl.Overlay>
    </>
  );
}

/** Legend in words beside the map, and a loud notice while the data is a stub. */
export function FireLegend({
  detections,
  history,
  error,
}: {
  detections: DetectionsResponse | undefined;
  history: HistoryResponse | undefined;
  error: string;
}) {
  const { day, week } = splitByAge(detections);
  const stub = detections?.stub || history?.stub;
  return (
    <section className="fire-legend" aria-labelledby="fire-legend-title">
      <h3 id="fire-legend-title">Fire map</h3>
      {error && <p className="small error">{error}</p>}
      {stub && (
        <p className="risk-stub" role="note">
          STUB DATA: {detections?.stub ? "detections" : ""}
          {detections?.stub && history?.stub ? " and " : ""}
          {history?.stub ? "fire history" : ""} are fake until the data files exist.
        </p>
      )}
      <ul className="fire-legend-list">
        <li>
          <span className="fl-dot" style={{ background: DETECTION_COLOR.day }} aria-hidden="true" />
          Detected in the last 24 h ({day.length})
        </li>
        <li>
          <span className="fl-dot small-dot" style={{ background: DETECTION_COLOR.week }} aria-hidden="true" />
          Detected 1–7 days ago ({week.length})
        </li>
        <li>
          <span className="fl-ramp" aria-hidden="true">
            {HISTORY_RAMP.map((c) => (
              <span key={c} style={{ background: c }} />
            ))}
          </span>
          Past fires{history?.first_year ? ` ${history.first_year}–${history.last_year}` : ""}: light = few, dark = many
        </li>
      </ul>
      <p className="small">Click a dot for its time, satellite and fire power (FRP). Toggle layers top right of the map.</p>
    </section>
  );
}
