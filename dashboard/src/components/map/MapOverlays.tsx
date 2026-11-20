// Layers button over the map: closed by default, opens a short list of grouped toggles.
// Each group drives several map layers, so the operator sees five choices, not nine.
import { StackSimple, X } from "@phosphor-icons/react";
import { useState } from "react";
import { DETECTION_COLOR, HISTORY_RAMP } from "../../api/fireMap";
import { RISK_COLOR } from "../../api/risk";
import { mapColors } from "../../map/colors";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { LayerKey, LayerVisibility } from "./FireMap";

const GROUPS: { label: string; keys: LayerKey[]; color: string }[] = [
  { label: "Fire spread", keys: ["burning", "zone1h", "zone2h", "nextPass"], color: mapColors.burning },
  { label: "Villages", keys: ["villages", "alertAreas"], color: mapColors.ink },
  { label: "Satellite detections", keys: ["detections"], color: DETECTION_COLOR.day },
  { label: "Past fires", keys: ["history"], color: HISTORY_RAMP[HISTORY_RAMP.length - 1] },
  { label: "Risk today", keys: ["risk"], color: RISK_COLOR.very_high },
];

interface LayersProps {
  layers: LayerVisibility;
  onChange: (k: LayerKey, v: boolean) => void;
}

export function LayersCard({ layers, onChange }: LayersProps) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <Button variant="outline" size="sm" className="absolute left-4 top-4 z-10 bg-card shadow-1" onClick={() => setOpen(true)}>
        <StackSimple weight="bold" />
        Layers
      </Button>
    );
  }
  return (
    <section className="absolute left-4 top-4 z-10 w-56 rounded-xl border bg-card p-3 shadow-1" aria-label="Layers">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[13px] font-semibold">Layers</span>
        <Button variant="ghost" size="icon-sm" onClick={() => setOpen(false)} aria-label="Close layers">
          <X />
        </Button>
      </div>
      {GROUPS.map((g) => {
        const on = layers[g.keys[0]];
        const id = `layer-${g.keys[0]}`;
        return (
          <label key={g.label} htmlFor={id} className="flex min-h-8 cursor-pointer items-center gap-2.5 text-[13px]">
            <span className="size-2.5 shrink-0 rounded-full" style={{ background: g.color }} aria-hidden="true" />
            <span className="flex-1">{g.label}</span>
            <Switch id={id} checked={on} onCheckedChange={(v) => g.keys.forEach((k) => onChange(k, v))} />
          </label>
        );
      })}
    </section>
  );
}
