"""Terrain and fuel at 375 m for all of northern Algeria -> data/out/static_375m.npz (issue #17).

The API cannot read DEM / WorldCover tiles at request time, so this precomputes every cell once.
Same definitions as step 4 (data/firedata/04_terrain_fuel.py, imported, not copied): Copernicus DEM
90 m and ESA WorldCover 2021 read remotely, averaged onto 375 m cells, then slope and aspect.

Grid: northern Algeria is treated as one big "fire grid" in the sense of 02_clean.py: lat0/lon0 =
the south-west corner of config.yaml -> static_raster.bbox, mlon = 111,320 * cos(centre latitude),
cells of CELL_M metres, same floor() snap. It is filled in chunks (each one a small grid with a
2-cell halo, so cells at chunk edges are computed like interior ones); every chunk is cached, so the
run is resumable and can be sharded like step 4. Fuel shares match step 4 up to its 1-in-3 WorldCover
sampling, which starts at each read window's corner. Only an HTTP 404 tile is sea; any other failed read is
retried, then the chunk is skipped (never saved as sea) and the file is not written until a rerun
fills it.
    .venv/bin/python data/build_static_raster.py                 # whole bbox, resumable
    .venv/bin/python data/build_static_raster.py --shard 0/4     # run 4 of these at once
    .venv/bin/python data/build_static_raster.py --bbox 3.9 36.4 4.4 36.9 --out /tmp/tizi.npz
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

REPO = Path(__file__).resolve().parents[1]
FIREDATA = REPO / "data" / "firedata"
sys.path.insert(0, str(REPO))
HALO = 2   # cells read around each chunk: the outermost one can miss an edge pixel, the next feeds the slope


def load_step4():
    """Import data/firedata/04_terrain_fuel.py (and its config.py) as a module."""
    os.environ.setdefault("FIREDATA_DIR", str(REPO / "data"))     # like `make data`
    if str(FIREDATA) not in sys.path:
        sys.path.insert(0, str(FIREDATA))
    if "terrain_fuel_04" in sys.modules:
        return sys.modules["terrain_fuel_04"]
    spec = importlib.util.spec_from_file_location("terrain_fuel_04", FIREDATA / "04_terrain_fuel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["terrain_fuel_04"] = mod
    return mod


def national_grid(bbox, cell_m, m_per_deg_lat):
    w, s, e, n = map(float, bbox)
    mlon = 111_320 * np.cos(np.radians((s + n) / 2))              # as 02_clean.py, at the grid centre
    nx = math.ceil((e - w) * mlon / cell_m)
    ny = math.ceil((n - s) * m_per_deg_lat / cell_m)
    return SimpleNamespace(lat0=s, lon0=w, mlon=float(mlon), nx=nx, ny=ny,
                           cell_m=float(cell_m), m_per_deg_lat=float(m_per_deg_lat))


def chunks(g, size):
    """(name, iy0, ix0, ny, nx) covering the grid."""
    for iy0 in range(0, g.ny, size):
        for ix0 in range(0, g.nx, size):
            yield f"{iy0:05d}_{ix0:05d}", iy0, ix0, min(size, g.ny - iy0), min(size, g.nx - ix0)


def chunk_grid(g, iy0, ix0, ny, nx):
    """The chunk (plus halo) as a fire-like grid that 04's static_for_fire understands."""
    return SimpleNamespace(fire_id=f"chunk {iy0}_{ix0}",
                           lat0=g.lat0 + (iy0 - HALO) * g.cell_m / g.m_per_deg_lat,
                           lon0=g.lon0 + (ix0 - HALO) * g.cell_m / g.mlon,
                           mlon=g.mlon, nx=nx + 2 * HALO, ny=ny + 2 * HALO)


def build_chunk(t4, g, iy0, ix0, ny, nx, dem_url, wc_url):
    st = t4.static_for_fire(chunk_grid(g, iy0, ix0, ny, nx), dem_url, wc_url, require_land=False)
    return {k: v[HALO:-HALO, HALO:-HALO] for k, v in st.items()}


def grid_key(g, size, dem_url, wc_url):
    s = f"{g.lat0:.9f} {g.lon0:.9f} {g.mlon:.6f} {g.nx} {g.ny} {g.cell_m} {size} {dem_url} {wc_url}"
    return hashlib.sha1(s.encode()).hexdigest()[:10]


