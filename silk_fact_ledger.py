"""سجلّ الحقائق الواحد — one fact ledger for every report surface (الدرس ٢٦٢).

**الجذر المُعالَج (بلاغ المالك 2026-09-19، التقرير 6):** كل قسم كان يعيد
استخراج الحقيقة بنفسه — قسم الاقتصاد يقرأ التعرفة بـregex فوق نثر البعثة
بمفردات «تعرفة» فتفوته «التعريفة المطبَّقة» ويعلن «0% — غير متاحة» بينما
القسم ٧ يطبع 25%؛ عدد الشروط يُعرض بخمسة سطوح بسقوف مختلفة؛ خيط المنافس
يقول «سعر غير مرصود» والجدول يعرض أسعاراً؛ النمو محسوب في مكوّن ومعلَن
ناقصاً في قسم آخر. مسارُ استخراجٍ ثانٍ = تناقضٌ حتميّ عاجلاً أو آجلاً.

**القاعدة:** الاستخراج يقع **مرة واحدة** هنا (`build_ledger`)، وكلُّ سطح —
الأقسام الحتمية، الخلاصة، جدول النواقص، ونثرُ الكاتب — يقرأ النتيجة نفسها.

**نثر الكاتب — النهج المختلط (قرار المالك):**
- ستة معطيات **رموزٌ إلزامية** لا يكتب الكاتب لها قيمة ولا حالة من عنده:
  التعرفة، عدد الشروط المفتوحة، عدد بنود الاشتراطات، حالة أي معطى
  (`{{status:key}}`)، الشرط الحاجب، السنة الأحدث للسلسلة. التصيير يملؤها
  (`bind`) بجمل سليمة لغوياً حسب الحالة والعدد.
- بقية الأرقام يكتبها الكاتب بصيغته الطبيعية (تقريب، مقارنات) وتُفحص بعد
  الكتابة (`draft_issues`) مقابل السجلّ بتسامح التقريب؛ المخالفة تُعاد
  صياغتها جملةً وحدها داخل حلقة المراجع قبل التخزين.
- الرموز **داخلية حصراً**: لا تصل أي سطح عميل (كل مُصدِّر يقرأ نصاً مملوءاً
  من `build_view`، وحارس التصدير يرفض `{{` متبقّية).
- **لقطة** للرموز التي استخدمها الكاتب فعلاً تُخزَّن مع التقرير
  (`snapshot_for`)؛ عند العرض إن اختلفت عن السجلّ الحالي لا يُملأ بصمت:
  يُعلَّم القسم قديماً (`stale_keys`) ويُعاد التوليد في الخلفية تحت الإنفاذ.
- **الأرقام المشتقة:** كل رقم إمّا مفتاح هنا (يُفحص بالتسامح) أو مسموح
  صراحةً في `DERIVED_ALLOWED`.

**التقارير المخزونة قبل الفكس** (نص بلا رموز): `check` شبكة أمان — وضع
القياس افتراضاً (تحذيري، يُسجَّل)، والإنفاذ خلف `SILK_LEDGER_ENFORCE=1`
بإصلاح تلقائي من السجلّ أولاً (`repair`، إعادة صياغة الجملة كاملة) ثم حجب
ما لم يُصلَح.

stdlib فقط؛ الاستيرادات الداخلية كسولة (كل وحدة تُستورد بلا مفتاح ولا شبكة).
"""
from __future__ import annotations

import os
import re

ENFORCE_FLAG = "SILK_LEDGER_ENFORCE"
MAX_REVISIONS_FLAG = "SILK_LEDGER_MAX_REVISIONS"
TOKEN_RE = re.compile(r"\{\{\s*(status:)?([a-z_]+)(:sentence)?\s*\}\}")

OBSERVED, WEAK, MISSING = "observed", "weak", "missing"
#: درجتان للاستنتاج (الموجة د): تقديرٌ بنطاقٍ وافتراضٍ معلن، واستنتاجٌ يسمّي
#: ما يستند إليه. لا تدخلان `build_pillar_inputs` فلا تُحرّكان حكماً (قيدُ
#: المالك: التقديراتُ لا تُحتسب متحققاً منها) — تعيشان في السجلّ وسطوحه فقط.
ESTIMATE, INFERENCE = "estimate", "inference"
STATUSES = (OBSERVED, WEAK, MISSING, ESTIMATE, INFERENCE)
#: الدرجاتُ ذاتُ النطاق: رقمُها في النثر لا يُقارَن بقيمةٍ واحدة.
_RANGED = frozenset({ESTIMATE, INFERENCE})

from collections import namedtuple

#: صفُّ مفتاحٍ بأعلامه (الموجة د-١): قوائمُ التخطّي التي كانت تُعدَّد يدوياً في
#: `facts_block`/`draft_issues`/`check`/`repair`/`build_ledger` تُشتقّ من هذه
#: الأعلام — إضافةُ مفتاحٍ = سطرٌ واحد. الحقولُ الخمسةُ الأولى بترتيبها القديم
#: فيبقى الوصولُ بالفهرس (`row[1]`, `row[4]`) صالحاً.
KeyRow = namedtuple("KeyRow", (
    "key", "label_ar", "label_en", "unit", "words",
    "kind",              # fact | insight
    "mandatory",         # رمزٌ إلزاميٌّ للكاتب (لا يكتب قيمتَه ولا حالتَه)
    "self_describing",   # صيغتُه تصف نفسَها عند الغياب فلا تُبدَّل جملتُه
    "numeric_check",     # رقمُه في النثر يُقارَن بالسجلّ
    "engine_computed",   # يحسبه المحرّك حتمياً — لا درجةَ مصدرٍ له
    "writer_hidden",     # لا يُعرَض على الكاتب في [LEDGER]
    "gap_listed",        # يدخل قائمةَ الفجوات حين يغيب
    "hide_when_missing", # لا يُعرَض على الكاتب حين يغيب (مفاتيحُ التحليل التجاري)
), defaults=("fact", False, False, True, False, False, True, False))


def _fact(key, label_ar, label_en, unit, words=(), **flags):
    return KeyRow(key, label_ar, label_en, unit, tuple(words), **flags)


#: المفاتيح القانونية بترتيب العرض — (المفتاح، التسمية العربية، الإنجليزية،
#: الوحدة، مفردات التعرّف عليها في النص) + الأعلام.
KEYS: tuple = (
    _fact("market_imports_usd", "واردات السوق", "market imports", "USD",
          ("واردات السوق", "إجمالي الواردات", "الواردات المصرَّحة", "TAM",
           "market imports")),
    _fact("imports_latest_year", "أحدث سنة بيانات للواردات",
          "latest imports data year", "", (), mandatory=True,
          gap_listed=False),
    _fact("import_growth_pct", "نمو الواردات", "imports growth", "%",
          ("نمو الواردات", "نمو السوق", "imports growth", "market growth")),
    _fact("import_cagr_pct", "معدل النمو السنوي المركّب", "import CAGR", "%",
          ("معدل النمو السنوي المركّب", "نمو مركّب", "CAGR")),
    _fact("saudi_share_pct", "الحصة السعودية", "Saudi share", "%",
          ("الحصة السعودية", "حصة السعودية", "تستحوذ السعودية", "Saudi share")),
    _fact("hhi", "مؤشر تركّز المورّدين", "supplier concentration (HHI)", "",
          ("مؤشر التركّز", "تركّز المورّدين", "HHI")),
    _fact("top_supplier_share_pct", "حصة المورّد الأكبر", "top supplier share",
          "%", ("حصة المورّد الأكبر", "أكبر مورّد", "top supplier")),
    _fact("border_price_usd_kg", "متوسط سعر الاستيراد الحدودي",
          "border unit value", "USD/kg",
          ("سعر الاستيراد الحدودي", "سعر الوحدة عند الحدود", "سعر الحدود",
           "border unit value")),
    _fact("tariff_applied_pct", "الرسوم الجمركية المطبَّقة", "applied tariff",
          "%", ("الرسوم الجمركية", "التعرفة", "التعريفة", "الرسم الجمركي",
                "tariff", "customs duty"), mandatory=True),
    _fact("per_capita_income_usd", "دخل الفرد", "GDP per capita", "USD",
          ("دخل الفرد", "نصيب الفرد", "per capita")),
    _fact("population", "عدد السكان", "population", "",
          ("عدد السكان", "population")),
    _fact("open_conditions", "الشروط المفتوحة", "open conditions", "",
          ("الشروط المفتوحة", "شروط مفتوحة", "open conditions"),
          mandatory=True, self_describing=True, numeric_check=False,
          engine_computed=True),
    _fact("requirements_count", "بنود الاشتراطات", "entry requirements", "",
          ("بنود الاشتراطات", "قائمة الاشتراطات", "entry requirements"),
          mandatory=True, self_describing=True, numeric_check=False),
    _fact("competitor_prices", "أسعار المنافسين", "competitor prices", "",
          ("أسعار المنافسين", "competitor prices"), numeric_check=False,
          writer_hidden=True),
    # تقرير ٧ §5: «الشرط الحاجب» مصطلحٌ داخليّ — التسميةُ للعميل وصفٌ لما
    # يعنيه؛ والمصطلحُ القديم يبقى كلمةَ تعرّفٍ (نصوصٌ محفوظة قبل التغيير).
    _fact("blocking_condition", "المتطلب السابق للتعاقد أو الشحن", "prerequisite before contracting or shipping", "",
          ("المتطلب السابق للتعاقد أو الشحن", "الشرط الحاجب", "blocking condition"), mandatory=True,
          self_describing=True, numeric_check=False, engine_computed=True,
          gap_listed=False),
    # ── الموجة د-٢: مفاتيحُ التحليل التجاري (`silk_commercial_analysis`) —
    #    بلا كلماتِ تعرّفٍ (لا مسحَ للنثر)، ولا تدخل قائمةَ الفجوات، وتُخفى عن
    #    الكاتب حين تغيب (تُقال في «أسئلة المصدّر» في د-٤).
    _fact("saudi_raw_input_balance", "صافي تجارة السعودية في المدخلات الخام",
          "Saudi net trade in raw inputs", "USD", numeric_check=False,
          gap_listed=False, hide_when_missing=True),
    _fact("cost_advantage", "ميزة التكلفة", "cost advantage", "",
          kind="insight", numeric_check=False, gap_listed=False,
          hide_when_missing=True),
    _fact("supplier_nature", "طبيعة المورّدين الأكبر", "nature of top suppliers",
          "", kind="insight", numeric_check=False, gap_listed=False,
          hide_when_missing=True),
    _fact("direct_competitor_share_pct", "حصة المنافسين المباشرين",
          "direct competitors' share", "%", kind="insight",
          numeric_check=False, gap_listed=False, hide_when_missing=True),
    _fact("differentiation", "مصدر التمايز", "differentiation", "",
          kind="insight", numeric_check=False, gap_listed=False,
          hide_when_missing=True),
    _fact("price_evidence_quality", "توثيق أسعار المنافسين",
          "competitor price evidence", "", numeric_check=False,
          gap_listed=False, hide_when_missing=True),
    _fact("mandatory_certifications", "الشهادات الإلزامية بمصدر رسمي",
          "mandatory certifications (official source)", "",
          numeric_check=False, gap_listed=False, hide_when_missing=True),
    # الموجة د-٤ (البند ١١): تقديراتٌ بنطاقٍ وافتراضٍ معلنَين — تُحسَب بعد
    # اكتمال العرض من قسم الاقتصاد، ولا تدخل `build_pillar_inputs` فلا تحرّك
    # حكماً (قيدُ المالك: التقديراتُ لا تُحتسب «متحققاً منها»).
    _fact("border_to_shelf_multiple", "مضاعف الحدود إلى الرف",
          "border-to-shelf multiple", "×", kind="insight", numeric_check=False,
          gap_listed=False, hide_when_missing=True),
    _fact("max_exw_estimate", "أقصى سعر مصنع قابل للمنافسة",
          "maximum competitive ex-works price", "", kind="insight",
          numeric_check=False, gap_listed=False, hide_when_missing=True),
    _fact("trial_shipment_units", "حجم الشحنة التجريبية",
          "trial shipment size", "", kind="insight", numeric_check=False,
          gap_listed=False, hide_when_missing=True),
    # الموجة د-٣: موضعُ الحلال — شرطُ دخولٍ أم ميزةٌ بثلاثة شروطٍ مرصودة.
    _fact("halal_positioning", "موضع الحلال", "halal positioning", "",
          kind="insight", numeric_check=False, gap_listed=False,
          hide_when_missing=True),
)
_KEY_ROWS = {r.key: r for r in KEYS}

#: الرموز الإلزامية الستة (قرار المالك) — الكاتب لا يكتب لها قيمة ولا حالة.
#: الترتيبُ ثابتٌ (يظهر في نصّ القاعدة)؛ والعضويةُ تُشتقّ من علم `mandatory`.
MANDATORY_TOKEN_KEYS: tuple = ("tariff_applied_pct", "open_conditions",
                               "requirements_count", "blocking_condition",
                               "imports_latest_year")
assert set(MANDATORY_TOKEN_KEYS) == {r.key for r in KEYS if r.mandatory}
#: `{{status:key}}` السادس — حالة أي مفتاح.
#: مفاتيحُ يحسبها المحرّكُ حتمياً (لا مصدرَ خارجيّ فلا درجةَ مصدر)، ومفاتيحُ
#: صيغتُها تصف نفسَها عند الغياب — كلاهما من الأعلام.
_ENGINE_COMPUTED = frozenset(r.key for r in KEYS if r.engine_computed)
_SELF_DESCRIBING_KEYS = frozenset(r.key for r in KEYS if r.self_describing)

