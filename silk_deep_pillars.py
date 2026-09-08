"""مدخلاتُ أعمدة القرار من بعثات المسار العميق · deep-path pillar inputs.

> **الفجوة D-01 + الجذر ١** (`docs/ENGINE_AUDIT.md`): السلسلةُ الحتمية
> `run_market → pillar_inputs → decide → row["decision"] → view["decision"]`
> **مقطوعةٌ من طرفيها** على المسار العميق: `silk_research` غيرُ مستورَدٍ هناك
> أصلاً، وليس بين البعثات الاثنتي عشرة بعثةٌ تُنتِج `pillar_inputs`،
> و`api.py` يثبّت `"markets": []` فيسقط `top` في `build_view`.
>
> فالأعمدةُ الخمسة وأوزانُها A/B و«قاعدةُ القرار قبل الحكم» والحجّةُ المضادّة —
> **لا شيءَ منها يصل المصنع**، رغم أنّ `silk_reports` مُهيَّأةٌ لعرضها كلِّها.
> ومعها سقط قسمُ «موقعك التنافسي»، وتحذيرُ القِدَم ذو الطبقتين (S-01)، وبوّابةُ
> الأهلية (R-03)، وحرّاسُ الدرس ٨٨ (X-03)، و`_completeness`.

**القاعدةُ الحاكمة:** هذه الوحدةُ **مُستخرِجٌ لا مقرِّر**. تقرأ ما رصدته
البعثاتُ وتضعه في المفاتيح التي يتوقّعها `silk_decision`، ولا تحسب درجةً ولا
تُصدِر حكماً ولا تخمّن قيمةً غائبة. المنطقُ الوحيد للقرار يبقى في
`silk_decision.decide` — نسخُه هنا كان سيُنتِج محرّكَ قرارٍ ثانياً، وهو بالضبط
ما تحظره قاعدةُ «حكمٌ واحد».

**وما لا يُرصَد يبقى `None`.** عمودٌ بمدخلٍ ناقص يُعيد `silk_decision` تسويةَ
أوزانه ويُعلن الشرط — وهو السلوكُ الصحيح. ملؤه بصفرٍ أو بتقديرٍ كان سيُنتِج
درجةً تبدو محسوبةً وهي مختلَقة.

stdlib فقط؛ صفرُ شبكة؛ الاستيرادات الثقيلة كسولةٌ داخل الدوالّ.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger("silk.deep_pillars")

# كلماتٌ مفتاحية لكلّ مؤشّر — تُطابَق على **ملاحظة** الاكتشاف وقيمتِه النصّية
# معاً (البعثاتُ تُعيد جملاً؛ الدرسُ المتكرّر في الموجة C).
_KW = {
    # «واردات ٢٠٢٣» هي الصيغةُ التي تكتبها بعثةُ التجارة فعلاً — والإبرُ
    # الطويلةُ وحدَها («إجمالي واردات السوق») كانت تُفوِّتها فيخرج عمودُ السوق
    # فارغاً رغم وجود الرقم. الإبرةُ تتبع ما يُكتَب لا ما نتمنّى أن يُكتَب.
    # «إجمالي استيراد …» صيغةُ ملاحظة أداة comtrade_imports الحتمية نفسها
    # (دراسة #12): بدونها كانت حقائقُ الأداة الرقمية (بسنواتها البنيوية)
    # غيرَ مرئية للعمود فيفوز النثر — الإبرة تتبع ما يُكتب.
    "tam_usd": ("واردات", "الواردات", "استيراد", "TAM", "imports",
                "import value"),
    "import_cagr_pct": ("CAGR", "نمو مركّب", "معدل النمو السنوي"),
    "gdp_per_capita_usd": ("نصيب الفرد", "دخل الفرد", "GDP per capita"),
    # «تستحوذ السعودية على 90.61%» صيغةُ بعثات التجارة الفعلية (تقرير #10) —
    # الإبرةُ تتبع ما يُكتَب لا ما نتمنى (نفس درس «واردات ٢٠٢٣» أعلاه).
    "saudi_share_pct": ("حصة السعودية", "الحصة السعودية", "saudi share",
                        "تستحوذ السعودية"),
    # البند 3: تقلّب الصرف يصل بإلحاق `_augment_risk_news_fx` الحتمي —
    # الإبرة تطابق ملاحظته المصوغة هناك حرفياً.
    "fx_volatility_pct": ("تقلب سعر الصرف", "تقلّب سعر الصرف",
                          "fx volatility"),
    "hhi": ("HHI", "تركّز", "تركز السوق"),
    "top_supplier_share_pct": ("حصة أكبر مورّد", "أكبر مورد", "top supplier"),
    "tariff_applied_pct": ("التعرفة", "الرسوم الجمركية", "tariff", "MFN"),
    "political_stability_wgi": ("الاستقرار السياسي", "political stability"),
    "regulatory_quality_wgi": ("جودة التنظيم", "regulatory quality"),
    "logistics_lpi": ("LPI", "الأداء اللوجستي", "logistics performance"),
    "border_unit_value_usd_kg": ("قيمة الوحدة الحدودية", "سعر الوحدة الحدودي",
                                 "unit value"),
}

# مدياتٌ معقولة لكلّ مؤشّر — حارسٌ ضد التقاط رقمٍ من نوعٍ آخر في الجملة نفسها
# (نفسُ مبدأ `_mission_numeric`: الكلمةُ المفتاحية شرطٌ سابق، والمدى ثانٍ).
_RANGE = {
    "import_cagr_pct": (-100.0, 200.0),
    "gdp_per_capita_usd": (100.0, 300_000.0),
    "saudi_share_pct": (0.0, 100.0),
    # البند 1: مقياسا المنافسة لم يعودا يمرّان بالمسار النثريّ العام
    # (`_numeric`) إطلاقاً — مدخلاهما `_structured_competition` (ملخّص مُهيكل
    # ثم قيمٌ رقمية بمدى صريح هناك). المدخلان أدناه إسنادُ كلماتٍ فقط.
    "hhi": (0.0, 10_000.0),
    "top_supplier_share_pct": (0.0, 100.0),
    "tariff_applied_pct": (0.0, 100.0),
    "political_stability_wgi": (-3.0, 3.0),
    "regulatory_quality_wgi": (-3.0, 3.0),
    # درس 191 (§58 الملاحظة 4، قرار مالك 2026-08-27): الحدّ الأعلى كان 100
    # فيُسقِط تقلّباً >100% (عملة منهارة — اليمن) في `_numeric_with_source`،
    # فيقرأ العمودُ «غير مرصود» ويُعيد التطبيع **صعوداً**: 187% تبدو «أأمن»
    # (0.217) من 18% (0.188) — انقلابُ إشارةٍ حيث تلزم أكثر ما تلزم. التقلّب
    # نسبةٌ غير مقيّدة أعلى بطبيعتها (تضخّم جامح)؛ السقف الآن يسع الانهيار
    # ويرفض العبث، و`_clip` (silk_decision.py:284) يقصّ المساهمة للأسوأ 0.0.
    # سلامة الأساس مثبتةٌ بإعادة تشغيل المدوّنات العشر (كلها fx=None) — صفر
    # تغيير. حارسُ الكلمات المفتاحية يفصل «سعر الصرف الرسمي» فلا يتسرّب كنسبة.
    "fx_volatility_pct": (0.0, 100_000.0),
    "logistics_lpi": (1.0, 5.0),
    "border_unit_value_usd_kg": (0.0, 100_000.0),
    # الحدُّ الأدنى فوق نطاق السنوات (٢٠٢٣) عمداً: «واردات 2023»
    # تحمل رقمين، والسنةُ ليست حجمَ سوق.
    "tam_usd": (100_000.0, 1e13),
}

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")

# رُموزُ الكلماتِ الكاملة — لا تُطابَق **تحت-سلسلةً** أبداً: «طن» جزءُ «قطن»،
# و«kg» جزءُ «background»، و«الف» جزءُ «خالف» (مراجعة §58). التقسيمُ على حدود
# الأحرف يمنع كلَّ ذلك: «قطن» رمزٌ واحدٌ لا يساوي «طن».
_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# كلماتُ المقدار الملتصقةُ بالرقم — «350 مليون دولار» رقمُ TAM لا 350. ترتيبٌ
# تنازليّ، ولا `k`/`mn`/`bn` (تلتقط ضوضاءً مثل «kg»/رموزِ عملات).
_MAGNITUDE = (
    (("تريليون", "trillion"), 1e12),
    (("مليار", "بليون", "billion"), 1e9),
    (("مليون", "million"), 1e6),
    (("ألف", "الف", "thousand"), 1e3),
)
# وحداتُ وزنٍ (رموزُ كلماتٍ كاملة) تُبطِل تبنّي الرقم قيمةً دولاريّة (TAM/نصيب
# الفرد): «الوزن الصافي 2,300,000 كجم» ليس حجمَ سوقٍ بالدولار. (border_unit_value
# دولار/كجم ليست من `_USD_VALUE_METRICS` فلا تتأثّر.)
_MASS_TOKENS = frozenset({"كجم", "كغم", "كيلوغرام", "كيلو", "طن", "طنّ",
                          "kg", "tonne", "tonnes", "ton", "tons",
                          "lb", "lbs", "رطل"})
_USD_VALUE_METRICS = ("tam_usd", "gdp_per_capita_usd")


def _num_to_float(tok: str) -> "float | None":
    """رقمٌ من رمزٍ نصّيّ بعرفِ الريبو (نقطةٌ عشريّة، فاصلةٌ آلاف) **مع تمييز
    الفاصلةِ العشريّةِ الأوروبية**: فاصلةٌ تتبعها ٣ خاناتٍ في كلّ مجموعة =
    آلاف («2,350»→2350)؛ وإلّا فاصلةٌ عشريّة («2,35»→2.35) — فلا يُضخَّم رقمٌ
    أوروبيّ ١٠٠ ضعف (مراجعة §58)."""
    tok = (tok or "").strip()
    try:
        if "," in tok and "." in tok:
            return float(tok.replace(",", ""))          # نقطةٌ عشريّة، فاصلةٌ آلاف
        if "," in tok:
            parts = tok.lstrip("-").split(",")
            if (len(parts) > 1 and all(len(p) == 3 for p in parts[1:])
                    and 1 <= len(parts[0]) <= 3):
                return float(tok.replace(",", ""))       # مجموعاتُ آلافٍ صحيحة
            return float(tok.replace(",", "."))          # فاصلةٌ عشريّةٌ أوروبية
        return float(tok)
    except (TypeError, ValueError):
        return None


def _magnitude_scale(tokens: set) -> float:
    """مضاعِفُ المقدار من رموزِ ذيلِ الرقم — أو 1.0. مطابقةُ رمزٍ كاملٍ حصراً."""
    for words, mult in _MAGNITUDE:
        if any(w in tokens for w in words):
            return mult
    return 1.0


def _is_mass_tail(tokens: set) -> bool:
    return not tokens.isdisjoint(_MASS_TOKENS)


def _findings(missions: dict, key: str) -> list:
    m = (missions or {}).get(key)
    if isinstance(m, dict):
        return m.get("findings") or []
    return list(getattr(m, "findings", []) or [])


def _fv(f):
    return f.get("value") if isinstance(f, dict) else getattr(f, "value", None)


def _fnote(f) -> str:
    return str(f.get("note") if isinstance(f, dict)
               else getattr(f, "note", "") or "")


# §58 (هذه الموجة، ثم تحويل الخطر المصرَّف فكساً): تاريخ ISO في الملاحظة
# («جُلبت أصلاً 2026-08-20») لا يُقرأ سنةَ حقيقة — الاستثناء «سنةٌ يتبعها
# -\d\d ليس بعده رقم» (شهرُ ISO) حصراً، فمدى السنوات «2019-2024» يبقى
# مقروءاً بطرفيه (كان استثناء «-» الأعمى يلتهمهما معاً فيفقد بندُ مدى
# سنته). قيدٌ معلَن: صيغة المدى المختزلة «2019-20» تُقرأ ISO فتُستثنى.
_NOTE_YEAR_RE = re.compile(
    r"(?<![\d/])(19\d\d|20\d\d)(?![\d/])(?!-\d\d(?!\d))")


def _fact_year(f, *, allow_note_year: bool = True) -> "int | None":
    """سنةُ حقيقة الاكتشاف للمفاضلة: `data_year` البنيوية أولاً، وإلا أحدثُ
    سنةٍ مذكورةٍ في ملاحظته/قيمته النصية («من 2019 إلى 2024» ⇒ 2024) حين
    يُسمح بذلك، وإلا None. **لا** احتياط بـ`retrieved_at` — تاريخُ الجلب
    يجعل كلَّ نثرٍ «أحدث» من حقائق الأداة زوراً (دراسة #12).

    §58: `allow_note_year=False` لمرشّحي **النثر** في `_numeric_with_source`
    — سنو نثرٍ يمتد 2019→2024 لا تصلح اقتراناً برقمه الأول المستخرج
    (كانت قيمة 2019 تُختم بسنة 2024 فتحجب حقيقة الأداة الحقيقية)."""
    dy = (f.get("data_year") if isinstance(f, dict)
          else getattr(f, "data_year", None))
    try:
        if dy is not None:
            return int(dy)
    except (TypeError, ValueError):
        pass
    if not allow_note_year:
        return None
    val = _fv(f)
    blob = f"{_fnote(f)} {val if isinstance(val, str) else ''}"
    years = [int(m.group(1)) for m in _NOTE_YEAR_RE.finditer(blob)]
    return max(years) if years else None


def _numeric(findings: list, metric: str) -> "float | None":
    return _numeric_with_source(findings, metric)[0]


def _numeric_with_source(findings: list, metric: str) -> tuple:
    """(القيمة، الاكتشافُ مصدرُها) — **أحدثُ سنةِ حقيقةٍ تفوز** بين المطابقات
    الصالحة (دراسة #12 الحيّة: البعثة تسرد السنوات من الأقدم فعرض جدولُ
    المكوّنات واردات 2019 (1.77M) بينما أساسُ السرد 18.6M لسنة 2024 — نفسُ
    قاعدة `silk_plausibility._prefer_latest`: لا مكوّن على قيمةٍ تاريخية).

    قواعد الاختيار (§58 + أمر المُشرِف C2):
      • سنةُ النثر **لا تُنقَّب من ملاحظته** (`allow_note_year=False`) —
        نثرٌ يمتد 2019→2024 كان يقترن رقمُه الأول بسنته الأخيرة فيحجب
        حقيقةَ الأداة الحقيقية؛ سنةُ النثر إذن `data_year` أو None.
      • على سنةٍ متساوية تفوز القيمةُ المُهيكلة على المستخرجة نثراً.
      • مرشحٌ واحد يُستهلَك كما هو (لا اعتباطَ فيه — سنتُه قد تبقى مجهولة
        معلَنةً في إسناده).
      • مرشحان نثريان فأكثر بلا أي سنةٍ وبلا مُهيكلٍ بينهما = لا أساسَ
        للاختيار ⇒ فجوةٌ معلنة `(None, None)` — لا انزلاقَ لأول وصولٍ
        (آلية #12 بعينها).

    يقرأ النثرَ كما يقرأ الأرقام: البعثاتُ على هذا المسار تُعيد جملاً، وقراءةُ
    `float(value)` وحدَها هي ما أبقى أربعَ طبقاتٍ خامدةً حتى الموجة C.
    """
    # كل مرشح: (القيمة، الاكتشاف، مُهيكل؟، السنة)
    cands: list = []
    words = _KW.get(metric, ())
    lo, hi = _RANGE.get(metric, (float("-inf"), float("inf")))
    usd_metric = metric in _USD_VALUE_METRICS

    def _consider(value: float, f, structured: bool) -> None:
        cands.append((value, f, structured,
                      _fact_year(f, allow_note_year=structured)))

    for f in findings:
        val, note = _fv(f), _fnote(f)
        if isinstance(val, bool):
            continue
        blob = f"{note} {val if isinstance(val, str) else ''}"
        if words and not any(w.lower() in blob.lower() for w in words):
            continue
        if isinstance(val, (int, float)):
            # قيمةٌ رقميّةٌ مُهيكَلة — لا نصَّ وحدةٍ ولا مقدار؛ المدى وحدَه.
            if lo <= float(val) <= hi:
                _consider(float(val), f, True)
            continue
        # النثرُ: كلُّ رقمٍ ومعه ذيلُه (المقدارُ والوحدةُ الملتصقان به) — كي
        # يُطبَّق «مليون/مليار» على الرقم نفسِه، ويُرفَض رقمُ وزنٍ قيمةً دولاريّة
        # (مراجعة §58: «الوزن الصافي … كجم» كان يُتبنّى TAM، و«350 مليون دولار»
        # كان يسقط دون العتبة لإهمال كلمةِ المقدار).
        raw = str(val or "")
        for m in _NUM_RE.finditer(raw):
            base = _num_to_float(m.group(0))
            if base is None:
                continue
            # الذيلُ **حتّى الرقمِ التالي فقط** (بنافذةٍ محدودة): كلمةُ مقدارٍ
            # تخصّ رقماً لاحقاً لا يجوز أن تُنسَب لهذا الرقم — «واردات 2023:
            # 129.6 مليون» كانت تُعطي 2023×1e6 لأنّ «مليون» وقعت في نافذةِ
            # السنة (مراجعة §58). القطعُ عند أوّل خانةٍ يمنع النزفَ.
            tail = re.split(r"\d", raw[m.end():m.end() + 20], maxsplit=1)[0]
            toks = {t.lower() for t in _TOKEN_RE.findall(tail)}
            if usd_metric and _is_mass_tail(toks):
                continue                       # كميّةُ وزنٍ لا قيمةٌ دولاريّة
            # المقدارُ (مليون/مليار) يُطبَّق على قيمِ **المال المطلقة** حصراً
            # (TAM/نصيب الفرد): النِسَبُ والمؤشّرات (حصة/تعرفة/WGI/LPI/HHI) لا
            # تُقاس بالملايين، فكلمةُ مقدارٍ في جملةٍ مجاورة كانت ستُضخّمها
            # زوراً حيث يسمح مداها (مراجعة §58، إعادة مراجعة).
            mult = _magnitude_scale(toks) if usd_metric else 1.0
            # عقدُ عدم الاختلاق (مراجعة §58×٣): رقمٌ صحيحٌ بشكلِ **سنةٍ**
            # (1900–2099) مضروبٌ بمقدارٍ غالباً سنةُ تأريخٍ لا قيمة — «واردات
            # 2023 مليون» كانت تُنتِج 2.023e9 مختلَقة. إسقاطٌ معلَنٌ خيرٌ من
            # رقمٍ مختلَق: نتخطّى المرشّح فيبقى العمودُ فجوةً لا كذباً.
            if mult > 1.0 and base == int(base) and 1900 <= base <= 2099:
                continue
            c = base * mult
            if lo <= c <= hi:
                _consider(c, f, False)
                break                     # رقمٌ صالح واحد من كل اكتشاف
    if not cands:
        return None, None
    if len(cands) == 1:
        return cands[0][0], cands[0][1]
    dated = [c for c in cands if c[3] is not None]
    if dated:
        top_y = max(c[3] for c in dated)
        tied = [c for c in dated if c[3] == top_y]
        pick = next((c for c in tied if c[2]), tied[0])
        return pick[0], pick[1]
    structured = [c for c in cands if c[2]]
    if structured:
        return structured[0][0], structured[0][1]
    return None, None      # C2: نثرٌ متعدد بلا سنوات — فجوة معلنة لا اعتباط


def _scaled_hhi(value: "float | None") -> "float | None":
    """HHI بمقياسٍ واحد 0–10000 — نفسُ التطبيع الذي يفعله `silk_economics`."""
    if value is None:
        return None
    return round(value * 10_000) if value <= 1.0 else value


# كلماتٌ تدلّ على أنّ الاكتشافَ **مقياسٌ** لا اسمُ شركة.
_METRIC_WORDS = ("hhi", "تركّز", "تركز", "حصة", "حصّة", "نسبة", "share",
                 "index", "مؤشر", "مؤشّر", "%")

# المهيمنُ سعوديّ؟ — أسماءُ الشريك كما يعيدها `partner_name` (إنجليزيةً من
# countries.csv أو عربيةً احتياطاً).
_INCUMBENT_SAUDI_TOKENS = ("saudi", "السعودية", "سعودية")


def _structured_competition(findings: list) -> tuple:
    """(hhi، حصةُ الأكبر، اسمُ الأكبر) من ملخّص `comtrade_competitors`
    **المُهيكل حصراً** — لا استخراجَ نثرياً لهذين المقياسين.

    البند 1 من أمر إصلاح المحرّك (تقريرا #10/#11، حليب/الأردن): حقلُ
    المنافسة قَبِل كمّيتين مختلفتين — HHI (0–10000) وحصةً مئوية (0–100) —
    لأنّ الاستخراج النثريّ يلتقط أوّل رقمٍ في المدى قرب الكلمة، والمدى
    النثريّ يبتلع الحصص، فانقلب الحكم 26%→84% من هذا الحقل وحده. الأداةُ
    تعيد الرقمين مُهيكلَين أصلاً في نقطة الملخّص (silk_llm_runtime،
    comtrade_competitors) — فالوحدةُ مضمونةٌ بالبناء لا بفحص مدى.
    الملخّص غائب (بعثة فاشلة/بلا سجل) ⇒ (None, None, None) — فجوةٌ معلنة
    يعيد `silk_decision` تسويةَ أوزانه عندها، لا تخمين من النثر."""
    # D5 (دراسة #12): بين ملخّصاتٍ مُهيكلة متعددة كان **أول** قاموسٍ يفوز
    # بترتيب الوصول — فعرض جدولُ المكوّنات مرآةَ 2025 (ثقة 0.6) بينما أساسُ
    # السرد مباشرُ 2024 (ثقة 0.9). المفاضلة: المباشرُ (غير مرآة) أولاً، ثم
    # الأحدثُ سنةً، ثم ترتيبُ الوصول.
    cands: list = []
    for order, f in enumerate(findings):
        v = _fv(f)
        if not (isinstance(v, dict) and "hhi" in v):
            continue
        try:
            hhi = float(v["hhi"]) if v.get("hhi") is not None else None
        except (TypeError, ValueError):
            hhi = None
        share = partner = None
        tops = v.get("top_suppliers") or []
        if tops and isinstance(tops[0], dict):
            partner = str(tops[0].get("partner") or "") or None
            try:
                share = (float(tops[0]["share"])
                         if tops[0].get("share") is not None else None)
            except (TypeError, ValueError):
                share = None
        if share is not None and not (0.0 <= share <= 100.0):
            share = None    # وحدةٌ خارج عقدها لا تُستهلَك — تُعلَن غائبة
        hhi = _scaled_hhi(hhi)
        # موجة سدّ الفجوات (F1): مدى الوحدة يُفرَض هنا أيضاً لا على مسار
        # الاحتياط وحده — حصةٌ تسرّبت لمفتاح hhi (قيمة الحادثة 84.05) كانت
        # تنجو خاماً فتُقرأ «HHI 84» بدرجة منافسة 98%. نفسُ حدَّي الاحتياط:
        # الأرضية 100 تحسم الوحدةَ الملتبسة والسقف 10000 حدُّ المقياس نفسه.
        if hhi is not None and not (100.0 <= hhi <= 10_000.0):
            hhi = None
        src = str(f.get("source") if isinstance(f, dict)
                  else getattr(f, "source", "") or "")
        mirrored = ("مرآة" in src or "mirror" in src.lower()
                    or "مرآة" in _fnote(f))
        try:
            year = int(v.get("year") or 0) or _fact_year(f)
        except (TypeError, ValueError):
            year = _fact_year(f)
        # §58 (الملاحظة 5): صلاحيةُ HHI قبل كل شيء — مباشرٌ بقيمة خارج
        # المدى (⇒ None) لا يحجب مرآةً صالحة. الدراسة الحية الرابعة (E3،
        # نفس عيب #12): اكتمالُ الحصة كان يسبق المباشرية فتغلب مرآةٌ كاملةُ
        # الهيكلة مباشراً بلا حصة — والمكوّن المعروض هو HHI وحده، فالمباشرية
        # قبل اكتمال الحصة (أقفال D5 الثلاثة تصمد: الصلاحية أولاً باقية).
        cands.append((((hhi is None),
                       0 if not mirrored else 1, (share is None),
                       -(year or 0), order), (hhi, share, partner, f)))
    # E3 (الدراسة الحية الرابعة): حقيقةُ HHI مباشرة رقمية القيمة (من المخزن/
    # الإلحاق الحتمي — «تركّز الموردين: 7118») تُنافس كمرشح أيضاً — كانت
    # احتياطاً لا يعمل إلا بغياب كل مُهيكل، فتفوز مرآةٌ مُهيكلة على مباشرٍ
    # رقمي أحدث ويتنافر جدول المكوّنات مع السرد.
    structured_cands = list(cands)
    hhi_nf, hhi_nf_src = _numeric_value_only(findings, "hhi", 100.0, 10_000.0)
    if hhi_nf is not None and hhi_nf_src is not None:
        src_n = str(hhi_nf_src.get("source") if isinstance(hhi_nf_src, dict)
                    else getattr(hhi_nf_src, "source", "") or "")
        mirrored_n = ("مرآة" in src_n or "mirror" in src_n.lower()
                      or "مرآة" in _fnote(hhi_nf_src))
        year_n = _fact_year(hhi_nf_src)
        cands.append((((False), 0 if not mirrored_n else 1, True,
                       -(year_n or 0), len(findings)),
                      (_scaled_hhi(hhi_nf), None, None, hhi_nf_src)))
    # احتياط الحصة **رقميّ القيمة حصراً** (مراجعة §58): نتائجُ النموذج نصوصُ
    # ادعاءاتٍ دوماً، فالقيمُ الرقمية هنا من مصادرنا الحتمية وحدها — لا
    # قراءةَ نصٍّ إطلاقاً (وهي التي التقطت 84.05 كأنها HHI).
    share_f = _numeric_value_only(findings, "top_supplier_share_pct",
                                  0.0, 100.0)
    if cands:
        hhi_w, share_w, partner_w, f_w = min(cands)[1]
        if share_w is None:
            # C4 موجة #14 (الملاحظتان 1+2): فوزُ المرشح الرقمي (بلا حصة)
            # لا يُسقِط حصةً مرصودة — تُكمَّل قيمتا الحصة/الاسم من أفضل
            # ملخّصٍ مُهيكل يحملهما (قيمُ أعمدةٍ بلا إسناد فردي — إسنادُ
            # مكوّن المنافسة المعروض يبقى نتيجةَ HHI الفائزة f_w)، وإلا
            # فمن احتياط الحصة الرقمي القائم قبل الموجة.
            with_share = [c for c in structured_cands
                          if c[1][1] is not None]
            if with_share:
                _hw, share_w2, partner_w2, _fw2 = min(with_share)[1]
                share_w, partner_w = share_w2, partner_w2
            elif share_f[0] is not None:
                share_w = share_f[0]
        return hhi_w, share_w, partner_w, f_w
    # لا ملخّص مُهيكل ولا حقيقة HHI رقمية — حصةُ الاحتياط الرقمية وحدها.
    return (None, share_f[0], None, share_f[1])


def _numeric_value_only(findings: list, metric: str,
                        lo: float, hi: float) -> tuple:
    """(القيمة، النتيجةُ مصدرُها) لنتيجةٍ **قيمتُها رقمٌ** بكلمة المؤشّر في
    ملاحظتها وضمن المدى — لا تحليلَ نصٍّ (عقد البند 1).

    C4 موجة #14 (الملاحظة 7): بين المطابقات تفوز **أحدثُ سنةِ حقيقة** (نفس
    قاعدة D5) لا أولُ وصول — حقيقةُ مرآة قديمة كانت قد تحجب مباشرةً أحدث
    كمرشحٍ منافس؛ السنة المجهولة أقدمُ من أي سنة، والوصولُ حاسمُ التعادل."""
    words = _KW.get(metric, ())
    best = None
    for order, f in enumerate(findings):
        val = _fv(f)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        note = _fnote(f)
        if words and not any(w.lower() in note.lower() for w in words):
            continue
        if lo <= float(val) <= hi:
            key = (-(_fact_year(f) or 0), order)
            if best is None or key < best[0]:
                best = (key, (float(val), f))
    return best[1] if best else (None, None)


def _named_companies(findings: list) -> "int | None":
    """عددُ المنافسين **المسمَّين** — لا كلُّ اكتشافٍ نصّيّ في البعثة.

    عدُّ كلِّ سلسلةٍ نصّية كان يحسب «HHI يقارب 940» شركةً، فيرتفع مدخلُ العمود
    ويبدو المشهدُ التنافسيّ مرصوداً أكثر ممّا هو. والمبالغةُ هنا ليست تجميلاً:
    `_pillar_competition` يقرؤه إشارةَ **تغطية**، فرقمٌ منتفخٌ يرفع الدرجة.

    `None` حين لا اسمَ واحداً — لا صفرٌ يُقرأ «سوقٌ بلا منافسين».
    """
    n = 0
    for f in findings:
        val = _fv(f)
        if not isinstance(val, str):
            continue
        text = val.strip()
        if len(text) <= 2:
            continue
        low = text.lower()
        if any(w in low for w in _METRIC_WORDS):
            continue
        digits = sum(ch.isdigit() for ch in text)
        if digits * 2 >= len(text):      # أغلبُه أرقام ⇒ ليس اسماً
            continue
        n += 1
    return n or None


def build_pillar_inputs(dr: dict, *, product_card: dict | None = None,
                        regulatory: dict | None = None) -> dict:
    """مدخلاتُ الأعمدة الخمسة من نتيجة البحث العميق — استخراجٌ لا حساب.

    `regulatory` هي حالةُ الحواجز البنيوية من الموجة C
    (`silk_requirements_agent.regulatory_state`) — منها تُقرأ **بوّابةُ الأهلية**
    التي كان `_pillar_regulatory` يتوقّعها ولا تصله على هذا المسار (R-03).
    """
    missions = (dr or {}).get("missions") or {}
    trade = _findings(missions, "trade_flow")
    comp = _findings(missions, "competitors")
    tariffs = _findings(missions, "tariffs_agreements")
    risk_f = _findings(missions, "risk_news") + _findings(missions, "logistics")
    econ = _findings(missions, "demographics_economy") + trade

    # البند 1 (أمر إصلاح المحرّك): HHI وحصةُ الأكبر من الملخّص المُهيكل
    # حصراً — الاستخراجُ النثريّ لهما هو الذي قلب الحكم 26%→84% (تقرير #11).
    s_hhi, s_top, s_partner, _s_f = _structured_competition(comp)
    # البند 3: «الحصة السعودية غير مرصودة» في اللوحة بينما الملخّص التنفيذي
    # يذكرها رقماً — حين يكون المهيمنُ سعودياً فحصتُه المُهيكلة (كومتريد،
    # نفس التشغيلة) هي الحصة السعودية بعينها؛ النثرُ احتياطٌ لا بديل.
    saudi_share = _numeric(trade, "saudi_share_pct")
    if saudi_share is None:
        # Same structured source used by build_components, even when the
        # Saudi supplier is not the dominant supplier (Factory A study 1).
        saudi_share, _ = _saudi_share_from_competitors(comp)
    _incumbent_saudi = bool(
        s_partner and not (s_partner.lower().startswith("unclassified")
                           or s_partner.isdigit())
        and any(t in s_partner.lower() for t in _INCUMBENT_SAUDI_TOKENS))
    if saudi_share is None and _incumbent_saudi and s_top is not None:
        saudi_share = s_top
    market = {
        "tam_usd": _numeric(trade, "tam_usd"),
        "import_cagr_pct": _numeric(trade, "import_cagr_pct"),
        "gdp_per_capita_usd": _numeric(econ, "gdp_per_capita_usd"),
        "saudi_share_pct": saudi_share,
    }
    # المُصدِّرُ المستهدف سعوديّ (فرضيةُ المنصّة): مهيمنٌ سعوديّ = دفاعُ
    # حصةٍ قائمة لا دخولٌ جديد — علمٌ مستقل، لا يُطوى في درجة المنافسة.
    # اسمٌ غيرُ محلول (رمزٌ خام/«Unclassified») = هويةٌ غير مرصودة ⇒ None،
    # لا نفيٌ واثق (مراجعة §58 — عقد عدم الاختلاق يشمل النفي).
    incumbent = None
    if s_partner and not (s_partner.lower().startswith("unclassified")
                          or s_partner.isdigit()):
        incumbent = _incumbent_saudi
    competition = {
        "hhi": s_hhi,
        "top_supplier_share_pct": s_top,
        "named_company_count": _named_companies(comp),
        "incumbent_is_self": incumbent,
    }
    reg_state = regulatory or {}
    entry_n = len(reg_state.get("all") or []) or None
    # البند 3: «وضوح قائمة الاشتراطات غير مرصود» بينما §7 يعرض جداول
    # اشتراطاتٍ كاملة — المرجعُ المقنَّن (CSV) قد لا يحمل صفوفاً لهذا
    # السوق بينما بعثةُ الاشتراطات رصدت بنوداً فعلية. عدُّ بنودها المرصودة
    # (قيمةٌ غير فارغة) احتياطُ وضوحٍ من نفس مخزن حقائق التشغيلة — عدٌّ
    # حتميّ لا تخمين، والمصدرُ يبقى معلَناً في أساس العمود.
    if not entry_n:
        reqs = _findings(missions, "customs_requirements")
        entry_n = sum(1 for f in reqs if _fv(f) is not None) or None
    regulatory_fit = {
        "tariff_applied_pct": _numeric(tariffs, "tariff_applied_pct"),
        "entry_requirements_count": entry_n,
        # **بوّابةُ الأهلية بنيويّةٌ لا نصّية** (R-03): تُقرأ من حالة الحواجز
        # التي بنتها الموجة C، لا بمطابقة عبارةٍ في نثرٍ قد يصوغها الكاتب بألف
        # صيغة. حاجزٌ صلبٌ مؤكَّدُ الانطباق وغيرُ محسوم = بوّابةٌ مفتوحة.
        "eligibility_gate": bool(reg_state.get("open_hard")),
    }
    card = product_card or {}
    profitability = {
        "border_unit_value_usd_kg": _numeric(trade, "border_unit_value_usd_kg"),
        # التكلفةُ رقمُ المصنع نفسه (E-04) — غيابُها فجوةُ إدخالٍ لا تُقدَّر.
        "cost_per_unit_usd": card.get("cost_per_unit"),
    }
    risk = {
        "political_stability_wgi": _numeric(risk_f + econ,
                                            "political_stability_wgi"),
        "regulatory_quality_wgi": _numeric(risk_f + econ,
                                           "regulatory_quality_wgi"),
        "logistics_lpi": _numeric(risk_f, "logistics_lpi"),
        # البند 3: من إلحاق `_augment_risk_news_fx` الحتمي — كان العمود
        # يستهلكه ولا يستخرجه أحد (غيابٌ بنيويّ دائم).
        "fx_volatility_pct": _numeric(risk_f, "fx_volatility_pct"),
    }
    return {"market_attractiveness": market,
            "competition_intensity": competition,
            "regulatory_fit": regulatory_fit,
            "profitability": profitability,
            "risk": risk}



# ── مكوّناتُ صفّ السوق · the row's per-metric components ──────────────────
#
# `build_view` يبني `components_detail` — سطرَ المصدر تحت كلّ رقم، ووسمَ القِدَم
# ذا الطبقتين — من `row["components"]` (`silk_render.py:2342`). وصفٌّ بلا
# `components` يُنتِج `components_detail: []`، فيبقى **حارسا الدرس ٨٨**
# (`X-03`) وتحذيرُ القِدَم (`S-01`) خامدَين **بشكلٍ آخر** حتى بعد إصلاح الجذر.
#
# أي أنّ `markets: []` لم يكن العائقَ الوحيد: الصفُّ يحتاج مكوّناتِه أيضاً.
# لذلك تُبنى هنا من **نفس** اكتشافات البعثات، بنفس عقد `DataPoint` الذي يقرؤه
# العرض — لا شكلٌ ثانٍ.

# اسمُ المكوّن في العرض ← (البعثةُ التي ترصده، مفتاحُ المؤشّر)
_COMPONENT_SOURCES = (
    ("market_size", "trade_flow", "tam_usd"),
    ("saudi_position", "trade_flow", "saudi_share_pct"),
    ("competition", "competitors", "hhi"),
    ("demand_capacity", "demographics_economy", "gdp_per_capita_usd"),
)


def _saudi_share_from_competitors(findings: list) -> tuple:
    """(حصة الشريك السعودي، نتيجتها) من **أفضل ملخّص مُهيكل يحمل صفاً
    سعودياً** لبعثة المنافسين — E2: مكوّن «saudi_position» كان يقرأ بعثة
    trade_flow حصراً فبقي «—» ثلاث دراسات والحصة 84.05% معروضة في السرد من
    هذا الملخّص نفسه. C4 موجة #14 (الملاحظة 1): البحث مستقلٌّ عن فائز HHI —
    فوزُ حقيقةٍ رقمية بلا موردين كان يُسقِط حصةً سعودية مرصودة في ملخّصٍ
    مرآة. المفاضلة بين الملخّصات الحاملة: المباشرُ ثم الأحدثُ سنةً ثم
    الوصول، والإسناد من النتيجة الحاملة نفسها. لا استخراج نثرياً (عقد
    البند 1)؛ غياب الصف في كل الملخّصات = (None, None)."""
    best = None
    for order, f in enumerate(findings):
        v = _fv(f)
        if not isinstance(v, dict):
            continue
        for row in (v.get("top_suppliers") or []):
            if not isinstance(row, dict):
                continue
            p = str(row.get("partner") or "")
            if not ("سعود" in p or "saudi" in p.lower()):
                continue
            try:
                s = float(row["share"]) if row.get("share") is not None \
                    else None
            except (TypeError, ValueError):
                continue
            if s is None or not (0.0 <= s <= 100.0):
                continue
            src = str(f.get("source") if isinstance(f, dict)
                      else getattr(f, "source", "") or "")
            mirrored = ("مرآة" in src or "mirror" in src.lower()
                        or "مرآة" in _fnote(f))
            try:
                year = int(v.get("year") or 0) or _fact_year(f)
            except (TypeError, ValueError):
                year = _fact_year(f)
            key = (0 if not mirrored else 1, -(year or 0), order)
            if best is None or key < best[0]:
                best = (key, (s, f))
            break
    return best[1] if best else (None, None)


def build_components(dr: dict) -> dict:
    """مكوّناتُ الصفّ من البعثات — كلُّ مكوّنٍ نقطةٌ بمصدرها وسنتها.

    المكوّنُ غيرُ المرصود **يُدرَج بقيمة `None`** لا يُحذَف: العرضُ يحسب
    `components_present` منها، وحذفُ الغائب يجعل التغطيةَ تبدو كاملةً دائماً —
    وهو بعينه العطلُ الذي عالجته الموجة B في تغطية المصادر.
    """
    missions = (dr or {}).get("missions") or {}
    out: dict = {}
    for comp_name, mission_key, metric in _COMPONENT_SOURCES:
        findings = _findings(missions, mission_key)
        comp_src_f = None
        if comp_name == "competition":
            # نفس عقد البند 1: HHI من الملخّص المُهيكل — جدول «مكوّنات أفضل
            # سوق» عرض 84.05 (حصةً) تحت اسم المنافسة (تقرير #11). الإسنادُ
            # (المصدر/السنة) من **نفس** النتيجة التي أعطت الرقم — لا من أول
            # نتيجةٍ تطابق الكلمة (مراجعة §58: رقمُ كومتريد كان قد يُنسَب
            # لمصدر «بحث ويب» وسنةٍ أخرى — خرقُ عقد الإسناد لكل رقم).
            value, _sh, _pt, comp_src_f = _structured_competition(findings)
        elif comp_name == "saudi_position":
            # E2 (الدراسة الحية الرابعة — «—» ثلاث دراسات متتالية): بعثة
            # trade_flow لا تُنتج فعلياً حقيقة «saudi_share_pct» رقمية،
            # بينما الحصة السعودية تعيش في الملخّص المُهيكل لبعثة المنافسين
            # (top_suppliers) — الاحتياط يقرؤها من هناك بنفس عقد الإسناد
            # (المصدر/السنة/الثقة من النتيجة الفائزة نفسها).
            value, comp_src_f = _numeric_with_source(findings, metric)
            if value is None:
                value, comp_src_f = _saudi_share_from_competitors(
                    _findings(missions, "competitors"))
        else:
            # D5 (دراسة #12): القيمة والإسناد من **النتيجة الفائزة نفسها**
            # (أحدث سنة حقيقة) — حلقةُ إعادة البحث بأول مطابقة كلمةٍ كانت
            # قد تنسب رقمَ 2024 لمصدر/سنة نتيجةٍ أخرى (خرق عقد الإسناد).
            value, comp_src_f = _numeric_with_source(findings, metric)
        src, year, note, conf = "", None, "", None
        if comp_src_f is not None:
            src = (comp_src_f.get("source") if isinstance(comp_src_f, dict)
                   else getattr(comp_src_f, "source", "")) or ""
            year = (comp_src_f.get("data_year") if isinstance(comp_src_f, dict)
                    else getattr(comp_src_f, "data_year", None))
            note = _fnote(comp_src_f)
            try:
                conf = float(comp_src_f.get("confidence")
                             if isinstance(comp_src_f, dict)
                             else getattr(comp_src_f, "confidence", None))
            except (TypeError, ValueError):
                conf = None
        out[comp_name] = {
            "value": value, "source": src, "note": note,
            "data_year": year,
            # D5: ثقةُ المكوّن ثقةُ نتيجته الفائزة (0.9 مباشر / 0.6 مرآة) —
            # الحرفية 0.6 كانت تمحو إشارةَ الجودة الوحيدة المتاحة؛ الغائب
            # صفرٌ كما هو، ولا تُخترَع قيمةٌ حين لا ثقةَ على النتيجة.
            "confidence": (max(0.0, min(1.0, conf))
                           if (value is not None and conf is not None)
                           else (0.6 if value is not None else 0.0)),
            "status": "" if value is not None else "no_record",
        }
    return out


def coverage_of(dr: dict) -> float:
    """تغطيةُ البعثات — نسبةُ ما نجح منها فعلاً، لا عددُها المُعلَن.

    `decide` يضرب بها نسبةَ الأعمدة المحسوبة فتخرج الثقةُ **معلَنةَ الأساس**
    (لا رقمٌ حدسيّ). بعثةٌ فاشلةٌ تخفض الثقةَ بحقّ.
    """
    missions = (dr or {}).get("missions") or {}
    if not missions:
        return 0.0
    ok = 0
    for m in missions.values():
        failed = (m.get("failed") if isinstance(m, dict)
                  else getattr(m, "failed", True))
        if failed is False:
            ok += 1
    return round(ok / len(missions), 3)


def decide_for_deep(dr: dict, *, product_card: dict | None = None,
                    regulatory: dict | None = None,
                    weights_option: str | None = None) -> "dict | None":
    """شغّل **محرّك القرار الواحد** على مخرجات المسار العميق.

    لا منطقَ قرارٍ هنا: تُبنى الحزمةُ ثمّ يُنادى `silk_decision.decide` نفسُه
    الذي يخدم `/analyze`. أيُّ عطلٍ يعيد `None` فيبقى السطحُ كما كان — إضافةٌ
    لا شرطُ تشغيل.
    """
    try:
        import silk_decision
    except Exception as exc:  # noqa: BLE001
        log.warning("decision engine unavailable: %s", exc)
        return None
    try:
        bundle = {"pillar_inputs": build_pillar_inputs(
            dr, product_card=product_card, regulatory=regulatory),
            "coverage": coverage_of(dr)}
        return silk_decision.decide(bundle, weights_option)
    except Exception as exc:  # noqa: BLE001 — القرارُ إضافةٌ لا يُسقِط تشغيلة
        log.warning("deep decision failed: %s", exc)
        return None


def promote_engine_verdict(verdict: dict,
                           decision: "dict | None") -> dict:
    """قدِّم حكمَ المحرّك الحتميّ في قاموس الحكم — والتغطيةُ تبقى مُعلَنة.

    `JuryCommittee` يقيس **تغطيةَ الأدلة** لا جاذبيةَ السوق (الموجة B،
    البند V-01)، ومع ذلك كان مُخرَجُه هو ما يُشتَقّ منه غلافُ التقرير
    والمختصر وسردُ الكاتب. هنا يصير حقلُ الحكم حكمَ `silk_decision` —
    المحرّكَ الموزون الوحيد — وتُحفَظ قراءةُ التغطية بجواره
    (`coverage_verdict`/`coverage_state`/`coverage_basis`) فلا تُفقَد ولا
    تُقدَّم توصيةً تجارية.

    بلا قرارٍ من المحرّك: يُعاد القاموسُ **كما هو حرفياً** — تكافؤٌ رجعيّ
    تامّ مع ما قبل هذه الموجة (بما فيه `basis="data_coverage"` الذي تقرؤه
    `silk_render._coverage_basis_tone`).
    """
    v = dict(verdict or {})
    eng = str((decision or {}).get("verdict") or "").strip()
    if not eng or (decision or {}).get("error"):
        return v
    v["coverage_verdict"] = v.get("verdict")
    v["coverage_basis"] = v.get("basis")
    v["verdict"] = eng
    v["confidence"] = (decision or {}).get("confidence")
    # `basis` لم يعد «تغطيةَ أدلة»: الحكمُ صادرٌ عن المحرّك الموزون،
    # فتبقى تسميتُه التجارية على كلّ سطح (`_coverage_basis_tone`).
    v["basis"] = "silk.decision/v1"
    v["decision_score"] = (decision or {}).get("score")
    # **ولا يُمسّ `note`.** كان يُستبدَل بـ`why` المحرّك، فتسقط بصمتٍ عبارةُ
    # الجورية «تنبيه: قرار مبدئي والنواقص معلّمة لا مُخمّنة» — وهي نفسُها ما
    # تطبعه أربعةُ مُصدِّرات نثرَ أساسِ القرار حين تغيب قراءةُ المرحلة ٢ (بلا
    # مفتاح، أو سقفٌ نافد، أو تشغيلةٌ متدهورة). أي أنّ الترقيةَ كانت تحذف
    # تحفّظَ عدمِ الاختلاق من التقرير المُسلَّم. سببُ المحرّك يُحفَظ في حقلٍ
    # خاصّ ويُعرَض في قسم أساس الحكم (مراجعةٌ ذاتية §٥٨).
    v["decision_why"] = (decision or {}).get("why") or ""
    # Carry the canonical panel's gaps to the writer; do not recalculate them.
    v["decision_missing_components"] = list(dict.fromkeys(
        str(component)
        for pillar in ((decision or {}).get("pillars") or {}).values()
        if isinstance(pillar, dict)
        for component in (pillar.get("missing") or [])))
    return v
