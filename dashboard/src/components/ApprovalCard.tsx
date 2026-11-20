import { useRef, useState } from "react";
import type { Alert } from "../api/client";
import type { AlertApprove } from "../api/approval";
import { langsOf, SOURCE_WORD } from "../api/approval";
import { fmtAge, statusWord } from "../format";

interface Props {
  alert: Alert;
  selected: boolean;
  onSelect: (a: Alert) => void;
  /** Runs one write call; resolves to an error text, or null on success. */
  onApprove: (a: Alert, body?: AlertApprove) => Promise<string | null>;
  onReject: (a: Alert, reason: string) => Promise<string | null>;
}

type Mode = "view" | "edit" | "reject";

function minutesText(a: Alert): string {
  if (a.minutes_left != null) return `${a.minutes_left} min left`;
  return a.level === "preventive" ? "risk today (no spread time)" : "not reached within 2 h";
}

export function ApprovalCard({ alert: a, selected, onSelect, onApprove, onReject }: Props) {
  const langs = langsOf(a.texts);
  const [lang, setLang] = useState(langs[0]?.code ?? "");
  const [mode, setMode] = useState<Mode>("view");
  const [busy, setBusy] = useState<"" | "approve" | "reject">("");
  const [error, setError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [radius, setRadius] = useState(String(a.area.radius_km));
  const [reason, setReason] = useState("");
  const inFlight = useRef(false); // no double send, even before the re-render disables the buttons

  const shown = langs.find((l) => l.code === lang) ?? langs[0];
  const radiusNum = Number(radius);
  const radiusOk = radius.trim() !== "" && Number.isFinite(radiusNum) && radiusNum > 0 && radiusNum <= 50;
  const emptyText = mode === "edit" && langs.some((l) => (drafts[l.code] ?? "").trim() === "");
  const editInvalid = mode === "edit" && (!radiusOk || emptyText);

  function startEdit() {
    setDrafts({ ...a.texts });
    setRadius(String(a.area.radius_km));
    setMode("edit");
    setError("");
  }

  async function approve() {
    let body: AlertApprove | undefined;
    if (mode === "edit") {
      const texts = Object.fromEntries(
        Object.entries(drafts)
          .map(([k, v]) => [k, v.trim()] as const)
          .filter(([k, v]) => v !== a.texts[k]),
      );
      body = {
        ...(Object.keys(texts).length ? { texts } : {}),
        ...(radiusNum !== a.area.radius_km ? { radius_km: radiusNum } : {}),
      };
      if (!body.texts && body.radius_km === undefined) body = undefined;
    }
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy("approve");
    setError("");
    const err = await onApprove(a, body);
    inFlight.current = false;
    setBusy("");
    if (err) setError(err);
  }

  async function reject() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy("reject");
    setError("");
    const err = await onReject(a, reason.trim());
    inFlight.current = false;
    setBusy("");
    if (err) setError(err);
  }

  return (
    <li
      className={`aq-card${selected ? " aq-selected" : ""}`}
      aria-busy={busy !== ""}
      aria-label={`${a.village_name}, ${statusWord(a.level)}, pending approval`}
    >
      <button type="button" className="aq-head" onClick={() => onSelect(a)} aria-pressed={selected}>
        <span className={`badge ${a.level}`}>{statusWord(a.level)}</span>
        <span className="aq-village">{a.village_name}</span>
        <span className="aq-minutes">{minutesText(a)}</span>
      </button>
      <div className="aq-facts small">
        {a.level === "preventive"
          ? `fire risk for ${a.scenario_time.slice(0, 10)} (no fire yet)`
          : `${a.distance_km.toFixed(1)} km from the fire · fire to the ${a.fire_direction} · leave toward ${a.leave_toward} · ${fmtAge(a.data_age_min)}`}{" "}
        · {SOURCE_WORD[a.source]} · radius {a.area.radius_km} km · pending approval
        {selected ? " · shown on the map" : ""}
      </div>

      {mode !== "edit" && shown && (
        <div className="aq-preview">
          <label className="small">
            Text{" "}
            <select value={shown.code} onChange={(e) => setLang(e.target.value)}>
              {langs.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <p dir={shown.rtl ? "rtl" : "ltr"} lang={shown.code}>
            {a.texts[shown.code]}
          </p>
        </div>
      )}
      {langs.length === 0 && <p className="small">No alert text yet.</p>}

      {mode === "edit" && (
        <div className="aq-edit">
          {langs.map((l) => (
            <label key={l.code} className="small">
              {l.name}
              <textarea
                dir={l.rtl ? "rtl" : "ltr"}
                lang={l.code}
                rows={3}
                value={drafts[l.code] ?? ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [l.code]: e.target.value }))}
                disabled={busy !== ""}
              />
              {(drafts[l.code] ?? "").trim() === "" && <span className="error">Text cannot be empty.</span>}
            </label>
          ))}
          <label className="small">
            Radius (km, more than 0 and at most 50){" "}
            <input
              type="number"
              min={0.1}
              max={50}
              step={0.5}
              value={radius}
              onChange={(e) => setRadius(e.target.value)}
              disabled={busy !== ""}
            />
          </label>
          {!radiusOk && <span className="small error">Radius must be more than 0 and at most 50 km.</span>}
        </div>
      )}

      {mode === "reject" && (
        <label className="small aq-reason">
          Reason for rejecting (required)
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={busy !== ""}
            autoFocus
          />
        </label>
      )}

      {error && (
        <p className="small error" role="alert">
          {error}
        </p>
      )}

      <div className="aq-actions">
        {mode === "reject" ? (
          <>
            <button
              type="button"
              className="aq-reject"
              disabled={busy !== "" || reason.trim() === ""}
              onClick={reject}
            >
              {busy === "reject" ? "Rejecting…" : "Confirm reject"}
            </button>
            <button type="button" className="ghost" disabled={busy !== ""} onClick={() => setMode("view")}>
              Back
            </button>
          </>
        ) : (
          <>
            <button type="button" className="aq-approve" disabled={busy !== "" || editInvalid} onClick={approve}>
              {busy === "approve" ? "Sending…" : mode === "edit" ? "Approve & send edited" : "Approve & send"}
            </button>
            {mode === "edit" ? (
              <button type="button" className="ghost" disabled={busy !== ""} onClick={() => setMode("view")}>
                Discard edits
              </button>
            ) : (
              <button type="button" className="ghost" disabled={busy !== ""} onClick={startEdit}>
                Edit
              </button>
            )}
            <button
              type="button"
              className="ghost"
              disabled={busy !== ""}
              onClick={() => {
                setMode("reject");
                setError("");
              }}
            >
              Reject
            </button>
          </>
        )}
      </div>
    </li>
  );
}
