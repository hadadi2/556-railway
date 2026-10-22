"""جداولُ السوق الحتمية — PR-C، الدرس ٣٠٤: ضريبة القيمة المضافة وسعر الصرف (`data/market_fiscal_l1.csv`)
وقواعد المنشأ (`data/origin_rules_l1.csv`) مع عضوية الاتفاقيات (`data/agreements_l1.csv`).

لكلّ صفٍّ جهةٌ رسمية ورابطها؛ السوقُ خارج الجدول أو العملةُ العائمة = `None` (فجوة معلنة)، لا رقمٌ مخمَّن.
مكتبةٌ قياسية فقط، بلا شبكة. Deterministic per-market VAT / FX peg / rules-of-origin tables.
"""
from __future__ import annotations

import csv
import functools
import os

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
#: الاتفاقياتُ التي تُعفي المصدِّرَ السعوديَّ، بالأولوية: الاتحادُ الجمركيّ قبل منطقة التجارة الحرة.
_SAUDI_AGREEMENTS = ("GCC", "GAFTA")


def _rows(name: str) -> list:
    path = os.path.join(_DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(line for line in fh if not line.startswith("#")))


def _num(v) -> "float | None":
    try:
        return float(v) if str(v or "").strip() != "" else None
    except ValueError:
        return None


@functools.lru_cache(maxsize=None)
def _fiscal_index() -> dict:
    return {r["iso3"].strip().upper(): r for r in _rows("market_fiscal_l1.csv") if r.get("iso3")}


@functools.lru_cache(maxsize=None)
def _currency_index() -> dict:
    """العملةُ من `market_locale.csv` — المصدرُ الواحد الذي يقرؤه `run_checks.infer_meta` (مراجعة §58)."""
    return {r["iso3"].strip().upper(): (r.get("currency") or "").strip()
            for r in _rows("market_locale.csv") if r.get("iso3")}


def fiscal(iso3: str) -> "dict | None":
    """{currency, fx_regime, fx_local_per_usd, vat_pct, vat_note, source, source_url} أو None."""
    key = str(iso3 or "").strip().upper()
    r = _fiscal_index().get(key)
    if not r:
        return None
    return {"currency": _currency_index().get(key) or "", "fx_regime": r["fx_regime"],
            "fx_local_per_usd": _num(r["fx_local_per_usd"]) if r["fx_regime"] == "peg" else None,
            "vat_pct": _num(r["vat_pct"]), "vat_note": r.get("vat_note") or "",
            "source": r["source"], "source_url": r["source_url"]}


@functools.lru_cache(maxsize=None)
def _origin_index() -> dict:
    return {r["agreement"].strip(): r for r in _rows("origin_rules_l1.csv") if r.get("agreement")}


@functools.lru_cache(maxsize=None)
def _membership() -> dict:
    """عضويةُ الاتفاقيات: GCC من `silk_blocs.GCC` (المصدر الواحد للتكتّلات، DEF-2)، وغيرُه من
    `agreements_l1.csv`."""
    out: dict = {}
    for r in _rows("agreements_l1.csv"):
        ag = (r.get("agreement") or "").strip()
        if (r.get("status") or "").strip() == "member" and ag != "GCC":
            out.setdefault(r["iso3"].strip().upper(), set()).add(ag)
    from silk_blocs import GCC
    for iso in GCC:
        out.setdefault(iso, set()).add("GCC")
    return out


def fill_meta(meta: dict) -> dict:
    """يملأ الضريبة والصرف والعملة من الجدول **بلا دهس** ما في meta (الصريحُ يعلو)."""
    fis = fiscal((meta or {}).get("market_iso3") or "")
    if fis:
        for k, v in (("currency", fis["currency"] or None), ("fx_local_per_usd", fis["fx_local_per_usd"]),
                     ("vat_pct", fis["vat_pct"]), ("fiscal_source", fis["source_url"])):
            if meta.get(k) is None and v is not None:
                meta[k] = v
    return meta


def origin_rule(market_iso3: str) -> "dict | None":
    """قاعدةُ المنشأ التي تحكم إعفاءَ منتجٍ سعوديّ في السوق — أولُ اتفاقيةٍ مشتركة بالأولوية."""
    mem = _membership().get(str(market_iso3 or "").strip().upper()) or set()
    for ag in _SAUDI_AGREEMENTS:
        if ag in mem and ag in _origin_index():
            r = _origin_index()[ag]
            return {"agreement": ag, "min_value_added_pct": _num(r["min_value_added_pct"]),
                    "other_conditions": r.get("other_conditions") or "",
                    "source": r["source"], "source_url": r["source_url"]}
    return None
