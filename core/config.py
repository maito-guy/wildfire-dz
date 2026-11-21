"""Load config.yaml once. Paths are resolved relative to the repo root."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path or os.environ.get("WF_CONFIG", ROOT / "config.yaml"))
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def repo_path(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p
