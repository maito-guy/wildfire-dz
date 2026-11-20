import type { PredictResponse } from "../api/client";
import { fmtAge } from "../format";

export function Header({ prediction }: { prediction: PredictResponse | null }) {
  const p = prediction;
  return (
    <>
      <header>
        <strong>Wildfire early warning · northern Algeria</strong>
        <span className="age">{fmtAge(p?.data_age_min)}</span>
        {p && (
          <span className="pill" title={p.fallback_reason ?? undefined}>
            model {p.model}
            {p.fallback_reason ? ` (fallback: ${p.fallback_reason})` : ""}
            {p.embers_applied ? " · embers rule" : ""} · wind {p.wind_source}
          </span>
        )}
      </header>
      {p?.data_stale && (
        <div className="stale" role="alert">
          Newest satellite data is more than 3 h old. Zones may be out of date.
        </div>
      )}
    </>
  );
}
