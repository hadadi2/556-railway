"""وكيل الميثاق — Charter Agent (محرك دراسة السوق، القاعدة ١).

يُشغَّل أولاً ووحيداً، قبل أن تلمس أيّ بعثة من الاثنتي عشرة الملفَّ: يجمّد
تعريف المنتج، ورمز HS، ووسيلةَ النقل، قبل أن يُبنى عليها أيّ عمل لاحق.

**حادثة دراسة #9 (السبب المباشر لهذا الملف).** دراسةٌ عامة عن «الحليب»
حُلِّلت على HS 040110 — وهو نصّاً «حليب ومنتجات ألبان لا تتجاوز نسبة
الدهن فيها ١٪ وزناً» (منزوع الدسم حصراً)، لا الحليبَ عموماً. لم يكتشف
أحد التضييق لأن المطابقة اللفظية القائمة (`silk_hs_confirm.confirm_hs`)
تكتشف **تعارضاً صريحاً** فقط (اسمُ منتج يحمل صفة درجة تناقض الرمز، مثل
"full fat milk" ضد 040110) — لا **التضييق الصامت**: منتَجٌ عامٌّ بلا أي
صفة دهن مصرَّحة يُصادَق على رمزٍ ضيّق بعتبةٍ رقمية بلا اعتراض، لأن
تداخل الكلمات وحده (حليب ∈ وصف الرمز) يكفي لإقناع المطابق اللفظي.

هذا الملف **يضيف** فحصاً جديداً فوق `silk_hs_confirm` الموجود (لا يُعيد
كتابته): إن كان وصفُ الرمز محدوداً بنفيٍ/عتبةٍ رقمية (`describes_by_
exclusion`) ولم تُصرِّح الدراسة بأيّ صفةٍ مميّزة تتقاطع لفظياً مع ذلك
الوصف — فالتصنيفُ تضييقٌ صامت، ويُعلَن استبعاداً يوقف الميثاق.

**طَور الطرح — الموجة ١ (SHADOW فقط).** يُحسَب الميثاقُ ويُرفَق دوماً
بنتيجة `/research` (`result["charter"]`)، دون أن يوقف أيّ تشغيلة حقيقية
بعد. التوقّفُ الفعليّ (`ENFORCE`) موجودٌ في الشيفرة لكنه خلف صمّامٍ
مُطفأ افتراضياً (`SILK_CHARTER_ENFORCE`) — قاعدة الطرح «SHADOW ← WARN ←
ENFORCE، علمٌ واحدٌ قابلٌ للعكس» (قواعد محرك دراسة السوق، البند ١٠).
تدقيقُ كل مستهلكٍ لشكل `deep_research()` قبل تفعيل ENFORCE إنتاجياً
مسؤوليةُ الموجة التالية — لا يُفترَض هنا.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass

import silk_hs_confirm

#: جيرانُ السعودية البرّيون — حدودٌ فعلية، لا عضويةُ كتلةٍ تجارية (تلك في
#: silk_blocs.py). يُستعمَل لتحديد وسيلة النقل قبل أيّ عملٍ لوجستي —
#: القاعدة ١: «لا افتراض بحري تلقائي؛ سوقٌ ملاصقة بَرّاً تُحلَّل عبر المعبر».
SAUDI_LAND_NEIGHBORS = frozenset({"JOR", "IRQ", "YEM", "ARE", "QAT", "KWT", "OMN"})
#: متّصلةٌ بجسرٍ ثابت (جسر الملك فهد) — تُعامَل معاملة البرّي تجارياً لا
#: البحري (شحنُ الشاحنات عبر الجسر لا عبر ميناء).
SAUDI_CAUSEWAY_LINKED = frozenset({"BHR"})

#: صمّام التفعيل الصلب — مُطفأٌ افتراضياً (SHADOW). "1" يُفعِّل التوقّف الفعليّ.
CHARTER_ENFORCE_ENV = "SILK_CHARTER_ENFORCE"

_DEFAULT_HS_PATH = "data/hscodes_full.csv"
_TOKEN_RE = re.compile(r"[\w؀-ۿ]+")


def charter_enforce_enabled() -> bool:
    """هل صمّام التوقّف الفعليّ مفعَّل؟ افتراضياً لا (SHADOW)."""
    return os.environ.get(CHARTER_ENFORCE_ENV, "0") == "1"


def _simple_tokens(text: str) -> set:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def determine_transport_mode(market_iso3: str | None) -> dict:
    """وسيلةُ النقل من الجغرافيا — لا افتراض بحري تلقائي (القاعدة ١).

    سوقٌ ملاصقة بَرّاً (أو متّصلة بجسر) للسعودية تُحلَّل عبر معبرها
    البرّي، لا عبر ميناءٍ بحريّ افتراضي (حادثة مرجعية: الأردن ↔ ميناء
    العقبة البحري بينما المعبر البرّي هو المسار الفعليّ الأرخص)."""
    if not market_iso3:
        return {"mode": None,
                "reason": "لا رمز دولة (iso3) للسوق — يتعذّر تحديد وسيلة النقل"}
    iso = market_iso3.upper()
    if iso in SAUDI_LAND_NEIGHBORS:
        return {"mode": "land",
                "reason": f"{iso} تشترك بحدود برّية مباشرة مع السعودية — "
                          "يُحلَّل المعبر البرّي، لا ميناء بحري افتراضي"}
    if iso in SAUDI_CAUSEWAY_LINKED:
        return {"mode": "land",
                "reason": f"{iso} متّصلة بجسرٍ ثابت (جسر الملك فهد) — "
                          "تُعامَل معاملة النقل البرّي تجارياً"}
    return {"mode": "sea",
            "reason": f"{iso} بلا حدود برّية مع السعودية — النقل البحري/"
                      "الجوي هو المسار الافتراضي القابل للتحليل"}


def check_attribute_exclusion(product: str, hs_code: str,
                              declared_attributes: list | None = None,
                              path: str = _DEFAULT_HS_PATH) -> dict:
    """يقارن وصفَ الرمز بصفات المنتج المميّزة **المصرَّح بها في الدراسة**.

    فرعان مستقلّان، كلاهما يُعلن استبعاداً:
    (١) تعارضٌ لفظيٌّ صريح **أو غموضٌ درجة/عتبة** يكتشفه `confirm_hs` أصلاً
        (اسمُ منتج يحمل صفةَ درجة أمام رمزٍ محدودٍ بعتبة — سواء ناقضته
        «full fat milk» أو وافقته «skimmed milk» ضد 040110: التمييزُ رقميٌّ
        لا لفظيّ، فـ`confirm_hs` نفسُه يرفض الحسم بتطابق الكلمات في
        الحالتين معاً ويطلب تأكيداً — سياسةٌ قائمةٌ من قبل هذا الملف).
    (٢) **تضييقٌ صامت** (الحالة الجديدة، حادثة دراسة #9): وصفُ الرمز محدودٌ
        بنفيٍ/عتبةٍ رقمية (`describes_by_exclusion`) ولا اسمُ المنتج ولا
        صفاتُ الدراسة المصرَّحة (`declared_attributes`) تحمل **أيّ** صفةَ
        درجةٍ/كمّية إطلاقاً (`silk_hs_confirm._DEGREE_TERMS` — أدواتٌ
        لغويةٌ عامة كـ"skimmed"/"full"/"منزوع"، لا نصّاً حرفياً من وصف
        الرمز — تلافياً لهشاشة مطابقة الترجمة/الصياغة) — أي أن أحداً لم
        يُصرِّح بأيّ نطاقٍ ضيّق إطلاقاً. دراسةٌ كهذه تُستبعَد دوماً أمام
        رمزٍ ضيّق — فشلٌ آمن مقصود (لا يقع لو صرَّحت بأيّ صفة درجة، ولو
        كانت الصفةُ نفسها تحتاج فرع (١) لاحقاً للتأكد من موافقتها للرمز).
    """
    result = silk_hs_confirm.confirm_hs(product, hs_code, path=path)
    code_desc = result.get("code_desc") or ""
    excluded: list = []

    if result.get("confirmed") is False:
        excluded.append(result.get("reason") or
                        "وصف الرمز لا يطابق صفات المنتج المصرَّحة")
    elif code_desc and silk_hs_confirm.describes_by_exclusion(code_desc):
        product_tokens = set(result.get("product_terms") or [])
        declared_tokens: set = set()
        for a in (declared_attributes or []):
            declared_tokens |= _simple_tokens(a)
        has_degree_signal = bool(
            (product_tokens | declared_tokens) & silk_hs_confirm._DEGREE_TERMS)
        if not has_degree_signal:
            excluded.append(
                f"الرمز {hs_code} محدودٌ بعتبةٍ/نفيٍ رقميّ في وصفه "
                f"(«{code_desc}»)، ولا اسمُ المنتج ولا صفاتُ الدراسة "
                "المصرَّحة تحمل أيّ صفةَ درجة/كمّية — تصنيفٌ عامٌّ على "
                "رمزٍ ضيّقٍ صامتاً (حادثة دراسة #9: «حليب» عام صُنِّف "
                "على 040110 منزوع الدسم حصراً)")

    return {"excluded_attributes": excluded, "code_desc": code_desc,
            "confirm": result}


@dataclass(frozen=True)
class Charter:
    """الميثاق — مجمَّد فور إصداره (dataclass غير قابل للتعديل)."""

    product: str
    hs_code: str | None
    market_iso3: str | None
    code_desc: str
    excluded_attributes: tuple
    halted: bool
    halt_reason: str | None
    transport_mode: str | None
    transport_reason: str
    charter_confidence: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["excluded_attributes"] = list(self.excluded_attributes)
        return d


def build_charter(product: str, hs_code: str | None,
                  market_iso3: str | None = None,
                  declared_attributes: list | None = None,
                  path: str = _DEFAULT_HS_PATH) -> Charter:
    """يبني الميثاق — يُعاد تصنيف HS **في كل استدعاء** (لا استظهار/تخزين
    مؤقّت هنا؛ القاعدة ١: «لا يُعاد استخدام رمز مخزَّن»)."""
    transport = determine_transport_mode(market_iso3)

    if not hs_code:
        return Charter(
            product=product, hs_code=None, market_iso3=market_iso3,
            code_desc="", excluded_attributes=(), halted=False,
            halt_reason=None, transport_mode=transport["mode"],
            transport_reason=transport["reason"], charter_confidence=0.0)

    attr_check = check_attribute_exclusion(
        product, hs_code, declared_attributes, path=path)
    excluded = tuple(attr_check["excluded_attributes"])
    halted = bool(excluded)
    # ملاحظة: `confirmed is False` يُسقِط `excluded` غير فارغة دوماً (الفرع ١
    # في check_attribute_exclusion) — أي `halted=True` حتماً؛ فلا حالة
    # `halted=False` مع `confirmed=False` ممكنة أصلاً هنا.
    confirmed = attr_check["confirm"].get("confirmed")
    if halted:
        charter_confidence = 0.0
    elif confirmed is True:
        charter_confidence = 1.0
    else:
        charter_confidence = 0.5   # confirmed is None — لا حكم، لا اختلاق

    return Charter(
        product=product, hs_code=hs_code, market_iso3=market_iso3,
        code_desc=attr_check["code_desc"], excluded_attributes=excluded,
        halted=halted, halt_reason=(excluded[0] if excluded else None),
        transport_mode=transport["mode"], transport_reason=transport["reason"],
        charter_confidence=charter_confidence)


if __name__ == "__main__":
    c = build_charter("حليب", "040110", market_iso3="JOR")
    print(c.to_dict())
