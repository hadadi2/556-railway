"""الموجة C · T-13 وT-14 — حارسان كانا **يبدوان قائمَين وهما لا يعملان**.

> **T-13** (`docs/ENGINE_AUDIT.md` §٤-ط): WP-3 يعلن خفضَ رتبة الدليل درجةً حين
> يجمعه وكيلُ بحثٍ ما لم يُعزَّز — والسقفُ يقرأ وسمَ «(Claude tool-use)» داخل
> `source`. لكنّ **الموجة B أزالت ذلك الوسم** حين صار `source` هو المصدرَ
> العموميَّ الحقيقيّ. فبقي السقفُ خامداً بلا أن يُحذَف.
>
> **T-14:** `tag_indicative_estimate` معرَّفٌ ولا مُنادىً — فالمسارُ الشرعيّ
> **الوحيد** لعدّ رقمٍ مشتقٍّ بلا مصدرٍ مباشر «مسنوداً» ميّت. والنتيجةُ إمّا
> احتسابُ رقمٍ منمذَجٍ مسنوداً بلا حقّ، أو رفضُه وهو مشروعٌ معلَنُ المعادلة.

**والدرسُ المشترك:** حارسٌ يبدو قائماً وهو لا يعمل أسوأُ من حارسٍ محذوف —
المحذوفُ يُرى في المراجعة، والخامدُ يُحتَجّ به.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_research                                    # noqa: E402
from silk_data_layer import DataPoint                   # noqa: E402
from silk_narrative import evidence_badge_for, is_agent_gathered  # noqa: E402
from silk_source_coverage import (INDICATIVE_ESTIMATE_TAG,  # noqa: E402
                                  _is_backed)


# ── T-13 · سقفُ الرتبة يستيقظ بإشارةٍ بنيوية ────────────────────────────

def test_the_legacy_textual_mark_still_counts():
    """تكافؤٌ رجعيّ: السجلّاتُ المخزَّنة قبل الموجة تبقى مقروءة."""
    assert is_agent_gathered("X (Claude tool-use)") is True


def test_the_structural_signal_now_counts_too():
    assert is_agent_gathered("UN Comtrade", "llm_web") is True
    assert is_agent_gathered("UN Comtrade", "mission_label_fallback") is True


def test_a_deterministic_retrieval_is_not_agent_gathered():
    """ما جاء من واجهةٍ رسمية أو من المخزن ليس جمعَ وكيل — فلا يُسقَف."""
    assert is_agent_gathered("UN Comtrade", "api") is False
    assert is_agent_gathered("World Bank", "store") is False


def test_an_agent_gathered_point_is_capped_one_rank_down():
    api = DataPoint(5, "UN Comtrade", 0.9, "n", "", retrieval_method="api")
    web = DataPoint(5, "UN Comtrade", 0.9, "n", "", retrieval_method="llm_web")
    assert evidence_badge_for(api).startswith("✓")
    assert evidence_badge_for(web).startswith("◐"), (
        "سقفُ الرتبة ما يزال خامداً — يبدو قائماً ولا يعمل (T-13)")


def test_corroboration_lifts_the_cap():
    """رصدٌ مباشرٌ من جامعٍ رسميّ يرفع السقف — القاعدةُ القائمة كما هي."""
    f = {"confidence": 0.9, "source": "UN Comtrade",
         "retrieval_method": "llm_web", "corroborated": True}
    assert evidence_badge_for(f).startswith("✓")


def test_the_producer_emits_the_structural_signal():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_llm_runtime.py"),
        encoding="utf-8").read()
    assert '"llm_web" if pub_sources' in src, (
        "المنتِجُ لا يسجّل طريقةَ الاسترجاع — السقفُ بلا إشارة (T-13)")


# ── T-14 · وسمُ التقدير الاسترشاديّ يُنادى فعلاً ─────────────────────────

def test_the_indicative_tag_is_applied_at_its_producer():
    note = silk_research._indicative("مُقدَّر — نموذج بافتراضات معلنة",
                                     "SAM = TAM × 0.3")
    assert INDICATIVE_ESTIMATE_TAG in note
    assert "SAM = TAM × 0.3" in note, "الوسمُ بلا اشتقاقه لا يفيد"


def test_a_tagged_estimate_counts_as_backed():
    """المسارُ الشرعيّ الوحيد صار حيّاً — رقمٌ مشتقٌّ معلَنُ المعادلة يُحتسَب."""
    note = silk_research._indicative("مُقدَّر", "SOM = SAM × 0.2")
    assert _is_backed("", note) is True


def test_an_untagged_estimate_is_not_backed():
    """والعكسُ محفوظ: «مُقدَّر» وحدَها ليست سنداً."""
    assert _is_backed("", "مُقدَّر — نموذج") is False


def test_the_modeled_sizing_values_carry_the_tag():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_research.py"),
        encoding="utf-8").read()
    assert src.count("note=_indicative(") >= 2, (
        "قيمُ التحجيم المنمذجة لا تحمل وسمَ التقدير (T-14)")


def test_the_tagger_failure_never_breaks_production():
    """الوسمُ تحسينٌ لا شرطُ إنتاج — عطلُه يعيد الملاحظةَ كما هي."""
    assert silk_research._indicative("ملاحظة", "") .startswith("ملاحظة")
