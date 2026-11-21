import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Alert } from "../api/client";
import type { AlertApprove } from "../api/approval";
import { approval, PENDING_KEY, sortQueue, writeErrorText } from "../api/approval";
import type { StreamState } from "../hooks/useEventSource";
import { ApprovalCard } from "./ApprovalCard";

const FALLBACK_POLL_MS = 10_000; // only while /events is down

interface Props {
  live: StreamState;
  /** Show this alert's village on the map. */
  onSelect: (a: Alert) => void;
}

export function ApprovalQueue({ live, onSelect }: Props) {
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
    <section className="flex min-h-0 flex-1 flex-col" aria-labelledby="aq-title">
      <div className="px-4 pb-3 pt-3">
        <p id="aq-title" className="label-mono">
          AI flags and risk-today places · nothing is sent without a click
        </p>
      </div>
      {pending.error && (
        <p className="px-4 pb-2 text-sm font-semibold text-fire-text">Could not load the queue: {writeErrorText(pending.error).text}</p>
      )}
      <ol className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto border-t p-4">
        {pending.isSuccess && queue.length === 0 && (
          <li className="text-sm text-muted-foreground">No flag waiting for approval.</li>
        )}
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
    </section>
  );
}
