"""Simulated cell broadcast: auto-send on threshold crossing, manual send, cancel, push stream.

Rules (config.yaml `status`):
  * a village crossing into get_ready or leave_now gets an automatic alert at that level
  * escalation (get_ready -> leave_now) sends again; the same level is never re-sent
  * status is sticky: it never goes back to "safe" while the fire is active
  * if a warned village's computed status drops to safe, one "update" alert is sent
  * cancel marks the alert cancelled and pushes a cancel event; it does not re-arm auto-send at that level
"""
from __future__ import annotations

import asyncio
import datetime as dt
import itertools
import json
from functools import lru_cache

from core.config import load_config, repo_path

SEV = {"safe": 0, "get_ready": 1, "leave_now": 2}
LANGS = ("ary", "kab", "ar", "fr", "en")


def _iso(o):
    return o.isoformat() if hasattr(o, "isoformat") else str(o)


class Broker:
    """Fan-out of events to every connected test phone (SSE)."""

    def __init__(self):
        self.queues: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.queues.discard(q)

    def publish(self, event: str, data: dict) -> None:
        msg = f"event: {event}\ndata: {json.dumps(data, default=_iso)}\n\n"
        for q in list(self.queues):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


@lru_cache(maxsize=1)
def texts() -> dict:
    return json.loads(repo_path(load_config()["paths"]["alert_texts"]).read_text(encoding="utf-8"))


def render(level: str, v: dict) -> dict[str, str]:
    t = texts()
    fields = {"village": v["name"], "km": f"{v['distance_km']:.0f}", "direction": v["fire_direction"],
              "minutes": v["minutes_left"] if v["minutes_left"] is not None else "?",
              "leave_toward": v["leave_toward"], "phone": t.get("civil_protection_phone", "")}
    out = {}
    for lang in LANGS:
        tpl = t["templates"][level].get(lang) or ""
        if tpl:  # untranslated languages are simply left out; the phone shows what exists
            out[lang] = tpl.format(**fields)
    return out


class AlertStore:
    def __init__(self):
        self.reset()

    def reset(self):
        self.alerts: dict[str, dict] = {}
        self.sent_level: dict[tuple[str, str], str] = {}   # (fire, village) -> highest level sent
        self.update_sent: set[tuple[str, str]] = set()
        self._ids = itertools.count(1)
        self.broker = getattr(self, "broker", Broker())

    def sticky_status(self, fire_id: str, v: dict) -> str:
        if not load_config()["status"]["sticky"]:
            return v["status"]
        prev = self.sent_level.get((fire_id, v["id"]), "safe")
        return max(v["status"], prev, key=SEV.get)

    def last_alert_id(self, fire_id: str, village_id: str) -> str | None:
        ids = [a["id"] for a in self.alerts.values()
               if a["fire_id"] == fire_id and a["village_id"] == village_id and a["status"] == "sent"]
        return ids[-1] if ids else None

    def send(self, fire_id: str, v: dict, level: str, source: str, scenario_time, data_age_min: int) -> dict:
        now = dt.datetime.now(dt.UTC)
        a = {"id": f"al_{next(self._ids):04d}", "fire_id": fire_id, "village_id": v["id"],
             "village_name": v["name"], "level": level, "source": source, "status": "sent",
             "created_at": now, "scenario_time": scenario_time, "cancelled_at": None,
             "minutes_left": v["minutes_left"], "distance_km": v["distance_km"],
             "fire_direction": v["fire_direction"], "leave_toward": v["leave_toward"],
             "data_age_min": data_age_min,
             "area": {"lat": v["lat"], "lon": v["lon"], "radius_km": load_config()["api"]["alert_area_radius_km"]},
             "texts": render(level, v)}
        self.alerts[a["id"]] = a
        key = (fire_id, v["id"])
        if level in SEV and SEV[level] > SEV[self.sent_level.get(key, "safe")]:
            self.sent_level[key] = level
        self.broker.publish("alert", a)
        return a

    def apply_rules(self, fire_id: str, villages: list[dict], scenario_time, data_age_min: int) -> list[dict]:
        sent = []
        for v in villages:
            key = (fire_id, v["id"])
            prev = self.sent_level.get(key, "safe")
            if SEV[v["status"]] > SEV[prev]:
                sent.append(self.send(fire_id, v, v["status"], "auto", scenario_time, data_age_min))
            elif v["status"] == "safe" and prev != "safe" and key not in self.update_sent:
                self.update_sent.add(key)
                sent.append(self.send(fire_id, v, "update", "auto", scenario_time, data_age_min))
        return sent

    def cancel(self, alert_id: str) -> dict | None:
        a = self.alerts.get(alert_id)
        if a is None:
            return None
        if a["status"] != "cancelled":
            a["status"] = "cancelled"
            a["cancelled_at"] = dt.datetime.now(dt.UTC)
            self.broker.publish("cancel", a)
        return a


store = AlertStore()
