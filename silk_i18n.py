"""طبقة اللغة الواحدة — the ONE server-side language layer (الموجة ٠).

> **الغرض.** لغة المصنع المحفوظة تحكم لغة التقرير المولَّد. هذه الوحدة هي
> المصدر الواحد لثلاثة أشياء لا رابعَ لها:
>   ١) **قاموس المصطلحات القانوني** `TERMS` — مفهومٌ واحد ⇒ مفتاحٌ واحد ⇒
>      تسميتان (عربية/إنجليزية). فيستحيل أن يظهر المفهوم نفسه بلفظين مختلفين
>      في تقريرٍ واحد.
>   ٢) **حلّ اللغة** `normalize` / `is_rtl` — أيّ مدخلٍ غير `"en"` يسقط إلى
>      `"ar"` (افتراضٌ آمن: لا ينقلب تقريرٌ قائم بصمت).
>   ٣) **كاشف تسرّب اللغة** `foreign_prose_spans` — يكشف النثر بلغةٍ خطأ على
>      سطح العميل، باستثناءٍ **بنيويّ صريح** لا يُخمَّن (أسماء علامات/شركات/
>      منتجات/مصادر رسمية، روابط، رموز HS، معرّفات تقنية، اختصارات معيارية).
>
> **ما ليس من شأن هذه الوحدة.** لا تحسب رقماً، ولا تعيد تفسير قيمة، ولا تترجم
> تقريراً مولَّداً. اللغة **شأن عرضٍ لا شأن تحليل** (§17 من أمر العمل): طبقةُ
> الأدلة والحساب والقرار محايدةٌ لغوياً، والعارضان يستهلكان الكائن القانوني
> نفسه. أي حسابٍ هنا خرقٌ للتصميم.
>
> **The ONE language layer.** The factory's stored language decides the report
> language. This module owns the canonical terminology dictionary, language
> resolution, and the wrong-language leak detector — nothing else. Language is
> a rendering concern, never an analytical one.

عقد عدم الاختلاق يبقى: مفتاحٌ ناقص من `TERMS` يرفع `KeyError` عالياً — لا
يُختلَق نصّ بديل ولا تُعاد السلسلة الخام كأنها ترجمة.
"""
from __future__ import annotations

import os
import re

# ── ١) اللغات المدعومة وحلّها · supported languages and resolution ──────────

LANGS = ("ar", "en")
DEFAULT_LANG = "ar"

# نسخة مخطّط التقرير ومحرّكه — تُختَم في البيانات الوصفية للمصنوع (§14) كي
# يُعرَف **بأيّ عقدٍ** وُلِّد تقريرٌ قديم عند مراجعته لاحقاً.
REPORT_SCHEMA_VERSION = "silk.report/v1"
REPORT_ENGINE_VERSION = "silk.i18n/1.0"


