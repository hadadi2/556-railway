"""أرقام القرار الحتمية لنمط «دراسة السوق» — deterministic decision numbers (P0-T / P1-6…P1-9).

المدخل: حالة بصيغة `evals/golden_set/malaysia_coffee_fixture.json` (بيانات مرصودة
بمصادرها). المخرج: قاموس فراغات جاهزة للقوالب — كل رقم محسوب هنا لا في النموذج،
والمتعذر يبقى `None` (فجوة معلنة). stdlib فقط.

- تفكيك نمو القيمة إلى كمية وسعر مع استبعاد سنوات الوزن الشاذ (P1-7).
- حدّا مؤشر التركّز من الحصص المعروضة (P1-9): الأدنى Σs²، والأعلى يوزّع الباقي
  على موردين لا تتجاوز حصة أيٍّ منهم أصغر حصة معروضة.
- الكسور اللفظية والاتجاهات من الإشارة (P1-6).
"""
from __future__ import annotations

import csv
import math
import os

from silk_study_arabic import fraction_word, ratio_change_pct

ROOT = os.path.dirname(os.path.abspath(__file__))
NEAR_KM = 3000.0


# ── مسافات العواصم ────────────────────────────────────────────────────────
def _geodist():
    path = os.path.join(ROOT, "data", "geodist_l1.csv")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        rows = [ln for ln in f if not ln.startswith("#")]
    for r in csv.DictReader(rows):
        out[(r["iso3_a"], r["iso3_b"])] = (float(r["distcap_km"]), r["basis"])
    return out


def is_near(a: str, b: str, table=None) -> bool:
    """near = مسافة عواصم ≤ 3,000 كم و basis=capital؛ غياب الصف أو centroid = far."""
    t = table if table is not None else _geodist()
    row = t.get((a, b)) or t.get((b, a))
    return bool(row and row[1] == "capital" and row[0] <= NEAR_KM)


# ── مؤشر التركّز ──────────────────────────────────────────────────────────
def hhi_bounds(shares: list[float]) -> tuple[float, float]:
    """(أدنى، أعلى) من الحصص المعروضة بالمئة. الأعلى: الباقي r يوزَّع على موردين
    حصة كلٍّ منهم ≤ s_min: floor(r/s_min)·s_min² + (r mod s_min)²."""
    s = [float(x) for x in shares if x is not None]
    if not s:
        raise ValueError("no shares")
    base = sum(x * x for x in s)
    r = max(0.0, 100.0 - sum(s))
    s_min = min(s)
    if s_min <= 0:
        return base, base + r * r
    k = math.floor(r / s_min)
    rem = r - k * s_min
    return base, base + k * s_min * s_min + rem * rem


def hhi_consistent(hhi: float, shares: list[float]) -> bool:
    lo, hi = hhi_bounds(shares)
    return lo - 1e-9 <= hhi <= hi + 1e-9


def hhi_band(lo: float, hi: float) -> str:
    """below_1500 / straddles_1500 / between_1500_2500 / straddles_2500 / above_2500 (قواعد s1_hhi)."""
    if hi < 1500:
        return "below_1500"
    if lo < 1500 <= hi:
        return "straddles_1500"
    if 1500 <= lo and hi < 2500:
        return "between_1500_2500"
    if lo < 2500 <= hi:
        return "straddles_2500"
    return "above_2500"


def _round100(x: float) -> int:
    return int(round(x / 100.0)) * 100


# ── السلسلة والتفكيك ──────────────────────────────────────────────────────
_EMPTY_SHAPE = {k: None for k in ("y_first", "v_first", "y_last", "v_last", "g_first_last", "trend",
                                  "monotone", "dip_year", "dip_value", "jump_year", "peak_year", "last_yoy")}


