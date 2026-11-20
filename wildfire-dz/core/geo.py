"""Small geometry helpers: local equirectangular grid, distances, bearings."""
from __future__ import annotations

import numpy as np

EARTH_R = 6_371_000.0
COMPASS8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def to_xy(lat, lon, lat0: float, lon0: float):
    """Degrees -> metres on a local equirectangular plane (x east, y north)."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    mlon = np.cos(np.radians(lat0))
    x = np.radians(lon - lon0) * EARTH_R * mlon
    y = np.radians(lat - lat0) * EARTH_R
    return x, y


def to_latlon(x, y, lat0: float, lon0: float):
    mlon = np.cos(np.radians(lat0))
    lat = lat0 + np.degrees(np.asarray(y, dtype=float) / EARTH_R)
    lon = lon0 + np.degrees(np.asarray(x, dtype=float) / (EARTH_R * mlon))
    return lat, lon


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlon = lon2 - lon1
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return (np.degrees(np.arctan2(x, y)) + 360) % 360


def compass8(deg: float) -> str:
    return COMPASS8[int(((deg % 360) + 22.5) // 45) % 8]
