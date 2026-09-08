"""الموجة C · C1 — البوّاباتُ التنظيمية **حتميّةٌ** لا تعليماتٌ لنموذج.

> **الفجوة التي تُغلقها** (`docs/ENGINE_AUDIT.md` §٥): مرجعُ الاشتراطات كان
> يحمل بنوداً **بلا درجةِ حجب**، والحالةُ «الصلبة» الوحيدة مُرمَّزةً صلباً في
> الشيفرة لصفٍّ واحد — وأثرُها **تعليقُ ملاحظة** (`conditional=True`) لا منعُ
> حكم. فحتى بوّابةُ الاتحاد الأوروبي 2017/625، وهي المثالُ الذي سمّاه المالك،
> كانت **ملاحظةً لا بوّابة**: لا شيء يمنع حكماً إيجابياً بينما المنشأةُ غيرُ
> مُدرَجة.
>
> الآن الدرجةُ **بيانٌ في المدوّنة** (`blocking`) ومحدِّدُ الانطباق بيانٌ آخر
> (`applies_when`)، والمحرّكُ يقرؤهما بلا مطابقةِ عبارات.

**والقيدُ الأهمّ المقفول هنا:** ما لا يُعرَف انطباقُه من رمز HS **لا يُعَدّ
حاجزاً مؤكَّداً ولا يُعَدّ سالكاً** — يُصرَّح به «يحتاج تحقّقاً». عدُّه حاجزاً
كان سيحجب كلّ تقريرٍ أوروبيّ (بند «الغذاء الجديد» لا يُحسَم من الفصل)، وعدُّه
سالكاً كان ادّعاءَ سلامةٍ لم يُرصَد.
"""
from __future__ import annotations

import csv
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_i18n                                    # noqa: E402
import silk_reports                                 # noqa: E402
import silk_requirements_agent as R                 # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── (١) المدوّنة تحمل الحجب ومحدِّدَ الانطباق ────────────────────────────

