"""عقد أسلوب الكاتب — Writer Style Contract (B1، أمر العمل الرئيس SPEC-v2).

مصدر واحد للأسلوب التجاري: نصّ العقد يُحقَن في موجّه كاتب التقرير
(`silk_ai_judge`)، وثابت المسرد + سعر الربط يُنفَّذان حتمياً في طبقة العرض
الواحدة (`silk_render._apply_merchant_language`) — فالمسرد والتفسيرات
والتسييق بالريال **مضمونة على md وdocx معاً حتى لو انحرف النموذج**.

الجمهور: صاحب قرار تجاري غير متخصص — عربية واضحة، جمل قصيرة، صوت مبني
للمعلوم. كل مصطلح تقني عند أول ورود يُشرح بين قوسين بالعربية؛ الإنجليزية
بين قوسين بعد العربية لا مستقلّة؛ يُذيَّل التقرير بمسرد من المصطلحات
المستعملة فعلاً.

**§1 (أمر العمل الرئيس — تحديث تسليم التقرير):** العملة تبقى بالدولار كما
وردت من المصادر بالضبط — لا تحويل إلى الريال ولا أي مقابل مُقوَّس (أُلغي
تسييق B1 الريالي). الأسعار المرصودة باليورو تبقى باليورو. الصياغة موحّدة:
دائماً «مليون دولار»، لا اختزال مثل «م$».

عقد عدم الاختلاق يبقى: هذه الطبقة تشرح وتوحّد الصياغة فقط — لا تغيّر أي
رقم، ولا تخترع قيمة أو تحويلاً.
"""
from __future__ import annotations

CONTRACT_VERSION = "1.1"

# المصطلح → شرح عربي سطر واحد (B1). المصدر الوحيد المستعمَل في الحقن
# (الموجّه) والتنفيذ (طبقة العرض) معاً.
GLOSSARY: dict[str, str] = {
    # §F-4 (حزمة الفكس v2.1): «سيطرة لاعب واحد» ادّعاءٌ أقوى مما يثبته الرقم
    # وحده (فوق 2500 يعني تركّزاً مرتفعاً، لا بالضرورة لاعباً مهيمناً منفرداً
    # — قد يكون ٢-٣ لاعبين كباراً). الصياغة الصحيحة: «تركّز مرتفع».
    "HHI": "مؤشر يقيس تركّز السوق بين المورّدين: فوق 2500 تركّز مرتفع",
    "CAGR": "متوسط النمو السنوي المركّب",
    "LPI": "تقييم البنك الدولي لجودة الشحن واللوجستيات من 5",
    "MFN": "التعريفة الجمركية العادية بلا تخفيض تفضيلي",
    "TRACES": "نظام الإخطار الجمركي الأوروبي الإلكتروني للشحنات",
    "CHED": "وثيقة الإدخال الصحّي المشترَك الأوروبية — إخطار مسبق للشحنة",
    "EORI": "رقم تسجيل المُستورِد لدى الجمارك الأوروبية",
    "WGI": "مؤشرات الحوكمة العالمية للبنك الدولي: استقرار سياسي وسيادة قانون وجودة تنظيم",
    "TAM": "إجمالي حجم السوق الكلي المتاح نظرياً",
    "SAM": "الجزء من السوق الذي يمكن خدمته فعلاً بالمنتج والقنوات المتاحة",
    "SOM": "الحصة الواقعية القابلة للالتقاط في المدى القصير",
}

# ── لغة التاجر (قرار المالك 2026-08-19) · plain-trader Arabic ───────────────
# البلاغ: «التقرير بلغة غير مفهومة». الشاهد من تقريره نفسه:
#   «سوق مورّدين مجزَّأ (HHI (مؤشر يقيس تركّز السوق بين المورّدين: فوق 2500
#    تركّز مرتفع)≈2350، لا مورّد مهيمناً)»
# الشرح المقحوم أطول من الجملة فيقطع المعنى. القرار: **على سطح العميل
# يُستبدَل المصطلح بمعناه**، ولا يُشرح بين قوسين؛ والمسرد يبقى قائمةً في
# آخر التقرير لمن أراد. نسخة المدقّق/المشغّل تحتفظ بالمصطلحات كما هي.

# (أ) مصطلحات تُستبدَل بمعناها كاملاً — لا قيمة للاسم عند التاجر.
PLAIN_TERMS: dict[str, str] = {
    "HHI": "مؤشر تركّز السوق",
    "CAGR": "متوسط النمو السنوي",
    "TAM": "حجم السوق كله",
    "SAM": "الجزء الذي يمكن خدمته فعلاً",
    "SOM": "الحصة الواقعية المتوقّعة",
    "LPI": "تقييم جودة الشحن",
    "MFN": "التعريفة الجمركية العادية",
    "WGI": "مؤشرات استقرار الدولة",
}

# (أ-٢) مصطلحات قياس عربية داخلية تُستبدل بجملة معناها على سطح العميل —
# المصدر الواحد للزوج (هدف الدراسة الاحترافية، البند ٣): يستهلكه مُطهِّر
# العميل (silk_reports) وباني لوحة الأساس (silk_render.decision_basis —
# نص «لماذا لم تُعتمد» من المحرّك) معاً، فلا نسختان تتباعدان.
CLIENT_TERM_REPLACEMENTS: tuple = (
    ("الدرجة الموزونة", "قوة الفرصة في التقييم"),
)

