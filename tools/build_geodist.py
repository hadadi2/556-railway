#!/usr/bin/env python3
"""يبني `data/geodist_l1.csv` — مسافة العواصم بين كل زوج دول (هافرساين، كم).

> **لماذا هذا الملف.** قالب E1 في نمط «دراسة السوق» يصف أكبر ثلاثة موردين
> بـ«قريبة جغرافياً» حين تكون مسافة العاصمة ≤ 3,000 كم (P0-T في
> `docs/plans/STUDY_MODE_FIX_PLAN.md`). `cepii.fr` محجوب بسياسة الشبكة، فالمصدر
> مجموعتان مفتوحتان على GitHub مثبَّتتان بالإصدار (SHA):
>   - mledoze/countries `countries.json` — رمز الدولة (cca3/cca2) واسم العاصمة
>     ومركز الدولة الجغرافي (احتياط حين لا تُطابَق العاصمة).
>   - lutangar/cities.json `cities.json` (مشتق من GeoNames، CC BY 4.0) —
>     إحداثيات المدن بالاسم ورمز الدولة.
> المسافة بمعادلة هافرساين بنصف قطر 6,371 كم. الصفوف `basis=capital` حين
> طابقت العاصمة مدينةً، و`basis=centroid` حين رُدّ إلى مركز الدولة (معلَن لا مخفي).

الاستعمال:  python3 tools/build_geodist.py [--countries F --cities F]
بلا وسائط يُنزِّل الملفين من الإصدار المثبَّت أدناه. stdlib فقط.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import unicodedata
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "geodist_l1.csv")

COUNTRIES_REPO = "mledoze/countries"
COUNTRIES_SHA = "c8015eebdd94c533358406b0d709f441389e1f2e"
CITIES_REPO = "lutangar/cities.json"
CITIES_SHA = "e66576247c5d26b1fc65d96a499acff3c3fef827"
COUNTRIES_URL = f"https://raw.githubusercontent.com/{COUNTRIES_REPO}/{COUNTRIES_SHA}/countries.json"
CITIES_URL = f"https://raw.githubusercontent.com/{CITIES_REPO}/{CITIES_SHA}/cities.json"
EARTH_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """مسافة الدائرة العظمى بالكيلومتر — haversine."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c)).lower().strip()


def _load(path_or_url: str):
    if os.path.exists(path_or_url):
        with open(path_or_url, encoding="utf-8") as f:
            return json.load(f)
    with urllib.request.urlopen(path_or_url, timeout=120) as r:  # noqa: S310
        return json.load(r)


def capitals(countries, cities) -> dict[str, tuple[float, float, str]]:
    """iso3 → (lat, lon, basis). العاصمة من cities.json وإلا مركز الدولة."""
    by_cc: dict[str, list] = {}
    for c in cities:
        by_cc.setdefault(c["country"], []).append(c)
    out = {}
    for c in countries:
        iso3, iso2 = c["cca3"], c["cca2"]
        cap = (c.get("capital") or [""])[0]
        hit = None
        if cap:
            key = _fold(cap)
            for city in by_cc.get(iso2, []):
                if _fold(city["name"]) == key:
                    hit = city
                    break
        if hit:
            out[iso3] = (float(hit["lat"]), float(hit["lng"]), "capital")
        elif c.get("latlng"):
            out[iso3] = (float(c["latlng"][0]), float(c["latlng"][1]), "centroid")
    return out


def build(countries, cities, out_path: str = OUT) -> int:
    caps = capitals(countries, cities)
    codes = sorted(caps)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write("# geodist_l1 — capital-to-capital great-circle distance (haversine, km).\n")
        f.write(f"# sources: {COUNTRIES_REPO}@{COUNTRIES_SHA} (countries.json: cca3, capital, latlng); "
                f"{CITIES_REPO}@{CITIES_SHA} (cities.json, GeoNames-derived, CC BY 4.0: capital coordinates).\n")
        f.write("# basis: capital = both endpoints matched a capital city; centroid = at least one endpoint fell back to the country centroid.\n")
        f.write("# built by tools/build_geodist.py; threshold for «قريبة جغرافياً» lives in the template rules, not here.\n")
        w = csv.writer(f)
        w.writerow(["iso3_a", "iso3_b", "distcap_km", "basis"])
        n = 0
        for i, a in enumerate(codes):
            for b in codes[i + 1:]:
                la, lo, ba = caps[a]
                lb, lob, bb = caps[b]
                basis = "capital" if ba == bb == "capital" else "centroid"
                w.writerow([a, b, round(haversine_km(la, lo, lb, lob), 1), basis])
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default=COUNTRIES_URL)
    ap.add_argument("--cities", default=CITIES_URL)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    n = build(_load(a.countries), _load(a.cities), a.out)
    print(f"wrote {n} pairs → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
