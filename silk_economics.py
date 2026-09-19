"""الحساب الاقتصادي الموحّد — canonical economics arithmetic (الموجة 2أ).

> **الغرض.** دوالّ حسابية واحدة قانونية يستوردها الجميع بدل التكرار الصامت:
> - `hhi()` — مؤشر هيرفندال–هيرشمان على **مقياس واحد معلن 0–10000**
>   (اصطلاح سطح العميل: فوق 2500 تركّز مرتفع — silk_style_contract). كان
>   المؤشر يُحسب في موضعين بمقياس 0–1 بينما العتبات المعروضة 0–10000 —
>   خطر مقارنة 0.25 بـ2500 صامتة.
> - `landed_cost()` — معادلة التكلفة الواصلة الوحيدة (مفصولة من
>   correlation.py وتُستورد عائدةً إليه — لا نسختان تتباعدان).
>
> **Purpose.** One canonical arithmetic module: `hhi()` on the single declared
> 0–10000 scale, and the ONE landed-cost formula factored out of
> correlation.py and imported back.

المكتبات: stdlib فقط؛ صفر شبكة. يضم محرك §5.4 كاملاً: سلسلة التكلفة الواصلة
المُعلمَنة + الشلال (`margin_waterfall`) + الحل العكسي (`reverse_solve_max_exw`).
"""
from __future__ import annotations

HHI_SCALE_MAX = 10_000
HHI_HIGH_CONCENTRATION = 2_500   # فوقها تركّز مرتفع (اصطلاح العميل المعلن)
HHI_MODERATE_CONCENTRATION = 1_500   # بينها و2500 تركّزٌ متوسط — الحدُّ
# الأدنى المعتاد في أدلّة المنافسة؛ يُقرَأ من هنا حصراً (رسمُ التركّز، الموجة ٥).


def hhi(shares_pct) -> int | None:
    """HHI على مقياس 0–10000 من حصص **مئوية** (0–100).

    - يتجاهل القيم غير الرقمية/السالبة (لا اختلاق — تُسقَط لا تُصفَّر).
    - يعيد None لقائمة فارغة (فجوة، لا صفر مختلَق).
    - المدخل بكسور 0–1؟ استعمل hhi_from_fractions — لا تخمين مقياس هنا.
    """
    vals = []
    for s in shares_pct or ():
        try:
            f = float(s)
        except (TypeError, ValueError):
            continue
        if f >= 0:
            vals.append(f)
    if not vals:
        return None
    return round(sum(s * s for s in vals))


def hhi_from_fractions(shares_frac) -> int | None:
    """HHI 0–10000 من حصص كسرية (0–1) — التحويل الصريح الوحيد للمقياس."""
    try:
        return hhi([float(s) * 100.0 for s in shares_frac or ()
                    if s is not None])
    except (TypeError, ValueError):
        return None


def hhi_band(value_0_10000) -> "str | None":
    """منطقةُ التركّز على المقياس الموحّد: "open" دون 1500، "moderate" بين
    1500 و2500، "high" فوق 2500 — `None` لقيمةٍ غير رقمية أو خارج 0–10000
    (فجوةٌ لا منطقةٌ مخمَّنة). المصدرُ الواحد لتسمية المنطقة على كلّ سطح.

    **الصفرُ فجوةٌ لا سوقٌ مفتوحة** (مراجعة §58): HHI لسوقٍ حقيقيةٍ أكبرُ من
    صفرٍ حتماً (أيُّ حصّةٍ مرصودة ترفعه)، والصفرُ يصل من مسارٍ يكتب
    `hhi = حساب أو 0` حين لا حصّةَ صالحة — فقراءتُه «مفتوحة» حكمٌ على قياسٍ
    غائب، وهو عينُ ما يحظره عقدُ عدم الاختلاق (البند ٨).
    """
    try:
        v = float(value_0_10000)
    except (TypeError, ValueError):
        return None
    if not (0 < v <= HHI_SCALE_MAX):
        return None
    if v > HHI_HIGH_CONCENTRATION:
        return "high"
    if v >= HHI_MODERATE_CONCENTRATION:
        return "moderate"
    return "open"


def hhi_is_high(value_0_10000) -> bool:
    """هل يتجاوز عتبة التركّز المرتفع 2500؟ (على المقياس الموحّد حصراً)."""
    try:
        return float(value_0_10000) > HHI_HIGH_CONCENTRATION
    except (TypeError, ValueError):
        return False


def landed_cost(cost: float, shipping: float,
                tariff_pct: float | None) -> float:
    """التكلفة الواصلة — المعادلة الواحدة (مفصولة من correlation.py):
    (التكلفة + الشحن) × (1 + التعرفة٪/100)؛ تعرفة غير مرصودة (None) =
    التكلفة + الشحن، والمستدعي يعلن الفجوة (لا صفر تعرفة مختلَق)."""
    base = float(cost) + float(shipping)
    if tariff_pct is None:
        return base
    return base * (1.0 + float(tariff_pct) / 100.0)


# ═══════════════════ الموجة ٣ — تطبيع الوحدات + المحرك الاقتصادي ═══════════════════
# (توجيه المنصّة §4.3/§5.4 + تعديل مالك ٢): بنية سعر مطبّعة واحدة، سجل ثوابت
# تحويل كلٌّ بمصدره، سلسلة تكلفة واصلة مُعلمَنة، شلال هوامش، وحلّ عكسي لأقصى
# سعر مصنع منافس. حتمي بالكامل — صفر شبكة، صفر نماذج.

from dataclasses import dataclass, field, asdict

# سجل ثوابت التحويل — كل ثابت بمصدره وفئة المنتج المنطبقة (تعديل مالك ٢:
# «لا ثابت مكتوب في الكود بلا مرجع»). المفتاح: (من، إلى، فئة).
CONVERSION_REGISTRY: dict = {
    ("litre", "kg", "milk"): (
        1.03, "كثافة الحليب 1.03 كجم/لتر — USDA/FAO (ثابت فيزيائي معروف)"),
    ("litre", "kg", "water"): (
        1.00, "كثافة الماء 1.00 كجم/لتر — تعريف فيزيائي"),
    ("litre", "kg", "vegetable_oil"): (
        0.92, "كثافة الزيوت النباتية ~0.92 كجم/لتر — FAO/Codex"),
    ("litre", "kg", "honey"): (
        1.42, "كثافة العسل ~1.42 كجم/لتر — National Honey Board"),
    ("litre", "kg", "juice"): (
        1.05, "كثافة العصائر ~1.05 كجم/لتر — USDA FoodData"),
}


# ── مفتاحُ فئة التحويل (الموجة C، البند E-06) ─────────────────────────────
#
# **الحادثة:** مفاتيحُ `CONVERSION_REGISTRY` أسماءُ فئاتٍ إنجليزية (`milk`،
# `honey`…)، والمنادي الإنتاجيّ الوحيد يمرّر `category=str(result["product"])`
# — أي **اسمَ المنتج العربيّ** («حليب»). فلا يُصاب مفتاحٌ أبداً، ويُعلَن تعذّرُ
# التحويل على كلّ منتجٍ سائل مهما كانت كثافتُه مسجَّلةً في السجلّ.
#
# الترجمةُ حتميّةٌ ومحدودة: ما لا يُطابَق يبقى **كما هو** فيُصاب المفتاحُ إن
# مرّره منادٍ بالإنجليزية، وإلّا بقيت الفجوةُ معلنةً بلا تخمينِ كثافة.
_CATEGORY_ALIASES = {
    "milk": ("حليب", "لبن", "milk", "dairy drink"),
    "juice": ("عصير", "juice"),
    "honey": ("عسل", "honey"),
    "water": ("ماء", "مياه", "water"),
    "vegetable_oil": ("زيت", "زيت نباتي", "زيت زيتون", "olive oil",
                      "vegetable oil", "cooking oil"),
    "solid_food": ("تمور", "تمر", "dates", "حلاوة", "halva", "halawa", "طحينة", "طحينية",
                   "tahini", "سكر", "sugar", "دقيق", "flour", "أرز", "rice",
                   "زبدة الفول السوداني", "peanut butter"),
    "piece_goods": ("قميص", "قمصان", "shirt", "shirts", "حفاضات", "diapers",
                    "كرسي", "كراسي", "chair", "chairs", "غسالة", "washing machine"),
}


def registry_category(raw: object) -> str:
    """حوّل وصفَ المنتج إلى مفتاح فئةٍ في سجلّ التحويل — أو أعده كما هو."""
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    if any(text == k for k in _CATEGORY_ALIASES):
        return text
    for key, needles in _CATEGORY_ALIASES.items():
        if any(n in text for n in needles):
            return key
    return text


# ── وحدة السوق تتبع المنتج (هدف الدراسة الاحترافية، البند ١) ────────────────
#
# القاعدة: الزائر لا يرى وحدةً لا يشتري بها سوقُه — السوائل باللتر، المواد
# الصلبة بالكيلوغرام، والقطعيّ بالقطعة (يُضاف صفّه حين تدعم المنصّة عائلة
# قطعية). كومتريد يبلّغ بالوزن، والتحويل بين الوحدتين شأنٌ داخليّ عبر
# `CONVERSION_REGISTRY` — لا يُعلَن فجوةً أبداً لفئةٍ ثابتُها مسجّل.
# الفئة غير المسجلة تبقى بوحدة غير محددة؛ لا نخلط وزن بيانات التجارة
# مع وحدة بيع المنتج، ولا نفترض أن كل وحدة تجارية تزن كيلوغراماً.
MARKET_UNIT_REGISTRY = {
    "milk": ("litre", "لتر"),
    "juice": ("litre", "لتر"),
    "water": ("litre", "لتر"),
    "vegetable_oil": ("litre", "لتر"),
    "honey": ("kg", "كجم"),
    "solid_food": ("kg", "كجم"),
    "piece_goods": ("piece", "قطعة"),
}
DEFAULT_MARKET_UNIT = ("unit", "وحدة")


