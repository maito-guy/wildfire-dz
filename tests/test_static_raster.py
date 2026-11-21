"""Issue #17: the national terrain/fuel raster and its lookup. Offline only (C-10): tiles are tiny
GeoTIFFs written to tmp_path, and the HEAD request step 4 makes for a missing tile is monkeypatched."""
import importlib.util

import numpy as np
import pytest

from core import static_raster as sr
from core.config import ROOT, load_config

# ---------- lookup only (no rasterio needed) ----------


def fake_raster(tmp_path, ny=4, nx=5):
    rng = np.random.default_rng(0)
    layers = {k: rng.random((ny, nx)).astype(np.float32) * (360 if k == "aspect" else 1) for k in sr.LAYERS}
    p = tmp_path / "r.npz"
    np.savez_compressed(p, **layers, lat0=36.0, lon0=4.0, mlon=90_000.0, cell_m=375.0, m_per_deg_lat=110_574.0)
    return p, layers


def test_lookup_cell_snap_and_columns(tmp_path):
    p, layers = fake_raster(tmp_path)
    r = sr.load(p)
    assert r.shape == (4, 5)
    lat, lon = r.cell_center(2, 3)
    got = r.lookup(float(lat), float(lon))
    assert list(got) == list(sr.COLUMNS)
    assert got["elev"] == pytest.approx(float(layers["elev"][2, 3]))
    assert got["fuel_water"] == pytest.approx(float(layers["fuel_water"][2, 3]))
    a = layers["aspect"][2, 3]
    assert got["aspect_sin"] == float(np.sin(np.radians(a)))       # float32 maths, like 05_build_table.py
    # the cell's south-west corner belongs to it, the next cell's corner does not (same floor() as 04/05)
    assert r.lookup(36.0 + 2 * 375 / 110_574.0 + 1e-9, 4.0 + 3 * 375 / 90_000.0 + 1e-9)["elev"] == got["elev"]
    assert r.lookup(35.999, 4.1) is None and r.lookup(36.001, 3.999) is None
    assert r.lookup(36.0 + 4 * 375 / 110_574.0 + 1e-6, 4.001) is None
    assert r.lookup(float("nan"), 4.001) is None


def test_lookup_many_matches_lookup(tmp_path):
    p, _ = fake_raster(tmp_path)
    r = sr.load(p)
    lats = np.array([36.001, 36.008, 35.0, 36.01])
    lons = np.array([4.001, 4.012, 4.001, 4.02])
    df = r.lookup_many(lats, lons)
    assert list(df.columns) == list(sr.COLUMNS) and len(df) == 4
    for i in range(4):
        one = r.lookup(lats[i], lons[i])
        if one is None:
            assert df.iloc[i].isna().all()
        else:
            assert df.iloc[i].to_dict() == pytest.approx(one)


def test_load_rejects_incomplete_file(tmp_path):
    p = tmp_path / "bad.npz"
    np.savez(p, elev=np.zeros((2, 2)))
    with pytest.raises(ValueError, match="missing"):
        sr.load(p)


def test_config_registers_the_file():
    c = load_config()
    assert c["paths"]["static_raster"] == "data/out/static_375m.npz"
    w, s, e, n = c["static_raster"]["bbox"]
    assert s == c["scope"]["lat_min"] and w < e and s < n


def test_columns_match_training_table_names():
    """The names 05_build_table.py writes for terrain and fuel (built by core/features.py since #18)."""
    from core import features
    st = {k: np.zeros((2, 2), np.float32) for k in sr.LAYERS}
    assert tuple(features.fire_npz_terrain(st)(np.array([0]), np.array([0]))) == sr.COLUMNS
    cfg = (ROOT / "data" / "firedata" / "config.py").read_text()
    for n in sr.FUEL_NAMES:
        assert f'"{n}"' in cfg


# ---------- build from fake tiles (needs rasterio, like step 4) ----------

DEG = 1 / 2400   # fake tile resolution (~46 m): coarse, but several pixels per 375 m cell


