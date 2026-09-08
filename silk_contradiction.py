"""وكيل التناقض — Contradiction Agent (محرك دراسة السوق، القاعدة ٤).

يُشغَّل بعد كل الوكلاء وقبل الحكم. فرعان:

**أ) التعارضات** — فجوةُ مرآةٍ (export مقابل import) أكبر من ٢× تفرض
فرضيةً أولى **إلزامية**: عدم تطابق نطاق HS، لا التقصير الجمركي — لأن
تضييق نطاق الرمز (وكيل الميثاق) أكثر شيوعاً وأرخص تحققاً من اتهام
مصلحة جمارك بأكملها بالتقصير. يجوز أن يرفع تحدّياً ضد الميثاق (سقفٌ ٣
دورات، القاعدة ١٠).

**ب) التوليف** — استبصاراتٌ تحتاج وكيلين مندمجين، لا وكيلاً واحداً:
- **قاعدة العلاوة السعرية**: علاوةُ تجزئةٍ مستدامة لعلامةٍ مستوردة تعني
  سوقاً **متمايزاً**، لا **مغلقاً** (مثال مرجعي: علاوة ~٥٠٪ لم تُحلَّل قط).
- **الاتجاهات الواعية بالمنشأ**: استعلامٌ صاعد يقابل علامةً من بلد
  التصدير إشارةُ **فرصة**، لا ضجيج (يثبت أن الممرّ يعمل فعلاً).

صفرُ نداءات خارجية — يبني حصراً من نتائج الوكلاء في الذاكرة (مطابقةً
لقاعدة `correlation.py`؛ الاختبار الهيكلي في `tests/` يفرض ذلك)."""
from __future__ import annotations

from dataclasses import dataclass

#: عتبةُ فجوة المرآة — فوقها الفرضيةُ الأولى إلزامياً «عدم تطابق نطاق HS».
MIRROR_GAP_RATIO_THRESHOLD = 2.0
#: سقفُ دورات التحدّي ضد الميثاق (القاعدة ١٠).
MAX_CHALLENGE_CYCLES = 3
#: عتبةُ إشارة العلاوة السعرية — علاوةٌ دون هذا لا تُعَدّ «مستدامة».
PREMIUM_SIGNAL_THRESHOLD = 0.15


def detect_mirror_gap(export_value: float | None, import_value: float | None,
                      cycle: int = 0) -> dict | None:
    """فجوةُ مرآة > ٢× ⇒ فرضيةٌ أولى إلزامية: عدم تطابق نطاق HS.

    `cycle` عدّاد دورات التحدّي الحالي — يرفض المتابعة فوق السقف بدل
    الدوران إلى ما لا نهاية (القاعدة ١٠)."""
    if export_value is None or import_value is None:
        return None
    if export_value <= 0 or import_value <= 0:
        return None
    ratio = max(export_value, import_value) / min(export_value, import_value)
    if ratio <= MIRROR_GAP_RATIO_THRESHOLD:
        return None
    if cycle >= MAX_CHALLENGE_CYCLES:
        return {
            "conflict": True, "ratio": round(ratio, 2),
            "hypothesis": "hs_scope_mismatch",
            "challenge_exhausted": True,
            "note": f"فجوةُ مرآة {ratio:.1f}× تجاوزت سقفَ {MAX_CHALLENGE_CYCLES}"
                    " دورات تحدٍّ — تُعلَن فجوةً غير محسومة، لا مزيدَ من"
                    " إعادة تشغيل الميثاق",
        }
    return {
        "conflict": True, "ratio": round(ratio, 2),
        "hypothesis": "hs_scope_mismatch",
        "challenge_exhausted": False,
        "note": f"فجوةُ مرآة {ratio:.1f}× (export={export_value}، "
                f"import={import_value}) — الفرضيةُ الأولى الإلزامية: عدم "
                "تطابق نطاق HS (وكيل الميثاق)، لا تقصيرٌ جمركيّ",
    }


def import_premium_synthesis(imported_price: float | None,
                             local_price: float | None,
                             imported_brand: str | None = None) -> dict | None:
    """علاوةُ تجزئةٍ مستدامة لعلامةٍ مستوردة ⇒ سوقٌ متمايز لا مغلق."""
    if not imported_price or not local_price or local_price <= 0:
        return None
    premium = (imported_price / local_price) - 1.0
    if premium < PREMIUM_SIGNAL_THRESHOLD:
        return None
    who = imported_brand or "العلامة المستوردة"
    return {
        "kind": "import_premium", "premium_pct": round(premium * 100, 1),
        "imported_price": imported_price, "local_price": local_price,
        "signal": "differentiated_not_closed",
        "note": f"{who} تبيع بعلاوة {premium * 100:.0f}٪ فوق السعر المحلي "
                f"({imported_price} مقابل {local_price}) — السوقُ متمايزٌ "
                "بالجودة/العلامة، لا مغلقٌ أمام مستورد جديد",
    }


def origin_aware_trend_synthesis(trend_findings: list,
                                 exporting_country_iso3: str) -> list:
    """استعلامٌ صاعدٌ يقابل علامةً من بلد التصدير ⇒ إشارةُ فرصة.

    `trend_findings`: قائمة dict بالحقول `{query, rising, brand_origin_iso3}`
    — بياناتٌ من الوكلاء فعلاً، لا تخمين علامة/بلد هنا (القاعدة: لا
    ترميزٍ صلبٍ لأسماء منتجات/علامات — عائلة hardcoded-product-rule)."""
    signals = []
    for f in trend_findings or []:
        if not f.get("rising"):
            continue
        origin = f.get("brand_origin_iso3")
        if origin and origin.upper() == (exporting_country_iso3 or "").upper():
            signals.append({
                "kind": "origin_aware_trend", "query": f.get("query"),
                "brand_origin_iso3": origin, "signal": "opportunity",
                "note": f"استعلامٌ صاعد «{f.get('query')}» يقابل علامةً من "
                        f"{origin} — إثباتٌ أن الممرّ التصديريّ يعمل فعلاً، "
                        "لا ضجيجاً عابراً",
            })
    return signals


@dataclass
class ContradictionReport:
    conflicts: list
    synthesis_records: list
    strongest_counter_argument: str | None = None

    def to_dict(self) -> dict:
        return {
            "conflicts": self.conflicts,
            "synthesis_records": self.synthesis_records,
            "strongest_counter_argument": self.strongest_counter_argument,
        }


def build_contradiction_report(
        *, export_value: float | None = None, import_value: float | None = None,
        cycle: int = 0, imported_price: float | None = None,
        local_price: float | None = None, imported_brand: str | None = None,
        trend_findings: list | None = None,
        exporting_country_iso3: str = "SAU") -> ContradictionReport:
    """يجمع فرعَي الوكيل (تعارضات + توليف) في تقريرٍ واحد. كل معامل
    اختياري ومصدره نتائج الوكلاء في الذاكرة فقط — صفر نداء خارجي."""
    conflicts = []
    gap = detect_mirror_gap(export_value, import_value, cycle=cycle)
    if gap:
        conflicts.append(gap)

    synthesis = []
    premium = import_premium_synthesis(imported_price, local_price, imported_brand)
    if premium:
        synthesis.append(premium)
    synthesis.extend(origin_aware_trend_synthesis(
        trend_findings or [], exporting_country_iso3))

    counter = None
    if conflicts:
        counter = conflicts[0]["note"]
    elif synthesis:
        counter = synthesis[0]["note"]

    return ContradictionReport(conflicts=conflicts, synthesis_records=synthesis,
                               strongest_counter_argument=counter)
