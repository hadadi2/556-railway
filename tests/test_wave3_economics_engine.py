"""الموجة ٣ — المحرك الاقتصادي + تطبيع الوحدات (§4.3/§5.4 + تعديل مالك ٢).

هرمتي بالكامل: صفر شبكة، صفر نماذج (كتلة الكاتب تُلتقط بترقيع _call).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_economics as E  # noqa: E402


# ── التطبيع · normalization ─────────────────────────────────────────────────

def test_multipack_unpacked_to_unit_price():
    np_ = E.normalize_price(12.0, currency="USD", pack_count=4, pack_kg=0.5)
    assert np_.per_unit == 3.0 and np_.per_kg == 6.0
    assert np_.value_usd == 3.0


def test_litre_to_kg_via_registry_constant_with_source():
    np_ = E.normalize_price(6.2, currency="EUR", pack_litre=1.0,
                            category="milk", fx_rate=0.92)
    assert np_.per_litre == 6.2
    assert np_.per_kg is not None and abs(np_.per_kg - 6.0194) < 0.01
    assert np_.value_usd is not None  # بسعر صرف معلن


def test_missing_pack_size_declares_named_gap_not_silent_pass():
    np_ = E.normalize_price(7.49, currency="EUR", fx_rate=0.92)
    assert np_.per_kg is None and np_.per_litre is None
    assert any("حجم العبوة" in g for g in np_.gaps)


def test_conversion_refusal_names_the_missing_property():
    val, note = E.convert_amount(1.0, "litre", "kg", "unknown_paste")
    assert val is None
    assert "الكثافة" in note                 # الخاصية مسماة تحديداً
    assert "يتعذر التحويل" not in note       # العبارة العامة ممنوعة


def test_every_registry_constant_carries_a_source():
    for key, (factor, src) in E.CONVERSION_REGISTRY.items():
        assert factor > 0 and "—" in src, f"ثابت بلا مصدر: {key}"


# ── الحل العكسي · reverse solve ─────────────────────────────────────────────

def test_reverse_solve_algebra_exact_with_known_inputs():
    rs = E.reverse_solve_max_exw(
        10.0, tariff_pct=25, vat_pct=0,
        freight_pct_of_exw=0, distributor_margin_pct=0,
        retailer_margin_pct=0)
    assert rs["max_exw"] == 8.0                # 10 ÷ 1.25
    assert rs["headline_scenario"] == "مرصود"
    assert rs["scenarios"] == []               # كل المدخلات مرصودة


def test_reverse_solve_unknowns_produce_declared_scenario_table():
    rs = E.reverse_solve_max_exw(10.0, tariff_pct=None, vat_pct=None)
    assert len(rs["scenarios"]) == 3
    labels = [s["scenario"] for s in rs["scenarios"]]
    assert labels == ["منخفض", "متوسط", "مرتفع"]
    assert rs["max_exw"] == rs["scenarios"][1]["max_exw"]  # العنوان = المتوسط
    assert any("التعرفة" in p for p in rs["parameters"])
    assert any(E.PARAM_TAG in p for p in rs["parameters"])


def test_waterfall_tags_parameters_and_uses_canonical_landed():
    wf = E.margin_waterfall(2.0, freight=None, tariff_pct=25, vat_pct=None,
                            distributor_margin_pct=None,
                            retailer_margin_pct=None)
    tagged = [r for r in wf if r["is_parameter"]]
    assert tagged and all(E.PARAM_TAG in r["note"] for r in tagged)
    landed_row = next(r for r in wf if "الواصلة" in r["name"])
    assert landed_row["value"] == round(E.landed_cost(2.0, 0.24, 25), 3)


# ── بناء العرض · economics_view ─────────────────────────────────────────────

def test_economics_view_no_prices_declares_gap_never_fabricates():
    eco = E.economics_view({"missions": {}})
    assert eco["reverse_solve"] is None and eco["anchor_price"] is None
    assert any("لا سعر رف" in g for g in eco["gaps"])


def test_economics_attached_to_deep_research_view():
    import silk_render as R
    from tools.canonical_netherlands import netherlands_research_blob
    dr = R.build_view(netherlands_research_blob())["deep_research"]
    eco = dr.get("economics")
    assert eco and eco["anchor_price"]["per_unit"] == 7.49
    assert eco["reverse_solve"]["max_exw"] > 0
    assert eco["reverse_solve"]["scenarios"]  # معالم → جدول سيناريوهات معلن


def test_displacement_flag_scale_normalized():
    dr = {"missions": {"competitors": {"findings": [
        {"value": 0.31, "note": "HHI تركّز السوق"}]}}}
    eco = E.economics_view(dr)
    assert eco["hhi"] == 3100 and eco["displacement_required"] is True
    dr2 = {"missions": {"competitors": {"findings": [
        {"value": 940.0, "note": "HHI"}]}}}
    assert E.economics_view(dr2)["displacement_required"] is False


# ── المُصدِّرات · report renderers ──────────────────────────────────────────

def test_markdown_report_carries_economics_section():
    import silk_render as R
    import silk_reports as REP
    from tools.canonical_netherlands import netherlands_research_blob
    md = REP.render_markdown(R.build_view(netherlands_research_blob()))
    assert REP.ECONOMICS_HEADING in md
    assert "أقصى سعر مصنع قابل للمنافسة" in md
    assert "| السيناريو |" in md


def test_docx_report_carries_economics_section(tmp_path):
    import silk_render as R
    import silk_reports as REP
    from docx import Document
    from tools.canonical_netherlands import netherlands_research_blob
    path = str(tmp_path / "eco.docx")
    REP.render_docx(R.build_view(netherlands_research_blob()), path)
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "أقصى سعر مصنع قابل للمنافسة" in text


# ── كتلة الكاتب · writer prompt block ───────────────────────────────────────

def test_writer_prompt_carries_economics_block_and_conditional_verb_rule():
    import silk_ai_judge as J
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    reports = {"pricing_scout": AgentReport("m", [
        DataPoint(value=7.49, source="Google Maps", confidence=0.8,
                  note="Albert Heijn", retrieved_at="2026-08-19")], False,
        "أسعار")}
    captured = {}

    def fake_call(system, user, *a, **kw):
        captured["prompt"] = user
        return "## 1. نص"
    with patch.object(J, "available", return_value=True), \
            patch.object(J, "_call", side_effect=fake_call):
        J.deep_report(reports, "ملخص", {"verdict": "WATCH"}, "حليب", "الأردن")
    up = captured.get("prompt") or ""
    assert "أقصى سعر مصنع قابل للمنافسة" in up
    assert "بافتراض" in up        # قاعدة الأفعال الشرطية للمعالم


def test_writer_prompt_carries_displacement_question_when_hhi_high():
    import silk_ai_judge as J
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    reports = {
        "pricing_scout": AgentReport("m", [
            DataPoint(value=5.0, source="س", confidence=0.8, note="متجر",
                      retrieved_at="2026-08-19")], False, "أسعار"),
        "competitors": AgentReport("m", [
            DataPoint(value=3100.0, source="UN Comtrade", confidence=0.9,
                      note="HHI تركّز", retrieved_at="2026-08-19")], False,
            "منافسون")}
    captured = {}

    def fake_call(system, user, *a, **kw):
        captured["prompt"] = user
        return "## 1. نص"
    with patch.object(J, "available", return_value=True), \
            patch.object(J, "_call", side_effect=fake_call):
        J.deep_report(reports, "ملخص", {"verdict": "WATCH"}, "حليب", "الأردن")
    assert "سؤال الإزاحة" in (captured.get("prompt") or "")


# ── فحوص البوابة — تحذيرية لا حاجبة ─────────────────────────────────────────

def test_wave3_gate_checks_are_warn_never_fail():
    import silk_quality_gate as Q
    for name in ("economics_missing_despite_inputs",
                 "price_comparability_gaps", "generic_conversion_refusal"):
        assert name not in Q.FAIL_TRIGGER_CHECKS
    dr = {"missions": {"pricing_scout": {"findings": [
        {"value": 7.49, "note": "متجر"}]}},
        "economics": {"reverse_solve": None},
        "report": {"text": "نص فيه يتعذر التحويل بلا تفصيل"}}
    f1 = Q._check_economics_present(dr)
    f3 = Q._check_generic_conversion_refusal(dr)
    assert f1 and f1[0]["repairable"] and f3 and f3[0]["repairable"]


# ── أقفال المراجعة الذاتية §58 (الموجة ٣) ───────────────────────────────────

def test_economics_view_handles_live_agentreport_objects():
    """الشكل الحيّ (AgentReport) يعمل كما المُخزَّن — القسم لا يختفي من
    التشغيلات الطازجة (قفل مراجعة §58)."""
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    reports = {"pricing_scout": AgentReport("m", [
        DataPoint(value=7.49, source="Google Maps", confidence=0.8,
                  note="Albert Heijn سعر رف 1 لتر €", retrieved_at="2026-08-19")],
        False, "أسعار")}
    eco = E.economics_view({"missions": reports}, category="milk")
    assert eco["anchor_price"]["per_unit"] == 7.49
    assert eco["anchor_price"]["per_kg"] is not None   # لتر↔كجم من السجل
    assert eco["reverse_solve"]["max_exw"] > 0


def test_anchor_excludes_counts_percentages_and_booleans():
    dr = {"missions": {"pricing_scout": {"findings": [
        {"value": 7.49, "note": "سعر رف Albert Heijn"},
        {"value": 3, "note": "عدد المتاجر المرصودة"},
        {"value": True, "note": "متوفر"},
        {"value": 15.0, "note": "نسبة النمو ٪"}]}}}
    eco = E.economics_view(dr)
    assert eco["anchor_price"]["per_unit"] == 7.49


def test_pack_size_parsed_from_note_reaches_conversion_registry():
    dr = {"missions": {"pricing_scout": {"findings": [
        {"value": 6.2, "note": "سعر رف 1 لتر € متجر محلي"}]}}}
    eco = E.economics_view(dr, category="milk")
    anchor = eco["anchor_price"]
    assert anchor["per_litre"] == 6.2
    assert anchor["per_kg"] is not None    # الكثافة من السجل — لا «متعذر»


def test_pack_kg_branch_declares_conversion_gap_not_silent():
    np_ = E.normalize_price(5.0, currency="USD", pack_kg=1.0,
                            category="unknown_paste")
    assert np_.per_litre is None
    assert any("الكثافة" in g for g in np_.gaps)   # لا فجوة صامتة


def test_render_sanitizes_anchor_source():
    import silk_render as R
    result = {"product": "تمور", "hs_code": "080410", "year": 2024,
              "market": {"name_ar": "هولندا"},
              "deep_research": {"missions": {"pricing_scout": {
                  "summary": "أسعار", "failed": False, "findings": [
                      {"value": 7.49, "source": "Google Maps",
                       "confidence": 0.8, "retrieved_at": "2026-08-19",
                       "note": "سعر رف web_search dp3 متجر"}]}},
                  "report": {"text": "## 1. نص"}, "verdict": {"verdict": "WATCH",
                  "confidence": 0.5}},
              "markets": []}
    dr = R.build_view(result)["deep_research"]
    src = (dr.get("economics") or {}).get("anchor_price", {}).get("source", "")
    # نفس عقد بقية الملاحظات في العرض: وسوم dpN الداخلية تُنزع (المُطهِّر
    # القانوني)؛ أسماء الأدوات تخضع لحارس سطح العميل — وقسم الاقتصاد لا
    # يُصيَّر على سطح العميل بمصدره الخام أصلاً (تقرير المشغّل فقط).
    assert "dp3" not in src


def test_comparability_check_fires_only_on_per_kg_claims():
    import silk_quality_gate as Q
    eco = {"anchor_price": {"per_kg": None,
                            "gaps": ["حجم العبوة غير مرصود"]}}
    quiet = {"economics": eco, "report": {"text": "نص بلا مقارنة كيلو"}}
    assert Q._check_price_comparability(quiet) == []
    loud = {"economics": eco,
            "report": {"text": "السعر 5 دولار/كجم أرخص من المنافس"}}
    assert Q._check_price_comparability(loud)
