// Floating bars over the map. Each fact has one home:
// - ModeBar (top left): logo, mode, and the fire context (Controls) as its children.
// - StatusPill (top right): server link, receivers, satellite data age, scoreboard, settings, theme.
// - Banners (top centre): only when something is wrong (server down, live updates down, data older than 3 h).
import { Broadcast, ChartBar, DeviceMobile, GearSix, Moon, Sun, Warning } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type { Health, PredictResponse } from "../api/client";
import { brand } from "../config/brand";
import { fmtAge, fmtClock } from "../format";
import type { StreamState } from "../hooks/useEventSource";
import type { Theme } from "../lib/theme";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn, floating } from "@/lib/utils";

export type Mode = "replay" | "live" | "demo";

export interface HealthState {
  data: Health | undefined; // last known values, kept while the server is unreachable
  unreachable: boolean;
  updatedAt: number; // ms since epoch of the last successful /health, 0 if never
}

const MODES = [
  ["replay", "Replay"],
  ["live", "Live"],
  ["demo", "Demo"],
] as const;

export function ModeBar({
  mode,
  onMode,
  theme,
  children,
}: {
  mode: Mode;
  onMode: (m: Mode) => void;
  theme: Theme;
  children: ReactNode;
}) {
  const base = import.meta.env.BASE_URL;
  return (
    <div className={floating("glass-strong flex flex-col gap-2.5 p-3")}>
      <div className="flex items-center justify-between gap-3">
        <img
          src={`${base}${theme === "dark" ? brand.logo.dark : brand.logo.light}`}
          alt={brand.name}
          width={1851}
          height={608}
          className="h-7 w-auto"
        />
        <ToggleGroup
          type="single"
          value={mode}
          onValueChange={(v) => v && onMode(v as Mode)}
          aria-label="Mode"
          className="rounded-[10px] bg-secondary p-[3px]"
        >
          {MODES.map(([v, label]) => (
            <ToggleGroupItem
              key={v}
              value={v}
              className={cn(
                "h-8 rounded-[7px]! px-3 text-[13px] font-semibold text-muted-foreground",
                "data-[state=on]:shadow-1 transition-colors duration-200",
                v === "demo"
                  ? "data-[state=on]:bg-fire data-[state=on]:text-fire-foreground"
                  : "data-[state=on]:bg-primary data-[state=on]:text-primary-foreground",
              )}
            >
              {v === "demo" && <Broadcast weight="bold" aria-hidden="true" />}
              {label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      {children}
    </div>
  );
}

interface StatusProps {
  prediction: PredictResponse | null;
  health: HealthState;
  theme: Theme;
  onTheme: () => void;
  onScoreboard: () => void;
  onSettings: () => void;
}

export function StatusPill({ prediction: p, health, theme, onTheme, onScoreboard, onSettings }: StatusProps) {
  const h = health.data;
  const phones = h?.phones_connected;
  const down = health.unreachable;
  return (
    <div className={floating("flex items-center gap-1 rounded-full p-1 pl-3.5 text-[13px] font-semibold")}>
      <span role="status" aria-live="polite" className="flex items-center gap-1">
        <span
          className={cn("size-2 rounded-full", down ? "bg-fire" : h ? "bg-ok" : "bg-safe")}
          title={down ? "Server unreachable" : h ? "Connected" : "Connecting…"}
          aria-hidden="true"
        />
        <span className={cn("flex items-center gap-1 px-1.5 tabular-nums", phones === 0 && "text-fire-text")}>
          <DeviceMobile weight="bold" aria-hidden="true" />
          {phones ?? "—"}{" "}
          <span className={cn("font-normal", phones === 0 ? "text-fire-text" : "text-muted-foreground")}>
            {phones === 1 ? "receiver" : "receivers"}
          </span>
        </span>
        <span
          className={cn(
            "hidden px-1.5 font-normal text-muted-foreground tabular-nums sm:inline",
            p?.data_stale && "font-semibold text-fire-text",
          )}
        >
          {fmtAge(p?.data_age_min)}
        </span>
      </span>
      <span className="mx-0.5 h-5 w-px bg-border" aria-hidden="true" />
      <Button variant="ghost" size="icon-sm" className="rounded-full" onClick={onScoreboard} aria-label="Scoreboard" title="Scoreboard">
        <ChartBar weight="bold" />
      </Button>
      <Button variant="ghost" size="icon-sm" className="rounded-full" onClick={onSettings} aria-label="Settings" title="Settings">
        <GearSix weight="bold" />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        className="rounded-full"
        onClick={onTheme}
        aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        title={theme === "dark" ? "Light mode" : "Dark mode"}
      >
        {theme === "dark" ? <Sun weight="bold" /> : <Moon weight="bold" />}
      </Button>
    </div>
  );
}

interface BannerProps {
  health: HealthState;
  live: StreamState;
  prediction: PredictResponse | null;
}

/** Problems only, in words, never dismissible while they hold (DESIGN1 §8). */
export function Banners({ health, live, prediction: p }: BannerProps) {
  const lines: string[] = [];
  if (health.unreachable) {
    lines.push(
      `Not connected to the server${health.updatedAt ? ` · last seen ${fmtClock(health.updatedAt)}` : ""}. Numbers may be out of date.`,
    );
  } else if (live === "down") {
    lines.push("Live updates disconnected. Reconnecting; new flags are checked every 10 s.");
  }
  if (p?.data_stale) lines.push("Newest satellite pass is more than 3 h old. Zones may be out of date.");
  if (lines.length === 0) return null;
  return (
    <div className="pointer-events-auto flex flex-col gap-1.5" role="alert">
      {lines.map((l) => (
        <p key={l} className="flex items-center gap-2 rounded-xl bg-fire px-3.5 py-2 text-sm font-semibold text-fire-foreground shadow-1">
          <Warning weight="bold" aria-hidden="true" />
          {l}
        </p>
      ))}
    </div>
  );
}
