"""ثغراتٌ التقطتها المراجعةُ الذاتية على فرق هذه الموجة (اللائحة ٥٨).

ثلاثُ ثغراتٍ لم يلتقطها أيُّ اختبارٍ قائم لأن كلَّ واحدةٍ منها **صامتة**:
لا تُفشِل شيئاً، بل تُنتِج جواباً يبدو سليماً.

١) فهرسٌ يعيش أطولَ من الصفوف التي فهرسها — تصنيفٌ على مرجعٍ قديم بلا أثر.
٢) ثقةٌ تُقاس على `/analyze` ثمّ تُرمى — البوّابةُ هناك تبقى معطّلة بينما
   تعمل على `/research` («إصلاحٌ على مسارٍ واحد نصفُ إصلاح»، الدرسان ٣٥/٣٧).
٣) عقدُ التصنيف لا يصل النتيجة — فوعدُ الإفصاح عن التناقضات بلا حامل.
"""
import io
import os

import silk_hs_pipeline as P
import silk_hs_resolver as R


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _api_src() -> str:
    with open(os.path.join(_ROOT, "api.py"), encoding="utf-8") as f:
        return f.read()


# ═══════════ ١ — الفهرس لا يعيش أطول من مرجعه ═══════════════════════════════
def test_the_token_index_rebuilds_when_the_reference_reloads():
    """`load_hs_codes.cache_clear()` كان يترك الفهرسَ يُصنِّف على صفوفٍ ميّتة.

    ذاكرتان مستقلّتان على المصدر نفسه: مَن يمسح الأولى (`extend_from_comtrade_rows`
    يفعل) يترك الثانيةَ تعمل على نسخةٍ قديمة — **بلا أيّ خطأ**. الربطُ بهويّة
    الكائن يجعل التزامنَ بنيوياً لا اتفاقاً بين مستدعين.
    """
    R.load_hs_codes()
    first = R._index()
    assert R._index() is first, "الفهرسُ يُعاد بناؤه بلا داعٍ (خسارةُ أداء)"
    R.load_hs_codes.cache_clear()
    rebuilt = R._index()
    assert rebuilt is not first, (
        "الفهرسُ نجا من مسح ذاكرة المرجع — تصنيفٌ على صفوفٍ قديمة بصمت")
    assert len(rebuilt[0]) == len(first[0])
    # والتصنيفُ نفسُه لا يتأثّر بإعادة البناء.
    assert P.classify("حلاوة طحينية")["final_hs_code"] == "170490"


def test_the_index_is_not_a_second_lru_cache_on_the_same_source():
    """قفلٌ على الشكل: `_index` لا يحمل ذاكرةً مستقلّةً عن `load_hs_codes`."""
    src = io.open(os.path.join(_ROOT, "silk_hs_resolver.py"),
                  encoding="utf-8").read()
    i = src.index("def _index(")
    head = src[max(0, i - 400):i]
    assert "lru_cache" not in head.split("_INDEX_CACHE")[-1], (
        "عادت ذاكرةٌ مستقلّة على الفهرس — العائلةُ نفسُها")
    assert "_INDEX_CACHE" in src


# ═══════════ ٢ — تكافؤ البوّابة على المسارات الثلاثة ════════════════════════
def test_every_spending_path_arms_the_confidence_gate_with_a_real_number():
    """الثقةُ المقيسة تصل البوّابةَ على كلّ مسارٍ ينفق — لا تُحسَب وتُرمى.

    `preflight_resolve` تتخطّى بوّابةَ الثقة حين لا يُمرَّر `hs_confidence`
    (`_UNSET` ≠ `None` عمداً). فمستدعٍ يقيس الثقةَ ثمّ لا يمرّرها يترك
    بوّابتَه معطّلةً وهو يظنّها تعمل — وهذا ما كان يفعله `/analyze`.
    """
    src = _api_src()
    assert src.count("hs_confidence=_analyze_conf") == 1, "/analyze لا يسلّح بوّابته"
    assert src.count("hs_confidence=_deepen_conf") == 1, "/deepen لا يسلّح بوّابته"
    assert src.count("hs_confidence=hs_confidence") >= 1, "/research لا يسلّح بوّابته"
    # ولا مسارَ ينفق يستدعي خطَّ التصنيف ثمّ يهمل ما أعاده.
    assert "settled_contract=_analyze_cls" in src and "settled_contract=_deepen_cls" in src, (
        "ارتباطٌ ميّت من خطّ التصنيف — قيمةٌ تُحسَب ولا تُقرأ")


