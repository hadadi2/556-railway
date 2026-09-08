"""الموجة C · S-02 وX-02 — القِدَمُ يصل الكاتب، والنطاقُ الأعمى يُغلَق.

> **S-02** (`docs/ENGINE_AUDIT.md` §٤-و): تحذيرُ القِدَم يُحسَب لكلّ مكوّن
> (`components_detail[*]["vintage"]`) ثمّ **لا يقرؤه أيُّ مُصيّر** — مئاتُ
> الحسابات تُرمى. فيبني الكاتبُ سرداً واثقاً على رقمٍ عمرُه سنوات وهو لا يعلم
> أنه قديم، ويقرأ المصنعُ اتجاهاً لعلّ السوقَ تجاوزه.
>
> **X-02:** كشفُ التناقض الرقميّ كان **شريحتين منفصلتين**: تطابقٌ شبهُ تامّ
> يمرّ، وتناقضٌ فاحش (>٣×) يحجب. وبينهما — حيث يعيش أخطرُ تعارضٍ حقيقيّ —
> لا كشفَ إطلاقاً: رقمان يختلفان ٢٫٥× لنفس المؤشر يصلان العميلَ في وثيقةٍ
> واحدة بلا كلمة.
"""
from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_quality_gate as Q                           # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── S-02 · القِدَمُ يصل كتلةَ حقائق الكاتب ────────────────────────────────

def test_the_vintage_caveat_reaches_the_writer_facts_block():
    src = io.open(os.path.join(_ROOT, "silk_render.py"), encoding="utf-8").read()
    assert '_vint = str(c.get("vintage") or "").strip()' in src, (
        "تحذيرُ القِدَم عاد يُحسَب ويُهمَل (S-02)")
    assert '_age = f" — {_vint}" if _vint else ""' in src, (
        "التحذيرُ لا يلتصق برقمه — مصدرُ الرقم وعمرُه يُقرآن معاً أو لا")


def test_a_fresh_component_gains_no_noise():
    """لا وسمَ حيث لا قِدَم — الإضافةُ مشروطةٌ لا دائمة."""
    src = io.open(os.path.join(_ROOT, "silk_render.py"), encoding="utf-8").read()
    idx = src.index('_age = f" — {_vint}" if _vint else ""')
    assert 'if _vint else ""' in src[idx:idx + 60]


# ── X-02 · الشريحةُ الوسطى تُكشَف تحذيرياً ──────────────────────────────

def _dr(evidence_usd: float, body_millions: float) -> dict:
    """الشكلُ الذي يقرؤه الفحصُ فعلاً: ملاحظةٌ فيها «واردات»، ومتنٌ بصيغة
    «N مليون دولار» (`_USD_AMOUNT_RE` يشترط كلمة «دولار» لا الرمز `$`)."""
    return {"missions": {"trade_flow": {"findings": [
        {"value": evidence_usd, "note": "إجمالي واردات السوق"}]}},
        "report": {"text": (f"بلغت واردات السوق {body_millions:g} مليون "
                            "دولار خلال العام.")}}


def test_a_gross_contradiction_still_blocks():
    """تكافؤٌ رجعيّ: الحاجزُ عند ٣× كما كان حرفياً."""
    hits = Q._check_evidence_body_numeric_consistency(_dr(10_000_000, 50))
    checks = {h["check"] for h in hits}
    assert "evidence_body_numeric_contradiction" in checks
    assert all(not h["repairable"] for h in hits
               if h["check"] == "evidence_body_numeric_contradiction")


def test_the_blind_band_is_now_reported_as_a_warning():
    """٢٫٥× كانت تمرّ بلا كلمة — الآن تُعلَن، ولا تحجب."""
    hits = Q._check_evidence_body_numeric_consistency(_dr(10_000_000, 25))
    checks = {h["check"] for h in hits}
    assert "evidence_body_numeric_divergence" in checks, (
        "النطاقُ الأعمى ما يزال أعمى (X-02)")
    assert all(h["repairable"] for h in hits), "الشريحةُ الوسطى صارت حاجبة"


def test_the_middle_band_is_not_a_blocking_check():
    """أسبابٌ مشروعة (سنةٌ أخرى، تجميعٌ مختلف) — حجبُ تقريرٍ صحيحٍ ضررٌ لا نفع."""
    assert "evidence_body_numeric_divergence" not in Q.FAIL_TRIGGER_CHECKS
    assert "evidence_body_numeric_contradiction" in Q.FAIL_TRIGGER_CHECKS


def test_a_near_match_stays_silent():
    """تحت العتبة يغلب التقريبُ وبترُ الوحدات — لا ضجيج."""
    assert Q._check_evidence_body_numeric_consistency(
        _dr(10_000_000, 10.4)) == []


def test_the_warning_names_the_legitimate_explanations():
    """C9: التحذيرُ يقترح السببَ والفعل، لا يكتفي بالإبلاغ."""
    hits = Q._check_evidence_body_numeric_consistency(_dr(10_000_000, 25))
    note = " ".join(h["note"] for h in hits)
    assert "سنة" in note and "تجميع" in note, "التحذيرُ بلا سببٍ محتمل"
    assert "وحّدهما" in note or "اذكر" in note, "التحذيرُ بلا فعلٍ مطلوب"
