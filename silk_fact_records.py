"""سجلّ الحقائق ودرجات المصادر — Fact Records & Source Tiers (محرك دراسة
السوق، القاعدتان ٢-٣، ٧).

**لا نثر بين الوكلاء.** كل وكيل يُصدر سجلّات بنيوية (`FactRecord`) لا
نصّاً سردياً؛ النثر يُولَّد مرّة واحدة عند طَور الكاتب فقط. الحقول
المحسوبة (`matches_charter`, `tier`, `verdict_eligible`,
`effective_confidence`) **لا تُصرَّح ذاتياً من الوكيل** — تُحسَب هنا حصراً،
وهذا ما يمنع التناقض الذي كانت عليه دراسة #9: منهجيةٌ تتبرّأ من كل رقم
Comtrade ثم يستخدمه الملخّص نفسُه لرفض السوق.

**طَور الطرح — الموجة ١ (SHADOW).** الدوالّ نقيّة (pure) ومُختبَرة هرمتياً،
**ومربوطة** باستخلاصٍ فعليّ من نتائج البعثات الحقيقية عبر المُطعِّم
(`build_fact_records_from_missions` أسفله) — الربط بالبيانات الحقيقية هو
مُسلَّم الموجة ١ نفسه، لا تأجيلٌ لموجةٍ لاحقة (SHADOW بلا بياناتٍ حقيقية لا
يقيس شيئاً، ولا يفتح بوّابة قياس أيّ موجة لاحقة). حدٌّ معلن: النطاق
(scope_hs_code) يُشتَقّ من ميثاق التشغيلة الواحد لا من كل نتيجة على حدة —
`DataPoint` لا يحمل حقل HS لكل سجلّ اليوم؛ التفصيل في توثيق `fact_record_
from_finding` أسفله.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: أوزان الدرجة — تُطبَّق حرفياً في `effective_confidence` (القاعدة ٧).
TIER_WEIGHTS = {"A": 1.0, "B": 0.8, "C": 0.4, "X": 0.0}

#: أهلية الحكم — درجة A فقط مؤهَّلة للحكم كاملاً؛ B «مساندة» (تُعرَض، لا
#: تُحسَب)؛ C وX غير مؤهَّلتين إطلاقاً (القاعدة ٣، الجدول).
VERDICT_ELIGIBLE_TIERS = frozenset({"A"})
SUPPORTING_TIERS = frozenset({"B"})

_TIER_A_MARKERS = (
    "comtrade", "un comtrade", "customs", "central bank", "world bank",
    "imf", "gazette", "official gazette", "wits",
    "كومتريد", "الجمارك", "بنك مركزي", "البنك الدولي", "صندوق النقد",
    "الجريدة الرسمية",
)
_TIER_B_MARKERS = (
    "industry report", "trade press", "registry", "commercial registry",
    "trade registry", "تقرير قطاعي", "الصحافة التجارية", "سجل تجاري",
    "سجل الشركات",
)
_TIER_C_MARKERS = (
    "web search", "social media", "بحث ويب", "منصات التواصل",
    "غير مؤرَّخ", "undated",
)
#: مصادرُ ذات مصلحة — رأيٌ مموَّل لا دليل سوق (جمعيةٌ/اتحادٌ يدافع عن موقفه).
_INTEREST_BEARING_MARKERS = (
    "association", "syndicate", "chamber of commerce", "lobby",
    "producers association", "trade union",
    "جمعية", "اتحاد", "غرفة تجارة", "نقابة",
)


def _has_marker(text: str, markers: tuple) -> bool:
    low = (text or "").lower()
    return any(m in low for m in markers)


def classify_tier(source_name: str, note: str = "", *,
                  interest_bearing: bool | None = None) -> str:
    """يصنّف مصدراً إلى درجة A/B/C/X (القاعدة ٣).

    `interest_bearing=True` صريح — أو اسم/ملاحظة المصدر يطابق قائمة
    الجهات ذاتة المصلحة — يفرض X بصرف النظر عن أيّ تشابهٍ آخر (جمعيةٌ
    تنشر «تقريراً قطاعياً» تبقى X لا B — القاعدة ٣: «موقفٌ ترويجي لا
    دليل سوق»). الافتراض عند غياب أيّ إشارة هو C — لا نمنح A/B ثقةً
    افتراضية لمصدرٍ غير معروف."""
    combined = f"{source_name or ''} {note or ''}"
    if interest_bearing is True or _has_marker(combined, _INTEREST_BEARING_MARKERS):
        return "X"
    if _has_marker(combined, _TIER_A_MARKERS):
        return "A"
    if _has_marker(combined, _TIER_B_MARKERS):
        return "B"
    if _has_marker(combined, _TIER_C_MARKERS):
        return "C"
    return "C"


def effective_confidence(agent_confidence: float, charter_confidence: float,
                         tier: str, biased: bool = False) -> float:
    """effective = agent_conf × charter_conf × tier_weight × (0.5 إن مُتحيّز)
    (القاعدة ٧ حرفياً)."""
    weight = TIER_WEIGHTS.get(tier, 0.0)
    value = float(agent_confidence) * float(charter_confidence) * weight
    if biased:
        value *= 0.5
    return round(value, 4)


def report_confidence(pillar_confidences: dict) -> float | None:
    """ثقة التقرير = **أدنى** قيمة بين الأعمدة (لا متوسّط) — القاعدة ٧:
    «رمز HS ضعيف يُسقِط كل ما بعده تلقائياً». عمودٌ بثقة صفرية يُسقِط
    التقرير كلَّه إلى صفر، تماماً كما تُسقِط ثقةُ الميثاق كلَّ سجلّ لاحق
    عبر `effective_confidence`. `None` حين لا عمود واحداً محسوباً (فجوة
    معلنة، لا صفر مختلَق)."""
    values = [v for v in pillar_confidences.values() if v is not None]
    if not values:
        return None
    return round(min(values), 4)


def matches_charter(record_hs_code: str | None, charter_hs_code: str | None) -> bool:
    """هل يطابق نطاقُ السجلّ رمزَ الميثاق المجمَّد؟ مطابقةٌ صارمة — أيّ
    اختلاف (حتى لاحقة/بادئة) يُسقِط `matches_charter` بدل تخمين تسامح."""
    if not record_hs_code or not charter_hs_code:
        return False
    return str(record_hs_code).strip() == str(charter_hs_code).strip()


def flags_growth_without_base(claim: str, has_base_volume: bool) -> str | None:
    """لا نمو% بلا حجمٍ مطلق أساسيّ (القاعدة ٣)."""
    text = (claim or "").lower()
    growth_markers = ("%", "growth", "نمو", "زيادة", "ارتفاع", "نسبة")
    if any(m in text for m in growth_markers) and not has_base_volume:
        return "UNVERIFIED_GROWTH_NO_BASE"
    return None


def flags_regulation_without_number(claim: str, has_regulation_number: bool) -> str | None:
    """لا تنظيمٍ بلا رقم قرار/معيار (القاعدة ٣)."""
    text = (claim or "").lower()
    reg_markers = ("regulation", "law", "decree", "standard", "لائحة",
                  "نظام", "قرار", "معيار", "تشريع")
    if any(m in text for m in reg_markers) and not has_regulation_number:
        return "UNVERIFIED"
    return None


def flags_named_partner_without_registry(has_partner_name: bool,
                                         has_registry_source: bool) -> str | None:
    """لا شريكٍ مُسمّى بلا تسجيلٍ رسمي (القاعدة ٣)."""
    if has_partner_name and not has_registry_source:
        return "UNVERIFIED_LEADS"
    return None


@dataclass
class FactRecord:
    """سجلّ حقيقة بنيوي — الشكل الوحيد الذي يتنقّل بين الوكلاء (القاعدة ٢)."""

    claim: str
    value: object
    unit: str | None
    source_name: str
    source_date: str | None
    scope_hs_code: str | None
    agent_confidence: float
    charter_hs_code: str | None = None
    charter_confidence: float = 1.0
    bias_flag: bool = False
    depends_on: list = field(default_factory=list)
    tier: str = field(init=False, default="")
    verdict_eligible: bool = field(init=False, default=False)
    effective_confidence_value: float = field(init=False, default=0.0)
    matches_charter_value: bool = field(init=False, default=False)

    def __post_init__(self):
        self.tier = classify_tier(self.source_name)
        self.matches_charter_value = matches_charter(
            self.scope_hs_code, self.charter_hs_code)
        # درجةٌ مؤهَّلة للحكم لا تكفي وحدها — سجلٌّ خارج نطاق الميثاق
        # المجمَّد (رمزُ HS مختلف) غيرُ مؤهَّلٍ مهما كانت درجةُ مصدره
        # (نفسُ العائلة التي منعها `effective_confidence`: لا يُقاس رقمٌ
        # خارج النطاق كدليلٍ للحكم مهما بلغت درجةُ مصدره).
        self.verdict_eligible = (self.tier in VERDICT_ELIGIBLE_TIERS
                                 and self.matches_charter_value)
        base_charter_conf = self.charter_confidence if self.matches_charter_value else 0.0
        self.effective_confidence_value = effective_confidence(
            self.agent_confidence, base_charter_conf, self.tier, self.bias_flag)

    def to_dict(self) -> dict:
        """الشكلُ التعاقديّ من القاعدة ٢ حرفياً — حقولٌ محسوبة
        (`matches_charter`, `tier`, `verdict_eligible`, `effective_
        confidence`) لا تُقرَأ من الوكيل، بل من `__post_init__` أعلاه."""
        return {
            "claim": self.claim,
            "value": self.value,
            "unit": self.unit,
            "source": {"name": self.source_name, "tier": self.tier,
                      "date": self.source_date},
            "scope": {"hs_code": self.scope_hs_code,
                     "matches_charter": self.matches_charter_value,
                     "excluded_attributes": []},
            "bias_flag": self.bias_flag,
            "agent_confidence": self.agent_confidence,
            "effective_confidence": self.effective_confidence_value,
            "verdict_eligible": self.verdict_eligible,
            "depends_on": list(self.depends_on),
        }


# ── المُطعِّم — adapter: من نتائج البعثات الحقيقية إلى سجلّات حقائق ──────────
# هذا هو مُسلَّم الموجة ١ الفعليّ (تصحيح مسار — لا تأجيل): بلا ربطٍ بنتائج
# حقيقية، SHADOW لا يقيس شيئاً ولا يفتح بوّابة أيّ موجة لاحقة. المُطعِّم
# يقرأ الشكل المُطبَّع لأيّ نتيجة بعثة (dict: value/source/confidence/note/
# retrieved_at/unit — نفس شكل `silk_render._dp()`، وهو نفسُه شكل التخزين
# الفعليّ) فلا حاجة لاستيراد silk_render (يتفادى دورة استيراد؛ الاتجاه
# الصحيح: العرض يستهلك هذا الملف مستقبلاً، لا العكس).

def _normalize_finding(finding: object) -> dict:
    """يطبّع نتيجة بعثة (dict مُطبَّع أصلاً، أو كائن DataPoint حيّ) إلى dict
    موحّد — بلا استيراد silk_render (تفادي دورة استيراد)."""
    if isinstance(finding, dict):
        return finding
    return {"value": getattr(finding, "value", None),
           "source": getattr(finding, "source", ""),
           "confidence": getattr(finding, "confidence", 0.0),
           "note": getattr(finding, "note", ""),
           "retrieved_at": getattr(finding, "retrieved_at", ""),
           "unit": getattr(finding, "unit", "")}


def fact_record_from_finding(finding: object, mission_key: str,
                             charter=None) -> tuple:
    """يبني `FactRecord` من نتيجة بعثة حقيقية واحدة. لا استثناء يُرفَع
    أبداً — فشلُ التحويل تخطٍّ معلن (`(None, سبب)`) لا كسر تشغيلة حقيقية.

    **حدٌّ معلن (لا تعمية):** `DataPoint`/شكل التخزين الحالي لا يحمل حقل
    HS لكل نتيجة على حدة — النطاق الوحيد المتاح اليوم هو رمز الميثاق
    الواحد للتشغيلة كلها. فـ`scope_hs_code` هنا يُشتَقّ من ميثاق التشغيلة
    (`charter.hs_code`) لكل السجلّات، لا من النتيجة نفسها؛ لذا `matches_
    charter` لكل سجلّ سيكون `True` دوماً ما دام الميثاق نفسه غير متوقِّف —
    اكتشاف عدم تطابق HS **على مستوى نتيجة واحدة** غير ممكن بالبنية
    الحالية؛ الإشارة الحقيقية اليوم هي **الميثاق نفسه على مستوى الدراسة**
    (`build_charter(...).halted`)، لا مقياس «معدّل عدم تطابق» لكل نتيجة."""
    try:
        f = _normalize_finding(finding)
        note = str(f.get("note") or "").strip()
        source_name = str(f.get("source") or "").strip()
        value = f.get("value")
        if not note and value is None:
            return None, "لا نصّ ادّعاء ولا قيمة — لا شيء يُسجَّل"
        if not source_name:
            return None, "لا اسم مصدر — يتعذّر تصنيف الدرجة"
        # الميثاق يصل إمّا كائن `Charter` حيّاً (Wave 1، اختبارات/أداة
        # التحقّق) أو dict مُخزَّناً (`Charter.to_dict()` عبر تخزين/API —
        # الشكل الذي يستهلكه وكيل الامتناع Wave 3 من `research_run.get(
        # "charter")`). كلاهما مدعومٌ صراحةً — لا افتراض شكلٍ واحد.
        if isinstance(charter, dict):
            charter_hs = charter.get("hs_code")
            charter_conf = charter.get("charter_confidence", 1.0)
        else:
            charter_hs = getattr(charter, "hs_code", None) if charter else None
            charter_conf = (getattr(charter, "charter_confidence", 1.0)
                            if charter else 1.0)
        rec = FactRecord(
            claim=note or f"[{mission_key}] بلا نصّ ادّعاء — قيمة فقط",
            value=value, unit=f.get("unit") or None,
            source_name=source_name,
            source_date=(f.get("retrieved_at") or None),
            scope_hs_code=charter_hs,
            agent_confidence=float(f.get("confidence") or 0.0),
            charter_hs_code=charter_hs, charter_confidence=charter_conf)
        return rec, None
    except Exception as exc:               # حصنٌ أخير — تخطٍّ لا كسر
        return None, f"استثناء تحويل غير متوقَّع: {exc!r}"


def build_fact_records_from_missions(missions: dict, charter=None) -> dict:
    """يبني سجلّات الحقائق من نتائج بعثاتٍ حقيقية (SHADOW — قراءة فقط، صفر
    أثر على النتيجة/الحكم). `missions`: dict[مفتاح البعثة -> كائن/dict يحمل
    `findings`] — يقبل شكل `AgentReport` الحيّ (`.findings`) أو dict مُخزَّن
    (`{"findings": [...]}`) بلا تمييز.

    يعيد `{"records": [...], "stats": {total_findings, parsed, skipped,
    parse_rate, skipped_reasons}}` — معدّل التحويل (`parse_rate`) هو المقياس
    المطلوب لإثبات أن المُطعِّم يعمل فعلياً على بيانات حقيقية، لا فقط على
    بيانات اصطناعية مثالية."""
    records: list = []
    skipped: list = []
    total = 0
    for mission_key, mission in (missions or {}).items():
        if isinstance(mission, dict):
            findings = mission.get("findings")
            failed = bool(mission.get("failed"))
        else:
            findings = getattr(mission, "findings", None)
            failed = bool(getattr(mission, "failed", False))
        for f in (findings or []):
            total += 1
            # مراجعة الشيفرة (code-review): بعثةٌ فاشلة تضع سببَ الفشل داخل
            # DataPoint وحيدة (`BaseAgent.run`) — ادّعاءٌ لا يُستخرَج من ملاحظة
            # فشلٍ داخلية (استثناء/مهلة) مهما بدت شكلاً صالحاً، وإلا صار خطأٌ
            # تشغيليّ خام «حقيقةً» بمصدر ودرجةٍ محسوبَين، ومعدّل التحويل نفسُه
            # يُصبح كاذباً (بعثةٌ فاشلة تُعَدّ نجاحاً في التحويل).
            if failed:
                skipped.append({"mission": mission_key,
                               "reason": "بعثةٌ فاشلة — لا يُستخرَج ادّعاء من ملاحظة الفشل"})
                continue
            rec, reason = fact_record_from_finding(f, mission_key, charter)
            if rec is not None:
                records.append(rec)
            else:
                skipped.append({"mission": mission_key, "reason": reason})
    parsed = len(records)
    return {
        "records": [r.to_dict() for r in records],
        "stats": {
            "total_findings": total, "parsed": parsed,
            "skipped": len(skipped),
            "parse_rate": round(parsed / total, 4) if total else None,
            "skipped_reasons": skipped,
        },
    }
