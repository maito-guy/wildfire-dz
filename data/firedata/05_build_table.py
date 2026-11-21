"""Step 5: one training row per candidate cell per pass pair -> data/out/train.parquet

Label  : 1 if the cell is burning at the next pass (and was not already burning or next to it).
Rows   : every cell within CANDIDATE_RADIUS_CELLS (6 km) of the fire, all positives, and a share of
         negatives: NEG_KEEP within NEAR_CELLS, NEG_KEEP_FAR beyond (`weight` = 1/share undoes it).
Pairs  : each pass k with the next pass (hop 1) and with passes k+2 .. k+MAX_HOPS while the gap is
         <= 16 h. Label = burning at ANY of those later passes, so the row answers "burning within
         gap_min minutes?", which is what the dashboard asks for every horizon.
Weather: values at the first pass, the actual values 1 h and 2 h later (a perfect forecast,
         since history has no forecasts), and hours since the last rain.
Pairs with no weather or terrain file yet are skipped, so you can rerun after steps 3-4 finish.
    python 05_build_table.py [--kind short|long|both] [--max-hops 4] [--out out/train.parquet] [--terrain fire|raster]
Rows are built by core/features.py, the same code the API uses (#18). --terrain raster reads terrain and fuel
from the national 375 m raster (paths.static_raster) instead of step 4's per-fire files.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy import ndimage
import config as C

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from core import features as F                      # noqa: E402  the builder the API uses too (#18)

FUEL = F.FUEL
weather_at = F.weather_at                           # kept: 07_holdout_dense.py calls B.weather_at


def load_weather(fid):
    p = C.CACHE_WEATHER / f"{fid}.json"
    if not p.exists():
        return None
    return F.prepare_weather(pd.DataFrame(json.loads(p.read_text())), C.WEATHER_LOOKBACK_DAYS)


def grid_of(f):
    return F.FireGrid(f.lat0, f.lon0, f.mlon, int(f.nx), int(f.ny), f.lon_c, C.CELL_M)


def terrain_for(fid, f):
    """Terrain source: the national raster when TERRAIN == "raster" (Q-05), else the fire's step 4 file."""
    if TERRAIN == "raster":
        return F.raster_terrain(RASTER, grid_of(f))
    sp = C.CACHE_STATIC / f"{fid}.npz"
    return F.fire_npz_terrain(dict(np.load(sp))) if sp.exists() else None


TERRAIN, RASTER = "fire", None                     # set by --terrain


def add_hops(pairs, passes, max_hops):
    """Consecutive pairs (hop 1) plus pass k -> k+j for j = 2..max_hops while the gap is <= 16 h."""
    pairs = pairs.assign(hop=1)
    if max_hops <= 1:
        return pairs
    ps = passes.set_index(["fire_id", "pass_idx"])
    extra = []
    for j in range(2, max_hops + 1):
        key = pd.MultiIndex.from_arrays([pairs.fire_id, pairs.pass_idx + j])
        ok = key.isin(ps.index)
        e = pairs[ok].copy()
        later = ps.loc[key[ok]]
        e["t2"] = pd.to_datetime(later.t.values, utc=True)
        e["gap_min"] = (e.t2 - pd.to_datetime(e.t1, utc=True)).dt.total_seconds() / 60
        e["sat2"] = later.sat.values
        e["hop"] = j
        e = e[e.gap_min <= C.LONG_PAIR[1]]
        e["kind"] = np.where(e.gap_min <= C.SHORT_PAIR[1], "short", "long")
        extra.append(e)
    return pd.concat([pairs, *extra], ignore_index=True)


