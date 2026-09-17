"""مخزنُ الأرقام — one figure, one identity (الصنف ٦ من موجة عيوب التقرير).

> **العيبُ المرصود:** «الحصة السعودية 10.44% في الملخّص و12.42% في الجدول»،
> و«10.44% هي أيضاً حصةُ الصين لعام 2023». رقمٌ واحدٌ بقراءتين، وقراءةٌ واحدة
> لكيانين.
>
> **الجذر:** الأرقام تصل الكاتبَ **نصّاً بلا هوية** — `silk_ai_judge._facts`
> يبني أسطراً كـ«[trade_flow] 18400000 | المصدر: … | ثقة 0.8 | واردات 2024»،
> فلا شيء يربط رقماً مكتوباً في §1 برقمٍ مكتوبٍ في §6. والكاتبُ ينسخ ويُعيد
> الاشتقاق بحرّية، والعارضُ يقرأ قراءةً أخرى من السجلّ.
>
> **الحلّ:** لكلّ قراءةٍ **معرّفٌ ثابت** (`F1`, `F2`…) يحمل
> `{id, metric, value, year, source, method, confidence}`؛ والموجّه يُخاطِب
> الكاتبَ بالمعرّف؛ وقاعدةٌ **واحدةٌ موثَّقة** تختار القراءة التي تُغذّي
> بطاقة القرار.

**خلف رايةٍ مطفأةٍ افتراضياً** (`SILK_FIGURE_STORE=1`): بلا الراية لا يُبنى
المخزنُ ولا يُحقَن معرّفٌ في موجّه، ولا يدخل الفحصُ مجموعةَ الحجب — السلوكُ
السابق هو نفسُه حرفياً (قرار المالك: لا حجب جديداً بلا راية).

منطقُ قراءةٍ صرف: صفرُ شبكة، صفرُ تعديلٍ على أيّ قيمة — تصنيفٌ وتسميةٌ فقط،
مثل `silk_render` تماماً. عقدُ عدم الاختلاق سليم: قراءةٌ بلا قيمةٍ لا تُخزَّن.
"""
from __future__ import annotations

import os
import re

FLAG = "SILK_FIGURE_STORE"


def enabled() -> bool:
    """هل رايةُ الصنف ٦ مفعّلة؟ — نمطُ `silk_gap_recovery.enabled` القائم."""
    return os.environ.get(FLAG, "").strip().lower() in ("1", "true", "yes")


# ── تصنيفُ المؤشِّر · metric classification ──────────────────────────────────
# حتميّ من **ملاحظة** القراءة (لا من قيمتها): الملاحظةُ هي ما تكتبه البعثةُ
# الحيّة فعلاً («واردات 2024»، «مرآة صادرات الشركاء 2023»، «HHI تركّز»).
# الأطولُ أوّلاً كي لا يبتلعَ مؤشّرٌ جزءاً من آخر.
_METRIC_PATTERNS: tuple = (
    ("mirror_imports", re.compile(r"مرآة|mirror", re.I)),
    ("supplier_share", re.compile(r"حصة|نصيب\s+سوق|share", re.I)),
    ("concentration", re.compile(r"HHI|تركّز|تركز|concentration", re.I)),
    ("growth", re.compile(r"نمو|نموّ|CAGR|معدّل النمو|growth", re.I)),
    ("tariff", re.compile(r"تعريفة|رسم\s+جمركي|جمرك|tariff|duty", re.I)),
    ("retail_price", re.compile(r"سعر\s+(?:ال)?(?:رف|تجزئة)|retail\s+price", re.I)),
    ("border_price", re.compile(r"سعر\s+(?:ال)?حدود|سعر\s+الاستيراد|border", re.I)),
    ("unit_price", re.compile(r"سعر|price", re.I)),
    ("population", re.compile(r"سكان|نسمة|population", re.I)),
    ("income", re.compile(r"دخل|للفرد|per\s+capita|income|GDP", re.I)),
    ("imports", re.compile(r"واردات|استيراد|imports?", re.I)),
)

