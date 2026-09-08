"""البند 6 من أمر إصلاح المحرّك — تناقض التسعير لا يمرّ بلا تعليق.

الدليل (direct reproduction — تقرير #11): أقصى سعر مصنع $0.3274/كجم مقابل
سعر استيراد مرجعي مرصود $0.81/كجم — أدنى بـ60% أي «لا منافسة سعرية قائمة»،
ومع ذلك أوصى التقرير باعتماده أساساً للتفاوض بلا أي تعليق. المطلوب حرفياً:
انخفاض >20% تحت متوسط سعر الاستيراد المرصود = تحذير إلزامي + حظر اقتراح
الرقم أساساً تفاوضياً. هرمتي. Run:
  python3 -m pytest tests/test_goal6_pricing_contradiction.py -q
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_economics as E                               # noqa: E402
import silk_quality_gate as QG                           # noqa: E402


def _dr(shelf_note, ref_price=0.81, fx=None, shelf_value=0.60):
    """تشغيلة دنيا: سعر رف + متوسط استيراد كومتريد بصيغته الحرفية + صرف."""
    risk = []
    if fx is not None:
        risk.append({"value": fx, "source": "World Bank", "confidence": 0.9,
                     "note": f"[risk] سعر الصرف الرسمي {fx} "
                             "(وحدة محلية لكل دولار) — PA.NUS.FCRF سنة 2023"})
    return {"missions": {
        "pricing_scout": {"findings": [{"value": shelf_value,
                                        "note": shelf_note}]},
        "trade_flow": {"findings": [
            {"value": ref_price, "source": "UN Comtrade", "confidence": 0.7,
             "note": "HS040120 متوسط سعر استيراد الأردن 2023 (القيمة "
                     "الإجمالية ÷ الوزن الصافي بالكجم) — نطاق جملة مرجعي"}]},
        "risk_news": {"findings": risk}}}


def test_acceptance_shortfall_over_20pct_emits_mandatory_warning():
    """قبول الأمر حرفياً: EXW محوَّل للدولار أدنى بـ>20% من متوسط الاستيراد
    ⇒ `pricing_contradiction` بنصّ تحذير يحظر الأساس التفاوضي.
    الحساب: رف 0.60 دينار/كجم ÷ 1.68 (سيناريو متوسط) ÷ 0.71 = ‎$0.503
    مقابل مرجع $0.81 ⇒ عجز ~38%."""
    eco = E.economics_view(
        _dr("سعر رف عبوة 1 كجم بسعر 0.60 دينار في متجر", fx=0.71))
    pc = eco["pricing_contradiction"]
    assert pc is not None and pc["shortfall_pct"] > 20
    assert "لا يصلح هذا الرقم أساساً للتفاوض" in pc["note"]
    assert eco["reverse_solve"]["max_exw_usd"] == pc["max_exw_usd"]


def test_no_contradiction_when_exw_is_competitive():
    """مرجع استيراد منخفض ⇒ EXW فوق 80% منه ⇒ لا تناقض."""
    eco = E.economics_view(
        _dr("سعر رف عبوة 1 كجم بسعر 4.50 دينار في متجر",
            ref_price=0.5, fx=0.71, shelf_value=4.5))
    assert eco["pricing_contradiction"] is None
    # وسعرٌ منافس فعلاً (فوق 80% من المرجع) لا يتناقض
    eco2 = E.economics_view(
        _dr("سعر رف عبوة 1 كجم بسعر 0.90 دينار في متجر", fx=0.71,
            shelf_value=0.90))
    assert eco2["pricing_contradiction"] is None


def test_missing_fx_declares_the_gap_not_a_guess():
    eco = E.economics_view(
        _dr("سعر رف عبوة 1 كجم بسعر 4.50 دينار في متجر", fx=None))
    assert eco["pricing_contradiction"] is None
    gap = [g for g in eco["gaps"] if "التنافسية السعرية" in g]
    assert gap and "سعر الصرف" in gap[0]


def test_usd_anchor_compares_directly_without_fx():
    eco = E.economics_view(
        _dr("سعر رف عبوة 1 كجم بسعر 0.60 دولار في متجر", fx=None))
    assert eco["pricing_contradiction"] is not None


def test_fx_rate_fact_is_appended_by_the_augment():
    """إلحاق الصرف (البند 3) صار يودع آخر سعر رسمي حقيقةً مستقلة."""
    import silk_missions as sm
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    report = AgentReport("LLMMissionAgent:risk_news", [], False, "ملخص")
    series = {2025: 0.71, 2024: 0.71, 2023: 0.71}

    def fake_wb(iso3, ind, year=None):
        return DataPoint(series.get(year), "World Bank", 0.9, f"{ind} {year}")

    with mock.patch("silk_data_layer.world_bank", side_effect=fake_wb), \
         mock.patch("silk_store.get_indicator", return_value=None):
        sm._augment_risk_news_fx(report, "JOR")
    rate = [dp for dp in report.findings if "سعر الصرف الرسمي" in dp.note]
    assert len(rate) == 1 and rate[0].value == 0.71
    assert "2025" in rate[0].note                    # سنة السعر معلنة


def _view(pc, text):
    return {"deep_research": {
        "missions": {}, "economics": {"pricing_contradiction": pc},
        "report": {"text": text}}, "markets": []}


_PC = {"max_exw_usd": 0.3274, "reference_import_price_usd_kg": 0.81,
       "shortfall_pct": 59.6,
       "note": "تحذير: … لا يصلح هذا الرقم أساساً للتفاوض"}


def test_gate_fails_a_body_without_the_mandatory_warning():
    out = QG.run_quality_gate(_view(_PC, "نص تسعير يذكر 0.3274 بلا تحذير."))
    hits = [f for f in out["findings"]
            if f["check"] == "pricing_contradiction_flagged"]
    assert hits and out["verdict"] == QG.FAIL


def test_gate_fails_a_negotiating_baseline_suggestion():
    body = ("تحذير: المنافسة السعرية غير قائمة عملياً، لا يصلح هذا الرقم "
            "أساساً للتفاوض.\nنوصي مع ذلك باعتماد 0.3274 أساساً للتفاوض "
            "مع الموزعين.")
    out = QG.run_quality_gate(_view(_PC, body))
    hits = [f for f in out["findings"]
            if f["check"] == "pricing_contradiction_flagged"]
    assert hits and "تفاوض" in hits[0]["note"]


def test_gate_passes_a_body_carrying_the_warning_verbatim():
    body = ("تحذير: أقصى سعر مصنع قابل للمنافسة (0.3274 دولار/كجم) أدنى "
            "بنسبة 59.6% من متوسط سعر الاستيراد المرصود — المنافسة السعرية "
            "غير قائمة عملياً، ولا يصلح هذا الرقم أساساً للتفاوض.")
    assert QG._check_pricing_contradiction_flagged(_view(_PC, body)) == []


def test_gate_silent_without_a_computed_contradiction():
    assert QG._check_pricing_contradiction_flagged(
        _view(None, "نوصي باعتماد السعر أساساً للتفاوض.")) == []


def test_check_is_a_fail_trigger():
    assert "pricing_contradiction_flagged" in QG._REGRESSION_GUARD_FIRED
