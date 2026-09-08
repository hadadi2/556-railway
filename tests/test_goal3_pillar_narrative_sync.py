"""البند 3 من أمر إصلاح المحرّك — اللوحة والسرد يقرآن من مصدرٍ واحد.

الدليل (direct reproduction — تقرير #11): عمود الأمان «استقرار العملة لم
يُرصَد» بينما §9 يسرد ثبات الدينار عند 0.71؛ «وضوح الاشتراطات غير مرصود»
بينما §7 ثلاثة جداول؛ «الحصة السعودية غير مرصودة» بينما الملخّص يذكرها.
الجذر: مكوّناتٌ يستهلكها العمود ولا يستخرجها أحد (fx)، أو مصدرها CSV فارغ
بينما البعثة رصدت (الاشتراطات)، أو إبرة استخراج لا تطابق صيغة الكتابة
(«تستحوذ السعودية»). هرمتي. Run:
  python3 -m pytest tests/test_goal3_pillar_narrative_sync.py -q
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_deep_pillars as DP                           # noqa: E402


def _dr(**missions):
    return {"missions": {k: {"findings": v, "failed": False}
                         for k, v in missions.items()}}


def test_fx_volatility_augment_computes_from_wb_series_declaredly():
    """تقلّب الصرف مستنتَج بقاعدة معلنة من سلسلة البنك الدولي — لا تقدير."""
    import silk_missions as sm
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint

    report = AgentReport("LLMMissionAgent:risk_news", [], False, "ملخص")
    series = {2025: 0.71, 2024: 0.71, 2023: 0.71}

    def fake_wb(iso3, ind, year=None):
        assert ind == "PA.NUS.FCRF"
        return DataPoint(series.get(year), "World Bank", 0.9, f"{ind} {year}")

    with mock.patch("silk_data_layer.world_bank", side_effect=fake_wb), \
         mock.patch("silk_store.get_indicator", return_value=None):
        sm._augment_risk_news_fx(report, "JOR")
        sm._augment_risk_news_fx(report, "JOR")   # idempotent
    fx = [dp for dp in report.findings if "تقلب سعر الصرف" in dp.note]
    assert len(fx) == 1
    assert fx[0].value == 0.0                     # دينار ثابت ⇒ صفر تقلب
    assert "قاعدة معلنة" in fx[0].note


def test_fx_augment_declares_gap_below_two_years():
    import silk_missions as sm
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint

    report = AgentReport("LLMMissionAgent:risk_news", [], False, "ملخص")
    with mock.patch("silk_data_layer.world_bank",
                    return_value=DataPoint(None, "World Bank", 0.0, "x")), \
         mock.patch("silk_store.get_indicator", return_value=None):
        sm._augment_risk_news_fx(report, "JOR")
    gap = [dp for dp in report.findings if "تقلب سعر الصرف" in dp.note]
    assert len(gap) == 1 and gap[0].value is None
    assert gap[0].confidence == 0.0


def test_fx_reaches_the_risk_pillar_input():
    pi = DP.build_pillar_inputs(_dr(risk_news=[{
        "value": 0.0, "source": "World Bank", "confidence": 0.85,
        "note": "[risk] تقلب سعر الصرف 0.0% — مستنتَج بقاعدة معلنة"}]))
    assert pi["risk"]["fx_volatility_pct"] == 0.0


def test_saudi_share_falls_back_to_structured_top_supplier():
    """المهيمن سعودي بحصة مُهيكلة ⇒ هي الحصة السعودية — لا «غير مرصودة»
    بجوار ملخّصٍ تنفيذي يذكرها."""
    summary = {"value": {"year": 2023, "hhi": 7118, "supplier_count": 7,
                         "top_suppliers": [{"partner": "Saudi Arabia",
                                            "share": 84.05}]},
               "source": "UN Comtrade", "confidence": 0.9, "note": "تركّز"}
    pi = DP.build_pillar_inputs(_dr(competitors=[summary]))
    assert pi["market_attractiveness"]["saudi_share_pct"] == 84.05


def test_saudi_share_prose_needle_matches_actual_wording():
    pi = DP.build_pillar_inputs(_dr(trade_flow=[{
        "value": "تستحوذ السعودية على 84.05% من واردات الفئة",
        "source": "UN Comtrade", "confidence": 0.9,
        "note": "تستحوذ السعودية على 84.05%"}]))
    assert pi["market_attractiveness"]["saudi_share_pct"] == 84.05


def test_requirements_count_falls_back_to_mission_findings():
    """CSV بلا صفوف لهذا السوق بينما البعثة رصدت بنوداً ⇒ عدُّها الحتمي
    يغذّي وضوحَ الاشتراطات — لا «غير مرصود» فوق ثلاثة جداول."""
    reqs = [{"value": f"اشتراط {i}", "source": "مرجع", "confidence": 0.7,
             "note": "بند"} for i in range(4)]
    pi = DP.build_pillar_inputs(_dr(customs_requirements=reqs))
    assert pi["regulatory_fit"]["entry_requirements_count"] == 4
    # والمرجع المقنَّن يتقدّم حين يوجد
    pi2 = DP.build_pillar_inputs(_dr(customs_requirements=reqs),
                                 regulatory={"all": [1, 2]})
    assert pi2["regulatory_fit"]["entry_requirements_count"] == 2


def test_gate_fails_when_panel_denies_what_the_body_narrates():
    import silk_quality_gate as QG
    view = {"deep_research": {"missions": {}, "report": {
        "text": "استقر سعر الصرف للدينار عند 0.71 عبر السنوات الثلاث."}},
        "markets": [{"decision": {
            "schema": "silk.decision/v1", "score": 0.5,
            "pillars": {
                "market": {"value": 0.5, "missing": []},
                "competition": {"value": 0.5, "missing": []},
                "risk": {"value": 0.4, "missing": ["fx_stability"]},
                "regulatory": {"value": 0.5, "missing": []},
                "profit": {"value": 0.5, "missing": []}}}}]}
    out = QG.run_quality_gate(view)
    assert any(f["check"] == "pillar_narrative_sync" for f in out["findings"])
    assert out["verdict"] == QG.FAIL
    # متنٌ لا يذكر الصرف ⇒ الغياب المعلن مشروع، لا فشل
    view["deep_research"]["report"]["text"] = "نص لا يذكر العملة إطلاقاً."
    out2 = QG.run_quality_gate(view)
    assert not any(f["check"] == "pillar_narrative_sync"
                   for f in out2["findings"])


def test_declared_gap_sentence_in_body_is_not_a_contradiction():
    """جملةُ فجوةٍ في المتن («لم يُرصَد سعر الصرف») ذكرٌ مشروع لا سرد —
    مراجعة §58: فحصٌ مُفشِل يجب ألا يحجب تقريراً أميناً أعلن فجوته."""
    import silk_quality_gate as QG
    view = {"deep_research": {"missions": {}, "report": {
        "text": ("حدود هذا التقرير: لم يُرصَد سعر الصرف لهذه السنوات.\n"
                 "| إجمالي الواردات | غير مرصود |")}},
        "markets": [{"decision": {
            "schema": "silk.decision/v1", "score": 0.5,
            "pillars": {
                "market": {"value": 0.5, "missing": ["tam_log"]},
                "risk": {"value": 0.4, "missing": ["fx_stability"]}}}}]}
    out = QG.run_quality_gate(view)
    assert not any(f["check"] == "pillar_narrative_sync"
                   for f in out["findings"])
    # وجملةٌ سردية إلى جوار جملة الفجوة تُفشِل رغم وجودها
    view["deep_research"]["report"]["text"] += (
        "\nاستقر سعر الصرف للدينار عند 0.71 عبر السنوات الثلاث.")
    out2 = QG.run_quality_gate(view)
    assert any(f["check"] == "pillar_narrative_sync"
               for f in out2["findings"])