# قراءةٌ بالمرآة تُصنَّف مؤشّرَ الواردات نفسَه بطريقةٍ مختلفة — لا مؤشّراً
# آخر: هذا بعينه ما يجعل «قيمتان لمؤشرٍ واحد» قابلاً للكشف أصلاً.
_METHOD_OF_METRIC = {"mirror_imports": ("imports", "mirror"),
                     "imports": ("imports", "direct")}


def _get(row: object, key: str, default=None):
    """قراءةٌ من قاموسٍ أو من كائنِ تقريرٍ — المخزنُ يخدم الطرفين."""
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


# مؤشِّراتٌ **تخصّ كياناً** لا السوقَ ككلّ: «حصة الصين» و«حصة السعودية»
# قراءتان لكيانين لا قراءتان لمؤشِّرٍ واحد. مأخذُ المراجعة الذاتية: التصنيفُ
# كان بالملاحظة **بلا الكيان**، فصار الرقمان تعارضاً — و`metric_value_
# divergence` غيرُ قابلٍ للإصلاح وفي مجموعة الحجب بالراية، فتقريرٌ صحيحٌ
# يسرد حصصَ المورّدين كان يُفشَل. والتمييزُ **بيانيٌّ لا قُطريّ**: مؤهِّلُ
# الملاحظة هو ما بقي بعد طيّ كلماتِ المؤشِّر والأرقام والسنوات.
# **مقصورةٌ على المؤشِّر المرصودِ عيبُه.** جُرِّبت أوسعَ (بأسعار الرفّ
# والحدود) فقِيس أنّ المؤهِّلَ يصير **اسمَ العملة** لا كياناً
# (`retail_price:دينار`) — فيفترق مفتاحُ سعرَين لنفس المؤشِّر ويضيع الكشفُ
# الذي وُضع له الصنفُ ٦. فالتوسيعُ يحتاج قياسَه لا حدسَه.
_ENTITY_SCOPED_METRICS = frozenset({"supplier_share"})
# كلماتُ المؤشِّر **بحدودِ كلمة** — وإلّا ابتلعت «سوق» صدرَ «سوقية» فصار
# المؤهِّلُ «ية» (قِياسٌ على هذه الدالّة نفسِها كشفه قبل الكوميت).
_QUALIFIER_DROP_WORDS_RE = re.compile(
    r"\b(?:حصة|حصه|حصص|نصيب|سوق|سوقية|سوقيه|share|market|سعر|price|رف|"
    r"تجزئة|تجزئه|retail|حدود|border|استيراد|imports?|للكيلوغرام|كجم|كغم|"
    r"كغ|لكل|عبوة|عبوه|متوسط|مرصود|مصرحة|مصرَّحة|value|unit)\b", re.I)
_QUALIFIER_DROP_CHARS_RE = re.compile(r"[%٪\d،,\.\-—()«»/]+")


def qualifier(note: object) -> str:
    """مؤهِّلُ القراءة — ما يبقى من الملاحظة بعد طيّ كلماتِ المؤشِّر وأرقامِه.

    «حصة الصين % 2023» ⇒ «الصين»، و«حصة السعودية % 2023» ⇒ «السعودية».
    وملاحظةٌ بلا مؤهِّلٍ تُعيد فراغاً فيبقى المفتاحُ هو المؤشِّرَ وحدَه.
    """
    rest = _QUALIFIER_DROP_CHARS_RE.sub(" ", str(note or ""))
    rest = _QUALIFIER_DROP_WORDS_RE.sub(" ", rest)
    return " ".join(w for w in rest.split() if len(w) > 2)