#: الأرقام المشتقة المسموح بها صراحةً في النثر بلا مفتاح: سياقاتٌ يُقاس
#: بها الرقم (إن وقعت كلمةٌ منها في جملة الرقم لا يُعَدّ رقماً عارياً).
DERIVED_ALLOWED: tuple = (
    "الشحنة التجريبية", "كلفة الدخول", "نقطة التعادل", "أقصى خسارة",
    "أقصى سعر مصنع", "التكلفة الواصلة", "حصة", "نصيب", "سنة", "عام",
    "trial shipment", "entry cost", "break-even", "maximum loss", "share",
)

# مفردات الغياب التي يُسمَح بها لأي سطح — ما ليس هنا تحظره البوابة أصلاً.
_ABSENCE_RE = re.compile(
    r"غير\s*متاح(?:ة)?|غير\s*محسوب(?:ة)?|لم\s*نتمكّن|لم\s*نتمكن|لم\s*يُرصد"
    r"|لم\s*يرصد|غير\s*مرصود(?:ة)?|not\s+available|unavailable|not\s+computed",
    re.IGNORECASE)
_NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:[,\d]{0,12})(?:\.\d+)?)\s*(%|٪|مليون|مليار|ألف|million|billion)?")
_YEAR_RE = re.compile(r"\b(20\d\d|19\d\d)\b")
_WINDOW = 70
#: نافذةُ **مطابقة القيمة** أضيق من نافذة الحالة: رقمٌ بعيدٌ عن التسمية
#: غالباً رقمُ مفهومٍ آخر في الجملة نفسها (قِياسٌ على المدوّنات: «حصة
#: السعودية المنخفضة مقابل نمو السوق 9.3%» — الرقمُ نموٌّ لا حصة).
_VALUE_WINDOW = 45
#: فاصلٌ يمنع المطابقة: تعريفٌ أو عتبةٌ أو مفهومٌ آخر بين التسمية والرقم.
#: العيبُ المرصود (الدرس ٢٣٩ نفسُه): «HHI مؤشر يقيس تركّز السوق — فوق 2500
#: يعني سوقاً مركّزاً» ليس قراءةَ تركّزٍ لهذا السوق بل تعريفَ المقياس.
_DEFINITION_RE = re.compile(
    r"يعني|يقيس|مقياس|عتبة|تعريف|فوق|أعلى\s*من|دون|أقل\s*من|بين|مثال"
    r"|means|measures|threshold|above|below|scale")
_TOLERANCE = 0.02
_SENT_SPLIT_RE = re.compile(r"(?<=[.؛!؟\n])")
_SCALE = {"مليون": 1e6, "million": 1e6, "مليار": 1e9, "billion": 1e9,
          "ألف": 1e3}


def enforce() -> bool:
    """هل وضعُ الإنفاذ مفعّل؟ — افتراضاً لا (قياس فقط، قرار المالك)."""
    return os.environ.get(ENFORCE_FLAG, "").strip().lower() in ("1", "true",
                                                                "yes", "on")


def max_revisions() -> int:
    """سقف دورات التنقيح بسبب السجلّ — افتراضه ١، أقصاه ٢ (الشرط ٣)."""
    try:
        n = int(os.environ.get(MAX_REVISIONS_FLAG, "1"))
    except ValueError:
        n = 1
    return max(0, min(2, n))


# ── مساعدات القراءة · readers ────────────────────────────────────────────────

