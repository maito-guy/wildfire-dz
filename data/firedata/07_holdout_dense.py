"""Step 7: every grid cell around the held-out fires, for scoring model C on villages.

train.parquet keeps only cells within 3 km and a random 30 % of the cells that did not burn, so
most villages have no row. This reruns step 5's row builder (unchanged) on the holdout fires with
all cells kept out to the edge of each fire's terrain grid (GRID_MARGIN_CELLS, 6 km).
    python 07_holdout_dense.py              # holdouts        -> out/holdout_dense.parquet
    python 07_holdout_dense.py --events     # crossval.events -> out/events_dense.parquet
Output: out/holdout_dense.parquet = train.parquet columns + holdout + the fire's grid origin
(grid_lat0, grid_lon0, grid_mlon) so a village can be mapped to its cell.
"""
import argparse, importlib
from pathlib import Path
import numpy as np, pandas as pd, yaml
import config as C

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"
B = importlib.import_module("05_build_table")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", action="store_true", help="crossval.events instead of the holdouts")
    a = ap.parse_args()
    cfg = yaml.safe_load(REPO_CONFIG.read_text())
    holdouts = cfg["crossval"]["events"] if a.events else cfg["holdouts"]
    target = C.OUT / ("events_dense.parquet" if a.events else "holdout_dense.parquet")
    C.NEG_KEEP = C.NEG_KEEP_FAR = 1.0                  # keep every cell (weight becomes 1)
    C.CANDIDATE_RADIUS_CELLS = C.GRID_MARGIN_CELLS     # out to the edge of the terrain grid
    fires = pd.read_parquet(C.OUT / "fires.parquet").set_index("fire_id")
    pairs = pd.read_parquet(C.OUT / "pairs.parquet")
    cells_all = pd.read_parquet(C.OUT / "pass_cells.parquet")
    out = []
    for key, h in holdouts.items():
        w, s, e, n = h["bbox"]
        t0 = pd.Timestamp(h["start"], tz="UTC")
        t1 = pd.Timestamp(h["end"], tz="UTC") + pd.Timedelta(days=1)
        inbox = fires[fires.lon_c.between(w, e) & fires.lat_c.between(s, n)].index
        hp = pairs[pairs.fire_id.isin(inbox) & (pairs.t1 >= t0) & (pairs.t1 < t1)]
        n_rows = 0
        for fid, fp in hp.groupby("fire_id"):
            sp = C.CACHE_STATIC / f"{fid}.npz"
            wth = B.load_weather(fid)
            if not sp.exists() or wth is None:
                continue                               # fire never grew: no terrain/weather fetched
            st = dict(np.load(sp)); f = fires.loc[fid]
            cells = {k: c for k, c in cells_all[cells_all.fire_id == fid].groupby("pass_idx")}
            rng = np.random.default_rng(int(fid))
            for pr in fp.itertuples():
                wx = B.weather_at(wth, pr.t1)
                if wx is None:
                    continue
                df = B.rows_for_pair(pr, f, cells, st, wx, rng)
                if df is not None:
                    df["holdout"] = key
                    df["grid_lat0"], df["grid_lon0"], df["grid_mlon"] = f.lat0, f.lon0, f.mlon
                    out.append(df); n_rows += len(df)
        print(f"{key}: {hp.fire_id.nunique()} fires, {len(hp)} passes, {n_rows:,} cells", flush=True)
    pd.concat(out, ignore_index=True).to_parquet(target)


if __name__ == "__main__":
    main()
