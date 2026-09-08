"""عائلة `generic-term-on-a-specific-sibling` — مقياسٌ مُرصَد لا إصلاحُ حادثة.

> **الاكتشاف (توسيعُ المجموعة الذهبية على سلّةٍ تصديرية حقيقية، 2026-08-30).**
> «سجاد» تُحلّ إلى `570110` — *سجادٌ **معقود** من صوف* — بثقة ١٫٠٠. والترويسةُ
> 5701 وحدها تنقسم إلى بنودٍ عدّة، وبقيةُ الفصل ٥٧ تحمل المنسوج والمنتوف
> واللبّاد. أيّ سجادٍ آليٍّ من بولي بروبيلين بندُه ٥٧٠٣ لا ٥٧٠١١٠.
>
> الآليةُ **جديدة** ولا علاقة لها بعائلة `substring-false-positive`: لا تصادمَ
> حرفياً هنا، بل مصطلحٌ عربيٌّ **عامّ** موضوعٌ على بندٍ **خاصّ** داخل ترويسةٍ
> منقسمة، وإخوتُه بلا مفاتيحَ عربية فلا يستطيع أحدٌ منافستَه — فتمرّ بوّابةُ
> الفصل عن الثاني (`min_separation`) لأنه **لا ثانيَ أصلاً**.

المسحُ يجد **٥٢** حالة. أسوأها بعدد الإخوة الذين يتخطّاهم المصطلحُ صامتاً:

    «سمك»   ⇒ 030289 (سمكٌ طازج n.e.c.)      يتخطّى ٤٥ بنداً
    «تونة»  ⇒ 030487 (شرائح تونة **مجمّدة**)  يتخطّى ٤٨ بنداً
    «جمبري» ⇒ 030617 (قريدسٌ **مجمّد**)       يتخطّى ٢٠ بنداً
    «دجاج»  ⇒ 020714 (قطعٌ **مجمّدة**)        يتخطّى ١٩ بنداً
    «سماد»  ⇒ 310210 (يوريا تحديداً)          يتخطّى  ٩ بنداً

ليست كلُّها خطأً: «حلاوة» ⇒ 170490 سليمةٌ لأن الترويسة ١٧٠٤ تنقسم إلى «علكة»
و«غيرها» فقط. فالحكمُ **قرارُ سياسةٍ لكل سلعة** لا كنسٌ آليّ — ولذلك يُقاس هنا
ويُقفَل على ألّا ينمو، ويُترَك تقليمُه لقرارِ المالك (لا يجوز أن يُعدَّل ٥٢ صفّاً
من بيانات مُحكَّمة بحكمٍ ذاتيّ).

**ما يقفله هذا الملفّ:** العددُ لا يزيد، وأسوأُ الحالات المرصودة تبقى مرصودة.
تقليمُ أيّ صفّ يُنقِص العدد ⇒ يُحدَّث الأساس نزولاً، وهو الاتجاه الوحيد المسموح.
"""
import collections
import csv
import os

import pytest

import silk_hs_norm as N
import silk_hs_pipeline as P

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# الأساسُ المرصود وقت الاكتشاف. **سقفٌ لا هدف**: ينزل بالتقليم ولا يرتفع أبداً.
_BASELINE = 52

# أسوأُ الحالات — مصطلحٌ عامٌّ يتخطّى ≥١٩ بنداً شقيقاً بلا منافس. تبقى مرصودةً
# باسمها كي لا يختفي أخطرُها داخل عدٍّ إجماليّ ينزل لأسبابٍ أخرى.
_WORST = {"سمك", "تونة", "تونا", "جمبري", "روبيان", "قريدس", "دجاج",
          "حبار", "سبيط", "ميثانول"}


