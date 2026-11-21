"""STUB helpers (PROGRESS D-12): believable fake villages and organic fake risk while the real files are missing.

Everything is a pure function of integer lattice indices (plus an optional seed), so the stub stays
deterministic for tests but looks irregular on the map: villages are scattered, not on a grid, and carry
Kabyle/Arabic-style names built from common parts. They are not real places and keep their `stub` ids.
"""
from __future__ import annotations

import numpy as np

_M64 = np.uint64(0xFFFFFFFFFFFFFFFF)

_PREFIX = ("Aït", "Beni", "Tizi", "Ighil", "Taourirt", "Ouled", "Draâ", "Thala", "Agouni", "Bordj", "Sidi",
           "Aïn", "Tala", "Azrou", "Ath", "Mechta", "Douar", "Oued", "Ighzer", "Tighilt")
_ROOT = ("Ouchen", "Meraou", "Rached", "Mansour", "Hamza", "Ali", "Bouzid", "Yahia", "Amrane", "Zekri",
         "Lahcen", "Saâda", "Messaoud", "Kheir", "Abdellah", "Zmenzer", "Guendouz", "Allaoua", "Aïssa",
         "Brahim", "Tahar", "Ouacif", "Larbaâ", "Mimoun", "Bouhlal", "Selma", "Rabah", "Khelil", "Amar",
         "Djemâa", "Ifira", "Lakhdar", "Ksar", "Zitoun", "Hammam", "Tamda", "Fraoun", "Taka", "Smaïl", "Idir")
_SUFFIX = ("", "", "", "", " El Djedid", " Oufella", " Bwadda", " El Bahri", " Centre")


def hash01(a: np.ndarray, b: np.ndarray, salt: int = 0) -> np.ndarray:
    """Uniform [0, 1) per (a, b, salt), vectorised splitmix64."""
    with np.errstate(over="ignore"):
        x = (np.asarray(a, dtype=np.int64).astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)
             ^ np.asarray(b, dtype=np.int64).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
             ^ np.uint64(salt & 0xFFFFFFFF) * np.uint64(0x165667B19E3779F9)) & _M64
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9) & _M64
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB) & _M64
        x = x ^ (x >> np.uint64(31))
    return (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def names(a: np.ndarray, b: np.ndarray) -> list[str]:
    p = (hash01(a, b, 11) * len(_PREFIX)).astype(int)
    r = (hash01(a, b, 12) * len(_ROOT)).astype(int)
    s = (hash01(a, b, 13) * len(_SUFFIX)).astype(int)
    return [f"{_PREFIX[i]} {_ROOT[j]}{_SUFFIX[k]}" for i, j, k in zip(p, r, s)]


def value_noise(lat: np.ndarray, lon: np.ndarray, scale_deg: float, salt: int) -> np.ndarray:
    """Smooth noise in [0, 1): hashed lattice values every `scale_deg`, smoothstep-interpolated."""
    x, y = np.asarray(lon) / scale_deg, np.asarray(lat) / scale_deg
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    v = lambda i, j: hash01(y0 + j, x0 + i, salt)  # noqa: E731
    top = v(0, 0) * (1 - fx) + v(1, 0) * fx
    bot = v(0, 1) * (1 - fx) + v(1, 1) * fx
    return top * (1 - fy) + bot * fy


def fractal_noise(lat: np.ndarray, lon: np.ndarray, salt: int = 0) -> np.ndarray:
    """Three octaves (~60, 25, 10 km), in [0, 1)."""
    n = (0.55 * value_noise(lat, lon, 0.55, salt + 1) + 0.30 * value_noise(lat, lon, 0.22, salt + 2)
         + 0.15 * value_noise(lat, lon, 0.09, salt + 3))
    return n
