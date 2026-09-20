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
    # **تحديثُ قفلٍ مُعلَن (تشديد):** كان هذا التأكيدُ يُقنِّن العيبَ الذي
    # كشفته المراجعةُ الذاتية — مؤشِّرٌ يخصّ كياناً بمفتاحٍ بلا كيان، فحصتا
    # مورّدَين تصيران قراءتين متعارضتين ويُفشَل تقريرٌ صحيح. المفتاحُ الآن
    # يحمل مؤهِّلَه، والطريقةُ كما هي.
    assert FS.classify("حصة السعودية") == ("supplier_share:السعودية",
                                            "reported")
    assert FS.classify("حصة سوقية %") == ("supplier_share", "reported")
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


# ════════════════ الصنف ٧ — عددُ الشروط المفتوحة ════════════════

def _prod_view(key: str) -> dict:
    """عرضٌ مبنيٌّ **كما يبنيه الإنتاج** — المدوّنات مجمّدةٌ بـ`markets: []`
    فلا تُشغِّل `decision_basis` إطلاقاً (منطقةٌ عمياء أُعلِنت في الصنف ١)."""
    import silk_deep_pillars
    import silk_render
    blob = _blob(key)
    dr = blob.get("deep_research") or {}
    mk = blob.get("market") or {}
    dec = silk_deep_pillars.decide_for_deep(dr, product_card=None,
                                            regulatory=None)
    row = {"iso3": mk.get("iso3") or "XXX",
           "name_ar": mk.get("name_ar") or "سوق",
           "name_en": mk.get("name_en") or "Market",
           "country": mk.get("name_ar") or "سوق", "rank": 1, "deep": True,
           "components": silk_deep_pillars.build_components(dr),
           "decision": dec}
    if dec.get("score") is not None:
        row["total_score"] = dec["score"]
    if dec.get("confidence") is not None:
        row["confidence"] = dec["confidence"]
    blob = dict(blob)
    blob["markets"] = [row]
    return silk_render.build_view(blob)


def test_c7_five_surfaces_read_one_list():
    """**الجذرُ المرصود حرفياً**: قائمةٌ واحدة، خمسةُ سطوحٍ بأربعِ سلوكيّات
    — `[:3]` في الطرفية، `[:4]` في نصّ المحادثة، إعادةُ بناءٍ ثم `[:6]` في
    لوحة الأساس، وكاملةٌ في موضعَي المشغّل."""
    import inspect

    import silk_render as R
    import silk_reports
    for mod in (R, silk_reports):
        src = inspect.getsource(mod)
        assert "open_conditions(" in src, mod.__name__
    # ولا قصَّ يدويّ باقياً على أيّ سطح.
    rsrc = inspect.getsource(R)
    for stale in ('(ed.get("conditions") or [])[:3]',
                  '(ed.get("conditions") or [])[:4]'):
        assert stale not in rsrc, stale


def test_c7_count_is_always_the_full_count_and_truncation_is_disclosed():
    """سطحٌ يعرض ثلاثةً من ثمانيةٍ **يقول ذلك** — الصمتُ هو العيب."""
    import silk_render as R
    ed = {"conditions": [f"شرط {i}" for i in range(1, 9)]}
    with _env(SILK_OPEN_CONDITIONS_SINGLE=None):
        off = R.open_conditions(ed, 3)
    with _env(SILK_OPEN_CONDITIONS_SINGLE="1"):
        on = R.open_conditions(ed, 3)
    assert off["count"] == on["count"] == 8, "العددُ الكامل في الحالتين"
    assert len(off["shown"]) == 3, "مطفأةً: السقفُ القائم للسطح"
    assert len(on["shown"]) == R.OPEN_CONDITIONS_CAP, "مفعّلةً: سقفٌ موحَّد"
    assert off["more_note"] and on["more_note"], "القصُّ يُعلَن دائماً"
    # مخفيٌّ واحد ⇒ صيغةُ المفرد (أربعةُ شروطٍ بسقف ثلاثة).
    one = R.open_conditions({"conditions": [f"ش{i}" for i in range(4)]}, 3)
    assert one["hidden"] == 1 and "شرطٌ آخر" in one["more_note"], one


def test_c7_reader_wording_is_not_replaced_by_engine_measurement_language():
    """**تصحيحٌ جاء من القياس.** جُرِّبت قراءةُ نصوصِ المحرّك مباشرةً
    فأعادت لغةَ القياس الداخلية إلى لوحة الأساس («متوسط المتاح من:
    log10(TAM)/9…») — أي أنّ تفعيل الراية كان **يُعيد** عيبَ الصنف ١.

    العيبُ المرصود لم يكن إعادةَ البناء بل انزياحَ العدد وصمتَ القصّ."""
    with block_network(), _env(SILK_OPEN_CONDITIONS_SINGLE="1"):
        basis = ((_prod_view("dza_peanut_butter").get("decision") or {})
                 .get("basis") or {})
    conds = " ".join(str(c) for c in (basis.get("conditions") or []))
    assert conds.strip(), "لوحةُ الأساس بلا شروط — المسارُ لم يُشغَّل"
    for leak in ("log10", "متوسط المتاح من", "مقسوماً على"):
        assert leak not in conds, leak
    assert "عالِجه قبل الالتزام" in conds or "أكمِلها" in conds, conds


def test_c7_basis_exposes_both_counts_and_they_agree():
    """عددُ الصياغة المعروضة وعددُ قائمة المحرّك — كلاهما مُعلَن، ويتطابقان
    لأنّ كلتيهما من الأعمدة نفسِها. اختلافُهما إشارةُ انحدارٍ لا تُخفى."""
    with block_network():
        basis = ((_prod_view("dza_peanut_butter").get("decision") or {})
                 .get("basis") or {})
    assert basis.get("conditions_count") is not None
    assert basis["conditions_count"] == basis.get("engine_conditions_count")


def test_c7_gate_catches_two_different_counts_in_one_report():
    """**العيبُ المرصود**: ثلاثةٌ في الملخّص، واثنان في التوصيات."""
    import silk_quality_gate as G
    view = {"markets": [{"entry_decision": {"conditions": ["أ", "ب", "ج"]}}]}
    dr = {"report": {"text": "## 1. الخلاصة التنفيذية\nاستند الحكم إلى "
                             "ثلاثة شروط مفتوحة.\n\n## 10. التوصيات "
                             "الاستراتيجية\nيبقى شرطين مفتوحين قبل "
                             "الالتزام."}}
    with _env(SILK_OPEN_CONDITIONS_SINGLE=None):
        off = G._check_open_conditions_count_mismatch(view, dr)
    with _env(SILK_OPEN_CONDITIONS_SINGLE="1"):
        on = G._check_open_conditions_count_mismatch(view, dr)
    assert [f["check"] for f in off] == ["open_conditions_count_mismatch"]
    assert off[0]["repairable"] is True and on[0]["repairable"] is False


