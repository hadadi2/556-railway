"""الموجة C · E-04 — بطاقةُ المنتج تصير قابلةً للتعبئة، والفراغُ يبقى فراغاً.

> **الفجوة** (`docs/ENGINE_AUDIT.md` §٤-هـ): `ProductCard` في المحرّك يطلب
> `cost_per_unit` إلزامياً و`tier` و`monthly_capacity`، بينما كتالوجُ المنصّة
> يحمل `(name, description, hs_code, image_id)` فقط. فالحقلُ كان **غيرَ قابلٍ
> للتعبئة أصلاً** حتى لو وُصِّل، والأثرُ المقيس على **كلّ** دراسة مصنع:
> `margin_waterfall` صفر · `landed_cost` صفر · `correlate` صفر · SAM/SOM
> فجوةٌ دائمة. والعلاجُ الذي شُحن سابقاً كان **حذفَ الرطانة** من نصّ التقرير
> («أضف بطاقة منتجك (product_card)») لا تسليمَ القدرة.

**التبعيةُ الملزِمة:** هذا البند نُفِّذ **بعد** Z-01. تمريرُ البطاقة قبل نقل
التحجيم إلى الشيفرة كان **سيُفعِّل** خرقَ §9 لا يُصلِحه: البطاقةُ تصل النموذجَ
ضمن الحقائق، والموجِّهُ كان يأمره بالضرب.

**والقاعدةُ المقفولة:** تكلفةُ الوحدة رقمُ المصنع نفسه لا رقمٌ منشورٌ يُبحَث
عنه — فغيابُها **فجوةُ إدخال** لا فجوةُ بحث، ولا تُقدَّر أبداً. بطاقةٌ نصفُ
مملوءةٍ خيرٌ من بطاقةٍ مُخمَّنة، ولا بطاقةَ خيرٌ من تكلفةٍ مُختلَقة تُنتِج
هامشاً وهمياً يبني عليه المصنعُ قرارَ تصدير.
"""
from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_platform.engine_bridge import product_card_from_row   # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── الترحيل إضافيٌّ بحت ──────────────────────────────────────────────────

def test_the_migration_is_additive_only():
    path = os.path.join(_ROOT, "migrations", "platform",
                        "014_product_economics.sql")
    sql = io.open(path, encoding="utf-8").read()
    assert "ALTER TABLE products ADD COLUMN" in sql
    for banned in ("DROP ", "DELETE ", "UPDATE products SET"):
        assert banned not in sql.upper().replace("ADD COLUMN", ""), (
            f"الترحيلُ ليس إضافياً بحتاً: {banned}")
    # ولا قيمةَ افتراضية لتكلفةٍ أو طاقة — الصمتُ فجوةٌ لا صفر.
    assert "cost_per_unit REAL;" in sql, "ظهرت قيمةٌ افتراضية لتكلفة الوحدة"
    assert "monthly_capacity REAL;" in sql


def test_the_migration_number_does_not_collide():
    """درسُ ٩٧: رقمٌ مكرَّرٌ يُسقِط ترحيلاً صامتاً على كلّ قاعدة."""
    import collections
    import re
    d = os.path.join(_ROOT, "migrations", "platform")
    nums = collections.Counter(
        re.match(r"(\d+)", n).group(1) for n in os.listdir(d)
        if re.match(r"\d+.*\.sql$", n))
    assert not [k for k, v in nums.items() if v > 1], f"تصادمٌ: {nums}"


# ── البطاقةُ تُبنى — أو لا تُبنى ─────────────────────────────────────────

def test_no_cost_means_no_card_at_all():
    """بلا تكلفة لا بطاقة — ولا تكلفةٌ مُقدَّرة تُختلَق مكانها."""
    assert product_card_from_row({"name": "تمور", "tier": "premium"}) is None
    assert product_card_from_row({"cost_per_unit": None}) is None
    assert product_card_from_row({"cost_per_unit": ""}) is None
    assert product_card_from_row(None) is None


