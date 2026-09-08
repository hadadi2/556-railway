"""الموجة C · C-07 · C-08 · T-05 · R-04 — الربطُ الغائب بين النثر والحقيقة.

> **C-07/C-08:** فحصا الثقة والحكم حارسا اتساقٍ **داخليّ** لنثر الكاتب: يرصدان
> رقمَي ثقةٍ مختلفَين داخل النصّ، أو تسميتَي حكمٍ داخل النصّ. فنصٌّ متّسقٌ مع
> نفسه تماماً بينما يخالف **الحكمَ المخزَّن والثقةَ المسقوفة** يمرّ منهما معاً.
>
> **T-05:** رابطُ نتيجة بحث الويب يعيش داخل `value` ولا يصل حقلَ `url` — فينتهي
> ادّعاءٌ مبنيٌّ على صفحةِ ويبٍ بلا رابطٍ ولا صفٍّ في المراجع. ودليلٌ لا يُفتَح
> ليس دليلاً يُراجَع.
>
> **R-04:** `access_timeline` **شيفرةٌ ميتة** — معرَّفٌ ولا يُنادى — والبوّابةُ
> تكتفي بالبحث عن عبارة «المدة الكلية». فتقريرٌ يكتب العبارةَ بلا حساب يمرّ،
> وتقريرٌ يحسب المدّةَ بصياغةٍ أخرى يُلام. مطابقةُ عباراتٍ لا قياس.
"""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_quality_gate as Q                           # noqa: E402
import silk_requirements_agent as R                     # noqa: E402
import silk_websearch_agent as W                        # noqa: E402
from silk_render import _VERDICT_LABELS_AR as LBL       # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _view(verdict: str, conf: float, text: str) -> dict:
    return {"deep_research": {"verdict": {"verdict": verdict,
                                          "confidence": conf},
                              "report": {"text": text}}}


# ── C-07/C-08 · النثرُ يُربَط بالحكم المُسجَّل ────────────────────────────

def test_a_narrative_agreeing_with_the_recorded_verdict_passes():
    assert Q._check_narrative_matches_the_verdict(
        _view("GO", 0.72, f"التوصية: {LBL['go']}. الثقة 72%.")) == []


def test_a_narrative_asserting_a_different_verdict_is_blocked():
    """حكمان في وثيقةٍ واحدة — والنصُّ متّسقٌ مع نفسه فلا يلتقطه الحارسُ القديم."""
    hits = Q._check_narrative_matches_the_verdict(
        _view("NO-GO", 0.72, f"التوصية: {LBL['go']}. الثقة 72%."))
    assert [h["check"] for h in hits] == ["narrative_verdict_mismatch"]
    # **تحذيريٌّ في هذه الموجة بسببٍ معلَن، لا سهواً.** جعلُه حاجزاً فوراً
    # أسقط ١٢ اختباراً قائماً لأنّ مدوّناتِها تخالف نيّتَها المكتوبة (حقلُ
    # الحكم `CONDITIONAL-GO` وسردُها `WATCH`) — وهو التناقضُ نفسُه الذي يعالجه
    # V-01 في الموجة D عند **مصدر** الحكم. الترقيةُ تتبع ذلك الإصلاح لا تسبقه:
    # الحجبُ بناءً على مدوّناتٍ متناقضةٍ سلفاً يمنع الصحيحَ قبل الخطأ.
    assert hits[0]["repairable"] is True
    assert "narrative_verdict_mismatch" not in Q.FAIL_TRIGGER_CHECKS


def test_a_confidence_far_from_the_recorded_one_is_warned_not_blocked():
    """فرقُ نقطةٍ قد يكون تقريباً — الحجبُ لأجله ضررٌ لا نفع."""
    hits = Q._check_narrative_matches_the_verdict(
        _view("GO", 0.55, f"التوصية: {LBL['go']}. الثقة 72%."))
    assert [h["check"] for h in hits] == ["narrative_confidence_mismatch"]
    assert hits[0]["repairable"]
    assert "narrative_confidence_mismatch" not in Q.FAIL_TRIGGER_CHECKS


def test_a_rounding_difference_is_tolerated():
    assert Q._check_narrative_matches_the_verdict(
        _view("GO", 0.715, f"التوصية: {LBL['go']}. الثقة 72%.")) == []


def test_a_non_decisive_recorded_verdict_never_blocks_a_decisive_narrative():
    """**عيبٌ من المرور الأول:** حكمٌ مُسجَّلٌ غائبٌ أو «غير محسوم» كان يُقرأ
    مناقضاً لأيّ تسميةٍ حاسمةٍ في المتن، فحُجِب تقريرٌ سليمٌ فوراً في الحزمة.
    يُقارَن الحاسمُ بالحاسم وحدَه؛ وتلك مشكلةٌ أخرى (V-01، الموجة D).
    """
    for recorded in (None, "", "غير محسوم"):
        assert Q._check_narrative_matches_the_verdict(
            _view(recorded, 0.7, f"التوصية: {LBL['go']}.")) == [], (
            f"حُجِب تقريرٌ سليمٌ بحكمٍ مُسجَّلٍ «{recorded}»")


