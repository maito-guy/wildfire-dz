import { useRef, useState } from "react";
import type { Alert, Village } from "../api/client";
import { api } from "../api/client";
import { writeErrorText } from "../api/approval";
import { fmtMinutesLeft, statusWord } from "../format";

const LEVELS: Alert["level"][] = ["leave_now", "get_ready", "preventive", "update"];

interface Props {
  fireId: string | null;
  villages: Village[]; // the current at-risk list, most urgent first
  onSent: () => void;
}

// Manual alert: sent at once, the operator's confirm click is the approval (PROGRESS D-10).
export function NewAlertForm({ fireId, villages, onSent }: Props) {
  const [villageId, setVillageId] = useState("");
  const [level, setLevel] = useState<Alert["level"]>("leave_now");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const inFlight = useRef(false);

  const village = villages.find((v) => v.id === villageId) ?? villages[0];

  async function send() {
    if (!village || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setMessage(null);
    try {
      const a = await api.sendAlert({ village_id: village.id, fire_id: fireId, level });
      setMessage({ text: `Sent to ${a.village_name} (${statusWord(a.level)}).`, error: false });
      setConfirming(false);
    } catch (e) {
      setMessage({ text: writeErrorText(e).text, error: true });
    } finally {
      inFlight.current = false;
      setBusy(false);
      onSent();
    }
  }

  return (
    <details className="aq-new">
      <summary>New alert (manual)</summary>
      {villages.length === 0 ? (
        <p className="small">No village at risk: start a fire or pick a replay first.</p>
      ) : (
        <div className="aq-new-body">
          <label className="small">
            Village{" "}
            <select
              value={village?.id ?? ""}
              onChange={(e) => {
                setVillageId(e.target.value);
                setConfirming(false);
              }}
              disabled={busy}
            >
              {villages.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} · {statusWord(v.status)} · {fmtMinutesLeft(v.minutes_left)}
                </option>
              ))}
            </select>
          </label>
          <label className="small">
            Level{" "}
            <select
              value={level}
              onChange={(e) => {
                setLevel(e.target.value as Alert["level"]);
                setConfirming(false);
              }}
              disabled={busy}
            >
              {LEVELS.map((l) => (
                <option key={l} value={l}>
                  {statusWord(l)}
                </option>
              ))}
            </select>
          </label>
          {!confirming ? (
            <button type="button" onClick={() => setConfirming(true)} disabled={busy || !village}>
              Send…
            </button>
          ) : (
            <div className="aq-confirm" role="alert">
              <p>
                This sends to every phone around <strong>{village?.name}</strong> now ({statusWord(level)}).
              </p>
              <button type="button" className="aq-approve" onClick={send} disabled={busy}>
                {busy ? "Sending…" : "Yes, send now"}
              </button>{" "}
              <button type="button" className="ghost" onClick={() => setConfirming(false)} disabled={busy}>
                Back
              </button>
            </div>
          )}
          {message && (
            <p className={`small${message.error ? " error" : ""}`} role="status">
              {message.text}
            </p>
          )}
        </div>
      )}
    </details>
  );
}