def test_c7_gate_catches_a_count_that_contradicts_the_actual_list():
    import silk_quality_gate as G
    view = {"markets": [{"entry_decision": {"conditions": ["أ", "ب", "ج"]}}]}
    wrong = {"report": {"text": "## 1. الخلاصة\nاستند الحكم إلى شرطين "
                                "مفتوحين."}}
    out = G._check_open_conditions_count_mismatch(view, wrong)
    assert out and "الفعلية 3" in out[0]["note"], out
    right = {"report": {"text": "## 1. الخلاصة\nاستند الحكم إلى ثلاثة شروط "
                                "مفتوحة."}}
    assert G._check_open_conditions_count_mismatch(view, right) == []


def test_c7_a_count_outside_the_open_conditions_sense_is_not_counted():
    """قيدُ صدق: «ثلاثة شروط صحّية» ليست عدَّ شروطِ القرار — وبلا هذا القيد
    تُطلِق القاعدةُ على كلّ قسمٍ تنظيميّ."""
    import silk_quality_gate as G
    view = {"markets": [{"entry_decision": {"conditions": ["أ", "ب", "ج"]}}]}
    dr = {"report": {"text": "## 7. التنظيم\nتشترط الجهة ثلاثة شروط صحّية "
                             "للشحن."}}
    assert G._check_open_conditions_count_mismatch(view, dr) == []


def test_c7_flag_changes_nothing_on_any_production_shaped_view():
    """شرطُ قبول الجولة: فرقُ البيانات المهيكلة مفعّلةً ضدّ مطفأة.

    يُقاس على **شكل الإنتاج** لا على المدوّنة الخام: المدوّناتُ مجمّدةٌ
    بـ`markets: []` فلا تُشغِّل `decision_basis`، وقياسٌ عليها وحدها يُنتِج
    «صفرَ فرق» **فراغاً** لا دليلاً (منطقةٌ عمياء أُعلِنت في الصنف ١)."""
    import json

    import silk_quality_gate as G
    import silk_reports

    def snap(key: str) -> tuple:
        view = _prod_view(key)
        return (json.dumps(view, ensure_ascii=False, sort_keys=True,
                           default=str),
                silk_reports.render_markdown(view),
                G.run_quality_gate(view)["verdict"])

    diffs: dict = {}
    with block_network():
        for key in _canonical_keys():
            with _env(SILK_FIGURE_STORE=None,
                      SILK_OPEN_CONDITIONS_SINGLE=None):
                off = snap(key)
            with _env(SILK_FIGURE_STORE="1",
                      SILK_OPEN_CONDITIONS_SINGLE="1"):
                on = snap(key)
            if off != on:
                diffs[key] = [n for n, (a, b) in
                              zip(("view", "md", "verdict"), zip(off, on))
                              if a != b]
    assert diffs == {}, diffs


# ════════════════ الصنف ٨ — انضباطُ الثقة والدرجة ════════════════

_PILLARS_FULL = {
    "market": {"value": 0.8, "missing": []},
    "competition": {"value": 0.43, "missing": []},
    "regulatory": {"value": 0.9, "missing": []},
    "profit": {"value": 0.6, "missing": []},
    "risk": {"value": 0.5, "missing": []},
}


def _pillars_missing_core() -> dict:
    out = {k: dict(v) for k, v in _PILLARS_FULL.items()}
    out["profit"] = {"value": None, "missing": ["margin"]}
    return out


def test_c8_core_pillars_are_named_not_guessed():
    """القاعدةُ تحتاج تعريفاً: قرارُ دخولٍ لا يُبنى بلا معرفةِ الطلب وجدارِ
    السعر ووجودِ هامش. والتنظيمُ والمخاطرُ بوّابتان — غيابُهما **شرطٌ
    مفتوح** لا عجزٌ عن التقييم، فلا يمنعان «عالية» وحدهما."""
    import silk_decision as D
    assert D.CORE_PILLARS == ("market", "competition", "profit")
    assert D.missing_core_pillars(_PILLARS_FULL) == []
    assert D.missing_core_pillars(_pillars_missing_core()) == ["profit"]
    only_gates = {k: dict(v) for k, v in _PILLARS_FULL.items()}
    only_gates["regulatory"] = {"value": None, "missing": ["x"]}
    only_gates["risk"] = {"value": None, "missing": ["y"]}
    assert D.missing_core_pillars(only_gates) == []
    assert D.confidence_band_cap(only_gates, []) is None


def test_c8_high_confidence_is_capped_by_a_missing_core_pillar():
    import silk_decision as D
    from silk_style_contract import confidence_band_label as label
    assert D.confidence_band_cap(_pillars_missing_core(), []) == "medium"
    assert label(91) == "عالية"
    assert label(91, cap="medium") == "متوسطة", "التسميةُ تُسقَّف"
    assert label(40, cap="medium") == "منخفضة", "السقفُ لا يرفع نطاقاً"
    assert label(91, "en", cap="medium") == "medium"


def test_c8_two_open_conditions_also_cap_the_band():
    import silk_decision as D
    assert D.confidence_band_cap(_PILLARS_FULL, ["أ"]) is None
    assert D.confidence_band_cap(_PILLARS_FULL, ["أ", "ب"]) == "medium"
    assert D.MAX_CONDITIONS_FOR_HIGH == 2


def test_c8_age_decay_follows_a_published_schedule():
    """جدولٌ معلَنٌ لا معامِلٌ مخفيّ — بياناتُ عشرِ سنواتٍ تصف سوقاً آخر."""
    import silk_decision as D
    assert [D.age_decay_factor(y) for y in (0, 2, 3, 5, 6, 10, 11, 40)] == \
        [1.0, 1.0, 0.9, 0.9, 0.75, 0.75, 0.6, 0.6]
    assert D.age_decay_factor(None) == 1.0
    assert D.age_decay_factor(-3) == 1.0
    # والجدولُ نفسُه منشورٌ كثابتٍ يُقرأ لا مدفونٌ في شرطٍ.
    assert D.CONFIDENCE_AGE_DECAY[0] == (2, 0.00)


def test_c8_rendered_arithmetic_reproduces_the_score_exactly():
    """**شرطُ المهمة حرفياً**: «اختبارٌ يثبت أنّ الحساب المعروض يُعيد إنتاج
    الدرجة». يُقاس على الاثنتي عشرة مدوّنة لا على مثالٍ واحد."""
    import silk_decision as D
    import silk_deep_pillars
    with block_network():
        for key in _canonical_keys():
            dec = silk_deep_pillars.decide_for_deep(
                _blob(key).get("deep_research") or {},
                product_card=None, regulatory=None)
            opt = dec.get("weights_option") or "A"
            arith = D.score_arithmetic(dec.get("pillars"),
                                       D.WEIGHT_OPTIONS[opt])
            assert arith["score"] == dec.get("score"), (key, arith, dec.get("score"))