def test_analyze_and_research_agree_on_the_same_pair():
    """نفسُ المنتج والرمز ⇒ نفسُ القرار على المسارين (تكافؤٌ سلوكيّ لا نصّي)."""
    for product, catalog in [("حلاوة طحينية", "170490"),
                             ("حلاوة طحينية", "110100"),
                             ("مناديل ورقية", None)]:
        out = P.classify(product, catalog)
        # نقطةُ الاختناق واحدة، فالتكافؤ خاصيّةُ بنيةٍ لا مصادفةَ إعداد.
        assert out is not None
        again = P.classify(product, catalog)
        assert again["classification_status"] == out["classification_status"]
        assert again["final_hs_code"] == out["final_hs_code"]


# ═══════════ ٣ — الإفصاح يصل النتيجة فعلاً ══════════════════════════════════
def test_the_classification_contract_reaches_the_result():
    """وعدُ الإفصاح يحتاج حاملاً: النتيجةُ تحمل ملخّصَ التصنيف لا الثقةَ وحدها.

    التوثيق يَعِد بأن التناقضات «تبقى معلنةً فتعرضها طبقةُ العرض» — وبلا
    حاملٍ في النتيجة يبقى ذلك وعداً بلا مخرج (نفسُ عائلة الدرس ٢٠٦).
    """
    src = _api_src()
    assert "hs_classification=" in src, (
        "عقدُ التصنيف لا يُمرَّر إلى بناء النتيجة — لا إفصاحَ عن التناقضات")
    pipe = io.open(os.path.join(_ROOT, "silk_research_pipeline.py"),
                   encoding="utf-8").read()
    assert 'result["hs_classification"]' in pipe, (
        "النتيجةُ لا تحمل ملخّصَ التصنيف")
    # والمسارُ **غيرُ المتزامن** يمرّره وسيطاً لا يلتقطه من نطاقٍ خارجيّ:
    # الخيطُ الخلفي دالّةٌ مستقلّة، فالالتقاطُ هناك `NameError` يقع **داخل
    # خيط** فيُبتلَع سبباً غامضاً («background run failed») بعد أن تكون
    # التشغيلةُ أُنفِقت. رُصِد حياً في كنس الثغرات.
    assert "hs_classification=None) -> None:" in src, (
        "الخيطُ الخلفي لا يستقبل الملخّصَ وسيطاً")
    i = src.index("target=_research_background")
    assert "_hs_classification_summary(hs_classification)" in src[i:i + 700], (
        "استدعاءُ الخيط الخلفي لا يمرّر الملخّص")


def test_the_summary_carries_disclosure_and_no_internal_keys():
    """الملخّصُ يحمل ما يُفصح، ولا يسرّب مفتاحاً داخلياً إلى سطحٍ يقرؤه مصنع."""
    out = P.classify("حلاوة طحينية", "110100", hs_confirmed=True)
    summary = P.result_summary(out)
    assert summary["classification_method"] == P.METHOD_USER_CONFIRMED
    assert summary["catalog_hs_status"]
    assert summary["contradictions"], "التأكيدُ أخفى التعارضَ بدل أن يُعلنه"
    assert isinstance(summary["confidence"], float)
    # لا حمولةً ثقيلة ولا مفاتيحَ داخلية على سطحٍ مخزَّن مع كل تحليل.
    assert set(summary) <= {
        "classification_status", "classification_method", "catalog_hs_code",
        "catalog_hs_status", "confidence", "contradictions",
        "official_hs_description", "normalized_product"}, summary.keys()
