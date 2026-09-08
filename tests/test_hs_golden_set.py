"""مجموعة التصنيف الذهبية — قفلُ دقّةٍ على حدّ «المنتج ← HS6».

البند ١٤/١٥/٢٦ من أمر الموجة: مجموعةٌ مصانةٌ من منتجاتٍ حقيقية، توقّعاتُها
**مشتقّةٌ من المرجع الرسمي** لا مخترَعة (`evals/hs_golden_set.csv` يحمل عمود
`evidence` لكل صف). القفلان اللذان لا يجوز أن ينكسرا:

1. **لا إيجابيةٌ كاذبة.** رمزٌ في `forbidden_hs6` لا يجوز أن يظهر مرشّحاً
   مقبولاً ولا رمزاً نهائياً — هذه عائلة «مناديل ورقية ⇒ بطيخ».
2. **لا تخمين.** منتجٌ لا يحمله المرجعُ بالعربية يعود `requires_confirmation`
   لا «أفضل مرشّح» صامتاً (عقد عدم الاختلاق).

The golden set locks accuracy at the Product → HS6 boundary: no false positive
may reach the decision, and anything the reference cannot support in Arabic must
ask rather than guess.
"""
import csv
import os

import pytest

import silk_hs_pipeline as P

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GOLDEN = os.path.join(_ROOT, "evals", "hs_golden_set.csv")


def _rows() -> list[dict]:
    """صفوفُ المجموعة الذهبية — التعليقاتُ (#) تُسقَط قبل القراءة."""
    with open(_GOLDEN, encoding="utf-8") as f:
        body = [ln for ln in f if not ln.lstrip().startswith("#")]
    return [r for r in csv.DictReader(body) if (r.get("product") or "").strip()]


GOLDEN = _rows()
IDS = [r["product"] for r in GOLDEN]


def test_the_golden_set_is_actually_loaded():
    """حارسُ الحارس: ملفٌّ فارغ/متعذّر القراءة يجعل كل ما تحته أخضرَ كذباً."""
    assert len(GOLDEN) >= 24, len(GOLDEN)
    for r in GOLDEN:
        assert r["expect_status"] in ("approved", "requires_confirmation"), r
        assert (r.get("evidence") or "").strip(), r


@pytest.mark.parametrize("row", GOLDEN, ids=IDS)
def test_no_forbidden_code_ever_survives_to_the_decision(row):
    """القفلُ الأهمّ: الرمزُ الممنوع لا يصير نهائياً ولا مرشّحاً مقبولاً.

    الممنوعُ هنا ليس رأياً — كلُّ صفٍّ منها عيبٌ مرصودٌ فعلاً أو تصادمٌ لفظيّ
    مُثبَت (بطيخ/ورقية، طحين/طحينية، زبدة/زبدة الفول السوداني).
    """
    forbidden = [c for c in (row.get("forbidden_hs6") or "").split(";") if c.strip()]
    if not forbidden:
        pytest.skip("no forbidden codes declared for this product")
    out = P.classify(row["product"])
    assert out["final_hs_code"] not in forbidden, (
        row["product"], out["final_hs_code"], out["classification_status"])
    # ولا **مؤهَّلاً للاعتماد التلقائي**: مرشّحٌ بلا تناقضٍ فوق العتبة يُعتمَد
    # بنقرةٍ واحدة، فوجودُه في تلك الدائرة يساوي وجودَه في النتيجة (بلاغ دقيق
    # القمح 2026-08-29). أمّا اقتراحٌ أضعفُ يُعرَض للاختيار فمشروع: المصنعُ
    # يرى بدائلَ ويقرّر — ذلك عينُ ما تطلبه شاشةُ التأكيد.
    eligible = [c["hs6"] for c in out["candidate_codes"]
                if c.get("offer") and c["score"] >= P.min_confidence()]
    assert not (set(eligible) & set(forbidden)), (
        row["product"], eligible, forbidden)


@pytest.mark.parametrize("row", GOLDEN, ids=IDS)
def test_expected_status_and_code(row):
    """الحالةُ المتوقَّعة تقع، والرمزُ المتوقَّع (إن وُجد) هو النهائي."""
    out = P.classify(row["product"])
    assert out["classification_status"] == row["expect_status"], (
        row["product"], out["classification_status"], out.get("reason"))
    expected = (row.get("expect_hs6") or "").strip()
    if expected:
        assert out["final_hs_code"] == expected, (row["product"], out)
    else:
        # لا رمزَ متوقَّعاً ⇒ لا رمزَ نهائيّاً يُبنى عليه إنفاق.
        assert out["final_hs_code"] is None, (row["product"], out)


@pytest.mark.parametrize("row", GOLDEN, ids=IDS)
def test_confidence_is_numeric_or_explicitly_unresolved(row):
    """البند ٤: الثقةُ رقمٌ أو حالةُ عدم حسمٍ معلنة — لا `None` صامتة.

    `approved` تشترط رقماً فوق العتبة؛ `requires_confirmation` تشترط رقماً
    أيضاً (قد يكون 0.0) كي يقرأ المشغّلُ **كم** نقص لا «غير معلومة».
    """
    out = P.classify(row["product"])
    conf = out["confidence"]
    assert isinstance(conf, float), (row["product"], conf)
    assert 0.0 <= conf <= 1.0, (row["product"], conf)
    if out["classification_status"] == "approved":
        assert conf >= P.min_confidence(), (row["product"], conf)


def test_the_set_covers_both_outcomes():
    """مجموعةٌ كلُّها «مقبول» لا تقيس شيئاً — والعكس كذلك."""
    statuses = {r["expect_status"] for r in GOLDEN}
    assert statuses == {"approved", "requires_confirmation"}, statuses


def test_accuracy_floor_is_reported_and_held():
    """أرضيّةُ دقّةٍ مُعلَنة: القرارُ الصحيح على كل صفٍّ من صفوف المجموعة.

    رقمٌ واحد يُقاس في CI بدل «تحسّن الإحساس» — انحدارُه يُحمِّر السويت
    (البند ٣ من خطة الإصلاح: مصدرُ حقيقةٍ واحد **مقيس**).
    """
    correct = 0
    for row in GOLDEN:
        out = P.classify(row["product"])
        want_code = (row.get("expect_hs6") or "").strip() or None
        if (out["classification_status"] == row["expect_status"]
                and out["final_hs_code"] == want_code):
            correct += 1
    ratio = correct / len(GOLDEN)
    assert ratio == 1.0, f"golden-set accuracy {ratio:.2%} ({correct}/{len(GOLDEN)})"
