"""إعادةُ التحقّق من رمز الكتالوج — catalog HS re-validation (البندان ٢ و١٦).

> **الحادثة (تدقيق 2026-08-30).** رمزُ الكتالوج كان **يتخطّى التصنيف كلّه**:
> `api.py` يضبط ثقتَه `None` لأنّ مصدرَه «catalog»، وفرعُ المُحلِّل محروسٌ
> بـ`if not hs_code` فلا يُسأل أصلاً. النتيجة المرصودة: «حلاوة طحينية» + 170490
> (وهو **الصحيح**، والمُحلِّل يمنحه ١٫٠٠) تُحجَب بـ«ثقةُ التصنيف غير معلومة».
> العطلُ لم يكن في البوّابة ولا في العتبة ولا في الرمز — بل في أنّ أحداً لم
> يقِس المطابقةَ إطلاقاً.

القاعدةُ الدائمة: **رمزُ الكتالوج مرشّحٌ يُقاس، لا حقيقةٌ تُفترَض ولا تهمةٌ
تُحجَب.** يُقاس على اسم المنتج كأيّ مرشّح، ثمّ يُقارَن بما يعيده المُحلِّل
مستقلاً — والمصفوفةُ الأربعة أدناه هي العقد.

The catalog code is neither trusted nor dismissed: it is measured against the
product name and reconciled with the independent classifier.
"""
import pytest

import silk_hs_pipeline as P


# ═══════════ ١ — المصفوفة الأربعة (البند ١٦) ═════════════════════════════════
def test_catalog_agrees_with_classifier_is_auto_approved():
    """الحالةُ المُبلَّغة حرفياً: اتفاقٌ بدليلٍ قويّ ⇒ تنطلق الدراسة."""
    out = P.classify("حلاوة طحينية", "170490")
    assert out["classification_status"] == P.APPROVED, out["reason"]
    assert out["catalog_hs_status"] == P.CATALOG_AUTO_APPROVED
    assert out["final_hs_code"] == "170490"
    assert out["classification_method"] == P.METHOD_CATALOG_AGREEMENT
    assert out["confidence"] >= P.min_confidence()
    assert out["requires_user_confirmation"] is False


def test_catalog_disagrees_with_classifier_is_a_conflict_not_a_silent_pick():
    """اختلافٌ ⇒ **لا يُختار أحدُهما صامتاً** — نصُّ البند ٢ حرفياً."""
    out = P.classify("حلاوة طحينية", "110100")     # دقيق قمح لمنتج حلوى
    assert out["classification_status"] == P.REQUIRES_CONFIRMATION
    assert out["catalog_hs_status"] == P.CATALOG_CONFLICT
    assert out["refusal_code"] == P.REFUSAL_CONFLICT
    # ولا يُسرَّب أيٌّ منهما رمزاً نهائياً يُبنى عليه إنفاق.
    assert out["final_hs_code"] is None
    assert "110100" in out["reason"] and "170490" in out["reason"]


def test_missing_catalog_code_classifies_normally():
    """بلا رمزِ كتالوج ⇒ المُحلِّل يعمل كالمعتاد ويُصرّح بغيابه."""
    out = P.classify("حلاوة طحينية")
    assert out["catalog_hs_status"] == P.CATALOG_ABSENT
    assert out["final_hs_code"] == "170490"
    assert out["classification_status"] == P.APPROVED


@pytest.mark.parametrize("bad", ["17049", "1704900", "17049A", "abcdef",
                                 "170490; DROP TABLE studies", "17 49 0",
                                 "١٧٠٤٩٠"])
def test_invalid_catalog_code_is_rejected_and_never_reaches_storage(bad):
    """رمزٌ باطلُ الشكل ⇒ يُرفَض صراحةً (البند ٢٨: تحقّقُ شكلٍ قبل أيّ استعمال)."""
    out = P.classify("حلاوة طحينية", bad)
    assert out["catalog_hs_status"] == P.CATALOG_REJECTED
    assert out["refusal_code"] == P.REFUSAL_CATALOG_REJECTED
    assert out["final_hs_code"] is None
    assert out["classification_status"] == P.REQUIRES_CONFIRMATION


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_blank_catalog_code_is_absent_not_malformed(blank):
    """فراغٌ ليس رمزاً باطلاً بل **غياب** رمز — التمييزُ يغيّر نصَّ ما يُطلَب."""
    out = P.classify("حلاوة طحينية", blank)
    assert out["catalog_hs_status"] == P.CATALOG_ABSENT
    assert out["classification_status"] == P.APPROVED
    assert out["final_hs_code"] == "170490"


