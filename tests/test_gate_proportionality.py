"""تناسبُ الحجب — بعثةٌ إثرائيةٌ واحدة لا تمنع تقريراً كاملاً (بلاغ المالك).

**الحادثة (direct reproduction من تقريرٍ حقيقيّ):** دراسةُ «قهوة محمصة ×
ماليزيا» أنتجت تقريراً كامل الأقسام — عشرٌ من اثنتي عشرة بعثةً بأدلةٍ
مستشهَدة، جدولُ قرارٍ بخمسة أعمدة، أسعارُ أربعةِ منافسين بعلامةٍ ومتجرٍ
وتاريخ، اشتراطاتٌ بثلاث طبقات، وجهاتُ اتصال — **ورُفض تسليمه**. البعثتان
الصفريتان كانتا «اتجاهات الطلب» و«الفرص»: كلتاهما **إثرائيةٌ لا تغذّي عمودَ
قرار**.

**الجذر:** `_check_agent_health` كانت حلقةً بشرطٍ واحد `if m.get("failed")`
تُصدر `agent_failed` (في `FAIL_TRIGGER_CHECKS`، `repairable=False`) ⇒ FAIL
دائماً. لا عتبةَ عددٍ ولا تمييزَ بين بعثةٍ جوهريةٍ وأخرى إثرائية — فبعثةٌ
إثرائيةٌ واحدة تُعامَل كتقريرٍ بلا أدلةٍ أصلاً. وكلُّ حكمٍ مُدرَّجٍ آخرَ في
الملفّ له عتبة (`_style_grade`)؛ هذا وحدَه كان شاذّاً بلا واحدة.

**ولماذا طارد المالكُ السببَ الخطأ:** نصُّ العميل كان عامّاً («أحدُ مصادر
البحث تعذّر تشغيله») لا يسمّي البعثة، فقرأه مع سطرِ حدودٍ يذكر فشلَ مؤشرات
البنك الدولي فطارده — وفشلُ WGI **لا يستطيع بنيوياً** رفعَ الراية:
`failed = not findings` تُجمَّد في `run_llm_agent` قبل أن يُلحِق
`_augment_risk_news_wgi` مؤشراتِه. نفسُ عائلة الدرس ٢٥٥.

هرمتي. Run: python3 -m pytest tests/test_gate_proportionality.py -q
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_export_gate as EG                              # noqa: E402
import silk_quality_gate as QG                             # noqa: E402


def _mission(failed: bool) -> dict:
    return {"failed": failed, "summary": "بلا نتائج", "findings": []}


def _ok_mission() -> dict:
    return {"failed": False, "summary": "ok", "findings": [
        {"value": 1.0, "source": "UN Comtrade", "confidence": 0.9,
         "note": "n", "retrieved_at": "2026-01-01", "status": ""}]}


def _dr(failed_keys: tuple[str, ...]) -> dict:
    """كلُّ البعثات ناجحةٌ إلا المسمّاة — أقربُ ما يكون لتشغيلة المالك."""
    from silk_missions import MISSION_ORDER
    return {"missions": {k: (_mission(True) if k in failed_keys else _ok_mission())
                         for k in MISSION_ORDER}}


# ═══ ١) البلاغ حرفياً: إثرائيةٌ واحدة لا تحجب ═══════════════════════════════

def test_one_failed_enrichment_mission_does_not_block_delivery():
    """بعثةُ «الفرص» صفريةٌ وحدَها ⇒ ملاحظةٌ منهجية، لا رفضَ تسليم."""
    findings = QG._check_agent_health(_dr(("opportunity_gaps",)))
    checks = {f["check"] for f in findings}
    assert "agent_failed_optional" in checks
    assert "agent_failed" not in checks
    assert not (checks & QG.effective_fail_triggers())


def test_the_owners_exact_run_is_delivered():
    """البعثتان الصفريتان في تقرير المالك — كلتاهما إثرائية ⇒ لا حجب."""
    findings = QG._check_agent_health(_dr(("demand_trends", "opportunity_gaps")))
    assert not ({f["check"] for f in findings} & QG.effective_fail_triggers())


def test_the_note_still_reaches_the_reader_as_a_methodology_limit():
    """غيرُ حاجبٍ **لا يعني** صامتاً: الفجوةُ تبقى معلنةً للقارئ."""
    findings = QG._check_agent_health(_dr(("opportunity_gaps",)))
    row = next(f for f in findings if f["check"] == "agent_failed_optional")
    assert row["repairable"] is False          # شديدة ⇒ تصل methodology_notes
    assert "opportunity_gaps" not in row["note"]
    assert QG._mission_label("opportunity_gaps") in row["note"]


# ═══ ٢) لا توسيعَ سماح: الجوهريُّ يبقى حاجباً ═══════════════════════════════

def test_a_failed_core_evidence_mission_still_blocks():
    for key in sorted(QG._CORE_EVIDENCE_MISSIONS):
        checks = {f["check"] for f in QG._check_agent_health(_dr((key,)))}
        assert "agent_failed" in checks, key
        assert checks & QG.effective_fail_triggers(), key


def test_core_missions_are_exactly_what_the_pillar_layer_reads():
    """**مقيسةٌ من المصدر لا مُقدَّرة** — القفلُ الذي منع تعداداً بالحدس.

    أوّلُ تعدادٍ كُتب «من أعمدة القرار» أخطأ في الاتجاهين: أدرج
    `pricing_scout` (لا تُقرأ في `silk_deep_pillars` إطلاقاً) وأسقط
    `tariffs_agreements`/`demographics_economy`/`logistics` (تُقرأ). هذا
    القفلُ يقارن المجموعةَ بما يناديه الملفُّ فعلاً فلا تتباعد صامتةً.
    """
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "silk_deep_pillars.py"),
               encoding="utf-8").read()
    read = set(re.findall(r'_(?:metric_)?findings\(missions[^,]*,\s*"([a-z_]+)"',
                          src))
    read |= set(re.findall(r'\(\s*"[a-z_]+",\s*"([a-z_]+)",\s*"[a-z_]+"\s*\)',
                           src))
    from silk_missions import MISSION_ORDER
    read &= set(MISSION_ORDER)
    assert QG._CORE_EVIDENCE_MISSIONS == read, (
        f"تباعدت المجموعةُ عن مصدرها: زائد {QG._CORE_EVIDENCE_MISSIONS - read}، "
        f"ناقص {read - QG._CORE_EVIDENCE_MISSIONS}")
    assert "pricing_scout" not in QG._CORE_EVIDENCE_MISSIONS


# ═══ حصادُ المراجعة الذاتية §58 ══════════════════════════════════════════════

def test_a_mission_with_appended_evidence_is_not_called_void():
    """`failed` تُجمَّد قبل أن تُلحِق خطواتُ D3 أدلّتَها الحتمية — فبعثةٌ
    رُفعت رايتُها ثمّ امتلأت بأدلةٍ مُهيكَلة كانت تُحجَب وتُوصَف «بلا
    نتائج مستشهَد بها» بينما طبقةُ الأعمدة تحسب منها درجة."""
    dr = _dr(())
    dr["missions"]["risk_news"] = {
        "failed": True, "summary": "انتهت المهلة",
        "findings": [{"value": 0.55, "source": "World Bank",
                      "confidence": 0.8, "note": "[risk] سيادة القانون",
                      "retrieved_at": "2026-01-01", "status": ""}]}
    checks = {f["check"] for f in QG._check_agent_health(dr)}
    assert "agent_failed" not in checks
    assert not (checks & QG.effective_fail_triggers())


def test_the_threshold_denominator_is_the_defined_set_not_the_payload():
    """حمولةٌ جزئية كانت تُصغِّر المقامَ فيعود الحجبُ على فشلٍ واحد."""
    partial = {"missions": {"trade_flow": _ok_mission(),
                            "opportunity_gaps": _mission(True),
                            "demand_trends": _ok_mission()}}
    checks = {f["check"] for f in QG._check_agent_health(partial)}
    assert "agent_failed_many_optional" not in checks
    assert not (checks & QG.effective_fail_triggers())


def test_the_threshold_block_says_the_threshold_not_a_missing_pillar():
    """سببُ الحجب عتبةُ العدد — فالاسمُ والنصُّ يقولانه لا «عمودٌ بلا سند»."""
    from silk_missions import MISSION_ORDER
    opt = [k for k in MISSION_ORDER if k not in QG._CORE_EVIDENCE_MISSIONS]
    checks = {f["check"] for f in
              QG._check_agent_health(_dr(tuple(opt[:(len(opt) + 1) // 2])))}
    assert "agent_failed_many_optional" in checks
    assert "agent_failed" not in checks
    ar = EG._CLIENT_REASONS["agent_failed_many_optional"]["ar"]
    assert "نصف" in ar and "عمود" not in ar.split("أعمدةُ القرار قائمة")[0]


def test_no_reason_points_at_a_section_of_an_undelivered_report():
    """«اسمُها في حدود المنهجية أدناه» إحالةٌ معلَّقة: عند الحجب لا تقرير."""
    for key in ("agent_failed", "agent_failed_many_optional"):
        assert "أدناه" not in EG._CLIENT_REASONS[key]["ar"], key
        assert "below" not in EG._CLIENT_REASONS[key]["en"], key


def test_the_non_blocking_reason_does_not_announce_delivery_itself():
    """الواجهةُ تعرضه تحت «ملاحظات لا تحجب التسليم»؛ ادّعاؤه التسليمَ بنفسه
    يناقض «لم نُسلِّمه» حين يحجب فحصٌ آخر على الشاشة نفسِها."""
    ar = EG._CLIENT_REASONS["agent_failed_optional"]["ar"]
    assert "يُسلَّم" not in ar and "التقريرُ يُسلَّم" not in ar


# ═══ ٣) حدُّ الكمّ: نصفُ الإثرائيات فأكثر يعود حاجباً ═══════════════════════

def test_half_the_enrichment_missions_failing_blocks_again():
    """تقريرٌ نصفُ إثرائه فارغٌ ليس تقريرَ قرارٍ ولو نجا جوهرُه."""
    from silk_missions import MISSION_ORDER
    opt = [k for k in MISSION_ORDER if k not in QG._CORE_EVIDENCE_MISSIONS]
    half = tuple(opt[:(len(opt) + 1) // 2])
    checks = {f["check"] for f in QG._check_agent_health(_dr(half))}
    assert "agent_failed_many_optional" in checks
    assert checks & QG.effective_fail_triggers()


def test_just_below_the_threshold_still_delivers():
    from silk_missions import MISSION_ORDER
    opt = [k for k in MISSION_ORDER if k not in QG._CORE_EVIDENCE_MISSIONS]
    under = tuple(opt[:((len(opt) + 1) // 2) - 1])
    checks = {f["check"] for f in QG._check_agent_health(_dr(under))}
    assert not (checks & QG.effective_fail_triggers())


# ═══ ٤) الرسالةُ تسمّي ما وقع فعلاً ════════════════════════════════════════

def test_the_blocking_message_names_the_mission_not_a_generic_source():
    """المالك طارد مؤشرَ البنك الدولي لأنّ الرسالة لم تسمِّ البعثة."""
    ar = EG._CLIENT_REASONS["agent_failed"]["ar"]
    assert "أحدُ مصادر البحث" not in ar
    assert "بعثة" in ar or "البعثة" in ar


def test_every_blocking_and_optional_check_has_a_visitor_sentence():
    for key in ("agent_failed", "agent_failed_optional",
                "agent_failed_many_optional"):
        row = EG._CLIENT_REASONS.get(key)
        assert row and row.get("ar") and row.get("en"), key


def test_the_optional_check_is_not_a_delivery_blocker_anywhere():
    assert "agent_failed_optional" not in QG.FAIL_TRIGGER_CHECKS
    assert "agent_failed_optional" not in QG.effective_fail_triggers()
    assert "agent_failed_optional" not in QG._REGRESSION_GUARD_FIRED
