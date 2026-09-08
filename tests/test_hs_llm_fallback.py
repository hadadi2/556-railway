"""المخرجُ الثالث: مصنّفٌ مُرسًى يُسأل **حين يعجز المعجم ولا صورة** (المرحلة ٣).

> **قرارُ المالك (2026-08-30، بعد قياس التغطية).** المرجعُ يحمل مصطلحاً عربياً
> على ١٤٦ صفّاً من ٥٦١٣ (٢٫٦٪) — وفي فصول الغذاء ١٠٫٥٪ فقط، وفصولُ الآلات
> والكهرباء والكيماويات صفرٌ تماماً. الدرس ٢٠٩ حسم المسارين (رمزٌ يكتبه المصنع،
> أو صورةٌ تُحسَم) — لكنّ مصنعاً بلا صورةٍ ومنتجاً خارج المعجم كان يبقى بلا
> مخرج. المخرجُ الثالث: `classify_general` المُرسى على المرجع الرسميّ.

**العقدُ الذي يقفله هذا الملفّ:**

١) المسارُ السريع يبقى مجّانياً وحتمياً — تصنيفٌ يحسمه المعجم **لا يُنادي
   نموذجاً إطلاقاً**. الكلفةُ تقع على الإخفاق وحده.
٢) `tier == "auto"` وحدها تُعتمَد — لا «أفضل مرشّح» ولا قائمةٌ تُعرَض (نفسُ
   عقد مسار الصورة، الدرس ٢٠٩).
٣) الثقةُ **مقيسة** (تداخلُ صفات المنتج مع وصف النموذج نفسِه) لا مختلَقة،
   والطريقةُ تُسمّى `llm_grounded` فيُقرأ أساسُ القرار بعد شهر.
٤) الحرّاسُ البنيويّون يسري كلُّهم على جواب النموذج: فصلٌ حقيقيّ، داخل نطاق
   سِلك غير النفطيّ، وموجودٌ في المرجع. «مُرسًى» تعني هذا حرفياً.
٥) لا يُستشار النموذجُ حين يكون السؤالُ **قراراً بشرياً**: تعارضُ كتالوج،
   أو محورٌ رقميّ يُجيب عنه المنتجُ لا النموذج.
"""
from unittest import mock

import pytest

import silk_hs_pipeline as P


def _auto(hs6: str, overlap: float = 0.9, desc: str = "وصفٌ رسميّ للبند"):
    """ردُّ `classify_general` بدرجة auto — الشكلُ الحقيقيّ لا مُبسَّطاً."""
    return {"tier": "auto", "hs6": hs6, "confidence": overlap,
            "candidates": [{"hs6": hs6, "code_desc": desc, "overlap": overlap,
                            "verified": True, "source": "llm",
                            "reason_ar": "سببٌ من النموذج"}],
            "message": "", "source": "llm", "used_llm": True}


def _not_auto(tier: str = "candidates"):
    return {"tier": tier, "hs6": None, "confidence": 0.0,
            "candidates": [{"hs6": "210690", "code_desc": "محضرات غذائية",
                            "overlap": 0.5, "verified": True, "source": "llm"}],
            "message": "", "source": "llm", "used_llm": True}


# ═══════════ ١ — المسارُ السريع لا يكلّف شيئاً ═══════════════════════════════
def test_a_deterministic_hit_never_calls_the_model():
    """«حلاوة طحينية» يحسمها المعجم — صفر نداءٍ مدفوع مهما كان الإذن مفتوحاً."""
    with mock.patch("silk_hs_classifier.classify_general") as spy:
        out = P.classify("حلاوة طحينية", allow_claude=True)
    assert out["classification_status"] == P.APPROVED
    assert out["final_hs_code"] == "170490"
    assert spy.call_count == 0, "نداءٌ مدفوع على مسارٍ حسمه المعجم مجّاناً"


def test_the_catalog_agreement_path_never_calls_the_model():
    """اتفاقُ الكتالوج مع المُحلِّل حسمٌ حتميّ — لا نموذجَ ولا كلفة."""
    with mock.patch("silk_hs_classifier.classify_general") as spy:
        out = P.classify("حلاوة طحينية", "170490", allow_claude=True)
    assert out["classification_status"] == P.APPROVED
    assert spy.call_count == 0


# ═══════════ ٢ — الإذنُ شرط، والدرجةُ `auto` شرط ════════════════════════════
def test_without_permission_the_miss_still_just_asks():
    """بلا إذنٍ صريح لا يقع نداءٌ مدفوع — السلوكُ اليوم يبقى كما هو."""
    with mock.patch("silk_hs_classifier.classify_general") as spy:
        out = P.classify("مناديل ورقية", allow_claude=False)
    assert out["classification_status"] == P.REQUIRES_CONFIRMATION
    assert spy.call_count == 0