def classify(note: object) -> tuple:
    """(المؤشّر، الطريقة) من ملاحظة القراءة — `("other", "reported")` افتراضاً.

    ومؤشِّرٌ يخصّ كياناً يحمل مؤهِّلَه في مفتاحه (`supplier_share:الصين`)
    كي لا يُقرأَ كيانان قراءتين متعارضتين لمؤشِّرٍ واحد.
    """
    text = str(note or "")
    for name, rex in _METRIC_PATTERNS:
        if rex.search(text):
            metric, method = _METHOD_OF_METRIC.get(name, (name, "reported"))
            if metric in _ENTITY_SCOPED_METRICS:
                q = qualifier(text)
                if q:
                    metric = f"{metric}:{q}"
            return metric, method
    return "other", "reported"


_YEAR_RE = re.compile(r"\b(19\d\d|20\d\d)\b")


def _year_of(row: object) -> "int | None":
    """سنةُ القراءة — الحقلُ البنيويّ أوّلاً، ثم سنةٌ صريحةٌ في الملاحظة.

    لا تُستعار سنةٌ من ساعة التشغيل (الصنف ٣): الغيابُ يبقى `None`.
    """
    y = _get(row, "data_year")
    if isinstance(y, (int, float)) and not isinstance(y, bool):
        return int(y)
    m = _YEAR_RE.search(str(_get(row, "note") or ""))
    return int(m.group(1)) if m else None


def _numeric(v: object) -> "float | None":
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build(missions: object, analyst: object = None) -> dict:
    """ابنِ المخزن من بعثاتِ الدراسة (ومن تقاطعات المحلل إن مُرِّرت).

    يعيد `{"figures": [...], "by_metric": {metric: [ids]},
    "decision_reading": {metric: id}}`. كلُّ قراءةٍ **بقيمةٍ رقمية** تُخزَّن
    بمعرّفٍ ثابتٍ مرتَّبٍ (`F1`, `F2`, …) — والترتيبُ على (البعثة، الموضع)
    فيكون المعرّفُ مستقرّاً بين تشغيلتين لنفس المدوّنة.
    """
    figures: list = []
    rows: list = []
    for key in sorted((missions or {}) if isinstance(missions, dict) else {}):
        rep = (missions or {})[key]
        for dp in (_get(rep, "findings") or []):
            rows.append((key, dp))
    by_cat = (_get(analyst, "by_category") or {}) if analyst else {}
    for cat in sorted(by_cat):
        for dp in (by_cat[cat] or []):
            rows.append((f"analyst:{cat}", dp))

    for origin, dp in rows:
        value = _numeric(_get(dp, "value"))
        if value is None:           # عقد عدم الاختلاق: لا قراءةَ بلا قيمة
            continue
        metric, method = classify(_get(dp, "note"))
        figures.append({
            "id": f"F{len(figures) + 1}",
            "metric": metric,
            "value": value,
            "year": _year_of(dp),
            "source": str(_get(dp, "source") or "") or None,
            "method": method,
            "confidence": _numeric(_get(dp, "confidence")),
            "origin": origin,
            "note": str(_get(dp, "note") or ""),
        })

    by_metric: dict = {}
    for f in figures:
        by_metric.setdefault(f["metric"], []).append(f["id"])
    return {"figures": figures, "by_metric": by_metric,
            "decision_reading": {m: decision_reading(figures, m)
                                 for m in by_metric}}


