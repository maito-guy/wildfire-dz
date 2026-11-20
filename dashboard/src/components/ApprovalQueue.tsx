import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Alert, Village } from "../api/client";
import type { AlertApprove } from "../api/approval";
import { approval, PENDING_KEY, sortQueue, writeErrorText } from "../api/approval";
import type { StreamState } from "../hooks/useEventSource";
import { ApprovalCard } from "./ApprovalCard";
import "./ApprovalQueue.css";
import { NewAlertForm } from "./NewAlertForm";

const FALLBACK_POLL_MS = 10_000; // only while /events is down

interface Props {
  live: StreamState;
  fireId: string | null;
  villages: Village[];
  /** Show this alert's village on the map. */
  onSelect: (a: Alert) => void;
}

export function ApprovalQueue({ live, fireId, villages, onSelect }: Props) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const pending = useQuery({
    queryKey: PENDING_KEY,
    queryFn: approval.pending,
    refetchInterval: live === "open" ? false : FALLBACK_POLL_MS,
  });
  const queue = sortQueue(pending.data ?? []);

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["alerts"] }),
      queryClient.invalidateQueries({ queryKey: ["villages"] }),
    ]);

  // Returns an error text for the card, or null once the alert left the queue.
  async function run(a: Alert, action: () => Promise<Alert>): Promise<string | null> {
    try {
      await action();
      queryClient.setQueryData<Alert[]>(PENDING_KEY, (old) => old?.filter((x) => x.id !== a.id));
      void refresh();
      return null;
    } catch (e) {
      const { text, stale } = writeErrorText(e);
      if (stale) void refresh();
      return text;
    }
  }

  const onApprove = (a: Alert, body?: AlertApprove) => run(a, () => approval.approve(a.id, body));
  const onReject = (a: Alert, reason: string) => run(a, () => approval.reject(a.id, reason));

  return (
    <section className="aq" aria-labelledby="aq-title">
      <h3 id="aq-title">
        Approval queue{" "}
        <span className="small">
          ({queue.length} pending · most urgent first, preventive below · nothing is sent without a click)
        </span>
      </h3>
      {live === "down" && (
        <p className="aq-down" role="status">
          Live updates disconnected — reconnecting. Checking for new flags every 10 s.
        </p>
      )}
      {live === "connecting" && <p className="small">Connecting to live updates…</p>}
      {pending.error && <p className="small error">Could not load the queue: {writeErrorText(pending.error).text}</p>}
      {pending.isSuccess && queue.length === 0 && <p className="small">No flag waiting for approval.</p>}
      <ol className="aq-list">
        {queue.map((a) => (
          <ApprovalCard
            key={a.id}
            alert={a}
            selected={a.id === selectedId}
            onSelect={(x) => {
              setSelectedId(x.id);
              onSelect(x);
            }}
            onApprove={onApprove}
            onReject={onReject}
          />
        ))}
      </ol>
      <NewAlertForm fireId={fireId} villages={villages} onSent={() => void refresh()} />
    </section>
  );
}