def write_tile(path, west, north, arr, dtype):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_origin(west, north, DEG, DEG)) as d:
        d.write(arr.astype(dtype), 1)


@pytest.fixture
def tiles(tmp_path):
    """DEM tile N36E004 (a tilted, bumpy plane) and WorldCover tile N36E003 (bands of classes), both
    covering only 36.0-36.5 N, 4.0-4.5 E. Every other tile is missing on disk."""
    pytest.importorskip("rasterio")
    n = int(0.5 / DEG)
    lat = 36.5 - (np.arange(n) + 0.5) * DEG
    lon = 4.0 + (np.arange(n) + 0.5) * DEG
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    dem = 200 + 4000 * (la - 36) + 1500 * (lo - 4) + 30 * np.sin(la * 900) * np.cos(lo * 700)
    classes = np.array([10, 20, 30, 40, 50, 60, 80, 90])
    wc = classes[((la * 50).astype(int) + (lo * 40).astype(int)) % len(classes)]   # ~2 km blocks
    d = tmp_path / "tiles"
    d.mkdir()
    write_tile(d / "dem_N36_E004.tif", 4.0, 36.5, dem, "float32")
    write_tile(d / "wc_N36E003.tif", 4.0, 36.5, wc, "uint8")
    return str(d / "dem_{ns}{lat:02d}_{ew}{lon:03d}.tif"), str(d / "wc_{ns}{lat:02d}{ew}{lon:03d}.tif")


def assert_fuel_close(got, want, name):
    """Step 4 reads WorldCover at 1 pixel in 3, counted from the start of its read window, so which
    pixels a cell samples depends on where the grid starts: cells inside one land-cover block agree
    exactly, cells on a block edge differ by sampling noise only."""
    assert np.mean(np.isclose(got, want, atol=1e-6)) > 0.75, name
    assert np.mean(np.abs(got - want)) < 0.05, name


def load_builder():
    spec = importlib.util.spec_from_file_location("build_static_raster", ROOT / "data" / "build_static_raster.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def builder(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREDATA_DIR", str(tmp_path / "firedata"))   # step 4's config makes folders here
    b = load_builder()
    t4 = b.load_step4()
    calls = []

    def head(url, **kw):              # what the tile server says about a missing tile
        calls.append(url)
        return head.reply(url)
    head.reply = lambda url: type("R", (), {"status_code": 404})()
    monkeypatch.setattr(t4.requests, "head", head)
    return b, t4, head, calls


def test_build_matches_step4(builder, tiles, tmp_path):
    b, t4, _, _ = builder
    dem, wc = tiles
    bbox = [4.05, 36.05, 4.35, 36.3]
    out = tmp_path / "static.npz"
    assert b.run(bbox, out, tmp_path / "cache", chunk_cells=24, dem_url=dem, wc_url=wc, retry_wait_s=0)
    r = sr.load(out)
    g = b.national_grid(bbox, t4.C.CELL_M, t4.C.M_PER_DEG_LAT)
    assert r.shape == (g.ny, g.nx) and g.nx > 48 and g.ny > 48      # several chunks each way
    # step 4 on the whole grid at once (same halo) gives the same numbers as the chunked build
    ref = b.build_chunk(t4, g, 0, 0, g.ny, g.nx, dem, wc)
    for k in ("elev", "elev_std", "slope", "aspect"):                        # DEM read at full resolution
        np.testing.assert_allclose(r.layers[k], ref[k], rtol=1e-6, atol=1e-4, err_msg=k)
    for k in (f"fuel_{n}" for n in sr.FUEL_NAMES):
        assert_fuel_close(r.layers[k], ref[k], k)
    # and step 4 on a "fire" grid lying on the raster's cells gives what the lookup returns
    fire = b.chunk_grid(g, 10, 20, 15, 12)
    st = t4.static_for_fire(fire, dem, wc)
    iy, ix = np.mgrid[0:fire.ny, 0:fire.nx]
    lat = fire.lat0 + (iy + 0.5) * t4.C.CELL_M / t4.C.M_PER_DEG_LAT        # 05's cell centre
    lon = fire.lon0 + (ix + 0.5) * t4.C.CELL_M / fire.mlon
    df = r.lookup_many(lat.ravel(), lon.ravel())
    # step 4's own grid edge: the outer ring can miss a pixel of the read window, the next ring's slope
    # sees it. Training rows never sit there (GRID_MARGIN_CELLS = 16 around each fire).
    ring1, inner = (slice(1, -1), slice(1, -1)), (slice(2, -2), slice(2, -2))
    for k in ("elev", "elev_std"):
        np.testing.assert_allclose(df[k].to_numpy().reshape(lat.shape)[ring1], st[k][ring1], rtol=1e-6, atol=1e-4,
                                   err_msg=k)
    for k in (f"fuel_{n}" for n in sr.FUEL_NAMES):
        assert_fuel_close(df[k].to_numpy().reshape(lat.shape), st[k], k)
    np.testing.assert_allclose(df.slope.to_numpy().reshape(lat.shape)[inner], st["slope"][inner], atol=1e-4)
    np.testing.assert_allclose(df.aspect_sin.to_numpy().reshape(lat.shape)[inner],
                               np.sin(np.radians(st["aspect"]))[inner], atol=1e-4)
    # sanity: the fake plane rises to the north-east, so the slope faces south-west
    assert 180 < float(np.median(r.layers["aspect"])) < 270
    assert r.layers["fuel_water"].mean() < 0.3 and r.layers["elev"].min() > 100