def test_c8_arithmetic_respects_the_min_pillars_rule():
    """**قِياسٌ كشف عيباً كنتُ سأُدخِله**: الصيغةُ الأولى حسبت درجةً لإحدى
    عشرةَ مدوّنةٍ من اثنتي عشرة **حجب المحرّكُ درجتَها عمداً** — فكان
    الحسابُ المعروض يُظهِر رقماً قال المحرّكُ إنه لا يُصدره. حسابٌ يخالف
    الدرجةَ أسوأُ من حسابٍ غائب لأنه يُوهِم القارئَ بالتحقّق."""
    import silk_decision as D
    thin = {"market": {"value": 0.8, "missing": []},
            "competition": {"value": None, "missing": ["x"]},
            "regulatory": {"value": None, "missing": ["y"]},
            "profit": {"value": None, "missing": ["z"]},
            "risk": {"value": None, "missing": ["w"]}}
    arith = D.score_arithmetic(thin, D.WEIGHT_OPTIONS["A"])
    assert arith["score"] is None
    assert arith["withheld_reason"], "الامتناعُ يُقال بسببه لا يُترَك فراغاً"
    assert arith["computed_pillars"] == 1
    # وبأعمدةٍ كافية يُحسَب فعلاً، والأوزانُ مُعاد تسويتها معلَنةً.
    full = D.score_arithmetic(_PILLARS_FULL, D.WEIGHT_OPTIONS["A"])
    assert full["score"] is not None and full["renormalised"] is False


def test_c8_basis_additions_are_purely_additive_behind_the_flag():
    """مفعّلةً: مفاتيحُ **جديدة** فقط — لا قيمةَ قائمةٌ تتغيّر."""
    import silk_render as R
    ed = {"schema": "silk.decision/v1", "score": 0.579, "confidence": 0.9,
          "coverage": 0.8, "weights_option": "A", "conditions": ["أ"],
          "pillars": _pillars_missing_core()}
    with _env(SILK_CONFIDENCE_DISCIPLINE=None):
        off = R.decision_basis(ed, None, "ar")
    with _env(SILK_CONFIDENCE_DISCIPLINE="1"):
        on = R.decision_basis(ed, None, "ar")
    assert set(off) <= set(on), "مفتاحٌ اختفى بالتفعيل"
    for key in off:
        assert off[key] == on[key], f"قيمةٌ قائمة تغيّرت: {key}"
    for key in ("score_arithmetic", "score_arithmetic_line",
                "confidence_band", "verification_rate_pct",
                "confidence_band_cap"):
        assert key in on and key not in off, key
    assert on["confidence_band"] == "متوسطة", on["confidence_band"]


def test_c8_verification_rate_is_named_as_not_being_confidence():
    """البلاغ: «نسبةُ التحقّق من البيانات معروضةٌ كأنها ثقةُ الحكم»."""
    import silk_i18n as I
    import silk_render as R
    note = I.t("verification_rate_note", "ar")
    assert "غير" in note and "ثقة" in note
    ed = {"schema": "silk.decision/v1", "score": 0.579, "confidence": 0.9,
          "coverage": 0.8, "weights_option": "A", "conditions": [],
          "pillars": dict(_PILLARS_FULL)}
    with _env(SILK_CONFIDENCE_DISCIPLINE="1"):
        basis = R.decision_basis(ed, None, "ar")
    assert basis["verification_rate_pct"] == 80
    assert basis["confidence_pct"] == 90, "المقياسان مختلفان ولا يُدمَجان"


def test_c8_gate_severity_follows_the_flag_and_spares_a_capped_label():
    import silk_quality_gate as G
    view = {"markets": [{"entry_decision": {
        "pillars": _pillars_missing_core(), "conditions": []}}],
        "decision": {"basis": {}}}
    high = {"report": {"text": "## 1. الخلاصة\nالحكم بثقة عالية."}}
    with _env(SILK_CONFIDENCE_DISCIPLINE=None):
        off = G._check_high_confidence_with_missing_pillar(view, high)
    with _env(SILK_CONFIDENCE_DISCIPLINE="1"):
        on = G._check_high_confidence_with_missing_pillar(view, high)
    assert off and off[0]["repairable"] is True
    assert on and on[0]["repairable"] is False
    # تسميةٌ مسقوفةٌ فعلاً ⇒ لا إطلاقة.
    medium = {"report": {"text": "## 1. الخلاصة\nالحكم بثقة متوسطة."}}
    assert G._check_high_confidence_with_missing_pillar(view, medium) == []
    # وأعمدةٌ كاملةٌ بلا شروط ⇒ «عالية» مشروعة.
    ok_view = {"markets": [{"entry_decision": {
        "pillars": dict(_PILLARS_FULL), "conditions": []}}],
        "decision": {"basis": {}}}
    assert G._check_high_confidence_with_missing_pillar(ok_view, high) == []


def test_c8_all_three_flags_add_only_new_keys_on_production_views():
    """شرطُ قبول الجولة على الرايات الثلاث مجتمعةً: لا قيمةَ قائمة تتغيّر،
    ولا حكمٌ يتغيّر، ولا حجبٌ جديدٌ على أيّ مدوّنة."""
    import silk_quality_gate as G
    import silk_reports
    flags = {"SILK_FIGURE_STORE": "1", "SILK_OPEN_CONDITIONS_SINGLE": "1",
             "SILK_CONFIDENCE_DISCIPLINE": "1"}
    off_flags = {k: None for k in flags}
    problems: dict = {}
    with block_network():
        for key in _canonical_keys():
            with _env(**off_flags):
                v_off = _prod_view(key)
                md_off = silk_reports.render_markdown(v_off)
                g_off = G.run_quality_gate(v_off)
            with _env(**flags):
                v_on = _prod_view(key)
                md_on = silk_reports.render_markdown(v_on)
                g_on = G.run_quality_gate(v_on)
            issues = []
            if g_off["verdict"] != g_on["verdict"]:
                issues.append(f"verdict {g_off['verdict']}→{g_on['verdict']}")
            if md_off != md_on:
                issues.append("md")
            b_off = (v_off.get("decision") or {}).get("basis") or {}
            b_on = (v_on.get("decision") or {}).get("basis") or {}
            for k in b_off:
                if b_off[k] != b_on.get(k):
                    issues.append(f"basis.{k} changed")
            if issues:
                problems[key] = issues
    assert problems == {}, problems


# ════════════ الصنف ٩ — رقمٌ مشتقٌّ بلا إسنادٍ ولا عملة ════════════

def _engine_dn(cost: "float | None" = 1.2, cur: str = "SAR") -> list:
    """أرقامُ القرار **كما يحسبها المحرّك** لفئةٍ لها وحدةُ سوقٍ مسجّلة —
    لا جدولٌ مكتوبٌ باليد: الاستبعادُ («الشحن بلا سعر ممر متحقق»، «رسوم
    التسجيل غير متحققة») من الحساب نفسِه، وهو مصدرُ العيب المرصود."""
    import silk_economics as E
    return E.build_decision_numbers(
        category="milk", market_iso3="EGY", cost_per_unit=cost,
        cost_currency=cur,
        reverse={"max_exw": 3.0, "unit": "لتر", "currency": cur})