# (ب) أسماء أنظمة حقيقية يحتاجها التاجر بالاسم — تبقى، بوصف قصير مرّة واحدة.
KEEP_WITH_SHORT_DESC: dict[str, str] = {
    "TRACES": "نظام الإخطار الجمركي الأوروبي",
    "CHED": "وثيقة الإدخال الصحّي الأوروبية",
    "EORI": "رقم تسجيل المستورد لدى الجمارك الأوروبية",
}

# (ج) تعريفٌ قصيرٌ لمسرد العميل — يمنع التعريف الدائري («مؤشر تركّز السوق:
# مؤشر يقيس تركّز السوق…»). المسرد التقني الكامل يبقى لنسخة المدقّق.
PLAIN_GLOSS: dict[str, str] = {
    "HHI": "فوق 2500 يعني سوقاً بيد قلّة؛ أقلّ يعني موزّعاً على كثيرين",
    "CAGR": "متوسط ما ينمو به السوق كل سنة",
    "TAM": "قيمة واردات السوق كلها من هذا المنتج",
    "SAM": "الجزء الذي يناسب منتجك وقنواتك فعلاً",
    "SOM": "ما يمكن التقاطه واقعياً في أول ثلاث سنوات",
    "LPI": "تقييم البنك الدولي لجودة الشحن من 5",
    "MFN": "الرسوم الجمركية بلا أي تخفيض تفضيلي",
    "WGI": "قياس البنك الدولي لاستقرار الدولة وجودة أنظمتها",
}

PLAIN_LANGUAGE_RULE = (
    "**لغة التقرير (إلزامي — تكتب لتاجر لا لأكاديمي):** جملة واحدة لكل "
    "فكرة، وطولها لا يتجاوز سطرين. **ممنوع** أن تكتب اختصاراً إنجليزياً "
    "عارياً في المتن (HHI، CAGR، TAM، SAM، SOM، LPI، MFN، WGI) — اكتب "
    "معناه العربي مباشرة: «مؤشر تركّز السوق»، «متوسط النمو السنوي»، «حجم "
    "السوق كله»، «الجزء الذي يمكن خدمته فعلاً»، «الحصة الواقعية المتوقّعة»، "
    "«تقييم جودة الشحن»، «التعريفة الجمركية العادية»، «مؤشرات استقرار "
    "الدولة». **وممنوع الشرح بين قوسين وسط الجملة** — إن لزم توضيح فاجعله "
    "جملة مستقلّة بعدها. تجنّب الكلمات الثقيلة (تجزّؤ، متضافرة، إجرائية لا "
    "سوقية، مركّباً) واستعمل بديلها الدارج (موزّع على كثيرين، مجتمعة، "
    "إدارية لا تتعلق بالطلب، سنوياً). أسماء الأنظمة الرسمية التي يحتاجها "
    "التاجر بالاسم (TRACES، CHED، EORI، أرقام اللوائح الأوروبية) تبقى كما "
    "هي مع وصف عربي قصير عند أول ذكر."
)


# WP-1 §4 — سُلَّم معايرة الثقة الواحد: المصدر الوحيد لعتبات نطاقات الثقة
# المعروضة على وجه التقرير. الثقة المعروضة هي ثقة المحرّك الحتمي المحسوبة،
# لا التقرير الذاتي غير المعاير من النموذج؛ والتسمية العربية تُشتقّ من
# الرقم عبر `confidence_band_label` حصراً — يستهلكه العارض
# (silk_narrative.confidence_phrase) وحارس البوابة
# (silk_quality_gate._check_confidence_band_label) معاً فلا يتباعدان.
CONFIDENCE_HIGH_MIN_PCT = 80    # عالية ≥ 80%
CONFIDENCE_MEDIUM_MIN_PCT = 60  # متوسطة 60–79% / منخفضة < 60%


def confidence_band_label(pct: float, lang: str = "ar") -> str:
    """تسمية نطاق الثقة من النسبة المئوية — المشتقّ الوحيد.

    الموجة ٠: **العتبات لا تتغيّر بتغيّر اللغة** (٨٠٪ / ٦٠٪ في اللغتين) —
    النطاق حكمٌ حسابيّ، والتسمية وحدها معروضة. العربية تبقى حرفياً كما هي."""
    if pct >= CONFIDENCE_HIGH_MIN_PCT:
        band = "high"
    elif pct >= CONFIDENCE_MEDIUM_MIN_PCT:
        band = "medium"
    else:
        band = "low"
    if str(lang or "ar").lower() != "en":
        return {"high": "عالية", "medium": "متوسطة", "low": "منخفضة"}[band]
    import silk_i18n
    return silk_i18n.t(f"confidence_{band}", "en")


# ترتيب الفحص: الأطول أولاً كي لا يبتلع اختصارٌ جزءاً من آخر عند البحث.
GLOSSARY_ORDER: list[tuple[str, str]] = sorted(
    GLOSSARY.items(), key=lambda kv: -len(kv[0]))

GLOSSARY_HEADING = "مسرد المصطلحات"

