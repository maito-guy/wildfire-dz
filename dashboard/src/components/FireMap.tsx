import type { LatLngTuple, LeafletMouseEvent } from "leaflet";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import type { LatLon, PredictResponse, Village } from "../api/client";
import { zoneFeatures } from "../api/client";
import { fmtMinutesLeft, STATUS_COLOR, statusWord } from "../format";

const ZONE_COLOR: Record<number, string> = { 60: "#b00020", 120: "#e07000" };
const HOME: LatLngTuple = [36.6, 4.1];

export interface MapView {
  center: LatLngTuple;
  zoom: number;
  seq: number; // bump to re-apply the same view
}

interface Props {
  prediction: PredictResponse | null;
  burning: LatLon[];
  truth: LatLon[];
  villages: Village[];
  view: MapView | null;
  startMode: boolean;
  onMapClick: (p: LatLon) => void;
  /** Extra layers drawn under the fire (e.g. today's risk). */
  children?: ReactNode;
}

function ViewController({ view }: { view: MapView | null }) {
  const map = useMap();
  useEffect(() => {
    if (view) map.setView(view.center, view.zoom);
  }, [map, view]);
  return null;
}

function ClickHandler({ onClick }: { onClick: (p: LatLon) => void }) {
  useMapEvents({ click: (e: LeafletMouseEvent) => onClick({ lat: e.latlng.lat, lon: e.latlng.lng }) });
  return null;
}

export function FireMap({ prediction, burning, truth, villages, view, startMode, onMapClick, children }: Props) {
  const zones = prediction ? zoneFeatures(prediction) : [];
  return (
    <div className={`map${startMode ? " start-mode" : ""}`}>
      {/* preferCanvas: thousands of detections stay fast */}
      <MapContainer center={HOME} zoom={10} preferCanvas style={{ height: "100%", width: "100%" }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={17}
          attribution="© OpenStreetMap contributors · fire data NASA FIRMS"
        />
        <ViewController view={view} />
        <ClickHandler onClick={onMapClick} />
        {children}

        {zones.map((f) => {
          const h = f.properties.horizon_min;
          return (
            <GeoJSON
              // GeoJSON layers do not update in place: a new prediction remounts them.
              key={`${prediction?.fire_id}-${prediction?.time}-${h}`}
              data={f}
              style={{ color: ZONE_COLOR[h] ?? "#e07000", weight: 2, fillOpacity: h === 60 ? 0.35 : 0.2 }}
            >
              <Tooltip>{`${h / 60} h zone`}</Tooltip>
            </GeoJSON>
          );
        })}

        {burning.map((b, i) => (
          <CircleMarker
            key={`b${i}-${b.lat}-${b.lon}`}
            center={[b.lat, b.lon]}
            radius={3}
            pathOptions={{ color: "#000", fillColor: "#ff3d00", fillOpacity: 1, weight: 1 }}
          />
        ))}

        {truth.map((b, i) => (
          <CircleMarker
            key={`t${i}-${b.lat}-${b.lon}`}
            center={[b.lat, b.lon]}
            radius={2}
            pathOptions={{ color: "#000", fillColor: "#000", fillOpacity: 0.8, weight: 0 }}
          />
        ))}

        {villages.map((v) => (
          <CircleMarker
            key={v.id}
            center={[v.lat, v.lon]}
            radius={v.status === "safe" ? 4 : 6}
            pathOptions={{ color: "#fff", weight: 2, fillColor: STATUS_COLOR[v.status], fillOpacity: 1 }}
          >
            {/* Colour is never the only signal: urgent villages carry a permanent word label. */}
            <Tooltip permanent={v.status !== "safe"} direction="right" className="village-label">
              {`${v.name}: ${statusWord(v.status)} · ${fmtMinutesLeft(v.minutes_left)}`}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
