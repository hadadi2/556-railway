"""خطُّ التصنيف الواحد: منتج ← HS6 — the ONE Product → HS6 pipeline.

> **العائلة.** `classification-decided-by-provenance`: كان القرارُ يُتَّخذ من
> **مَن سلّم الرمز** لا من **مدى مطابقته للمنتج**. رمزُ كتالوجٍ مُعادٌ تُضبَط
> ثقتُه `None` ابتداءً (`api.py`) ولا يُسأل المُحلِّلُ عنه إطلاقاً، فبوّابةُ
> الثقة تحجب رمزاً كان المُحلِّلُ نفسُه سيمنحه ١٫٠٠ — «حلاوة طحينية» ⇒ 170490.
> وتحته عيبٌ أخطر: الدليلُ اللفظيّ كان يُقاس بالاحتواء الحرفيّ فيصنّف
> «مناديل ورقية» بطيخاً بثقة ٠٫٨٧٥ **بصمت**.
>
> **القاعدةُ الدائمة.** الثقةُ **قياسٌ** لا وسمُ مصدر. ومَن يملك رمزاً — كتالوجاً
> كان أو إنساناً — يُقاس رمزُه كما يُقاس أيُّ مرشّح، ثم يُقارَن بما يقوله
> المُحلِّلُ مستقلّاً. الاتفاقُ يُعتمَد، والاختلافُ يُسأل عنه، ولا يُحسَم صامتاً.

The single authoritative flow (البند ١ من أمر الموجة):

    PRODUCT NAME → NORMALIZATION → CANDIDATE RETRIEVAL → RANKING →
    SEMANTIC VALIDATION → CONTRADICTION DETECTION → SEPARATION →
    CONFIDENCE → DECISION → FINAL HS6

هذه الوحدة **لا تُنشئ مُصنِّفاً ثالثاً**: تُركّب القطعَ القائمة بترتيبٍ واحد
معلَن — `silk_hs_norm` للتنميط، `silk_hs_resolver.retrieve` للاسترجاع،
`silk_hs_confirm` للتأكيد الدلاليّ وكشف التناقض، `silk_hs_dialog` للوصف
الرسميّ. الاسترجاعُ يقترح والقرارُ يقع هنا، وحدَه.

المكتبات: stdlib فقط — لا شبكة، لا نداء نموذج، لا تكلفة. صفرُ اختلاق: ما لا
يُثبِته الدليلُ يُسأل عنه (`requires_confirmation`) ولا يُخمَّن.
"""
from __future__ import annotations

import logging
import os

import silk_hs_norm as _norm

log = logging.getLogger("silk.hs_pipeline")

DEFAULT_PATH = "data/hscodes_full.csv"

# ── حالاتُ التصنيف · classification statuses (البند ٤) ───────────────────────
APPROVED = "approved"
REQUIRES_CONFIRMATION = "requires_confirmation"
ERROR = "error"

# ── حالاتُ رمز الكتالوج · catalog HS statuses (البند ٢) ──────────────────────
CATALOG_ABSENT = "absent"
CATALOG_AUTO_APPROVED = "auto_approved"
CATALOG_CONFLICT = "hs_conflict"
CATALOG_REJECTED = "catalog_hs_rejected"
CATALOG_REQUIRES_CONFIRMATION = "requires_confirmation"

# ── طرائقُ الحسم · classification methods ────────────────────────────────────
METHOD_EXACT = "deterministic_exact"          # عبارةُ المنتج = مفتاحُ المرجع
METHOD_TOKEN = "deterministic_token"          # تغطيةُ وحداتٍ + تأكيدٌ دلاليّ
METHOD_CATALOG_AGREEMENT = "catalog_agreement"  # الكتالوجُ يوافق المُحلِّل
METHOD_USER_CONFIRMED = "user_confirmed"      # إنسانٌ حاضرٌ اختار
METHOD_LLM_GROUNDED = "llm_grounded"          # مصنّفٌ مُرسًى على المرجع
METHOD_UNRESOLVED = "unresolved"              # لا حسم — يُسأل

# ── رموزُ الرفض · refusal codes ──────────────────────────────────────────────
# كلُّ سببِ رفضٍ يحمل رمزَه: السطحُ الذي يعرضه، والسجلُّ الذي يُشخَّص منه، وجسرُ
# المنصّة الذي يقرّر «هل (اختر البند) جوابٌ صالحٌ لهذا الرفض؟» — كلُّها تقرأ
# هذا الحقل. رمزٌ عامٌّ واحد لكلّ الأسباب يُفقِد التشخيصَ معناه.
REFUSAL_AXIS = "hs_axis_disambiguation_needed"    # محورٌ رقميّ يستوجب اختياراً
REFUSAL_CONFLICT = "hs_catalog_conflict"          # الكتالوج يخالف المُحلِّل
REFUSAL_CATALOG_REJECTED = "hs_catalog_rejected"  # رمزُ كتالوجٍ باطل/خارج النطاق
REFUSAL_UNRESOLVED = "hs_requires_confirmation"   # لا دليلَ كافٍ للحسم
REFUSAL_ERROR = "hs_classification_error"         # عطلٌ في خطّ التصنيف نفسه

# ── العتبات · thresholds (كلُّها من البيئة، لا رقمَ صلبٍ في المنطق) ──────────
_DEFAULT_MIN_CONFIDENCE = 0.80
# فارقٌ أدنى بين الأول والثاني. متقاربان (0.81 مقابل 0.80) ليسا حسماً بل
# سؤالاً — البند ١١. القيمةُ صغيرةٌ عمداً: هي تكشف التعادلَ لا تفرض تفوّقاً.
_DEFAULT_MIN_SEPARATION = 0.06
# أدنى دليلٍ يستحقّ أن يُعرَض للمصنع أصلاً. ما دونه ضجيجٌ لا خيار.
_DEFAULT_CANDIDATE_FLOOR = 0.55
# **كيف يتركّب الدليلان.** التأكيدُ الدلاليّ ليس نصفَ متوسّطٍ بل **بوّابة**:
# مرشّحٌ غيرُ مؤكَّدٍ أو متناقض يسقط من دائرة القرار كلّها (score = 0). ما نجا
# منها تحمل **الرتبةُ اللفظية** مقدارَه، مخصوماً منه خصمٌ صغير بقدر ما بقي من
# صفات المنتج بلا تفسير.
#
# لماذا لا متوسّطٌ موزون: الوحدةُ غيرُ المفسَّرة تُدفَع مرّتين — مرّةً في F1
# اللفظيّ (دقّةٌ أقلّ) ومرّةً في التداخل الدلاليّ — فتسقط تصنيفاتٌ صحيحةٌ تحت
# العتبة لمجرّد صفةٍ وصفيّة لا يحملها أيُّ وصفٍ جمركيّ («حلاوة طحينية **سادة**»).
# العقوبةُ المزدوجة تقيس الشيءَ نفسَه مرّتين، وذلك عيبُ قياسٍ لا صرامة.
_SEMANTIC_DISCOUNT = 0.10


