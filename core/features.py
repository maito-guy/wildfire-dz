"""One feature builder for training (data/firedata/05_build_table.py) and prediction (the API), issue #18.

Model C sees one row per candidate cell around a fire at a satellite pass. Every column is built here, so
training rows and prediction rows cannot drift apart (SPEC §4.3):

    grid    = fire_grid(lat, lon)                      # the fire's local 375 m grid (as step 2)
    state   = fire_state(grid, cells_by_pass, k)       # burned so far, burning now, FRP now
    wx      = weather_at(prepare_weather(hourly), t1)  # weather at the pass + mean wind of the next 2 h
    rows    = cell_features(grid, state, iy, ix, ...)  # one row per cell, train.parquet column names

Terrain and fuel come from a `terrain(iy, ix)` function: `fire_npz_terrain` reads a fire's step 4 file
(how train.parquet was first built), `raster_terrain` reads `core/static_raster.py` (the national file the
API uses; Q-05: training uses it too). For the API, `rows_from_detections` does all of the above from raw
detections. Grid sizes and radii are in config.yaml -> features (the pipeline's config.py must match).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import ndimage

from core.static_raster import FUEL_NAMES, StaticRaster

M_PER_DEG_LAT = 110_574.0
FUEL = [f"fuel_{n}" for n in FUEL_NAMES]
WEATHER_NOW = ["temperature_2m", "relative_humidity_2m", "vapour_pressure_deficit", "wind_speed_10m",
               "wind_gusts_10m", "soil_moisture_0_to_7cm", "hours_since_rain", "rain_24h"]
HOURLY = ["temperature_2m", "relative_humidity_2m", "vapour_pressure_deficit", "wind_speed_10m",
          "wind_direction_10m", "wind_gusts_10m", "soil_moisture_0_to_7cm", "precipitation"]  # Open-Meteo names

Terrain = Callable[[np.ndarray, np.ndarray], dict]


@dataclass(frozen=True)
class FireGrid:
    """A fire's local grid: cell (iy, ix) covers lat0 + [iy, iy+1) * cell_m / M_PER_DEG_LAT, same for lon."""
    lat0: float
    lon0: float
    mlon: float               # metres per degree of longitude at the fire's mean latitude
    nx: int
    ny: int
    lon_c: float              # mean longitude of the detections (local solar hour)
    cell_m: float = 375.0

    def index(self, lat, lon):
        ix = np.floor((np.asarray(lon, float) - self.lon0) * self.mlon / self.cell_m).astype(int)
        iy = np.floor((np.asarray(lat, float) - self.lat0) * M_PER_DEG_LAT / self.cell_m).astype(int)
        return iy, ix

    def center(self, iy, ix):
        lat = self.lat0 + (np.asarray(iy) + 0.5) * self.cell_m / M_PER_DEG_LAT
        lon = self.lon0 + (np.asarray(ix) + 0.5) * self.cell_m / self.mlon
        return lat, lon


def fire_grid(lat, lon, margin_cells: int = 16, cell_m: float = 375.0) -> FireGrid:
    """Same grid as data/firedata/02_clean.py build(): the detections' box plus a margin."""
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    mlon = 111_320 * np.cos(np.radians(lat.mean()))
    lat0 = lat.min() - margin_cells * cell_m / M_PER_DEG_LAT
    lon0 = lon.min() - margin_cells * cell_m / mlon
    g = FireGrid(lat0, lon0, mlon, 0, 0, float(lon.mean()), cell_m)
    iy, ix = g.index(lat, lon)
    return FireGrid(lat0, lon0, mlon, int(ix.max() + margin_cells + 1), int(iy.max() + margin_cells + 1),
                    float(lon.mean()), cell_m)


def assign_passes(t: pd.Series, sat: pd.Series, split_min: float = 15) -> tuple[np.ndarray, pd.Series]:
    """Pass index per detection (0 = first pass) and each pass's median time, as step 2:
    a new pass starts when the satellite changes or detections are more than split_min apart."""
    d = pd.DataFrame({"t": pd.to_datetime(t, utc=True).to_numpy(), "sat": np.asarray(sat)})
    d = d.sort_values(["sat", "t"])
    new = (d.sat != d.sat.shift()) | (d.t.diff() > pd.Timedelta(minutes=split_min))
    p = new.cumsum()
    times = d.groupby(p).t.median().sort_values()
    rank = {q: k for k, q in enumerate(times.index)}
    idx = p.map(rank).reindex(range(len(d))).to_numpy()
    return idx, pd.Series(times.to_numpy(), index=range(len(times)))


