"""طبقة الترجمة السردية لسِلك — Silk narrative/translation layer (P1).

مواصفة المالك: «المشكلة في الميل الأخير — التوليف والعرض، لا الوكلاء ولا
البيانات». هذه الطبقة تجلس فوق النموذج القانوني (`silk_render.build_view`)
وتحوّل قيم الآلة إلى عربية بشرية:

  - الدرجات المعيارية 0–1 لا تصل وجه المستخدم أبداً — تُترجم لحالة لغوية
    («منافسة مفتوحة — لا مورّد مهيمن») أو تُخفى.
  - المصطلحات الإحصائية والرموز (HHI، CAGR، CONDITIONAL-GO، أسماء الوكلاء)
    تمرّ عبر معجم إلزامي؛ الإنجليزية تبقى لملحق المحلّل فقط.
  - القيمة الغائبة تُعرض «—» هادئة بلا شعار ولا نسبة اكتمال ولا وعظ نزاهة —
    سطر المصدر تحت الرقم الحاضر هو إشارة النزاهة الوحيدة للمستخدم.

عرض صرف: قراءة حقول محسوبة فقط، صفر شبكة، صفر رقم جديد — «لا اختلاق»
يبقى قاعدة هندسية داخلية ولا يُطبع نصاً للمستخدم أبداً.
Pure display over computed fields; adds no numbers, calls no network.
"""
from __future__ import annotations

import functools
import re

# ── المعجم — the mandatory glossary ─────────────────────────────────────────

VERDICT_AR: dict[str, str] = {
    "GO": "التوصية بالدخول",
    "CONDITIONAL-GO": "دخول مشروط",
    "NO-GO": "عدم الدخول حالياً",
    "WATCH": "مراقبة السوق",
}

# أسماء الأسواق بالعربية — أسواق سِلك الـ38 + السعودية (المنشأ).
COUNTRY_AR: dict[str, str] = {
    "SAU": "السعودية", "ARE": "الإمارات", "QAT": "قطر", "KWT": "الكويت",
    "OMN": "عُمان", "BHR": "البحرين", "JOR": "الأردن", "LBN": "لبنان",
    "EGY": "مصر", "MAR": "المغرب", "TUN": "تونس", "DZA": "الجزائر",
    "IRQ": "العراق", "TUR": "تركيا", "YEM": "اليمن", "ZAF": "جنوب أفريقيا",
    "NGA": "نيجيريا", "KEN": "كينيا", "ETH": "إثيوبيا", "GHA": "غانا",
    "IND": "الهند", "PAK": "باكستان", "BGD": "بنغلاديش", "IDN": "إندونيسيا",
    "MYS": "ماليزيا", "SGP": "سنغافورة", "THA": "تايلند", "VNM": "فيتنام",
    "CHN": "الصين", "JPN": "اليابان", "KOR": "كوريا الجنوبية",
    "GBR": "بريطانيا", "DEU": "ألمانيا", "FRA": "فرنسا", "ITA": "إيطاليا",
    "ESP": "إسبانيا", "NLD": "هولندا", "USA": "الولايات المتحدة",
    "CAN": "كندا",
}

# أسماء إنجليزية شائعة → عربية (لحقول تحمل الاسم لا الرمز).
_EN_COUNTRY_AR: dict[str, str] = {
    "United Arab Emirates": "الإمارات", "Saudi Arabia": "السعودية",
    "Kuwait": "الكويت", "Qatar": "قطر", "Oman": "عُمان",
    "Bahrain": "البحرين", "China": "الصين", "India": "الهند",
    "Germany": "ألمانيا", "France": "فرنسا", "United Kingdom": "بريطانيا",
    "United States": "الولايات المتحدة", "USA": "الولايات المتحدة",
    "Japan": "اليابان", "New Zealand": "نيوزيلندا", "Turkey": "تركيا",
    "Egypt": "مصر", "Jordan": "الأردن", "Morocco": "المغرب",
    "Indonesia": "إندونيسيا", "Malaysia": "ماليزيا",
    "Singapore": "سنغافورة", "Netherlands": "هولندا", "Spain": "إسبانيا",
    "Italy": "إيطاليا", "Canada": "كندا", "Pakistan": "باكستان",
    "Thailand": "تايلند", "Vietnam": "فيتنام", "Viet Nam": "فيتنام",
    "South Korea": "كوريا الجنوبية", "Rep. of Korea": "كوريا الجنوبية",
    "Iran": "إيران", "Tunisia": "تونس", "Algeria": "الجزائر",
    "Mexico": "المكسيك", "Argentina": "الأرجنتين", "Ukraine": "أوكرانيا",
    "Brazil": "البرازيل", "Australia": "أستراليا",
}

# أسماء الوكلاء/المقاييس الداخلية → وصف عربي — لا اسم صنف كود يصل المستخدم.
INTERNAL_AR: dict[str, str] = {
    "TradeFlowAgent": "بيانات التدفق التجاري",
    "EconomicAgent": "المؤشرات الاقتصادية",
    "CompetitionAgent": "بيانات المنافسة",
    "market_size": "حجم واردات السوق",
    "saudi_position": "الحصة السعودية",
    "demand_capacity": "دخل الفرد",
    "competition": "تركّز الموردين",
    "tam_usd": "إجمالي واردات السوق (TAM)",
    "sam_usd": "السوق القابل للخدمة (SAM)",
    "som_usd": "الحصة القابلة للتحصيل (SOM)",
    "import_growth_pct": "نمو الواردات",
    "import_cagr_pct": "معدل النمو السنوي المركّب",
    "hhi": "تركّز الموردين",
    "top_supplier_share_pct": "حصة المورّد الأكبر",
    "saudi_share_pct": "الحصة السعودية",
    "border_unit_value_usd_kg": "متوسط سعر الوحدة عند الحدود",
    "saudi_border_unit_value_usd_kg": "سعر الوحدة السعودي عند الحدود",
    "margin_at_border_pct": "الهامش عند الحدود",
    "tariff_applied_pct": "التعريفة الجمركية المطبّقة",
    "political_stability_wgi": "الاستقرار السياسي",
    "regulatory_quality_wgi": "الجودة التنظيمية",
    "logistics_lpi": "الأداء اللوجستي",
    "fx_volatility_pct": "تقلب سعر الصرف",
    "supplier_concentration_hhi": "تركّز مصادر التوريد",
    "gdp_per_capita_usd": "دخل الفرد",
    "population": "عدد السكان",
    "requirements_count": "عدد الاشتراطات",
    "entry_requirements_count": "عدد اشتراطات الدخول",
    "eligibility_gate": "بوابة الأهلية الأوروبية",
    "saudi_suppliers": "مرشّحو الموردين السعوديين",
    "target_distributors": "مرشّحو الموزّعين المستهدفين",
    "retail_references": "مراجع أسعار التجزئة",
    "(SEARCH_API_KEY / الشبكة)": "(مفتاح خدمة البحث / الشبكة)",
    "ramadan_seasonality": "موسمية رمضان",
    "muslim_share_pct": "حصة السكان المسلمين",
    "lpi_timeliness": "الالتزام بمواعيد الشحن",
    "lpi_intl_shipments": "جودة الشحن الدولي",
    # ملاحظات الحُرّاس الداخلية (عقود إنجليزية مثبَّتة بالاختبارات في طبقة
    # البيانات) وأسماء مسارات/مفاتيح داخلية — تسريب سباكة إن وصلت العميل
    # حرفياً. الأطول أولاً: الاستبدال حرفي متسلسل والقصير جزء من الطويل.
    ("paid agent outside /deepen — skipped (structural guard, "
     "no call attempted)"):
        "وكيل مدفوع لا يعمل خارج خدمة التعميق المدفوعة — تخطٍّ بنيوي "
        "بلا أي نداء",
    "requires SEARCH_API_KEY (or SERPER_API_KEY)":
        "يتطلب تهيئة مفتاح خدمة البحث (Serper)",
    "تتطلب SEARCH_API_KEY و/أو GOOGLE_MAPS_API_KEY في بيئة الخادم":
        "يتطلب تهيئة مفاتيح البحث/الخرائط في بيئة الخادم",
    "يتطلب SEARCH_API_KEY / GOOGLE_MAPS_API_KEY":
        "يتطلب تهيئة مفاتيح البحث/الخرائط",
    "عبر /deepen": "عبر خدمة التعميق المدفوعة",
    "LocalPriceAgent": "وكيل أسعار التجزئة المدفوع",
    "retail_prices": "أسعار التجزئة",
    "no shopping results": "لا نتائج تسوّق مرصودة",
    "(ThreadPoolExecutor)": "",
    "ThreadPoolExecutor": "المعالجة المتوازية",
}

# مفاتيح حزمة وكلاء البحث الثمانية الحتمية (silk_research.py، row["research"])
# — نفس التسمية المستخدَمة في لوحة العميل (web/index.html AGENT_AR) كي لا
# يختلف اسم نفس الوكيل بين الدردشة السياقية (analysis_context) واللوحة.
# قاموس منفصل عمداً عن INTERNAL_AR: هذه كلمات إنجليزية شائعة جداً بذاتها
# ("supplier"، "risk"، "pricing") — لو دخلت حلقة الاستبدال الشامل في
# humanize_technical_note() (تُطبَّق على أي نص حرّ) لأفسدت ظهورها العادي
# داخل جمل أخرى غير مقصودة (بلاغ تصحيح: "supplier HHI over 3 suppliers"
# في ملاحظة DataPoint خام تحوّلت لخليط "المورّدون HHI over 3 suppliers").
# تُستهلك حصراً عبر مطابقة تامة (internal_ar) على مفتاح معروف، لا استبدال
# نصّي داخل جملة عشوائية.
_AGENT_KEY_AR: dict[str, str] = {
    "competitor": "المنافسة",
    "regulatory": "الاشتراطات",
    "pricing": "التسعير",
    "risk": "المخاطر",
    "consumer_demand": "ثقافة المستهلك",
    "supplier": "المورّدون",
    "logistics": "اللوجستيات",
}

# رموز مؤشرات البنك الدولي → عربية — لا رمز API خام يصل وجه المستخدم.
_WB_INDICATOR_AR: dict[str, str] = {
    "NY.GDP.PCAP.CD": "دخل الفرد",
    "NY.GDP.PCAP.PP.CD": "دخل الفرد (تعادل القوة الشرائية)",
    "SP.POP.TOTL": "عدد السكان",
    "PV.EST": "الاستقرار السياسي",
    "RQ.EST": "الجودة التنظيمية",
    "RL.EST": "سيادة القانون",
    "GE.EST": "فعالية الحكومة",
    "CC.EST": "مكافحة الفساد",
    "VA.EST": "الصوت والمساءلة",
    "LP.LPI.OVRL.XQ": "الأداء اللوجستي",
    "LP.LPI.TIME.XQ": "الالتزام بالمواعيد اللوجستية",
    "LP.LPI.ITRN.XQ": "جودة الشحن الدولي",
    "PA.NUS.FCRF": "سعر الصرف",
}


