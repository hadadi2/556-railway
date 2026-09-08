"""بوابة تأكيد رمز HS المسبقة — HS pre-flight confirmation gate (Wave 1.2).

> **العائلة.** `unresolved-hs-silent-spend` موسَّعةً: رمز HS قد يُحسَم بثقة
> عالية لكنه **خاطئ دلالياً** — صفة المنتج المميّزة تضيع لصالح تطابق كلمة
> ثانوية عارية. البلاغ الأصلي (تدقيق المالك، تقرير زبدة الفول السوداني/اليمن):
> «زبدة الفول السوداني» حُسِمت إلى 040510 (زبدة/Butter) لأن «زبدة» طابقت،
> بينما الصفة المميّزة «فول سوداني» غائبة عن وصف الرمز — العائلة الصحيحة
> 200811 (فول سوداني محضّر) / 210690 (محضرات غذائية).
>
> **القاعدة الدائمة (عقد التأكيد المسبق).** قبل أيّ إنفاق، يُقاس تداخل صفات
> المنتج المميّزة مع وصف الرمز المُصنَّف. تداخل ضعيف => الرمز **غير مؤكَّد**
> (`confirmed=False`) => بوابة صلبة (خلف `SILK_HS_CONFIRM_GATE`) تُوقِف
> التشغيل وتسأل المستخدم، وطبقة العرض/الكاتب تعيد تأطير كل رقم مشتقّ من الرمز
> «مؤشر سياقي لا مقياس فعلي». صفر اسم منتج/رمز مكتوب صلباً — القاعدة مبنيّة
> على البيانات (`data/hscodes_full.csv` — القائمة الرسمية الكاملة HS2022،
> ٥٦١٣ رمزاً) والعتبة من env (عائلة `hardcoded-product-rule`، الدرس ٢٤).

المكتبات: stdlib فقط — يستورده api (البوابة) وطبقة العرض (التأطير) بلا شبكة.
"""
from __future__ import annotations

import logging
import os
import re

import silk_hs_norm as _hs_norm

log = logging.getLogger(__name__)

# عتبة التداخل الأدنى لاعتبار الرمز مؤكَّداً — config-driven (لا رقم صلب في
# المنطق). تداخل صفات المنتج المغطّاة بوصف الرمز دونها => غير مؤكَّد.
_DEFAULT_MIN_OVERLAP = 0.5


def _min_overlap() -> float:
    """عتبة التداخل من env (`SILK_HS_CONFIRM_MIN_OVERLAP`) أو الافتراضي."""
    try:
        v = float(os.environ.get("SILK_HS_CONFIRM_MIN_OVERLAP", ""))
        return v if 0.0 < v <= 1.0 else _DEFAULT_MIN_OVERLAP
    except (TypeError, ValueError):
        return _DEFAULT_MIN_OVERLAP


# ── بوّابة ثقة التصنيف (بلاغ «حليب نادك») ────────────────────────────────────
# الحادثة: الرمز حُسِم وثقتُه **فارغة** («ثقة التصنيف —» في جدول التقرير)،
# ومضى الخطُّ إلى الترتيب والبعثات على رمزٍ داخل الترويسة الصحيحة لكنه البند
# الخاطئ (040110 «دسم ≤1%» — حليبٌ منزوع الدسم — لمنتجٍ كامل الدسم مرصودٍ في
# السوق). الفارق بين 040110/040120/040150 **نسبةُ دسمٍ رقمية** لا كلمةٌ في
# اسم المنتج، فبوّابةُ التطابق الدلالي (`confirm_hs`) لا تراه أصلاً: كلاهما
# «حليب». الحارس الصحيح هنا هو **الثقة نفسها**: ثقةٌ غائبة أو دون العتبة =
# لا ترتيبَ ولا إنفاق، بل سؤالُ المستخدم بين المرشّحين.
#
# رمزٌ خاطئ يُعيد تأطير **كل** رقمٍ لاحق (حجم السوق/الحصص/التركّز/الاتجاه)،
# فالخطأ هنا ليس رقماً واحداً بل التقرير كلّه — لذا فشل-آمن: مفعّلة افتراضياً.
_DEFAULT_MIN_CONFIDENCE = 0.8

# ذيلا رسالة الحجب — **ثابتان مُصدَّران** لا نصّان مدفونان: مَن يملك مرشّحين
# أكثر من هذه البوّابة (جسرُ المنصّة يقرأ وصفَ الكتالوج) يبدّل الذيل بالمصدر
# نفسه بدل أن يترك نصّاً يقول «لا مرشّحين» فوق قائمةٍ مملوءة (مراجعة ذاتية
# §58 على موجة «الطاحونة»: تناقضٌ في السطر الواحد هو عين الدرس ٢٠٦).
PICK_TAIL = "اختر من المرشّحين أدناه أو أدخل رمزاً يدوياً."
NO_CANDIDATES_TAIL = ("لا مرشّحين حتميّين لهذا الاسم — اسمُ العلامة التجارية "
                      "وحده لا يكفي للتصنيف: اكتب وصف المنتج نفسه (نوعه "
                      "ومادّته) أو أدخل الرمز يدوياً.")


def min_confidence() -> float:
    """عتبةُ ثقة التصنيف من env (`SILK_HS_MIN_CONFIDENCE`) أو الافتراضي.

    الافتراض 0.8 مُعايَرٌ على سلوك المُحلِّل الحتمي الفعلي (`silk_hs_resolver`):
    تطابقٌ تامّ = 1.0، إصابةُ كلمةٍ مفتاحية = 0.85، وما دونهما درجةُ difflib
    (وهو أصلاً يقصّ ما دون 0.7 إلى `None`). فالعتبة تُمرِّر المطابقةَ التامّة
    والمفتاحية، وتحجب النافذةَ الضبابية 0.7–0.79 — حيث يعيش تطابقُ الحروف
    العارضُ («نفط خام» → 520100 قطن بدرجة 0.71)."""
    try:
        v = float(os.environ.get("SILK_HS_MIN_CONFIDENCE", ""))
        return v if 0.0 < v <= 1.0 else _DEFAULT_MIN_CONFIDENCE
    except (TypeError, ValueError):
        return _DEFAULT_MIN_CONFIDENCE