def test_out_of_scope_catalog_code_is_rejected_with_its_reason():
    """رمزٌ في فصلٍ خارج نطاق سِلك (الوقود المعدني) ⇒ رفضٌ بسببٍ معلَن."""
    out = P.classify("نفط خام", "270900")
    assert out["final_hs_code"] is None
    assert out["classification_status"] == P.REQUIRES_CONFIRMATION
    assert any("نطاق" in c or "بترولي" in c for c in out["contradictions"]), out


# ═══════════ ٢ — لا ثقةَ مختلَقة ولا ثقةَ ضائعة (البند ٤) ════════════════════
def test_confidence_is_never_none_on_any_outcome():
    """كلُّ مخرجٍ يحمل رقماً — «غير معلومة» كانت عَرَضَ العطل الأصليّ."""
    for product, catalog in [("حلاوة طحينية", "170490"),
                             ("حلاوة طحينية", "110100"),
                             ("مناديل ورقية", None),
                             ("سمسم", "999999"),
                             ("", "170490")]:
        out = P.classify(product, catalog)
        assert isinstance(out["confidence"], float), (product, catalog, out)


def test_a_catalog_code_is_never_approved_on_storage_alone():
    """رمزٌ مخزَّنٌ لا يُعتمَد لكونه مخزَّناً — يجتاز دليلَه أو يُسأل عنه.

    هذا هو الحدُّ الذي يفصل هذه الموجة عن «ثِق بالكتالوج»: الحلاوةُ تمرّ لأن
    المُحلِّل يوافقها بدليلٍ مقيس، لا لأن أحداً كتبها في جدول.
    """
    # اسمُ علامةٍ تجارية لا يطابق أيّ صفّ: لا دليلَ يُقاس ⇒ لا اعتماد.
    out = P.classify("الطاحونة", "170490")
    assert out["classification_status"] == P.REQUIRES_CONFIRMATION, out
    assert out["final_hs_code"] is None
    assert out["catalog_hs_status"] in (P.CATALOG_REQUIRES_CONFIRMATION,
                                        P.CATALOG_CONFLICT)


def test_explicit_human_confirmation_approves_but_still_discloses():
    """تأكيدُ المصنع يعتمد الرمزَ — ويُبقي ما يخالفه معلناً (إفصاحٌ لا إخفاء)."""
    out = P.classify("حلاوة طحينية", "110100", hs_confirmed=True)
    assert out["classification_status"] == P.APPROVED
    assert out["final_hs_code"] == "110100"
    assert out["classification_method"] == P.METHOD_USER_CONFIRMED
    # الثقةُ تبقى **مقيسةً** ولا تُرفَع إلى 1.0 لمجرّد التأكيد.
    assert out["confidence"] < 1.0, out["confidence"]
    assert out["contradictions"], "التأكيدُ أخفى التعارضَ بدل أن يُعلنه"


def test_a_present_human_may_refine_inside_the_established_heading():
    """تنقيحٌ داخل الترويسة ليس خلافاً — والكتالوجُ لا ينال هذا الحقّ.

    المرجعُ يعلّق كلمتَه العربية على بندٍ واحدٍ من الترويسة مصادفةً، فرفضُ
    اختيار إنسانٍ حاضرٍ لبندٍ شقيقٍ يعاقبه على فجوةِ تغطيةٍ عندنا. أمّا رمزُ
    كتالوجٍ مخزَّن فلا إنسانَ خلفه في هذه اللحظة (الدرس ١٢٠ — حادثة الحليب).
    """
    typed = P.classify("معكرونة", "190219", user_supplied=True)
    assert typed["classification_status"] == P.APPROVED, typed["reason"]
    assert typed["final_hs_code"] == "190219"
    assert typed["classification_method"] == P.METHOD_USER_CONFIRMED

    stored = P.classify("معكرونة", "190219", user_supplied=False)
    assert stored["classification_status"] == P.REQUIRES_CONFIRMATION, stored
    assert stored["catalog_hs_status"] == P.CATALOG_CONFLICT


def test_determinism_same_input_same_output():
    """البند ١٠: نفسُ المدخل ⇒ نفسُ الترتيب ونفسُ القرار، في كل مرّة."""
    runs = [P.classify("حلاوة طحينية", "170490") for _ in range(3)]
    keys = ("final_hs_code", "confidence", "classification_status",
            "classification_method", "catalog_hs_status")
    for r in runs[1:]:
        assert {k: r[k] for k in keys} == {k: runs[0][k] for k in keys}
        assert [c["hs6"] for c in r["candidate_codes"]] == \
               [c["hs6"] for c in runs[0]["candidate_codes"]]
