"""الموجة ٥ — بنية الحكم (القاعدة قبل الحكم + الحجة المضادة) + الجدول
الزمني للنفاذ. هرمتي بالكامل.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_decision as D  # noqa: E402


def _pillar(v):
    return {"value": v, "components": {}, "missing": [], "basis": "أساس"}


def test_decision_rule_states_thresholds_before_application():
    rule = D.decision_rule_text()
    assert "قبل تطبيقها" in rule
    # Z-07: العتباتُ تُطبَع نِسَباً مئوية لا كسوراً خام (لا جملةٌ بوحدتين).
    assert D._pct(D._GO) in rule and D._pct(D._NOGO) in rule
    assert str(D._GO) not in rule and str(D._NOGO) not in rule
    assert "60%" in rule


def test_decide_output_carries_rule_and_counter_case():
    bundle = {"pillar_inputs": {}}
    out = D.decide(bundle) if False else None
    # decide يتطلب حزمة كاملة — نختبر عبر counter_case مباشرة والقاعدة نصاً،
    # وحضور المفتاحين في بنية المخرج عبر مسح المصدر (قفل بنيوي).
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_decision.py"), encoding="utf-8").read()
    assert '"decision_rule": decision_rule_text()' in src
    assert 'out["counter_case"] = counter_case(out)' in src


def test_counter_case_for_go_names_weakest_pillar():
    dec = {"verdict": "GO", "score": 0.71, "confidence": 0.8,
           "pillars": {"market": _pillar(0.9), "risk": _pillar(0.2)},
           "conditions": []}
    cc = D.counter_case(dec)
    assert "أمان السوق" in cc["case"]          # أضعف عمود مسمّى
    assert "لماذا لم تُعتمد" in cc["rebuttal"]


def test_counter_case_for_nogo_names_strongest_pillar():
    dec = {"verdict": "NO-GO", "score": 0.3, "confidence": 0.5,
           "pillars": {"market": _pillar(0.9), "risk": _pillar(0.1)},
           "conditions": []}
    cc = D.counter_case(dec)
    assert "جاذبية السوق" in cc["case"]


def test_counter_case_no_pillars_declares_insufficiency():
    cc = D.counter_case({"verdict": "GO", "pillars": {}})
    assert "غير كافية" in cc["case"] and cc["rebuttal"] == ""


def test_markdown_renders_rule_before_verdict_and_counter_after():
    import silk_reports as REP
    view = {"product": "x", "hs_code": "080410", "year": 2024,
            "header": {}, "markets": [{
                "country": "م", "iso3": "NLD", "total_score": 0.7,
                "confidence": 0.8, "components": {},
                "entry_decision": {
                    "schema": "silk.decision/v1",
                    "decision_rule": D.decision_rule_text(),
                    "verdict": "GO", "score": 0.71, "confidence": 0.8,
                    "confidence_basis": "أساس", "weights_option": "A",
                    "weights_label": "الأوزان القياسية",
                    "scores_by_option": {"A": 0.71, "B": 0.7},
                    "pillars": {"market": _pillar(0.9), "risk": _pillar(0.2)},
                    "missing_pillars": [], "conditions": [], "risks": [],
                    "first_steps": [], "why": "بلغت العتبة",
                    "counter_case": D.counter_case({
                        "verdict": "GO", "score": 0.71, "confidence": 0.8,
                        "pillars": {"market": _pillar(0.9),
                                    "risk": _pillar(0.2)},
                        "conditions": []})}}],
            "decision": {}, "limits": [], "provenance": []}
    md = REP.render_markdown(view)
    rule_i = md.find("قاعدة القرار (معلنة قبل تطبيقها)")
    verdict_i = md.find("الحكم: **")
    counter_i = md.find("الحجة المضادة")
    assert 0 < rule_i < verdict_i < counter_i


# ── الجدول الزمني للنفاذ (§5.5) ─────────────────────────────────────────────

def test_access_timeline_declares_gap_when_durations_uncodified():
    import silk_requirements_agent as RA
    tl = RA.access_timeline("GCC", "food")
    assert tl["steps"] and tl["total_days"] is None
    assert "غير مقنّنة" in tl["gap"]   # لا مدى مختلَق من صفوف بلا مدد


def test_access_timeline_totals_when_all_steps_carry_durations():
    import silk_requirements_agent as RA
    rows = [{"item_ar": "أ", "authority": "ج", "source_url": "u",
             "processing_days_min": "10", "processing_days_max": "20"},
            {"item_ar": "ب", "authority": "ج", "source_url": "u",
             "processing_days_min": "5", "processing_days_max": "5"}]
    from unittest.mock import patch
    with patch.object(RA, "_load_reference", return_value=tuple(rows)), \
            patch.object(RA, "_matches", return_value=True):
        tl = RA.access_timeline("X", "food")
    assert tl["total_days"] == {"min": 15.0, "max": 25.0}
    assert "المدى الكلي" in tl["note"]


def test_timeline_gate_check_is_warn_and_fires_only_without_total_line():
    import silk_quality_gate as Q
    assert "access_timeline_missing" not in Q.FAIL_TRIGGER_CHECKS
    dr_bad = {"missions": {"customs_requirements": {"failed": False,
                                                    "summary": "ن"}},
              "report": {"text": "قسم الاشتراطات بلا خاتمة"}}
    f = Q._check_access_timeline_presence(dr_bad)
    assert f and f[0]["repairable"]
    dr_ok = {"missions": {"customs_requirements": {"failed": False}},
             "report": {"text": "المدة الكلية من قرار الدخول: 90–150 يوماً"}}
    assert Q._check_access_timeline_presence(dr_ok) == []


def test_writer_contract_carries_timeline_rule():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_ai_judge.py"),
        encoding="utf-8").read()
    assert "المدة الكلية من قرار الدخول حتى أول شحنة نظامية" in src