def report_language_enabled() -> bool:
    """صمّام الطبقة (البند ٩١) — `SILK_REPORT_LANGUAGE_ENABLED=0` يعيد سلوك ما
    قبل الموجة حرفياً: كل توليدٍ بالعربية مهما كان إعداد المصنع.

    الافتراض ON. صمّام إطفاءٍ فوريّ في الإنتاج بلا نشر.
    """
    raw = os.environ.get("SILK_REPORT_LANGUAGE_ENABLED", "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def normalize(raw: object) -> str:
    """أعِد لغةً مدعومة من أيّ مدخل — `"en"` أو `"ar"`.

    كل ما ليس إنجليزيةً صريحة ⇒ عربية. الافتراض الآمن مقصود: قيمةٌ تالفة أو
    فارغة أو لغةٌ غير مدعومة لا يجوز أن تقلب تقريراً كان عربياً.
    """
    if not report_language_enabled():
        return DEFAULT_LANG
    text = str(raw or "").strip().lower()
    # يقبل "en", "en-US", "eng" — ولا يقبل ما عداها.
    if text == "en" or text.startswith("en-") or text == "eng":
        return "en"
    return DEFAULT_LANG


def is_rtl(lang: str) -> bool:
    """هل هذه اللغة من اليمين لليسار؟ — يقرّر تفريعة الاتجاه في المصدِّرات."""
    return normalize(lang) == "ar"


# ── ٢) قاموس المصطلحات القانوني · the canonical terminology dictionary ──────
#
# مفتاحٌ قانونيّ واحد لكل مفهوم، وتسميتان. القاعدة الحاكمة: **لا ترجمةَ عشوائية
# للمفهوم نفسه داخل التقرير** (§8 من أمر العمل). كل نصٍّ قالبيّ على سطح العميل
# يُبنى من هنا، لا من سلسلةٍ مكتوبةٍ في موضع الاستعمال.
#
# الإنجليزية مكتوبةٌ **أصالةً** بلغة أعمالٍ دولية طبيعية، لا مترجمةً حرفياً عن
# العربية (§34): «Market Entry» لا «Entering the market».

TERMS: dict[str, dict[str, str]] = {
    # ══ الموجة C · حالاتٌ جديدة تصل المصنع — بلغةِ أعمالٍ لا لغةِ نظام ═════
    #
    # القيدُ الحاكم (أمر المالك): الصحّةُ التحليلية لا تُشترى بقابلية القراءة.
    # كلُّ رسالةٍ هنا مكتوبةٌ **أصالةً** في اللغتين (لا ترجمةَ آليّة)، وتتبع
    # البنية الخماسية: خلاصة ← سبب ← دليل ← أثر ← الفعل المطلوب. فيعرف صاحبُ
    # المصنع فوراً: ما المعلوم، ما غيرُ المؤكَّد، لماذا يهمّ، ما الذي يحجب
    # القرار، وما المطلوب منه. لا معرّفاتٍ داخلية ولا أسماءَ دوالّ ولا رموزَ
    # حالة — تلك تُحجَب بنيوياً بـ`_CLIENT_FORBIDDEN_PATTERNS` ومرآتِها.

    # ── الحاجز التنظيميّ ──────────────────────────────────────────────────
    "reg_block_head": {
        "ar": "ما يمنع الشحن اليوم",
        "en": "What blocks shipping today"},
    "reg_block_lead": {
        "ar": "لا يمكن الشحن إلى {market} قبل حسم هذا البند.",
        "en": "You cannot ship to {market} until this is resolved."},
    "reg_block_why": {
        "ar": "السبب أن {authority} تشترطه شرطَ دخولٍ لا إجراءً تنظيمياً "
              "لاحقاً.",
        "en": "The reason is that {authority} treats it as a condition of "
              "entry, not paperwork you can finish later."},
    "reg_block_impact": {
        "ar": "وأثر ذلك أن الشحنة تُرفض عند الحدود — لا أن تتأخر أو تُغرَّم.",
        "en": "The impact is that the shipment is refused at the border — "
              "not delayed, and not fined."},
    "reg_block_action": {
        "ar": "المطلوب: ابدأ هذا الملف قبل أي التزام تجاري مع مشترٍ في هذا "
              "السوق.",
        "en": "What to do: start this file before you commit commercially to "
              "any buyer in this market."},
    "reg_verify_head": {
        "ar": "بنود يجب التأكد منها قبل الالتزام",
        "en": "Points to confirm before you commit"},
    "reg_verify_lead": {
        "ar": "هذا البند قد ينطبق على منتجك وقد لا ينطبق، ولا نستطيع حسمه من "
              "رمز المنتج وحده.",
        "en": "This requirement may or may not apply to your product, and the "
              "product code alone cannot settle it."},
    "reg_verify_why": {
        "ar": "الحسم يحتاج دليلاً عن المنتج نفسه — تركيبته أو تحليل مختبر أو "
              "إدراج فئته في قوائم السوق.",
        "en": "Settling it needs evidence about the product itself — its "
              "composition, a lab analysis, or how its category is listed."},
    "reg_verify_impact": {
        "ar": "لم نفترض أنه لا ينطبق: سكوتنا عنه كان سيُقرأ ضماناً لم نرصده.",
        "en": "We did not assume it away: staying silent would have read as a "
              "guarantee we never verified."},
    "reg_verify_action": {
        "ar": "المطلوب: اسأل {authority} عن انطباقه على منتجك تحديداً قبل "
              "التسعير النهائي.",
        "en": "What to do: ask {authority} whether it applies to your specific "
              "product before you finalise pricing."},
    "reg_clear_note": {
        "ar": "راجعنا اشتراطات الدخول لهذا السوق ولم نجد بنداً يمنع الشحن.",
        "en": "We reviewed this market's entry requirements and found nothing "
              "that blocks shipping."},

    # ── دليلٌ غيرُ كافٍ · لا يُحسَب ──────────────────────────────────────────
    "insufficient_evidence": {
        "ar": "لم نجد بيانات كافية نثق بها لهذا البند، فتركناه مفتوحاً بدل أن "
              "نملأه بتقدير. الرقم المخمَّن هنا أسوأ من غيابه لأنه يدخل "
              "حساباتك ولا يمكنك تمييزه.",
        "en": "We did not find data we trust for this point, so we left it "
              "open instead of filling it with an estimate. A guessed number "
              "here is worse than none: it enters your maths and you cannot "
              "tell it apart."},
    "not_calculable": {
        "ar": "هذا الرقم غير قابل للحساب بالمعطيات المتاحة.",
        "en": "This figure cannot be calculated from what is available."},
    "not_calculable_why": {
        "ar": "ينقصه: {missing}.",
        "en": "What it needs: {missing}."},
    "not_calculable_action": {
        "ar": "زوّدنا بهذا المدخل وسنحسبه في التحديث القادم بلا تكلفة إضافية.",
        "en": "Give us this input and we will compute it in the next update "
              "at no extra cost."},

    # ── بيانٌ مُستَردّ ومتقادم ─────────────────────────────────────────────
    "recovered_value": {
        "ar": "هذا الرقم جاء من محاولة استرجاع ثانية بعد أن أخفقت الأولى — "
              "المصدر نفسه، والقيمة كما نشرها.",
        "en": "This figure came from a second retrieval attempt after the "
              "first failed — same source, value as published."},
    "recovered_derived": {
        "ar": "هذا الرقم محسوب لا منقول: {formula}. نعرضه لأنه مفيد، ونسمّيه "
              "محسوباً كي لا تعامله كرقم رسمي منشور.",
        "en": "This figure is computed, not reported: {formula}. We show it "
              "because it is useful, and we name it as computed so you do not "
              "treat it as an officially published number."},
    "stale_value": {
        "ar": "أحدث رقم منشور لهذا البند يعود إلى {year}، ولم يصدر أحدث منه.",
        "en": "The most recent published figure here is from {year}; nothing "
              "newer has been released."},
    "stale_impact": {
        "ar": "استعمله للاتجاه العام لا للتسعير الدقيق — السوق قد يكون تحرّك.",
        "en": "Use it for direction, not for precise pricing — the market may "
              "have moved since."},

    # ── تغطيةُ المصادر والثقة ────────────────────────────────────────────
    "coverage_head": {
        "ar": "على أي قدر من الأدلة يقوم هذا التقرير",
        "en": "How much evidence this report rests on"},
    "coverage_good": {
        "ar": "{pct}٪ من أرقام هذا التقرير مسنودة إلى مصدر منشور يمكنك فتحه.",
        "en": "{pct}% of the figures in this report trace to a published "
              "source you can open."},
    "coverage_low": {
        "ar": "{pct}٪ فقط من أرقام هذا التقرير مسنودة إلى مصدر منشور، وهي "
              "نسبة دون ما نعتبره كافياً للقرار.",
        "en": "Only {pct}% of the figures here trace to a published source — "
              "below what we consider enough to decide on."},
    "coverage_low_action": {
        "ar": "اقرأه استطلاعاً للسوق، ولا تبنِ عليه التزاماً تعاقدياً قبل "
              "التحقق من الأرقام الحرجة.",
        "en": "Read it as a scan of the market; do not base a contractual "
              "commitment on it before the critical figures are verified."},
    "confidence_because": {
        "ar": "الثقة {band} لأن {reason}.",
        "en": "Confidence is {band} because {reason}."},
    "confidence_reason_coverage": {
        "ar": "معظم الأرقام مسنودة إلى مصادر منشورة",
        "en": "most figures trace to published sources"},
    "confidence_reason_gaps": {
        "ar": "بنوداً أساسية بقيت بلا بيانات",
        "en": "core inputs remain without data"},
    "confidence_reason_stale": {
        "ar": "جزءاً من الأرقام يعود إلى سنوات سابقة",
        "en": "some figures date back to earlier years"},
    "confidence_reason_conflict": {
        "ar": "مصدرين رسميين يعطيان رقمين مختلفين لنفس البند",
        "en": "two official sources give different figures for the same item"},

    # ── حدودُ التسعير والاقتصاد ──────────────────────────────────────────
    "price_level_missing": {
        "ar": "هذا السعر بلا مستوى معلوم — لا نعرف هل هو سعر رفّ للمستهلك أم "
              "سعر جملة أم سعر عند الحدود.",
        "en": "This price has no known level — we cannot tell whether it is a "
              "consumer shelf price, a wholesale price, or a border price."},
    "price_level_impact": {
        "ar": "والفرق بينها أضعاف، فمقارنته بسعر تكلفتك تعطي هامشاً وهمياً.",
        "en": "The gap between those is several-fold, so comparing it with "
              "your cost produces an imaginary margin."},
    "price_level_action": {
        "ar": "المطلوب: عامِله مؤشراً على وجود سوق، لا أساساً لتسعيرك.",
        "en": "What to do: treat it as a signal that a market exists, not as "
              "the basis for your pricing."},
    "margin_needs_cost": {
        "ar": "لم نحسب هامشك لأننا لا نعرف تكلفة إنتاجك — وهي رقمك أنت لا رقم "
              "منشور نبحث عنه.",
        "en": "We did not compute your margin because we do not know your "
              "production cost — that is your number, not a published one we "
              "could look up."},
    "margin_needs_cost_action": {
        "ar": "أضف تكلفة الوحدة في ملف منتجك وسيظهر شلال الهامش كاملاً.",
        "en": "Add your unit cost to the product profile and the full margin "
              "breakdown will appear."},

    # ── القرار والحكم · decision ───────────────────────────────────────────
    "market_entry": {"ar": "دخول السوق", "en": "Market Entry"},
    "decision_blocker": {"ar": "مانع قرار", "en": "Decision Blocker"},
    "data_gap": {"ar": "فجوة بيانات", "en": "Data Gap"},
    "current_decision": {"ar": "الحكم الحالي", "en": "Current decision"},
    "decision_basis": {"ar": "أساس الحكم", "en": "Basis for the decision"},
    "counter_case": {"ar": "الحجة المضادة", "en": "The case against"},
    "flip_conditions": {"ar": "شرطا قلب الحكم", "en": "What would change this decision"},
    "upgrade_trigger": {"ar": "ما يرفع الحكم", "en": "Upgrade trigger"},
    "downgrade_trigger": {"ar": "ما يخفض الحكم", "en": "Downgrade trigger"},
    # تسميات الحكم — تُشتقّ من `silk_render._verdict_tone` حصراً.
    "verdict_go": {"ar": "التوصية بالدخول", "en": "Enter the market"},
    "verdict_conditional": {"ar": "دخول مشروط", "en": "Conditional entry"},
    "verdict_preliminary": {"ar": "توصية أولية بالدخول",
                            "en": "Preliminary recommendation to enter"},
    "verdict_watch": {"ar": "مراقبة السوق", "en": "Monitor the market"},
    "verdict_nogo": {"ar": "عدم الدخول حالياً", "en": "Do not enter at this time"},
    "verdict_inconclusive": {"ar": "نتيجة مبدئية — غير محسومة",
                             "en": "Preliminary — not conclusive"},
    "verdict_unknown": {"ar": "تعذّر إصدار توصية",
                        "en": "No recommendation could be issued"},
    # الموجة B (البند V-01): نبراتُ **حالةِ الأدلة** — تُستعمَل حين يكون
    # أساسُ الحكم تغطيةَ بعثاتٍ لا تقييمَ سوق، فلا يُقرأ نجاحُ خطّ الأنابيب
    # توصيةً تجارية ولا انقطاعُه نصيحةً بهجر السوق.
    "verdict_data_complete": {
        "ar": "اكتمل البحث — لم يصدر تقييمٌ تجاريّ بعد",
        "en": "Research complete — no commercial assessment issued yet"},
    "verdict_data_partial": {
        "ar": "بحثٌ ناقص — بعض المصادر لم تُجِب",
        "en": "Research incomplete — some sources did not respond"},
    "verdict_data_absent": {
        "ar": "تعذّر البحث — لا بيانات كافية لأيّ حكم",
        "en": "Research could not run — not enough data for any judgement"},
    # ── الثقة · confidence ─────────────────────────────────────────────────
    "confidence": {"ar": "درجة الثقة", "en": "Confidence"},
    "confidence_high": {"ar": "عالية", "en": "high"},
    "confidence_medium": {"ar": "متوسطة", "en": "medium"},
    "confidence_low": {"ar": "منخفضة", "en": "low"},
    # ── أقسام تقرير العميل · client report sections ────────────────────────
    # البند ٤ (هدف الدراسة الاحترافية): الملخص التنفيذي قسم عميل مستقل يفتتح
    # المستند — التوصية ثم أرقامها بمعانيها ثم المسار ثم الشرط الحاجب.
    "sec_exec_summary": {"ar": "الملخص التنفيذي", "en": "Executive summary"},
    "sec_decision": {"ar": "القرار وأساسه", "en": "The decision and its basis"},

    # ── الموجة Z · البند Z-06 — أساسُ الحكم يصل المصنع أخيراً ─────────────
    # الأعمدةُ الخمسة وأوزانُها وقاعدةُ الحكم والحجّةُ المضادّة كانت تُحسَب
    # كلَّ مرّة وتصل `view["decision"]` **ولا يعرضها أيُّ سطحِ عميل**: صفر
    # ذكرٍ في docx العميل، صفر في PDF، صفر في `web/platform.html`. المصنعُ
    # يقرأ حكماً بلا أن يعرف على أيّ شيءٍ بُني. النصّان مكتوبان أصالةً في
    # اللغتين، والنِّسَبُ بشرية لا كسورٌ آلية خام (الدرس ٩٢).
    "decision_basis_head": {
        "ar": "على أيّ أساس صدر هذا الحكم",
        "en": "What this decision rests on"},
    # البند ٣ (لغة الزائر): «الدرجة الموزونة … بثقة %» صيغت بجملة معنى —
    # القاعدة نفسها والعتبات نفسها، بلا مصطلح قياس داخلي على سطح العميل.
    "decision_rule_lead": {
        "ar": "قاعدة الحكم مُعلنة قبل النظر في الأرقام: نوصي بالمضي حين "
              "تبلغ قوة الفرصة {go} من 100 فأعلى وقد تحقّقنا من {conf}% من "
              "بياناتها فأعلى وبلا شروط مفتوحة؛ ونرفض حين تنزل القوة دون "
              "{nogo} أو عند اختلال أمان السوق؛ "
              "وما بينهما دخول مشروط بشروط مسمّاة أدناه.",
        "en": "The decision rule, stated before the numbers were weighed: we "
              "recommend proceeding when the opportunity strength reaches "
              "{go} out of 100 or more with {conf}% or more of its data "
              "directly verified and no open conditions; we decline "
              "when it falls below {nogo} or when market safety breaks down; "
              "anything in between is a conditional entry, with the "
              "conditions named below."},
    # هدف الدراسة الاحترافية (البند ٣ — لغة الزائر): هذه المفاتيح تغذّي
    # `decision_basis` الذي يقرؤه العميل على اللوحة وفي docx معاً — المصطلح
    # القياسي («العمود»/«الدرجة الموزونة»/«بثقة %»/«مرصود») يُستبدل بجملة
    # معنى تحفظ الرقم؛ المصطلح الداخلي يبقى لسطح المشغّل والملحق الفني.
    "pillar_col": {"ar": "الجانب", "en": "Aspect"},
    "pillar_strength_col": {"ar": "قوّته", "en": "Strength"},
    "pillar_note_col": {"ar": "ماذا يعني", "en": "What it means"},
    "pillar_not_computed": {"ar": "لا نعرفه بعد", "en": "Not known yet"},
    # D4 (دراسة #12، البند 16) ثم البند ٣: الغياب يُقال بما ينقصنا فعلاً.
    "pillar_missing_lead": {
        "ar": "ينقصنا: {parts} — أكمِلها قبل أي التزام.",
        "en": "We still need: {parts} — close these before committing."},
    "pillar_measured": {
        "ar": "تحقّقنا منه مباشرة من مصادره.",
        "en": "Verified directly from its sources."},
    "decision_weighted_line": {
        "ar": "قوة هذه الفرصة في تقييمنا {score} من 100، وقد تحقّقنا "
              "مباشرة من نحو {conf}% من البيانات خلف هذا التقييم.",
        "en": "We rate this opportunity {score} out of 100, and we "
              "directly verified about {conf}% of the data behind that "
              "rating."},
    # الشروطُ تُبنى **بنيوياً** من الأعمدة في اللغتين، لا من نثر المحرّك
    # العربيّ: نثرُه يُسقَط في تقريرٍ إنجليزيّ (الفصلُ الصلب §5) فيبقى القارئ
    # الإنجليزيّ بلا الشروط التي تَعِده قاعدةُ الحكم بها — وسطرُ العمود الضعيف
    # فيه معادلةُ حسابٍ بلغةِ مشغّل لا بلغةِ عميل.
    "cond_pillar_missing": {
        "ar": "جانب {pillar} لا نعرفه بعد — ينقصنا: {parts}. أكمِلها "
              "قبل أي التزام إنتاجي أو شحني.",
        "en": "The {pillar} aspect is not known yet — we still need: "
              "{parts}. Close these before you commit to "
              "production or shipping."},
    "cond_pillar_weak": {
        "ar": "جانب {pillar} ضعيف ({pct}%) — عالِجه قبل الالتزام، أو ادخل "
              "بحجمٍ يحتمل ضعفه.",
        "en": "Pillar {pillar} is weak ({pct}%) — address it before you "
              "commit, or enter at a size that can absorb it."},
    "cond_eligibility_gate": {
        "ar": "منشأتك يجب أن تُدرَج في قائمة المنشآت المعتمدة (EU 2017/625) "
              "قبل أي شحن — ولا يُغني عنها أي إجراء لاحق.",
        "en": "Your facility must be on the approved-establishment list "
              "(EU 2017/625) before any shipment — nothing later substitutes "
              "for it."},
    # البند T-10: ذيلُ سطرِ أثر المصدر — نصّان مكتوبان أصالةً، والنسبُ بشرية.
    "prov_confidence": {"ar": "ثقة المرصود {range}",
                        "en": "observed confidence {range}"},
    "prov_merged_sources": {"ar": "مصادر مدمجة: {names}",
                            "en": "merged sources: {names}"},
    "decision_conditions_head": {
        "ar": "ما يجب إغلاقه قبل الالتزام",
        "en": "What must be closed before you commit"},
    "counter_case_head": {
        "ar": "أقوى ما يُقال ضدّ هذا الحكم",
        "en": "The strongest case against this decision"},
    "counter_case_computed": {
        "ar": "أقوى الجوانب «{strong}» عند {strong_pct}% يشدّ نحو الدخول، "
              "وأضعفها «{weak}» عند {weak_pct}% يشدّ ضدّه. اعتُمد الحكم على "
              "الجوانب مجتمعةً بأوزانها المعلنة، لا على جانبٍ واحد.",
        "en": "The strongest pillar, {strong}, at {strong_pct}% pulls toward "
              "entry; the weakest, {weak}, at {weak_pct}% pulls against it. "
              "The decision follows the pillars together under their stated "
              "weights, not any single one."},
    "sec_market_numbers": {"ar": "السوق بالأرقام", "en": "The market in numbers"},
    "sec_competition": {"ar": "المنافسة والتسعير والهامش",
                        "en": "Competition, pricing and margin"},
    "sec_entry_path": {"ar": "مسار الدخول والمتطلبات",
                       "en": "Entry route and requirements"},
    "sec_risks": {"ar": "المخاطر", "en": "Risks"},
    "sec_open_items": {"ar": "ما لم يكتمل للقرار",
                       "en": "What is still open for this decision"},
    "sec_methodology": {"ar": "المنهجية وسجل الأدلة",
                        "en": "Methodology and evidence log"},
    # ── أقسام الكاتب الأحد عشر · the eleven writer sections ────────────────
    "wsec_executive_summary": {"ar": "الخلاصة التنفيذية",
                               "en": "Executive Summary"},
    "wsec_methodology": {"ar": "منهجية البحث ونطاقه",
                         "en": "Research Methodology and Scope"},
    "wsec_market_overview": {"ar": "نظرة عامة على السوق وحجمه",
                             "en": "Market Overview and Size"},
    "wsec_market_dynamics": {"ar": "ديناميكيات السوق", "en": "Market Dynamics"},
    "wsec_consumer_demand": {"ar": "تحليل المستهلك والطلب",
                             "en": "Consumer and Demand Analysis"},
    "wsec_competitive_landscape": {"ar": "المشهد التنافسي",
                                   "en": "Competitive Landscape"},
    "wsec_regulation": {"ar": "التنظيم والوصول للسوق",
                        "en": "Regulation and Market Access"},
    "wsec_logistics": {"ar": "اللوجستيات وسلسلة الإمداد",
                       "en": "Logistics and Supply Chain"},
    "wsec_risk": {"ar": "تقييم المخاطر", "en": "Risk Assessment"},
    "wsec_recommendations": {"ar": "التوصيات الاستراتيجية",
                             "en": "Strategic Recommendations"},
    "wsec_appendices": {"ar": "الملاحق", "en": "Appendices"},
    # ── الغلاف والترويسة · cover and header ────────────────────────────────
    "report_title": {"ar": "دراسة سوق تصديرية", "en": "Export Market Study"},
    "report_by": {"ar": "أُعدّت بواسطة منصة سِلك لذكاء الأسواق",
                  "en": "Prepared by Silk Market Intelligence"},
    "origin_saudi": {"ar": "المملكة العربية السعودية", "en": "Saudi Arabia"},
    "test_run_banner": {
        "ar": "⚠ نموذج توضيحي ببيانات موسومة — ليس تقريراً إنتاجياً",
        "en": "⚠ Demonstration sample with labelled data — not a production report"},
    "recommendation_line": {"ar": "التوصية: {label}",
                            "en": "Recommendation: {label}"},
    "section_narrative_absent": {
        "ar": "التحليل السردي التفصيلي لهذا القسم غير متاح ضمن هذا التقرير؛ "
              "الأدلة المرصودة ذات الصلة مُدرجة في «المراجع» ختام التقرير.",
        "en": "The detailed narrative for this section is not available in "
              "this report; the relevant observed evidence is listed under "
              "“References” at the end of the report."},
    "narrative_unavailable": {
        "ar": "تعذّر إنجاز التقرير السردي التفصيلي في هذه المحاولة لأسباب "
              "تقنية مؤقتة؛ القرار أعلاه والأدلة المرصودة في «المراجع» ختام "
              "هذا التقرير قائمة وصحيحة، ويمكن إعادة توليد النص السردي دون "
              "إعادة البحث الكامل.",
        "en": "The detailed narrative could not be produced on this attempt "
              "for temporary technical reasons. The decision above and the "
              "observed evidence listed under “Sources” at the end of this "
              "report stand and are correct; the narrative can be regenerated "
              "without re-running the full research."},
    # البند ٣ (لغة الزائر): «حكم المحرّك الحتمي» لغةُ نظامٍ كانت تصل docx
    # العميل — الحكم يُنسب للدراسة والثقة تبقى بتسميتها النوعية {phrase}.
    "confidence_basis_line": {
        "ar": "تصدر هذه الدراسة حكمها بدرجة ثقة {phrase} بناءً على الأدلة "
              "التي جمعتها — تفصيل الأساس في هذا القسم والأقسام التالية.",
        "en": "This study issues its assessment with {phrase} confidence, "
              "based on the evidence it gathered — the detailed basis "
              "follows in this and the subsequent sections."},
    "product": {"ar": "المنتج", "en": "Product"},
    "target_market": {"ar": "السوق المستهدف", "en": "Target market"},
    "hs_code": {"ar": "رمز HS", "en": "HS code"},
    "origin": {"ar": "بلد المنشأ", "en": "Country of origin"},
    "report_date": {"ar": "تاريخ التقرير", "en": "Report date"},
    "item": {"ar": "البند", "en": "Item"},
    "value": {"ar": "القيمة", "en": "Value"},
    "source": {"ar": "المصدر", "en": "Source"},
    "retrieved_at": {"ar": "تاريخ الرصد", "en": "Retrieved"},
    "unit": {"ar": "الوحدة", "en": "Unit"},
    "period": {"ar": "الفترة", "en": "Period"},
    # ── الحدود والفجوات · limits and gaps ──────────────────────────────────
    "limits_heading": {"ar": "حدود هذا التقرير", "en": "Limits of this report"},
    "glossary_heading": {"ar": "مسرد المصطلحات", "en": "Glossary"},
    # «المراجع» هي التسمية العربية القائمة فعلاً في تقرير العميل والتقرير
    # الأكاديمي — تبقى حرفياً (اختبارات مطابقةٍ قائمة تقرأ العنوان نفسه).
    "sources_heading": {"ar": "المراجع", "en": "References"},
    # D4: بالثنائية القانونية حتى في المفاتيح غير الموصولة حالياً — لو
    # وُصلت لاحقاً لا تعيد بعث المفردة المحظورة.
    "not_observed": {"ar": "غير متاح", "en": "not available"},
    "price_not_observed": {"ar": "السعر غير متاح", "en": "price not available"},
    "not_calculable": {"ar": "غير قابل للحساب", "en": "not calculable"},
    "from_store": {"ar": "من المخزن", "en": "from the store"},
    "latest_available": {"ar": "الأحدث المتاح", "en": "latest available"},
    # ── الاقتصاد والسوق · market and economics ─────────────────────────────
    "market_size_total": {"ar": "حجم السوق كله", "en": "Total market size"},
    "market_size_serviceable": {"ar": "الجزء الذي يمكن خدمته فعلاً",
                                "en": "Serviceable market"},
    "market_size_obtainable": {"ar": "الحصة الواقعية المتوقّعة",
                               "en": "Obtainable share"},
    "market_concentration": {"ar": "مؤشر تركّز السوق",
                             "en": "Market concentration index"},
    "growth_cagr": {"ar": "متوسط النمو السنوي", "en": "Average annual growth"},
    "landed_cost": {"ar": "التكلفة الواصلة", "en": "Landed cost"},
    "gross_margin": {"ar": "الهامش الإجمالي", "en": "Gross margin"},
    "tariff_mfn": {"ar": "التعريفة الجمركية العادية", "en": "Standard (MFN) tariff"},
    "logistics_quality": {"ar": "تقييم جودة الشحن", "en": "Logistics quality score"},
    "country_stability": {"ar": "مؤشرات استقرار الدولة",
                          "en": "Country stability indicators"},
    # ── مستويات السعر · price levels (§17) ─────────────────────────────────
    "price_retail": {"ar": "سعر التجزئة", "en": "Retail price"},
    "price_wholesale": {"ar": "سعر الجملة", "en": "Wholesale price"},
    "price_import": {"ar": "سعر الاستيراد", "en": "Import price"},
    "price_export": {"ar": "سعر التصدير", "en": "Export price"},
    # ── البيانات الوصفية · artifact metadata (§14) ─────────────────────────
    "meta_heading": {"ar": "بيانات المستند", "en": "Document metadata"},
    "meta_report_language": {"ar": "لغة التقرير", "en": "Report language"},
    "meta_factory_language": {"ar": "لغة المصنع وقت التوليد",
                              "en": "Factory language at generation"},
    "meta_study_id": {"ar": "معرّف الدراسة", "en": "Study ID"},
    "meta_factory_id": {"ar": "معرّف المصنع", "en": "Factory ID"},
    "meta_generated_at": {"ar": "تاريخ التوليد", "en": "Generated at"},
    "meta_schema_version": {"ar": "نسخة مخطّط التقرير", "en": "Report schema version"},
    "meta_engine_version": {"ar": "نسخة محرّك التقرير", "en": "Report engine version"},
    # ── اسم اللغة نفسها (للمؤشّر في الواجهة) ───────────────────────────────
    "lang_name_ar": {"ar": "العربية", "en": "Arabic"},
    "lang_name_en": {"ar": "الإنجليزية", "en": "English"},

    # ── سطور «ما لم يكتمل للقرار» · the declared-gap lines ──────────────────
    # هذه قوالبُ نصّ **مشتقّة من مفاتيح قانونية** لا منسوخةٌ من نصّ بعثةٍ عربيّ
    # — وهو الشقّ الثاني من الفصل الصلب بين لغة الأدلة الداخلية ولغة تقرير
    # العميل: البعثة تبقى عربية، والسطر المعروض يُولَّد من مفتاحه بلغة التقرير.
    "limit_mission_uncited": {
        "ar": "فرصة {label} بلا نتائج مبنية على استشهاد: {detail}",
        "en": "{label}: no citation-backed findings — {detail}"},
    # الصنف ١ (موجة عيوب التقرير): «تقاطع المحلل» اسمُ بنيةٍ داخلية لا
    # يعرفها القارئ ولا يتصرّف بها — الجانبُ نفسه وأثرُ نقصه هما ما يُقال.
    "limit_analyst_thin": {
        "ar": "{label}: الأدلة المتاحة لا تكفي لحكمٍ في هذا الجانب — "
              "يُقرأ بما هو، لا يُبنى عليه قرار.",
        "en": "{label}: the available evidence does not support a judgement "
              "on this aspect — read it as context, do not decide on it."},
    "limit_unresolved_note": {
        "ar": "ملاحظة مراجع لم تُعالَج: {detail}",
        "en": "Reviewer note left unaddressed: {detail}"},
    "limit_report_missing": {
        "ar": "التقرير الكامل غائب: {detail}",
        "en": "The full narrative is missing: {detail}"},
    "limit_hs_classification": {
        "ar": "تصنيف HS: {detail}", "en": "HS classification: {detail}"},
    "limit_ai_extras": {
        "ar": "تحليل إضافي: {detail}", "en": "Additional analysis: {detail}"},
    "limit_verdict_note": {
        "ar": "ملاحظة على التوصية: {detail}",
        "en": "Note on the recommendation: {detail}"},
    "limit_source_fetch_failed": {
        "ar": "المصدر «{label}» تعذّر جلب بياناته في هذه التشغيلة — لم يُعتمد "
              "عليه ولا يُدرَج ضمن مصادر التقرير.",
        "en": "Source “{label}” could not be retrieved for this study — it "
              "was not relied upon and is not listed among the report's sources."},
    "limit_unclassified": {
        "ar": "تعذّر التصنيف",
        "en": "The product could not be classified"},
    # ── قسم «ما لم يكتمل للقرار» وفقرة المنهجية والمراجع ───────────────────
    "gaps_heading": {
        "ar": "ما لم يكتمل للقرار، والخطوة التالية",
        "en": "What is still open for the decision, and the next step"},
    "gaps_intro": {
        "ar": "النقاط التالية لم تكتمل توثيقاً ضمن هذا التقرير؛ هي ما يفصل "
              "التوصية الحالية عن قرار نهائي كامل، وكلٌّ منها قابل للإغلاق "
              "بخطوة محدّدة:",
        "en": "The following points are not fully documented in this report. "
              "They are what separates the current recommendation from a "
              "final decision, and each can be closed by a specific step:"},
    "gaps_next_step_intro": {
        "ar": "الخطوة التالية المقترحة أدناه:",
        "en": "The suggested next step is below:"},
    "gaps_nonblocking_one": {
        "ar": "يوجد معطى ناقص واحد لا يمنع القرار الحالي لكنه يقيّد يقينه "
              "— مفصّل أدناه:",
        "en": "There is one missing input that does not block the current "
              "decision but limits its certainty — detailed below:"},
    "gaps_nonblocking_many": {
        "ar": "توجد {n} معطيات ناقصة لا تمنع القرار الحالي لكنها تقيّد يقينه "
              "— مفصّلة أدناه:",
        "en": "There are {n} declared gaps that do not block the current "
              "decision but limit its certainty — detailed below:"},
    "gaps_none": {
        "ar": "اكتملت التقاطعات التحليلية الأساسية بأدلة موثّقة بمصادرها، ولا "
              "بند حاسم للقرار موسوم بأنه غير محقَّق؛ لا فجوة جوهرية تمنع "
              "اتخاذ القرار ضمن نطاق هذا التقرير.",
        "en": "The core analytical intersections are complete with "
              "source-backed evidence, and no decision-critical item is "
              "flagged as unverified; no material gap prevents a decision "
              "within the scope of this report."},
    "references_none": {
        "ar": "لا مصادر عمومية موثّقة قابلة للعرض هنا في هذه التشغيلة.",
        "en": "No documented public sources are available to list for this study."},
    "methodology_paragraph": {
        "ar": "اعتمد هذا التقرير على مصادر رسمية عامة ({sources})، مع تحليل "
              "تقاطعي بينها ومراجعة للاتساق قبل الاعتماد. كل رقم يحمل "
              "مصدره المعلن بجانبه، وما لم نرصد له مصدراً يُذكَر فجوةً "
              "صريحة لا تقديراً. {dates}. قائمة المراجع الكاملة "
              "بروابطها الرسمية ختام التقرير.",
        # الموجة B (البند T-07): كان النصّان يَعِدان بأنّ «كلّ معلومة
        # خضعت للتحقّق من مصدرها العمومي المباشر» — وعدٌ لا تُنفّذه أيُّ
        # طبقة: الإسنادُ يُقاس على مؤشّرات البعثات لا على أرقام المتن،
        # ودليلُ بحثِ الويب يفقد رابطه قبل المراجع. وعدٌ لا يُنفَّذ في
        # مُسلَّمٍ للعميل أسوأُ من صمت. الصيغةُ الآن تصف ما يجري فعلاً.
        "en": "This report draws on public official sources ({sources}), "
              "cross-analysed and checked for consistency before being "
              "relied upon. Every figure carries its stated source beside "
              "it; anything we could not source is named as an explicit "
              "gap rather than estimated. {dates}. The full reference list "
              "with official links appears at the end of this report."},
    "methodology_sources_generic": {
        "ar": "مصادر رسمية عامة", "en": "public official sources"},
    # الموجة B (البند T-11): قسمُ «مؤشّر تغطية المصادر» كان معرَّفاً بلا
    # مُنادٍ — أي أنّ رقمَ التغطية لم يبلغ المصنعَ قطّ رغم أنّ الشيفرة تبنيه.
    "coverage_heading": {
        "ar": "مؤشّر تغطية المصادر", "en": "Source-coverage indicator"},
    # #13 (تعميق المُشرِف): الجدول يعدّ **رتب تحقق** (شارات ✓/◐/○) لا
    # تصنيف مصادر — التسميات القديمة («مصدر رسمي أوّلي»/«مصدر عامّ»/«معطى
    # ناقص») ادّعت تصنيفاً فوق عدٍّ آخر، فظهر «2 رسمي أولي» بجوار ثقة 80%
    # وComtrade «مصدراً عاماً». التسمية الآن بما يُعدّ فعلاً، وسطر الإسناد
    # المسمّى الحقيقي (compute_source_coverage) بُعدٌ ثانٍ منفصل.
    "coverage_intro": {
        "ar": "من إجمالي {total} قيمة معدودة في سجل أدلة هذه الدراسة، نحو "
              "{pct}% منها مُتحقَّقٌ منه مباشرةً، والبقية بين قيم مرصودة "
              "بثقة متوسطة وقيم لم يكتمل التحقق منها وفجوات معلنة. مصادرُ "
              "كل قيمةٍ مجموعةٌ في قسم «المراجع» ختام التقرير، فالقرار "
              "يُتَّخذ بمعرفة مدى التغطية خلف الأرقام لا على ثقة عمياء.",
        "en": "Of the {total} values tallied in this study's evidence log, "
              "about {pct}% are directly verified; the rest range from "
              "medium-confidence observations to values whose verification "
              "is incomplete, plus explicitly declared gaps. Each value's "
              "source is collected under \u201cReferences\u201d at the "
              "end of this report, so the decision is made knowing how "
              "much coverage sits behind the figures rather than on blind "
              "trust."},
    "coverage_named_sources": {
        "ar": "وعلى مستوى الإسناد: {pct}% من القيم المرصودة ({backed}/{n}) "
              "يحمل مصدراً عمومياً مسمّى (UN Comtrade والبنك الدولي "
              "ونحوهما)؛ وما لم نرصد له مصدراً يُذكَر فجوةً صريحة.",
        "en": "On sourcing: {pct}% of the observed values ({backed}/{n}) "
              "carry a named public source (UN Comtrade, World Bank and "
              "the like); anything without an observed source is stated "
              "as an explicit gap."},
    "coverage_col_kind": {"ar": "رتبة التحقق", "en": "Verification tier"},
    "coverage_col_count": {"ar": "عدد القيم", "en": "Values"},
    "coverage_primary": {"ar": "مُتحقَّق منه مباشرة",
                         "en": "Directly verified"},
    "coverage_public": {"ar": "مرصود بثقة متوسطة (مصدر مسمّى)",
                        "en": "Observed at medium confidence (named source)"},
    "coverage_unverified": {"ar": "قيمة حاضرة لم يكتمل التحقق منها",
                            "en": "Present, verification incomplete"},
    "coverage_gap": {"ar": "فجوة معلنة بلا قيمة",
                     "en": "Declared gap (no value)"},
    # البند 18 (موجة سدّ الفجوات الثانية): صندوق التحذير الواحد بلغة
    # التقرير — يستهلكه build_view وتعرضه كل الأسطح (md/docx/اللوحتان).
    # القالب العربي بلا الوصف الرسمي — وصف كومتريد إنجليزيٌّ حرفياً،
    # واقتباسه داخل مستند عربي يُفشِل حارسَ لغة سطح العميل بحق.
    "hs_caveat_box": {
        "ar": "{tag}: أرقام الاستيراد والتركّز والحصص في هذا التقرير "
              "مجموعةٌ تحت رمز HS {hs}، ووصفه الرسمي لا يشمل صفة المنتج "
              "المميّزة — الأرقام الموسومة بنجمة (*) تُقرأ في سياق هذا "
              "التنبيه حتى تأكيد الرمز الصحيح.",
        "en": "{tag}: the import, concentration and share figures in this "
              "report were collected under HS code {hs} (\"{desc}\"), which "
              "does not cover the product's distinguishing attribute — "
              "figures marked with an asterisk (*) are to be read in the "
              "light of this notice until the correct code is confirmed."},
    # درس 191 (§58 الملاحظة 5، B2): وصف الرمز غائبٌ في المرجع (code_desc=None
    # من silk_hs_classifier) — قالب EN كان يطبع ("None"). صيغةٌ بلا اقتباس
    # وصفٍ (نمط سابقة silk_hs_confirm.py:566: «غير متاح» لا اقتباس فارغ/None).
    "hs_caveat_box_nodesc": {
        "ar": "{tag}: أرقام الاستيراد والتركّز والحصص في هذا التقرير "
              "مجموعةٌ تحت رمز HS {hs}، ووصفه الرسمي غير متاح في المرجع "
              "ولا يشمل صفة المنتج المميّزة — الأرقام الموسومة بنجمة (*) "
              "تُقرأ في سياق هذا التنبيه حتى تأكيد الرمز الصحيح.",
        "en": "{tag}: the import, concentration and share figures in this "
              "report were collected under HS code {hs}, whose reference "
              "description is unavailable and does not cover the product's "
              "distinguishing attribute — figures marked with an asterisk "
              "(*) are to be read in the light of this notice until the "
              "correct code is confirmed."},
    "methodology_latest_date": {
        "ar": "أحدث تاريخ جمع بيانات: {date}",
        "en": "Most recent data collection date: {date}"},
    "methodology_dates_in_log": {
        "ar": "تواريخ الجمع مسجّلة في سجل الأدلة أدناه",
        "en": "Collection dates are recorded in the evidence log below"},
    "client_gap_template": {
        "ar": "لم نتمكّن من توثيق {what} من مصدر موثّق ضمن هذا التقرير — "
              "إغلاق هذه الفجوة يتطلّب {how}.",
        "en": "We could not document {what} from a verified source within "
              "this report — closing this gap requires {how}."},
    "gap_what_demand": {
        "ar": "الحجم الدقيق للطلب الفعلي القابل للتوجيه",
        "en": "the precise addressable demand volume"},
    "gap_how_demand": {
        "ar": "بحثاً ميدانياً أوّلياً (مقابلات موزّعين أو استبيان طلب)",
        "en": "primary field research (distributor interviews or a demand survey)"},
    "gap_what_entry_cost": {
        "ar": "تكلفة الدخول الكاملة بما فيها الشحن الفعلي",
        "en": "the full entry cost including actual freight"},
    "gap_how_entry_cost": {
        "ar": "عرض أسعار شحن ملزماً من وكيل لوجستي",
        "en": "a binding freight quotation from a logistics agent"},
    "gap_what_price_competitiveness": {
        "ar": "موقعك السعري الدقيق مقابل المنافسين",
        "en": "your precise price position against competitors"},
    "gap_how_price_competitiveness": {
        "ar": "سعر المصنع بوحدة المنتج وأسعار منافسين موثقة بنفس العملة ووحدة المقارنة",
        "en": "your ex-factory price and documented competitor prices in "
              "matching currencies and product units"},
    "gap_what_entry_door": {
        "ar": "قائمة موزّعين/مستوردين مؤكَّدين بالاسم",
        "en": "a named, confirmed list of distributors and importers"},
    "gap_how_entry_door": {
        "ar": "خدمة تحقّق جهات اتصال مدفوعة (قواعد بيانات تجارية)",
        "en": "a paid contact-verification service (commercial databases)"},
    "gap_what_swot": {
        "ar": "الموقف التنافسي المؤكَّد من منظور مصدّر سعودي",
        "en": "the confirmed competitive position from a Saudi exporter's perspective"},
    "gap_how_swot": {
        "ar": "دمج نتائج التحقّق الميداني أعلاه في تقييم موحّد",
        "en": "consolidating the field-verification results above into a single assessment"},
    "gap_what_generic": {"ar": "بند تحليلي إضافي",
                         "en": "an additional analytical item"},
    "gap_how_generic": {"ar": "بحثاً تكميلياً موجّهاً",
                        "en": "targeted supplementary research"},
    "gap_entry_door_unverified": {
        "ar": "لم نتمكّن من تأكيد قناة الدخول الأولى{named} من مصدر موثّق — "
              "إغلاق هذه الفجوة يتطلّب خدمة تحقّق جهات اتصال مدفوعة (قواعد "
              "بيانات تجارية) قبل الالتزام بالموزّع.",
        "en": "We could not confirm the primary entry channel{named} from a "
              "verified source — closing this gap requires a paid "
              "contact-verification service (commercial databases) before "
              "committing to a distributor."},
    "gap_flip_condition": {
        "ar": "لم يتحقّق بعد: {condition} — إغلاق هذا الشرط يتطلّب {closes_via}.",
        "en": "Not yet met: {condition} — closing this condition requires "
              "{closes_via}."},
    # #13 ص15: الذيل «لا تمنع القرار…» كان مخبوزاً في قالب البند فتكرر
    # حرفياً خمس مرات — التأطير صار سطرَ تمهيدٍ واحداً للقائمة
    # (`gaps_nonblocking_*`)، والبند تفصيله وحده مباشرة في silk_reports
    # (المفتاح أزيل — قالبٌ بلا نصّ لغويّ يخرق عقد ثنائية اللغة).
    # ── قسم أقصى سعر مصنع قابل للمنافسة ────────────────────────────────────
    "eco_heading": {"ar": "أقصى سعر مصنع قابل للمنافسة",
                    "en": "Maximum competitive ex-factory price"},
    # صيد الفجوات ٣: صفوف الأسعار المرصودة وسطر الفتح كانا يُبنيان في العرض
    # (Wave 3.1) بلا أي سطح يعرضهما — قسم docx العميل يستهلكهما الآن.
    "price_obs_heading": {"ar": "الأسعار المرصودة على الرف",
                          "en": "Observed shelf prices"},
    "price_unlock": {
        "ar": "تتطلب المقارنة السعرية سعر المصنع وسعر المنافس بعملة ووحدة متطابقتين، مع توثيق حجم العبوة وأي تحويل مستخدم.",
        "en": "Price comparison requires your factory price and competitor prices "
              "in matching currencies and units, with documented pack sizes and conversions."},
    "concentration_context_line": {
        "ar": "أرقام تركّز السوق في هذا التقرير تُقرأ سياقاً عاماً للفئة لا "
              "قياساً مباشراً لهذا المنتج (الرمز الجمركي مُعلَّم).",
        "en": "Market-concentration figures in this report read as category "
              "context, not a direct measurement for this product (the HS "
              "code is flagged)."},
    "hs_derivation_heading": {"ar": "كيف حُدّد الرمز الجمركي",
                              "en": "How the HS code was derived"},
    "eco_anchor_line": {
        "ar": "أدنى سعر رف منافس مرصود في السوق: {price} {currency} "
              "(أساس التقييم: تجزئة).",
        "en": "Lowest competing shelf price observed in the market: {price} "
              "{currency} (pricing basis: retail)."},
    "eco_local_currency": {"ar": "بالعملة المحلية المرصودة",
                           "en": "in the observed local currency"},
    "eco_max_exw_line": {
        "ar": "لكي تجاري هذا السعر بعد الشحن والرسوم وهوامش التوزيع، يلزم ألا "
              "تتجاوز تكلفة منتجك خارج المصنع {max_exw} (بافتراضات السيناريو "
              "{scenario} أدناه).",
        "en": "To match that price after freight, duties and distribution "
              "margins, your ex-factory cost must not exceed {max_exw} (under "
              "the {scenario} scenario assumptions below)."},
    # البند 6 (أمر إصلاح المحرّك): تحذير التناقض التسعيري — إلزامي حين
    # يحسبه المحرك؛ لغة أعمال بلا مصطلح تشغيلي (سطح العميل).
    "eco_pricing_warning": {
        "ar": "تحذير: أقصى سعر مصنع قابل للمنافسة ({exw} دولار/كجم) أدنى "
              "بنسبة {pct}% من متوسط سعر الاستيراد المرصود ({ref} دولار/كجم) "
              "— المنافسة السعرية غير قائمة عملياً في هذه الفئة، ولا يصلح "
              "هذا الرقم أساساً للتفاوض.",
        "en": "Warning: the maximum competitive ex-factory price ({exw} "
              "USD/kg) is {pct}% below the observed average import price "
              "({ref} USD/kg) — price competition is not practically viable "
              "in this category, and this figure must not be used as a "
              "negotiating baseline."},
    "col_scenario": {"ar": "السيناريو", "en": "Scenario"},
    "col_freight_pct": {"ar": "الشحن %", "en": "Freight %"},
    "col_distributor_pct": {"ar": "هامش الموزّع %", "en": "Distributor margin %"},
    "col_retailer_pct": {"ar": "هامش التجزئة %", "en": "Retail margin %"},
    "col_max_exw": {"ar": "أقصى سعر المصنع", "en": "Max ex-factory price"},
    "eco_assumptions_note": {
        "ar": "القيم أعلاه افتراضات معلنة قابلة للتعديل — أدخل أرقامك الفعلية "
              "(شحنك وهوامش موزّعك) لتحديث الحد بدقة.",
        "en": "The values above are declared, adjustable assumptions — enter "
              "your actual figures (your freight and distributor margins) to "
              "refine the ceiling."},
    # ── شرطا قلب الحكم · flip conditions ───────────────────────────────────
    "flip_cond_hs": {
        "ar": "توفّر بيانات استيراد موثوقة تحت رمز HS الصحيح",
        "en": "Reliable import data becomes available under the correct HS code"},
    "flip_via_hs": {
        "ar": "إعادة تصنيف الرمز ثم سحب واردات كومتريد تحته",
        "en": "reclassifying the code, then pulling Comtrade imports under it"},
    "flip_cond_distributor": {
        "ar": "التعاقد مع موزّع محلي مؤكَّد بالاسم في {market}",
        "en": "Signing a named, confirmed local distributor in {market}"},
    "flip_via_distributor": {
        "ar": "التحقق من نشاط الجهة واهتمامها بالمنتج، ثم الاتفاق على شروط التوزيع وتوثيق العقد",
        "en": "verify the company's activity and product interest, then agree distribution terms and document the contract"},
    "the_market": {"ar": "السوق", "en": "the market"},
    "degraded_banner": {
        "ar": "⚠ DEGRADED — نظام الذكاء الاصطناعي غير متاح ({reason})",
        "en": "⚠ DEGRADED — the AI analysis service was unavailable ({reason})"},
    "degraded_reason_default": {
        "ar": "خدمة التحليل الآلي غير متاحة",
        "en": "the automated analysis service was unavailable"},
    "collected_on": {"ar": "تاريخ الجمع: {date}",
                     "en": "collected on {date}"},
    # ── تذييل الصفحة (§7: الترويسات والتذييلات تتبع لغة التقرير) ───────────
    # العلامةُ التجارية اسمُ علَمٍ يُكتب بحروف اللغة؛ الوصفُ بعدها يُترجَم.
    "footer_identity": {
        "ar": "سِلك لذكاء الأسواق — منصة تحليل أسواق التصدير السعودية",
        "en": "Silk Market Intelligence — Saudi export market analysis"},
    "footer_page": {"ar": " — صفحة ", "en": " — page "},
    # ── جدول المستوردين/الموزّعين · importer & distributor leads ───────────
    "leads_title": {"ar": "قائمة مستوردين وموزعين قابلين للتواصل",
                    "en": "Contactable importers and distributors"},
    "leads_none": {
        "ar": "لا جهات اتصال قابلة للتواصل في هذا التشغيل — القائمة غير متاحة",
        "en": "No contactable leads in this study — the list is not available"},
    "col_name": {"ar": "الاسم", "en": "Name"},
    "col_address": {"ar": "العنوان", "en": "Address"},
    "col_phone": {"ar": "الهاتف", "en": "Phone"},
    "col_email": {"ar": "الإيميل", "en": "Email"},
    "col_website": {"ar": "الموقع", "en": "Website"},
    "col_rating": {"ar": "التقييم", "en": "Rating"},
    # الصنف ١٠: سببُ إدراج الجهة — الجهةُ تُدرَج لنشاطها أو لتسميةِ التقرير
    # لها، لا لقربها الجغرافيّ (عمودٌ خلف رايةِ الصنف ١٠).
    "col_include_reason": {"ar": "سبب الإدراج", "en": "Why included"},
    "lead_reason_activity": {"ar": "نشاطٌ ذو صلة: {activity}",
                             "en": "Relevant activity: {activity}"},
    "lead_reason_named": {"ar": "مذكورةٌ في متن التقرير",
                          "en": "Named in the report body"},
    "lead_reason_unknown": {"ar": "نشاطُها غير مُصرَّح",
                            "en": "Activity not declared"},
    "next_step_deepen": {
        "ar": "فعّل خدمة التعميق المدفوعة للتحقق من المستوردين وجهات الاتصال "
              "قبل الالتزام",
        "en": "Activate the paid verification service to confirm importers and "
              "contacts before committing"},

    # ── تقاطعات المحلّل الشامل · the analyst intersections ─────────────────
    #
    # **موجة الخياطة (البند S-02/S-08).** هذه التسميات كانت عربيةً واحدةً
    # (`silk_market_analyst._CATEGORY_LABELS`) تُحقَن في جملةٍ إنجليزية كما
    # هي، فيقرأ المصنعُ الإنجليزيُّ سطراً هجيناً؛ وحارسُ تسرّب اللغة لا
    # يلتقطه لأنّ الشظيّة أقصرُ من حدّ النثر (`_MIN_PROSE_WORDS`). ومصدرُها
    # الواحد هنا هو نفسُه الذي تُمفصِل عليه بوّابةُ الجودة
    # (`silk_quality_gate._check_intersection_insufficiency`) — خريطةٌ واحدة
    # لا خريطتان تتباعدان.
    "cat_demand": {
        "ar": "الطلب الفعلي القابل للتوجيه",
        "en": "Addressable demand"},
    "cat_entry_cost": {
        "ar": "تكلفة وصعوبة الدخول",
        "en": "Entry cost and difficulty"},
    "cat_price_competitiveness": {
        "ar": "التنافسية السعرية",
        "en": "Price competitiveness"},
    "cat_entry_door": {
        "ar": "أبواب الدخول الأكثر أماناً",
        "en": "Safest entry routes"},
    "cat_swot": {
        "ar": "SWOT من منظور المصدّر السعودي",
        "en": "SWOT from a Saudi exporter's perspective"},
}


# ── الموجة الرابعة (تقريرٌ تنفيذيّ): وارداتُ السوق والرسومُ بلغة القارئ ──────
# لا مصطلحَ قياسٍ داخليّ هنا عمداً (لا «درجة الثقة» ولا score/confidence): هذه
# السلاسل تصل متنَ العميل ويحرسها `_client_forbidden_hits`.
TERMS.update({
    "imports_head": {
        "ar": "واردات السوق من هذا الصنف",
        "en": "The market's imports of this product"},
    "imports_value_line": {
        "ar": "واردات السوق من هذا الصنف بلغت {amount} في {year} وفق {source}.",
        "en": "The market imported {amount} of this product in {year}, "
              "according to {source}."},
    "imports_growth_line": {
        "ar": "{phrase}.",
        "en": "Imports {verb} {growth} between {first_year} and {last_year} "
              "— a compound annual rate of {cagr}."},
    # لا نقطتين رأسيتين قبل خانةٍ قد تفرغ (اختبار «كلّ قالبٍ ينجو بخاناتٍ فارغة»).
    "imports_saudi_line": {
        "ar": "نصيب السعودية من هذه الواردات {pct} ({year}).",
        "en": "Saudi Arabia holds {pct} of these imports ({year})."},
    "imports_saudi_line_noyear": {
        "ar": "نصيب السعودية من هذه الواردات {pct} (سنة الحصة لم يذكرها "
              "المصدر).",
        "en": "Saudi Arabia holds {pct} of these imports (the source does not "
              "state the year of this share)."},
    "imports_growth_line_nocagr": {
        "ar": "{phrase}.",
        "en": "Imports {verb} {growth} between {first_year} and {last_year}; "
              "the compound annual rate is not computed for this series."},
    "imports_trend_not_computed": {
        "ar": "سنتان فأكثر مرصودتان لكن النمو لم يُحسب لهذه السلسلة.",
        "en": "Two or more years are observed, but growth is not computed "
              "for this series."},
    "imports_single_year_note": {
        "ar": "سنة واحدة مرصودة ({year}) — لا يُرسَم مسار بلا سنتين على الأقل.",
        "en": "Only one year observed ({year}) — no trend is drawn without "
              "at least two years."},
    "imports_gap_years_note": {
        "ar": "سنوات لم يُجلب رقمها: {years} — لم تُقدَّر ولم تُملأ.",
        "en": "Years without a fetched figure: {years} — not estimated, "
              "not filled in."},
    "imports_mirrored_note": {
        "ar": "قيمة {years} مقدَّرة من تصريحات الشركاء التجاريين (مرآة) — "
              "أقل يقيناً من تصريح مباشر.",
        "en": "The {years} value is estimated from trading partners' "
              "declarations (mirror data) — less certain than a direct "
              "declaration."},
    "chart_imports_trend": {
        "ar": "واردات السوق بالسنوات (دولار)",
        "en": "Market imports by year (USD)"},
    "chart_supplier_shares": {
        "ar": "حصص الدول المورِّدة لهذه السوق (%)",
        "en": "Supplying countries' shares of this market (%)"},
    "chart_saudi_highlight_note": {
        "ar": "حصة السعودية مميَّزة بالذهبي.",
        "en": "Saudi Arabia's share is highlighted in gold."},
    "chart_saudi_absent_note": {
        "ar": "السعودية ليست بين أكبر المورِّدين المرصودين لهذه السوق.",
        "en": "Saudi Arabia is not among this market's observed top "
              "suppliers."},
    "imports_col_year": {"ar": "السنة", "en": "Year"},
    "imports_col_value": {"ar": "قيمة الواردات", "en": "Import value"},
})



# ════════════════════════════════════════════════════════════════════════════
# الصنف ٢ (موجة عيوب التقرير) — خانةٌ فارغة لا تكسر جملة
# ════════════════════════════════════════════════════════════════════════════
# بلاغُ المالك: «الشريحة المحسوبة أعلاه رغم غياب رقم لحجمها»، و«استند هذا
# الحكم إلى شرطين مفتوحين» بلا شرطين. الجذرُ: القوالبُ تفترض امتلاءَ كلّ
# خانة، فخانةٌ فارغةٌ تتركُ أثرَها المكانيكيّ في الجملة.
#
# القياسُ (لا التخمين): **٦٣ من ٨٦** زوجَ (قالب، لغة) ذي خانةٍ ينكسر عند
# تفريغ خاناته — نقطتان متدلّيتان، قوسان فارغان، فراغٌ مزدوج، ترقيمٌ يتيم.
#
# العلاجُ طبقتان، لأنّ العطبَ نوعان:
#   (أ) **عطبٌ مكانيكيّ** يُصلَح حتمياً بلا معرفةِ معنى: `repair_interpolation`
#       — نفسُ نمط `silk_render._ORPHAN_LEAD_COMMA_RE`/`_EMPTY_CITATION_GROUP_RE`.
#   (ب) **جملةٌ تفقد معناها** بفقد خانتها («الثقة لأن .»، «أقوى الجوانب «»
#       عند %») — لا يُصلِحها تنظيفٌ: تحتاج **صيغةَ فراغٍ نحوية صريحة**،
#       تُسجَّل بمفتاحٍ مرافق `<key>_empty` يختاره `t()` تلقائياً.
#
# ولا يُمَسّ أيُّ نداءٍ قائم: المسارُ الجديد لا يعمل إلّا حين تكون خانةٌ
# **فارغةً فعلاً** — وهي الحالةُ التي كانت تُنتِج النصَّ المكسور.

_EMPTY_SUFFIX = "_empty"

# قوسٌ/علامةُ اقتباسٍ فارغةٌ بعد فقدِ خانتها.
_EMPTY_WRAP_RE = re.compile(
    "«\\s*»|\\(\\s*\\)|\\[\\s*\\]|\u201c\\s*\u201d|\"\\s*\"")
# نقطتان تتلوهما نهايةُ الجملة أو علامةُ ترقيم — «ينقصه: .» / «تصنيف HS:».
# نقاطُ الحذف بعد النقطتين ترقيمٌ مشروع («WITS unavailable: ...») —
# تُستثنى صريحاً (قياسٌ: حارس test_legacy_datapoint_shape).
_DANGLING_COLON_RE = re.compile(r"\s*:\s*(?!\.{2,}|\u2026)(?=[.،؛,;]|\Z)")
# فاصلةٌ/شرطةٌ يتيمة تركتها خانةٌ فارغة.
_ORPHAN_SEP_RE = re.compile(r"(?:\A|(?<=\s))[،؛,;]\s*(?=[.،؛,;]|\Z)")
_ORPHAN_DASH_RE = re.compile(r"\s+[—–]\s*(?=[.،؛,;]|\Z)")
# «(%)» أو «%» عارية بلا رقمها، و«من 100» بلا درجتها لا تُصلَّح مكانيكياً —
# مكانُها صيغةُ الفراغ الصريحة؛ هنا يُنظَّف القوسُ وحده.
_BARE_PCT_WRAP_RE = re.compile(r"\(\s*%\s*\)")
# فراغان آخرَ السطر فاصلُ أسطرٍ مقصودٌ في ماركداون — يُستثنى صريحاً.
_MULTISPACE_RE = re.compile(r"[ \t]{2,}(?!$)", re.M)
# فراغٌ قبل نقاطِ حذفٍ مشروع («WITS unavailable: ...») — يُستثنى صريحاً
# (قياسٌ: حارس test_legacy_datapoint_shape_still_counted_unchanged).
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+(?!\.{2,}|\u2026)(?=[.،؛,;؟!])")


def _is_blank(value: object) -> bool:
    """خانةٌ فارغةٌ فعلاً — `None` أو نصٌّ خالٍ. الصفرُ **ليس** فراغاً."""
    return value is None or (isinstance(value, str) and not value.strip())


def tidy_punctuation(text: str) -> str:
    """المجموعةُ **الآمنةُ على النثر الحرّ** من الإصلاح المكانيكيّ.

    قوسٌ فارغ، فراغٌ مزدوج، وفراغٌ قبل علامة ترقيم — ثلاثةٌ لا تكون مقصودةً
    في أيّ نثرٍ عربيٍّ أو إنجليزيّ سليم، فتُصلَح حتمياً حيثما وقعت.

    **لا** تلمس النقطتين المتدلّيتين: «التوصية:» آخرَ سطرٍ عنوانٌ مشروع،
    وحذفُه إفسادٌ لا إصلاح. تلك حالةُ الخانةِ الفارغة وحدها
    (`repair_interpolation`) — قناتان لأنّ ما يَصحّ داخل قالبٍ مفرَّغ لا
    يَصحّ على جملةٍ كتبها الكاتب.
    """
    if not text:
        return text
    out = _EMPTY_WRAP_RE.sub("", text)
    out = _BARE_PCT_WRAP_RE.sub("", out)
    out = _MULTISPACE_RE.sub(" ", out)
    out = _SPACE_BEFORE_PUNCT_RE.sub("", out)
    return out


# ── الصنف ٨ (موجة عيوب التقرير): حسابُ الدرجة وسقفُ الثقة بلغة القارئ ──────
TERMS.update({
    "score_arithmetic_line": {
        "ar": "كيف حُسبت هذه القوة: {parts} — مقسومةً على مجموع أوزان "
              "الجوانب المحسوبة ({wsum}) فالناتج {score} من 100. الجوانبُ "
              "التي لا نعرفها لم تُحسَب صفراً بل أُخرِجت من القسمة.",
        "en": "How this strength was computed: {parts} — divided by the sum "
              "of the scored aspects' weights ({wsum}), giving {score} out "
              "of 100. Aspects we do not know were excluded from the "
              "division, not counted as zero."},
    "score_arithmetic_withheld": {
        "ar": "لم تُحسَب قوةُ الفرصة: {reason}.",
        "en": "The opportunity strength was not computed: {reason}."},
    "score_arithmetic_withheld_empty": {
        "ar": "لم تُحسَب قوةُ الفرصة — الجوانبُ المحسوبة دون الحدّ الأدنى "
              "للتقييم، فلا درجةَ تُعرَض ولا تُخمَّن.",
        "en": "The opportunity strength was not computed — the scored "
              "aspects are below the minimum needed to rate it, so no score "
              "is shown and none is guessed."},
    "confidence_cap_core_missing": {
        "ar": "لا نصف ثقتَنا بأنها عالية ونحن لا نعرف {parts} — السقفُ "
              "«متوسطة» حتى تُكمَل هذه الجوانب أو تُغلَق الشروط المفتوحة.",
        "en": "We do not call our confidence high while {parts} is unknown — "
              "it is capped at “medium” until those aspects are completed or "
              "the open conditions are closed."},
    "confidence_cap_core_missing_empty": {
        "ar": "لا نصف ثقتَنا بأنها عالية مع وجود شرطين مفتوحين أو أكثر — "
              "السقفُ «متوسطة» حتى تُغلَق.",
        "en": "We do not call our confidence high with two or more open "
              "conditions — it is capped at “medium” until they are closed."},
    # الصنف ٨ (المراجعةُ الذاتية للفرق، البند ٥٨): جدولُ تحلُّلِ الثقة
    # بقِدَم البيانات كان **معلَناً بلا قارئ** — يُعرَض الآن سطراً مسمّىً
    # ولا يُمَسّ الرقمُ المخزَّن (نمطُ سقفِ التسمية نفسِه).
    "confidence_age_haircut": {
        "ar": "أقدمُ سنةٍ تستند إليها هذه التوصية {year} (عمرُها {age} سنة) "
              "— وبجدول تحلُّل الثقة المعلَن تُقرأ ثقةُ التوصية بخصمٍ قدرُه "
              "{pct}% عن ثقةِ توصيةٍ مبنيةٍ على بيانات العام الماضي.",
        "en": "The oldest year behind this recommendation is {year} ({age} "
              "years old) — under the published confidence-decay table, read "
              "its confidence with a {pct}% haircut against one built on "
              "last year's data."},
    # صيغةُ الفراغ (الصنف ٢): بلا سنةٍ مرصودةٍ لا خصمَ يُعرَض — والجملةُ
    # تبقى نحويةً تامّةً بلا خانةٍ مكسورة.
    "confidence_age_haircut_empty": {
        "ar": "لم تُرصَد سنةُ أقدمِ معطىً تستند إليه هذه التوصية، فلا خصمَ "
              "قِدَمٍ محسوب.",
        "en": "The oldest data year behind this recommendation was not "
              "observed, so no age haircut is computed."},
    "verification_rate_note": {
        "ar": "نسبةُ التحقّق تقيس كم من أرقام هذا التقرير فُتِح مصدرُها "
              "وتأكّدت قيمتُه منه — وهي **غيرُ** ثقةِ التوصية: تقريرٌ "
              "مُتحقَّقٌ من أرقامه قد تبقى توصيتُه منخفضةَ الثقة لنقصِ جانب.",
        "en": "The verification rate measures how many of this report's "
              "figures had their source opened and value confirmed — it is "
              "**not** the recommendation's confidence: a well-verified "
              "report can still carry low confidence if an aspect is "
              "missing."},
})


def repair_interpolation(text: str) -> str:
    """أصلِح العطبَ المكانيكيّ الذي تتركه **خانةٌ فارغة** — حتميّ، بلا معنى.

    الآمنُ على النثر (`tidy_punctuation`) زائداً ما يَصحّ داخل قالبٍ مفرَّغ
    وحده: النقطتان المتدلّيتان والشرطةُ والفاصلةُ اليتيمتان.

    دالّةٌ عامّة كي يستهلكها `silk_quality_gate._check_template_interpolation`
    والاختبارُ **نفسَها** — فلا قاعدةُ فحصٍ تخالف قاعدةَ إصلاح.
    """
    if not text:
        return text
    out = _DANGLING_COLON_RE.sub("", text)
    out = _ORPHAN_DASH_RE.sub("", out)
    out = _ORPHAN_SEP_RE.sub("", out)
    return tidy_punctuation(out).strip()


# ── الصنف ٢: صيغُ الفراغ النحوية الصريحة · explicit empty-state variants ────
# تسعةُ قوالبَ لا يُصلِحها تنظيفٌ مكانيكيّ لأنها **تدّعي رقماً**: «قوة هذه
# الفرصة في تقييمنا من 100» جملةٌ تقول شيئاً عن لا شيء. القاعدة: الغيابُ
# يُقال بما ينقص وبأثره على القرار — لا جملةٌ مبتورة ولا صفرٌ مختلَق (عقدُ
# عدم الاختلاق نفسُه). تُسجَّل هنا في `TERMS` فيمرّ عليها اختبارُ تكافؤ
# اللغتين القائم كأيّ مفتاح.
TERMS.update({
    "coverage_good_empty": {
        "ar": "نسبةُ الأرقام المسنودة إلى مصدرٍ منشور غيرُ محسوبة في هذه "
              "التشغيلة — تُقرأ مصادرُ كلّ رقم من قسم «المراجع».",
        "en": "The share of figures traceable to a published source was not "
              "computed for this study — read each figure's source under "
              "“References”."},
    "coverage_low_empty": {
        "ar": "نسبةُ الأرقام المسنودة إلى مصدرٍ منشور غيرُ محسوبة في هذه "
              "التشغيلة — تُقرأ مصادرُ كلّ رقم من قسم «المراجع».",
        "en": "The share of figures traceable to a published source was not "
              "computed for this study — read each figure's source under "
              "“References”."},
    "coverage_intro_empty": {
        "ar": "لم يُحسَب مدى التغطية خلف أرقام هذه الدراسة في هذه التشغيلة. "
              "مصادرُ كلّ قيمةٍ مجموعةٌ في قسم «المراجع» ختام التقرير — "
              "تُقرأ منه مباشرةً بدل نسبةٍ إجمالية غير متاحة.",
        "en": "The coverage behind this study's figures was not computed here. "
              "Each value's source is collected under “References” "
              "at the end of the report — read it there instead of an "
              "unavailable summary percentage."},
    "coverage_named_sources_empty": {
        "ar": "وعلى مستوى الإسناد: نسبةُ القيم الحاملة مصدراً عمومياً مسمّى "
              "غيرُ محسوبة في هذه التشغيلة؛ وما لم نرصد له مصدراً يُذكَر "
              "فجوةً صريحة كما هو.",
        "en": "On sourcing: the share of values carrying a named public "
              "source was not computed for this study; anything without an "
              "observed source is still stated as an explicit gap."},
    "decision_rule_lead_empty": {
        "ar": "قاعدة الحكم مُعلنة قبل النظر في الأرقام: نوصي بالمضي حين تبلغ "
              "قوة الفرصة عتبتَها المُعلنة وقد تحقّقنا من حدٍّ أدنى من "
              "بياناتها وبلا شروط مفتوحة؛ ونرفض حين تنزل دون عتبة الرفض أو "
              "عند اختلال أمان السوق؛ وما بينهما دخول مشروط بشروط مسمّاة "
              "أدناه. عتباتُ هذه التشغيلة غير متاحة للعرض.",
        "en": "The decision rule, stated before the numbers were weighed: we "
              "recommend proceeding when the opportunity strength reaches its "
              "stated threshold with a minimum share of its data verified and "
              "no open conditions; we decline below the rejection threshold or "
              "when market safety breaks down; anything in between is a "
              "conditional entry, with the conditions named below. This study's "
              "thresholds are not available for display."},
    "decision_weighted_line_empty": {
        "ar": "قوةُ هذه الفرصة غيرُ محسوبة في هذه التشغيلة — الجوانبُ "
              "المحسوبة دون الحدّ الأدنى للتقييم، فلا درجةَ تُعرَض ولا "
              "تُخمَّن.",
        "en": "This opportunity's strength was not computed for this study — "
              "the scored aspects are below the minimum needed to rate it, so "
              "no score is shown and none is guessed."},
    "counter_case_computed_empty": {
        "ar": "لا تُبنى حجةٌ مضادة من جانبٍ واحد: مقارنةُ أقوى الجوانب "
              "بأضعفها تحتاج جانبين محسوبين على الأقل، وهما غيرُ متاحين في "
              "هذه التشغيلة.",
        "en": "A counter-case cannot be built from a single aspect: "
              "contrasting the strongest with the weakest needs at least two "
              "scored aspects, and those are not available in this study."},
    "hs_caveat_box_empty": {
        "ar": "تنبيه: وصفُ رمز HS المستخدَم لا يشمل صفة المنتج المميّزة — "
              "الأرقام الموسومة بنجمة (*) تُقرأ في سياق هذا التنبيه حتى "
              "تأكيد الرمز الصحيح.",
        "en": "Notice: the description of the HS code used does not cover the "
              "product's distinguishing attribute — figures marked with an "
              "asterisk (*) are to be read in the light of this notice until "
              "the correct code is confirmed."},
    "eco_pricing_warning_empty": {
        "ar": "تحذير: تعارضٌ تسعيريٌّ مرصود بين أقصى سعر مصنع قابل للمنافسة "
              "ومتوسط سعر الاستيراد، وطرفُ المقارنة غيرُ محسوب في هذه "
              "التشغيلة — لا يصلح هذا الرقم أساساً للتفاوض.",
        "en": "Warning: a pricing contradiction was observed between the "
              "maximum competitive ex-factory price and the average import "
              "price, and one side of the comparison is not computed for this "
              "study — this figure must not be used as a negotiating baseline."},
})


def t(key: str, lang: str = DEFAULT_LANG, **fmt: object) -> str:
    """التسمية القانونية لمفهومٍ بلغةٍ بعينها.

    مفتاحٌ غير مسجَّل يرفع `KeyError` — عمداً: النصّ الناقص يجب أن يُكتشَف في
    الاختبار لا أن يظهر للعميل كمفتاحٍ خام أو سلسلةٍ فارغة. اختبار تكافؤ
    المفاتيح يضمن أن كل مفتاحٍ يحمل اللغتين معاً.

    الصنف ٢: إن كانت إحدى الخانات **فارغةً فعلاً**، تُقدَّم صيغةُ الفراغ
    النحوية `<key>_empty` إن كانت مسجَّلة؛ وإلّا يُصلَح العطبُ المكانيكيّ
    حتمياً. بلا خانةٍ فارغة لا يتغيّر شيءٌ في المسار القائم.
    """
    lng = normalize(lang)
    if fmt and any(_is_blank(v) for v in fmt.values()):
        alt = TERMS.get(key + _EMPTY_SUFFIX)
        if alt and (alt.get(lng) or "").strip():
            # صيغةُ الفراغ قد تحمل خاناتٍ أخرى ممتلئة — تُحشى بما توفّر.
            filled = {k: v for k, v in fmt.items() if not _is_blank(v)}
            try:
                return alt[lng].format(**filled) if filled else alt[lng]
            except (KeyError, IndexError):
                return alt[lng]
        return repair_interpolation(TERMS[key][lng].format(**fmt))
    row = TERMS[key]
    text = row[lng]
    return text.format(**fmt) if fmt else text


def terms_missing_language() -> list[str]:
    """المفاتيح التي تنقصها إحدى اللغتين — يستهلكها اختبار التكافؤ."""
    return sorted(k for k, v in TERMS.items()
                  if not (v.get("ar") or "").strip()
                  or not (v.get("en") or "").strip())


# ── ٣) كاشف تسرّب اللغة · the wrong-language leak detector (§13) ────────────
#
# المسؤولية **الوحيدة**: كشف النثر بلغةٍ خطأ. ليست فحص جودةٍ أسلوبية — ذاك فحصٌ
# منفصل تماماً في `silk_quality_gate._check_language_quality`. خلط المسؤوليتين
# يجعل الحاجز يحجب تقريراً سليماً لعيبٍ أسلوبيّ، أو يمرّر تسرّباً لأنّ الأسلوب حسن.

_AR_CHARS = r"؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿"
_ARABIC_RE = re.compile(f"[{_AR_CHARS}]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# ما لا يُحسَب تسرّباً أبداً — استثناءٌ **بنيويّ** (شكل الرمز نفسه يحدّده)، لا
# قائمة كلماتٍ مختلَقة. أسماء العلامات/الشركات/المنتجات تُمرَّر عبر `allow`
# مستخرَجةً من كيانات العرض نفسها، لا مُخمَّنة هنا.
_URL_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+")
_HS_RE = re.compile(r"\bHS\s?\d{2,10}\b|\b\d{4,10}\b")
_ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9&./-]{1,9}\b")     # HHI, CAGR, EU, TRACES, ISO3
_IDENT_RE = re.compile(r"\b[a-z]+(?:[_.][a-z0-9]+)+\b")     # معرّفات تقنية: silk.decision/v1
_NUMERIC_RE = re.compile(r"[\d٠-٩][\d٠-٩.,%٪:/–—-]*")
_CURRENCY_RE = re.compile(r"\b(?:USD|EUR|SAR|GBP|JOD|AED)\b", re.I)

# كلماتٌ لاتينية قصيرة تلتصق بالأرقام والوحدات في **كلا** التقريرين ولا تدلّ
# على نثرٍ أجنبي (وحدات القياس والعملات المكتوبة بحروف).
_UNIT_WORDS = frozenset({
    "kg", "g", "mt", "ton", "tons", "tonne", "tonnes", "l", "ml", "cm", "mm",
    "usd", "eur", "sar", "gbp", "jod", "aed", "fob", "cif", "exw", "ddp",
    "hs", "iso", "eu", "gcc", "efta", "un", "wto", "fao", "imf", "lpi", "wgi",
})

# طول أدنى لاعتبار سلسلةٍ أجنبية «نثراً» لا رمزاً. كلمةٌ واحدة عابرة ليست نثراً؛
# جملةٌ هي التسرّب الذي يهمّ العميل.
_MIN_PROSE_WORDS = 3

# أدواتُ الأعلام المركّبة — صنفٌ نحويّ **مغلق** (لا قائمة منتجات): الكلمة
# الصغيرة داخل اسمٍ علَمٍ («MSC de Jordan»، «Bank of Jordan»، «Marks and
# Spencer») ليست دليلَ نثرٍ إنجليزيّ (الدراسة الحية الرابعة — فحص B).
_NAME_PARTICLES = frozenset({
    "de", "del", "della", "di", "da", "van", "von", "der", "den", "ten",
    "ter", "of", "and", "al", "el", "bin", "ibn", "abu", "le", "la", "du",
    "dos", "das", "y", "e"})


def _strip_structural(text: str) -> str:
    """احذف كل ما هو استثناءٌ بنيويّ قبل قياس اللغة."""
    out = _URL_RE.sub(" ", text)
    out = _IDENT_RE.sub(" ", out)
    out = _ACRONYM_RE.sub(" ", out)
    out = _HS_RE.sub(" ", out)
    out = _CURRENCY_RE.sub(" ", out)
    out = _NUMERIC_RE.sub(" ", out)
    return out


def _split_segments(text: str) -> list[str]:
    """قسّم النصّ إلى مقاطع قابلة للحكم — سطور وجُمَل، لا مستند كامل.

    الحكم على المستند كله عديم الفائدة (أي تقريرٍ فيه اسم مصدرٍ لاتينيّ سيبدو
    «مختلطاً»)؛ الحكم على المقطع يعزل الجملة المتسرّبة بعينها فيُصلَح منشؤها.
    """
    parts: list[str] = []
    for line in text.splitlines():
        for seg in re.split(r"(?<=[.!?؟।])\s+|[؛;]\s*", line):
            seg = seg.strip()
            if seg:
                parts.append(seg)
    return parts


def foreign_prose_spans(text: object, lang: str,
                        allow: "tuple[str, ...] | list[str]" = ()) -> list[str]:
    """المقاطع المكتوبة **بلغةٍ خطأ** داخل نصٍّ موجَّه لسطح العميل.

    `lang="ar"` ⇒ يعيد المقاطع الإنجليزية غير المتوقَّعة.
    `lang="en"` ⇒ يعيد المقاطع العربية.

    `allow`: أسماء الكيانات المرصودة فعلاً في هذه الدراسة (علامات، شركات،
    منتجات، مصادر رسمية) — تُستخرَج من العرض نفسه لا تُخمَّن، فتُحذَف قبل
    القياس. القائمة الفارغة مشروعة: الاستثناء البنيويّ وحده يكفي لمعظم النصوص.

    يعيد قائمةً فارغة عند السلامة — فيقرأ المستدعي `if spans: FAIL`.
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    target = normalize(lang)

    allow_list = sorted((str(a).strip() for a in allow if str(a or "").strip()),
                        key=len, reverse=True)
    hits: list[str] = []
    for seg in _split_segments(raw):
        probe = seg
        for name in allow_list:
            probe = probe.replace(name, " ")
        probe = _strip_structural(probe)
        if target == "ar":
            # الدراسة الحية الرابعة (حجب 409): «Alyoum.jo» كانت تُشطَر عند
            # النقطة إلى «Alyoum» + «jo» — و«jo» الصغيرة تُسقط استثناء
            # الأعلام البنيوي فتُقرأ قائمةُ أسماء موزعين مشروعة (يفرضها
            # الموجّه: «مرشّحين بالاسم») نثراً إنجليزياً يحجب التقرير.
            # الرمز المنقوط الملتصق (نطاق/اختصار منقّط) كلمة واحدة — النثر
            # الحقيقي كلماته تفصلها مسافات فلا يتأثر.
            words = [w for w in re.findall(
                         r"[A-Za-z][A-Za-z'’-]*(?:\.[A-Za-z][A-Za-z'’-]*)*",
                         probe)
                     if w.lower() not in _UNIT_WORDS]
            # **اسمُ علَمٍ ليس نثراً.** سلسلةٌ لاتينية كلُّ كلماتها تبدأ بحرفٍ
            # كبير («UN Comtrade, World Bank, Google Maps») قائمةُ أسماءٍ
            # رسمية لا جملةٌ إنجليزية. الدراسة الحية الرابعة (فحص B
            # للمُشرِف) كشفت أن «كلمة صغيرة واحدة = نثر» معيارٌ هشّ: أداةُ
            # اسمٍ واحدة («de» في «MSC de Jordan») كانت تقلب قائمةَ أسماءٍ
            # كاملة نثراً فتحجب التقرير. والأداةُ نفسُها صنفٌ نحويّ مغلق
            # (لا قائمة منتجاتٍ تتخلّف): de/van/of/al وأخواتها جزءٌ معياريّ
            # من الأعلام المركّبة. المعيار: النثر يتطلب **كلمتين صغيرتين
            # على الأقل من خارج أدوات الأعلام** — الفعل/الوصل الإنجليزي
            # الحقيقي (regulates/supports/the) يبقى دليلَ نثرٍ ولو غلب
            # الترميزُ الكبير على البقية (مراجعة C4 موجة #14). منطقة عمى
            # معلنة: كلمةُ نثرٍ وحيدة بين الأسماء («Kaylani Food Center
            # est 1991») خارج الالتقاط — تغطيه إبر `english_field_leak`.
            lower_words = [w for w in words
                           if w[0].islower()
                           and w.lower() not in _NAME_PARTICLES]
            if len(words) >= _MIN_PROSE_WORDS and len(lower_words) >= 2:
                hits.append(seg.strip())
        else:
            # العربية لا تُكتب بلا حروفٍ عربية — أيّ كلمةٍ عربية في تقريرٍ
            # إنجليزيّ تسرّبٌ من طبقة الأدلة الداخلية، والعتبة نفسها تُطبَّق.
            words = re.findall(f"[{_AR_CHARS}]+", probe)
            if len(words) >= _MIN_PROSE_WORDS:
                hits.append(seg.strip())
    return hits


def has_foreign_prose(text: object, lang: str,
                      allow: "tuple[str, ...] | list[str]" = ()) -> bool:
    """اختصارٌ منطقيّ لـ`foreign_prose_spans` — للفحوص التي لا تحتاج المقاطع."""
    return bool(foreign_prose_spans(text, lang, allow))


def entity_allowlist(view: dict) -> tuple[str, ...]:
    """استخرج أسماء الكيانات المرصودة من العرض نفسه — أساس استثناء §13.

    المصدر **بيانات التشغيلة لا قائمةٌ مكتوبة**: أسماء المنافسين، الموردين،
    المستوردين، المصادر، اسم المنتج واسم السوق. فما يمرّ من لاتينيّ في تقريرٍ
    عربيّ (أو عربيّ في تقريرٍ إنجليزيّ) هو ما رُصد فعلاً، لا ما خمّنّاه.
    """
    names: set[str] = set()

    def _add(val: object) -> None:
        text = str(val or "").strip()
        if 1 < len(text) <= 80:
            names.add(text)

    def _add_sources(row: dict) -> None:
        # Documents display individual source IDs, not their joined original label.
        # Reuse that same reference-name formatting; never exempt findings or notes.
        from silk_data_layer import atomic_source_ids
        from silk_reports import _clean_source_label
        for source in atomic_source_ids(row.get("source"), row.get("source_ids")):
            _add(source)
            label = _clean_source_label(source)
            _add(re.split(r"\s+[—\-(]", str(label))[0].strip())

    if not isinstance(view, dict):
        return ()
    _add(view.get("product"))
    header = view.get("header") or {}
    if isinstance(header, dict):
        _add(header.get("product"))
        _add(header.get("target_market"))
    # مصادرُ البعثات وبنودُها — الموضع الفعليّ لأسماء المصادر الرسمية في
    # مسار البحث العميق (`dr.missions[*].findings[*].source`). بلا هذا كان
    # سطرُ «اعتمد هذا التقرير على مصادر رسمية عامة (UN Comtrade, World
    # Bank…)» يُقرَأ تسرّباً لغوياً — وهو اقتباسُ أسماءٍ رسمية لا نثرٌ أجنبيّ.
    _dr_early = view.get("deep_research") or {}
    if isinstance(_dr_early, dict):
        for _m in (_dr_early.get("missions") or {}).values():
            if not isinstance(_m, dict):
                continue
            for _f in (_m.get("findings") or []):
                if isinstance(_f, dict):
                    _add_sources(_f)
        _analyst = _dr_early.get("analyst") or {}
        if isinstance(_analyst, dict):
            for _items in (_analyst.get("by_category") or {}).values():
                for _f in (_items or []):
                    if isinstance(_f, dict):
                        _add_sources(_f)
    for row in (view.get("markets") or []):
        if not isinstance(row, dict):
            continue
        _add(row.get("country"))
        for comp in (row.get("components_detail") or []):
            if isinstance(comp, dict):
                _add(comp.get("source"))
        for key in ("named_competitors", "suppliers", "supplier_countries"):
            for item in (row.get(key) or []):
                if isinstance(item, dict):
                    _add(item.get("name") or item.get("company")
                         or item.get("brand") or item.get("country"))
                else:
                    _add(item)
    dr = view.get("deep_research") or {}
    if isinstance(dr, dict):
        market = dr.get("market") or {}
        if isinstance(market, dict):
            # صيد الفجوات ٣: المفتاح «name» لا يوجد في قاموس السوق العميق
            # (name_ar/name_en فقط) — كان السطر معطّلاً بصمت.
            _add(market.get("name_ar"))
            _add(market.get("name_en"))
        # `importer_leads` قاموسٌ لا قائمة: {"path", "note", "leads": [...]}
        # — التكرارُ عليه مباشرةً كان يمرّ على مفاتيحه النصّية فلا يُضاف اسمُ
        # جهةِ اتصالٍ واحد. والعنوانُ يدخل القائمة أيضاً: عنوانٌ لاتينيّ في
        # تقريرٍ عربيّ (شارع/مدينة) اسمُ مكانٍ لا نثرٌ إنجليزيّ.
        _leads_box = dr.get("importer_leads") or {}
        _leads = (_leads_box.get("leads") if isinstance(_leads_box, dict)
                  else _leads_box) or []
        for lead in _leads:
            if isinstance(lead, dict):
                _add(lead.get("name") or lead.get("company"))
                _add(lead.get("address"))
                _add(lead.get("website"))
        for row in (dr.get("price_rows") or []):
            if isinstance(row, dict):
                # صيد الفجوات ٣: كانت المفاتيح brand/retailer لا تُضبط قطّ،
                # و«store» كان يحمل الملاحظةَ المطهَّرة كاملةً (سُمّي «note»)
                # — وإدراجُ جملةِ ملاحظةٍ كاملةً «كياناً» يُعفيها من بوابة
                # اللغة. تُدرَج أسماءُ الكيانات الحقيقية فقط من قيمة الصف.
                v = row.get("value")
                if isinstance(v, dict):
                    _add(v.get("store"))
                    _add(v.get("brand"))
                    _add(v.get("title"))
    return tuple(sorted(names, key=len, reverse=True))
