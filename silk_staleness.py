"""تقادُم البيانات من المصدر لا من النثر — provenance-based staleness (القاعدة العامة).

> **قرار المالك (يستبدل نهج «الوسم بالتعبير النمطي أولاً»).** التقادُم يُقرَّر
> **عند الحقيقة** لا بتحليل الجُمَل العربية: كل `DataPoint` يحمل سنة بياناته
> (صراحةً، أو عبر وسم `year=YYYY` البنيوي في الملاحظة كما يكتبه جامع البنك
> الدولي `silk_data_layer.py`، أو من `retrieved_at`). سنةٌ ≤ (السنة الحالية −
> `SILK_STALE_DATA_YEARS`، افتراضياً ٥) => الحقيقة **مُتقادِمة**، فتُوسَم
> «بيانات {السنة} — الأحدث المتاح» **قبل الكتابة** ويحملها الكاتب، وتتحقّق طبقة
> العرض من بقاء الوسم بمقارنة التقرير بـ**قائمة الحقائق المتقادِمة**، لا بإعادة
> تحليل النثر. التعبير النمطي يبقى **شبكة أمان أخيرة فقط**.
>
> **يقتل عائلة العيب دفعةً واحدة** (مراجعة الشيفرة #1/#2/#3/#5): «الطعام 2013»
> لا يُوسَم زوراً (لا حقيقة متقادِمة خلفه)، و«في 2013»/«2013م»/أيّ صياغة
> مستقبلية لا تفلت (الحقيقة نفسها مُعلَّمة مهما كانت الصياغة)، ورمز HS مثل
> 2008 لا يُوسَم (رمزٌ لا سنةَ حقيقة).

المكتبات: stdlib فقط — يستورده جامع الحقائق (الكاتب) وطبقة العرض بلا شبكة.
"""
from __future__ import annotations

import datetime
import os
import re

# وسم السنة البنيوي الذي يكتبه الجامعون في الملاحظة («… year=2013») — البنك
# الدولي (`silk_data_layer._world_bank_for_year`) وكومتريد (`silk_llm_runtime.
# _tool_comtrade_imports`). استخلاصٌ من حقلٍ بنيويّ لا من نثرٍ عربيّ.
_YEAR_MARKER_RE = re.compile(r"\byear\s*=\s*(\d{4})\b")
# سنة تاريخِ رصدٍ في retrieved_at — أيّ «YYYY-MM-DD» (مراجعة الشيفرة #3: لا
# تُقيَّد بنهاية السنة). تمييزُ طابع الجلب عن سنة البيانات يتمّ في fact_year
# بإشارةِ «السنة الماضية» (طابع `_today()` = السنة الجارية => ليس فِنتيج).
_OBS_YEAR_RE = re.compile(r"^\s*(\d{4})-\d{2}-\d{2}\b")

STALE_TAG = "الأحدث المتاح"


def stale_years_back() -> int:
    """نافذة التقادُم بالسنوات — SILK_STALE_DATA_YEARS (٥ افتراضياً)."""
    try:
        n = int(os.environ.get("SILK_STALE_DATA_YEARS", "5"))
        return n if n > 0 else 5
    except (TypeError, ValueError):
        return 5


def stale_threshold_year() -> int:
    """أحدث سنةٍ تُعتبَر «متقادِمة» — (السنة الحالية − النافذة)."""
    return datetime.date.today().year - stale_years_back()


def _get(dp: object, key: str) -> object:
    """اقرأ حقلاً من DataPoint (كائن) أو dict خام."""
    if isinstance(dp, dict):
        return dp.get(key)
    return getattr(dp, key, None)


def fact_year(dp: object) -> int | None:
    """سنة بيانات الحقيقة من مصدرها البنيوي — لا تحليل نثر (الدرس ٣٣):
    (١) **الحقل البنيويّ `data_year`** الذي يضبطه الجامعون (المصدر المُعتمَد)،
    (٢) `year=YYYY` في الملاحظة (**احتياط قديم** لمدوّنات مخزّنة قبل الحقل — لم
    يعد يُكتَب)، (٣) سنة `retrieved_at` كتاريخِ رصدٍ (أيّ YYYY-MM-DD) **إن كانت
    سنةً ماضية** لا طابعَ جلبٍ للسنة الجارية (مراجعة #3: يقبل غير نهاية السنة،
    ويستبعد طابع الجلب بإشارةِ «السنة الماضية»). None إن تعذّر."""
    for k in ("data_year", "year"):
        v = _get(dp, k)
        if isinstance(v, bool):
            continue
        if isinstance(v, int) and 1900 <= v <= 2100:
            return v
        if isinstance(v, str) and v.strip().isdigit() and len(v.strip()) == 4:
            return int(v)
    note = str(_get(dp, "note") or "")
    m = _YEAR_MARKER_RE.search(note)  # احتياط قديم لا يُكتَب بعد اليوم
    if m:
        return int(m.group(1))
    ra = str(_get(dp, "retrieved_at") or "")
    m = _OBS_YEAR_RE.match(ra)
    if m:
        y = int(m.group(1))
        # السنة الجارية = طابع جلبٍ (`_today()`) لا سنةَ بيانات؛ الماضية = رصد.
        if y < datetime.date.today().year:
            return y
    return None


