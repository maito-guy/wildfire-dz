// MapLibre paint properties need real colour strings, not CSS variables (DESIGN.md §9).
export const mapColors = {
  burningCore: "#9E1016",
  burning: "#E3262B",
  burningEdge: "#F26A21",
  zone1hFill: "rgba(227, 38, 43, 0.22)",
  zone1hLine: "#E3262B",
  zone2hFill: "rgba(242, 106, 33, 0.13)",
  zone2hLine: "#F26A21",
  nextPassLine: "#1C1B1A",
  alertArea: "#1C1B1A",
  land: "#ECE7DD",
  sea: "#D3DFE1",
  ink: "#1C1B1A",
  safe: "#6F6A62",
} as const;

// Village and alert status on the map and in the legend. SAFE is grey on purpose (DESIGN.md §3.1).
export const statusMapColor = {
  leave_now: mapColors.burning,
  get_ready: mapColors.burningEdge,
  safe: mapColors.safe,
  update: mapColors.ink,
  preventive: mapColors.ink,
} as const;
