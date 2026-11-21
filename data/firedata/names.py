"""One clean display name per place. The export's OSM `name` often mixes scripts
("Oran ⵡⴰⵀⵔⴻⵏ وهران", "الطاهر ⵟⵟⴰⵀⵔ"); the dashboard and alerts need one name in one script."""
import re

_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_TIFINAGH = re.compile(r"[ⴰ-⵿]")
_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")
_EDGE = " -/,;|()·"


def script_parts(name: str) -> dict[str, str]:
    """Split a name into its Latin, Arabic and Tifinagh words. Words without letters
    (digits, dashes) go with the word before them."""
    parts: dict[str, list[str]] = {"latin": [], "arabic": [], "tifinagh": []}
    last = None
    for w in str(name).split():
        if _TIFINAGH.search(w):
            last = "tifinagh"
        elif _ARABIC.search(w):
            last = "arabic"
        elif _LATIN.search(w):
            last = "latin"
        elif last is None:
            continue
        parts[last].append(w)
    return {k: " ".join(v).strip(_EDGE) for k, v in parts.items()}


def _text(v) -> str:
    return "" if v is None or v != v else str(v).strip()   # v != v: NaN


def display_name(name, name_en=None, name_ar=None) -> str:
    """name_en, else the Latin part of name, else name_ar, else the Arabic part, else the raw name."""
    if _text(name_en):
        return _text(name_en)
    parts = script_parts(_text(name))
    return parts["latin"] or _text(name_ar) or parts["arabic"] or _text(name)
