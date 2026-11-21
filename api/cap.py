"""CAP 1.2 message for a sent or cancelled alert, and the simulated cell-broadcast hand-off.

Cell broadcast is ordered from the operators (Mobilis, Djezzy, Ooredoo) with a Common Alerting Protocol
message (OASIS CAP 1.2). The demo builds the real message but only logs the hand-off (SPEC §1, §6.1).

  * one <info> per language in `alert.texts`; urgency, severity and certainty follow the alert level
  * a cancelled alert gives msgType Cancel, whose <references> names the original Alert message
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import xml.etree.ElementTree as ET
from functools import lru_cache

from core.config import repo_path

log = logging.getLogger(__name__)

NS = "urn:oasis:names:tc:emergency:cap:1.2"
ET.register_namespace("", NS)

LANGUAGE = {"ar": "ar-DZ", "ary": "ar-DZ", "kab": "kab-DZ", "fr": "fr-DZ", "en": "en"}
RESPONSE = {"leave_now": "Evacuate", "get_ready": "Prepare", "update": "Monitor", "preventive": "Monitor"}
URGENCY_SEVERITY_CERTAINTY = {
    "leave_now": ("Immediate", "Extreme", "Likely"),
    "get_ready": ("Expected", "Severe", "Likely"),
    "preventive": ("Future", "Moderate", "Possible"),
    "update": ("Expected", "Moderate", "Possible"),
}
PARAMETERS = ("minutes_left", "distance_km", "leave_toward", "data_age_min")


@lru_cache(maxsize=4)
def _headlines(path: str) -> dict:
    return json.loads(repo_path(path).read_text(encoding="utf-8")).get("headline", {})


def cap_time(t: dt.datetime | str) -> str:
    """CAP dateTime: `YYYY-MM-DDThh:mm:ss+00:00` (no fraction, explicit offset, UTC)."""
    if isinstance(t, str):
        t = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.UTC)
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def identifier(alert: dict, cfg: dict) -> str:
    """Identifier of the CAP Alert message for this alert."""
    return f"{cfg['cap']['identifier_prefix']}.{alert['id']}"


def _sub(parent: ET.Element, tag: str, text: str) -> ET.Element:
    el = ET.SubElement(parent, f"{{{NS}}}{tag}")
    el.text = text
    return el


def _area_text(alert: dict) -> str:
    area = alert["area"]
    return f"{area['lat']},{area['lon']} {area['radius_km']}"


def build_cap(alert: dict, cfg: dict, references: dict | None = None) -> str:
    """CAP 1.2 XML (UTF-8, with declaration) for a sent alert (msgType Alert) or a cancelled one (Cancel).

    `references` ({sender, identifier, sent}) names the message a Cancel refers to; by default the
    original Alert message of this same alert.
    """
    c = cfg["cap"]
    sent_at = alert.get("approved_at") or alert["created_at"]
    cancel = alert["status"] == "cancelled"

    root = ET.Element(f"{{{NS}}}alert")
    if cancel:
        # A Cancel is its own message, so it needs its own identifier; the original is in <references>.
        ref = references or {"sender": c["sender"], "identifier": identifier(alert, cfg), "sent": cap_time(sent_at)}
        _sub(root, "identifier", f"{identifier(alert, cfg)}.cancel")
        _sub(root, "sender", c["sender"])
        _sub(root, "sent", cap_time(alert.get("cancelled_at") or sent_at))
    else:
        _sub(root, "identifier", identifier(alert, cfg))
        _sub(root, "sender", c["sender"])
        _sub(root, "sent", cap_time(sent_at))
    _sub(root, "status", c.get("status", "Exercise"))
    _sub(root, "msgType", "Cancel" if cancel else "Alert")
    _sub(root, "scope", "Public")
    if cancel:
        _sub(root, "references", f"{ref['sender']},{ref['identifier']},{ref['sent']}")

    level = alert["level"]
    urgency, severity, certainty = URGENCY_SEVERITY_CERTAINTY[level]
    headlines = _headlines(cfg["paths"]["alert_texts"]).get(level, {})
    params = {k: alert.get(k) for k in PARAMETERS} | {"wildfire_alert_id": alert["id"]}
    for lang, text in alert["texts"].items():
        info = ET.SubElement(root, f"{{{NS}}}info")
        _sub(info, "language", LANGUAGE.get(lang, lang))
        _sub(info, "category", "Fire")
        _sub(info, "event", "Wildfire")
        _sub(info, "responseType", RESPONSE[level])
        _sub(info, "urgency", urgency)
        _sub(info, "severity", severity)
        _sub(info, "certainty", certainty)
        _sub(info, "senderName", c["sender_name"])
        headline = headlines.get(lang) or headlines.get("en")
        if headline:
            _sub(info, "headline", headline)
        _sub(info, "description", text)
        for name, value in params.items():
            if value is None or value == "":
                continue  # e.g. minutes_left = null: not reached within the model's horizon
            p = ET.SubElement(info, f"{{{NS}}}parameter")
            _sub(p, "valueName", name)
            _sub(p, "value", str(value))
        area = ET.SubElement(info, f"{{{NS}}}area")
        _sub(area, "areaDesc", alert["village_name"])
        _sub(area, "circle", _area_text(alert))

    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def handoff(alert: dict, xml: str) -> None:
    """Simulated hand-off to the operators' cell broadcast centres: one log line, nothing is sent."""
    root = ET.fromstring(xml.encode("utf-8"))
    ident = root.findtext(f"{{{NS}}}identifier")
    msg_type = root.findtext(f"{{{NS}}}msgType")
    log.info("CBC hand-off (simulated): %s %s area=%s km", ident, msg_type, _area_text(alert))
