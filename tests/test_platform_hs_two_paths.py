"""سطحُ المصنع: رمزٌ يكتبه يُعتمَد، أو صورةٌ تُحسَم — ولا ثالث.

قرار المالك (2026-08-29): «إما المصنع موجود عنده الكود يضيفه ويعتمد عليه، أو
طلب رفع الصورة وتحليل الصورة وتحديد المنتج بدقة عالية — بدون وضع خيارات
للمصنع لكي يختار أو كتابة ثقة».

هذا الملفّ يقفل السطحَ نفسَه: النقطةُ الجديدة تكتب الرمز حين يُحسَم وتطلبه
حين لا يُحسَم، وشاشةُ المصنع خاليةٌ من حوار الاختيار ومن أيّ رقم ثقة.
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _page() -> str:
    with open(os.path.join(_ROOT, "web", "platform.html"), encoding="utf-8") as f:
        return f.read()


def _api_src() -> str:
    with open(os.path.join(_ROOT, "silk_platform", "api.py"),
              encoding="utf-8") as f:
        return f.read()


# ═══════════ ١ — الشاشة: لا حوارَ اختيار ولا ثقة ═════════════════════════════
def test_the_factory_screen_has_no_heading_picker_anymore():
    """حوارُ «اختر البند الجمركي» حُذف — لا خيارات تُعرَض على المصنع."""
    page = _page()
    assert "hsPickBtn" not in page
    assert "_hsCandidates" not in page.replace(
        "و`_hsCandidates` حُذفا", "")          # التعليقُ التاريخيّ مسموح
    assert 'name="hs_pick"' not in page


def test_the_factory_screen_never_prints_a_confidence_number():
    """«كتابة ثقة» ممنوعة على سطح المصنع — لا حقلَ ولا نصّ."""
    page = _page()
    for needle in ("hs_confidence", "ثقة التصنيف", "min_confidence"):
        assert needle not in page, needle


# عقدُ الخادم يبقى (قرار المالك 2026-08-31: القرارُ على الشاشة وحدها) —
# اختيارُ عميلِ الـAPI عبر PATCH يُسجَّل تأكيداً صريحاً بمصدرٍ معلَن.
def test_the_server_records_the_choice_as_user_confirmed():
    """`classification_method="user_confirmed"` يُخزَّن — إفصاحٌ يبقى بعد شهر."""
    src = _api_src()
    assert 'method = "user_confirmed" if confirmed else None' in src
    assert "hs_classification_method = ?" in src


def test_a_no_op_resave_never_buys_a_confirmation():
    """إعادةُ حفظٍ بلا تغيير لا تُرفَع تأكيداً — التأكيدُ نقرةُ اختيارٍ صريحة.

    الرمزُ المُقارَن يأتي من **جسم الطلب** لا من الصفّ المحدَّث: الصفُّ يحمل
    الرمزَ المخزَّن دائماً، فمقارنتُه بالمرشّحين كانت تُمرِّر أيَّ حفظٍ ولو لم
    يلمس المصنعُ شيئاً (تدقيق 2026-08-30).

    ومراجعة PR #254 أكملت القاعدة: الذكرُ في الجسم وحده لا يكفي أيضاً —
    نموذجُ التحرير يردّد الرمزَ المعبّأ في كل حفظ، فالتأكيدُ يشترط رمزاً
    **تغيّر** إلى مرشّح، وحفظٌ لا يغيّر رمزاً ولا منتجاً لا يكتب شيئاً
    (القفل السلوكيّ الكامل في `tests/test_pr254_review_fixes.py`).
    """
    src = _api_src()
    assert 'else str(body.get("hs_code") or "").strip())' in src
    assert 'else str(updated.get("hs_code") or "").strip())' not in src
    assert "if code_changed or product_changed:" in src
    assert "confirmed = 1 if (code_changed and chosen and any(" in src


# ═══════════ ٢ — النقطة: تكتب عند الحسم، وتطلب الرمز عند غيره ════════════════
def test_the_screen_offers_the_photo_path_as_a_real_button():
    """المخرجُ الجديد زرٌّ يُنادي النقطة فعلاً — لا تعليقاً يمرّ به قفلٌ أجوف.

    (أُضيف بعد أن كادت مرساةُ الدرس ٧٩ تمرّ على تعليقٍ في الصفحة وحده.)
    """
    page = _page()
    assert "function classifyImageBtn(p)" in page
    assert '"/products/" + p.id + "/classify-image"' in page
    # ولا يظهر الزرُّ إلا حيث يلزم: منتجٌ بلا رمزٍ وله صورة.
    assert "if (!p.hs_code && p.image_id) td.appendChild(classifyImageBtn(p));" \
        in page


def test_the_endpoint_exists_and_writes_the_code_only_when_settled():
    src = _api_src()
    assert '"/products/{product_id}/classify-image"' in src
    # الحسمُ يأتي من نقطة الاختناق المشتركة لا من منطقٍ ثانٍ هنا.
    assert "silk_hs_from_image.classify_from_image(" in src
    # ولا يُكتَب رمزٌ إلا بعد `ok` — لا «أفضل مرشّح» صامت.
    idx_guard = src.index('if not out.get("ok"):')
    idx_write = src.index('"hs_code": out["hs6"], "hs_source": "image"')
    assert idx_guard < idx_write, "الكتابةُ تسبق حارسَ الحسم"


def test_the_endpoint_reply_carries_no_options_and_no_confidence():
    """حمولةُ الردّ نفسُها خاليةٌ من القائمة والرقم (لا تعتمد على الواجهة)."""
    import silk_hs_from_image as F
    src = _api_src()
    seg = src[src.index('"/products/{product_id}/classify-image"'):
              src.index('@app.patch(_PREFIX + "/products/{product_id}")')]
    for key in F.FORBIDDEN_CLIENT_KEYS:
        assert f'"{key}"' not in seg, key


def test_ownership_is_proven_before_any_image_byte_is_read():
    """صورةٌ لحسابٍ آخر لا تُقرأ أصلاً — الملكيةُ قبل فتح الملف."""
    src = _api_src()
    seg = src[src.index('"/products/{product_id}/classify-image"'):
              src.index('@app.patch(_PREFIX + "/products/{product_id}")')]
    assert seg.index("repository.images(conn).get(ctx.account_id") < \
        seg.index("storage.path_for(")


def test_no_paid_slot_is_reserved_before_the_call_is_certain():
    """نقرةٌ على صمّامٍ مُطفأ كانت تحرق تفعيلةً من السقف بصفر نداءات.

    ملاحظةُ مراجعةٍ ذاتية §58: الحجزُ سبق فحصَ `enabled()` وصحّةِ الصورة —
    عكسَ ترتيبَ `api.products_intake` («لا حجز على إدخالٍ باطل»).
    """
    src = _api_src()
    seg = src[src.index('"/products/{product_id}/classify-image"'):
              src.index('@app.patch(_PREFIX + "/products/{product_id}")')]
    assert seg.index("silk_product_intake.enabled()") < \
        seg.index("_vision_allowed_for_platform()")
    assert seg.index("_decode_and_check(") < \
        seg.index("_vision_allowed_for_platform()")


def test_a_blocked_or_capped_vision_degrades_to_asking_for_the_code():
    """السقفُ المستنفد أو غيابُ المفتاح ⇒ «أدخل الرمز»، لا عطلٌ ولا اختلاق."""
    src = _api_src()
    assert "def _vision_allowed_for_platform" in src
    assert "SILK_API_KEY" in src and "try_reserve_paid_calls(1)" in src
    # وكلفةُ النداء تدخل الدفتر اليوميّ المشترك (لا نداءٌ غير محسوب).
    seg = src[src.index("def _vision_allowed_for_platform"):
              src.index('@app.patch(_PREFIX + "/products/{product_id}")')]
    assert "record_usd" in seg and "begin_data_counter" in seg
