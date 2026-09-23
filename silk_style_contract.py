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

import functools

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
    # الصنف ١ (موجة عيوب التقرير): «العمود» مفردةُ قياسٍ داخلية، والمفردةُ
    # المعتمدة على سطح القارئ «الجانب» (`silk_i18n.pillar_col` = «الجانب»،
    # و`cond_pillar_weak` = «جانب {pillar} ضعيف»). كان الزوجُ يغطّي «الدرجة
    # الموزونة» وحدها، فأفلتت «العمود الأقوى/الأضعف» من سردِ المحرّك
    # (`silk_decision.counter_case`) إلى `counter_case_line` ثمّ إلى **docx
    # العميل** (`silk_reports.py:4012`) — إعادةُ إنتاجٍ مباشرة على مدوّنة
    # الجزائر. الجذرُ مُصلَحٌ في منشأ السرد؛ وهذه شبكةُ أمانٍ للمدوّنات
    # المخزَّنة قبل الإصلاح (سابقة `test_weighted_score_sanitized_as_backstop`).
    # الأطولُ أولاً كي لا يبتلعَ استبدالٌ جزءاً من آخر.
    ("العمود الأقوى", "أقوى الجوانب"),
    ("العمود الأضعف", "أضعف الجوانب"),
    ("أقوى الأعمدة", "أقوى الجوانب"),
    ("أضعف الأعمدة", "أضعف الجوانب"),
    ("الأعمدة مجتمعة", "الجوانب مجتمعة"),
    ("أقوى عمود", "أقوى جانب"),
    ("أضعف عمود", "أضعف جانب"),
    ("عمود ضعيف", "جانب ضعيف"),
    ("عمود قوي", "جانب قوي"),
    ("عمود واحد", "جانب واحد"),
    ("لا أعمدة محسوبة", "لا جوانب محسوبة"),
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


# ════════════════════════════════════════════════════════════════════════════
# الصنف ١ (موجة عيوب التقرير) — لغةُ القارئ · reader-facing language
# ════════════════════════════════════════════════════════════════════════════
# بلاغُ المالك: عباراتٌ كُتبت لمطوّرٍ وصلت صاحبَ القرار («لم يتمكن الاستدعاء من
# جلب أي سجل»، «عطل تقني في واجهة»، «خارج أساس الحكم الآلي»…).
#
# **إعلانُ ما ثبت (صنفُ الدليل: static code review + direct reproduction):**
# سبعٌ من العشر المرصودة **لا توجد في هذا المستودع إطلاقاً** — فلا قالبَ
# أنتجها، وهي من نثرِ الكاتب (النموذج). الموجودةُ ثلاثٌ فقط، وكلُّها مُصلَحةٌ
# في منشئها بهذه الموجة:
#   - «تقاطع المحلل بلا أدلة كافية» — `silk_i18n.limit_analyst_thin`
#   - «العمود الأقوى/الأضعف» — `silk_decision.counter_case` (أُعيد إنتاجُ
#     وصولها إلى docx العميل مباشرةً على مدوّنة الجزائر)
#   - «هامش المضاهاة» — كانت تُطبَع في العرض وتُحظَر في الموجّه معاً
# ولذلك فالحارسُ الوحيد الممكن لما لا قالبَ له هو **قائمةٌ حتمية** تُفحَص
# على كلّ تقرير: القوائمُ هنا (مصدرٌ واحد) والفحصُ في
# `silk_quality_gate._check_reader_language_leak`.

# (١) عباراتٌ حرفيةٌ لا تصلح لقارئٍ بأيّ سياق — بذرتُها العشرُ المرصودة.
FORBIDDEN_READER_PHRASES: tuple = (
    "لم تصل معادلة محسوبة مسبقاً",
    "لم يتمكن الاستدعاء من جلب أي سجل",
    "عطل تقني في واجهة",
    "خارج أساس الحكم الآلي",
    "بعثة بحثية",
    "تقاطع المحلل بلا أدلة كافية",
    "وحدة نقدية",
    "وحدة ريال لكل دولار",
    "العمود الأقوى",
    "العمود الأضعف",
    "هامش المضاهاة",
    "بفئة تكلفة",
)

# (٢) رموزٌ لا معنى لها عند قارئٍ بشريّ في أيّ سياق — تُلتقَط عارية.
# `{`/`}` قوسا قالبٍ لم يُحشَ (يغطّيهما الصنف ٢ أيضاً)، وBقيتُها مفرداتُ
# برمجةٍ خام. `N/A` تُلتقَط لأن معجمَ الغياب المعتمَد عربيٌّ ثنائيّ
# («غير متاح» / «غير محسوب» — `silk_quality_gate._ABSENCE_FORBIDDEN`).
HARD_READER_TOKENS: tuple = (
    "pipeline", "null", "undefined", "NaN", "N/A", "{", "}", "استدعاء",
)

# (٣) مفرداتٌ **ذاتُ معنيين**: مشروعةٌ بمعناها التجاري، ولغةُ نظامٍ بمعناها
# التقني. تُفحَص بالسياق لا عارية — وهذا شرطُ صدقٍ لا تسامحاً: «معادلة» وردت
# ١١ مرّة في خطّ الأساس كلُّها **مأمورٌ بها** في معيار الكتابة («معادلة
# التعادل = كلفة الدخول ÷ هامش الوحدة»)، فحظرُها عارياً يُطلِق على كلّ تقرير
# صحيح. و«واجهة» كانت تُلتقَط من داخل «مواجهة» بلا حدِّ كلمة.
CONTEXTUAL_READER_TOKENS: tuple = ("واجهة", "معادلة", "آلي", "آلياً", "آليّاً")

# قرائنُ المعنى التقنيّ — وجودُ إحداها قربَ المفردة (± ٤٠ محرفاً) يجعلها
# لغةَ نظام. مبنيّةٌ على مفرداتِ السباكة التي يعرفها هذا المستودع فعلاً.
SYSTEM_SENSE_CUES: tuple = (
    "النظام", "نظامنا", "الحقل", "حقل", "سجل", "السجل", "طبقة", "الطبقة",
    "قاعدة البيانات", "الخادم", "المخزن", "التشغيل", "عطل", "تعذّر",
    "تعذر", "فشل", "خطأ", "استدعاء", "واجهة برمجية", "مُصنَّف", "مصنَّف",
    "صُنِّف", "صنِّف", "التصنيف الآلي", "الحكم الآلي", "محسوبة مسبقاً",
)

# استثناءاتُ المعنى التجاريّ الصريح — تُفحَص أوّلاً فتمنع الإنذار الكاذب.
READER_TOKEN_ALLOW: tuple = (
    "واجهة المتجر", "واجهة الرف", "واجهة العرض", "واجهة المحل",
    "خط إنتاج آلي", "خطّ إنتاج آلي", "تعبئة آلية", "فرز آلي",
)

# القاعدةُ المحقونةُ في عقود الكاتب والمراجع — إلحاقٌ لا استبدال (نمط
# `EPISTEMIC_VERB_RULE`). لا تُكرِّر ما في معيار الكتابة؛ تضيف بُعداً واحداً:
# **من يقرأ**.
READER_LANGUAGE_RULE = (
    "**لغةُ القارئ (إلزامي — القارئ صاحبُ قرارٍ تجاريّ لا مهندسُ النظام):**\n"
    "- عربيةٌ فصحى مهنية، وترقيمٌ عربيّ (، ؛ ؟) لا لاتينيّ.\n"
    "- **لا تصف النظامَ ولا عملَه**: لا «استدعاء» ولا «واجهة» ولا «طبقة "
    "عرض» ولا «حقل» ولا «سجل» ولا «بعثة» ولا «تقاطع محلل» ولا «معادلة "
    "محسوبة مسبقاً» ولا «الحكم الآلي». هذه أسماءُ أجزاءٍ من أداةٍ داخلية "
    "لا يعرفها القارئ ولا يستطيع التصرّف بها.\n"
    "- **العجزُ يُقال بأثره على القرار لا بسببه التقنيّ**: «لم نجد سعر "
    "تجزئة مرصوداً لهذا الصنف، فلا تُحسَب نقطة التعادل» — لا «تعذّر جلب "
    "السجل» ولا «عطل تقني».\n"
    "- **مفردتا الغياب المعتمدتان اثنتان فقط**: «غير متاح» (لا وجود "
    "للرقم) و«غير محسوب» (يوجد ولم يُحسب). لا `N/A` ولا رمزٌ إنجليزيّ.\n"
    "- **مفرداتُ التقييم بلغة القارئ**: «الجانب» لا «العمود»، و«قوة "
    "الفرصة» لا «الدرجة الموزونة»، و«فارق السعر التنافسي» لا «هامش "
    "المضاهاة».\n"
    "- **نوِّع الروابط**: لا تفتتح أكثر من فقرةٍ واحدة في القسم بالرابط "
    "نفسه، ولا تُعِد «وهذا يعني» في فقرتين متجاورتين — للمعنى الواحد "
    "صيغٌ عدّة (ومن ثمّ، فـ، لذلك، والأثرُ العمليّ)."
)

