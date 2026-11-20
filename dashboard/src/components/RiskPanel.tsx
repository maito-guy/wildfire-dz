// Risk today (#28): the very-high-risk places and their top factors. Each place is a preventive flag in
// the approval queue; this list only shows where it stands. The map layer toggle lives in the Layers card.
import { MapPin } from "@phosphor-icons/react";
import type { RiskPlace, RiskResponse } from "../api/risk";
import { RISK_COLOR, RISK_WORD } from "../api/risk";
import { alertStatusWord } from "../format";
import { Switch } from "@/components/ui/switch";

interface Props {
  risk: RiskResponse | undefined;
  error: string;
  show: boolean;
  onShow: (show: boolean) => void;
  /** Show this place on the map. */
  onSelect: (p: RiskPlace) => void;
}

export function RiskPanel({ risk, error, show, onShow, onSelect }: Props) {
  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-labelledby="risk-title">
      <div className="px-4 pb-3 pt-4">
        <div className="flex items-center justify-between gap-3">
          <h2 id="risk-title" className="font-display text-[21px] font-bold tracking-[-0.01em]">
            Risk today
          </h2>
          <label className="flex items-center gap-2 text-[13px] font-semibold">
            On the map
            <Switch checked={show} onCheckedChange={onShow} />
          </label>
        </div>
        <p className="font-mono text-xs text-muted-foreground tabular-nums">
          {risk ? `${risk.date} · ${risk.places.length} ${RISK_WORD[risk.flag_level].toLowerCase()}-risk places` : "Loading…"}
        </p>
        {error && <p className="mt-2 text-sm font-semibold text-fire-text">Could not load the risk map: {error}</p>}
        {risk?.stub && (
          <p className="mt-3 rounded-md border border-dashed border-flame px-2.5 py-1.5 text-xs font-medium text-flame-text" role="note">
            Sample values: the risk model has not published today’s file yet. These cells and places are fake.
          </p>
        )}
      </div>
      <ol className="min-h-0 flex-1 overflow-y-auto border-t">
        {risk && risk.places.length === 0 && (
          <li className="px-4 py-6 text-sm text-muted-foreground">No place at {RISK_WORD[risk.flag_level].toLowerCase()} risk today.</li>
        )}
        {risk?.places.map((p) => (
          <li key={p.id} className="border-b">
            <button
              type="button"
              onClick={() => onSelect(p)}
              className="flex min-h-16 w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-secondary/50"
            >
              <span className="w-[3px] self-stretch rounded-full" style={{ background: RISK_COLOR[p.level] }} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-semibold">{p.name}</span>
                <span className="block truncate font-mono text-[11.5px] text-muted-foreground">
                  {p.top_factors.join(" · ") || "no factors given"} · {p.distance_km.toFixed(1)} km
                </span>
              </span>
              <span className="shrink-0 text-right">
                <span className="status-word block text-fire-text">{RISK_WORD[p.level]} risk</span>
                <span className="font-mono text-[11px] text-muted-foreground">flag {alertStatusWord(p.alert_status)}</span>
              </span>
              <MapPin className="shrink-0 text-muted-foreground" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ol>
      <p className="border-t bg-card px-4 py-3 text-xs text-muted-foreground">
        Each place is a preventive flag in the approval queue. Nothing is sent without a click.
      </p>
    </section>
  );
}
