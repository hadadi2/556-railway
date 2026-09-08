"""الموجة B — أقفالُ الحواجز · Wave B barrier locks.

كلُّ اختبارٍ هنا يقفل بنداً مسمّىً من `docs/ENGINE_AUDIT.md`، ويُذكَر رمزُه في
اسم الدالّة وفي سطرها الأول. المبدأ: **الاختبارُ يُثبِت العطلَ لو عاد**، لا
مجرّدَ وجودِ رمز — فحيثما أمكن يُشغَّل السلوكُ فعلاً على شكل الإنتاج.

Run:  python3 -m pytest tests/test_wave_b_barriers.py -q
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(rel: str) -> str:
    return open(os.path.join(_ROOT, rel), encoding="utf-8").read()


def _dr(**over) -> dict:
    """عرضٌ عميقٌ صغيرٌ بشكل الإنتاج: بعثةٌ بمؤشّرٍ مرصودٍ ومصدرٍ عموميّ."""
    dr = {"report": {"text": "## 1. الخلاصة التنفيذية\nنصّ."},
          "analyst": {},
          "missions": {"trade_flow": {"findings": [
              {"value": 8400000, "source": "UN Comtrade", "confidence": 0.8,
               "note": "واردات مرصودة 2023"}]}}}
    dr.update(over)
    return dr


# ══════════════════════════════════════════════════════════════════════════
# V-01 — حكمُ تغطيةٍ لا يُقدَّم توصيةً تجارية
# ══════════════════════════════════════════════════════════════════════════

def test_v01_coverage_verdict_never_reads_as_a_commercial_recommendation():
    """V-01 — «نجحت البعثات» لا تُطبَع «توصية أولية بالدخول».

    `JuryCommittee` يفرّع على نجاح الوكلاء لا على السوق. كان مُخرَجُه يصل
    المصنعَ بتسمياتٍ تجارية، فيُقرأ نجاحُ خطّ الأنابيب توصيةً بدخول سوق —
    وانقطاعُ كلود نصيحةً بهجرها.
    """
    import silk_render as R
    for tone, expected in (("preliminary", "data_complete"),
                           ("inconclusive", "data_partial"),
                           ("nogo", "data_absent")):
        got = R._coverage_basis_tone(tone, {"basis": "data_coverage"})
        assert got == expected, f"{tone} لم يتحوّل إلى نبرة حالة الأدلة"
        label_ar = R._verdict_label(got, "ar")
        label_en = R._verdict_label(got, "en")
        for lab in (label_ar, label_en):
            for banned in ("توصية", "بالدخول", "عدم الدخول",
                           "recommendation", "enter"):
                assert banned not in lab, (
                    f"تسميةُ حالةِ أدلةٍ تحمل لغةً تجارية: {lab!r}")


def test_v01_decision_engine_verdicts_keep_their_commercial_labels():
    """V-01 (النصفُ المقابل) — `/analyze` لم يتغيّر بحرف.

    الحكمُ الصادر عن محرّك القرار الموزون تسميتُه التجارية **صادقة**، فلا
    يجوز أن يمسّها هذا الإصلاح. لولا هذا القفل لكان «التشديد» انحداراً.
    """
    import silk_render as R
    assert R._VERDICT_LABELS_AR["go"] == "التوصية بالدخول"
    assert R._VERDICT_LABELS_AR["preliminary"] == "توصية أولية بالدخول"
    assert R._VERDICT_LABELS_AR["nogo"] == "عدم الدخول حالياً"
    # بلا إعلانِ أساسٍ، أو بأساسٍ من المحرّك: النبرةُ كما هي.
    for verdict in ({}, {"basis": "decision_engine"}, None, "نصّ"):
        assert R._coverage_basis_tone("preliminary", verdict) == "preliminary"
        assert R._coverage_basis_tone("go", verdict) == "go"


def test_v01_jury_declares_its_basis_structurally():
    """V-01 — الأساسُ يُعلَن من المنتِج، لا يُستنتَج من شكل النصّ."""
    from silk_agents import AgentReport, JuryCommittee
    from silk_data_layer import DataPoint
    rep = AgentReport("A", [DataPoint(1.0, "UN Comtrade", 0.9, "n", "2026")],
                      False, "s")
    out = JuryCommittee.evaluate([rep])
    assert out["basis"] == "data_coverage"


# ══════════════════════════════════════════════════════════════════════════
# G-01/G-02/G-04/G-05 — سطحُ تصدير المصنع محكومٌ بنفس البوّابة
# ══════════════════════════════════════════════════════════════════════════

def test_g01_one_gate_module_serves_both_export_surfaces():
    """G-01 — سياسةُ التسليم في وحدةٍ واحدة يستهلكها السطحان."""
    eg = _src("silk_export_gate.py")
    for fn in ("def evaluate(", "def is_blocked(", "def prepare_fallback_prose(",
               "def override_authorized(", "def record_block("):
        assert fn in eg, f"silk_export_gate: {fn} مفقود"
    api = _src("api.py")
    platform = _src("silk_platform/api.py")
    assert "import silk_export_gate" in api
    assert "import silk_export_gate" in platform, (
        "سطحُ المصنع لا يستورد بوّابة التسليم — عاد المساران اثنين")
    # ولا سياسةَ بوابةٍ **ثانية** في وحدة المنصّة.
    assert "run_quality_gate(" not in platform, (
        "منطقُ بوّابةٍ نُسِخ داخل silk_platform — مسارٌ ثانٍ")


def test_g01_all_three_factory_endpoints_go_through_the_gate():
    """G-01 — النقاطُ الثلاث كلُّها تمرّ بالمُساعد الواحد."""
    platform = _src("silk_platform/api.py")
    assert platform.count("_client_view_gated(row,") >= 3, (
        "نقطةُ تصديرٍ للمصنع لا تمرّ ببوّابة التسليم")
    for fmt in ('"docx"', '"pdf"', '"json"'):
        assert f"_client_view_gated(row, {fmt}" in platform


def test_g04_factory_block_message_is_client_language_not_infrastructure():
    """G-04 — رفضُ الجودة لا يُقدَّم للمصنع «عطلاً في البنية»."""
    import silk_export_gate as eg
    for lang in ("ar", "en"):
        detail = eg.factory_detail(
            [{"check": "agent_failed",
              "note": "LLMMissionAgent:pricing_scout فشلت — لغةٌ داخلية"}],
            lang)
        assert detail["error"] == "quality_gate_fail"
        msg = detail["message"]
        for banned in ("engine_unavailable", "وحدات المحرّك", "RuntimeError",
                       "docx", "500"):
            assert banned not in msg, f"لغةُ نظامٍ في رسالة المصنع: {msg!r}"
        # ولا تُسرَّب نصوصُ الملاحظات الداخلية — أسماءُ الفحوص فقط.
        blob = json.dumps(detail, ensure_ascii=False)
        assert "LLMMissionAgent" not in blob and "لغةٌ داخلية" not in blob
        assert detail["blocked_checks"] == ["agent_failed"]


def test_g02_factory_read_surface_is_told_the_gate_verdict():
    """G-02 — لا حجبٌ **ولا حتى إخبار** كان الوضعَ السابق."""
    import silk_export_gate as eg
    platform = _src("silk_platform/api.py")
    assert '"quality": _eg.client_quality_summary(' in platform, (
        "حمولةُ قراءة تقرير المصنع لا تحمل حكمَ البوّابة")
    for verdict, must in (("FAIL", True), ("PASS", False)):
        s = eg.client_quality_summary({"verdict": verdict, "blocking": []},
                                      "ar")
        assert s["verdict"] == verdict and s["note"]
        assert ("لم يجتز" in s["note"]) is must


# ══════════════════════════════════════════════════════════════════════════
# T-01/T-02 — الإسنادُ صار قياساً
# ══════════════════════════════════════════════════════════════════════════

def test_t01_mission_label_is_not_a_source():
    """T-01 — اسمُ البعثة الداخليّ لا يُحتسَب سنداً."""
    import silk_source_coverage as c
    assert c._is_backed("UN Comtrade", "") is True
    assert c._is_backed("Google Maps", "") is True     # لا سلبيّةَ كاذبة
    assert c._is_backed("الاشتراطات الجمركية", "") is False
    assert c._is_backed("LLMAgent:pricing_scout", "") is False
    assert c._is_backed("أيّاً كان", "", retrieval_method="mission_label_fallback") \
        is False
    # `source_ids` غير الفارغة سندٌ كافٍ بذاتها.
    assert c._is_backed("بعثة", "", source_ids=("World Bank",)) is True


def test_t01_zero_evidence_is_not_full_coverage():
    """T-01 — صفرُ مؤشّراتٍ كان يُحتسَب ١٠٠٪ ويمرّ بصمت."""
    import silk_source_coverage as c
    from silk_quality_gate import run_quality_gate
    assert c.compute_source_coverage({"missions": {}})["pct"] == 0.0
    out = run_quality_gate({"deep_research": {
        "report": {"text": "## 1. الخلاصة التنفيذية\nالسوق ٤٢ مليون دولار."},
        "analyst": {}, "missions": {}}})
    checks = {f["check"] for f in out["findings"]}
    assert "source_coverage_below_threshold" in checks
    assert out["verdict"] == "FAIL"


def test_t01_coverage_can_actually_fall_below_the_threshold():
    """T-01 — العتبةُ كانت **بنيوياً** غيرَ قابلةٍ للإطلاق."""
    import silk_source_coverage as c
    dr = {"missions": {"m": {"findings": [
        {"value": 1, "source": "بعثة", "confidence": 0.5,
         "retrieval_method": "mission_label_fallback"},
        {"value": 2, "source": "UN Comtrade", "confidence": 0.8}]}}}
    cov = c.compute_source_coverage(dr)
    assert cov == {"total": 2, "backed": 1, "pct": 50.0}
    assert cov["pct"] < c.SOURCE_COVERAGE_MIN_PCT


def test_t01_producer_marks_the_mission_label_fallback():
    """T-01 — الوسمُ يُكتب عند المنتِج لا يُخمَّن من شكل السلسلة.

    (الموجة C: صيغةُ السطر تطوّرت حين صارت حقولُ عقد المصدر تُورَث من النقاط
    المُستشهَد بها، فبقي **الشرطُ نفسه** متداخلاً في تعبيرٍ أوسع. المرساةُ
    تتبع المعنى: الوسمُ مشروطٌ بغياب مصدرٍ عموميّ، لا سطراً حرفياً.)
    """
    rt = _src("silk_llm_runtime.py")
    assert '"mission_label_fallback"' in rt, "الوسمُ نفسه حُذف (T-01)"
    assert 'if pub_sources' in rt, (
        "الوسمُ لم يعد مشروطاً بغياب مصدرٍ عموميّ (T-01)")
    # وسلوكياً: بندٌ بلا مصدرٍ عموميّ يخرج موسوماً، وبمصدرٍ عموميّ لا يُوسَم.
    idx = rt.index('"mission_label_fallback"')
    window = rt[max(0, idx - 400):idx]
    assert "pub_sources" in window, "الوسمُ انفصل عن شرطه (T-01)"


def test_t02_citing_a_valueless_datapoint_is_not_a_citation():
    """T-02 — ادّعاءٌ استشهد بفجوةٍ معلنة كان يُقبَل ويرث اسمَ مصدرها."""
    import silk_llm_runtime as rt
    from silk_data_layer import DataPoint
    registry = {"ok": DataPoint(5.0, "UN Comtrade", 0.8, "n", "2026"),
                "gap": DataPoint(None, "FAOSTAT", 0.0, "401", "2026")}
    payload = json.dumps({"findings": [
        {"claim": "مسنود", "datapoint_ids": ["ok"], "confidence": 0.8},
        {"claim": "على فجوة", "datapoint_ids": ["gap"], "confidence": 0.9},
    ], "gaps": [], "summary": "س"}, ensure_ascii=False)
    out = rt._parse_output(payload, registry)
    assert [f["claim"] for f in out["findings"]] == ["مسنود"]
    # ولا يسقط صامتاً: يصير **فجوةً معلنة** (عقد عدم الاختلاق).
    assert any("على فجوة" in g for g in out["gaps"])
    assert any("declared gaps" in d["reason"] for d in out["dropped"])


def test_t03_mission_summary_is_flagged_as_uncited():
    """T-03 — `summary` يمرّ بلا تحقّق؛ يُوسَم بنيوياً فلا يُبنى عليه رقم."""
    import silk_llm_runtime as rt
    out = rt._parse_output(json.dumps({"findings": [], "gaps": [],
                                       "summary": "السوق ٩٩ مليون دولار"}),
                           {})
    assert out["summary_uncited"] is True


# ══════════════════════════════════════════════════════════════════════════
# G-06/G-08 — لا فحصَ حاجزٌ يخمُد على الإنجليزية
# ══════════════════════════════════════════════════════════════════════════

def test_g06_no_blocking_check_is_skipped_on_english():
    """G-06 — خمسةُ فحوصٍ حاجزة كانت تخمُد على تقرير المصنع الإنجليزيّ."""
    import silk_quality_gate as g
    ar_only = {c[0] for c in g._AR_ONLY_CHECKS}
    blocking_skipped = sorted(ar_only & set(g.FAIL_TRIGGER_CHECKS))
    assert blocking_skipped == [], (
        f"فحوصٌ حاجزةٌ تخمُد على الإنجليزية: {blocking_skipped}")


def test_g06_english_placeholder_and_dangling_reference_are_caught():
    """G-06 — المرايا تعمل فعلاً، لا مجرّد وجودِ رمز."""
    import silk_quality_gate as g
    leak = g._check_placeholder_leak(
        "The detailed narrative for this section is not available.", "en")
    assert leak and leak[0]["check"] == "placeholder_leak"
    dangling = g._check_dangling_cross_reference(
        'As shown above, see "Market sizing" for the derivation.', "en")
    assert dangling and dangling[0]["check"] == "dangling_cross_reference"


def test_g06_english_mirrors_do_not_fire_on_clean_prose():
    """G-06 — حارسٌ يرفض نثراً سليماً أسوأُ من حارسٍ متساهل."""
    import silk_quality_gate as g
    clean = ("## 1. Executive summary\n\nImports reached USD 8.4M in 2023 "
             "(UN Comtrade), and the tariff is 12%.\n")
    assert g._check_placeholder_leak(clean, "en") == []
    assert g._check_dangling_cross_reference(clean, "en") == []
    assert g._check_orphan_short_token(clean, "en") == []
    # كلماتٌ إنجليزيةٌ قصيرةٌ مشروعة تختم فقرةً بلا ترقيم — ليست بتراً.
    assert g._check_orphan_short_token("The margin is thin so\n", "en") == []


def test_g08_skipped_list_declares_only_genuinely_arabic_checks():
    """G-08 — إعلانُ تخطٍّ كاذبٍ يُضعِف الثقةَ بالقائمة كلِّها."""
    import silk_quality_gate as g
    ar_only = {c[0] for c in g._AR_ONLY_CHECKS}
    assert "client_scaffold_leak" not in ar_only, (
        "الفحصُ يعمل على الإنجليزية (يطابق «So what») — إعلانُه مُتخطّى كذب")
    assert g._check_client_scaffold_leak("So what: the margin is thin.")


# ══════════════════════════════════════════════════════════════════════════
# E-03 · X-01 · T-06 · T-07 · T-11 · D-02 · R-02 · E2
# ══════════════════════════════════════════════════════════════════════════

def test_e03_economics_gaps_survive_when_the_model_is_absent():
    """E-03 — حجبُ القسم كان يحذف معه **الفجواتِ المسمّاة** فيصمت الغياب."""
    from silk_reports import _economics_md_lines
    dr = {"economics": {"reverse_solve": {}, "gaps": [
        "لا سعر رف منافس مرصود — الحل العكسي غير ممكن",
        "تكلفة المصنع (EXW) غير مدخلة"]}}
    lines = _economics_md_lines(dr)
    assert lines, "قسمُ الاقتصاد اختفى ومعه فجواتُه المعلنة"
    body = "\n".join(lines)
    assert "لا سعر رف منافس مرصود" in body and "EXW" in body
    # وبلا نموذجٍ **ولا فجوات**: لا قسمَ فارغ.
    assert _economics_md_lines({"economics": {"reverse_solve": {}}}) == []


def test_x01_drop_mode_no_longer_suppresses_the_caveat():
    """X-01 — صمّامٌ كان مقلوبَ الأثر: يكتم التحفّظ ولا يُسقِط البند."""
    import silk_plausibility as P
    src = _src("silk_plausibility.py")
    assert 'if action() == "drop":\n        return []' not in src, (
        "وضعُ drop عاد يكتم التحفّظ بلا إسقاطٍ فعليّ")
    flags = [{"mission": "m", "kind": "magnitude", "claim_usd": 1e12,
              "anchor_usd": 1e6, "ratio": 1e6}]
    with_drop = dict(os.environ)
    try:
        os.environ["SILK_PLAUSIBILITY_ACTION"] = "drop"
        assert P.caveat_lines(flags), (
            "بندٌ غيرُ معقولٍ يُشحَن بلا تحفّظٍ أصلاً — أسوأُ من الافتراضيّ")
    finally:
        os.environ.clear()
        os.environ.update(with_drop)


def test_t06_trace_follows_the_mounted_volume():
    """T-06 — ملفُّ التتبّع كان يتخطّى `SILK_DATA_DIR` وحدَه بين المخازن."""
    import importlib
    import silk_trace
    saved = {k: os.environ.get(k) for k in ("SILK_TRACE_DIR", "SILK_DATA_DIR")}
    try:
        os.environ.pop("SILK_TRACE_DIR", None)
        os.environ["SILK_DATA_DIR"] = "/data"
        importlib.reload(silk_trace)
        assert silk_trace._default_dir() == os.path.join("/data", "traces")
        # الصريحُ يفوز كما كان (الاختباراتُ تعزل به).
        os.environ["SILK_TRACE_DIR"] = "/tmp/x"
        assert silk_trace._default_dir() == "/tmp/x"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(silk_trace)


def test_t07_methodology_promises_only_what_is_delivered():
    """T-07 — وعدٌ لا يُنفَّذ في مُسلَّمٍ للعميل أسوأُ من صمت."""
    import silk_i18n
    for lang in ("ar", "en"):
        p = silk_i18n.TERMS["methodology_paragraph"][lang]
        assert "خضعت كل معلومة للتحقّق" not in p
        assert "Every figure was verified" not in p
    assert "فجوةً صريحة لا تقديراً" in \
        silk_i18n.TERMS["methodology_paragraph"]["ar"]
    assert "explicit gap rather than estimated" in \
        silk_i18n.TERMS["methodology_paragraph"]["en"]


def test_t11_coverage_section_is_actually_called():
    """T-11 — القسمُ كان معرَّفاً بلا مُنادٍ: الرقمُ لا يبلغ المصنع قطّ."""
    rep = _src("silk_reports.py")
    assert rep.count("_client_confidence_section(doc, dr, lang)") == 1, (
        "قسمُ تغطية المصادر لا يُنادى من مُصيّر تقرير العميل")
    import silk_i18n
    for key in ("coverage_heading", "coverage_intro", "coverage_primary"):
        assert silk_i18n.t(key, "ar") and silk_i18n.t(key, "en")


def test_d02_audit_registry_no_longer_claims_absent_coverage():
    """D-02 — سجلٌّ يدّعي تغطيةً غيرَ موجودة يُسكِت السؤال."""
    from silk_quality_gate import DIRECTIVE_AUDIT_CHECKS
    mech, sev = DIRECTIVE_AUDIT_CHECKS["19-قاعدة القرار قبل الحكم"]
    assert sev != "بنيوي", "السجلّ عاد يدّعي تغطيةً بنيويةً غيرَ موجودة"
    assert "ENGINE_AUDIT D-01" in mech


def test_r02_curated_reference_guard_fires_and_stays_advisory():
    """R-02 — الخطرُ المتبقّي بعد الدحض: اشتراطاتٌ من بحثٍ عامّ لا من لائحة."""
    import silk_quality_gate as g
    missing = g._check_curated_reference_consulted({"missions": {
        "customs_requirements": {"failed": False, "findings": [
            {"value": "شهادة", "source": "example.com", "note": "من الويب"}]}}})
    assert missing and missing[0]["check"] == "curated_reference_not_consulted"
    assert missing[0]["repairable"] is True, "الفحصُ تحذيريٌّ لا حاجز"
    assert missing[0]["check"] not in g.FAIL_TRIGGER_CHECKS
    # واستشارةُ المرجع تُسكِته.
    ok = g._check_curated_reference_consulted({"missions": {
        "customs_requirements": {"failed": False, "findings": [
            {"value": "بند", "source": "Silk L1 requirements reference "
                                       "(official portals / EUR-Lex)",
             "note": ""}]}}})
    assert ok == []
    # وبعثةٌ فاشلة يلتقطها `agent_failed` الحاجز — لا ازدواجَ إبلاغ.
    assert g._check_curated_reference_consulted({"missions": {
        "customs_requirements": {"failed": True, "findings": []}}}) == []


def test_r06_quick_mode_keeps_the_regulatory_layer():
    """R-06 — وضعُ الطوارئ كان يُسقِط الطبقةَ التنظيمية بأكملها بلا إعلان."""
    bridge = _src("silk_platform/engine_bridge.py")
    body = bridge.split("def _run_engine(")[1].split("\ndef ")[0]
    assert "with_requirements=True" in body
    assert "with_research=True" in body


def test_e2_sample_generator_does_not_write_on_import():
    """E2 — اختبارٌ يُوسِّخ الشجرة بعيّنةٍ ملتزَمة عند كلّ تشغيلٍ للحزمة."""
    gen = _src("tools/gen_research_sample.py")
    assert '_WRITE = (__name__ == "__main__"' in gen
    assert gen.count("if _WRITE:") == 2, (
        "كتابةٌ إلى samples/ بلا حراسة — تُوسِّخ الشجرة عند الاستيراد")
