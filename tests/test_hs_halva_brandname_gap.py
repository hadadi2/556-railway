"""فجوةُ «الطاحونة» — اسمُ علامةٍ تجارية فوق منتجٍ غائبٍ عن المرجع العربي.

الحادثة (بلاغ المالك 2026-08-29): دراسةُ مصنعٍ لمنتج «الطاحونة» (حلاوة طحينية
سادة) لم تنطلق. بوّابةُ الثقة حجبت رمزَ الكتالوج 170490 لأن ثقتَه «غير معلومة»
— وهو **سلوكها الصحيح** (رمزُ كتالوجٍ مُعادٌ ليس إجابةَ إنسانٍ حاضر) — ثمّ
سلّمت قائمةَ مرشّحين **فارغة** بينما نصُّها يقول «اختر من المرشّحين أدناه»:
طريقٌ مسدود بنصٍّ يعِد بما لا يوجد (زرُّ «اختر البند الجمركي» في شاشة المصنع
لا يظهر إلا بوجود مرشّحين — `web/platform.html:_hsCandidates`).

وتحته عطلٌ أخطر من الحجب: المرجعُ العربي لا يحمل «حلاوة» ولا «طحينة» إطلاقاً،
بينما 110100 (دقيق قمح) يحمل «طحين» — سلسلةٌ **مُحتواةٌ حرفياً** داخل
«طحينية»/«طحينة»، ففرعُ الاحتواء في `silk_hs_resolver._score` كان يمنح دقيقَ
القمح ثقة 0.88 لـ«حلاوة طحينية» و0.93 لـ«طحينة»: **فوق** عتبة البوّابة (0.80)،
أي أن الطريق البديل (كتابةُ اسم المنتج بدل اسم العلامة) كان يمرّ صامتاً
ويبني دراسةً كاملةً على رمز دقيق القمح. رمزٌ خاطئ يُعيد تأطير كل رقمٍ لاحق.

الأقفال هنا اشتُقّت من الحادثة نفسها: عائلة `lookup-table-ceiling` (سقفُ جدول
البحث) + عائلة «رسالةٌ تعِد بمخرجٍ غير موجود».
"""
import silk_hs_confirm as HC
from silk_hs_resolver import resolve, resolve_all

_FLOUR = "110100"          # دقيق قمح — الرمزُ الخاطئ الذي كان يفوز
_CONFECTIONERY = "170490"  # حلويات سكرية غير محتوية على كاكاو — الصحيح للحلاوة
_PREPARED_SEEDS = "200819" # بذور محضّرة — الصحيح للطحينة (معجون السمسم)


# ═══════════ ١ — الحلاوة الطحينية ليست دقيق قمح ═══════════════════════════════
def test_halva_resolves_to_sugar_confectionery_never_wheat_flour():
    """كلُّ تهجئةٍ معقولةٍ للمنتج تحلّ إلى 170490 — ولا واحدة منها إلى 110100."""
    for name in ("حلاوة طحينية سادة", "حلاوة طحينية", "حلاوه طحينيه",
                 "حلاوة طحينية بالفستق"):
        dp = resolve(name)
        assert dp.value == _CONFECTIONERY, (name, dp.value, dp.note)
        # الثقةُ فوق عتبة البوّابة: منتجٌ محسومٌ لا يُوقِف المصنعَ بسؤال.
        assert dp.confidence >= HC.min_confidence(), (name, dp.confidence)


def test_wheat_flour_never_appears_among_the_halva_candidates():
    """«طحين» المُحتواةُ في «طحينية» لا تُصعِد دقيقَ القمح ولو مرشّحاً."""
    values = [dp.value for dp in resolve_all("حلاوة طحينية سادة", top_n=5)]
    assert _FLOUR not in values, values
    assert values[0] == _CONFECTIONERY, values


def test_tahini_resolves_to_prepared_seeds_never_wheat_flour():
    """«طحينة» (معجون السمسم) بندُ البذور المحضّرة لا بندُ الطحين."""
    for name in ("طحينة", "طحينه", "طحينة سمسم"):
        dp = resolve(name)
        assert dp.value == _PREPARED_SEEDS, (name, dp.value, dp.note)
        assert dp.value != _FLOUR


