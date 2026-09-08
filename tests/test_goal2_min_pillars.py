"""البند 2 من أمر إصلاح المحرّك — لا درجةَ موزونة بأقل من ٣ أعمدة.

الدليل (direct reproduction — تقريرا #10/#11): «درجة موزونة 84%» بعمودٍ واحد
محسوب و«26%» بعمودين — متوسّطٌ موزون على أوزانٍ فارغة رقمٌ بلا معنى، وحكمٌ
آليّ مبنيّ عليه أخطر منه. القاعدة: أقل من الحد الأدنى (3/5، `SILK_MIN_SCORED_
PILLARS`) ⇒ لا رقم ولا حكم آلي — «بيانات غير كافية» بأسماء الغائب.
هرمتي. Run:
  python3 -m pytest tests/test_goal2_min_pillars.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_decision as D                                # noqa: E402
import silk_deep_pillars as DP                           # noqa: E402

_ONE = {"competition_intensity": {"hhi": 7118, "top_supplier_share_pct": 84.0}}
_TWO = {**_ONE, "market_attractiveness": {"tam_usd": 6_950_000,
                                          "import_cagr_pct": -12.0}}
_THREE = {**_TWO, "risk": {"political_stability_wgi": -0.5,
                           "regulatory_quality_wgi": 0.1,
                           "logistics_lpi": 2.69}}


def test_acceptance_one_pillar_yields_no_score_and_no_verdict():
    d = D.decide({"coverage": 1.0, "pillar_inputs": _ONE})
    assert d["score"] is None
    assert d["verdict"] == ""
    assert d["confidence"] is None
    assert d["insufficient_pillars"] is True
    assert all(v is None for v in d["scores_by_option"].values())
    # الغائب مُسمّى بالعربية للقارئ
    assert "الغائب" in d["why"] and "جاذبية السوق" in d["why"]


def test_two_pillars_still_insufficient():
    d = D.decide({"coverage": 1.0, "pillar_inputs": _TWO})
    assert d["score"] is None and d["verdict"] == ""


def test_three_pillars_score_and_verdict_return():
    d = D.decide({"coverage": 1.0, "pillar_inputs": _THREE})
    assert isinstance(d["score"], float)
    assert d["verdict"] in ("GO", "CONDITIONAL-GO", "NO-GO")


def test_zero_pillars_no_longer_fabricates_a_nogo():
    """الفرع القديم كان يُصدر NO-GO من لا-بيانات — حكمٌ من عدمٍ يُلغى."""
    d = D.decide({"coverage": 1.0, "pillar_inputs": {}})
    assert d["verdict"] == "" and d["score"] is None


def test_insufficient_decision_is_never_promoted_to_the_artefact():
    """`promote_engine_verdict` يترك قاموسَ الحكم كما هو حرفياً — يبقى سطرُ
    التغطية («الحالة») لا توصية آلية."""
    dec = D.decide({"coverage": 1.0, "pillar_inputs": _ONE})
    jury = {"verdict": "PRELIMINARY / INCONCLUSIVE", "basis": "data_coverage",
            "note": "تنبيه"}
    assert DP.promote_engine_verdict(jury, dec) == jury


def test_view_precedence_rejects_empty_verdict_row_decision():
    """قفل مسار العرض (silk_render.py:2360): صفٌّ بقرارٍ حكمُه فارغ لا يحلّ
    محلّ قراءة التغطية — القفل نصّي لأن التدفق الكامل يحتاج مدوّنة كاملة."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_render.py"), encoding="utf-8").read()
    assert '_row_dec.get("schema") and not _row_dec.get("error")' in src
    assert '_row_dec.get("verdict")' in src


def test_tuning_valve_lowers_the_floor_explicitly(monkeypatch):
    monkeypatch.setenv("SILK_MIN_SCORED_PILLARS", "1")
    d = D.decide({"coverage": 1.0, "pillar_inputs": _ONE})
    assert d["score"] is not None and d["verdict"]