def confidence_gate_enabled() -> bool:
    """هل بوّابة الثقة مفعّلة؟ (`SILK_HS_CONFIDENCE_GATE`) — فشل-آمن: نعم.

    صمّامٌ **مستقلّ** عن `SILK_HS_CONFIRM_GATE` (بوّابة التطابق الدلالي):
    البوّابتان تقيسان شيئين مختلفين، فإطفاءُ إحداهما يجب ألّا يُطفئ الأخرى."""
    raw = os.environ.get("SILK_HS_CONFIDENCE_GATE", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return True


# صمّاماتٌ تغيّر معناها ولم يتغيّر اسمُها (موجة خطّ التصنيف، 2026-08-30).
# إعادةُ التسمية تكسر نشراً حيّاً بصمت؛ فالتحذيرُ يقع **حيث يُعتمَد عليها**،
# مرّةً واحدة لكلّ صمّام في عمر العملية — لا في كل نداءٍ فيغرق السجلّ.
_WARNED_VALVES: set = set()


def _warn_superseded_valve(name: str, what_changed: str) -> None:
    """حذِّر مرّةً أنّ هذا الصمّام لم يعد يفعل ما يوحي به اسمُه."""
    if name in _WARNED_VALVES:
        return
    _WARNED_VALVES.add(name)
    log.warning("%s مضبوطٌ على الإطفاء لكنّه لم يعد يُعطّل التصنيف: %s",
                name, what_changed)


def gate_enabled() -> bool:
    """هل بوابة التأكيد الصلبة مفعّلة؟ (`SILK_HS_CONFIRM_GATE`).

    **فشل-آمن: مفعّلة افتراضياً** (البلاغ الحيّ 2026-07-21، عائلة
    `unresolved-hs-silent-spend`): تشغيلةُ `/research` مدفوعة على «زبدة الفول
    السوداني» مضت على 040510 (زبدة ألبان) لأن البوّابة كانت خلف صمّامٍ مُطفأ
    في الإنتاج، فأُنفِقت دولارات على فئةٍ مجاورةٍ خاطئةٍ دلالياً ولم يُحذَّر
    إلا نثراً. القانون (LAW): لا إنفاق صامت على رمزٍ خاطئ؛ المالك آخِر مؤكِّد.
    لذا البوّابة تعمل ما لم تُطفَأ صراحةً (`SILK_HS_CONFIRM_GATE=0/false/off`).
    الحساب الاستشاري (`confirm_hs`) يعمل دائماً بمعزلٍ عن هذا الصمّام."""
    raw = os.environ.get("SILK_HS_CONFIRM_GATE", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        _warn_superseded_valve(
            "SILK_HS_CONFIRM_GATE",
            "التحقّقُ الدلاليّ صار جزءاً من التصنيف نفسه (silk_hs_pipeline) لا "
            "بوّابةً فوقه، فإطفاءُ هذا الصمّام لم يعد يُمرِّر رمزاً يخالف "
            "المنتج. المَخرجُ الشرعيّ: hs_confirmed=true — تأكيدُ إنسانٍ "
            "حاضر يُسجَّل باسمه، لا متغيّرُ بيئةٍ صامتٌ على مستوى الخادم.")
        return False
    return True


# كلمات ربط/أدوات عامة — نقطةُ الحقيقة صارت `silk_hs_norm.STOPWORDS`؛ الاسمُ
# المحلّي يبقى للمستدعين القدامى (لا كسرَ توافق).
_STOPWORDS = _hs_norm.STOPWORDS



def _norm(s: str) -> str:
    """طبّع نصاً للمطابقة — **الطبقةُ المشتركة** (`silk_hs_norm`).

    كانت هنا نسخةٌ محلية تطوي الألفَ والياءَ والتاءَ المربوطة بينما المُحلِّل
    يخفض الحالةَ فقط — تنميطان على مسارٍ واحد، عوّضهما المرجعُ بتكرار
    التهجئات صفّاً صفّاً (البند ٥ من أمر الموجة).
    """
    return _hs_norm.normalize(s)


def _tokens(text: str) -> list[str]:
    """قسّم نصاً إلى صفات ذات معنى — نفسُ عقد `silk_hs_norm.tokens`."""
    return _hs_norm.tokens(text)


# [متروك] حدُّ طولِ الاحتواء — لم يعد يحكم شيئاً بعد أن صار
# القياسُ على وحداتٍ كاملة. يبقى مُصدَّراً للمستدعين القدامى.
_MIN_CONTAINMENT_LEN = int(
    os.environ.get("SILK_HS_CONFIRM_MIN_CONTAINMENT_LEN", "3") or "3")


def _covered(term: str, code_terms: list[str]) -> bool:
    """هل صفةُ المنتج **هي نفسُها** إحدى صفات وصف الرمز؟ — تطابقُ وحدةٍ كاملة.

    **الاحتواءُ الحرفيّ حُذف** (البند ٨ من أمر الموجة). كان الحدُّ الأدنى للطول
    (٣ أحرف) يُقصَد به ترويضُ التصادم، لكنه لا يعالج جذره: العربيةُ مليئةٌ
    بجذورٍ ثلاثيةٍ سليمةِ الطول تقع داخل كلماتٍ بعيدةٍ عنها معنى — «رقي»
    (بطيخ) داخل «ورقية»، و«طحين» (دقيق) داخل «طحينية». معايرةُ الطول تُطارد
    الأعراض؛ القاعدةُ الصحيحة أن **الوحدةَ الكاملة** هي وحدةُ القياس.

    والتنميطُ المشترك يجعل «حلاوة»/«حلاوه» وحدةً واحدة ويُبقي «رقي»/«ورقية»
    وحدتين — وهذا بالضبط الفارقُ بين تسامحٍ إملائيّ مشروع وتصادمٍ كاذب.
    """
    t = _hs_norm.normalize(term)
    if not t:
        return False
    return any(t == _hs_norm.normalize(c) for c in code_terms if c)


def _keywords_ar_list(row: dict) -> list[str]:
    """كلمات `keywords_ar` كقائمة — مفصولةٌ بفاصلةٍ منقوطة `;` (راجع
    tools/migrate_hs_keywords.py)، الأولى هي الاسم العربي الأساسي عرفاً.

    متسامحةٌ مع المخطّط القديم (`name_ar`/`keywords` بفواصل عادية — الدمج
    المُكيَّف لـ#139 أبقى `data/hs_codes.csv` مصدراً لقرّاء البذرة القدامى):
    صفٌّ بلا `keywords_ar` يُقرأ من أعمدته القديمة بدل فراغٍ صامت."""
    ar = (row.get("keywords_ar") or "").strip()
    if ar:
        return [t.strip() for t in ar.split(";") if t.strip()]
    legacy = [row.get("name_ar") or ""] +         (row.get("keywords") or "").replace("؛", ";").replace("،", ",").split(",")
    return [t.strip() for t in legacy if t.strip()]


def _code_terms(row: dict) -> list[str]:
    """صفات وصف الرمز — الوصف الرسمي الإنجليزي + الكلمات المفتاحية العربية،
    مُنمَّطة (القائمة الرسمية الكاملة: `description_en`/`keywords_ar`)."""
    parts: list[str] = list(_tokens(
        row.get("description_en") or row.get("name_en") or ""))
    for kw in _keywords_ar_list(row):
        parts.extend(_tokens(kw))
    return parts


def _code_desc(row: dict) -> str:
    """وصف مقروء للرمز للعرض — العربي الأساسي إن وُجد وإلا الوصف الرسمي
    الإنجليزي."""
    ar = _keywords_ar_list(row)
    return (ar[0] if ar else (row.get("description_en") or "")).strip()


# الخريطةُ مربوطةٌ بهويّة قائمة الصفوف التي بُنيت منها — لا بذاكرةٍ مستقلّة.
# نفسُ درس `_INDEX_CACHE` في `silk_hs_resolver` حرفياً («بذاكرتين مستقلّتين…
# أخطرُ أشكال العطل»): كانت هنا `lru_cache` بمفتاح المسار وحده، فمَن يمسح
# ذاكرة المرجع (`extend_from_comtrade_rows` يفعل بعد توسيع الملف) كان يترك
# هذه الخريطةَ ميّتة — `_find_row` يعيد `None` لرمزٍ **موجودٍ** في المرجع
# ⇒ `confirmed=None` ⇒ درجة 0.0 ⇒ رفضُ رمزٍ صحيح على مسارٍ ينفق، بصمت.
# فحصُ `is` على كائن الصفوف يجعل إعادةَ البناء تلقائيةً بعد أيّ `cache_clear`.
# القيمة: {path: (rows_obj, map)}؛ السقفُ أربعةُ مسارات (سقفُ maxsize=4
# القديم) — عند التجاوز يُحذَف الأقدمُ إدراجياً (`dict` يحفظ الترتيب).
_ROWS_CACHE: dict = {}
_ROWS_CACHE_MAX = 4


def _rows_by_code(path: str = "data/hscodes_full.csv") -> dict:
    """خريطةُ رمز ⇒ صفّ، مبنيّةٌ مرّة — البند ٢٧ (الأداء).

    كان `_find_row` يمسح ٥٦٢٦ صفّاً خطّياً في **كل** نداء تأكيد، وخطُّ التصنيف
    يستدعيه مرّةً لكلّ مرشّح — أي عشراتُ آلاف المقارنات لكل طلب. مُخزَّنةٌ
    بعمر **كائن** الصفوف لا بمفتاح المسار (راجع `_ROWS_CACHE` أعلاه).
    """
    from silk_hs_resolver import load_hs_codes
    rows = load_hs_codes(path)
    cached = _ROWS_CACHE.get(path)
    if cached is not None and cached[0] is rows:
        return cached[1]
    out: dict = {}
    for r in rows:
        code = str(r.get("hs_code", "")).strip()
        if code and code not in out:
            out[code] = r
    _ROWS_CACHE.pop(path, None)          # إعادةُ البناء تُجدِّد موضع الإدراج
    _ROWS_CACHE[path] = (rows, out)
    while len(_ROWS_CACHE) > _ROWS_CACHE_MAX:
        _ROWS_CACHE.pop(next(iter(_ROWS_CACHE)))
    return out


def _find_row(hs_code: str, path: str = "data/hscodes_full.csv") -> dict | None:
    """صفّ الرمز من المرجع — بحثٌ بالخريطة المُخزَّنة لا مسحٌ خطّي."""
    return _rows_by_code(path).get(str(hs_code or "").strip())


# رسالة موحّدة للتأطير — تُعرَض مرة واحدة في المنهجية (الدرس ٤.١: لا تكرار).
CONTEXTUAL_TAG = "بيانات فئة مجاورة — مؤشر سياقي لا مقياس فعلي"


# ── وعيُ النفي (بلاغ «full fat milk» ضد 040110) ─────────────────────────────
# الحادثة: `confirm_hs("full fat milk", "040110")` أعاد **مؤكَّداً** بتداخل
# 0.67 — لأنّ وصفَ الرمز «…fat content, by weight, not exceeding 1%» يحوي
# «fat» و«milk»، وهو يعني **النقيض** (منزوعُ الدسم). تداخلُ النصّ يَعُدّ
# الكلماتِ ولا يقرأ النفي: «لا يتجاوز ١٪» و«كامل الدسم» يتشاركان الكلمات
# نفسَها ويتناقضان تماماً.
#
# القاعدة: حين يكون الرمزُ **محدوداً بنفيٍ أو بعتبةٍ رقمية**، لا يجوز أن
# يحسم التداخلُ وحده. يُفرَض `confirmed=False` في حالتين:
#   (١) صفةُ المنتج تقع **داخل** المقطع المنفيّ نفسه («other than X» ومنتجُنا
#       هو X) — تأكيدٌ صريحٌ لِما يستثنيه الرمز.
#   (٢) اسمُ المنتج يحمل **صفةَ درجةٍ/كمّية** (كامل، عالي، منزوع، full، whole،
#       high…) والوصفُ محدودٌ بعتبة — فالتمييزُ رقميٌّ لا لفظيّ، والتداخلُ
#       أعمى عنه بنيوياً. فشلٌ آمن: يُسأل المستخدم بدل أن يُصادَق الخطأ.
# ليست هذه قائمةَ منتجاتٍ مكتوبةً صلباً (عائلة `hardcoded-product-rule`) —
# بل أدواتُ نفيٍ وصفاتُ درجةٍ لغوية، لا اسمَ منتجٍ ولا رمزَ فيها.
_NEGATION_SPAN_RE = re.compile(
    r"\b(?:not\s+exceeding|not\s+containing|not\s+more\s+than|less\s+than"
    r"|other\s+than|excluding|except(?:ing)?|free\s+of|without|unsweetened"
    r"|n\.?e\.?[cs]\.?|not\s+elsewhere\s+specified"
    r"|بخلاف|عدا|باستثناء|لا\s+يتجاوز|دون|خالٍ\s+من|بدون)\b",
    re.I)
# عتبةٌ رقمية (٪ أو نسبةُ وزن/حجم) — التمييزُ الحقيقيّ بين بنود الترويسة.
_THRESHOLD_RE = re.compile(
    r"\d+\s*(?:%|per\s*cent|في\s*المئة|بالمئة)|by\s+weight|by\s+volume"
    r"|بالوزن|بالحجم", re.I)
# صفاتُ الدرجة/الكمّية التي يستحيل على التداخل أن يحكم عليها أمام عتبة.
_DEGREE_TERMS = frozenset({
    "full", "whole", "high", "rich", "heavy", "concentrated", "pure",
    "low", "light", "skimmed", "skim", "lean", "reduced", "semi",
    "sweetened", "unsweetened", "fortified", "extra", "virgin", "crude",
    "كامل", "كامله", "كاملة", "عالي", "عاليه", "عالية", "غني", "غنيه",
    "منزوع", "منزوعه", "منزوعة", "مركز", "مركزه", "مركزة", "خام", "نقي",
    "قليل", "خفيف", "محلى", "مدعم", "بكر", "دسم", "الدسم",
})


def describes_by_exclusion(code_desc: str) -> bool:
    """هل يُعرَّف الرمزُ بنفيٍ أو بعتبةٍ رقمية؟ — negation/threshold-defined."""
    d = code_desc or ""
    return bool(_NEGATION_SPAN_RE.search(d) or _THRESHOLD_RE.search(d))


def _negated_terms(code_desc: str) -> set[str]:
    """صفاتُ المقطع المنفيّ — ما بعد أداةِ النفي حتى أقرب فاصل."""
    out: set[str] = set()
    for m in _NEGATION_SPAN_RE.finditer(code_desc or ""):
        tail = (code_desc or "")[m.end():]
        span = re.split(r"[,;()،؛]|\band\b|\bor\b", tail, maxsplit=1)[0]
        out.update(_tokens(span))
    return out


# فاصلُ الحقول عند ضمّ صفّ CSV لفحص النفي — **ليس مسافة**. المقطعُ المنفيّ
# يمتدّ حتى أقرب فاصل، فضمُّ الحقول بمسافةٍ كان يجعل النفيَ في `name_en`
# يبتلع `keywords` التالية: صفُّ 040221 «Milk powder unsweetened» بكلماتٍ
# مفتاحية تحوي «حليب» أنتج تعارضاً كاذباً على «حليب» نفسه (اكتُشف بفشل
# قفلِ بوّابة الالتباس قبل الدمج). الفاصلةُ المنقوطة تُنهي المقطع.
_FIELD_SEP = " ؛ "


# ── حارسُ حالة التصنيع (بلاغ المالك: «مشكلة في تحديد HS بدقة») ────────────
# القياس الذي أسّس هذا الحارس: «عصير برتقال» ⇒ 080510 (برتقال **طازج**) بثقة
# 0.90 و`confirmed=True`؛ ومثلُه «شيبس بطاطس» ⇒ 070190، «مربى فراولة» ⇒
# 081010، «طماطم معلبة» ⇒ 070200. أربعةٌ من أربعة: دراسةٌ كاملةٌ مدفوعة تُبنى
# على الخام لمصنعٍ يُصنِّع — بصمتٍ، فوق عتبة الثقة وبمباركة بوّابة التطابق.
#
# السبب: `_covered` يَعُدّ صفةَ المنتج مغطّاةً إن احتواها أيُّ حدٍّ في الوصف،
# فـ«برتقال» وحدها تبلغ التداخلَ الأدنى، بينما الصفةُ **المُحوِّلة للحالة**
# («عصير») تسقط بلا أثر — وهي بعينها الفارقُ بين الفصل ٨ والفصل ٢٠.
#
# القاعدة: صفةُ تصنيعٍ في اسم المنتج بلا مقابلها في وصف الرمز **ووصفُ الرمز
# يعلن حالةً خاماً صراحةً** ⇒ رمزٌ غير مؤكَّد (فجوة معلنة تُسأل بمرشّحين، لا
# رمزٌ خاطئٌ واثق). الشرطُ الثالث يمنع الرفضَ الكاذب: «تمور مجففة» أمام
# «dates, fresh or **dried**» تمرّ لأن المقابل حاضر.
#
# بياناتٌ لا حالةُ منتج: معجمُ حالاتٍ عام، صفر اسم منتجٍ أو رمزٍ مكتوب صلباً.
_PROCESS_STATES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("عصير", "juice"), ("juice", "عصير")),
    (("شيبس", "رقائق", "chips", "crisps"),
     ("prepared", "preserved", "محضر", "محفوظ", "chips")),
    (("مربى", "jam", "marmalade", "مرملاد"),
     ("jam", "marmalade", "puree", "paste", "prepared", "preserved",
      "مربى", "محضر")),
    (("معلب", "معلبه", "محفوظ", "canned", "tinned"),
     ("prepared", "preserved", "محضر", "محفوظ", "canned")),
    (("مجفف", "مجففه", "مجففات", "dried", "dehydrated"),
     ("dried", "dehydrated", "مجفف")),
    (("مجمد", "مجمده", "frozen"), ("frozen", "مجمد")),
    (("محمص", "محمصه", "roasted"), ("roasted", "محمص")),
    (("معجون", "paste", "puree", "بوريه"),
     ("paste", "puree", "prepared", "معجون", "محضر")),
    (("مركز", "concentrate", "concentrated"),
     ("concentrate", "concentrated", "مركز")),
    (("مخلل", "مخللات", "pickled"),
     ("pickled", "vinegar", "acetic", "مخلل", "prepared", "preserved")),
    (("مطحون", "مسحوق", "بودره", "ground", "powder", "powdered"),
     ("ground", "powder", "flour", "meal", "مطحون", "مسحوق")),
)