def test_a_zero_or_negative_cost_is_not_a_cost():
    """صفرٌ ليس تكلفةً — قبولُه كان سيُنتِج هامشاً يساوي السعر كلَّه."""
    assert product_card_from_row({"cost_per_unit": 0}) is None
    assert product_card_from_row({"cost_per_unit": -5}) is None


def test_a_malformed_cost_does_not_crash_and_does_not_pass():
    assert product_card_from_row({"cost_per_unit": "غالية"}) is None


def test_cost_alone_builds_a_minimal_card():
    """بطاقةٌ ناقصةٌ صالحة: الحقولُ الغائبة تُعلِن فجواتِها باسمها لاحقاً."""
    card = product_card_from_row({"cost_per_unit": 12.5})
    assert card == {"cost_per_unit": 12.5}
    assert "tier" not in card, "شريحةٌ افتراضيةٌ اختُلِقت"
    assert "monthly_capacity" not in card, "طاقةٌ افتراضيةٌ اختُلِقت"


def test_a_full_row_builds_a_full_card():
    card = product_card_from_row({
        "cost_per_unit": "12.5", "cost_unit": "kg", "tier": "premium",
        "monthly_capacity": 5000, "shipping_per_unit": 1.2,
        "certifications": "HALAL, ISO22000"})
    assert card["cost_per_unit"] == 12.5
    assert card["unit"] == "kg" and card["tier"] == "premium"
    assert card["monthly_capacity"] == 5000
    assert card["certifications"] == ["HALAL", "ISO22000"]


# ── التوصيل الحقيقيّ ─────────────────────────────────────────────────────

def test_the_launch_path_builds_the_card_from_the_catalogue():
    src = io.open(os.path.join(_ROOT, "silk_platform", "api.py"),
                  encoding="utf-8").read()
    assert "product_card=_study_product_card(study, ctx)" in src, (
        "نقطةُ الإطلاق لا تمرّر بطاقةَ المنتج (E-04)")
    assert "def _study_product_card" in src
    # **عزلُ المستأجر**: قراءةُ صفّ المنتج تُقيَّد بالحساب. المرورُ الأول كتبها
    # بلا نطاقِ ملكية فحمّرها حارسُ العزل الآليّ فوراً — والمعرّفُ وإن جاء من
    # صفّ الدراسة لا يُقرأ بلا قيد.
    assert ('"SELECT * FROM products WHERE id = ? AND account_id = ?"'
            in src), "قراءةُ بطاقة المنتج غيرُ مقيَّدةٍ بالحساب"


def test_a_none_card_is_never_passed_to_the_runner():
    """«بلا بطاقة» و«ببطاقةٍ فارغة» حالتان مختلفتان عند المستهلِك."""
    src = io.open(os.path.join(_ROOT, "silk_platform", "engine_bridge.py"),
                  encoding="utf-8").read()
    assert 'if product_card and _runner_takes(runner, "product_card")' in src, (
        "بطاقةٌ فارغة تُمرَّر فتختلط بفجوة الإدخال المعلنة (E-04)")


def test_the_economics_columns_are_writable():
    from silk_platform.repository import _WRITABLE
    for col in ("cost_per_unit", "cost_unit", "tier", "monthly_capacity",
                "shipping_per_unit", "certifications"):
        assert col in _WRITABLE["products"], f"{col} غيرُ قابلٍ للكتابة"


# ── C9 · ما يُقال حين تغيب التكلفة ───────────────────────────────────────

def test_the_missing_cost_message_names_it_as_the_factorys_own_number():
    """لا نقول «بيانات ناقصة» — نقول أيّ رقمٍ ولماذا هو رقمُ المصنع."""
    import silk_i18n
    import silk_reports
    for lang in ("ar", "en"):
        msg = silk_i18n.t("margin_needs_cost", lang)
        action = silk_i18n.t("margin_needs_cost_action", lang)
        assert msg.strip() and action.strip()
        for text in (msg, action):
            hits = silk_reports._client_forbidden_hits(text, lang)
            assert hits == [], f"بلغةِ نظام في {lang}: {hits[:2]}"
        assert "product_card" not in msg, (
            "عادت رطانةُ الشيفرة إلى سطح العميل — الحادثةُ الأصلية")