def _wb_ar(code: str) -> str:
    return _WB_INDICATOR_AR.get(code, code)


# أنماط ملاحظات تقنية خام شائعة (استثناءات بايثون/أخطاء HTTP/قوالب مصادر
# محدَّدة) → عربية مقروءة. مُرتَّبة الأخصّ أولاً؛ عقود الملاحظات في طبقة
# البيانات (silk_data_layer.py، silk_hs_resolver.py، ...) تبقى كما هي —
# هذا تحويل عرض فقط (silk_render._strip_internal_plumbing يستدعيه أيضاً
# عبر humanize_technical_note، فالإصلاح مركزي مرة واحدة).
_TECH_PATTERNS: list[tuple[re.Pattern, object]] = [
    # البنك الدولي
    (re.compile(r"\b([A-Z]{2}(?:\.[A-Z0-9]+){1,3})\s+fetch failed for\s+(\w+):.*"),
     lambda m: f"{_wb_ar(m.group(1))} ({m.group(2)}): تعذّر الجلب — أعد المحاولة"),
    (re.compile(r"\b([A-Z]{2}(?:\.[A-Z0-9]+){1,3}):\s*no value returned for\s+(\w+)"),
     lambda m: f"{_wb_ar(m.group(1))} ({m.group(2)}): لا قيمة منشورة"),
    (re.compile(r"\bno value returned for\s+(\w+)"),
     lambda m: f"لا قيمة منشورة لـ{m.group(1)}"),
    (re.compile(r"\b([A-Z]{2}(?:\.[A-Z0-9]+){1,3})\s+year=(\d{4})"),
     lambda m: f"{_wb_ar(m.group(1))} (سنة {m.group(2)})"),
    (re.compile(r"شكل ردّ غير متوقع من البنك الدولي:\s*\S+"),
     "تعذّر تفسير رد البنك الدولي"),
    (re.compile(r"البنك الدولي أعاد خطأ API:.*"),
     "البنك الدولي أعاد خطأ فني — أعد المحاولة"),
    (re.compile(r"سجلات البنك الدولي ليست قائمة:\s*\S+"),
     "تعذّر تفسير رد البنك الدولي"),
    (re.compile(r"\b([A-Z]{2}(?:\.[A-Z0-9]+){1,3})\b"),
     lambda m: _wb_ar(m.group(1))),
    # مصنّف HS
    (re.compile(r"no HS match for\s+['\"]([^'\"]*)['\"]"),
     lambda m: f"لا تطابق لتصنيف HS للمنتج «{m.group(1)}»"),
    (re.compile(r"weak match for\s+['\"]([^'\"]*)['\"]\s*"
               r"\(best=['\"]([^'\"]*)['\"],\s*score=([\d.]+)\)"),
     lambda m: (f"تطابق ضعيف لتصنيف HS للمنتج «{m.group(1)}» — أقرب نتيجة: "
                f"{m.group(2)} (نسبة {round(float(m.group(3)) * 100)}%)")),
    (re.compile(r"HS seed empty/unavailable"), "قاعدة تصنيف HS غير متاحة حالياً"),
    (re.compile(r"invalid HS code\s+['\"]([^'\"]*)['\"]"),
     lambda m: f"رمز HS غير صالح: {m.group(1)}"),
    # فاو ستات
    (re.compile(r"FAOSTAT unavailable:\s*non-JSON response for ([\w/]+):"
               r".*\(may require auth\)"),
     lambda m: f"فاو ستات: رد غير مقروء لـ{m.group(1)} — قد يتطلب تفعيل مفتاح"),
    (re.compile(r"FAOSTAT unavailable:\s*fetch failed for ([\w/]+):"
               r".*\(may require auth\)"),
     lambda m: f"فاو ستات: تعذّر الجلب لـ{m.group(1)} — قد يتطلب تفعيل مفتاح"),
    (re.compile(r"FAOSTAT unavailable:\s*unknown area for ISO3 '(\w+)' "
               r"\(no mapping\)"),
     lambda m: f"فاو ستات: لا يغطي هذا المصدر {m.group(1)}"),
    (re.compile(r"FAOSTAT unavailable:.*"), "فاو ستات: غير متاح حالياً"),
    # مصادر أخرى بأنماط "fetch failed" إنجليزية عامة
    (re.compile(r"\bGDELT\b.*fetch failed for.*"),
     "تعذّر جلب أخبار المخاطر — أعد المحاولة"),
    (re.compile(r"\bOpenAlex\b.*fetch failed for.*"),
     "تعذّر جلب المراجع البحثية — أعد المحاولة"),
    # بلاغ المالك: «(بلا شبكة)» كانت تُشخِّص **خطأً** كلَّ فشلٍ من Trends —
    # 429 (تجاوز معدّل: أعد المحاولة لاحقاً) و«pytrends غير مثبَّتة» وانقطاعُ
    # الشبكة الحقيقي أفعالٌ مختلفة. السببُ يُحفَظ ويُعرَّب بعدها عبر
    # `_EXC_FAMILY_AR`/`_http_status_ar` (يعملان بعد هذه القائمة).
    (re.compile(r"pytrends unavailable / no network:\s*(.*)"),
     lambda m: (f"بيانات الاتجاهات غير متاحة: {m.group(1)}"
                if m.group(1).strip() else
                "بيانات الاتجاهات غير متاحة (بلا شبكة)")),
    (re.compile(r"Volza:\s*no named importers parsed for HS(\d+) into (\w+)"),
     lambda m: f"فولزا: لا مستوردون بالاسم مرصودون لرمز {m.group(1)} في {m.group(2)}"),
    (re.compile(r"Explee unavailable:.*"), "إكسبلي غير متاح حالياً"),
    (re.compile(r"Google Maps API status=(\w+):.*"),
     lambda m: f"خرائط جوجل: تعذّر الجلب ({m.group(1)})"),
    # فشل نداء كلود — رموز داخلية (تدقيق H4، بلاغ هولندا): failure_reason
    # يحمل "empty_response"/"stop_reason='max_tokens'"/"راجع سجلّات الخادم"
    # التي كانت تنجو من التعقيم وتصل /ask و/report.md وحدود التقرير. تُعرَّب
    # هنا قبل أي سطح عميل — نفس نقطة التعريب المركزية.
    (re.compile(r"\bstop_reason\s*=\s*'?max_tokens'?"),
     "بلغ التوليد الحدّ الأقصى للطول"),
    (re.compile(r"\bstop_reason\s*=\s*'?[\w-]+'?"), ""),   # أي سبب آخر — يُزال الرمز الخام
    # تدقيق v2 (الموجة ١، تسريب المشرف #1): «stop_reason = » بفراغٍ وبلا قيمة
    # (أو أيّ صيغة عارية) كانت تنجو من النمطين أعلاه (يطلبان `=`+قيمة). شبكة
    # أمان تُزيل الرمز العاري مهما تباعدت الفراغات حوله.
    (re.compile(r"\bstop_reason\b\s*=?\s*'?[\w-]*'?"), ""),
    (re.compile(r"\bempty_response\b:?\s*"), ""),          # نوع فشل داخلي
    # تدقيق v2 (تسريب المشرف #5): الصيغة غير المشكَّلة «سجلات الخادم» (بلا شدّة
    # على اللام) كانت تنجو من النمط المشكَّل «سجلّات». الشدّة اختيارية الآن،
    # و«راجع» اختيارية — أيّ توجيهٍ لسجلّات الخادم يُزال (لا يخصّ العميل).
    (re.compile(r"\s*[—–-]?\s*(?:راجع\s*)?سجلّ?ات\s+الخادم"), ""),
    # ملاحظة: عدّ نداءات الأدوات العربي «نداءات أدوات: N» **لا يُجرَّد هنا** —
    # هو تِلِمتري تتبّعٍ يُقرأ من الملخّص الخام قبل العرض (silk_render يجرّده
    # لسطح العرض بعد استخراج التتبّع). تجريده هنا (نقطة مركزية) يصفّر عدّ اللوحة.
]

# ── تعريب أخطاء المصادر — يُترجِم ولا يبتلع ─────────────────────────────────
# بلاغ المالك: «فشل نداء التحليل الآلي (تعذّر الاتصال بالمصدر — خطأ تقني مؤقت»
# — قوسٌ غير مغلق، وكلُّ أنماط الفشل منهارةٌ في سلسلةٍ واحدة. السبب: النمط
# القديم كان ينتهي بـ`.*` فيبتلع بقيةَ السطر — رمزَ الحالة والرسالةَ والقوسَ
# الخاتم معاً. القاعدة الآن: **استبدل الرمزَ التقني وحده، وأبقِ الذيلَ
# التشخيصي**؛ ولكلّ عائلةِ فشلٍ عبارتُها المميِّزة (مهلةُ اتصالٍ ≠ مهلةُ ردٍّ ≠
# تجاوزُ معدّلٍ ≠ ردُّ خطأٍ من الخادم) — التشخيص يبدأ من التمييز.
# مرتَّبةٌ من الأخصّ إلى الأعمّ؛ أوّلُ مطابقةٍ تفوز لكلّ موضع.
_EXC_FAMILY_AR = (
    (re.compile(r"\b\w*ConnectTimeout\w*\b"), "انتهت مهلة الاتصال بالمصدر"),
    (re.compile(r"\b\w*ReadTimeout\w*\b"), "انتهت مهلة انتظار ردّ المصدر"),
    (re.compile(r"\b\w*TooManyRequests\w*\b"), "تجاوز حدّ معدّل الطلبات"),
    (re.compile(r"\b\w*RateLimit\w*\b"), "تجاوز حدّ معدّل الطلبات"),
    (re.compile(r"\b\w*(?:Timeout|Timedout)(?:Error|Exception)?\b"),
     "انتهت مهلة النداء"),
    (re.compile(r"\b\w*(?:SSL|Proxy)\w*(?:Error|Exception)\b"),
     "تعذّر تأمين الاتصال بالمصدر"),
    (re.compile(r"\b\w*Connection\w*(?:Error|Exception)\b"),
     "تعذّر الاتصال بالمصدر"),
    (re.compile(r"\b\w*HTTPError\b"), "ردّ خطأ من المصدر"),
    (re.compile(r"\b\w*JSONDecode\w*(?:Error|Exception)?\b"),
     "ردّ غير مقروء من المصدر"),
    (re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception)\b"),
     "خطأ تقني من المصدر"),
)
# `[^.؛)]*` لا `[^.؛]*`: الذيلُ لا يعبر قوساً خاتماً، وإلا ابتلع القوسَ نفسه
# فأنتج نفسَ عيبِ القوس المفتوح داخل «(... ConnectionPool(...) ...)».
_CONN_POOL_RE = re.compile(r"\b\w*ConnectionPool\([^)]*\)[^.؛)]*")
_HTTP_STATUS_RE = re.compile(r"\bHTTP\s*(\d{3})\b:?[ \t]*")
# بلاغ المالك (Nadec/اليمن #7): «خطأ (HTTP 429):» كانت تُعرَّب إلى
# «خطأ (خطأ استجابة الخادم (HTTP 429)):» — بادئة خطأ مزدوجة + ترقيم فارغ
# «): » معلّق. يُطوى الغلاف «خطأ (…)» قبل التعريب العام، ويُطوى الشكل
# المزدوج المخزَّن من تشغيلات سابقة عند إعادة عرضه.
_ERR_HTTP_DOUBLED_RE = re.compile(
    r"خطأ\s*\(\s*خطأ استجابة الخادم\s*\(HTTP\s*(\d{3})\)\s*:?\s*\)\s*:?[ \t]*")