def rows_for_pair(pr, f, cells, terrain, wx, rng, hop=1):
    grid = grid_of(f)
    shape = (grid.ny, grid.nx)
    state = F.fire_state(grid, cells, pr.pass_idx)
    near = F.near_mask(state.burned, C.JITTER_CELLS)
    label = np.zeros(shape, bool)
    for k in range(pr.pass_idx + 1, pr.pass_idx + hop + 1):
        nxt = cells[k]
        label[nxt.iy.values, nxt.ix.values] = True
    label &= ~near
    d_burn = ndimage.distance_transform_edt(~state.burned)
    cand = (d_burn <= C.CANDIDATE_RADIUS_CELLS) & ~near
    pos = cand & label
    share = np.where(d_burn <= getattr(C, "NEAR_CELLS", C.CANDIDATE_RADIUS_CELLS), C.NEG_KEEP,
                     getattr(C, "NEG_KEEP_FAR", C.NEG_KEEP))
    keep = pos | (cand & ~label & (rng.random(shape) < share))
    iy, ix = np.nonzero(keep)
    if len(iy) == 0:
        return None
    if isinstance(terrain, dict):                    # a step 4 file's arrays (older callers)
        terrain = F.fire_npz_terrain(terrain)
    meta = {"fire_id": pr.fire_id, "country": f.country, "pass_idx": pr.pass_idx, "t1": pr.t1,
            "kind": pr.kind, "gap_min": pr.gap_min, "sat1": pr.sat1, "sat2": pr.sat2}
    extra = {"label": label[iy, ix].astype(np.int8), "hop": hop,
             "weight": np.where(label[iy, ix], 1.0, 1.0 / share[iy, ix]).astype(np.float32)}
    return F.cell_features(grid, state, iy, ix, pass_idx=pr.pass_idx, t1=pr.t1, wx=wx, terrain=terrain,
                           meta=meta, extra=extra)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--kind", default="both")
    ap.add_argument("--max-hops", type=int, default=getattr(C, "MAX_HOPS", 1))
    ap.add_argument("--out", default=None, help="default: out/train.parquet")
    ap.add_argument("--terrain", choices=["fire", "raster"], default="fire",
                    help="raster: terrain/fuel from config.yaml paths.static_raster (Q-05), not step 4's files")
    a = ap.parse_args()
    global TERRAIN, RASTER
    TERRAIN = a.terrain
    if TERRAIN == "raster":
        from core import static_raster
        RASTER = static_raster.load()
    fires = pd.read_parquet(C.OUT / "fires.parquet").set_index("fire_id")
    pairs = add_hops(pd.read_parquet(C.OUT / "pairs.parquet"),
                     pd.read_parquet(C.OUT / "passes.parquet"), a.max_hops)
    if a.kind != "both":
        pairs = pairs[pairs.kind == a.kind]
    cells_all = pd.read_parquet(C.OUT / "pass_cells.parquet")
    cells_by_fire = {fid: {k: c for k, c in g.groupby("pass_idx")} for fid, g in cells_all.groupby("fire_id")}
    out, skipped = [], {"no_weather": 0, "no_static": 0, "weather_gap": 0}
    for fid, fp in pairs.groupby("fire_id"):
        f = fires.loc[fid]
        terrain = terrain_for(fid, f)
        if terrain is None:
            skipped["no_static"] += len(fp); continue
        w = load_weather(fid)
        if w is None:
            skipped["no_weather"] += len(fp); continue
        rng = np.random.default_rng(int(fid))
        for pr in fp.itertuples():
            wx = weather_at(w, pr.t1)
            if wx is None:
                skipped["weather_gap"] += 1; continue
            df = rows_for_pair(pr, f, cells_by_fire[fid], terrain, wx, rng, pr.hop)
            if df is not None:
                out.append(df)
    if not out:
        raise SystemExit(f"no rows built; skipped: {skipped}. Run steps 3 and 4 first.")
    t = pd.concat(out, ignore_index=True)
    f64 = t.select_dtypes("float64").columns
    t[f64] = t[f64].astype(np.float32)                 # halves the size; 7 digits is plenty
    t.to_parquet(a.out or C.OUT / "train.parquet")
    print(f"{len(t):,} rows, {int(t.label.sum()):,} positive, from {t.fire_id.nunique():,} fires; skipped pairs: {skipped}")
    print(t.groupby(["country", "kind", "hop"]).label.agg(["size", "sum"]))


if __name__ == "__main__":
    main()