# شكلٌ صلبٌ لفئةٍ سائلة (§58 find all gaps): «حليب مجفف»/«بودرة الحليب» يُطابِق
# «حليب» بالتضمين فيُسعَّر باللتر ويُحوَّل بكثافة السائل 1.03 — رقمٌ مختلَق فوق
# وحدةٍ وكثافةٍ خاطئتين. **الإبر تقتصر على ما يعني الجفاف قطعاً**: مراجعةٌ
# ثانية أثبتت أن «حبيبات»/«granul» تصف سائلاً بحبيبات أيضاً («عصير بحبيبات»)،
# فأُسقِطتا كي لا يُعاد تصنيف سائلٍ صلباً. المُطابَقة على حدود كلمة عربية/لاتينية
# لا تضمّناً خامّاً («مجففة»/«powdered» يُغطّيان، و«undried» لا يُطابِق).
_SOLID_FORM_NEEDLES = ("مجفف", "مجفّف", "مجففة", "مجفّفة", "بودرة", "مسحوق",
                       "powder", "powdered", "dried")


def _has_solid_form_qualifier(text: str) -> bool:
    import re as _re
    low = text.lower()
    for n in _SOLID_FORM_NEEDLES:
        if _re.search(r"(?<![\w])" + _re.escape(n), low):
            return True
    return False


def market_unit(category: object, declared_unit: object = None) -> tuple:
    """(رمز الوحدة، تسميتها العربية) لوحدة السوق التي يُسعَّر بها المنتج
    فعلاً — «حليب» ⇒ ("litre", "لتر")؛ «حليب مجفف» (شكلٌ صلب) ⇒ ("kg", "كجم")؛
    «عصير بحبيبات» (سائل) يبقى لتراً؛ فئة غير مسجّلة ⇒ ("unit", "وحدة")."""
    declared = str(declared_unit or '').strip().lower()
    if declared in ('kg', 'g', 'كجم', 'كغ', 'كيلوغرام', 'غرام', 'جم'):
        return ('kg', 'كجم')
    if declared in ('l', 'ml', 'litre', 'liter', 'لتر', 'مل'):
        return ('litre', 'لتر')
    if declared in ('piece', 'pieces', 'pcs', 'قطعة', 'قطع'):
        return ('piece', 'قطعة')
    if _has_solid_form_qualifier(str(category or "")):
        return ('kg', 'كجم')
    return MARKET_UNIT_REGISTRY.get(registry_category(category),
                                    DEFAULT_MARKET_UNIT)


def convert_amount(value: float, from_unit: str, to_unit: str,
                   category: str = "") -> tuple:
    """تحويل كمية عبر السجل — يعيد (القيمة، ملاحظة الثابت ومصدره) عند وجود
    ثابت، أو (None، رسالة تسمّي الخاصية الفيزيائية المفقودة **تحديداً**).
    قاعدة التعذر (تعديل مالك ٢): عبارة «يتعذر التحويل» العامة ممنوعة."""
    if from_unit == to_unit:
        return float(value), "بلا تحويل (نفس الوحدة)"
    original_category = category
    category = registry_category(category)
    key = (from_unit, to_unit, category)
    if key in CONVERSION_REGISTRY:
        factor, src = CONVERSION_REGISTRY[key]
        return round(float(value) * factor, 4), f"ثابت التحويل {factor} — {src}"
    inv = (to_unit, from_unit, category)
    if inv in CONVERSION_REGISTRY:
        factor, src = CONVERSION_REGISTRY[inv]
        return round(float(value) / factor, 4), f"ثابت التحويل 1/{factor} — {src}"
    missing = ("الكثافة" if {"litre", "kg"} == {from_unit, to_unit}
               else f"معامل التحويل {from_unit}→{to_unit}")
    return None, (f"التحويل {from_unit}→{to_unit} يتطلب {missing} لفئة "
                  f"«{original_category or 'غير محددة'}» — غير مسجّل في سجل الثوابت؛ "
                  "أضفه بمصدره أو صرّح بالخاصية المفقودة")


@dataclass
class NormalizedPrice:
    """سعر مطبّع (تعديل مالك ٢) — دوال المحرك لا تقبل غيره."""

    raw_value: float
    currency: str = ""                 # العملة المحلية كما وردت
    value_usd: float | None = None
    fx_rate: float | None = None
    fx_date: str = ""
    basis: str = "retail"              # retail | wholesale | CIF | FOB | EXW
    per_unit: float | None = None      # سعر الوحدة/العبوة الواحدة
    per_kg: float | None = None
    per_litre: float | None = None
    category: str = ""
    source: str = ""
    note: str = ""
    gaps: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_price(raw_value, *, currency="", basis="retail", category="",
                    pack_kg=None, pack_litre=None, pack_count=1,
                    fx_rate=None, fx_date="", source="",
                    note="") -> NormalizedPrice | None:
    """التطبيع الإلزامي قبل أي مقارنة (§4.3): للوحدة، للكجم، لللتر، وللدولار
    بسعر صرف معلن. الناقص = فجوة تسمّي الخاصية المفقودة — لا تمرير صامت."""
    try:
        raw = float(raw_value)
    except (TypeError, ValueError):
        return None
    np_ = NormalizedPrice(raw_value=raw, currency=currency, basis=basis,
                          category=category, source=source, note=note,
                          fx_rate=fx_rate, fx_date=fx_date)
    count = max(1, int(pack_count or 1))
    np_.per_unit = round(raw / count, 4)          # فكّ العبوات المتعددة
    if pack_kg:
        np_.per_kg = round(np_.per_unit / float(pack_kg), 4)
        lit, note_l = convert_amount(float(pack_kg), "kg", "litre", category)
        if lit:
            np_.per_litre = round(np_.per_unit / lit, 4)
        else:
            np_.gaps.append(note_l)  # لا فجوة صامتة — نفس عقد فرع اللتر
    elif pack_litre:
        np_.per_litre = round(np_.per_unit / float(pack_litre), 4)
        kg, note_k = convert_amount(float(pack_litre), "litre", "kg", category)
        if kg:
            np_.per_kg = round(np_.per_unit / kg, 4)
        else:
            np_.gaps.append(note_k)
    else:
        np_.gaps.append("حجم العبوة (كجم أو لتر) غير متاح — السعر/كجم "
                        "والسعر/لتر غير محسوبَين، لا تخمين")
    if fx_rate:
        np_.value_usd = round(np_.per_unit / float(fx_rate), 4) \
            if currency and currency.upper() != "USD" else np_.per_unit
    elif currency and currency.upper() == "USD":
        np_.value_usd = np_.per_unit
    else:
        np_.gaps.append("سعر الصرف غير متاح — القيمة بالدولار غير محسوبة")
    return np_


# ── سلسلة التكلفة الواصلة المُعلمَنة + الشلال + الحل العكسي (§5.4) ──────────

# سيناريوهات المعالم المعلنة عند غياب الرصد (قرار مالك: جدول معلن لا افتراض
# واحد مخفي). القيم **معالم افتراض قابلة للتعديل** لا حقائق مرصودة — تُعرض
# دائماً بوسم «معلمة معلنة».
PARAMETER_SCENARIOS = {
    "freight_pct_of_exw": {"منخفض": 5.0, "متوسط": 12.0, "مرتفع": 25.0},
    "distributor_margin_pct": {"منخفض": 10.0, "متوسط": 20.0, "مرتفع": 30.0},
    "retailer_margin_pct": {"منخفض": 15.0, "متوسط": 25.0, "مرتفع": 40.0},
}
PARAM_TAG = "معلمة معلنة قابلة للتعديل"


def _item(name: str, value, is_parameter: bool, note: str) -> dict:
    return {"name": name, "value": value, "is_parameter": is_parameter,
            "note": (f"{PARAM_TAG} — {note}" if is_parameter else note)}


def margin_waterfall(exw: float, *, freight, tariff_pct, vat_pct,
                     distributor_margin_pct, retailer_margin_pct,
                     currency: str = "USD") -> list[dict]:
    """شلال الهوامش: من سعر المصنع حتى سعر الرف — كل مرحلة سطر بقيمته
    وملاحظته؛ المدخل None = يُحسب بالسيناريو المتوسط ويُوسم معلمة."""
    def p(val, key):
        return (float(val), False) if val is not None else \
            (PARAMETER_SCENARIOS[key]["متوسط"], True)

    fr_pct, fr_param = p(freight, "freight_pct_of_exw")
    dist, dist_param = p(distributor_margin_pct, "distributor_margin_pct")
    ret, ret_param = p(retailer_margin_pct, "retailer_margin_pct")
    t = float(tariff_pct) if tariff_pct is not None else 0.0
    v = float(vat_pct) if vat_pct is not None else 0.0
    freight_val = exw * fr_pct / 100.0
    landed = landed_cost(exw, freight_val, tariff_pct)
    wholesale = landed * (1 + dist / 100.0)
    retail_net = wholesale * (1 + ret / 100.0)
    shelf = retail_net * (1 + v / 100.0)
    rows = [
        _item("سعر المصنع (EXW)", round(exw, 3), False, currency),
        _item(f"الشحن ({fr_pct:.0f}% من EXW)", round(freight_val, 3),
              fr_param, "من سيناريو الشحن" if fr_param else "مرصود"),
        _item(f"التكلفة الواصلة (بعد تعرفة {t:.1f}%)", round(landed, 3),
              tariff_pct is None,
              "التعرفة غير متاحة — بلا جمارك" if tariff_pct is None
              else "التعرفة مرصودة"),
        _item(f"سعر الموزّع (+{dist:.0f}%)", round(wholesale, 3), dist_param,
              "هامش الموزّع"),
        _item(f"سعر التجزئة قبل الضريبة (+{ret:.0f}%)", round(retail_net, 3),
              ret_param, "هامش التجزئة"),
        _item(f"سعر الرف (+ضريبة {v:.1f}%)", round(shelf, 3),
              vat_pct is None, "الضريبة غير متاحة — صفر معلن"
              if vat_pct is None else "الضريبة مرصودة"),
    ]
    return rows