_ERR_HTTP_WRAPPED_RE = re.compile(
    r"خطأ\s*\(\s*HTTP\s*(\d{3})\s*\)\s*:?[ \t]*")


def _http_status_ar(m: "re.Match") -> str:
    """رمزُ الحالة يبقى ظاهراً — كان يُمحى فيُخلِّف «خطأ استجابة الخادم: )».

    429 (تجاوز معدّل، أعد المحاولة) و503 (المصدر معطّل) و404 (لا سجلّ) أفعالٌ
    تشغيليةٌ مختلفة تماماً — طمسُها في سلسلةٍ واحدة يُلغي قيمةَ الرسالة. غيرُ
    الأخطاء (2xx/3xx) يمرّ كما هو بلا تعريب.

    idempotent (بلاغ Nadec/اليمن #7): «HTTP nnn» داخل بادئةٍ معرَّبة سابقاً
    («…استجابة الخادم (») يمرّ كما هو — تطبيقُ التعريب مرّتين على نصٍّ
    مخزَّن كان يضاعف البادئة «خطأ (خطأ استجابة الخادم …»."""
    code = m.group(1)
    if m.string[max(0, m.start() - 24):m.start()].endswith("استجابة الخادم ("):
        return m.group(0)
    if code[:1] in ("4", "5"):
        return f"خطأ استجابة الخادم (HTTP {code}): "
    return m.group(0)


# قوسٌ فُتِح ولم يُغلَق (أو العكس) بعد حذف/استبدال نصٍّ تقني — يُنظَّف بنيوياً
# بدل الاعتماد على أن كلَّ نمطٍ «مهذَّب». هذا حارسُ العيب المُبلَّغ حرفياً.
def _balance_parens(s: str) -> str:
    """أسقِط القوسَ **المفتوحَ** غير المُغلَق — العيبُ المُبلَّغ حرفياً.

    قوسٌ فُتِح ولم يُغلَق أثرٌ لاستبدالٍ ابتلع خاتمتَه («(تعذّر الاتصال
    بالمصدر — خطأ تقني مؤقت»)، فيُسقَط. أمّا القوسُ الخاتمُ الشاردُ فيبقى
    كما هو: في النثر العربي هو **علامةُ ترقيمٍ مشروعة** لا خلل — تعدادُ
    «1) 2) 3)» و«أ) ب)» أشيعُ صوره، وإسقاطُه يشوّه المتن (اكتُشف على
    `samples/research_report_latest.md` قبل الدمج: «1)» صارت «1»)."""
    stack: list[int] = []
    for i, ch in enumerate(s):
        if ch == "(":
            stack.append(i)
        elif ch == ")" and stack:
            stack.pop()
    if not stack:
        return s
    drop = set(stack)
    return "".join(c for i, c in enumerate(s) if i not in drop)

# رمز بسيط (حروف/أرقام/شرطة سفلية فقط، مثل "supplier" أو "market_size") —
# يُستبدل بحدود كلمة \b كي لا يخترق كلمة أطول تحتويه حرفياً (بلاغ: مفتاح
# "supplier" الجديد كان يفسد "saudi_suppliers" إلى "saudi_المورّدونs" عبر
# استبدال حرفي أعمى). القوالب الإنجليزية الطويلة (جمل/عبارات حراس) تبقى
# على الاستبدال الحرفي كسابقاً — لا حدود كلمة لها أصلاً لأنها ليست رمزاً واحداً.
_SIMPLE_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@functools.lru_cache(maxsize=4096)
def _word_rx(token: str) -> re.Pattern:
    """تعبيرُ حدود الكلمة للرمز — R5 (CONC-11): كان قاموساً ينمو بلا سقف."""
    return re.compile(r"\b" + re.escape(token) + r"\b")


def _replace_token(s: str, token: str, ar: str) -> str:
    if _SIMPLE_TOKEN_RE.match(token):
        return _word_rx(token).sub(ar, s)
    return s.replace(token, ar)


# ── الموجة ٠: مرآةٌ إنجليزية لنقطة التعريب المركزية ─────────────────────────
#
# `humanize_technical_note` تُعرِّب: تستبدل أسماءَ الحقول الداخلية وأسماءَ الدول
# الإنجليزية وأصنافَ الاستثناءات بعربيةٍ مقروءة. تشغيلُها على نصٍّ إنجليزيّ
# يحقن العربية فيه («الأردن's imports…») — تسرّبٌ عكسيّ رصدته المراجعة الذاتية.
#
# المرآة تُحقّق **نفس الغاية** (لا سباكةَ خاماً على سطح العميل) بمخرجٍ إنجليزيّ:
# نفس الإزالات البنيوية، وبدائلُ إنجليزية للعائلات نفسها. وأسماءُ الدول تبقى
# كما هي — فهي بالإنجليزية أصلاً على تقريرٍ إنجليزيّ.
_TECH_EN: tuple = (
    (re.compile(r"missing \(no [^)]*\)", re.I), "not available"),
    (re.compile(r"\bmissing\b", re.I), "not available"),
    (re.compile(r"\(no [^)]*signal\)", re.I), ""),
    (re.compile(r"\bunobserved\b", re.I), "not observed"),
    (re.compile(r"\bfetch[_ ]failed\b", re.I), "source retrieval failed"),
    (re.compile(r"\bno[_ ]record\b", re.I), "no record at the source"),
    (re.compile(r"\brate[_ ]limit(?:ed)?\b", re.I), "source rate limit reached"),
    (re.compile(r"\btimeout\b|\bTimeoutError\b"), "the source timed out"),
    (re.compile(r"\b(?:Connection|Proxy|SSL)Error\b|"
                r"HTTPSConnectionPool\([^)]*\)"), "could not reach the source"),
    (re.compile(r"\b(?:KeyError|ValueError|TypeError|IndexError|"
                r"JSONDecodeError|AttributeError)\b"),
     "the source returned an unreadable response"),
)
_HTTP_STATUS_EN_RE = re.compile(r"\bHTTP\s*(\d{3})\b")


def _humanize_note_en(text: object) -> str:
    """نظِّف ملاحظةً تقنيةً خاماً بمخرجٍ **إنجليزيّ** — نفس عقد النظيرة العربية.

    لا يُترجِم نصّاً عربياً (ذاك مسارُ الترجمة الممنوع): يزيل السباكةَ ويصوغ
    عائلاتِ الفشل المعروفة بالإنجليزية. نصٌّ عربيٌّ يمرّ من هنا يبقى عربياً،
    وتلتقطه بوابةُ اتساق اللغة الحاجزة — لا يُخفى.
    """
    s = str(text or "")
    if not s:
        return s
    for rx, repl in _TECH_EN:
        s = rx.sub(repl, s)
    s = _HTTP_STATUS_EN_RE.sub(r"server responded with HTTP \1", s)
    s = _balance_parens(s)
    s = re.sub(r"\(\s*\)", "", s)
    return re.sub(r"[ \t]{2,}", " ", s).strip(" —:")


def humanize_technical_note(text: object, lang: str = "ar") -> str:
    """حوّل ملاحظة تقنية خام (استثناء بايثون/خطأ HTTP/قالب مصدر داخلي)
    لعربية مقروءة — نقطة التعريب المركزية الوحيدة، يستدعيها كل من
    `translate_gaps` (قوائم الفجوات/الحدود) و
    `silk_render._strip_internal_plumbing` (نصوص حرة: ملخّصات
    البعثات/المحلل/الملاحظات غير المحلولة) فلا يتكرر الإصلاح مرتين.

    عقود ملاحظات DataPoint في طبقة البيانات تبقى كما هي حرفياً — هذا
    تحويل عرض فقط، لا تعديل على قيمة أو مصدر أو حقل مخزَّن.
    """
    if str(lang or "ar").lower() == "en":
        return _humanize_note_en(text)
    s = str(text or "")
    if not s:
        return s
    for token, ar in INTERNAL_AR.items():
        s = _replace_token(s, token, ar)
    for en, ar in _EN_COUNTRY_AR.items():
        s = s.replace(en, ar)
    for rx, repl in _TECH_PATTERNS:
        s = rx.sub(repl, s)
    # D4 (البند 16): مترجم الرموز التقنية يخرج بالثنائية القانونية —
    # «غير متاح» لا «غير متوفر»/«غير مرصود» (توحيد مفردات الغياب).
    s = re.sub(r"missing \(no [^)]*\)", "غير متاح", s)
    s = re.sub(r"\bmissing\b", "غير متاح", s)
    s = re.sub(r"\(no [^)]*signal\)", "", s)
    s = re.sub(r"\bunobserved\b", "غير متاح", s)
    # الشبكة الأمان الأخيرة: أي اسم صنف استثناء بايثون أو جزء اتصال HTTP
    # خام لم يلتقطه نمط معروف أعلاه — لا نص تقني خام يمر أبداً للعميل.
    # يُترجَم الرمزُ التقني وحده؛ الذيلُ التشخيصي (رمزُ الحالة/الرسالة) يبقى.
    s = _CONN_POOL_RE.sub("تعذّر الاتصال بالمصدر", s)
    for rx, ar in _EXC_FAMILY_AR:
        s = rx.sub(ar, s)
    # اطوِ غلاف «خطأ (…)» حول رمز HTTP قبل التعريب العام — وإلا تضاعفت
    # البادئة «خطأ (خطأ استجابة الخادم (HTTP 429)):» (المزدوج المخزَّن أولاً
    # لأن النمط الأعمّ يبتلع نصفه).
    s = _ERR_HTTP_DOUBLED_RE.sub(r"خطأ استجابة الخادم (HTTP \1): ", s)
    s = _ERR_HTTP_WRAPPED_RE.sub(r"خطأ استجابة الخادم (HTTP \1): ", s)
    s = _HTTP_STATUS_RE.sub(_http_status_ar, s)
    s = _balance_parens(s)
    # قوسٌ صار فارغاً بعد التنظيف («()») لا يحمل معلومة — يُسقَط.
    s = re.sub(r"\(\s*\)", "", s)
    # قوسٌ خاتمٌ شاردٌ في **ذيل** النصّ مسبوقٌ بترقيمٍ فارغ («…: )») حطامُ
    # استبدال، لا ترقيم. مشروطٌ بوجود فائضٍ فعليٍّ من الخواتم كي لا يُمسّ
    # تعدادٌ مشروع («… 3)») ولا قوسٌ متوازنٌ ينتهي به السطر.
    if s.count(")") > s.count("("):
        s = re.sub(r"[\s:—]+\)\s*$", "", s)
    # مسافةٌ قبل قوسٍ لاصقٍ لكلمةٍ عربية (نتجت عن استبدال رمزٍ لاتينيٍّ كان
    # ملاصقاً لقوسه، مثل `TooManyRequestsError(...)`) — قراءةٌ لا معنى.
    s = re.sub(r"([ء-ي])\(", r"\1 (", s)
    return re.sub(r"[ \t]{2,}", " ", s).strip(" —:")


