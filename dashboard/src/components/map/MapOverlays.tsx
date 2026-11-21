// Floating map controls: map view switch (Heatmap / 3D / Normal) and the Layers button, which opens a short
// list of grouped toggles. Each group drives several map layers, so the operator sees five choices, not nine.
// This card is the only place a layer is switched on or off; the dots double as the legend.
// The AI estimate (model C, #53) is advice only: its row is disabled when /predict has no `ai` block.
// The risk row also says the day's fire weather (FWI, #57), which caps the risk levels on calm days.
import { Cube, Fire, MapTrifold, StackSimple, X } from "@phosphor-icons/react";
import { useState } from "react";
import { DETECTION_COLOR, HISTORY_RAMP } from "../../api/fireMap";
import { FIRE_WEATHER_WORD, RISK_COLOR, type RiskResponse } from "../../api/risk";
import { mapColors } from "../../map/colors";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn, floating } from "@/lib/utils";
import type { Basemap, LayerKey, LayerVisibility } from "./FireMap";

const GROUPS: { label: string; keys: LayerKey[]; color: string }[] = [
  { label: "Fire spread", keys: ["burning", "zone1h", "zone2h", "nextPass"], color: mapColors.burning },
  { label: "AI estimate, check before acting", keys: ["ai"], color: "var(--ai)" },
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
  /** The current prediction has model C's zones (`PredictResponse.ai` is not null). */
  aiAvailable: boolean;
  /** Today's risk answer, for the fire weather line under "Risk today". */
  risk: RiskResponse | undefined;
}

function fireWeatherLine(risk: RiskResponse | undefined): { text: string; title: string } | null {
  if (!risk) return null;
  const fw = risk.fwi;
  if (!fw) return risk.fwi_note ? { text: "Fire weather: unavailable", title: risk.fwi_note } : null;
  const capped = fw.capped_cells > 0 ? ` ${fw.capped_cells} cells lowered to match the weather.` : "";
  return {
    text: `Fire weather: ${FIRE_WEATHER_WORD[fw.level]} (FWI ${Math.round(fw.value)})`,
    title: `Worst of ${fw.points} weather points on ${fw.date} (median FWI ${fw.median}).${capped}`,
  };
}

export function MapControls({ basemap, onBasemap, layers, onLayer, aiAvailable, risk }: Props) {
  const [open, setOpen] = useState(false);
  const weather = fireWeatherLine(risk);
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
        <section className={floating("animate-in-up w-60 p-2.5")} aria-label="Layers">
          <p className="label-mono mb-1.5">Layers</p>
          {GROUPS.map((g) => {
            const id = `layer-${g.keys[0]}`;
            const isAi = g.keys[0] === "ai";
            const isRisk = g.keys[0] === "risk";
            const off = isAi && !aiAvailable;
            return (
              <label
                key={g.label}
                htmlFor={id}
                className={cn("flex min-h-7 items-center gap-2 py-0.5 text-xs", off ? "cursor-not-allowed" : "cursor-pointer")}
              >
                <span className={cn("size-2.5 shrink-0 rounded-full", off && "opacity-40")} style={{ background: g.color }} aria-hidden="true" />
                <span className="flex-1 leading-tight">
                  <span className={cn("block", off && "text-muted-foreground")}>{g.label}</span>
                  {isAi && (
                    <span className="block font-mono text-[10px] text-muted-foreground">
                      {off ? "no AI estimate for this fire" : "solid likely · dashed possible"}
                    </span>
                  )}
                  {isRisk && weather && (
                    <span className="block font-mono text-[10px] text-muted-foreground" title={weather.title}>
                      {weather.text}
                    </span>
                  )}
                </span>
                <Switch
                  id={id}
                  checked={!off && layers[g.keys[0]]}
                  disabled={off}
                  onCheckedChange={(v) => g.keys.forEach((k) => onLayer(k, v))}
                />
              </label>
            );
          })}
        </section>
      )}
    </div>
  );
}