@dataclass
class FireState:
    burned: np.ndarray        # bool (ny, nx): burning at this pass or any earlier one
    active: np.ndarray        # bool: burning at this pass
    frp_now: np.ndarray       # FRP (MW) of this pass's cells
    n_active: int
    n_burned: int
    frp_sum: float            # total FRP of this pass


def fire_state(grid: FireGrid, cells: dict[int, pd.DataFrame], k: int) -> FireState:
    """cells: pass index -> DataFrame(ix, iy, frp), one row per cell (step 2's pass_cells)."""
    shape = (grid.ny, grid.nx)
    burned = np.zeros(shape, bool)
    for j, c in cells.items():
        if j <= k:
            burned[c.iy.values, c.ix.values] = True
    cur = cells[k]
    active = np.zeros(shape, bool)
    active[cur.iy.values, cur.ix.values] = True
    frp_now = np.zeros(shape)
    frp_now[cur.iy.values, cur.ix.values] = cur.frp.values
    return FireState(burned, active, frp_now, int(len(cur)), int(burned.sum()), float(cur.frp.sum()))


def near_mask(burned: np.ndarray, jitter_cells: int = 1) -> np.ndarray:
    """Cells next to the burned area: never a label, never a candidate (geolocation jitter)."""
    if not jitter_cells:
        return burned
    return ndimage.binary_dilation(burned, np.ones((2 * jitter_cells + 1,) * 2, bool))


def candidates(state: FireState, radius_cells: int = 16, jitter_cells: int = 1):
    """Every cell within radius_cells of the burned area, minus the burned area and its jitter ring."""
    near = near_mask(state.burned, jitter_cells)
    d_burn = ndimage.distance_transform_edt(~state.burned)
    return np.nonzero((d_burn <= radius_cells) & ~near)


def prepare_weather(hourly: pd.DataFrame, lookback_days: int = 10) -> pd.DataFrame:
    """Hourly weather (Open-Meteo names, UTC `time` column or index) + hours_since_rain and rain_24h."""
    w = hourly.copy()
    if "time" in w:
        w["time"] = pd.to_datetime(w.time, utc=True)
        w = w.set_index("time")
    w = w.sort_index()
    rain = w.precipitation.fillna(0) >= 1.0
    last_rain = w.index.to_series().where(rain).ffill()
    w["hours_since_rain"] = (w.index.to_series() - last_rain).dt.total_seconds() / 3600
    w["hours_since_rain"] = w.hours_since_rain.fillna(lookback_days * 24)
    w["rain_24h"] = w.precipitation.fillna(0).rolling(24, min_periods=1).sum()
    return w


def weather_at(w: pd.DataFrame, t) -> dict | None:
    """Weather at the hour of t, and the vector-mean wind of that hour and the next 2 (wind_speed_2h)."""
    h = pd.Timestamp(t).floor("h")
    if h not in w.index:
        return None
    now = w.loc[h]
    nxt = w.loc[h + pd.Timedelta("1h"): h + pd.Timedelta("2h")]
    out = {k: now[k] for k in WEATHER_NOW}
    out["wind_dir_now"] = now.wind_direction_10m
    ws = pd.concat([now.to_frame().T, nxt])        # directions can't be averaged as numbers: use vectors
    rad = np.radians(ws.wind_direction_10m.astype(float))
    u = (ws.wind_speed_10m * np.sin(rad)).mean()
    v = (ws.wind_speed_10m * np.cos(rad)).mean()
    out["wind_speed_2h"] = float(np.hypot(u, v))
    out["wind_from_2h"] = float((np.degrees(np.arctan2(u, v)) + 360) % 360)
    out["gust_max_2h"] = float(ws.wind_gusts_10m.max())
    return out


def fire_npz_terrain(st: dict) -> Terrain:
    """Terrain from a fire's step 4 file (arrays on the fire's own grid)."""
    def terrain(iy, ix):
        return {"elev": st["elev"][iy, ix], "elev_std": st["elev_std"][iy, ix], "slope": st["slope"][iy, ix],
                "aspect_sin": np.sin(np.radians(st["aspect"][iy, ix])),
                "aspect_cos": np.cos(np.radians(st["aspect"][iy, ix])),
                **{k: st[k][iy, ix] for k in FUEL}}
    return terrain


def raster_terrain(raster: StaticRaster, grid: FireGrid) -> Terrain:
    """Terrain from the national 375 m raster at each fire-grid cell's centre (Q-05)."""
    def terrain(iy, ix):
        lat, lon = grid.center(iy, ix)
        t = raster.lookup_many(lat, lon)
        return {k: t[k].to_numpy() for k in t.columns}
    return terrain