def _reference() -> list[dict]:
    p = os.path.join(_ROOT, "data", "hscodes_full.csv")
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _generic_overreach() -> list[tuple]:
    """(عددُ الإخوة، المصطلح، الرمز) لكل مصطلحٍ عامٍّ يحسم بندًا خاصًّا بلا منافس."""
    rows = _reference()
    by_heading = collections.defaultdict(list)
    for r in rows:
        by_heading[r["hs_code"][:4]].append(r)

    found = []
    for r in rows:
        siblings = by_heading[r["hs_code"][:4]]
        if len(siblings) < 2:
            continue        # ترويسةٌ ببندٍ واحد — لا خصوصيةَ تُفقَد
        keyed = [s for s in siblings if (s.get("keywords_ar") or "").strip()]
        if len(keyed) != 1:
            continue        # لأخيه مفاتيح ⇒ بوّابةُ الفصل عن الثاني تلتقطه
        for kw in (r.get("keywords_ar") or "").split(";"):
            kw = kw.strip()
            if not kw or not N.is_arabic(kw) or len(N.tokens(kw)) != 1:
                continue    # المصطلحُ المركّب («سجاد صوف معقود») خاصٌّ لا عامّ
            out = P.classify(kw)
            if (out["classification_status"] == P.APPROVED
                    and out["final_hs_code"] == r["hs_code"]):
                found.append((len(siblings), kw, r["hs_code"]))
    return sorted(found, reverse=True)


@pytest.fixture(scope="module")
def overreach():
    return _generic_overreach()


def test_the_family_never_grows(overreach):
    """قفلُ التغطية: مفتاحٌ عامٌّ جديد على بندٍ خاصّ يُحمِّر السويت فوراً.

    لا تُرفَع القيمةُ لتمرير إضافةٍ جديدة — الإضافةُ نفسُها هي العيب. النزولُ
    وحده مسموح (بعد تقليمٍ مقصود)، ويُحدَّث الأساسُ حينها.
    """
    assert len(overreach) <= _BASELINE, (
        f"نمت العائلة إلى {len(overreach)} (الأساس {_BASELINE}): "
        + ", ".join(f"«{k}»⇒{c}" for _, k, c in overreach[:6]))


def test_the_worst_cases_stay_visible(overreach):
    """أخطرُها لا يختفي داخل عدٍّ إجماليّ — كلٌّ منها يتخطّى ≥١٩ بنداً شقيقاً."""
    seen = {k for n, k, _ in overreach if n >= 19}
    missing = _WORST - seen
    # اختفاءُ حالةٍ مقصودٌ بعد تقليمها — لكن يجب أن يكون **تقليماً**، أي أن
    # المصطلحَ لم يعد يُحسَم تلقائياً، لا أنه انتقل لبندٍ خاصٍّ آخر بصمت.
    for term in sorted(missing):
        out = P.classify(term)
        assert out["classification_status"] != P.APPROVED, (
            f"«{term}» خرج من الرصد لكنه ما زال يُحسَم تلقائياً إلى "
            f"{out['final_hs_code']} — انتقلَ العيبُ ولم يُقلَّم")


def test_a_specific_product_name_is_unaffected():
    """العيبُ في المصطلح العامّ وحده: الاسمُ المُحدَّد يبقى صحيحاً ومقبولاً.

    «روبيان مجمد» يصف المجمّد صراحةً فـ030617 صحيحٌ له؛ العيبُ أن «روبيان»
    وحدها تُحلّ إليه أيضاً. هذا يمنع «الإصلاح» بحذف المفاتيح المركّبة.
    """
    for name, code in (("روبيان مجمد", "030617"),
                       ("ألمنيوم خام", "760110"),
                       ("ألواح ألمنيوم", "760611")):
        out = P.classify(name)
        assert out["classification_status"] == P.APPROVED, (name, out["reason"])
        assert out["final_hs_code"] == code, (name, out["final_hs_code"])


def test_the_detector_is_load_bearing(overreach):
    """حارسُ الحارس: كاشفٌ يعيد صفراً يجعل كلَّ ما فوقه أخضرَ كذباً."""
    assert len(overreach) > 10, len(overreach)
    assert any(n >= 40 for n, _, _ in overreach), "الكاشفُ لا يرى أسوأ الحالات"