def _g(obj: object, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _num(v: object) -> "float | None":
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _entry(key: str, value=None, *, source: str = "", confidence=None,
           note: str = "", year=None, unit: str | None = None,
           mirrored: bool = False, origin: str = "", items=None) -> dict:
    """بندُ سجلّ واحد بحالته المحسوبة — الحالة **لا تُصرَّح** من المصدر."""
    row = _KEY_ROWS[key]
    if value is None and not items:
        status = MISSING
    elif key in _ENGINE_COMPUTED:
        status = OBSERVED
    else:
        from silk_fact_records import classify_tier
        from silk_narrative import EVIDENCE_SECONDARY_MIN
        tier = classify_tier(source, note)
        conf = _num(confidence)
        weak = (tier in ("C", "X") or mirrored
                or (conf is not None and conf < EVIDENCE_SECONDARY_MIN))
        status = WEAK if weak else OBSERVED
    return {"key": key, "label_ar": row[1], "label_en": row[2],
            "unit": unit if unit is not None else row[3],
            "status": status, "value": value, "items": items,
            "source": str(source or ""), "confidence": _num(confidence),
            "note": str(note or ""), "year": year, "mirrored": bool(mirrored),
            "origin": origin}


def graded_entry(key: str, value, status: str, *, source: str = "",
                 note: str = "", year=None, origin: str = "",
                 items=None) -> dict:
    """بندُ حقيقةٍ درجتُها **محسوبةٌ بقاعدةٍ معلنة** لا من درجة المصدر (مثل
    توثيق الأسعار: أقلّ من ٣ سطور مكتملة = ضعيف). لا يقبل إلا مرصود/ضعيف."""
    if status not in (OBSERVED, WEAK):
        raise ValueError("graded_entry accepts observed/weak only")
    e = _entry(key, value, source=source, note=note, year=year, origin=origin,
               items=items, confidence=0.9)
    e["status"] = status
    return e


def insight_entry(key: str, value, *, grade: str, assumption: str = "",
                  range=None, basis=(), flip_if: str = "", source: str = "",
                  note: str = "", unit: str | None = None, year=None,
                  how_to_close: str = "", items=None) -> dict:
    """بندُ استنتاجٍ (الموجة د): تقديرٌ أو استنتاجٌ **يُصرِّح** بدرجته — عكسُ
    `_entry` التي تحسب الدرجةَ من المصدر. قيدُ المالك بنيويّ: لا تقديرَ بلا
    افتراضٍ معلنٍ ونطاق، ولا استنتاجَ بلا ما يستند إليه (يرفع ValueError).
    """
    if grade not in _RANGED:
        raise ValueError(f"insight grade must be estimate/inference, got {grade!r}")
    rng = tuple(range) if isinstance(range, (list, tuple)) else None
    if grade == ESTIMATE:
        lo = _num(rng[0]) if rng and len(rng) == 2 else None
        hi = _num(rng[1]) if rng and len(rng) == 2 else None
        if not str(assumption).strip() or lo is None or hi is None or lo > hi:
            raise ValueError("an estimate needs a declared assumption and a "
                             "numeric (low, high) range with low <= high — "
                             "لا تقدير بلا افتراض معلن ونطاق")
        rng = (lo, hi)
    basis = tuple(basis or ())
    unknown = [b for b in basis if b not in _KEY_ROWS]
    if unknown:
        raise ValueError(f"basis names unknown ledger keys: {unknown}")
    if grade == INFERENCE and not basis:
        raise ValueError("an inference must name the ledger keys it rests on")
    row = _KEY_ROWS[key]
    return {"key": key, "label_ar": row.label_ar, "label_en": row.label_en,
            "unit": unit if unit is not None else row.unit,
            "status": grade, "value": value, "items": items,
            "source": str(source or "حساب من السجلّ"), "confidence": None,
            "note": str(note or ""), "year": year, "mirrored": False,
            "origin": "insight", "assumption": str(assumption or ""),
            # **قوائمُ لا صِفافٌ** عمداً: السجلُّ يُخزَّن ويُعاد عبر JSON
            # (`GET /analyses/{id}`)، والصفُّ يعود قائمةً بعد الجولة فيصير
            # الكائنُ المُعاد ≠ المخزَّن حرفياً (قِيس في
            # `test_without_economics_flag_full_blob_still_returned_unchanged`).
            # التطبيعُ في المُنشئ الواحد فلا يتسرّب صفٌّ من أيّ مُعبِّئ.
            "range": list(rng) if rng else None, "basis": list(basis),
            "flip_if": str(flip_if or ""),
            "how_to_close": str(how_to_close or "")}


def _dp_entry(key: str, dp: object, origin: str, *, value=None) -> dict:
    d = dp if isinstance(dp, dict) else {
        "value": _g(dp, "value"), "source": _g(dp, "source", ""),
        "confidence": _g(dp, "confidence"), "note": _g(dp, "note", ""),
        "status": _g(dp, "status", ""), "data_year": _g(dp, "data_year")}
    src = str(d.get("source") or "")
    st = str(d.get("status") or "")
    mirrored = ("مرآة" in src or "mirror" in src.lower() or st == "mirrored")
    return _entry(key, d.get("value") if value is None else value,
                  source=src, confidence=d.get("confidence"),
                  note=str(d.get("note") or ""), year=d.get("data_year"),
                  mirrored=mirrored, origin=origin)


def _bundle_finding(row: dict, agent: str, metric: str) -> "dict | None":
    """اكتشافٌ من حزمة البحث الحتمية (`row["research"]["agents"]`) بشكل
    `{metric, value, sources[], note}` → dict بشكل DataPoint."""
    research = row.get("research") or {}
    findings = ((research.get("agents") or {}).get(agent) or {}).get("findings") or []
    for f in findings:
        if _g(f, "metric") != metric:
            continue
        srcs = _g(f, "sources") or []
        s0 = srcs[0] if srcs and isinstance(srcs[0], dict) else {}
        return {"value": _g(f, "value"), "source": str(s0.get("source") or ""),
                "confidence": s0.get("confidence"), "note": _g(f, "note", ""),
                "status": "", "data_year": s0.get("data_year")}
    return None


# ── البناء · build ───────────────────────────────────────────────────────────

def build_ledger(result: dict, lang: str = "ar") -> dict:
    """ابنِ السجلّ من النتيجة الخام (المسارين معاً) — نقيّ، بلا شبكة.

    /research: بعثات `deep_research` عبر مستخلِصات `silk_deep_pillars`
    (المصدر الوحيد للأعمدة أيضاً) + مفردات التعرفة الموسَّعة دائماً.
    /analyze: صفّ السوق الأعلى — حزمة البحث الحتمية + DataPoints الطبقات.
    أي عطل في مفتاح = بند `missing` بملاحظة، لا كسر عرض.
    """
    result = result or {}
    markets = result.get("markets") or []
    row = markets[0] if markets and isinstance(markets[0], dict) else {}
    dr = result.get("deep_research") or {}
    entries: dict = {}

    def put(e: dict) -> None:
        entries[e["key"]] = e

    try:
        if dr:
            _fill_from_research(dr, put, result)
        else:
            _fill_from_analyze(row, put)
    except Exception:  # noqa: BLE001 — عطل استخراج = فجوات معلنة لا كسر
        pass
    _fill_decision(row, result, put)
    _fill_competitor_prices(row, put)
    for key, *_ in KEYS:
        if key not in entries:
            put(_entry(key, None, note="لم تُحاوَل قراءة هذا المعطى"))
    ordered = [entries[k[0]] for k in KEYS]
    gaps = [{"key": e["key"], "label_ar": e["label_ar"],
             "label_en": e["label_en"], "status": e["status"],
             "note": e["note"], "source": e["source"]}
            for e in ordered if e["status"] in (MISSING, WEAK)
            and _KEY_ROWS[e["key"]].gap_listed]
    return {"schema": "silk.ledger/v1", "lang": lang,
            # الموجة د-٣: رمزُ الصنف يرافق السجلَّ كي يعرف حارسُ المسوّدة فئةَ
            # المنتج (لا لفظَ دينيّ في فئةٍ لا صلةَ للدين بها) — بيانٌ مرافقٌ
            # لا مفتاحُ حقيقةٍ يُعرَض.
            "hs_code": str(result.get("hs_code") or "") or None,
            "entries": {e["key"]: e for e in ordered},
            "order": [k[0] for k in KEYS], "gaps": gaps,
            "repairs": [], "findings": [], "stale": []}


def _fill_from_research(dr: dict, put, result: dict | None = None) -> None:
    """المسار العميق — **قارئٌ واحد**: قيمُ المفاتيح من `build_pillar_inputs`
    نفسِه الذي يقرؤه محرّكُ القرار، لا من مستخلِصٍ ثانٍ.

    الدرس ٢٦٢: مستخلِصٌ خاصٌّ بالسجلّ كان يقول «لا ملخّص مورّدين» بينما
    المحرّك يحمل HHI — أي أنّه يخلق التناقضَ الذي وُضع ليمنعه. الإسنادُ
    (المصدر/السنة/الثقة) يُقرأ من الاكتشاف نفسِه بعد معرفة القيمة.
    """
    import silk_deep_pillars as P
    missions = dr.get("missions") or {}
    try:
        pi = P.build_pillar_inputs(dr)
    except Exception:  # noqa: BLE001 — تعذّر القراءة = فجواتٌ معلنة
        pi = {}
    flat: dict = {}
    for group in (pi or {}).values():
        if isinstance(group, dict):
            flat.update(group)

    # (المفتاح في السجلّ، مفتاح المحرّك، البعثة المسؤولة)
    _MAP = (("market_imports_usd", "tam_usd", "trade_flow"),
            ("import_cagr_pct", "import_cagr_pct", "trade_flow"),
            ("saudi_share_pct", "saudi_share_pct", "trade_flow"),
            ("hhi", "hhi", "competitors"),
            ("top_supplier_share_pct", "top_supplier_share_pct", "competitors"),
            ("border_price_usd_kg", "border_unit_value_usd_kg", "trade_flow"),
            ("tariff_applied_pct", "tariff_applied_pct", "tariffs_agreements"),
            ("per_capita_income_usd", "gdp_per_capita_usd",
             "demographics_economy"),
            ("requirements_count", "entry_requirements_count",
             "customs_requirements"))
    for key, metric, mission in _MAP:
        value = flat.get(metric)
        if value is None:
            put(_entry(key, None, origin=mission,
                       note="لم يرصده المحرّك في نتائج هذه البعثة"))
            continue
        put(_entry(key, value, origin=mission,
                   **_attribution(missions, mission, metric, value,
                                  winner=(_hhi_winner(missions)
                                          if key == "hhi" else None))))
    _fill_series(missions, put)
    put(_entry("population", None, note="لا يُقرأ عدد السكان من البعثات"))
    # الموجة د-٢: استنتاجاتُ التحليل التجاري من الاكتشافات المخزَّنة (نقيّة).
    try:
        import silk_commercial_analysis as _CA
        ctx = result or {}
        _CA.fill_insights(dr, put, hs_code=ctx.get("hs_code"),
                          market_iso3=str((ctx.get("market") or {}).get("iso3") or ""),
                          product_card=ctx.get("product_card"))
    except Exception as e:  # noqa: BLE001 — استنتاجٌ متعذّر = فجوةٌ معلنة
        put(_entry("cost_advantage", None, note=f"تعذّر التحليل التجاري: {e}"))


def _hhi_winner(missions: dict):
    """الاكتشافُ الفائزُ بقيمة HHI عند المحرّك نفسِه — أو None.

    الدرس ٢٧٠ (تقرير ٧): الإسنادُ بالمطابقة بالقيمة يفشل على الملخّص المهيكل
    (قيمتُه قاموس) فتُلتقَط سنةُ اكتشافٍ آخر ومصدرُه. الفائزُ هو ما يعيده
    `_structured_competition` — القارئُ نفسُه الذي أنتج القيمة.
    """
    import silk_deep_pillars as P
    try:
        return P._structured_competition(
            P._metric_findings(missions or {}, "competitors"))[3]
    except Exception:  # noqa: BLE001 — تعذُّر = مطابقةٌ بالقيمة كما كانت
        return None


def _winner_attribution(f) -> dict:
    """إسنادُ اكتشافٍ معروفٍ سلفاً: السنةُ من حقل القيمة المهيكل ثم البنيوية."""
    import silk_deep_pillars as P
    raw = _g(f, "value")
    year = raw.get("year") if isinstance(raw, dict) else None
    try:
        year = int(year) if year else P._fact_year(f)
    except (TypeError, ValueError):
        year = P._fact_year(f)
    src = str(_g(f, "source", "") or "")
    st = str(_g(f, "status", "") or "")
    return {"source": src, "confidence": _g(f, "confidence"),
            "note": str(_g(f, "note", "") or ""), "year": year,
            "mirrored": ("مرآة" in src or "mirror" in src.lower()
                         or st == "mirrored")}


def _attribution(missions: dict, mission: str, metric: str,
                 value: float, winner=None) -> dict:
    """المصدر/السنة/الثقة للقيمة التي قرأها المحرّك — من الاكتشاف الحامل لها.

    المطابقةُ بالقيمة نفسِها (لا بإعادة استخراج): تعذُّرها يترك الإسنادَ
    فارغاً فتُحسَب الحالةُ على أقسى تقدير، ولا يُختلَق مصدر. و`winner`
    (الاكتشافُ الذي أنتج القيمةَ عند المحرّك) يعلو المطابقةَ حين يُعرَف.
    """
    if winner is not None:
        return _winner_attribution(winner)
    import silk_deep_pillars as P
    try:
        findings = P._metric_findings(missions or {}, mission)
    except Exception:  # noqa: BLE001
        findings = []
    for f in findings:
        raw = _g(f, "value")
        num = _num(raw if not isinstance(raw, dict) else None)
        blob = f"{_g(f, 'note', '')} {raw if isinstance(raw, str) else ''}"
        hit = (num is not None and abs(num - float(value)) < 1e-6) or \
            (f"{value:g}" in blob)
        if not hit:
            continue
        src = str(_g(f, "source", "") or "")
        st = str(_g(f, "status", "") or "")
        return {"source": src, "confidence": _g(f, "confidence"),
                "note": str(_g(f, "note", "") or ""),
                "year": _g(f, "data_year"),
                "mirrored": ("مرآة" in src or "mirror" in src.lower()
                             or st == "mirrored")}
    return {"source": "", "confidence": None,
            "note": "قرأه المحرّك من نتائج البعثة", "year": None}


def _fill_series(missions: dict, put) -> None:
    """السلسلة الزمنية وأحدثُ سنةٍ مرصودة + نموُّ الواردات منها."""
    import silk_deep_pillars as P
    try:
        series = P.import_series(missions)
    except Exception:  # noqa: BLE001
        series = {}
    pts = series.get("series") or []
    if not pts:
        put(_entry("imports_latest_year", None, note="لا سلسلة واردات مرصودة"))
        put(_entry("import_growth_pct", None, note="لا سلسلة واردات مرصودة"))
        return
    latest = max(int(p["year"]) for p in pts)
    put(_entry("imports_latest_year", latest, source="UN Comtrade",
               confidence=0.9, note="أحدث سنة مرصودة في سلسلة الواردات",
               origin="trade_flow", items=[dict(p) for p in pts]))
    g = _num(series.get("growth_pct"))
    put(_entry("import_growth_pct", g, source="UN Comtrade", confidence=0.9,
               origin="trade_flow",
               note=("نمو الواردات بين أول وآخر سنة مرصودة" if g is not None
                     else "يتطلب سنتين مرصودتين")))


def _fill_from_analyze(row: dict, put) -> None:
    from silk_render import _dp
    comps = row.get("components") or {}
    if comps.get("market_size"):
        put(_dp_entry("market_imports_usd", _dp(comps["market_size"]),
                      "market_size"))
    for metric, key in (("import_growth_pct", "import_growth_pct"),
                        ("import_cagr_pct", "import_cagr_pct")):
        f = _bundle_finding(row, "market_size", metric)
        put(_dp_entry(key, f, "market_size") if f else
            _entry(key, None, note="لا سلسلة سنوات كافية"))
    tr = row.get("trend") or {}
    pts = [p for p in (tr.get("series") or []) if p.get("value") is not None]
    if pts:
        put(_entry("imports_latest_year", max(int(p["year"]) for p in pts),
                   source=tr.get("source") or "UN Comtrade", confidence=0.9,
                   note="أحدث سنة مرصودة في خط الاتجاه", origin="trend",
                   items=[dict(p) for p in pts]))
    elif row.get("year_used"):
        put(_entry("imports_latest_year", int(row["year_used"]),
                   source="UN Comtrade", confidence=0.9,
                   note="سنة بيانات الواردات المعتمدة", origin="market_size"))
    for agent, metric, key in (("competitor", "hhi", "hhi"),
                               ("competitor", "top_supplier_share_pct",
                                "top_supplier_share_pct"),
                               ("competitor", "saudi_share_pct", "saudi_share_pct"),
                               ("pricing", "border_unit_value_usd_kg",
                                "border_price_usd_kg"),
                               ("regulatory", "entry_requirements_count",
                                "requirements_count")):
        f = _bundle_finding(row, agent, metric)
        put(_dp_entry(key, f, agent) if f else
            _entry(key, None, note="لا اكتشاف يحمل هذا المعطى"))
    tdp = row.get("tariff")
    f = _bundle_finding(row, "regulatory", "tariff_applied_pct")
    if tdp is not None and _g(tdp, "value") is not None:
        put(_dp_entry("tariff_applied_pct", tdp, "tariffs"))
    elif f:
        put(_dp_entry("tariff_applied_pct", f, "regulatory"))
    else:
        put(_entry("tariff_applied_pct", None, origin="tariffs",
                   note=str(_g(tdp, "note") or "التعرفة غير مرصودة")))
    for key, field, gap in (("per_capita_income_usd", "income_ppp",
                             "دخل الفرد غير متاح"),
                            ("population", "population", "عدد السكان غير متاح")):
        dp = row.get(field)
        put(_dp_entry(key, dp, "economic")
            if dp is not None and _g(dp, "value") is not None
            else _entry(key, None, note=gap))


def _fill_decision(row: dict, result: dict, put) -> None:
    """الشروط المفتوحة **كاملة بلا سقف** + الشرط الحاجب بتعريف واحد."""
    ed = row.get("decision") if isinstance(row.get("decision"), dict) else {}
    conds = [str(c) for c in (ed.get("conditions") or []) if str(c).strip()]
    put(_entry("open_conditions", len(conds), source="محرك القرار",
               confidence=1.0, items=conds or None,
               note="قائمة محرك القرار الواحدة", origin="decision"))
    reg = result.get("regulatory") if isinstance(result.get("regulatory"), dict) \
        else (row.get("regulatory") if isinstance(row.get("regulatory"), dict) else {})
    pillars = ed.get("pillars") if isinstance(ed.get("pillars"), dict) else {}
    if (reg or {}).get("blocked") or (pillars.get("regulatory") or {}).get(
            "eligibility_gate"):
        blocking = next((c for c in conds if "أهلية" in c), None) or \
            "بوابة أهلية أمامية مفتوحة — لا تقدّم قبل عبورها"
    elif ed.get("critical_risk"):
        blocking = "خطر حرج مرصود (الاستقرار السياسي دون العتبة)"
    else:
        blocking = next((c for c in conds if "غائب" in c), None)
    put(_entry("blocking_condition", blocking, source="محرك القرار",
               confidence=1.0, origin="decision",
               note="شرط واحد بتعريف واحد لكل الأقسام" if blocking
               else "لا متطلب سابق"))


def _fill_competitor_prices(row: dict, put) -> None:
    """المنافسون المسمَّون وأسعارهم — من خيوط الترابط نفسها (مصدر واحد للجدول
    والخيط): {named, matched, listings}."""
    cp = row.get("competitive_position") if isinstance(
        row.get("competitive_position"), dict) else {}
    threads = cp.get("competitor_threads") or []
    listings = [v for v in _real_values(row.get("localprice"))
                if isinstance(v, dict) and v.get("price") is not None]
    named = [{"name": t.get("name"),
              "price": (t.get("observed_price") or {}).get("value")}
             for t in threads if isinstance(t, dict)]
    if not named and not listings:
        put(_entry("competitor_prices", None,
                   note="لا منافس مسمّى ولا سعر مرصود", origin="correlation"))
        return
    matched = sum(1 for n in named if n["price"] is not None)
    put(_entry("competitor_prices",
               {"named": len(named), "matched": matched, "listings": len(listings)},
               source="طبقة الأسعار المرصودة", confidence=0.6,
               items=named, origin="correlation",
               note=f"{len(listings)} سعر مرصود في الجدول، {matched} منها يطابق "
                    f"منافساً مسمّى من {len(named)}"))


def _real_values(obj) -> list:
    return [v for v in (_g(f, "value") for f in (obj or [])) if v is not None]


# ── العرض · rendering (الشرط ٢: صيغ سليمة لغوياً حسب الحالة والعدد) ──────────

def _value_text(entry: dict, lang: str) -> str:
    from silk_narrative import fmt_amount, fmt_number, fmt_pct
    key, v, unit = entry["key"], entry.get("value"), entry.get("unit") or ""
    if unit == "%":
        return fmt_pct(v)
    if unit == "USD":
        return f"{fmt_number(v)} USD" if lang == "en" else fmt_amount(v, "USD")
    if unit == "USD/kg":
        return (f"{fmt_number(v)} USD/kg" if lang == "en"
                else f"{fmt_number(v)} دولار/كجم")
    if key == "imports_latest_year":
        return str(int(v))
    return fmt_number(v)


def render_value(entry: dict, lang: str = "ar") -> str:
    """القيمة بمصدرها — للرمز داخل جملة رقمية (`{{key}}`)."""
    st, key = entry["status"], entry["key"]
    if key == "blocking_condition" and not entry.get("value"):
        # قرارٌ محسوبٌ («لا شرطَ يحجب») لا فجوةٌ غيرُ مقيسة.
        return "no prerequisite" if lang == "en" else "لا متطلب سابق"
    if st == MISSING:
        return "not available" if lang == "en" else "غير متاح"
    if st == ESTIMATE:
        # النطاقُ والافتراضُ في **كلّ** سياق — حتى خليّةِ جدولٍ يملؤها `bind`
        # مباشرةً — وإلا خرج التقديرُ رقماً عارياً (قيدُ المالك).
        return _estimate_text(entry, lang)
    if st == INFERENCE:
        body = (_value_text(entry, lang) if _num(entry.get("value")) is not None
                else str(entry.get("value") or ""))
        basis = _basis_labels(entry, lang)
        return (f"{body} (inferred from {basis})" if lang == "en"
                else f"{body} (يشير إليه {basis})")
    v = entry.get("value")
    if key == "open_conditions":
        return count_text(int(v or 0), lang, "شرط", "شرطان", "شروط", "شرطاً",
                          "condition")
    if key == "requirements_count":
        return count_text(int(v or 0), lang, "بند", "بندان", "بنود", "بنداً",
                          "requirement")
    if key == "blocking_condition":
        return str(v)
    if key == "competitor_prices":
        d = v or {}
        return (f"{d.get('listings', 0)} observed prices, {d.get('matched', 0)} "
                f"matched to a named competitor out of {d.get('named', 0)}"
                if lang == "en" else
                f"{d.get('listings', 0)} سعر مرصود، {d.get('matched', 0)} منها "
                f"يطابق منافساً مسمّى من {d.get('named', 0)}")
    body = _value_text(entry, lang)
    tail = " ".join(x for x in (entry.get("source") or "",
                                str(entry.get("year") or "")) if x)
    if st == WEAK:
        # لغةُ قارئ لا اسمُ حالة — الذيلُ يصل نصَّ العميل عبر الرمز المملوء.
        body += (" — from unofficial sources only" if lang == "en"
                 else " — من مصادر غير رسمية فقط")
    return f"{body} ({tail})" if tail else body


def _estimate_text(entry: dict, lang: str) -> str:
    """«بين X وY [وحدة]، إذا افترضنا …» — النطاقُ والوحدةُ والافتراضُ معاً.

    الوحدةُ تُلحَق هنا لا في `_value_text`: ذاك يخدم كلَّ المفاتيح القائمة
    وخطوطَ أساسها المؤرشَفة، وهو يعرف `%`/`USD`/`USD/kg` وحدَها — فكانت
    التقديراتُ الجديدة تخرج نطاقاً **عارياً بلا وحدة** («بين 0.02 و0.03»
    لسعرٍ بالدولار/كجم، «بين 27,745 و30,630» للترات؛ قِيس على المدوّنات
    §58). الإلحاقُ مقصورٌ على التقدير فلا يتغيّر مُصيَّرٌ قائم.
    """
    from silk_narrative import fmt_number
    lo, hi = entry.get("range") or (None, None)
    hi_txt = _value_text({**entry, "value": hi}, lang)
    unit = str(entry.get("unit") or "").strip()
    if unit and unit not in hi_txt and unit not in ("%", "USD", "USD/kg"):
        hi_txt = f"{hi_txt} {unit}"
    a = entry.get("assumption") or ""
    return (f"between {fmt_number(lo)} and {hi_txt}, assuming {a}" if lang == "en"
            else f"بين {fmt_number(lo)} و{hi_txt}، إذا افترضنا {a}")


def _basis_labels(entry: dict, lang: str) -> str:
    labels = []
    for k in entry.get("basis") or ():
        row = _KEY_ROWS.get(k)
        labels.append((row.label_en if lang == "en" else row.label_ar)
                      if row else str(k))
    return (" and ".join(labels) if lang == "en" else " و".join(labels)) or (
        "observed figures" if lang == "en" else "أرقام مرصودة")


def render_sentence(entry: dict, lang: str = "ar") -> str:
    """جملة كاملة سليمة — للرمز حين يكون هو الجملة (`{{key:sentence}}`)
    ولاستبدال سطرٍ كُتب لرقمٍ غاب معطاه."""
    key, st = entry["key"], entry["status"]
    label = entry["label_en"] if lang == "en" else entry["label_ar"]
    en = lang == "en"
    if st == ESTIMATE:
        return (f"We estimate {label} {render_value(entry, lang)}." if en
                else f"نقدّر {label} {render_value(entry, lang)}.")
    if st == INFERENCE:
        body = (_value_text(entry, lang) if _num(entry.get("value")) is not None
                else str(entry.get("value") or ""))
        basis = _basis_labels(entry, lang)
        return (f"{basis} point to {label}: {body}." if en
                else f"يشير {basis} إلى أن {label}: {body}.")
    if key == "open_conditions":
        n = int(entry.get("value") or 0)
        if n == 0:
            return "There are no open conditions." if en else "لا شروط مفتوحة."
        return (f"There are {render_value(entry, lang)} open." if en
                else f"الشروط المفتوحة {render_value(entry, lang)}.")
    if key == "requirements_count":
        n = int(entry.get("value") or 0) if st != MISSING else 0
        if st == MISSING or n == 0:
            return ("No entry requirement items were observed." if en
                    else "لم تُرصد بنود اشتراطات لهذا السوق.")
        return (f"The entry checklist holds {render_value(entry, lang)}." if en
                else f"قائمة الاشتراطات تضم {render_value(entry, lang)}.")
    if key == "blocking_condition":
        v = entry.get("value")
        if not v:
            return "No single prerequisite holds the decision." if en else \
                "لا متطلب سابق يعلّق القرار."
        return (f"Prerequisite before contracting or shipping: {v}." if en
                else f"المتطلب السابق للتعاقد أو الشحن: {v}.")
    if st == MISSING:
        return f"{label} is not available." if en else f"{label} غير متاح."
    return f"{label}: {render_value(entry, lang)}."


def render_status(entry: dict, lang: str = "ar") -> str:
    """حالة معطى — `{{status:key}}` بلغة قارئ: متاح من مصدر موثّق / متاح من
    مصادر غير رسمية فقط / غير متاح / مُقدَّر بافتراض معلن / مستنتَج."""
    en = lang == "en"
    # لغةُ قارئ لا أسماءُ حالات (بلاغ المالك، الموجة د): «مرصود» و«ناقص»
    # و«تقدير» تسمياتٌ داخلية لا تصل العميل ولو عبر `{{status:key}}`.
    return {OBSERVED: ("available from a documented source" if en
                       else "متاح من مصدر موثّق"),
            WEAK: ("available from unofficial sources only" if en
                   else "متاح من مصادر غير رسمية فقط"),
            MISSING: "not available" if en else "غير متاح",
            ESTIMATE: ("estimated under a declared assumption" if en
                       else "مُقدَّر بافتراض معلن"),
            INFERENCE: ("inferred from observed figures" if en
                        else "مستنتَج من أرقام مرصودة")}[entry["status"]]


def count_text(n: int, lang: str, one: str, two: str, plural: str,
               acc_sing: str, en_noun: str) -> str:
    """عددٌ ومعدود بمطابقة العربية — يفوّض إلى `silk_narrative.count_sentence`."""
    if lang == "en":
        return f"{n} {en_noun}{'' if n == 1 else 's'}"
    from silk_narrative import count_sentence
    return count_sentence(n, one, two, plural, acc_sing)


def facts_block(ledger: dict, lang: str = "ar") -> str:
    """كتلة الرموز التي يستلمها الكاتب — الستة الإلزامية برموزها، وبقية
    المعطيات بقيمتها كي يكتبها بصيغته الطبيعية (تُفحص بعدها بالتسامح)."""
    lines = []
    for key in ledger.get("order") or []:
        e = ledger["entries"][key]
        label = e["label_en"] if lang == "en" else e["label_ar"]
        st = render_status(e, lang)
        if key in MANDATORY_TOKEN_KEYS:
            lines.append(f"- {{{{{key}}}}} = {label} ({st}) — اكتب الرمز لا القيمة")
        elif _KEY_ROWS[key].writer_hidden or (
                _KEY_ROWS[key].hide_when_missing and e["status"] == MISSING):
            continue
        else:
            val = render_value(e, lang) if e["status"] != MISSING else st
            lines.append(f"- {label}: {val} — {{{{status:{key}}}}} لحالته")
    return "\n".join(lines)


def insights_block(ledger: dict, lang: str = "ar") -> str:
    """كتلةُ `[INSIGHTS]` — استنتاجاتُ الطبقة التجارية وتقديراتُها بالرمز.

    الموجة د-٤ (البند ١٢): الكاتبُ يكتب **الرمزَ** لا القيمة (نفسُ عقد الرموز
    الإلزامية)، فتُملأ عند العرض بصيغتها الطبيعية بنطاقها وافتراضها — ولا
    يعيد النموذجُ صياغةَ تقديرٍ فيُسقِط نطاقَه أو يقلبه حقيقةً مرصودة.
    سطرٌ لكلّ مفتاحِ استنتاجٍ **محسوبٍ فعلاً**؛ الغائبُ لا يُذكر أصلاً.

    **حدٌّ بنيويٌّ معلَن (§58).** السجلُّ الذي يصل الكاتبَ يُبنى **قبلَه**
    (`silk_research_pipeline.py:664`) من البعثات والقرار والاشتراطات — بلا
    قسم الاقتصاد، لأنّ الاقتصادَ يُبنى في `build_view` بعد الكاتب. فمفاتيحُ
    `fill_estimates` الثلاثة (مضاعفُ الحدود→الرف، أقصى سعرِ مصنع، حجمُ
    الشحنة التجريبية) **لا تصل هذه الكتلةَ أبداً**، وتصل القارئَ من قسم
    «أسئلتك الحاسمة» المحسوبِ بالكود — وهو التصميمُ المقصود (البند ١٠:
    «الكاتبُ لا يكتبه»). ما يصل الكاتبَ هنا استنتاجاتُ د-٢/د-٣ (ميزةُ
    التكلفة، طبيعةُ المورّدين، حصةُ المنافسين، التمايز، موضعُ الحلال).
    """
    lines = []
    for key in ledger.get("order") or []:
        row = _KEY_ROWS.get(key)
        e = (ledger.get("entries") or {}).get(key)
        if not row or not e or row.kind != "insight":
            continue
        if e.get("status") in (MISSING, None) or e.get("value") is None:
            continue
        label = e["label_en"] if lang == "en" else e["label_ar"]
        en = lang == "en"
        tail = ""
        if e.get("status") == ESTIMATE:
            tail = (" — an estimate with a declared range and assumption"
                    if en else " — تقديرٌ بنطاقٍ وافتراضٍ معلنَين")
        elif e.get("status") == INFERENCE:
            tail = (" — inferred from observed figures" if en
                    else " — استنتاجٌ من أرقامٍ مرصودة")
        # الذيلُ والأمرُ بالعربية في موجّهٍ إنجليزيّ يخالطان
        # `INSIGHT_WRITING_RULE_EN` — لغةُ الكتلة لغةُ الموجّه (§58).
        order = ("write the token, not the value" if en
                 else "اكتب الرمز لا القيمة")
        lines.append(f"- {{{{{key}}}}} = {label}{tail} — {order}")
    return "\n".join(lines)


#: قاعدةُ الكتابة التحليلية (البند ١٢): الرقمُ وحدَه ليس تحليلاً.
INSIGHT_WRITING_RULE = (
    "**الكتابة التحليلية (إلزامية):** رتّب كلّ فقرةٍ **الخلاصة ← ما يعنيه "
    "الرقم للمصدّر ← الدليل بمصدره** — لا سرداً للأرقام ثمّ صمتاً عن معناها. "
    "وكلُّ رقمٍ مهمٍّ يتبعه أثرُه العملي في جملةٍ واحدة (ماذا يعني لقراره: "
    "يدخل؟ بأيّ سعر؟ ما الذي يجب أن يتحقّق أوّلاً؟). "
    "واستنتاجاتُ [INSIGHTS] تُكتب برموزها حيث تخدم السرد — النظامُ يملؤها "
    "بنطاقها وافتراضها؛ لا تعد صياغتَها ولا تحوّل تقديراً إلى حقيقةٍ مرصودة، "
    "ولا تخترع استنتاجاً ليس فيها.")
INSIGHT_WRITING_RULE_EN = (
    "**Analytical writing (mandatory):** order every paragraph **conclusion → "
    "what the number means for the exporter → the evidence with its source**. "
    "Every material number is followed by one sentence on what it changes for "
    "the decision. Write [INSIGHTS] items by their token — the system fills "
    "the range and the stated assumption; never restate an estimate as an "
    "observed fact, and never invent an insight that is not listed.")


LEDGER_TOKEN_RULE = (
    "**سجلّ الحقائق (إلزامي):** المعطيات الموسومة «اكتب الرمز لا القيمة» في "
    "[LEDGER] تُكتب برمزها بين قوسين مزدوجين — مثل {{tariff_applied_pct}} "
    "و{{open_conditions}} و{{requirements_count}} و{{blocking_condition}} "
    "و{{imports_latest_year}} — ولا تُكتب قيمتها ولا حالتها من عندك؛ النظام "
    "يستبدلها بالقيمة ومصدرها أو بإعلان الغياب بصيغة سليمة. الرمز بلاحقة "
    ":sentence (مثل {{open_conditions:sentence}}) يصير جملة كاملة تقف وحدها. "
    "لتقرير حالة أي معطى آخر (متاح/ضعيف/غير متاح) اكتب {{status:المفتاح}} لا "
    "كلمة من عندك. بقية الأرقام اكتبها بصيغتك الطبيعية (تقريب، مقارنة) — "
    "وتُفحص بعد الكتابة مقابل السجلّ بتسامح التقريب؛ رقم يخالفه يُعاد للتنقيح "
    "بجملته. لا تخترع رموزاً غير المسرودة.")
LEDGER_TOKEN_RULE_EN = (
    "**Fact ledger (mandatory):** facts marked 'write the token, not the "
    "value' under [LEDGER] are written by their double-brace token — e.g. "
    "{{tariff_applied_pct}}, {{open_conditions}}, {{requirements_count}}, "
    "{{blocking_condition}}, {{imports_latest_year}} — never their value or "
    "availability; the system substitutes the value with its source, or a "
    "well-formed absence sentence. A token with the :sentence suffix (e.g. "
    "{{open_conditions:sentence}}) becomes a standalone sentence. To state "
    "the status of any other fact write {{status:key}}. Write all other "
    "numbers in your natural phrasing (rounding, comparisons); they are "
    "checked against the ledger with rounding tolerance and a violating "
    "sentence is sent back. Do not invent tokens.")


def bind(text: str, ledger: dict, lang: str = "ar") -> tuple:
    """استبدل كل رمز بصيغته من السجلّ — يعيد (النص، {bound, unknown, used}).

    **الوحدةُ جملةٌ لا سطر** (مراجعة §58): رمزُ قيمةٍ غاب معطاه داخل جملةٍ
    كُتبت لرقمٍ تُستبدَل **جملتُه وحدها** بجملة الغياب، فلا تُبتَر فقرةٌ
    كاملة ولا يُهدَر ما حولها من سرد. وصفُّ جدولٍ (`| … |`) لا يُعاد بناؤه
    أبداً — يُملأ في مكانه بكلمة الغياب كي لا ينكسر عمودُ الجدول.
    """
    if not text or "{{" not in text:
        return text or "", {"bound": 0, "unknown": [], "used": []}
    entries = (ledger or {}).get("entries") or {}
    unknown: list = []
    used: list = []
    n = 0

    def _render(m, *, in_table: bool) -> str:
        nonlocal n
        is_status, key, as_sentence = m.group(1), m.group(2), m.group(3)
        e = entries.get(key)
        if e is None:
            unknown.append(key)
            return "not available" if lang == "en" else "غير متاح"
        n += 1
        used.append(key)
        if is_status:
            return render_status(e, lang)
        if as_sentence and not in_table:
            return render_sentence(e, lang)
        return render_value(e, lang)

    out_lines = []
    for line in text.split("\n"):
        if "{{" not in line:
            out_lines.append(line)
            continue
        in_table = line.lstrip().startswith("|")
        if in_table:
            out_lines.append(TOKEN_RE.sub(
                lambda m: _render(m, in_table=True), line))
            continue
        out_lines.append(_bind_line(line, entries, lang, _render))
    return "\n".join(out_lines), {"bound": n, "unknown": sorted(set(unknown)),
                                   "used": sorted(set(used))}


def _bind_line(line: str, entries: dict, lang: str, render) -> str:
    """املأ سطرَ نثرٍ جملةً جملة — الغائبُ يُبدِّل جملتَه لا السطرَ كلَّه."""
    prefix_m = _LIST_PREFIX_RE.match(line)
    prefix = prefix_m.group(1) if prefix_m else ""
    body = line[len(prefix):]
    parts = _SENT_KEEP_RE.split(body)
    out = []
    for part in parts:
        if "{{" not in part:
            out.append(part)
            continue
        gone = None
        for m in TOKEN_RE.finditer(part):
            is_status, key, as_sentence = m.group(1), m.group(2), m.group(3)
            e = entries.get(key)
            if (e is not None and not is_status and not as_sentence
                    and e["status"] == MISSING
                    and key not in _SELF_DESCRIBING_KEYS):
                gone = e
                break
        if gone is not None:
            tail = _trailing_space(part)
            out.append(render_sentence(gone, lang) + tail)
            continue
        out.append(TOKEN_RE.sub(lambda m: render(m, in_table=False), part))
    return prefix + "".join(out)


def _trailing_space(part: str) -> str:
    stripped = part.rstrip()
    return part[len(stripped):]


#: تقطيعٌ يحفظ الفواصل — الجملةُ تُستبدَل بعلامتها لا بدونها.
_SENT_KEEP_RE = re.compile(r"(?<=[.؛!؟])")


_LIST_PREFIX_RE = re.compile(r"^(\s*(?:[-*•]|\d+[.)]|#+)\s+)")


def _keep_list_prefix(line: str, new: str) -> str:
    m = _LIST_PREFIX_RE.match(line)
    return (m.group(1) if m else "") + new


# ── اللقطة · snapshot (الشرط ١) ─────────────────────────────────────────────

def snapshot_for(text: str, ledger: dict) -> dict:
    """لقطة الرموز التي **استخدمها الكاتب فعلاً**: القيمة والحالة والمصدر
    والسنة كما رآها — تُخزَّن مع التقرير. `leads` مستثناة بالبناء (ليست مفتاحاً)."""
    entries = (ledger or {}).get("entries") or {}
    snap: dict = {}
    for _st, key, _s in TOKEN_RE.findall(text or ""):
        e = entries.get(key)
        if e is not None and key not in snap:
            snap[key] = {"value": e.get("value"), "status": e["status"],
                         "source": e.get("source"), "year": e.get("year")}
    return snap


def stale_keys(snapshot: dict, ledger: dict) -> list:
    """المفاتيح التي اختلف السجلّ الحالي فيها عن لقطة الكاتب — لا تُملأ بصمت."""
    entries = (ledger or {}).get("entries") or {}
    out = []
    for key, seen in (snapshot or {}).items():
        e = entries.get(key)
        if e is None:
            continue
        if seen.get("status") == MISSING and e["status"] in _RANGED:
            continue      # غيابٌ صار تقديراً: تحسينٌ لا انزياح (الموجة د)
        if e["status"] != seen.get("status") or not _same_value(
                e.get("value"), seen.get("value")):
            out.append({"key": key, "label_ar": e["label_ar"],
                        "was": seen, "now": {"value": e.get("value"),
                                             "status": e["status"]}})
    return out


def _same_value(a, b) -> bool:
    fa, fb = _num(a), _num(b)
    if fa is not None and fb is not None:
        return abs(fa - fb) <= max(abs(fb) * 1e-6, 1e-9)
    return a == b


# ── فحص المسوّدة قبل التخزين · draft gate ───────────────────────────────────

def draft_issues(draft: str, ledger: dict, lang: str = "ar") -> list:
    """ملاحظات حاجبة حتمية على مسوّدة الكاتب — تعيد المسوّدة للتنقيح:
    (أ) رمز مخترَع؛ (ب) قيمة أو حالة مكتوبة لمعطى إلزامي الرمز؛ (ج) رقم
    طبيعي قرب تسمية معطى يخالف السجلّ خارج تسامح التقريب (المقارنات اللفظية
    لا تُفحص)؛ (د) رقم لمعطى غائب في السجلّ. كل ملاحظة تسمّي الجملة."""
    if not draft:
        return []
    issues: list = []
    entries = (ledger or {}).get("entries") or {}
    for _st, key, _s in TOKEN_RE.findall(draft):
        if key not in entries:
            issues.append(f"رمز غير مسرود في السجلّ «{{{{{key}}}}}» — احذفه أو "
                          "استعمل رمزاً من [LEDGER]")
    stripped = TOKEN_RE.sub(" ", draft)
    for sent in _religious_sentences_in_neutral_category(stripped, ledger):
        issues.append("لفظٌ دينيّ في تقرير فئةٍ لا صلةَ للدين بها (تصنيف فصل "
                      "HS) — احذفه أو استبدله بالمعطى التجاري المقصود: «"
                      f"{sent[:160]}»")
    for sent in _unsourced_channel_claims(stripped):
        issues.append("ادّعاءٌ عن القناة (هامش/سهولة تعاقد) بلا مصدرٍ ولا افتراض — "
                      "اذكر مصدره، أو قدّمه تقديراً بافتراضه، أو احذفه: «"
                      f"{sent[:160]}»")
    for key, e in entries.items():
        row = _KEY_ROWS[key]
        words = row.words
        if not words or row.writer_hidden:
            continue
        if e["status"] in _RANGED:
            bare = _ranged_bare_sentence(stripped, words, e)
            if bare:
                issues.append(f"«{e['label_ar']}» تقديرٌ بنطاقٍ في السجلّ "
                              f"({render_value(e, lang)}) لكن الجملة تكتبه رقماً "
                              f"واحداً بلا نطاق — أعد صياغتها بالنطاق والافتراض: «{bare}»")
            continue
        mandatory = row.mandatory
        for w in words:
            m = re.search(re.escape(w), stripped)
            if not m:
                continue
            sent = _sentence_at(stripped, m.start())
            win = stripped[m.end():m.end() + _WINDOW].split("\n")[0]
            if mandatory:
                # نفسُ حرّاس الفرع الآخر (مراجعة §58): رقمُ سنةٍ أو رقمُ
                # مفهومٍ مجاورٍ أو تعريفٌ أو سياقٌ مسموحٌ **ليس** كتابةً
                # لقيمة المعطى — ورفضُه يحرق نداءَ كاتبٍ مدفوعاً بلا سبب.
                nm_m = _NUM_RE.search(win[:_VALUE_WINDOW])
                wrote_number = bool(
                    nm_m and not _derived_context(sent, words)
                    and not _DEFINITION_RE.search(win[:nm_m.start()])
                    and not _other_key_between(win[:nm_m.start()], key)
                    and not _is_bare_year(nm_m, key))
                if _ABSENCE_RE.search(win.split("\n")[0]) or wrote_number:
                    issues.append(f"«{e['label_ar']}» رمزٌ إلزامي — لا تكتب قيمته "
                                  f"ولا حالته؛ اكتب {{{{{key}}}}} في: «{sent}»")
                    break
                continue
            if e["status"] != MISSING and _ABSENCE_RE.search(win):
                issues.append(f"«{e['label_ar']}» مرصود في السجلّ "
                              f"({render_value(e, lang)}) لكن الجملة تعلنه غير "
                              f"متاح — أعد صياغتها أو اكتب {{{{status:{key}}}}}: «{sent}»")
                break
            nm = _NUM_RE.search(win[:_VALUE_WINDOW])
            if nm and not _derived_context(sent, words) \
                    and not _DEFINITION_RE.search(win[:nm.start()]) \
                    and not _other_key_between(win[:nm.start()], key) \
                    and not _is_bare_year(nm, key):
                got = _scaled(nm)
                if e["status"] == MISSING and got is not None:
                    issues.append(f"«{e['label_ar']}» غير متاح في السجلّ لكن "
                                  f"الجملة تذكر رقماً — احذفه أو اكتب "
                                  f"{{{{status:{key}}}}}: «{sent}»")
                    break
                exp = _num(e.get("value"))
                if got is not None and exp is not None and not _within_tolerance(got, exp, e):
                    issues.append(f"«{e['label_ar']}» في السجلّ {render_value(e, lang)} "
                                  f"بينما الجملة تذكر {nm.group(0).strip()} — أعد "
                                  f"صياغة الجملة بالقيمة الصحيحة: «{sent}»")
                    break
    return issues


#: البند ٧ (الموجة د-٢): ادّعاءٌ عن هامش قناةٍ أو سهولةِ تعاقدٍ يحتاج مصدراً أو
#: يُقدَّم تقديراً بافتراضه، وإلا يُعاد للكاتب ثمّ يُحذَف عند نفاد الميزانية.
#: مفرداتُ المالك حرفياً («هامش القناة»، «سهولة التعاقد»، «الموزّعون يقبلون») —
#: **لا** «هامش الموزّع/التجزئة» لأنّهما معلمتا المحرّك المعلنتان اللتان يُؤمَر
#: الكاتبُ بذكرهما (مراجعةٌ ذاتية §58: كانتا تُحذَفان من جملة الافتراض نفسِها).
_CHANNEL_CLAIM_RE = re.compile(
    r"هامش(?:ات|ه|ها)?\s+(?:ال)?(?:قناة|قنوات|وسطاء)|سهولة\s+التعاقد|"
    r"يقبل(?:ون)?\s+الموزّع|الموزّعون\s+يقبلون|عقود\s+(?:ال)?موزّعين\s+سهلة|"
    r"channel margins?|easy to contract|distributors readily accept", re.IGNORECASE)
#: الجملةُ هنا تنتهي بنقطةٍ لا بفاصلةٍ منقوطة — «بافتراض شحن 12%؛ هامش…» جملةٌ
#: واحدةٌ افتراضُها في صدرها.
_CLAIM_SENT_RE = re.compile(r"(?<=[.!؟\n])")
_SOURCED_RE = re.compile(r"وفق|بحسب|حسب\s|المصدر|استناداً|كما ورد|according to|"
                         r"\bper\b|source|reported by", re.IGNORECASE)
_ESTIMATED_RE = re.compile(r"نقدّر|نقدر|بافتراض|إذا افترضنا|تقديرياً|على فرض|"
                           r"estimate|assuming|roughly", re.IGNORECASE)


def _unsourced_channel_claims(text: str) -> list:
    """الجملُ التي تدّعي عن القناة بلا مصدرٍ ولا افتراض."""
    out = []
    for sent in _CLAIM_SENT_RE.split(text or ""):
        if sent.lstrip().startswith("|"):
            continue                      # صفوفُ الجداول عناوينُ لا ادّعاءات
        if _CHANNEL_CLAIM_RE.search(sent) and not _SOURCED_RE.search(sent) \
                and not _ESTIMATED_RE.search(sent):
            out.append(sent.strip())
    return out


#: الموجة د-٣: ألفاظُ الدين في نصّ تقرير — تُمنَع في فئةٍ `religion_relevance
#: == "none"` (صناعيٌّ/كيميائيٌّ/معدنيّ): لا الحلالُ اشتراطٌ فيها ولا التركيبةُ
#: الدينية طلبٌ، فذكرُها حشوٌ يُضعِف الثقة (بلاغُ المالك، الموجة د).
#: «المسلمة» (شحنةٌ مُسلَّمة) و«الإسلاميّ» (البنك الإسلامي للتنمية — جهةُ
#: تمويلٍ تجاريّ) أُسقطتا بعد إعادة إنتاجهما إنذارَين كاذبَين يكلّفان دورةَ
#: كاتبٍ مدفوعة (مراجعةٌ ذاتية §58).
_RELIGIOUS_RE = re.compile(r"حلال|رمضان|العيدين|عيد الفطر|عيد الأضحى|"
                           r"المسلمين|halal|ramadan|muslim",
                           re.IGNORECASE)


def _religious_sentences_in_neutral_category(text: str, ledger: dict) -> list:
    """جملُ النصّ التي تذكر الدين بينما فئةُ المنتج لا صلةَ للدين بها.

    فصلٌ غيرُ مصنَّف أو سجلٌّ بلا رمز ⇒ لا حكم (لا كتمَ ذكرٍ بناءً على جهل).
    """
    hs = (ledger or {}).get("hs_code")
    if not hs:
        return []
    try:
        from silk_ai_judge import religion_relevance
    except Exception:  # noqa: BLE001
        return []
    if religion_relevance(hs) != "none":
        return []
    return [p.strip() for p in _SENT_SPLIT_RE.split(text or "")
            if _RELIGIOUS_RE.search(p)]


#: علاماتُ النطاق في الجملة — وجودُ إحداها قربَ التقدير يعني أنّه كُتب نطاقاً.
_RANGE_MARK_RE = re.compile(r"بين|نقدّر|نقدر|تقريباً|نحو|between|estimate|"
                            r"approximately|roughly|about", re.IGNORECASE)


def _ranged_bare_sentence(text: str, words: tuple, entry: dict) -> str:
    """الجملةُ التي تكتب تقديراً رقماً واحداً بلا نطاق — أو "" إن سلمت."""
    for w in words:
        for m in re.finditer(re.escape(w), text):
            win = text[m.end():m.end() + _VALUE_WINDOW].split("\n")[0]
            nm = _NUM_RE.search(win)
            if not nm or _is_bare_year(nm, entry["key"]):
                continue
            sent = _sentence_at(text, m.start())
            if _RANGE_MARK_RE.search(sent):
                continue
            return sent
    return ""


def _is_bare_year(match, key: str) -> bool:
    """رقمٌ عارٍ بأربع خانات في مدى السنوات = **سنةُ رصدٍ** لا قيمةُ المعطى.

    «دخل الفرد لليمن (2018)» كان يُقرأ قيمةً فيخالف السجلَّ (١٢٠٠ دولار) —
    إنذارٌ كاذبٌ على تقريرٍ صحيح (عائلة الدرس ٢٣٩).
    """
    if key == "imports_latest_year":
        return False
    if match.group(2):            # للرقم وحدةٌ (%/مليون…) فليس سنة
        return False
    tok = match.group(1).replace(",", "")
    return bool(_YEAR_RE.fullmatch(tok))


def _other_key_between(gap_text: str, key: str) -> bool:
    """هل يفصل **مفهومٌ آخر** من السجلّ بين التسمية والرقم؟

    جملةٌ تذكر معطيين ورقماً واحداً تنسب الرقمَ إلى الأقرب لا إلى الأول
    («حصة السعودية المنخفضة مقابل نمو السوق 9.3%»).
    """
    for other, row in _KEY_ROWS.items():
        if other == key:
            continue
        if any(w and w in gap_text for w in row[4]):
            return True
    return False


def _derived_context(sentence: str, words: tuple) -> bool:
    """هل الرقمُ في سياقٍ مسموحٍ صراحةً (الشرط ٤)؟

    سياقٌ يطابق كلمةً من **تسمية المعطى نفسه** لا يُعَدّ سماحاً («حصة» داخل
    «الحصة السعودية» كانت تُعطِّل الفحصَ على المعطى الذي وُضع له).
    """
    allow = [a for a in DERIVED_ALLOWED
             if not any(a in w for w in words)]
    return any(a in sentence for a in allow)


def _sentence_at(text: str, pos: int) -> str:
    start = max(text.rfind(ch, 0, pos) for ch in ".؛\n!؟") + 1
    end_candidates = [i for i in (text.find(ch, pos) for ch in ".؛\n!؟") if i >= 0]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end].strip()[:160]


