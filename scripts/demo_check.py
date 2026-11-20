#!/usr/bin/env python3
"""Demo check for issue #16: start a fire → AI flag → operator approves → phone gets the alert.

Runs the same chain the judge sees, N times, against a running API, and times it. This script listens on
/alerts/stream like a phone. Real phones on /alert/ should be armed at the same time: they sound when this
script prints "phone".

    .venv/bin/python scripts/demo_check.py                          # 5 runs on http://localhost:8000
    .venv/bin/python scripts/demo_check.py --base http://10.0.0.5:8000 --runs 5 --token "$OPERATOR_TOKEN"

Stdlib only. Each run: POST /reset, POST /predict (one point, like a map click), wait for the pending flag,
approve the most urgent one, wait for it on the phone stream, fetch its CAP message. Target: approve → phone < 30 s.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import urllib.request

TARGET_S = 30.0
URGENCY = {"leave_now": 0, "get_ready": 1, "update": 2, "preventive": 3}


class Api:
    def __init__(self, base: str, token: str | None):
        self.base = base.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None, timeout: float = 30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("X-Operator-Token", self.token)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if r.headers.get_content_type() == "application/json" else raw.decode()


def phone_listener(base: str, events: queue.Queue, stop: threading.Event) -> None:
    """Reads /alerts/stream like the phone page does and puts (arrival time, alert) on the queue."""
    while not stop.is_set():
        try:
            with urllib.request.urlopen(base.rstrip("/") + "/alerts/stream", timeout=60) as r:
                name = None
                for line in r:
                    if stop.is_set():
                        return
                    s = line.decode().rstrip("\n")
                    if s.startswith("event:"):
                        name = s[6:].strip()
                    elif s.startswith("data:") and name == "alert":
                        events.put((time.monotonic(), json.loads(s[5:])))
                    elif s == "":
                        name = None
        except OSError:
            time.sleep(0.5)  # reconnect, like a browser


def start_point(api: Api) -> dict:
    """A burning point near villages: the first pass of the first replay fire."""
    fires = api.call("GET", "/replay")
    r = api.call("GET", f"/replay/{fires[0]['fire_id']}")
    return r["passes"][0]["burning"][0]


def one_run(api: Api, point: dict, wind: dict, phone: queue.Queue) -> dict:
    api.call("POST", "/reset")
    while not phone.empty():
        phone.get_nowait()

    t0 = time.monotonic()
    p = api.call("POST", "/predict", {"burning": [point], "model": "auto", "wind": wind})
    flags = []
    while not flags and time.monotonic() - t0 < TARGET_S:
        flags = [
            a for a in api.call("GET", f"/alerts?fire_id={p['fire_id']}&status=pending") if a["source"] == "ai_spread"
        ]
        if not flags:
            time.sleep(0.2)
    t_flag = time.monotonic() - t0
    if not flags:
        return {"ok": False, "why": "no flag within 30 s", "flag_s": t_flag}

    top = min(
        flags, key=lambda a: (URGENCY.get(a["level"], 9), a["minutes_left"] if a["minutes_left"] is not None else 1e9)
    )
    t1 = time.monotonic()
    api.call("POST", f"/alerts/{top['id']}/approve", {})
    got = None
    while got is None and time.monotonic() - t1 < TARGET_S:
        try:
            t, a = phone.get(timeout=TARGET_S)
        except queue.Empty:
            break
        if a["id"] == top["id"]:
            got = t
    if got is None:
        return {
            "ok": False,
            "why": "phone stream never got the alert",
            "flag_s": t_flag,
            "village": top["village_name"],
        }

    cap = api.call("GET", f"/alerts/{top['id']}/cap.xml")
    return {
        "ok": got - t1 < TARGET_S and "<alert" in cap,
        "flag_s": t_flag,
        "phone_s": got - t1,
        "village": top["village_name"],
        "level": top["level"],
        "flags": len(flags),
        "cap": "<alert" in cap,
        "model": p["model"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--token", default=os.environ.get("OPERATOR_TOKEN"))
    ap.add_argument("--wind", type=float, nargs=2, default=(30, 270), metavar=("KMH", "FROM_DEG"))
    ap.add_argument("--pause", type=float, default=3, help="seconds between runs, to watch the phones")
    a = ap.parse_args()

    api = Api(a.base, a.token)
    health = api.call("GET", "/health")
    print(f"API {a.base} · model C exported: {health['model_c_exported']} · places: {health['places']}")

    phone: queue.Queue = queue.Queue()
    stop = threading.Event()
    threading.Thread(target=phone_listener, args=(a.base, phone, stop), daemon=True).start()
    time.sleep(1)
    real = api.call("GET", "/health")["phones_connected"] - 1  # minus this script
    print(f"Real phones connected: {real}" + ("  ⚠ arm the test phones on /alert/" if real < 3 else ""))

    point = start_point(api)
    wind = {"speed_kmh": a.wind[0], "from_deg": a.wind[1]}
    print(
        f"Fire at {point['lat']:.4f}, {point['lon']:.4f} · wind {wind['speed_kmh']:.0f} km/h from {wind['from_deg']:.0f}°\n"
    )
    print(f"{'run':>3}  {'click→flag':>10}  {'approve→phone':>13}  {'CAP':>3}  result")

    results = []
    for i in range(1, a.runs + 1):
        r = one_run(api, point, wind, phone)
        results.append(r)
        phone_s = f"{r['phone_s']:.2f} s" if "phone_s" in r else "—"
        detail = (
            f"{r.get('level', '')} → {r.get('village', '')} ({r.get('flags', 0)} flags, model {r.get('model', '?')})"
        )
        print(
            f"{i:>3}  {r['flag_s']:>8.2f} s  {phone_s:>13}  {'yes' if r.get('cap') else 'no':>3}  "
            + ("PASS " + detail if r["ok"] else "FAIL " + r.get("why", detail))
        )
        if i < a.runs:
            time.sleep(a.pause)
    stop.set()

    passed = sum(r["ok"] for r in results)
    print(f"\n{passed}/{a.runs} runs under {TARGET_S:.0f} s with a CAP message.")
    return 0 if passed == a.runs else 1


if __name__ == "__main__":
    sys.exit(main())
