import type { Alert } from "../api/client";
import { alertStatusWord, statusWord } from "../format";

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
              {a.source} · {new Date(a.created_at).toLocaleTimeString()}
              {" · "}
              {alertStatusWord(a.status)}
            </span>
          </li>
        ))}
      </ol>
    </>
  );
}