# نصّ العقد المحقون في موجّه الكاتب (silk_ai_judge). طبقة العرض تُكمِل ما
# ينساه النموذج، لكن العقد يوجّه الكاتب لكتابة نصّ مفهوم بذاته أصلاً.
# Wave 5.1 (تدقيق زبدة الفول السوداني/اليمن — نبرة تنبيهية): عبارات مبالِغة/
# مثيرة للقلق تُستبدَل بصياغة مهنية مقيسة على **نفس الحقائق**. المصدر الوحيد
# يستهلكه عقد الكاتب (توجيه) والمراجع + الفحص الحتمي (إنفاذ، بلا نداء مدفوع).
ALARMIST_PHRASES: list[str] = [
    "يجب التوقف هنا فوراً", "يجب التوقف فوراً", "توقف فوراً",
    "يبطل كل الأرقام", "تبطل كل الأرقام", "يُبطِل كل الأرقام",
    "سوق مضطربة وشحيحة البيانات", "سوق مضطربة", "كارثي", "كارثة",
    "خطير جداً", "مرعب", "مقلق للغاية", "لا أمل", "مستحيل تماماً",
]

# البديل المقيس المُوصى به (يُعرَض في التوجيه وكاقتراح إصلاح للمراجع).
MEASURED_TONE_HINT = ("ينبغي التعامل مع هذه الأرقام كمؤشر سياقي لا كمقياس "
                      "مباشر")

# Wave 4.3 — ميزانية طول مستهدَفة: ~٣٠٪ أقصر من خطّ أساس اليمن، بقصّ التكرار
# لا الدليل. حدّ إرشادي للجملة (Wave 5.2): جملة قصيرة مفضّلة، متوسط ≤ ٢٥ كلمة.
TARGET_TIGHTEN_PCT = 30
SENTENCE_MAX_WORDS = 25

# قاعدة النبرة المهنية + الطول (تُحقَن في الموجّه؛ الإنفاذ في المراجع/الفحص).
PROFESSIONAL_TONE_RULE = (
    "**النبرة المهنية (إلزامي، Wave 5):** لا صياغة تنبيهية أو مبالِغة "
    "(«يجب التوقف هنا فوراً»، «يبطل كل الأرقام»، «سوق مضطربة وشحيحة "
    "البيانات») — بنفس الحقائق استعمل صياغة مقيسة («ينبغي التعامل مع هذه "
    "الأرقام كمؤشر سياقي لا كمقياس مباشر»). فضّل الجُمل القصيرة (المتوسط "
    "المستهدف ≤ خمس وعشرين كلمة)؛ والجملة التي تتجاوز خمساً وثلاثين "
    "كلمة — السقف الأقصى الموحّد — تُقسَم. **الطول (Wave 4.3): استهدِف تقريراً "
    "أوجز بنحو ٣٠٪ من الإسهاب المعتاد — احذف التكرار والاعتذار المكرّر، لا "
    "الدليل ولا رقماً مرصوداً.**")


# الموجة ٦ (توجيه §7.2 + قرار WS10): تمييز طبقات الأدلة **نحوياً** — قوائم
# أفعال لكل طبقة داخل عقد الكاتب، بلا شارات ✓/◐/○ ولا مفردات تصنيف في نص
# العميل (WS10 يبقى سليماً). يُلحق بكلا العقدين (امتداد لا استبدال — D-23).
EPISTEMIC_VERB_RULE = (
    "**تمييز طبقات الأدلة نحوياً (إلزامي — بلا شارات ولا مفردات تصنيف):** "
    "الرقم المرصود مباشرة من مصدر مسمّى يُصاغ بفعل تقريري (بلغ، سجّل، "
    "أظهر، وفق)؛ الرقم المشتق بحساب معلن يُصاغ بفعل استدلالي (يُقدَّر بـ، "
    "يستدل منه، يعادل، يقابل)؛ الرقم المبني على معلمة أو افتراض معلن "
    "يُصاغ شرطياً (بافتراض…، في حال…، على فرض…). لا يُصاغ رقم مشتق أو "
    "مُعلمَن بفعل تقريري أبداً — الفعل هو وسم الطبقة الوحيد المسموح."
)

def epistemic_rule() -> str:
    """قاعدة الأفعال كما تُحقَن فعلاً — صمّام إطفاء فوري في الإنتاج
    (`SILK_EPISTEMIC_VERBS_ENABLED=0`) يعيد سلوك ما قبل الموجة ٦ حرفياً."""
    import os as _os
    raw = _os.environ.get("SILK_EPISTEMIC_VERBS_ENABLED", "").strip().lower()
    return "" if raw in ("0", "false", "no", "off") else EPISTEMIC_VERB_RULE


OBSERVED_VERBS = ("بلغ", "سجّل", "أظهر", "وفق")
INFERRED_VERBS = ("يُقدَّر", "يستدل", "يعادل", "يقابل")
PARAMETER_VERBS = ("بافتراض", "في حال", "على فرض")


# ════════════════════════════════════════════════════════════════════════════
# Part B — معيار الكتابة (أمر إصلاح المحرّك) · the writing standard
# ════════════════════════════════════════════════════════════════════════════
# معايَر على التقرير الذهبي حليب×الأردن + دراسة #12 الحية (قرار المالك:
# المعايرة على مثال يدوي وحده نصف عمياء — انتُظرت الدراسة الحية أولاً).
# ثابت مشترك واحد يُركَّب في العقدين التجاري والأكاديمي (نمط
# PROFESSIONAL_TONE_RULE) — لا نسختين تتباعدان. جوهره: التقرير يكتب عن
# السوق لصاحب قرار، لا عن حال بياناته لنفسه.