def _dn_view(dn: list, text: str) -> dict:
    return {"deep_research": {"report": {"text": text},
                              "economics": {"decision_numbers": dn}}}


def test_c9_severity_follows_the_flag():
    """الحجبُ **مع الراية فقط** — قرارُ المالك «لا حجب جديداً» سليم."""
    import silk_quality_gate as G
    with _env(SILK_DERIVED_PROVENANCE=None):
        assert "reference_to_nonexistent_figure" \
            not in G.effective_fail_triggers()
    with _env(SILK_DERIVED_PROVENANCE="1"):
        assert "reference_to_nonexistent_figure" in G.effective_fail_triggers()
    # التحذيريُّ لا يدخل مجموعةَ الحجب في أيّ حال.
    assert "max_loss_without_components" not in G.FAIL_TRIGGER_CHECKS
    with _env(SILK_DERIVED_PROVENANCE="1"):
        assert "max_loss_without_components" \
            not in G.effective_fail_triggers()


def test_c9_gate_catches_a_number_for_a_figure_the_engine_declares_unknown():
    """**العيبُ المرصود**: المتنُ يُسمّي بنداً برقمٍ في إطارٍ محسوب بينما
    المحرّكُ يُعلنه فجوة — «خارطةُ الطريق تُحيل إلى شريحةٍ لم تُحسَب»."""
    import silk_quality_gate as G
    dn = _engine_dn(cost=None)          # بلا تكلفةٍ ⇒ البنودُ فجواتٌ معلنة
    gaps = [e["name"] for e in dn if e.get("tier") == "gap"]
    assert "نقطة التعادل" in gaps and any("أقصى خسارة" in g for g in gaps)
    view = _dn_view(dn, "تبلغ نقطة التعادل 3 شحنات، وأقصى خسارة إن فشل "
                        "الدخول 8,900 ريال.")
    out = G._check_reference_to_nonexistent_figure(view)
    assert len(out) == 1 and out[0]["check"] == "reference_to_nonexistent_figure"
    assert out[0]["repairable"] is False
    assert "نقطة التعادل" in out[0]["note"]
    assert any("أقصى خسارة" in x for x in [out[0]["note"]])


def test_c9_the_declared_gap_wording_is_the_legitimate_form():
    """«غير محسوب — الناقص: …» هي الصيغةُ المشروعة ولا تُحتسَب — وإلّا
    عاقبَ الفحصُ الإفصاحَ نفسَه (سابقةُ حارسِ سياق النفي القائم)."""
    import silk_quality_gate as G
    dn = _engine_dn(cost=None)
    ok = _dn_view(dn, "نقطة التعادل غير محسوبة — الناقص: تكلفة إنتاج "
                      "الوحدة لديك (دقيقة واحدة لإدخالها).")
    assert G._check_reference_to_nonexistent_figure(ok) == []
    # وبندٌ **محسوب** برقمه ليس عيباً بحال.
    dn2 = _engine_dn()
    est = [e["name"] for e in dn2 if e.get("tier") == "estimated"]
    assert est, "الفئةُ المسجّلة تُنتِج بنداً محسوباً واحداً على الأقلّ"
    assert G._check_reference_to_nonexistent_figure(
        _dn_view(dn2, f"{est[0]} يبلغ 26,070 لتراً.")) == []


def test_c9_needle_never_swallows_general_prose():
    """إبرةُ البند مقطعٌ متّصلٌ يضمّ كلمةً دالّةً — «الزمن من» وحدَها تسعُ
    نثراً عاماً فتُضَمّ الثالثة."""
    import silk_quality_gate as G
    assert G._dn_needle("نقطة التعادل") == G._norm_ar("نقطة التعادل")
    assert G._dn_needle("أقصى خسارة إن فشل الدخول") == G._norm_ar("أقصى خسارة")
    assert G._dn_needle("الزمن من القرار إلى أول فاتورة") == \
        G._norm_ar("الزمن من القرار")


def test_c9_max_loss_single_figure_is_flagged_when_its_base_excluded_a_part():
    """سقفُ المخاطرة رقماً مفرداً فوق أساسٍ استُبعد منه مكوّنٌ سمّاه المحرّك
    — يُقرأ شاملاً وهو ناقص. المرجعُ حتميّ من `method` نفسِه."""
    import silk_quality_gate as G
    dn = _engine_dn()
    entry = [e for e in dn if e["name"].startswith("كلفة الدخول")][0]
    assert any(m in entry["method"] for m in G._ENGINE_EXCLUSION_MARKS), \
        "هذا الاختبار يقيس حالةَ الاستبعاد المُعلَنة في الحساب"
    bad = _dn_view(dn, "أقصى خسارة إن فشل الدخول 8,900 ريال.")
    out = G._check_max_loss_without_components(bad)
    assert len(out) == 1 and out[0]["check"] == "max_loss_without_components"
    assert out[0]["repairable"] is True
    # المدى إفصاحٌ، وتسميةُ الخارج إفصاحٌ — كلٌّ منهما يُعفي وحده.
    for ok_text in ("أقصى خسارة إن فشل الدخول بين 7,100 و 10,700 ريال.",
                    "أقصى خسارة إن فشل الدخول 8,900 ريال، ولا يشمل الرقم "
                    "كلفة الشحن ورسوم التسجيل.",
                    "أقصى خسارة غير محسوبة — الناقص: تكلفتك."):
        assert G._check_max_loss_without_components(
            _dn_view(dn, ok_text)) == [], ok_text


def test_c9_max_loss_inherits_the_named_unknown_components():
    """المكوّناتُ المستبعَدة من كلفةِ الدخول تنتقل **بأسمائها** إلى سقفِ
    المخاطرة ونقطةِ التعادل — لا سقفَ يُقدَّم شاملاً وهو ناقص."""
    with _env(SILK_DERIVED_PROVENANCE="1"):
        dn = _engine_dn()
    entry = [e for e in dn if e["name"].startswith("كلفة الدخول")][0]
    ml = [e for e in dn if e["name"].startswith("أقصى خسارة")][0]
    assert entry.get("unknown"), "الشحنُ والرسومُ غيرُ المتحققين مُسمَّيان"
    assert ml.get("unknown") == entry["unknown"]
    assert any("الشحن" in u for u in ml["unknown"])


def test_c9_every_input_carries_a_source_or_an_assumption_tag():
    """لا مدخلَ يُعرَض عارياً: مصدرٌ مرصود أو وسمُ «افتراض» صريح — فلا
    تُقرَأ معلمةُ سيناريو قياساً."""
    import silk_narrative as N
    with _env(SILK_DERIVED_PROVENANCE="1"):
        dn = _engine_dn()
        seen = 0
        for e in dn:
            for i in (e.get("inputs") or []):
                seen += 1
                rendered = N.fmt_derived_input(i)
                assert "—" in rendered, rendered
                assert ("المصدر:" in rendered
                        or N.ASSUMPTION_TAG_AR in rendered), rendered
        assert seen >= 5, seen
        # الوسمُ يُطبَع فعلاً على مدخلٍ مفترض واحدٍ على الأقلّ.
        allp = " ".join(N.fmt_derived(e) for e in dn)
        assert N.ASSUMPTION_TAG_AR in allp