# حالةٌ خامٌّ **معلنةٌ صراحةً** في وصف الرمز — الشرطُ الثالث. بدونها لا يُرفَض
# شيء: رمزٌ صامتٌ عن حالته قد يشمل المحضّر فلا نُسقِطه بالظنّ.
# **عبارات** لا شظايا (ملاحظة مراجعةٍ ذاتية §58): «live» تقع داخل `olives`
# و`livers`، و«حي» داخل «حيوانية» — فكان شرطُ «الرمز يعلن حالةً خاماً» يتحقّق
# على رموزِ **محضّرات** فيُرفَض المشروع. نفسُ فخّ الاحتواء الذي وثّقه
# `_MIN_CONTAINMENT_LEN` أعلاه بالضبط. الحلّ: مطابقةٌ على **حدود الكلمات**
# للمفردات، وعلى النصّ كاملاً للعبارات المركّبة وحدها.
_RAW_STATE_WORDS = ("fresh", "chilled", "raw", "طازج", "طازجه", "طازجة",
                    "مبرد", "مبرده", "خام")
_RAW_STATE_PHRASES = ("fresh or chilled", "not roasted", "not cooked",
                      "live animals", "غير محمص", "غير مطبوخ")


# حدُّ الكلمة لحرفٍ لاتينيّ أو عربيّ — «live» لا تُطابَق داخل `olives`.
_WORD_EDGE = r"[a-z0-9\u0621-\u064a]"


def _word_in(word: str, text: str) -> bool:
    """هل الكلمة حاضرةٌ **ككلمةٍ كاملة** في نصٍّ مُنمَّط؟"""
    w = re.escape(_norm(word))
    return bool(re.search(rf"(?<!{_WORD_EDGE}){w}(?!{_WORD_EDGE})", text))


# نفيٌ يسبق العلامةَ مباشرةً يُلغيها — «not roasted» تعني أنّ الرمزَ يغطّي
# **غيرَ** المحمّص، فحضورُ السلسلة «roasted» فيه ليس مقابلاً لصفة «محمّص» بل
# نقيضُها. كان الفحصُ `marker in desc` يقرأ النفيَ حضوراً فيسكت الحارسُ على
# التناقض الصريح («قهوة محمصة» ضد 090111 «Coffee; not roasted»).
# **حدُّ كلمةٍ قبل الأداة** (مراجعة #254): بلا حدٍّ كانت أيُّ كلمةٍ تنتهي
# بـ«un»/«non»/«غير» تُقرأ نفياً — «s**un**-dried» تُسكِت «dried»
# و«صـ**غير**» تُسكِت «مجفف» ⇒ تناقضٌ كاذبٌ يُصفِّر الرمزَ الصحيح. الأداةُ
# نفسُها تبدأ عند بداية النصّ أو بعد فاصلٍ [\s,;(/-] — فيبقى «unroasted»
# نفياً (سابقتُه «un» مسبوقةٌ بفراغ بداية الكلمة) وتسقط «sun-dried».
_MARKER_NEGATION = re.compile(
    r"(?:^|(?<=[\s,;(/-]))"
    r"(?:not|non|un|without|excluding|free\s+of|غير|بدون|بلا)"
    r"\s*[-]?\s*$", re.I)


