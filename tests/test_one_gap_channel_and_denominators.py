"""حرّاس عائلة تشغيلة الحليب–الأردن (2026-08-19) — عامّة للمنصّة لا لتقرير:

  (١) LESSONS 88 — سجلّ فجوات **واحد** لكل سطوح الحكم: «لا شيء» ممنوعة ما
      دام التقرير يسرد بنوداً (الحقل كان يقرأ أسماء وكلاء الفرز المنهارين).
  (٢) المقام مُعلَن مع كل نسبة: قيمة المورّد لا تُقدَّم إجماليَّ واردات.
  (٣) سنة المؤشر من الـDataPoint حرفياً لا من افتراض «الأحدث» في البرومبت.

هرمتي بالكامل — بلا شبكة ولا مفاتيح.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════ (١) قناة الفجوات الواحدة ═══════════

def test_gap_line_never_says_nothing_while_real_gaps_exist():
    from silk_render import verification_gap_line
    line = verification_gap_line({"data_gaps": []},
                                 ["تعذّر جلب التعرفة", "لا سعر رفّ مرصود"])
    assert "لا شيء" not in line
    assert "2 بنداً" in line and "تعذّر جلب التعرفة" in line


def test_gap_line_says_nothing_only_when_truly_empty():
    from silk_render import verification_gap_line
    assert verification_gap_line({"data_gaps": []}, []) == "لا شيء"
    assert verification_gap_line(None, None) == "لا شيء"


def test_gap_line_merges_both_channels_and_caps_the_head():
    from silk_render import verification_gap_line
    line = verification_gap_line({"data_gaps": ["TradeFlowAgent"]},
                                 [f"بند {i}" for i in range(7)])
    assert "7 بنداً" in line and "+5 بنداً" in line   # رأسان + بقية معلنة
    assert "وكلاء بلا بيانات" in line
    assert "TradeFlowAgent" not in line          # مُعرَّب لا اسم صنف داخلي


def test_view_sufficiency_reflects_real_limits_not_agent_crashes():
    """مسار محرك القرار (§8): سطر الكفاية يُعاد بناؤه بعد اكتمال الحدود."""
    import silk_render as R
    result = {"product": "حليب", "hs_code": "040120", "year": 2023,
              "markets": [{
                  "country": "الأردن", "total_score": 0.55, "confidence": 0.6,
                  "decision": {"schema": "silk.decision/v1", "verdict": "WATCH",
                               "confidence": 0.6, "score": 0.55,
                               "why": "سبب", "decision_rule": "قاعدة"},
                  "jury": {"agents_with_data": 4, "agents_total": 4,
                           "data_gaps": []},
                  "quality_flags": ["تعذّر جلب التعرفة لهذا السوق",
                                    "لا سعر رفّ مرصود"]}]}
    view = R.build_view(result)
    suff = (view.get("decision") or {}).get("sufficiency") or ""
    assert suff, "سطر الكفاية غائب عن مسار محرك القرار"
    assert len(view.get("limits") or []) > 0
    assert "لا شيء" not in suff, suff
    assert "تحتاج تحققاً" in suff


def test_gate_flags_sufficiency_contradiction_and_stays_warning_only():
    import silk_quality_gate as Q
    view = {"decision": {"sufficiency": "بوابة كفاية البيانات: 4/4؛ فجوات: لا شيء"}}
    dr = {"gap_register": [{"text": "فجوة أ"}, {"text": "فجوة ب"}]}
    f = Q._check_sufficiency_contradiction(view, dr)
    assert f and f[0]["check"] == "sufficiency_contradiction"
    assert f[0]["repairable"] is True
    assert "sufficiency_contradiction" not in Q.FAIL_TRIGGER_CHECKS
    # صادقٌ = صمت
    assert Q._check_sufficiency_contradiction(
        {"decision": {"sufficiency": "فجوات: 2 بنداً تحتاج تحققاً: أ؛ ب"}}, dr) == []


def test_writer_prompt_receives_the_same_gap_line():
    # صيد الفجوات ٣ (الدرس 162): كان هنا `hasattr(J, "_verdict_block") or
    # True` — توتولوجيا تخفي رمزاً لم يوجد قط. القفل سلوكي: سطر الفجوات
    # القانوني نفسه (verification_gap_line) يصل نص موجّه الكاتب فعلاً.
    import silk_ai_judge as J
    import silk_render as R
    src = open(os.path.join(_ROOT, "silk_ai_judge.py"), encoding="utf-8").read()
    assert "verification_gap_line" in src, "الكاتب يقرأ قناة فجوات ثانية"
    line = R.verification_gap_line(
        {"data_gaps": []}, ["سعر التجزئة المرصود", "بيانات الاتجاهات"])
    assert "تحتاج تحققاً" in line   # القناة الواحدة تنتج السطر القانوني


# ═══════════ (٢) المقام مُعلَن ═══════════

def test_supplier_line_declares_its_denominator():
    import silk_render as R
    view = {"markets": [{
        "components_detail": [{"name": "market_size", "value": 8470000}],
        "supplier_countries": [{"partner": "السعودية", "share": 90.61,
                                "value_usd": 7670000}]}]}
    ctx = R.analysis_context({"view": view}, max_chars=4000)
    line = next((l for l in ctx.splitlines() if "مورّد:" in l), "")
    assert "من إجمالي واردات السوق" in line
    assert "ليست إجمالي واردات السوق" in line


def test_gate_flags_supplier_value_presented_as_total_imports():
    import silk_quality_gate as Q
    view = {"markets": [{
        "components_detail": [{"name": "market_size", "value": 8470000}],
        "supplier_countries": [{"partner": "السعودية", "value_usd": 7670000}]}]}
    dr = {"report": {"text": "بلغت واردات الأردن 7.67 مليون دولار في 2023."}}
    f = Q._check_metric_value_conflict(view, dr)
    assert f and f[0]["check"] == "metric_value_conflict"
    assert "metric_value_conflict" not in Q.FAIL_TRIGGER_CHECKS
    ok = {"report": {"text": "بلغت واردات الأردن 8.47 مليون دولار في 2023."}}
    assert Q._check_metric_value_conflict(view, ok) == []


# ═══════════ (٣) سنة المؤشر من المصدر ═══════════

def test_writer_prompt_no_longer_volunteers_a_latest_year():
    src = open(os.path.join(_ROOT, "silk_ai_judge.py"), encoding="utf-8").read()
    # التعليق التوثيقي يذكر العبارة كحادثة؛ المحظور أن تبقى **داخل نصّ
    # البرومبت** المرسل للنموذج (سطر يبدأ باقتباس ولا يبدأ بـ#).
    prompt_lines = [l for l in src.splitlines()
                    if l.strip().startswith('"') and "الأحدث" in l]
    assert not any("2023 هي الأحدث" in l for l in prompt_lines), (
        "البرومبت يتطوّع بسنة «أحدث» فيعيد الكاتب ختم قيمة أقدم بها")
    assert "استشهِد حرفياً بالسنة" in src  # النص مقسوم على سطرين في المصدر


def test_gate_flags_lpi_year_not_matching_the_fetched_value():
    import silk_quality_gate as Q
    dr = {"missions": {"logistics": {"findings": [
              {"metric": "logistics_lpi", "value": 2.69, "data_year": 2018}]}},
          "report": {"text": "الأداء اللوجستي LPI 2.69 في نسخة 2023 المنشورة."}}
    f = Q._check_lpi_year_mismatch(dr)
    assert f and f[0]["check"] == "lpi_year_mismatch"
    assert "lpi_year_mismatch" not in Q.FAIL_TRIGGER_CHECKS
    dr_ok = dict(dr, report={"text": "الأداء اللوجستي LPI 2.69 لعام 2018."})
    assert Q._check_lpi_year_mismatch(dr_ok) == []


def test_store_latest_indicator_skips_null_valued_newer_rows():
    import tempfile
    import silk_store as S
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("SILK_STORE_DB")
        os.environ["SILK_STORE_DB"] = os.path.join(d, "s.db")
        try:
            S.migrate()
            S.upsert_indicator("JOR", "LP.LPI.OVRL.XQ", 2018, 2.69, "World Bank", 0.8, "")
            S.upsert_indicator("JOR", "LP.LPI.OVRL.XQ", 2023, None, "World Bank", 0.0, "فارغ")
            row = S.get_indicator("JOR", "LP.LPI.OVRL.XQ")
            assert row and row["year"] == 2018 and row["value"] == 2.69
        finally:
            if old is None:
                os.environ.pop("SILK_STORE_DB", None)
            else:
                os.environ["SILK_STORE_DB"] = old


def test_live_family_guards_are_registered_as_warnings():
    """الحرّاس الحيّة على /research تحذيرية لا حاجبة. درس 186: `metric_value_
    conflict` و`cagr_recompute` كانا مُدرَجَين تحذيرَين بينما هما على شكل
    بيانات /analyze لا /research (المسار الوحيد للبوابة) — فصُحِّح ادعاؤهما في
    السجل إلى «غير مغطّى على /research» (نمط سابقة البند 19)."""
    import silk_quality_gate as Q
    reg = Q.DIRECTIVE_AUDIT_CHECKS
    checks = {c for c, _ in reg.values()}
    for name in ("sufficiency_contradiction", "lpi_year_mismatch"):
        assert name in checks, f"{name} غير مسجَّل في سجلّ التدقيق"
        assert name not in Q.FAIL_TRIGGER_CHECKS
    # الفحصان المصحّحان: مذكوران بالاسم مع قيد /analyze، وشدّتهما تعلن العماء.
    for key in ("3-إعادة حساب المشتقات (CAGR)", "12ب-لا قيمتان لمؤشر واحد"):
        cid, sev = reg[key]
        assert "analyze" in cid and "غير مغطّى" in sev