DECISION_NUMBERS_HEADING = "أرقام القرار"
DECISION_NUMBERS_HEADING_EN = "Decision numbers"

WRITING_STANDARD_RULE = (
    "**معيار الكتابة (إلزامي — مقياسُ كل فقرة: هل يتصرف تاجرٌ بها؟):**\n"
    "- **قاعدة الطبقتين:** المتن لغةُ قرار؛ حالُ البيانات (الثقة، المنهجية، "
    "أسماء الحقول) في قسم المنهجية والملحق فقط. لا تذكر معطىً ناقصاً في "
    "المتن إلا إن غيّر القرار، وقُله بأثره لا بتسميته: «كلفة التسجيل غير "
    "متاحة فلا تُحسب نقطة التعادل — هذا الرقم وحده قد يقلب الجدوى». ولا "
    "تُحِل القارئ إلى مدخلات النظام (لا «بطاقة منتجك») — اطلب المعطى "
    "نفسه: سعر المصنع مع وحدة المنتج الفعلية (كيلوغرام أو لتر أو قطعة). "
    "لا تفترض الكيلوغرام لكل المنتجات ولا تدّع أن مدخلاً واحداً يكفي "
    "لحساب الربح إذا غابت أسعار البيع أو الشحن أو الرسوم.\n"
    "- **الخلاصة التنفيذية بقالب ثابت:** سطر «التوصية: …» وحده أولاً، ثم "
    "رقمان أو ثلاثة تحملها يتبع كلَّ رقمٍ **معناه** لا مصدره، ثم المسار "
    "العملي (من تقصد وماذا تفعل أولاً)، ثم الشرط الحاجب (ما يجب إغلاقه "
    "قبل أي مال) — **تحت 150 كلمة**، تصمد وحدها لو لم يُقرأ غيرها، "
    "بلا أي اسم مصدر فيها (المصادر لبقية الأقسام والملحق) ولا مفردة "
    "قياس داخلية ولا نسبة بلا معناها.\n"
    "- **السجل المهني:** صوت التقرير («توصي الدراسة بـ…»/«يُوصى بـ…») لا "
    "الأمرُ المباشر؛ جمل كاملة (المتوسط ≤25 كلمة والسقف 35 — الحدود "
    "الموحّدة في هندسة الجملة أدناه)؛ حسم هادئ بلا شحنة عاطفية "
    "(«فتات السوق» ونحوها ممنوعة)؛ لا استعارة ولا تشبيه؛ التحفظ يحدد نطاق "
    "الصلاحية («بحسب بيانات 2024») ولا يميّع الحكم؛ الفعل قبل الوصف "
    "(«يستحوذ مورّد واحد على 84%» لا «يمثل نسبة استحواذ…»)؛ مصطلح واحد "
    "بصيغة واحدة للتقرير كله؛ اليقين في الحكم والتوصية والحذر في البيانات "
    "— لا العكس.\n"
    "- **صوت المحلل:** تحفظ واحد كحد أقصى في الجملة؛ إن لم يسند الدليل "
    "حكماً فقُل ذلك في جملة مستقلة بدل تمييع الفقرة كلها.\n"
    "- **كل قسم يفتتح بإجابة سؤال قراره:** السوق وحجمه = كم دولاراً متاحاً "
    "لي فعلاً بعد حصة المهيمن؟ الديناميكيات = ما الذي يتغير خلال 24 شهراً "
    "فيغير قراري؟ المستهلك = من يشتري وأين وأي منتج تحديداً؟ المنافسة = "
    "بأي سعر أدخل وهل أبلغه؟ التنظيم = ما الذي يمنع شحني غداً؟ "
    "اللوجستيات = كم يوماً وكم دولاراً من مصنعي إلى الرف؟ المخاطر = ما "
    "الذي يخسّرني المال وباحتمال كم؟ التوصيات = ما أول ثلاث مكالمات هذا "
    "الأسبوع؟ والقسم الذي لا يملك إجابة سؤاله يعلن ذلك بإيجاز ولا يُحشى "
    "بمحتوى بديل. هذه الأسئلة إرشاد للمحلل؛ لا تنقلها حرفياً عناوين "
    "أو افتتاحيات، بل اكتب الإجابة بصياغة تقرير مهني.\n"
    "- **حدود الاستنتاج:** انخفاض الحصة وحده لا يثبت فرصة نمو؛ وغياب "
    "الرصد لا يثبت غياب الطلب. لا تكرر رقماً استُبعد لضعف دليله في المتن. "
    "لا تصف كلفة البضاعة بأنها أقصى خسارة ما لم تشمل الشحن والرسوم "
    "والالتزامات الأخرى، ولا تفترض حجم شحنة تجريبية أو احتمال خسارة "
    "بلا أساس معلن. ثبات سعر الصرف في فترة مرصودة لا يلغي مخاطر "
    "التحويل والتحصيل أو يضمن الاستقرار المستقبلي.\n"
    "- **هندسة الجملة:** فكرة واحدة ورقم واحد لكل جملة؛ متوسط ≤25 كلمة "
    "وأقصى 35؛ قوس اعتراضي واحد كحد أقصى؛ افتتح الفقرة بخلاصتها لا "
    "بتمهيدها؛ ممنوعة الافتتاحيات القالبية: «دلالة هذه النتيجة:»، «تجدر "
    "الإشارة إلى»، «من زاوية…»، «يُلاحَظ أن».\n"
    "- **الأرقام في النثر:** ثلاثة أرقام معنوية وبمنزلتين عشريتين كحدّ "
    "أقصى معاً (0.81 دولار لا 0.8136، "
    "و84% لا 84.05%) والدقة الكاملة للملحق؛ الرقم المفتاحي كاملاً مرة "
    "واحدة ثم باسمه («الحصة السعودية») ولا يتجاوز ذكره الحرفي مرتين في "
    "المتن كله؛ أتبِع الرقم بمعناه لا بمصدره "
    "(«9040 — سوق شبه مغلق عملياً»)؛ المقارنة الملموسة أبلغ من النسبة "
    "(«أقل من شحنة واحدة مجدية» أبلغ من «1.11 مليون دولار»).\n"
    "- **نثر عربي أصيل (هدف الدراسة الاحترافية):** ابدأ بالفعل الحقيقي "
    "لا بالاسم ولا بأفعال الحشو (يمثل/يشكل/يعتبر) — «انكمش السوق، فضاقت "
    "الفرصة» لا «يمثّل انكماش السوق عاملاً مقيّداً»؛ سمِّ الفاعل («لم نجد "
    "سعر تجزئة») وتجنّب بناء «يتم + مصدر»؛ الروابط الخفيفة (و، فـ، لكن، "
    "لذلك، أما…فـ) لا الثقيلة (بوصفه، إذ، من حيث، في ضوء، وعليه)؛ "
    "الإضافة ثلاث كلمات كحد أقصى («القيود الرسمية على ترخيص المجفف» لا "
    "«قيود ترخيص الحليب المجفف الرسمية»)؛ المعلومة الجديدة آخر الجملة "
    "(«لا يبقى لبقية الموردين سوى 1.11 مليون»)؛ استهدف 12–25 كلمة ضمن "
    "الحدود الموحدة أعلاه؛ ولا مصطلح مترجم حرفياً (نافذة فرصة، من "
    "الصفر، بطاقة تكلفة، رتبة حجم).\n"
    "- **المعطى الناقص يُعرض بثلاثة حقول ثابتة:** «المعطى الناقص: …» ثم "
    "«أثره على القرار: …» ثم «سبيل الإغلاق: … (الجهة والمدة والكلفة)» — "
    "خمس عشرة فجوة بهذا الشكل خطةُ عمل، لا قائمةُ ضعف.\n"
    f"- **قسم فرعي بعنوان «{DECISION_NUMBERS_HEADING}» إلزامي داخل "
    "التوصيات الاستراتيجية** يجمع: كلفة الدخول الكلية حتى أول شحنة، حجم "
    "الشحنة التجريبية الموصى به، نقطة التعادل (طن/شهر)، الزمن من القرار "
    "إلى أول فاتورة بالأسابيع، وأقصى خسارة إن فشل الدخول. المتعذر حسابه "
    "يُطبع بمعادلته وناقصه: «نقطة التعادل = كلفة الدخول ÷ هامش الطن. "
    "المتاح: الهامش. الناقص: كلفة الدخول.» — أنفع من إسقاطه صامتاً.\n"
    "- **قبل التسليم راجع:** التوصية مقروءة في أول ثلاثة أسطر بلا مصادر؛ "
    "كل قسم يفتتح بإجابة؛ لا لغة نظام في المتن؛ كل معطى ناقص بحقوله "
    "الثلاثة؛ لا جملة بتحفظين؛ كل رقم يتبعه معناه؛ قسم أرقام القرار "
    "قائم؛ التوصيات قابلة للتنفيذ صباح الاثنين (جهة مسماة، فعل، مدة)؛ "
    "لا فقرة تُختم بلا معلومة مضافة."
)

