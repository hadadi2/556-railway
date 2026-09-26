"""قفل `data/geodist_l1.csv` — مسافات العواصم لقاعدة «قريبة جغرافياً» (P0-T).

الاختبارات التي طلبها المالك: كوالالمبور–جاكرتا/هانوي/سنغافورة تحت 3,000 كم،
وكوالالمبور–روما فوقها؛ + رأس الملف يذكر المصدرين والإصدار؛ + هافرساين معايَر.
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CSV = os.path.join(_ROOT, "data", "geodist_l1.csv")
NEAR_KM = 3000.0


def _load() -> dict[tuple[str, str], tuple[float, str]]:
    out = {}
    with open(_CSV, encoding="utf-8") as f:
        rows = [ln for ln in f if not ln.startswith("#")]
    for r in csv.DictReader(rows):
        out[(r["iso3_a"], r["iso3_b"])] = (float(r["distcap_km"]), r["basis"])
    return out


def dist(a: str, b: str) -> float:
    d = _load()
    return d[(a, b)][0] if (a, b) in d else d[(b, a)][0]


def test_header_names_sources_and_pinned_versions():
    with open(_CSV, encoding="utf-8") as f:
        head = "".join(next(f) for _ in range(4))
    assert "mledoze/countries@" in head and "lutangar/cities.json@" in head
    assert "haversine" in head


def test_malaysia_neighbours_are_near_and_rome_is_far():
    assert dist("MYS", "IDN") < NEAR_KM
    assert dist("MYS", "VNM") < NEAR_KM
    assert dist("MYS", "SGP") < NEAR_KM
    assert dist("MYS", "ITA") > NEAR_KM


def test_reference_capitals_matched_not_centroids():
    d = _load()
    for pair in (("IDN", "MYS"), ("MYS", "SGP"), ("MYS", "VNM"), ("ITA", "MYS")):
        assert d[pair][1] == "capital", pair


def test_haversine_matches_known_distance():
    from tools.build_geodist import haversine_km
    # كوالالمبور (3.139, 101.687) ↔ سنغافورة (1.290, 103.852) ≈ 316 كم
    assert abs(haversine_km(3.139, 101.687, 1.290, 103.852) - 316) < 5
