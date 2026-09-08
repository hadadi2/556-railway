"""الموجة C · E-01 وE-09 — مستوى السعر حقلٌ بنيويّ، ولا مرساةَ عبر مستويين.

> **الحادثة** (`docs/ENGINE_AUDIT.md` §٤-هـ): مرساةُ سعر الرفّ كانت **أدنى**
> قيمةٍ رقمية في بعثة الأسعار، و`basis="retail"` **مُرمَّزاً صلباً**. فقيمةُ
> استيرادٍ عند الحدود (CIF) — وهي بطبيعتها أدنى من سعر الرفّ بأضعاف — تُوسَم
> «أدنى سعر رفّ منافس مرصود» ويُبنى عليها الحلُّ العكسيّ كلُّه.
>
> والأثرُ ليس خطأً عشوائياً بل **تفاؤلٌ منهجيٌّ في اتجاهٍ واحد**: كلُّ هامشٍ
> لاحقٍ أكبرُ من الحقيقة لأنّ المقام أصغرُ ممّا يجب. مصنعٌ يقرأ هامشاً ٤٠٪ وهو
> ١٢٪ يوقّع عقداً يخسر فيه.

**القاعدةُ المقفولة:** لا مرساةَ رفٍّ إلا من صفٍّ مستواه `retail` **مُصرَّحٌ
به**. ومستوىً لا يُكتشَف ليس `retail` افتراضاً — هو **مجهول**، والمجهولُ يُعلَن
ولا يُرسي حساباً.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_economics as E                              # noqa: E402


def _dr(*rows) -> dict:
    return {"missions": {"pricing_scout": {"findings": [
        {"value": v, "note": n} for v, n in rows]}}}


# ── الكشفُ حتميٌّ بلا نموذج ──────────────────────────────────────────────

@pytest.mark.parametrize("note,level", [
    ("سعر الرف في سوبرماركت 25 ريال", "retail"),
    # بلا «ال» التعريف — الصيغةُ التي تكتبها بعثةُ الأسعار فعلاً، وكان
    # إغفالُها يُعطِّل المرساةَ على مدخلٍ سليمٍ تماماً.
    ("سعر رف Albert Heijn", "retail"),
    ("سعر التجزئة للمستهلك", "retail"),
    ("shelf price in the supermarket", "retail"),
    ("retail price observed", "retail"),
    ("سعر الجملة للموزّع", "wholesale"),
    ("wholesale price per carton", "wholesale"),
    ("قيمة الاستيراد عند الحدود", "CIF"),
    ("landed customs value", "CIF"),
    ("تسليم ظهر السفينة", "FOB"),
    ("ex-works price", "EXW"),
])
def test_price_level_is_detected_deterministically(note, level):
    assert E.detect_price_level(note) == level


@pytest.mark.parametrize("note", ["متوسط السعر 20", "السعر 15", "", None,
                                  "average price observed"])
def test_an_undetectable_level_is_unknown_not_retail(note):
    """المجهولُ ليس تجزئةً — افتراضُ التجزئة عند الجهل هو العطلُ نفسه."""
    assert E.detect_price_level(note) is None


# ── المستوى بحكم المصدر — والإبرةُ الصريحة تسبقه ────────────────────────

def test_a_store_listing_is_retail_by_provenance():
    """سعرٌ من قائمة متجرٍ على الخرائط تجزئةٌ **بحكم بنائه**.

    الملاحظةُ تسمّي المتجرَ فقط («Albert Heijn»)، فاشتراطُ إبرةٍ صريحة كان
    سيُسقِط إشارةَ تجزئةٍ مشروعة ويُعطِّل قسمَ الاقتصاد كلَّه — إصلاحٌ يُنتِج
    عطلاً آخر. خاصّيةُ الجامع موثَّقةٌ لا مفترَضة.
    """
    assert E.detect_price_level("Albert Heijn", "Google Maps") == "retail"
    assert E.detect_price_level("متجر", "") == "retail"


def test_an_explicit_marker_beats_the_source_property():
    """**الحدُّ الحاسم:** «عند الحدود» تُقرأ CIF ولو جاءت من الخرائط.

    لولا هذا الترتيب لعاد العطلُ الأصليّ من الباب الخلفيّ: كلُّ ما يأتي من
    جامعِ التجزئة يصير تجزئةً مهما قالت ملاحظتُه.
    """
    assert E.detect_price_level("قيمة الاستيراد عند الحدود",
                                "Google Maps") == "CIF"
    assert E.detect_price_level("سعر الجملة", "Google Maps") == "wholesale"


def test_an_unrelated_source_grants_no_level():
    assert E.detect_price_level("السعر 20", "UN Comtrade") is None


# ── المرساةُ لا تتكوّن إلا من تجزئةٍ مُصرَّحٍ بها ──────────────────────────

def test_a_border_price_can_never_become_the_shelf_anchor():
    """الحادثةُ الأصلية: CIF يُتبنّى مرساةَ رفّ."""
    out = E.economics_view(_dr((6.0, "قيمة الاستيراد عند الحدود")))
    assert out["anchor_price"] is None, "سعرُ حدودٍ صار مرساةَ رفّ مجدّداً"


def test_the_lowest_price_no_longer_wins_across_levels():
    """أدنى قيمةٍ لم تعد تفوز — المستوى يسبق الرقم."""
    out = E.economics_view(_dr((6.0, "قيمة الاستيراد عند الحدود"),
                               (25.0, "سعر الرف بالتجزئة")))
    assert out["anchor_price"]["raw_value"] == 25.0
    assert out["anchor_price"]["basis"] == "retail"


def test_the_lowest_retail_row_still_wins_among_retail_rows():
    """أقسى قيدٍ للدخول يبقى القاعدة — **داخل** المستوى الواحد."""
    out = E.economics_view(_dr((30.0, "سعر الرف"), (25.0, "shelf price")))
    assert out["anchor_price"]["raw_value"] == 25.0


def test_an_unknown_level_never_anchors():
    assert E.economics_view(_dr((20.0, "متوسط السعر")))["anchor_price"] is None


# ── الغيابُ يُعلَن ويسمّي ما رُصِد ────────────────────────────────────────

def test_non_retail_prices_are_declared_by_their_level():
    """لا صمت: يُقال إنّ أسعاراً رُصدت وإنّها ليست أسعارَ رفّ، وأيَّ مستوىً هي."""
    gaps = E.economics_view(_dr((6.0, "قيمة الاستيراد عند الحدود"),
                                (12.0, "سعر الجملة")))["gaps"]
    joined = " ".join(gaps)
    assert "ليست أسعار رفّ" in joined, "غيابُ المرساة صار صامتاً"
    assert "سعر عند الحدود" in joined and "سعر جملة" in joined, (
        "الفجوةُ لا تسمّي المستويات التي رُصدت فعلاً")


def test_the_declared_gap_explains_the_business_consequence():
    """C9: الفجوةُ تقول **لماذا يهمّ** لا «تعذّر التسعير» وحدها."""
    gaps = E.economics_view(_dr((6.0, "قيمة الاستيراد عند الحدود")))["gaps"]
    joined = " ".join(gaps)
    assert "أضعاف" in joined and "أكبر من الحقيقي" in joined, (
        "الفجوةُ لا تشرح أثرَ خلط المستويات على الهامش")


def test_zero_prices_still_yield_the_original_gap():
    """لا أسعارَ إطلاقاً ⇒ الفجوةُ القديمة كما هي (تكافؤٌ رجعيّ)."""
    gaps = E.economics_view(_dr())["gaps"]
    assert any("لا سعر رف منافس مرصود" in g for g in gaps)


def test_counts_are_still_excluded_before_the_level_check():
    """«عدد المتاجر ٣» لا يصير سعراً — الحارسُ القائم يبقى أولاً."""
    out = E.economics_view(_dr((3.0, "عدد المتاجر في سعر الرف")))
    assert out["anchor_price"] is None


# ── E-02 · المرساةُ تتكوّن من بعثاتٍ نثرية ───────────────────────────────
#
# `float(finding["value"])` ينجح على قيمةٍ رقمية فقط، وبعثةُ الأسعار على
# المسار العميق تُعيد **جملاً**. فكان الفشلُ على **كلّ** اكتشاف، ولا يتكوّن
# قسمُ الاقتصاد أصلاً مهما رصدت البعثةُ من أسعارٍ حقيقية.

def test_a_price_is_extracted_from_a_prose_finding():
    dr = {"missions": {"pricing_scout": {"findings": [{
        "value": "سعر رف عبوة التمر ١ كجم في ألبرت هاين 7.49 يورو",
        "note": "Albert Heijn", "source": "Google Maps"}]}}}
    anchor = E.economics_view(dr)["anchor_price"]
    assert anchor is not None, "بعثةٌ نثرية ما تزال تُنتِج صفرَ مرساة (E-02)"
    assert anchor["raw_value"] == 7.49
    assert anchor["basis"] == "retail"


def test_a_range_takes_its_lower_bound_not_its_upper():
    """**الاتجاه المتفائل مسدود:** «بين ٦ و٩» ⇒ ٦ لا ٩.

    الحدُّ الأدنى غيرُ ملتصقٍ بعملة، فقاعدةُ الالتصاق وحدَها كانت تلتقط ٩ —
    أي الحدَّ الأعلى، فمرساةٌ أعلى ⇒ هامشٌ أكبر من الحقيقة. وهو بعينه العطلُ
    الذي تعالجه هذه الموجة، بشكلٍ آخر.
    """
    assert min(E.price_numbers_in_text("يتراوح بين 6 و9 يورو للكيلو")) == 6.0
    assert min(E.price_numbers_in_text("السعر من 12 إلى 18 ريال")) == 12.0


def test_a_floating_number_is_never_taken_as_a_price():
    """رقمٌ بلا عملةٍ متروكٌ عمداً — «٣ متاجر» و«٢٠٢٤» ليست أسعاراً."""
    assert E.price_numbers_in_text("رُصِد 3 متاجر في 2024") == []
    assert E.price_numbers_in_text("بين 2019 و2024 ارتفع") == []


def test_a_currency_symbol_prefix_is_read_too():
    assert E.price_numbers_in_text("€5.20 في المتجر") == [5.2]


def test_a_numeric_finding_still_takes_the_old_path():
    """تكافؤٌ رجعيّ: القيمةُ الرقمية تُقرأ كما كانت، بلا مرورٍ بالنثر."""
    dr = {"missions": {"pricing_scout": {"findings": [
        {"value": 7.49, "note": "سعر رف Albert Heijn"}]}}}
    assert E.economics_view(dr)["anchor_price"]["raw_value"] == 7.49


def test_prose_carrying_a_non_price_word_is_still_rejected():
    """حارسُ «عدد/نسبة/مؤشر» يبقى فوق الاستخراج النثريّ لا تحته."""
    dr = {"missions": {"pricing_scout": {"findings": [
        {"value": "عدد المتاجر 3 بمتوسط 12 يورو", "note": "مسح"}]}}}
    assert E.economics_view(dr)["anchor_price"] is None