WRITING_STANDARD_RULE_EN = (
    "**Writing standard (mandatory — the test for every paragraph: would a "
    "trader act on it?):** Keep two layers separate: the body speaks "
    "decision language; data-state language (confidence, methodology, field "
    "names) belongs in the methodology section and appendix only. Mention a "
    "missing input in the body only when it changes the decision, stated by "
    "its effect, and ask for the datum itself — never for a system input. "
    "Use exactly two absence terms: \"not available\" (the figure does not "
    "exist in the sources) and \"not computed\" (it exists but the "
    "calculation was not run) — never \"not observed\", \"declared gap\", "
    "\"cannot be computed\", \"unspecified\", or \"unobserved\". "
    "Executive summary in a fixed template: one recommendation line first, "
    "then the two or three figures that carry it — each figure followed by "
    "its meaning, not its source — then the practical route (whom to "
    "approach, what to do first), then the blocking condition (what must "
    "close before money is committed) — under 150 words, standing alone if "
    "nothing else is read, with no source names, no internal measurement "
    "vocabulary, and no percentage without its meaning. Report voice, "
    "complete sentences (average ≤25 words, maximum 35 — the unified "
    "caps below), calm commitment with no emotive "
    "phrasing, no metaphors, scope-defining hedges only (\"per 2024 "
    "data\"), verb before description, one term in one form throughout, "
    "certainty in the verdict and caution about the data — never the "
    "reverse — and at most one hedge per sentence; if the evidence cannot "
    "support a judgement, say so in its own sentence. Every section opens "
    "with the answer to its decision question (market size: dollars "
    "actually available after the incumbent's share; dynamics: what changes "
    "within 24 months; consumer: who buys, where, which product exactly; "
    "competition: at what price do I enter and can I hit it; regulation: "
    "what stops tomorrow's shipment; logistics: days and dollars from plant "
    "to shelf; risk: what loses money and at what likelihood; "
    "recommendations: the first three calls this week) — a section without "
    "its answer says so briefly instead of being padded. One idea and one "
    "figure per sentence, average ≤25 words and maximum 35, at most one "
    "parenthetical, open each paragraph with its conclusion, no boilerplate "
    "openers. Three significant figures in prose (full precision in the "
    "appendix), state a key figure in full once then refer to it by name — "
    "never spelling the same figure out more than twice in the body, follow "
    "each figure with its meaning rather than its source, and prefer a "
    "concrete comparison to a bare percentage. Authentic prose "
    "(professional-study goal): open with the real verb rather than a noun "
    "or filler verb, name the agent (\"we found no retail price\") and "
    "avoid stacked passives, use light connectors, keep genitive chains to "
    "three words, put the new information last in the sentence, aim for "
    "12-25 words within the unified caps above, and use no "
    "literally-translated idioms. Present every missing input "
    "with three fixed fields: the missing input / its impact on the "
    "decision / how to close it (party, duration, cost). Include a "
    f"mandatory \"{DECISION_NUMBERS_HEADING_EN}\" subsection inside the "
    "strategic recommendations covering: total cost of entry through the "
    "first shipment, recommended trial shipment size, break-even in tonnes "
    "per month, weeks from decision to first invoice, and maximum downside "
    "if entry fails — print an uncomputable one as its formula plus the "
    "missing input. Before delivery check: recommendation readable in the "
    "first three lines without citations; every section opens with an "
    "answer; no system language in the body; every gap in its three "
    "fields; no sentence with two hedges; a Decision-numbers subsection "
    "present; recommendations executable Monday morning (named party, "
    "action, duration); no paragraph ends without adding information."
)