def _scaled(m) -> "float | None":
    v = _num(m.group(1).replace(",", ""))
    if v is None:
        return None
    unit = m.group(2) or ""
    return v * _SCALE.get(unit, 1.0)


def _within_tolerance(got: float, exp: float, entry: dict) -> bool:
    """تسامح التقريب: ±2%، أو تقريب إلى منزلة معروضة (18.7 مليون ≈ 18,700,000)."""
    if exp == 0:
        return abs(got) <= 0.05
    if abs(got - exp) / abs(exp) <= _TOLERANCE:
        return True
    # نسبةٌ مكتوبة بمنزلة أقل («25%» لـ25.4).
    if entry.get("unit") == "%" and abs(round(exp) - got) < 0.5:
        return True
    return False


# ── الفحص على النص المُصيَّر · check (شبكة الأمان) ───────────────────────────

def _finding(check: str, note: str, *, always_block: bool = False) -> dict:
    return {"check": check, "repairable": (not enforce()) and not always_block,
            "note": note}


def check(view: dict, text: str) -> list:
    """قابِل النصَّ النهائي المُصيَّر بالسجلّ — يعيد ملاحظات بشكل بوابة
    الجودة. تحذيرية افتراضاً (قياس)، وغير قابلة للإصلاح تحت الإنفاذ؛ رمزٌ
    غير مملوء حاجب دائماً (رمز داخلي لا يصل العميل)."""
    if not text:
        return []
    ledger = (view or {}).get("ledger") or {}
    entries = ledger.get("entries") or {}
    findings: list = []
    # **يُفحَص قبل أيّ شيء وبلا سجلّ** (مراجعة §58): تعذُّرُ بناء السجلّ هو
    # نفسُه الحالةُ التي يُتخطّى فيها الملء، فلو اشترط الفحصُ وجودَ سجلٍّ
    # لمرّت الرموزُ غيرُ المملوءة إلى العميل في الحالة الوحيدة التي تقع فيها.
    if "{{" in text:
        findings.append(_finding(
            "ledger_token_unbound",
            "رمز سجلّ داخلي غير مملوء وصل نصاً مُصيَّراً — لا يُسلَّم",
            always_block=True))
    if not entries:
        return findings
    for s in ledger.get("stale") or []:
        findings.append(_finding(
            "ledger_stale",
            f"«{s['label_ar']}» تغيّر منذ كتابة التقرير ({s['was'].get('value')} "
            f"→ {s['now'].get('value')}) — القسم مُعلَّم قديماً ويحتاج إعادة توليد"))
    for key, e in entries.items():
        row = _KEY_ROWS[key]
        words = row.words
        if not words or not row.numeric_check:
            continue
        if e["status"] in _RANGED:
            # التقديرُ لا يُقارَن بقيمةٍ واحدة — لكنّ رقماً واحداً بلا نطاقٍ
            # قربَ تسميته هو عينُ «التقدير رقماً عارياً» (مراجعة §58).
            bare = _ranged_bare_sentence(text, words, e)
            if bare:
                findings.append(_finding(
                    "ledger_value_mismatch",
                    f"«{e['label_ar']}» تقديرٌ بنطاقٍ ({render_value(e)}) بينما "
                    f"النص يكتبه رقماً واحداً بلا نطاق قرب «…{bare[:60]}…»"))
            continue
        for w in words:
            for m in re.finditer(re.escape(w), text):
                win = text[m.end():m.end() + _WINDOW].split("\n")[0]
                near = f"…{text[max(0, m.start() - 20):m.end() + 30]}…"
                if e["status"] != MISSING and _ABSENCE_RE.search(win):
                    findings.append(_finding(
                        "ledger_status_mismatch",
                        f"«{e['label_ar']}» مرصود في السجلّ ({render_value(e)}) "
                        f"بينما النص يعلنه غير متاح قرب «{near}»"))
                    break
                nm = _NUM_RE.search(win[:_VALUE_WINDOW])
                if nm and e["status"] != MISSING:
                    sent = _sentence_at(text, m.start())
                    if _derived_context(sent, words):
                        continue
                    # فاصلٌ بين التسمية والرقم (تعريفٌ/عتبةٌ/مفهومٌ آخر) =
                    # ليست قراءةَ هذا المعطى — لا تُحكَم مخالفةً.
                    gap_txt = win[:nm.start()]
                    if _DEFINITION_RE.search(gap_txt) or \
                            _other_key_between(gap_txt, key) or \
                            _is_bare_year(nm, key):
                        continue
                    got, exp = _scaled(nm), _num(e.get("value"))
                    if got is not None and exp is not None and \
                            not _within_tolerance(got, exp, e):
                        findings.append(_finding(
                            "ledger_value_mismatch",
                            f"«{e['label_ar']}» في السجلّ {render_value(e)} بينما "
                            f"النص يذكر {nm.group(0).strip()} قرب «{near}»"))
                        break
            else:
                continue
            break
    oc = entries.get("open_conditions") or {}
    try:
        from silk_quality_gate import _stated_condition_counts
        stated = _stated_condition_counts(text)
    except Exception:  # noqa: BLE001
        stated = []
    actual = int(oc.get("value") or 0)
    bad = sorted({n for n, _p, _f in stated if n != actual})
    if stated and bad:
        findings.append(_finding(
            "ledger_count_mismatch",
            f"النص يذكر عدد شروط {bad} بينما قائمة السجلّ الواحدة تحمل {actual}"))
    ly = entries.get("imports_latest_year") or {}
    if ly.get("status") != MISSING and ly.get("value"):
        latest = int(ly["value"])
        for m in re.finditer(r"واردات|الواردات|imports", text):
            win = text[m.start():m.end() + 60].split("\n")[0]
            yrs = [int(y) for y in _YEAR_RE.findall(win)]
            if yrs and max(yrs) > latest:
                findings.append(_finding(
                    "ledger_series_year_mismatch",
                    f"النص ينسب الواردات إلى سنة {max(yrs)} بينما أحدث سنة "
                    f"مرصودة في السلسلة {latest}"))
                break
        charts = ((view.get("deep_research") or {}).get("charts") or []) \
            if isinstance(view, dict) else []
        for ch in charts:
            cy = _num(ch.get("year")) if isinstance(ch, dict) else None
            if isinstance(ch, dict) and ch.get("id") == "imports_trend" and cy \
                    and int(cy) != latest:
                findings.append(_finding(
                    "chart_year_mismatch",
                    f"رسم الواردات موسوم بسنة {int(cy)} بينما أحدث سنة مرصودة "
                    f"{latest}"))
    bc = entries.get("blocking_condition") or {}
    if bc.get("value"):
        needle = _distinct_tokens(str(bc["value"]))
        # الأنماطُ من كلمات التعرّف نفسِها (التسميةُ الجديدة والقديمة — مصدرٌ
        # واحد)، والمقارنةُ على ما **بعد** التسمية: كلماتُ التسمية نفسِها
        # («الشحن»…) كانت تُرضي الإبرةَ فيمرّ تعريفٌ مخالف (مراجعة §58).
        _bc_words = [w for w in _KEY_ROWS["blocking_condition"].words
                     if re.search(r"[؀-ۿ]", w)]
        _bc_re = "|".join(map(re.escape, _bc_words))
        for m in re.finditer(_bc_re, text):
            sent = text[m.end():m.end() + 200].split("\n")[0]
            if needle and not any(t in sent for t in needle):
                findings.append(_finding(
                    "blocking_condition_drift",
                    f"النص يذكر «المتطلب السابق للتعاقد أو الشحن» بغير تعريف السجلّ "
                    f"({str(bc['value'])[:60]}) قرب «…{sent[:60]}…»"))
                break
    return findings