def _marker_present(marker: str, desc: str) -> bool:
    """هل علامةُ الحالة حاضرةٌ **غيرَ منفيّة** في الوصف؟"""
    m = _norm(marker)
    if not m:
        return False
    for hit in re.finditer(re.escape(m), desc):
        if not _MARKER_NEGATION.search(desc[:hit.start()]):
            return True
    return False



def _process_state_conflict(product_terms: list[str], code_desc: str
                            ) -> str | None:
    """صفةُ تصنيعٍ في الاسم بلا مقابلها في وصفِ رمزٍ خامٍّ معلَن — أو `None`."""
    desc = _norm(code_desc or "")
    if not desc:
        return None
    # **لا `_tokens` هنا**: `_STOPWORDS` تحوي «fresh»/«dried»/«prepared» —
    # أي أنها تحذف بالضبط كلماتِ الحالة التي يبحث عنها هذا الحارس، فيعمى عن
    # «oranges, fresh or dried» كلّها (ملاحظة مراجعةٍ ذاتية ثانية على نفس
    # الإصلاح). المطابقةُ على **حدود الكلمة** في النصّ المُنمَّط مباشرةً.
    raw_declared = (any(_word_in(w, desc) for w in _RAW_STATE_WORDS)
                    or any(_norm(ph) in desc for ph in _RAW_STATE_PHRASES))
    if not raw_declared:
        return None
    joined = " ".join(product_terms or [])
    for names, markers in _PROCESS_STATES:
        hit = next((n for n in names if _norm(n) in joined), None)
        if not hit:
            continue
        if any(_marker_present(m, desc) for m in markers):
            # المقابلُ حاضرٌ لهذه الحالة — تُتجاوَز، **ولا تُنهى الحلقة**:
            # «برتقال مجفف مركز» كان يمرّ لأن `مجفف` طابقت `dried` فسكت
            # الحارسُ عن `مركز` (ملاحظة مراجعةٍ ذاتية §58).
            continue
        return (f"اسمُ المنتج يحمل صفةَ تصنيع («{hit}») ووصفُ الرمز يعلن "
                "حالةً خاماً بلا مقابلها — الفارقُ بين الخام والمحضّر فصلٌ "
                "جمركيٌّ مختلف، فلا يُحسَم بتطابق اسم المادة وحده")
    return None


def _negation_conflict(product_terms: list[str], code_desc: str
                       ) -> str | None:
    """سببُ رفضٍ قاطعٍ رغم التداخل — أو `None` حين لا تعارض.

    يُستدعى بعد حساب التداخل ويتقدّم عليه: التداخلُ يَعُدّ الكلمات، وهذا يقرأ
    ما تعنيه. Returns a human reason (Arabic) or None."""
    desc = code_desc or ""
    if not desc:
        return None
    # (١) صفةُ المنتج داخل المقطع المنفيّ = تأكيدٌ لِما يستثنيه الرمز.
    negated = _negated_terms(desc)
    if negated:
        clash = [t for t in product_terms if _covered(t, sorted(negated))]
        if clash:
            return (f"وصفُ الرمز يستثني صراحةً ما يؤكّده اسمُ المنتج "
                    f"({'، '.join(clash)})")
    # (٢) صفةُ درجةٍ في اسم المنتج أمام رمزٍ محدودٍ بعتبةٍ رقمية.
    if _THRESHOLD_RE.search(desc) or _NEGATION_SPAN_RE.search(desc):
        degree = [t for t in product_terms if t in _DEGREE_TERMS]
        if degree:
            return (f"الرمزُ محدودٌ بعتبةٍ/نفيٍ رقميّ واسمُ المنتج يحمل صفةَ "
                    f"درجة ({'، '.join(degree)}) — التمييزُ رقميٌّ لا لفظيّ، "
                    "فلا يُحسَم بتطابق الكلمات")
    return None


def _overlap_stats(p_terms: list[str], desc_terms: list[str]
                   ) -> tuple[list[str], list[str], float]:
    """نواةُ حساب التداخل المشتركة — (المُغطّى، الناقص، نسبة التداخل).

    مُستخرَجةٌ (الموجة ٣ — التصنيف العام) كي يستعملها `confirm_hs` (وصفٌ من
    صفّ CSV) و`confirm_against_description` (وصفٌ حرٌّ — من نموذجٍ أو أيّ
    مصدر) بمنطقٍ واحدٍ لا نسختين متوازيتين قابلتين للانحراف."""
    shared = [t for t in p_terms if _covered(t, desc_terms)]
    missing = [t for t in p_terms if not _covered(t, desc_terms)]
    overlap = round(len(shared) / len(p_terms), 2) if p_terms else 0.0
    return shared, missing, overlap


def confirm_against_description(product_name: str, hs_code: str,
                                code_desc: str,
                                min_overlap: float | None = None) -> dict:
    """قِس تطابق صفات المنتج مع **وصفٍ حرّ** لرمزٍ ما — نفس شكل/عقد
    `confirm_hs` بالضبط، لكن بلا اشتراط وجود الرمز في بذرة CSV.

    الاستعمال (الموجة ٤ — عكس التدفّق: النموذج يقترح دوماً، القائمة تتحقّق
    فقط): مرشّحٌ اقترحه النموذج يُصادَق عليه بوصفه **الرسمي الذي قدّمه
    النموذج نفسه** — عقد عدم الاختلاق لا يزال ساريًا: لا نثق برمزٍ لمجرّد
    ادّعائه، بل نقيس تداخل الصفات المميّزة مع الوصف المُقدَّم فعليًا، تمامًا
    كما نفعل مع صفّ القائمة الرسمية. `code_desc` فارغ => `confirmed=None`
    (لا وصف = لا حكم)."""
    p_terms = _tokens(product_name)
    desc = (code_desc or "").strip()
    if not desc:
        return {"confirmed": None, "hs_code": str(hs_code or ""),
                "code_desc": "", "product_terms": p_terms,
                "shared_terms": [], "missing_terms": [], "overlap": None,
                "reason": "لا وصفَ متاحاً لهذا الرمز — تعذّر تأكيده"}
    if not p_terms:
        return {"confirmed": None, "hs_code": str(hs_code or ""),
                "code_desc": desc, "product_terms": [],
                "shared_terms": [], "missing_terms": [], "overlap": None,
                "reason": "اسم المنتج بلا صفات قابلة للمطابقة"}
    desc_terms = _tokens(desc)
    shared, missing, overlap = _overlap_stats(p_terms, desc_terms)
    threshold = min_overlap if min_overlap is not None else _min_overlap()
    confirmed = overlap >= threshold
    # وعيُ النفي **وحالةُ التصنيع** يتقدّمان على التداخل مهما بلغ.
    _conflict = (_negation_conflict(p_terms, desc)
                 or _process_state_conflict(p_terms, desc))
    if _conflict:
        return {"confirmed": False, "hs_code": str(hs_code or ""),
                "code_desc": desc, "product_terms": p_terms,
                "shared_terms": shared, "missing_terms": missing,
                "overlap": overlap, "reason": _conflict,
                "negation_conflict": True}
    if confirmed:
        reason = "وصف الرمز يشمل صفات المنتج المميّزة"
    else:
        reason = ("وصف الرمز «" + desc + "» لا يشمل الصفة/الصفات "
                  "المميّزة: " + "، ".join(missing))
    return {"confirmed": confirmed, "hs_code": str(hs_code or ""),
            "code_desc": desc, "product_terms": p_terms,
            "shared_terms": shared, "missing_terms": missing,
            "overlap": overlap, "reason": reason}


