import type { Health, PredictResponse } from "../api/client";
import { fmtAge, fmtClock, fmtWind, windSourceWord } from "../format";

export interface HealthState {
  data: Health | undefined; // last known values, kept while the server is unreachable
  unreachable: boolean;
  updatedAt: number; // ms since epoch of the last successful /health, 0 if never
}

const count = (n: number | undefined, one: string, many: string): string =>
  n == null ? `— ${many}` : `${n} ${n === 1 ? one : many}`;

function serverText(h: HealthState): string {
  if (h.unreachable) {
    return h.updatedAt ? `Server unreachable · last seen ${fmtClock(h.updatedAt)}` : "Server unreachable";
  }
  return h.data ? "Server connected" : "Connecting to server…";
}

export function Header({ prediction, health }: { prediction: PredictResponse | null; health: HealthState }) {
  const p = prediction;
  const h = health.data;
  return (
    <>
      <header>
        <strong>Wildfire early warning · northern Algeria</strong>
        <span className="age">{fmtAge(p?.data_age_min)}</span>
      </header>
      <div className="statusbar">
        <span role="status" className={health.unreachable ? "server down" : "server"}>
          {serverText(health)}
        </span>
        <span className={health.unreachable ? "counts greyed" : "counts"}>
          <span>{count(h?.phones_connected, "phone connected", "phones connected")}</span>
          <span>{count(h?.dashboards_connected, "dashboard connected", "dashboards connected")}</span>
          <span>{count(h?.pending_alerts, "pending alert", "pending alerts")}</span>
        </span>
        {p && (
          <>
            <span title={p.fallback_reason ?? undefined}>
              Model {p.model}
              {p.fallback_reason ? ` (fallback: ${p.fallback_reason})` : ""}
              {p.embers_applied ? " · embers rule" : ""}
            </span>
            <span>
              Wind {fmtWind(p.wind)} ({windSourceWord(p.wind_source)})
            </span>
          </>
        )}
      </div>
      {p?.data_stale && (
        <div className="stale" role="alert">
          Newest satellite data is more than 3 h old. Zones may be out of date.
        </div>
      )}
    </>
  );
}