READER_LANGUAGE_RULE_EN = (
    "**Reader's language (mandatory — your reader is a commercial "
    "decision-maker, not the system's engineer):**\n"
    "- Never describe the system or its internals: no \"call\", "
    "\"interface\", \"render layer\", \"field\", \"record\", "
    "\"mission\", \"analyst intersection\", \"pre-computed equation\" "
    "or \"automated verdict\".\n"
    "- State a shortfall by its effect on the decision, never by its "
    "technical cause: \"no observed retail price for this item, so the "
    "break-even cannot be computed\" — not \"record fetch failed\".\n"
    "- Exactly two absence words: \"not available\" (the figure does not "
    "exist) and \"not computed\" (it exists and was not computed). Never "
    "N/A, null or NaN.\n"
    "- Vary connectives: no two adjacent paragraphs may open with the same "
    "connective, and never repeat \"this means\" twice in a row."
)


# ── الصنف ٢ (موجة عيوب التقرير): سلامةُ الإحالة · referential integrity ─────
# القوالبُ مُصلَحةٌ حتمياً (`silk_i18n.t` + صيغُ الفراغ)، لكنّ الكاتبَ يركّب
# جملاً من النوع نفسِه بنفسه — «ثم السعودية بالحصة السعودية»، و«الشريحة
# المحسوبة أعلاه» لشريحةٍ أُعلِن أن حجمها غير محسوب. لا قالبَ يُصلَح فيها،
# فالقاعدةُ توجيهٌ والفحصُ إنفاذ (`_check_template_interpolation`).
REFERENTIAL_INTEGRITY_RULE = (
    "**سلامةُ الإحالة (إلزامي — لا تُحِل إلى ما لم يُعرَض):**\n"
    "- **لا «أعلاه» ولا «أدناه» لرقمٍ أو شريحةٍ أعلنتَ أنها «غير محسوبة» "
    "أو «غير متاحة».** إن لم يُحسَب فقُل ما ينقص لحسابه، لا تُحِل القارئَ "
    "إلى فراغ.\n"
    "- **العددُ المذكور يطابق المعدود**: لا «شرطين مفتوحين» ثم شرطٌ واحد "
    "في القائمة. اكتب العددَ من القائمة التي ستسردها، أو اسرِدها بلا عدد.\n"
    "- **لا تُعِد اسمَ الكيان داخل وصفِه**: «ثم السعودية بحصة 10.44%» لا "
    "«ثم السعودية بالحصة السعودية البالغة 10.44%».\n"
    "- **لا تشرح مصطلحاً بين قوسين وسط الجملة** بكلمةٍ من المصطلح نفسِه "
    "(«مؤشر التركّز (مؤشر يقيس التركّز)») — التعريفُ مرّةً واحدة في "
    "المنهجية، والمتنُ يستعمل المعنى لا الاسمَ ثم شرحَه."
)

REFERENTIAL_INTEGRITY_RULE_EN = (
    "**Referential integrity (mandatory — never point at what was not "
    "shown):**\n"
    "- No \"above\" or \"below\" for a figure or segment you declared "
    "\"not computed\" or \"not available\". If it was not computed, say "
    "what is missing to compute it; do not send the reader to an empty spot.\n"
    "- A stated count must match what you then list: never \"two open "
    "conditions\" followed by one. Take the number from the list you are "
    "about to write, or list them without a count.\n"
    "- Never repeat an entity's name inside its own description.\n"
    "- Never gloss a term mid-sentence with a word from the term itself — "
    "define it once in the methodology and use the meaning in the body."
)


# ── الصنف ٥ (موجة عيوب التقرير): شرحٌ واحدٌ لكلّ حقيقة · single explanation ──
# بلاغُ المالك: القرارُ التنظيميّ نفسُه مشروحٌ في خمسة أقسام، و«وهذا يعني»
# في كلّ فقرةٍ تقريباً. الجذرُ: كلُّ قسمٍ يُولَّد باستقلالٍ فلا يعرف ما شُرِح
# قبله. القاعدةُ توجيهٌ، والفحصُ إنفاذ (`cross_section_near_duplicate` و
# `connector_repeated_in_paragraph`).
#
# **مفاتيحُ الروابط مصدرٌ واحد** يقرؤه الموجّهُ والفحص: قاعدةٌ تحظر رابطاً
# لا يعدّه فحصٌ أمنيةٌ لا قاعدة.
REPEATED_CONNECTORS: tuple = (
    "وهذا يعني", "هذا يعني", "ومعنى ذلك", "ما يعني", "وبالتالي", "بالتالي",
    "من ناحية", "علاوة على ذلك", "بالإضافة إلى", "من جهة أخرى",
    "إضافة إلى ذلك", "ومن ثم", "لذلك", "وعليه", "في المقابل", "ومع ذلك",
    "كما أن", "جدير بالذكر",
)

REPEATED_CONNECTORS_EN: tuple = (
    "this means", "which means", "therefore", "as a result",
    "in addition", "furthermore", "moreover", "on the other hand",
    "that said", "it is worth noting", "consequently",
)

SINGLE_EXPLANATION_RULE = (
    "**شرحٌ واحدٌ لكلّ حقيقة (إلزامي — التكرارُ يُطيل ولا يُقنع):**\n"
    "- **لكلّ حقيقةٍ قسمٌ واحدٌ يشرحها كاملةً**: القرارُ التنظيميّ في "
    "قسم التنظيم، والمنافسةُ في قسمها، والسعرُ في قسمه. حين تحتاجها في "
    "قسمٍ آخر فاذكرها **بجملةٍ واحدة** تُحيل إلى قسمها ولا تُعيد شرحها: "
    "«يبقى قيدُ الإدراج المذكور في التنظيم حاجزاً أمام أول شحنة» — لا "
    "إعادةَ سردِ اللائحة ورقمِها وأثرِها من جديد.\n"
    "- **لا فقرةَ تُختَم بما افتتحته**: إن لم تُضِف الجملةُ الأخيرة معلومةً "
    "أو نتيجةً لم تُقَل، احذفها.\n"
    "- **الرابطُ لا يتكرّر في الفقرة الواحدة**: لا «وهذا يعني» مرّتين في "
    "فقرة، ولا في فقرتين متجاورتين. للمعنى الواحد صيغٌ عدّة (ومن ثمّ، فـ، "
    "والأثرُ العمليّ، ويترتّب على ذلك) — أو اذكر النتيجة مباشرةً بلا رابط."
)

SINGLE_EXPLANATION_RULE_EN = (
    "**One explanation per fact (mandatory — repetition lengthens without "
    "persuading):**\n"
    "- **Each fact has exactly one section that explains it in full.** Where "
    "you need it elsewhere, state it in **one sentence** that points back to "
    "that section and do not re-explain it.\n"
    "- **No paragraph may close on what it opened with**: if the last "
    "sentence adds no information or conclusion not already stated, cut it.\n"
    "- **Never repeat a connective inside one paragraph**, and not in two "
    "adjacent paragraphs either — vary it, or state the conclusion with no "
    "connective at all."
)


def single_explanation_rule(lang: str = "ar") -> str:
    """قاعدةُ الشرح الواحد بلغة التقرير — مصدرٌ واحد للموجّه والفحص."""
    return SINGLE_EXPLANATION_RULE_EN if str(lang).lower().startswith("en") \
        else SINGLE_EXPLANATION_RULE


def referential_integrity_rule(lang: str = "ar") -> str:
    """قاعدةُ سلامة الإحالة بلغة التقرير — مصدرٌ واحد للموجّه والفحص."""
    return REFERENTIAL_INTEGRITY_RULE_EN if str(lang).lower().startswith("en") \
        else REFERENTIAL_INTEGRITY_RULE


def reader_language_rule(lang: str = "ar") -> str:
    """القاعدةُ بلغة التقرير — مصدرٌ واحد للموجّه والمراجع والفحص."""
    return READER_LANGUAGE_RULE_EN if str(lang).lower().startswith("en") \
        else READER_LANGUAGE_RULE

# WP-1 §4 — سُلَّم معايرة الثقة الواحد: المصدر الوحيد لعتبات نطاقات الثقة
# المعروضة على وجه التقرير. الثقة المعروضة هي ثقة المحرّك الحتمي المحسوبة،
# لا التقرير الذاتي غير المعاير من النموذج؛ والتسمية العربية تُشتقّ من
# الرقم عبر `confidence_band_label` حصراً — يستهلكه العارض
# (silk_narrative.confidence_phrase) وحارس البوابة
# (silk_quality_gate._check_confidence_band_label) معاً فلا يتباعدان.
CONFIDENCE_HIGH_MIN_PCT = 80    # عالية ≥ 80%
CONFIDENCE_MEDIUM_MIN_PCT = 60  # متوسطة 60–79% / منخفضة < 60%