def test_c9_iso_currency_never_guesses_an_ambiguous_name():
    """«دينار» تسعُ خمسَ دول — رمزٌ مخمَّنٌ اختلاقٌ لا ترجمة، فيُعاد فراغاً
    ويبقى النصُّ كما صرّح به المالك."""
    import silk_narrative as N
    assert N.iso_currency("ريال") == "SAR"
    assert N.iso_currency("usd") == "USD"
    assert N.iso_currency("دينار") == ""
    assert N.iso_currency("") == ""
    with _env(SILK_DERIVED_PROVENANCE="1"):
        import silk_economics as E
        assert E._unit_cur("ريال") == "SAR"
        assert E._unit_cur("دينار") == "دينار"      # لا تخمين
        assert E._unit_cur("") == "بعملة تكلفتك"


def test_c9_flag_off_adds_no_field_and_no_prompt_line():
    """عقدُ عدمِ المساس: بلا الراية لا حقلَ إسنادٍ يُضاف ولا قاعدةَ تُلحَق."""
    import silk_narrative as N
    with _env(SILK_DERIVED_PROVENANCE=None):
        dn = _engine_dn()
        for e in dn:
            assert "inputs" not in e and "unknown" not in e, e["name"]
            assert N.fmt_derived(e) == str(e.get("method") or "")
        assert N.derived_provenance_enabled() is False
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_ai_judge.py"),
        encoding="utf-8").read()
    assert "_derived_rule = \"\"" in src
    assert "*([_derived_rule] if _derived_rule else [])" in src


def test_c9_flag_on_only_appends_provenance_to_the_derived_row():
    """شرطُ قبول الصنف: **كلُّ** فرقٍ بين الرايتين إضافةُ إسنادٍ على صفِّ
    رقمٍ مشتقّ — لا قيمةَ ولا مدىً ولا حكمَ ولا سطرَ آخرَ يتغيّر."""
    import silk_reports
    changed: dict = {}
    with block_network():
        for key in _canonical_keys():
            with _env(SILK_DERIVED_PROVENANCE=None):
                off = silk_reports.render_markdown(_prod_view(key)).split("\n")
            with _env(SILK_DERIVED_PROVENANCE="1"):
                on = silk_reports.render_markdown(_prod_view(key)).split("\n")
            assert len(off) == len(on), key
            diffs = [(a, b) for a, b in zip(off, on) if a != b]
            changed[key] = len(diffs)
            for a, b in diffs:
                # الصفُّ نفسُه: العمودان الأوّلان (الاسمُ والقيمة) كما هما.
                assert a.split("|")[:3] == b.split("|")[:3], (key, a, b)
                assert "المدخلات:" in b and "المدخلات:" not in a, (key, b)
                assert len(b) > len(a), (key, a, b)
    # العددُ **مقيسٌ لكلّ مدوّنة** لا مُقدَّر: بندٌ محسوبٌ واحدٌ في المدوّنات
    # بلا تكلفةٍ مُدخَلة (الشحنةُ التجريبية وحدها)، وثلاثةٌ في مدوّنتَي
    # الجولة الثانية (تكلفةٌ مُدخَلة ⇒ كلفةُ الدخول وسقفُ المخاطرة أيضاً)،
    # وصفرٌ في `fettuccine` (فئةٌ بلا وحدةِ سوقٍ مسجّلة فلا بندَ محسوب).
    # العددُ **مقيسٌ لكلّ مدوّنة**: بندٌ محسوبٌ واحدٌ حيث لا تكلفةَ مُدخَلة
    # (الشحنةُ التجريبية وحدها)، وثلاثةٌ حيث أُدخِلت تكلفةٌ بعملةٍ مختلفةٍ
    # عن سعر الرف (فالتعادلُ فجوة)، **وأربعةٌ** حيث اتّحدت العملتان فحُسِب
    # التعادلُ أيضاً (ليبيا)، وصفرٌ في `fettuccine` (فئةٌ بلا وحدةِ سوق).
    # الموجة د-٢: `netherlands_honey` تكلفةٌ بالدولار وسعرُ رفٍّ باليورو ⇒ ٣؛
    # و`turkey_polymers` فئةٌ صناعية بلا وحدةِ سوقٍ مسجّلة ⇒ ٠ (كـ`fettuccine`).
    _three = ("india_honey", "morocco_juice", "kenya_honey", "netherlands_honey")
    # الموجة د-٣: مدوّنتا التجميل فئةٌ بلا وحدةِ سوقٍ مسجّلة ⇒ لا بندَ محسوب.
    _zero = ("fettuccine", "turkey_polymers", "malaysia_cosmetics",
             "japan_cosmetics")
    expected = {k: 4 if k == "libya_tahini"
                else 3 if k in _three
                else 0 if k in _zero else 1
                for k in _canonical_keys()}
    assert changed == expected, changed


def test_c9_no_hard_fail_on_any_canonical_blob_with_the_flag_on():
    """صفرُ إطلاقةٍ للقاعدتين على المدوّنات الاثنتَي عشرة في الحالتين —
    والحكمُ نفسُه بالراية وبدونها (شرطُ القبول الذي أخفقت فيه قاعدةُ
    الصنف ٥ أوّلَ مرّة: قاعدةٌ تُطلِق على الصحيح لا تُشحَن)."""
    import silk_quality_gate as G
    new = {"reference_to_nonexistent_figure", "max_loss_without_components"}
    fired: dict = {}
    with block_network():
        for key in _canonical_keys():
            with _env(SILK_DERIVED_PROVENANCE=None):
                g_off = G.run_quality_gate(_prod_view(key))
            with _env(SILK_DERIVED_PROVENANCE="1"):
                g_on = G.run_quality_gate(_prod_view(key))
            hits = [f["check"] for f in g_off["findings"] + g_on["findings"]
                    if f["check"] in new]
            if hits:
                fired[key] = hits
            assert g_off["verdict"] == g_on["verdict"], key
    assert fired == {}, fired


def test_c9_the_checks_are_live_not_dormant_on_production_data():
    """القاعدةُ التي لا تُقاس إلّا على مثالٍ مصنوعٍ في اختبارٍ لا يُعرَف أنها
    تلتقط شيئاً في الإنتاج: كلُّ مدوّنةٍ تحمل بنودَ قرارٍ حقيقيةً بفجواتٍ
    معلنة، فالفحصُ يمرّ على نصٍّ حقيقيّ ويصمت — صمتٌ مقيسٌ لا غياب."""
    with block_network():
        for key in _canonical_keys():
            v = _prod_view(key)
            eco = ((v.get("deep_research") or {}).get("economics") or {})
            dn = eco.get("decision_numbers") or []
            assert len(dn) == 5, (key, len(dn))
            assert any(e.get("tier") == "gap" for e in dn), key
            assert (((v.get("deep_research") or {}).get("report") or {})
                    .get("text") or "").strip(), key


