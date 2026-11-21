"""Step 6: the two files the API needs (schemas in docs/contracts.md).

    python 06_places_replay.py --export-dir ~/Downloads/algeria-fire-map-data

out/places.parquet         id, name, lat, lon, name_ar   (OSM settlements from the export's places.csv)
out/replay_passes.parquet  holdout, t, lat, lon, satellite, frp   (one row per burning cell per pass,
                           cleaned detections from step 2 inside each holdout's bbox and dates)
Holdouts (bbox, start, end) are read from the repo's config.yaml.
"""
import argparse
from pathlib import Path
import pandas as pd, yaml
import config as C

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"
SAT_NAME = {"SNPP": "S-NPP", "NOAA20": "NOAA-20", "NOAA21": "NOAA-21"}


def places(export_dir):
    p = pd.read_csv(Path(export_dir).expanduser() / "places.csv",
                    usecols=["osm_id", "name", "name_ar", "name_en", "lng", "lat"])
    # export "name" mixes scripts ("Oran ⵡⴰⵀⵔⴻⵏ وهران"); prefer the English name when there is one
    name = p.name_en.where(p.name_en.notna() & (p.name_en.astype(str).str.strip() != ""), p.name)
    return pd.DataFrame({"id": "osm:" + p.osm_id.astype(str), "name": name.astype(str),
                         "lat": p.lat.astype(float), "lon": p.lng.astype(float),
                         "name_ar": p.name_ar.astype("string")})


def replay(holdouts):
    d = pd.read_parquet(C.OUT / "detections.parquet", columns=["lat", "lon", "t", "sat", "frp"])
    parts = []
    for key, h in holdouts.items():
        w, s, e, n = h["bbox"]
        t0 = pd.Timestamp(h["start"], tz="UTC")
        t1 = pd.Timestamp(h["end"], tz="UTC") + pd.Timedelta(days=1)
        g = d[d.lon.between(w, e) & d.lat.between(s, n) & (d.t >= t0) & (d.t < t1)]
        parts.append(pd.DataFrame({"holdout": key, "t": g.t, "lat": g.lat, "lon": g.lon,
                                   "satellite": g.sat.map(SAT_NAME).fillna(g.sat), "frp": g.frp}))
        print(f"{key}: {len(g):,} burning cells over {g.t.nunique()} passes")
    return pd.concat(parts, ignore_index=True).sort_values(["holdout", "t"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-dir", required=True, help="folder with the export's places.csv")
    a = ap.parse_args()
    holdouts = yaml.safe_load(REPO_CONFIG.read_text())["holdouts"]
    pl = places(a.export_dir)
    pl.to_parquet(C.OUT / "places.parquet", index=False)
    print(f"places: {len(pl):,}")
    replay(holdouts).to_parquet(C.OUT / "replay_passes.parquet", index=False)


if __name__ == "__main__":
    main()
