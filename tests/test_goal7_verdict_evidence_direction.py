"""البند 7 من أمر إصلاح المحرّك — الحكم يتحرك مع الدليل عبر التشغيلات.

الدليل (direct reproduction — #10/#11 حليب×الأردن): الثقة 40%→20%،
المؤشرات المرصودة 108→87، الفجوات 9→15 — وكل ذلك ترافق مع **ترقية** الحكم
(«لا تدخل»→«دخول مشروط»). المطلوب حرفياً: لنفس (المنتج × السوق)، هبوط
الثقة + هبوط المؤشرات + ارتفاع الفجوات + ترقية الحكم = توقّف وبلاغ. هرمتي.
Run:
  python3 -m pytest tests/test_goal7_verdict_evidence_direction.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_consistency as C                             # noqa: E402
import silk_quality_gate as QG                           # noqa: E402


def _result(verdict, confidence, observed, gaps, product="حليب",
            market="الأردن"):
    findings = ([{"value": 1, "note": f"مؤشر {i}"} for i in range(observed)]
                + [{"value": None, "note": f"فجوة {i}"} for i in range(gaps)])
    return {"product": product,
            "market": {"name_ar": market, "iso3": "JOR"},
            "deep_research": {
                "missions": {"trade_flow": {"findings": findings}},
                "verdict": {"verdict": verdict, "confidence": confidence}}}


_PREV = _result("NO-GO", 0.40, 108, 9)         # تقرير #10
_CURR = _result("CONDITIONAL-GO", 0.20, 87, 15)  # تقرير #11


def test_verdict_rank_order_and_unrankables():
    assert C.verdict_rank("NO-GO") == 0
    assert C.verdict_rank("WATCH") == 1
    assert C.verdict_rank("CONDITIONAL-GO") == 2
    assert C.verdict_rank("GO") == 3
    assert C.verdict_rank("PRELIMINARY GO") == 3
    assert C.verdict_rank("") is None
    assert C.verdict_rank("INSUFFICIENT_DATA") is None


def test_evidence_stats_counts_observed_and_declared_gaps():
    s = C.evidence_stats(_PREV)
    assert s["observed"] == 108 and s["gaps"] == 9
    assert s["verdict_rank"] == 0 and s["confidence"] == 0.40


def test_acceptance_10_to_11_pattern_is_flagged():
    """قبول الأمر حرفياً: نمط #10→#11 بالضبط = تنافر مُبلَّغ بأرقامه."""
    out = C.direction_check(C.evidence_stats(_PREV), C.evidence_stats(_CURR))
    assert out["inconsistent"] is True
    for needle in ("108", "87", "9", "15", "NO-GO", "CONDITIONAL-GO"):
        assert needle in out["note"]


def test_upgrade_with_better_evidence_passes():
    better = _result("CONDITIONAL-GO", 0.55, 130, 5)
    out = C.direction_check(C.evidence_stats(_PREV),
                            C.evidence_stats(better))
    assert out["inconsistent"] is False


def test_downgrade_never_flags():
    worse_but_downgraded = _result("NO-GO", 0.10, 50, 30)
    out = C.direction_check(C.evidence_stats(_CURR),
                            C.evidence_stats(worse_but_downgraded))
    assert out["inconsistent"] is False


def test_unrankable_verdict_declares_incomparable():
    prev = _result("", None, 10, 2)
    out = C.direction_check(C.evidence_stats(prev), C.evidence_stats(_CURR))
    assert out["comparable"] is False and out["inconsistent"] is False


def test_history_lookup_matches_product_market_completed_only():
    rows = [
        {"id": 11, "product": "حليب", "market_name": "الأردن",
         "status": "running"},
        {"id": 10, "product": "حليب", "market_name": "الأردن",
         "status": "completed"},
        {"id": 9, "product": "تمور", "market_name": "الأردن",
         "status": "completed"},
    ]
    out = C.check_against_history(
        _CURR, analysis_id=11,
        _list=lambda: rows, _get=lambda i: {10: _PREV}.get(i))
    assert out["previous_analysis_id"] == 10
    assert out["inconsistent"] is True


def test_no_prior_run_is_a_declared_non_comparison():
    out = C.check_against_history(_CURR, analysis_id=1,
                                  _list=lambda: [], _get=lambda i: None)
    assert out["comparable"] is False and out["inconsistent"] is False
    assert "لا تشغيلة سابقة" in out["note"]


def test_gate_fails_an_inconsistent_run_and_names_the_prior():
    view = {"deep_research": {
        "missions": {},
        "verdict_consistency": {"inconsistent": True,
                                "previous_analysis_id": 10,
                                "note": "الحكم ترقّى بينما ساءت المؤشرات"},
        "report": {"text": "نص"}}, "markets": []}
    out = QG.run_quality_gate(view)
    hits = [f for f in out["findings"]
            if f["check"] == "verdict_evidence_direction"]
    assert hits and out["verdict"] == QG.FAIL
    assert "#10" in hits[0]["note"]


def test_gate_silent_when_consistent_or_unchecked():
    for vc in ({}, {"inconsistent": False, "checked": True}):
        view = {"deep_research": {"missions": {}, "verdict_consistency": vc,
                                  "report": {"text": "نص"}}, "markets": []}
        assert QG._check_verdict_evidence_direction(view) == []


def test_check_is_a_fail_trigger():
    assert "verdict_evidence_direction" in QG._REGRESSION_GUARD_FIRED


def test_view_passes_the_consistency_field_through():
    import silk_render as R
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    from canonical_netherlands import netherlands_research_blob
    blob = netherlands_research_blob()
    blob["deep_research"]["verdict_consistency"] = {"inconsistent": False,
                                                   "checked": True}
    dr = R.build_view(blob)["deep_research"]
    assert dr["verdict_consistency"]["checked"] is True