def is_stale_year(year: object, back: int | None = None) -> bool:
    """هل السنة متقادِمة؟ — year ≤ (الحالية − النافذة). None => False."""
    if year is None:
        return False
    try:
        y = int(year)
    except (TypeError, ValueError):
        return False
    thr = datetime.date.today().year - (back if back and back > 0
                                        else stale_years_back())
    return y <= thr


def stale_tag(year: object) -> str:
    """نصّ الإفصاح الموحّد — «بيانات {السنة} — الأحدث المتاح»."""
    return f"بيانات {year} — {STALE_TAG}"


def is_stale_fact(dp: object) -> bool:
    """حقيقةٌ حاملةٌ قيمةً فعلية وسنتُها متقادِمة (فجوة None ليست رقماً)."""
    if _get(dp, "value") is None:
        return False
    return is_stale_year(fact_year(dp))


def stale_fact_years(findings: object) -> set[int]:
    """مجموعة سنوات الحقائق المتقادِمة (ذات القيم) — قائمة الحقيقة المتقادِمة
    التي تقارن بها طبقةُ العرض التقريرَ (لا تحليل نثر)."""
    out: set[int] = set()
    for f in findings or []:
        if _get(f, "value") is None:
            continue
        y = fact_year(f)
        if y is not None and is_stale_year(y):
            out.add(int(y))
    return out


# ── قِدم البيانات بطبقتين (توجيه المنصّة §2.4، الموجة ١) ────────────────────
# طبقتان فوق نافذة التقادُم القائمة: تحذير عند > SILK_VINTAGE_WARN_YEARS
# (افتراضياً 3؛ وإن ضُبطت SILK_STALE_DATA_YEARS القديمة فهي طبقة التحذير —
# توافق خلفي)، و«منتهٍ» عند > SILK_VINTAGE_HARD_YEARS (افتراضياً 7): لا يدعم
# استنتاجاً — سياقٌ فقط. لا حجب ولا إخفاء قيمة (قرار مالك 2026-08-19):
# الطبقة الصلبة فحص بوابة تحذيري + تحذير ضمن الجملة، لا أكثر.

VINTAGE_FRESH, VINTAGE_WARN, VINTAGE_EXPIRED = "fresh", "warn", "expired"


def vintage_warn_years() -> int:
    """طبقة التحذير — SILK_VINTAGE_WARN_YEARS، وإلا SILK_STALE_DATA_YEARS
    القديمة إن ضُبطت (توافق خلفي)، وإلا 3."""
    raw = os.environ.get("SILK_VINTAGE_WARN_YEARS")
    if raw is None and os.environ.get("SILK_STALE_DATA_YEARS"):
        # توافق دلاليّ دقيق: التقادُم القديم يقع عند العمر ≥ N (is_stale_year)
        # بينما طبقة التحذير هنا «أقدم من N» (العمر > N) — فتُترجَم N القديمة
        # إلى N−1 كي يتطابق حدّا الآليّتين على نفس سنة الحدود (مراجعة §58).
        return max(1, stale_years_back() - 1)
    try:
        n = int(raw) if raw is not None else 3
        return n if n > 0 else 3
    except (TypeError, ValueError):
        return 3


def vintage_hard_years() -> int:
    """الطبقة الصلبة — SILK_VINTAGE_HARD_YEARS (7 افتراضياً): أقدم من هذا
    لا يدعم استنتاجاً، سياقٌ فقط."""
    try:
        n = int(os.environ.get("SILK_VINTAGE_HARD_YEARS", "7"))
        return n if n > 0 else 7
    except (TypeError, ValueError):
        return 7


def vintage_tier(year: object) -> str:
    """fresh | warn | expired — من سنة البيانات (int أو DataPoint/dict)."""
    y = year if isinstance(year, int) else fact_year(year)
    if y is None:
        return VINTAGE_FRESH  # لا سنة معروفة — لا وسم زور (الدرس ٣٣)
    age = datetime.date.today().year - y
    warn = vintage_warn_years()
    # الطبقة الصلبة فوق طبقة التحذير دائماً: مالكٌ وسّع نافذة التحذير فوق 7
    # لا يُعاقَب بوسم «منتهٍ» أقسى مما كانت إعداداته تنتج، وتبقى لطبقة
    # التحذير سنةٌ واحدة على الأقل قبل «منتهٍ» (مراجعة §58).
    hard = max(vintage_hard_years(), warn + 1)
    if age > hard:
        return VINTAGE_EXPIRED
    if age > warn:
        return VINTAGE_WARN
    return VINTAGE_FRESH


def vintage_caveat(year: object) -> str:
    """تحذير القِدم ضمن الجملة نفسها (§2.4) — نص عربي جاهز، أو "" للحديث."""
    y = year if isinstance(year, int) else fact_year(year)
    tier = vintage_tier(y)
    if tier == VINTAGE_EXPIRED:
        hard = max(vintage_hard_years(), vintage_warn_years() + 1)
        return (f"بيانات {y} — أقدم من {hard} سنوات: "
                "سياقٌ فقط، لا تُبنى عليها خلاصة")
    if tier == VINTAGE_WARN:
        return f"بيانات {y} — أقدم من {vintage_warn_years()} سنوات"
    return ""