# ── مراجعةُ الجولة الثانية الذاتية: سطحُ العميل لا يحمل استشهاداً خاماً ──

def test_c9_client_surface_never_carries_a_raw_latin_citation():
    """**قِياسُ المراجعة الذاتية**: أوّلُ تفعيلٍ للصنف ٩ أدخل الاستشهادَ
    الخام (`icontainers.com — ISO max gross 30,480 kg`) إلى جدولِ أرقامِ
    القرار على **سطح العميل** — وبوابةُ نصّ المُنتَج النهائي رفضت المغربَ
    وأمرّت الهندَ بالتسرّب نفسِه، فالبوابةُ ليست شبكةً موثوقة لهذا.
    المنعُ عند المصدر: `client=True` يُخرِج لغةَ الزائر حصراً."""
    import silk_narrative as N
    inp = {"name": "حمولة حاوية 40 قدماً",
           "source": "icontainers.com — ISO max gross 30,480 kg",
           "source_client": "مواصفة حمولة الحاوية المنشورة"}
    assert "icontainers" in N.fmt_derived_input(inp)              # المشغّل
    assert "icontainers" not in N.fmt_derived_input(inp, True)    # العميل
    assert "مواصفة حمولة الحاوية المنشورة" in N.fmt_derived_input(inp, True)
    # مصدرٌ عربيٌّ خالصٌ يخدم السطحين بلا تكرارِ نصٍّ في المحرّك.
    ar = {"name": "تكلفتك", "source": "بطاقة المنتج التي أدخلتها"}
    assert N.fmt_derived_input(ar, True) == N.fmt_derived_input(ar)
    # واستشهادٌ لاتينيٌّ بلا تسميةٍ عربية يُحال إلى الملحق الذي يحمله فعلاً.
    lat = {"name": "سعر الممر", "source": "https://example.com/lane.csv"}
    assert N.fmt_derived_input(lat, True).endswith(N.APPENDIX_SOURCE_AR)


def test_c9_every_blob_still_renders_a_client_docx_with_the_flag_on():
    """حارسُ انحدارٍ على كلّ المدوّنات: تقريرُ العميل يُبنى فعلاً والرايةُ
    مفعّلة — أيُّ تسرّبٍ لغويٍّ جديدٍ من طبقة الإسناد يُحمِّر هذا الاختبار
    بدل أن يرفضَه المالكُ عند التصدير."""
    import tempfile

    import silk_reports
    with block_network(), _env(SILK_DERIVED_PROVENANCE="1"):
        with tempfile.TemporaryDirectory() as tmp:
            for key in _canonical_keys():
                v = _prod_view(key)
                out = silk_reports.render_client_docx(
                    v, os.path.join(tmp, f"{key}.docx"))
                assert os.path.getsize(out) > 0, key


# ═══ الصنف ١٢ — «غير متاح» وهو مرصود (مفرداتُ التعرّف) ═══

def _repo(name: str) -> str:
    return open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), name), encoding="utf-8").read()


def test_c12_the_repo_own_provider_wording_was_unreadable():
    """**الجذرُ مرصودٌ في هذا الـHEAD**: مزوّدُ التعريفة في الريبو يكتب
    «التعريفة المطبَّقة %» بينما مستخلِصُ الاقتصاد يعرف «تعرفة» وحدَها —
    تباعدٌ داخليّ لا افتراضيّ. و`silk_gap_recovery` يقبل الإملاءَين معاً."""
    import silk_economics as E
    provider = "التعريفة المطبَّقة"
    assert provider in _repo("silk_wto_tariff.py")
    assert not any(w in provider for w in E._TARIFF_WORDS), \
        "لو صار الضيّقُ يقرؤها لسقط سببُ هذا الصنف"
    assert any(w in provider for w in E._TARIFF_WORDS_EXTRA)
    assert "التعريفة" in _repo("silk_gap_recovery.py")
    # الدرس ٢٦٢: المفرداتُ الموسَّعةُ صارت الافتراضَ بلا راية — صيغةُ المزوّد
    # تُقرَأ في الوضعين، والقائمةُ الضيّقةُ تبقى مسجَّلةً شاهداً على ما كان
    # يُفوَّت (ومفتاحُ القياس وحدَه يعيدها لعمود «قبل» في أداة الجرد).
    for _flag in (None, "1"):
        with _env(SILK_RECOGNITION_VOCABULARY=_flag):
            assert any(w in provider for w in E.tariff_words())
    assert set(E._TARIFF_WORDS) < set(E.tariff_words())
    with _env(**{E.LEDGER_OFF_FLAG: "1", "SILK_RECOGNITION_VOCABULARY": None}):
        assert E.tariff_words() == E._TARIFF_WORDS


def test_c12_one_vocabulary_feeds_display_detector_and_guard():
    """مصدرٌ واحد: سجلُّ العرض `CURRENCY_AR` يُغذّي الكاشفَ والحارس — فإضافةُ
    عملةٍ للعرض تُعلِّم الكاشفَ تلقائياً ولا تتباعد ثلاثُ مفردات."""
    import silk_narrative as N
    toks = set(N.currency_tokens())
    assert set(N.CURRENCY_AR) <= toks and set(N.CURRENCY_AR.values()) <= toks
    short = {t for t in N.CURRENCY_AR.values()
             if len(t) < N._CURRENCY_MIN_AR}
    for code, ar in N.CURRENCY_AR.items():
        assert N.currency_in(f"سعر الرف 12 {code}") == code, code
        if ar not in short:
            assert N.currency_in(f"سعر الرف 12 {ar}") == ar, ar
    # منطقةُ العمى المعلنة: الاسمُ الأقصرُ من ثلاثة أحرف («ين») مستبعَد،
    # ورمزُه يُقرَأ — إعلانٌ لا صمت.
    assert short and all(N.currency_in(f"12 {t}") == "" for t in short)
    assert N.currency_in("12 JPY") == "JPY"


def test_c12_no_alternative_of_the_frozen_narrow_pattern_is_lost():
    """الاتحادُ لا الاستبدال — حارسُ انحدارٍ قِيس **قبل** الشحن: «جنيه»
    العارية كانت في النمط القائم ولا مقابلَ لها في سجلّ العرض، فأوّلُ صيغةٍ
    للمصدر الواحد أسقطتها. وكذلك «ر.س» أسقطها قيدُ الطول (حرفان)."""
    import silk_economics as E
    import silk_narrative as N
    frozen = E._CURRENCY_RE.pattern.strip("()").split("|")
    assert len(frozen) >= 15
    for alt in frozen:
        raw = alt.replace("\\", "")
        assert N.currency_in(f"السعر 5 {raw}"), raw