def _env_float(name: str, default: float) -> float:
    """عتبةٌ من البيئة ضمن (0,1] — أيُّ قيمةٍ فاسدة تعود للافتراض بصمتٍ آمن."""
    try:
        v = float(os.environ.get(name, ""))
        return v if 0.0 < v <= 1.0 else default
    except (TypeError, ValueError):
        return default


def min_confidence() -> float:
    """عتبةُ الاعتماد — نفسُ صمّام البوّابة القائمة (`SILK_HS_MIN_CONFIDENCE`).

    تُقرأ من `silk_hs_confirm` كي تبقى **عتبةً واحدة** لا اثنتين تتباعدان.
    """
    from silk_hs_confirm import min_confidence as _mc
    return _mc()


def min_separation() -> float:
    """أدنى فارقٍ بين المرشّح الأول والثاني (`SILK_HS_MIN_SEPARATION`)."""
    return _env_float("SILK_HS_MIN_SEPARATION", _DEFAULT_MIN_SEPARATION)


def candidate_floor() -> float:
    """أدنى دليلٍ يُعرَض به مرشّح (`SILK_HS_CANDIDATE_FLOOR`)."""
    return _env_float("SILK_HS_CANDIDATE_FLOOR", _DEFAULT_CANDIDATE_FLOOR)


# ═══════════════ تقييمُ مرشّحٍ واحد · evaluating one candidate ════════════════

def _official_description(hs6: str) -> str:
    """الوصفُ الرسميّ من المرجع الكامل — `""` إن غاب (لا اختلاق)."""
    try:
        from silk_hs_resolver import official_description
        return official_description(hs6) or ""
    except Exception as exc:  # noqa: BLE001 — مرجعٌ غائب = فجوة معلنة
        log.warning("official description lookup failed for %s: %s", hs6, exc)
        return ""


def _contradictions(product: str, hs6: str, confirmation: dict,
                    official: str) -> tuple[list[str], list[str]]:
    """كلُّ ما يناقض هذا المرشّح — قائمةٌ عربيةٌ مقروءة، فارغةٌ حين لا تناقض.

    البند ٩. ثلاثةُ مصادرَ مستقلّة، كلُّها حتميّة:
    ١) نفيٌ/عتبةٌ رقمية في وصف الرمز تناقض صفةَ المنتج (`_negation_conflict`).
    ٢) صفةُ تصنيعٍ في الاسم أمام رمزٍ يعلن حالةً خاماً (`_process_state_conflict`).
    ٣) **صفرُ تداخل**: لا صفةَ واحدة من صفات المنتج يشملها وصفُ الرمز. هذا هو
       الحارسُ الذي كان غائباً — «مناديل ورقية» ضد «بطيخ» صفرُ تداخلٍ تامّ،
       ومع ذلك كان الاحتواءُ الحرفيّ يمنحها 0.875.

    تُعيد `(الكلُّ، القاسي)`. **الفرقُ جوهريّ**: (١) و(٢) تعارضٌ حقيقيّ —
    الوصفُ يقول نقيضَ ما يقوله الاسم. أمّا (٣) فقد يكون مجرّدَ **فجوةِ تغطية**
    في المرجع: صفٌّ بلا كلماتٍ عربية لا يتقاطع مع اسمٍ عربيّ مهما كان صحيحاً.
    خلطُهما يجعل كلَّ صفٍّ غيرِ مُعرَّبٍ «متناقضاً»، وذلك ادّعاءٌ لا يملكه
    الدليل. كلاهما يمنع الاعتمادَ التلقائي؛ القاسي وحده يمنع **الإنسانَ** من
    اختياره.
    """
    import silk_hs_confirm as HC
    out: list[str] = []
    hard: list[str] = []
    if confirmation.get("negation_conflict"):
        reason = str(confirmation.get("reason") or "").strip()
        if reason:
            out.append(reason)
            hard.append(reason)
    overlap = confirmation.get("overlap")
    terms = confirmation.get("product_terms") or []
    if terms and overlap == 0.0:
        out.append("لا تشترك صفاتُ المنتج مع وصف الرمز في صفةٍ واحدة — "
                   "تشابهُ الحروف وحده ليس تصنيفاً")
    elif confirmation.get("confirmed") is False and not out:
        missing = "، ".join(confirmation.get("missing_terms") or [])
        out.append("وصفُ الرمز لا يشمل الصفةَ المميّزة"
                   + (f" ({missing})" if missing else ""))
    # الوصفُ الرسميُّ الكامل مصدرٌ ثانٍ للنفي: قد يحمل عتبةً/استثناءً لا يحمله
    # صفُّ المفاتيح (البند ١٢ — التحقّق ضد المصدر الرسميّ لا المفاتيح وحدها).
    if official:
        p_terms = _norm.tokens(product)
        clash = (HC._negation_conflict(p_terms, official)
                 or HC._process_state_conflict(p_terms, official))
        if clash and clash not in out:
            out.append(clash)
        if clash and clash not in hard:
            hard.append(clash)
    return out, hard