def confirm_hs(product_name: str, hs_code: str,
               path: str = "data/hscodes_full.csv") -> dict:
    """قِس تطابق صفات المنتج المميّزة مع وصف الرمز المُصنَّف — عقد التأكيد.

    يعيد dict: {confirmed, hs_code, code_desc, product_terms, shared_terms,
    missing_terms, overlap, reason}. `confirmed=False` حين يقلّ تداخل صفات
    المنتج المغطّاة عن العتبة (`SILK_HS_CONFIRM_MIN_OVERLAP`) — أي أن صفةً
    مميّزةً للمنتج غائبة عن وصف الرمز. لا اختلاق: رمزٌ غير موجود في البذرة =>
    `confirmed=None` (غير قابل للتأكيد) لا False كاذبة. مبنيّةٌ الآن فوق
    `confirm_against_description` (نواةٌ واحدة مشتركة) — راجع تلك للوصف الحرّ."""
    p_terms = _tokens(product_name)
    row = _find_row(hs_code, path)
    if row is None:
        return {"confirmed": None, "hs_code": str(hs_code or ""),
                "code_desc": "", "product_terms": p_terms,
                "shared_terms": [], "missing_terms": [], "overlap": None,
                "reason": "الرمز خارج بذرة التصنيف — تعذّر تأكيده"}
    if not p_terms:
        return {"confirmed": None, "hs_code": str(hs_code or ""),
                "code_desc": _code_desc(row), "product_terms": [],
                "shared_terms": [], "missing_terms": [], "overlap": None,
                "reason": "اسم المنتج بلا صفات قابلة للمطابقة"}
    # مطابقةٌ ضد **كل** صفات وصف الصفّ (name_ar + name_en + keywords) — نفس
    # نطاق `_code_terms` الأصلي، لا الاسم المعروض فقط (`_code_desc` وحده
    # قد يخلو من كلماتٍ مفتاحية تحسم التداخل، كما في العيّنة الأصلية التي
    # أسّست هذا الحارس أصلاً — راجع الملفّ العلوي).
    c_terms = _code_terms(row)
    shared, missing, overlap = _overlap_stats(p_terms, c_terms)
    confirmed = overlap >= _min_overlap()
    desc = _code_desc(row)
    # وعيُ النفي يُقاس على **كلّ** نصّ الصفّ (الاسمان + الكلمات المفتاحية)،
    # لا على الوصف المعروض وحده: عتبةُ «not exceeding 1%» قد تعيش في name_en
    # بينما `_code_desc` يعيد name_ar القصير.
    _full_desc = _FIELD_SEP.join(
        str(row.get(f) or "")
        for f in ("name_ar", "name_en", "keywords",
                  "description_en", "keywords_ar"))  # المخطّطان معاً
    _conflict = (_negation_conflict(p_terms, _full_desc)
                 or _process_state_conflict(p_terms, _full_desc))
    if _conflict:
        return {"confirmed": False, "hs_code": str(hs_code or ""),
                "code_desc": desc, "product_terms": p_terms,
                "shared_terms": shared, "missing_terms": missing,
                "overlap": overlap, "reason": _conflict,
                "negation_conflict": True}
    if confirmed:
        reason = "وصف الرمز يشمل صفات المنتج المميّزة"
    else:
        reason = ("وصف الرمز «" + desc + "» لا يشمل الصفة/الصفات "
                  "المميّزة: " + "، ".join(missing))
    return {"confirmed": confirmed, "hs_code": str(hs_code or ""),
            "code_desc": desc, "product_terms": p_terms,
            "shared_terms": shared, "missing_terms": missing,
            "overlap": overlap, "reason": reason}


def is_flagged(confirmation: object) -> bool:
    """هل الرمز مُعلَّم غير مؤكَّد؟ — True فقط عند `confirmed is False`.

    None (غير قابل للتأكيد) لا يُعامَل تعليماً — لا نُطأطئ ثقة على مجهول
    (عقد عدم الاختلاق: لا نُعلن عيباً بلا دليل)."""
    return isinstance(confirmation, dict) and confirmation.get("confirmed") is False


def flagged_conf_cap() -> float:
    """سقفُ ثقةِ الحكم عند تعليم رمز HS — `SILK_HS_FLAGGED_CONF_CAP` (0.5)."""
    try:
        return float(os.environ.get("SILK_HS_FLAGGED_CONF_CAP", "0.5"))
    except (TypeError, ValueError):
        return 0.5


def cap_confidence_for_flagged_hs(verdict: "dict | None",
                                  confirmation: object) -> "dict | None":
    """PR A §A1 (بلاغ تحليل ٧): مصدرٌ واحدٌ لثقةٍ مسقوفة عند تعليم الرمز.

    كان السقف يُطبَّق في طبقة العرض وحدها (`silk_render._deep_research_view`)
    **بعد** أن جمّد الكاتب النسخة غير المسقوفة (0.73) في المتن — فظهر الغلاف
    «ثقة منخفضة (50%)» بينما §4 «الثقة متوسطة (73%)». الحلّ تمريرُ القيمة
    المسقوفة نفسها للكاتب: هذا المُسقِّف الواحد يُستدعى قبل الكاتب (المسار
    الرئيسي + إعادة التوليد) **و** في طبقة العرض (فيبقى idempotent). ينغّم إلى
    الأدنى فقط ولا يرفع ثقةً قط؛ رمزٌ مؤكَّد/غير قابلٍ للتأكيد (None) لا يُسقَّف
    (عقد عدم الاختلاق: لا نُطأطئ ثقةً على مجهول). يعيد القاموس كما هو إن لم
    ينطبق شيء (لا نسخة زائدة)."""
    if not isinstance(verdict, dict) or not is_flagged(confirmation):
        return verdict
    cap = flagged_conf_cap()
    out = verdict
    c = out.get("confidence")
    if isinstance(c, (int, float)) and not isinstance(c, bool) and c > cap:
        out = {**out, "confidence": cap}
    ai = out.get("ai")
    if isinstance(ai, dict) and isinstance(ai.get("confidence"), (int, float)) \
            and not isinstance(ai.get("confidence"), bool) \
            and ai["confidence"] > cap:
        out = {**out, "ai": {**ai, "confidence": cap}}
    return out


# ══════════════ التباسُ المحور (بلاغ المُشرِف — الالتباس اللفظيّ) ════════════
#
# `confirm_hs` تداخلٌ لفظيّ صرف: «حليب» تطابق 040110/040120/040140/0402 معاً
# لأنّ الفارقَ بينها **نسبةُ دهنٍ/حالةُ حفظٍ** لا كلمةٌ في اسم المنتج. حين
# يمرّ اسمٌ عامّ (بلا صفةِ دهنٍ/حفظ) فقد يُؤكَّد لفظياً (`confirmed=True`)
# فيمضي الخطّ صامتاً على البند الأدنى (040110) بدل أن **يُطالَب المشغّل
# بالاختيار**. هذا الكاشفُ يرصد ذلك الالتباس بيانياً (لا اسمَ منتج/رمز صلب):
# ترويسةٌ تنقسم بمحورٍ رقميّ (≥بندين شقيقين) واسمٌ لا يحمل صفةَ درجةٍ تُثبِّت
# البند => التباسٌ يستوجب حواراً، حتى لو أكّده التداخل اللفظيّ.
_DAIRY_PCT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")


def axis_disambiguation_needed(product: str, hs_code: str,
                               path: str = "data/hscodes_full.csv") -> bool:
    """هل الرمزُ داخل ترويسةٍ متعدّدةِ البنود على محورٍ رقميّ، واسمُ المنتج لا
    يُثبِّت أيَّ بند؟ — التباسٌ يستوجب حواراً (نسبةُ الدهن/حالةُ الحفظ صفةٌ
    رقمية يجيب عنها المنتج، فلا يُفترَض البند الأدنى صامتاً).

    بياناتٌ لا حالةُ منتج: الأشقّاءُ من المرجع الرسميّ (`axis_siblings`)،
    وصفاتُ الدرجة من `_DEGREE_TERMS`. اسمٌ يحمل صفةَ درجةٍ («كامل الدسم») أو
    نسبةً مئوية صريحة يُثبِّت البند => لا التباس."""
    code = str(hs_code or "").strip()
    if not code:
        return False
    try:
        import silk_hs_dialog
        sibs = silk_hs_dialog.axis_siblings(code)
    except Exception:  # noqa: BLE001 — كاشفٌ إضافيّ لا يكسر البوّابة
        return False
    if len(sibs) < 2:
        return False               # لا محورَ رقميّ — لا التباسَ من هذا النوع
    toks = _tokens(product or "")
    if any(t in _DEGREE_TERMS for t in toks):
        return False               # اسمٌ يحمل صفةَ درجةٍ يُثبِّت البند
    if _DAIRY_PCT_RE.search(product or ""):
        return False               # نسبةٌ صريحة في الاسم تُثبِّت البند
    return True                    # اسمٌ عامّ + ترويسةٌ متعدّدة => التباس


def deterministic_candidates(product: str, top_n: int = 3,
                             path: str = "data/hscodes_full.csv") -> list[dict]:
    """مرشّحو الرمز من البذرة الحتميّة — بلا نداء كلود وبلا شبكة وبلا تكلفة.

    نفس شكل مرشّحي `silk_hs_classifier.classify_general` (`hs6` / `description_ar`
    / `reason_ar` / `confidence`) كي تعرضهما الواجهةُ بمكوّنٍ واحد. يُستعمَل في
    ردّ بوّابة الثقة: المستخدمُ يحتاج **خياراتٍ** لا رفضاً عارياً."""
    from silk_hs_resolver import resolve_all
    import silk_hs_dialog
    hits = [dp for dp in resolve_all(product or "", top_n=top_n, path=path)
            if dp.value is not None]
    # نفسُ نقطة اختناق العرض: الوصفُ من المرجع الرسميّ لا من البذرة، وأشقّاءُ
    # المحور الرقميّ كاملون. الثقةُ الحتمية تُنقَل كما هي (حسابٌ لا نصّ).
    scores = {dp.value: dp.confidence for dp in hits}
    rows = silk_hs_dialog.build_candidates(
        product, [dp.value for dp in hits],
        reasons={dp.value: dp.note for dp in hits})
    for r in rows:
        r["confidence"] = scores.get(r["hs6"])
    return rows


