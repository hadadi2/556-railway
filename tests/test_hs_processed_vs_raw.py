"""المنتجُ المصنَّع لا يُحَلّ إلى الخام — بلاغ المالك «تحديد HS بدقة».

القياسُ الذي أسّس هذا الملفّ (direct reproduction، 2026-08-29): أربعةٌ من
أربعةِ منتجاتٍ مصنّعةٍ عاديّة كانت تُحَلّ إلى **الرمز الخام** بثقة 0.90
و`confirmed=True` — فوق عتبة البوّابة (0.80) وبمباركة بوّابة التطابق الدلالي:

    عصير برتقال  ⇒ 080510 (برتقال طازج)     مربى فراولة ⇒ 081010 (فراولة طازجة)
    شيبس بطاطس  ⇒ 070190 (بطاطس طازجة)     طماطم معلبة ⇒ 070200 (طماطم طازجة)

أي دراسةٌ كاملةٌ مدفوعة تُبنى على «برتقال طازج» لمصنع عصير، بصمتٍ تامّ.

السبب: `_covered` يَعُدّ صفةَ المنتج مغطّاةً إن احتواها أيُّ حدٍّ في وصف
الرمز، فاسمُ المادة وحده («برتقال») يبلغ التداخلَ الأدنى بينما الصفةُ
المُحوِّلة للحالة («عصير») تسقط بلا أثر — وهي بعينها الفارقُ بين الفصل ٨
والفصل ٢٠.

القاعدة: **صفةُ تصنيعٍ في الاسم بلا مقابلها في وصف رمزٍ خامٍّ معلَن ⇒ رمزٌ
غير مؤكَّد** (فجوةٌ معلنة تُسأل بمرشّحين، لا رمزٌ خاطئٌ واثق). والشرطُ الثالث
(«الرمز يعلن حالةً خاماً صراحةً») هو ما يمنع الرفضَ الكاذب.
"""
import silk_hs_confirm as C
from silk_hs_resolver import resolve

# (الاسم، الرمز الخام الذي كان يفوز)
_WAS_WRONG = [
    ("عصير برتقال", "080510"),
    ("شيبس بطاطس", "070190"),
    ("مربى فراولة", "081010"),
    ("طماطم معلبة", "070200"),
]

# منتجاتٌ صفتُها حاضرةٌ في وصف الرمز — يجب ألّا يمسّها الحارس.
_STILL_FINE = [
    ("تمور مجففة", "080410"),        # dates, fresh or **dried**
    ("فول سوداني محمص", "200811"),   # ground-nuts, **prepared**
    ("دجاج مجمد", "020714"),         # fowls, cuts, **frozen**
    ("زيت زيتون بكر", "150910"),
    ("عسل سدر", "040900"),
]


# ═══════════ ١ — لا رمزَ خامٍّ واثقٍ لمنتجٍ مصنَّع ═════════════════════════════
def test_a_processed_product_never_resolves_to_the_raw_code():
    for name, raw_code in _WAS_WRONG:
        dp = resolve(name)
        assert dp.value != raw_code, (name, dp.value, dp.confidence)
        # فجوةٌ معلنة لا رمزٌ بديل مخمَّن (عقد عدم الاختلاق).
        assert dp.value is None and dp.confidence == 0.0, (name, dp.value)


def test_the_confirmation_gate_no_longer_endorses_the_raw_code():
    """كان `confirmed=True` — وهو ما جعل الخطأ يمرّ فوق كلّ البوّابات."""
    for name, raw_code in _WAS_WRONG:
        conf = C.confirm_hs(name, raw_code)
        assert conf["confirmed"] is False, (name, conf)
        assert "صفةَ تصنيع" in conf["reason"], conf["reason"]


def test_legitimate_matches_are_not_falsely_refused():
    """الشرطُ الثالث يحمي المشروع: المقابلُ حاضرٌ في الوصف فيمرّ."""
    for name, code in _STILL_FINE:
        dp = resolve(name)
        assert dp.value == code, (name, dp.value, dp.note[:60])
        assert dp.confidence >= 0.8, (name, dp.confidence)


def test_the_guard_needs_an_explicit_raw_state_in_the_description():
    """رمزٌ صامتٌ عن حالته لا يُرفَض بالظنّ — لا حجبَ بلا دليلٍ في النصّ."""
    assert C._process_state_conflict(["عصير", "برتقال"], "Fruit juices") is None
    assert C._process_state_conflict(
        ["عصير", "برتقال"], "Oranges, prepared") is None
    assert C._process_state_conflict(
        ["عصير", "برتقال"], "Oranges, fresh or dried") is not None


def test_the_guard_covers_the_free_description_path_too():
    """نفسُ الحارس على `confirm_against_description` — لا إصلاحَ على مسارٍ واحد."""
    out = C.confirm_against_description(
        "عصير برتقال", "080510", "Fruit, edible; oranges, fresh")
    assert out["confirmed"] is False, out
    assert "صفةَ تصنيع" in out["reason"]