# الصنف ٨ (موجة عيوب التقرير): ترتيبُ النطاقات لتطبيق سقفٍ عليها.
_BAND_ORDER: tuple = ("low", "medium", "high")


def confidence_band_label(pct: float, lang: str = "ar",
                          cap: "str | None" = None) -> str:
    """تسمية نطاق الثقة من النسبة المئوية — المشتقّ الوحيد.

    الموجة ٠: **العتبات لا تتغيّر بتغيّر اللغة** (٨٠٪ / ٦٠٪ في اللغتين) —
    النطاق حكمٌ حسابيّ، والتسمية وحدها معروضة. العربية تبقى حرفياً كما هي.

    الصنف ٨: `cap` سقفٌ اختياريّ (`"medium"`) يمنع تسميةَ «عالية» حين يكون
    عمودٌ أساسيٌّ مجهولاً أو الشروطُ المفتوحة اثنتين — **الرقمُ لا يُمَسّ،
    التسميةُ وحدها تُسقَّف**، فلا قيمةَ مخزَّنة تتغيّر. القاعدةُ تُقال
    للقارئ: «لا نقول ثقةً عالية ونحن لا نعرف الربحية».
    """
    if pct >= CONFIDENCE_HIGH_MIN_PCT:
        band = "high"
    elif pct >= CONFIDENCE_MEDIUM_MIN_PCT:
        band = "medium"
    else:
        band = "low"
    if cap in _BAND_ORDER and \
            _BAND_ORDER.index(band) > _BAND_ORDER.index(cap):
        band = cap
    if str(lang or "ar").lower() != "en":
        return {"high": "عالية", "medium": "متوسطة", "low": "منخفضة"}[band]
    import silk_i18n
    return silk_i18n.t(f"confidence_{band}", "en")


# ترتيب الفحص: الأطول أولاً كي لا يبتلع اختصارٌ جزءاً من آخر عند البحث.
GLOSSARY_ORDER: list[tuple[str, str]] = sorted(
    GLOSSARY.items(), key=lambda kv: -len(kv[0]))

# ════════════════════════════════════════════════════════════════════════════
# الصنف ٤ (موجة عيوب التقرير) — انزياحُ التسمية والمصطلح
# ════════════════════════════════════════════════════════════════════════════
# بلاغُ المالك ثلاثةُ عيوبٍ في عائلةٍ واحدة: (أ) «الحكومة الحوثية» و«السلطات
# الحوثية» و«الحكومة» لنفس الجهة في تقريرٍ واحد، (ب) تسمياتُ نشاطٍ إنجليزية
# («Import export company»، «Food broker») في جدولٍ عربيّ، (ج) مصطلحاتٌ
# تُستعمَل بلا تعريف (المرآة، عتباتُ التركّز، سعرُ الحدود، نسبةُ التحقّق).
#
# **(ب) مغطّاةٌ أصلاً بحاجز**: `_check_language_consistency` يُفشِل على مقطعٍ
# إنجليزيٍّ في مستندٍ عربيّ — مقيسٌ على «| Import export company |». الناقصُ
# كان **الفكس**: الجدولُ يُبنى من `category` الخام
# (`silk_gmaps.py`) بلا ترجمة، فكان الحاجزُ يحجب تقريراً صحيحاً بدل أن
# تُترجَم الخليّة. الترجمةُ أدناه، والحاجزُ يبقى حارسَه.

# (أ) تسمياتُ النشاط من مصادرَ خارجية (تصنيف خرائط قوقل وأمثالها) → عربيّ.
# جدولُ **ترجمةٍ** لا تفسير: المفتاحُ مُطبَّعٌ صغيراً بلا فواصل.
ACTIVITY_LABEL_AR: dict[str, str] = {
    "import export company": "شركة استيراد وتصدير",
    "importer": "مستورد",
    "exporter": "مصدّر",
    "food broker": "وسيط أغذية",
    "food products supplier": "مورّد منتجات غذائية",
    "wholesaler": "تاجر جملة",
    "wholesale grocer": "تاجر جملة بقالة",
    "distributor": "موزّع",
    "food manufacturer": "مصنع أغذية",
    "grocery store": "بقالة",
    "supermarket": "سوق مركزي",
    "hypermarket": "هايبرماركت",
    "convenience store": "متجر ملائم",
    "trading company": "شركة تجارية",
    "general store": "متجر عام",
    "warehouse": "مستودع",
    "logistics service": "خدمة لوجستية",
    "freight forwarding service": "وكالة شحن",
    "customs broker": "مخلّص جمركي",
    "confectionery": "حلويات",
    "candy store": "متجر حلويات",
    "dairy store": "متجر ألبان",
    "dairy farm": "مزرعة ألبان",
    "auto parts store": "متجر قطع غيار",
    # ── الدرس ٢٥٥ — تسمياتٌ **مقيسةٌ من تقارير حيّة** لا مُختلَقة ──────────
    # (دراسة ماليزيا × قهوة محمصة، ٢٠٢٦-٠٩-١٧): جدولُ العملاء المحتملين حمل
    # `Greengrocer` و`Seafood wholesaler` و`Confectionery wholesaler` و
    # `Consultant` **بالإنجليزية داخل جدولٍ عربيّ**، لأن الجدولَ لم يعرفها
    # (٢٤ مدخلاً) فأعادها `activity_label_ar` كما هي. تُعرَّب هنا، فيزول
    # خلطُ اللغة؛ وتصنيفُ صلتِها بالمنتج شيءٌ آخر (انظر قائمةَ السماح).
    "greengrocer": "بائع خضار وفواكه",
    "seafood wholesaler": "تاجر جملة مأكولات بحرية",
    "confectionery wholesaler": "تاجر جملة حلويات",
    "food wholesaler": "تاجر جملة أغذية",
    "beverage distributor": "موزّع مشروبات",
    "coffee wholesaler": "تاجر جملة قهوة",
    "coffee store": "متجر قهوة",
    "spice store": "متجر بهارات",
    "butcher shop": "ملحمة",
    "bakery": "مخبز",
    # ── مقدّمو خدماتٍ **ليسوا أطرافاً تجارية لأيّ منتج** (منعٌ عامّ لا
    # يتعلّق بفئة المنتج إطلاقاً — ولذلك يصحّ عامّاً): ظهر `Consultant`
    # صفّاً أوّلَ في جدول تلك الدراسة وهو لا يستورد ولا يوزّع ولا يخلّص.
    "consultant": "مستشار",
    "business management consultant": "مستشار إدارة أعمال",
    "consulting agency": "مكتب استشارات",
    "marketing agency": "وكالة تسويق",
    "advertising agency": "وكالة إعلان",
    "law firm": "مكتب محاماة",
    "accounting firm": "مكتب محاسبة",
    "bank": "بنك",
    "insurance agency": "وكالة تأمين",
    "real estate agency": "مكتب عقارات",
}


# ── الصنف ١٠: قائمةُ سماحِ النشاط · lead activity allow-list ───────────────
# **العيبُ المرصود:** قائمةُ الروابط حملت «متجر قطع غيار» بينما غاب عنها
# الموزّعون الذين يوصي بهم التقريرُ نفسُه. و`_clean_leads` يُنقّي بالاسم
# والجغرافيا والحشو **لا بالنشاط** — فلا مِصفاةَ تمنع نشاطاً لا صلةَ له.
#
# القائمةُ **بياناتٌ لا تفريعُ سوق**: نشاطٌ يُشترى منه أو يُوزَّع عبره أو
# يُخلّص به. والنشاطُ **غيرُ المُدرَج في الجدول يمرّ** (سياسةُ
# `activity_label_ar` نفسُها): الجهلُ بالتسمية ليس دليلَ عدمِ الصلة، والمنعُ
# يكون بنشاطٍ مُدرَجٍ **ومستبعَدٍ صريحاً** لا بنشاطٍ مجهول.
LEAD_ACTIVITY_ALLOWED: frozenset = frozenset({
    "import export company", "importer", "exporter", "food broker",
    "food products supplier", "wholesaler", "wholesale grocer",
    "distributor", "food manufacturer", "grocery store", "supermarket",
    "hypermarket", "convenience store", "trading company", "general store",
    "warehouse", "logistics service", "freight forwarding service",
    "customs broker", "confectionery", "candy store", "dairy store",
    "dairy farm",
    # ── الدرس ٢٥٥ — أطرافٌ تجاريةٌ مقيسةٌ من تقارير حيّة ───────────────────
    # تُدرَج **مسموحةً**: كلُّها تشتري أو توزّع سلعاً، وكونُ بائعِ الخضار
    # غيرَ ذي صلةٍ بالقهوة تحديداً هو **محورُ مطابقةِ فئةِ المنتج** لا محورُ
    # «طرفٌ تجاريّ أم لا» — والمِصفاةُ هنا عامّةٌ بالتصميم (لا تفريعَ منتج).
    # فحصرُها على فئةِ المنتج قرارُ مالكٍ مفتوحٌ مُعلَنٌ في
    # `docs/report-quality/LOGIC_ISSUES.md`، لا يُقرَّر هنا ضمناً: منعُ
    # «ملحمة» عامّاً يُسقِط الرابطَ الصحيحَ لمصدّرِ لحوم.
    "greengrocer", "seafood wholesaler", "confectionery wholesaler",
    "food wholesaler", "beverage distributor", "coffee wholesaler",
    "coffee store", "spice store", "butcher shop", "bakery",
    # وما **لا** يُدرَج هنا وهو في جدول التعريب أعلاه = ممنوعٌ صريحاً:
    # مقدّمو الخدمات (مستشار/محاماة/محاسبة/تسويق/بنك/تأمين/عقارات) ومتجرُ
    # قطع الغيار — ليسوا أطرافاً تجاريةً لأيّ منتجٍ مُصدَّر.
})