def test_a_grounded_auto_answer_is_adopted_with_a_measured_confidence():
    """إخفاقُ المعجم + `tier=auto` ⇒ اعتمادٌ بثقةٍ **مقيسة** وطريقةٍ مسمّاة."""
    with mock.patch("silk_hs_classifier.classify_general",
                    return_value=_auto("481820", overlap=0.88)) as spy:
        out = P.classify("مناديل ورقية", allow_claude=True)
    assert spy.call_count == 1
    assert out["classification_status"] == P.APPROVED, out["reason"]
    assert out["final_hs_code"] == "481820"
    assert out["classification_method"] == P.METHOD_LLM_GROUNDED
    assert out["confidence"] == pytest.approx(0.88)
    assert isinstance(out["confidence"], float)
    # وأثرُ القرار مكتوبٌ في السلسلة، فلا يُقرأ الرمزُ بلا مصدره.
    assert any(p["step"] == "llm_fallback" for p in out["provenance"]), out


@pytest.mark.parametrize("tier", ["candidates", "manual"])
def test_anything_below_auto_asks_and_never_guesses(tier):
    """ما دون `auto` يُسأل فيه — لا «أفضل مرشّح» صامت (الدرس ٢٠٩ حرفياً)."""
    with mock.patch("silk_hs_classifier.classify_general",
                    return_value=_not_auto(tier)):
        out = P.classify("مناديل ورقية", allow_claude=True)
    assert out["classification_status"] == P.REQUIRES_CONFIRMATION
    assert out["final_hs_code"] is None


# ═══════════ ٣ — الحرّاسُ البنيويّون يسرون على النموذج أيضاً ════════════════
@pytest.mark.parametrize("bad,why", [
    ("270900", "فصلٌ خارج نطاق سِلك غير النفطيّ"),
    ("009900", "فصلٌ غير موجود في بنية WCO"),
    ("99", "رمزٌ باطلُ الشكل"),
    ("999999", "رمزٌ خارج المرجع الرسميّ"),
])
def test_a_model_answer_that_fails_a_structural_guard_is_refused(bad, why):
    """«مُرسًى» ليست كلمةً: جوابُ النموذج يواجه الحرّاسَ التي لا تعتمد المعجم."""
    with mock.patch("silk_hs_classifier.classify_general",
                    return_value=_auto(bad)):
        out = P.classify("مناديل ورقية", allow_claude=True)
    assert out["final_hs_code"] != bad, why
    assert out["classification_status"] == P.REQUIRES_CONFIRMATION


def test_a_failing_model_call_degrades_to_asking_never_crashes():
    """عطلُ النموذج/انقطاعُ الشبكة ⇒ سؤالٌ معلَن، لا انهيارٌ ولا رمزٌ مختلَق."""
    with mock.patch("silk_hs_classifier.classify_general",
                    side_effect=RuntimeError("provider down")):
        out = P.classify("مناديل ورقية", allow_claude=True)
    assert out["classification_status"] == P.REQUIRES_CONFIRMATION
    assert out["final_hs_code"] is None


# ═══════════ ٤ — لا يُستشار النموذجُ في قرارٍ بشريّ ═════════════════════════
def test_a_catalog_conflict_is_not_handed_to_the_model():
    """تعارضُ الكتالوج قرارُ إنسان — لا يُحسَم بنموذجٍ ولا يُنفَق عليه."""
    with mock.patch("silk_hs_classifier.classify_general") as spy:
        out = P.classify("حلاوة طحينية", "110100", allow_claude=True)
    assert out["catalog_hs_status"] == P.CATALOG_CONFLICT
    assert out["final_hs_code"] is None
    assert spy.call_count == 0, "أُنفِق على سؤالٍ جوابُه عند المصنع لا النموذج"


def test_a_numeric_axis_is_not_handed_to_the_model():
    """المحورُ الرقميّ يُجيب عنه المنتجُ (بطاقةُ العبوة) لا نموذجٌ لغويّ."""
    with mock.patch("silk_hs_classifier.classify_general") as spy:
        out = P.classify("حليب", allow_claude=True)
    assert out["refusal_code"] == P.REFUSAL_AXIS
    assert spy.call_count == 0


# ═══════════ ٥ — الإفصاح يصل النتيجة ════════════════════════════════════════
def test_the_summary_names_the_model_grounded_basis():
    """تقريرٌ بُني على جوابِ نموذجٍ يقول ذلك — لا يُقرأ كحسمٍ حتميّ."""
    with mock.patch("silk_hs_classifier.classify_general",
                    return_value=_auto("481820", overlap=0.86)):
        out = P.classify("مناديل ورقية", allow_claude=True)
    summary = P.result_summary(out)
    assert summary["classification_method"] == P.METHOD_LLM_GROUNDED
    assert summary["confidence"] == pytest.approx(0.86)