# ── القاعدةُ الواحدة الموثَّقة لاختيار قراءةِ القرار ────────────────────────
# ثلاثةُ مرشِّحاتٍ بترتيبٍ **مُعلَن**، وكلُّ واحدٍ منها له سببٌ يُقال للقارئ:
#   ١) **الأحدثُ سنةً** — قرارُ دخولٍ يُبنى على أحدث ما رُصد، لا على متوسّط
#      تاريخيّ؛ والقراءةُ بلا سنةٍ تتأخّر عن أيّ قراءةٍ بسنة (لا تُرقَّى
#      بمجهولٍ).
#   ٢) **المباشرُ قبل المرآة** — تصريحُ المستورد نفسِه أقربُ إلى الواقع
#      الجمركيّ الذي سيواجهه المصدِّر؛ والمرآةُ بديلٌ عند ضعف التبليغ لا
#      مساويةٌ له (وتمييزُهما عقدٌ محفوظ).
#   ٣) **الأعلى ثقةً** — عند تعادلِ ما سبق.
# وعند تعادل الثلاثة: **أوّلُ معرّفٍ** — لا عشوائيةَ، فالنتيجةُ قابلةٌ للتكرار.
_METHOD_RANK = {"direct": 0, "reported": 1, "mirror": 2}


def decision_reading(figures: list, metric: str) -> "str | None":
    """معرّفُ القراءة التي تُغذّي بطاقة القرار لهذا المؤشّر — أو `None`."""
    cands = [f for f in figures if f["metric"] == metric]
    if not cands:
        return None
    def _key(f: dict) -> tuple:
        return (-(f["year"] or 0),
                _METHOD_RANK.get(f["method"], 1),
                -(f["confidence"] or 0.0),
                int(f["id"][1:]))
    return sorted(cands, key=_key)[0]["id"]


def facts_block(store: dict) -> str:
    """أسطرُ الحقائق **بمعرّفاتها** كما تُحقَن في موجّه الكاتب.

    الغرضُ أن يُخاطِب الموجّهُ الكاتبَ بالمعرّف: «اذكر F3 مرّةً واحدة كاملة
    ثم أَحِل إليه» — فيصير تعارضُ قراءتين قابلاً للكشف بدل أن يُنسَخ الرقمُ
    مرّتين بقيمتين.
    """
    lines: list = []
    for f in (store or {}).get("figures") or []:
        year = f"سنة {f['year']}" if f["year"] else "سنة غير مذكورة"
        method = {"direct": "تصريح مباشر", "mirror": "مرآة",
                  "reported": "مرصود"}.get(f["method"], f["method"])
        conf = ("ثقة غير محسوبة" if f["confidence"] is None
                else f"ثقة {f['confidence']}")
        lines.append(f"- [{f['id']}] {f['value']} | {f['metric']} | {year} | "
                     f"{method} | المصدر: {f['source'] or 'غير مذكور'} | "
                     f"{conf} | {f['note']}")
    return "\n".join(lines) or "(لا أرقام مخزَّنة)"


FIGURE_ID_RULE = (
    "**هويةُ الرقم (إلزامي):** كلُّ رقمٍ في قائمة الحقائق يحمل معرّفاً بين "
    "معقوفتين ([F1]، [F2]…). اذكر الرقمَ كاملاً **مرّة واحدة** في قسمه، ثم "
    "أَحِل إليه لاحقاً بالمعنى لا بإعادة كتابته. **ولا تُعِد اشتقاق رقمٍ له "
    "معرّف**: إن احتجت قيمةً أخرى للمؤشّر نفسِه فاذكر معرّفَها الآخر وسمِّ "
    "الفرق (سنةٌ أخرى، تصريحٌ مباشر مقابل مرآة) — قيمتان لمؤشّرٍ واحد بلا "
    "تسميةِ الفرق خطأٌ يصل القارئ. ولا تنسب قيمةً واحدةً لكيانين مختلفين."
)


if __name__ == "__main__":       # فحصٌ يدويّ سريع على مدوّنةٍ قانونية
    import importlib
    import json
    import sys
    sys.path.insert(0, "tools")
    blob = importlib.import_module(
        "canonical_nigeria_dates").nigeria_dates_research_blob()
    dr = blob["deep_research"]
    st = build(dr.get("missions"), dr.get("analyst"))
    print(facts_block(st))
    print(json.dumps({"by_metric": st["by_metric"],
                      "decision_reading": st["decision_reading"]},
                     ensure_ascii=False, indent=1))
