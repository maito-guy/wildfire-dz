import type { Alert } from "../api/client";
import { api } from "../api/client";
import { alertStatusWord, fmtClock, hasCap, lastChangeAt, statusWord } from "../format";

export function AlertLog({ alerts }: { alerts: Alert[] }) {
  return (
    <>
      <h3>
        Alerts <span className="small">(newest first)</span>
      </h3>
      {alerts.length === 0 && <p className="small">None yet.</p>}
      <ol className="list">
        {[...alerts].reverse().map((a) => (
          <li key={a.id} className={a.status === "sent" ? undefined : a.status}>
            <span className={`badge ${a.level}`}>{statusWord(a.level)}</span>
            <span className="name">{a.village_name}</span>
            <span className="small">
              {a.source} · {alertStatusWord(a.status)} {fmtClock(lastChangeAt(a))}
            </span>
            {hasCap(a) && (
              <a
                className="cap small"
                href={api.capUrl(a.id)}
                target="_blank"
                rel="noopener noreferrer"
                title={`CAP 1.2 message (${a.status === "sent" ? "Alert" : "Cancel"})`}
              >
                CAP
              </a>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}