def _evaluate(product: str, hs6: str, lexical: float, description: str,
              path: str) -> dict:
    """قِس مرشّحاً واحداً بكل الأدلّة — الشكلُ الذي يستهلكه الترتيبُ والقرار."""
    import silk_hs_confirm as HC
    from silk_hs_resolver import chapter_valid, exclusion_note

    official = _official_description(hs6)
    confirmation = HC.confirm_hs(product, hs6, path)
    contras, hard = _contradictions(product, hs6, confirmation, official)

    if not chapter_valid(hs6):
        _bad = f"فصلُ الرمز {hs6[:2]} غير موجود في بنية WCO"
        contras.insert(0, _bad)
        hard.insert(0, _bad)
    excl = exclusion_note(hs6)
    if excl:
        contras.insert(0, excl)
        hard.insert(0, excl)

    overlap = confirmation.get("overlap")
    semantic = float(overlap) if isinstance(overlap, (int, float)) else 0.0
    confirmed = confirmation.get("confirmed")
    score = float(lexical) * (1.0 - _SEMANTIC_DISCOUNT * (1.0 - semantic))
    if contras or confirmed is not True:
        # تناقضٌ لا يُوازَن بدليلٍ لفظيّ مهما قوي (البند ٩ حرفياً): مرشّحٌ
        # متناقضٌ — أو غيرُ مؤكَّدٍ دلالياً — يسقط من دائرة القرار كلّها، لا
        # يُخفَّض ترتيبُه فحسب. هذه هي البوّابةُ التي تجعل الرتبةَ اللفظية
        # **دليلاً مشروطاً** لا حكماً مستقلاً (البند ٧).
        score = 0.0
    return {
        "hs6": hs6,
        "description": (description or official or "").strip(),
        "band_ar": "",
        "official_description": official,
        "lexical_score": round(float(lexical), 4),
        "semantic_overlap": None if overlap is None else round(semantic, 4),
        "score": round(score, 4),
        "confirmed": confirmed,
        "matched_attributes": list(confirmation.get("shared_terms") or []),
        "missing_attributes": list(confirmation.get("missing_terms") or []),
        "contradictions": contras,
        # تعارضٌ حقيقيّ (نفيٌ/حالةُ تصنيعٍ/نطاق) لا فجوةُ تغطيةٍ في المرجع —
        # هذا وحده يمنع اختيارَ إنسانٍ حاضر، لا مجرّدُ صفٍّ غيرِ مُعرَّب.
        "hard_contradiction": bool(hard),
        # يُعرَض للمصنع؟ مؤكَّدٌ دلالياً + بلا تناقض + فوق أرضيّة العرض.
        "offer": bool(confirmed is True and not contras
                      and score >= candidate_floor()),
        "reason_ar": str(confirmation.get("reason") or "").strip(),
    }


# ═══════════════ القرار · the decision ═══════════════════════════════════════

def _contract(**kw) -> dict:
    """العقدُ الموحّد — **شكلٌ واحد** لكل مخرجات التصنيف (البند ٣).

    كلُّ مفتاحٍ حاضرٌ دائماً؛ الغيابُ يُمثَّل بـ`None`/`[]` لا بمفتاحٍ ناقص —
    فمستهلكٌ يقرأ مفتاحاً غائباً كان يعرض «—» ويظنّها فجوةَ بيانات.
    """
    base = {
        "product_name": "",
        "normalized_product": "",
        "final_hs_code": None,
        "official_hs_description": "",
        "confidence": 0.0,
        # درجةُ أعلى مرشّحٍ **باسمها الصريح** — عند الرفض تبقى `confidence`
        # رقماً (البند ٤) لكنها لا تُقرأ سبباً: سببُ الرفض تعادلٌ/محورٌ/
        # تعارضٌ يذكره `reason`، وهذا الحقل يفصل الدرجةَ عن السبب.
        "top_candidate_score": 0.0,
        "classification_status": REQUIRES_CONFIRMATION,
        "classification_method": METHOD_UNRESOLVED,
        "catalog_hs_code": None,
        "catalog_hs_status": CATALOG_ABSENT,
        "candidate_codes": [],
        "candidate_scores": {},
        "matched_attributes": [],
        "contradictions": [],
        "requires_user_confirmation": True,
        "provenance": [],
        "reason": "",
        "error": None,
        "refusal_code": None,
        "attribute_probe": None,
        # تقريرُ مجسّ المحور الكامل حين يكون هو الحاسم — يحمله العقدُ
        # كي تُعيده بوّابةُ ما بعد التصنيف provenance كما هو بدل أن
        # تعيد القياسَ كاملاً (المهمة ١٤: الآلةُ مرّةً واحدة لكل طلب).
        "probe_report": None,
    }
    base.update(kw)
    base["requires_user_confirmation"] = (
        base["classification_status"] == REQUIRES_CONFIRMATION)
    base["candidate_scores"] = {c["hs6"]: c["score"]
                                for c in base["candidate_codes"]}
    return base


def _valid_hs6(code: object) -> str:
    """رمزٌ سداسيُّ الأرقام أو نصٌّ فارغ — تحقّقُ شكلٍ قبل أيّ استعمال/تخزين.

    البند ٢٨ (الأمن): مدخلُ المستخدم لا يصل قاعدةً ولا مسارَ ملفٍّ ولا استعلاماً
    بلا هذا الفحص. أرقامٌ فقط، طولٌ ٦ — لا مسافات ولا حروف ولا محارف تحكّم.
    """
    c = str(code or "").strip()
    return c if (len(c) == 6 and c.isdigit() and c.isascii()) else ""