# حارسٌ للتمييز بين «لم يمرّر المستدعي ثقةً إطلاقاً» (سلوكٌ قديم — لا بوّابة
# ثقة) و«مرّرها None» (تصنيفٌ بلا ثقة — يُحجَب). لا يجوز خلطهما.
_UNSET = object()


def confidence_block(product: str, hs_code: str | None,
                     hs_confidence: object,
                     path: str = "data/hscodes_full.csv") -> dict | None:
    """احجب رمزاً ثقتُه غائبةٌ أو دون العتبة — تفاصيل 422 أو `None` للمرور.

    `None`/غير رقمية => حجب (هذه حالةُ «ثقة التصنيف —» حرفياً: تصنيفٌ بلا
    ثقةٍ معلومة ليس تصنيفاً محسوماً). الردّ يحمل **مرشّحين حتميّين** ليختار
    المستخدم، لا رفضاً عارياً — نفس عقد `preflight_block`."""
    if not hs_code or not confidence_gate_enabled():
        return None
    threshold = min_confidence()
    try:
        conf = None if hs_confidence is None else float(hs_confidence)
    except (TypeError, ValueError):
        conf = None
    if conf is not None and conf >= threshold:
        return None
    shown = "غير معلومة" if conf is None else f"{conf:.2f}"
    candidates = deterministic_candidates(product, path=path)
    # بلاغ «الطاحونة» (2026-08-29): الذيل كان يقول «اختر من المرشّحين أدناه»
    # مهما كانت القائمة — واسمُ علامةٍ تجارية لا يطابق أيّ صفٍّ في المرجع
    # فتعود فارغة، وزرُّ الاختيار في شاشة المصنع لا يظهر إلا بوجود مرشّحين
    # (`web/platform.html:_hsCandidates`). النتيجة: رسالةٌ تُحيل إلى «أدناه»
    # الخالية — طريقٌ مسدود لا مخرج منه إلا رمزٌ جمركيّ بيد المالك. القاعدة:
    # **لا تَعِد بمخرجٍ قبل أن تُثبِت وجوده**؛ والنصّ يقول ما يُغلق الفجوة
    # فعلاً (وصفُ المنتج لا اسمُ العلامة).
    tail = PICK_TAIL if candidates else NO_CANDIDATES_TAIL
    return {
        "error": "hs_confidence_too_low",
        "message": (f"ثقةُ تصنيف «{product}» إلى رمز HS {hs_code} {shown} "
                    f"(الحدّ الأدنى {threshold:.2f}) — لن يبدأ التحليل على "
                    "رمزٍ غير محسوم: رمزٌ خاطئ يُعيد تأطير كل رقمٍ لاحق. "
                    + tail),
        "hs_code": hs_code,
        "hs_confidence": conf,
        "min_confidence": threshold,
        "candidates": candidates,
        "candidates_source": "deterministic",
    }


def revalidate(product: str, hs_code: str | None,
               hs_confidence: object = None,
               path: str = "data/hscodes_full.csv") -> dict | None:
    """أعِد التحقّق من رمزٍ **مخزَّن** يُعاد تشغيلُه — وسمٌ لا حجب.

    `resume` وإعادةُ توليد التقرير يُعيدان استعمالَ رمزٍ حُسِم في الماضي: حجبُهما
    يُفقِد المالكَ عملاً مدفوعاً سبق أن اكتمل (والبعثات المخزَّنة تُعاد بلا نداء
    جديد) — لكنّ تمريرَهما بصمتٍ يُعيد إنتاج تقريرٍ على رمزٍ ربّما صار خاطئاً.
    فالعقد هنا: **يمرّ ويُوسَم**. تُعيد `None` حين لا شيء يُقال (الرمزُ يوافق
    حُكمَ اليوم ويجتاز التأكيد والعتبة)، وإلا dict يُرفَق بالنتيجة فتعرضه طبقةُ
    العرض في «حدود هذا التقرير».

    قراءةٌ حتميّة صرفة: صفر شبكة، صفر نداء كلود، صفر تكلفة."""
    code = str(hs_code or "").strip()
    if not code:
        return None
    from silk_hs_resolver import resolve
    dp = resolve(product or "", path=path)
    conf_contract = confirm_hs(product or "", code, path)
    notes: list[str] = []
    if dp.value and dp.value != code:
        notes.append(f"المُحلِّل الحتمي اليوم يعيد {dp.value} لهذا الاسم "
                     f"لا {code} المخزَّن")
    if is_flagged(conf_contract):
        _missing = "، ".join(conf_contract.get("missing_terms") or [])
        # وصفٌ فارغ كان يُطبَع «» حرفياً في «حدود هذا التقرير» (دراسة #10) —
        # غيابُ الوصف يُعلَن لا يُقتبَس فارغاً (عقد عدم الاختلاق).
        _desc = (conf_contract.get("code_desc") or "").strip()
        notes.append(
            (f"وصف الرمز المخزَّن «{_desc}» " if _desc
             else "وصف الرمز المخزَّن غير متاح في المرجع، والتأكيد اللفظي ")
            + "لا يشمل صفة المنتج المميّزة"
            + (f" ({_missing})" if _missing else ""))
    try:
        _c = None if hs_confidence is None else float(hs_confidence)
    except (TypeError, ValueError):
        _c = None
    if _c is not None and _c < min_confidence():
        notes.append(f"ثقةُ التصنيف {_c:.2f} دون العتبة "
                     f"{min_confidence():.2f} المعمول بها اليوم")
    if not notes:
        return None
    return {
        "agrees_with_resolver_today": bool(dp.value and dp.value == code),
        "stored_hs": code,
        "resolver_today": dp.value,
        "resolver_confidence_today": dp.confidence,
        "confirmed": conf_contract.get("confirmed"),
        "notes": notes,
        "message": ("رمزُ HS المستعمَل في هذه التشغيلة أُعيد من سجلٍّ سابق ولم "
                    "يَعُد يوافق حُكمَ التصنيف اليوم: " + "؛ ".join(notes)
                    + ". أعِد تصنيف المنتج قبل الاعتماد على أرقام هذا التقرير."),
    }


def seed_coverage(path: str = "data/hscodes_full.csv") -> dict:
    """تغطيةُ بذرة التصنيف — كم صفّاً يملك حارساً دلالياً عربياً وكم لا يملك.

    صفٌّ بلا `name_ar` **وبلا** `keywords` لا يمكن بلوغُه من اسمٍ عربي إطلاقاً
    (المُحلِّل يطابق العربية على هذين الحقلين)، فيصير **رمزَ إمدادٍ فقط**: لا
    يُنتَج إلا حين يُمرَّر صراحةً — وهناك بالضبط تعيش حادثةُ 040110. يُستعمَل
    في قفلِ انحدارٍ يمنع نموَّ هذا العدد بلا قرار."""
    import csv as _csv
    total = ar = kw = guarded = 0
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                total += 1
                # المقياسُ كان أعمى عن الملفّ الحيّ (بلاغ المالك «تحديد HS
                # بدقة»): يقرأ أعمدةَ البذرة المتروكة (`name_ar`/`keywords`)
                # فيعيد `arabic_guarded: 0` عن مرجعٍ فيه مئاتُ الصفوف
                # المُحصَّنة في `keywords_ar`. أداةُ قياسٍ لا ترى ما تقيسه
                # أسوأُ من غيابها: تُطمئِن كذباً. تُقرأ الأعمدةُ الثلاثة.
                _ar_kw = (row.get("keywords_ar") or "").strip()
                has_ar = bool((row.get("name_ar") or "").strip())
                has_kw = bool((row.get("keywords") or "").strip() or _ar_kw)
                ar += has_ar
                kw += has_kw
                guarded += bool(has_ar or has_kw or _ar_kw)
    except OSError:
        return {"total": 0, "with_name_ar": 0, "with_keywords": 0,
                "arabic_guarded": 0, "supply_only": 0}
    return {"total": total, "with_name_ar": ar, "with_keywords": kw,
            "arabic_guarded": guarded, "supply_only": total - guarded}


def _norm_hs6(code) -> str:
    return "".join(ch for ch in str(code or "") if ch.isdigit())[:6]


def _code_in_candidates(hs_code: str | None, candidates: list | None) -> bool:
    """هل الرمز المُدخَل أحدُ مرشّحي المحور المعروضين؟ — مقارنة على HS6
    المطبَّع (بلا نقاط/فراغات) لا على النصّ الخام."""
    _n = _norm_hs6
    target = _n(hs_code)
    if len(target) < 6:
        return False
    for c in candidates or []:
        code = c.get("hs6") or c.get("code") if isinstance(c, dict) else c
        if _n(code) == target:
            return True
    return False


