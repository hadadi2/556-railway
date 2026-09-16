"""موجةُ عيوب التقرير — الطبقةُ المنطقية (الأصناف ٦–٩)، اختبارٌ أوّلاً.

كلُّ صنفٍ هنا **خلف رايةٍ مطفأةٍ افتراضياً**: بلا الراية لا يتغيّر مخرَجٌ ولا
حكمٌ ولا موجّهٌ — والسلوكُ السابق هو نفسُه حرفياً (قرار المالك 2026-08-19:
«لا حجب جديداً»، وقرارُه في هذه الموجة: حاجبٌ مع الراية فقط).

كلُّ اختبارٍ يقيس **الحالتين**: مطفأةً (عقدُ عدم المساس) ومفعّلةً (الأثر).

Run: python3 -m pytest tests/test_report_quality_logic_layer.py -q
"""
from __future__ import annotations

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from conftest import block_network  # noqa: E402


class _env:
    """متغيّراتُ بيئةٍ باستعادةٍ مضمونة — الاصطلاحُ القائم في هذه الحزمة."""

    def __init__(self, **vals):
        self.vals = vals
        self.old = {}

    def __enter__(self):
        for k, v in self.vals.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def _canonical_keys() -> list:
    from tools import gen_verdict_baseline as B
    return sorted(B.CANONICAL_BLOBS)


def _blob(key: str) -> dict:
    from tools import gen_verdict_baseline as B
    mod, fn = B.CANONICAL_BLOBS[key]
    return getattr(importlib.import_module(mod), fn)()


# ════════════════ الصنف ٦ — قيمتان لمؤشرٍ واحد ════════════════

def _two_readings_dr(text: str) -> dict:
    """قراءتان لمؤشرٍ واحد في الأدلة — الشكلُ الذي أنتج العيب المرصود."""
    return {"report": {"text": text},
            "missions": {"competitors": {"summary": "x", "findings": [
                {"value": 10.44, "note": "حصة السعودية 2023",
                 "source": "UN Comtrade", "confidence": 0.8},
                {"value": 12.42, "note": "حصة السعودية 2024",
                 "source": "UN Comtrade", "confidence": 0.8}]}},
            "analyst": {"by_category": {}, "missing_categories": []}}


def test_c6_flag_off_changes_nothing_in_the_fail_set():
    """عقدُ عدم المساس: مطفأةً، مجموعةُ الحجب هي الأصليةُ حرفياً."""
    import silk_quality_gate as G
    with _env(SILK_FIGURE_STORE=None):
        assert G.effective_fail_triggers() == G.FAIL_TRIGGER_CHECKS
    with _env(SILK_FIGURE_STORE="1"):
        assert G.effective_fail_triggers() - G.FAIL_TRIGGER_CHECKS == \
            {"metric_value_divergence"}
    # والثابتةُ نفسُها لا تُمَسّ — عشراتُ الاختبارات تقرؤها عقداً.
    assert "metric_value_divergence" not in G.FAIL_TRIGGER_CHECKS


def test_c6_divergence_severity_follows_the_flag():
    """**العيبُ المرصود**: «10.44% في الملخّص و12.42% في الجدول».

    تحذيريٌّ مطفأةً، حاجبٌ مفعّلةً — لا سلوكَ ثالث."""
    import silk_quality_gate as G
    dr = _two_readings_dr(
        "## 1. الخلاصة التنفيذية\nالحصة السعودية 10.44% من السوق.\n\n"
        "## 6. المشهد التنافسي\nالحصة السعودية 12.42% هذا العام.")
    with _env(SILK_FIGURE_STORE=None):
        off = G._check_metric_value_divergence({}, dr)
    with _env(SILK_FIGURE_STORE="1"):
        on = G._check_metric_value_divergence({}, dr)
    assert [f["check"] for f in off] == ["metric_value_divergence"]
    assert off[0]["repairable"] is True, "مطفأةً: تحذير"
    assert on[0]["repairable"] is False, "مفعّلةً: حاجب"
    # والبلاغُ يسمّي المعرّفين وقراءةَ القرار كي يعرف الكاتبُ ما يُصلِح.
    assert "F1" in on[0]["note"] and "F2" in on[0]["note"]