def reverse_solve_max_exw(shelf_price: float, *, tariff_pct, vat_pct,
                          freight_pct_of_exw=None, distributor_margin_pct=None,
                          retailer_margin_pct=None) -> dict:
    """الحل العكسي (§5.4 — أهم رقم في الدراسة): من سعر الرف المنافس المرصود،
    أقصى سعر مصنع (EXW) يسمح بمجاراته. المجهول = جدول سيناريوهات معلن
    {منخفض/متوسط/مرتفع} — «إعلان استحالة التسعير ليس مخرجاً مقبولاً».

    الجبر: shelf = EXW×(1+fr)×(1+t)×(1+dist)×(1+ret)×(1+vat)
    ⇒ EXW_max = shelf ÷ [(1+fr)(1+t)(1+dist)(1+ret)(1+vat)]
    """
    t = float(tariff_pct) / 100.0 if tariff_pct is not None else 0.0
    v = float(vat_pct) / 100.0 if vat_pct is not None else 0.0
    params: list[str] = []
    if tariff_pct is None:
        params.append("التعرفة (اعتُمد 0% — قيمتها الفعلية غير متاحة)")
    if vat_pct is None:
        params.append("الضريبة (اعتُمد 0% — قيمتها الفعلية غير متاحة)")

    def solve(fr_pct: float, dist_pct: float, ret_pct: float) -> float:
        denom = ((1 + fr_pct / 100.0) * (1 + t) * (1 + dist_pct / 100.0)
                 * (1 + ret_pct / 100.0) * (1 + v))
        return round(float(shelf_price) / denom, 4)

    fixed_fr = freight_pct_of_exw
    fixed_dist = distributor_margin_pct
    fixed_ret = retailer_margin_pct
    scenario_needed = any(x is None for x in (fixed_fr, fixed_dist, fixed_ret))
    scenarios = []
    for label in ("منخفض", "متوسط", "مرتفع"):
        fr = fixed_fr if fixed_fr is not None \
            else PARAMETER_SCENARIOS["freight_pct_of_exw"][label]
        di = fixed_dist if fixed_dist is not None \
            else PARAMETER_SCENARIOS["distributor_margin_pct"][label]
        re_ = fixed_ret if fixed_ret is not None \
            else PARAMETER_SCENARIOS["retailer_margin_pct"][label]
        scenarios.append({"scenario": label, "freight_pct": fr,
                          "distributor_pct": di, "retailer_pct": re_,
                          "max_exw": solve(fr, di, re_)})
    for name, val in (("نسبة الشحن", fixed_fr),
                      ("هامش الموزّع", fixed_dist),
                      ("هامش التجزئة", fixed_ret)):
        if val is None:
            params.append(f"{name} ({PARAM_TAG})")
    return {
        "shelf_price": float(shelf_price),
        "formula": ("EXW_max = سعر الرف ÷ [(1+شحن)(1+تعرفة)(1+هامش الموزّع)"
                    "(1+هامش التجزئة)(1+ضريبة)]"),
        "max_exw": scenarios[1]["max_exw"] if scenario_needed
        else solve(fixed_fr, fixed_dist, fixed_ret),
        "headline_scenario": "متوسط" if scenario_needed else "مرصود",
        "scenarios": scenarios if scenario_needed else [],
        "parameters": params,
    }


# ── بناء قسم الاقتصاد من نتائج البعثات · the view assembler ────────────────

_TARIFF_WORDS = ("تعرفة", "التعرفة", "رسوم جمركية", "جمرك", "tariff", "duty")
# ── الصنف ١٢: «غير متاح» وهو مرصود · one recognition vocabulary ────────────
# **العيبُ المرصود:** بعثةُ التعريفات تُعيد «التعريفة المطبَّقة % HS…» —
# وهي **الصيغةُ الحرفية** التي يكتبها مزوّدُ WTO في هذا الريبو
# (`silk_wto_tariff.py:149`) — فلا تُقرَأ هنا لأنّ القائمة تعرف «تعرفة»
# وحدَها، فيُعتمَد **٠٪ جمارك** في الحل العكسي ويُعلَن «التعرفة غير متاحة».
# أثرُه رقميّ لا لغويّ: أقصى سعرِ مصنعٍ منافسٍ مُبالَغٌ بمقدار التعريفة
# كلِّها، أي أنّ التقرير يُبلِغ المصدّرَ أنه يقدر على تكلفةٍ لا يقدر عليها.
# و`silk_gap_recovery.py:691` يقبل الإملاءَين معاً أصلاً — فالتباعدُ داخليّ
# لا افتراضيّ.
_TARIFF_WORDS_EXTRA = ("تعريفة", "التعريفة", "التعريفات",
                       "الرسوم الجمركية", "customs duty", "applied tariff")

RECOGNITION_VOCABULARY_FLAG = "SILK_RECOGNITION_VOCABULARY"


def recognition_vocabulary() -> bool:
    """هل رايةُ الصنف ١٢ مفعّلة؟ — نمطُ الرايات القائم."""
    import os
    return os.environ.get(RECOGNITION_VOCABULARY_FLAG,
                          "").strip().lower() in ("1", "true", "yes")


#: مفتاحُ قياسٍ لأداة `tools/consistency_audit.py` وحدَها: يعيد قارئَ التعرفة
#: إلى مساره الضيّق (سلوكُ ما قبل الدرس ٢٦٢) كي يُقاس عمودُ «قبل» بالتشغيل
#: لا بالادّعاء. **لا يُضبَط في الإنتاج إطلاقاً** — غيابُه هو الافتراض.
LEDGER_OFF_FLAG = "SILK_FACT_LEDGER_OFF"


def ledger_reader_off() -> bool:
    import os
    return os.environ.get(LEDGER_OFF_FLAG, "").strip().lower() in (
        "1", "true", "yes", "on")


def tariff_words() -> tuple:
    """مفرداتُ التعرّف على التعريفة — **الموسَّعةُ دائماً** بعد الدرس ٢٦٢.

    كانت الموسَّعةُ خلف راية، فيُعتمَد ٠٪ حيث لم تُقرَأ التعريفة ويُعلَن
    «غير متاحة» بينما القسمُ التنظيميّ يطبعها (بلاغ التقرير 6). الرايةُ
    تبقى مقبولةً بلا أثرٍ إضافيّ، ومفتاحُ القياس وحدَه يعيد المسارَ الضيّق.
    """
    if ledger_reader_off() and not recognition_vocabulary():
        return _TARIFF_WORDS
    return _TARIFF_WORDS + _TARIFF_WORDS_EXTRA


def currency_in_note(note: object) -> str:
    """عملةُ الملاحظة — من المصدر الواحد (`silk_narrative.currency_in`) حين
    تكون الرايةُ مفعّلة، وبالنمط الضيّق القائم حرفياً بدونها."""
    if recognition_vocabulary():
        import silk_narrative
        return silk_narrative.currency_in(note)
    m = _CURRENCY_RE.search(str(note or ""))
    return m.group(1) if m else ""
_VAT_WORDS = ("ضريبة القيمة المضافة", "ضريبة", "VAT")
_HHI_WORDS = ("HHI", "هيرفندال", "تركّز")
# بنود بعثة الأسعار التي ليست أسعاراً (عدّادات/نِسَب/مؤشرات) — تُستبعد من
# مرساة السعر كي لا يصبح «عدد المتاجر 3» هو سعر الرف (مراجعة §58).
_NON_PRICE_WORDS = ("عدد", "نسبة", "٪", "%", "HHI", "تركّز", "مؤشر",
                    "تقييم", "count", "share")

import re as _re
_PACK_RE = _re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(كجم|كغم|كغ|جم|غرام|غ|لتر|مل|kg|g(?![a-z])|l(?![a-z])|ml)",
    _re.IGNORECASE)
# البند 6 (مراجعة §58): «دولار/يورو/ريال/جنيه» تلتقطها شبكة الأسعار
# `_PRICE_IN_TEXT_RE` كعملات إلصاق — غيابها هنا كان يجعل سعراً رُصد
# **بسبب** عملته يفقدها في المرساة فيُعلَّق الحل العكسي بلا داعٍ.
_CURRENCY_RE = _re.compile(r"(€|\$|£|ر\.س|درهم|دينار|يورو|دولار|ريال|جنيه"
                           r"|EUR|USD|GBP|SAR|AED|JOD)")
_PACK_TO_KG = {"كجم": 1.0, "كغم": 1.0, "كغ": 1.0, "kg": 1.0,
               "جم": 0.001, "غرام": 0.001, "غ": 0.001, "g": 0.001}
_PACK_TO_L = {"لتر": 1.0, "l": 1.0, "مل": 0.001, "ml": 0.001}


def _findings_of(mission) -> list:
    """نتائج بعثة بأي شكل — dict مُخزَّن أو AgentReport حيّ (مراجعة §58:
    الشكل الحيّ كان يكسر economics_view فيختفي القسم من التشغيلات الطازجة)."""
    if isinstance(mission, dict):
        return mission.get("findings") or []
    return getattr(mission, "findings", None) or []


def _fv(f) -> object:
    return f.get("value") if isinstance(f, dict) else getattr(f, "value", None)


def _fsource(f) -> str:
    """مصدرُ الاكتشاف — dict أو `DataPoint` (نفس تسامح `_fv`/`_fnote`)."""
    if isinstance(f, dict):
        return str(f.get("source") or "")
    return str(getattr(f, "source", "") or "")


def _fnote(f) -> str:
    return str((f.get("note") if isinstance(f, dict)
                else getattr(f, "note", "")) or "")


_NUM_NEAR_RE = _re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def _num_to_float_eu(tok: str):
    """رقمٌ من رمزٍ نصّيّ (آلافٌ مقابل عشريّ أوروبيّ) — المُميِّزُ **الواحد** في
    `silk_deep_pillars._num_to_float` كي لا يتباعد استخراجان لنفسِ العرف
    (مراجعة §58، إعادة مراجعة: كان مُكرَّراً في وحدتين). استيرادٌ كسولٌ فيبقى
    استيرادُ الوحدةِ خفيفاً بلا تبعيةٍ ثابتة."""
    from silk_deep_pillars import _num_to_float
    return _num_to_float(tok)