def classify(product: object, catalog_hs: object = None, *,
             hs_confirmed: bool = False,
             user_supplied: bool = False,
             allow_claude: bool = False,
             ingredients: object = None,
             category: object = None,
             label_attributes: object = None,
             allow_web: bool = True,
             gl: str | None = None,
             path: str = DEFAULT_PATH,
             top_n: int = 5) -> dict:
    """صنِّف منتجاً إلى HS6 — نقطةُ الحقيقة الواحدة، وتُعيد العقدَ دائماً.

    `catalog_hs` رمزُ الكتالوج إن وُجد: يدخل **مرشّحاً يُقاس** لا حقيقةً
    تُفترَض (البند ٢). `hs_confirmed` تأكيدُ إنسانٍ حاضر — يعتمد الرمزَ ويبقي
    التناقضاتِ معلنةً في العقد (إفصاحٌ لا إخفاء). `user_supplied` رمزٌ كتبه
    إنسانٌ **في هذا الطلب**: لا يُعفيه من القياس، لكنه يُعَدّ **إجابةَ سؤال
    المحور** إن كان أحدَ أشقّائه (بلاغ 2026-08-19: رمزٌ أدخله المستخدم بنفسه
    كان يُسأل عنه ثانيةً بلا مخرج). رمزُ كتالوجٍ مخزَّن ليس ذلك — لا إنسانَ
    حاضرٌ خلفه في هذه اللحظة (الدرس ١٢٠).

    لا ترفع استثناءً أبداً: أيُّ عطلٍ داخليّ يعود `classification_status="error"`
    برسالةٍ قابلةٍ للتنفيذ — الصمتُ هو ما أنتج «ثقة غير معلومة» أصلاً.
    """
    name = str(product or "").strip()
    normalized = _norm.normalize(name)
    catalog = _valid_hs6(catalog_hs)
    catalog_raw = str(catalog_hs or "").strip()

    if not normalized:
        return _contract(
            product_name=name, normalized_product="",
            classification_status=ERROR, error="empty_product",
            refusal_code=REFUSAL_ERROR,
            catalog_hs_code=catalog or None,
            catalog_hs_status=(CATALOG_ABSENT if not catalog_raw
                               else CATALOG_REQUIRES_CONFIRMATION),
            reason="اسمُ المنتج فارغ — لا يمكن التصنيف بلا اسم. اكتب اسمَ "
                   "المنتج كما هو على العبوة.")

    prov: list[dict] = [{"step": "normalization", "source": "silk_hs_norm",
                         "detail": normalized}]
    try:
        from silk_hs_resolver import retrieve
        hits = retrieve(name, top_n=max(1, top_n), path=path)
    except Exception as exc:  # noqa: BLE001 — عطلُ مرجعٍ = خطأٌ معلَن لا صمت
        log.warning("HS retrieval failed for %r: %s", name, exc)
        return _contract(
            product_name=name, normalized_product=normalized,
            classification_status=ERROR,
            error=f"retrieval_failed: {type(exc).__name__}",
            refusal_code=REFUSAL_ERROR,
            catalog_hs_code=catalog or None,
            reason="تعذّر قراءةُ مرجع الرموز الجمركية — راجع سلامة "
                   "data/hscodes_full.csv ثم أعد المحاولة.")
    prov.append({"step": "retrieval", "source": f"{path} (token index)",
                 "detail": f"{len(hits)} candidate(s)"})

    cands = [_evaluate(name, h["hs_code"], h["score"], h["description"], path)
             for h in hits if _valid_hs6(h["hs_code"])]

    # رمزُ الكتالوج يُقاس دائماً — حتى لو لم يُرشّحه الاسترجاع (وهذا هو
    # الشائع: الاسمُ لا يطابقه، وذاك بعينه ما يجب أن يُكتشَف لا أن يُتخطّى).
    catalog_eval = None
    if catalog:
        catalog_eval = next((c for c in cands if c["hs6"] == catalog), None)
        if catalog_eval is None:
            # الرتبةُ اللفظية لصفٍّ **واحد** بعينه — لا استرجاعٌ ثانٍ بعرض ٢٠٠
            # (كان يُعيد المسحَ الضبابيَّ كلَّه على كل طلبٍ لا يُرشَّح رمزُه).
            catalog_eval = _evaluate(name, catalog, _catalog_lexical(
                name, catalog, path), _official_description(catalog), path)
            cands.append(catalog_eval)
        prov.append({"step": "catalog_revalidation", "source": "catalog",
                     "detail": f"{catalog} score={catalog_eval['score']}"})

    cands.sort(key=lambda c: (-c["score"], c["hs6"]))
    prov.append({"step": "ranking",
                 "source": f"lexical*(1-{_SEMANTIC_DISCOUNT}*(1-semantic)), "
                           "contradiction ⇒ 0, unconfirmed ⇒ 0",
                 "detail": ", ".join(f"{c['hs6']}={c['score']}"
                                     for c in cands[:5])})

    eligible = [c for c in cands if c["offer"] and c["score"] >= min_confidence()]
    top = eligible[0] if eligible else None
    second = eligible[1] if len(eligible) > 1 else None

    return _decide(name, normalized, catalog, catalog_raw, catalog_eval,
                   cands, top, second, prov, hs_confirmed, path,
                   user_supplied, label_attributes, allow_web, gl,
                   allow_claude, ingredients, category)


