import type { Alert } from "../api/client";
import { statusWord } from "../format";

export function AlertLog({ alerts }: { alerts: Alert[] }) {
  return (
    <>
      <h3>Alerts sent</h3>
      {alerts.length === 0 && <p className="small">None yet.</p>}
      <ol className="list">
        {[...alerts].reverse().map((a) => (
          <li key={a.id} className={a.status === "cancelled" ? "cancelled" : undefined}>
            <span className={`badge ${a.level}`}>{statusWord(a.level)}</span>
            <span className="name">{a.village_name}</span>
            <span className="small">
              {a.source} · {new Date(a.created_at).toLocaleTimeString()}
              {a.status === "cancelled" ? " · cancelled" : ""}
            </span>
          </li>
        ))}
      </ol>
    </>
  );
}