GAP = "—"          # القيمة الغائبة: شرطة هادئة، لا شعار ولا شرح مكرّر.
GAP_WORD = "غير متوفر"


def country_ar(code_or_name: object, fallback: str | None = None) -> str:
    """اسم السوق بالعربية — من ISO3 أو الاسم الإنجليزي؛ يسقط للأصل بلا تخمين."""
    s = str(code_or_name or "").strip()
    return (COUNTRY_AR.get(s.upper()) or _EN_COUNTRY_AR.get(s)
            or fallback or s or GAP)


def authoritative_verdict(verdict: "dict | None") -> "tuple[object, object]":
    """(الحكم المعروض، ثقته) من قاموس التوليف — WP-1 (برنامج إصلاح جودة
    التقارير): **الحكم الحتمي أولاً**. المرحلة الحتمية
    (`verdict["verdict"]`/`["confidence"]` — لجنة التحكيم/المحرّك الموزون)
    هي المصدر الوحيد للحكم المعروض على أي سطح؛ قراءة كلود (`ai.verdict`)
    حقل استشاري داخلي («قراءة تحليلية للذكاء الاصطناعي») لا يُعرَض توصيةً
    أبداً — يُستعمَل احتياطاً فقط حين يغيب الحكم الحتمي كلياً (مدوّنات
    قديمة خُزِّنت بلا مرحلة حتمية). كان الترتيب معكوساً (ai أولاً) فأنتج
    تشغيلتان بنفس المدخلات حكمين مختلفين (WATCH ثم GO) في يومٍ واحد."""
    v = verdict if isinstance(verdict, dict) else {}
    ai = v.get("ai") if isinstance(v.get("ai"), dict) else {}
    raw = v.get("verdict") or ai.get("verdict") or ""
    conf = v.get("confidence")
    if conf is None:
        conf = ai.get("confidence")
    return raw, conf


def verdict_ar(verdict: object) -> str:
    """الحكم بالعربية — رمز الآلة (GO/CONDITIONAL-GO/NO-GO) لا يصل المستخدم."""
    s = str(verdict or "").strip().upper()
    if not s:
        return "تعذّر إصدار توصية"
    if "INSUFFICIENT" in s:
        return "تعذّر إصدار توصية — بيانات غير كافية"
    # حكمُ اللجنة الحتمية حين تنقص التغطية (وكيل/بعثة فشلت) مع بقاء نتائج
    # حقيقية — حكمٌ صادر، لا غياب. كان يسقط لآخر الدالة فيُعاد خاماً/unknown.
    if "INCONCLUSIVE" in s:
        return "نتيجة مبدئية — غير محسومة"
    if "PRELIMINARY" in s and "NO-GO" not in s and "GO" in s:
        return "توصية أولية بالدخول"
    for key in ("CONDITIONAL-GO", "NO-GO", "GO", "WATCH"):
        if key in s:
            return VERDICT_AR[key]
    # مراجعة الشيفرة (عائلة اللائحتين ٤٤/٤٥): بعض مسارات الحكم تضع التسمية
    # العربية مباشرةً بدل الرمز الإنجليزي (`verdict = "دخول مشروط"` لا
    # "CONDITIONAL-GO") — كانت تمرّ من هنا بلا ترجمة (النص الخام كما ورد).
    # نفس التصنيف الواحد المُستعمَل للشارة (silk_render._verdict_tone) بدل
    # مسارٍ ثانٍ غير مترجَم قد يتباعد عنه.
    from silk_render import _verdict_tone
    _tone_key = {"go": "GO", "conditional": "CONDITIONAL-GO",
                "nogo": "NO-GO", "watch": "WATCH"}.get(_verdict_tone(verdict))
    if _tone_key:
        return VERDICT_AR[_tone_key]
    return str(verdict)


def internal_ar(token: object) -> str:
    """مصطلح داخلي (وكيل/مقياس/رمز مؤشر بنك دولي) → عربي؛ غير المعروف يمرّ
    كما هو. المعاجم منفصلة (لا دمج) كي تبقى أنماط `_TECH_PATTERNS`
    الأدق (مثل "PV.EST year=2022" → "الاستقرار السياسي (سنة 2022)") تعمل
    قبل أي استبدال حرفي مبكر؛ و`_AGENT_KEY_AR` (كلمات إنجليزية شائعة
    كمفاتيح وكلاء) لا تدخل حلقة الاستبدال الشامل في
    `humanize_technical_note` — مطابقة تامة هنا فقط."""
    s = str(token or "")
    return (INTERNAL_AR.get(s) or _WB_INDICATOR_AR.get(s)
            or _AGENT_KEY_AR.get(s) or s)


# ════════════════════════════════════════════════════════════════════════════
# الصنف ٣ (موجة عيوب التقرير) — مُنسِّقُ العرض الواحد · the one display formatter
# ════════════════════════════════════════════════════════════════════════════
# بلاغُ المالك: «36,234,200.146 مقابل 26730»، والدرجةُ تظهر 65 و0.65 و65%،
# وأرقامٌ بلا وحدةٍ ولا سنة، وبياناتُ 2018 بلا سنةٍ مطبوعة، وتوقّعُ 2024
# بصيغةِ المستقبل في 2026، وتاريخُ التشغيل مطبوعاً مكانَ تاريخ الرصد.
#
# الجذرُ المُقاس: **لا مُنسِّقَ واحد**. خمسُ عائلاتٍ متوازية تُنسِّق الأرقام —
# `silk_narrative.fmt_money`/`fmt_pct` هنا، و`silk_reports._fmt`
# (`{:,.0f}`) و`_readable_number` (منزلةٌ واحدة)، و`silk_decision._pct`،
# وعشرُ صيغِ `{:,.0f}` مضمَّنةٍ داخل بوابة الجودة نفسها. عائلةٌ لكلّ مُصدِّر
# ⇒ رقمٌ واحد بأشكالٍ عدّة في مستندٍ واحد.
#
# القاعدةُ هنا **مصدرٌ واحد**، وكلُّ مُستهلِكٍ يشير إليها بأسمائه القائمة
# كما هي (صفرُ تغييرٍ في أيّ سطح API).

SCORE_MAX = 100          # صيغةُ الدرجة الوحيدة: «N من SCORE_MAX»
PCT_MAX_DP = 2           # النسبةُ بمنزلتين عشريتين كحدٍّ أقصى
AMOUNT_MAX_DP = 2        # المقاديرُ الكبيرة بمنزلتين
OBSERVED_UNKNOWN_AR = "تاريخ الرصد غير معروف"
OBSERVED_UNKNOWN_EN = "observation date unknown"