def test_c12_clitics_are_read_and_ordinary_words_are_not():
    """اسمُ العملة في العربية يَرِد ملتصقاً أكثرَ مما يَرِد مفرداً؛ ونمطٌ
    بحدودٍ صارمةٍ يفوّته. وفي المقابل «الصين» و«بين» ليستا عملة."""
    import silk_narrative as N
    for t in ("سعر بالروبية", "والنايرا للعبوة", "سعرٌ فبالدرهم"):
        assert N.currency_in(t), t
    for t in ("حصة الصين 10%", "بين المتجرين", "سنتين", "مؤشر HHI 1490",
              "برنامج SONCAP", "وفق WITS"):
        assert N.currency_in(t) == "", t


def test_c12_an_ambiguous_currency_name_never_gets_an_iso_code():
    """سجلُّ العرض خريطةٌ **واحدٌ لواحد** والعلاقةُ كثيرٌ لواحد: «درهم» تسعُ
    الإماراتَ والمغرب، و«روبية» ستَّ دول. فعكسُ الخريطة كان يُخمِّن دولةً —
    درهمُ المغرب يُوسَم AED. القائمةُ الواسعةُ تعلو العكسَ دائماً."""
    import silk_narrative as N
    for name in ("درهم", "روبية", "جنيه", "ليرة", "بيزو", "فرنك"):
        assert N.iso_currency(name) == "", name
        assert N.currency_in(f"12 {name}") == name, name   # تُقرَأ عملةً
    # «ريال» تبقى SAR: عرفُ الريبو المُسجَّل (`CURRENCY_AR["SAR"]`) وسياقُ
    # مالكِ المنصّة — والخطرُ المتبقّي (ريالُ قطر/اليمن) مُعلَنٌ في
    # docs/report-quality/LOGIC_ISSUES.md ومسكنُه تهيئةُ الصنف ١٠.
    assert N.iso_currency("ريال") == "SAR"


def test_c12_guard_is_silent_because_the_root_is_fixed_for_everyone():
    """**تحديثُ الدرس ٢٦٢.** كان هذا الفحصُ يُطلِق على سبعِ حالاتٍ بلا راية
    (تعريفةٌ مقروءةٌ لم تُقرَأ) ويصمت بها. الآن الجذرُ مُصلَحٌ **بلا راية**:
    مفرداتُ التعرفة واحدةٌ للريبو كلّه (`silk_economics.tariff_words` يقرأ
    منها السجلُّ ومحرّكُ الأعمدة معاً)، فيصمت الحارسُ في الحالين — وصمتُه
    هنا **دليلُ الإصلاح** لا خمودُ حارس: الاختبارُ التالي يقيس القيمة التي
    صحّت، وحالةُ الإطلاق الصناعية أدناه تُثبت أنّ الحارس ما زال حيّاً.
    """
    import silk_quality_gate as G
    with block_network():
        fired = {}
        for flag in (None, "1"):
            with _env(SILK_RECOGNITION_VOCABULARY=flag):
                fired[flag] = {
                    (k, "التعرفة" if "«التعرفة»" in f["note"]
                     else "عملة السعر المرصود")
                    for k in _canonical_keys()
                    for f in G.run_quality_gate(_prod_view(k))["findings"]
                    if f["check"] == "observed_value_declared_unavailable"}
    # التعرفةُ لا تُطلِق في أيّ وضع — جذرُها مُصلَحٌ بلا راية (الدرس ٢٦٢).
    assert not [x for x in fired[None] if x[1] == "التعرفة"], fired[None]
    assert fired["1"] == set(), fired["1"]
    # ويبقى **نصفُ العملة** خلف رايته كما كان (قرارُ مالكٍ معلَّق، مسجَّلٌ في
    # `docs/report-quality/LOGIC_ISSUES.md`) — يُقاس هنا صراحةً لا يُفترَض.
    assert fired[None] == {("india_honey", "عملة السعر المرصود"),
                           ("kenya_honey", "عملة السعر المرصود")}, fired[None]


def test_c12_guard_still_fires_when_a_gap_is_declared_over_a_readable_value():
    """الحارسُ حيٌّ لا خامد: فجوةٌ مُعلَنةٌ لمعطىً تحمله بعثتُه قابلاً
    للقراءة تُطلِقه — يُبنى الشرطُ صناعياً لأنّ المدوّنات لم تعد تحمله."""
    import silk_quality_gate as G
    view = _prod_view("morocco_juice")
    eco = (view.get("deep_research") or {}).get("economics") or {}
    eco["gaps"] = list(eco.get("gaps") or []) + [
        "التعرفة غير متاحة — اعتُمدت 0% معلنةً في الحل العكسي"]
    fired = [f for f in G.run_quality_gate(view)["findings"]
             if f["check"] == "observed_value_declared_unavailable"]
    assert fired and fired[0]["repairable"] is True


def test_c12_the_tariff_correction_holds_with_the_flag_off():
    """كلُّ قيمةٍ تتغيّر **مسمّاةٌ ومحسوبة**: التعريفةُ المُهمَلة كانت تُضخِّم
    أقصى سعرِ مصنعٍ منافسٍ بمقدارها بالضبط — ٨.٦٣١ ÷ ١.٢٥ = ٦.٩٠٤٨ للمغرب،
    و٨٨.٠٩٥٢ ÷ ١.١٠ = ٨٠.٠٨٦٦ لمصر. الدرس ٢٦٢: القيمةُ المصحَّحة صارت هي
    الناتجَ **بلا راية**، فالأرقامُ المُضخَّمة لم تعد تخرج في أيّ وضع."""
    import silk_render

    def exw(key):
        blob = _blob(key)
        eco = (silk_render.build_view(blob).get("deep_research")
               or {}).get("economics") or {}
        return (eco.get("reverse_solve") or {}).get("max_exw")
    with block_network():
        vals = {}
        for flag in (None, "1"):
            with _env(SILK_RECOGNITION_VOCABULARY=flag):
                vals[flag] = {k: exw(k) for k in _canonical_keys()}
    # الرايةُ لم تعد تحكم **التعرفة**؛ يبقى أثرُها على نصف العملة وحده
    # (الهندُ وكينيا — الحلُّ العكسيّ يحتاج عملةَ المرساة).
    assert {k for k in vals[None] if vals[None][k] != vals["1"][k]} == {
        "india_honey", "kenya_honey"}
    fixed = vals[None]
    assert fixed["morocco_juice"] == 6.9048          # ٨.٦٣١ قبل الإصلاح
    assert fixed["egypt_olive_oil"] == 80.0866       # ٨٨.٠٩٥٢ قبله
    assert fixed["india_honey"] is None              # معلَّقٌ على نصف العملة


