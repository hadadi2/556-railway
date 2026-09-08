"""تغطية المصادر ووسم «تقدير استرشادي» — Master Prompt Part 2 §D.

كل مؤشرٍ في التقرير المُسلَّم إما: (١) مصدرٌ عموميٌّ مسمّى + تاريخ رصدٍ، أو
(٢) وسمُ «تقدير استرشادي» صريح عند نقطة الاستعمال (لا حاشية وحدها). لا عمود
مصدرٍ عارٍ («—») بلا أحد الخيارين. عتبة قبول: ≥٨٥٪ من المؤشرات بمصدرٍ مسمّى
حقيقي؛ دون ذلك، ضيّق نطاق التقرير وأعلن الفجوة بدل شحن مؤشرات بلا مصدر.

منطق صرف: صفر شبكة، قراءة CSV محلي فقط — نفس نمط `data/requirements_l1.csv`.
"""
from __future__ import annotations

import csv
import os

# وسم «تقدير استرشادي» — يظهر عند **نقطة استعمال** الرقم المُقدَّر (لا في
# حاشية فقط)، مصحوباً بسطر اشتقاق واحد وفرضياته (Master Prompt Part 2، البند ١٢).
INDICATIVE_ESTIMATE_TAG = "تقدير استرشادي"

# قيم مصدرٍ تُعامَل كغيابٍ فعلي — «—» العارية ممنوعة، ووسم التقدير الصريح هو
# البديل الوحيد المقبول (لا صمتٌ ولا اختلاق).
_BLANK_SOURCE_TOKENS = frozenset({
    "", "-", "—", "–", "none", "null", "n/a", "na", "unknown",
    "غير معروف", "غير محدد", "غير متاح", "غير متوفر"})

SOURCE_COVERAGE_MIN_PCT = 85.0

_FAMILY_SOURCES_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data",
    "default_sources_by_family.csv")

_cache: "dict[str, list[dict]] | None" = None


def tag_indicative_estimate(value_text: str, derivation: str) -> str:
    """ألصق وسم «تقدير استرشادي» + سطر اشتقاقٍ واحد عند نقطة استعمال رقمٍ
    مُقدَّر — لا حاشيةٌ منفصلة (Master Prompt Part 2، البند ١٢)."""
    v = str(value_text or "").strip()
    d = str(derivation or "").strip()
    if not d:
        return f"{v} ({INDICATIVE_ESTIMATE_TAG})"
    return f"{v} ({INDICATIVE_ESTIMATE_TAG} — {d})"


