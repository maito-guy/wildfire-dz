// Scoreboard (#21): models x held-out fires from GET /scoreboard, plus the
// "warned X before vs old method" counter for the replay fire. Every number
// comes from the JSON; null or missing shows "not measured" (DESIGN.md §1.6, honest numbers).
import { useQuery } from "@tanstack/react-query";
import type { Metric, ModelScore, ReplayCounter, Scoreboard as Board } from "../api/scoreboard";
import { fetchScoreboard } from "../api/scoreboard";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const NOT_MEASURED = "not measured";

const MODEL_NAMES: Record<string, string> = {
  A: "A · buffer",
  B: "B · physics-lite",
  C_mixed: "C · LightGBM (mixed)",
  C_dza: "C · LightGBM (Algeria only)",
};
const modelName = (k: string) => MODEL_NAMES[k] ?? k;

const pct = (v: number) => `${(v * 100).toFixed(1)} %`;
const num = (v: number) => String(v);
const times = (v: number) => `${v.toFixed(2)} ×`;

function fmtLead(min: number): string {
  const m = Math.round(min);
  if (m < 60) return `${m} min`;
  const rest = m % 60;
  return rest ? `${Math.floor(m / 60)} h ${rest} min` : `${m / 60} h`;
}

const COLUMNS: { key: keyof ModelScore; label: string; title: string; fmt: (v: number) => string }[] = [
  { key: "recall_1h", label: "Recall 1 h", title: "Share of really-burned cells inside the 1 h zone", fmt: pct },
  { key: "false_alarm_cell_share", label: "False-alarm cells", title: "Share of unburned cells flagged", fmt: pct },
  { key: "zone_cells_per_burned_cell", label: "Zone / burned", title: "Zone cells per really-burned cell", fmt: times },
  { key: "missed_villages", label: "Missed villages", title: "Villages reached by fire without a warning", fmt: num },
  { key: "median_lead_min", label: "Median lead", title: "Median warning time before the fire arrived", fmt: fmtLead },
  { key: "false_alarm_villages", label: "False-alarm villages", title: "Villages warned that the fire never reached", fmt: num },
];

function cell(v: ModelScore[keyof ModelScore], fmt: (v: number) => string) {
  return typeof v === "number" && Number.isFinite(v) ? fmt(v) : <span className="text-xs font-normal italic text-muted-foreground">{NOT_MEASURED}</span>;
}

const measured = (v: Metric | undefined): v is number => typeof v === "number" && Number.isFinite(v);

function counterText(c: ReplayCounter | null | undefined): string | null {
  if (!c || !c.village || !measured(c.lead_min) || !measured(c.old_method_lead_min)) return null;
  const by = c.model ? ` (model ${c.model})` : "";
  return `${c.village} warned ${fmtLead(c.lead_min)} before the fire arrived${by}; ${c.old_method || "old method"}: ${fmtLead(c.old_method_lead_min)}`;
}

function Counter({ board }: { board: Board }) {
  const c = board.replay_counter;
  const text = counterText(c);
  if (!text || !c || !measured(c.lead_min) || !measured(c.old_method_lead_min)) {
    return (
      <div className="rounded-2xl border bg-card p-5" aria-live="polite">
        <p className="label-mono">Warned before vs old method</p>
        <p className="mt-2 font-display text-[44px] font-extrabold leading-none tracking-[-0.03em] text-safe">{NOT_MEASURED}</p>
      </div>
    );
  }
  const extra = c.lead_min - c.old_method_lead_min;
  return (
    <div className="grid gap-6 rounded-2xl border bg-card p-5 sm:grid-cols-3" aria-live="polite" aria-label={text}>
      <div>
        <p className="label-mono">
          {c.village} · warned{c.model ? ` · model ${c.model}` : ""}
        </p>
        <p className="mt-2 font-display text-[54px] font-extrabold leading-none tracking-[-0.04em] text-fire tabular-nums">
          {fmtLead(c.lead_min)}
        </p>
      </div>
      <div>
        <p className="label-mono">{c.old_method || "old method"}</p>
        <p className="mt-2 font-display text-[54px] font-extrabold leading-none tracking-[-0.04em] text-safe tabular-nums">
          {fmtLead(c.old_method_lead_min)}
        </p>
      </div>
      <div className="self-center">
        <p className="label-mono">Extra time to leave</p>
        <p className="mt-2 font-display text-[30px] font-extrabold leading-none tracking-[-0.03em] tabular-nums">
          {extra >= 0 ? "+" : "−"}
          {fmtLead(Math.abs(extra))}
        </p>
      </div>
    </div>
  );
}

