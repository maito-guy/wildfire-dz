// GET /scoreboard (docs/contracts.md §2). The endpoint has no response_model,
// so the generated schema types it as unknown; these types mirror the contract.
// Every metric may be null ("not measured"), and any field may be missing in an
// older scoreboard.json, so everything optional is typed optional.
import { ApiError } from "./client";

export type Metric = number | null;

export interface ModelScore {
  recall_1h?: Metric;
  false_alarm_cell_share?: Metric;
  zone_cells_per_burned_cell?: Metric;
  missed_villages?: Metric;
  median_lead_min?: Metric;
  false_alarm_villages?: Metric;
  status?: string;
}

export interface HoldoutScore {
  holdout: string;
  name?: string;
  n_fires?: number | null;
  status?: string;
  models?: Record<string, ModelScore>;
}

// "Village X warned 1 h 40 before; old method 25 min" for the replay fire.
export interface ReplayCounter {
  holdout?: string | null;
  village?: string | null;
  model?: string | null;
  lead_min?: Metric;
  old_method?: string | null;
  old_method_lead_min?: Metric;
  status?: string;
}

export interface Scoreboard {
  stub?: boolean;
  status?: string;
  generated_at?: string | null;
  weather_note?: string;
  horizon?: string;
  fires?: HoldoutScore[];
  replay_counter?: ReplayCounter | null;
  ship_c?: { rule?: string; decision?: string };
}

export async function fetchScoreboard(): Promise<Scoreboard> {
  const r = await fetch("/scoreboard");
  if (!r.ok) throw new ApiError("/scoreboard", r.status, await r.text());
  return (await r.json()) as Scoreboard;
}
