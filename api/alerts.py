"""Alert queue: AI flags become pending alerts; an operator approves (sent) or rejects them.

Nothing reaches the phones (`/alerts/stream`) without a human click (SPEC §1, §6.1). The dashboard
follows the queue on `/events`.

Auto rule (runs on every /predict, per fire and village; config.yaml `status`):
  * crossing into level L (get_ready / leave_now) when no alert at level >= L was sent, none is pending
    and no flag at level >= L was rejected -> a pending flag (source "ai_spread", event `flag`)
  * a pending flag whose village changes level or minutes is updated in place (level only goes up,
    texts re-rendered, event `flag_updated`)
  * escalation after a sent get_ready -> a new pending leave_now flag
  * a village with a sent alert whose computed status drops to safe -> one pending `update` flag
  * status is sticky: it never goes back to "safe" while the fire is active
  * cancel (sent alerts only) pushes a cancel event; it does not re-arm the rule at that level

Every action is logged (logger "api.alerts") and its time is kept on the alert
(created_at, approved_at, rejected_at, cancelled_at).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import itertools
import json
import logging
from functools import lru_cache

from api import cap
from core.config import load_config, repo_path

log = logging.getLogger(__name__)

SEV = {"safe": 0, "get_ready": 1, "leave_now": 2}
LANGS = ("ary", "kab", "ar", "fr", "en")


def _iso(o):
    return o.isoformat() if hasattr(o, "isoformat") else str(o)


class Broker:
    """Fan-out of SSE events to every connected client (phones, or dashboards)."""

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
    minutes = v.get("minutes_left")
    fields = {"village": v["name"], "km": f"{v.get('distance_km') or 0:.0f}",
              "direction": v.get("fire_direction", ""),
              "minutes": minutes if minutes is not None else "?",
              "leave_toward": v.get("leave_toward", ""), "phone": t.get("civil_protection_phone", "")}
    out = {}
    for lang in LANGS:
        tpl = t["templates"][level].get(lang) or ""
        if tpl:  # untranslated languages are simply left out; the phone shows what exists
            out[lang] = tpl.format(**fields)
    return out


def _cap_handoff(a: dict) -> None:
    """Simulated cell-broadcast hand-off of the CAP message. A CAP failure never blocks the phones."""
    try:
        cap.handoff(a, cap.build_cap(a, load_config()))
    except Exception:
        log.exception("CAP message for alert %s could not be built", a["id"])


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class AlertStore:
    def __init__(self):
        self.broker = Broker()   # phones: /alerts/stream, sent alerts and cancels only
        self.events = Broker()   # dashboards: /events, the whole queue
        self.reset()

    def reset(self):
        self.alerts: dict[str, dict] = {}
        self.sent_level: dict[tuple[str, str], str] = {}      # (fire, village) -> highest level sent
        self.rejected_level: dict[tuple[str, str], str] = {}  # (fire, village) -> highest level rejected
        self.peak: dict[tuple[str, str], str] = {}            # (fire, village) -> highest computed status
        self.pending: dict[tuple[str, str], str] = {}         # (fire, village) -> pending alert id
        self.update_flagged: set[tuple[str, str]] = set()
        self._ids = itertools.count(1)

    # ---- reads -------------------------------------------------------------------------------
    def sticky_status(self, fire_id: str, v: dict) -> str:
        if not load_config()["status"]["sticky"]:
            return v["status"]
        key = (fire_id, v["id"])
        prev = max(self.peak.get(key, "safe"), self.sent_level.get(key, "safe"), key=SEV.get)
        return max(v["status"], prev, key=SEV.get)

    def last_alert_id(self, fire_id: str, village_id: str) -> str | None:
        ids = [a["id"] for a in self.alerts.values()
               if a["fire_id"] == fire_id and a["village_id"] == village_id and a["status"] == "sent"]
        return ids[-1] if ids else None

    def pending_count(self) -> int:
        return sum(1 for a in self.alerts.values() if a["status"] == "pending")

    # ---- creation ----------------------------------------------------------------------------
    def _new(self, fire_id: str, v: dict, level: str, source: str, status: str, scenario_time,
             data_age_min: int) -> dict:
        a = {"id": f"al_{next(self._ids):04d}", "fire_id": fire_id, "village_id": v["id"],
             "village_name": v["name"], "level": level, "source": source, "status": status,
             "created_at": _now(), "scenario_time": scenario_time, "approved_at": None,
             "rejected_at": None, "reject_reason": None, "cancelled_at": None, "edited": False,
             "minutes_left": v.get("minutes_left"), "ai_minutes_left": v.get("ai_minutes_left"),
             "distance_km": v.get("distance_km") or 0.0,
             "fire_direction": v.get("fire_direction", ""), "leave_toward": v.get("leave_toward", ""),
             "data_age_min": data_age_min,
             "area": {"lat": v["lat"], "lon": v["lon"], "radius_km": load_config()["api"]["alert_area_radius_km"]},
             "texts": render(level, v)}
        self.alerts[a["id"]] = a
        return a

    def _mark_sent(self, a: dict) -> None:
        key = (a["fire_id"], a["village_id"])
        if a["level"] in SEV and SEV[a["level"]] > SEV[self.sent_level.get(key, "safe")]:
            self.sent_level[key] = a["level"]
        self.broker.publish("alert", a)
        self.events.publish("alert_sent", a)
        _cap_handoff(a)

    def send(self, fire_id: str, v: dict, level: str, source: str, scenario_time, data_age_min: int) -> dict:
        """Send at once (manual operator alert). Goes straight to the phones."""
        a = self._new(fire_id, v, level, source, "sent", scenario_time, data_age_min)
        a["approved_at"] = a["created_at"]
        log.info("alert %s sent by operator (%s, %s, %s)", a["id"], level, fire_id, v["id"])
        self._mark_sent(a)
        return a

    def flag(self, fire_id: str, v: dict, level: str, source: str, scenario_time, data_age_min: int) -> dict:
        """Create a pending flag for (fire, village), or update the pending one in place.

        On update the level only goes up within get_ready/leave_now; any other level replaces it.
        Publishes `flag` (new) or `flag_updated` (changed) on /events. Never reaches the phones.
        """
        key = (fire_id, v["id"])
        pid = self.pending.get(key)
        if pid is None:
            a = self._new(fire_id, v, level, source, "pending", scenario_time, data_age_min)
            self.pending[key] = a["id"]
            log.info("alert %s flagged by %s (%s, %s, %s)", a["id"], source, level, fire_id, v["id"])
            self.events.publish("flag", a)
            return a
        a = self.alerts[pid]
        new_level = level
        if level in SEV and a["level"] in SEV:
            new_level = max(level, a["level"], key=SEV.get)
        new = {"level": new_level, "minutes_left": v.get("minutes_left"), "ai_minutes_left": v.get("ai_minutes_left"),
               "distance_km": v.get("distance_km") or 0.0, "fire_direction": v.get("fire_direction", ""),
               "leave_toward": v.get("leave_toward", ""), "data_age_min": data_age_min}
        if all(a[k] == val for k, val in new.items()):
            return a
        a.update(new, scenario_time=scenario_time, texts=render(new_level, v), source=source)
        log.info("alert %s flag updated (%s, %s min)", a["id"], new_level, new["minutes_left"])
        self.events.publish("flag_updated", a)
        return a

    def apply_rules(self, fire_id: str, villages: list[dict], scenario_time, data_age_min: int) -> list[dict]:
        """Turn the computed village statuses into pending flags. Returns the flags created or updated."""
        out = []
        for v in villages:
            key = (fire_id, v["id"])
            status = v["status"]
            if SEV[status] > SEV[self.peak.get(key, "safe")]:
                self.peak[key] = status
            sent = self.sent_level.get(key, "safe")
            pid = self.pending.get(key)
            if pid is not None:
                p = self.alerts[pid]
                if p["level"] in SEV and status != "safe":
                    out.append(self.flag(fire_id, v, status, "ai_spread", scenario_time, data_age_min))
                elif p["level"] == "update" and SEV[status] > SEV[sent]:
                    # the fire turned back toward a warned village: the pending update becomes a warning
                    out.append(self.flag(fire_id, v, status, "ai_spread", scenario_time, data_age_min))
                continue
            barrier = max(sent, self.rejected_level.get(key, "safe"), key=SEV.get)
            if SEV[status] > SEV[barrier]:
                out.append(self.flag(fire_id, v, status, "ai_spread", scenario_time, data_age_min))
            elif status == "safe" and sent != "safe" and key not in self.update_flagged:
                self.update_flagged.add(key)
                out.append(self.flag(fire_id, v, "update", "ai_spread", scenario_time, data_age_min))
        return out

    # ---- operator actions --------------------------------------------------------------------
    def approve(self, alert_id: str, texts: dict[str, str] | None = None,
                radius_km: float | None = None) -> dict:
        """Pending -> sent. Raises KeyError (unknown) or ValueError (not pending)."""
        a = self._pending_or_raise(alert_id)
        if texts:
            a["texts"] = a["texts"] | texts
            a["edited"] = True
        if radius_km is not None:
            a["area"]["radius_km"] = radius_km
        a["status"] = "sent"
        a["approved_at"] = _now()
        self.pending.pop((a["fire_id"], a["village_id"]), None)
        log.info("alert %s approved and sent (%s, edited=%s)", a["id"], a["level"], a["edited"])
        self._mark_sent(a)
        return a

    def reject(self, alert_id: str, reason: str) -> dict:
        """Pending -> rejected. Raises KeyError (unknown) or ValueError (not pending)."""
        a = self._pending_or_raise(alert_id)
        a["status"] = "rejected"
        a["rejected_at"] = _now()
        a["reject_reason"] = reason
        key = (a["fire_id"], a["village_id"])
        self.pending.pop(key, None)
        if a["level"] in SEV and SEV[a["level"]] > SEV[self.rejected_level.get(key, "safe")]:
            self.rejected_level[key] = a["level"]
        log.info("alert %s rejected: %s", a["id"], reason)
        self.events.publish("alert_rejected", a)
        return a

    def cancel(self, alert_id: str) -> dict:
        """Sent -> cancelled. Raises KeyError (unknown) or ValueError (not sent)."""
        a = self.alerts.get(alert_id)
        if a is None:
            raise KeyError(alert_id)
        if a["status"] != "sent":
            raise ValueError(f"alert {alert_id} is {a['status']}, only sent alerts can be cancelled")
        a["status"] = "cancelled"
        a["cancelled_at"] = _now()
        log.info("alert %s cancelled", a["id"])
        self.broker.publish("cancel", a)
        self.events.publish("alert_cancelled", a)
        _cap_handoff(a)
        return a

    def _pending_or_raise(self, alert_id: str) -> dict:
        a = self.alerts.get(alert_id)
        if a is None:
            raise KeyError(alert_id)
        if a["status"] != "pending":
            raise ValueError(f"alert {alert_id} is {a['status']}, not pending")
        return a


store = AlertStore()
