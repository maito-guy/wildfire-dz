// "Risk today" toggle, legend in words, and the very-high-risk places with their top factors (#28).
// Each place is a preventive flag in the approval queue; this list only shows where it stands.
import type { RiskPlace, RiskResponse } from "../api/risk";
import { RISK_COLOR, RISK_LEVELS, RISK_WORD } from "../api/risk";
import { alertStatusWord } from "../format";

interface Props {
  risk: RiskResponse | undefined;
  error: string;
  show: boolean;
  onShow: (show: boolean) => void;
  /** Show this place on the map. */
  onSelect: (p: RiskPlace) => void;
}

export function RiskPanel({ risk, error, show, onShow, onSelect }: Props) {
  const shown = risk ? RISK_LEVELS.filter((l) => risk.cells.some((c) => c.level === l)) : [];
  return (
    <section className="risk" aria-labelledby="risk-title">
      <h3 id="risk-title">
        <label>
          <input type="checkbox" checked={show} onChange={(e) => onShow(e.target.checked)} /> Risk today
        </label>{" "}
        {risk && <span className="small">({risk.date})</span>}
      </h3>
      {error && <p className="small error">Could not load the risk map: {error}</p>}
      {risk?.stub && (
        <p className="risk-stub" role="note">
          STUB DATA: the risk model has not published today's file yet. These cells are fake.
        </p>
      )}
      {show && risk && (
        <ul className="risk-legend" aria-label="Risk legend">
          {shown.map((l) => (
            <li key={l}>
              <span className="risk-swatch" style={{ background: RISK_COLOR[l] }} aria-hidden="true" />
              {RISK_WORD[l]} risk
            </li>
          ))}
          {shown.length === 0 && <li className="small">No cell at moderate risk or above today.</li>}
        </ul>
      )}
      {risk && (
        <>
          <p className="small">
            {RISK_WORD[risk.flag_level]}-risk places ({risk.places.length}) · each one is a preventive flag in the
            approval queue
          </p>
          <ol className="list">
            {risk.places.map((p) => (
              <li key={p.id}>
                <span className="badge" style={{ background: RISK_COLOR[p.level] }}>
                  {RISK_WORD[p.level]}
                </span>
                <button type="button" className="ghost name risk-place" onClick={() => onSelect(p)}>
                  {p.name}
                  <span className="small"> · {p.top_factors.join(", ") || "no factors given"}</span>
                </button>
                <span className="small">{alertStatusWord(p.alert_status)}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
