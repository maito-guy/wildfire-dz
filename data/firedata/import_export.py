"""Turn the Algeria Fire Map export (CSV) into the files the API reads, so the dashboard shows real data.

    python import_export.py --export-dir ../algeria-fire-map-data      (or: make import-export)

Writes (schemas in docs/contracts.md):
  out/detections.parquet        VIIRS detections, all months, northern Algeria, low confidence dropped.
                                Same columns as step 2 (lat, lon, t, sat, frp, conf, daynight, country), so
                                step 6 can cut the replay passes from it and a later step 2 run can replace it.
  out/places.parquet            OSM settlements (step 6)
  out/replay_passes.parquet     holdout fire passes (step 6)
  out/history_grid.parquet      fire history per fire_map.history_cell_deg cell (api.detections build-history)
  <paths.risk_today>            the export's cell_risk.csv (0.1 deg cells) until model.risk (#27) exists.
                                Each 0.1 deg cell is split into the display lattice so the map has no gaps.
                                Its classes are mapped to the API levels; top_factors come from the export's
                                grid_cells.csv (fuel, slope) and the fire history, not from the risk model.
MODIS rows (1 km) are skipped: the map and the models use VIIRS 375 m only.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import config as C

REPO = Path(__file__).resolve().parents[2]
SAT_FROM_SOURCE = {"VIIRS_SNPP": "SNPP", "VIIRS_NOAA20": "NOAA20", "VIIRS_NOAA21": "NOAA21"}
LEVEL_FROM_CLASS = {"very-low": "low", "low": "low", "moderate": "moderate", "high": "high",
                    "very-high": "very_high", "extreme": "very_high"}
EXPORT_CELL_DEG = 0.1
STEEP_DEG = 10        # slope above this is listed as a factor
PAST_FIRE_COUNT = 50  # this many detections since 2012 in the cell -> "past fires"


def detections(export_dir: Path) -> pd.DataFrame:
    d = pd.read_csv(export_dir / "detections.csv",
                    usecols=["lng", "lat", "frp", "confidence", "acq_datetime", "instrument", "source", "daynight"])
    d = d[(d.instrument == "VIIRS") & (d.confidence != "low") & (d.lat >= C.DZA_MIN_LAT)]
    out = pd.DataFrame({
        "lat": d.lat.astype(float), "lon": d.lng.astype(float),
        "t": pd.to_datetime(d.acq_datetime, utc=True, format="ISO8601"),
        "sat": d.source.str.extract(r"^(VIIRS_[A-Z0-9]+?)_(?:SP|NRT)$")[0].map(SAT_FROM_SOURCE),
        "frp": d.frp.astype(float), "conf": d.confidence.str[0],
        "daynight": d.daynight, "country": "DZA"})
    key = out.lat.round(4).astype(str) + out.lon.round(4).astype(str) + out.t.dt.strftime("%Y%m%d%H%M") + out.sat
    return out[~key.duplicated()].sort_values("t").reset_index(drop=True)


def risk(export_dir: Path, history: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    r = pd.read_csv(export_dir / "cell_risk.csv", usecols=["cell_id", "lat", "lng", "day", "prob", "risk_class"])
    g = pd.read_csv(export_dir / "grid_cells.csv", usecols=["cell_id", "slope_deg", "land_cover"])
    r = r.merge(g, on="cell_id", how="left")
    unknown = set(r.risk_class) - set(LEVEL_FROM_CLASS)
    if unknown:
        raise SystemExit(f"cell_risk.csv has unknown risk_class value(s) {sorted(unknown)}")
    # past fires: history cells inside each 0.1 deg export cell
    half = EXPORT_CELL_DEG / 2
    iy = np.floor((history.lat + 1e-9) / EXPORT_CELL_DEG).astype(int)
    ix = np.floor((history.lon + 1e-9) / EXPORT_CELL_DEG).astype(int)
    fires = history.groupby([iy, ix])["count"].sum()
    r_key = list(zip(np.floor((r.lat - half + 1e-9) / EXPORT_CELL_DEG).astype(int),
                     np.floor((r.lng - half + 1e-9) / EXPORT_CELL_DEG).astype(int)))
    past = np.array([fires.get(k, 0) for k in r_key])

    def factors(row, n_past):
        f = []
        if row.land_cover in ("forest", "shrub"):
            f.append(f"{row.land_cover} fuel")
        if n_past >= PAST_FIRE_COUNT:
            f.append("past fires")
        if row.slope_deg >= STEEP_DEG:
            f.append("steep slope")
        if row.land_cover == "grass":
            f.append("dry grass")
        return f

    top = [factors(row, n) for row, n in zip(r.itertuples(index=False), past)]
    # split each 0.1 deg cell into display cells (the API merges cells onto risk.display_cell_deg)
    d = float(cfg["risk"]["display_cell_deg"])
    k = max(1, round(EXPORT_CELL_DEG / d))
    offs = (np.arange(k) + 0.5) * (EXPORT_CELL_DEG / k) - half
    oy, ox = (a.ravel() for a in np.meshgrid(offs, offs, indexing="ij"))
    n = len(r)
    rep = np.repeat(np.arange(n), k * k)
    return pd.DataFrame({
        "date": r.day.astype(str).to_numpy()[rep],
        "lat": np.round(r.lat.to_numpy()[rep] + np.tile(oy, n), 5),
        "lon": np.round(r.lng.to_numpy()[rep] + np.tile(ox, n), 5),
        "score": r.prob.astype(float).round(4).to_numpy()[rep],
        "level": r.risk_class.map(LEVEL_FROM_CLASS).to_numpy()[rep],
        "top_factors": [top[i] for i in rep]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-dir", required=True, help="folder with the export's CSV files")
    a = ap.parse_args()
    export_dir = Path(a.export_dir).expanduser().resolve()
    cfg = yaml.safe_load((REPO / "config.yaml").read_text())

    det = detections(export_dir)
    det.to_parquet(C.OUT / "detections.parquet", index=False)
    print(f"detections: {len(det):,} VIIRS rows, {det.t.min():%Y-%m-%d} .. {det.t.max():%Y-%m-%d %H:%M} UTC")

    subprocess.run([sys.executable, "06_places_replay.py", "--export-dir", str(export_dir)],
                   cwd=Path(__file__).parent, check=True)
    subprocess.run([sys.executable, "-m", "api.detections", "build-history"], cwd=REPO, check=True)

    history = pd.read_parquet(REPO / cfg["paths"]["history_grid"])
    rk = risk(export_dir, history, cfg)
    out = REPO / cfg["paths"]["risk_today"]
    out.parent.mkdir(parents=True, exist_ok=True)
    rk.to_parquet(out, index=False)
    print(f"risk: {len(rk):,} cells for {rk.date.max()} -> {out}  "
          f"({rk.level.value_counts().to_dict()})")


if __name__ == "__main__":
    main()
