// Today's risk cells on the map (#28). Colour is never the only signal: every cell has a word
// tooltip, very-high-risk places carry a permanent word label, and RiskPanel holds the legend.
import { CircleMarker, Rectangle, Tooltip } from "react-leaflet";
import type { RiskResponse } from "../api/risk";
import { RISK_COLOR, RISK_WORD } from "../api/risk";

export function RiskLayer({ risk }: { risk: RiskResponse }) {
  const h = risk.cell_deg / 2;
  const stub = risk.stub ? " · STUB DATA" : "";
  return (
    <>
      {risk.cells.map((c) => (
        <Rectangle
          key={`r${c.lat}-${c.lon}`}
          bounds={[
            [c.lat - h, c.lon - h],
            [c.lat + h, c.lon + h],
          ]}
          pathOptions={{ stroke: false, fillColor: RISK_COLOR[c.level], fillOpacity: 0.35 }}
        >
          <Tooltip sticky>{`${RISK_WORD[c.level]} fire risk today · score ${c.score.toFixed(2)}${stub}`}</Tooltip>
        </Rectangle>
      ))}
      {risk.places.map((p) => (
        <CircleMarker
          key={`rp-${p.id}`}
          center={[p.lat, p.lon]}
          radius={6}
          pathOptions={{ color: "#fff", weight: 2, fillColor: RISK_COLOR[p.level], fillOpacity: 1 }}
        >
          <Tooltip permanent direction="right" className="village-label">
            {`${p.name}: ${RISK_WORD[p.level]} risk`}
          </Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}