def _decide(name, normalized, catalog, catalog_raw, catalog_eval,
            cands, top, second, prov, hs_confirmed, path,
            user_supplied=False, label_attributes=None, allow_web=True,
            gl=None, allow_claude=False, ingredients=None,
            category=None) -> dict:
    """اجمع الأدلّةَ في قرارٍ واحد — الفرعُ الوحيد الذي يُنتِج رمزاً نهائياً."""
    from silk_hs_confirm import axis_disambiguation_needed

    def out(candidates=None, **kw):
        return _contract(product_name=name, normalized_product=normalized,
                         candidate_codes=(cands if candidates is None
                                          else candidates),
                         catalog_hs_code=catalog or (catalog_raw or None),
                         provenance=prov, **kw)

    # درجةُ أعلى مرشّحٍ — تُعلَن باسمها في كل فرع رفضٍ أدناه: الرفضُ سببُه
    # تعادلٌ/محورٌ/تعارض لا «ثقةٌ دون العتبة»، والدرجةُ لا تتنكّر «ثقةً».
    # `cands` مرتَّبة تنازلياً، فصدرُها أعلى المُقيَّمين حين لا مؤهَّل (`top`).
    top_score = float(top["score"]) if top else (
        float(cands[0]["score"]) if cands else 0.0)

    from silk_hs_resolver import chapter_valid
    if catalog and not chapter_valid(catalog):
        return out(classification_status=REQUIRES_CONFIRMATION,
                   catalog_hs_status=CATALOG_REJECTED,
                   refusal_code=REFUSAL_CATALOG_REJECTED,
                   reason="الرمز المدخل غير صالح بنيوياً؛ التأكيد لا يصحّح رمزاً غير موجود.")

    # ── التأكيد لا يتجاوز صحة بنية الرمز ──
    if hs_confirmed and catalog:
        ev = catalog_eval or {}
        prov.append({"step": "decision", "source": "human",
                     "detail": "hs_confirmed=true"})
        return out(final_hs_code=catalog,
                   official_hs_description=_official_description(catalog),
                   # **الثقةُ تبقى مقيسةً** ولا تُرفَع إلى 1.0: التأكيدُ يعتمد
                   # الرمزَ ولا يختلق دليلاً لم يوجد (البند ٤).
                   confidence=float(ev.get("score") or 0.0),
                   classification_status=APPROVED,
                   classification_method=METHOD_USER_CONFIRMED,
                   catalog_hs_status=CATALOG_AUTO_APPROVED,
                   matched_attributes=list(ev.get("matched_attributes") or []),
                   contradictions=list(ev.get("contradictions") or []),
                   reason="اعتمد المصنعُ هذا البند صراحةً.")

    # ── رمزُ كتالوجٍ باطلُ الشكل أو خارجَ المرجع/النطاق ⇒ يُرفَض ويُصنَّف مستقلاً ──
    if catalog_raw and not catalog:
        prov.append({"step": "catalog_revalidation", "source": "catalog",
                     "detail": "malformed hs code"})
        return out(refusal_code=REFUSAL_CATALOG_REJECTED,
                   classification_status=REQUIRES_CONFIRMATION,
                   catalog_hs_status=CATALOG_REJECTED,
                   top_candidate_score=top_score,
                   reason=f"رمزُ الكتالوج «{catalog_raw}» ليس رمزاً جمركياً "
                          "سداسيّ الأرقام — أدخل رمزاً صحيحاً أو اختر بنداً.")
    if catalog and catalog_eval and catalog_eval["contradictions"] \
            and catalog_eval["confirmed"] is None:
        # غيرُ موجودٍ في المرجع أصلاً/فصلٌ باطل — رفضٌ صريح لا حجبٌ غامض.
        return out(refusal_code=REFUSAL_CATALOG_REJECTED,
                   classification_status=REQUIRES_CONFIRMATION,
                   catalog_hs_status=CATALOG_REJECTED,
                   top_candidate_score=top_score,
                   contradictions=catalog_eval["contradictions"],
                   reason=f"رمزُ الكتالوج {catalog} لا يصلح أساساً للدراسة: "
                          + "؛ ".join(catalog_eval["contradictions"]))

    # ── تعادلٌ بين الأول والثاني ⇒ سؤالٌ لا حسم (البند ١١) ──
    if top and second and (top["score"] - second["score"]) < min_separation():
        prov.append({"step": "separation",
                     "source": f"min_separation={min_separation()}",
                     "detail": f"{top['hs6']}={top['score']} vs "
                               f"{second['hs6']}={second['score']}"})
        return out(refusal_code=REFUSAL_UNRESOLVED,
                   classification_status=REQUIRES_CONFIRMATION,
                   catalog_hs_status=(CATALOG_REQUIRES_CONFIRMATION if catalog
                                      else CATALOG_ABSENT),
                   confidence=float(top["score"]),
                   top_candidate_score=top_score,
                   reason=f"بندان متقاربان في الدليل ({top['hs6']} و"
                          f"{second['hs6']}) — الفارقُ بينهما أصغر من أن "
                          "يحسم. اختر البند المطابق.")

    # ── التباسُ المحور الرقميّ (نسبةُ دهن/حالةُ حفظ) ⇒ سؤال ──
    if top and axis_disambiguation_needed(name, top["hs6"], path):
        prov.append({"step": "axis", "source": "silk_hs_confirm",
                     "detail": f"{top['hs6']} sits on a numeric axis"})
        siblings = _axis_candidates(name, top["hs6"], cands)
        # **القياسُ يسبق السؤال** (بلاغ المُشرِف): العتبةُ الرقمية التي تفصل
        # بنودَ الترويسة رقمٌ **يُجيب عنه المنتجُ نفسُه** — بطاقةُ العبوة تحمله
        # واستعلامُ ويبٍ واحد يستشهد به. فالحوارُ احتياطٌ لا افتراض، ولا يُسأل
        # المصنعُ عمّا نستطيع قياسَه.
        probe = _probe_axis(name, siblings, label_attributes, allow_web, gl)
        if probe.get("hs6"):
            prov.append({"step": "attribute_probe",
                         "source": probe.get("resolved_from") or "probe",
                         "detail": f"{probe['hs6']} = {probe.get('value')}"})
            return out(candidates=siblings, final_hs_code=probe["hs6"],
                       official_hs_description=_official_description(
                           probe["hs6"]),
                       probe_report=probe.get("report"),
                       confidence=float(top["score"]),
                       classification_status=APPROVED,
                       classification_method=METHOD_TOKEN,
                       catalog_hs_status=(CATALOG_AUTO_APPROVED if catalog
                                          else CATALOG_ABSENT),
                       matched_attributes=top["matched_attributes"],
                       reason="حُسِم البندُ بالسمة الرقمية المقيسة من "
                              + str(probe.get("resolved_from") or "الدليل")
                              + " — بلا سؤالٍ للمصنع.")
        if user_supplied and catalog and any(c["hs6"] == catalog
                                             for c in siblings):
            # الدليلُ النصّيّ حسم **الترويسة** (مصطلحُ العائلة)، والإنسانُ حسم
            # **البند** داخلها — وهو الفارقُ الرقميّ الذي لا يحمله أيُّ اسم.
            # فالثقةُ المعروضة ثقةُ الترويسة المقيسة، لا رقمٌ مختلَق للبند.
            prov.append({"step": "decision", "source": "human",
                         "detail": f"user-typed {catalog} answers the axis"})
            return out(candidates=siblings, final_hs_code=catalog,
                       official_hs_description=_official_description(catalog),
                       confidence=float(top["score"]),
                       classification_status=APPROVED,
                       classification_method=METHOD_USER_CONFIRMED,
                       catalog_hs_status=CATALOG_AUTO_APPROVED,
                       matched_attributes=top["matched_attributes"],
                       reason="اختار المشغّلُ البندَ داخل الترويسة صراحةً — "
                              "الفارقُ بين بنودها رقمٌ يعرفه عن منتجه.")
        return out(refusal_code=REFUSAL_AXIS,
                   candidates=siblings,
                   attribute_probe=probe.get("public"),
                   classification_status=REQUIRES_CONFIRMATION,
                   catalog_hs_status=(CATALOG_REQUIRES_CONFIRMATION if catalog
                                      else CATALOG_ABSENT),
                   confidence=float(top["score"]),
                   top_candidate_score=top_score,
                   reason=f"البند {top['hs6']} داخل ترويسةٍ تنقسم بسمةٍ رقمية "
                          "(نسبةُ الدهن أو حالةُ الحفظ) واسمُ المنتج لا يحدّد "
                          "أيّها — اختر البند المطابق.")

    # ── مصالحةُ الكتالوج مع المُحلِّل (البند ٢) ──
    if catalog:
        if top and top["hs6"] == catalog:
            prov.append({"step": "decision", "source": "catalog+classifier",
                         "detail": "agree"})
            return out(final_hs_code=catalog,
                       official_hs_description=_official_description(catalog),
                       confidence=float(top["score"]),
                       classification_status=APPROVED,
                       classification_method=METHOD_CATALOG_AGREEMENT,
                       catalog_hs_status=CATALOG_AUTO_APPROVED,
                       matched_attributes=top["matched_attributes"],
                       reason="رمزُ الكتالوج يوافق ما يعيده المُحلِّل مستقلاً "
                              "على هذا الاسم.")
        if (top and top["hs6"] != catalog and user_supplied
                and catalog[:4] == top["hs6"][:4]
                and not (catalog_eval or {}).get("hard_contradiction")):
            # **تنقيحٌ داخل الترويسة، لا خلاف.** الدليلُ النصّيّ أثبت الترويسة
            # (أربعةُ أرقام)؛ أمّا أيُّ بندٍ داخلها فغالباً فارقٌ لا يحمله اسمُ
            # المنتج أصلاً (مطبوخ/غير مطبوخ، نسبةُ دهن)، والمرجعُ يعلّق كلمتَه
            # العربية على بندٍ واحدٍ منها مصادفةً. رفضُ اختيار إنسانٍ حاضرٍ
            # لهذا السبب يعاقبه على فجوةِ تغطيةٍ عندنا. رمزُ الكتالوج **لا**
            # ينال هذا (الدرس ١٢٠: 040110 المخزَّن ضد 040120 — لا إنسانَ خلفه).
            ev = catalog_eval or {}
            prov.append({"step": "decision", "source": "human",
                         "detail": f"{catalog} refines heading "
                                   f"{top['hs6'][:4]}"})
            return out(final_hs_code=catalog,
                       official_hs_description=_official_description(catalog),
                       confidence=float(top["score"]),
                       classification_status=APPROVED,
                       classification_method=METHOD_USER_CONFIRMED,
                       catalog_hs_status=CATALOG_AUTO_APPROVED,
                       matched_attributes=top["matched_attributes"],
                       contradictions=list(ev.get("contradictions") or []),
                       reason=f"اختار المشغّلُ البند {catalog} داخل الترويسة "
                              f"{top['hs6'][:4]} التي أثبتها الدليل.")
        if top and top["hs6"] != catalog:
            prov.append({"step": "decision", "source": "catalog+classifier",
                         "detail": f"conflict {catalog} vs {top['hs6']}"})
            return out(refusal_code=REFUSAL_CONFLICT,
                       classification_status=REQUIRES_CONFIRMATION,
                       catalog_hs_status=CATALOG_CONFLICT,
                       confidence=float(top["score"]),
                       top_candidate_score=top_score,
                       contradictions=list(
                           (catalog_eval or {}).get("contradictions") or []),
                       reason=f"رمزُ الكتالوج {catalog} يخالف ما يعيده "
                              f"المُحلِّل لهذا الاسم ({top['hs6']}) — لن "
                              "يُختار أحدُهما صامتاً. اختر البند الصحيح.")
        # لا مرشّحَ مستقلٌّ مقبول: رمزُ الكتالوج يُعتمَد **بدليله وحده** إن بلغ
        # العتبةَ بلا تناقض؛ وإلا يُسأل. لا اعتمادَ لمجرّد أنه مخزَّن.
        ev = catalog_eval or {}
        if ev.get("offer") and ev.get("score", 0.0) >= min_confidence():
            prov.append({"step": "decision", "source": "catalog",
                         "detail": "catalog validated on its own evidence"})
            return out(final_hs_code=catalog,
                       official_hs_description=_official_description(catalog),
                       confidence=float(ev["score"]),
                       classification_status=APPROVED,
                       classification_method=METHOD_TOKEN,
                       catalog_hs_status=CATALOG_AUTO_APPROVED,
                       matched_attributes=ev.get("matched_attributes") or [],
                       reason="رمزُ الكتالوج اجتاز التحقّق الدلاليّ على اسم "
                              "المنتج نفسه.")
        return out(refusal_code=REFUSAL_UNRESOLVED,
                   classification_status=REQUIRES_CONFIRMATION,
                   catalog_hs_status=CATALOG_REQUIRES_CONFIRMATION,
                   confidence=float(ev.get("score") or 0.0),
                   top_candidate_score=top_score,
                   contradictions=list(ev.get("contradictions") or []),
                   reason=_ask_reason(name, cands, catalog))

    # ── لا كتالوج: قرارُ المُحلِّل وحده ──
    if top:
        method = (METHOD_EXACT if top["lexical_score"] >= 1.0
                  else METHOD_TOKEN)
        prov.append({"step": "decision", "source": "classifier",
                     "detail": f"{top['hs6']} @ {top['score']}"})
        return out(final_hs_code=top["hs6"],
                   official_hs_description=top["official_description"],
                   confidence=float(top["score"]),
                   classification_status=APPROVED,
                   classification_method=method,
                   catalog_hs_status=CATALOG_ABSENT,
                   matched_attributes=top["matched_attributes"],
                   reason="وصفُ البند يشمل صفاتِ المنتج المميّزة، ولا مرشّحَ "
                          "يقاربه في الدليل.")
    # ── المخرجُ الثالث: مصنّفٌ مُرسًى، حين يعجز المعجم ولا صورة ──────────
    # **هنا وحدها.** لا يُستشار النموذجُ في تعارضِ كتالوجٍ (قرارُ إنسان) ولا
    # على محورٍ رقميّ (يُجيب عنه المنتجُ نفسُه)، ولا حين حسم المعجمُ مجّاناً —
    # فالكلفةُ تقع على الإخفاق وحده. قرارُ المالك 2026-08-30 بعد قياس تغطيةٍ
    # عربية بلغت ٢٫٦٪ (وصفراً في فصول الآلات والكهرباء والكيماويات).
    if allow_claude:
        settled = _llm_fallback(name, ingredients, category, prov)
        if settled is not None:
            return out(**settled)
    return out(refusal_code=REFUSAL_UNRESOLVED,
               classification_status=REQUIRES_CONFIRMATION,
               catalog_hs_status=CATALOG_ABSENT,
               confidence=float(cands[0]["score"]) if cands else 0.0,
               top_candidate_score=top_score,
               reason=_ask_reason(name, cands, None))