def _mission_numeric(dr: dict, mission_key: str, words: tuple,
                     lo: float, hi: float):
    """أول قيمة رقمية ضمن مدى معقول تحمل ملاحظتها إحدى الكلمات — أو None.

    **الموجة C (البند E-05).** كان `float(val)` وحدَه، والبعثاتُ على المسار
    العميق تُعيد **جملاً** — فلا يتكوّن HHI أبداً، وتصير بوّابةُ الإزاحة
    «غيرَ مطلوبة» صامتةً على كلّ دراسة. الآن يُقرأ الرقمُ من النثر أيضاً
    **حتمياً**: أوّل رقمٍ ضمن المدى المعقول في نصٍّ تحمل كلمتَه المفتاحية.
    المدى نفسُه هو الحارس — «٣ منافسين» لا تمرّ مدىً بين ٠ و١٠٠٠٠ لأنها لا
    تحمل كلمةَ HHI، و«٢٣٥٠» تمرّ لأنها تحملها.
    """
    for f in _findings_of((dr.get("missions") or {}).get(mission_key)):
        val, note = _fv(f), _fnote(f)
        if isinstance(val, bool):
            continue
        blob = f"{note} {val if isinstance(val, str) else ''}"
        if not any(w in blob for w in words):
            continue
        try:
            fv = float(val)
        except (TypeError, ValueError):
            fv = None
            for m in _NUM_NEAR_RE.finditer(str(val or "")):
                # الفاصلةُ فاصلُ آلافٍ لا عشريّ (عرفُ الريبو) **مع تمييز
                # الفاصلةِ العشريّةِ الأوروبية**: «2,350»→2350، لكنّ «2,35»→2.35
                # فلا يُضخَّم رقمٌ أوروبيّ ١٠٠ ضعف (مراجعة §58).
                cand = _num_to_float_eu(m.group(1))
                if cand is not None and lo <= cand <= hi:
                    fv = cand
                    break
        if fv is not None and lo <= fv <= hi:
            return fv, note
    return None, ""


def _parse_pack_from_note(note: str) -> tuple:
    """(pack_kg, pack_litre) من نص الملاحظة إن حمل حجم عبوة — وإلا (None, None)."""
    m = _PACK_RE.search(note or "")
    if not m:
        return None, None
    try:
        qty = float(m.group(1).replace(",", "."))
    except ValueError:
        return None, None
    unit = m.group(2).lower()
    if unit in _PACK_TO_KG:
        return qty * _PACK_TO_KG[unit], None
    if unit in _PACK_TO_L:
        return None, qty * _PACK_TO_L[unit]
    return None, None


# ── مستوى السعر · price level (الموجة C، البندان E-01 وE-09) ───────────────
#
# **الحادثة:** المرساةُ كانت **أدنى** قيمةٍ رقمية في بعثة الأسعار، و`basis`
# مُرمَّزاً `"retail"` صلباً. فقيمةُ استيرادٍ عند الحدود (CIF) — وهي بطبيعتها
# أدنى من سعر الرفّ بأضعاف — تُوسَم «أدنى سعر رفّ منافس مرصود» ويُبنى عليها
# الحلُّ العكسيّ كلُّه. والأثرُ **تفاؤلٌ منهجيّ في اتجاهٍ واحد**: كلُّ هامشٍ
# لاحقٍ أكبرُ من الحقيقة، لأنّ المقام أصغرُ ممّا يجب.
#
# القاعدة: **لا مرساةَ رفٍّ إلا من صفٍّ مستواه `retail` مُصرَّحٌ به.** ومستوىً
# لا يُكتشَف ليس `retail` افتراضاً — هو **مجهول**، والمجهولُ لا يُرسي حساباً.
_PRICE_LEVEL_MARKERS = (
    # (المستوى، إبرٌ عربية وإنجليزية — أخصُّها أوّلاً)
    ("EXW", ("تسليم المصنع", "من المصنع", "ex-works", "ex works", "exw")),
    ("FOB", ("تسليم ظهر السفينة", "فوب", "f.o.b", "fob")),
    ("CIF", ("عند الحدود", "قيمة الاستيراد", "سعر الاستيراد", "الكلفة والتأمين",
             "سيف", "c.i.f", "cif", "landed", "customs value", "import value",
             "import price")),
    ("wholesale", ("بالجملة", "سعر الجملة", "الجملة", "wholesale", "bulk price")),
    ("retail", ("سعر الرف", "سعر الرفّ", "سعر رف", "سعر رفّ",
                "على الرف", "على الرفّ", "التجزئة",
                "بالتجزئة", "للمستهلك", "سوبرماركت", "متجر", "بقالة",
                "shelf price", "retail price", "retail", "consumer price",
                "supermarket", "store", "shop")),
)

# **المستوى بحكم المصدر.** الملاحظةُ ليست القناةَ الوحيدة: سعرٌ جاء من قائمة
# متجرٍ على الخرائط هو سعرُ تجزئةٍ **بحكم بنائه**، وإن لم تقل الملاحظةُ ذلك
# (تُسمّي المتجرَ فقط: «Albert Heijn»). هذه خاصّيةٌ موثَّقةٌ للجامع لا افتراض.
# وتبقى الإبرةُ الصريحة **أقوى**: ملاحظةٌ تقول «عند الحدود» تُقرأ CIF ولو جاءت
# من الخرائط — فالعطلُ الأصليّ (سعرُ حدودٍ يُتبنّى رفّاً) يبقى مسدوداً.
_RETAIL_BY_SOURCE = ("google maps", "maps", "serper", "local price",
                     "localprice", "متجر", "خرائط")


# ── استخراجُ سعرٍ من نصٍّ نثريّ (الموجة C، البند E-02) ────────────────────
#
# **الحادثة:** `float(finding["value"])` ينجح على قيمةٍ رقمية فقط، وبعثةُ
# الأسعار على المسار العميق تُعيد **جملاً** («سعر رف عبوة ١ كجم في ألبرت هاين
# 7.49 يورو»). فلا مرساة ⇒ لا حلَّ عكسيّ ⇒ **لا قسمَ اقتصادٍ إطلاقاً** على
# مسار المصنع، مهما رصدت البعثةُ من أسعارٍ حقيقية.
#
# القيدُ الحاكم: الاستخراجُ **حتميٌّ بلا نموذج**، ويرفض ما لا يقين فيه. رقمٌ
# ملتصقٌ بعملةٍ أو بوحدةِ عبوةٍ سعرٌ؛ ورقمٌ عائمٌ في الجملة قد يكون سنةً أو
# نسبةً أو عدداً — فيُترَك. **مدىً** («بين ٦ و٩») يُؤخَذ **حدُّه الأدنى**:
# أقسى قيدٍ للدخول هو القاعدة القائمة في هذه الطبقة.
# **المدى أوّلاً.** «بين ٦ و٩ يورو»: الحدُّ الأدنى غيرُ ملتصقٍ بعملة، فقاعدةُ
# الالتصاق وحدَها كانت تلتقط ٩ فقط — أي **الحدَّ الأعلى**، وهو الاتجاه
# المتفائل بالضبط الذي تعالجه هذه الموجة (مرساةٌ أعلى ⇒ هامشٌ أكبر من الحقيقة).
# فالمدى يُلتقَط كوحدةٍ واحدة ويُؤخَذ طرفاه، ثمّ يفوز أدناهما.
_PRICE_RANGE_RE = _re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:و|–|—|-|إلى|الى|to)\s*"
    r"(\d+(?:[.,]\d+)?)\s*(?:€|\$|£|ر\.س|درهم|دينار|يورو|دولار|جنيه|ريال|"
    r"EUR|USD|GBP|SAR|AED|JOD)")

_PRICE_IN_TEXT_RE = _re.compile(
    r"(?:(€|\$|£)\s*(\d+(?:[.,]\d+)?))"                      # €7.49
    r"|(?:(\d+(?:[.,]\d+)?)\s*(€|\$|£|ر\.س|درهم|دينار|يورو|دولار|"
    r"جنيه|ريال|EUR|USD|GBP|SAR|AED|JOD))"                    # 7.49 يورو
)
# سنواتٌ ونسبٌ لا تكون أسعاراً حتى لو لامست عملةً في جملةٍ مزدحمة.
_YEARISH_RE = _re.compile(r"\b(19|20)\d{2}\b")


