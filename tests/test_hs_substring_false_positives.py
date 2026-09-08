"""عائلة `substring-false-positive` — جذرٌ قصير داخل كلمةٍ لا علاقة لها.

البند ٨/٢٦ من أمر الموجة. العيبُ البنيويّ: `if keyword in product` يَعُدّ
التصادمَ الحرفيّ دليلَ تصنيف، والعربيةُ مليئةٌ بجذورٍ ثلاثية تقع داخل كلماتٍ
بعيدةٍ تماماً:

    «رقي»   (بطيخ، لهجةً)  ⊂  «ورقية»   (من الورق)   ⇒ مناديل ⇒ بطيخ  @0.875
    «طحين»  (دقيق قمح)     ⊂  «طحينية»  (من السمسم)  ⇒ حلاوة  ⇒ دقيق  @0.88
    «بن»    (قهوة)         ⊂  «بنكهة»                ⇒ أيُّ منكَّهٍ ⇒ بنّ

القاعدةُ المُنفَّذة هنا: **الدليلُ يُقاس على وحداتٍ كاملة (tokens)، لا على
سلاسلَ حرفية**. لا تُغلَق هذه العائلة بإضافة مفاتيحَ للصفوف المتصادمة — تلك
معالجةُ حادثةٍ لا إغلاقُ عائلة (الدرس ٢٠٥ حرفياً).

Locks the token-boundary rule: a short root inside an unrelated word is never
classification evidence, for any row in the reference — not just the two rows
whose collisions were reported.
"""
import pytest

import silk_hs_confirm as HC
import silk_hs_norm as N
import silk_hs_pipeline as P
from silk_hs_resolver import load_hs_codes, resolve, resolve_all

_WATERMELON = "080711"
_FLOUR = "110100"
_CONFECTIONERY = "170490"
_PREPARED_SEEDS = "200819"


# ═══════════ ١ — الحادثتان المرصودتان حرفياً ══════════════════════════════════
@pytest.mark.parametrize("name", ["مناديل ورقية", "منديل ورقي", "مناديل ورقيه",
                                  "ورق تواليت", "أكياس ورقية"])
def test_paper_products_never_become_watermelons(name):
    """«رقي» ⊂ «ورقية» لا يصنّف ورقاً بطيخاً — القياسُ الحيّ الذي أسّس البند."""
    dp = resolve(name)
    assert dp.value != _WATERMELON, (name, dp.value, dp.confidence)
    assert _WATERMELON not in [d.value for d in resolve_all(name, top_n=5)], name
    out = P.classify(name)
    assert out["final_hs_code"] != _WATERMELON, (name, out)


@pytest.mark.parametrize("name", ["حلاوة طحينية", "حلاوة طحينية سادة", "طحينة",
                                  "حلاوه طحينيه", "طحينة سمسم"])
def test_tahini_family_never_becomes_wheat_flour(name):
    """«طحين» ⊂ «طحينية» لا يصنّف الحلاوةَ دقيقَ قمح — لا في النتيجة ولا مرشّحاً.

    القفلُ السابق (`test_hs_halva_brandname_gap`) اختبر تهجئةً واحدة فقط
    («حلاوة طحينية سادة») بينما الإنتاج يستقبل المجرّدة — فبقي 110100 مرشّحاً
    بثقة 0.88 فوق العتبة. هنا كلُّ التهجئات.
    """
    values = [d.value for d in resolve_all(name, top_n=5)]
    assert _FLOUR not in values, (name, values)
    out = P.classify(name)
    assert out["final_hs_code"] != _FLOUR, (name, out)
    assert _FLOUR not in [c["hs6"] for c in out["candidate_codes"] if c.get("offer")]


# ═══════════ ٢ — القاعدة نفسها، لا الحادثتان ═════════════════════════════════
def test_containment_alone_is_never_evidence_anywhere_in_the_reference():
    """قفلُ **تغطية**: لا صفَّ في المرجع يفوز باحتواءٍ عبر حدود الوحدات.

    مصنوعٌ من المرجع نفسه لا من قائمةِ حالات: لكلّ مفتاحٍ عربيٍّ قصير نبني
    استعلاماً يحتويه حرفياً داخل كلمةٍ أطول، ونؤكّد أنه لا يُحسَم. فحصٌ
    حتميّ صرف — صفر شبكة، صفر نداء نموذج.
    """
    rows = load_hs_codes()
    probes = 0
    for row in rows:
        for kw in (row.get("keywords_ar") or "").split(";"):
            kw = N.normalize(kw)
            # جذورٌ عربيةٌ قصيرة أحاديةُ الوحدة هي وحدها موضعُ الخطر.
            if not kw or " " in kw or len(kw) > 5 or not N.is_arabic(kw):
                continue
            probes += 1
            # كلمةٌ أطول تحتوي المفتاحَ حرفياً لكنها ليست هو.
            fabricated = "س" + kw + "ية"
            score = HC._covered(fabricated, [kw])
            assert score is False, (row["hs_code"], kw, fabricated)
    assert probes > 30, f"probe set too small to be a guard: {probes}"


def test_token_equality_is_what_counts_not_string_containment():
    """`_covered` صار حكماً على وحداتٍ كاملة — تطابقٌ تامّ يمرّ، احتواءٌ لا."""
    assert HC._covered("حليب", ["حليب", "قشطه"]) is True
    assert HC._covered("رقي", ["رقي"]) is True
    assert HC._covered("ورقيه", ["رقي"]) is False
    assert HC._covered("طحينيه", ["طحين"]) is False
    assert HC._covered("بنكهه", ["بن"]) is False


def test_the_semantic_gate_no_longer_confirms_paper_as_watermelon():
    """بوّابةُ التطابق الدلالي كانت **توافق** على الخطأ (overlap 0.5)."""
    conf = HC.confirm_hs("مناديل ورقية", _WATERMELON)
    assert conf["confirmed"] is not True, conf


# ═══════════ ٣ — لا انهيار للمفاهيم المتجاورة (البند ٢٦) ═════════════════════
def test_sesame_tahini_and_halva_stay_three_distinct_things():
    """«سمسم» ≠ «طحينة» ≠ «حلاوة طحينية» — تداخلُ الحروف لا يوحّد المفاهيم."""
    sesame = P.classify("سمسم")
    tahini = P.classify("طحينة")
    halva = P.classify("حلاوة طحينية")
    assert tahini["final_hs_code"] == _PREPARED_SEEDS, tahini
    assert halva["final_hs_code"] == _CONFECTIONERY, halva
    assert tahini["final_hs_code"] != halva["final_hs_code"]
    # البذرةُ الخام لا يحملها المرجعُ بالعربية ⇒ تُسأل ولا تُلحَق بأيٍّ منهما.
    assert sesame["final_hs_code"] is None, sesame
    assert sesame["classification_status"] == "requires_confirmation", sesame


def test_peanut_butter_stays_out_of_the_dairy_chapter():
    """حادثةُ التأسيس (تدقيق المالك): «زبدة» ⊂ «زبدة الفول السوداني»."""
    out = P.classify("زبدة الفول السوداني")
    assert out["final_hs_code"] == "200811", out
    assert out["final_hs_code"] != "040510"
    plain = P.classify("زبدة")
    assert plain["final_hs_code"] == "040510", plain