def test_reference_carries_blocking_and_applies_columns():
    """العمودان موجودان على **كلّ** صفّ — لا صفَّ بلا درجةٍ معلومة."""
    with io.open(os.path.join(_ROOT, "data", "requirements_l1.csv"),
                 encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "مرجعُ الاشتراطات فارغ"
    for r in rows:
        assert "blocking" in r and "applies_when" in r, (
            "صفٌّ بلا عمودَي الحجب/الانطباق — عادت الدرجةُ ترميزاً صلباً")
        assert R.blocking_level(r) in (
            R.BLOCKING_HARD, R.BLOCKING_CONDITIONAL, R.BLOCKING_PROCEDURAL)


def test_unknown_blocking_value_degrades_to_the_weakest_level():
    """قيمةٌ غيرُ معلومة ⇒ `procedural` — لا حاجزٌ صامتٌ من خطأٍ إملائيّ."""
    assert R.blocking_level({"blocking": "HARD"}) == R.BLOCKING_HARD
    assert R.blocking_level({"blocking": "typo"}) == R.BLOCKING_PROCEDURAL
    assert R.blocking_level({}) == R.BLOCKING_PROCEDURAL


# ── (٢) محدِّدُ الانطباق حتميٌّ بثلاث حالاتٍ لا حالتين ────────────────────

def test_applies_to_is_deterministic_and_has_a_third_state():
    row_meat = {"applies_when": "hs_chapter:02,04,16"}
    assert R.applies_to(row_meat, "020130", "food") is True
    assert R.applies_to(row_meat, "080410", "food") is False
    # بلا رمزٍ لا يُخمَّن الانطباق.
    assert R.applies_to(row_meat, None, "food") is None
    # ما يحتاج دليلاً خارجياً يُصرَّح به `None` صراحةً.
    assert R.applies_to({"applies_when": "needs_evidence"}, "080410",
                        "food") is None
    # فارغٌ = ينطبق كلّما طابق الصفّ.
    assert R.applies_to({"applies_when": ""}, "080410", "food") is True
    # محدِّدٌ غيرُ معروف لا يُقرأ «ينطبق».
    assert R.applies_to({"applies_when": "moon_phase:full"}, "080410",
                        "food") is None


# ── (٣) مثالُ المالك: EU 2017/625 ────────────────────────────────────────

def test_eu_establishment_listing_is_a_hard_blocker_for_animal_products():
    """منتجٌ حيوانيٌّ إلى الاتحاد ⇒ حاجزٌ صلبٌ مؤكَّدُ الانطباق."""
    blockers = R.regulatory_blockers("DEU", "020130")
    hard = R.open_hard_blockers(blockers)
    assert hard, "بوّابةُ 2017/625 عادت ملاحظةً لا حاجزاً"
    assert any("المنشأة" in (b["item"] or "") for b in hard), (
        "الحاجزُ الصلب ليس بندَ إدراج المنشأة")
    assert all(b["source_url"] for b in hard), "حاجزٌ بلا مصدرٍ مُستشهَد"


def test_a_non_animal_product_is_not_blocked_by_the_animal_gate():
    """تمورٌ إلى الاتحاد: بندُ إدراج المنشأة **لا ينطبق** فلا يُحجَب بلا سبب."""
    hard = R.open_hard_blockers(R.regulatory_blockers("DEU", "080410"))
    assert hard == [], f"حُجِبت تمورٌ ببندٍ حيوانيّ: {[b['item'] for b in hard]}"


def test_requirements_that_hs_cannot_settle_are_declared_not_assumed():
    """«الغذاء الجديد» و«حدود المتبقيات» تحتاجان دليلاً — لا منعاً ولا سلامة."""
    blockers = R.regulatory_blockers("DEU", "080410")
    need = R.unverified_blockers(blockers)
    assert need, "بنودٌ لا تُحسَم من رمز HS اختفت بدل أن تُعلَن"
    assert all(b["applies"] is None for b in need)
    # ولا واحدٌ منها يُعَدّ منعاً.
    assert not (set(id(b) for b in need)
                & set(id(b) for b in R.open_hard_blockers(blockers)))


def test_an_uncovered_market_yields_no_invented_blockers():
    """سوقٌ خارج تغطية المرجع لا تُختلَق له حواجز."""
    assert R.regulatory_blockers("KEN", "080410") == []


def test_resolved_is_never_fabricated_as_false():
    """`resolved` تبقى `None` — سِلك لا يرصد أنّ مصنعاً أنهى إدراجه."""
    for b in R.regulatory_blockers("DEU", "020130"):
        assert b["resolved"] is None, (
            "ادُّعي حسمُ حاجزٍ لم يُرصَد — خرقُ عقد عدم الاختلاق")


# ── (٤) الوكيل يبثّها بنيوياً ────────────────────────────────────────────

def test_state_is_a_structural_field_beside_the_checklist_not_inside_it():
    """الحالةُ حقلٌ مستقلّ — لا نقطةٌ محقونةٌ في `findings`.

    الحقنُ داخل القائمة كسر أربعةَ اختباراتٍ قائمة فوراً: `requirements`
    عقدُها الضمنيّ «كلُّ قيمةٍ بندُ تحقّقٍ باتجاه»، وشكلٌ غريبٌ فيها يُسقِط
    كلَّ مستهلِك. القفلُ هنا يمنع تكرارَ الحقن.
    """
    st = R.regulatory_state("DEU", "020130")
    assert set(st) == {"open_hard", "needs_verification", "all", "checked",
                       "access_timeline"}
    assert st["open_hard"], "الحاجزُ الصلب لم يصل المستهلِكين"
    rep = R.RequirementsAgent().run({"market_iso3": "DEU",
                                     "hs_code": "020130"})
    for dp in rep.findings:
        assert isinstance(dp.value, dict) is False or "direction" in dp.value, (
            "قيمةٌ بشكلٍ غريبٍ حُقِنت في قائمة الاشتراطات")


def test_checked_is_true_even_when_nothing_blocks():
    """«فُحِصت ولا حاجز» ≠ «لم تُفحَص» — الفرقُ بنيويٌّ لا صامت."""
    st = R.regulatory_state("DEU", "080410")
    assert st["checked"] is True and st["open_hard"] == []


def test_the_view_hoists_the_state_from_every_market_row():
    """سوقٌ محجوبٌ بجوار سوقٍ سالك لا يختفي في العرض."""
    import silk_render
    res = {"product": "لحوم", "hs_code": "020130", "markets": [
        {"iso3": "KEN", "regulatory": R.regulatory_state("KEN", "020130")},
        {"iso3": "DEU", "regulatory": R.regulatory_state("DEU", "020130")}]}
    view = silk_render.build_view(res, "ar")
    assert view["regulatory"]["open_hard"], "حاجزُ سوقٍ اختفى خلف سوقٍ سالك"
    # وغيابُ الحقل كلِّه يعني «لم تُفحَص»، لا «لا حاجز».
    assert silk_render._regulatory_state({"markets": [{"iso3": "DEU"}]}) == {}


def test_a_positive_verdict_over_an_open_hard_blocker_is_refused():
    """البوّابةُ الحاجزة: إيجابٌ + حاجزٌ مفتوح = رفضُ تسليم."""
    import silk_quality_gate
    assert "regulatory_hard_blocker_open" in silk_quality_gate.FAIL_TRIGGER_CHECKS
    view = {"regulatory": R.regulatory_state("DEU", "020130")}
    for verdict, blocked in (("GO", True), ("PRELIMINARY GO", True),
                             ("CONDITIONAL-GO", False), ("NO-GO", False),
                             ("WATCH", False)):
        view["deep_research"] = {"verdict": {"verdict": verdict}}
        hits = silk_quality_gate._check_regulatory_blocker(view)
        assert bool(hits) is blocked, f"«{verdict}» تصرّفت خطأً أمام الحاجز"
    # ولا حاجزَ ⇒ لا حجب، مهما كان الحكم إيجابياً.
    assert silk_quality_gate._check_regulatory_blocker(
        {"regulatory": R.regulatory_state("KEN", "020130"),
         "deep_research": {"verdict": {"verdict": "GO"}}}) == []


# ── (٥) C9 — ما يُقال للمصنع عن هذه الحالات يُقرأ بلغةِ أعمال ────────────

_REG_KEYS = ("reg_block_head", "reg_block_lead", "reg_block_why",
             "reg_block_impact", "reg_block_action", "reg_verify_head",
             "reg_verify_lead", "reg_verify_why", "reg_verify_impact",
             "reg_verify_action", "reg_clear_note")
_FMT = {"market": "الاتحاد الأوروبي", "authority": "الهيئة المختصة",
        "pct": "80", "year": "2023", "band": "متوسطة", "reason": "سبب",
        "missing": "تكلفة الوحدة", "formula": "الواردات ÷ السكان"}


@pytest.mark.parametrize("lang", ["ar", "en"])
def test_regulatory_messages_read_as_business_language(lang):
    """صفرُ لغةِ نظامٍ على سطح العميل — بالحارس القائم نفسه لا بحارسٍ ثانٍ."""
    for key in _REG_KEYS:
        text = silk_i18n.t(key, lang, **_FMT)
        hits = silk_reports._client_forbidden_hits(text, lang)
        assert hits == [], f"«{key}» بلغةِ نظام في «{lang}»: {hits[:2]}"


@pytest.mark.parametrize("lang", ["ar", "en"])
def test_regulatory_messages_carry_the_five_slots(lang):
    """خلاصة ← سبب ← دليل ← أثر ← فعل: كلُّ خانةٍ لها مفتاحُها الخاص."""
    for suffix in ("lead", "why", "impact", "action"):
        key = f"reg_block_{suffix}"
        assert key in silk_i18n.TERMS, f"خانةٌ مفقودة من البنية: {key}"
        assert silk_i18n.t(key, lang, **_FMT).strip(), f"{key} فارغ في {lang}"


def test_regulatory_messages_never_leak_an_internal_identifier():
    """لا `blocking=` ولا `seq=` ولا اسمُ مفتاحٍ داخليّ في نصِّ عميل."""
    import re
    leak = re.compile(r"(blocking\s*=|seq\s*=|regulatory_blockers|_v\d|"
                      r"\bNone\b|\bTrue\b|\bFalse\b)")
    for lang in ("ar", "en"):
        for key in _REG_KEYS:
            text = silk_i18n.t(key, lang, **_FMT)
            assert not leak.search(text), f"تسريبٌ داخليّ في «{key}» ({lang})"
