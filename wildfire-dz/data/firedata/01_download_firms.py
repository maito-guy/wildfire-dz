"""Step 1: download VIIRS 375 m fire detections for every country in config.COUNTRIES.

Uses the FIRMS country API (free MAP_KEY). Standard-processing (SP) data where it exists,
near-real-time (NRT) for recent months. Resumable: finished windows are skipped.
    export FIRMS_MAP_KEY=xxxxxxxx    (Windows: set FIRMS_MAP_KEY=xxxxxxxx)
    python 01_download_firms.py
"""
import io, sys, time, datetime as dt
import pandas as pd, requests
import config as C

API = "https://firms.modaps.eosdis.nasa.gov/api"
BUDGET_PER_10MIN = 4500   # FIRMS allows 5,000 transactions per 10 min per key; each day = 1


def availability(key):
    r = requests.get(f"{API}/data_availability/csv/{key}/ALL", timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df = df[df.data_id.str.startswith(C.SOURCE_PREFIXES)]
    return {row.data_id: (pd.Timestamp(row.min_date).date(), pd.Timestamp(row.max_date).date())
            for row in df.itertuples()}


def windows():
    """10-day windows covering the fire-season months of every year."""
    for y in C.YEARS:
        for m in C.MONTHS:
            start = dt.date(y, m, 1)
            end = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
            d = start
            while d <= end:
                n = min(10, (end - d).days + 1)
                yield d, n
                d += dt.timedelta(days=n)


def pick_source(avail, prefix, d, n):
    """Prefer SP; fall back to NRT for dates SP doesn't cover yet."""
    last = d + dt.timedelta(days=n - 1)
    for kind in ("SP", "NRT"):
        sid = f"{prefix}_{kind}"
        if sid in avail and avail[sid][0] <= d and last <= avail[sid][1]:
            return sid
    for kind in ("SP", "NRT"):  # partial overlap: still useful
        sid = f"{prefix}_{kind}"
        if sid in avail and avail[sid][0] <= last and d <= avail[sid][1]:
            return sid
    return None


def main():
    key = C.FIRMS_MAP_KEY
    if not key:
        sys.exit("Set FIRMS_MAP_KEY first (free: https://firms.modaps.eosdis.nasa.gov/api/map_key/)")
    avail = availability(key)
    print("sources available:", {k: f"{v[0]}..{v[1]}" for k, v in avail.items()})
    jobs = []
    for country in C.COUNTRIES:
        for prefix in C.SOURCE_PREFIXES:
            for d, n in windows():
                sid = pick_source(avail, prefix, d, n)
                if sid:
                    out = C.RAW_FIRMS / f"{country}_{sid}_{d}_{n}.csv"
                    if not out.exists():
                        jobs.append((country, sid, d, n, out))
    print(f"{len(jobs)} windows to download")
    spent, t0 = 0, time.time()
    for i, (country, sid, d, n, out) in enumerate(jobs, 1):
        if spent + n > BUDGET_PER_10MIN:          # stay under the rate limit
            wait = max(0, 600 - (time.time() - t0)) + 5
            print(f"  rate limit: sleeping {wait:.0f}s"); time.sleep(wait)
            spent, t0 = 0, time.time()
        url = f"{API}/country/csv/{key}/{sid}/{country}/{n}/{d}"
        for attempt in range(4):
            try:
                r = requests.get(url, timeout=120)
                if r.status_code == 200 and not r.text.lower().startswith(("invalid", "exceeding")):
                    break
                print(f"  {r.status_code} {r.text[:80]!r}")
            except requests.RequestException as e:
                print("  error", e)
            time.sleep(10 * (attempt + 1))
        else:
            print(f"  giving up on {out.name}; rerun the script later"); continue
        tmp = out.with_suffix(".part"); tmp.write_text(r.text); tmp.replace(out)
        spent += n
        if i % 50 == 0 or i == len(jobs):
            print(f"{i}/{len(jobs)} done ({country} {sid} {d})")


if __name__ == "__main__":
    main()