def _distinct_tokens(s: str) -> list:
    return [w for w in re.findall(r"[\w؀-ۿ]{4,}", s) if w not in
            ("جانب", "غائب", "متاح", "قبل", "قرار", "نهائي", "مصادره")][:4]


# ── الإصلاح من السجلّ (وضع الإنفاذ) · repair ─────────────────────────────────

def repair(text: str, ledger: dict, lang: str = "ar") -> tuple:
    """أصلح النصَّ المُصيَّر من السجلّ قبل الحجب — إعادةُ صياغة **الجملة
    كاملة** (لا استبدال الرقم وحده، التعديل ٨): عدد الشروط بمطابقة العدد
    والمعدود، وإعلان غيابٍ لمعطىً مرصود. يعيد (النص، قائمة الإصلاحات).

    **تُعاد المطابقة داخل كل جملة على حدة** (مراجعة §58): مواضعُ
    `_stated_condition_counts` مقيسةٌ على نصٍّ مُطبَّع بطول مختلف، فاستعمالُها
    هنا كان يحذف الجملةَ الخطأ ويُبقي المخالِفة.
    """
    if not text:
        return text, []
    entries = (ledger or {}).get("entries") or {}
    repairs: list = []
    oc = entries.get("open_conditions") or {}
    actual = int(oc.get("value") or 0)
    out: list = []
    claims = set(_unsourced_channel_claims(text))
    for part in _SENT_SPLIT_RE.split(text):
        tail = "\n" if part.endswith("\n") else ""
        fixed = part
        if claims and part.strip() in claims:
            # البند ٧: بلا مصدرٍ ولا افتراض ⇒ تُحذَف الجملةُ لا تُعدَّل.
            repairs.append({"kind": "channel_claim", "before": part.strip(),
                            "after": ""})
            out.append(tail)
            continue
        if oc and _sentence_states_wrong_count(part, actual):
            new = render_sentence(oc, lang)
            repairs.append({"kind": "open_conditions_count",
                            "before": part.strip(), "after": new})
            out.append(_keep_list_prefix(part, new) + tail)
            continue
        for key, e in entries.items():
            row = _KEY_ROWS[key]
            words = row.words
            if e["status"] == MISSING or not words or not row.numeric_check:
                continue
            if any(w in part for w in words) and _ABSENCE_RE.search(part):
                new = render_sentence(e, lang)
                repairs.append({"kind": "status", "key": key,
                                "before": part.strip(), "after": new})
                fixed = _keep_list_prefix(part, new) + tail
                break
        out.append(fixed)
    return "".join(out), repairs


