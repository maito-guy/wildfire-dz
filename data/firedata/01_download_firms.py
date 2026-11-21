"""Step 1: download VIIRS 375 m fire detections for every country in config.COUNTRIES.

Uses the FIRMS area API (free MAP_KEY) on each country's bounding box; the country API stopped
answering ("Invalid API call."). Boxes include neighbours: step 2 relabels by real border. Standard-processing (SP) data where it exists,
near-real-time (NRT) for recent months. Resumable: finished windows are skipped.
    export FIRMS_MAP_KEY=xxxxxxxx    (Windows: set FIRMS_MAP_KEY=xxxxxxxx)
    python 01_download_firms.py
"""
import io, sys, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import pandas as pd, requests
import config as C
import boundaries

API = "https://firms.modaps.eosdis.nasa.gov/api"
BUDGET_PER_10MIN = 4000   # FIRMS allows 5,000 transactions per 10 min per key; each day = 1
                          # (headroom for other use of the key; the window is rolling)
WORKERS = 4               # parallel requests; the server's response time is the bottleneck


class BadRequest(Exception):
    pass


def availability(key):
    r = requests.get(f"{API}/data_availability/csv/{key}/ALL", timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df = df[df.data_id.str.startswith(C.SOURCE_PREFIXES)]
    return {row.data_id: (pd.Timestamp(row.min_date).date(), pd.Timestamp(row.max_date).date())
            for row in df.itertuples()}


def windows():
    """5-day windows (the area API maximum) covering the fire-season months of every year."""
    for y in C.YEARS:
        for m in C.MONTHS:
            start = dt.date(y, m, 1)
            end = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
            d = start
            while d <= end:
                n = min(5, (end - d).days + 1)
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
    boxes = {c: ",".join(map(str, boundaries.bbox(c))) for c in C.COUNTRIES}
    print("boxes:", boxes, flush=True)
    jobs = []
    for country in C.COUNTRIES:
        for prefix in C.SOURCE_PREFIXES:
            for d, n in windows():
                sid = pick_source(avail, prefix, d, n)
                if sid:
                    out = C.RAW_FIRMS / f"{country}_{sid}_{d}_{n}.csv"
                    if not out.exists():
                        jobs.append((country, sid, d, n, out))
    print(f"{len(jobs)} windows to download, {WORKERS} at a time", flush=True)

    def fetch(job):
        country, sid, d, n, out = job
        url = f"{API}/area/csv/{key}/{sid}/{boxes[country]}/{n}/{d}"
        for attempt in range(6):
            try:
                r = requests.get(url, timeout=120)
                txt = r.text.lower()
                if r.status_code == 200 and not txt.startswith(("invalid", "exceeding")):
                    tmp = out.with_suffix(".part"); tmp.write_text(r.text); tmp.replace(out)
                    return True
                print(f"  {r.status_code} {r.text[:80]!r}", flush=True)
                # over the 10-min cap FIRMS answers "Exceeding..." and also "Invalid MAP_KEY."
                # (the key was already checked by the availability call): wait it out
                if txt.startswith(("exceeding", "invalid map_key")):
                    time.sleep(120); continue
                if txt.startswith("invalid"):   # a bad request never fixes itself
                    raise BadRequest(f"FIRMS rejected {url.replace(key, '<key>')}: {r.text[:120]}")
            except requests.RequestException as e:
                print("  error", e, flush=True)
            time.sleep(10 * (attempt + 1))
        print(f"  giving up on {out.name}; rerun the script later", flush=True)
        return False

    # batches that fit the 10-minute transaction budget; each batch runs WORKERS requests at once
    batches, cur, cost = [], [], 0
    for j in jobs:
        if cost + j[3] > BUDGET_PER_10MIN:
            batches.append(cur); cur, cost = [], 0
        cur.append(j); cost += j[3]
    if cur:
        batches.append(cur)
    done = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        for b, batch in enumerate(batches):
            t0 = time.time()
            try:
                for job, ok in zip(batch, pool.map(fetch, batch)):
                    done += 1
                    if done % 100 == 0 or done == len(jobs):
                        print(f"{done}/{len(jobs)} done ({job[0]} {job[1]} {job[2]})", flush=True)
            except BadRequest as e:
                pool.shutdown(cancel_futures=True)
                sys.exit(str(e))
            if b < len(batches) - 1:                  # stay under the rate limit
                wait = max(0, 600 - (time.time() - t0)) + 5
                print(f"  rate limit: sleeping {wait:.0f}s", flush=True); time.sleep(wait)


if __name__ == "__main__":
    main()