def test_c6_naming_the_difference_is_correct_not_a_defect():
    """تمييزُ المباشر عن المرآة **عقدٌ محفوظ** — وقد أثبت الصنف ١١ أنّ
    معاقبتَه كانت تحجب تقارير سليمة. فالشرطُ غيابُ الإفصاح لا وجودُ
    قراءتين."""
    import silk_quality_gate as G
    dr = {"report": {"text": "## 3. نظرة عامة على السوق\nالتصريح المباشر "
                             "1.2 مليون دولار، وبيانات المرآة 9.6 مليون "
                             "دولار — فجوة ثمانية أضعاف لم تُحسم."},
          "missions": {"trade_flow": {"summary": "x", "findings": [
              {"value": 1_200_000, "note": "واردات مصرَّحة 2023"},
              {"value": 9_600_000, "note": "مرآة صادرات الشركاء 2023"}]}},
          "analyst": {"by_category": {}}}
    with _env(SILK_FIGURE_STORE="1"):
        assert G._check_metric_value_divergence({}, dr) == []


def test_c6_one_reading_or_a_repeated_value_is_not_a_divergence():
    import silk_quality_gate as G
    single = {"report": {"text": "## 4. الديناميكيات\nنمو 6.1% عبر "
                                 "2020–2024."},
              "missions": {"trade_flow": {"summary": "x", "findings": [
                  {"value": 6.1, "note": "نمو مركّب"}]}},
              "analyst": {"by_category": {}}}
    same = _two_readings_dr("## 1. الخلاصة\nالحصة السعودية 10.44%.\n\n"
                            "## 6. المنافسة\nوالحصة السعودية 10.44% أيضاً.")
    with _env(SILK_FIGURE_STORE="1"):
        assert G._check_metric_value_divergence({}, single) == []
        assert G._check_metric_value_divergence({}, same) == [], \
            "تكرارُ القيمة نفسِها ليس تعارضاً"


def test_c6_small_values_are_matched_only_with_a_percent_sign():
    """قيدُ صدق: «10» من «2010» ليس ظهوراً للقيمة 10.

    `_significant_number_mentions` يشترط ≥1000 كي لا يُطابِق مصادفةً،
    والحصصُ دونه — فتُطابَق بحرفها **متبوعةً بعلامة نسبة** حصراً."""
    from silk_quality_gate import _rendered_figure_positions as pos
    assert pos("الحصة 10.44% من السوق", 10.44)
    assert pos("في عام 2010 بلغت 12", 10.0) == []
    assert pos("النمو 6.1% سنوياً", 6.1)


def test_c6_shared_value_across_entities_is_always_a_warning():
    """«10.44% هي أيضاً حصةُ الصين» — سؤالٌ لا حجب (قد يتطابق رقمان صدقاً)."""
    import silk_quality_gate as G
    dr = {"report": {"text": "## 6. المشهد التنافسي\nالسعودية بحصة 10.44%، "
                             "والصين بحصة 10.44%."}}
    for flag in (None, "1"):
        with _env(SILK_FIGURE_STORE=flag):
            out = G._check_shared_value_across_entities(dr)
            assert out and out[0]["check"] == "shared_value_across_entities"
            assert out[0]["repairable"] is True, "تحذيرٌ دائم"
    assert "shared_value_across_entities" not in G.FAIL_TRIGGER_CHECKS
    # واسمُ الكيان يُبلَّغ بلا رابطِ بدايته.
    note = G._check_shared_value_across_entities(dr)[0]["note"]
    assert "«الصين»" in note, note


# ── مخزنُ الأرقام نفسُه ──────────────────────────────────────────────────

def test_c6_store_gives_every_reading_a_stable_identity():
    import silk_figure_store as FS
    dr = _two_readings_dr("")
    first = FS.build(dr["missions"], dr["analyst"])
    second = FS.build(dr["missions"], dr["analyst"])
    ids = [f["id"] for f in first["figures"]]
    assert ids == ["F1", "F2"]
    assert ids == [f["id"] for f in second["figures"]], \
        "المعرّفُ مستقرٌّ بين تشغيلتين — وإلّا لا معنى للإحالة به"
    for f in first["figures"]:
        assert set(f) >= {"id", "metric", "value", "year", "source",
                          "method", "confidence"}