def cell_features(grid: FireGrid, state: FireState, iy, ix, *, pass_idx: int, t1, wx: dict,
                  terrain: Terrain, meta: dict | None = None, extra: dict | None = None) -> pd.DataFrame:
    """One row per cell (iy, ix), with train.parquet's columns in train.parquet's order:
    meta (fire_id, country, pass_idx, t1, kind, gap_min, sat1, sat2) | ix iy lat lon | extra (label, hop,
    weight) | fire geometry | terrain and fuel | weather."""
    iy = np.asarray(iy)
    ix = np.asarray(ix)
    t1 = pd.Timestamp(t1)
    d_burn = ndimage.distance_transform_edt(~state.burned)
    d_act, (ay, ax) = ndimage.distance_transform_edt(~state.active, return_indices=True)
    ny_, nx_ = ay[iy, ix], ax[iy, ix]
    # direction from the nearest burning cell to this cell, compared with where the wind blows to
    dy = (iy - ny_).astype(float)
    dx = (ix - nx_).astype(float)
    bearing = np.degrees(np.arctan2(dx, dy)) % 360
    wind_to = (wx["wind_from_2h"] + 180) % 360
    dist_m = np.hypot(dx, dy) * grid.cell_m
    ter = terrain(iy, ix)
    rise = ter["elev"] - terrain(ny_, nx_)["elev"]
    lat, lon = grid.center(iy, ix)
    cols = {**(meta or {}), "ix": ix, "iy": iy, "lat": lat, "lon": lon, **(extra or {}),
            "dist_burned_m": d_burn[iy, ix] * grid.cell_m, "dist_active_m": d_act[iy, ix] * grid.cell_m,
            "downwind_cos": np.cos(np.radians(bearing - wind_to)),
            "bearing_deg": bearing,        # fire -> cell direction, so downwind_cos can be redone for another wind
            "uphill_grade": np.where(dist_m > 0, rise / np.maximum(dist_m, 1), 0.0),
            "n_active": state.n_active, "n_burned": state.n_burned,
            "frp_active_sum": state.frp_sum,
            "frp_nearest": state.frp_now[ny_, nx_],
            "hour_local": (t1.hour + t1.minute / 60 + grid.lon_c / 15) % 24,
            **ter}
    cols["pass_idx"] = cols.get("pass_idx", pass_idx)
    df = pd.DataFrame(cols)
    for k, v in wx.items():
        df[k] = v
    return df


def rows_from_detections(det: pd.DataFrame, t_now, hourly: pd.DataFrame, raster: StaticRaster,
                         cfg: dict, grid: FireGrid | None = None) -> tuple[pd.DataFrame, FireGrid]:
    """Prediction rows for one fire at time t_now, from its detections so far (columns t, lat, lon, frp,
    sat) and hourly weather around t_now. Candidates = every cell within features.candidate_radius_cells
    of the burned area. The last pass at or before t_now is "now". `gap_min`/`kind` are not set: the
    caller asks C for each horizon. Raises ValueError if there is no pass yet or no weather for that hour."""
    f = cfg["features"]
    cell_m = float(cfg["grid"]["cell_m"])
    det = det[pd.to_datetime(det.t, utc=True) <= pd.Timestamp(t_now)].reset_index(drop=True)
    if det.empty:
        raise ValueError("no detection at or before t_now")
    grid = grid or fire_grid(det.lat, det.lon, f["grid_margin_cells"], cell_m)
    pidx, ptimes = assign_passes(det.t, det.sat, f["pass_split_min"])
    iy, ix = grid.index(det.lat, det.lon)
    cells_df = pd.DataFrame({"pass_idx": pidx, "ix": ix, "iy": iy, "frp": det.frp.to_numpy(float)})
    cells_df = cells_df.groupby(["pass_idx", "ix", "iy"]).frp.sum().reset_index()
    cells = {k: c for k, c in cells_df.groupby("pass_idx")}
    k = len(ptimes) - 1
    t1 = ptimes.iloc[k]
    wx = weather_at(prepare_weather(hourly, f["weather_lookback_days"]), t1)
    if wx is None:
        raise ValueError(f"no weather for {t1}")
    state = fire_state(grid, cells, k)
    cy, cx = candidates(state, f["candidate_radius_cells"], f["jitter_cells"])
    rows = cell_features(grid, state, cy, cx, pass_idx=k, t1=t1, wx=wx,
                         terrain=raster_terrain(raster, grid), meta={"pass_idx": k, "t1": t1})
    return rows, grid