def price_numbers_in_text(text: object) -> list:
    """أرقامُ الأسعار في نصٍّ نثريّ — حتميّاً، أو قائمةٌ فارغة.

    لا يُؤخَذ رقمٌ إلا إن كان **ملتصقاً بعملة**. الرقمُ العائم متروكٌ عمداً:
    «٣ متاجر» و«٢٠٢٤» و«١٥٪» كلُّها أرقامٌ في جملة أسعار، وأخذُها سعراً هو
    نفسُ عائلة العطل التي منعها حارسُ `_NON_PRICE_WORDS`.
    """
    raw = str(text or "")
    if not raw:
        return []
    out: list = []
    for rm in _PRICE_RANGE_RE.finditer(raw):
        for grp in (rm.group(1), rm.group(2)):
            try:
                v = float(str(grp).replace(",", "."))
            except (TypeError, ValueError):
                continue
            if v > 0 and not _YEARISH_RE.search(str(grp)):
                out.append(v)
    for m in _PRICE_IN_TEXT_RE.finditer(raw):
        num = m.group(2) or m.group(3)
        if not num:
            continue
        # رقمٌ يقع داخل سنةٍ («في 2024 يورو» لا معنى لها، لكن «2024» قد
        # تلتصق بعملةٍ في نصٍّ مشوّش) — يُترَك.
        span = raw[max(0, m.start() - 6):m.end() + 6]
        if _YEARISH_RE.search(num):
            continue
        if "٪" in span or "%" in span:
            continue
        try:
            val = float(str(num).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if val > 0:
            out.append(val)
    return out


def detect_price_level(note: object, source: object = "") -> "str | None":
    """استنتِج مستوى السعر من ملاحظته ثمّ من مصدره — أو `None`. حتميٌّ بلا نموذج.

    الترتيب مقصود: **الإبرةُ الصريحة في الملاحظة تسبق خاصّيةَ المصدر**، فسعرٌ
    من الخرائط ملاحظتُه «قيمة الاستيراد عند الحدود» يُقرأ CIF لا تجزئة —
    وهو العطلُ الأصليّ الذي يجب أن يبقى مسدوداً.

    `None` تعني **مجهول** لا «تجزئة»: افتراضُ التجزئة عند الجهل هو بعينه
    ما أنتج التفاؤل المنهجيّ. المجهولُ يُعلَن ولا يُرسي.
    """
    text = str(note or "").lower()
    for level, needles in _PRICE_LEVEL_MARKERS:
        if any(n in text for n in needles):
            return level
    src = str(source or "").lower()
    if src and any(n in src for n in _RETAIL_BY_SOURCE):
        return "retail"
    return None


PRICE_LEVEL_AR = {"retail": "سعر تجزئة (رفّ)", "wholesale": "سعر جملة",
                  "CIF": "سعر عند الحدود", "FOB": "سعر تسليم ظهر السفينة",
                  "EXW": "سعر تسليم المصنع"}
PRICE_LEVEL_EN = {"retail": "retail (shelf) price", "wholesale": "wholesale price",
                  "CIF": "border (CIF) price", "FOB": "FOB price",
                  "EXW": "ex-works price"}


# ═══════════ هدف الدراسة الاحترافية (البند ٧) — تقدير المستمرّ ═══════════
#
# **الحد الصارم:** يُقدَّر المستمرّ (كلفة، حجم، مسافة، هامش) ولا يُقدَّر
# الحدّي/التعاقدي أبداً (تعرفة جمركية، إذن تنظيمي، هوية موزّع، شرط عقد) —
# التاجر يُحاسَب على العمود الثاني كحقائق نعم/لا، وخطؤها بثقة أسوأ من
# إعلان الفجوة. لا دالة تقدير لأي بند حدّي في هذه الوحدة (قفل بنيوي في
# الاختبارات). كل تقدير يحمل حقوله الأربعة معاً: القيمة، طريقة الاشتقاق،
# المدى وعرضه، وسبيل التأكيد ومدته — ومدى أوسع من ±50% يُعلن «أوسع من أن
# يُتصرف به» ولا يُطبع رقماً، ولا يُبنى رقم ثالث على تقديرين واسعين.
#
# ثوابت الحاويات: مواصفات منشورة (مسترجعة 2026-08-26) —
# 40ft dry: أقصى إجمالي ISO ‏30,480 كجم ⇒ حمولة ≈26,730 كجم، ٦٧ م³
#   (icontainers.com/help/40-foot-container)؛
# 40ft HC reefer: حمولة 25,526–28,180 كجم، ≈59.8 م³
#   (tracecontainer.com/container-types/reefer-container)؛
# 20ft reefer: حمولة ≈20,756 كجم (المصدر نفسه).
CONTAINER_SPECS = {
    "40ft_dry": {"payload_kg": (26_730.0, 26_730.0),
                 "source": "icontainers.com — ISO max gross 30,480 kg"},
    "40ft_reefer": {"payload_kg": (25_526.0, 28_180.0),
                    "source": "tracecontainer.com — 40ft HC reefer spec"},
    "20ft_reefer": {"payload_kg": (20_756.0, 20_756.0),
                    "source": "tracecontainer.com — 20ft reefer spec"},
}
ESTIMATE_TAG = "تقدير معلن بمدى"
TOO_WIDE_PCT = 50.0
TOO_WIDE_NOTE = ("المدى أوسع من ±50% — أوسع من أن يُتصرف به؛ يُعلن بدل "
                 "أن يُطبع رقماً")


def _round_clean(x: float) -> "int | float":
    """تقريب عرضٍ نظيف: منزلتان، والعدد الصحيح بلا «.0» (26730 لا 26730.0)."""
    r = round(float(x), 2)
    return int(r) if float(r).is_integer() else r


def _mk_estimate(name: str, low: float, high: float, method: str,
                 confirm: str, confirm_time: str, unit: str = "",
                 inputs: "list | None" = None,
                 unknown: "list | None" = None) -> dict:
    """تقدير بحقوله الأربعة — أو إعلان «أوسع من أن يُتصرف به» فوق ±50%.

    الصنف ٩ (خلف `SILK_DERIVED_PROVENANCE`): `inputs` مدخلاتُ المعادلة، كلٌّ
    `{name, source, assumed}`؛ و`unknown` المكوّناتُ المستبعَدةُ من الجمع
    بأسمائها. بلا الراية **لا يُضاف الحقلان** فيبقى البند حرفياً كما كان
    (قرار المالك: لا تغييرَ سلوكٍ بلا راية)."""
    mid = (low + high) / 2.0
    width = abs(high - low) / 2.0 / mid * 100.0 if mid else 0.0
    width = round(width, 1)
    est = {"name": name, "tier": "estimated", "tag": ESTIMATE_TAG,
           "unit": unit, "method": method,
           "range": {"low": _round_clean(low), "high": _round_clean(high)},
           "width_pct": int(width) if width.is_integer() else width,
           "confirm": confirm, "confirm_time": confirm_time,
           "too_wide": width > TOO_WIDE_PCT}
    if est["too_wide"]:
        est["value"] = None
        est["note"] = TOO_WIDE_NOTE
    else:
        est["value"] = _round_clean(mid)
    if inputs or unknown:
        import silk_narrative
        if silk_narrative.derived_provenance_enabled():
            if inputs:
                est["inputs"] = [i for i in inputs if i]
            if unknown:
                est["unknown"] = [str(u) for u in unknown if str(u).strip()]
    return est


def _perishable(category: str) -> bool:
    """مبرّد أم جاف؟ — السوائل الغذائية المسجّلة تُشحن مبرّدة (قاعدة
    تشغيلية محافظة)؛ غيرها جاف. تقريب معلن لا حقيقة تعاقدية."""
    return market_unit(category)[0] == "litre"


def estimate_trial_shipment(category: str, unit_kg: float | None = None
                            ) -> "dict | None":
    """حجم الشحنة التجريبية = حاوية واحدة (سعة منشورة ÷ وزن وحدة السوق).

    وزن الوحدة: كجم مباشرة للمواد الصلبة، ومن ثابت الكثافة المسجّل للتر —
    فئة بلا ثابت ولا وزن وحدة = None معلن (لا تخمين)."""
    mu_code, mu_ar = market_unit(category)
    if unit_kg is None:
        if mu_code == "litre":
            unit_kg, _ = convert_amount(1.0, "litre", "kg", category)
        elif mu_code == "kg":
            unit_kg = 1.0
    if not unit_kg:
        return None
    spec = CONTAINER_SPECS["40ft_reefer" if _perishable(category)
                           else "40ft_dry"]
    lo, hi = spec["payload_kg"]
    est = _mk_estimate(
        "حجم الشحنة التجريبية",
        lo / unit_kg, hi / unit_kg,
        f"حمولة حاوية 40 قدماً المنشورة ÷ وزن "
        f"{mu_ar} الواحد ({unit_kg:g} كجم)",
        "عرض أسعار رسمي من خط ملاحي/وكيل شحن للحاوية والممر المحددين",
        "3–5 أيام عمل", unit=mu_ar,
        inputs=[{"name": "حمولة حاوية 40 قدماً", "source": spec["source"],
                 "source_client": "مواصفة حمولة الحاوية المنشورة"},
                {"name": f"وزن {mu_ar} الواحد ({unit_kg:g} كجم)",
                 "source": "ثابت كثافة الفئة المسجّل" if mu_code == "litre"
                           else "وحدة السوق كجم (بلا تحويل)"}])
    # الاستشهاد الخام (لاتيني) حقلٌ منفصل: أسطح المشغّل تعرضه، وسطح
    # العميل يبقى بلغة الزائر (سياسة «لا مصدر خام على سطح العميل»، موجة ٣).
    est["source"] = spec["source"]
    return est


def _lane_rate(market_iso3: str, reefer: bool) -> "tuple | None":
    """سطر ممر شحن متحقق من `data/freight_lanes_l1.csv` — الملف يُشحن
    فارغاً (عقد golden_cases: لا صف بلا رقم متحقق بمصدره وتاريخه) ويملؤه
    المالك/البعثات الحية؛ غيابه = مسار السيناريو المعلن."""
    import csv
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "freight_lanes_l1.csv")
    try:
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("lane", "")).upper().endswith(
                        str(market_iso3 or "").upper()) \
                        and (("reefer" in str(row.get("container", "")))
                             == reefer):
                    return (float(row["rate_low_usd"]),
                            float(row["rate_high_usd"]),
                            row.get("source_url", ""))
    except (OSError, ValueError, KeyError):
        return None
    return None


def estimate_freight_per_unit(category: str, exw_per_unit: float | None,
                              market_iso3: str = "",
                              trial: dict | None = None) -> "dict | None":
    """شحن الوحدة: سطر ممر متحقق إن وُجد (÷ وحدات الحاوية)، وإلا نسب
    السيناريو المعلنة (منخفض 5% – مرتفع 25% من EXW) — يتطلب تكلفة الوحدة؛
    غيابها = None معلن (لا رقم شحن فوق تكلفة مجهولة).

    `trial`: تقدير الشحنة التجريبية المحسوب سلفاً — يمرَّر من
    `build_decision_numbers` فلا يُحسب مرتين (مراجعة §58: نسختان من نفس
    الحساب قد تتباعدان)."""
    if trial is None:
        trial = estimate_trial_shipment(category)
    lane = _lane_rate(market_iso3, _perishable(category))
    if lane and trial and not trial["too_wide"]:
        lo_rate, hi_rate, src = lane
        units_hi = trial["range"]["high"] or 1
        units_lo = trial["range"]["low"] or 1
        est = _mk_estimate(
            "كلفة الشحن للوحدة", lo_rate / units_hi, hi_rate / units_lo,
            "سعر ممر منشور متحقق ÷ وحدات الحاوية",
            "عرض أسعار رسمي للممر نفسه", "3–5 أيام عمل",
            unit=f"دولار/{market_unit(category)[1]}")
        est["source"] = src
        return est
    if exw_per_unit is None or exw_per_unit <= 0:
        return None
    lo = exw_per_unit * PARAMETER_SCENARIOS["freight_pct_of_exw"]["منخفض"] / 100
    hi = exw_per_unit * PARAMETER_SCENARIOS["freight_pct_of_exw"]["مرتفع"] / 100
    return _mk_estimate(
        "كلفة الشحن للوحدة", lo, hi,
        "نسب سيناريو الشحن المعلنة (5%–25% من تكلفة المصنع) — "
        f"{PARAM_TAG}",
        "عرض أسعار رسمي من وكيل شحن للممر والحاوية المحددين",
        "3–5 أيام عمل", unit=f"لكل {market_unit(category)[1]}")


def _unit_cur(cost_currency: str) -> str:
    """وحدةُ المبلغ المشتقّ — رمزُ ISO حين يُعرَف (الصنف ٩، خلف رايته).

    «8,900 بعملة تكلفتك» مبلغٌ غيرُ قابلٍ للتدقيق؛ و«8,900 SAR» يُدقَّق.
    عملةٌ لا يُعرَف رمزُها تبقى بنصّها كما صرّح به المالك (لا تخمينَ رمز)،
    وغيابُ التصريح يبقى معلَناً بالعبارة القائمة نفسها.
    """
    import silk_narrative
    cur = (cost_currency or "").strip()
    if not cur:
        return "بعملة تكلفتك"
    if not silk_narrative.derived_provenance_enabled():
        return cur
    return silk_narrative.iso_currency(cur) or cur


