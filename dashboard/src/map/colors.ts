// MapLibre paint properties need real colour strings, not CSS variables (DESIGN.md §9).
export const mapColors = {
  burningCore: "#9E1016",
  burning: "#E3262B",
  burningEdge: "#F26A21",
  zone1hFill: "rgba(227, 38, 43, 0.35)",
  zone1hLine: "#E3262B",
  zone2hFill: "rgba(242, 106, 33, 0.25)",
  zone2hLine: "#F26A21",
  land: "#ECE7DD",
  sea: "#D3DFE1",
  ink: "#1C1B1A",
  inkOnDark: "#F5F6F8", // the same lines on a dark map (DESIGN2 --text)
  safe: "#6F6A62",
  // Model C's advice layer (#53): a cool violet, so it never reads as B's fire zones or a village status.
  ai: "#5B3FB8",
  aiOnDark: "#B9A6FF", // the same lines on a dark map
} as const;

// Village and alert status on the map and in the legend. SAFE is grey on purpose (DESIGN.md §3.1).
export const statusMapColor = {
  leave_now: mapColors.burning,
  get_ready: mapColors.burningEdge,
  safe: mapColors.safe,
  update: mapColors.ink,
  preventive: mapColors.ink,
} as const;
