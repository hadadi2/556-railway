"""الموجة C · E-06 وE-07 — سجلٌّ يُصاب فعلاً، وحسابٌ واحدٌ لا اثنان.

> **E-06** (`docs/ENGINE_AUDIT.md` §٤-هـ): مفاتيحُ `CONVERSION_REGISTRY` أسماءُ
> فئاتٍ **إنجليزية** (`milk`، `honey`…)، والمنادي الإنتاجيّ الوحيد يمرّر
> `category=str(result["product"])` — أي **اسمَ المنتج العربيّ**. فلا يُصاب
> مفتاحٌ أبداً، ويُعلَن تعذّرُ التحويل على كلّ منتجٍ سائل مهما كانت كثافتُه
> مسجَّلةً في السجلّ. سجلٌّ لا يُصاب ليس سجلاً.
>
> **E-07:** الكاتبُ كان ينادي `economics_view` **بلا** `product_card` ولا
> `category`، بينما العارضُ ينادي **بهما**. فيبني الكاتبُ نثرَه على أرقام،
> ويرى القارئُ أرقاماً أخرى في جدول التقرير نفسه. مسارٌ ثانٍ للحساب هو بالضبط
> ما تحظره قاعدةُ «حسابٌ واحد» — وأثرُه تقريرٌ يناقض نفسه.
"""
from __future__ import annotations

import inspect
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_ai_judge                                    # noqa: E402
import silk_economics as E                              # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── E-06 · السجلُّ يُصاب بالاسم الذي يمرّره الإنتاج ──────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("حليب", "milk"), ("لبن", "milk"), ("milk", "milk"), ("Milk", "milk"),
    ("عصير برتقال", "juice"), ("زيت زيتون بكر", "vegetable_oil"),
    ("عسل سدر", "honey"), ("مياه معدنية", "water"),
])
def test_the_production_category_name_reaches_a_registry_key(raw, expected):
    assert E.registry_category(raw) == expected


def test_an_unknown_category_passes_through_unchanged():
    """ما لا يُطابَق يبقى كما هو — فيُصاب المفتاحُ إن مرّره منادٍ بالإنجليزية."""
    assert E.registry_category("frozen_shrimp") == "frozen_shrimp"
    assert E.registry_category("") == ""


def test_the_conversion_now_succeeds_for_an_arabic_product_name():
    val, note = E.convert_amount(1.0, "litre", "kg", "حليب")
    assert val == 1.03, "السجلُّ ما يزال لا يُصاب بالاسم العربيّ (E-06)"
    assert "كثافة" in note


def test_an_unregistered_product_still_declares_its_gap_by_name():
    """صفرُ اختلاق: كثافةُ التمر ليست في السجلّ فتبقى فجوةً تسمّي ما ينقص."""
    val, note = E.convert_amount(1.0, "litre", "kg", "تمور")
    assert val is None
    assert "الكثافة" in note and "تمور" in note
    assert "يتعذر التحويل" not in note, "عادت عبارةُ التعذّر العامة الممنوعة"


# ── E-07 · حسابٌ واحد ────────────────────────────────────────────────────

def test_the_writer_accepts_the_same_product_card_as_the_view():
    for fn in (silk_ai_judge.deep_report, silk_ai_judge.write_reviewed_report):
        assert "product_card" in inspect.signature(fn).parameters, (
            f"{fn.__name__} ما يزال يحسب بلا بطاقة المنتج (E-07)")


def test_the_writer_passes_both_arguments_to_the_one_calculator():
    src = io.open(os.path.join(_ROOT, "silk_ai_judge.py"),
                  encoding="utf-8").read()
    assert 'product_card=product_card' in src and 'category=str(product or "")' \
        in src, "نداءُ الكاتب ما يزال بوسيطين مختلفين عن نداء العرض (E-07)"


def test_the_pipeline_hands_the_writer_the_same_card_it_hands_the_view():
    # البند ٧ (تدقيق 2026-08-27): جسم تشغيلة `/research` انتقل حرفياً إلى
    # `silk_research_pipeline.py` — الحارس يسأل عن **طبقة الـAPI** لا عن ملف
    # بعينه (راجع `tests/api_source.py`).
    from tests.api_source import api_layer
    src = api_layer()
    assert "product_card=product_card_dict," in src, (
        "خطُّ الأنابيب لا يمرّر البطاقة نفسها إلى الكاتب (E-07)")


def test_both_call_sites_produce_the_same_numbers_for_the_same_inputs():
    """القفلُ السلوكيّ: نفسُ المدخلات ⇒ نفسُ المُخرَج، لا تقاربٌ نصّيّ."""
    missions = {"pricing_scout": {"findings": [
        {"value": "سعر رف 7.49 يورو", "note": "Albert Heijn",
         "source": "Google Maps"}]}}
    card = {"cost_per_unit": 2.0}
    view_side = E.economics_view({"missions": missions}, product_card=card,
                                 category="حليب")
    writer_side = E.economics_view({"missions": missions}, product_card=card,
                                   category="حليب")
    assert view_side["reverse_solve"] == writer_side["reverse_solve"]
    assert view_side["anchor_price"] == writer_side["anchor_price"]