def _contract_settlement(contract: object, hs_code: str | None
                         ) -> dict | None:
    """هل هذا عقدُ تصنيفٍ معتمَدٌ لهذا الرمز بعينه؟ — وما بقي مفتوحاً.

    يعيد `None` حين لا عقدَ صالحاً (فيسلك المستدعي المسارَ القديم
    حرفياً)، وإلا قاموساً صغيراً: `axis_open` وحده اليوم — هل بقي
    سؤالُ المحور مفتوحاً؟ فحصُ المحور في `silk_hs_pipeline._decide`
    يجري على أعلى مرشّحٍ **قبل** كل فروع الاعتماد، إلا مخرجَ النموذج
    المُرسى (`llm_grounded` — يقع بعده فلم يُفحَص محورُ رمزِه) ورمزَ
    «صريحٌ باسمٍ فارغ» (`explicit_unverified` — لا اسمَ فُحِص عليه
    شيء أصلاً)."""
    if not isinstance(contract, dict) or not hs_code:
        return None
    import silk_hs_pipeline as _pipe   # استيرادٌ كسول — لا دورة وحدات
    if contract.get("classification_status") != _pipe.APPROVED:
        return None
    if _norm_hs6(contract.get("final_hs_code")) != _norm_hs6(hs_code):
        return None
    method = str(contract.get("classification_method") or "")
    return {"axis_open": method in (_pipe.METHOD_LLM_GROUNDED,
                                    "explicit_unverified")}


def _settled_probe(contract: object, hs_code: str | None) -> dict | None:
    """تقريرُ مجسّ المحور الذي حَسَم العقدَ لهذا الرمز — أو `None`.

    حين يكون العقدُ معتمَداً بقياس المجسّ نفسِه (`probe_report` يحمل
    التقريرَ الكامل ورمزُه هو الرمزُ النهائي)، فالقياسُ **جرى** — يُعاد
    تقريرُه provenance كما كانت تعيده إعادةُ القياس، بلا استعلامِ ويبٍ
    ثانٍ ولا استرجاعٍ ثانٍ."""
    if _contract_settlement(contract, hs_code) is None:
        return None
    report = contract.get("probe_report")
    if not isinstance(report, dict) or not report.get("hs6"):
        return None
    if _norm_hs6(report.get("hs6")) != _norm_hs6(hs_code):
        return None
    return report


def preflight_block(product: str, hs_code: str | None,
                    hs_confirmed: bool = False,
                    path: str = "data/hscodes_full.csv",
                    allow_claude: bool = False,
                    ingredients: list | None = None,
                    category: str | None = None,
                    instruction: str = "",
                    hs_confidence: object = _UNSET,
                    user_supplied: bool = False,
                    settled_contract: dict | None = None) -> dict | None:
    """نقطةُ الاختناق المشتركة الوحيدة للبوّابة — the ONE choke-point both
    `/analyze` و`/research` يستدعيانها قبل أيّ إنفاق (الموجة ٢، تدقيق
    المُشرِف 2026-07-21: الحادثة الأصلية أُصلِحت على `/research` فقط ثم
    عاودت الظهور — «إصلاحٌ على مسارٍ واحد نصفُ إصلاح»). تُعيد `dict` تفاصيل
    422 (`error`, `message`, `hs_confirmation`, `candidates`) أو `None` إن
    كان الرمز مؤكَّداً/غير محسوم/الصمّام مُطفأ صراحةً/المستخدم أكّد صراحةً.

    منطقٌ واحدٌ يعيش هنا — لا نسخة مكرّرة داخل كل معالج HTTP؛ المعالجات
    تستدعي هذه الدالة فقط ثم ترفع `HTTPException` بنفسها (هذه الوحدة لا
    تستورد fastapi عمداً — تبقى مكتبة منطق صرفة بلا إطار HTTP).

    الموجة ٣ (المصنّف العام، systemic fix): رمزٌ مُعلَّم (`confirmed=False`)
    لا يُعاد بسبب رفضٍ عارٍ بعد الآن — `silk_hs_classifier.classify_general`
    يُستدعى فوراً (مرشّحون من معرفة النموذج الكاملة بنظام HS، لا بذرتنا
    الجزئية وحدها) فيحمل ردّ الـ422 **مرشّحين فعليّين** (رمز + وصف + سبب)
    يختار المستخدم منهم بنقرة — لا مجرّد «حاول مرة أخرى» بلا توجيه.
    `allow_claude` (يُقرَّره طبقة الـAPI عبر نفس بوّابة القياس التي يستعملها
    `/classify_hs` — هذه الوحدة لا تستورد `silk_usage`/`fastapi` عمداً)
    يتحكّم فقط بهل نداء كلود مسموحٌ هذه المرّة؛ المرشّحون الحتميّون (بذرتنا)
    يظهرون دائماً بلا أي نداء.

    بوّابةُ الثقة (بلاغ «حليب نادك»): يمرّر المستدعي `hs_confidence` صراحةً
    فتُفحَص **أولاً** (أرخص — بلا أيّ نداء) قبل التطابق الدلالي. المستدعي الذي
    لا يمرّرها يحتفظ بالسلوك القديم حرفياً (`_UNSET` ≠ `None`)."""
    if not hs_code or hs_confirmed:
        return None
    # (١) بوّابة الثقة — صمّامٌ مستقلّ، تسبق التطابق الدلالي.
    if hs_confidence is not _UNSET:
        low = confidence_block(product or "", hs_code, hs_confidence, path)
        if low is not None:
            return low
    # (٢) بوّابة التطابق الدلالي — كما كانت، بصمّامها الخاص.
    if not gate_enabled():
        return None
    # (٣) عقدُ التصنيف الجاهز (المهمة ١٤ — قاعدة المالك: «الآلةُ
    # التصنيفية مرّةً واحدة لكل طلب»): مستدعٍ حسم للتوّ العقدَ عبر
    # `silk_hs_pipeline.classify` يمرّره هنا، فلا يُعاد تشغيلُ الآلة
    # نفسِها (استرجاعُ `deterministic_candidates` ثانيةً، تأكيدٌ
    # دلاليّ ثانٍ، نداءُ `classify_general` ثانٍ) على منتجٍ أجاب
    # الخطُّ أسئلتَه للتوّ. التشغيلةُ الثانية لم تكن تكراراً بريئاً بل
    # **نقضاً**: بطاقةٌ حسمت المحورَ في الخطّ فيعيد preflight بناء
    # المرشّحين بمقياسٍ آخر ويرُدّ 422 لطلبٍ اعتُمد للتوّ (قياسٌ
    # مباشر 2026-08-31). ما بقي للبوّابة هو ما تملكه وحدها: سؤالُ
    # المحور لرمزٍ لم يواجهه الخطُّ (`axis_open` أدناه — مخرجُ النموذج
    # المُرسى يقع في `_decide` **بعد** فحص المحور). مستدعٍ بلا العقد
    # (كل المستدعين القدامى) يسلك المسارَ كلَّه حرفياً كما كان.
    settled = _contract_settlement(settled_contract, hs_code)
    if settled is not None and not settled["axis_open"]:
        return None
    conf = confirm_hs(product or "", hs_code, path)
    # التباسُ المحور (بلاغ المُشرِف): ترويسةٌ تنقسم بنودها بمحورٍ رقميّ (نسبةُ
    # دهنٍ/سعةٍ/وزن) واسمُ المنتج لا يُثبِّت البند — يُطالَب المشغّل صراحةً
    # بالاختيار بدل المضيّ صامتاً على البند الأدنى، **سواءٌ أكّده التداخلُ
    # اللفظيّ أم علّمه** (التداخل اللفظيّ لا يرى الفارقَ الرقميّ أصلاً: كلاهما
    # «حليب»). يسبق مسارَ التعليم العامّ كي يحمل حدودَ الأشقّاء المفهومة كاملةً
    # (لا مرشّحي المصنّف العام) — مصدرٌ حتميّ صفر تكلفة.
    if axis_disambiguation_needed(product or "", hs_code, path):
        cands = deterministic_candidates(product or "", path=path)
        # رمزٌ أدخله المستخدم بنفسه وهو **أحدُ مرشّحي المحور ذاتهم** = إجابةُ
        # السؤال لا سببٌ لإعادة طرحه: البوّابة تسأل «أيّ بند؟» فإذا سمّاه
        # المشغّل صراحةً وكان ضمن القائمة، فالسؤال محسوم (بلاغ 2026-08-19:
        # 040120 مكتوباً يدوياً كان يُرَدّ 422 بلا مخرج). رمزٌ خارج القائمة
        # يبقى مُبوَّباً كما هو (حارس LESSONS ٧٩).
        if user_supplied and _code_in_candidates(hs_code, cands):
            return None
        if len([c for c in cands if c.get("band_ar")]) >= 2:
            return {
                "error": "hs_axis_disambiguation_needed",
                "message": (
                    f"رمز HS {hs_code} داخل ترويسةٍ تنقسم بنودها بحسب سمةٍ "
                    "رقمية (مثل نسبة الدهن أو حالة الحفظ: طازج/طويل الأمد/"
                    f"مركّز/مجفّف)، واسم المنتج «{product or ''}» لا يحدّد أيّها "
                    "— لن يبدأ التحليل على البند الأدنى افتراضاً. اختر البند "
                    "المطابق أدناه (يظهر حدُّ كلٍّ بلغةٍ مفهومة) أو أدخل رمزاً "
                    "يدوياً قبل بدء التحليل."),
                "hs_confirmation": conf,
                "candidates": cands,
                "candidates_source": "deterministic",
            }
    if settled is not None:
        # المحورُ وحده كان السؤالَ المفتوح وقد فُحِص أعلاه ولم يحجب —
        # التطابقُ الدلاليّ أجاب عنه العقدُ (قياسُ `classify_general`
        # المُرسى نفسِه الذي اعتمد الرمز)، فلا يُستدعى النموذجُ ثانيةً
        # لنقض ما اعتُمد للتوّ.
        return None
    if not is_flagged(conf):
        return None
    from silk_hs_classifier import classify_general
    general = classify_general(product or "", hs_code=hs_code,
                               ingredients=ingredients, category=category,
                               allow_claude=allow_claude, instruction=instruction)
    return {
        "error": "hs_confirmation_needed",
        "message": (f"رمز HS {hs_code} («{conf.get('code_desc')}») "
                    "قد لا يطابق هذا المنتج — الصفة المميّزة غير مشمولة: "
                    f"{'، '.join(conf.get('missing_terms') or [])}. "
                    "اختر من المرشّحين أدناه أو أدخل رمزاً يدوياً قبل بدء "
                    "التحليل."),
        "hs_confirmation": conf,
        "candidates": general.get("candidates") or [],
        "candidates_source": general.get("source"),
    }


