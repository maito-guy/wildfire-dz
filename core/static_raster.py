"""Precomputed terrain and fuel at 375 m for northern Algeria (issue #17).

The file is built by `data/build_static_raster.py` (`make static-raster`) with the same definitions as
`data/firedata/04_terrain_fuel.py`. It is one grid laid out like a training fire's grid in
`02_clean.py` / `05_build_table.py`: cell (iy, ix) covers
    lat in lat0 + [iy, iy + 1) * cell_m / m_per_deg_lat
    lon in lon0 + [ix, ix + 1) * cell_m / mlon
Lookups return the terrain and fuel columns with the names used in `train.parquet`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from core.config import load_config, repo_path

FUEL_NAMES = ("tree", "shrub", "grass", "crop", "built", "bare", "water")   # 04's C.FUEL_CLASSES values
LAYERS = ("elev", "elev_std", "slope", "aspect", *(f"fuel_{n}" for n in FUEL_NAMES))  # stored in the file
COLUMNS = ("elev", "elev_std", "slope", "aspect_sin", "aspect_cos",
           *(f"fuel_{n}" for n in FUEL_NAMES))                                     # train.parquet names
META = ("lat0", "lon0", "mlon", "cell_m", "m_per_deg_lat")


@dataclass(frozen=True)
class StaticRaster:
    lat0: float
    lon0: float
    mlon: float               # metres per degree of longitude, one value for the whole grid
    cell_m: float
    m_per_deg_lat: float
    layers: dict[str, np.ndarray] = field(repr=False)   # LAYERS -> float32 array (ny, nx); row 0 = south

    @property
    def shape(self) -> tuple[int, int]:
        return self.layers["elev"].shape

    def cell_index(self, lats, lons):
        """(iy, ix, inside) for each point, with the same floor() as 04/05."""
        lats = np.asarray(lats, dtype=float)
        lons = np.asarray(lons, dtype=float)
        ny, nx = self.shape
        with np.errstate(invalid="ignore"):
            fy = np.floor((lats - self.lat0) * self.m_per_deg_lat / self.cell_m)
            fx = np.floor((lons - self.lon0) * self.mlon / self.cell_m)
            inside = np.isfinite(fy) & np.isfinite(fx) & (fy >= 0) & (fy < ny) & (fx >= 0) & (fx < nx)
        iy = np.where(inside, fy, 0).astype(np.int64)
        ix = np.where(inside, fx, 0).astype(np.int64)
        return iy, ix, inside

    def cell_center(self, iy, ix):
        """Cell centre (lat, lon), as `lat`/`lon` in 05_build_table.py."""
        lat = self.lat0 + (np.asarray(iy) + 0.5) * self.cell_m / self.m_per_deg_lat
        lon = self.lon0 + (np.asarray(ix) + 0.5) * self.cell_m / self.mlon
        return lat, lon

    def _columns(self, iy, ix) -> dict[str, np.ndarray]:
        aspect = self.layers["aspect"][iy, ix]          # float32, so sin/cos round like 05 does
        out = {"elev": self.layers["elev"][iy, ix], "elev_std": self.layers["elev_std"][iy, ix],
               "slope": self.layers["slope"][iy, ix],
               "aspect_sin": np.sin(np.radians(aspect)), "aspect_cos": np.cos(np.radians(aspect))}
        for n in FUEL_NAMES:
            out[f"fuel_{n}"] = self.layers[f"fuel_{n}"][iy, ix]
        return out

    def lookup(self, lat: float, lon: float) -> dict[str, float] | None:
        """Terrain and fuel of the cell holding (lat, lon); None outside the grid."""
        iy, ix, inside = self.cell_index([lat], [lon])
        if not inside[0]:
            return None
        return {k: float(v[0]) for k, v in self._columns(iy, ix).items()}

    def lookup_many(self, lats, lons) -> pd.DataFrame:
        """One row per point, columns COLUMNS (float32); NaN for points outside the grid."""
        iy, ix, inside = self.cell_index(lats, lons)
        cols = self._columns(iy, ix)
        return pd.DataFrame({k: np.where(inside, v, np.nan).astype(np.float32) for k, v in cols.items()},
                            index=pd.RangeIndex(len(inside)))


def load(path: str | Path | None = None) -> StaticRaster:
    """Read the .npz written by data/build_static_raster.py (default: config.yaml paths.static_raster)."""
    p = Path(path) if path is not None else repo_path(load_config()["paths"]["static_raster"])
    with np.load(p) as z:
        missing = [k for k in (*LAYERS, *META) if k not in z.files]
        if missing:
            raise ValueError(f"{p}: missing {missing}; rebuild with `make static-raster`")
        meta = {k: float(z[k]) for k in META}
        layers = {k: z[k].astype(np.float32, copy=False) for k in LAYERS}
    return StaticRaster(**meta, layers=layers)