def assemble(g, names, cache, out, dem_url, wc_url):
    first = dict(np.load(cache / f"{names[0][0]}.npz"))
    layers = {k: np.full((g.ny, g.nx), np.nan, np.float32) for k in first}
    for name, iy0, ix0, ny, nx in names:
        with np.load(cache / f"{name}.npz") as z:
            for k in layers:
                layers[k][iy0:iy0 + ny, ix0:ix0 + nx] = z[k]
    assert not any(np.isnan(a).any() for a in layers.values()), "a chunk left a hole"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp.npz")
    np.savez_compressed(tmp, **layers, lat0=g.lat0, lon0=g.lon0, mlon=g.mlon, cell_m=g.cell_m,
                        m_per_deg_lat=g.m_per_deg_lat, nx=g.nx, ny=g.ny,
                        dem_url=dem_url, wc_url=wc_url, built=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    os.replace(tmp, out)
    land = (layers["fuel_water"] < 1).mean()
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB): {g.ny} x {g.nx} cells, {land:.0%} with land; "
          f"elev {layers['elev'].min():.0f}..{layers['elev'].max():.0f} m")


def run(bbox, out, cache_dir, chunk_cells=128, shard=(0, 1), dem_url=None, wc_url=None,
        attempts=3, retry_wait_s=5.0):
    """Build (or resume) the raster. Returns True once `out` is written."""
    import rasterio
    from rasterio.errors import RasterioIOError

    t4 = load_step4()
    C = t4.C
    from core.static_raster import FUEL_NAMES
    assert tuple(C.FUEL_CLASSES.values()) == FUEL_NAMES, "core.static_raster.FUEL_NAMES is out of date"
    dem_url, wc_url = dem_url or C.DEM_URL, wc_url or C.WORLDCOVER_URL
    g = national_grid(bbox, C.CELL_M, C.M_PER_DEG_LAT)
    cache = Path(cache_dir) / grid_key(g, chunk_cells, dem_url, wc_url)
    cache.mkdir(parents=True, exist_ok=True)
    names = list(chunks(g, chunk_cells))
    i, n_sh = shard
    todo = [c for c in names[i::n_sh] if not (cache / f"{c[0]}.npz").exists()]
    print(f"grid {g.ny} x {g.nx} cells ({g.ny * g.nx:,}), {len(names)} chunks of {chunk_cells}; "
          f"shard {i}/{n_sh}: {len(todo)} still to do. Cache: {cache}", flush=True)
    t0 = time.time()
    with rasterio.Env(**t4.ENV):
        for n, (name, iy0, ix0, ny, nx) in enumerate(todo, 1):
            for attempt in range(attempts):              # remote tile reads fail now and then
                try:
                    st = build_chunk(t4, g, iy0, ix0, ny, nx, dem_url, wc_url)
                    break
                except RasterioIOError as e:
                    print(f"  chunk {name}: {str(e)[:120]} (attempt {attempt + 1})", flush=True)
                    if attempt + 1 < attempts:
                        time.sleep(retry_wait_s)
            else:
                print(f"  skipped chunk {name}; rerun later", flush=True)
                continue
            tmp = cache / f"{name}.tmp.npz"
            np.savez_compressed(tmp, **st)
            os.replace(tmp, cache / f"{name}.npz")
            el = time.time() - t0
            print(f"{n}/{len(todo)} chunks, {el / 60:.1f} min, ~{el / n * (len(todo) - n) / 60:.0f} min left",
                  flush=True)
    missing = [c for c in names if not (cache / f"{c[0]}.npz").exists()]
    if missing:
        print(f"{len(missing)} chunks missing (other shards or failed reads); rerun to finish, "
              f"{out} not written", flush=True)
        return False
    assemble(g, names, cache, Path(out), dem_url, wc_url)
    return True


def main():
    from core.config import load_config, repo_path
    cfg = load_config()
    sr = cfg["static_raster"]
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"), default=sr["bbox"])
    ap.add_argument("--out", default=str(repo_path(cfg["paths"]["static_raster"])))
    ap.add_argument("--cache", default=str(repo_path(sr["cache_dir"])))
    ap.add_argument("--chunk-cells", type=int, default=sr["chunk_cells"])
    ap.add_argument("--shard", default="0/1", help="i/n: this process does every n-th chunk (run n at once)")
    a = ap.parse_args()
    ok = run(a.bbox, a.out, a.cache, a.chunk_cells, tuple(map(int, a.shard.split("/"))))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