def _activity_key(raw: object) -> str:
    """مفتاحُ النشاط المطبَّع — المصدرُ الواحد للمِصفاة وللعرض معاً."""
    return " ".join(str(raw or "").strip().lower().replace("_", " ").split())


def lead_activity_allowed(raw: object) -> bool:
    """هل نشاطُ الرابط ضمن السماح؟ — والمجهولُ يمرّ (انظر أعلاه).

    المطابقةُ على التسميةِ الخام **وعلى ترجمتها** كلتيهما، فرابطٌ خُزِّن
    مترجَماً (المسارُ يترجم عند `_clean_leads`) لا يصير مجهولاً بالترجمة.
    """
    given = str(raw or "").strip()
    if not given:
        return True
    # مأخذُ المراجعة الذاتية: التطبيعُ هنا كان `lower()` وحدَه بينما
    # `activity_label_ar` يطوي الشرطةَ السفلى والفراغَ — فـ«Auto_parts_store»
    # تمرّ المِصفاةَ ثمّ تُعرَض «متجر قطع غيار» المستبعَدة. مُطبِّعٌ **واحد**
    # للطرفين كي لا يفترقا مرّةً أخرى.
    key = _activity_key(given)
    # تُحلّ التسميةُ العربية إلى مفتاحها الخام أوّلاً — وإلّا مرّ «متجر قطع
    # غيار» المترجَمُ بينما يُمنَع أصلُه الإنجليزيّ (قِياسٌ على هذه الدالّة
    # نفسِها كشف العيبَ قبل الشحن).
    if key not in ACTIVITY_LABEL_AR:
        for k, v in ACTIVITY_LABEL_AR.items():
            if v == given:
                key = k
                break
    if key in LEAD_ACTIVITY_ALLOWED:
        return True
    return key not in ACTIVITY_LABEL_AR


# ── الدرس ٢٦٣: صلةُ الرابط بالمنتج · lead ↔ product relevance ──────────────
# **العيبُ المرصود (بلاغ المالك):** «مؤسسة النخبة لقطع الغيار» في قائمة
# موزّعي الطحينة. `lead_activity_allowed` عامّةٌ بالتصميم (لا تفريعَ منتج)
# فمرّ نشاطٌ مُدرَجٌ لا صلةَ له بفئة المنتج، وكان الحسمُ قرارَ مالكٍ معلَّقاً
# في `docs/report-quality/LOGIC_ISSUES.md` — وقد حُسِم: احذف غير المرتبط.
#
# المحورُ الثاني الذي كان ناقصاً: **فئةُ المنتج من فصل HS × فئةُ نشاط
# الرابط**. النشاطُ المُدرَجُ الذي يخدم فئةً **أخرى** يُسقَط بسببٍ مسمّى؛
# والنشاطُ العامّ (استيراد/تجارة/جملة/لوجستيات) يخدم كلَّ الفئات فيمرّ.
#
# وكلماتُ المنتج **بثلاث لغات** (عربية/إنجليزية/لغة السوق —
# `data/product_terms_l1.csv`) تُبقي رابطاً لا تحذفه: «Pastificio Milano Srl»
# صانعُ معكرونة إيطاليّ بلا كلمةٍ عربيةٍ ولا إنجليزية في اسمه.

#: نشاطٌ **يخدم كلَّ الفئات** — وسيطٌ تجاريّ أو ناقلٌ لا يتخصّص بسلعة.
_ACTIVITY_CATEGORY_FREE: frozenset = frozenset({
    "import export company", "importer", "exporter", "wholesaler",
    "distributor", "trading company", "general store", "warehouse",
    "logistics service", "freight forwarding service", "customs broker",
})
#: مقدّمو خدماتٍ **ليسوا طرفاً تجارياً لأيّ منتج** — لا يشترون ولا يوزّعون
#: ولا يخلّصون. استبعادُهم مقرَّرٌ في الريبو أصلاً (خارج `LEAD_ACTIVITY_
#: ALLOWED`) وهو **مستقلٌّ عن فئة المنتج**، فيسري بلا راية.
_ACTIVITY_NON_TRADE: frozenset = frozenset({
    "consultant", "business management consultant", "consulting agency",
    "marketing agency", "advertising agency", "law firm", "accounting firm",
    "bank", "insurance agency", "real estate agency",
})
#: نشاطٌ مُدرَجٌ يخدم فئةً بعينها — خارجَها يُسقَط بسببٍ مسمّى.
_ACTIVITY_CATEGORY: dict = {
    "منتج غذائي/زراعي": frozenset({
        "food broker", "food products supplier", "wholesale grocer",
        "food manufacturer", "grocery store", "supermarket", "hypermarket",
        "convenience store", "confectionery", "candy store", "dairy store",
        "dairy farm", "greengrocer", "seafood wholesaler",
        "confectionery wholesaler", "food wholesaler", "beverage distributor",
        "coffee wholesaler", "coffee store", "spice store", "butcher shop",
        "bakery"}),
    "مركبات/معدّات نقل": frozenset({"auto parts store"}),
}


#: نشاطٌ غذائيٌّ **متخصّصٌ بمنتجٍ بعينه** ⇒ فصولُ HS التي يخدمها (تقرير ٧
#: §4.4). فئةُ «منتج غذائي/زراعي» واحدةٌ للفصول ١–٢٤ فلا تُفرّق بين تاجر
#: مأكولاتٍ بحرية وتاجر قهوة؛ هذا هو المحورُ الثاني الذي طلبه
#: `LOGIC_ISSUES.md`: فصلُ المنتج × نشاطُ الرابط. الملحمةُ تبقى لمصدّر
#: اللحوم، وبائعُ الخضار لمصدّر الخضار والفواكه — لا منعٌ عامّ.
_ACTIVITY_HS_CHAPTERS: dict = {
    # بادئاتُ HS (فصلٌ أو بندٌ رباعيّ) — البندُ حيث يخلط الفصلُ منتجاتٍ لا
    # صلةَ بينها (العسلُ في الفصل ٠٤ مع الألبان، والطحينةُ في ٢٠ مع العصائر).
    "seafood wholesaler": frozenset({"03", "1604", "1605"}),
    "greengrocer": frozenset({"07", "08"}),
    "butcher shop": frozenset({"02", "1601", "1602"}),
    "bakery": frozenset({"1101", "1901", "1905"}),
    "dairy store": frozenset({"0401", "0402", "0403", "0404", "0405", "0406"}),
    "dairy farm": frozenset({"0401", "0402", "0403", "0404", "0405", "0406"}),
    "coffee wholesaler": frozenset({"0901", "2101"}),
    "coffee store": frozenset({"0901", "2101"}),
    "spice store": frozenset({"0904", "0905", "0906", "0907", "0908", "0909",
                              "0910"}),
    "confectionery": frozenset({"1704", "1806", "1905"}),
    "candy store": frozenset({"1704", "1806"}),
    "confectionery wholesaler": frozenset({"1704", "1806", "1905"}),
}

#: أوصافٌ عامّة في اسم المنتج لا تميّزه («محمصة» تطابق «محمصة المكسرات»
#: لمنتج «قهوة محمصة»، و«Fresh» تطابق «Fresh Seafood» لمنتج «Fresh Dates»).
_GENERIC_PRODUCT_WORDS = frozenset({
    "fresh", "dried", "roasted", "natural", "organic", "premium", "frozen",
    "raw", "pure", "processed", "prepared", "other", "whole", "ground",
    "طازج", "طازجة", "محمص", "محمصة", "مجفف", "مجففة", "طبيعي", "طبيعية",
    "عضوي", "عضوية", "مجمد", "مجمدة", "خام", "مطحون", "مطحونة", "فاخر",
    "فاخرة", "مصنّع", "مصنع", "أخرى",
})

