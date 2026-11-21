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
    python 05_build_table.py [--kind short|long|both] [--max-hops 4] [--out out/train.parquet]
"""
import argparse, json
import numpy as np, pandas as pd
from scipy import ndimage
import config as C

FUEL = [f"fuel_{n}" for n in C.FUEL_CLASSES.values()]


def load_weather(fid):
    p = C.CACHE_WEATHER / f"{fid}.json"
    if not p.exists():
        return None
    w = pd.DataFrame(json.loads(p.read_text()))
    w["time"] = pd.to_datetime(w.time, utc=True)
    w = w.set_index("time").sort_index()
    rain = w.precipitation.fillna(0) >= 1.0
    last_rain = w.index.to_series().where(rain).ffill()
    w["hours_since_rain"] = (w.index.to_series() - last_rain).dt.total_seconds() / 3600
    w["hours_since_rain"] = w.hours_since_rain.fillna(C.WEATHER_LOOKBACK_DAYS * 24)
    w["rain_24h"] = w.precipitation.fillna(0).rolling(24, min_periods=1).sum()
    return w


def weather_at(w, t):
    h = t.floor("h")
    if h not in w.index:
        return None
    now = w.loc[h]
    nxt = w.loc[h + pd.Timedelta("1h"): h + pd.Timedelta("2h")]
    out = {k: now[k] for k in ["temperature_2m", "relative_humidity_2m", "vapour_pressure_deficit",
                               "wind_speed_10m", "wind_gusts_10m", "soil_moisture_0_to_7cm",
                               "hours_since_rain", "rain_24h"]}
    out["wind_dir_now"] = now.wind_direction_10m
    # mean wind over the next 2 h as a vector (directions can't be averaged as numbers)
    ws = pd.concat([now.to_frame().T, nxt])
    rad = np.radians(ws.wind_direction_10m.astype(float))
    u = (ws.wind_speed_10m * np.sin(rad)).mean(); v = (ws.wind_speed_10m * np.cos(rad)).mean()
    out["wind_speed_2h"] = float(np.hypot(u, v))
    out["wind_from_2h"] = float((np.degrees(np.arctan2(u, v)) + 360) % 360)
    out["gust_max_2h"] = float(ws.wind_gusts_10m.max())
    return out


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


def rows_for_pair(pr, f, cells, st, wx, rng, hop=1):
    shape = (int(f.ny), int(f.nx))
    burned = np.zeros(shape, bool)
    for k, c in cells.items():
        if k <= pr.pass_idx:
            burned[c.iy.values, c.ix.values] = True
    active = np.zeros(shape, bool); cur = cells[pr.pass_idx]
    active[cur.iy.values, cur.ix.values] = True
    frp_now = np.zeros(shape); frp_now[cur.iy.values, cur.ix.values] = cur.frp.values
    struct = np.ones((2 * C.JITTER_CELLS + 1,) * 2, bool)
    near = ndimage.binary_dilation(burned, struct) if C.JITTER_CELLS else burned
    label = np.zeros(shape, bool)
    for k in range(pr.pass_idx + 1, pr.pass_idx + hop + 1):
        nxt = cells[k]
        label[nxt.iy.values, nxt.ix.values] = True
    label &= ~near
    d_burn = ndimage.distance_transform_edt(~burned)
    d_act, (ay, ax) = ndimage.distance_transform_edt(~active, return_indices=True)
    cand = (d_burn <= C.CANDIDATE_RADIUS_CELLS) & ~near
    pos = cand & label
    share = np.where(d_burn <= getattr(C, "NEAR_CELLS", C.CANDIDATE_RADIUS_CELLS), C.NEG_KEEP,
                     getattr(C, "NEG_KEEP_FAR", C.NEG_KEEP))
    keep = pos | (cand & ~label & (rng.random(shape) < share))
    iy, ix = np.nonzero(keep)
    if len(iy) == 0:
        return None
    # direction from the nearest burning cell to this cell, compared with where the wind blows to
    dy = (iy - ay[iy, ix]).astype(float); dx = (ix - ax[iy, ix]).astype(float)
    bearing = np.degrees(np.arctan2(dx, dy)) % 360
    wind_to = (wx["wind_from_2h"] + 180) % 360
    dist_m = np.hypot(dx, dy) * C.CELL_M
    rise = st["elev"][iy, ix] - st["elev"][ay[iy, ix], ax[iy, ix]]
    t1 = pr.t1
    df = pd.DataFrame({
        "fire_id": pr.fire_id, "country": f.country, "pass_idx": pr.pass_idx, "t1": t1,
        "kind": pr.kind, "gap_min": pr.gap_min, "sat1": pr.sat1, "sat2": pr.sat2,
        "ix": ix, "iy": iy,
        "lat": f.lat0 + (iy + 0.5) * C.CELL_M / C.M_PER_DEG_LAT,
        "lon": f.lon0 + (ix + 0.5) * C.CELL_M / f.mlon,
        "label": label[iy, ix].astype(np.int8),
        "hop": hop,
        "weight": np.where(label[iy, ix], 1.0, 1.0 / share[iy, ix]).astype(np.float32),
        # fire geometry
        "dist_burned_m": d_burn[iy, ix] * C.CELL_M, "dist_active_m": d_act[iy, ix] * C.CELL_M,
        "downwind_cos": np.cos(np.radians(bearing - wind_to)),
        "bearing_deg": bearing,        # fire -> cell direction, so downwind_cos can be redone for another wind
        "uphill_grade": np.where(dist_m > 0, rise / np.maximum(dist_m, 1), 0.0),
        "n_active": pr.n_active, "n_burned": pr.n_burned, "frp_active_sum": cur.frp.sum(),
        "frp_nearest": frp_now[ay[iy, ix], ax[iy, ix]],
        "hour_local": ((t1.hour + t1.minute / 60 + f.lon_c / 15) % 24),
        # terrain and fuel at the cell
        "elev": st["elev"][iy, ix], "elev_std": st["elev_std"][iy, ix],
        "slope": st["slope"][iy, ix],
        "aspect_sin": np.sin(np.radians(st["aspect"][iy, ix])),
        "aspect_cos": np.cos(np.radians(st["aspect"][iy, ix])),
        **{k: st[k][iy, ix] for k in FUEL},
    })
    for k, v in wx.items():
        df[k] = v
    return df


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--kind", default="both")
    ap.add_argument("--max-hops", type=int, default=getattr(C, "MAX_HOPS", 1))
    ap.add_argument("--out", default=None, help="default: out/train.parquet")
    a = ap.parse_args()
    fires = pd.read_parquet(C.OUT / "fires.parquet").set_index("fire_id")
    pairs = add_hops(pd.read_parquet(C.OUT / "pairs.parquet"),
                     pd.read_parquet(C.OUT / "passes.parquet"), a.max_hops)
    if a.kind != "both":
        pairs = pairs[pairs.kind == a.kind]
    cells_all = pd.read_parquet(C.OUT / "pass_cells.parquet")
    cells_by_fire = {fid: {k: c for k, c in g.groupby("pass_idx")} for fid, g in cells_all.groupby("fire_id")}
    out, skipped = [], {"no_weather": 0, "no_static": 0, "weather_gap": 0}
    for fid, fp in pairs.groupby("fire_id"):
        sp = C.CACHE_STATIC / f"{fid}.npz"
        if not sp.exists():
            skipped["no_static"] += len(fp); continue
        w = load_weather(fid)
        if w is None:
            skipped["no_weather"] += len(fp); continue
        st = dict(np.load(sp)); f = fires.loc[fid]
        rng = np.random.default_rng(int(fid))
        for pr in fp.itertuples():
            wx = weather_at(w, pr.t1)
            if wx is None:
                skipped["weather_gap"] += 1; continue
            df = rows_for_pair(pr, f, cells_by_fire[fid], st, wx, rng, pr.hop)
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
