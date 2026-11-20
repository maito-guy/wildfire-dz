// App header (DESIGN.md §8): brand, mode switch, status chips, scoreboard and settings.
// Data age is always visible; it turns into a fire banner past 3 h (§1.3). Server down is a banner too.
import { Broadcast, ChartBar, Clock, DeviceMobile, GearSix, Warning, Wind } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type { Health, PredictResponse } from "../api/client";
import { brand } from "../config/brand";
import { fmtClock } from "../format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

export type Mode = "replay" | "live" | "demo";

export interface HealthState {
  data: Health | undefined; // last known values, kept while the server is unreachable
  unreachable: boolean;
  updatedAt: number; // ms since epoch of the last successful /health, 0 if never
}

function Chip({ icon, dot, tone, children, title }: { icon?: ReactNode; dot?: "ok" | "fire"; tone?: "fire"; children: ReactNode; title?: string }) {
  return (
    <Badge
      variant="outline"
      title={title}
      className={cn(
        "h-8 gap-1.5 rounded-lg bg-secondary/70 px-2.5 text-[13px] font-semibold tabular-nums text-ink [&>svg]:size-4",
        tone === "fire" && "border-fire/40 bg-fire/10 text-fire-text",
      )}
    >
      {dot && <span className={cn("size-2 rounded-full", dot === "ok" ? "bg-ok" : "bg-fire")} aria-hidden="true" />}
      {icon}
      {children}
    </Badge>
  );
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function ageText(min: number | null | undefined): string {
  if (min == null) return "No pass yet";
  return min < 60 ? `Pass ${min} min ago` : `Pass ${Math.floor(min / 60)} h ${min % 60} min ago`;
}

interface Props {
  mode: Mode;
  onMode: (m: Mode) => void;
  prediction: PredictResponse | null;
  health: HealthState;
  onScoreboard: () => void;
  onSettings: () => void;
}

export function Header({ mode, onMode, prediction: p, health, onScoreboard, onSettings }: Props) {
  const h = health.data;
  const phones = h?.phones_connected;
  return (
    <>
      <header className="flex h-[60px] shrink-0 items-center gap-4 border-b bg-card px-4">
        <div className="flex items-center gap-2.5">
          <img src={`${import.meta.env.BASE_URL}logo.png`} alt="" width={20} height={28} className="h-7 w-auto" />
          <span className="font-display text-[21px] font-extrabold tracking-[-0.03em]">{brand.name}</span>
        </div>
        <div className="h-7 w-px bg-border" aria-hidden="true" />
        <ToggleGroup
          type="single"
          value={mode}
          onValueChange={(v) => v && onMode(v as Mode)}
          aria-label="Mode"
          className="rounded-[10px] border bg-secondary/60 p-0.5"
        >
          {(
            [
              ["replay", "Replay"],
              ["live", "Live"],
              ["demo", "Demo"],
            ] as const
          ).map(([v, label]) => (
            <ToggleGroupItem
              key={v}
              value={v}
              className={cn(
                "h-8 rounded-lg! px-4 text-[13px] font-semibold text-muted-foreground",
                "data-[state=on]:text-white data-[state=on]:shadow-1",
                v === "demo" ? "data-[state=on]:bg-fire" : "data-[state=on]:bg-ink",
              )}
            >
              {v === "demo" && <Broadcast weight="bold" aria-hidden="true" />}
              {label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-2" role="status" aria-live="polite">
          {health.unreachable ? (
            <Chip dot="fire" tone="fire">
              Server unreachable
            </Chip>
          ) : (
            <Chip dot={h ? "ok" : undefined}>{h ? "Connected" : "Connecting…"}</Chip>
          )}
          <Chip icon={<Clock aria-hidden="true" />} tone={p?.data_stale ? "fire" : undefined}>
            {ageText(p?.data_age_min)}
          </Chip>
          {p && (
            <Chip icon={<Wind aria-hidden="true" />}>
              {Math.round(p.wind.speed_kmh)} km/h · {Math.round(p.wind.from_deg)}°
            </Chip>
          )}
          <Chip icon={<DeviceMobile aria-hidden="true" />} tone={phones === 0 ? "fire" : undefined}>
            {phones == null ? "— receivers" : plural(phones, "receiver", "receivers")}
          </Chip>
          <Button variant="ghost" size="sm" onClick={onScoreboard}>
            <ChartBar weight="bold" aria-hidden="true" />
            Scoreboard
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={onSettings} aria-label="Settings">
            <GearSix weight="bold" />
          </Button>
        </div>
      </header>

      {health.unreachable && (
        <div className="flex items-center gap-2 bg-fire px-4 py-2 text-sm font-semibold text-white" role="alert">
          <Warning weight="bold" aria-hidden="true" />
          Not connected to the server{health.updatedAt ? ` · last seen ${fmtClock(health.updatedAt)}` : ""}. Numbers
          below may be out of date.
        </div>
      )}
      {p?.data_stale && (
        <div className="flex items-center gap-2 bg-fire px-4 py-2 text-sm font-semibold text-white" role="alert">
          <Warning weight="bold" aria-hidden="true" />
          Newest satellite pass is more than 3 h old. Zones may be out of date.
        </div>
      )}
    </>
  );
}