def test_the_lexicon_carries_no_product_or_code_literal():
    """قاعدةٌ عامّة لا حالةُ منتج: معجمُ حالاتٍ صرف، صفر رمزِ HS أو اسم منتج."""
    import re
    for names, markers in C._PROCESS_STATES:
        for w in tuple(names) + tuple(markers):
            assert not re.fullmatch(r"\d{4,6}", w), w
    joined = " ".join(w for n, m in C._PROCESS_STATES for w in tuple(n) + tuple(m))
    for product_word in ("برتقال", "بطاطس", "فراولة", "طماطم", "تمر"):
        assert product_word not in joined, product_word


# ═══════════ ٢ — انحدارُ الدقّة العامّة لا يتراجع ═════════════════════════════
_SAMPLE = ["تمور مجففة", "عسل سدر", "زيت زيتون بكر", "عصير برتقال",
           "شيبس بطاطس", "معكرونة", "شوكولاتة بالحليب", "جبن شيدر",
           "لبن زبادي", "دجاج مجمد", "قهوة مطحونة", "بهارات مشكلة",
           "ماء معدني", "صابون سائل", "شامبو", "عبايات نسائية",
           "كرتون تعبئة", "أنابيب بلاستيك", "أسمنت", "تمر مكنوز"]


def test_confident_resolution_rate_does_not_regress():
    """قِيس قبل الحارس: ١٣/٢٠ محسوماً بثقة ≥0.80 — أربعةٌ منها **خاطئة**.

    الحارسُ يُحوّل الأربعة الخاطئة إلى فجواتٍ معلنة، فالنسبةُ تنزل إلى ٩/٢٠
    **عمداً**: رمزٌ خاطئٌ واثق أسوأ من فجوةٍ معلنة تُسأل بمرشّحين. القفلُ
    يمنع النزولَ تحت ذلك (انحدارُ تغطيةٍ حقيقيّ) والصعودَ بلا قرار.
    """
    ok = [n for n in _SAMPLE
          if (lambda d: d.value and d.confidence >= C.min_confidence())(
              resolve(n))]
    assert len(ok) >= 9, sorted(set(_SAMPLE) - set(ok))
    for wrong, _ in _WAS_WRONG:
        assert wrong not in ok, wrong


# ═══════════ ٣ — مقياسُ التغطية يرى الملفّ الحيّ ═════════════════════════════
def test_seed_coverage_reads_the_live_reference_not_the_retired_seed():
    """أداةُ قياسٍ لا ترى ما تقيسه تُطمئِن كذباً — كانت تعيد صفراً."""
    cov = C.seed_coverage()
    assert cov["total"] > 5000
    assert cov["arabic_guarded"] > 0, (
        "مقياسُ التغطية أعمى عن `keywords_ar` — عاد يقرأ أعمدةَ البذرة المتروكة")
    assert cov["arabic_guarded"] + cov["supply_only"] == cov["total"]


# ═══════════ ٤ — ما التقطته المراجعة الذاتية على هذا الحارس نفسه ═════════════
def test_raw_state_words_never_match_inside_a_longer_word():
    """«live» داخل `olives`/`livers` و«حي» داخل «حيوانية» كانت تُفعِّل الشرط.

    نفسُ فخّ الاحتواء الذي وثّقه `_MIN_CONTAINMENT_LEN` في الملفّ نفسه —
    والحارسُ الجديد كان يتجاوزه فيرفض **محضّرات** مشروعة.
    """
    assert C.confirm_hs("زيتون مطحون", "200570")["confirmed"] is not False
    assert C._process_state_conflict(
        C._tokens("علف مركز"), "أعلاف حيوانية محضّرة") is None
    assert C._process_state_conflict(
        C._tokens("كبد مطحون"), "Livers, prepared") is None


def test_a_second_processing_qualifier_is_still_checked():
    """صفةٌ أولى مغطّاة لا تُسكِت الثانية («برتقال مجفف مركز»)."""
    assert C._process_state_conflict(
        C._tokens("برتقال مجفف مركز"),
        "Fruit, edible; oranges, fresh or dried") is not None


def test_the_state_words_survive_the_stopword_list():
    """`_STOPWORDS` تحوي «fresh»/«dried» — فلا يُبنى الشرطُ على `_tokens`."""
    assert C._process_state_conflict(
        C._tokens("عصير برتقال"),
        "Fruit, edible; oranges, fresh or dried") is not None


def test_seed_coverage_reports_a_real_breakdown_not_one_number():
    """التفصيلُ تفصيل: عمودٌ لكلّ مصدرٍ فعليّ لا رقمٌ مكرّر ثلاثاً."""
    cov = C.seed_coverage()
    assert cov["with_keywords"] >= cov["with_name_ar"]
    assert cov["arabic_guarded"] >= cov["with_keywords"]
