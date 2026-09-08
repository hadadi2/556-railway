"""ما بعد الموجة Z — مسحُ الفجوات المتبقّية: `T-10` أُغلِق، و`G-07` **مدحوض**.

> **`T-10`.** `_walk_dps` كان يُعيد بناءَ البند من `sources[]` بثلاثة حقول
> (`source`/`value`/`note`)، فتسقط `url` و`confidence` و`source_ids`. وأوّلُ
> علاجٍ كتبتُه **لم يُغلِقه**: الحقولُ صارت تُحمَل في البند ثمّ يبتلعها
> `_provenance` الذي يجمع باسم المصدر — فلا تبلغ مصنوعاً أبداً. التقطته
> المراجعةُ الذاتية (§٥٨) بنصّ الدرس ١٠٤: «يصل العرض» ≠ «يصل المصنوع».
> **ولذلك تفحص أقفالُ هذا الملف النصَّ المُصيَّر لا القوائمَ الوسيطة.**
>
> وأوّلُ علاجٍ أيضاً كان **يختلق إسناداً**: عند غياب الحقل يرجع إلى الاكتشاف
> الأمّ، فيُنسَب رابطُ «UN Comtrade» إلى صفّ «مسح ميداني» في الاكتشاف نفسِه.
> الغائبُ يبقى غائباً.
>
> **`G-07` مدحوضٌ بإعادة قراءةٍ مقيسة** — راجع `docs/ENGINE_AUDIT.md`. جرّبتُ
> إخضاعَ `report.md` و`/brief` لبوّابة تسليم العميل ثمّ **تراجعتُ**: القياسُ
> أثبت أنّ `render_markdown` للمسار العميق هو **قالبُ المشغّل** (يحمل ملحقَي
> الأدلة وأثرِ المصادر اللذين يستبعدهما تقريرُ العميل)، وأنّ لا سطحَ مصنعٍ
> يبلغ أيّاً من المسارين. فالحجبُ كان يحرم المدقّقَ من أداة تشخيصه لحظةَ
> عطلِ التقرير — وهو أذىً بلا مستفيد.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import silk_render                                       # noqa: E402
import silk_reports                                      # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REAL_URL = "https://comtradeplus.un.org/x"


def _view_with(sources: list) -> dict:
    """عرضٌ من اكتشافٍ بشكل `sources[]` — الشكلُ الذي كان يُسقِط الإسناد."""
    return silk_render.build_view({
        "header": {}, "markets": [{"country": "هولندا", "components": {}}],
        "deep_research": {
            "missions": {"m": {"findings": [
                {"metric": "tam", "value": 42_000_000, "note": "واردات 2024",
                 "sources": sources}]}},
            "verdict": {"verdict": "WATCH"},
            "report": {"report": "نصّ العيّنة"}}}, "ar")


def dp_view(dps: list) -> dict:
    """عرضٌ من كائنات `DataPoint` — **شكلُ الإنتاج على `/analyze`**.

    مُثبِّتي الأوّل كان بشكل القاموس وحدَه، فمرّ أخضرَ بينما فرعُ الكائن —
    الذي يخدم كلَّ تحليلٍ كلاسيكيّ — ما يزال يُسقِط الحقولَ الثلاثة.
    """
    return silk_render.build_view({
        "header": {}, "product": "تمور", "hs_code": "080410",
        "markets": [{"country": "هولندا", "iso3": "NLD", "total_score": 0.6,
                     "confidence": 0.6,
                     "components": {"market_size": dps[0] if len(dps) == 1
                                    else dps}}]}, "ar")


def _appendix(view: dict) -> str:
    """قسمُ «أثر المصادر» من **النصّ المُصيَّر** لا من قائمةٍ وسيطة.

    القسمُ **كاملاً** حتى العنوان التالي — نافذةُ ٥٠٠ حرفٍ الثابتة كانت
    تقطع صفوفاً وتُنتِج «غائبٌ» زائفاً حين يطول السطرُ بروابطَ وأسماء.
    """
    md = silk_reports.render_markdown(view)
    i = md.index("أثر المصادر")
    rest = md[i:]
    nxt = re.search(r"\n#{1,6} ", rest)
    return rest[:nxt.start()] if nxt else rest


# ── T-10 · الإسنادُ يبلغ المصنوع ─────────────────────────────────────────

def test_the_production_datapoint_shape_carries_all_three_fields():
    """**القفلُ الحاكم:** فرعُ كائن `DataPoint` — لا القاموسُ وحدَه.

    سجّلتُ `T-10` مغلقاً «مُثبَتاً على المصنوع» وقياسي كان على مُثبِّتٍ بشكل
    القاموس؛ ومسارُ `/analyze` كلُّه يمرّ بفرع الكائن.
    """
    from silk_data_layer import DataPoint
    text = _appendix(dp_view([DataPoint(
        42_000_000, "World Bank", 0.77, "واردات",
        url="https://x.test/q", evidence_ids=("dp1", "dp7"))]))
    assert "https://x.test/q" in text, text[:250]
    assert "ثقة المرصود 77%" in text, text[:250]
    # `evidence_ids` تُحمَل في البند ولا تُنطَق في السطر — راجع
    # `test_evidence_ids_are_carried_but_never_spoken_as_attribution`.
    row = dp_view([DataPoint(
        42_000_000, "World Bank", 0.77, "واردات",
        url="https://x.test/q", evidence_ids=("dp1", "dp7"))])
    assert row["provenance"][0]["url"] == "https://x.test/q"


def test_the_deep_path_datapoint_shape_carries_every_field():
    """شكلُ `silk_llm_runtime:1278-1279` — المنتِجُ الوحيد لهذين الحقلين.

    `source_ids` و`evidence_ids` **لا يُملآن على `/analyze` إطلاقاً** (قياسٌ
    على `samples/analysis_latest.json`: صفرٌ من ٤٩ بنداً)؛ منتِجُهما مسارُ
    البعثات العميق. فاختبارُهما على مدوّنة `/analyze` وحدَها كان سيُبقيهما
    بلا أيّ تغطيةٍ حقيقية — نفسُ عائلة «المُثبِّت يخالف شكلَ الإنتاج».
    """
    from silk_data_layer import DataPoint
    text = _appendix(dp_view([DataPoint(
        5, "GCC secretariat", 0.8, "n", url="https://gcc-sg.org/doc/17",
        source_ids=("GCC secretariat", "GAFTA secretariat"),
        evidence_ids=("dp3", "dp9"))]))
    line = next(l for l in text.splitlines() if l.startswith("- GCC"))
    assert "https://gcc-sg.org/doc/17" in line, line
    assert "ثقة المرصود 80%" in line, line
    assert "مصادر مدمجة: GCC secretariat، GAFTA secretariat" in line, line


def test_an_observed_link_is_never_replaced_by_a_registry_homepage():
    """رابطُ الرقم الحقيقيّ لا يُستبدَل بصفحةِ المصدر الرئيسة.

    كان فرعُ الكائن يُسقِط الرابطَ، فيملأ المُجمِّعُ مكانَه رابطَ السجلّ —
    فيرى القارئ رابطاً **ليس** الذي جاء منه الرقم. تنزيلٌ للإسناد لا ترقية.
    """
    from silk_data_layer import DataPoint
    text = _appendix(dp_view([DataPoint(
        5, "World Bank", 0.7, "n", url="https://x.test/q")]))
    assert "https://x.test/q" in text and "data.worldbank.org" not in text, (
        text[:250])


def test_confidence_is_a_range_not_a_flattering_peak():
    """قمّةٌ وحدَها تُجمِّل مصدراً أسهم عشراً بثقةٍ متدنّية ومرّةً بعالية."""
    from silk_data_layer import DataPoint
    text = _appendix(dp_view([DataPoint(1, "S", 0.30, "n"),
                              DataPoint(2, "S", 0.95, "n")]))
    assert "ثقة المرصود 30–95%" in text, text[:250]


def test_an_out_of_range_confidence_is_refused_not_printed():
    """زلّةُ JSON شائعة (`82` بدل `0.82`) كانت تطبع «8200%»."""
    from silk_data_layer import DataPoint
    text = _appendix(dp_view([DataPoint(1, "S", 82, "n")]))
    assert "8200" not in text and "ثقة المرصود" not in text, text[:250]
    text_bool = _appendix(dp_view([DataPoint(1, "S", True, "n")]))
    assert "ثقة المرصود" not in text_bool, text_bool[:250]


def test_more_observed_links_never_yield_less_attribution():
    """رابطان مختلفان كانا يُسقِطان الاثنين — أدلّةٌ أكثر ⇒ إسنادٌ أقلّ."""
    from silk_data_layer import DataPoint
    text = _appendix(dp_view([DataPoint(1, "رصد ويب", 0.5, "n", url="https://a/1"),
                              DataPoint(2, "رصد ويب", 0.5, "n", url="https://a/2")]))
    assert "https://a/1" in text and "https://a/2" in text, text[:250]


def test_an_unmerged_row_does_not_repeat_its_own_name_as_a_merged_source():
    """`source_ids` بمصدرٍ واحد = اسمُ الصفّ نفسِه — لا يُطبَع تكراراً."""
    from silk_data_layer import DataPoint
    text = _appendix(dp_view([DataPoint(
        5, "World Bank", 0.7, "n", url="https://x/1",
        source_ids=("World Bank",))]))
    assert "مصادر مدمجة" not in text, text[:250]


def test_a_string_of_source_names_is_not_read_character_by_character():
    """`source_ids="GAFTA"` كانت تُنتِج «G، A، F، T» **أسماءَ مصادرَ مختلَقة**.

    القارئُ القانونيّ نفسُه (`atomic_source_ids`) كان يكرّر على السلسلة حرفاً
    حرفاً — والحقلُ يصل من JSON نموذجٍ سلسلةً مفردةً أحياناً. مراجعةٌ ذاتية
    (§٥٨) على هذا الفرع بالذات: الاختلاقُ هنا يُطبَع في المصنوع نصّاً.
    """
    from silk_data_layer import DataPoint, atomic_source_ids
    assert atomic_source_ids("GCC secretariat", "GAFTA") == ["GAFTA"]
    text = _appendix(dp_view([
        DataPoint(1, "GCC secretariat", 0.5, "n", source_ids="GAFTA"),
        DataPoint(2, "GCC secretariat", 0.5, "n",
                  source_ids=("GCC secretariat",))]))
    assert "مصادر مدمجة: GAFTA، GCC secretariat" in text, text[:300]
    assert "G، A، F" not in text, text[:300]


def test_a_truncated_source_name_list_declares_what_it_dropped():
    """قائمةٌ مبتورةٌ بصمتٍ تُقرأ إسناداً كاملاً — وكانت أسماءُ المصادر
    وحدَها من القائمتين تُبتَر بلا عدّاد (مراجعةٌ ذاتية §٥٨)."""
    from silk_data_layer import DataPoint
    names = tuple(f"هيئة {i}" for i in range(12))
    text = _appendix(dp_view([DataPoint(1, "S", 0.5, "n", source_ids=names)]))
    assert "(+4)" in text, text[:400]
    assert text.index("هيئة 0") < text.index("هيئة 7"), "الترتيبُ الأصليّ ضاع"


def test_two_spellings_of_one_source_name_are_not_a_merge():
    """«World Bank» و«world bank» مصدرٌ واحد — والتجميعُ كان حسّاساً للحالة
    فيَسِم صفّاً مفردَ المصدر «مصادر مدمجة» زوراً (مراجعةٌ ذاتية §٥٨)."""
    from silk_data_layer import DataPoint
    text = _appendix(dp_view([
        DataPoint(1, "World Bank", 0.5, "n", source_ids=("World Bank",)),
        DataPoint(2, "World Bank", 0.5, "n", source_ids=("world bank",))]))
    assert "مصادر مدمجة" not in text, text[:300]


def test_evidence_ids_are_carried_but_never_spoken_as_attribution():
    """`dpN` **لا يُنطَق** في أيّ مصنوع — نطاقُه بعثةٌ واحدة ولا جدولَ فكٍّ له.

    `silk_llm_runtime._run_loop` يبدأ `next_id = [1]` مع كلّ بعثة/سوق، فـ
    `dp1` في بعثتين شيئان مختلفان كان التجميعُ باسم المصدر يوحّدهما؛ ولا
    مصنوعَ يحمل خريطةَ `dpN → نقطة`، فالمعرّفُ غيرُ قابلٍ للحلّ عند قارئه.
    يبقى محمولاً في البند (اقتفاءٌ آليّ) ولا يُقدَّم إسناداً منطوقاً.
    """
    from silk_data_layer import DataPoint
    v = dp_view([DataPoint(1, "S", 0.5, "n", url="https://x/1",
                           evidence_ids=("dp1", "dp7"))])
    assert re.search(r"\bdp\d+\b", v["provenance"][0]["tail"] or "") is None
    text = _appendix(v)
    assert re.search(r"\bdp\d+\b", text) is None, text[:300]
    out: list = []
    silk_render._walk_dps(
        {"metric": "م", "value": 1.0,
         "sources": [{"source": "S", "evidence_ids": ["dp3"]}]}, out)
    assert out[0]["evidence_ids"] == ["dp3"], out


def test_both_walk_branches_carry_the_same_contract_fields():
    """فرعان بقائمتين تتباعدان: أضفتُ `evidence_ids` إلى فرع `sources[]`
    فأسقطتُ منه `retrieved_at`/`data_year` — وكانا **مدموجَين في main**.
    القائمةُ واحدة الآن، والقفلُ يقيس الفرعين معاً (مراجعةٌ ذاتية §٥٨)."""
    from silk_data_layer import DataPoint
    fields = ("url", "confidence", "evidence_ids", "source_ids",
              "retrieved_at", "data_year")
    assert set(silk_render._DP_CARRIED_FIELDS) == set(fields)
    out: list = []
    silk_render._walk_dps({
        "metric": "م", "value": 1.0,
        "sources": [{"source": "World Bank", "url": "https://x/1",
                     "confidence": 0.5, "evidence_ids": ["dp1"],
                     "source_ids": ["wb-1"], "retrieved_at": "2026-01-02",
                     "data_year": 2024}]}, out)
    assert out[0]["data_year"] == 2024 and out[0]["retrieved_at"] == "2026-01-02"
    assert out[0]["source_ids"] == ["wb-1"]
    out2: list = []
    silk_render._walk_dps(
        DataPoint(1, "World Bank", 0.5, "n", "2026-01-02", data_year=2024,
                  url="https://x/1", source_ids=("wb-1",),
                  evidence_ids=("dp1",)), out2)
    for f in fields:
        assert f in out2[0], (f, out2[0])


def test_the_tail_is_built_in_the_view_model_not_in_a_viewer():
    """الدرس ١٠٥ — العارضون يعرضون ولا يبنون."""
    src = open(os.path.join(_ROOT, "silk_reports.py"), encoding="utf-8").read()
    assert "def _provenance_tail" not in src, "الذيلُ عاد يُبنى في العارض"
    # «لا أقلّ من ثلاثة» لا «ثلاثةٌ بالضبط»: العقدُ أن يقرأ كلُّ عارضٍ الحقلَ
    # المبنيّ — وعارضٌ رابعٌ صحيحٌ كان يُحمِّر القفلَ برسالةٍ تقول عكسَ ما وقع.
    assert src.count('b.get("tail")') >= 3, "عارضٌ لا يقرأ الحقلَ المبنيّ"
    from silk_data_layer import DataPoint
    v = dp_view([DataPoint(5, "World Bank", 0.7, "n", url="https://x/q")])
    assert (v["provenance"][0].get("tail") or "").strip(), v["provenance"][:1]


def test_the_tail_speaks_the_language_of_its_viewers_not_of_the_view():
    """سطرٌ بلغتين على مسارٍ حيّ: `silk_platform/api.py:1385` يبني العرضَ بلغة
    الدراسة و`:1462` يسلّمه `render_docx` — ومُصيِّرا هذا الملحق عربيّان
    بالكامل مهما كانت `lang`. فذيلٌ يتبع `lang` أنتج «أسهم 1 من 1 محاولة —
    observed confidence 77%» في مستندِ مصنعٍ إنجليزيّ (مراجعةٌ ذاتية §٥٨)."""
    from silk_data_layer import DataPoint
    en = silk_render.build_view({
        "header": {}, "product": "dates", "hs_code": "080410",
        "markets": [{"country": "NL", "iso3": "NLD", "total_score": 0.6,
                     "confidence": 0.6, "components": {"market_size": DataPoint(
                         5, "World Bank", 0.77, "n", url="https://x/q")}}]}, "en")
    tail = en["provenance"][0]["tail"]
    assert "ثقة المرصود 77%" in tail, tail
    assert "observed confidence" not in tail, tail
    line = next(l for l in _appendix(en).splitlines()
                if l.startswith("- World Bank"))
    assert "أسهم" in line and "observed" not in line, line


def test_a_sub_percent_confidence_is_not_flattened_to_zero():
    """«ثقة المرصود 0%» تُقرأ «بلا ثقة» — وهي ٠٫٤٪ (مراجعةٌ ذاتية §٥٨)."""
    from silk_data_layer import DataPoint
    assert "<1%" in _appendix(dp_view([DataPoint(1, "S", 0.004, "n")]))
    assert "ثقة المرصود 0%" in _appendix(dp_view([DataPoint(1, "S", 0.0, "n")]))


def test_two_spellings_of_one_source_are_not_two_sources():
    """`source` المخدومُ من المخزن يحمل لاحقةً و`source_ids` تحمل الاسمَ
    العاري — فكان الصفُّ **مفردُ المصدر** يُوسَم «مصادر مدمجة»: ادّعاءُ
    إسنادٍ لم يقع، على شكل إنتاجٍ حاضرٍ في `samples/`."""
    from silk_data_layer import DataPoint
    text = _appendix(dp_view([
        DataPoint(1, "UN Comtrade (مخزن الحقائق)", 0.9, "n",
                  source_ids=("UN Comtrade",)),
        DataPoint(2, "UN Comtrade (مخزن الحقائق)", 0.9, "n")]))
    assert "مصادر مدمجة" not in text, text[:300]


def test_a_malformed_source_ids_never_invents_a_name_nor_a_500():
    """`source_ids` تصل من JSON نموذجٍ بأشكالٍ غير القائمة: قاموسٌ كان يُقدِّم
    **مفاتيحَه** أسماءَ مصادر، وعددٌ كان يُفجِّر `TypeError` خارج `build_view`
    فيصير `500` على تصديرِ تقريرٍ بدل فجوةٍ معلَنة (مراجعةٌ ذاتية §٥٨)."""
    from silk_data_layer import atomic_source_ids as a
    assert a("World Bank", {"A": 1, "B": 2}) == ["World Bank"]
    assert a("World Bank", 5) == ["5"]
    assert a("World Bank", None) == ["World Bank"]
    text = _appendix(_view_with([{"source": "World Bank",
                                  "source_ids": {"A": 1, "B": 2}}]))
    assert "مصادر مدمجة" not in text, text[:300]


def test_the_latin_link_is_bracketed_for_rtl_isolation():
    """WP-5: مقطعٌ لاتينيّ عارٍ في فقرةٍ عربية ينقلب في PDF المُحوَّل.

    الأقواسُ ليست زينة — هي ما تلتقطه `_bidi_isolate_brackets` لحقن RLM.
    """
    from silk_data_layer import DataPoint
    tail = dp_view([DataPoint(5, "S", 0.7, "n", url="https://x/q")]
                   )["provenance"][0]["tail"]
    assert "(https://x/q)" in tail, tail



def test_the_link_reaches_the_rendered_appendix_not_just_the_view():
    """**القفلُ الحاكم:** يُفحَص النصُّ المُصيَّر — القائمةُ الوسيطة لا تكفي.

    أوّلُ علاجٍ مرّ خضراءَ وهو عاجزٌ تماماً لأنّ قفلَه فحص ناتجَ `_walk_dps`
    مباشرةً، و`_provenance` يبتلع الحقولَ بعده بسطور.
    """
    text = _appendix(_view_with([{"source": "UN Comtrade", "url": _REAL_URL}]))
    assert _REAL_URL in text, (
        f"الرابطُ لا يبلغ الملحقَ المُصيَّر — {text[:200]}")


def test_all_three_provenance_fields_reach_the_rendered_appendix():
    """معيارُ القبول: `url` و`confidence` و`source_ids` تبلغ **المصنوع**.

    أوّلُ علاجٍ أوصل الرابطَ وحدَه؛ والحقلان الآخران كانا ما يزالان يموتان في
    المُجمِّع.
    """
    text = _appendix(_view_with([{"source": "UN Comtrade", "url": _REAL_URL,
                                  "confidence": 0.82,
                                  "source_ids": ["UN Comtrade", "ITC"]}]))
    assert _REAL_URL in text, text[:200]
    assert "ثقة المرصود 82%" in text, text[:200]
    assert "مصادر مدمجة: UN Comtrade، ITC" in text, text[:300]


def test_every_observed_link_is_shown_not_just_the_first():
    """لا اقتطاعَ صامت: الروابطُ المرصودة كلُّها تُعرَض حتى السقف المُعلَن."""
    text = _appendix(_view_with([{"source": "UN Comtrade", "url": _REAL_URL},
                                 {"source": "UN Comtrade",
                                  "url": _REAL_URL + "2"}]))
    line = next(l for l in text.splitlines() if l.startswith("- UN Comtrade"))
    assert _REAL_URL in line and _REAL_URL + "2" in line, line


def test_an_unknown_source_gets_no_invented_link():
    """عقدُ عدم الاختلاق يسبق اكتمالَ الشكل: خانةٌ فارغةٌ خيرٌ من رابطٍ مصنوع."""
    text = _appendix(_view_with([{"source": "مسح ميداني"}]))
    assert "مسح ميداني" in text
    assert "http" not in text.split("حدود هذا التقرير")[0], text[:200]


def test_one_sources_link_is_never_attributed_to_a_sibling_source():
    """**إسنادٌ مختلَق** — التقطته المراجعةُ الذاتية على أوّل علاج.

    اكتشافٌ واحد بمصدرين: أحدُهما يحمل رابطاً والآخر لا. الرجوعُ إلى الاكتشاف
    الأمّ كان ينسب رابطَ الأوّل إلى الثاني.
    """
    out: list = []
    silk_render._walk_dps({
        "metric": "حجم السوق", "value": 42_000_000, "url": _REAL_URL,
        "confidence": 0.9,
        "sources": [{"source": "UN Comtrade", "url": _REAL_URL},
                    {"source": "مسح ميداني"}]}, out)
    survey = [d for d in out if d["source"] == "مسح ميداني"]
    assert survey and "url" not in survey[0], survey
    assert "confidence" not in survey[0], survey


def _analyze_view(sources: list) -> dict:
    """عرضٌ بشكل `/analyze` — ملحقُ أثر المصادر في **docx** يعيش في فرعه.

    `render_docx` يرتدّ مبكّراً لنتيجة البحث العميق (`_render_research_docx`)،
    فملحقُ الأثر في docx خاصٌّ بالمسار الكلاسيكيّ؛ والمسارُ العميق يحمل بدله
    «سجل الأدلة للمدققين». فحصُ الاثنين حيث يعيش كلٌّ منهما — لا إضافةُ ملحقٍ
    إلى مستندٍ لم يطلبه أحد.
    """
    return silk_render.build_view({
        "header": {}, "product": "تمور", "hs_code": "080410",
        "markets": [{"country": "هولندا", "iso3": "NLD", "total_score": 0.6,
                     "confidence": 0.6, "components": {
                         "market_size": {"metric": "tam", "value": 42_000_000,
                                         "note": "واردات", "sources": sources}}}],
    }, "ar")


def test_the_final_docx_and_pdf_carry_the_provenance_too(tmp_path):
    """المصنوعُ النهائيّ لا الوسيط: docx **و**PDF مُولَّدان فعلاً ومقروءان."""
    import re as _re
    import subprocess
    import zipfile
    view = _analyze_view([{"source": "UN Comtrade", "url": _REAL_URL,
                           "confidence": 0.82,
                           "source_ids": ["UN Comtrade", "ITC"]}])
    d = str(tmp_path / "r.docx")
    silk_reports.render_docx(view, d)
    xml = zipfile.ZipFile(d).read("word/document.xml").decode("utf-8")
    dtext = _re.sub(r"<[^>]+>", "", xml.replace("</w:p>", "\n"))
    assert _REAL_URL in dtext and "ثقة المرصود 82%" in dtext, dtext[-400:]
    assert "مصادر مدمجة: UN Comtrade، ITC" in dtext, dtext[-400:]
    f = str(tmp_path / "r.pdf")
    try:
        silk_reports.docx_to_pdf(d, f)
    except RuntimeError as e:
        # تدقيق 2026-08-27 (§W-04): فرعُ «بوّابةُ الأقواس أطلقت ⇒ تخطَّ» **حُذِف**.
        # كان يحوّل إطلاقَ البوّابة إلى `pytest.skip`، فالبيئةُ الوحيدةُ التي
        # تُشغّل هذا المسار فعلاً (حيث pymupdf مثبَّتة) صارت تتخطّى بدل أن
        # تُحمِّر — والتوكيدُ أدناه بلا موضعِ تنفيذ. بعد معايرة المقياس صارت
        # البوّابةُ لا تُطلِق على مستندٍ سليم، فإطلاقُها اليومَ **عطلٌ يجب أن
        # يُحمِّر**. يبقى التخطّي لغياب المحوّل وحدَه (بيئةٌ بلا soffice).
        if "الأقواس" in str(e):
            raise
        from tests.pdf_gate import pdf_engine_broken
        pdf_engine_broken(str(e))
    import shutil
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext غير مثبَّت")
    out = subprocess.run(["pdftotext", "-layout", f, "-"],
                         capture_output=True, text=True, timeout=300).stdout
    assert "comtradeplus.un.org" in out, out[-500:]


def test_source_ids_are_never_relabelled_as_evidence_ids():
    """`source_ids` أسماءُ مصادرَ عمومية، و`evidence_ids` معرّفاتُ اقتفاء.

    `silk_data_layer` يوثّق تمايزَهما نصّاً («دمجُهما كان سيُفسِد الإسناد»)،
    وكنتُ أطبع `source_ids` تحت عنوان «معرّفات الأدلة» — فاسمُ مصدرٍ شقيقٍ
    يُقدَّم دليلاً لهذا الصفّ.
    """
    out: list = []
    silk_render._walk_dps({
        "metric": "م", "value": 1.0,
        "sources": [{"source": "GCC secretariat", "confidence": 0.82,
                     "source_ids": ["GCC secretariat", "GAFTA secretariat"],
                     "evidence_ids": ["dp3"]}]}, out)
    assert out[0]["confidence"] == 0.82
    assert out[0]["evidence_ids"] == ["dp3"]
    # تُحمَل، **لكن** تُعرَض تحت «مصادر مدمجة» لا تحت أيّ عنوانِ أدلة:
    text = _appendix(_view_with([{
        "source": "GCC secretariat", "evidence_ids": ["dp3"],
        "source_ids": ["GCC secretariat", "GAFTA secretariat"]}]))
    line = next(l for l in text.splitlines() if l.startswith("- GCC"))
    assert "مصادر مدمجة: GCC secretariat، GAFTA secretariat" in line, line
    assert "أدلة" not in line, line


def test_the_plain_datapoint_shape_is_untouched():
    """تكافؤٌ رجعيّ: البندُ ذو `source`/`value` يمرّ كما هو بلا إعادة بناء."""
    out: list = []
    dp = {"source": "Google Maps", "value": 7.49, "confidence": 0.4}
    silk_render._walk_dps(dp, out)
    assert out == [dp] and out[0] is dp


def test_the_failure_lines_of_the_appendix_are_unchanged():
    """تكافؤٌ رجعيّ: «لا فشل صامتاً» يبقى كما كان — أضفنا حقلاً لا غيّرنا عقداً."""
    view = _view_with([{"source": "UN Comtrade"}])
    prov = view.get("provenance") or []
    assert prov and set(prov[0]) >= {"source", "attempted", "contributed",
                                     "failures", "url"}


# ── G-07 · مدحوضٌ — والقفلُ يمنع «إصلاحَه» ثانيةً ────────────────────────

def test_the_operator_markdown_is_the_operator_artifact_not_the_client_one():
    """الأساسُ الذي بُني عليه الدحض — مقيسٌ لا مُستنتَج.

    `report.md` يحمل ملحقَي الأدلة وأثرِ المصادر اللذين يستبعدهما تقريرُ
    العميل. فإخضاعُه لبوّابةِ **قالبِ العميل** حجبٌ زائف: تحليلٌ سليمٌ تشكو
    نسختُه العميلة من قسمٍ نائب يفقد المدقّقُ أداةَ تشخيصه كلَّها.
    """
    sys.path.insert(0, os.path.join(_ROOT, "tools"))
    from test_wave_z_one_verdict import _view
    md = silk_reports.render_markdown(_view(engine="NO-GO"))
    assert "ملحق: أثر المصادر" in md and "ملحق: الأدلة الرقمية" in md


def test_neither_operator_text_export_is_reachable_from_a_factory_surface():
    """النصفُ الثاني من الدحض: لا سطحَ مصنعٍ يبلغ `report.md` ولا `/brief`."""
    plat = open(os.path.join(_ROOT, "silk_platform", "api.py"),
                encoding="utf-8").read()
    routes = re.findall(r'@app\.(?:get|post)\(_PREFIX \+ "([^"]+)"', plat)
    for r in routes:
        assert not r.endswith("report.md"), r
        assert not r.endswith("/brief"), r


def test_the_client_deliverables_do_stay_gated():
    """وما كان محروساً يبقى محروساً — الدحضُ لا يفتح باباً."""
    src = open(os.path.join(_ROOT, "api.py"), encoding="utf-8").read()
    for path in ("report.docx", "report.pdf"):
        i = src.index(f'@app.get("/analyses/{{analysis_id}}/{path}")')
        j = src.index("@app.get(", i + 10)
        assert "_block_client_export_if_gate_failed" in src[i:j], path