def _as_float(v: object) -> "float | None":
    """رقمٌ أو `None` — لا استثناءَ يُسقِط عرضاً."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _trim_zeros(s: str) -> str:
    """أزِل الأصفارَ الزائدة بعد الفاصلة: «4.40» → «4.4»، «4.00» → «4»."""
    return s.rstrip("0").rstrip(".") if "." in s else s


# **المراجعةُ الذاتية للفرق (البند ٥٨)**: سقفُ المنزلتين كان يطبع حصةً
# مرصودةً 0.004% صفراً — **صفرٌ مختلَق** يصل سطحَ العميل، وهو خرقٌ للمبدأ
# المؤسِّس لا عيبُ تنسيق (والصفرُ المُستنتَج مسقوفٌ بثقةٍ 0.6 في طبقة
# البيانات لهذا السبب نفسِه). القاعدة: **قيمةٌ غيرُ صفريةٍ لا تُعرَض صفراً
# أبداً** — تُزاد المنازلُ حتى يظهر أوّلُ رقمٍ دالّ، بسقفٍ مُعلَن.
_SIGNIFICANT_DP_CAP = 6


def _dp_keeping_value(n: float, dp: int) -> int:
    """المنازلُ اللازمة كي لا تُعرَض قيمةٌ غيرُ صفريةٍ صفراً — بسقفٍ مُعلَن."""
    dp = max(0, int(dp))
    if not n:
        return dp
    while dp < _SIGNIFICANT_DP_CAP and round(abs(n), dp) == 0:
        dp += 1
    return dp


def fmt_number(v: object, dp: int = AMOUNT_MAX_DP) -> str:
    """رقمٌ للعرض: فاصلُ آلافٍ دائماً، وحدٌّ أقصى للمنازل العشرية.

    «36234200.146» → «36,234,200.15»، و«26730» → «26,730». فاصلُ الآلاف ليس
    تجميلاً: بلاغُ المالك قارَن الرقمين فعلاً، وأحدُهما بلا فاصلٍ يُقرأ خطأً.
    وقيمةٌ أصغرُ من سقف المنازل **لا تُطوى إلى صفر** (انظر أعلاه).
    """
    n = _as_float(v)
    if n is None:
        return GAP if v is None else str(v)
    return _trim_zeros(f"{n:,.{_dp_keeping_value(n, dp)}f}")


def fmt_pct(v: object, signed: bool = False, dp: int = PCT_MAX_DP) -> str:
    """نسبةٌ مئوية بمنزلتين كحدٍّ أقصى — «84.05%» تصير «84.05%» و«84.0%» «84%».

    كانت `{n:g}` فتُخرِج «12.416666666666666%» من قسمةٍ غير منتهية.
    """
    n = _as_float(v)
    if n is None:
        return GAP if v is None else str(v)
    sign = "+" if (signed and n > 0) else ""
    return f"{sign}{_trim_zeros(f'{n:,.{_dp_keeping_value(n, dp)}f}')}%"


def fmt_score(v: object) -> str:
    """**الصيغةُ الوحيدة** للدرجة: «65 من 100».

    يقبل الكسرَ 0–1 والعددَ 0–100 معاً ويوحّدهما — العلّةُ المرصودة أنّ نفسَ
    الدرجة ظهرت «65» و«0.65» و«65%» في تقريرٍ واحد. الكسرُ ≤1 يُضرَب في 100؛
    وهو تمييزٌ آمنٌ لأنّ درجةً معروضةً بـ«1 من 100» لا معنى لها عملياً،
    والحدُّ موثَّقٌ هنا لا مخفيّ.
    """
    n = _as_float(v)
    if n is None:
        return GAP if v is None else str(v)
    if 0.0 <= n <= 1.0:
        n *= SCORE_MAX
    return f"{round(n)} من {SCORE_MAX}"


def fmt_amount(v: object, currency: object = None,
               dp: int = AMOUNT_MAX_DP) -> str:
    """مبلغٌ **بعملته** — «48.53 مليون دولار»، و«789 ألف يورو»، و«1,234 SAR».

    العملةُ وسيطٌ صريح: مبلغٌ بلا عملةٍ عيبٌ في ذاته (الصنف ٩)، فلا تُخمَّن
    هنا ولا تُفترَض بالدولار. غيابُها يُخرِج الرقمَ وحده كي **تُلتقَطه**
    قاعدةُ البوابة بدل أن يُستَر بعملةٍ مختلَقة.
    """
    n = _as_float(v)
    if n is None:
        return GAP if v is None else str(v)
    cur = str(currency or "").strip()
    label = CURRENCY_AR.get(cur.upper(), cur)
    a = abs(n)
    if a >= 1e9:
        body = f"{_trim_zeros(f'{n / 1e9:,.{dp}f}')} مليار"
    elif a >= 1e6:
        body = f"{_trim_zeros(f'{n / 1e6:,.{dp}f}')} مليون"
    else:
        # لا فرعَ «ألف»: «1,234 ريال» أصدقُ من «1 ألف ريال» — فاصلُ الآلاف
        # يحفظ الرقم كما هو، والاختزالُ يفقد دقّةً بلا مكسبِ قراءة.
        body = fmt_number(n, dp)
    return f"{body} {label}".strip() if label else body


# العملاتُ التي يَرِد نصُّها عربياً — ما ليس هنا يُطبَع برمزه ISO كما هو
# (لا تخمينَ اسمٍ عربيٍّ لعملةٍ غير مُسجَّلة).
CURRENCY_AR = {
    "USD": "دولار", "EUR": "يورو", "SAR": "ريال", "GBP": "جنيه إسترليني",
    "AED": "درهم", "QAR": "ريال قطري", "KWD": "دينار كويتي",
    "JOD": "دينار أردني", "DZD": "دينار جزائري", "YER": "ريال يمني",
    "JPY": "ين", "NGN": "نايرا", "INR": "روبية", "EGP": "جنيه مصري",
    # الدرس ٢٧١ (تقرير ٧): «25.80 رينجيت ماليزي» كان يُعاد قائمةً فارغة.
    "MYR": "رينجيت ماليزي",
}


# ── الصنف ٩: إسنادُ الرقم المشتقّ · derived-figure provenance ───────────────
# **العيبُ المرصود:** «أقصى خسارة إن فشل الدخول: 8,900» — رقمٌ مشتقٌّ يصل
# القارئَ بلا عملته، وبلا معادلته، وبلا مصدرِ كلّ مدخلٍ فيه، وبلا تسميةِ
# المكوّنات التي **استُبعدت** من جمعه (الشحنُ غيرُ المتحقّق، رسومُ التسجيل).
# فيقرأ صاحبُ القرار سقفَ مخاطرةٍ يظنّه شاملاً وهو ناقص.
#
# **الجذر:** المحرّك يكتب المعادلةَ نثراً في `method` ويُخفي الاستبعاد داخل
# نفس الجملة، فلا حقلَ يحمل المدخلاتِ ولا مصادرَها ولا الناقص — فلا سطحَ
# يقدر على عرضها ولا بوابةَ تقدر على قياس غيابها.
#
# **الحلّ:** حقلان مهيكلان على بند الرقم المشتقّ (`inputs` و`unknown`) يبنيهما
# `silk_economics.build_decision_numbers`، ومُنسِّقٌ واحدٌ هنا يعرضهما على كلّ
# سطح. خلف رايةٍ مطفأةٍ افتراضياً (`SILK_DERIVED_PROVENANCE=1`): بلا الراية
# لا حقلَ يُضاف ولا حرفَ يتغيّر في أيّ سطح.
DERIVED_PROVENANCE_FLAG = "SILK_DERIVED_PROVENANCE"
ASSUMPTION_TAG_AR = "افتراض"       # وسمُ المدخل غير المرصود (لا يُقدَّم رصداً)


def derived_provenance_enabled() -> bool:
    """هل رايةُ الصنف ٩ مفعّلة؟ — نمطُ `silk_figure_store.enabled` القائم."""
    import os
    return os.environ.get(DERIVED_PROVENANCE_FLAG,
                          "").strip().lower() in ("1", "true", "yes")


# اسمُ العملةِ العربيّ ⇄ رمزُها ISO. الاتجاهُ العكسيّ من `CURRENCY_AR` نفسه
# (مصدرٌ واحد)، مع أسماءٍ شائعةٍ بلا تمييزٍ قُطريّ صريح تُترك **بلا** رمز:
# «دينار» وحدَها تسعُ خمسَ دول، وتخمينُ رمزها اختلاقٌ لا ترجمة.
_CURRENCY_ISO_EXTRA = {"دولار أمريكي": "USD", "الدولار": "USD",
                       "ريال سعودي": "SAR", "جنيه استرليني": "GBP",
                       "رينجيت": "MYR"}


def iso_currency(currency: object) -> str:
    """رمزُ ISO للعملة إن كان معروفاً — وإلّا سلسلةٌ فارغة.

    الصنف ٩: مبلغٌ بلا رمزِ عملةٍ لا يُدقَّق. والغيابُ يُعاد فارغاً كي
    **يُعلَن** ناقصاً، لا يُخمَّن رمزٌ من اسمٍ يسعُ عدّةَ دول.
    """
    cur = str(currency or "").strip()
    if not cur:
        return ""
    if re.fullmatch(r"[A-Za-z]{3}", cur):
        return cur.upper()
    if cur in _CURRENCY_ISO_EXTRA:
        return _CURRENCY_ISO_EXTRA[cur]
    # الصنف ١٢: سجلُّ العرض خريطةٌ **واحدٌ لواحد** والعلاقةُ الحقيقية
    # كثيرٌ لواحد — «روبية» تسعُ ستَّ دولٍ و«درهم» تسعُ الإماراتَ والمغرب.
    # فعكسُ الخريطة يُخمِّن دولةً: درهمُ المغرب كان يُوسَم `AED`. قائمةُ
    # الأسماء الواسعة تعلو العكسَ دائماً — ولا رمزَ إلّا حين يكون قاطعاً.
    if cur in _CURRENCY_AMBIGUOUS_AR:
        return ""
    for code, ar in CURRENCY_AR.items():
        if ar == cur:
            return code
    return ""


# ── الدرس ٢٧٢: عملةُ سعرٍ مرصودٍ في السوق — تُحسَم بعملة السوق لا بالتخمين ──
# اسمٌ أو رمزٌ عامّ يسعُ عائلةَ عملات: (رموزُ العائلة، الافتراضُ المعلن حين لا
# تكون عملةُ السوق منها). «دولار/$» ⇒ USD اصطلاحُ الريبو القائم؛ و«ريال»
# بلا سوقٍ منها بلا رمز (قفل c19: ريالُ قطر ليس SAR). المصدرُ الواحد نفسُه
# (`_CURRENCY_AMBIGUOUS_AR`) مُغطّى كلُّه هنا — يُقفله اختبار.
_DOLLAR_CODES = frozenset({"USD", "SGD", "AUD", "CAD", "HKD", "NZD", "BND",
                           "TWD"})
CURRENCY_FAMILIES = {
    "دولار": (_DOLLAR_CODES, "USD"), "$": (_DOLLAR_CODES, "USD"),
    "£": (frozenset({"GBP", "EGP"}), "GBP"),
    "ريال": (frozenset({"SAR", "QAR", "YER", "OMR", "IRR"}), ""),
    "دينار": (frozenset({"KWD", "JOD", "BHD", "IQD", "LYD", "TND", "DZD",
                         "RSD"}), ""),
    "درهم": (frozenset({"AED", "MAD"}), ""),
    "جنيه": (frozenset({"EGP", "GBP", "SDG", "SSP"}), ""),
    "روبية": (frozenset({"INR", "PKR", "LKR", "IDR", "NPR", "MUR"}), ""),
    "ليرة": (frozenset({"TRY", "LBP", "SYP"}), ""),
    "بيزو": (frozenset({"MXN", "ARS", "CLP", "COP", "PHP", "UYU"}), ""),
    "شلن": (frozenset({"KES", "TZS", "UGX", "SOS"}), ""),
    "فرنك": (frozenset({"CHF", "XOF", "XAF", "RWF", "DJF"}), ""),
    "كرونة": (frozenset({"SEK", "NOK", "DKK", "ISK", "CZK"}), ""),
    "يوان": (frozenset({"CNY"}), "CNY"),
    "روبل": (frozenset({"RUB", "BYN"}), ""),
    "راند": (frozenset({"ZAR"}), "ZAR"),
}
_SYMBOL_CODES = {"€": "EUR", "ر.س": "SAR", "RM": "MYR"}


def resolve_market_currency(currency: object, local: object = "") -> str:
    """رمزُ ISO لعملةِ سعرٍ **مرصودٍ في سوقٍ** عملتُه `local` — أو "".

    الاسمُ العامّ يُقرأ عملةَ السوق حين تكون من عائلته، وإلّا افتراضُه المعلن
    أو لا رمز؛ والاسمُ القُطريّ الصريح والرمزُ يمرّان بالاتجاه العكسيّ القائم.
    """
    cur = str(currency or "").strip()
    loc = str(local or "").strip().upper()
    if not cur:
        return ""
    fam = CURRENCY_FAMILIES.get(cur)
    if fam:
        return loc if loc in fam[0] else fam[1]
    if cur in _SYMBOL_CODES:
        return _SYMBOL_CODES[cur]
    return iso_currency(cur)


def currency_is_local(currency: object, local: object) -> "bool | None":
    """هل عملةُ السعر هي عملةُ السوق؟ True/False حين يُقطَع، None حين يتعذّر.

    «درهم» في ماليزيا ليست الرينجيت **يقيناً** وإن تعذّر رمزُها — فلا يُطبَّق
    عليها صرفُ الرينجيت؛ وسعرٌ بلا عملةٍ مسمّاة يبقى «يتعذّر الحكم»."""
    loc = str(local or "").strip().upper()
    cur = str(currency or "").strip()
    if not loc or not cur:
        return None
    code = resolve_market_currency(cur, loc)
    if code:
        return code == loc
    fam = CURRENCY_FAMILIES.get(cur)
    if fam:
        return loc in fam[0]
    return None


_LATIN_RE = re.compile(r"[A-Za-z]")
APPENDIX_SOURCE_AR = "المصدر مذكورٌ في ملحق المراجع"


def _input_source(inp: dict, client: bool) -> str:
    """مصدرُ المدخل **بلغةِ السطح**.

    سياسةُ الريبو القائمة: الاستشهادُ الخام (`icontainers.com — ISO max
    gross 30,480 kg`) سطحُ مشغّلٍ لا سطحُ عميل — وبوابةُ نصّ المُنتَج
    النهائي ترفض تسرّبَ اللغة. وقياسُ المراجعة الذاتية للجولة الثانية أثبت
    أنّ البوابةَ **ليست شبكةً موثوقة** لهذا التسرّب: مواصفةُ حاويةٍ واحدة
    رُفِضت والأخرى مرّت. فالمنعُ عند المصدر: تسميةٌ عربيةٌ صريحة
    (`source_client`) أوّلاً، ثمّ المصدرُ نفسُه **إن خلا من الحرف اللاتيني**،
    وإلّا فإحالةٌ إلى ملحق المراجع الذي يحمله فعلاً.
    """
    ar = str(inp.get("source_client") or "").strip()
    raw = str(inp.get("source") or "").strip()
    if not client:
        return raw or ar
    if ar:
        return ar
    if raw and not _LATIN_RE.search(raw):
        return raw
    return APPENDIX_SOURCE_AR if raw else ""


def fmt_derived_input(inp: object, client: bool = False) -> str:
    """مدخلٌ واحدٌ من مدخلات رقمٍ مشتقّ: اسمُه ثمّ مصدرُه أو وسمُ الافتراض.

    المصدرُ المرصود يُسمّى؛ والمعلمةُ المفترضة تُوسَم «افتراض» صريحاً — فلا
    يقرأ صاحبُ القرار معلمةَ سيناريو كأنها قياس. مدخلٌ بلا أيٍّ منهما
    يُعلَن «مصدره غير مسجّل» (فجوةٌ معلنة لا حشوٌ صامت).

    `client=True`: لغةُ الزائر حصراً (انظر `_input_source`).
    """
    if not isinstance(inp, dict):
        return str(inp or "").strip()
    name = str(inp.get("name") or "").strip()
    if not name:
        return ""
    src = _input_source(inp, client)
    if inp.get("assumed"):
        return (f"{name} — {ASSUMPTION_TAG_AR}: {src}" if src
                else f"{name} — {ASSUMPTION_TAG_AR} غير مصدَّق")
    if src:
        return f"{name} — المصدر: {src}"
    return f"{name} — مصدره غير مسجّل"


DERIVED_PROVENANCE_RULE = (
    "**إسنادُ الرقم المشتقّ (إلزامي):** كلُّ مبلغٍ يُكتَب برمز عملته "
    "(SAR/USD/EUR…) — مبلغٌ بلا عملةٍ لا يُدقَّق. وكلُّ رقمٍ **تشتقّه** "
    "(تعادل، كلفةُ دخول، سقفُ خسارة، شريحةٌ قابلة للخدمة) يُكتَب معه: "
    "معادلتُه، ومدخلاتُها واحداً واحداً، ومصدرُ كلّ مدخلٍ مرصود، ووسمُ "
    "«افتراض» على كلّ مدخلٍ غيرِ مرصود. وسقفُ الخسارة **مدىً** لا رقماً "
    "مفرداً، وتُسمّى فيه المكوّناتُ التي لم تُحسَب وبقيت خارجه. "
    "ولا تكتب رقماً لبندٍ تُعلِنه الحقائقُ غيرَ محسوب: الصيغةُ المشروعة "
    "«غير محسوب — الناقص: [اسم المدخل]»."
)


def fmt_derived(entry: object, client: bool = False) -> str:
    """طريقةُ اشتقاق بندٍ من «أرقام القرار» — معادلتُه ثمّ مدخلاتُها بمصادرها
    ثمّ المكوّناتُ غير المحسوبة بأسمائها.

    بلا الراية (أو بلا الحقلين) تُعاد `method` **حرفياً كما هي** — فكلّ سطح
    يستدعي هذا المُنسِّق بلا أن يتغيّر خرجُه المطفأ.
    """
    e = entry if isinstance(entry, dict) else {}
    method = str(e.get("method") or "").strip()
    if not derived_provenance_enabled():
        return method
    inputs = [x for x in (e.get("inputs") or []) if x]
    unknown = [str(u).strip() for u in (e.get("unknown") or []) if str(u).strip()]
    if not inputs and not unknown:
        return method
    parts = [method] if method else []
    rendered = [r for r in (fmt_derived_input(i, client) for i in inputs)
                if r]
    if rendered:
        parts.append("المدخلات: " + "؛ ".join(rendered) + ".")
    if unknown:
        parts.append("مكوّنات غير محسوبة وخارج هذا الرقم: "
                     + "؛ ".join(unknown) + ".")
    return " ".join(parts)


# ── الصنف ١٢: مفرداتُ التعرّف · one recognition vocabulary ─────────────────
# **العيبُ المرصود:** سعرُ رفٍّ مرصودٌ وملاحظتُه تقول «روبية» صريحةً، ومع ذلك
# يُعلَن «أقصى سعر مصنع غير محسوب — الناقص: **عملة السعر المرصود**». السببُ
# أنّ كاشفَ العملات في `silk_economics` قائمةٌ مكتوبةٌ بخمسةَ عشرَ بديلاً
# (خليجيةٌ وأوروبيةٌ وأمريكية) لا تعرف الروبيةَ ولا النايرا ولا الين — فجودةُ
# التقرير تتبع **جغرافيا العملة** لا جودةَ الرصد.
#
# هذه الدالّةُ المصدرُ الواحد: سجلُّ العرض (`CURRENCY_AR`) وكاشفُ المحرّك
# وحارسُ البوابة يقرؤون منها جميعاً، فلا تتباعد ثلاثُ مفرداتٍ مرّةً أخرى.
# الرموزُ وأسماءٌ عربيةٌ شائعةٌ **بلا** تمييزٍ قُطريّ تبقى مقبولةً كعملةٍ
# مرصودة (فالرصدُ حاصل) وإن تعذّر رمزُها ISO (انظر `iso_currency`).
_CURRENCY_SYMBOLS = ("€", "$", "£", "ر.س")
# أسماءٌ عربيةٌ **تسعُ أكثرَ من دولة** — تُقرَأ عملةً مرصودة (فالرصدُ حاصل)
# ولا يُخمَّن لها رمزُ ISO أبداً (`iso_currency` تعيد فراغاً). «جنيه» العارية
# كانت في النمط القائم ولا مقابلَ لها في سجلّ العرض، فإسقاطُها من المصدر
# الواحد كان **انحداراً** رصده اختبارُ عدمِ الانحدار قبل الشحن.
_CURRENCY_AMBIGUOUS_AR = ("درهم", "دينار", "روبية", "ليرة", "بيزو", "شلن",
                          "جنيه", "فرنك", "كرونة", "يوان", "روبل", "راند")


def currency_tokens() -> tuple:
    """كلُّ ما يُقرَأ عملةً — رموزٌ ثمّ رموزُ ISO ثمّ الأسماءُ العربية.

    مرتَّبةٌ بالأطول أوّلاً كي لا يبتلعَ «دينار» جزءاً من «دينار كويتي».
    """
    toks = set(_CURRENCY_SYMBOLS) | set(_CURRENCY_AMBIGUOUS_AR)
    toks |= set(CURRENCY_AR) | set(CURRENCY_AR.values())
    toks |= set(_CURRENCY_ISO_EXTRA)
    return tuple(sorted((t for t in toks if t), key=len, reverse=True))


_CURRENCY_MIN_AR = 3          # «ين» تسكن داخل «الصين»/«بين» — انظر أدناه
_AR_LETTER = "\u0621-\u064a"


_CURRENCY_TOKEN_RE: dict = {}


def _currency_token_re(token: str) -> "re.Pattern | None":
    """نمطُ تعرّفٍ على اسمِ عملةٍ واحد — مُخزَّنٌ بعد أوّل بناء.

    الحدود: لا حرفَ عربيٍّ بعد الاسم، ويُسمَح قبله بأدواتِ الجرّ والعطف
    والتعريف الملتصقة («بالروبية»، «والنايرا») — فاسمُ العملة في العربية
    يَرِد ملتصقاً أكثرَ مما يَرِد مفرداً، ونمطٌ بحدودٍ صارمةٍ كان يفوّته.

    **منطقةُ العمى المعلنة:** الأسماءُ العربيةُ الأقصرُ من ثلاثة أحرف
    مستبعَدة («ين» تسكن داخل «الصين» و«بين» و«سنتين»، فقبولُها يُنتِج
    عملةً من كلّ جملةٍ تقريباً) — ورمزُها ISO (`JPY`) يُقرَأ.
    """
    if token in _CURRENCY_TOKEN_RE:
        return _CURRENCY_TOKEN_RE[token]
    rx = None
    if re.fullmatch(r"[A-Za-z]{3}", token):
        rx = re.compile(f"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])")
    elif re.fullmatch(f"[{_AR_LETTER} ]+", token):
        # كلمةٌ عربيةٌ خالصة — القيدُ الطوليّ وأدواتُ الالتصاق لها وحدها؛
        # «ر.س» اختصارٌ بنقطةٍ فلا يسقط بقيدِ الطول (وكان يسقط: القاعدةُ
        # الأولى عدّت حروفَه اثنين فأسقطت رمزاً يقرؤه النمطُ القائم أصلاً).
        if len(re.findall(f"[{_AR_LETTER}]", token)) >= _CURRENCY_MIN_AR:
            rx = re.compile(f"(?<![{_AR_LETTER}])[وفبكل]{{0,2}}(?:ال)?"
                            f"{re.escape(token)}(?![{_AR_LETTER}])")
    else:
        rx = re.compile(re.escape(token))
    _CURRENCY_TOKEN_RE[token] = rx
    return rx


def currency_in(text: object) -> str:
    """أوّلُ عملةٍ يُسمّيها النصّ — **بتسميتها في السجلّ** لا بالكلمة الملتصقة.

    «سعر رف لعبوة 1 كجم، بالروبية» ⇒ «روبية». الأطولُ أوّلاً فلا يبتلع
    «دينار» جزءاً من «دينار كويتي». وغيابُ التسمية يُعاد فراغاً — تُعلَن
    الفجوةُ ولا تُخمَّن عملة.
    """
    t_ = str(text or "")
    if not t_:
        return ""
    for token in currency_tokens():
        rx = _currency_token_re(token)
        if rx is not None and rx.search(t_):
            return token
    return ""


# ── الصنف ١٣: قيمةُ بندِ القرار تمرّ بالمنسِّق الواحد ─────────────────────
# **العيبُ المرصود** (المراجعةُ الذاتية للجولة الثانية، مدوّنةُ الهند):
# «كلفة الدخول الكلية حتى أول شحنة | **2539350 INR** (المدى
# 2539350–2539350، ±0%)» — رقمٌ من سبع خاناتٍ بلا فاصلِ آلاف يقرؤه صاحبُ
# القرار بالتقطيع، ومدىً **منحلٌّ** طرفاه متساويان يُقدَّم كأنه مجالُ قياسٍ
# ±0% بينما هو قيمةٌ نقطية.
#
# **الجذر:** الصنفُ ٣ وحّد المنسِّقات، وهذان السطحان (`_economics_md_lines`
# و`_client_decision_numbers_table`) يبنيان خانةَ القيمة بـf-string خاصّةٍ
# بهما — سطحٌ لم يبلغه التوحيد، فعاد العيبُ من الباب نفسه.
DECISION_NUMBER_FORMAT_FLAG = "SILK_DECISION_NUMBER_FORMAT"


def decision_number_format() -> bool:
    """هل رايةُ الصنف ١٣ مفعّلة؟ — نمطُ الرايات القائم."""
    import os
    return os.environ.get(DECISION_NUMBER_FORMAT_FLAG,
                          "").strip().lower() in ("1", "true", "yes")


def _legacy_decision_value(e: dict) -> str:
    """الصيغةُ القائمة حرفياً — تُحفَظ هنا مرجعاً للمقابلة لا للاستخدام."""
    r = e.get("range") or {}
    return (f"{e.get('value')} {e.get('unit', '')} "
            f"(المدى {r.get('low')}–{r.get('high')}، "
            f"±{e.get('width_pct')}%)")


def canonical_decision_value(entry: object) -> str:
    """الصيغةُ القانونية **بلا سؤالِ الراية** — مرجعُ المقابلة في البوابة.

    فاصلُ آلافٍ من `fmt_number`، ومدىً منحلٌّ (طرفاه متساويان) يُطوى فلا
    يُقدَّم مجالَ قياسٍ ±0% حيث لا مجال.
    """
    e = entry if isinstance(entry, dict) else {}
    unit = str(e.get("unit") or "").strip()
    body = fmt_number(e.get("value"))
    head = f"{body} {unit}".strip()
    r = e.get("range") or {}
    lo, hi = r.get("low"), r.get("high")
    if lo is None or hi is None or _as_float(lo) == _as_float(hi):
        return head
    return (f"{head} (المدى {fmt_number(lo)}–{fmt_number(hi)}، "
            f"±{e.get('width_pct')}%)")


def fmt_decision_value(entry: object) -> str:
    """خانةُ القيمة كما تُعرَض **الآن**: قانونيةً مع الراية، والقائمةُ حرفاً
    بحرفٍ بدونها. والبوابةُ تقابل هذه بتلك فتعرف أيُّ مسارٍ سارٍ."""
    return (canonical_decision_value(entry) if decision_number_format()
            else _legacy_decision_value(
                entry if isinstance(entry, dict) else {}))


def fmt_year(v: object) -> str:
    """سنةٌ للعرض — بلا فاصلِ آلاف («2024» لا «2,024»)."""
    n = _as_float(v)
    if n is None:
        return GAP if v is None else str(v)
    return str(int(round(n)))


def fmt_observed_at(v: object, lang: str = "ar") -> str:
    """تاريخُ الرصد — يُطبَع **إن وُجد في البيانات فقط**.

    عند غيابه يُقال ذلك صريحاً، ولا يُستعار تاريخُ التشغيل: بلاغُ المالك أن
    تاريخَ التشغيل طُبِع مكانَ تاريخِ الرصد، فقرأ القارئُ بياناتَ 2018
    كأنها رُصدت اليوم. ساعةُ خطِّ التجميع ليست معطىً.
    """
    s = str(v or "").strip()
    if not s:
        return (OBSERVED_UNKNOWN_EN if str(lang).lower().startswith("en")
                else OBSERVED_UNKNOWN_AR)
    return s


def past_tense_projection(year: object, today_year: "int | None" = None) -> bool:
    """هل مضت سنةُ التوقّع؟ — «يُتوقَّع أن يبلغ في 2024» مكتوبةً في 2026 خطأٌ
    زمنيّ يصل القارئ. القرارُ هنا، والصياغةُ عند المُصدِّر."""
    n = _as_float(year)
    if n is None:
        return False
    if today_year is None:
        import datetime
        today_year = datetime.date.today().year
    return int(n) < int(today_year)


def fmt_money(v: object) -> str:
    """مبلغٌ بالدولار مقروء — الاسمُ القائم، والمنطقُ من المُنسِّق الواحد.

    الصنف ٣: كانت هذه نسخةً ثانيةً من قواعد المقادير (منزلةٌ واحدة للمليون،
    واختزالُ «ألف» بلا عشور) تتباعد عن `silk_reports._readable_number`
    و`_fmt`. صارت غلافاً لـ`fmt_amount(v, "USD")` — مصدرٌ واحد، وسطحُ النداء
    كما هو حرفياً لكلّ مُستهلِك.
    """
    return fmt_amount(v, "USD")


def confidence_phrase(c: object, lang: str = "ar",
                      cap: "str | None" = None) -> str:
    """الثقة كحالة لغوية بنسبة مقروءة — لا كسر عشري خام على وجه التقرير.

    الموجة ٠: **النسبة نفسها والنطاق نفسه** في اللغتين — الرقم يخرج من
    المحرّك الحتمي لا من العارض؛ التسمية وحدها تتبع لغة التقرير.

    `cap` (الدرس ٢٥٤): سقفُ التسمية من `silk_decision.confidence_band_cap`،
    يُمرَّر كما هو إلى `confidence_band_label`. **النسبة لا تُمَسّ** — تُطبَع
    كما وردت من المحرّك؛ التسميةُ وحدها تُسقَّف. بلا تمرير: السلوك حرفياً
    كما كان (كلُّ مُنادٍ قائمٍ لا يتغيّر عنده حرف).

    لماذا وُجد الوسيط: سقفُ الصنف ٨ كان مُطبَّقاً في `silk_render.build_view`
    (العرض) وفي بوّابة الجودة (الحجب) **ولم يكن يصل موجّهَ الكاتب** — وهذه
    الدالّة هي منبعُه الوحيد هناك (`silk_ai_judge._summarize_verdict`). فكان
    الموجّهُ يُسلّم الكاتبَ «عالية (80%)» ويأمره بعدم ذكر تسميةٍ غيرها، ثم
    تحجب البوّابةُ التقريرَ على طاعته. عائلة الدرس ٩٨.
    """
    import silk_i18n
    lang = silk_i18n.normalize(lang)
    if c is None:
        return ("غير محسوبة" if lang == "ar" else "not calculated")
    try:
        n = float(c)
    except (TypeError, ValueError):
        return str(c)
    pct = round(n * 100)
    # §F-3 (حزمة الفكس v2.1) + WP-1 §4: نطاقات الثقة الموحّدة — عالية ≥80% /
    # متوسطة 60-79% / منخفضة <60%. العتبات والمشتقّ في سُلَّم المعايرة الواحد
    # (silk_style_contract.confidence_band_label) — لا نسخة محلية قد تتباعد.
    from silk_style_contract import confidence_band_label
    return f"{confidence_band_label(pct, lang, cap=cap)} ({pct}%)"


# عتبات شارة الأدلة — ثابت واحد (P0-B، الموجة ٩): بلاغ حي "درجات ثقة تبدو
# بلا سند" — أرقام "(ثقة 0.6)" خام كانت تتخلّل السرد بلا سياق لقارئ غير
# تقني. رقمها الكامل ينتقل لملحق تقني للمدقّقين؛ متن التقرير يحمل شارة
# مبسّطة ثلاثية فقط. رُحِّلت إلى هنا (P2) لتُستعمل في نموذج العرض نفسه
# (silk_render._deep_research_view) لا في طبقة العرض النصي وحدها.
EVIDENCE_VERIFIED_MIN = 0.8
EVIDENCE_SECONDARY_MIN = 0.5


def evidence_badge(confidence: object) -> str:
    """شارة أدلة ثلاثية — ✓ موثّق (مصدر رسمي)/◐ ثانوي (مصدر واحد غير رسمي)/
    ○ غير متحقق (مرشّح غير مؤكَّد) — بدل رقم ثقة خام في متن السرد."""
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return "○ غير متحقق"
    if c >= EVIDENCE_VERIFIED_MIN:
        return "✓ موثّق"
    if c >= EVIDENCE_SECONDARY_MIN:
        return "◐ ثانوي"
    return "○ غير متحقق"


# WP-3 §1 — وسم المنشأ «(Claude tool-use)» يبقى داخلياً على DataPoint
# ويُجرَّد للعرض فقط؛ هنا يُقرأ لسقف تصنيف الشارة، لا للعرض.
TOOLUSE_MARK_RE = re.compile(r"\(\s*(?:Claude\s*)?tool[-\s]?use\s*\)", re.I)

# وسم سجل الأدلة لبندٍ رفضته المصالحة الرقمية (WP-3 §2).
RECONCILED_OUT_TAG = "متعارض — مستبعد"


# طرائقُ استرجاعٍ تعني «جمعه وكيلٌ بأدواته» — إشارةٌ بنيويّةٌ لا نصّية.
# `recovered` ضمنها (الموجة C، §٦): نقطةٌ جاءت من **محاولةٍ ثانية** بعد إخفاق
# الأولى ليست رصداً مباشراً — عرضُها «✓ موثّق» ادّعاءُ منشأٍ لم يحدث، حتى وإن
# كان المصدرُ رسمياً والقيمةُ صحيحة.
AGENT_RETRIEVAL_METHODS = ("llm_web", "mission_label_fallback", "recovered")


def is_agent_gathered(source: object, retrieval_method: object = "") -> bool:
    """هل جُمِع البند بوكيل بحث؟ — بالوسم النصّيّ القديم أو بالإشارة البنيوية.

    **الموجة C (T-13):** الوسمُ النصّيّ «(Claude tool-use)» كان يعيش في
    `source`، وأزالته الموجةُ B حين صار `source` هو المصدرَ العموميَّ الحقيقيّ.
    فبقي سقفُ الرتبة **خامداً بلا أن يُحذَف** — يبدو قائماً وهو لا يعمل، وهي
    أسوأُ حالات الحارس. الإشارةُ البنيويّة (`retrieval_method`) تحلّ محلَّه،
    ويبقى النصّيُّ مقبولاً للبيانات المخزَّنة قبل الموجة.
    """
    if TOOLUSE_MARK_RE.search(str(source or "")):
        return True
    return str(retrieval_method or "") in AGENT_RETRIEVAL_METHODS


def evidence_badge_for(finding: object) -> str:
    """WP-3 — شارة الأدلة الواعية بالمنشأ والمصالحة، لسجلّ الأدلة وكل عدّاد:

    1. بند أسقطته المصالحة الرقمية (`evidence_tag` = «متعارض — مستبعد»)
       يعرض وسمه بدل أي شارة — لا «✓ موثّق» لرقمٍ رفضه السرد/المصالحة.
    2. بند مُعاد تأطيره «مؤشر سياقي» (رمز HS غير مؤكَّد) يُسقَف عند ◐.
    3. بند جمعه وكيل بحث (وسم tool-use) يُسقَف درجةً واحدة تحت شارة مصدره
       المسمّى (✓→◐، ◐→○) ما لم يُسانده رصدٌ مباشر من جامعٍ رسمي
       (`corroborated=True` يضبطها ممرّ المصالحة في نموذج العرض).
    القيم لا تتغيّر أبداً — التصنيف فقط (عقد عدم الاختلاق)."""
    if isinstance(finding, dict):
        f = finding
    else:
        f = {"confidence": getattr(finding, "confidence", None),
             "source": getattr(finding, "source", None),
             "retrieval_method": getattr(finding, "retrieval_method", "")}
    tag = str(f.get("evidence_tag") or "")
    if tag.startswith(RECONCILED_OUT_TAG):
        return RECONCILED_OUT_TAG
    badge = evidence_badge(f.get("confidence"))
    if tag.startswith("مؤشر سياقي") and badge.startswith("✓"):
        badge = "◐ ثانوي"
    if is_agent_gathered(f.get("source"), f.get("retrieval_method")) \
            and not f.get("corroborated"):
        if badge.startswith("✓"):
            return "◐ ثانوي"
        if badge.startswith("◐"):
            return "○ غير متحقق"
    return badge


def competition_phrase(hhi: object, top_share_pct: object = None,
                       n_suppliers: object = None) -> str:
    """حالة المنافسة بالعربية — مؤشر HHI الخام لا يصل المستخدم أبداً.

    العتبات هي أشرطة وزارة العدل الأمريكية القياسية للتركّز (0.15/0.25) —
    تصنيف معياري معلن فوق رقم مرصود، لا حكم جديد.
    """
    if hhi is None:
        return GAP_WORD
    try:
        h = float(hhi)
    except (TypeError, ValueError):
        return str(hhi)
    if h < 0.15:
        state = "منافسة مفتوحة — لا مورّد مهيمن"
    elif h < 0.25:
        state = "منافسة معتدلة التركّز"
    else:
        state = "سوق عالي التركّز — مورّد أو اثنان يهيمنان"
    bits = [state]
    if n_suppliers:
        bits.append(f"{n_suppliers} مورّداً نشطاً")
    if top_share_pct is not None:
        bits.append(f"حصة الأكبر {fmt_pct(top_share_pct)}")
    return "؛ ".join(bits)


def growth_phrase(cagr_pct: object, growth_pct: object = None,
                  years: str = "") -> str:
    """النمو بالعربية — «CAGR» يُستبدل بمصطلحه العربي الكامل."""
    if cagr_pct is None and growth_pct is None:
        return GAP_WORD
    bits = []
    if growth_pct is not None:
        arrow = "نمو" if float(growth_pct) >= 0 else "انكماش"
        bits.append(f"{arrow} إجمالي {fmt_pct(abs(float(growth_pct)))}"
                    + (f" عبر {years}" if years else ""))
    if cagr_pct is not None:
        bits.append(f"بمعدل نمو سنوي مركّب {fmt_pct(cagr_pct)}")
    return " ".join(bits)


def translate_gaps(gaps: list) -> list[str]:
    """فجوات داخلية (بأسماء وكلاء/مقاييس وهياكل إنجليزية) → عربية كاملة.

    لا اسم صنف كود ولا هيكل جملة إنجليزي يمرّ — ملاحظات الفجوة الداخلية
    تبقى كما هي في نموذج البيانات؛ الترجمة للعرض فقط. مُفوَّض بالكامل
    لـ `humanize_technical_note` — نقطة تعريب واحدة (راجع تعليقها).
    """
    return [humanize_technical_note(g) for g in (gaps or [])]


# ── الخلاصة التنفيذية السردية — the 3-paragraph executive summary ───────────

def market_component_lines(market: dict) -> list[str]:
    """جمل تجارية سردية من مكوّنات سوق واحد أياً كان ترتيبه في القائمة —
    بلا ثقة خام ولا اسم مقياس داخلي؛ سطر واحد لكل حقيقة مرصودة + مصدرها.
    تعذّر الجلب يُذكر صراحة بدل إسقاطه صامتاً — لا فجوة صامتة."""
    drivers: list[str] = []
    comps = {c.get("name"): c for c in
             (market.get("components_detail") or [])}
    ms = comps.get("market_size") or {}
    if ms.get("value") is not None:
        drivers.append(f"يستورد السوق ما قيمته {fmt_money(ms['value'])} سنوياً "
                       f"من هذا المنتج (المصدر: {ms.get('source')})")
    elif ms.get("status") == "fetch_failed":
        drivers.append("حجم واردات السوق: تعذّر الجلب — أعد المحاولة")
    tr = market.get("trend") or {}
    if tr.get("growth_pct") is not None:
        drivers.append(
            growth_phrase(tr.get("cagr_pct"), tr.get("growth_pct"),
                          years="سنوات الدراسة")
            + f" (المصدر: {tr.get('source') or 'UN Comtrade'})")
    sp = comps.get("saudi_position") or {}
    if sp.get("value") is not None:
        drivers.append(f"المنتجات السعودية حاضرة فعلاً بحصة "
                       f"{fmt_pct(sp['value'])} من واردات السوق "
                       f"(المصدر: {sp.get('source')})")
    elif sp.get("status") == "fetch_failed":
        drivers.append("الحصة السعودية: تعذّر الجلب — أعد المحاولة")
    comp = comps.get("competition") or {}
    if comp.get("value") is not None:
        drivers.append(competition_phrase(comp["value"]))
    return drivers


def exec_summary(view: dict) -> list[str]:
    """ثلاث فقرات عربية كاملة: التوصية / لماذا تجارياً / ما ينقص للتأكد.

    بلا درجات معيارية، بلا أسماء وكلاء، بلا شروط كود — كل جملة من حقل محسوب.
    """
    d = view.get("decision") or {}
    top = (view.get("markets") or [{}])[0]
    market = country_ar(top.get("iso3"), d.get("market") or top.get("country"))

    # (أ) التوصية بكلمات بسيطة.
    p1 = f"التوصية: {verdict_ar(d.get('verdict'))} لسوق {market}"
    p1 += f"، بدرجة ثقة {confidence_phrase(d.get('confidence'))}."
    if str(d.get("verdict") or "").upper().find("CONDITIONAL") >= 0:
        p1 += (" الفرصة قائمة، لكن اكتمال الصورة يتطلب استيفاء الشروط "
               "الواردة أدناه قبل قرار نهائي.")

    # (ب) لماذا — تجارياً، من الأرقام المرصودة فقط.
    # الدرس ٢٦٤: صياغةٌ واحدةٌ محكمةٌ بلغة محلّل بدل «الأساس التجاري:»
    # الحرفية المتكرّرة في كل تقرير — نفسُ الأرقام ونفسُ الترتيب، بنبرةٍ
    # يكتبها إنسان. (لا قوالبَ متناوبة: قرارُ المالك.)
    # ومراجعةٌ ذاتية (§58): العنوانُ القديم كان محايداً، أمّا «ما يسند» فهو
    # **ادّعاءُ إسناد** — فلا يصحّ أن يُدرَج تحته سطرُ «تعذّر الجلب». يُفصَل
    # المرصودُ عمّا تعذّر، ويُقال كلٌّ باسمه.
    observed, failed = [], []
    for line in market_component_lines(top):
        (failed if "تعذّر الجلب" in line else observed).append(line)
    if observed:
        p2 = "ما يسند هذه القراءة: " + "؛ و".join(observed) + "."
        if failed:
            p2 += " ولم يُرصد بعد: " + "؛ و".join(
                x.split(":")[0].strip() for x in failed) + "."
    else:
        p2 = ("لم يُرصد بعدُ ما يكفي من بيانات هذا السوق لبناء القراءة على "
              "أرقامه وحدها، فالتوصية أعلاه مبنية على التغطية الجزئية "
              "المتاحة.")

    # (ج) ما ينقص للتأكد — من limits/الشروط، مترجَماً.
    missing = translate_gaps((view.get("limits") or [])[:2])
    ed = top.get("entry_decision") or {}
    if not missing and ed.get("conditions"):
        missing = translate_gaps(ed["conditions"][:2])
    if missing:
        # البندُ ينتهي بنقطةٍ في مصدره، فكان الفاصلُ يُنتِج «.؛» و«..».
        p3 = ("ويبقى قبل الحسم النهائي: "
              + "؛ ".join(x.rstrip(" .،؛") for x in missing) + ".")
    elif _all_sections_ok(top):
        p3 = ("ولا يعترض اعتمادَ هذه القراءةِ الأوليةِ نقصٌ جوهريٌّ — مكوّنات "
              "التقييم الرئيسية لهذا السوق مكتملة.")
    else:
        # قائمةُ حدودٍ فارغةٌ ليست دليلَ اكتمال: سوقٌ بلا بياناتٍ أصلاً كان
        # يُقال عنه «مكوّناتُ التقييم مكتملة» بعد سطرين من «لم يُرصد ما
        # يكفي» — فجوةٌ تُقدَّم مُغلَقة (مراجعةٌ ذاتية §58).
        p3 = ("ولم تُسجَّل حدودٌ مسمّاةٌ لهذه القراءة، لكنّ أقساماً من التقييم "
              "لم تبلغ عتبة الكفاية — راجع تغطية الأقسام قبل الحسم.")
    return [p1, p2, p3]


def _all_sections_ok(market: dict) -> bool:
    """أبلغت **كلُّ** أقسام هذا السوق عتبةَ الكفاية؟ (بوابة 2B نفسُها.)"""
    st = market.get("section_status") or {}
    return bool(st) and all((v or {}).get("status") == "ok"
                            for v in st.values())


def count_sentence(n: int, one: str, two: str, plural: str,
                   acc_sing: str) -> str:
    """عددٌ ومعدودٌ بمطابقة العربية — «شرط واحد»، «شرطان»، «ثلاثة شروط»،
    «أحد عشر شرطاً». الدرس ٢٦٢: استبدالُ الرقم وحده في جملةٍ مكتوبة يُنتِج
    «2 شروط»؛ الصيغةُ تُبنى كاملةً من العدد.
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return f"لا {plural}"
    if n == 1:
        return f"{one} واحد"
    if n == 2:
        return two
    if n <= 10:
        return f"{_AR_ONES[n]} {plural}"
    return f"{_AR_TEENS.get(n, str(n))} {acc_sing}"


