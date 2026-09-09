"""صورةُ المنتج ⇒ بندٌ جمركيّ واحد محسوم — أو طلبُ إدخالٍ يدويّ. لا ثالث.

قرار المالك (2026-08-29): «إما المصنع موجود عنده الكود يضيفه ويعتمد عليه، أو
طلب رفع الصورة وتحليل الصورة وتحديد المنتج بدقة عالية — **بدون وضع خيارات
للمصنع لكي يختار أو كتابة ثقة**».

لماذا: المُحلِّل اللفظي لا يصلح أساساً للتصنيف، والقياسُ في نفس الجلسة يثبته —
«عصير برتقال» ⇒ برتقال **طازج** بثقة 0.90 وتأكيدٍ إيجابيّ، و١٣ من ٢٠ منتجاً
سعودياً عادياً فقط تُحسَم، والحارسُ العربي على ١٤٦ صفّاً من ٥٦١٣ (٢٫٦٪).
عرضُ خياراتٍ على المصنع لا يُصلِح مُحلِّلاً لا يعرف؛ يُستبدَل بمصدرٍ يعرف:
الرؤيةُ تقرأ العبوة (اسم + **مكوّنات + صفات + فئة**) ثمّ يُصنِّف المصنّفُ العام
المُرسى على المرجع الرسميّ.

**العقد — يفرضه `tests/test_hs_from_image.py`:**

1. مخرَجُ النجاح رمزٌ **واحد** (`hs6`) لا قائمة. لا مفتاح `candidates` ولا
   `confidence` في أيّ ردّ يخرج من هنا — لا لأنها غير محسوبة، بل لأن عرضَها
   على المصنع هو ما مُنِع.
2. لا يُقبَل إلا `tier == "auto"` من `silk_hs_classifier.classify_general`
   (وهو صارمٌ أصلاً: مؤكَّدٌ على المرجع، وبهامشٍ واضح على تاليه). أيُّ درجةٍ
   أدنى ⇒ **طلبُ الرمز يدوياً**، لا «أفضل مرشّح» صامت (عقد عدم الاختلاق).
3. لا نداءَ رؤيةٍ إلا بإذنٍ مُمرَّرٍ من المستدعي (`allow_vision`) — القياسُ
   والحجزُ يبقيان عند السطح المالك لدفتر الاستهلاك، لا هنا.

هذه الوحدة **محوّلٌ أماميّ**: لا تستورد المحرّك ولا الخادم، فتُختبَر هرمتياً
ويستعملها سطحُ المنصّة والسطحُ الجذريّ معاً بلا ازدواج منطق.
"""
from __future__ import annotations

import logging

log = logging.getLogger("silk.hs_from_image")

# الرسالةُ الموحّدة حين لا يُحسَم — **مطابَقةٌ تامّة في الاختبارات**. تقول
# للمصنع ما يفعل (المسار الأوّل) ولا تعرض خياراً ولا رقماً.
MANUAL_FALLBACK_MSG = ("لم نتمكّن من تحديد البند الجمركي من الصورة — "
                       "أدخل رمز HS الخاص بمنتجك.")

# المفاتيحُ الممنوعة على أيّ ردٍّ يخرج من هنا (قفلٌ بنيويّ لا عُرف).
FORBIDDEN_CLIENT_KEYS = ("candidates", "confidence", "hs_confidence",
                         "alternates", "tier")


def _manual(reason: str) -> dict:
    """طلبُ إدخالٍ يدويّ — السببُ للسجلّ لا للعرض."""
    return {"ok": False, "hs6": None, "message": MANUAL_FALLBACK_MSG,
            "reason": reason, "source": "image"}


def classify_from_image(image_b64: str, media_type: str, *,
                        allow_vision: bool = True,
                        blocked_reason: str = "",
                        allow_claude: bool = True) -> dict:
    """صورةٌ ⇒ `{ok, hs6, product_name, source}` أو طلبُ إدخالٍ يدويّ.

    لا تُعيد مرشّحين ولا ثقة في أيّ حال — راجع عقد الوحدة أعلاه.
    """
    import silk_product_intake as intake

    if not intake.enabled():
        return _manual("مسار الصورة مُعطَّل (SILK_IMAGE_INTAKE)")

    read = intake.intake_image(image_b64, media_type, "product",
                               allow_vision=allow_vision,
                               blocked_reason=blocked_reason)
    return classify_extraction(read, allow_claude=allow_claude)


def classify_extraction(read: dict, *, allow_claude: bool = True) -> dict:
    """حكم واحد لقراءة الصورة، سواء أتت من الكتالوج أو نافذة الدراسة.

    Reuse an already metered extraction without repeating the vision call.
    """
    if not read.get("ok"):
        # سببُ الرؤية الحقيقي يُحفَظ للسجلّ؛ المعروضُ رسالةٌ واحدة.
        return _manual(str(read.get("reason") or read.get("status") or
                           "تعذّرت قراءة الصورة"))

    product = str(read.get("product_name") or "").strip()
    if not product:
        return _manual("الرؤية لم تُعِد اسم منتج")
    extraction = read.get("extraction") or {}
    # Brand/marketing words are not tariff characteristics. The vision reader
    # supplies a separate evidenced type; keep the label name for display.
    classification_product = str(extraction.get("product_type") or "").strip() or product

    import silk_hs_classifier as hsc
    image_context = {}
    if extraction.get("attributes"):
        image_context["label_attributes"] = extraction["attributes"]
    out = hsc.classify_general(
        classification_product,
        ingredients=extraction.get("ingredients") or None,
        category=extraction.get("category_hint") or None,
        allow_claude=allow_claude, **image_context)

    # **الدرجة `auto` وحدها.** `candidates`/`manual` كلاهما «غير محسوم»، وقرارُ
    # المالك أن غيرَ المحسوم يُطلَب فيه الرمز لا تُعرَض فيه قائمة.
    if str(out.get("tier")) != "auto" or not out.get("hs6"):
        return _manual(f"التصنيف لم يبلغ الحسم (درجة {out.get('tier')})")

    return {"ok": True, "hs6": str(out["hs6"]), "product_name": product,
            "source": "image", "classifier_source": out.get("source") or ""}