def test_the_reference_carries_the_arabic_guard_for_both_codes():
    """الجذرُ بياناتٌ لا منطق: الحارسُ العربي مكتوبٌ في المرجع نفسه."""
    from silk_hs_resolver import load_hs_codes
    rows = {r["hs_code"]: r for r in load_hs_codes()}
    assert "حلاوة طحينية" in (rows[_CONFECTIONERY].get("keywords_ar") or "")
    assert "طحينة" in (rows[_PREPARED_SEEDS].get("keywords_ar") or "")


# ═══════════ ٢ — الرفض يسلّم مخرجاً أو يقول الحقيقة، ولا يعِد بالفراغ ═════════
def test_confidence_block_hands_back_real_candidates_for_a_product_name():
    """اسمُ منتجٍ حقيقي ⇒ مرشّحون فعليّون، والرسالةُ تحيل إليهم."""
    blocked = HC.confidence_block("حلاوة طحينية سادة", _CONFECTIONERY, None)
    assert blocked is not None
    cands = blocked["candidates"]
    assert cands, blocked
    assert cands[0]["hs6"] == _CONFECTIONERY, cands
    assert "اختر من المرشّحين أدناه" in blocked["message"]


def test_confidence_block_without_candidates_never_promises_a_list():
    """اسمُ علامةٍ تجارية ⇒ لا مرشّحين: الرسالةُ تقول ذلك بدل «أدناه» الكاذبة.

    هذا هو الطريقُ المسدود الذي رآه المالك حرفياً: نصٌّ يحيل إلى قائمةٍ
    فارغة، وشاشةٌ بلا زرِّ اختيار.
    """
    blocked = HC.confidence_block("الطاحونة", _CONFECTIONERY, None)
    assert blocked is not None
    assert blocked["candidates"] == []
    msg = blocked["message"]
    assert "أدناه" not in msg, msg
    assert "وصف المنتج" in msg, msg
    # الحدُّ الأدنى والثقةُ الغائبة يبقيان معلنَين — لا يُخفيهما تحسينُ النصّ.
    assert "غير معلومة" in msg and blocked["hs_confidence"] is None


# ═══════════ ٣ — ما التقطته المراجعة الذاتية (§58) على هذه الموجة ════════════
def test_adding_tahini_never_hijacks_bare_sesame():
    """«سمسم» (بذور خام، ترويسة 1207) تبقى فجوةً معلنة لا بندَ محضّرات.

    ملاحظةُ مراجعةٍ ذاتية على هذه الموجة نفسها: مفتاحُ «معجون سمسم» على
    200819 جعل «سمسم» المجرَّدة تُحَلّ إليه بثقة 0.95 — **فوق** العتبة، أي
    دراسةُ بذورٍ خام تمضي صامتةً على بندِ المحضّرات. نفسُ فخّ الاحتواء الذي
    كُتب هذا الدرسُ لإغلاقه: الحارسُ المضاف يجب ألّا يفتح ثغرةً بجواره.
    """
    dp = resolve("سمسم")
    assert dp.value is None, (dp.value, dp.confidence)
    assert dp.confidence == 0.0
    from silk_hs_resolver import load_hs_codes
    rows = {r["hs_code"]: r for r in load_hs_codes()}
    assert "معجون سمسم" not in (rows[_PREPARED_SEEDS].get("keywords_ar") or "")


def test_the_two_message_tails_are_one_exported_source():
    """ذيلا الرسالة ثابتان مُصدَّران — لا نسخةَ نصٍّ ثانية تتباعد عنهما.

    جسرُ المنصّة يملك مرشّحين لا تراهم البوّابة (وصفُ الكتالوج)، فيبدّل الذيل
    بدل أن يترك «لا مرشّحين» فوق قائمةٍ مملوءة — والتبديل يقرأ الثابتَين
    نفسَيهما لا سلسلةً مكرّرة.
    """
    assert HC.PICK_TAIL.endswith("أو أدخل رمزاً يدوياً.")
    assert "وصف المنتج" in HC.NO_CANDIDATES_TAIL
    with_c = HC.confidence_block("حلاوة طحينية سادة", _CONFECTIONERY, None)
    without = HC.confidence_block("الطاحونة", _CONFECTIONERY, None)
    assert with_c["message"].endswith(HC.PICK_TAIL)
    assert without["message"].endswith(HC.NO_CANDIDATES_TAIL)
    import silk_platform.engine_bridge as eb
    src = open(eb.__file__, encoding="utf-8").read()
    assert "from silk_hs_confirm import NO_CANDIDATES_TAIL, PICK_TAIL" in src