# قرار المالك (2026-07-22، متابعة القالب الأكاديمي — «اختلفت الصياغة»):
# القالب الأكاديمي الحتمي (#148) يعيد ترتيب السرد لكن لا يغيّر سجلّه
# اللغوي؛ هذا العقد البديل يُحقَن في الكاتب حين style="academic" فيخرج
# **النثر نفسه** بنبرة البحث العلمي من التوليد/إعادة التوليد (نداء كاتب
# واحد بقروش عبر POST /analyses/{id}/report?style=academic). نفس قواعد
# الصدق والعملة والمسرد حرفياً — السجل اللغوي وحده يتغيّر.
ACADEMIC_SECTION_CLOSER = "دلالة هذه النتيجة:"

ACADEMIC_WRITER_CONTRACT = (
    PROFESSIONAL_TONE_RULE + "\n\n"
    "**عقد السجل الأكاديمي (إلزامي — يتقدّم على أي صياغة تسويقية):** اكتب "
    "بعربية فصحى بحثية رصينة بصيغة الدراسة العلمية: «تشير النتائج إلى…»، "
    "«تخلص الدراسة إلى…»، «توضح البيانات أنّ…» — لا خطاب مباشر للقارئ ولا صيغة "
    "أمر تسويقية. انسب كل نتيجة لمصدرها داخل الجملة نفسها، وميّز صراحةً "
    "بين الملاحظة المرصودة والاستدلال المبني عليها. اختم كل قسم رئيس "
    "بجملة دلالةٍ بحثية مدمجة نثراً تشرح أثر نتائج القسم على سؤال "
    "الدراسة **وتقف بمعناها بذاتها — بلا الافتتاحية القالبية "
    f"«{ACADEMIC_SECTION_CLOSER}»** (البند 22 من أمر إصلاح المحرّك: "
    "تكرّرت افتتاحيةً جامدة في تقريرين؛ الجملة إمّا تقف بمعناها أو "
    "تُحذف) — **بدل** خاتمة «ماذا يعني هذا لقرارك» التجارية أينما طُلبت. "
    "وعند تعارضه مع معيار الكتابة أدناه يتقدّم هذا العقد في موضعين "
    "حصراً: الإسنادُ داخل الجملة نفسها (سمة السجل البحثي)، وخاتمةُ "
    "القسم البحثية — والباقي على المعيار."
    "**اكتب معنى كل مصطلح بالعربية مباشرةً بدل الاختصار — لا HHI بل "
    "«مؤشر تركّز السوق»، ولا TAM/SAM/SOM بل «حجم السوق كله»/«الجزء "
    "الذي يمكن خدمته»/«الحصة الواقعية». ولا شرحَ بين قوسين وسط "
    "الجملة (قرار المالك 2026-08-19: الشرح المقحوم يقطع المعنى). "
    "أسماء الأنظمة الرسمية (TRACES/CHED/EORI) تبقى بالاسم وشرحها "
    "في المسرد لا في المتن. "
    "**العملة تبقى "
    "بالدولار كما وردت من المصادر — لا تحويل إلى الريال ولا أي مقابل "
    "مُقوَّس؛ والأسعار المرصودة باليورو تبقى باليورو.** اكتب المبالغ "
    "بصيغة كاملة موحّدة «مليون دولار» لا اختزال «م$». حافظ على الدقة "
    "الكمية الحرفية: نفس الأرقام والمصادر بلا أي تعميم إنشائي، ولا تخترع "
    "أي رقم أو تحويل لم يُعطَ لك."
    + "\n\n" + WRITING_STANDARD_RULE
    + "\n\n" + EPISTEMIC_VERB_RULE
    + "\n\n" + PLAIN_LANGUAGE_RULE
)


