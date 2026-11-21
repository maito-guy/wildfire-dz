import { useRef, useState } from "react";
import type { Alert } from "../api/client";
import type { AlertApprove } from "../api/approval";
import { langsOf, missingLangs, SOURCE_WORD } from "../api/approval";
import { BOTH_TIMES_TITLE, fmtAge, fmtBothTimes, statusWord } from "../format";
import { StatusBadge } from "./status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const STRIP: Record<Alert["level"], string> = {
  leave_now: "border-l-fire",
  get_ready: "border-l-flame",
  update: "border-l-ink",
  preventive: "border-l-ink",
};

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
  const missing = missingLangs(a.texts);
  const [mode, setMode] = useState<Mode>("view");
  const [busy, setBusy] = useState<"" | "approve" | "reject">("");
  const [error, setError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [radius, setRadius] = useState(String(a.area.radius_km));
  const [reason, setReason] = useState("");
  const inFlight = useRef(false); // no double send, even before the re-render disables the buttons

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

  const urgentNumber = a.minutes_left != null && a.level !== "preventive";
  return (
    <li
      className={cn(
        "rounded-xl border border-l-4 bg-card p-3.5 shadow-1 transition-shadow",
        STRIP[a.level],
        selected && "ring-2 ring-ink",
        busy !== "" && "opacity-70",
      )}
      aria-busy={busy !== ""}
      aria-label={`${a.village_name}, ${statusWord(a.level)}, pending approval`}
    >
      <button
        type="button"
        className="flex w-full items-center gap-3 text-left"
        onClick={() => onSelect(a)}
        aria-pressed={selected}
        title="Show on the map"
      >
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <StatusBadge status={a.level} />
            <span className="label-mono text-[10px]">Pending · {SOURCE_WORD[a.source]}</span>
          </span>
          <span className="mt-1.5 block truncate font-display text-[19px] font-bold leading-tight">{a.village_name}</span>
        </span>
        <span className="shrink-0 text-right">
          {urgentNumber ? (
            <>
              <span
                className={cn(
                  "block font-display text-[30px] font-extrabold leading-none tracking-[-0.04em] tabular-nums",
                  a.level === "leave_now" ? "text-fire" : a.level === "get_ready" ? "text-flame" : "text-ink",
                )}
              >
                {a.minutes_left}
              </span>
              <span className="label-mono text-[9.5px]">min left</span>
            </>
          ) : (
            <span className="text-xs font-medium text-muted-foreground">{minutesText(a)}</span>
          )}
        </span>
      </button>
      {a.level !== "preventive" && (
        <p className="mt-2 font-mono text-[12px] font-semibold tabular-nums" title={BOTH_TIMES_TITLE}>
          {fmtBothTimes(a.minutes_left, a.ai_minutes_left)}
        </p>
      )}
      <p className={cn("font-mono text-[11.5px] leading-relaxed text-muted-foreground tabular-nums", a.level === "preventive" ? "mt-2" : "mt-1")}>
        {a.level === "preventive"
          ? `fire risk for ${a.scenario_time.slice(0, 10)} (no fire yet)`
          : `${a.distance_km.toFixed(1)} km from the fire · fire to the ${a.fire_direction} · leave → ${a.leave_toward} · ${fmtAge(a.data_age_min)}`}{" "}
        · radius {a.area.radius_km} km{selected ? " · shown on the map" : ""}
      </p>

      {mode !== "edit" && langs.length > 0 && (
        <div className="mt-3 flex flex-col gap-1.5" aria-label="Texts the phones will show">
          {langs.map((l) => (
            <div key={l.code} className="rounded-lg bg-secondary/70 px-2.5 py-2">
              <span className="label-mono block text-[10px]">{l.name}</span>
              <p
                dir={l.rtl ? "rtl" : "ltr"}
                lang={l.code}
                className={cn("mt-0.5 whitespace-pre-wrap text-[13.5px] leading-snug", l.rtl && "text-right text-[15px] font-medium")}
              >
                {a.texts[l.code]}
              </p>
            </div>
          ))}
          {missing.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Not ready yet: {missing.map((l) => l.name).join(", ")}. Phones that chose one of these show{" "}
              {"fr" in a.texts ? "French" : "English"} first.
            </p>
          )}
        </div>
      )}
      {langs.length === 0 && <p className="mt-2 text-sm text-muted-foreground">No alert text yet.</p>}

      {mode === "edit" && (
        <div className="mt-3 flex flex-col gap-2.5">
          {langs.map((l) => (
            <label key={l.code} className="flex flex-col gap-1">
              <span className="label-mono text-[10px]">{l.name}</span>
              <Textarea
                dir={l.rtl ? "rtl" : "ltr"}
                lang={l.code}
                rows={3}
                value={drafts[l.code] ?? ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [l.code]: e.target.value }))}
                disabled={busy !== ""}
                className={cn("bg-card text-[13.5px]", l.rtl && "text-right")}
              />
              {(drafts[l.code] ?? "").trim() === "" && <span className="text-xs font-semibold text-fire-text">Text cannot be empty.</span>}
            </label>
          ))}
          <label className="flex items-center gap-2 text-sm">
            <span className="label-mono text-[10px]">Radius km</span>
            <Input
              type="number"
              min={0.1}
              max={50}
              step={0.5}
              value={radius}
              onChange={(e) => setRadius(e.target.value)}
              disabled={busy !== ""}
              className="h-8 w-24 tabular-nums"
            />
          </label>
          {!radiusOk && <span className="text-xs font-semibold text-fire-text">Radius must be more than 0 and at most 50 km.</span>}
        </div>
      )}

      {mode === "reject" && (
        <label className="mt-3 flex flex-col gap-1">
          <span className="label-mono text-[10px]">Reason for rejecting (required)</span>
          <Input type="text" value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy !== ""} autoFocus />
        </label>
      )}

      {error && (
        <p className="mt-2 text-xs font-semibold text-fire-text" role="alert">
          {error}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {mode === "reject" ? (
          <>
            <Button variant="default" size="sm" disabled={busy !== "" || reason.trim() === ""} onClick={reject}>
              {busy === "reject" ? "Rejecting…" : "Confirm reject"}
            </Button>
            <Button variant="outline" size="sm" disabled={busy !== ""} onClick={() => setMode("view")}>
              Back
            </Button>
          </>
        ) : (
          <>
            <Button variant="alert" size="sm" disabled={busy !== "" || editInvalid} onClick={approve}>
              {busy === "approve" ? "Sending…" : mode === "edit" ? "Approve & send edited" : "Approve & send"}
            </Button>
            {mode === "edit" ? (
              <Button variant="outline" size="sm" disabled={busy !== ""} onClick={() => setMode("view")}>
                Discard edits
              </Button>
            ) : (
              <Button variant="outline" size="sm" disabled={busy !== ""} onClick={startEdit}>
                Edit
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={busy !== ""}
              onClick={() => {
                setMode("reject");
                setError("");
              }}
            >
              Reject
            </Button>
          </>
        )}
      </div>
    </li>
  );
}