#: أسماء الأعداد ٣–١٠ (تُضاف للجمع) و١١–١٩ (تُضاف للمفرد المنصوب).
_AR_ONES = {3: "ثلاثة", 4: "أربعة", 5: "خمسة", 6: "ستة", 7: "سبعة",
            8: "ثمانية", 9: "تسعة", 10: "عشرة"}
_AR_TEENS = {11: "أحد عشر", 12: "اثنا عشر", 13: "ثلاثة عشر",
             14: "أربعة عشر", 15: "خمسة عشر", 16: "ستة عشر",
             17: "سبعة عشر", 18: "ثمانية عشر", 19: "تسعة عشر"}


def brief_lines(view: dict) -> list[str]:
    """سطور المختصر البشرية — بديل شعارات «القرار: X (ثقة 0.52)» الآلية."""
    d = view.get("decision") or {}
    top = (view.get("markets") or [{}])[0]
    market = country_ar(top.get("iso3"), d.get("market") or top.get("country"))
    lines = [f"{verdict_ar(d.get('verdict'))} — سوق {market} "
             f"(ثقة {confidence_phrase(d.get('confidence'))})"]
    for c in (top.get("components_detail") or []):
        if c.get("value") is None:
            continue
        label = internal_ar(c.get("name"))
        val = (fmt_money(c["value"]) if c.get("name") == "market_size"
               else fmt_pct(c["value"]) if c.get("name") == "saudi_position"
               else competition_phrase(c["value"])
               if c.get("name") == "competition"
               else fmt_money(c["value"]))
        lines.append(f"{label}: {val} — المصدر: {c.get('source')}")
        if len(lines) >= 4:
            break
    return lines
