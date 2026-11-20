// Cards over the map (DESIGN.md §8): Layers top-left, Weather top-right, demo hint bottom-left.
// White at 96 %, level-1 shadow, 16 px from the map edges. Every swatch carries its word and its
// dash pattern, not colour alone.
import { Crosshair, Warning, Wind } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type { DetectionsResponse, HistoryResponse, PredictResponse } from "../../api/client";
import { DETECTION_COLOR, HISTORY_RAMP, splitByAge } from "../../api/fireMap";
import type { RiskResponse } from "../../api/risk";
import { RISK_COLOR, RISK_LEVELS, RISK_WORD } from "../../api/risk";
import { fmtClock, windSourceWord } from "../../format";
import { mapColors } from "../../map/colors";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import type { LayerKey, LayerVisibility } from "./FireMap";

const card = "rounded-xl border bg-card/95 shadow-1 backdrop-blur-sm";

function Swatch({ kind, color }: { kind: "fill" | "zone1" | "zone2" | "dot" | "small-dot" | "dashed" | "dotted" | "ramp" | "pin"; color?: string }) {
  switch (kind) {
    case "fill":
      return <span className="size-3.5 rounded-[3px]" style={{ background: color }} />;
    case "zone1":
      return <span className="size-3.5 rounded-[3px] border-2" style={{ borderColor: mapColors.zone1hLine, background: mapColors.zone1hFill }} />;
    case "zone2":
      return <span className="size-3.5 rounded-[3px] border-2 border-dashed" style={{ borderColor: mapColors.zone2hLine, background: mapColors.zone2hFill }} />;
    case "dot":
      return <span className="size-3 rounded-full border border-ink" style={{ background: color }} />;
    case "small-dot":
      return <span className="m-0.5 size-2 rounded-full border border-ink" style={{ background: color }} />;
    case "pin":
      return <span className="size-3.5 rounded-full ring-2 ring-white" style={{ background: color, boxShadow: "0 0 0 3px rgba(0,0,0,.1)" }} />;
    case "dashed":
      return <span className="size-3.5 rounded-full border-2 border-dashed border-ink" />;
    case "dotted":
      return <span className="size-3.5 rounded-[3px] border-2 border-dotted border-ink/70" />;
    case "ramp":
      return (
        <span className="flex">
          {HISTORY_RAMP.map((c) => (
            <span key={c} className="h-3.5 w-1" style={{ background: c }} />
          ))}
        </span>
      );
  }
}

function Row({
  id,
  checked,
  onChange,
  swatch,
  children,
}: {
  id: LayerKey;
  checked: boolean;
  onChange: (k: LayerKey, v: boolean) => void;
  swatch: ReactNode;
  children: ReactNode;
}) {
  return (
    <label htmlFor={`layer-${id}`} className="flex min-h-7 cursor-pointer items-center gap-2.5 text-[13px] font-medium">
      <span className="flex w-5 shrink-0 justify-center" aria-hidden="true">
        {swatch}
      </span>
      <span className="flex-1">{children}</span>
      <Checkbox id={`layer-${id}`} checked={checked} onCheckedChange={(v) => onChange(id, v === true)} />
    </label>
  );
}

interface LayersProps {
  layers: LayerVisibility;
  onChange: (k: LayerKey, v: boolean) => void;
  burningAt: string | null; // pass time of the burning cells
  replay: boolean; // the next-pass layer only exists in replay
  detections: DetectionsResponse | undefined;
  history: HistoryResponse | undefined;
  risk: RiskResponse | undefined;
}