#: حالةُ دليل الصلة لكلّ جهةٍ تُعرَض (تقرير ٧ §4.4) — تُكتَب على الرابط ولا
#: تُحذَف بها البياناتُ الخام: متخصّصٌ مثبت، تاجرٌ عامّ قابلٌ للتحقق، أو جهةٌ
#: ذكرها التحليلُ بلا دليلِ صلةٍ مستقلّ.
EVIDENCE_SPECIALIST = "specialist"
EVIDENCE_GENERAL = "general_trader"
EVIDENCE_NAMED = "named_unverified"


def _hs_digits(hs_code: object) -> str:
    return "".join(ch for ch in str(hs_code or "") if ch.isdigit())


@functools.lru_cache(maxsize=4096)
def _word_re(word: str):
    import re as _re
    w = str(word or "").strip().lower()
    if not w:
        return None
    if _re.search(r"[\u0621-\u064a]", w):
        pat = (r"(?<![\u0621-\u064a])[وفبكل]{0,2}(?:ال)?" + _re.escape(w)
               + r"(?![\u0621-\u064a])")
    else:
        pat = r"(?<![a-z0-9])" + _re.escape(w) + r"(?![a-z0-9])"
    return _re.compile(pat)


def _word_in(text: str, word: str) -> bool:
    """كلمةٌ كاملة لا جزءُ كلمة: «food» لا تطابق «seafood»، و«بن» لا تطابق
    «لبنان». الاسمُ العربيّ يُسمَح قبله بأداةِ جرٍّ/عطفٍ/تعريفٍ ملتصقة."""
    rx = _word_re(str(word or ""))
    return bool(rx and rx.search(text))


@functools.lru_cache(maxsize=1)
def _hs_keywords() -> dict:
    """{رمز سداسيّ: كلماتُه المنسَّقة} — قراءةٌ واحدة لـ`hs_codes.csv` يتشاركها
    القارئان (مراجعة §58: نسختان من المسح بقاعدتَي مطابقة مختلفتين)."""
    import csv
    import os
    out: dict = {}
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "hs_codes.csv")
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                code = (row.get("hs_code") or "").strip()
                if code:
                    out[code] = frozenset(
                        k.strip().lower()
                        for k in (row.get("keywords") or "").split(",")
                        if len(k.strip()) >= 3)
    except Exception:  # noqa: BLE001 — المرجعُ مساعدٌ لا شرط
        return {}
    return out


def _lead_text(lead: object) -> str:
    fields = ("name", "category", "activity", "description", "snippet",
              "title")
    return " ".join(str((lead or {}).get(f) or "") for f in fields
                    if isinstance(lead, dict)).lower()


def _activity_key_of(lead: object) -> str:
    raw = str((lead or {}).get("category") or "").strip() \
        if isinstance(lead, dict) else ""
    if not raw:
        return ""
    key = _activity_key(raw)
    if key not in ACTIVITY_LABEL_AR:
        for k, v in ACTIVITY_LABEL_AR.items():
            if v == raw:
                return k
    return key


_FORBIDDEN_TERMS_PATH = __import__("os").path.join(
    __import__("os").path.dirname(__import__("os").path.abspath(__file__)),
    "data", "client_forbidden_terms_l1.csv")


@functools.lru_cache(maxsize=1)
def client_forbidden_terms() -> tuple:
    """قائمةُ الممنوعات القابلةُ للتحديث بلا كود (الموجة د-١) من
    `data/client_forbidden_terms_l1.csv` — صفوفٌ `{label, langs, regex,
    replacement_ar, replacement_en, refuse}`. صفٌّ بنمطٍ فاسد يُتخطّى بتحذيرٍ
    ولا يكسر التصدير؛ الملفُّ الغائب = لا صفوف (الأنماطُ الحرفية القائمة تبقى)."""
    import csv
    import logging
    import re as _re
    rows: list = []
    try:
        with open(_FORBIDDEN_TERMS_PATH, encoding="utf-8") as fh:
            for r in csv.DictReader(l for l in fh if not l.startswith("#")):
                pat = (r.get("pattern") or "").strip()
                label = (r.get("label") or "").strip()
                if not pat or not label:
                    continue
                try:
                    rx = _re.compile(pat)
                except _re.error as e:
                    logging.getLogger(__name__).warning(
                        "client_forbidden_terms_l1: bad pattern for %s: %s",
                        label, e)
                    continue
                lang = (r.get("lang") or "both").strip().lower()
                rep_ar = r.get("replacement_ar") or ""
                rep_en = r.get("replacement_en") or ""
                rows.append({
                    "label": label,
                    "langs": frozenset({"ar", "en"}) if lang == "both"
                    else frozenset({lang}),
                    "regex": rx, "replacement_ar": rep_ar,
                    "replacement_en": rep_en,
                    "refuse": "<refuse>" in (rep_ar, rep_en)})
    except OSError:
        return ()
    return tuple(rows)


@functools.lru_cache(maxsize=256)
def product_terms(category: str, lang: str) -> tuple:
    """كلماتُ فئةِ المنتج بلغةٍ بعينها من `data/product_terms_l1.csv`.

    صفٌّ غائب = **محورٌ متخطّى معلَن** (tuple فارغة) لا تخمينَ ترجمة.
    """
    import csv
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                        "product_terms_l1.csv")
    try:
        with open(path, encoding="utf-8") as fh:
            rows = csv.DictReader(l for l in fh if not l.startswith("#"))
            for row in rows:
                if (row.get("category") or "").strip() == category and \
                        (row.get("lang") or "").strip().lower() == \
                        str(lang or "").strip().lower():
                    return tuple(t.strip().lower()
                                 for t in (row.get("terms") or "").split(",")
                                 if t.strip())
    except Exception:  # noqa: BLE001 — مرجعٌ مساعد، غيابُه لا يكسر شيئاً
        return ()
    return ()


@functools.lru_cache(maxsize=64)
def _market_language(iso3: str) -> str:
    import csv
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                        "market_locale.csv")
    try:
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(l for l in fh if not l.startswith("#")):
                if (row.get("iso3") or "").strip().upper() == (iso3 or "").upper():
                    return (row.get("lang_primary") or "").strip()
    except Exception:  # noqa: BLE001
        return ""
    return ""


@functools.lru_cache(maxsize=256)
def _product_words_cached(hs_code: str, product: str, market_iso3: str) -> frozenset:
    """نسخةٌ مُخزَّنة — الجداولُ ملفاتٌ ثابتة، وكان كلُّ رابطٍ يُعيد قراءة
    `hs_codes.csv` (آلافُ الصفوف) وجدولين آخرين (مراجعة §58)."""
    return frozenset(_product_words(hs_code, product, market_iso3))


@functools.lru_cache(maxsize=256)
def _product_specific_words(hs_code: str, product: str) -> frozenset:
    """كلماتُ **المنتج نفسِه** — كلماتُ بنده السداسيّ، وحين تخلو (090112) كلماتُ
    أشقّائه في البند الرباعيّ؛ واسمُه بلا الأوصاف العامّة («محمصة»، «Fresh»).
    بلا كلمات الفئة («food»/«produce») التي تُبقي كلَّ تاجرٍ غذائيّ، وبلا
    كلمات أشقّاءٍ لمنتجاتٍ أخرى حين يحمل البندُ كلماتِه (المانجو ليست التمر)."""
    import re as _re
    words = {w.strip().lower()
             for w in _re.split(r"[\s,،]+", str(product or ""))
             if len(w.strip()) >= 3}
    words -= _GENERIC_PRODUCT_WORDS
    code = _hs_digits(hs_code)
    kw = _hs_keywords()
    own = kw.get(code[:6]) if len(code) >= 6 else None
    if own:
        words |= own
    elif not words and len(code) >= 4:
        # الأشقّاءُ احتياطٌ أخير حين يخلو البندُ **واسمُ المنتج** معاً — البندُ
        # الرباعيّ قد يخلط منتجات (2008: الطحينة مع زبدة الفول السوداني).
        for c, ks in kw.items():
            if c[:4] == code[:4]:
                words |= ks
    return frozenset(w for w in words if w)


def _product_words(hs_code: object, product: str, market_iso3: str) -> set:
    """كلماتُ المنتج بالعربية والإنجليزية ولغة السوق — اتحادٌ لا استبدال."""
    import re as _re
    words = {w.strip().lower()
             for w in _re.split(r"[\s,،]+", str(product or ""))
             if len(w.strip()) >= 3}
    code = _hs_digits(hs_code)
    # **عمودُ `keywords` وحدَه** — وصفُ البند الرسميّ نثرٌ جمركيّ عامّ
    # («parts»، «other»، «prepared») فيتطابق مع «auto parts store» فيُبقي
    # رابطاً لا صلةَ له (قِياسٌ كشفه قبل الشحن). الكلماتُ المنسَّقة مميِّزة.
    if code:
        words |= set(_hs_keywords().get(code[:6]) or ())
    try:
        from silk_ai_judge import _product_category
        cat = (_product_category(hs_code) or ("", ""))[0]
    except Exception:  # noqa: BLE001
        cat = ""
    if cat:
        for lang in ("ar", "en", _market_language(market_iso3)):
            if lang:
                words |= set(product_terms(cat, lang))
    return {w for w in words if w}