def _sentence_states_wrong_count(sentence: str, actual: int) -> bool:
    """هل تذكر هذه الجملةُ عددَ شروطٍ مفتوحةٍ يخالف القائمةَ الواحدة؟

    تُقاس **داخل الجملة نفسِها** فلا تنزلق المواضعُ بين نصٍّ ونصٍّ مُطبَّع.
    """
    try:
        from silk_quality_gate import _stated_condition_counts
        stated = _stated_condition_counts(sentence)
    except Exception:  # noqa: BLE001 — تعذّرُ القراءة = لا إصلاح
        return False
    return any(n != actual for n, _p, _f in stated)


# ── جدولُ النواقص الواحد · one gaps table (الدرس ٢٦٤) ───────────────────────
# **بلاغ المالك:** «ادمج النواقص المتشابهة في جدول واحد بدل سردها بالصياغة
# نفسها». المقيس قبل الإصلاح: ٧٫٥ سطرِ نقصٍ في المتوسط لكلّ تقرير موزّعةً على
# ٣–٥ أقسام، أغلبُها في قسم الاقتصاد وجدول أرقام القرار — نفسُ المعطى يُعلَن
# ناقصاً أكثر من مرّة بصياغاتٍ متقاربة.
#
# الجدولُ يُبنى من **مصدرٍ واحد** (السجلّ + فجوات الاقتصاد + الحدود المعلنة)
# بعد إزالة المكرَّر بالمحتوى، ويُفرِّق «ناقص» عن «مرصود بتوثيق ضعيف».

