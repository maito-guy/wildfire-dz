"""Publish artifacts for the API: the chosen model C plus tuned thresholds.

  python -m model.export --tag mixed     # after train + evaluate

Writes model/artifacts/api_manifest.json, which api/predictor.py reads at startup.
If the manifest is missing the API uses config.yaml placeholders and model A/B only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil

from core.config import load_config, repo_path


def export(cfg: dict, tag: str | None) -> dict:
    art = repo_path(cfg["paths"]["artifacts"])
    th_path = art / "thresholds.json"
    if not th_path.exists():
        raise FileNotFoundError("run `python -m model.evaluate` first (thresholds.json missing)")
    th = json.loads(th_path.read_text())
    manifest = {
        "exported_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "rate_m_per_min": {"A": th["A"]["rate_m_per_min"], "B": th["B"]["rate_m_per_min"]},
        "model_c": None,
    }
    if tag:
        feats = art / f"features_{tag}.json"
        if not feats.exists() or f"C_{tag}" not in th:
            raise FileNotFoundError(f"features_{tag}.json or its threshold missing; train + evaluate first")
        files = json.loads(feats.read_text()).get("files") or [f"model_c_{tag}.txt"]
        missing = [f for f in files if not (art / f).exists()]
        if missing:
            raise FileNotFoundError(f"model files missing: {missing}")
        shutil.copy(feats, art / "features.json")
        manifest["model_c"] = {"tag": tag, "features": "features.json", "files": files,
                               "prob_threshold": th[f"C_{tag}"]["prob"]}
    (art / "api_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=None, help="model C tag to ship (omit = baselines only)")
    export(load_config(), ap.parse_args().tag)


if __name__ == "__main__":
    main()
