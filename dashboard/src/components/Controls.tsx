// Fire context, inside the ModeBar card under the mode switch (the mode itself is shown only there).
// Replay: pick a fire and step through its passes. Live: what the map shows. Demo: wind for the demo fire.
// Reset sits on the last line in every mode.
import { ArrowCounterClockwise, CaretLeft, CaretRight, Pause, Play } from "@phosphor-icons/react";
import type { ReplayFire } from "../api/client";
import type { Mode } from "./Header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface WindInput {
  speedKmh: number;
  fromDeg: number;
}

interface Props {
  mode: Mode;
  fires: ReplayFire[];
  fireId: string;
  onSelectFire: (id: string) => void;
  canPrev: boolean;
  canNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  playing: boolean;
  onTogglePlay: () => void;
  passInfo: string;
  stub: boolean; // replay is synthetic
  demoInfo: string; // the demo fire, once started
  info: string; // last error, in words
  wind: WindInput;
  onWind: (w: WindInput) => void;
  onReset: () => void;
}

const well = "rounded-xl border bg-secondary/60 px-3 py-2.5";

export function Controls(p: Props) {
  return (
    <div className="flex flex-col gap-2 text-[13px]">
      {p.mode === "replay" && (
        <div className={`${well} flex flex-col gap-2`}>
          <div className="flex items-center gap-1.5">
            <Select value={p.fireId} onValueChange={p.onSelectFire}>
              <SelectTrigger size="sm" className="h-8 min-w-0 flex-1 bg-card font-semibold" aria-label="Replay fire">
                <SelectValue placeholder="Pick a fire" />
              </SelectTrigger>
              <SelectContent>
                {p.fires.map((f) => (
                  <SelectItem key={f.fire_id} value={f.fire_id}>
                    {f.name}
                    {f.stub ? " · stub" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="icon-sm" className="bg-card" onClick={p.onPrev} disabled={!p.canPrev} aria-label="Previous pass">
              <CaretLeft weight="bold" />
            </Button>
            <Button variant="outline" size="icon-sm" className="bg-card" onClick={p.onNext} disabled={!p.canNext} aria-label="Next pass">
              <CaretRight weight="bold" />
            </Button>
            <Button variant="default" size="sm" onClick={p.onTogglePlay} disabled={!p.canNext && !p.playing}>
              {p.playing ? <Pause weight="fill" /> : <Play weight="fill" />}
              {p.playing ? "Pause" : "Play"}
            </Button>
          </div>
          <p className="flex items-center gap-2 font-mono text-[11.5px] text-muted-foreground tabular-nums">
            <span className="min-w-0 flex-1 truncate" title={p.passInfo}>
              {p.passInfo || "—"}
            </span>
            {p.stub && (
              <span className="status-word shrink-0 rounded-md border border-dashed border-flame px-1.5 py-0.5 text-flame-text">
                Sample data
              </span>
            )}
          </p>
        </div>
      )}

      {p.mode === "live" && (
        <p className={`${well} text-muted-foreground`}>Satellite detections of the last 7 days, fire history and today’s risk.</p>
      )}

      {p.mode === "demo" && (
        <div className={`${well} flex flex-col gap-2`}>
          <p className="text-muted-foreground">{p.demoInfo || "Click anywhere on the map to start a fire there."}</p>
          <label className="flex items-center gap-1.5 font-medium">
            Wind
            <Input
              type="number"
              min={0}
              max={150}
              value={p.wind.speedKmh}
              onChange={(e) => p.onWind({ ...p.wind, speedKmh: Number(e.target.value) })}
              className="h-8 w-16 bg-card tabular-nums"
            />
            <span className="text-muted-foreground">km/h from</span>
            <Input
              type="number"
              min={0}
              max={359}
              value={p.wind.fromDeg}
              onChange={(e) => p.onWind({ ...p.wind, fromDeg: Number(e.target.value) })}
              className="h-8 w-16 bg-card tabular-nums"
              aria-label="Wind from, degrees"
            />
            <span className="text-muted-foreground">°</span>
          </label>
        </div>
      )}

      <div className="flex items-center gap-2">
        {p.info ? (
          <span className="min-w-0 flex-1 text-[12.5px] font-semibold text-fire-text" role="alert">
            {p.info}
          </span>
        ) : (
          <span className="flex-1" />
        )}
        <Button variant="outline" size="sm" onClick={p.onReset} className="bg-card">
          <ArrowCounterClockwise weight="bold" />
          Reset demo
        </Button>
      </div>
    </div>
  );
}