_GAP_NORM_RE = re.compile(r"[\sً-ْـ]+")


def _gap_key(text: str) -> str:
    """مفتاحُ تطبيعٍ للمقارنة — يطوي التشكيل والفراغ وعلامات الترقيم."""
    t = _GAP_NORM_RE.sub(" ", str(text or "")).strip(" .،؛:-—")
    return t[:80].lower()


def _split_gap(line: str) -> tuple:
    """(المعطى، سبيلُ الإغلاق) من سطرِ فجوةٍ مكتوب — بلا اختلاق.

    صيغُ الريبو القائمة: «X غير محسوب — الناقص: Y» و«X: Y» و«X غير متاح».
    ما لا يُفصَّل يبقى كلُّه في عمود المعطى وسبيلُه فارغ (يُقال «—»).
    """
    text = str(line or "").strip()
    for sep in (" — الناقص: ", " - الناقص: ", " — يُغلَق عبر: ",
                " — يتطلب ", " — يتطلّب "):
        if sep in text:
            head, tail = text.split(sep, 1)
            return head.strip(" .،؛"), tail.strip(" .،؛")
    # ذيلٌ بعد شرطةٍ يصلح سبيلَ إغلاقٍ **فقط إن كان إجراءً** — «اعتُمدت 0%
    # في الحل العكسي» نتيجةٌ لا إجراء، ووضعُها في عمود «ما يلزم لإغلاقه»
    # يجعل الجدولَ يكذب على قارئه.
    for sep in (" — ", " - "):
        if sep in text:
            head, tail = text.split(sep, 1)
            if _is_actionable(tail):
                return head.strip(" .،؛"), tail.strip(" .،؛")
            break
    # ذيلُ «:» كان يدخل عمودَ الإغلاق بلا شرط، فحطّ شرحُ «بيانات فئة مجاورة»
    # («رمز HS … لا يشمل صفة المنتج») في خانة «ما يلزم لإغلاقه» — شرحٌ لا
    # إجراء (مراجعةٌ ذاتية §58). الشرطُ نفسُه يسري هنا.
    if ": " in text and len(text.split(": ", 1)[0]) <= 45:
        head, tail = text.split(": ", 1)
        if _is_actionable(tail):
            return head.strip(" .،؛"), tail.strip(" .،؛")
    return text.strip(" .،؛"), ""


#: فعلُ إجراءٍ في صدر الذيل — عربيٌّ وإنجليزيّ.
_ACTIONABLE_RE = re.compile(
    r"^(أدخل|أكمل|حدِّث|حدث|تحقّق|تحقق|أعد|راجع|اطلب|سجِّل|سجل|احصل|قدِّم"
    r"|يتطلب|يتطلّب|يلزم|يحتاج|أضف|وفّر|وفر|enter|add|provide|request|verify"
    r"|update|obtain|submit|supply|needs|requires)\b")


def _is_actionable(tail: str) -> bool:
    """أهذا الذيلُ **إجراءً** يُغلِق الفجوة، أم شرحاً لها؟

    الفعلُ قد تسبقه كلمةٌ واحدةٌ رابطة («إغلاقها يتطلّب بحثاً ميدانياً») —
    فالمطابقةُ على الصدر وحدَه كانت تترك سبيلَ إغلاقٍ حقيقياً في عمود المعطى
    (مراجعةٌ ذاتية §58). وما بعد الكلمتين شرحٌ لا إجراء، فلا يُوسَّع أكثر.
    """
    t = " ".join(str(tail or "").split())
    if not t:
        return False
    words = t.split(" ", 1)
    return bool(_ACTIONABLE_RE.match(t) or
                (len(words) > 1 and _ACTIONABLE_RE.match(words[1])))


def clip_clause(text: str, limit: int = 120) -> str:
    """قصٌّ **صادق**: عند حدّ شبهِ جملة، وبعلامةِ قصٍّ حين لا حدَّ يكفي.

    عيبان قاسهما التحقّقُ قبل الشحن (مراجعةٌ ذاتية §58): الخوارزميةُ الأولى
    كانت تعيد **أوّلَ** مقطعٍ مهما قصُر فتُسقِط باقي الجملة صامتةً («A — B»
    تصير «A»)، وحين لا مقطعَ يكفي كانت تقصّ عند الكلمة فيخرج كِسْرٌ مُعلَّق
    («… لاستكمال أحد»). الآن: أطولُ مقطعٍ يقع داخل الحدّ، وإلّا قصٌّ عند
    الكلمة بعلامة «…» تقول للقارئ إنّ ثمّة بقيّة. ولا قصَّ أصلاً لما يسع.
    """
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    best = ""
    for sep in ("؛", "،", " — ", ". "):
        if sep not in t:
            continue
        acc = ""
        for piece in t.split(sep):
            cand = (acc + sep + piece) if acc else piece
            if len(cand.strip()) > limit:
                break
            acc = cand
        head = acc.strip(" .،؛-—")
        if len(head) > len(best):
            best = head
    # كلُّ اختصارٍ يُعلِن نفسَه: القصُّ عند حدِّ مقطعٍ كان يُسقِط البقيّةَ
    # **صامتاً** — وهو عينُ ما يمنعه عقدُ «لا فجوةَ مطويّة» (مراجعةٌ ذاتية).
    if best:
        return best + "…"
    cut = t[:max(1, limit - 1)].rsplit(" ", 1)[0].strip(" ،؛-—")
    return (cut + "…") if cut else t[:limit]


#: حدُّ خليّةِ الجدول — فهرسٌ يُقرأ بلمحة. ما تجاوزه يُطبَع كاملاً تحته.
_GAP_WHAT_LIMIT = 180
_GAP_HOW_LIMIT = 160


def gaps_table(view: dict, lang: str = "ar") -> list:
    """صفوفُ جدول النواقص الواحد: (المعطى، الحالة، سبيلُ الإغلاق).

    يُدمِج سجلَّ الحقائق وفجواتِ قسم الاقتصاد وحدودَ التقرير في قائمةٍ واحدة
    بلا تكرار. `[]` حين لا نقص — فلا يُطبَع جدولٌ فارغ.
    """
    if not isinstance(view, dict):
        return []
    en = lang == "en"
    # تسمياتُ الحالة هنا **لغةُ قارئ** لا أسماءُ حالات السجلّ: «ناقص» و«مرصود
    # بتوثيق ضعيف» مفرداتٌ داخلية وصلت جدولَ العميل (بلاغ المالك بعد الدرس
    # ٢٦٤) — تُصلَح في منشئها الواحد فلا يحملها أيُّ سطحٍ حاضرٍ أو قادم.
    lbl_missing = "not yet known" if en else "لم يُعرَف بعد"
    lbl_weak = ("from unofficial sources only" if en
                else "مرصود من مصادر غير رسمية فقط")
    rows: list = []
    seen: set = set()

    def add(what: str, status: str, how: str) -> None:
        # قيمةٌ ليست نصّاً (رقمٌ تسرّب إلى `limits`) ليست فجوةً مقروءة.
        what = what.strip() if isinstance(what, str) else ""
        if not what or not any(c.isalpha() for c in what):
            return
        # المفتاحُ يقطع عند ٨٠ محرفاً بينما المعطى يبلغ ١٨٠: فجوتان تشتركان
        # في صدرهما كانتا تُطويان في صفٍّ واحدٍ بلا أثر (مراجعةٌ ذاتية §58).
        key = _gap_key(what) + "|" + _gap_key(how)
        if key in seen:
            return
        seen.add(key)
        # الحدُّ سخيٌّ عمداً: قياسُ الـPDF الحقيقيّ أثبت أنّ سببَ المحاذاة
        # اليسارية ليس طولَ النصّ بل **موضعَ العمود** — التفافُ خليّةٍ في
        # العمود الأيسر يبدأ من هامش اليسار فيطابق إمضاءَ انقلاب jc. فصار
        # العمودُ الأيسر «الحالة» (مفرداتٌ قصيرةٌ لا تلتفّ)، وبقي النصُّ
        # كاملاً بلا قصٍّ في أغلب الصفوف.
        short_what = clip_clause(what, _GAP_WHAT_LIMIT)
        short_how = clip_clause(how, _GAP_HOW_LIMIT) if how else "—"
        full = (what + " — " + how) if how else what
        rows.append({"what": short_what, "status": status, "how": short_how,
                     "status_code": WEAK if status == lbl_weak else MISSING,
                     # الصفُّ المُختصَر يحمل أصلَه كاملاً: الجدولُ فهرسٌ
                     # يُقرأ، والتفصيلُ يُطبَع تحته مرّةً — فلا سطرٌ يضيع.
                     "full": " ".join(full.split()),
                     "clipped": short_what != what or (
                         bool(how) and short_how != how)})

    # **ما يُطبَع فعلاً وحدَه** يدخل الجدول: مفتاحٌ لم يقرأه المحرّك ولا
    # يذكره أيُّ قسمٍ ليس «نقصاً يراه القارئ» — إدراجُه يصنع قائمةَ إخفاقاتٍ
    # طويلةً بلا سبيلِ إغلاق، وهو عكسُ المطلوب (دمجُ المكرَّر لا تكثيرُه).
    # ويُستثنى من ذلك **الضعيفُ التوثيق**: مرصودٌ ويُعرَض رقمُه، وحالتُه لا
    # تظهر اليوم في أيّ سطح رغم أنها فرقٌ طلبه المالك صراحةً.
    ledger = view.get("ledger") or {}
    for g in ledger.get("gaps") or []:
        if g.get("status") != WEAK:
            continue
        label = g.get("label_en") if en else g.get("label_ar")
        add(label, lbl_weak, _split_gap(g.get("note") or "")[1])
    # فجواتُ قسم الاقتصاد **لا تدخل** الجدول: القسمُ يطبعها بنصّها في
    # موضعها (وحجبُها هناك أعاد حادثةَ E-03 — غيابٌ صامتٌ بعد إعلان)،
    # فإدراجُها هنا يجعل التقريرَ يقول المعطى مرّتين بالصياغة نفسها —
    # وهو بعينه ما طلب المالكُ إنهاءه. قِيس: أربعةٌ من خمسةِ صفوفٍ في
    # مدوّنة الأردن كانت مكرّرةً حرفياً (مراجعةٌ ذاتية §58).
    for line in (view.get("limits") or []):
        what, how = _split_gap(line)
        add(what, lbl_missing, how)
    return rows


