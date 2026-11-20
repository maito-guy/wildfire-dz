// Alert log (DESIGN.md §8): time · status · place · source, newest first. Sent and cancelled rows link
// to their CAP 1.2 message. "0 receivers connected" is shown in red when nobody would get it.
import type { Alert } from "../api/client";
import { api } from "../api/client";
import { alertStatusWord, fmtClock, hasCap, lastChangeAt } from "../format";
import type { BadgeStatus } from "./status-badge";
import { StatusBadge } from "./status-badge";
import { cn } from "@/lib/utils";

function badge(a: Alert): BadgeStatus {
  return a.status === "cancelled" ? "cancel" : a.level;
}

export function AlertLog({ alerts, phones }: { alerts: Alert[]; phones: number | undefined }) {
  const sent = alerts.filter((a) => a.status === "sent").length;
  const cancelled = alerts.filter((a) => a.status === "cancelled").length;
  return (
    <section className="max-h-[34%] shrink-0 overflow-y-auto border-t bg-card px-4 py-3" aria-labelledby="log-title">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 id="log-title" className="label-mono">
          Alert log
        </h2>
        <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
          {sent} sent · {cancelled} cancelled
        </span>
      </div>
      {phones === 0 && <p className="mb-1.5 text-xs font-semibold text-fire-text">0 receivers connected</p>}
      {alerts.length === 0 && <p className="text-sm text-muted-foreground">No alert yet for this fire.</p>}
      <ol className="flex flex-col gap-1.5">
        {[...alerts].reverse().map((a) => (
          <li
            key={a.id}
            className={cn("flex items-center gap-2.5 text-[13px]", (a.status === "rejected" || a.status === "cancelled") && "opacity-60")}
          >
            <span className="w-10 shrink-0 font-mono text-xs tabular-nums text-muted-foreground">{fmtClock(lastChangeAt(a))}</span>
            <StatusBadge status={badge(a)} className="px-1.5 py-0.5 text-[9.5px]" />
            <span className={cn("min-w-0 flex-1 truncate font-medium", a.status === "pending" && "italic")}>{a.village_name}</span>
            <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
              {a.source === "manual" ? "operator" : "auto"}
              {a.status !== "sent" ? ` · ${alertStatusWord(a.status)}` : ""}
            </span>
            {hasCap(a) && (
              <a
                className="shrink-0 font-mono text-[11px] font-semibold text-ink underline underline-offset-2"
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
    </section>
  );
}
