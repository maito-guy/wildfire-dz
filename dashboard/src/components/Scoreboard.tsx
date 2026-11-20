// Scoreboard (#21): models x held-out fires from GET /scoreboard, plus the
// "warned X before vs old method" counter for the replay fire. Every number
// comes from the JSON; null or missing shows "not measured". Plain styling
// until the design mockups (#8, PROGRESS D-11).
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import type { Metric, ModelScore, ReplayCounter, Scoreboard as Board } from "../api/scoreboard";
import { fetchScoreboard } from "../api/scoreboard";
import "./Scoreboard.css";

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
  return typeof v === "number" && Number.isFinite(v) ? fmt(v) : <span className="sb-nm">{NOT_MEASURED}</span>;
}

const measured = (v: Metric | undefined): v is number => typeof v === "number" && Number.isFinite(v);

function counterText(c: ReplayCounter | null | undefined): string | null {
  if (!c || !c.village || !measured(c.lead_min) || !measured(c.old_method_lead_min)) return null;
  const by = c.model ? ` (model ${c.model})` : "";
  return `${c.village} warned ${fmtLead(c.lead_min)} before the fire arrived${by}; ${c.old_method || "old method"}: ${fmtLead(c.old_method_lead_min)}`;
}

function Counter({ board }: { board: Board }) {
  const text = counterText(board.replay_counter);
  return (
    <p className="sb-counter" aria-live="polite">
      {text ?? (
        <>
          Warned before vs old method: <span className="sb-nm">{NOT_MEASURED}</span>
        </>
      )}
    </p>
  );
}

function Tables({ board }: { board: Board }) {
  const fires = board.fires ?? [];
  return (
    <>
      {board.horizon && <p className="small">Horizon: {board.horizon}</p>}
      {fires.length === 0 && <p className="sb-nm">No held-out fire {NOT_MEASURED} yet.</p>}
      {fires.map((f) => {
        const models = Object.entries(f.models ?? {});
        return (
          <section key={f.holdout} className="sb-holdout">
            <h4>
              {f.name ?? f.holdout}{" "}
              <span className="small">
                {measured(f.n_fires) ? `${f.n_fires} fire${f.n_fires === 1 ? "" : "s"}` : `fires: ${NOT_MEASURED}`}
              </span>
            </h4>
            {f.status && <p className="small">{f.status}</p>}
            {models.length === 0 ? (
              <p className="sb-nm">{NOT_MEASURED}</p>
            ) : (
              <div className="sb-scroll">
                <table className="sb-table">
                  <thead>
                    <tr>
                      <th scope="col">Model</th>
                      {COLUMNS.map((c) => (
                        <th key={c.key} scope="col" title={c.title}>
                          {c.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {models.map(([k, m]) => (
                      <tr key={k}>
                        <th scope="row">{modelName(k)}</th>
                        {COLUMNS.map((c) => (
                          <td key={c.key}>{cell(m[c.key], c.fmt)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        );
      })}
      {board.ship_c && (
        <p className="small">
          Ship C? {board.ship_c.decision ?? NOT_MEASURED}
          {board.ship_c.rule ? ` (${board.ship_c.rule})` : ""}
        </p>
      )}
      {board.generated_at && <p className="small">Generated {new Date(board.generated_at).toUTCString()}</p>}
    </>
  );
}

export function Scoreboard() {
  const q = useQuery({ queryKey: ["scoreboard"], queryFn: fetchScoreboard, staleTime: 60_000 });
  const dialog = useRef<HTMLDialogElement>(null);
  const board = q.data;

  return (
    <section className="sb">
      <h3>Scoreboard</h3>
      {q.isPending && <p className="small">Loading…</p>}
      {q.isError && <p className="error">Scoreboard unavailable: {q.error.message}</p>}
      {board && (
        <>
          {board.stub && <p className="sb-stub">STUB: no evaluation has run yet (model/artifacts/scoreboard.json missing).</p>}
          <Counter board={board} />
          {board.weather_note && <p className="sb-weather">{board.weather_note}</p>}
          <button type="button" onClick={() => dialog.current?.showModal()}>
            Open scoreboard table
          </button>
          <dialog ref={dialog} className="sb-dialog" aria-labelledby="sb-title" onClick={(e) => e.target === dialog.current && dialog.current.close()}>
            <div className="sb-dialog-head">
              <h3 id="sb-title">Scoreboard: models on held-out fires</h3>
              <button type="button" className="ghost" onClick={() => dialog.current?.close()}>
                Close
              </button>
            </div>
            {board.stub && <p className="sb-stub">STUB: no evaluation has run yet. Every metric is {NOT_MEASURED}.</p>}
            <Counter board={board} />
            {board.weather_note && <p className="sb-weather">{board.weather_note}</p>}
            <Tables board={board} />
          </dialog>
        </>
      )}
    </section>
  );
}