def lead_relevant_to_product(lead: object, hs_code: object = None,
                             product: str = "", market_iso3: str = "") -> tuple:
    """(هل يُبقى الرابط؟، سببُ الإسقاط) — الدرس ٢٦٣.

    القاعدةُ بترتيبها: تقاطعُ كلمةٍ من كلمات المنتج (ثلاث لغات) يُبقي؛ ثم
    نشاطٌ عامٌّ يخدم كلَّ الفئات يُبقي؛ ثم نشاطٌ مُدرَجٌ يخدم فئةً أخرى
    يُسقِط **بسببٍ مسمّى**؛ وما عدا ذلك يُبقى (لا حذفَ بالجهل).
    """
    ok, why, _status = lead_product_fit(lead, hs_code, product, market_iso3)
    return ok, why


def lead_product_fit(lead: object, hs_code: object = None, product: str = "",
                     market_iso3: str = "") -> tuple:
    """(يُبقى؟، سببُ الإسقاط، حالةُ الدليل) — تقرير ٧ §4.4 فوق الدرس ٢٦٣.

    ١) كلمةُ **المنتج نفسِه** كلمةً كاملة ⇒ متخصّص. ٢) مقدّمُ خدمة ⇒ يُسقَط.
    ٣) نشاطٌ غذائيٌّ متخصّص: فصلُه فصلُ المنتج ⇒ متخصّص، وإلا يُسقَط بسببٍ
    مسمّى (تاجرُ مأكولاتٍ بحرية ليس مشتري قهوة). ٤) كلمةُ الفئة العامّة أو
    نشاطٌ عامّ أو مجهول ⇒ تاجرٌ عامّ قابلٌ للتحقق. ٥) نشاطٌ لفئةٍ أخرى ⇒ يُسقَط.
    المطابقةُ بالكلمة الكاملة — «food» لم تعد تطابق «seafood wholesaler».
    """
    if not isinstance(lead, dict):
        return False, "ليس صفّاً", ""
    text = _lead_text(lead)
    key = _activity_key_of(lead)
    # مراجعة §58: **التعارضُ المقيس أوّلاً** — كلمةٌ في الاسم («Fresh
    # Seafood» لمنتج «Fresh Dates»، أو «Motor Oil» لزيت الزيتون) لا تُنقذ
    # مقدّمَ خدمة ولا نشاطاً لمنتجٍ آخر أو لفئةٍ أخرى.
    if key in _ACTIVITY_NON_TRADE:
        return False, (f"نشاطُ «{activity_label_ar(key)}» مقدّمُ خدمةٍ لا "
                       "طرفٌ تجاريّ يشتري أو يوزّع"), ""
    code = _hs_digits(hs_code)
    fam = _ACTIVITY_HS_CHAPTERS.get(key)
    if fam and len(code) >= 2:
        if any(code.startswith(p) for p in fam):
            return True, "", EVIDENCE_SPECIALIST
        return False, (f"نشاطُ «{activity_label_ar(key)}» متخصّصٌ بمنتجٍ آخر "
                       "لا بهذا المنتج"), ""
    if key and key not in _ACTIVITY_CATEGORY_FREE:
        try:
            from silk_ai_judge import _product_category
            cat = (_product_category(hs_code) or ("", ""))[0]
        except Exception:  # noqa: BLE001
            cat = ""
        # فئةُ المنتج مجهولة ⇒ لا محورَ للمقارنة فلا حذف (الحذفُ يحتاج
        # تعارضاً مقيساً لا جهلاً بطرفيه).
        for other_cat, activities in _ACTIVITY_CATEGORY.items():
            if cat and key in activities and other_cat != cat:
                return False, (f"نشاطُ «{activity_label_ar(key)}» يخدم فئة "
                               f"«{other_cat}» لا فئةَ هذا المنتج «{cat}»"), ""
    own = _product_specific_words(str(hs_code or ""), str(product or ""))
    if any(_word_in(text, w) for w in own):
        return True, "", EVIDENCE_SPECIALIST
    return True, "", EVIDENCE_GENERAL
    if not key or key in _ACTIVITY_CATEGORY_FREE:
        return True, "", EVIDENCE_GENERAL
    try:
        from silk_ai_judge import _product_category
        cat = (_product_category(hs_code) or ("", ""))[0]
    except Exception:  # noqa: BLE001
        cat = ""
    if not cat:
        # فئةُ المنتج مجهولة (رمزٌ غائبٌ أو فصلٌ غيرُ مصنَّف) ⇒ **لا محورَ
        # للمقارنة**، فلا حذف. الحذفُ يحتاج تعارضاً مقيساً لا جهلاً بطرفيه.
        return True, "", EVIDENCE_GENERAL
    for other_cat, activities in _ACTIVITY_CATEGORY.items():
        if key in activities and other_cat != cat:
            return False, (f"نشاطُ «{activity_label_ar(key)}» يخدم فئة "
                           f"«{other_cat}» لا فئةَ هذا المنتج"
                           + (f" «{cat}»" if cat else "")), ""
    return True, "", EVIDENCE_GENERAL


def activity_label_ar(raw: object) -> str:
    """تسميةُ نشاطٍ خارجية بالعربية — غيرُ المعروفة **تُعاد كما هي**.

    لا تخمينَ ترجمة: تسميةٌ غيرُ مُدرَجة تمرّ بحالها فيلتقطها حاجزُ اتساق
    اللغة (`_check_language_consistency`) ويُعلَن النقصُ بدل أن يُستَر
    بترجمةٍ مختلَقة — نفسُ منطقِ العملة في الصنف ٣.
    """
    return ACTIVITY_LABEL_AR.get(_activity_key(raw), str(raw or "").strip())


# (ب) تعريفاتُ المنهجية — سطرٌ واحدٌ ثابتٌ لكلّ مصطلحٍ **يُعرَض حين يَرِد**.
# مصطلحاتٌ عربية لا اختصاراتٌ لاتينية، فلا يبلغها `GLOSSARY_ORDER`؛ ويستهلكها
# بانيُ المسرد الواحد (`silk_render._apply_merchant_language`) نفسُه، فلا
# مسارَ عرضٍ ثانٍ. الأطولُ أوّلاً كي لا يبتلعَ مصطلحٌ جزءاً من آخر.
METHODOLOGY_DEFINITIONS: dict[str, str] = {
    "بيانات المرآة": "أرقامُ الشريك المصدّر بدل تصريح المستورد — تُستعمَل حين "
                     "لا يُبلِّغ المستورد، وقد تختلف عن أرقامه",
    "المرآة": "أرقامُ الشريك المصدّر بدل تصريح المستورد — تُستعمَل حين لا "
              "يُبلِّغ المستورد، وقد تختلف عن أرقامه",
    "البيانات المباشرة": "أرقامٌ صرّح بها المستورد نفسُه لجهته الجمركية",
    "مؤشر تركّز السوق": "مقياسٌ من 0 إلى 10000؛ فوق 2500 يعني سوقاً بيد قلّة، "
                        "وأقلّ يعني موزّعاً على كثيرين",
    "سعر الحدود": "قيمةُ الشحنة عند نقطة الدخول قبل الرسوم وهوامش التوزيع — "
                  "ليست سعرَ الرفّ",
    "نسبة التحقّق": "حصّةُ أرقام هذا التقرير التي فُتِح مصدرُها وتأكّدت قيمتُه "
                    "منه — وهي غيرُ ثقةِ التوصية",
    "نسبة التحقق": "حصّةُ أرقام هذا التقرير التي فُتِح مصدرُها وتأكّدت قيمتُه "
                   "منه — وهي غيرُ ثقةِ التوصية",
}

METHODOLOGY_DEFINITIONS_ORDER: list = sorted(
    METHODOLOGY_DEFINITIONS.items(), key=lambda kv: -len(kv[0]))

# (ج) رؤوسُ أسماءِ الجهات الرسمية — تُستعمَل لكشف انزياح التسمية حتمياً.
# «الحكومة» و«السلطات» بلا نسبةٍ إحالةٌ مبهمة حين يذكر التقريرُ جهتين.
AUTHORITY_HEADS: tuple = ("الحكومة", "حكومة", "السلطات", "السلطة", "سلطات",
                          "الإدارة", "إدارة", "الهيئة", "هيئة")

# تسمياتُ السلطة المحيَّدة لكلّ سوق تُهيَّأ في
# `data/market_profiles.json` تحت `authorities` (قائمةٌ موثَّقة) مع
# `multi_authority` — **تهيئةٌ لا تفريعٌ في الشيفرة** (`silk_profiles`). حين
# تُهيَّأ، تصير التسميةُ المفضَّلة؛ وحين لا تُهيَّأ، يعمل كشفُ الانزياح على
# نصّ التقرير وحده فلا يكون الحارسُ نائماً بانتظار بيانات.

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

