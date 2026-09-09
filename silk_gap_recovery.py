"""طبقة سد الفجوات — the gap recovery layer (المرحلة 0، أمر تنفيذي 2026-08-19).

> **الغرض.** معظم «الفجوات المعلنة» في تقرير `/research` ليست فجوات بيانات بل
> فشل استرجاع (مؤشرات WGI منشورة علناً، نصيب الفرد من FAOSTAT، حصص الدول
> والأوزان موجودة في نفس استجابة Comtrade، حدّ معدل Google Trends). هذه الطبقة
> تعمل **مرة واحدة** بعد انتهاء كل البعثات وقبل المحلل/الكاتب/العرض: تصنّف كل
> فجوة، ثم تلاحقها عبر مسار استرجاع متدرّج، وتكتب المسترجَع في تقرير بعثته.
>
> **Purpose.** Runs ONCE after all missions complete and before analyst/writer/
> view: classifies every declared gap, chases it through an escalating recovery
> ladder, and writes recovered facts back into the mission report.

**القيود الحاكمة (من الأمر التنفيذي — غير قابلة للتفاوض):**
- إضافية بالكامل: لا تعديل على أي وكيل قائم ولا على عقد البيانات؛ لا تُستدعى
  من داخل أي وكيل (اختبار AST يحرس ذلك).
- خلف صمّام واحد `SILK_GAP_RECOVERY_ENABLED` (افتراضياً مُطفأ — LESSONS 70).
- لا حجب: فشلها الكلي = مسار اليوم حرفياً (النداء في api.py داخل try/except).
- لا اختلاق: تسترجع من المصدر أو تشتق بقاعدة معلنة (`مستنتَج` + معادلة)؛
  لا رقم تقديري من نموذج إطلاقاً.
- سقوف صلبة: `SILK_GAP_MAX_ATTEMPTS` (3)، `SILK_GAP_MAX_WEB_SEARCH` (5)،
  `SILK_GAP_TIMEOUT_S` (180).

**التصنيف (§2 من الأمر):** OPS (عطل تشغيلي — سجل المشغّل فقط، ممنوع في
التقرير)، RATE (حد معدل — إعادة محاولة)، FIELD (الحقل موجود في مصدر جُلب
فعلاً)، DERIVE (يُشتق حسابياً بقاعدة معلنة)، FETCH (ناشر بديل من
`FALLBACK_ROUTES`)، PAID (خلف اشتراك — يبقى معلناً)، NONE (فجوة حقيقية).

**مسار الاسترجاع (§3):** م١ إعادة محاولة متصاعدة ← م٢ توسيع استعلام نفس
المصدر ← م٣ اشتقاق حسابي معلَن ← م٤ ناشر/نقطة نهاية بديلة ← م٥ بحث ويبي
موجّه (الوحيد الذي يستهلك نماذج؛ أولوية 1–2 فقط وتحت السقف).

المكتبات: stdlib + وحدات الريبو؛ استيراد كسول لكل ما يلمس الشبكة.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

# ── الصمّام والسقوف · valve + hard caps ─────────────────────────────────────

FLAG = "SILK_GAP_RECOVERY_ENABLED"


def enabled() -> bool:
    """صمّام LESSONS 70 — مُطفأ افتراضياً؛ تفعيله قرار مالك منفصل."""
    return os.environ.get(FLAG, "0").strip() == "1"


def _cap(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default



# ── تفعيلٌ **جزئيّ** بصمّامٍ لكلّ صنف (الموجة C، §٦ من `docs/ENGINE_AUDIT.md`) ──
#
# أمرُ المالك حرفياً: «لا تُفعِّلها عمياء». فالصمّامُ العامّ `FLAG` يبقى كما هو
# (البند ٧٠: تفعيلُه قرارُ مالكٍ منفصل)، ويُضاف **تحته** صمّامٌ لكلّ مُستَرِدّ
# بافتراضٍ يتبع تصنيفَه في §٦:
#
#   يجوز آلياً        — استعلامٌ حتميٌّ من **نفس** المصدر الرسميّ الذي كان
#                       سيستعمله الوكيل، بلا استنتاج. افتراضُه ON تحت الصمّام.
#   يحتاج دليلاً      — كياناتٌ مسمّاة أو إشارةٌ بديلة عن الحقيقة. افتراضُه
#                       OFF حتى يُشحَن وسمُها الصريح.
#   يبقى UNKNOWN      — مصدريّةٌ غير محدودة. **مطفأٌ بنيوياً، لا صمّامَ له.**
#
# ولا مفتاحَ واحدٌ يفتحها جميعاً: فتحُ الحتميّ لا يجرّ فتحَ ما يحتاج دليلاً.
_DETERMINISTIC_RECOVERERS = ("wgi", "per_capita", "partner_shares", "tariff")
_EVIDENCE_RECOVERERS = ("seasonality", "distributors")
# `web_search` غيرُ مذكورٍ عمداً: لا صمّامَ له — يُرفَض في `recoverer_enabled`.

RECOVERED_METHOD = "recovered"


def recoverer_enabled(name: str) -> bool:
    """هل يُسمَح لهذا المُستَرِدّ بالعمل؟ — صمّامٌ لكلّ صنف، لا مفتاحٌ واحد.

    `web_search` يعيد `False` **دائماً** ولا يقرأ بيئةً إطلاقاً: ملءُ فجوةٍ
    معلنة من نصّ ويبٍ عشوائيّ هو بالضبط ما يحظره عقدُ التأسيس، ومفتاحٌ يفتحه
    خطأٌ في التصميم لا خيارُ تشغيل.
    """
    if not enabled():
        return False
    key = str(name or "").strip().lower()
    if key == "web_search":
        return False
    if key in _DETERMINISTIC_RECOVERERS:
        default = "1"
    elif key in _EVIDENCE_RECOVERERS:
        default = "0"
    else:
        return False        # مُستَرِدٌّ غيرُ مصنَّف لا يعمل — لا افتراضَ متساهل
    return os.environ.get(
        f"SILK_GAP_RECOVER_{key.upper()}", default).strip() == "1"


def mark_recovered(dp, derivation: str = ""):
    """اختِم النقطةَ المُستَردّة — «مُستَردّ» يظهر في سطر المصدر لا في الصمت.

    القيمةُ لا تتغيّر (عقد عدم الاختلاق)؛ يتغيّر **ما يُقال عنها**: أنّها جاءت
    من محاولةٍ ثانية بعد إخفاق الأولى، أو أنّها محسوبةٌ لا منقولة. عرضُها بلا
    وسمٍ كان سيجعلها تبدو رصداً مباشراً — وهو ادّعاءُ منشأٍ لم يحدث.
    """
    try:
        dp.retrieval_method = RECOVERED_METHOD
        extra = f"مُستَردّ — {derivation}" if derivation else "مُستَردّ"
        note = str(getattr(dp, "note", "") or "")
        if "مُستَردّ" not in note:
            dp.note = f"{note} | {extra}".strip(" |")
    except Exception:  # noqa: BLE001 — الوسمُ لا يُسقِط الاسترداد
        pass
    return dp


# ── تصنيف الفجوة · gap taxonomy (§2) ────────────────────────────────────────

OPS, RATE, FIELD, DERIVE, FETCH, PAID, NONE = (
    "OPS", "RATE", "FIELD", "DERIVE", "FETCH", "PAID", "NONE")

def _load_producer_needles() -> tuple:
    """نصوص فشل الاسترجاع من وحدة المنتِج نفسها (LESSONS 89) — لا نسخة يدوية
    تتحجّر. الفشل في الاستيراد = حدّ أدنى صادق لا صمت كامل."""
    try:
        from silk_data_layer import RETRIEVAL_FAILURE_NEEDLES
        return tuple(RETRIEVAL_FAILURE_NEEDLES)
    except Exception:  # noqa: BLE001
        return ("فشل", "تعذّر", "fetch_failed")


_PRODUCER_FAILURE_NEEDLES = _load_producer_needles()
# «429» رمز حالة قائم بذاته لا جزء من رقم/سنة ($429M، 1429هـ) — النمط الحدّي
# نفسه المستعمل في تصنيف G1–G4، مستورَداً لا منسوخاً.
try:
    from silk_data_layer import _GAP_429_RE as _RATE_RE
except Exception:  # noqa: BLE001
    _RATE_RE = re.compile(r"(?<![\d$])429(?![\dهM])")

# أنماط التصنيف — تُفحص بالترتيب؛ أول مطابقة تحكم.
_CLASS_PATTERNS = [
    # PAID قبل OPS عمداً: فجوة مدفوعة تذكر مفتاحها تبقى «معلنة» للعميل
    # (عقد الطبقة)، لا تُحذف بوصفها عطلاً تشغيلياً.
    (PAID, ("الطبقة المدفوعة", "اشتراك مدفوع", "خلف اشتراك", "مصدر مدفوع")),
    (OPS, ("غير مضبوط", "غير مُهيَّأ", "لم يُهيَّأ", "no_key", "مفتاح API",
           "API key not", "خطأ إعداد")),
    (RATE, ("حد المعدل", "حدّ المعدل", "rate limit", "Retry-After",
            "تجاوز عدد الطلبات")),   # «429» بالنمط الحدّي أدناه لا بالاحتواء
    (DERIVE, ("نصيب الفرد", "للفرد", "per capita", "per-capita")),
    (FIELD, ("حصص الدول", "حصص المورد", "الأوزان", "بالأطنان", "netWgt",
             "الوزن الصافي", "partner")),
    # نصوص الفشل **مستوردة من المنتِج** (`silk_data_layer`) لا منسوخة يدوياً:
    # الإبرة المنسوخة «خطأ في واجهة» لم تطابق يوماً نصّاً إنتاجياً («البنك
    # الدولي أعاد خطأ API: …») فصُنِّفت الفجوة NONE وتُخطّيت صامتة رغم أن
    # العلم مفعَّل (حادثة الحليب–الأردن 2026-08-19 — LESSONS 89).
    # §6: فجوةُ الموزّعين/جهاتِ الاتصال — بياناتٌ منشورةٌ يلزمها استرجاع،
    # وكانت تُصنَّف NONE فتُتخطّى («كيان واحد بدل عشرة» في بلاغ المالك).
    (FETCH, ("موزع", "موزّع", "مستورد", "جهات اتصال", "جهات الاتصال",
             "الاستقرار السياسي", "سيادة القانون", "الجودة التنظيمية",
             "الحوكمة", "WGI", "FAOSTAT") + _PRODUCER_FAILURE_NEEDLES),
]


def classify(text: str, status: str = "") -> str:
    blob = f"{text or ''} {status or ''}"
    for cat, needles in _CLASS_PATTERNS:
        # «429» بالنمط الحدّي يُفحَص **بعد** PAID/OPS و**قبل** عائلة الفشل
        # العامة: «موسمية رمضان تعذّرت (429)» حدُّ معدلٍ لا فشلُ جلب — وإبرةُ
        # «تعذّر» العامة كانت تسبقه فتحوّلها FETCH بلا إعادة محاولة. وترتيبُ
        # PAID/OPS محفوظ (الدرس ٨١: عطلٌ تشغيليّ يبقى OPS).
        if cat == DERIVE and _RATE_RE.search(blob):
            return RATE
        if any(n in blob for n in needles):
            return cat
    if _RATE_RE.search(blob):
        return RATE
    if status == "fetch_failed":
        return FETCH
    return NONE


# ── أولوية الصرف · spend priority (§5) ──────────────────────────────────────

_P1 = ("تعرفة", "التعرفة", "حجم السوق", "حصص", "سعر", "أسعار", "متطلبات",
       "اشتراطات",
       # §5/§6: جهاتُ الاتصال أولويةُ ١ — بلا موزّعٍ لا تنفيذَ للقرار.
       "موزع", "موزّع", "مستورد", "جهات اتصال", "جهات الاتصال")
_P2 = ("موسمية", "رمضان", "لوجستيات", "شحن", "استهلاك", "الطلب")


def priority(text: str) -> int:
    t = text or ""
    if any(n in t for n in _P1):
        return 1
    if any(n in t for n in _P2):
        return 2
    return 3


# ── بنية بند الفجوة · gap item ──────────────────────────────────────────────

@dataclass
class GapItem:
    mission_key: str
    text: str
    category: str = NONE
    prio: int = 3
    recovered: bool = False
    route: str = ""           # م١..م٥ التي نجحت (أو آخر ما جُرِّب)
    attempts: int = 0
    tried: list = field(default_factory=list)


# نفس تعبير الرندر (silk_render._GAPS_RE) — نسخة محلية كي يبقى استيراد
# الرندر هنا كسولاً واختيارياً (المُطهِّر وحده، تحسيناً لا شرطاً)؛ اختبار
# الأقفال يفشل إن تباعد التعبيران عن شكل «| فجوات:» الموحّد.
_GAPS_RE = re.compile(r"فجوات:\s*([^|]*)")

# مؤشرات WGI الستة (silk_data_layer._WB_INDICATOR_SOURCE — source=3).
_WGI = {
    "PV.EST": "الاستقرار السياسي", "RL.EST": "سيادة القانون",
    "RQ.EST": "الجودة التنظيمية", "GE.EST": "فعالية الحكومة",
    "CC.EST": "ضبط الفساد", "VA.EST": "الصوت والمساءلة",
}

# سجل البدائل (§3 م٤) — نقاط نهاية بديلة **لناشرين معتمدين أصلاً** حصراً
# (استثناء الضمانات المعتمد، تعديل مالك ٣). كل مدخلة: وصف المسار البديل.
FALLBACK_ROUTES = {
    "World Bank/WGI": "world_bank(iso3, ind, year=None) — أحدث سنة غير فارغة (source=3)",
    "World Bank": "world_bank(iso3, ind, year=None) — إسقاط قيد السنة",
    "UN Comtrade": "comtrade_trade(partner='all') — نفس النداء بحقول الشركاء والأوزان",
    # التعرفة: سلسلة التراجع المعتمدة أصلاً (WTO TTD → WITS) — ناشران
    # معتمدان، لا واجهة جديدة (نطاق استثناء الضمانات).
    "التعرفة": "tariff_with_fallback(hs, market, partner) — WTO TTD ← WITS",
    # §6 من الأمر التنفيذي: مساراتٌ ثلاثةٌ لا تلمسها الخرائط — غرفةُ تجارة
    # بلد الوجهة، وأدلّةُ الشركات المحلية، وصفحاتُ «موزّعونا» في مواقع
    # العلامات المنافسة (وهي غالباً تسرد الموزّع المحلي بالاسم صراحةً).
    "الموزعون": ("بحث موجَّه: غرفة التجارة + أدلّة الشركات + صفحات "
                 "«موزّعونا» لدى العلامات المنافسة"),
}

# قوالبُ استعلامِ الموزّعين (§6) — بلغة السوق والعربية والإنجليزية معاً.
_DISTRIBUTOR_QUERIES = (
    "{prod} distributors {country}",
    "\"our distributors\" {prod} {country}",
    "\"where to buy\" {prod} {country} distributor",
    "chamber of commerce {country} food importers directory",
    "موزعو {prod} في {country_ar}",
    "دليل شركات استيراد الأغذية {country_ar}",
)


def _gap_clauses(summary: str) -> list[str]:
    m = _GAPS_RE.search(summary or "")
    if not m:
        return []
    return [g.strip() for g in m.group(1).split("؛") if g.strip()]


def _drop_clause(summary: str, clause: str) -> str:
    """يحذف فجوة واحدة من مقطع «| فجوات:» في الملخّص؛ إن خلا المقطع أُزيل."""
    m = _GAPS_RE.search(summary or "")
    if not m:
        return summary
    remaining = [g for g in _gap_clauses(summary) if g != clause]
    head = summary[:m.start()].rstrip().rstrip("|").rstrip()
    tail = summary[m.end():]
    if remaining:
        return f"{head} | فجوات: {'؛ '.join(remaining)}{tail}"
    return f"{head}{tail}"


def _append_finding(report, dp) -> None:
    findings = report.findings if not isinstance(report, dict) else report.setdefault("findings", [])
    findings.append(dp)


def _raw_failed_findings(report) -> list[dict]:
    """بنود بلا قيمة من تقرير بعثة/وكيل — بشكليها (كائن DataPoint أو قاموس).

    السطح الخام الذي كان محجوباً عن المصنّف: `status`/`note` الحقيقيان بدل
    ما تطوّع الكاتب بذكره في نثر الملخّص.
    """
    out: list[dict] = []
    findings = (report.get("findings") if isinstance(report, dict)
                else getattr(report, "findings", None)) or []
    for f in findings:
        if isinstance(f, dict):
            value, status, note = f.get("value"), f.get("status"), f.get("note")
            metric = f.get("metric") or f.get("name")
        else:
            value = getattr(f, "value", None)
            status = getattr(f, "status", "")
            note = getattr(f, "note", "")
            metric = getattr(f, "metric", "") or getattr(f, "name", "")
        if value is None:
            out.append({"metric": metric or "", "note": note or "",
                        "status": status or ""})
    return out


def _summary_get(report) -> str:
    return report.get("summary", "") if isinstance(report, dict) else getattr(report, "summary", "")


def _summary_set(report, value: str) -> None:
    if isinstance(report, dict):
        report["summary"] = value
    else:
        report.summary = value


# ── المسترجِعات الحتمية · deterministic recoverers (م١–م٤) ──────────────────

def _recover_wgi(item: GapItem, report, market_ref, deadline: float) -> bool:
    """م٤ — مؤشرات الحوكمة من نقطة النهاية البديلة (source=3، year=None)."""
    from silk_data_layer import world_bank
    wanted = [(ind, label) for ind, label in _WGI.items() if label in item.text] \
        or list(_WGI.items())
    got = 0
    for ind, label in wanted:
        if time.monotonic() >= deadline:
            break
        dp = world_bank(market_ref.iso3, ind, year=None)
        if getattr(dp, "value", None) is not None:
            dp.note = (f"{label} — {dp.note} · استُرجع عبر طبقة سد الفجوات "
                       f"(م٤: {FALLBACK_ROUTES['World Bank/WGI']})").strip(" ·")
            _append_finding(report, dp)
            got += 1
    return got > 0


def _recover_tariff(item: GapItem, report, market_ref, hs_code, year,
                    deadline: float) -> bool:
    """م٤ — التعرفة عبر سلسلة التراجع المعتمدة (WTO TTD ← WITS)."""
    if time.monotonic() >= deadline:
        return False
    from silk_tariffs_agent import tariff_with_fallback
    dp = tariff_with_fallback(str(hs_code), market_ref.iso3, "SAU", year)
    if getattr(dp, "value", None) is None:
        return False
    dp.note = (f"{dp.note} · استُرجع عبر طبقة سد الفجوات "
               f"(م٤: {FALLBACK_ROUTES['التعرفة']})").strip(" ·")
    _append_finding(report, dp)
    return True


def _recover_seasonality(item: GapItem, report, product: str, market_ref,
                         deadline: float) -> bool:
    """م١ — الموسمية بعد حدّ المعدل: نفسُ وكيل الاتجاهات بإعادةِ محاولته
    المتصاعدة الداخلية. حدُّ المعدل ليس فجوةَ بيانات (§2 من الأمر)."""
    if time.monotonic() >= deadline:
        return False
    try:
        from silk_trends_agent import trends_interest_resilient
    except Exception:  # noqa: BLE001 — الوكيل غير متاح = لا مسار
        return False
    geo = (getattr(market_ref, "iso2", "") or "").upper() or None
    dps = [trends_interest_resilient(product or "", geo=geo)]
    got = 0
    for dp in dps:
        if getattr(dp, "value", None) is None:
            continue
        dp.note = (f"{getattr(dp, 'note', '')} · استُرجع عبر طبقة سد الفجوات "
                   "(م١: إعادة محاولة بعد حدّ المعدل)").strip(" ·")
        _append_finding(report, dp)
        got += 1
    return got > 0


def _recover_distributors(item: GapItem, report, market_ref, product: str,
                          deadline: float) -> bool:
    """§6 — الموزّعون: مساراتٌ لا تصلها الخرائط (غرفة التجارة، أدلّة الشركات،
    صفحات «موزّعونا» لدى المنافسين). يعيد **مرشّحين معلَني الحالة**: الإدراج
    يثبت الوجودَ وجهةَ الاتصال فقط، لا نشاطَ الاستيراد (عقد الطبقة)."""
    if time.monotonic() >= deadline:
        return False
    from silk_websearch_agent import web_search
    country = (getattr(market_ref, "name_en", "") or "").strip()
    country_ar = (getattr(market_ref, "name_ar", "") or country).strip()
    gl = (getattr(market_ref, "iso2", "") or "").lower() or None
    found = 0
    for tpl in _DISTRIBUTOR_QUERIES:
        if time.monotonic() >= deadline:
            break
        q = tpl.format(prod=product or "", country=country,
                       country_ar=country_ar).strip()
        for dp in (web_search(q, num=5, gl=gl) or []):
            val = getattr(dp, "value", None)
            if not isinstance(val, dict) or not val.get("link"):
                continue
            dp.note = (f"مرشّح موزّع من بحث موجَّه — {q} · "
                       "الإدراج يثبت الوجود وجهة الاتصال فقط، لا نشاط "
                       "الاستيراد (يحتاج تحققاً تجارياً)").strip()
            _append_finding(report, dp)
            found += 1
    return found > 0


def _recover_partner_shares(item: GapItem, report, market_ref, hs_code, year,
                            deadline: float) -> bool:
    """م٢ — حصص الدول المورّدة والأوزان من نفس نداء Comtrade (partner='all')."""
    if not hs_code or not year or time.monotonic() >= deadline:
        return False
    from silk_data_layer import DataPoint, comtrade_trade, primary_value, primary_qty
    recs = comtrade_trade(hs_code, market_ref.m49, year, flow="M", partner="all")
    if not recs:
        return False
    rows = []
    for r in recs:
        # استبعاد صفوف الشريك المجمَّع (partnerCode 0 = العالم) — جمعها في
        # المقام يضاعف الإجمالي ويُنصِّف كل حصة حقيقية (مراجعة §58).
        code = str(r.get("partnerCode", "")).strip()
        if code in ("0", "WLD") or r.get("partnerDesc") == "World":
            continue
        v = primary_value(r)
        if v is None:
            continue
        rows.append((r.get("partnerDesc") or code, v, primary_qty(r)))
    if not rows:
        return False
    total = sum(v for _, v, _ in rows) or 1.0
    rows.sort(key=lambda t: -t[1])
    for name, v, qty in rows[:8]:
        share = round(100.0 * v / total, 1)
        qty_txt = f"؛ الوزن الصافي {qty:,.0f} كجم" if qty else ""
        _append_finding(report, DataPoint(
            value=share, source="UN Comtrade",
            confidence=0.8,
            note=(f"حصة {name} من واردات {market_ref.name_ar or market_ref.name_en} "
                  f"لعام {year} (٪ من القيمة){qty_txt} · استُرجع عبر طبقة سد "
                  f"الفجوات (م٢: توسيع استعلام نفس المصدر)"),
            retrieved_at=time.strftime("%Y-%m-%d"), data_year=int(year)))
    return True


def _recover_per_capita(item: GapItem, report, market_ref, deadline: float,
                        all_reports: dict | None = None) -> bool:
    """م٣ — اشتقاق نصيب الفرد: الواردات ÷ السكان، مُعلَّم «مستنتَج» بمعادلته.

    يبحث عن رقم الواردات في **كلّ البعثات** لا بعثةِ الفجوة وحدها: الفجوة
    تُعلَن في بعثة الاستهلاك بينما الإجمالي يعيش في بعثة حجم السوق، فكان
    الاشتقاق يفشل دائماً وتبقى الفجوة رغم توفّر طرفَي المعادلة (بلاغ
    الحليب–الأردن: «نصيب الفرد» ظلّ معلَناً بلا سبب).
    """
    if time.monotonic() >= deadline:
        return False
    pool = []
    for rep in (all_reports or {}).values():
        pool += (rep.findings if not isinstance(rep, dict)
                 else rep.get("findings", [])) or []
    own = (report.findings if not isinstance(report, dict)
           else report.get("findings", [])) or []
    imports_dp = None
    for f in list(own) + [x for x in pool if x not in own]:
        note = getattr(f, "note", "") or ""
        # الإجمالي فقط — لا نِسَب الحصص («حصة X من واردات…») ولا المشتقات؛
        # قسمة نسبة مئوية على السكان تُنتج رقماً بلا معنى (مراجعة §58).
        if getattr(f, "value", None) is None:
            continue
        if "حصة" in note or "٪" in note or "%" in note or "مستنتَج" in note:
            continue
        if "إجمالي" in note and ("واردات" in note or "استيراد" in note):
            imports_dp = f
            break
    if imports_dp is None:
        return False
    from silk_data_layer import DataPoint, world_bank
    pop = world_bank(market_ref.iso3, "SP.POP.TOTL", year=None)
    if getattr(pop, "value", None) in (None, 0):
        return False
    per_cap = round(float(imports_dp.value) / float(pop.value), 3)
    _append_finding(report, DataPoint(
        value=per_cap, source=f"{imports_dp.source} + World Bank",
        confidence=min(getattr(imports_dp, "confidence", 0.6) or 0.6, 0.6),
        note=("نصيب الفرد (دولار/فرد من قيمة الواردات) — مستنتَج: الواردات ÷ السكان "
              f"({imports_dp.value:,} ÷ {pop.value:,.0f}) · استُرجع عبر طبقة "
              "سد الفجوات (م٣: اشتقاق حسابي معلَن)"),
        retrieved_at=time.strftime("%Y-%m-%d"),
        data_year=getattr(imports_dp, "data_year", None)))
    return True


def _retry_backoff(fn, attempts: int, deadline: float,
                   delays=(2.0, 8.0, 30.0)):
    """م١ — إعادة محاولة متصاعدة تحت السقفين (محاولات + مهلة الطبقة)."""
    last = None
    for i in range(attempts):
        if time.monotonic() >= deadline:
            break
        try:
            out = fn()
            if out:
                return out
        except Exception as e:  # فشل محاولة ≠ فشل الطبقة
            last = e
        if i < attempts - 1:
            wait = delays[min(i, len(delays) - 1)]
            if time.monotonic() + wait >= deadline:
                break
            time.sleep(wait)
    return None


# ── م٥ — بحث ويبي موجّه (الوحيد الذي يستهلك نماذج) ─────────────────────────

def _web_search_recover(item: GapItem, report, market_ref, product: str,
                        hs_code, deadline: float) -> bool:
    import silk_context
    if silk_context.ai_extras_blocked():
        return False
    try:
        from silk_ai_judge import available
        if not available():
            return False
    except Exception:
        return False
    if time.monotonic() >= deadline:
        return False
    from silk_llm_runtime import run_llm_agent
    mission = {
        "key": "gap_recovery",
        "name": "سد فجوة محددة",
        "instructions": (
            "استرجع البيان المفقود التالي حصراً، من مصدر رسمي منشور، "
            "مع الاستشهاد الإلزامي بالمصدر والسنة. البيان المفقود: "
            f"«{item.text}». المنتج: {product or '—'}؛ الرمز: {hs_code or '—'}؛ "
            f"السوق: {market_ref.name_ar or market_ref.name_en}. "
            "إن لم تجد رقماً منشوراً مسنوداً، أعلن الفجوة — لا تقدّر ولا تختلق."),
        "allowed_tools": ["web_search"],
    }
    out = run_llm_agent(mission, market_ref, product=product, hs_code=hs_code)
    findings = getattr(out, "findings", None) or []
    good = [f for f in findings if getattr(f, "value", None) is not None]
    for f in good:
        f.note = f"{f.note} · استُرجع عبر طبقة سد الفجوات (م٥: بحث ويبي موجّه)"
        _append_finding(report, f)
    return bool(good)


# ── دمج الفجوات المتطابقة · mandatory dedup (§7) ────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


# ── نقطة الدخول الواحدة · the single entry point ────────────────────────────

def recover(mission_reports: dict, *, market_ref, product: str = "",
            hs_code: str | None = None, year: int | None = None) -> dict:
    """يعالج فجوات كل البعثات في مكانها ويعيد سجل المشغّل (§8).

    لا يُستدعى إلا من مسار `/research` في api.py بعد اكتمال البعثات — ممنوع
    استدعاؤه من داخل أي وكيل (حارس AST في الاختبارات).
    """
    if not enabled():
        return {"enabled": False}

    t0 = time.monotonic()
    deadline = t0 + _cap("SILK_GAP_TIMEOUT_S", 180)
    max_attempts = _cap("SILK_GAP_MAX_ATTEMPTS", 3)
    max_web = _cap("SILK_GAP_MAX_WEB_SEARCH", 5)

    # ١) جمع البنود من ملخّصات كل البعثات (الناجحة تصرّح بفجوات جزئية أيضاً).
    items: list[GapItem] = []
    seen: set = set()
    for key, report in (mission_reports or {}).items():
        for clause in _gap_clauses(_summary_get(report)):
            norm = _normalize(clause)
            if norm in seen:
                # دمج إلزامي: فجوتان بنفس النص = بند واحد؛ تُحذف المكرّرة.
                _summary_set(report, _drop_clause(_summary_get(report), clause))
                continue
            seen.add(norm)
            items.append(GapItem(mission_key=key, text=clause,
                                 category=classify(clause),
                                 prio=priority(clause)))
    # ١ب) البنود الخام أيضاً — لا نثر الملخّص وحده (العيب B، 2026-08-19):
    # `DataPoint.status="fetch_failed"` وملاحظته لم تكونا تصلان المصنّف
    # إطلاقاً، فأي فشل لم يذكره الكاتب في «| فجوات:» كان يمرّ بلا محاولة.
    for key, report in (mission_reports or {}).items():
        for f in _raw_failed_findings(report):
            text = f"{f.get('metric') or ''} {f.get('note') or ''}".strip()
            norm = _normalize(text)
            if not text or norm in seen:
                continue
            cat = classify(text, f.get("status") or "")
            if cat == NONE:
                continue
            seen.add(norm)
            items.append(GapItem(mission_key=key, text=text, category=cat,
                                 prio=priority(text)))

    ops_log: list[dict] = []
    web_used = 0
    by_route: dict = {}

    def _mark(item: GapItem, route: str, report) -> None:
        item.recovered, item.route = True, route
        by_route[route] = by_route.get(route, 0) + 1
        _summary_set(report, _drop_clause(_summary_get(report), item.text))

    # ٢) OPS أولاً — سجل المشغّل فقط، يُحذف من مسار العميل (قاعدة ملزمة §2).
    for item in items:
        if item.category != OPS:
            continue
        report = mission_reports[item.mission_key]
        reason = f"[{item.mission_key}] {item.text}"
        try:
            # المُطهِّر تحسين لا شرط — غيابه لا يُسقط تسجيل المشغّل نفسه
            # (مراجعة §58: كان الفشلان مبتلعين معاً فيضيع الأثر كلياً).
            from silk_render import _strip_internal_plumbing
            reason = _strip_internal_plumbing(reason)
        except Exception:
            pass
        recorded = False
        try:
            from silk_ops_log import record_service_failure
            record_service_failure("gap_recovery/ops", reason)
            recorded = True
        except Exception:
            pass
        ops_log.append({"mission": item.mission_key, "text": item.text,
                        "recorded": recorded})
        item.recovered, item.route = True, "OPS→ops_log"
        _summary_set(report, _drop_clause(_summary_get(report), item.text))

    # ٣) المسار المتدرّج — بالأولوية ثم بالفئة؛ توقف عند أول نجاح لكل بند.
    for item in sorted(items, key=lambda i: i.prio):
        if item.recovered or item.category in (OPS, PAID, NONE):
            continue
        if time.monotonic() >= deadline:
            break
        report = mission_reports[item.mission_key]
        item.attempts += 1

        wgi_family = (any(l in item.text for l in _WGI.values())
                      or "الحوكمة" in item.text)
        # الموسمية/الاتجاهات: حدُّ معدلٍ لا فجوةَ بيانات — إعادةُ محاولةٍ
        # متصاعدة عبر مسترجِع الاتجاهات نفسه (كان م١ محصوراً بعائلة WGI،
        # فتبقى «موسمية رمضان» فجوةً معلنةً بلا أيّ محاولة).
        if item.category == RATE and any(
                n in item.text for n in ("موسمية", "رمضان", "اتجاهات",
                                         "Trends", "الطلب الموسمي")):
            item.tried.append("م١-اتجاهات")
            if recoverer_enabled("seasonality") and _retry_backoff(
                    lambda: _recover_seasonality(item, report, product,
                                                 market_ref, deadline),
                    max_attempts, deadline):
                _mark(item, "م١-اتجاهات", report)
                continue
        if item.category == RATE and wgi_family:
            # م١: إعادة محاولة متصاعدة لعائلة معروفة المسترجِع فقط — لا نوم
            # أعمى على عائلة بلا مسترجِع (مراجعة §58). نجاح م١ هنا يغني عن م٤
            # (نفس نقطة النهاية — لا نداء رابع على مصدر فاشل).
            item.tried.append("م١")
            if recoverer_enabled("wgi") and _retry_backoff(
                    lambda: _recover_wgi(item, report, market_ref, deadline),
                    max_attempts, deadline):
                _mark(item, "م١", report)
                continue
        if item.category == FIELD:
            item.tried.append("م٢")
            if recoverer_enabled("partner_shares") and _recover_partner_shares(
                    item, report, market_ref, hs_code, year, deadline):
                _mark(item, "م٢", report)
                continue
        if item.category == DERIVE:
            item.tried.append("م٣")
            if recoverer_enabled("per_capita") and _recover_per_capita(
                    item, report, market_ref, deadline,
                                   mission_reports):
                _mark(item, "م٣", report)
                continue
        if item.category == FETCH and wgi_family and "م١" not in item.tried:
            item.tried.append("م٤")
            # الصمّامُ نفسُه الذي تفحصه كلُّ الطرق الأخرى (م١ سطر أعلاه) —
            # كان هذا المسارُ يستدعي `_recover_wgi` عارياً، فيتجاهل
            # `SILK_GAP_RECOVER_WGI=0` ويطلق نداءاتِ البنك الدوليّ الحيّة رغم
            # الإطفاء الصريح (مراجعة §58).
            if recoverer_enabled("wgi") and _recover_wgi(
                    item, report, market_ref, deadline):
                _mark(item, "م٤", report)
                continue
        # م٤ للتعرفة — سلسلة التراجع المعتمدة (WTO TTD ← WITS). كانت التعرفة
        # (أولوية ١، تقيّد الحكم مباشرة) بلا أي مسار حتمي: تسقط إلى م٥ أو لا
        # شيء رغم وجود مسار بديل جاهز في الشيفرة (العيب C).
        if (item.category in (FETCH, RATE) and hs_code
                and any(n in item.text for n in ("تعرفة", "التعريفة", "الرسوم الجمركية"))):
            item.tried.append("م٤")
            if recoverer_enabled("tariff") and _retry_backoff(
                    lambda: _recover_tariff(item, report, market_ref, hs_code,
                                            year, deadline),
                    max_attempts if item.category == RATE else 1, deadline):
                _mark(item, "م٤", report)
                continue

        # §6: فجوةُ الموزّعين أولويةُ ١ بمسارٍ خاصّ قبل م٥ العامّ.
        if (any(n in item.text for n in ("موزع", "موزّع", "مستورد", "جهات اتصال"))
                and web_used < max_web):
            item.tried.append("م٤-موزعون")
            # السقفُ يُستهلَك عند **نداءٍ فعليّ** فقط — كان `web_used += 1`
            # يسبق الصمّام، فيستنزفه استرجاعٌ مُطفأ (لا نداء) ويُجوِّع مسارَ
            # الموزّعين نفسَه حين يُفعَّل لاحقاً (مراجعة §58).
            if recoverer_enabled("distributors"):
                web_used += 1
                if _recover_distributors(
                        item, report, market_ref, product, deadline):
                    _mark(item, "م٤-موزعون", report)
                    continue

        # م٥ — أولوية 1–2 فقط، تحت السقف، وبعد استنفاد م١–م٤.
        if item.prio <= 2 and web_used < max_web:
            item.tried.append("م٥")
            # `web_search` مطفأٌ **بنيوياً** (`recoverer_enabled` يرفضه بلا
            # قراءة بيئة): مصدريّةٌ غير محدودة، وملءُ فجوةٍ معلنة من نصّ ويبٍ
            # عشوائيّ هو بالضبط ما يحظره عقدُ التأسيس. وحين يكون مطفأً **لا
            # نداءَ يُطلَق**، فلا يجوز خصمُ السقف: كان `web_used += 1` غيرُ
            # المشروط يستنزف الميزانيةَ على لا-عمليّاتٍ ويُجوِّع مسارَ
            # الموزّعين (مراجعة §58). السقفُ يُخصَم عند نداءٍ فعليّ حصراً.
            if recoverer_enabled("web_search"):
                web_used += 1  # المحاولة تُحتسب في السقف نجحت أم لا
                if _web_search_recover(
                        item, report, market_ref, product, hs_code, deadline):
                    _mark(item, "م٥", report)
                    continue

    closed = sum(1 for i in items if i.recovered)
    total = len(items)
    by_class: dict = {}
    for i in items:
        by_class[i.category] = by_class.get(i.category, 0) + 1
    # مؤشر الصحة يقيس القابل للاسترجاع فقط — PAID/NONE غير قابلة بنيوياً،
    # وOPS إصلاح إعدادات لا مسار بدائل (مراجعة §58).
    recoverable = [i for i in items
                   if i.category in (RATE, FIELD, DERIVE, FETCH)]
    rec_closed = sum(1 for i in recoverable if i.recovered)
    return {
        "enabled": True,
        "before": total,
        "after": total - closed,
        "closed": closed,
        "closure_pct": round(100.0 * closed / total, 1) if total else None,
        "by_class": by_class,
        "by_route": by_route,
        "ops": ops_log,               # قائمة إصلاحات المنصّة — للمشغّل فقط
        "web_search_used": web_used,
        "elapsed_s": round(time.monotonic() - t0, 1),
        "residual": [
            {"mission": i.mission_key, "text": i.text, "class": i.category,
             "tried": i.tried}
            for i in items if not i.recovered],
        # مؤشر الصحة (§8): إغلاق القابل-للاسترجاع دون 50٪ = خلل سجل البدائل.
        "health": ("fallback_registry_defect"
                   if recoverable and rec_closed / len(recoverable) < 0.5
                   else "ok"),
    }