def _load_family_sources() -> "dict[str, list[dict]]":
    """مراجع المصادر الافتراضية لكل عائلة منتج (غذاء/نسيج/كيماويات/آلات) —
    مرجعٌ ثابتٌ (كـ`data/requirements_l1.csv`) يُعامَل بحذر: أضِف مصدراً
    برابطه الرسمي الحقيقي فقط، لا رابطاً مختلَقاً."""
    global _cache
    if _cache is not None:
        return _cache
    out: "dict[str, list[dict]]" = {}
    try:
        with open(_FAMILY_SOURCES_CSV, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                fam = (row.get("family") or "").strip().lower()
                if not fam:
                    continue
                out.setdefault(fam, []).append({
                    "source_name": row.get("source_name") or "",
                    "url": row.get("url") or "",
                    "scope": row.get("scope") or ""})
    except OSError:
        out = {}
    _cache = out
    return out


def default_sources_for_family(family: str) -> list[dict]:
    """قائمة المصادر الافتراضية المسمّاة لعائلة منتجٍ (food/textiles/
    chemicals/machinery) — قائمةٌ فارغة لعائلةٍ غير معروفة (لا اختلاق)."""
    return list(_load_family_sources().get(str(family or "").strip().lower(), []))


def known_product_families() -> list[str]:
    return sorted(_load_family_sources().keys())


# وسمُ المنتِج حين يسقط المصدرُ إلى اسمِ البعثة الداخليّ — ليس مصدراً.
MISSION_LABEL_FALLBACK = "mission_label_fallback"


def _is_backed(source: object, note: object, *,
               retrieval_method: object = "",
               source_ids: object = ()) -> bool:
    """هل يحمل هذا المؤشّرُ **مصدراً مسمّى حقيقياً** أو وسمَ تقديرٍ صريحاً؟

    **الموجة B (البند T-01) — تشديدٌ بنيويّ.** كان الشرطُ «أيُّ سلسلةِ مصدرٍ
    غيرِ فارغة»، و`silk_llm_runtime` يُسقِط `source` إلى **اسم البعثة العربيّ**
    حين لا يوجد مصدرٌ عموميّ للنقاط المستشهَد بها — واسمُ البعثة ليس فارغاً
    أبداً. فكان كلُّ مؤشّرٍ يُحتسَب مسنوداً، وتغطيةُ المصادر ١٠٠٪ دائماً على
    مسار المصنع، وعتبةُ الـ٨٥٪ **بنيوياً غيرَ قابلةٍ للإطلاق**.

    الإشارةُ المستعمَلة **سالبةٌ ودقيقة** لا إيجابيةٌ تخمينية: تُرفَض حالتان
    معروفتان بيقين — وسمُ المنتِج `mission_label_fallback`، وسلسلةٌ تطابق
    **اسمَ بعثةٍ** من `silk_missions.MISSIONS` (تغطّي السجلّات السابقة للوسم).
    وما عدا ذلك يبقى مقبولاً كما كان: قائمةٌ إيجابيةٌ لأسماء المصادر كانت
    ستُنتِج سلبيّاتٍ كاذبة (رُصِدت «Google Maps» في مدوّنةٍ قانونية) — وحارسٌ
    يرفض مصدراً حقيقياً أسوأُ من حارسٍ متساهل.
    """
    if str(retrieval_method or "").strip() == MISSION_LABEL_FALLBACK:
        return False
    ids = source_ids or ()
    if isinstance(ids, (list, tuple, set)) and any(
            str(i or "").strip() for i in ids):
        return True
    src = str(source or "").strip()
    if src and src.lower() not in _BLANK_SOURCE_TOKENS:
        if not _is_mission_label(src):
            return True
    return INDICATIVE_ESTIMATE_TAG in str(note or "")


def _mission_labels() -> frozenset:
    """أسماءُ البعثات كما يكتبها `silk_llm_runtime` عند غياب مصدرٍ عموميّ."""
    global _MISSION_LABELS
    if _MISSION_LABELS is None:
        names = set()
        try:
            from silk_missions import MISSIONS
            for row in MISSIONS.values():
                for key in ("name", "key"):
                    v = str((row or {}).get(key) or "").strip()
                    if v:
                        names.add(v.lower())
                        names.add(f"llmagent:{v}".lower())
        except Exception:  # noqa: BLE001 — تعذّر السجلّ = لا رفضَ إضافيّ
            pass
        _MISSION_LABELS = frozenset(names)
    return _MISSION_LABELS


_MISSION_LABELS = None


def _is_mission_label(src: str) -> bool:
    low = src.strip().lower()
    return low in _mission_labels() or low.startswith("llmagent:")


def compute_source_coverage(dr: dict) -> dict:
    """نسبة المؤشرات (DataPoint بقيمةٍ فعلية `value is not None`) التي تحمل
    مصدراً مسمّى حقيقياً أو وسم «تقدير استرشادي» صريح — Master Prompt Part 2
    §D. فجواتٌ معلنة (`value=None`) ليست مؤشراتٍ مُسلَّمة فلا تُحتسَب."""
    total = 0
    backed = 0
    for m in (dr.get("missions") or {}).values():
        # البند T-15: بعثةٌ محفوظةٌ ككائن `AgentReport` خام (لا dict) كانت
        # ترفع `AttributeError` فتُسقِط الفحصَ كلَّه — تُقرَأ بنفس الأسماء.
        findings = (m.get("findings") if isinstance(m, dict)
                    else getattr(m, "findings", None)) or []
        for f in findings:
            get = (f.get if isinstance(f, dict)
                   else (lambda k, d=None, _o=f: getattr(_o, k, d)))
            if get("value") is None:
                continue
            total += 1
            if _is_backed(get("source"), get("note"),
                          retrieval_method=get("retrieval_method", ""),
                          source_ids=get("source_ids", ())):
                backed += 1
    # **لا مؤشّرَ واحد = ليست تغطيةً كاملة.** كان `total == 0` يعيد ١٠٠٪،
    # فتقريرٌ بصفر أدلةٍ يُحتسَب مثالياً ويمرّ بصمت (البند T-01).
    pct = (backed / total * 100.0) if total else 0.0
    return {"total": total, "backed": backed, "pct": pct}
