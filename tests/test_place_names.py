"""#62: one clean name per place, never mixed scripts (data/firedata/names.py)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "firedata"))
from names import display_name, script_parts  # noqa: E402


@pytest.mark.parametrize(("name", "en", "ar", "want"), [
    ("Oran ⵡⴰⵀⵔⴻⵏ وهران", "Oran", "وهران", "Oran"),
    ("قسنطينة ⵇⵙⵏⵟⵉⵏⴰ", "Constantine", "قسنطينة", "Constantine"),
    ("الطاهر ⵟⵟⴰⵀⵔ", None, "الطاهر", "الطاهر"),
    ("عين أم الجمل ⵜⵉⵟ ⵎⵎ'ⴰⵍⵖⴻⵎ", float("nan"), "عين أم الجمل", "عين أم الجمل"),
    ("Tizi Ouzou ⵜⵉⵣⵉ ⵓⵣⵣⵓ تيزي وزو", None, None, "Tizi Ouzou"),
    ("Ouled H'Cine", None, "اولاد حسين", "Ouled H'Cine"),
    ("المطرفة ⵍⵎⵟⵔⴼⴰ", None, None, "المطرفة"),
    ("ⵜⴰⵡⵔⵉⵔⵜ", None, None, "ⵜⴰⵡⵔⵉⵔⵜ"),          # only Tifinagh: keep it rather than show nothing
    ("Mechtat 2 - El Kef", "", None, "Mechtat 2 - El Kef"),
])
def test_display_name(name, en, ar, want):
    assert display_name(name, en, ar) == want


def test_script_parts_split():
    assert script_parts("Oran ⵡⴰⵀⵔⴻⵏ وهران") == {"latin": "Oran", "arabic": "وهران", "tifinagh": "ⵡⴰⵀⵔⴻⵏ"}