# ══════════════ حسمُ السمة الرقمية قبل الحوار (بلاغ المُشرِف) ════════════════
#
# البنودُ داخل الترويسة الواحدة تتمايز بعتبةٍ رقمية (نسبةُ دهنٍ مثلاً) لا
# بكلمة — وهذا بالضبط ما لا يراه `confirm_hs` (كلاهما «حليب»). كان الحلُّ
# السابق: أعرِض حواراً واسألِ المستخدمَ عن العتبة. لكنّ العتبة **رقمٌ يُجيب
# عنه المنتجُ نفسُه**: بطاقةُ العبوة تحمله والويبُ يستشهد به. فالحوارُ
# احتياطٌ لا افتراض، والقياسُ يسبقه دائماً (`silk_hs_attributes`).
#
# نقطةُ اختناقٍ واحدة هنا يستدعيها **كلُّ** معالجٍ ينفق (`/analyze`،
# `/research`، بوّابةُ الالتباس) — إصلاحٌ على مسارٍ واحد نصفُ إصلاح
# (الدرسان ٣٥/٣٧).

def _probe_public(report: dict) -> dict:
    """ما يحتاجه الحوارُ من تقرير القياس — بلا حقولٍ داخلية."""
    return {
        "attribute": report.get("attribute"),
        "label_ar": report.get("label_ar"),
        "unit": report.get("unit"),
        "searched": report.get("searched") or [],
        "missing_ar": report.get("missing_ar") or "",
        "bands_ar": report.get("bands_ar") or [],
    }


def resolve_or_probe(product: str, candidates: list,
                     label_attributes: object = None,
                     allow_web: bool = True,
                     gl: str | None = None) -> dict:
    """احسِم الرمزَ بالسمة الرقمية أو أعِد تقريرَ ما نقص — دوماً dict.

    `report["hs6"]` غيرُ `None` => حُسِم بدليلٍ موسوم (صورةُ عبوة أو رابطُ
    ويب) فلا حوارَ؛ وإلا يحمل التقريرُ ما جُرِّب وما نقص وحدودَ كلّ مرشّح
    بلغةٍ مفهومة كي يعرضها الحوارُ بدل عتبةٍ جمركية خام. لا اختلاق: بلا
    رقمٍ مقيسٍ يقع في نطاقٍ **وحيد** لا يُحسَم رمزٌ أبداً."""
    import silk_hs_attributes as _attrs
    # **قناةُ الأهلية تبقى كما كانت حرفياً.** إكمالُ أشقّاء المحور (إصلاحُ
    # العرض) لا يجعل صفَّ إكمالٍ نتيجةً أبداً: قياسٌ على ٦٠٠ منتجٍ أظهر أنّ
    # تمريرَ المجموعة المكتملة قناةً واحدةً يجعل أربعةَ منتجاتٍ قابلةً للحسم
    # لم تكن كذلك — **توسيعُ تغطية المُحلِّل من بابٍ خلفيّ**، وقد نهى
    # المُشرِف عنه صراحةً. أمّا **حدودُ المحور** فتُبنى من المجموعة الكاملة
    # (قناة `band_context` — عمارةُ المُشرِف 2026-08-31): مرشّحٌ مُقيَّمٌ
    # وحيدٌ من ترويسةٍ رباعيةِ البنود ما زال محوراً قائماً، وقتلُ حدودِه
    # بترشيح أشقّائه كان يقتل قياسَ البطاقة نفسَه قبل أن يقرأ قيمتَها.
    asked = [c for c in (candidates or [])
             if not (isinstance(c, dict) and c.get("axis_completion"))]
    return _attrs.resolve_by_attribute(
        product or "", asked, label_attributes=label_attributes,
        allow_web=allow_web, gl=gl, band_context=list(candidates or []))


def preflight_resolve(product: str, hs_code: str | None,
                      hs_confirmed: bool = False,
                      path: str = "data/hscodes_full.csv",
                      allow_claude: bool = False,
                      ingredients: list | None = None,
                      category: str | None = None,
                      instruction: str = "",
                      hs_confidence: object = _UNSET,
                      label_attributes: object = None,
                      allow_web: bool = True,
                      gl: str | None = None,
                      user_supplied: bool = False,
                      settled_contract: dict | None = None
                      ) -> tuple[str | None, dict | None, dict | None]:
    """البوّابةُ + القياسُ في نداءٍ واحد — `(hs_code, provenance, block)`.

    - `block` غيرُ `None` => ارفع ٤٢٢ بتفاصيله (تحمل الآن `attribute_probe`).
    - `provenance` غيرُ `None` => حُسِم الرمزُ آلياً؛ استعمل `hs_code` المُعاد
      وأرفِق `provenance` بالنتيجة كي يعرض التقريرُ مصدرَ الرمز.
    - كلاهما `None` => الرمزُ الأصليّ مؤكَّدٌ كما كان (السلوك السابق حرفياً).

    `preflight_block` يبقى بعقده الحرفيّ دون تغيير — هذه الدالةُ تغلّفه، فلا
    مستدعٍ قائمٌ ينكسر."""
    # عقدٌ حُسِم بمجسّ المحور داخل الخطّ (المهمة ١٤): القياسُ جرى —
    # تقريرُه هو الدليل ويُعاد provenance كما كانت تعيده إعادةُ القياس،
    # بلا استرجاعٍ ثانٍ (`deterministic_candidates`) ولا استعلامِ ويبٍ
    # ثانٍ. صمّاما البوّابة يُحترمان كما هما: بوّابةُ الثقة أولاً
    # (أرخص)، وصمّامُ `gate_enabled` مُطفأً يعني «لا بوّابةَ ولا حسمَ
    # آليّاً» — فيسقط الاختصارُ ويعود السلوكُ القديم حرفياً.
    _probe_settled = _settled_probe(settled_contract, hs_code)
    if _probe_settled is not None and hs_code and not hs_confirmed \
            and gate_enabled() \
            and (hs_confidence is _UNSET or confidence_block(
                product or "", hs_code, hs_confidence, path) is None):
        if user_supplied:
            # مرآةُ «رمزٌ كتبه المستخدم وهو أحدُ مرشّحي المحور»: يُخدَم
            # رمزُه بلا استبدالٍ ولا provenance — كما كانت البوّابة.
            return hs_code, None, None
        return hs_code, _probe_settled, None
    block = preflight_block(product, hs_code, hs_confirmed, path,
                            allow_claude, ingredients, category, instruction,
                            hs_confidence, user_supplied, settled_contract)
    if block is None:
        return hs_code, None, None
    report = resolve_or_probe(product, block.get("candidates") or [],
                              label_attributes=label_attributes,
                              allow_web=allow_web, gl=gl)
    if report.get("hs6"):
        # المجسّ يقترح ولا يستبدل رمزاً كتبه المستخدم بنفسه: استبدالٌ صامت
        # لرمزٍ مقصود يُفقِد المشغّل سيطرته على تصنيفه (بلاغ 2026-08-19).
        if user_supplied and hs_code and _norm_hs6(report["hs6"]) != _norm_hs6(hs_code):
            # الرمزُ يبقى للمستخدم، لكن **البوّابة لا تُبتلَع**: يعود الحظر
            # كما لو لم يُحسَم شيء، فيبقى الإفصاح وسجلّ المشغّل قائمين
            # (مراجعة ذاتية §58 — كان يمرّ بلا provenance ولا أثر).
            return hs_code, None, {**block, "attribute_probe": _probe_public(report),
                                   "user_supplied_kept": hs_code}
        return report["hs6"], report, None
    return hs_code, None, {**block, "attribute_probe": _probe_public(report)}


if __name__ == "__main__":  # فحص يدوي — عيّنات صحيحة وخاطئة
    for name, code in [("زبدة الفول السوداني", "040510"),
                       ("تمور", "080410"),
                       ("عسل سدر", "040900"),
                       ("زبدة", "040510"),
                       ("olive oil", "150910")]:
        c = confirm_hs(name, code)
        print(f"{name:>22} / {code}  confirmed={c['confirmed']}  "
              f"overlap={c['overlap']}  missing={c['missing_terms']}")
