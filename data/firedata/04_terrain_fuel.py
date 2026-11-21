"""Step 4: terrain and fuel on each fire's 375 m grid.

Elevation from Copernicus DEM 90 m, fuel from ESA WorldCover 10 m (2021). Both are public
cloud-optimised GeoTIFFs: only the window around each fire is read, nothing is downloaded whole.
    python 04_terrain_fuel.py
Output: data/cache_static/<fire_id>.npz with elev, elev_std, slope, aspect and one fraction
grid per fuel class (tree, shrub, grass, crop, built, bare, water).
"""
import math
import numpy as np, pandas as pd, rasterio
from rasterio.windows import from_bounds
from rasterio.errors import RasterioIOError
import config as C

ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
           GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2")


def tile_url(template, lat, lon):
    return template.format(ns="N" if lat >= 0 else "S", lat=abs(lat),
                           ew="E" if lon >= 0 else "W", lon=abs(lon))


def grid_bounds(f):
    lat1 = f.lat0 + f.ny * C.CELL_M / C.M_PER_DEG_LAT
    lon1 = f.lon0 + f.nx * C.CELL_M / f.mlon
    return f.lon0, f.lat0, lon1, lat1


def accumulate(url, f, bounds, decim, on_pixels):
    """Read the part of one tile inside the fire grid; hand pixels + cell index to on_pixels."""
    w, s, e, n = bounds
    try:
        src = rasterio.open(url)
    except RasterioIOError:
        return False                       # no tile (sea) or not reachable
    with src:
        tb = src.bounds
        ww, ss, ee, nn = max(w, tb.left), max(s, tb.bottom), min(e, tb.right), min(n, tb.top)
        if ww >= ee or ss >= nn:
            return True
        win = from_bounds(ww, ss, ee, nn, src.transform).round_offsets().round_lengths()
        h, wd = max(1, int(win.height // decim)), max(1, int(win.width // decim))
        a = src.read(1, window=win, out_shape=(h, wd))
        tr = src.window_transform(win) * rasterio.Affine.scale(win.width / wd, win.height / h)
    lons = tr.c + (np.arange(wd) + 0.5) * tr.a
    lats = tr.f + (np.arange(h) + 0.5) * tr.e
    ix = np.floor((lons - f.lon0) * f.mlon / C.CELL_M).astype(int)
    iy = np.floor((lats - f.lat0) * C.M_PER_DEG_LAT / C.CELL_M).astype(int)
    okx, oky = (ix >= 0) & (ix < f.nx), (iy >= 0) & (iy < f.ny)
    a = a[np.ix_(oky, okx)]
    idx = (iy[oky][:, None] * f.nx + ix[okx][None, :]).ravel()
    on_pixels(a.ravel(), idx)
    return True


def tiles(bounds, step):
    w, s, e, n = bounds
    for la in range(math.floor(s / step) * step, math.ceil(n / step) * step, step):
        for lo in range(math.floor(w / step) * step, math.ceil(e / step) * step, step):
            yield la, lo


def static_for_fire(f, dem_url=C.DEM_URL, wc_url=C.WORLDCOVER_URL):
    size = int(f.nx * f.ny)
    b = grid_bounds(f)
    s1, s2, cnt = np.zeros(size), np.zeros(size), np.zeros(size)

    def dem_px(v, idx):
        ok = np.isfinite(v) & (v > -1000)
        np.add.at(s1, idx[ok], v[ok]); np.add.at(s2, idx[ok], v[ok] ** 2); np.add.at(cnt, idx[ok], 1)

    for la, lo in tiles(b, 1):
        accumulate(tile_url(dem_url, la, lo), f, b, 1, dem_px)
    elev = np.where(cnt > 0, s1 / np.maximum(cnt, 1), 0.0)       # missing tile = sea = 0 m
    elev_std = np.sqrt(np.maximum(s2 / np.maximum(cnt, 1) - elev ** 2, 0))
    fuel = {k: np.zeros(size) for k in C.FUEL_CLASSES}
    wcnt = np.zeros(size)

    def wc_px(v, idx):
        np.add.at(wcnt, idx, 1)
        for k in fuel:
            m = v == k
            np.add.at(fuel[k], idx[m], 1)

    for la, lo in tiles(b, 3):
        accumulate(tile_url(wc_url, la, lo), f, b, 3, wc_px)       # read at ~30 m
    shape = (int(f.ny), int(f.nx))
    elev2 = elev.reshape(shape)
    dzdy, dzdx = np.gradient(elev2, C.CELL_M)                       # rows go south -> north
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    aspect = (np.degrees(np.arctan2(-dzdx, -dzdy)) + 360) % 360    # direction the slope faces
    out = dict(elev=elev2.astype(np.float32), elev_std=elev_std.reshape(shape).astype(np.float32),
               slope=slope.astype(np.float32), aspect=aspect.astype(np.float32))
    for k, name in C.FUEL_CLASSES.items():
        frac = np.where(wcnt > 0, fuel[k] / np.maximum(wcnt, 1), 1.0 if name == "water" else 0.0)
        out[f"fuel_{name}"] = frac.reshape(shape).astype(np.float32)
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", default="0/1", help="i/n: this process does every n-th fire (run n at once)")
    a = ap.parse_args()
    i, n_sh = map(int, a.shard.split("/"))
    fires = pd.read_parquet(C.OUT / "fires.parquet")
    pairs = pd.read_parquet(C.OUT / "pairs.parquet")
    order = C.growing_fires(fires.set_index("fire_id"), pairs)  # same fires as step 3
    need = fires.set_index("fire_id").loc[order.index].reset_index()
    need = need.iloc[i::n_sh]
    todo = [r for r in need.itertuples() if not (C.CACHE_STATIC / f"{r.fire_id}.npz").exists()]
    print(f"{len(need):,} fires to cover, {len(todo):,} still need terrain and fuel")
    with rasterio.Env(**ENV):
        for n, f in enumerate(todo, 1):
            np.savez_compressed(C.CACHE_STATIC / f"{f.fire_id}.npz", **static_for_fire(f))
            if n % 100 == 0:
                print(f"{n}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()
