// Native EventSource (SSE) as a React hook, plus the dashboard's /events wiring.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import type { Alert } from "../api/client";
import { PENDING_KEY } from "../api/approval";

export type StreamState = "connecting" | "open" | "down";

const RETRY_MS = 3000; // only when the browser gave up (readyState CLOSED, e.g. an HTTP error)

/**
 * Opens `url` with the browser's EventSource and calls `handlers[event]` with the
 * parsed JSON data of each named event. The browser reconnects by itself after a
 * dropped connection; if it gives up (CLOSED), the hook opens a new one.
 */
export function useEventSource(
  url: string,
  handlers: Record<string, (data: unknown) => void>,
): { connected: boolean; state: StreamState } {
  const [state, setState] = useState<StreamState>("connecting");
  const onEvent = useEffectEvent((name: string, raw: string) => {
    let data: unknown = raw;
    try {
      data = JSON.parse(raw);
    } catch {
      // not JSON: pass the raw string
    }
    handlers[name]?.(data);
  });
  // Event names are read once per connection; a changed set reconnects.
  const names = Object.keys(handlers).sort().join(",");

  useEffect(() => {
    let es: EventSource | null = null;
    let retry: number | undefined;
    let stopped = false;

    const open = () => {
      es = new EventSource(url);
      es.onopen = () => setState("open");
      es.onerror = () => {
        setState("down");
        if (es?.readyState === EventSource.CLOSED && !stopped) {
          es.close();
          retry = window.setTimeout(open, RETRY_MS);
        }
      };
      for (const name of names ? names.split(",") : []) {
        es.addEventListener(name, (e) => onEvent(name, (e as MessageEvent<string>).data));
      }
    };
    open();
    return () => {
      stopped = true;
      window.clearTimeout(retry);
      es?.close();
    };
  }, [url, names]);

  return { connected: state === "open", state };
}

const ALERT_EVENTS = ["flag", "flag_updated", "alert_sent", "alert_rejected", "alert_cancelled"] as const;
const BATCH_MS = 200; // one refetch for a burst of flags from one /predict

function isAlert(d: unknown): d is Alert {
  return typeof d === "object" && d !== null && typeof (d as Alert).id === "string" && "status" in d;
}

/**
 * The dashboard's live updates from GET /events. Each alert event updates the
 * approval queue at once from the event data, then refreshes the alert and
 * village queries (batched).
 */
export function useLiveEvents(): { connected: boolean; state: StreamState } {
  const queryClient = useQueryClient();
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const onAlert = (data: unknown) => {
    if (isAlert(data)) {
      queryClient.setQueryData<Alert[]>(PENDING_KEY, (old) => {
        if (!old) return old;
        const rest = old.filter((a) => a.id !== data.id);
        return data.status === "pending" ? [...rest, data] : rest;
      });
    }
    if (timer.current !== undefined) return;
    timer.current = window.setTimeout(() => {
      timer.current = undefined;
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      void queryClient.invalidateQueries({ queryKey: ["villages"] });
    }, BATCH_MS);
  };

  return useEventSource("/events", {
    ...Object.fromEntries(ALERT_EVENTS.map((e) => [e, onAlert])),
    // First event of every (re)connection: catch up on what was missed while down.
    hello: () => onAlert(null),
  });
}
