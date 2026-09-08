"""تحليل 20 (التقرير الحيّ) — قصّ تداخل الدمج عند استئناف الجملة.

الدليل المباشر (لصقه المالك): استئنافُ جملةٍ مقطوعة كرّر العبارةَ عند نقطة اللصق:
«هذا الانكماش هذا الانكماش الحاد». `_trim_join_overlap` حتميّ: يُسقِط أطولَ لاحقةٍ
من الأساس تساوي سابقةَ الإكمال (≥ ٨ أحرف، عند حدّ كلمةٍ على الجانبين) — فلا تكرار.
القطعُ **منتصفَ الكلمة** يتفاداه المسارُ النظيف ?seed=0 (لا إكمال). هرمتي. Run:
  python3 -m pytest tests/test_analysis20_join_overlap_trim.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_trim_removes_word_boundary_stutter():
    import silk_ai_judge as aj
    base = "يعني هذا أن الطلب يتقلّص. هذا الانكماش"
    cont = "هذا الانكماش الحاد يستدعي تحققاً."
    out = aj._trim_join_overlap(base, cont)
    assert out == "الحاد يستدعي تحققاً."          # حُذِف التداخلُ المكرَّر
    # النصُّ المدموجُ لا يحوي التكرار
    joined = base + " " + out
    assert "هذا الانكماش هذا الانكماش" not in joined
    assert "هذا الانكماش الحاد" in joined


def test_no_trim_when_no_overlap():
    import silk_ai_judge as aj
    base = "جملةٌ كاملةٌ منتهية."
    cont = "فقرةٌ جديدةٌ مختلفةٌ تماماً."
    assert aj._trim_join_overlap(base, cont) == cont


def test_no_trim_for_short_coincidental_overlap():
    import silk_ai_judge as aj
    base = "السوق في نموّ"
    cont = "في نموٍّ مطّرد"          # تداخلٌ قصيرٌ (<٨) لا يُقصّ
    assert aj._trim_join_overlap(base, cont) == cont


def test_no_trim_mid_word_partial_match():
    """تطابقٌ ينتهي وسطَ كلمةٍ في الإكمال لا يُقصّ (تفادي بتر كلمة) — يتركه للمسار
    النظيف ?seed=0."""
    import silk_ai_judge as aj
    base = "سلعةٌ سريعة التلف ك"        # قُطِع وسط «كالحليب»
    cont = "سريعة التلف كالحليب الطازج"
    # التداخلُ «سريعة التلف ك» ينتهي وسطَ «كالحليب» في الإكمال ⇒ لا قصّ
    assert aj._trim_join_overlap(base, cont) == cont


# ── دراسة #10 (حليب/الأردن 2026-08-24) — القصّ المتسامح للذيل المبتور ────────
# التلعثمان أدناه منقولان **حرفياً** من تقريرٍ مُسلَّم أفشل بوابةَ الجودة
# (style_repeated_key_figure): التطابقُ الحرفيّ وحده عجز عنهما لأن ذيل الأساس
# مبتورٌ («م») أو متباعدٌ عن نسخة الإكمال («الواردات»/«صادرات»).


def test_stutter_trim_drops_truncated_tail_token():
    """الأساس ينتهي بكلمةٍ مبتورة عند القطع والإكمال يعيد الجملة كاملةً —
    تُسقَط الشظيّةُ ويُقصّ التداخل فلا يتكرّر النصّ."""
    import silk_ai_judge as aj
    base = ("وهذا التناقض متوقَّع وناتج عن كون رقم كومتريد يخص "
            "فئة جملة ضيقة م")
    cont = ("وهذا التناقض متوقَّع وناتج عن كون رقم كومتريد يخص "
            "فئة جملة ضيقة محدودة الدهن لا تشمل غالبية الحليب")
    b, c = aj._trim_join_stutter(base, cont)
    joined = b + " " + c
    assert joined.count("وهذا التناقض متوقَّع") == 1
    assert "ضيقة م " not in joined            # الشظيّة المبتورة أُسقِطت
    assert "محدودة الدهن لا تشمل غالبية الحليب" in joined


def test_stutter_trim_drops_diverging_tail_token():
    """الأساس ينتهي بكلمةٍ صاغها الإكمالُ مختلفةً («الواردات» ⇐ «صادرات») —
    يُقصّ التلعثم وتبقى صياغةُ الإكمال الكاملة."""
    import silk_ai_judge as aj
    base = ("تقديرها يتطلب بيانات مبيعات فعلية لموزّع سدافكو وحصته "
            "من إجمالي الواردات")
    cont = ("تقديرها يتطلب بيانات مبيعات فعلية لموزّع سدافكو وحصته "
            "من إجمالي صادرات السعودية إلى الأردن")
    b, c = aj._trim_join_stutter(base, cont)
    joined = b + " " + c
    assert joined.count("تقديرها يتطلب") == 1
    assert "صادرات السعودية إلى الأردن" in joined
    assert "الواردات تقديرها" not in joined


def test_stutter_trim_exact_path_unchanged():
    """المسار الحرفيّ القائم (تحليل 20) يمرّ عبر الدالة الجديدة كما هو."""
    import silk_ai_judge as aj
    base = "يعني هذا أن الطلب يتقلّص. هذا الانكماش"
    cont = "هذا الانكماش الحاد يستدعي تحققاً."
    b, c = aj._trim_join_stutter(base, cont)
    assert b == base and c == "الحاد يستدعي تحققاً."


def test_stutter_trim_never_drops_tail_without_long_restart_overlap():
    """ذيلٌ سليم بلا استئنافٍ متلعثم لا يُمَسّ أبداً — الإسقاط مشروطٌ بتداخلٍ
    طويلٍ أو ببصمة البتر الكاملة (قفل محدَّث معلن — موجة #13 الدرس 168:
    الحالة القديمة الثانية هنا كانت بصمة بترٍ حقيقية تحت العتبة، وقد شُحن
    نظيرها في PDF #13 ص8 «لا يتوفر س لا يتوفر سعر» — صار إصلاحها مطلوباً)."""
    import silk_ai_judge as aj
    base = "السوق في نموّ مطّرد هذا العام"
    cont = "فقرةٌ جديدةٌ مختلفةٌ تماماً عن السابقة."
    assert aj._trim_join_stutter(base, cont) == (base, cont)
    # بصمة البتر الكاملة (ذيل مسقط واحد تمدّه كلمة الإكمال) تُصلَح الآن:
    base2 = "سلعةٌ سريعة التلف ك"
    cont2 = "سريعة التلف كالحليب الطازج"
    b2, c2 = aj._trim_join_stutter(base2, cont2)
    assert f"{b2} {c2}" == "سلعةٌ سريعة التلف كالحليب الطازج"
    # وتداخلٌ قصير **بلا** البصمة (كلمة الإكمال لا تمدّ الذيل المسقط) يبقى
    # محفوظاً — البتر الكاذب أسوأ من الازدواج المرئي (تصحيح المُشرِف).
    base3 = "سلعةٌ سريعة التلف جداً"
    cont3 = "سريعة التلف كالحليب الطازج"
    assert aj._trim_join_stutter(base3, cont3) == (base3, cont3)


def test_stutter_trim_preserves_section_heading_newline():
    """مراجعة §58 (مؤكَّد بالتنفيذ): القصُّ يمحو المسافات لا الأسطر — عنوان
    `##` تالٍ بعد التداخل يبقى على سطره فلا يسقط من عدّ الأقسام."""
    import re
    import silk_ai_judge as aj
    base = ("وهذا التناقض متوقَّع وناتج عن كون رقم كومتريد يخص "
            "فئة جملة ضيقة م")
    cont = ("وهذا التناقض متوقَّع وناتج عن كون رقم كومتريد يخص "
            "فئة جملة ضيقة\n\n## 8. اللوجستيات وسلسلة الإمداد\nنص القسم")
    b, c = aj._trim_join_stutter(base, cont)
    joined = b + " " + c
    assert re.findall(r"^##\s+\d+\.", joined, re.M), \
        "عنوان القسم التصق بسطر الجملة فسقط من العدّ"
    assert joined.count("وهذا التناقض متوقَّع") == 1


def test_stutter_trim_rejects_common_short_collocation():
    """مراجعة §58 (الحالة المضادّة المؤكَّدة): تركيبٌ شائع من ١٦ حرفاً («في
    السوق المحلية») لا يُعتمَد إسقاطاً — لا حذفَ كلمةٍ مشروعة من نصٍّ مدفوع."""
    import silk_ai_judge as aj
    base = "وارتفعت الأسعار في السوق المحلية بوضوح"
    cont = "في السوق المحلية يتركز الطلب على الحليب الطازج"
    assert aj._trim_join_stutter(base, cont) == (base, cont)
    assert "بوضوح" in (aj._trim_join_stutter(base, cont)[0])


def test_continuation_join_trims_truncated_tail_stutter_end_to_end():
    """تكامل: مسارُ الإكمال الفعليّ (`_continue_truncated_report`) لا يسلّم
    تلعثمَ دراسة #10 بعد اليوم (محاكاة `_call` بلا شبكة)."""
    import silk_ai_judge as aj
    from unittest import mock
    import silk_llm_provider as lp
    lp._last_stop_reason.set(None)

    draft = ("متوسط السعر يخص فئة جملة ضيقة لا تمثل السوق كله. "
             "وهذا التناقض متوقَّع وناتج عن كون رقم كومتريد يخص فئة جملة ضيقة م")

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        return ("وهذا التناقض متوقَّع وناتج عن كون رقم كومتريد يخص فئة جملة "
                "ضيقة محدودة الدهن لا تشمل غالبية الحليب المتداول.")

    with mock.patch("silk_ai_judge._call", side_effect=fake_call):
        out = aj._continue_truncated_report("t", "user", draft, "ar")
    assert out.count("وهذا التناقض متوقَّع") == 1
    assert "محدودة الدهن لا تشمل غالبية الحليب" in out


def test_continuation_join_has_no_stutter():
    """تكامل: `_continue_truncated_report` عبر مسار الجملة لا ينتج تلعثماً عند
    حدّ الكلمة (محاكاة `_call` بلا شبكة)."""
    import silk_ai_judge as aj
    from unittest import mock
    import silk_llm_provider as lp
    lp._last_stop_reason.set(None)

    draft = "المتنُ يقول إنّ الطلب يتقلّص. هذا الانكماش"

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        return "هذا الانكماش الحاد يفرض الحذر."   # يعيد العبارةَ المقطوعة

    with mock.patch("silk_ai_judge._call", side_effect=fake_call):
        out = aj._continue_truncated_report("t", "user", draft, "ar")
    assert "هذا الانكماش هذا الانكماش" not in out
    assert "هذا الانكماش الحاد يفرض الحذر." in out