def series_shape(series: list[dict]) -> dict:
    vals = [(r["year"], r["value_musd"]) for r in (series or [])
            if r.get("value_musd") is not None and r.get("complete", True)]
    if len(vals) < 2:
        return dict(_EMPTY_SHAPE, trend="flat")
    first_y, first_v = vals[0]
    last_y, last_v = vals[-1]
    g = ratio_change_pct(first_v, last_v)
    trend = "up" if g > 5 else ("down" if g < -5 else "flat")
    monotone = all(vals[i][1] <= vals[i + 1][1] for i in range(len(vals) - 1)) if trend == "up" else \
        all(vals[i][1] >= vals[i + 1][1] for i in range(len(vals) - 1)) if trend == "down" else False
    dips = [(y, v) for (y, v) in vals[1:] if v < first_v]
    dip = min(dips, key=lambda t: t[1]) if dips else None
    jumps = [(vals[i + 1][0], vals[i + 1][1] / vals[i][1] - 1) for i in range(len(vals) - 1)]
    jump = max(jumps, key=lambda t: t[1]) if jumps else None
    peak = max(vals, key=lambda t: t[1])
    return {"y_first": first_y, "v_first": first_v, "y_last": last_y, "v_last": last_v,
            "g_first_last": g, "trend": trend, "monotone": monotone,
            "dip_year": dip[0] if dip else None, "dip_value": dip[1] if dip else None,
            "jump_year": jump[0] if jump else None, "peak_year": peak[0],
            "last_yoy": ratio_change_pct(vals[-2][1], last_v) if len(vals) > 1 else None}


def decomposition(series: list[dict]) -> dict:
    """نافذة السنوات ذات الوزن السليم؛ dv/dp/dq؛ حصة الكمية من نمو القيمة؛ النسخة."""
    ok = [r for r in (series or []) if r.get("kg") and not r.get("weight_anomaly") and r.get("complete", True)]
    excluded = [r["year"] for r in series if r.get("weight_anomaly")]
    if len(ok) < 3:
        return {"variant": "not_decomposable", "reason": "غياب بيانات الوزن" if not ok else "عدم موثوقية بيانات الوزن في أكثر من سنة"}
    a, b = ok[0], ok[-1]
    p_a = a["value_musd"] * 1e6 / a["kg"]
    p_b = b["value_musd"] * 1e6 / b["kg"]
    dv = ratio_change_pct(a["value_musd"], b["value_musd"])
    dp = ratio_change_pct(p_a, p_b)
    dq = ratio_change_pct(a["kg"], b["kg"])
    q_share = dq / dv if dv else None
    if dv > 0 and dp < 0:
        variant = "value_up_price_down"
    elif dv < 0 and dp > 0:
        variant = "value_down_price_up"
    elif abs(dq) <= 0.2 * abs(dv):
        variant = "price_led"
    elif dv > 0 and dq > 0:
        variant = "decomposable_with_excluded_last" if excluded else "decomposable_full"
    elif dv < 0 and dq < 0:
        variant = "decomposable_down"
    else:
        variant = "price_led"
    return {"variant": variant, "y_a": a["year"], "y_b": b["year"], "dv": dv, "dp": dp, "dq": dq,
            "p_a": p_a, "p_b": p_b, "q_share": q_share, "y_excl": excluded[-1] if excluded else None,
            "span_years": b["year"] - a["year"]}


# ── القرار ────────────────────────────────────────────────────────────────
DECISION_WORDS = {"entry": "دخول", "conditional": "دخول مشروط", "defer": "إرجاء", "no_entry": "عدم دخول"}


def market_def_key(decision: str, trend: str) -> str:
    if decision == "no_entry":
        return "no_entry"
    if decision == "defer":
        return "defer"
    return trend  # down / flat / up


# ── التجميع ───────────────────────────────────────────────────────────────
DOMINANT_SHARE_PCT = 30.0


def counter_kind(n: dict, shape: dict) -> str:
    """P3-6: أقوى دليل مضاد للدخول بترتيب ثابت — غياب السعودية مع منتجَين إقليميين،
    ثم هيمنة مورد (≥30%)، ثم تراجع السلسلة، ثم مركز إعادة تصدير، وإلا «no_counter»."""
    if n.get("saudi_absent") and n.get("producers_two_share") is not None:
        return "saudi_absent"
    if (n.get("top1_share") or 0) >= DOMINANT_SHARE_PCT:
        return "dominant_supplier"
    if shape.get("trend") == "down":
        return "declining"
    if n.get("hub"):
        return "hub"
    return "no_counter"      # لا «none»: القالب يقرأ none قيمةً فارغة