WRITER_STYLE_CONTRACT = (
    PROFESSIONAL_TONE_RULE + "\n\n"
    "**عقد الأسلوب (إلزامي — تكتب لصاحب قرار تجاري غير متخصص):** عربية "
    "واضحة، جُمل قصيرة، صوت مبني للمعلوم، بلا حشو أكاديمي. "
    "**اكتب معنى كل مصطلح بالعربية مباشرةً بدل الاختصار — لا HHI بل "
    "«مؤشر تركّز السوق»، ولا TAM/SAM/SOM بل «حجم السوق كله»/«الجزء "
    "الذي يمكن خدمته»/«الحصة الواقعية». ولا شرحَ بين قوسين وسط "
    "الجملة (قرار المالك 2026-08-19: الشرح المقحوم يقطع المعنى). "
    "أسماء الأنظمة الرسمية (TRACES/CHED/EORI) تبقى بالاسم وشرحها "
    "في المسرد لا في المتن. "
    "**العملة تبقى بالدولار كما وردت من المصادر "
    "— لا تحويل إلى الريال ولا أي مقابل مُقوَّس؛ والأسعار المرصودة باليورو "
    "تبقى باليورو.** اكتب المبالغ بصيغة كاملة موحّدة «مليون دولار» لا اختزال "
    "«م$». لا تخترع أي رقم أو تحويل لم يُعطَ لك. طبقة العرض تُكمِل أي مسرد "
    "أو شرح ينقص حتماً — لكن اجتهد أن يكون نصّك مفهوماً بذاته للتاجر."
    + "\n\n" + WRITING_STANDARD_RULE
    + "\n\n" + EPISTEMIC_VERB_RULE
    + "\n\n" + PLAIN_LANGUAGE_RULE
)

# ════════════════════════════════════════════════════════════════════════════
# الموجة ٠ — عقود الكاتب الإنجليزية · the English writer contracts
# ════════════════════════════════════════════════════════════════════════════
#
# **مبدأ التصميم (§34 من أمر العمل).** هذه العقود **مكتوبةٌ بالإنجليزية أصالةً**
# لا مترجمةً عن العربية. الفرق ليس شكلياً:
#
#   • بالعربية، الاختصار الإنجليزي العاري (HHI/CAGR/TAM) **يُستبدَل بمعناه** —
#     لأنه دخيلٌ على القارئ العربي غير المتخصّص (قرار المالك 2026-08-19).
#   • بالإنجليزية، هذه المصطلحات **لغةُ أعمالٍ قياسية** يعرفها صاحب القرار —
#     فاستبدالها بشرحٍ مطوّل يجعل النصّ طفولياً. القاعدة الصحيحة: اشرحه **مرّة
#     واحدة عند أول ورود** ثم استعمل الاختصار.
#
# فالعقدان يحقّقان **نفس الغاية** (نصٌّ مفهوم لصاحب قرارٍ تجاريّ) بوسيلتين
# مختلفتين تناسب كلٌّ منهما لغتها — وهذا بالضبط معنى «عارضان لا مترجم».
#
# ونفس قواعد الصدق حرفياً: لا رقمَ مخترعاً، ولا حكمَ موازياً، ولا نسبةَ ثقةٍ
# من عند النموذج، ولا تحويلَ عملة.

PLAIN_LANGUAGE_RULE_EN = (
    "**Report language (mandatory — you are writing for a commercial "
    "decision-maker, not an academic):** one idea per sentence, no sentence "
    "longer than two lines. Standard business abbreviations (HHI, CAGR, TAM, "
    "SAM, SOM, LPI, MFN, WGI) are acceptable in English, but **spell each one "
    "out in full the first time it appears** and use the short form "
    "afterwards — for example \"market concentration (HHI)\" on first use, "
    "then \"HHI\". Do not stack parenthetical explanations mid-sentence; if "
    "something needs clarifying, make it its own following sentence. Prefer "
    "plain commercial words over consultancy filler (\"fragmented\" not "
    "\"characterised by fragmentation\"; \"yearly\" not \"on an annualised "
    "basis\"). Official system names the trader needs verbatim (TRACES, CHED, "
    "EORI, EU regulation numbers) stay exactly as they are."
)

PROFESSIONAL_TONE_RULE_EN = (
    "**Professional tone (mandatory):** no alarmist or exaggerated phrasing "
    "(\"you must stop immediately\", \"this invalidates every number\", \"a "
    "chaotic, data-starved market\"). State the same facts in measured terms "
    "(\"these figures should be read as contextual indicators rather than "
    "direct measurements\"). Prefer short sentences (target average ≤25 "
    "words); split anything over "
    "thirty-five words (the unified hard cap). **Length: aim for a report "
    "about 30% tighter than "
    "the usual sprawl — cut repetition and repeated caveats, never evidence "
    "and never an observed figure.**"
)

EPISTEMIC_VERB_RULE_EN = (
    "**Mark evidence layers grammatically (mandatory — no badges, no "
    "classification vocabulary):** a figure observed directly from a named "
    "source takes a reporting verb (reached, recorded, showed, according "
    "to); a figure derived by a declared calculation takes an inferential "
    "verb (is estimated at, implies, equates to, corresponds to); a figure "
    "resting on a stated parameter or assumption takes a conditional form "
    "(assuming…, if…, on the assumption that…). Never write a derived or "
    "assumption-based figure with a reporting verb — the verb is the only "
    "layer marker you may use."
)