def _axis_candidates(product: str, hs6: str, evaluated: list[dict]
                     ) -> list[dict]:
    """أشقّاءُ المحور الرقميّ كاملين، كلٌّ بحدّه بلغةٍ مفهومة.

    البند ١٧: خيارٌ بلا حدِّه ليس خياراً — «040110/040120/040150» أرقامٌ
    للمصنع ما لم يقل كلٌّ منها «حتى ١٪» و«أكثر من ١٪ وحتى ٦٪». الحدودُ من
    `silk_hs_dialog` (تُصاغ من الوصف الرسميّ)، والدليلُ المقيس يُنقَل كما هو
    لمن قِيس منهم — ولا يُختلَق لمن لم يُقَس (`score=0.0`).
    """
    try:
        import silk_hs_dialog
        rows = silk_hs_dialog.build_candidates(product, [hs6])
    except Exception as exc:  # noqa: BLE001 — إثراءُ عرضٍ لا شرطُ قرار
        log.warning("axis sibling expansion failed for %s: %s", hs6, exc)
        return evaluated
    by_code = {c["hs6"]: c for c in evaluated}
    out: list[dict] = []
    for r in rows:
        code = str(r.get("hs6") or "").strip()
        if not code:
            continue
        ev = by_code.get(code) or {}
        out.append({
            "hs6": code,
            "description": r.get("description_ar") or ev.get("description") or "",
            "official_description": (r.get("description_ar")
                                     or ev.get("official_description") or ""),
            "band_ar": r.get("band_ar") or "",
            "lexical_score": ev.get("lexical_score", 0.0),
            "semantic_overlap": ev.get("semantic_overlap"),
            "score": ev.get("score", 0.0),
            "confirmed": ev.get("confirmed"),
            "matched_attributes": ev.get("matched_attributes") or [],
            "missing_attributes": ev.get("missing_attributes") or [],
            "contradictions": ev.get("contradictions") or [],
            # علمُ الإكمال يُنقَل لا يُسقَط: عليه يقوم حارسُ `resolve_or_probe`
            # الذي يُبقي صفوفَ الإكمال خارج المُحلِّل الرقمي (نهيُ المُشرِف عن
            # توسيع التغطية من الباب الخلفي). وشرطُ `code not in by_code` لازم:
            # هنا تُستدعى `build_candidates` بـrequested=[top] وحده — بخلاف
            # مسار confirm حيث requested هي القائمة المسترجَعة كاملة — فشقيقٌ
            # استُرجع وقُيِّم فعلاً (حاضر في by_code بدرجات حقيقية) ليس صفَّ
            # إكمالٍ ولا يُحرَم من المجسّ.
            "axis_completion": bool(r.get("axis_completion")) and code not in by_code,
            # كلُّ أشقّاء المحور خياراتٌ مشروعة تُعرَض — الفارقُ بينها رقمٌ
            # يعرفه المصنعُ عن منتجه، لا دليلٌ نصّيٌّ نملكه نحن.
            "offer": True,
            "reason_ar": r.get("reason_ar") or "",
        })
    return out or evaluated


