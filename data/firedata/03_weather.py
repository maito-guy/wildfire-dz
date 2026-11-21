"""Step 3: hourly weather for every fire that has a training pair (ERA5 via Open-Meteo, free).

Free limit is 10,000 calls a day; fires are fetched most-useful first (most growth) and the
script is resumable, so if it stops at the limit just run it again tomorrow.
    python 03_weather.py [--max 9000]
"""
import argparse, json, time
import pandas as pd, requests
import config as C


def fetch(lat, lon, start, end):
    params = dict(latitude=round(lat, 4), longitude=round(lon, 4), start_date=str(start),
                  end_date=str(end), hourly=",".join(C.WEATHER_VARS), timezone="UTC",
                  wind_speed_unit="kmh")
    for attempt in range(6):
        try:
            r = requests.get(C.OPEN_METEO_URL, params=params, timeout=60)
        except requests.RequestException as e:        # timeouts, dropped connections
            print("  error", e, flush=True); time.sleep(5 * (attempt + 1)); continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:                       # rate limited
            msg = r.text.lower()
            if "daily" in msg:
                raise SystemExit("Daily Open-Meteo limit reached; run again tomorrow.")
            time.sleep(65)
            continue
        print(" ", r.status_code, r.text[:120]); time.sleep(5 * (attempt + 1))
    raise RuntimeError("weather request kept failing")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--max", type=int, default=9000)
    ap.add_argument("--all", action="store_true", help="also fires that never grew (more calls)")
    a = ap.parse_args()
    fires = pd.read_parquet(C.OUT / "fires.parquet").set_index("fire_id")
    pairs = pd.read_parquet(C.OUT / "pairs.parquet")
    useful = pairs.groupby("fire_id").n_new.sum()
    if not a.all:
        useful = useful[useful > 0]          # fires that never grew teach little
    # Algeria first, then the fires that grew most
    order = pd.DataFrame({"g": useful, "dza": fires.country.reindex(useful.index) == "DZA"})
    order = order.sort_values(["dza", "g"], ascending=[False, False])
    todo = [f for f in order.index if not (C.CACHE_WEATHER / f"{f}.json").exists()]
    print(f"{len(useful):,} fires to cover, {len(todo):,} still need weather")
    for n, fid in enumerate(todo[: a.max], 1):
        f = fires.loc[fid]
        start = (f.t_first - pd.Timedelta(days=C.WEATHER_LOOKBACK_DAYS)).date()
        end = (f.t_last + pd.Timedelta(days=1)).date()
        js = fetch(f.lat_c, f.lon_c, start, end)
        (C.CACHE_WEATHER / f"{fid}.json").write_text(json.dumps(js["hourly"]))
        time.sleep(0.12)                               # stays under 600 calls a minute
        if n % 200 == 0:
            print(f"{n}/{min(len(todo), a.max)}")


if __name__ == "__main__":
    main()
