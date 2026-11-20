// Today's risk layer (docs/contracts.md v0.4, GET /risk). Reading it also creates the day's
// preventive flags for very-high-risk places (they show up in the approval queue).
import { ApiError } from "./client";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type RiskResponse = Schemas["RiskResponse"];
export type RiskCell = Schemas["RiskCell"];
export type RiskPlace = Schemas["RiskPlace"];
export type RiskLevel = RiskCell["level"];

export const RISK_KEY = ["risk"] as const;

export async function fetchRisk(): Promise<RiskResponse> {
  const r = await fetch("/risk");
  if (!r.ok) throw new ApiError("/risk", r.status, await r.text());
  return (await r.json()) as RiskResponse;
}

// Highest first. "low" cells are never sent by the API (risk.min_level_shown).
export const RISK_LEVELS: RiskLevel[] = ["very_high", "high", "moderate", "low"];

export const RISK_WORD: Record<RiskLevel, string> = {
  very_high: "Very high",
  high: "High",
  moderate: "Moderate",
  low: "Low",
};

// Sequential in the DESIGN.md palette (no new hues): sand → flame → fire text red. The word is always shown too.
export const RISK_COLOR: Record<RiskLevel, string> = {
  very_high: "#B8161B",
  high: "#F26A21",
  moderate: "#F2B48A",
  low: "#D6D0C5",
};
