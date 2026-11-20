// Fire context strip under the header (DESIGN.md §8): one line on sand. Replay: pick a fire and step
// through its passes. Live: what the map shows. Demo: the demo fire and its wind. Reset on the right.
import { ArrowCounterClockwise, CaretLeft, CaretRight, Pause, Play } from "@phosphor-icons/react";
import type { ReplayFire } from "../api/client";
import type { Mode } from "./Header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

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

function Tag({ tone, children }: { tone: "ink" | "fire"; children: string }) {
  return (
    <span
      className={cn(
        "status-word shrink-0 rounded-md px-2 py-1 text-white",
        tone === "fire" ? "bg-fire" : "bg-ink",
      )}
    >
      {children}
    </span>
  );
}

export function Controls(p: Props) {
  return (
    <div className="flex min-h-12 shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b bg-sand px-4 py-2 text-[13px]">
      {p.mode === "replay" && (
        <>
          <Tag tone="ink">Replay</Tag>
          <Select value={p.fireId} onValueChange={p.onSelectFire}>
            <SelectTrigger size="sm" className="h-8 w-auto min-w-44 bg-card font-semibold" aria-label="Replay fire">
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
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon-sm" onClick={p.onPrev} disabled={!p.canPrev} aria-label="Previous pass">
              <CaretLeft weight="bold" />
            </Button>
            <Button variant="outline" size="icon-sm" onClick={p.onNext} disabled={!p.canNext} aria-label="Next pass">
              <CaretRight weight="bold" />
            </Button>
            <Button variant="default" size="sm" onClick={p.onTogglePlay} disabled={!p.canNext && !p.playing}>
              {p.playing ? <Pause weight="fill" /> : <Play weight="fill" />}
              {p.playing ? "Pause" : "Play"}
            </Button>
          </div>
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground tabular-nums">
            {p.passInfo || "—"}
          </span>
          {p.stub && <span className="status-word rounded-md border border-dashed border-flame px-2 py-1 text-flame-text">Sample data</span>}
        </>
      )}

      {p.mode === "live" && (
        <>
          <Tag tone="ink">Live</Tag>
          <span className="min-w-0 flex-1 truncate text-muted-foreground">
            Satellite detections of the last 7 days, fire history and today’s risk. Pick a replay or start a demo fire
            to see minutes left per village.
          </span>
        </>
      )}

      {p.mode === "demo" && (
        <>
          <Tag tone="fire">Demo fire</Tag>
          <span className="min-w-0 flex-1 truncate text-muted-foreground">
            {p.demoInfo || "Click anywhere on the map to start a fire there."}
          </span>
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
        </>
      )}

      {p.info && (
        <span className="basis-full text-[13px] font-semibold text-fire-text" role="alert">
          {p.info}
        </span>
      )}
      <Button variant="outline" size="sm" onClick={p.onReset} className="ml-auto bg-card">
        <ArrowCounterClockwise weight="bold" />
        Reset demo
      </Button>
    </div>
  );
}