def epistemic_rule_en() -> str:
    """قاعدة الأفعال الإنجليزية كما تُحقَن فعلاً — نفس صمّام النسخة العربية."""
    import os as _os
    raw = _os.environ.get("SILK_EPISTEMIC_VERBS_ENABLED", "").strip().lower()
    return "" if raw in ("0", "false", "no", "off") else EPISTEMIC_VERB_RULE_EN


# العنوان الفرعي لخارطة الدخول — المرساة الحتمية التي يقسم عندها المُصدِّر
# (`silk_reports._ROADMAP_SUBHEAD_EN_RE`). صياغةٌ ثابتة لا تُغيَّر بلا تحديثها.
ROADMAP_SUBHEAD_EN = "Entry roadmap"

ACADEMIC_SECTION_CLOSER_EN = "What this finding means:"

WRITER_STYLE_CONTRACT_EN = (
    PROFESSIONAL_TONE_RULE_EN + "\n\n"
    "**Style contract (mandatory — your reader is a commercial decision-maker "
    "without a research background):** clear business English, short "
    "sentences, active voice, no academic padding. **Currency stays in US "
    "dollars exactly as the sources reported it — no conversion to riyals and "
    "no bracketed equivalent; prices observed in euros stay in euros.** Write "
    "amounts in full and consistently (\"USD 4.2 million\", never \"4.2m$\"). "
    "Invent no figure and no conversion that was not given to you. The "
    "rendering layer will complete any missing glossary entry, but write "
    "prose that already stands on its own for a trader."
    + "\n\n" + WRITING_STANDARD_RULE_EN
    + "\n\n" + EPISTEMIC_VERB_RULE_EN
    + "\n\n" + PLAIN_LANGUAGE_RULE_EN
)

ACADEMIC_WRITER_CONTRACT_EN = (
    PROFESSIONAL_TONE_RULE_EN + "\n\n"
    "**Academic register contract (mandatory — overrides any marketing "
    "phrasing):** write in measured scholarly English in the voice of a "
    "research study: \"the findings indicate…\", \"the study concludes…\", "
    "\"the data shows that…\" — no direct address to the reader and no "
    "marketing imperatives. Attribute every finding to its source inside the "
    "sentence itself, and distinguish explicitly between an observation and "
    "an inference drawn from it. Close each main section with a "
    "research-significance sentence, written as flowing prose, explaining "
    "what that section's findings mean for the study question — a sentence "
    "that **stands on its own, without the boilerplate opener "
    f"\"{ACADEMIC_SECTION_CLOSER_EN}\"** (item 22 of the engine-fix order: "
    "the sentence either carries its meaning by itself or is cut) — "
    "**instead of** the commercial \"what this means for your "
    "decision\" closer wherever that is requested. "
    "**Currency stays in US dollars exactly as the sources reported it — no "
    "conversion to riyals and no bracketed equivalent; prices observed in "
    "euros stay in euros.** Write amounts in full and consistently (\"USD 4.2 "
    "million\", never \"4.2m$\"). Preserve literal quantitative accuracy: the "
    "same figures and the same sources, with no rhetorical generalisation, "
    "and invent no figure or conversion you were not given."
    + "\n\n" + WRITING_STANDARD_RULE_EN
    + "\n\n" + EPISTEMIC_VERB_RULE_EN
    + "\n\n" + PLAIN_LANGUAGE_RULE_EN
)


# ── الفصل الصلب: لغة الأدلة الداخلية ≠ لغة تقرير العميل (تصحيح المالك ٢) ────
#
# البعثات الاثنتا عشرة تبقى عربيةً (طبقة أدلة واحدة — §17). فحين يُطلَب تقريرٌ
# إنجليزيّ يستقبل الكاتبُ حقائقَ عربية ويجب أن يُخرج نصّاً إنجليزياً خالصاً.
# هذا **توليدٌ من الدليل لا ترجمةُ تقرير**: النموذج يقرأ الحقيقة ويكتب معناها
# بالإنجليزية، ولا ينسخ جملةً عربية ولا يخترع ما ليس في الدليل.
#
# هذا الإلزام **طبقةُ توجيهٍ واحدة من ثلاث**؛ الطبقتان الأخريان بنيويّتان:
# النصوص القالبية تُولَّد من مفاتيح `silk_i18n`، والبوابة الحاجزة
# `_check_language_consistency` ترفض التصدير عند أيّ تسرّب.
EVIDENCE_LANGUAGE_FIREWALL_EN = (
    "**Output language (absolute):** write the entire report in English. The "
    "evidence you are given may be recorded in Arabic — that is the internal "
    "research language of this system. Read it, understand it, and express "
    "each fact in your own natural business English. **Never copy an Arabic "
    "phrase, clause, or sentence into the report**, not even inside "
    "quotation marks or brackets. This is generation from evidence, not "
    "translation of a document: no transliteration, no Arabic script "
    "anywhere in your output. The only exceptions are proper names that have "
    "no English form — and where an entity has a known English name, use it. "
    "If a fact is unclear to you, declare the gap in English rather than "
    "reproducing the Arabic or guessing at its meaning."
)
