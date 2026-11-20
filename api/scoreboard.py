"""Scoreboard for GET /scoreboard (shape in docs/contracts.md §2).

Serves model/artifacts/scoreboard.json (written by `python -m model.evaluate`). Until that file
exists, serves a stub of the same shape, flagged stub=true, with every metric null
("not measured yet"). The stub never carries numbers.
"""
from __future__ import annotations

import json

from core.config import load_config, repo_path

NOT_MEASURED = "not measured yet"
STUB_MODELS = ("A", "B", "C_mixed", "C_dza")
METRICS = ("recall_1h", "false_alarm_cell_share", "zone_cells_per_burned_cell",
           "missed_villages", "median_lead_min", "false_alarm_villages")
WEATHER_NOTE = ("Training and evaluation weather is ERA5 reanalysis, i.e. a perfect forecast. "
                "Live accuracy will be lower.")


def load() -> dict:
    cfg = load_config()
    p = repo_path(cfg["paths"]["artifacts"]) / "scoreboard.json"
    if p.exists():
        return json.loads(p.read_text())
    return stub(cfg)


def stub(cfg: dict) -> dict:
    holdouts = cfg.get("holdouts", {})
    model = dict.fromkeys(METRICS) | {"status": NOT_MEASURED}
    return {
        "stub": True,
        "status": NOT_MEASURED,
        "generated_at": None,
        "weather_note": WEATHER_NOTE,
        "horizon": "1h, pairs 20-120 min apart",
        "thresholds": {"target_recall": cfg.get("safety", {}).get("target_recall"),
                       "A": {"rate_m_per_min": None}, "B": {"rate_m_per_min": None},
                       "C_mixed": {"prob": None}},
        "fires": [{"holdout": k, "name": h.get("name", k), "n_fires": None,
                   "models": {m: dict(model) for m in STUB_MODELS}} for k, h in holdouts.items()],
        "replay_counter": {"holdout": next(iter(holdouts), None), "village": None, "model": None,
                           "lead_min": None, "old_method": None, "old_method_lead_min": None,
                           "status": NOT_MEASURED},
        "ship_c": {"rule": "C ships only if it beats B on missed villages and lead time",
                   "decision": NOT_MEASURED},
    }