# ════════════════════════════════════════════════════════════════════════════
# الصوت البشري · human voice — خلف `SILK_HUMAN_VOICE` المطفأة افتراضياً
# ════════════════════════════════════════════════════════════════════════════
# طلب المالك: «Humanized اريد الكتابة» (ردودي **ونص التقارير** معاً).
#
# **ما ثبت بالقياس لا بالحدس:** الصوت الآليّ في التقارير **من كتابتنا** لا من
# النموذج. كل عبارة جاهزة في القائمة أدناه **مأمورٌ بها في هذا الملف نفسه**:
# «توصي الدراسة بـ» و«يُوصى بـ» في `WRITING_STANDARD_RULE` §السجل المهني،
# و«والأثرُ العمليّ» و«ومن ثمّ» بين بدائل الروابط في `READER_LANGUAGE_RULE`،
# و«تشير النتائج إلى» و«تخلص الدراسة إلى» و«توضح البيانات» في
# `ACADEMIC_WRITER_CONTRACT`، و«ينبغي التعامل مع» مثالُ `PROFESSIONAL_TONE_RULE`
# الحرفيّ. فالعلاج إعطاءُ بديلٍ طبيعيٍّ لكلّ واحدة، لا لومُ الكاتب.
#
# **وحدُّ القياس معلَن:** عدُّ هذه العبارات في المدوّنات الست عشرة أعطى اثنتين
# في أكبر مدوّنة وصفراً في اثنتي عشرة — لأنّ المدوّنات نصوصٌ مكتوبةٌ باليد لا
# خرجُ كلود حيّ. فكلّ عتبةٍ تُبنى على هذا القياس **محدودةٌ ومُعلنةٌ كذلك**، لا
# مبنيّةٌ على قياسِ إنتاجٍ حقيقيّ (لا وجود له في الريبو).
HUMAN_VOICE_FLAG = "SILK_HUMAN_VOICE"

# (العبارة الجاهزة، البديل الطبيعي) — ما يقرؤه **الموجّه** ليعطي بديلاً.
# **مأخذُ المراجعة الذاتية (الأخطر):** «ينبغي التعامل مع» كانت هنا — وهي صدرُ
# `MEASURED_TONE_HINT` الحرفيّ، وهو **مُخرَجٌ إلزاميّ مُسجَّل**
# (`silk_ai_judge.MANDATED_OUTPUT_LITERALS`) يُفرضه المراجعُ نفسُه. فمنعُها
# يأمر الكاتبَ بإسقاط تحذيرٍ واجب — عقابُ الإفصاح (الدرس ٢٣٩). أُزيلت.
# وأُزيل كذلك تكرارُ «يوصى بـ» بشكلَيه: عادةٌ واحدةٌ كانت تستهلك خانتين.
STOCK_PHRASES: tuple = (
    ("توصي الدراسة بـ", "ننصح بـ"),
    ("يُوصى بـ", "الأفضل أن"),
    ("تشير النتائج إلى", "الأرقام تقول"),
    ("تخلص الدراسة إلى", "الخلاصة"),
    ("توضح البيانات", "البيانات تُظهر"),
    ("وهذا يعني", "أي أنّ"),
    ("والأثر العملي", "عملياً"),
    ("من الجدير بالذكر", "ولاحظ أنّ"),
    ("في هذا السياق", "وهنا"),
    ("بناءً على ما سبق", "من كل ما سبق"),
    ("تجدر الإشارة", "ولاحظ"),
)

# ما تعدّه **البوابة** — حشوٌ محضٌ لا يأمر به عقدٌ ولا يفرضه مراجع. والفرقُ
# مقصود: الصيغُ التي يأمر بها `WRITING_STANDARD_RULE` أو
# `ACADEMIC_WRITER_CONTRACT` («توصي الدراسة بـ»، «تشير النتائج إلى»…) لا
# تُحتسَب عيباً — الكاتبُ أطاع عقدَه، والعلاجُ في العقد لا في لومه.
FILLER_PHRASES: tuple = (
    "وهذا يعني",
    "والأثر العملي",
    "من الجدير بالذكر",
    "في هذا السياق",
    "بناءً على ما سبق",
    "تجدر الإشارة",
)


def stock_phrases() -> tuple:
    """العباراتُ الجاهزة كما يراها **الموجّه** (بلا بدائلها)."""
    return tuple(p for p, _alt in STOCK_PHRASES)


def filler_phrases() -> tuple:
    """الحشوُ الذي تعدّه **البوابة** — لا يأمر به عقدٌ ولا يفرضه مراجع."""
    return FILLER_PHRASES


_HUMAN_VOICE_EXAMPLES = "؛ ".join(
    "«" + p + "» ⇒ «" + alt + "»" for p, alt in STOCK_PHRASES[:8])

HUMAN_VOICE_RULE = (
    "**الصوت البشري (إلزامي — يتقدّم على صياغة السجل التقريري أعلاه حيث "
    "يتعارضان، وعلى شيءٍ واحدٍ فقط: النبرة. لا يمسّ رقماً ولا مصدراً ولا "
    "أفعالَ طبقات الأدلة):**\n"
    "- **خاطِب القارئ**: «أمامك سوق تستورد 6.4 مليون دولار» أفضل من «توصي "
    "الدراسة بملاحظة أنّ حجم الاستيراد بلغ…». هو صاحبُ القرار، فاكتب له لا "
    "عنه.\n"
    "- **افتح الخلاصة بأهمّ جملة بصياغتك** لا بقالبٍ ثابت. والترتيبُ يبقى "
    "إلزامياً (القرار، ثم أرقامه، ثم أول خطوة، ثم المتطلب السابق للتعاقد أو الشحن) وسقفُ "
    "المئة والخمسين كلمة كما هو.\n"
    "- **العبارات الجاهزة ممنوعة** — لكلٍّ بديلها: " + _HUMAN_VOICE_EXAMPLES
    + ".\n"
    "- **نوِّع الإيقاع**: جملةٌ من ثلاث كلمات مسموحةٌ ومطلوبةٌ حين تُفيد "
    "(«الطلب مرصود.»)، تتبعها جملةٌ أطول تشرح. التساوي في الطول هو ما يجعل "
    "النصَّ آلياً.\n"
    "- **لا يبدأ سطران متتاليان بالتركيب نفسه** (لا «ويُلاحَظ… ويُلاحَظ…»).\n"
    "- **وليس هذا إذناً بالتهويل**: منعُ المبالغة والشحنة العاطفية قائمٌ كما "
    "هو، ولا استعارةَ تصف رقماً. بشريٌّ يعني طبيعياً لا متحمّساً."
)

HUMAN_VOICE_RULE_EN = (
    "**Human voice (mandatory — outranks the report-register phrasing above "
    "where they clash, and only on tone: it touches no figure, no source "
    "and no evidence-layer verb):**\n"
    "- Address the reader directly: \"you are looking at a market that "
    "imports $6.4m\" beats \"the study recommends noting that imports "
    "reached...\".\n"
    "- Open the summary with your most important sentence, not a fixed "
    "template. The order stays mandatory (decision, its figures, first "
    "step, prerequisite before contracting or shipping) and so does the "
    "150-word cap.\n"
    "- No stock formulas: not \"it is worth noting\", \"in this context\", "
    "\"the findings indicate\", \"the study concludes\".\n"
    "- Vary the rhythm: a three-word sentence is allowed and wanted where "
    "it earns its place. Uniform sentence length is what reads robotic.\n"
    "- No two consecutive lines may open with the same construction.\n"
    "- This is not licence to hype: the ban on alarmist and emotive "
    "phrasing stands, and no metaphor may describe a figure."
)


def human_voice() -> bool:
    """هل رايةُ الصوت البشريّ مفعّلة؟ — تقبل `on` كنظرائها في الريبو
    (مأخذُ المراجعة الذاتية: `SILK_HUMAN_VOICE=on` كانت تمرّ صامتةً بلا أثر)."""
    import os as _os
    raw = _os.environ.get(HUMAN_VOICE_FLAG, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def human_voice_rule() -> str:
    """قاعدةُ الصوت البشري كما تُحقَن فعلاً — فراغٌ حين تكون الرايةُ مطفأة
    (الافتراض)، فيبقى الموجّهُ حرفياً كما كان. نمطُ `epistemic_rule` نفسُه."""
    import os as _os
    return HUMAN_VOICE_RULE if human_voice() else ""


def human_voice_rule_en() -> str:
    """نظيرتُها الإنجليزية — نفسُ الراية."""
    import os as _os
    return HUMAN_VOICE_RULE_EN if human_voice() else ""


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
    "العملي (من تقصد وماذا تفعل أولاً)، ثم المتطلب السابق للتعاقد أو الشحن (ما يجب إغلاقه "
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
    "«أثره على القرار: …» ثم «الإجراء المطلوب: … (الجهة والمدة والكلفة)» — "
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
    "approach, what to do first), then the prerequisite before "
    "contracting or shipping (what must "
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
    # الصنف ١ (موجة عيوب التقرير): بُعدُ «من يقرأ» — إلحاقٌ لا استبدال.
    + "\n\n" + READER_LANGUAGE_RULE
    # الصنف ٢: لا إحالةَ إلى ما لم يُعرَض، ولا عددٌ يخالف معدودَه.
    + "\n\n" + REFERENTIAL_INTEGRITY_RULE
    # الصنف ٥: قسمٌ واحدٌ يشرح كلَّ حقيقة، ورابطٌ لا يتكرّر في الفقرة.
    + "\n\n" + SINGLE_EXPLANATION_RULE
)


