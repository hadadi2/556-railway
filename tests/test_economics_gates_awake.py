"""الموجة C · E-05 وE-08 — بوّابتان كانتا خامدتَين بنيوياً على مسار المصنع.

> **الجذرُ المشترك** (`docs/ENGINE_AUDIT.md` §٤-هـ): البعثاتُ على المسار العميق
> تُعيد **جملاً**، والطبقتان تقرآن `float(value)` فقط. فالنتيجةُ ليست خطأً
> عَرَضياً بل **خمودٌ بنيويّ**: HHI لا يتكوّن أبداً، وفحصُ «الاقتصاد حاضر» لا
> يُطلِق أبداً — على **كلّ** دراسة مصنع، بلا أثر.
>
> وفحصٌ لا يُطلِق ليس فحصاً؛ حضورُه في القائمة يوهم بتغطيةٍ غيرِ موجودة.

**والتمييزُ الأهمّ (E-05):** `bool(hhi is None and …)` كانت `False` — أي أنّ
«الإزاحة غير مطلوبة» تُقال بثقةٍ حين **لم تُقَس** أصلاً. والحالتان مختلفتان
تجارياً: سوقٌ مفتّتٌ يُدخَل بالتنافس السعريّ، وسوقٌ لم يُقَس تركّزُه يُدخَل
بحذر. طيُّ الثانية في الأولى ادّعاءُ قياسٍ لم يجرِ.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_economics as E                              # noqa: E402
import silk_quality_gate as Q                           # noqa: E402


def _competitors(value, note="تركّز") -> dict:
    return {"missions": {"competitors": {"findings": [
        {"value": value, "note": note}]}}}


# ── E-05 · HHI يتكوّن من النثر ───────────────────────────────────────────

def test_hhi_forms_from_a_prose_finding():
    out = E.economics_view(_competitors(
        "مؤشر HHI للسوق يقارب 2350 مما يعني تركّزاً متوسطاً"))
    assert out["hhi"] == 2350.0, "HHI ما يزال لا يتكوّن من النثر (E-05)"
    assert out["displacement_measured"] is True


def test_a_numeric_hhi_still_works():
    """تكافؤٌ رجعيّ للمسار القديم."""
    out = E.economics_view(_competitors(3100.0, "HHI تركّز"))
    assert out["hhi"] == 3100.0 and out["displacement_required"] is True


def test_unmeasured_concentration_is_declared_not_called_open():
    """«لم يُقَس» ≠ «سوقٌ مفتوح» — الفرقُ قرارُ دخولٍ مختلف."""
    out = E.economics_view({"missions": {}})
    assert out["displacement_measured"] is False
    assert out["displacement_required"] is False
    joined = " ".join(out["gaps"])
    assert "تركّز المورّدين غير متاح" in joined, "الخمودُ عاد صامتاً"
    assert "لا تقرأ ذلك" in joined, "الفجوةُ لا تحذّر من القراءة الخاطئة"


def test_a_number_without_its_keyword_is_not_taken_as_hhi():
    """«٣ منافسين» لا تصير مؤشرَ تركّز — الكلمةُ المفتاحية شرطٌ سابق."""
    out = E.economics_view(_competitors("رُصِد 3 منافسين رئيسيين", "منافسون"))
    assert out["hhi"] is None


# ── E-08 · فحصُ «الاقتصاد حاضر» يستيقظ ───────────────────────────────────

def _dr(price_value, eco=None) -> dict:
    return {"missions": {"pricing_scout": {"findings": [
        {"value": price_value, "note": "سعر رف"}]}},
        "economics": eco or {}}


def test_the_check_fires_on_a_prose_price_with_no_economics():
    hits = Q._check_economics_present(_dr("سعر رف 7.49 يورو"))
    assert [h["check"] for h in hits] == ["economics_missing_despite_inputs"], (
        "الفحصُ ما يزال خامداً على الشكل الإنتاجيّ (E-08)")


def test_the_check_still_fires_on_a_numeric_price():
    assert Q._check_economics_present(_dr(7.49))


def test_the_check_stays_quiet_when_economics_is_present():
    assert Q._check_economics_present(
        _dr(7.49, {"reverse_solve": {"max_exw": 3.2}})) == []


def test_the_check_stays_quiet_when_no_price_was_observed():
    """لا سعرَ ⇒ لا لومَ على غياب الاقتصاد (الفجوةُ مُعلَنةٌ في مكانها)."""
    assert Q._check_economics_present(
        {"missions": {"pricing_scout": {"findings": [
            {"value": "لم نرصد أسعاراً", "note": "مسح"}]}},
         "economics": {}}) == []
