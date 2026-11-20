import type { Village } from "../api/client";
import { fmtMinutesLeft, statusWord } from "../format";

interface Props {
  villages: Village[];
  busy: boolean;
  onSend: (v: Village) => void;
  onCancel: (alertId: string) => void;
}

export function VillageList({ villages, busy, onSend, onCancel }: Props) {
  return (
    <>
      <h3>
        Villages <span className="small">(most urgent first)</span>
      </h3>
      {villages.length === 0 && <p className="small">No fire yet: pick a replay or start a fire.</p>}
      <ol className="list">
        {villages.map((v) => (
          <li key={v.id}>
            <span className={`badge ${v.status}`}>{statusWord(v.status)}</span>
            <span className="name">{v.name}</span>
            <span>{fmtMinutesLeft(v.minutes_left)}</span>
            <span className="small">→ {v.leave_toward}</span>
            <button disabled={busy} onClick={() => onSend(v)}>
              Send
            </button>
            {v.last_alert_id && (
              <button disabled={busy} onClick={() => onCancel(v.last_alert_id!)}>
                Cancel
              </button>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}