def test_critical_risk_gate_survives_the_min_pillars_rule():
    """بوابة الخطر الحرج قياسٌ صلب لا درجة مختلقة — تقلب NO-GO حتى بأعمدةٍ
    دون الحد الأدنى (مراجعة §58: كتمُها كان يحوّل خطراً مقيساً إلى حيادٍ)."""
    d = D.decide({"coverage": 1.0, "pillar_inputs": {
        **_ONE, "risk": {"political_stability_wgi": -2.0,
                         "critical_risk": True}}})
    assert d["verdict"] == "NO-GO"
    assert d["score"] is None and d["insufficient_pillars"] is True
    assert "خطر حرج" in d["why"]


def test_insufficient_output_carries_every_key_of_the_normal_output():
    """توازي الشكل **بالبناء المُختبَر** لا بالتعليق (مراجعة §58: غياب
    `confidence_basis` طبع «أساس الثقة: None» على docx) — أيّ مفتاحٍ يُضاف
    للمخرج الطبيعي مستقبلاً يُفشِل هنا حتى يُضاف للممتنع."""
    normal = D.decide({"coverage": 1.0, "pillar_inputs": _THREE})
    insuff = D.decide({"coverage": 1.0, "pillar_inputs": _ONE})
    assert set(normal.keys()) <= set(insuff.keys()), \
        sorted(set(normal) - set(insuff))
    assert "None" not in str(insuff.get("confidence_basis"))


def test_render_never_prints_a_computed_counter_case_for_an_abstained_decision():
    """سطر «أقوى الأعمدة X وأضعفها X. اعتُمد الحكم…» لا يُطبع لقرارٍ ممتنع —
    ويشترط عمودين مختلفين عموماً (البند 8 جزئياً، تقرير #11 حرفياً)."""
    from silk_render import decision_basis
    ed = D.decide({"coverage": 1.0, "pillar_inputs": _ONE})
    out = decision_basis(ed)
    assert "counter_case_line" not in out
    # وقرارٌ محسوب بعمودٍ مسجَّلٍ واحد لا يطبع سطراً يناقض نفسه
    ed2 = dict(D.decide({"coverage": 1.0, "pillar_inputs": _THREE}))
    ed2["counter_case"] = {"note": "بلا نص"}   # يجبر مسار السطر المحسوب
    out2 = decision_basis(ed2)
    line = out2.get("counter_case_line", "")
    if line:
        assert line.count("شدة المنافسة") <= 1


def test_analyze_surface_keeps_jury_line_for_abstained_decision():
    """قفل مسار /analyze (silk_render.py:2736): حكمٌ فارغ لا يستبدل الجورية."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_render.py"), encoding="utf-8").read()
    assert 'and ed_top.get("verdict")' in src


def test_quality_gate_min_pillars_check_fails_a_leaked_score():
    import silk_quality_gate as QG
    # مفتاح العرض الحقيقي `entry_decision` لا «decision» المبني يدوياً —
    # المفتاح الخطأ أبقى الحارس ميّتاً والاختبار أخضر (درس 186).
    view = {"deep_research": {"report": {"text": "نص"}, "missions": {}},
            "markets": [{"entry_decision": {
                "schema": "silk.decision/v1", "score": 0.84,
                "pillars": {"competition": {"value": 0.16},
                            "market": {"value": None},
                            "regulatory": {"value": None},
                            "profit": {"value": None},
                            "risk": {"value": None}}}}]}
    out = QG.run_quality_gate(view)
    assert any(f["check"] == "min_pillars_scored" for f in out["findings"])
    # الحارس **يُفشِل** لا يحذّر فقط (مراجعة §58) — درجة مختلقة لا تُسلَّم
    assert out["verdict"] == QG.FAIL
    # ودرجةٌ بلا قاموس أعمدة أصلاً (مسار أجنبي) تُفشِل أيضاً
    view_naked = {"deep_research": {"report": {"text": "نص"}, "missions": {}},
                  "markets": [{"entry_decision": {"schema": "silk.decision/v1",
                                                  "score": 0.84}}]}
    outn = QG.run_quality_gate(view_naked)
    assert any(f["check"] == "min_pillars_scored" for f in outn["findings"])
    # قرارٌ ممتنع (score=None) لا يُعلَّم — هذا هو السلوك الصحيح لا انحداره
    view["markets"][0]["entry_decision"]["score"] = None
    out2 = QG.run_quality_gate(view)
    assert not any(f["check"] == "min_pillars_scored" for f in out2["findings"])
