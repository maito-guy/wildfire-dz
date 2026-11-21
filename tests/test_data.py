"""Smoke test for data/: the firedata scripts compile, and the output folder is git-ignored."""
import py_compile

import pytest

from core.config import ROOT

SCRIPTS = ["01_download_firms.py", "02_clean.py", "03_weather.py", "04_terrain_fuel.py", "05_build_table.py",
           "06_places_replay.py", "07_holdout_dense.py"]


@pytest.mark.parametrize("name", SCRIPTS)
def test_pipeline_script_compiles(name):
    p = ROOT / "data" / "firedata" / name
    if not p.exists():
        pytest.skip(f"{name} not in data/firedata/ (see data/README.md)")
    py_compile.compile(str(p), doraise=True)


def test_outputs_are_ignored():
    gi = (ROOT / ".gitignore").read_text()
    assert "data/out/" in gi and "*.parquet" in gi and ".env" in gi