def counter_follow(kind: str, decision: str) -> str:
    """مفتاح فقرة المتابعة في «ثامناً»: فقرات المرجع الأربع خاصة بحجة غياب
    السعودية؛ غيرها يأخذ متابعةً عامة بحسب اتجاه القرار، ولا متابعة بلا حجة."""
    if kind == "saudi_absent":
        return decision
    if kind == "no_counter":
        return "none_needed"
    return "other_go" if decision in ("entry", "conditional") else "other_stop"


def compute(case: dict) -> dict:
    """كل الفراغات الرقمية للقوالب من حالة واحدة."""
    imp = case.get("imports") or {}
    shape = series_shape(imp.get("series") or [])
    dec = decomposition(imp.get("series") or [])
    sup = case.get("suppliers") or {}
    top_all = sup.get("top") or []
    shares = [t["share_pct"] for t in top_all if t.get("share_pct") is not None]
    lo, hi = hhi_bounds(shares) if shares else (None, None)
    top3 = top_all[:3]
    top3_sum = sum(t["share_pct"] for t in top3) if top3 else None
    geo = _geodist()
    near = len(top3) >= 3 and all(is_near(case["market"].get("iso3") or "", t.get("iso3") or "", geo) for t in top3)
    hub = next((t for t in top_all if t.get("kind") == "reexport_hub"), None)
    producers = [t for t in top_all if t.get("kind") == "producer"]
    decision = (case.get("decision") or {}).get("type") or "defer"
    n = {
        **{f"shape_{k}": v for k, v in shape.items()},
        **{f"dec_{k}": v for k, v in dec.items()},
        "supplier_count": sup.get("count"),
        "saudi_share": sup.get("saudi_share_pct"),
        # الغياب حقيقة فقط حين الحصة صفر مثبت؛ None (مجهولة) لا تعني غياباً.
        "saudi_absent": sup.get("saudi_share_pct") == 0,
        "top_n": len(top3), "top3_share": top3_sum,
        "top3_frac": fraction_word(top3_sum / 100.0) if top3_sum is not None else None,
        "top3_near": near,
        "hhi_lo": lo, "hhi_hi": hi,
        "hhi_lo_100": _round100(lo) if lo is not None else None, "hhi_hi_100": _round100(hi) if hi is not None else None,
        "hhi_band": hhi_band(_round100(lo), _round100(hi)) if lo is not None else "not_computed",
        "top1_partner": top_all[0]["name_ar"] if top_all else None, "top1_share": top_all[0]["share_pct"] if top_all else None,
        "origin_word": "الإقليميين" if near else "الرئيسيين",
        "hub": hub, "producers_two_share": sum(t["share_pct"] for t in producers[:2]) if len(producers) >= 2 else None,
        "decision": decision, "decision_word": DECISION_WORDS[decision],
        "market_def": market_def_key(decision, shape["trend"]),
        "req_count": len((case.get("decision") or {}).get("requirements") or []),
        "last_yoy": imp.get("last_yoy_pct") if imp.get("last_yoy_pct") is not None else shape["last_yoy"],
    }
    n["counter_kind"] = counter_kind(n, shape)
    n["counter_follow"] = counter_follow(n["counter_kind"], decision)
    if dec.get("q_share") is not None:
        n["q_share_frac"] = fraction_word(dec["q_share"])
        n["q_growth_frac"] = fraction_word(abs(dec["dq"]) / 100.0, definite=True)
    if hub:
        n["hub_frac"] = fraction_word(hub["share_pct"] / 100.0)
    if n["producers_two_share"] is not None:
        n["producers_two_frac"] = fraction_word(n["producers_two_share"] / 100.0)
    return n
