"""Country borders (Natural Earth 1:10m) used to download by bounding box and to label detections.

The FIRMS country endpoint stopped answering, so step 1 asks the area endpoint for each
country's bounding box. Boxes overlap (Morocco/Algeria, Spain/Portugal, Greece/Turkey) and
include neighbours, so step 2 relabels every detection by the border it actually falls inside.
The file is downloaded once into data/boundaries/.
"""
import json
import numpy as np, requests, shapely
from shapely.geometry import shape
import config as C

PATH = C.ROOT / "boundaries" / "ne_10m_admin_0_countries.geojson"


def _load():
    if not PATH.exists():
        PATH.parent.mkdir(parents=True, exist_ok=True)
        print("downloading country borders (Natural Earth, ~13 MB)", flush=True)
        r = requests.get(C.BOUNDARIES_URL, timeout=300)
        r.raise_for_status()
        tmp = PATH.with_suffix(".part"); tmp.write_bytes(r.content); tmp.replace(PATH)
    feats = json.loads(PATH.read_text())["features"]
    geoms = {f["properties"]["ADM0_A3"]: shape(f["geometry"]) for f in feats
             if f["properties"]["ADM0_A3"] in C.COUNTRIES}
    missing = set(C.COUNTRIES) - set(geoms)
    if missing:
        raise SystemExit(f"no border for {sorted(missing)} in {PATH}")
    for g in geoms.values():
        shapely.prepare(g)
    return geoms


_GEOMS = None


def geoms():
    global _GEOMS
    if _GEOMS is None:
        _GEOMS = _load()
    return _GEOMS


def bbox(country):
    """(west, south, east, north) for the FIRMS area API; Algeria starts at DZA_MIN_LAT."""
    w, s, e, n = geoms()[country].bounds
    if country == "DZA":
        s = max(s, C.DZA_MIN_LAT)
    pad = 0.05
    return round(w - pad, 2), round(s - pad, 2), round(e + pad, 2), round(n + pad, 2)


def label(lat, lon):
    """ISO-3 code of the country each point falls in; coastal points within COAST_TOL_DEG
    of a border go to that country; anything else (neighbours, open sea) gets None."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    out = np.full(lat.shape, None, dtype=object)
    for code, g in geoms().items():
        out[(out == None) & shapely.contains_xy(g, lon, lat)] = code  # noqa: E711
    rest = np.flatnonzero(out == None)  # noqa: E711
    if len(rest):
        pts = shapely.points(lon[rest], lat[rest])
        for code, g in geoms().items():
            hit = (out[rest] == None) & shapely.dwithin(g, pts, C.COAST_TOL_DEG)  # noqa: E711
            out[rest[hit]] = code
    return out