def build_decision_numbers(*, category: str, market_iso3: str = "",
                           cost_per_unit: float | None = None,
                           cost_currency: str = "",
                           monthly_capacity: float | None = None,
                           reverse: dict | None = None,
                           cert_fee_range: "tuple | None" = None
                           ) -> list[dict]:
    """الأرقام الخمسة لقسم «أرقام القرار» — حتمياً (نمط Z-01: الكاتب يشرح
    ولا يحسب). كل بند إما تقدير بحقوله الأربعة وإما فجوة بحقولها الثلاثة
    (المعطى الناقص/أثره/سبيل الإغلاق) — لا خانة صامتة ولا رقم مختلَق،
    ولا يُبنى بند على تقديرين واسعين (يُعلن بدل أن يُركَّب)."""
    mu_ar = market_unit(category)[1]
    out: list[dict] = []

    trial = estimate_trial_shipment(category)
    if trial:
        out.append(trial)
    else:
        out.append({"name": "حجم الشحنة التجريبية", "tier": "gap",
                    "missing": f"وزن {mu_ar} الواحد (أو ثابت كثافة الفئة)",
                    "impact": "لا يُعرف حجم أول شحنة فتبقى كلفة الدخول "
                              "كلها غير قابلة للحساب",
                    "closure": "أدخل وزن العبوة أو سجّل ثابت الفئة — "
                               "دقيقة واحدة"})

    freight = estimate_freight_per_unit(category, cost_per_unit,
                                    market_iso3, trial=trial)

    entry = None
    if cost_per_unit and trial and not trial["too_wide"]:
        goods_lo = cost_per_unit * trial["range"]["low"]
        goods_hi = cost_per_unit * trial["range"]["high"]
        # قاعدة عدم التراكب: شحنٌ واسع المدى (>±50% — حال مسار السيناريو
        # 5%–25% دوماً) لا يدخل المجموع صامتاً بصفر — يُستبعد ويُعلَن
        # استبعادُه نصاً في طريقة الاشتقاق (لا رقم ثالث فوق تقدير واسع).
        fr_known = bool(freight and not freight["too_wide"])
        fr_lo = freight["range"]["low"] * trial["range"]["low"] \
            if fr_known else 0.0
        fr_hi = freight["range"]["high"] * trial["range"]["high"] \
            if fr_known else 0.0
        fee_lo, fee_hi = cert_fee_range or (0.0, 0.0)
        entry = _mk_estimate(
            "كلفة الدخول الكلية حتى أول شحنة",
            goods_lo + fr_lo + fee_lo, goods_hi + fr_hi + fee_hi,
            "بضاعة الشحنة التجريبية (تكلفتك × وحدات الحاوية)"
            + (" + الشحن بسعر ممر متحقق" if fr_known else
               " (الشحن بلا سعر ممر متحقق — مداه أوسع من ±50% فيُستبعد "
               "من المجموع ويُغلق بعرض أسعار)")
            + (" + رسوم متحققة" if cert_fee_range else
               " (رسوم التسجيل غير متحققة — خارج المجموع ومعلنة)"),
            "عرض شحن رسمي + جدول رسوم الجهة التنظيمية للسوق",
            "أسبوع عمل", unit=_unit_cur(cost_currency),
            inputs=[
                {"name": "تكلفة إنتاج الوحدة لديك",
                 "source": "بطاقة المنتج التي أدخلتها"},
                {"name": "وحدات الشحنة التجريبية",
                 "source": "حمولة الحاوية المنشورة ÷ وزن الوحدة"}]
            + ([{"name": "كلفة الشحن للوحدة",
                 "source": ((freight or {}).get("source")
                            or "سعر ممر منشور متحقق"),
                 "source_client": "سعر ممر شحن منشور متحقق"}]
               if fr_known else [])
            + ([{"name": "رسوم التسجيل والاعتماد",
                 "source": "جدول رسوم الجهة التنظيمية للسوق"}]
               if cert_fee_range else []),
            unknown=([] if fr_known else
                     ["كلفة الشحن للوحدة (بلا سعر ممر متحقق — مداها أوسع "
                      "من ±50%)"])
            + ([] if cert_fee_range else
               ["رسوم التسجيل والاعتماد (غير متحققة)"]))
        out.append(entry)
    else:
        out.append({"name": "كلفة الدخول الكلية حتى أول شحنة",
                    "tier": "gap",
                    "missing": f"تكلفة إنتاج {mu_ar} الواحد لديك",
                    "impact": "بلا تكلفتك لا تُحسب كلفة الدخول ولا التعادل "
                              "ولا أقصى الخسارة",
                    "closure": "أدخلها في نموذج الدراسة — دقيقة واحدة، "
                               "رقمك أنت لا يُبحث عنه"})

    # مراجعة §58 (الإقفال): معادلة الهامش طرحٌ بين رقمين من مصدرين —
    # أقصى EXW بعملة السعر المرصود ووحدة أساسه، وتكلفة المصنع بعملة لم
    # يصرّح بها النموذج بعد. لا طرح عابر للعملة أو الوحدة: الوحدة تُحاذى
    # بثابت السجل المعلن (كجم→وحدة السوق) أو تُعلن فجوة؛ والعملتان يجب أن
    # تتطابقا نصاً (cost_currency من البطاقة) وإلا صارت نقطة التعادل فجوة
    # ثلاثية تسمّي العملة المطلوبة — لا رقم تعادل فوق افتراض صرف صامت.
    max_exw = None
    align_gap = ""      # سبب تعذّر المحاذاة (وحدة/عملة) — نصه يدخل الفجوة
    if isinstance(reverse, dict):
        try:
            max_exw = float(reverse.get("max_exw"))
        except (TypeError, ValueError):
            max_exw = None
    rs_unit = str((reverse or {}).get("unit") or "").strip()
    rs_cur = str((reverse or {}).get("currency") or "").strip()
    _cc = (cost_currency or "").strip()
    if max_exw is not None and rs_unit and rs_unit != mu_ar:
        # سعر مرجعي لكل كجم لسوق لترية: سعر/لتر = سعر/كجم × (كجم/اللتر).
        _f, _fn = convert_amount(1.0, "litre", "kg", category)
        if rs_unit == "كجم" and mu_ar == "لتر" and _f:
            max_exw = max_exw * _f
            rs_unit = mu_ar
        else:
            align_gap = (f"سعر السوق المرجعي مرصود لكل {rs_unit} "
                         f"وتكلفتك لكل {mu_ar} — لا ثابت تحويل مسجّل")
    if max_exw is not None and not align_gap:
        if not rs_cur:
            align_gap = "عملة السعر المرجعي غير مرصودة"
        elif not _cc:
            align_gap = (f"عملة تكلفتك غير مصرّح بها والسعر المرجعي "
                         f"بعملة {rs_cur}")
        elif _cc.upper() != rs_cur.upper():
            align_gap = (f"تكلفتك بعملة {_cc} والسعر المرجعي بعملة "
                         f"{rs_cur} — لا طرح بين عملتين بلا سعر صرف معلن")
    if cost_per_unit and max_exw and not align_gap and entry \
            and not entry["too_wide"]:
        margin = max_exw - cost_per_unit
        if margin > 0:
            lo = entry["range"]["low"] / margin
            hi = entry["range"]["high"] / margin
            be = _mk_estimate(
                "نقطة التعادل",
                lo, hi,
                "كلفة الدخول ÷ هامش الوحدة (أقصى سعر مصنع منافس − "
                "تكلفتك)",
                "تثبيت سعر بيع فعلي من أول مفاوضة مستورد",
                "مع أول عرض سعر جاد", unit=mu_ar,
                inputs=[
                    {"name": "كلفة الدخول الكلية حتى أول شحنة",
                     "source": "بند «كلفة الدخول» في هذا الجدول"},
                    {"name": "أقصى سعر مصنع قابل للمنافسة",
                     "source": "هوامشُ الشحن والتوزيع من معلمات السيناريو "
                               "المعلنة فوق أدنى سعر رف منافس مرصود",
                     "assumed": True},
                    {"name": "تكلفة إنتاج الوحدة لديك",
                     "source": "بطاقة المنتج التي أدخلتها"}],
                unknown=list(entry.get("unknown") or []))
            if monthly_capacity:
                be["months_at_capacity"] = {
                    "low": round(lo / monthly_capacity, 1),
                    "high": round(hi / monthly_capacity, 1)}
            out.append(be)
        else:
            out.append({"name": "نقطة التعادل", "tier": "gap",
                        "missing": "هامش موجب — تكلفتك أعلى من أقصى سعر "
                                   "مصنع منافس",
                        "impact": "لا تعادل ممكناً بالأسعار المرصودة: كل "
                                  "وحدة تُباع بخسارة",
                        "closure": "خفّض التكلفة أو استهدف شريحة سعرية "
                                   "أعلى — قرار إنتاج لا بحث"})
    elif align_gap and cost_per_unit and max_exw:
        out.append({"name": "نقطة التعادل", "tier": "gap",
                    "missing": align_gap,
                    "impact": "هامش الوحدة طرحٌ بين رقمين — لا يصح إلا "
                              "بوحدة وعملة واحدتين",
                    "closure": "أدخل تكلفتك بعملة السعر المرجعي نفسها "
                               "(أو صرّح بعملتها) — دقيقة واحدة"})
    else:
        out.append({"name": "نقطة التعادل", "tier": "gap",
                    "missing": "تكلفتك + سعر رف منافس مرصود"
                    if not cost_per_unit else "سعر رف منافس مرصود",
                    "impact": "معادلة التعادل = كلفة الدخول ÷ هامش الوحدة "
                              "— طرفها الناقص يعطّلها",
                    "closure": "أدخل التكلفة (دقيقة) وارصد سعر رف واحداً "
                               "(زيارة متجر/موقع — ساعة)"})

    out.append({"name": "الزمن من القرار إلى أول فاتورة", "tier": "gap",
                "missing": "مدد التسجيل والاعتماد الرسمية للسوق المستهدف",
                "impact": "لا يُجدول التدفق النقدي لأول صفقة",
                "closure": "جدول المدد المنشور لدى الجهة التنظيمية + "
                           "سؤال وكيل تخليص واحد — يوم عمل"})

    if entry and not entry["too_wide"]:
        ml = _mk_estimate(
            "أقصى خسارة إن فشل الدخول",
            entry["range"]["low"], entry["range"]["high"],
            "كلفة الدخول كلها عرضة للفقد في أسوأ حالة (بضاعة + شحن غير "
            "مستردّين)",
            "شرط إعادة/تصريف في أول عقد يقلّص السقف فعلياً",
            "بند تفاوضي في أول عقد", unit=_unit_cur(cost_currency),
            inputs=[{"name": "كلفة الدخول الكلية حتى أول شحنة",
                     "source": "بند «كلفة الدخول» في هذا الجدول"}],
            # الصنف ٩: سقفُ المخاطرة يَرِث **ناقصَ** كلفة الدخول بالاسم —
            # سقفٌ يُقرأ شاملاً وهو ناقصٌ أخطرُ من سقفٍ معلَنِ النقص.
            unknown=list(entry.get("unknown") or []))
        out.append(ml)
    else:
        out.append({"name": "أقصى خسارة إن فشل الدخول", "tier": "gap",
                    "missing": "كلفة الدخول (أعلاه)",
                    "impact": "سقف المخاطرة غير معروف قبل الالتزام",
                    "closure": "يكتمل تلقائياً بإدخال تكلفتك"})
    return out


