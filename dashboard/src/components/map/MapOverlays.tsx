// Floating map controls: map view switch (Heatmap / 3D / Normal) and the Layers button, which opens a short
// list of grouped toggles. Each group drives several map layers, so the operator sees five choices, not nine.
// This card is the only place a layer is switched on or off; the dots double as the legend.
import { Cube, Fire, MapTrifold, StackSimple, X } from "@phosphor-icons/react";
import { useState } from "react";
import { DETECTION_COLOR, HISTORY_RAMP } from "../../api/fireMap";
import { RISK_COLOR } from "../../api/risk";
import { mapColors } from "../../map/colors";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { floating } from "@/lib/utils";
import type { Basemap, LayerKey, LayerVisibility } from "./FireMap";

const GROUPS: { label: string; keys: LayerKey[]; color: string }[] = [
  { label: "Fire spread", keys: ["burning", "zone1h", "zone2h", "nextPass"], color: mapColors.burning },
  { label: "Villages", keys: ["villages", "alertAreas"], color: "var(--ink)" },
  { label: "Satellite detections", keys: ["detections"], color: DETECTION_COLOR.day },
  { label: "Past fires", keys: ["history"], color: HISTORY_RAMP[HISTORY_RAMP.length - 1] },
  { label: "Risk today", keys: ["risk"], color: RISK_COLOR.very_high },
];

const BASEMAPS = [
  { value: "heat", label: "Heatmap", Icon: Fire },
  { value: "3d", label: "3D", Icon: Cube },
  { value: "normal", label: "Normal", Icon: MapTrifold },
] as const;

interface Props {
  basemap: Basemap;
  onBasemap: (b: Basemap) => void;
  layers: LayerVisibility;
  onLayer: (k: LayerKey, v: boolean) => void;
}

export function MapControls({ basemap, onBasemap, layers, onLayer }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col items-end gap-2">
      <div className={floating("flex items-center gap-1 rounded-full p-1")}>
        <ToggleGroup type="single" value={basemap} onValueChange={(v) => v && onBasemap(v as Basemap)} aria-label="Map view">
          {BASEMAPS.map(({ value, label, Icon }) => (
            <ToggleGroupItem
              key={value}
              value={value}
              className="h-7 rounded-full! px-2.5 text-xs font-semibold text-muted-foreground transition-colors duration-200 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
            >
              <Icon weight="bold" aria-hidden="true" />
              {label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <span className="mx-0.5 h-5 w-px bg-border" aria-hidden="true" />
        <Button
          variant={open ? "default" : "ghost"}
          size="icon-sm"
          className="rounded-full"
          onClick={() => setOpen((o) => !o)}
          aria-label="Layers"
          aria-expanded={open}
          title="Layers"
        >
          {open ? <X weight="bold" /> : <StackSimple weight="bold" />}
        </Button>
      </div>
      {open && (
        <section className={floating("animate-in-up w-52 p-2.5")} aria-label="Layers">
          <p className="label-mono mb-1.5">Layers</p>
          {GROUPS.map((g) => {
            const id = `layer-${g.keys[0]}`;
            return (
              <label key={g.label} htmlFor={id} className="flex min-h-7 cursor-pointer items-center gap-2 text-xs">
                <span className="size-2.5 shrink-0 rounded-full" style={{ background: g.color }} aria-hidden="true" />
                <span className="flex-1">{g.label}</span>
                <Switch id={id} checked={layers[g.keys[0]]} onCheckedChange={(v) => g.keys.forEach((k) => onLayer(k, v))} />
              </label>
            );
          })}
        </section>
      )}
    </div>
  );
}