def test_sea_only_from_404(builder, tiles, tmp_path):
    """Cells west of 4.0 E have no DEM tile (404 = sea): 0 m, all water. Rerunning reuses the cache."""
    b, _, _, calls = builder
    dem, wc = tiles
    out = tmp_path / "static.npz"
    assert b.run([3.9, 36.1, 4.1, 36.2], out, tmp_path / "cache", chunk_cells=16, dem_url=dem, wc_url=wc,
                 retry_wait_s=0)
    assert any("E003" in u for u in calls)
    r = sr.load(out)
    sea, land = r.lookup(36.15, 3.95), r.lookup(36.15, 4.05)
    assert sea["elev"] == 0 and sea["fuel_water"] == 1
    assert land["elev"] > 100 and land["fuel_water"] < 1
    calls.clear()
    assert b.run([3.9, 36.1, 4.1, 36.2], out, tmp_path / "cache", chunk_cells=16, dem_url=dem, wc_url=wc)
    assert calls == []                                                       # nothing re-read


@pytest.mark.parametrize("failure", ["connection", "503"])
def test_network_failure_is_never_sea(builder, tiles, tmp_path, failure):
    b, t4, head, _ = builder
    dem, wc = tiles

    def broken(url):
        if failure == "connection":
            raise t4.requests.ConnectionError("no route to host")
        return type("R", (), {"status_code": 503})()
    head.reply = broken
    out, cache = tmp_path / "static.npz", tmp_path / "cache"
    bbox = [3.9, 36.1, 4.1, 36.2]
    assert not b.run(bbox, out, cache, chunk_cells=16, dem_url=dem, wc_url=wc, retry_wait_s=0)
    assert not out.exists()
    g = b.national_grid(bbox, t4.C.CELL_M, t4.C.M_PER_DEG_LAT)
    saved = {p.stem for p in (cache / b.grid_key(g, 16, dem, wc)).glob("*.npz")}
    sea_chunks = {c[0] for c in b.chunks(g, 16) if g.lon0 + (c[2] + c[4] + 1) * g.cell_m / g.mlon < 4.0}
    assert sea_chunks and not (saved & sea_chunks)          # chunks touching the missing tile were not saved
    head.reply = lambda url: type("R", (), {"status_code": 404})()           # network back: rerun finishes
    assert b.run(bbox, out, cache, chunk_cells=16, dem_url=dem, wc_url=wc, retry_wait_s=0)
    assert sr.load(out).lookup(36.15, 3.95)["fuel_water"] == 1