DECISION_WRITING_RULE = (
    "**صياغة القرار:** افتتح بخلاصة واضحة: القرار الآن، سبب مختصر، وما يجب فعله تالياً. "
    "اكتب فكرة واحدة في كل جملة، وفضّل 15 إلى 20 كلمة. احذف المصطلحات التقنية التي "
    "لا يحتاجها القارئ. ضع الأرقام التفصيلية في موضعها مرة واحدة؛ لا تعيد الجدول نثراً. "
    "اعرض كل خطر بجملة تحدد أثره على البيع أو التكلفة، ثم إجراء التعامل معه. "
    "استمد شروط التنفيذ من المعلومات الناقصة فعلاً. لا تعد بدخول كامل بعد شرطين "
    "إذا بقيت الربحية أو المتطلبات النظامية بلا تحقق. استكمال المعلومات يستدعي إعادة "
    "التقييم، ولا يضمن تغيير الحكم. لا تحول عدد السكان أو نسبة دينية إلى طلب على المنتج، "
    "ولا تنشئ افتراض استهلاك للفرد لتملأ فراغاً. مؤشر اهتمام البحث من صفر إلى مئة "
    "ليس نسبة مشترين أو حصة سوقية. لا تستنتج تغير المنافسة من سنتين تختلف طريقة "
    "جمعهما. سعة الحاوية حد نقل وليست كمية تجربة موصى بها؛ اربط كمية البداية بطلب "
    "مؤكد أو اختبار بيع، وإلا اتركها معلقة لحين التحقق."
)

WRITER_STYLE_CONTRACT = (
    DECISION_WRITING_RULE + "\n\n" +
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
    # الصنف ١ (موجة عيوب التقرير): بُعدُ «من يقرأ» — إلحاقٌ لا استبدال.
    + "\n\n" + READER_LANGUAGE_RULE
    # الصنف ٢: لا إحالةَ إلى ما لم يُعرَض، ولا عددٌ يخالف معدودَه.
    + "\n\n" + REFERENTIAL_INTEGRITY_RULE
    # الصنف ٥: قسمٌ واحدٌ يشرح كلَّ حقيقة، ورابطٌ لا يتكرّر في الفقرة.
    + "\n\n" + SINGLE_EXPLANATION_RULE
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
    # الصنف ١ (موجة عيوب التقرير) — المرآةُ الإنجليزية، إلحاقٌ لا استبدال.
    + "\n\n" + READER_LANGUAGE_RULE_EN
    # الصنف ٢ — المرآةُ الإنجليزية.
    + "\n\n" + REFERENTIAL_INTEGRITY_RULE_EN
    # الصنف ٥ — المرآةُ الإنجليزية.
    + "\n\n" + SINGLE_EXPLANATION_RULE_EN
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
    # الصنف ١ (موجة عيوب التقرير) — المرآةُ الإنجليزية، إلحاقٌ لا استبدال.
    + "\n\n" + READER_LANGUAGE_RULE_EN
    # الصنف ٢ — المرآةُ الإنجليزية.
    + "\n\n" + REFERENTIAL_INTEGRITY_RULE_EN
    # الصنف ٥ — المرآةُ الإنجليزية.
    + "\n\n" + SINGLE_EXPLANATION_RULE_EN
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

# ── مصطلحاتُ البحث · deterministic search terms (الموجة د-٣، البند ٨) ───────
#
# **العيبُ المرصود:** استعلاماتُ البعثات كان يكتبها النموذجُ حرّاً من اسم
# المنتج، فيبحث كثيراً بترجمةٍ حرفيةٍ لوصف البند الجمركيّ («Horses; live,
# pure-bred breeding animals») لا بما يسمّيه السوقُ فعلاً — ولا توليدَ حتميّاً
# ولا ترجمة. **الفكس:** ثلاثةُ حقولٍ تُبنى بالكود من مراجعَ قائمة وتُمرَّر
# للنموذج: العربيةُ (اسمُ المنتج + مفردات `hs_codes.csv`)، والإنجليزيةُ (اسمُ
# البند الرسميّ)، ولغةُ السوق (**مفرداتُ فئةٍ** من `product_terms_l1.csv` —
# يُقال ذلك صراحةً: ليست ترجمةَ اسم المنتج).
def _hs_row(hs_code: object) -> dict:
    import csv
    import os
    d = "".join(ch for ch in str(hs_code or "") if ch.isdigit())[:6]
    if len(d) < 6:
        return {}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                        "hs_codes.csv")
    try:
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(l for l in fh if not l.startswith("#")):
                if (row.get("hs_code") or "").strip() == d:
                    return row
    except OSError:
        return {}
    return {}


def _customs_descriptions(hs_code: object) -> list:
    """أوصافُ البند الجمركيّ (البند/البند الرئيس/الفصل) من `hscodes_full.csv`."""
    import csv
    import os
    d = "".join(ch for ch in str(hs_code or "") if ch.isdigit())[:6]
    if len(d) < 6:
        return []
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                        "hscodes_full.csv")
    out: list = []
    try:
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(l for l in fh if not l.startswith("#")):
                if (row.get("hs_code") or "").strip() != d:
                    continue
                for col in ("description_en", "heading_desc_en",
                            "chapter_desc_en"):
                    v = (row.get(col) or "").strip()
                    if v and v not in out:
                        out.append(v)
                break
    except OSError:
        return []
    return out


def build_search_terms(product: str, hs_code: object, market) -> dict:
    """{ar, en, local:{lang, terms, note}} — حتميّ، بلا شبكة ولا نموذج.

    حقلٌ فارغٌ = **فجوةٌ معلنة** (لا صفَّ في المرجع)، لا ترجمةَ مخمَّنة.
    """
    row = _hs_row(hs_code)
    ar = [t for t in [str(product or "").strip()] if t]
    for kw in (row.get("keywords") or "").split(","):
        kw = kw.strip()
        if kw and any("\u0600" <= ch <= "\u06ff" for ch in kw) and kw not in ar:
            ar.append(kw)
    en = [t for t in [(row.get("name_en") or "").strip()] if t]
    lang = ""
    try:
        from silk_llm_runtime import _locale_hl
        lang = str(_locale_hl({"market": market}) or "").strip()
    except Exception:  # noqa: BLE001
        lang = ""
    terms: tuple = ()
    try:
        from silk_ai_judge import product_profile
        cat = (product_profile(hs_code) or {}).get("category") or ""
        if cat and lang:
            terms = product_terms(cat, lang)
    except Exception:  # noqa: BLE001
        terms = ()
    note = ("مفرداتُ **فئة** المنتج بلغة السوق (مرجع product_terms_l1) — ليست "
            "ترجمةَ اسم المنتج؛ اسمُه بلغة السوق يبقى على بطاقة المنتج أو "
            "على بحثك" if terms else
            "لا صفَّ لفئة هذا المنتج بلغة السوق في المرجع — فجوةٌ معلنة")
    return {"ar": ar[:6], "en": en,
            # وصفُ البند الجمركيّ الطويل — يُعرَض للحارس ليرفضه استعلاماً، ولا
            # يُعرَض للنموذج مصطلحاً (لغةُ تصنيفٍ لا لغةُ سوق).
            "customs_descriptions": _customs_descriptions(hs_code),
            "local": {"lang": lang or None, "terms": list(terms)[:6],
                      "note": note}}


def search_terms_block(terms: dict) -> str:
    """كتلةُ الموجّه من الحقول الثلاثة — فارغةٌ حين لا مصطلحَ أصلاً."""
    if not terms:
        return ""
    ar = "، ".join(terms.get("ar") or []) or "—"
    en = ", ".join(terms.get("en") or []) or "—"
    loc = terms.get("local") or {}
    local = "، ".join(loc.get("terms") or []) or "—"
    if ar == "—" and en == "—" and local == "—":
        return ""
    return ("مصطلحاتُ البحث المُعدّة لك (استعملها، ولا تبحث بترجمةٍ حرفيةٍ "
            f"لوصف البند الجمركيّ):\n- بالعربية: {ar}\n- بالإنجليزية: {en}\n"
            f"- بلغة السوق ({loc.get('lang') or 'غير محدّدة'}): {local} — "
            f"{loc.get('note') or ''}")