export function LayersCard(p: LayersProps) {
  const { day, week } = splitByAge(p.detections);
  const stub = [
    p.detections?.stub && "detections",
    p.history?.stub && "fire history",
    p.risk?.stub && "risk today",
  ].filter(Boolean);
  const riskShown = p.risk ? RISK_LEVELS.filter((l) => p.risk!.cells.some((c) => c.level === l)) : [];
  return (
    <section className={cn(card, "absolute left-4 top-4 z-10 w-[248px] p-3.5")} aria-labelledby="layers-title">
      <h2 id="layers-title" className="label-mono mb-2">
        Layers
      </h2>
      <div className="flex flex-col">
        <Row id="burning" checked={p.layers.burning} onChange={p.onChange} swatch={<Swatch kind="fill" color={mapColors.burningCore} />}>
          Burning cells{p.burningAt ? <span className="tabular-nums"> · {p.burningAt}</span> : null}
        </Row>
        <Row id="zone1h" checked={p.layers.zone1h} onChange={p.onChange} swatch={<Swatch kind="zone1" />}>
          1 h zone
        </Row>
        <Row id="zone2h" checked={p.layers.zone2h} onChange={p.onChange} swatch={<Swatch kind="zone2" />}>
          2 h zone
        </Row>
        <Row id="villages" checked={p.layers.villages} onChange={p.onChange} swatch={<Swatch kind="pin" color={mapColors.burning} />}>
          Villages, labelled
        </Row>
        <Row id="alertAreas" checked={p.layers.alertAreas} onChange={p.onChange} swatch={<Swatch kind="dashed" />}>
          Alert areas
        </Row>
        {p.replay && (
          <Row id="nextPass" checked={p.layers.nextPass} onChange={p.onChange} swatch={<Swatch kind="dotted" />}>
            Really burned next pass
          </Row>
        )}
      </div>
      <div className="my-2 h-px bg-border" />
      <div className="flex flex-col">
        <Row id="detections" checked={p.layers.detections} onChange={p.onChange} swatch={<Swatch kind="dot" color={DETECTION_COLOR.day} />}>
          Detected, last 24 h <span className="text-muted-foreground tabular-nums">({day.length})</span>
        </Row>
        {p.layers.detections && (
          <div className="flex min-h-6 items-center gap-2.5 pl-0 text-[12px] text-muted-foreground">
            <span className="flex w-5 justify-center" aria-hidden="true">
              <Swatch kind="small-dot" color={DETECTION_COLOR.week} />
            </span>
            1–7 days ago <span className="tabular-nums">({week.length})</span>
          </div>
        )}
        <Row id="history" checked={p.layers.history} onChange={p.onChange} swatch={<Swatch kind="ramp" />}>
          Past fires
          {p.history?.first_year ? (
            <span className="text-muted-foreground tabular-nums">
              {" "}
              {p.history.first_year}–{p.history.last_year}
            </span>
          ) : null}
        </Row>
        <Row id="risk" checked={p.layers.risk} onChange={p.onChange} swatch={<Swatch kind="fill" color={RISK_COLOR.very_high} />}>
          Risk today
        </Row>
        {p.layers.risk && riskShown.length > 0 && (
          <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 pl-[30px] text-[12px] text-muted-foreground" aria-label="Risk legend">
            {riskShown.map((l) => (
              <li key={l} className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-[2px]" style={{ background: RISK_COLOR[l] }} aria-hidden="true" />
                {RISK_WORD[l]}
              </li>
            ))}
          </ul>
        )}
      </div>
      {stub.length > 0 && (
        <p className="mt-2.5 rounded-md border border-dashed border-flame px-2 py-1.5 text-[11.5px] font-medium text-flame-text" role="note">
          Sample values: {stub.join(", ")} are stub data until the files exist.
        </p>
      )}
    </section>
  );
}

export function WeatherCard({ prediction }: { prediction: PredictResponse | null }) {
  if (!prediction) return null;
  const w = prediction.wind;
  return (
    <section className={cn(card, "absolute right-4 top-4 z-10 w-[236px] p-3.5")} aria-labelledby="weather-title">
      <h2 id="weather-title" className="label-mono mb-1.5">
        Weather · {windSourceWord(prediction.wind_source)}
      </h2>
      <p className="flex items-center gap-2 whitespace-nowrap font-display text-[17px] font-bold tabular-nums">
        <Wind size={20} aria-hidden="true" />
        {Math.round(w.speed_kmh)} km/h from {Math.round(w.from_deg)}°
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Model {prediction.model}
        {prediction.fallback_reason ? ` · fallback: ${prediction.fallback_reason}` : ""} · run {fmtClock(prediction.time)}
      </p>
      {prediction.embers_applied && (
        <p className="status-word mt-2 inline-flex items-center gap-1.5 rounded-md bg-flame/15 px-2 py-1 text-flame-text">
          <Warning size={13} weight="bold" aria-hidden="true" />
          Embers rule on
        </p>
      )}
    </section>
  );
}

export function DemoHint({ demo }: { demo: boolean }) {
  if (!demo) return null;
  return (
    <div className={cn(card, "absolute bottom-4 left-4 z-10 flex items-center gap-3 px-3.5 py-2.5")} role="status">
      <span className="grid size-8 place-items-center rounded-lg bg-fire text-white" aria-hidden="true">
        <Crosshair size={18} weight="bold" />
      </span>
      <span>
        <span className="block text-[13px] font-semibold">Click anywhere to start a fire here</span>
        <span className="font-mono text-[11px] text-muted-foreground">Demo mode · wind from the context bar</span>
      </span>
    </div>
  );
}