def test_an_empty_report_is_left_alone():
    assert Q._check_narrative_matches_the_verdict(_view("GO", 0.7, "")) == []


# ── T-05 · رابطُ الويب يصل عقدَ المصدر ───────────────────────────────────

def test_the_web_link_reaches_the_url_field():
    src = inspect.getsource(W)
    assert 'url=str(item.get("link") or "")' in src, (
        "رابطُ نتيجة البحث ما يزال حبيسَ `value` (T-05)")


def test_the_preferred_rebuild_does_not_lose_the_link_again():
    """الرابطُ كان يُفقَد **مرّتين** — إعادةُ البناء تُسقِط ما لم يُذكَر صراحةً."""
    src = inspect.getsource(W)
    assert 'url=(getattr(f, "url", "")' in src, (
        "إعادةُ بناء النتائج المفضّلة ما تزال تُسقِط الرابط (T-05)")


def test_web_evidence_declares_its_retrieval_method():
    """`llm_web` يجعل سقفَ الرتبة (T-13) يعمل على دليل الويب أيضاً."""
    assert 'retrieval_method="llm_web"' in inspect.getsource(W)


# ── R-04 · الجدولُ الزمنيّ يُحسَب بدل أن يُطابَق نصّاً ────────────────────

def test_the_timeline_is_computed_into_the_structural_state():
    st = R.regulatory_state("DEU", "020130")
    assert "access_timeline" in st, "الجدولُ الزمنيّ ما يزال شيفرةً ميتة (R-04)"
    tl = st["access_timeline"]
    assert tl.get("steps"), "لا خطواتٍ محسوبة"


def test_an_uncodified_timeline_names_the_items_that_lack_durations():
    """الفجوةُ تسمّي البنودَ الناقصة — لا «غير متاح» عامّة."""
    tl = R.regulatory_state("DEU", "020130")["access_timeline"]
    assert tl.get("total_days") is None
    assert "مدد المعالجة غير مقنّنة" in (tl.get("gap") or "")


def test_the_gate_reads_the_structure_before_the_prose():
    """حين تُحسَب المدّةُ فعلاً تصير الملاحظةُ «اذكرها» لا «احسبها»."""
    dr = {"missions": {"customs_requirements": {"failed": False}},
          "report": {"text": "نصٌّ بلا ذكرٍ للمدّة."},
          "regulatory": {"access_timeline": {
              "total_days": {"min": 10, "max": 30}}}}
    hits = Q._check_access_timeline_presence(dr)
    assert hits and "10" in hits[0]["note"] and "30" in hits[0]["note"], (
        "البوّابةُ ما تزال تطابق عبارةً بدل أن تقرأ الحساب (R-04)")


def test_the_gate_stays_quiet_when_the_report_states_the_duration():
    """تكافؤٌ رجعيّ: ذكرُ العبارة يبقى مقبولاً كما كان."""
    assert Q._check_access_timeline_presence(
        {"missions": {"customs_requirements": {"failed": False}},
         "report": {"text": "المدة الكلية من ٣٠ إلى ٤٥ يوماً."}}) == []


def test_c08_is_not_treated_as_blocking_by_any_delivery_path():
    """**قيدٌ معروفٌ مُسجَّل:** لا مسارَ يعامل C-08 حاجزاً قبل إصلاح V-01.

    التحقّقُ على قرار التسليم نفسِه لا على القائمة وحدَها: ملاحظةُ C-08 لا
    تظهر في `blocking` من `silk_export_gate.evaluate` مهما كان حكمُ البوّابة
    الإجماليّ (قد يُحجَب التقريرُ لأسبابٍ أخرى — وهذا شيءٌ آخر).
    """
    import silk_export_gate
    view = {"deep_research": {
        "verdict": {"verdict": "NO-GO", "confidence": 0.7},
        "report": {"text": f"التوصية: {LBL['go']}."}}}
    blocking = [f["check"] for f in silk_export_gate.evaluate(view)["blocking"]]
    assert "narrative_verdict_mismatch" not in blocking, (
        "C-08 صار حاجزاً قبل إصلاح V-01 — يمنع الصحيحَ قبل الخطأ")


def test_the_known_limitation_is_registered_with_its_upgrade_condition():
    """القيدُ مُسجَّلٌ في الجرد بشرطِ ترقيتِه — لا في رسالة التزامٍ وحدها."""
    import io as _io
    import os as _os
    doc = _io.open(_os.path.join(_ROOT, "docs", "ENGINE_AUDIT.md"),
                   encoding="utf-8").read()
    idx = doc.find("INTENTIONAL LIMITATIONS")
    assert idx > 0
    section = doc[idx:idx + 4000]
    assert "narrative_verdict_mismatch" in section, (
        "C-08 غيرُ مُسجَّلٍ قيداً معروفاً")
    assert "V-01" in section and "شرطُ الترقية" in section, (
        "القيدُ مُسجَّلٌ بلا ربطٍ بـV-01 ولا شرطِ ترقية")
