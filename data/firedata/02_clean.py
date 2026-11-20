"""Step 2: clean detections, group them into fires and satellite passes, and list pass pairs.

Inputs : data/raw_firms/*.csv (step 1) and, optionally, the Algeria Fire Map export
         (python 02_clean.py --export path/to/detections.csv)
Outputs: data/out/detections.parquet  one row per kept detection
         data/out/fires.parquet       one row per fire, with its local 375 m grid
         data/out/pass_cells.parquet  burning cells of every pass (fire_id, pass_idx, ix, iy, frp)
         data/out/passes.parquet      one row per pass
         data/out/pairs.parquet       consecutive passes 20 min - 16 h apart, with growth counts
"""
import argparse, glob
from pathlib import Path
import numpy as np, pandas as pd
from scipy import ndimage
import config as C

SAT_FROM_SOURCE = {"VIIRS_SNPP": "SNPP", "VIIRS_NOAA20": "NOAA20", "VIIRS_NOAA21": "NOAA21"}


# ---------- loading ----------
def load_firms_dir():
    frames = []
    for f in sorted(glob.glob(str(C.RAW_FIRMS / "*.csv"))):
        parts = Path(f).stem.split("_")
        country, sid = parts[0], "_".join(parts[1:-2])
        try:
            d = pd.read_csv(f)
        except pd.errors.EmptyDataError:
            continue
        if d.empty or "latitude" not in d:
            continue
        t = pd.to_datetime(d.acq_date + " " + d.acq_time.astype(int).astype(str).str.zfill(4),
                           format="%Y-%m-%d %H%M", utc=True)
        frames.append(pd.DataFrame({
            "lat": d.latitude, "lon": d.longitude, "t": t,
            "sat": SAT_FROM_SOURCE[sid.rsplit("_", 1)[0]],
            "frp": d.frp, "conf": d.confidence.astype(str).str[0].str.lower(),
            "daynight": d.daynight, "country": country}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_export(path):
    d = pd.read_csv(path, usecols=["lng", "lat", "frp", "confidence", "acq_datetime",
                                   "instrument", "source", "daynight"])
    d = d[d.instrument == "VIIRS"]
    return pd.DataFrame({
        "lat": d.lat, "lon": d.lng, "t": pd.to_datetime(d.acq_datetime, utc=True),
        "sat": d.source.str.extract(r"^(VIIRS_[A-Z0-9]+?)_(?:SP|NRT)$")[0].map(SAT_FROM_SOURCE),
        "frp": d.frp, "conf": d.confidence.astype(str).str[0].str.lower(),
        "daynight": d.daynight, "country": "DZA"})


# ---------- grids ----------
def global_cells(lat, lon):
    """Approximate 375 m cells used only for flare detection and clustering."""
    band = np.round(lat * 2) / 2
    gy = np.floor(lat * C.M_PER_DEG_LAT / C.CELL_M).astype(np.int64)
    gx = np.floor(lon * 111_320 * np.cos(np.radians(band)) / C.CELL_M).astype(np.int64)
    return gx, gy


def flare_mask(d):
    """True for detections in 750 m blocks that light up on many days across many years."""
    bx, by = d.gx // 2, d.gy // 2
    day = d.t.dt.floor("D")
    g = pd.DataFrame({"bx": bx, "by": by, "day": day, "yr": d.t.dt.year})
    s = g.groupby(["bx", "by"]).agg(ndays=("day", "nunique"), nyears=("yr", "nunique"))
    bad = s[(s.ndays >= C.FLARE_MIN_DAYS) & (s.nyears >= C.FLARE_MIN_YEARS)].index
    return pd.MultiIndex.from_arrays([bx, by]).isin(bad)


def cluster_fires(d):
    """Union-find: detections within CLUSTER_RADIUS_CELLS and CLUSTER_GAP_HOURS share a fire."""
    order = np.argsort(d.t.values, kind="stable")
    gx, gy = d.gx.values[order], d.gy.values[order]
    ts = d.t.values[order].astype("datetime64[s]").astype(np.int64)
    gap, R = C.CLUSTER_GAP_HOURS * 3600, C.CLUSTER_RADIUS_CELLS
    parent = np.arange(len(d))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i

    last = {}
    offs = [(dx, dy) for dx in range(-R, R + 1) for dy in range(-R, R + 1)]
    for i in range(len(d)):
        x, y, t = gx[i], gy[i], ts[i]
        for dx, dy in offs:
            hit = last.get((x + dx, y + dy))
            if hit is not None and t - hit[0] <= gap:
                a, b = find(i), find(hit[1])
                if a != b:
                    parent[a] = b
        last[(x, y)] = (t, i)
    roots = np.array([find(i) for i in range(len(d))])
    fire = np.empty(len(d), dtype=np.int64)
    fire[order] = pd.factorize(roots)[0]
    return fire


# ---------- per-fire grid, passes, pairs ----------
def build(d):
    fires, pass_rows, cell_rows, pair_rows = [], [], [], []
    for fid, g in d.groupby("fire_id", sort=False):
        lat_c = g.lat.mean()
        mlon = 111_320 * np.cos(np.radians(lat_c))
        m = C.GRID_MARGIN_CELLS
        lat0 = g.lat.min() - m * C.CELL_M / C.M_PER_DEG_LAT
        lon0 = g.lon.min() - m * C.CELL_M / mlon
        ix = np.floor((g.lon.values - lon0) * mlon / C.CELL_M).astype(int)
        iy = np.floor((g.lat.values - lat0) * C.M_PER_DEG_LAT / C.CELL_M).astype(int)
        nx, ny = ix.max() + m + 1, iy.max() + m + 1
        # passes: same satellite, detections less than 15 min apart
        g = g.assign(ix=ix, iy=iy).sort_values(["sat", "t"])
        new_pass = (g.sat != g.sat.shift()) | (g.t.diff() > pd.Timedelta("15min"))
        g["p"] = new_pass.cumsum()
        ptimes = g.groupby("p").t.median().sort_values()
        rank = {p: k for k, p in enumerate(ptimes.index)}
        g["pass_idx"] = g.p.map(rank)
        fires.append(dict(fire_id=fid, country=g.country.mode().iat[0], n_det=len(g),
                          t_first=g.t.min(), t_last=g.t.max(), lat_c=lat_c, lon_c=g.lon.mean(),
                          lat0=lat0, lon0=lon0, mlon=mlon, nx=nx, ny=ny, n_passes=len(ptimes),
                          max_frp=g.frp.max()))
        if len(ptimes) < 2:
            continue
        cells = (g.groupby(["pass_idx", "ix", "iy"]).frp.sum().reset_index())
        cells.insert(0, "fire_id", fid)
        cell_rows.append(cells)
        info = g.groupby("pass_idx").agg(t=("t", "median"), sat=("sat", "first"),
                                         daynight=("daynight", "first"), frp=("frp", "sum"))
        info.insert(0, "fire_id", fid)
        pass_rows.append(info.reset_index())
        burned = np.zeros((ny, nx), bool)
        by_pass = {k: v for k, v in cells.groupby("pass_idx")}
        struct = np.ones((2 * C.JITTER_CELLS + 1,) * 2, bool)
        for k in range(len(ptimes) - 1):
            cur = by_pass[k]
            burned[cur.iy.values, cur.ix.values] = True
            gap = (info.t.iat[k + 1] - info.t.iat[k]).total_seconds() / 60
            if gap < C.SHORT_PAIR[0] or gap > C.LONG_PAIR[1]:
                continue
            near = ndimage.binary_dilation(burned, struct) if C.JITTER_CELLS else burned
            nxt = by_pass[k + 1]
            n_new = int((~near[nxt.iy.values, nxt.ix.values]).sum())
            n_new_raw = int((~burned[nxt.iy.values, nxt.ix.values]).sum())
            pair_rows.append(dict(fire_id=fid, pass_idx=k, t1=info.t.iat[k], t2=info.t.iat[k + 1],
                                  gap_min=gap, kind="short" if gap <= C.SHORT_PAIR[1] else "long",
                                  sat1=info.sat.iat[k], sat2=info.sat.iat[k + 1],
                                  n_active=len(cur), n_burned=int(burned.sum()), n_new=n_new,
                                  n_new_raw=n_new_raw))
    cat = lambda rows: pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return pd.DataFrame(fires), cat(pass_rows), cat(cell_rows), pd.DataFrame(pair_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", help="Algeria Fire Map detections.csv to add (VIIRS rows only)")
    a = ap.parse_args()
    parts = [load_firms_dir()]
    if a.export:
        parts.append(load_export(a.export))
    d = pd.concat([p for p in parts if len(p)], ignore_index=True)
    print(f"loaded {len(d):,} VIIRS detections")
    d = d[d.conf != "l"]                                     # drop low-confidence
    d = d[~((d.country == "DZA") & (d.lat < C.DZA_MIN_LAT))]  # Sahara out
    d["key"] = (d.lat.round(4).astype(str) + d.lon.round(4).astype(str)
                + d.t.dt.strftime("%Y%m%d%H%M") + d.sat)
    d = d.drop_duplicates("key").drop(columns="key")         # export and API overlap
    d["gx"], d["gy"] = global_cells(d.lat.values, d.lon.values)
    flares = flare_mask(d)
    print(f"after low-confidence, Sahara and duplicate removal: {len(d):,}; flares removed: {flares.sum():,}")
    d = d[~flares].reset_index(drop=True)
    d["fire_id"] = cluster_fires(d)
    print(f"{d.fire_id.nunique():,} fires")
    fires, passes, cells, pairs = build(d)
    d.drop(columns=["gx", "gy"]).to_parquet(C.OUT / "detections.parquet")
    fires.to_parquet(C.OUT / "fires.parquet"); passes.to_parquet(C.OUT / "passes.parquet")
    cells.to_parquet(C.OUT / "pass_cells.parquet"); pairs.to_parquet(C.OUT / "pairs.parquet")
    s = pairs[pairs.kind == "short"]; l = pairs[pairs.kind == "long"]
    print(f"pairs 20-120 min: {len(s):,} (fire grew by 5+ cells in {(s.n_new >= 5).sum():,}; "
          f"{(s.n_new_raw >= 5).sum():,} counting cells right next to the old fire)")
    print(f"pairs 2-16 h:     {len(l):,} (fire grew by 5+ cells in {(l.n_new >= 5).sum():,})")
    print(pairs.groupby(fires.set_index("fire_id").country.reindex(pairs.fire_id).values)
               .n_new.agg(["size", "sum"]).rename(columns={"size": "pairs", "sum": "new_cells"}))


if __name__ == "__main__":
    main()