# ── الموجة د-٤: تقديراتٌ بعد اكتمال العرض · post-view estimates ─────────────
#
# **لماذا هنا لا في `build_ledger`:** قسمُ الاقتصاد (`economics_view`) يُبنى
# داخل العرض، والسجلُّ يُبنى قبله — فالتقديراتُ المشتقّة منه تُكتب في الخطوة
# نفسِها التي تُبنى فيها صفوفُ النواقص (`silk_render.build_view`، بعد اكتمال
# العرض). لا شبكةَ ولا نموذج: حسابٌ من أرقامٍ مرصودةٍ بسيناريوهاتٍ معلنة.
def fill_estimates(view: dict, lang: str = "ar") -> None:
    """اكتب تقديراتِ البند ١١ في سجلّ العرض — بنطاقها وافتراضها، أو لا شيء.

    قاعدةُ المالك: **لا تقديرَ بلا افتراضٍ معلن ونطاق**؛ ومدخلٌ ناقصٌ = لا
    تقدير (يبقى المفتاح غائباً ومخفياً، لا رقمٌ مخترَع).

    `lang` يحكم **نصَّ الافتراض والوحدة** لا الرقم: الافتراضُ يُطبَع مع كلّ
    تقديرٍ في كلّ سطح (`_estimate_text`)، فافتراضٌ عربيٌّ في تقريرٍ إنجليزيّ
    نصٌّ لا يقرؤه صاحبُه — والرقمُ بلا افتراضٍ مقروءٍ تقديرٌ بلا افتراض.
    """
    if not isinstance(view, dict):
        return
    en = str(lang or "").lower() == "en"

    def _t(ar: str, en_txt: str) -> str:
        return en_txt if en else ar
    ledger = view.get("ledger")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), dict):
        return
    entries = ledger["entries"]
    eco = ((view.get("deep_research") or {}).get("economics") or {})

    def _put(entry: dict) -> None:
        entries[entry["key"]] = entry
        if entry["key"] not in (ledger.get("order") or []):
            ledger.setdefault("order", []).append(entry["key"])

    # (أ) مضاعفُ الحدود إلى الرف — سعرُ الرف المرصود ÷ قيمةِ الوحدة الحدودية.
    anchor = (eco.get("anchor_price") or {})
    # **الأساسُ قبل العملة.** الطرفُ الآخر `border_price_usd_kg` سعرُ
    # **كيلوغرام**؛ فـ`anchor["value_usd"]` لا يصلح له: هو `per_unit / fx`
    # (`silk_economics.py:292`) أي سعرُ **عبوة** — قسمتُه على سعر كيلوغرام
    # تُخرج مضاعفاً مخترَعاً من مقامَين مختلفَين (§58). فالمقياسُ الوحيد
    # المقبول `per_kg` بالدولار، وإلا **لا تقدير** — لا احتياطَ بـ`raw_value`
    # (سعرُ عبوةٍ مجهولةِ الحجم).
    cur = str(anchor.get("currency") or "")
    shelf = _num(anchor.get("per_kg")) if cur in ("$", "USD", "دولار") else None
    border = _num((entries.get("border_price_usd_kg") or {}).get("value"))
    if shelf and border and border > 0:
        mult = round(shelf / border, 2)
        _put(insight_entry(
            "border_to_shelf_multiple", mult, grade=ESTIMATE,
            range=(round(mult * 0.8, 2), round(mult * 1.2, 2)),
            assumption=_t("سعرَ الرف المرصود قابلاً للمقارنة بقيمة الوحدة "
                          "الحدودية للصنف نفسِه، والنطاقُ ±20% لاختلاف "
                          "العبوة والقناة بين رصدةٍ وأخرى",
                          "the observed shelf price is comparable to the "
                          "border unit value of the same code, with a ±20% "
                          "range for pack and channel differences"),
            basis=("border_price_usd_kg", "competitor_prices"),
            source="حساب من السجلّ", unit="×",
            note=_t("كم يتضاعف السعرُ بين الحدود والرف في هذه الفئة",
                    "how much the price multiplies between border and "
                    "shelf in this category")))

    # (ب) أقصى سعرِ مصنعٍ منافس — بالنطاق من السيناريوهات الثلاثة المعلنة.
    rev = (eco.get("reverse_solve") or {})
    scen = [_num(r.get("max_exw")) for r in (rev.get("scenarios") or [])]
    scen = [v for v in scen if v is not None]
    mid = _num(rev.get("max_exw"))
    # تناقضُ التسعير المُعلَن (`pricing_contradiction`) يعني أنّ المحرّك نفسَه
    # يحذّر أنّ السقفَ لا يصلح أساساً للتفاوض (تركيا: نقصٌ 97.9%، ليبيا 50.5%)
    # — تقديمُه جواباً لسؤال «بكم أبيع للمصنع؟» رقمٌ مضلّلٌ في مسار المال،
    # وهو عينُ حادثة تقرير #11. فلا تقديرَ هنا، ويبقى التحذيرُ في قسم
    # الاقتصاد حيث يُشرَح (§58).
    if eco.get("pricing_contradiction"):
        mid = None
    if mid is not None and len(scen) >= 2:
        unit = f"{rev.get('currency') or ''}/{rev.get('unit') or ''}".strip("/")
        _put(insight_entry(
            "max_exw_estimate", mid, grade=ESTIMATE,
            range=(min(scen), max(scen)),
            assumption=_t("الشحنَ والهوامشَ عند سيناريو المتوسط المعلن، "
                          "والنطاقُ من السيناريوهين المنخفض والمرتفع",
                          "the range comes from the three declared freight "
                          "and margin scenarios (low/mid/high); the figure "
                          "shown is the mid scenario"),
            basis=("competitor_prices", "tariff_applied_pct"),
            source="حساب من السجلّ", unit=unit or None,
            note=_t("سقفُ سعر المصنع الذي يسمح بمجاراة سعر الرف المرصود",
                    "the ex-works ceiling that still matches the observed "
                    "shelf price"),
            how_to_close=_t("يضيق النطاقُ بعرضِ شحنٍ فعليٍّ وهامشِ موزّعٍ "
                            "مُتفاوَضٍ بدل السيناريوهات",
                            "the range narrows with an actual freight quote "
                            "and a negotiated distributor margin instead of "
                            "the scenarios")))

    # (ج) حجمُ الشحنة التجريبية — من بندِ القرار المحسوب حتمياً.
    for row in (eco.get("decision_numbers") or []):
        if not isinstance(row, dict) or "تجريبية" not in str(row.get("name") or ""):
            continue
        val = _num(row.get("value"))
        if val is None:
            break
        rng = row.get("range") or {}
        lo, hi = _num(rng.get("low")), _num(rng.get("high"))
        # نطاقُ البند المحسوب قد يكون نقطةً واحدة (حمولةٌ كاملة) — فيُوسَّع
        # صراحةً إلى «نصفُ حمولةٍ إلى حمولة»: أوّلُ شحنةٍ تُشحَن جزئيةً عادةً.
        # **والذيلُ يتبع ما وقع فعلاً**: إلحاقُه بنطاقٍ جاء من البند نفسِه
        # (مصر: ±4.9% من كثافة الصنف) افتراضٌ **يناقض نطاقَه** المطبوع
        # بجانبه — أسوأُ من غيابه لأنه يُطمئن (§58).
        widened = lo is None or hi is None or lo >= hi
        if widened:
            lo, hi = round(val * 0.5, 2), val
        _method = str(row.get("method")
                      or _t("حاويةٌ واحدةٌ بسعتها المنشورة",
                            "one container at its published capacity"))
        _put(insight_entry(
            "trial_shipment_units", val, grade=ESTIMATE, range=(lo, hi),
            assumption=(_method + (
                _t("؛ والنطاقُ من نصف حمولةٍ إلى حمولةٍ كاملة",
                   "; the range spans half a load to a full load")
                if widened else
                _t("؛ والنطاقُ كما حسبه بندُ القرار",
                   "; the range is the one the decision item computed"))),
            basis=("market_imports_usd",),
            source=str(row.get("source") or "حساب من السجلّ"),
            # بندُ القرار قد يصل بلا وحدة؛ و«وحدة» وصفُ ما عدَّه المحرّك
            # فعلاً (الحمولة ÷ وزن الوحدة) لا وحدةٌ مُختلَقة — رقمٌ عارٍ
            # يُقرأ كيلوغرامات أو دولارات سهواً.
            unit=str(row.get("unit") or "") or _t("وحدة", "units"),
            how_to_close=str(row.get("confirm") or ""),
            note=_t("حجمُ أوّل شحنةٍ معقولة بالوحدات",
                    "a reasonable first-shipment size in units")))
        break


# ── الموجة د-٤ (البند ١٠): أسئلةُ المصدّر الحاسمة ───────────────────────────
_QUESTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "data", "critical_questions_l1.csv")


def _question_rows() -> list:
    """صفوفُ `data/critical_questions_l1.csv` — تعذُّرُ القراءة = لا قسم."""
    import csv
    try:
        with open(_QUESTIONS_PATH, encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(
                l for l in fh if not l.startswith("#"))]
    except OSError as e:  # noqa: BLE001 — غيابُ الملف يُعلَن ولا يكسر العرض
        import logging
        logging.getLogger(__name__).error(
            "critical_questions_l1.csv unreadable: %s", e)
        return []
    out = []
    for r in rows:
        try:
            out.append({k: (r.get(k) or "").strip()
                        for k in ("category", "q_key", "question_ar",
                                  "question_en", "answer_keys",
                                  "how_to_learn_ar", "how_to_learn_en")}
                       | {"order": int(r.get("order") or 99)})
        except (TypeError, ValueError):
            continue
    return out


def _answer_cell(entry: dict, lang: str) -> str:
    """جوابُ الخليّة = `render_value` نفسُها — **مُصيِّرٌ واحدٌ لا ثانٍ**.

    كانت الخليّةُ تختصر: التقديرُ نطاقَه بلا افتراضِه، والاستنتاجُ قيمتَه بلا
    أساسِه. وهذا خرقٌ لقيد المالك («لا تقديرَ بلا افتراضٍ معلنٍ ونطاق»)
    ولمبدأ «لكلّ رقمٍ سطرُ مصدره» حين يكون هذا القسمُ الموضعَ الوحيدَ الذي
    يرى فيه القارئُ الرقم (قِيس على `samples/research_report_latest.md`:
    «بين 13,365 و26,730 (تقدير)» — نطاقٌ بلا افتراضٍ ولا وحدة). ودافعُ
    الاختصارِ الأصليُّ — عرضُ خليّةِ Word — زال ببناءِ القسم فقراتٍ في
    `silk_reports._docx_questions`. ولا قصَّ بـ«…» أبداً: بوّابةُ نصّ العميل
    ترفض سطراً ينتهي بنقاط حذف (قِيس على مدوّنة هولندا).
    """
    return " ".join(render_value(entry, lang).split())


def critical_questions(view: dict, lang: str = "ar") -> list:
    """صفوفُ «أسئلة المصدّر الحاسمة»: (السؤال، الجواب، الحالة، كيف تعرفه).

    الجوابُ **من السجلّ حصراً** بصيغته الطبيعية (مرصودٌ أو تقديرٌ بنطاقه)،
    وإلا «لم نعرفه بعد» وسبيلُ الإغلاق من الملفّ. الكاتبُ لا يكتب هذا القسم —
    فلا يختلق جواباً ولا يُسقِط سؤالاً (قرارُ المالك، البند ١٠).
    """
    if not isinstance(view, dict):
        return []
    ledger = view.get("ledger") or {}
    entries = ledger.get("entries") or {}
    if not entries:
        return []
    try:
        from silk_ai_judge import product_profile
        category = (product_profile(ledger.get("hs_code")
                                    or view.get("hs_code")) or {}).get("category")
    except Exception:  # noqa: BLE001
        category = None
    en = lang == "en"
    rows = [r for r in _question_rows()
            if r["category"] == "all" or r["category"] == category]
    rows.sort(key=lambda r: (r["order"], r["q_key"]))
    out: list = []
    said: set = set()
    for r in rows:
        answer = status = ""
        duplicate = False
        for key in [k.strip() for k in r["answer_keys"].split(";") if k.strip()]:
            e = entries.get(key)
            if not e or e.get("status") == MISSING or e.get("value") is None:
                continue
            txt = _answer_cell(e, lang)
            # **قُل الشيءَ مرّةً (الدرس ٢٦٤) — بالنصّ لا بالمفتاح.** المنعُ
            # بالمفتاح كان يُجوِّع سؤالاً لاحقاً يشترك في مفتاحه: تركيا
            # طبعت الشهادةَ الإلزامية جواباً لسؤال الحاجز، ثمّ «لم نعرفه
            # بعد» لسؤال المواصفة — **فجوةٌ كاذبةٌ عن معلومٍ**، وهي أسوأُ من
            # التكرار (§58). فإن تكرّر النصُّ نفسُه يُنزَل إلى المفتاح
            # التالي، وإن لم يبقَ غيرُه **يُحذَف السؤالُ كلُّه** — سؤالٌ
            # جوابُه مطبوعٌ أعلاه لا يضيف سطراً ولا يُنكِر معلوماً.
            if txt in said:
                duplicate = True
                dup_status = render_status(e, lang)
                continue
            duplicate = False
            said.add(txt)
            answer = txt
            status = render_status(e, lang)
            break
        answered = bool(answer)
        if not answered:
            if duplicate:
                # السؤالُ **مُجابٌ** ونصُّه مطبوعٌ أعلاه: لا يُحذَف (تسقط
                # مسألةُ الفئة التي سمّته) ولا يُعاد النصُّ (الدرس ٢٦٤) ولا
                # يُقال «لم نعرفه بعد» (فجوةٌ كاذبةٌ عن معلوم) — يُحال.
                answer = ("answered above" if en else "مذكورٌ في جوابٍ أعلاه")
                status = dup_status
                answered = True
            else:
                answer = "not yet known" if en else "لم نعرفه بعد"
                status = "not available" if en else "غير متاح"
        out.append({"q_key": r["q_key"],
                    "question": r["question_en"] if en and r["question_en"]
                    else r["question_ar"],
                    "answer": answer, "status": status,
                    # سبيلُ الإغلاق يُطبَع للسؤال غير المُجاب وحدَه — وللمُجاب
                    # يبقى في الصفّ للمدقّق بلا عرض (لا حشوَ في نصّ العميل).
                    # سبيلُ الإغلاق بلغة التقرير: مُطهِّرُ نصّ العميل
                    # الإنجليزيّ يُسقِط النصَّ العربيّ، فكان القارئُ يرى
                    # «not yet known» بلا سبيلٍ إليه (§58).
                    "how": ((r.get("how_to_learn_en")
                             or r["how_to_learn_ar"]) if en
                            else r["how_to_learn_ar"]),
                    "answered": answered})
    return out
