"""إحياء حرّاس البوابة الميّتة على مسار /research (find all gaps — مجموعة 1).

البوابة تعمل على مسار /research **فقط** (ترجع PASS فوراً إن `deep_research`
فارغ). حرّاسٌ كُتبت لأشكال بيانات /analyze (research.pillar_inputs،
dr.regulatory، finding.metric، analyst.report.summary) فبقيت خامدة على
العرض الفعلي (عائلة درس 186/98). هذا القفل يثبت أنها تُطلق الآن على مفاتيح
`build_view` الحقيقية — واختباراتها القديمة كانت تبني المفاتيح الخطأ يدوياً
فتخضرّ زوراً.

الأخطر (`competition_unit_valid`) حاجبٌ للتسليم (`_REGRESSION_GUARD_FIRED`)
وكُتب لحادثة انقلاب الحكم 26%→84% على مسار /research نفسه.
Hermetic؛ لا شبكة.
"""
from __future__ import annotations

import silk_quality_gate as QG


def _dr_view(dr: dict, markets=None) -> dict:
    return {"deep_research": dr, "markets": markets if markets is not None
            else [{}]}


# ── competition_unit_valid — حاجب التسليم، القيم الخام في بعثة المنافسين ──

def _comp_view(hhi, share):
    return _dr_view({"report": {"text": "نص"}, "missions": {"competitors": {
        "findings": [{"value": {"hhi": hhi,
                                "top_suppliers": [{"partner": "الصين",
                                                   "share": share}]}}]}}})


def test_competition_unit_valid_fires_on_out_of_range_top_share():
    """حصةُ أكبر مورّد فوق 100% (وحدةٌ تسرّبت للحقل — عائلة 26%→84%)."""
    out = QG._check_competition_unit_valid(_comp_view(7118, 250.0))
    assert any(f["check"] == "competition_unit_valid" for f in out)


def test_competition_unit_valid_fires_on_hhi_over_ceiling():
    out = QG._check_competition_unit_valid(_comp_view(48000, 84.05))
    assert any(f["check"] == "competition_unit_valid" for f in out)


def test_competition_unit_valid_silent_on_in_range_research_values():
    assert QG._check_competition_unit_valid(_comp_view(7118, 84.05)) == []


def test_competition_unit_valid_still_covers_the_analyze_pillar_inputs_path():
    """الاحتياط: عرضٌ يمرّر research.pillar_inputs (مسار /analyze) يبقى مغطّى."""
    view = _dr_view({"report": {"text": "نص"}, "missions": {}},
                    markets=[{"research": {"pillar_inputs": {
                        "competition_intensity": {"hhi": 48000.0,
                                                  "top_supplier_share_pct": 5.0}}}}])
    out = QG._check_competition_unit_valid(view)
    assert any(f["check"] == "competition_unit_valid" for f in out)


def test_competition_unit_valid_is_a_delivery_blocking_guard():
    assert "competition_unit_valid" in QG._REGRESSION_GUARD_FIRED


# ── access_timeline — الحالة التنظيمية في المستوى الأعلى للعرض ────────────

def test_access_timeline_enriched_branch_reads_top_level_regulatory():
    """فرعُ «المدة الكلية محسوبة» كان ميّتاً (dr.regulatory غير مبنيّ) —
    يقرأ الآن view.regulatory الحقيقي فيذكر المدى بدل الرسالة العامة."""
    dr = {"report": {"text": "لا يذكر المدة"},
          "missions": {"customs_requirements": {"failed": False}}}
    reg = {"access_timeline": {"total_days": {"min": 45, "max": 60}}}
    out = QG._check_access_timeline_presence(dr, "ar", regulatory=reg)
    assert out and "45" in out[0]["note"] and "60" in out[0]["note"]


# ── cagr_consistency — قناة ملخّص المحلل المسطّحة ─────────────────────────

def test_cagr_consistency_scans_the_flattened_analyst_summary():
    """تعارضٌ موضوعٌ **فقط** في analyst.summary (المفتاح المسطّح للعرض) —
    كانت القناة تقرأ analyst.report.summary غير المبنيّ فتعميها."""
    dr = {"report": {"text": "لا رقم هنا"}, "verdict": {},
          "analyst": {"summary": (
              "سجّل السوق نموّاً سنوياً مركّباً 5% خلال 2019–2021 ثم نموّاً "
              "سنوياً مركّباً 12% خلال 2021–2023 بلا مصالحة")}}
    out = QG._check_cagr_consistency(dr)
    assert any(f["check"] == "cagr_inconsistency" for f in out)


# ── lpi_year_mismatch — سنة المصدر من عبارة البعثة لا من finding.metric ───

def test_lpi_year_mismatch_finds_source_year_via_note_phrase():
    """على /research لا حقلَ metric في الاكتشافات؛ سنةُ LPI تُقرأ من عبارة
    البعثة + data_year، فيُكشف نصٌّ يختم القيمة بسنةٍ أحدث زوراً."""
    dr = {"report": {"text": "بلغ مؤشر الأداء اللوجستي LPI لعام 2023 مستوى جيداً"},
          "missions": {"logistics": {"findings": [
              {"value": 2.69, "data_year": 2018,
               "note": "مؤشر الأداء اللوجستي (LPI) 2.69"}]}}}
    out = QG._check_lpi_year_mismatch(dr)
    assert any(f["check"] == "lpi_year_mismatch" for f in out)


# ── التوثيق الصادق: فحصان بلا بيانات على /research (لا تزييف) ──────────────

def test_metric_value_conflict_and_cagr_recompute_declared_na_in_registry():
    """السجل يصرّح بأنهما على شكل بيانات /analyze لا /research (نمط سابقة
    البند 19: سجلٌّ يدّعي تغطية غير موجودة يُسكِت السؤال)."""
    reg = QG.DIRECTIVE_AUDIT_CHECKS
    assert "analyze" in reg["3-إعادة حساب المشتقات (CAGR)"][0]
    assert "analyze" in reg["12ب-لا قيمتان لمؤشر واحد"][0]
