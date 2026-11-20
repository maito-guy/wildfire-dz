// Villages at risk (DESIGN.md §8): most urgent first, the minutes left are the biggest number.
// Select rows, pick a level, Send alert. The operator's click is the approval (PROGRESS D-10).
import { Siren, XCircle } from "@phosphor-icons/react";
import { useState } from "react";
import type { Alert, Village } from "../api/client";
import { fmtClock, lastChangeAt, statusWord } from "../format";
import { StatusBadge } from "./status-badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

type Filter = "all" | Village["status"];
export type SendLevel = Extract<Alert["level"], "leave_now" | "get_ready" | "update">;
const LEVELS: SendLevel[] = ["leave_now", "get_ready", "update"];

const STRIP: Record<Village["status"], string> = {
  leave_now: "bg-fire",
  get_ready: "bg-flame",
  safe: "bg-safe-line",
};
const NUMBER: Record<Village["status"], string> = {
  leave_now: "text-fire",
  get_ready: "text-flame",
  safe: "text-safe",
};

interface Props {
  villages: Village[]; // most urgent first
  alerts: Alert[]; // this fire's alerts, to show "alert sent 14:41"
  busy: boolean;
  onSend: (villages: Village[], level: SendLevel) => Promise<boolean>;
  onCancel: (alertIds: string[]) => Promise<boolean>;
  onFocus: (v: Village) => void;
}

function metaLine(v: Village, sent: Alert | undefined): string {
  const parts = [`${v.distance_km.toFixed(1)} km`];
  if (v.status === "safe") parts.push(v.minutes_left == null ? "no zone in reach" : `${v.minutes_left} min`);
  else parts.push(`leave → ${v.leave_toward}`);
  if (sent) parts.push(`${statusWord(sent.level).toLowerCase()} sent ${fmtClock(lastChangeAt(sent))}`);
  return parts.join(" · ");
}

export function VillageList({ villages, alerts, busy, onSend, onCancel, onFocus }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [level, setLevel] = useState<SendLevel>("leave_now");

  const count = (s: Village["status"]) => villages.filter((v) => v.status === s).length;
  const shown = filter === "all" ? villages : villages.filter((v) => v.status === filter);
  const chosen = villages.filter((v) => selected.has(v.id));
  const sentById = new Map(alerts.filter((a) => a.status === "sent").map((a) => [a.id, a]));
  const cancellable = chosen.map((v) => v.last_alert_id).filter((id): id is string => !!id && sentById.has(id));

  const toggle = (id: string, on: boolean) =>
    setSelected((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });

  async function send() {
    if (await onSend(chosen, level)) setSelected(new Set());
  }
  async function cancel() {
    if (await onCancel(cancellable)) setSelected(new Set());
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-labelledby="villages-title">
      <div className="px-4 pb-3 pt-4">
        <h2 id="villages-title" className="font-display text-[21px] font-bold tracking-[-0.01em]">
          Villages at risk
        </h2>
        <p className="font-mono text-xs text-muted-foreground">
          {villages.length} in reach · sorted by minutes left
        </p>
        <ToggleGroup
          type="single"
          value={filter}
          onValueChange={(v) => v && setFilter(v as Filter)}
          className="mt-3 flex-nowrap gap-1"
          aria-label="Filter villages by status"
        >
          {(
            [
              ["all", "All", villages.length],
              ["leave_now", "Leave now", count("leave_now")],
              ["get_ready", "Get ready", count("get_ready")],
              ["safe", "Safe", count("safe")],
            ] as const
          ).map(([v, label, n]) => (
            <ToggleGroupItem
              key={v}
              value={v}
              className="h-7 shrink-0 rounded-full! border bg-card px-2.5 text-[13px] font-semibold data-[state=on]:border-ink data-[state=on]:bg-ink data-[state=on]:text-white"
            >
              {label}
              <span className="rounded-full bg-secondary px-1.5 font-mono text-[11px] text-ink tabular-nums">{n}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <ol className="min-h-0 flex-1 overflow-y-auto border-t" aria-label="Villages, most urgent first">
        {villages.length === 0 && (
          <li className="px-4 py-6 text-sm text-muted-foreground">No fire yet: pick a replay or start a demo fire.</li>
        )}
        {shown.map((v) => {
          const sent = v.last_alert_id ? sentById.get(v.last_alert_id) : undefined;
          return (
            <li key={v.id} className="border-b">
              <div
                className={cn(
                  "flex min-h-16 items-center gap-3 px-4 py-2.5 transition-colors hover:bg-secondary/50",
                  selected.has(v.id) && "bg-secondary/70",
                )}
              >
                <Checkbox
                  checked={selected.has(v.id)}
                  onCheckedChange={(c) => toggle(v.id, c === true)}
                  aria-label={`Select ${v.name}`}
                  className="size-5"
                />
                <span className={cn("w-[3px] self-stretch rounded-full", STRIP[v.status])} aria-hidden="true" />
                <button type="button" onClick={() => onFocus(v)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                  <span className="w-14 shrink-0 text-center">
                    <span
                      className={cn(
                        "block font-display text-[26px] font-extrabold leading-none tracking-[-0.04em] tabular-nums",
                        NUMBER[v.status],
                      )}
                    >
                      {v.status === "safe" || v.minutes_left == null ? "—" : v.minutes_left}
                    </span>
                    <span className="label-mono mt-1 block whitespace-nowrap text-[9px] tracking-[0.04em]">min left</span>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-semibold">{v.name}</span>
                    <span className="block truncate font-mono text-[11.5px] text-muted-foreground tabular-nums">
                      {metaLine(v, sent)}
                    </span>
                  </span>
                </button>
                <StatusBadge status={v.status} />
              </div>
            </li>
          );
        })}
      </ol>

      <div className="flex flex-wrap items-center gap-2 border-t bg-card px-4 py-3">
        <div className="mr-auto">
          <p className="text-sm font-semibold tabular-nums">{chosen.length} selected</p>
          <Select value={level} onValueChange={(v) => setLevel(v as SendLevel)}>
            <SelectTrigger size="sm" className="mt-0.5 h-6 border-0 px-0 font-mono text-xs text-muted-foreground shadow-none" aria-label="Alert level">
              Level: <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LEVELS.map((l) => (
                <SelectItem key={l} value={l}>
                  {statusWord(l).toLowerCase()}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" onClick={cancel} disabled={busy || cancellable.length === 0} title="Cancel the sent alert of each selected village">
          <XCircle weight="bold" />
          Cancel
        </Button>
        <Button variant="alert" onClick={send} disabled={busy || chosen.length === 0}>
          <Siren weight="bold" />
          Send alert
        </Button>
      </div>
    </section>
  );
}