def _catalog_lexical(product: str, hs6: str, path: str) -> float:
    """الرتبةُ اللفظية لرمزٍ بعينه — صفرٌ إن لم يكن في المرجع (فجوة معلنة)."""
    from silk_hs_confirm import _rows_by_code
    from silk_hs_resolver import _score
    row = _rows_by_code(path).get(hs6)
    return _score(product, row) if row else 0.0


def _probe_axis(product: str, siblings: list[dict], label_attributes,
                allow_web: bool, gl: str | None) -> dict:
    """قِس السمةَ الرقمية من بطاقة العبوة ثمّ من الويب — أو أعِد ما نقص.

    غلافٌ رقيق حول `silk_hs_confirm.resolve_or_probe` (نقطةُ القياس القائمة،
    لا نسخةٌ ثانية منها). أيُّ تعذّرٍ يعود بلا رمز — القياسُ تحسينٌ لا شرطٌ،
    والسؤالُ يبقى المَخرجَ حين لا يُقاس شيء.
    """
    try:
        from silk_hs_confirm import _probe_public, resolve_or_probe
        report = resolve_or_probe(product, siblings,
                                  label_attributes=label_attributes,
                                  allow_web=allow_web, gl=gl)
        return {"hs6": report.get("hs6"),
                "value": report.get("value"),
                "resolved_from": report.get("resolved_from"),
                # التقريرُ الكامل (بمصدره وثقته وقراءاته) — يُحمَل في
                # العقد فيُقدَّم provenance بلا قياسٍ ثانٍ (المهمة ١٤).
                "report": report,
                "public": _probe_public(report)}
    except Exception as exc:  # noqa: BLE001 — القياسُ تحسينٌ لا شرطُ قرار
        log.warning("attribute probe failed for %r: %s", product, exc)
        return {}


def _llm_fallback(product: str, ingredients, category,
                  prov: list[dict]) -> dict | None:
    """اسأل المصنّفَ العام المُرسى — أو `None` حين لا يحسم (فيبقى السؤال).

    **لماذا يُوثَق بـ`tier == "auto"` هنا** ولا يُعاد قياسُه بتداخلٍ عربيّ:
    `classify_general` يُرسي مرشّحَ النموذج على وصفه هو (`_validated_candidate`
    ← `confirm_against_description`) ويشترط تداخلاً ≥ `SILK_HS_AUTO_MIN_OVERLAP`
    **وهامشاً واضحاً** على الثاني. أمّا إعادةُ القياس بمفاتيح المرجع العربية
    فدائريّةٌ بالتعريف: هذه الصفوفُ بلا مفاتيح عربية أصلاً — وذلك سببُ وجود
    هذا المخرج. الدرس ٢٠٩ حسم القاعدة نفسها لمسار الصورة: `auto` وحدها.

    وما **لا** يُعفى منه جوابُ النموذج: الحرّاسُ البنيويّة التي لا تعتمد
    المعجمَ إطلاقاً — شكلُ الرمز، وفصلٌ حقيقيّ في بنية WCO، ونطاقُ سِلك غير
    النفطيّ، ووجودُه في المرجع الرسميّ. «مُرسًى» تعني هذا حرفياً لا وصفاً.

    الثقةُ المُعادة **مقيسة** (تداخلُ صفات المنتج مع وصف النموذج) لا مختلَقة،
    والطريقةُ تُسمّى `llm_grounded` فيُقرأ أساسُ القرار بعد شهر.
    """
    from silk_hs_confirm import _negation_conflict, _process_state_conflict
    from silk_hs_resolver import chapter_valid, exclusion_note

    try:
        import silk_hs_classifier as _hsc
        out = _hsc.classify_general(product, ingredients=ingredients,
                                    category=category, allow_claude=True)
    except Exception as exc:  # noqa: BLE001 — عطلُ مزوّدٍ = سؤالٌ لا انهيار
        log.warning("grounded classifier unavailable for %r: %s", product, exc)
        prov.append({"step": "llm_fallback", "source": "classify_general",
                     "detail": f"unavailable: {type(exc).__name__}"})
        return None

    hs6 = _valid_hs6((out or {}).get("hs6"))
    tier = str((out or {}).get("tier") or "")
    if tier != "auto" or not hs6:
        prov.append({"step": "llm_fallback", "source": "classify_general",
                     "detail": f"tier={tier or 'none'} — not settled"})
        return None

    # الحرّاسُ البنيويّة على جواب النموذج.
    if not chapter_valid(hs6) or exclusion_note(hs6):
        prov.append({"step": "llm_fallback", "source": "classify_general",
                     "detail": f"{hs6} rejected by a structural guard"})
        return None
    official = _official_description(hs6)
    if not official:
        # غيرُ موجودٍ في المرجع الرسميّ ⇒ لا يُبنى عليه إنفاق (عقد عدم الاختلاق).
        prov.append({"step": "llm_fallback", "source": "classify_general",
                     "detail": f"{hs6} absent from the official reference"})
        return None
    p_terms = _norm.tokens(product)
    clash = (_negation_conflict(p_terms, official)
             or _process_state_conflict(p_terms, official))
    if clash:
        prov.append({"step": "llm_fallback", "source": "classify_general",
                     "detail": f"{hs6} contradicts the product: {clash[:60]}"})
        return None

    top = next((c for c in (out.get("candidates") or [])
                if str(c.get("hs6") or "").strip() == hs6), {})
    measured = top.get("overlap")
    if not isinstance(measured, (int, float)):
        measured = out.get("confidence")
    confidence = float(measured or 0.0)
    if confidence < min_confidence():
        prov.append({"step": "llm_fallback", "source": "classify_general",
                     "detail": f"{hs6} measured {confidence:.2f} below threshold"})
        return None

    prov.append({"step": "llm_fallback", "source": "classify_general",
                 "detail": f"{hs6} @ {confidence:.2f} (tier=auto)"})
    return {
        "final_hs_code": hs6,
        "official_hs_description": official,
        "confidence": confidence,
        "classification_status": APPROVED,
        "classification_method": METHOD_LLM_GROUNDED,
        "catalog_hs_status": CATALOG_ABSENT,
        "matched_attributes": list(top.get("shared_terms") or []),
        "reason": "حُسِم البندُ بمصنّفٍ مُرسًى على المرجع الرسميّ بعد أن عجز "
                  "المعجمُ العربيّ عن حمل هذا المنتج.",
    }


