"""Smoke test for core/: config loads and geometry helpers agree with each other."""
import numpy as np

from core import geo
from core.config import load_config


def test_config_has_locked_thresholds():
    s = load_config()["status"]
    assert (s["leave_now_max_min"], s["get_ready_max_min"]) == (60, 120)
    assert load_config()["safety"]["target_recall"] == 0.95


def test_xy_roundtrip_and_bearing():
    x, y = geo.to_xy(36.7, 4.1, 36.6, 4.0)
    lat, lon = geo.to_latlon(x, y, 36.6, 4.0)
    assert np.isclose(lat, 36.7) and np.isclose(lon, 4.1)
    assert geo.compass8(geo.bearing_deg(36.0, 4.0, 36.1, 4.0)) == "N"
    assert abs(geo.haversine_m(36.0, 4.0, 36.1, 4.0) - 11_120) < 30