def _tariff_from_ledger(dr: dict) -> tuple:
    """(القيمة، الملاحظة) من سجلّ الحقائق الواحد — أو (None, "") عند تعذّره.

    الدرس ٢٦٢: لا مسارَ استخراجٍ ثانٍ للتعرفة؛ السجلّ هو القارئ الوحيد.
    """
    try:
        import silk_fact_ledger as _FL
        e = (_FL.build_ledger({"deep_research": dr}).get("entries")
             or {}).get("tariff_applied_pct") or {}
    except Exception:  # noqa: BLE001 — السجلُّ إضافةٌ لا شرطُ حساب
        return None, ""
    if e.get("status") == _FL.MISSING:
        return None, ""
    return _num_or_none(e.get("value")), str(e.get("note") or "")


def _num_or_none(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def economics_view(dr: dict, product_card: dict | None = None,
                   category: str = "") -> dict:
    """قسم الاقتصاد الكامل (§5.4) من نتائج البعثات + بطاقة المنتج إن وُجدت.
    حتمي، صفر شبكة؛ كل ناقص معلمة معلنة أو فجوة مسماة — لا «تعذّر التسعير»."""
    missions = dr.get("missions") or {}
    gaps: list[str] = []

    # مرساة سعر الرف: أدنى سعر منافس مرصود من بعثة الأسعار (أقسى قيد للدخول).
    # يُستبعد كل ما ليس سعراً: البوليان، والعدّادات/النِسَب/المؤشرات
    # (مراجعة §58: «عدد المتاجر 3» كان يمكن أن يصبح مرساة السعر).
    prices = []
    for f in _findings_of(missions.get("pricing_scout")):
        val, note = _fv(f), _fnote(f)
        if isinstance(val, bool):
            continue
        # **الموجة C (E-02).** القيمةُ الرقمية أوّلاً (المسار القديم كما هو)،
        # ثمّ — وفقط إن تعذّرت — استخراجٌ حتميٌّ من النثر: بعثةُ الأسعار على
        # المسار العميق تُعيد جملاً، فكان `float()` يفشل على **كلّ** اكتشافٍ
        # ولا يتكوّن قسمُ الاقتصاد أصلاً مهما رُصِد من أسعارٍ حقيقية.
        try:
            candidates = [float(val)]
        except (TypeError, ValueError):
            candidates = price_numbers_in_text(val)
        if not candidates:
            continue
        # المستوى يُقرأ من **نصّ القيمة أيضاً** حين كانت جملة: هناك تعيش
        # عبارةُ «سعر رف» لا في الملاحظة.
        blob = f"{note} {val if isinstance(val, str) else ''}"
        if any(w in blob for w in _NON_PRICE_WORDS):
            continue
        level = detect_price_level(blob, _fsource(f))
        # مدىً في جملةٍ واحدة ⇒ حدُّه الأدنى (أقسى قيدٍ للدخول، القاعدةُ القائمة).
        fv = min(c for c in candidates if c > 0) if any(
            c > 0 for c in candidates) else None
        if fv:
            prices.append((fv, note, level))
    # **الموجة C (E-01/E-09).** المرساةُ من صفوف **التجزئة المُصرَّح بها** فقط.
    # خلطُ المستويات كان يُنتِج تفاؤلاً منهجياً: سعرُ حدودٍ يُتبنّى سعرَ رفّ.
    retail_rows = [(v, n) for v, n, lvl in prices if lvl == "retail"]
    other_rows = [(v, n, lvl) for v, n, lvl in prices if lvl != "retail"]
    anchor = None
    if retail_rows:
        lowest, src_note = min(retail_rows, key=lambda t: t[0])
        pack_kg, pack_litre = _parse_pack_from_note(src_note)
        anchor = normalize_price(lowest, basis="retail", category=category,
                                 pack_kg=pack_kg, pack_litre=pack_litre,
                                 currency=currency_in_note(src_note),
                                 source=src_note,
                                 note="أدنى سعر رف منافس مرصود")
    elif other_rows:
        # أسعارٌ مرصودةٌ فعلاً لكن **بمستوىً آخر أو مجهول** — تُعلَن ولا تُرسي.
        named = sorted({PRICE_LEVEL_AR.get(lvl, "مستوى غير محدد")
                        for _v, _n, lvl in other_rows})
        gaps.append(
            "الأسعار المرصودة ليست أسعار رفّ للمستهلك (" + "، ".join(named) +
            ") — والفرق بينها وبين سعر الرفّ أضعاف، فبناء الهامش عليها يعطي "
            "ربحاً أكبر من الحقيقي. الحل العكسي يبقى معلَّقاً حتى يُرصد سعر "
            "رفّ واحد على الأقل")
    else:
        gaps.append("لا سعر رف منافس مرصود — الحل العكسي غير ممكن حتى يُرصد "
                    "سعر واحد على الأقل (بعثة الأسعار)")

    # الدرس ٢٦٢ — **قراءةٌ واحدة للتعرفة**: كانت تُستخرَج هنا بـregex بمفردات
    # ضيّقة، فتفوت «التعريفة المطبَّقة» (صيغة WTO/WITS الحرفية) فيُعتمَد ٠٪
    # ويُعلَن «غير متاحة» بينما القسم التنظيميّ يطبع ٢٥٪ — تناقضٌ يراه العميل
    # في تقريرٍ واحد (بلاغ التقرير 6). المصدرُ الآن سجلُّ الحقائق الواحد،
    # ومسارُ الregex يبقى احتياطاً حين يتعذّر بناء السجلّ (لا سلوكَ أسوأ).
    tariff, t_note = (None, "") if ledger_reader_off() \
        else _tariff_from_ledger(dr)
    if tariff is None:
        tariff, t_note = _mission_numeric(dr, "tariffs_agreements",
                                          tariff_words(), 0.0, 100.0)
    if tariff is None:
        gaps.append("التعرفة غير متاحة — اعتُمدت 0% معلنةً في الحل العكسي")
    vat, _ = _mission_numeric(dr, "tariffs_agreements", _VAT_WORDS, 0.0, 50.0)

    # البند 5 (أمر إصلاح المحرّك): لا رقمَ مشتقاً من مدخلاتٍ غير مرصودة.
    # أساسُ الكتلة (كجم/لتر) والعملةُ **مدخلا حقيقة** لا معلمتا افتراض —
    # سعرُ عبوةٍ مجهولةِ الحجم بعملةٍ محلية كان يمرّ إلى الحل العكسي فيخرج
    # «$0.3274/كجم» بأربع منازل (تقرير #11) بينما جدول الأسعار نفسه «يتعذّر
    # الحساب». غيابُهما يعلّق الحلّ باسم الناقص حرفياً («غير محسوب —
    # الناقص: …»)؛ معالمُ السيناريو المعلنة (شحن/هوامش/تعرفة 0%) تبقى
    # مساراً مشروعاً معلَناً (§5.4) — الفرقُ أنّها تُعلَن لا أنّها تُرصَد.
    # هدف الدراسة الاحترافية (البند ١): أساسُ العرض وحدةُ السوق التي يشتري
    # بها الزائر — الحليب باللتر لا بالكيلوغرام ولو أبلغ كومتريد بالوزن؛
    # التحويل شأنٌ داخليّ. الفئة غير المسجّلة تبقى كجم (اصطلاح التجارة).
    _mu_code, _mu_ar = market_unit(category, (product_card or {}).get('unit'))
    reverse = None
    if anchor is not None:
        _missing: list[str] = []
        basis_val, basis_unit = None, None
        if _mu_code == "litre" and anchor.per_litre is not None:
            basis_val, basis_unit = anchor.per_litre, "لتر"
        elif anchor.per_kg is not None:
            basis_val, basis_unit = anchor.per_kg, "كجم"
        elif anchor.per_litre is not None:
            basis_val, basis_unit = anchor.per_litre, "لتر"
        else:
            _missing.append(f"حجم العبوة (لتطبيع السعر إلى ال{_mu_ar})"
                            if _mu_code == "litre"
                            else "حجم العبوة (لتطبيع السعر إلى كجم/لتر)")
        _cur = (anchor.currency or "").strip()
        if not _cur:
            _missing.append("عملة السعر المرصود")
        if not _missing:
            reverse = reverse_solve_max_exw(basis_val,
                                            tariff_pct=tariff, vat_pct=vat)
            reverse["unit"] = basis_unit
            reverse["currency"] = _cur
        else:
            gaps.append("أقصى سعر مصنع (EXW) غير محسوب — الناقص: "
                        + "؛ ".join(_missing))

    # البند 6 (أمر إصلاح المحرّك): تناقضُ التسعير لا يمرّ بلا تعليق — أقصى
    # سعر مصنع (بعد تحويله للدولار) أدنى بأكثر من 20% من متوسط سعر الاستيراد
    # المرصود (كومتريد: القيمة÷الوزن الصافي، دولار/كجم) = «لا منافسة سعرية
    # قائمة»؛ تحذيرٌ إلزاميّ ويُحظَر اقتراحُ الرقم أساساً تفاوضياً (تقرير
    # #11: $0.3274 مقابل $0.81 — أدنى بـ60% وقُدِّم أساساً للتفاوض بلا
    # تعليق). المصدران حتميان: المرجعُ من بعثة التجارة بصيغتها الحرفية،
    # والصرفُ من إلحاق `_augment_risk_news_fx` (البنك الدولي، سنة معلنة).
    pricing_contradiction = None
    ref_import, _ref_note = _mission_numeric(
        dr, "trade_flow", ("متوسط سعر استيراد", "قيمة الوحدة الحدودية",
                           "unit value"), 0.0, 100_000.0)
    # البند ١ (وحدة السوق): حين يُعرَض الأساس باللتر يبقى فحصُ التناقض حياً —
    # المقارنة مع سعر الحدود ($/كجم) تتم بعد تحويلٍ داخليّ بثابت السجل، لا
    # تُعطَّل ولا تُعلَن فجوةً لفئةٍ كثافتُها معروفة.
    _exw_cmp = None      # قيمة EXW على أساس كجم للمقارنة الحدودية
    if reverse is not None:
        if reverse.get("unit") == "كجم":
            _exw_cmp = float(reverse["max_exw"])
        elif reverse.get("unit") == "لتر":
            _kg_per_l, _ = convert_amount(1.0, "litre", "kg", category)
            if _kg_per_l:
                _exw_cmp = round(float(reverse["max_exw"]) / _kg_per_l, 4)
    if reverse is not None and ref_import and _exw_cmp is not None:
        _cur = str(reverse.get("currency") or "")
        _exw_usd = None
        if _cur in ("$", "USD", "دولار"):
            _exw_usd = _exw_cmp
        else:
            fx, _ = _mission_numeric(dr, "risk_news",
                                     ("سعر الصرف الرسمي",), 1e-4, 100_000.0)
            if fx:
                # المقارنة الحدودية على أساس كجم ($/كجم)؛ العرضُ يبقى بوحدة
                # السوق — `max_exw_usd` بالوحدة المعروضة نفسها لا بغيرها.
                _exw_usd = round(_exw_cmp / fx, 4)
                reverse["max_exw_usd"] = round(
                    float(reverse["max_exw"]) / fx, 4)
                reverse["fx_rate"] = fx
            else:
                gaps.append("مقارنة التنافسية السعرية (أقصى EXW مقابل متوسط "
                            "سعر الاستيراد) غير محسوبة — الناقص: سعر الصرف "
                            "لتحويل أقصى سعر المصنع إلى الدولار")
        if _exw_usd is not None and _exw_usd < 0.8 * ref_import:
            _short = round((ref_import - _exw_usd) / ref_import * 100, 1)
            pricing_contradiction = {
                "max_exw_usd": _exw_usd,
                "reference_import_price_usd_kg": ref_import,
                "shortfall_pct": _short,
                "note": (f"تحذير: أقصى سعر مصنع قابل للمنافسة "
                         f"({_exw_usd} دولار/كجم) أدنى بنسبة {_short}% من "
                         f"متوسط سعر الاستيراد المرصود ({ref_import} "
                         "دولار/كجم) — المنافسة السعرية غير قائمة عملياً في "
                         "هذه الفئة، ولا يصلح هذا الرقم أساساً للتفاوض")}

    # الشلال من تكلفة المصنع إن وُجدت في بطاقة المنتج؛ وإلا معلمة مفتوحة.
    waterfall = None
    exw = None
    if product_card:
        try:
            exw = float(product_card.get("cost_per_unit") or 0) or None
        except (TypeError, ValueError):
            exw = None
    if exw:
        waterfall = margin_waterfall(exw, freight=None, tariff_pct=tariff,
                                     vat_pct=vat, distributor_margin_pct=None,
                                     retailer_margin_pct=None)
    else:
        # لا إحالة إلى «الحل العكسي أعلاه» حين يكون معلَّقاً — إحالةٌ معلّقة
        # من عائلة `dangling_cross_reference` نفسها (مراجعة §58، البند 5).
        # #13: «النموذج مُعلمَن/بطاقة المنتج/الشلال» لغة نظام بلغت PDF
        # العميل — تُطلب بلغة الزائر: المعطى نفسه وما الذي يكتمل به.
        # البند ١ (وحدة السوق): المعطى يُطلَب بوحدة سوق المنتج نفسها —
        # «سعر المصنع للتر» لمنتجٍ يباع باللتر، لا وحدة كومتريد.
        _unit_word = {'litre': 'للتر الواحد', 'kg': 'للكيلوغرام',
                      'piece': 'للقطعة الواحدة'}.get(_mu_code, 'لوحدة المنتج مع تحديدها')
        gaps.append(f"تكلفة المصنع (EXW) غير مدخلة — أدخل سعر المصنع "
                    f"{_unit_word} لاستكمال أحد مدخلات سلسلة التكلفة حتى الرف"
                    + ("؛ الحل العكسي أعلاه يعطيك أقصى تكلفة قابلة للمنافسة"
                       if reverse is not None else ""))

    # البند ٢ (هدف الدراسة الاحترافية): «سطر الفتح» الواحد — حين تغيب تكلفة
    # الإنتاج لا يُعلَن الغياب رقماً رقماً (خمس «غير محسوب» بلا تفسير)؛ جملة
    # واحدة بلغة الزائر تسمّي ما يفتحه رقم واحد، بوحدة سوق المنتج.
    unlock_note = None
    if not exw:
        _unit_name = {'litre': 'اللتر', 'kg': 'الكيلوغرام',
                      'piece': 'القطعة'}.get(_mu_code, 'وحدة المنتج المحددة')
        unlock_note = (f"حساب هامش الربح ونقطة التعادل والخسارة المحتملة يحتاج "
                       f"تكلفة إنتاج {_unit_name}، وسعر البيع المتوقع، والشحن "
                       f"والرسوم والتكاليف الثابتة. تبقى النتائج غير محسوبة "
                       f"إلى أن تتوفر المدخلات اللازمة بوحدات متطابقة")

    # سؤال الإزاحة عند تركّز مرتفع (§5.1): HHI من بعثة المنافسين، بتطبيع
    # مقياس صريح (≤1 = كسر → ×10000 عبر hhi_from_fractions المنطق الموحّد).
    hhi_val, _ = _mission_numeric(dr, "competitors", _HHI_WORDS, 0.0, 10_000.0)
    if hhi_val is not None and hhi_val <= 1.0:
        hhi_val = round(hhi_val * HHI_SCALE_MAX)
    # **الموجة C (E-05).** `bool(None ...)` كانت `False` — أي أنّ «الإزاحة غير
    # مطلوبة» تُقال بثقةٍ حين لم تُقَس أصلاً. الحالتان مختلفتان تجارياً: سوقٌ
    # مفتّتٌ يُدخَل بالتنافس السعريّ، وسوقٌ **لم يُقَس تركّزُه** يُدخَل بحذر.
    displacement_measured = hhi_val is not None
    displacement_required = bool(displacement_measured
                                 and hhi_is_high(hhi_val))
    if not displacement_measured:
        gaps.append(
            "تركّز المورّدين غير متاح — لم نستطع تحديد ما إذا كان السوق "
            "محكوماً بعدد قليل من المورّدين أم مفتوحاً للتنافس. لا تقرأ ذلك "
            "«سوقاً مفتوحاً»: هو بند لم يُقَس")

    # شكل المنتج الموصى به (Gate D بند 5 — سدّ الخياطة): يُحمل من بطاقة
    # المنتج حين تصرّح به («form»)؛ غيابه = None (الفحص نائم بلا اختلاق).
    product_form = ""
    if product_card:
        product_form = str(product_card.get("form")
                           or product_card.get("الشكل") or "").strip()

    # البند ٧: أرقام القرار الخمسة تُحسب هنا مرة واحدة (نمط Z-01) — الكاتب
    # يشرحها والأسطح تعرضها؛ كل بند تقدير بحقوله الأربعة أو فجوة بحقولها
    # الثلاثة. الطاقة الشهرية من البطاقة إن وُجدت (تحوّل التعادل زمناً).
    _capacity = None
    if product_card:
        try:
            _capacity = float(product_card.get("monthly_capacity") or 0) \
                or None
        except (TypeError, ValueError):
            _capacity = None
    # عملة التكلفة من البطاقة إن صُرّح بها (currency/cost_currency) — غيابها
    # يجعل نقطة التعادل فجوة معلنة تسمّي العملة (مراجعة §58: لا طرح بين
    # عملتين بلا تصريح).
    _cost_cur = ""
    if product_card:
        _cost_cur = str(product_card.get("cost_currency")
                        or product_card.get("currency") or "").strip()
    decision_numbers = build_decision_numbers(
        category=category, cost_per_unit=exw, cost_currency=_cost_cur,
        monthly_capacity=_capacity, reverse=reverse)

    return {
        "product_form": product_form or None,
        # البند ١: وحدة سوق المنتج تُعلَن في العرض فتتبعها كل الأسطح —
        # لا سطح يقرّر وحدته بنفسه (قاعدة العرض الواحد).
        "market_unit": {"code": _mu_code, "label_ar": _mu_ar},
        "decision_numbers": decision_numbers,
        "unlock_note": unlock_note,
        "anchor_price": anchor.to_dict() if anchor else None,
        "reverse_solve": reverse,
        "pricing_contradiction": pricing_contradiction,
        "waterfall": waterfall,
        # عملةُ التكلفة كما صرّح بها المالك في البطاقة — مفتاحٌ إضافيّ لا
        # يغيّر رقماً (مراجعة §58): كلُّ سطحٍ يعرض مبلغاً مشتقّاً من سعر
        # المصنع يقرأ عملتَه من هنا، فلا يستنتجها من افتراضٍ داخليّ
        # (`margin_waterfall(currency="USD")` افتراضٌ لم يصرّح به أحد).
        "cost_currency": _cost_cur or None,
        "hhi": hhi_val,
        "displacement_required": displacement_required,
        "displacement_measured": displacement_measured,
        "parameter_scenarios": PARAMETER_SCENARIOS,
        "gaps": gaps,
    }