def test_c6_store_never_stores_a_reading_without_a_value():
    """عقدُ عدم الاختلاق: قراءةٌ بلا قيمةٍ لا تُخزَّن ولا تُصفَّر."""
    import silk_figure_store as FS
    missions = {"pricing_scout": {"findings": [
        {"value": None, "note": "سعر التجزئة غير متاح", "confidence": 0.0},
        {"value": 7.49, "note": "سعر رف مرصود"}]}}
    store = FS.build(missions)
    assert [f["value"] for f in store["figures"]] == [7.49]


def test_c6_decision_reading_rule_is_documented_and_deterministic():
    """القاعدةُ الواحدة: الأحدثُ سنةً، ثم المباشرُ قبل المرآة، ثم الأعلى ثقةً.

    كلُّ مرشِّحٍ له سببٌ يُقال للقارئ، والتعادلُ يُحسَم بأوّل معرّف — فلا
    عشوائيةَ ولا نتيجةٌ غيرُ قابلةٍ للتكرار."""
    import silk_figure_store as FS
    figs = [
        {"id": "F1", "metric": "imports", "value": 1.0, "year": 2023,
         "method": "mirror", "confidence": 0.9},
        {"id": "F2", "metric": "imports", "value": 2.0, "year": 2023,
         "method": "direct", "confidence": 0.5},
        {"id": "F3", "metric": "imports", "value": 3.0, "year": 2021,
         "method": "direct", "confidence": 1.0},
    ]
    # الأحدثُ سنةً يسبق، وبين المتساويَين المباشرُ يسبق المرآة.
    assert FS.decision_reading(figs, "imports") == "F2"
    # قراءةٌ بلا سنةٍ لا تُرقَّى بمجهول.
    undated = [dict(figs[0], id="F9", year=None, method="direct",
                    confidence=1.0)]
    assert FS.decision_reading(figs + undated, "imports") == "F2"
    assert FS.decision_reading(figs, "nothing") is None


def test_c6_mirror_and_direct_are_one_metric_two_methods():
    """لو صُنِّفت المرآةُ مؤشّراً آخر لَما كان «قيمتان لمؤشرٍ واحد» قابلاً
    للكشف أصلاً."""
    import silk_figure_store as FS
    assert FS.classify("مرآة صادرات الشركاء 2023") == ("imports", "mirror")
    assert FS.classify("واردات مصرَّحة 2023") == ("imports", "direct")
    assert FS.classify("حصة السعودية") == ("supplier_share", "reported")
    assert FS.classify("HHI تركّز") == ("concentration", "reported")
    assert FS.classify("بلا ملاحظة مطابقة") == ("other", "reported")


def test_c6_store_never_borrows_a_year_from_the_clock():
    """الصنف ٣ سرى هنا أيضاً: سنةٌ غائبةٌ تبقى `None`."""
    import silk_figure_store as FS
    assert FS._year_of({"note": "واردات بلا سنة"}) is None
    assert FS._year_of({"note": "واردات 2024"}) == 2024
    assert FS._year_of({"data_year": 2021, "note": "واردات 2024"}) == 2021


# ── عقدُ عدم المساس على المسار الكامل ────────────────────────────────────

def test_c6_prompt_is_untouched_when_the_flag_is_off():
    """بلا الراية: لا معرّفٌ في الموجّه ولا قاعدةٌ إضافية — نفسُ `_facts`."""
    import inspect

    import silk_ai_judge as J
    src = inspect.getsource(J.deep_report)
    assert "silk_figure_store" in src and "_FS.enabled()" in src
    assert "FIGURE_ID_RULE" in src
    # والقاعدةُ تُحقَن **فقط** عند الراية (سلسلةٌ فارغة تُسقَط من الأجزاء).
    assert '*([_figure_rule] if _figure_rule else [])' in src


def test_c6_no_hard_fail_on_any_canonical_blob_with_the_flag_on():
    """شرطُ قبول الجولة الثانية: صفرُ حجبٍ جديد على المدوّنات الاثنتي عشرة
    **والرايةُ مفعّلة** — وإلّا كان تفعيلُها يوقف التسليم."""
    import silk_quality_gate as G
    import silk_render
    hits: dict = {}
    with block_network(), _env(SILK_FIGURE_STORE="1"):
        for key in _canonical_keys():
            out = G.run_quality_gate(silk_render.build_view(_blob(key)))
            got = [f["check"] for f in out["findings"]
                   if f["check"] == "metric_value_divergence"]
            if got:
                hits[key] = got
    assert hits == {}, hits