def test_c12_verdict_and_score_never_change_and_nothing_new_blocks():
    """القِيَمُ الاقتصاديةُ تتغيّر بالتصحيح، والحكمُ لا: الدرجةُ والثقةُ
    والتسميةُ كما هي على الأربعَ عشرة، وصفرُ حجبٍ جديد."""
    import silk_quality_gate as G
    assert "observed_value_declared_unavailable" \
        not in G.FAIL_TRIGGER_CHECKS
    with _env(SILK_RECOGNITION_VOCABULARY="1"):
        assert "observed_value_declared_unavailable" \
            not in G.effective_fail_triggers()
    problems = {}
    with block_network():
        for key in _canonical_keys():
            with _env(SILK_RECOGNITION_VOCABULARY=None):
                v0 = _prod_view(key)
                g0 = G.run_quality_gate(v0)
            with _env(SILK_RECOGNITION_VOCABULARY="1"):
                v1 = _prod_view(key)
                g1 = G.run_quality_gate(v1)
            d0, d1 = (v0.get("decision") or {}), (v1.get("decision") or {})
            issues = [k for k in ("verdict", "score", "confidence")
                      if d0.get(k) != d1.get(k)]
            if g0["verdict"] != g1["verdict"]:
                issues.append(f"gate {g0['verdict']}→{g1['verdict']}")
            if issues:
                problems[key] = issues
    assert problems == {}, problems


# ═══ الصنف ١٣ — خانةُ قيمةٍ خارج المنسِّق الواحد ═══

def _dn_estimated(key: str = "india_honey") -> dict:
    import silk_render
    v = silk_render.build_view(_blob(key))
    dn = ((v.get("deep_research") or {}).get("economics") or {}) \
        .get("decision_numbers") or []
    return [e for e in dn if e.get("tier") == "estimated"]


def test_c13_the_observed_cell_is_reproduced_then_fixed():
    """**العيبُ المرصود حرفياً** في تقرير الهند: «2539350 INR (المدى
    2539350–2539350، ±0%)» — سبعُ خاناتٍ بلا فاصلِ آلاف، ومدىً منحلٌّ
    يُقدَّم مجالَ قياسٍ ±0% حيث لا مجال."""
    import silk_narrative as N
    with block_network():
        entries = _dn_estimated()
    entry = [e for e in entries if e["name"].startswith("كلفة الدخول")][0]
    with _env(SILK_DECISION_NUMBER_FORMAT=None):
        legacy = N.fmt_decision_value(entry)
    assert legacy == "2539350 INR (المدى 2539350–2539350، ±0%)", legacy
    with _env(SILK_DECISION_NUMBER_FORMAT="1"):
        fixed = N.fmt_decision_value(entry)
    assert fixed == "2,539,350 INR", fixed


def test_c13_a_real_range_keeps_its_range_and_gains_separators():
    """المدى الحقيقيُّ يبقى مدىً — الطيُّ للمنحلِّ وحدَه، لا لكلّ مدى."""
    import silk_narrative as N
    with block_network():
        entries = _dn_estimated("egypt_olive_oil")
    trial = [e for e in entries if e["name"].startswith("حجم الشحنة")][0]
    with _env(SILK_DECISION_NUMBER_FORMAT="1"):
        out = N.fmt_decision_value(trial)
    assert out == ("29,188.04 لتر (المدى 27,745.65–30,630.43، ±4.9%)"), out


def test_c13_canonical_form_never_asks_about_the_flag():
    """مرجعُ المقابلة لا يسأل الراية — وإلّا قابلَ الفحصُ الشيءَ بنفسه
    فأطلقَ على المسار **المُصلَح** (وهو ما فعلته الصيغةُ الأولى: ثلاثَ عشرةَ
    إطلاقةً مقلوبةً، مطفأةً صفرٌ ومفعّلةً ثلاثَ عشرة)."""
    import silk_narrative as N
    e = {"tier": "estimated", "value": 1234567, "unit": "SAR",
         "range": {"low": 1234567, "high": 1234567}, "width_pct": 0}
    with _env(SILK_DECISION_NUMBER_FORMAT=None):
        assert N.canonical_decision_value(e) == "1,234,567 SAR"
        assert N.fmt_decision_value(e) != N.canonical_decision_value(e)
    with _env(SILK_DECISION_NUMBER_FORMAT="1"):
        assert N.fmt_decision_value(e) == N.canonical_decision_value(e)


def test_c13_guard_marks_the_superseded_path_and_goes_silent_when_fixed():
    """الحارسُ موضوعُه **مسارُ العرض الساري**: يُطلِق على كلّ مدوّنةٍ تحمل
    بنداً محسوباً ما دامت الرايةُ مطفأة (١٣ من ١٤ — و`fettuccine` بلا بندٍ
    محسوبٍ أصلاً)، ويصمت بالبناء حين تُفعَّل."""
    import silk_quality_gate as G
    with block_network():
        with _env(SILK_DECISION_NUMBER_FORMAT=None):
            off = {k for k in _canonical_keys()
                   if any(f["check"] == "decision_number_format_drift"
                          for f in G.run_quality_gate(
                              _prod_view(k))["findings"])}
        with _env(SILK_DECISION_NUMBER_FORMAT="1"):
            on = {k for k in _canonical_keys()
                  if any(f["check"] == "decision_number_format_drift"
                         for f in G.run_quality_gate(
                             _prod_view(k))["findings"])}
    # `turkey_polymers` (د-٢) بلا بندٍ محسوبٍ كـ`fettuccine` — فئةٌ بلا وحدةِ سوق.
    assert off == set(_canonical_keys()) - set(
        ("fettuccine", "turkey_polymers", "malaysia_cosmetics",
         "japan_cosmetics")), off
    assert on == set(), on
    assert "decision_number_format_drift" not in G.FAIL_TRIGGER_CHECKS
    with _env(SILK_DECISION_NUMBER_FORMAT="1"):
        assert "decision_number_format_drift" not in G.effective_fail_triggers()


def test_c13_flag_changes_only_the_value_cell_and_no_stored_number():
    """القيمُ المخزّنة لا تُمَسّ: الفرقُ كلُّه في **خانة العرض**، والقيمةُ
    والمدى في البيانات كما هما رقماً برقم."""
    import silk_reports
    with block_network():
        for key in _canonical_keys():
            with _env(SILK_DECISION_NUMBER_FORMAT=None):
                v0 = _prod_view(key)
                md0 = silk_reports.render_markdown(v0).split("\n")
                dn0 = (((v0.get("deep_research") or {}).get("economics")
                        or {}).get("decision_numbers") or [])
            with _env(SILK_DECISION_NUMBER_FORMAT="1"):
                v1 = _prod_view(key)
                md1 = silk_reports.render_markdown(v1).split("\n")
                dn1 = (((v1.get("deep_research") or {}).get("economics")
                        or {}).get("decision_numbers") or [])
            assert dn0 == dn1, key            # صفرُ مسٍّ بالبيانات
            assert len(md0) == len(md1), key
            for a, b in zip(md0, md1):
                if a == b:
                    continue
                # الاسمُ كما هو، والخانةُ الثانيةُ وحدَها تغيّرت.
                assert a.split("|")[1] == b.split("|")[1], (key, a, b)
                assert a.split("|")[3:] == b.split("|")[3:], (key, a, b)
