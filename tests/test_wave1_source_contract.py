"""الموجة ١ — عقد المصدر + قِدم البيانات بطبقتين + تصنيف الفجوات G1–G4.

هرمتي بالكامل. يثبت: الحقول الجديدة اختيارية بقيم افتراضية (كل مواقع الإنشاء
القديمة سليمة)؛ المحوّلان؛ ملء الرابط من السجلّ العمومي لا اختلاقه؛ طبقتا
القِدم 3/7 مع توافق SILK_STALE_DATA_YEARS؛ نقص البيانات الوصفية لا يمسّ عرض
الرقم (تعديل مالك ٤)؛ فحصا البوابة الجديدان تحذيريان لا حاجبان.
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_staleness as S  # noqa: E402
from silk_data_layer import (  # noqa: E402
    GAP_G1, GAP_G2, GAP_G3, GAP_G4, DataPoint, classify_gap_class,
    datapoint_provenance, fact_to_datapoint)

_THIS_YEAR = datetime.date.today().year


class _Env:
    def __init__(self, **vals):
        self.vals, self.old = vals, {}

    def __enter__(self):
        for k, v in self.vals.items():
            self.old[k] = os.environ.get(k)
            os.environ.pop(k, None) if v is None else os.environ.update({k: v})
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.update({k: v})


# ── الحقول الجديدة اختيارية — لا كسر لأي موقع إنشاء قديم ────────────────────

def test_new_fields_default_empty_and_old_constructors_still_work():
    dp = DataPoint(value=1.0, source="UN Comtrade", confidence=0.8)
    assert dp.unit == "" and dp.url == ""
    assert dp.reference_period == "" and dp.retrieval_method == ""
    dp2 = DataPoint(value=2.0, source="X", confidence=0.5, unit="كجم",
                    url="https://example.org", reference_period="2023 CY",
                    retrieval_method="api")
    assert dp2.unit == "كجم" and dp2.retrieval_method == "api"


# ── المحوّلان ───────────────────────────────────────────────────────────────

def test_fact_to_datapoint_carries_unit_url_and_formula():
    fact = {"metric": "lead_time_days", "value": 3.2, "unit": "يوم",
            "modeled": True, "formula": "IC.IMP.TMBC ÷ 24",
            "sources": [{"source": "World Bank", "confidence": 0.7,
                         "url": "https://data.worldbank.org/",
                         "retrieved_at": "2026-08-19"}],
            "note": "زمن التخليص"}
    dp = fact_to_datapoint(fact)
    assert dp.value == 3.2 and dp.unit == "يوم"
    assert dp.url == "https://data.worldbank.org/"
    assert "مستنتَج" in dp.note and "÷" in dp.note
    assert dp.retrieval_method == "derived"


def test_fact_to_datapoint_failure_stays_declared_gap():
    dp = fact_to_datapoint({"metric": "x", "value": None, "sources": [],
                            "note": "فجوة معلنة"})
    assert dp.value is None and dp.confidence == 0.0


def test_datapoint_provenance_fills_url_from_registry_never_fabricates():
    dp = DataPoint(value=5.0, source="UN Comtrade", confidence=0.9)
    prov = datapoint_provenance(dp)
    assert prov["url"] == "https://comtradeplus.un.org/"
    unknown = datapoint_provenance(
        DataPoint(value=1.0, source="مصدر مجهول", confidence=0.5))
    assert unknown["url"] == ""  # لا رابط مختلَق


# ── القِدم بطبقتين 3/7 ──────────────────────────────────────────────────────

def test_vintage_tiers_default_3_and_7():
    with _Env(SILK_VINTAGE_WARN_YEARS=None, SILK_VINTAGE_HARD_YEARS=None,
              SILK_STALE_DATA_YEARS=None):
        assert S.vintage_tier(_THIS_YEAR - 1) == S.VINTAGE_FRESH
        assert S.vintage_tier(_THIS_YEAR - 4) == S.VINTAGE_WARN
        assert S.vintage_tier(_THIS_YEAR - 8) == S.VINTAGE_EXPIRED
        assert S.vintage_tier(None) == S.VINTAGE_FRESH  # لا سنة = لا وسم زور


def test_stale_data_years_acts_as_warn_tier_backward_compat():
    """N القديمة (عمر ≥ N متقادم) تُترجَم N−1 (عمر > N−1) — نفس سنة الحدود
    بالضبط لآليّتي التقادُم والقِدم (قفل مراجعة §58)."""
    with _Env(SILK_STALE_DATA_YEARS="5", SILK_VINTAGE_WARN_YEARS=None,
              SILK_VINTAGE_HARD_YEARS=None):
        assert S.vintage_warn_years() == 4
        assert S.vintage_tier(_THIS_YEAR - 4) == S.VINTAGE_FRESH
        # سنة الحدود: is_stale_year يعتبرها متقادمة، والقِدم يحذّر عندها أيضاً.
        assert S.is_stale_year(_THIS_YEAR - 5)
        assert S.vintage_tier(_THIS_YEAR - 5) == S.VINTAGE_WARN
        assert S.vintage_tier(_THIS_YEAR - 6) == S.VINTAGE_WARN


def test_widened_legacy_window_never_brands_expired_below_it():
    """مالك وسّع النافذة إلى 10: بيانات عمرها 8–10 لا تُوسم «منتهية» —
    الطبقة الصلبة تُرفع فوق التحذير (قفل مراجعة §58)."""
    with _Env(SILK_STALE_DATA_YEARS="10", SILK_VINTAGE_WARN_YEARS=None,
              SILK_VINTAGE_HARD_YEARS=None):
        assert S.vintage_tier(_THIS_YEAR - 8) == S.VINTAGE_FRESH
        assert S.vintage_tier(_THIS_YEAR - 10) == S.VINTAGE_WARN
        assert S.vintage_tier(_THIS_YEAR - 11) == S.VINTAGE_EXPIRED


def test_vintage_caveat_texts():
    with _Env(SILK_VINTAGE_WARN_YEARS=None, SILK_VINTAGE_HARD_YEARS=None,
              SILK_STALE_DATA_YEARS=None):
        assert S.vintage_caveat(_THIS_YEAR - 1) == ""
        assert "أقدم من" in S.vintage_caveat(_THIS_YEAR - 4)
        hard = S.vintage_caveat(_THIS_YEAR - 9)
        assert "لا تُبنى عليها خلاصة" in hard


# ── تصنيف الفجوات G1–G4 ─────────────────────────────────────────────────────

def test_gap_class_g1_to_g4():
    assert classify_gap_class("بيان غير مجموع في أي مصدر") == GAP_G1
    assert classify_gap_class("متاح خلف اشتراك مدفوع") == GAP_G2
    assert classify_gap_class("تعذّر الجلب — 429") == GAP_G3
    assert classify_gap_class("فشل عام", status="fetch_failed") == GAP_G3
    assert classify_gap_class("هذا البند لا ينطبق على المنتج") == GAP_G4


# ── العرض: البطاقة تمرّ والقيمة لا تُحجب أبداً (تعديل مالك ٤) ───────────────

def test_components_detail_carries_contract_fields_and_never_hides_value():
    import silk_render as R
    result = {
        "product": "تمور", "hs_code": "080410", "year": 2024,
        "markets": [{
            "country": "هولندا", "iso3": "NLD", "total_score": 0.7,
            "confidence": 0.8, "recommendation": "ادرس",
            "components": {
                "الواردات": DataPoint(
                    value=9.9e6, source="UN Comtrade", confidence=0.9,
                    note="year=2015", retrieved_at="2026-08-19",
                    data_year=2015, unit="USD"),
                # بند قديم الشكل — بلا أي حقل جديد: يُعرض كما هو، WARN فقط.
                "الدخل": DataPoint(value=57000, source="مصدر مجهول",
                                   confidence=0.7),
            }}],
    }
    view = R.build_view(result)
    details = {d["name"]: d for d in view["markets"][0]["components_detail"]}
    imp = details["الواردات"]
    assert imp["unit"] == "USD" and imp["data_year"] == 2015
    assert imp["url"] == "https://comtradeplus.un.org/"
    assert "لا تُبنى عليها خلاصة" in imp["vintage"]  # طبقة صلبة ضمن البند
    old = details["الدخل"]
    assert old["value"] == 57000       # نقص البيانات الوصفية لا يحجب القيمة
    assert old["url"] == "" and old["vintage"] == ""


def test_gap_register_attached_and_classified():
    import silk_render as R
    from tools.canonical_netherlands import netherlands_research_blob
    dr = R.build_view(netherlands_research_blob())["deep_research"]
    reg = dr.get("gap_register")
    assert isinstance(reg, list)
    for row in reg:
        assert row["gap_class"] in (GAP_G1, GAP_G2, GAP_G3, GAP_G4)
        assert row["gap_class_label"]


# ── البوابة: الفحصان الجديدان تحذيريان لا حاجبان ────────────────────────────

def test_new_gate_checks_are_warn_never_fail():
    import silk_quality_gate as Q
    assert "source_contract_incomplete" not in Q.FAIL_TRIGGER_CHECKS
    assert "vintage_expired_facts_present" not in Q.FAIL_TRIGGER_CHECKS
    dr = {"missions": {"m": {"summary": "ن", "findings": [
        {"value": float(i), "source": "مصدر مجهول", "confidence": 0.5,
         "note": "", "retrieved_at": "", "data_year": _THIS_YEAR - 20}
        for i in range(1, 12)]}},
        "report": {"text": "نص"}, "verdict": {}}
    f1 = Q._check_source_contract_completeness(dr)
    f2 = Q._check_vintage_expired_facts(dr)
    assert f1 and f1[0]["repairable"] is True
    assert f2 and f2[0]["repairable"] is True


# ── أقفال المراجعة الذاتية §58 (الموجة ١) ───────────────────────────────────

def test_429_matches_as_token_not_substring():
    assert classify_gap_class("تعذّر مؤقت 429 من المصدر") == GAP_G3
    assert classify_gap_class("رسوم التسجيل 4290 ريال غير معروفة") == GAP_G1
    assert classify_gap_class("منذ 1429هـ لا بيانات") == GAP_G1


def test_store_served_fact_labeled_store_not_api():
    fact = {"metric": "x", "value": 5.0,
            "sources": [{"source": "UN Comtrade", "confidence": 0.8}],
            "note": "من المخزن — جُلب 2026-07-01"}
    assert fact_to_datapoint(fact).retrieval_method == "store"


def test_vintage_caveat_reads_legacy_year_marker_not_only_data_year():
    """بند مخزون قديم (data_year=None، الملاحظة تحمل year=2015) يُوسَم قِدماً
    في العرض — نفس ما تراه البوابة (قفل مراجعة §58)."""
    import silk_render as R
    with _Env(SILK_VINTAGE_WARN_YEARS=None, SILK_VINTAGE_HARD_YEARS=None,
              SILK_STALE_DATA_YEARS=None):
        result = {"product": "x", "hs_code": "080410", "year": 2024,
                  "markets": [{"country": "م", "iso3": "NLD",
                               "total_score": 0.5, "confidence": 0.5,
                               "recommendation": "ادرس",
                               "components": {"الدخل": DataPoint(
                                   value=1.0, source="World Bank",
                                   confidence=0.7, note="… year=2015",
                                   retrieved_at="2025-01-01")}}]}
        d = R.build_view(result)["markets"][0]["components_detail"][0]
        assert "لا تُبنى عليها خلاصة" in d["vintage"]