def _ask_reason(name: str, cands: list[dict], catalog: str | None) -> str:
    """نصُّ الطلب — **يتبع القائمةَ الفعلية** ولا يَعِد بما لا يوجد (الدرس ٢٠٦).

    ذيلٌ يقول «اختر من المرشّحين» فوق قائمةٍ خالية هو الطريقُ المسدود الذي
    رآه المالك حرفياً. هنا النصُّ يُشتقّ من عدد المعروضين لا من فرعٍ ثابت.
    """
    offered = [c for c in cands if c["offer"]]
    head = (f"رمزُ الكتالوج {catalog} لم يجتز التحقّق على اسم المنتج «{name}»"
            if catalog else f"تعذّر حسمُ البند الجمركي للمنتج «{name}»")
    if offered:
        return (head + " — اختر البند المطابق من البنود المعروضة، "
                "أو أدخل رمزَك الجمركي.")
    return (head + " — لا بندَ يطابق هذا الاسم في المرجع الرسمي. اكتب وصفَ "
            "المنتج نفسه (نوعه ومادّته لا اسم علامته)، أو ارفع صورةَ العبوة، "
            "أو أدخل رمزَك الجمركي.")


def result_summary(result: dict) -> dict:
    """ملخّصُ التصنيف المُرفَق بالنتيجة — حاملُ الإفصاح، لا نسخةُ العقد كاملاً.

    التوثيق يَعِد بأن التناقضات «تبقى معلنةً فتعرضها طبقةُ العرض». وعدٌ بلا
    حاملٍ في النتيجة هو نفسُ عائلة الدرس ٢٠٦ (نصٌّ يحيل إلى ما لا يوجد): تقريرٌ
    بُني على رمزٍ أكّده المصنعُ رغم تعارضه **يجب** أن يقول ذلك على وجهه.

    مقصوصٌ عمداً: لا مرشّحين ولا أدلّة لكلّ صفّ — النتيجةُ تُخزَّن مع كل تحليل،
    فحمولةٌ ثقيلة هنا تُضاعف كل صفٍّ في القاعدة بلا قارئ.
    """
    return {
        "classification_status": result.get("classification_status"),
        "classification_method": result.get("classification_method"),
        "catalog_hs_code": result.get("catalog_hs_code"),
        "catalog_hs_status": result.get("catalog_hs_status"),
        "confidence": result.get("confidence"),
        "contradictions": list(result.get("contradictions") or []),
        "official_hs_description": result.get("official_hs_description") or "",
        "normalized_product": result.get("normalized_product") or "",
    }


def diagnostics(result: dict) -> dict:
    """لقطةٌ بنيويّة للسجلّ — البند ٢٢، بلا أيّ سرّ ولا حمولةٍ ثقيلة."""
    return {
        "product": result.get("product_name"),
        "normalized_product": result.get("normalized_product"),
        "catalog_hs": result.get("catalog_hs_code"),
        "catalog_hs_status": result.get("catalog_hs_status"),
        "candidate_count": len(result.get("candidate_codes") or []),
        "top_candidates": [c["hs6"] for c in
                           (result.get("candidate_codes") or [])[:3]],
        "scores": result.get("candidate_scores"),
        "semantic_validation": [
            {"hs6": c["hs6"], "confirmed": c["confirmed"],
             "overlap": c["semantic_overlap"]}
            for c in (result.get("candidate_codes") or [])[:3]],
        "contradictions": result.get("contradictions"),
        "final_hs": result.get("final_hs_code"),
        "confidence": result.get("confidence"),
        "decision": result.get("classification_status"),
        "classification_method": result.get("classification_method"),
    }


if __name__ == "__main__":  # فحصٌ يدويّ — عيّناتُ الحوادث المرصودة
    logging.basicConfig(level=logging.INFO)
    for sample, cat in [("حلاوة طحينية", "170490"), ("حلاوة طحينية", None),
                        ("مناديل ورقية", None), ("سمسم", None),
                        ("طحينة", None), ("زبدة الفول السوداني", None)]:
        r = classify(sample, cat)
        print(f"{sample:22} catalog={cat or '—':7} => "
              f"{r['final_hs_code']} conf={r['confidence']:.2f} "
              f"{r['classification_status']} / {r['catalog_hs_status']}")