function Tables({ board }: { board: Board }) {
  const fires = board.fires ?? [];
  return (
    <>
      {board.horizon && <p className="text-sm text-muted-foreground">Horizon: {board.horizon}</p>}
      {fires.length === 0 && <p className="text-sm italic text-muted-foreground">No held-out fire {NOT_MEASURED} yet.</p>}
      {fires.map((f) => {
        const models = Object.entries(f.models ?? {});
        return (
          <section key={f.holdout} className="mt-2">
            <p className="label-mono">
              {f.name ?? f.holdout} ·{" "}
              {measured(f.n_fires) ? `${f.n_fires} fire${f.n_fires === 1 ? "" : "s"}` : `fires: ${NOT_MEASURED}`}
            </p>
            {f.status && <p className="mt-1 text-sm text-muted-foreground">{f.status}</p>}
            {models.length === 0 ? (
              <p className="mt-2 text-sm italic text-muted-foreground">{NOT_MEASURED}</p>
            ) : (
              <div className="mt-2 overflow-x-auto rounded-2xl border bg-card">
                <Table className="min-w-[860px]">
                  <TableHeader>
                    <TableRow className="bg-secondary/40">
                      <TableHead className="label-mono h-11 pl-5 text-ink">Model</TableHead>
                      {COLUMNS.map((c) => (
                        <TableHead key={c.key} title={c.title} className="label-mono h-11 text-right text-ink">
                          {c.label}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {models.map(([k, m]) => (
                      <TableRow key={k}>
                        <TableHead scope="row" className="pl-5 text-[15px] font-semibold text-ink">
                          {modelName(k)}
                        </TableHead>
                        {COLUMNS.map((c) => (
                          <TableCell key={c.key} className="text-right text-[15px] font-semibold tabular-nums">
                            {cell(m[c.key], c.fmt)}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </section>
        );
      })}
      {board.ship_c && (
        <p className="text-sm text-muted-foreground">
          Ship C? <span className="font-semibold text-ink">{board.ship_c.decision ?? NOT_MEASURED}</span>
          {board.ship_c.rule ? ` (${board.ship_c.rule})` : ""}
        </p>
      )}
      {board.generated_at && (
        <p className="font-mono text-xs text-muted-foreground">Generated {new Date(board.generated_at).toUTCString()}</p>
      )}
    </>
  );
}

export function Scoreboard({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const q = useQuery({ queryKey: ["scoreboard"], queryFn: fetchScoreboard, staleTime: 60_000 });
  const board = q.data;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100vh-32px)] overflow-y-auto bg-background sm:max-w-[1040px]">
        <DialogHeader>
          <p className="label-mono">Scoreboard · held-out fires only</p>
          <DialogTitle className="font-display text-[44px] font-extrabold leading-[1.05] tracking-[-0.03em]">
            Did every village get its warning in time?
          </DialogTitle>
          <DialogDescription className="text-base">
            Every number is read from scoreboard.json, written by the evaluation script. Only whole fire episodes
            the model never trained on count.
          </DialogDescription>
        </DialogHeader>
        {q.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
        {q.isError && <p className="text-sm font-semibold text-fire-text">Scoreboard unavailable: {q.error.message}</p>}
        {board && (
          <div className="flex flex-col gap-5">
            {board.stub && (
              <p className="w-fit rounded-full border border-dashed border-flame px-3 py-1 text-xs font-semibold text-flame-text">
                No evaluation has run yet (model/artifacts/scoreboard.json missing): every metric is {NOT_MEASURED}.
              </p>
            )}
            <Counter board={board} />
            {board.weather_note && <p className="text-sm text-muted-foreground">{board.weather_note}</p>}
            <Tables board={board} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
