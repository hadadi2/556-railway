"""القالب الموحّد لسِلك — Silk unified render template (wave 4, vision §10.1).

قالب واحد «أصل» والباقي مشتقات: `build_view()` يبني نموذج العرض القانوني
الوحيد من نتيجة المحرّك، وكل المخرجات تشتق منه:
  - اللوحة (الواجهة تستهلك `result["view"]` من الـ API)
  - نص الطرفية (`render_text` — يحل محل جسد format_result القديم)
  - أداة المطوّر Streamlit (`tools/dev_console.py` تقرأ الجدول من النموذج نفسه)
  - سطور المختصر (`view["brief"]` — القرار + الموقع التنافسي بسطرين)

المبرر (vision §10.1): خلل «التحليل الأجوف» كان خلل ربط عرض — مسارات
عرض منفصلة = فرص متعددة لنفس الخطأ؛ مسار مشترك = الخطأ يقع مرة ويُصلح مرة.

منطق عرض صرف: صفر شبكة، صفر تعديل على الأرقام — قراءة وتشكيل فقط.
"""
from __future__ import annotations

import json
import logging
import os
import re

log = logging.getLogger(__name__)


def _dp(obj: object) -> dict:
    """طبّع DataPoint/dict — normalize a DataPoint or dict to a plain dict."""
    if isinstance(obj, dict):
        return obj
    return {"value": getattr(obj, "value", None),
            "source": getattr(obj, "source", ""),
            "confidence": getattr(obj, "confidence", 0.0),
            "note": getattr(obj, "note", ""),
            "retrieved_at": getattr(obj, "retrieved_at", ""),
            "status": getattr(obj, "status", ""),
            # الحقل البنيويّ لسنة البيانات (الدرس ٣٣) يُحفَظ في التطبيع كي
            # يقرأه silk_staleness.fact_year في طبقة العرض/التصدير.
            "data_year": getattr(obj, "data_year", None),
            # عقد المصدر (الموجة ١): الحقول الجديدة تمرّ في التطبيع نفسه.
            "unit": getattr(obj, "unit", ""),
            "url": getattr(obj, "url", ""),
            "reference_period": getattr(obj, "reference_period", ""),
            "retrieval_method": getattr(obj, "retrieval_method", ""),
            # HF1: قائمةُ المعرّفات الذرّية تُحفَظ في التطبيع كي يسطّحها بناءُ
            # المراجع/المنهجية فيُسنِد كلُّ مصدرٍ لرابطه (لا معرّفٌ مركّب).
            "source_ids": tuple(getattr(obj, "source_ids", ()) or ())}




def _decision(top: dict | None) -> dict:
    """القرار أولاً (vision §10.2) — verdict + confidence + one-line why."""
    if not top:
        return {"verdict": None, "confidence": None,
                "why": "لا أسواق مرتّبة — لا بيانات كافية"}
    # **الموجة D (D-04 + إكمال V-01):** لا شيءَ يُضاف هنا عمداً.
    #
    # المسارُ القانونيّ للقرار المحسوب يعيش في `build_view` (`:2364`): حين يحمل
    # الصفُّ `decision` بمخطّطٍ صالح (`schema` بلا `error`) يصير **الحكمَ الوحيد**
    # في التقرير كلِّه، وتتحوّل الجوريةُ إلى سطرِ كفايةِ بياناتٍ بلا كلمةِ حكم.
    # وهذا الفرعُ يبقى لـ`/analyze` وللصفوف التي لا قرارَ محسوباً لها.
    #
    # **وأضفتُ هنا فرعاً ثانياً ثمّ حذفتُه:** كان يصوغ القرارَ من `row["decision"]`
    # بنفسه — أي مسارَ عرضٍ ثانياً لنفس الحكم، وهو ما تحظره قاعدةُ «عرضٌ واحد».
    # والعلاجُ الصحيحُ أن يحمل الصفُّ العميق `decision` فيسلكَ المسارَ القائم.
    jury = top.get("jury") or {}
    ai = jury.get("ai") or {}
    # WP-1: الحكم المعروض من المرحلة الحتمية حصراً (authoritative_verdict) —
    # ai.verdict قراءة استشارية داخلية، لم يعد يتقدّم على الحكم الحتمي.
    from silk_narrative import authoritative_verdict
    verdict, confidence = authoritative_verdict(jury)
    # أسماء أصناف الوكلاء الداخلية (TradeFlowAgent...) لا تصل وجه المستخدم —
    # تُعرَّب في المصدر هنا كي يرث كل مستهلك (نص/docx/markdown) الترجمة
    # نفسها، بدل ترقيعها في مستهلك واحد فقط (كانت docx وحدها تُعرِّبها).
    # LESSONS 88 — القناة الواحدة: حدود السوق المرصودة (quality_flags) تدخل
    # السطر كما تدخله أسماء الوكلاء المنهارين؛ «لا شيء» لا تُقال إلا بصدق.
    _row_gaps = [_humanize_gap_note(f) for f in (top.get("quality_flags") or [])]
    gaps_ar = verification_gap_line(jury, _row_gaps)
    # **الموجة Z (اختبارٌ عدائيّ).** صفٌّ بلا جوريةٍ وبلا قرارِ محرّكٍ صالح كان
    # يُنتِج «تغطية الوكلاء 0/0 وفجوات: **لا شيء**» — أي أنّ **صفرَ قياسٍ
    # يُعرَض طمأنينة**: «فحصنا فلم نجد فجوات» بينما لم يُفحَص شيءٌ أصلاً.
    # وهو بعينه ما يحظره تعليقُ هذه الدالّة نفسِه أعلاه («لا شيء» لا تُقال إلا
    # بصدق) — الحارسُ خالف قاعدتَه حين غاب مصدرُ الأرقام كلياً.
    #
    # يظهر حين يعطب محرّكُ القرار أو يغيب عن الصفّ: حالةٌ نادرة، لكنّ مُخرَجها
    # **مطمئنٌّ** لا محايد، وهذا أسوأُ ما يكون عليه فشل.
    _dec = top.get("decision") or {}
    # (البند 2): قرارٌ ممتنع (`verdict=""` — أعمدة دون الحد الأدنى) ليس
    # مصدرَ حكمٍ صالحاً — يرتدّ السطر لقراءة الجورية/الغياب الصادق.
    _dec_usable = (bool(_dec.get("schema")) and not _dec.get("error")
                   and bool(_dec.get("verdict")))
    if not jury and not _dec_usable:
        why = ("لم يصدر حكمٌ لهذه الدراسة: محرّك القرار لم يُنتِج نتيجة، "
               "ولا سِجلَّ تغطيةٍ للوكلاء. هذا غيابُ قياسٍ لا نتيجةَ قياس")
    else:
        why = (ai.get("reasoning")
               or f"تغطية الوكلاء {jury.get('agents_with_data', 0)}/"
                  f"{jury.get('agents_total', 0)} وفجوات: {gaps_ar}")
    return {"verdict": verdict, "confidence": confidence,
            # دورة C4 (موجة حجب #12): القصّ الحرفي `[:280]` كان يبتر لاحقة
            # `_clip_words` المعلنة منتصفَ عبارةٍ بقوسٍ أعرج — نفس صنف
            # العيب الذي تلغيه القاعدة البنائية، طابقاً أعلى. قصٌّ معلَن.
            "why": _clip_words(why, 280), "market": top.get("country"),
            "stage": jury.get("synthesis_stage"),
            # سدّ تسريب (الطبقة ٦): تصنيف الشارة محسوب هنا — لوحة الويب
            # تستهلكه بدل حساب تصنيفها الخاص من الرمز الخام (نفس الإصلاح
            # المطبَّق على شارة البحث العميق).
            "tone": _verdict_tone(verdict)}


# ════════════════════════════════════════════════════════════════════════════
# الصنف ٧ (موجة عيوب التقرير) — قائمةُ شروطٍ واحدة · one open-conditions list
# ════════════════════════════════════════════════════════════════════════════
# بلاغُ المالك: «ثلاثةُ شروطٍ في الملخّص، واثنان في التوصيات، وثلاثةٌ في قسم
# إعادة التقييم».
#
# الجذرُ **مرصودٌ حرفياً**: `silk_decision.decide` يبني القائمةَ الواحدة
# (`silk_decision.py` — مفتاح `conditions`)، ثم تقرؤها خمسةُ سطوحٍ بأربعِ
# سلوكيّات: هذا الملفّ يقصّ `[:3]` في `format_result` و`[:4]` في
# `render_text`، و`decision_basis` **يُعيد بناءها من الأعمدة** ثم يقصّ
# `[:6]`، و`silk_reports` يعرضها كاملةً في موضعين. فالقارئُ الذي يقارن
# مستندَ العميل بمستند المشغّل بالطرفية يرى ثلاثةَ أعدادٍ وأسماءً مختلفة.
#
# **خلف رايةٍ مطفأةٍ افتراضياً** (`SILK_OPEN_CONDITIONS_SINGLE`): مطفأةً يحفظ
# كلُّ سطحٍ سقفَه القائم حرفياً؛ ومفعّلةً يقرأ الجميعُ من هذا المُعِدّ —
# قائمةٌ واحدة، وعددٌ واحدٌ هو **العددُ الكامل دائماً**، وأيُّ قصٍّ يُعلَن
# نصّاً («وشرطان آخران») فلا يُخفي العددَ الحقيقيّ.

CONFIDENCE_DISCIPLINE_FLAG = "SILK_CONFIDENCE_DISCIPLINE"


def _oldest_fact_year(result: object) -> "int | None":
    """أقدمُ سنةِ حقيقةٍ يستند إليها هذا العرض — من `silk_staleness.fact_year`
    وحدَه (المصدرُ البنيويّ القائم) لا من النثر. `None` حين لا سنةَ مرصودة."""
    try:
        from silk_staleness import fact_year
    except Exception:  # noqa: BLE001
        return None
    years: list = []
    dr = (result or {}).get("deep_research") or {} \
        if isinstance(result, dict) else {}
    for m in (dr.get("missions") or {}).values():
        findings = ((m.get("findings") if isinstance(m, dict)
                     else getattr(m, "findings", None)) or [])
        for f in findings:
            y = fact_year(f)
            if isinstance(y, int) and 1900 < y < 2200:
                years.append(y)
    return min(years) if years else None


def confidence_discipline() -> bool:
    """هل رايةُ الصنف ٨ مفعّلة؟ — سقفُ النطاق وعرضُ حساب الدرجة."""
    return os.environ.get(CONFIDENCE_DISCIPLINE_FLAG, "").strip().lower() in (
        "1", "true", "yes")


OPEN_CONDITIONS_FLAG = "SILK_OPEN_CONDITIONS_SINGLE"
OPEN_CONDITIONS_CAP = 6          # سقفُ العرض الموحَّد عند التفعيل


def open_conditions_single() -> bool:
    """هل رايةُ الصنف ٧ مفعّلة؟"""
    return os.environ.get(OPEN_CONDITIONS_FLAG, "").strip().lower() in (
        "1", "true", "yes")


# ── الموجة الرابعة (تقريرٌ تنفيذيّ) — ثلاثُ راياتٍ مستقلّة مطفأةٌ افتراضياً ──
#
# قرارُ المالك (٢٠٢٦-٠٩-١٧، بعد دراسة ماليزيا المحجوبة): أرقامُ القياس
# الداخليّ الأربعة (درجةُ ثقة الحكم، نسبةُ التحقّق، ثقةُ كلّ مكوّن، والدرجةُ
# الكلية من ١٠٠) «لا تفيد القارئ وتفتح بابَ التساؤل على أيّ أساسٍ بُنيت» —
# فتخرج من **نسخة العميل** وحدَها. المحرّكُ والبوّابةُ وسطحُ المشغّل يقرؤون
# كلَّ مفتاحٍ كما هو: **لا مفتاحَ يُحذَف ولا رقمَ يتغيّر** — المتغيّرُ الوحيد هو
# مَن يُعرَض له. وهذا بعينه الحلُّ الجذريّ للحجب الأزليّ (الدرس ٢٥٤): نصٌّ لا
# يحمل تسميةَ ثقةٍ لا يمكن أن يتناقض معها.
#
# ثلاثُ راياتٍ لا واحدة: أمرُ المالك القائم «إذا صار حجب رجّع الرايات» لا
# يعمل إلا بتفصيلٍ كهذا — تراجعٌ عن واحدةٍ لا يُسقِط البقيّة.
CLIENT_METRIC_PRIVACY_FLAG = "SILK_CLIENT_METRIC_PRIVACY"
IMPORTS_SPOTLIGHT_FLAG = "SILK_IMPORTS_SPOTLIGHT"
REPORT_CHARTS_FLAG = "SILK_REPORT_CHARTS"

# أرقامُ القياس التي تخرج من نسخة العميل عند التفعيل — **أسماءٌ دلالية** لا
# مفاتيحُ عرض: كلُّ سطحِ عميل (`web/platform.html`، docx العميل) يسأل «هل
# المقياسُ X مخفيّ؟» بدل أن يحفظ قائمةَ مفاتيحَ تتباعد عن مصدرها.
CLIENT_HIDDEN_METRICS: tuple = (
    "score",                  # الدرجةُ الكلية «64 من 100» وسطرُها
    "confidence",             # درجةُ ثقة الحكم تسميةً ونسبةً
    "verification",           # نسبةُ التحقّق من البيانات وقسمُ التغطية
    "component_confidence",   # عمودُ «كم تحقّقنا منه» لكلّ مكوّن
)


def _flag_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes",
                                                        "on")


def client_metric_privacy() -> bool:
    """هل تخرج أرقامُ القياس الداخليّ من نسخة العميل؟ — تُقرَأ عند النداء."""
    return _flag_on(CLIENT_METRIC_PRIVACY_FLAG)


def imports_spotlight() -> bool:
    """هل تتقدّم وارداتُ السوق (بسلسلتها وسنتها) إلى وجه التقرير؟"""
    return _flag_on(IMPORTS_SPOTLIGHT_FLAG)


def report_charts() -> bool:
    """هل يُصدِر العرضُ بياناتِ الرسوم البيانية (`deep_research.charts`)؟"""
    return _flag_on(REPORT_CHARTS_FLAG)


def open_conditions(ed: object, cap: "int | None" = None) -> dict:
    """الشروطُ المفتوحة **بعددها الكامل** — المصدرُ الواحد لكلّ سطح.

    يعيد `{"items", "count", "shown", "hidden", "more_note"}`:
    `count` هو العددُ الكامل **دائماً** (لا عددُ المعروض)، و`more_note` جملةُ
    إفصاحٍ عن المخفيّ أو `""`. مطفأةً: `cap` كما يمرّره المُنادي (سلوكُه
    القائم)؛ ومفعّلةً: سقفٌ واحدٌ موحَّد.
    """
    items = [str(c) for c in ((ed or {}).get("conditions") or [])
             if str(c).strip()] if isinstance(ed, dict) else []
    # الدرس ٢٦٢: **سقفُ عرضٍ واحد** لكل السطوح (كان 3/4/6/بلا سقف حسب
    # المُنادي، فيبدو عددُ الشروط مختلفاً في أقسامٍ من تقريرٍ واحد). العددُ
    # الكامل `count` كان صادقاً دوماً؛ المعروضُ هو ما تباعد. `cap` يبقى في
    # التوقيع لمُنادٍ يريد سقفاً أضيق صراحةً، ولا مُنادي إنتاجيّ يستعمله.
    limit = OPEN_CONDITIONS_CAP if cap is None or cap >= OPEN_CONDITIONS_CAP \
        else cap
    if open_conditions_single():
        limit = OPEN_CONDITIONS_CAP
    shown = items[:limit] if isinstance(limit, int) else list(items)
    hidden = len(items) - len(shown)
    note = ""
    if hidden > 0:
        note = (f"و{hidden} شرطٌ آخر" if hidden == 1
                else f"و{hidden} شروطٌ أخرى")
    return {"items": items, "count": len(items), "shown": shown,
            "hidden": hidden, "more_note": note}


def _score_arithmetic_line(arith: dict, lang: str = "ar") -> str:
    """حسابُ الدرجة في سطرٍ يقرؤه صاحبُ القرار — أو إعلانُ الامتناع.

    الصنف ٨: «الدرجة 65» بلا حسابٍ لا تُراجَع؛ و«الدرجة 65 = (0.25×0.80 +
    0.20×0.57) ÷ 0.45» تُراجَع بقلم. والامتناعُ يُقال بسببه لا يُترَك فراغاً.
    """
    import silk_i18n as _I
    terms = (arith or {}).get("terms") or []
    if (arith or {}).get("score") is None:
        reason = (arith or {}).get("withheld_reason") or ""
        return _I.t("score_arithmetic_withheld", lang, reason=reason)
    import silk_decision as _D
    parts = "، ".join(
        f"{_D.pillar_label(t['name'], lang)} {t['weight']:g}×"
        f"{t['strength']:g}" for t in terms)
    return _I.t("score_arithmetic_line", lang, parts=parts,
                wsum=f"{arith['weight_sum']:g}",
                score=round(float(arith["score"]) * 100))


def _requirements_safe(result: dict) -> list:
    try:
        from silk_requirements_agent import requirement_rows
        return requirement_rows(
            str((result.get("market") or {}).get("iso3") or ""),
            result.get("hs_code"))
    except Exception as e:  # noqa: BLE001 — مرجعٌ مساعد لا شرطُ عرض
        # لا غيابَ صامت (مراجعة §58): يُسجَّل، ويُعلَن صفَّ فجوة.
        log.warning("requirement_rows failed: %s", e)
        return [{"item": "تعذّرت قراءة مرجع الاشتراطات — تحقق محلياً قبل "
                         "الشحن", "authority": "", "source_url": "",
                 "direction": "entry", "status": "", "gap": True,
                 "conditional_on_gate": False, "applies_when": ""}]


def entry_channel(by_category: object) -> "dict | None":
    """`{primary, alternative, source, status}` من `entry_door` — أو None.

    القيمةُ نصُّ المحلل كما هو (لا تُؤلَّف قناة)، والمصدرُ مصدرُ الاكتشاف؛
    والحالةُ «candidate» دائماً: ترتيبُ المحلل مؤشرٌ لا إثباتُ قناة.
    """
    from silk_narrative import EVIDENCE_SECONDARY_MIN

    def _txt(d):
        if isinstance(d, dict):
            return str(d.get("value") or d.get("claim") or "").strip()
        return str(getattr(d, "value", "") or "").strip()

    def _conf(d):
        c = d.get("confidence") if isinstance(d, dict) \
            else getattr(d, "confidence", None)
        try:
            return float(c)
        except (TypeError, ValueError):
            return None
    doors, seen = [], set()
    for d in ((by_category or {}).get("entry_door") or []):
        t = _txt(d)
        c = _conf(d)
        # مراجعة §58: بابٌ دون عتبة الدليل الثانويّ يُعلَن للعميل «غير متحقق»
        # في قسمٍ آخر — لا يصير القناةَ الأولى هنا؛ والمكرّرُ لا يصير بديلاً.
        if not t or t in seen or (c is not None and c < EVIDENCE_SECONDARY_MIN):
            continue
        seen.add(t)
        doors.append(d)
    if not doors:
        return None
    first = doors[0]
    src = (first.get("source") if isinstance(first, dict)
           else getattr(first, "source", "")) or ""
    return {"primary": _txt(first),
            "alternative": _txt(doors[1]) if len(doors) > 1 else "",
            "source": str(src), "status": "candidate"}


def condition_texts(ed: object, lang: str = "ar") -> "list | None":
    """صفوفُ الشروط المفتوحة بلغة القارئ — `[{id, text, closure}]` — أو None.

    تقرير ٧ §4.1: **قائمةٌ واحدة** يُشتقّ منها العددُ والصياغةُ في أساس الحكم
    وموجّه الكاتب معاً (كان الأساسُ يعيد بناءها من الأعمدة، والكاتبُ لا يراها
    فيؤلّف شروطَه وعددَها). None للنتائج المخزَّنة قبل `condition_items`
    فيبقى مسارُ إعادة البناء القائم لها.
    """
    import silk_i18n as _I
    import silk_decision as _D
    items = (ed or {}).get("condition_items") if isinstance(ed, dict) else None
    if not isinstance(items, list) or not items:
        return None
    rows: list = []
    for it in items:
        if not isinstance(it, dict):
            continue
        kind = it.get("kind")
        label = _D.pillar_label(it.get("pillar") or "", lang)
        if kind == "eligibility_gate":
            text = _I.t("cond_eligibility_gate", lang)
            closure = _I.t("cond_closure_gate", lang)
        elif kind == "pillar_missing":
            parts = _D.part_labels(it.get("missing"), lang)
            text = _I.t("cond_pillar_missing", lang, pillar=label, parts=parts)
            closure = _I.t("cond_closure_missing", lang, parts=parts)
        elif kind == "pillar_weak":
            text = _I.t("cond_pillar_weak", lang, pillar=label,
                        pct=it.get("pct"))
            closure = _I.t("cond_closure_weak", lang, pillar=label)
        else:
            continue
        cid = str(it.get("id") or f"C{len(rows) + 1}")
        num = cid[1:] if cid[:1] == "C" and cid[1:].isdigit() \
            else str(len(rows) + 1)
        # الرقمُ المعروضُ هو رقمُ المعرّف نفسُه — ما يكتبه الكاتبُ في الخطة
        # («← الشرط 3») يقع على شرطٍ مرئيٍّ بالرقم ذاته (مراجعة §58).
        rows.append({"id": cid, "text": text, "closure": closure,
                     "label": _I.t("cond_numbered", lang, n=num, text=text)})
    return rows


def _items_from_pillars(pillars: dict) -> list:
    """احتياطٌ للنتائج المخزَّنة قبل `condition_items`: القائمةُ المهيكلة
    نفسُها تُبنى من الأعمدة — فتمرّ الصياغةُ بمسارٍ واحد (`condition_texts`)."""
    import silk_decision as _D
    items: list = []
    if (pillars.get("regulatory") or {}).get("eligibility_gate"):
        items.append({"kind": "eligibility_gate", "pillar": "regulatory"})
    for name, p in pillars.items():
        strength = _D.pillar_strength(name, (p or {}).get("value"))
        if strength is None:
            items.append({"kind": "pillar_missing", "pillar": name,
                          "missing": list((p or {}).get("missing") or [])})
        elif strength < 0.5:
            items.append({"kind": "pillar_weak", "pillar": name,
                          "pct": round(strength * 100)})
    for n, it in enumerate(items, 1):
        it["id"] = f"C{n}"
    return items


def decision_basis(ed: dict, displayed_confidence: object = None,
                   lang: str = "ar",
                   oldest_fact_year: object = None) -> "dict | None":
    """أساسُ الحكم **جاهزاً للعرض** — بنيةٌ واحدة يستهلكها كلُّ سطحِ عميل.

    > **الموجة Z · البند Z-06.** الأعمدةُ الخمسة وقاعدتُها والحجّةُ المضادّة
    > تُحسَب في كلّ دراسة ولا يعرضها **أيُّ** سطحِ عميل: صفرُ ذكرٍ في docx
    > العميل وفي الـPDF وفي `web/platform.html`.
    >
    > وبناؤها هنا لا في كلّ عارضٍ على حدة **قصدٌ لا تنظيم**: أوّلُ علاجٍ
    > كتبتُه بنى الصفوفَ داخل `silk_reports` وحدَها، فكان سطحُ المصنع يحتاج
    > نسخةً ثانية بلغةٍ ثانية (JS) — وهو بعينه عطلُ «خريطتان تتباعدان» الذي
    > أضافت له هذه الموجةُ قفلاً. الآن: بانٍ واحد، ومستهلكون يعرضون.

    القيود المبنيّة هنا:

    * **الصمّام يُحترَم** — القاعدةُ والحجّةُ تحت `layer_enabled(
      "VERDICT_STRUCTURE")`، فإطفاؤه يُطفئهما على كلّ سطح.
    * **الثقةُ المعروضة هي المسقوفة** (`cap_confidence_for_flagged_hs`) لا
      ثقةُ المحرّك الخام — وإلّا ظهر رقمان في مستندٍ واحد.
    * **لا كسرٌ آليٌّ خام ولا معرّفٌ داخليّ** — نِسَبٌ بشرية وأسماءٌ من
      `silk_decision` (مصدرٌ واحد للتسمية في اللغتين).
    * الغيابُ يُعلَن ويقول ما ينقصه؛ ولا صفرَ مختلَق.
    """
    if not isinstance(ed, dict) or not ed.get("schema") or ed.get("error"):
        return None
    pillars = ed.get("pillars") or {}
    if not pillars:
        return None
    import silk_decision as _D
    import silk_i18n as _I

    def _t(key, **fmt):
        return _I.t(key, lang, **fmt)

    conf = displayed_confidence
    if not isinstance(conf, (int, float)):
        conf = ed.get("confidence")
    rows = []
    for name, p in pillars.items():
        strength = _D.pillar_strength(name, (p or {}).get("value"))
        label = _D.pillar_label(name, lang)
        parts = _D.part_labels((p or {}).get("missing"), lang)
        if strength is None:
            rows.append({"name": label, "strength_pct": None,
                         "note": _t("pillar_missing_lead", parts=parts)})
        else:
            pct = round(strength * 100)
            rows.append({"name": label, "strength_pct": pct,
                         # تقرير ٧ §4.3: الملاءمةُ التنظيمية تُشرح بما تقيسه
                         # — لا تعني ١٠٠٪ أنّ المصنع حاصلٌ على الموافقات.
                         "note": _t("pillar_regulatory_note"
                                    if name == "regulatory"
                                    else "pillar_measured")})
    # الصنف ٧: **العددُ والسقفُ يُوحَّدان، والصياغةُ تبقى صياغةَ القارئ.**
    #
    # جُرِّبت قراءةُ نصوصِ المحرّك مباشرةً وأُسقِطت بالقياس: سلاسلُ المحرّك
    # لغةُ قياسٍ داخلية («متوسط المتاح من: log10(TAM)/9…») بينما سطرُ
    # `cond_pillar_weak` صياغةُ قارئٍ («عالِجه قبل الالتزام…») — فكان
    # التفعيلُ **يُعيد** العيبَ الذي سدّه الصنف ١. والعيبُ المرصود لم يكن
    # إعادةَ البناء بل **انزياحَ العدد وصمتَ القصّ**: فيُعلَن العددُ الكامل
    # ويُوحَّد السقفُ ويُقال ما خُفي، والنصُّ كما هو.
    # تقرير ٧ §4.1: الشروطُ من قائمة المحرّك المهيكلة نفسِها حين تُوجد —
    # العددُ عددُ المحرّك حرفياً، والصياغةُ صياغةُ القارئ. إعادةُ البناء
    # من الأعمدة احتياطٌ للنتائج المخزَّنة قبلها.
    _rows = condition_texts(ed, lang)
    if _rows is None:
        _rows = condition_texts(
            {"condition_items": _items_from_pillars(pillars)}, lang) or []
    conds = [r["label"] for r in _rows]
    _oc = open_conditions(ed, OPEN_CONDITIONS_CAP)
    _cap = OPEN_CONDITIONS_CAP if open_conditions_single() else 6
    _shown_conds = conds[:_cap]
    _hidden = max(0, len(conds) - len(_shown_conds))
    if open_conditions_single() and _hidden:
        _shown_conds = _shown_conds + [
            (f"و{_hidden} شرطٌ آخر" if _hidden == 1
             else f"و{_hidden} شروطٌ أخرى") + f" (الإجمالي {len(conds)})"]
    out = {
        "head": _t("decision_basis_head"),
        "pillars": rows,
        "conditions_head": _t("decision_conditions_head"),
        "conditions": _shown_conds,
        # العددُ الكامل دائماً — سطحٌ يعرض ثلاثةً من ثمانيةٍ يقول ذلك.
        # يُقرأ من الصياغة المعروضة (هي ما يراه القارئ)، ويُطابِق عددَ
        # قائمة المحرّك في كلّ حالةٍ مقيسة (كلاهما من الأعمدة نفسِها).
        "conditions_count": len(conds),
        "engine_conditions_count": _oc["count"],
        # صفوفٌ بمعرّفٍ وخطوةِ استكمال — يربط بها الكاتبُ خطواتِ الـ٩٠ يوماً.
        "condition_rows": _rows or [],
        "col_pillar": _t("pillar_col"),
        "col_strength": _t("pillar_strength_col"),
        "col_note": _t("pillar_note_col"),
        "not_computed": _t("pillar_not_computed"),
        "score_pct": (round(float(ed["score"]) * 100)
                      if isinstance(ed.get("score"), (int, float)) else None),
        "confidence_pct": (round(float(conf) * 100)
                           if isinstance(conf, (int, float)) else None),
    }
    if out["score_pct"] is not None and out["confidence_pct"] is not None:
        out["score_line"] = _t("decision_weighted_line",
                               score=out["score_pct"],
                               conf=out["confidence_pct"])
    # الموجة الرابعة: القائمةُ **إضافيّة** — المفاتيحُ أعلاه تبقى كما هي
    # للمحرّك والبوّابة وسطح المشغّل؛ سطوحُ العميل تقرأ القائمةَ فتُسقِط
    # السطرَ/الخليةَ كاملاً (لا «—» ولا نسبةٌ عارية).
    if client_metric_privacy():
        out["client_hidden_metrics"] = list(CLIENT_HIDDEN_METRICS)
    # ── الصنف ٨ (موجة عيوب التقرير) — خلف رايةٍ مطفأةٍ افتراضياً ──────────
    # (أ) **سقفُ نطاق الثقة**: لا «عالية» عند عمودٍ أساسيٍّ مجهول أو شرطين
    #     مفتوحين. **الرقمُ لا يُمَسّ** — التسميةُ وحدها تُسقَّف، فلا قيمةَ
    #     مخزَّنة تتغيّر.
    # (ب) **حسابُ الدرجة معروضاً**: وزنٌ × قوّةٌ لكلّ عمودٍ محسوب، ومجموعُ
    #     الأوزان المُعاد تسويتها، والناتج — ومقفولٌ باختبارٍ أنّ الناتج
    #     يُطابِق `decide()["score"]` حرفياً في الحالتين (رقمٌ أو امتناعٌ
    #     مُعلَن). حسابٌ يخالف الدرجة يُوهِم القارئَ بالتحقّق.
    # (ج) **مقياسان لا واحد**: ثقةُ الحكم ≠ نسبةُ التحقّق من البيانات —
    #     البلاغُ أنّ الثانية عُرضت مكان الأولى.
    if confidence_discipline():
        _cap = _D.confidence_band_cap(pillars, ed.get("conditions"))
        if _cap:
            out["confidence_band_cap"] = _cap
            out["confidence_cap_reason"] = _t(
                "confidence_cap_core_missing",
                parts=_D.part_labels(
                    [_D.pillar_label(n, lang)
                     for n in _D.missing_core_pillars(pillars)], lang))
        if isinstance(out["confidence_pct"], (int, float)):
            from silk_style_contract import confidence_band_label
            out["confidence_band"] = confidence_band_label(
                out["confidence_pct"], lang, cap=_cap)
        # (د) **قِدَمُ البيانات يُقرَأ ولا يُمَسّ الرقم**. المراجعةُ الذاتية
        #     للفرق (البند ٥٨) كشفت أنّ `CONFIDENCE_AGE_DECAY` جدولٌ معلَنٌ
        #     **بلا قارئٍ في الإنتاج** — أي أنّ الصنفَ ٨ ادّعى تحلُّلاً لا
        #     يجري. الآن: يُعرَض الخصمُ سطراً مسمّىً من أقدم سنةٍ مرصودةٍ
        #     فعلاً، والثقةُ المخزَّنة كما هي (نمطُ سقفِ التسمية نفسِه).
        _oldest = oldest_fact_year
        if isinstance(_oldest, int) and _oldest > 1900:
            import datetime as _dt
            _age = max(0, _dt.date.today().year - int(_oldest))
            _keep = _D.age_decay_factor(_age)
            if _keep < 1.0:
                out["confidence_age_year"] = int(_oldest)
                out["confidence_age_years"] = _age
                out["confidence_age_haircut_pct"] = round(
                    (1.0 - _keep) * 100, 1)
                out["confidence_age_note"] = _t(
                    "confidence_age_haircut", year=int(_oldest), age=_age,
                    pct=out["confidence_age_haircut_pct"])
        _opt = ed.get("weights_option") or "A"
        _arith = _D.score_arithmetic(pillars,
                                     _D.WEIGHT_OPTIONS.get(_opt) or {})
        out["score_arithmetic"] = _arith
        out["score_arithmetic_line"] = _score_arithmetic_line(_arith, lang)
        # نسبةُ التحقّق مقياسٌ مسمّىً مستقلّ — لا تُقدَّم كثقةِ حكم.
        _cov = ed.get("coverage")
        if isinstance(_cov, (int, float)):
            out["verification_rate_pct"] = round(float(_cov) * 100)
            out["verification_rate_note"] = _t("verification_rate_note")
    # القاعدةُ والحجّة: مُصفّاتان بالصمّام — غيابُهما إطفاءٌ مقصود لا نقص.
    if layer_enabled("VERDICT_STRUCTURE"):
        if ed.get("decision_rule"):
            out["rule_line"] = _t("decision_rule_lead",
                                  go=round(_D._GO * 100),
                                  nogo=round(_D._NOGO * 100),
                                  conf=round(_D._MIN_CONF_GO * 100))
        cc = ed.get("counter_case") or {}
        txt = " ".join(x for x in (cc.get("case"), cc.get("rebuttal")) if x)
        # البند ٣ (لغة الزائر): نص «لماذا لم تُعتمد» يأتي من سرد المحرّك
        # بمصطلح القياس الداخلي — يُستبدل بالزوج القانوني الواحد قبل أي سطح.
        from silk_style_contract import CLIENT_TERM_REPLACEMENTS
        for _term, _repl in CLIENT_TERM_REPLACEMENTS:
            txt = txt.replace(_term, _repl)
        scored = [(r["name"], r["strength_pct"]) for r in rows
                  if r["strength_pct"] is not None]
        if txt and not _I.foreign_prose_spans(txt, lang):
            out["counter_case_head"] = _t("counter_case_head")
            out["counter_case_line"] = txt
        # (البند 2 + البند 8 من أمر إصلاح المحرّك): حجةٌ مضادة ممتنعة
        # (`skipped`) لا تُستبدل بسطرٍ محسوب يدّعي حكماً لم يصدر؛ والسطرُ
        # المحسوب يشترط عمودين مختلفين — «أقوى الأعمدة X وأضعفها X» نفسه
        # جملةٌ تناقض نفسها (تقرير #11 حرفياً).
        elif cc and not cc.get("skipped") and scored \
                and len({n for n, _ in scored}) >= 2:
            hi = max(scored, key=lambda t: t[1])
            lo = min(scored, key=lambda t: t[1])
            out["counter_case_head"] = _t("counter_case_head")
            out["counter_case_line"] = _t(
                "counter_case_computed", strong=hi[0], strong_pct=hi[1],
                weak=lo[0], weak_pct=lo[1])
    return out


def _competitive_position(top: dict | None) -> dict:
    """قسم "موقعك التنافسي" — the correlation section, or an honest absence."""
    cp = (top or {}).get("competitive_position")
    if not cp or "error" in (cp or {}):
        return {"available": False,
                # #13: «بطاقة منتجك (product_card)» لغة مدخلات نظام — يُطلب
                # المعطى نفسه بلغة الزائر (نفس سابقة تنقية الموجّه).
                "note": (cp or {}).get("error")
                or ("أدخل سعر المصنع بوحدة المنتج للمساعدة في تحديد "
                    "موقعك التنافسي")}
    feas = cp.get("feasibility_threads") or []
    best = max(feas, key=lambda f: f.get("margin_at_match_pct", -9e9),
               default=None)
    doors = (cp.get("entry_thread") or {}).get("doors") or []
    realistic = next((d for d in doors if str(d.get("assessment", ""))
                      .startswith("واقعية")), doors[0] if doors else None)
    return {
        "available": True,
        "market": (top or {}).get("country"),
        "coverage": cp.get("coverage"),
        "competitor_threads": cp.get("competitor_threads"),
        "feasibility_threads": feas,
        "entry_thread": cp.get("entry_thread"),
        "contacts_thread": cp.get("contacts_thread"),
        "nearest_beatable": best,
        "best_door": realistic,
        "note": cp.get("note"),
    }


def _brief(decision: dict, cp: dict, lang: str = "ar") -> list[str]:
    """المختصر — سطران للموقع التنافسي فوق سطر القرار (vision §6, §10.4).

    P1 (طبقة السرد): رمز الحكم الآلي (CONDITIONAL-GO) والكسر العشري الخام
    وأسماء أعلام الكود (with_localprice) لا تصل وجه المستخدم — تُترجم عبر
    silk_narrative. القيم نفسها بلا تغيير.

    صيد الفجوات ٣: كان عربياً صرفاً مهما كانت لغة التقرير — دراسةُ مصنعٍ
    إنجليزيّ كانت تفتتح بواجهة «التوصية: …» العربية (معامل عرضٍ بحت).
    """
    import silk_narrative as N
    ar = lang != "en"
    market = (N.country_ar(decision.get("market"), decision.get("market"))
              if ar else str(decision.get("market") or ""))
    label = N.verdict_ar(decision.get("verdict"))
    if not ar:
        tone = _verdict_tone(decision.get("verdict"))
        label = (_verdict_label(tone, "en")
                 if tone in _VERDICT_LABELS_AR else
                 str(decision.get("verdict") or ""))
    if client_metric_privacy():
        # الموجة الرابعة: المختصرُ سطحُ عميل (يُعرَض في نافذة المنصّة حين
        # لا نصَّ للكاتب) — التسميةُ والنسبةُ تخرجان منه.
        lines = [(f"التوصية: {label} — سوق {market}" if ar else
                  f"Recommendation: {label} — {market} market")]
    else:
        conf = N.confidence_phrase(decision.get("confidence"), lang)
        lines = [(f"التوصية: {label} — سوق {market} (ثقة {conf})" if ar else
                  f"Recommendation: {label} — {market} market "
                  f"(confidence {conf})")]
    if cp.get("available"):
        best = cp.get("nearest_beatable")
        if best:
            lines.append(
                f"أقرب منافس قابل للمنافسة: {best['competitor']} — هامشك عند "
                f"مضاهاته {best['margin_at_match_pct']}%" if ar else
                f"Nearest beatable competitor: {best['competitor']} — your "
                f"margin at price-match {best['margin_at_match_pct']}%")
        else:
            lines.append(
                "أسعار المنافسين على الرفّ لم تُجمع بعد — تتوافر مع الدراسة "
                "العميقة" if ar else
                "Competitor shelf prices not collected yet — available with "
                "the deep study")
        door = cp.get("best_door")
        if door:
            lines.append(
                f"أفضل باب دخول مرصود: {door['name']} ({door['assessment']})"
                if ar else
                f"Best observed entry door: {door['name']} "
                f"({door['assessment']})")
        else:
            lines.append(
                "قنوات الدخول التفصيلية تتوافر مع الدراسة العميقة" if ar else
                "Detailed entry channels are available with the deep study")
    else:
        lines.append(cp.get("note", ""))
    return lines


def _deep_research_brief(dr_view: dict, lang: str = "ar") -> list[str]:
    """مختصر البحث العميق — القرار + أرقام حاسمة + الموقع التنافسي (الموجة ٤).

    نفس فلسفة `_brief` (§10.4: سطر جوال) لكن على شكل view["deep_research"]
    (١٢ بعثة + محلل، لا قائمة أسواق مرتّبة)."""
    # ── الموجة Z · البند Z-02 — تسميةٌ واحدة، لا اشتقاقٌ ثانٍ ──────────
    # كان هذا السطرُ يُعيد اشتقاقَ التسمية من الحكم الخام
    # (`authoritative_verdict` ثم `verdict_ar`)، فيتخطّى `_coverage_basis_tone`
    # الذي أضافته الموجة B في موضعٍ واحدٍ فقط. النتيجةُ المُقاسة: نفسُ العرض
    # يحمل شارةً صادقة («اكتمل البحث — لم يصدر تقييمٌ تجاريّ بعد») ومختصراً
    # يقول «التوصية: توصية أولية بالدخول» — أي عدّادُ تغطيةٍ يُقدَّم توصيةً
    # تجارية من الباب الخلفيّ. الحقلُ المُصالَح `verdict_label` هو التسميةُ
    # الواحدة؛ الاشتقاقُ الخام يبقى احتياطاً لمدوّناتٍ مخزَّنة بلا الحقل.
    # التسميةُ من **التصنيف المُصالَح** لا من اشتقاقٍ ثانٍ — لكن بالعربية
    # صراحةً: هذا السطرُ جملةٌ عربيةٌ مبنيّة («التوصية: … — سوق … (بحث عميق
    # شامل)»)، وحقنُ تسميةٍ إنجليزية فيها يُنتِج سطراً نصفَ مترجَم على سطحِ
    # عميل (مراجعةٌ ذاتية §٥٨ التقطته: «التوصية: Conditional entry — سوق …»).
    _tone = str(dr_view.get("verdict_tone") or "")
    ar = lang != "en"   # صيد ٣: المختصر بلغة التقرير — كان عربياً دائماً
    v = _verdict_label(_tone, lang) if _tone in _VERDICT_LABELS_AR else ""
    if not v:
        from silk_narrative import authoritative_verdict, verdict_ar
        v_raw, _ = authoritative_verdict(dr_view.get("verdict") or {})
        if ar:
            v = verdict_ar(v_raw) if v_raw else "تعذّر إصدار توصية"
        else:
            v = str(v_raw) if v_raw else "No recommendation could be issued"
    mkt = dr_view.get("market") or {}
    market = ((mkt.get("name_ar") if ar else mkt.get("name_en"))
              or mkt.get("name_ar") or mkt.get("name_en") or "؟")
    # C9: «التوصية: بحثٌ ناقص» جملةٌ تناقض نفسَها — حالةُ الأدلة ليست توصية.
    # البادئةُ تتبع ما يقوله الحقلُ فعلاً، فيقرأ المصنعُ سطراً مستقيماً.
    if ar:
        _lead = "الحالة" if _tone.startswith("data_") else "التوصية"
        lines = [f"{_lead}: {v} — سوق {market} (بحث عميق شامل)"]
    else:
        _lead = "Status" if _tone.startswith("data_") else "Recommendation"
        lines = [f"{_lead}: {v} — {market} market (comprehensive deep "
                 "research)"]
    by_cat = (dr_view.get("analyst") or {}).get("by_category", {})
    # دورة C4 (صيد ٣): لاحقةُ المصدر أُسقطت عمداً من المختصر — حقلُ المصدر
    # ملاحظةُ بعثةٍ قد تحمل اسمَ مرجعٍ داخلي (demographics_l1.csv وقعت في
    # العينة فعلاً) أو نثراً بغير لغة التقرير؛ الإسنادُ الكامل في متن
    # التقرير وقسم المراجع، والمختصرُ سطرُ جوّالٍ.
    demand = by_cat.get("demand") or []
    if demand:
        lines.append((f"الطلب الفعلي المقدَّر: {demand[0].get('value')}"
                      if ar else
                      f"Estimated actual demand: {demand[0].get('value')}"))
    entry_door = by_cat.get("entry_door") or []
    if entry_door:
        lines.append((f"أفضل باب دخول: {entry_door[0].get('value')}"
                      if ar else
                      f"Best entry door: {entry_door[0].get('value')}"))
    if dr_view.get("next_step"):
        lines.append(dr_view["next_step"])
    return lines


def _completeness(markets: list) -> dict:
    """مؤشر اكتمال الدراسة — how much of the study is OBSERVED vs. declared gaps.

    يعدّ المكوّنات المرصودة (`value is not None`) عبر كل الأسواق ويعطي نسبة
    مئوية + تفصيلاً لكل مكوّن. لا يعدّل رقماً — قراءة فقط؛ يبني ثقة المستخدم
    بإظهار «كم% من الدراسة مرصود فعلاً» بدل إيحاء زائف بالاكتمال (المبدأ
    التأسيسي: الفجوات معلنة). Pure read-only; observed/total across markets.
    """
    total = observed = 0
    by_component: dict[str, dict] = {}
    for row in markets:
        for name, c in (row.get("components") or {}).items():
            present = _dp(c).get("value") is not None
            total += 1
            observed += 1 if present else 0
            b = by_component.setdefault(name, {"observed": 0, "total": 0})
            b["total"] += 1
            b["observed"] += 1 if present else 0
    pct = round(100.0 * observed / total, 1) if total else 0.0
    if pct >= 75:
        label = "دراسة شبه مكتملة — most components observed"
    elif pct >= 40:
        label = "دراسة جزئية — الفجوات معلنة، partial with declared gaps"
    else:
        label = "بيانات ضعيفة — thin data, gaps dominate"
    return {"observed": observed, "total": total, "pct": pct,
            "gap_count": total - observed, "by_component": by_component,
            "label": label}


def _fval(f: object) -> object:
    """قيمة نتيجة — .value whether DataPoint, dict, or a plain value."""
    if isinstance(f, dict):
        return f.get("value")
    return getattr(f, "value", f)


def _real_list(x: object) -> list:
    """قيم مرصودة فقط — real values from a DataPoint-or-list field ([] if none)."""
    if x is None:
        return []
    items = x if isinstance(x, list) else [x]
    out = []
    for f in items:
        v = _fval(f)
        if v is not None:
            out.append(v)
    return out


# Wave 3.1 (تدقيق زبدة الفول السوداني/اليمن — صفوف أسعار بلا وزن): سبب غياب
# السعر/كجم لكل صفّ يُصرَّح صراحةً (الوزن غير متاح / وحدة غامضة) بدل خانة فارغة،
# وسطر الفتح الوحيد «بطاقة منتج: التكلفة/كجم» يُذكَر مرة واحدة في قسم التسعير.
_PER_KG_RE = re.compile(
    r"(?:/|\bلكل\b|\bper\b)?\s*(?:كجم|كيلو|كغ|للكيلو|kg|كيلوغرام)"
    r"|(?:كجم|كيلو|كغ|kg)\s*/?\s*(?:€|\$|£|دولار|يورو)")
# الدرس ٢٧٣: كان البديلُ الأخير `\d` — فأيُّ رقمٍ «عملة»، و«12.5 للعبوة» يُوسَم
# «الوزن غير متاح» وهو بلا عملةٍ أصلاً. العملةُ الآن عملةٌ مسمّاة.
_CURRENCY_RE = re.compile(r"€|\$|£|دولار|يورو|ريال|درهم|(?<![A-Za-z])RM\s*\d")
_WEIGHT_RE = re.compile(
    r"\d+\s*(?:غ|جم|جرام|غرام|كجم|كيلو|كغ|kg|g|مل|لتر|ml|l|أونصة|oz)")

PRICE_UNLOCK_LINE = ("تتطلب المقارنة السعرية سعر المصنع وسعر المنافس بعملة "
                     "ووحدة متطابقتين، مع توثيق حجم العبوة وأي تحويل مستخدم.")


# #13 ص14 — سقالة استشهاد البعثة وصلت رفَّ أسعار العميل حرفياً: وسمٌ مقوّس
# عربي («[مرجع سوق]») لا يجرّده نمط الفئات الإنجليزي، وبادئة «مبني على:»
# (ملاحظة الاستشهاد من silk_llm_runtime)، ورمز داخلي («مرجع locale»)،
# وذيل «, USD» — كلها لغة نظام على مُسلَّم.
_PRICE_TAG_RE = re.compile(r"^\[[^\]\n]{1,40}\]\s*")
_HS_TOKEN_RE = re.compile(r"\bHS\s?(\d{4,6})\b")


def _clean_price_row_note(note: str) -> str:
    """ملاحظة صفّ سعرٍ صالحة لعين العميل — أو "" لصفّ مرجعٍ داخليّ خالص
    (يُسقِطه الباني). التنظيف عرضيّ خالص: لا تغيير رقمٍ ولا اختلاق."""
    s = _PRICE_TAG_RE.sub("", str(note or "").strip())
    if s.startswith("مبني على:"):
        s = s[len("مبني على:"):].strip()
    else:
        s = s.replace(" مبني على: ", " — ")
    if "locale" in s.lower():
        return ""      # مرجعُ نطاقِ سوقٍ داخليّ — ليس رصدَ سعرٍ يُعرَض
    s = _HS_TOKEN_RE.sub(r"البند \1", s)
    s = s.replace(", USD", " بالدولار").replace(",USD", " بالدولار")
    return s.strip()


def _hypotheses_safe(dr: dict) -> list:
    """فرضيات الاستدلال العابر للمهمات (البند ٦) — إثراء لا شرط: أي عطل
    يعيد قائمة فارغة ولا يُسقط العرض."""
    try:
        from silk_inference import derive_hypotheses
        return derive_hypotheses(dr or {})
    except Exception:  # noqa: BLE001
        return []


def _price_row_reason(text: object) -> str:
    """سبب تعذّر حساب السعر/كجم لصفّ سعر — «» إن كان قابلاً للحساب.

    - بلا رقمٍ أصلاً => «وحدة غامضة».
    - رقمٌ بلا عملةٍ مسمّاة => «العملة غير متاحة» (الدرس ٢٧٣ — حالةٌ مستقلة
      عن غياب الوزن، §3.3 من مراجعة التقرير ٧).
    - يحوي سعراً لكل كيلوغرام، أو سعراً ووزناً => «» (قابل للحساب/الاشتقاق).
    - سعرٌ بعملةٍ بلا وزن => «الوزن غير متاح». حتمي، لا اختلاق."""
    s = str(text or "").strip()
    if not s or not re.search(r"\d", s):
        return "وحدة غامضة"
    import silk_narrative as _N
    if not (_CURRENCY_RE.search(s) or _N.currency_in(s)):
        return "العملة غير متاحة"
    if _PER_KG_RE.search(s) or _WEIGHT_RE.search(s):
        return ""  # سعر/كجم مرصود مباشرة، أو سعر + وزن => قابل للاشتقاق
    return "الوزن غير متاح"


_LEADING_NUM_RE = re.compile(r"^\s*(?:€|\$|£|RM)?\s*\d")


def _is_price_row(value: object, note: object) -> bool:
    """هل هذا صفُّ سعرٍ فعلاً؟ (الدرس ٢٧١ — تقرير ٧)

    كان كلُّ صفٍّ بملاحظةٍ يُطبَع تحت «الأسعار المرصودة على الرف»: صفُّ
    استبعادِ منتجٍ مختلف (قيمتُه None)، ومعلومةُ حلال، وملاحظةُ بحث. يبقى
    الصفّ إن حمل قيمةً رقمية أو قاموسَ عرض، أو نصّاً يبدأ برقم (سعرٌ تنقصه
    العملة يبقى بحالته المعلنة «وحدة غامضة»)، أو سعراً ملتصقاً بعملة في
    القيمة أو الملاحظة. ما عدا ذلك يبقى في البيانات الخام ولا يُعرض سعراً.
    """
    import silk_economics as _E
    import silk_narrative as _N
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, dict)):
        return True
    text = f"{value if isinstance(value, str) else ''} {note or ''}"
    if isinstance(value, str) and _LEADING_NUM_RE.match(value):
        return True
    if _E.price_numbers_in_text(text):
        return True
    # احتياطٌ لا يُخفي رصداً حقيقياً بصيغةٍ لا يقرؤها النمط (مراجعة §58):
    # رقمٌ وعملةٌ مسمّاة في النصّ نفسِه ⇒ صفُّ سعر.
    return bool(re.search(r"\d", text) and _N.currency_in(text))


def _price_row_reason_row(dp: dict) -> str:
    """سبب صف سعرٍ كامل — القيمة أولاً ثم الملاحظة (صيد ٣ + دورة C4).

    قيمةٌ قابلة للحساب وحدها ⇒ ""؛ قيمة None تحتفظ بحكم غيابها (لا تُنقذها
    ملاحظةٌ تذكر الوحدة في جملة نفي)؛ قيمةٌ نصية/رقمية ناقصة تُكمَّل من
    الملاحظة (الوزن المعلَن فيها يجعل الصف قابلاً للحساب)."""
    v = dp.get("value")
    base = _price_row_reason(v)
    if not base or v is None:
        return base
    return _price_row_reason(f"{v} {dp.get('note') or ''}")


def _prices(row: dict) -> list:
    """أسعار السوق المرصودة — observed retail listings (localprice layer)."""
    out = []
    for v in _real_list(row.get("localprice")):
        if isinstance(v, dict) and v.get("price") is not None:
            out.append({"title": v.get("title"), "price": v.get("price"),
                        "currency": v.get("currency"), "store": v.get("store")})
    return out


def _client_leads(bundle, market, product: str = "", hs_code: object = None,
                  report_text: str = ""):
    """The browser and document exports must show the same validated rows.

    الدرس ٢٦٣: المنتجُ ورمزُه ومتنُ التقرير يمرّون أيضاً — مِصفاةُ الصلة
    بفئة المنتج تحتاجهم، وبدونهم كانت تعمل عمياء (تُبقي كلَّ شيء).
    """
    from silk_reports import _clean_leads
    result = dict(bundle or {"leads": [], "path": "gap"})
    ctx = {"market": market or {}, "product": product, "hs_code": hs_code,
           "report": {"text": report_text}}
    result["leads"] = _clean_leads(result.get("leads") or [], ctx)
    # أسبابُ الإسقاط تحمل أسماءَ جهاتٍ مرفوضةٍ وتعليلاً داخلياً — **عددُها
    # وحدَه** يصل العرض (يقرؤه المدقّق)، لا القائمةُ نفسُها (مراجعة §58).
    _dropped = ctx.get("leads_dropped") or []
    if _dropped:
        result["dropped_count"] = len(_dropped)
    return result


def _named_competitors(row: dict) -> list:
    """منافسون بالاسم — named-competitor candidates (web layer)."""
    out = []
    for v in _real_list(row.get("competitors_named")):
        name = (v.get("title") or v.get("name")) if isinstance(v, dict) else v
        if name:
            out.append(str(name))
    return out


def _suppliers(row: dict) -> list:
    """موردون/أعمال بالاسم — named businesses (maps/volza/explee)."""
    out = []
    for key, src in (("maps", "Google Maps"), ("volza", "Volza"),
                     ("explee", "explee")):
        for v in _real_list(row.get(key)):
            name = v.get("name") if isinstance(v, dict) else v
            if name:
                out.append({"name": str(name), "source": src})
    return out


def _culture(result: dict) -> list:
    """روابطُ بحثِ الويب الخام — raw web headlines (fallback only, links kept as citations)."""
    out = []
    for v in _real_list(result.get("websearch")):
        if isinstance(v, dict):
            title = v.get("title") or v.get("snippet")
            if title:
                out.append({"title": str(title), "link": v.get("link")})
        elif v:
            out.append({"title": str(v), "link": None})
    return out


def _consumer_culture(result: dict) -> dict:
    """ثقافةُ المستهلك المستخلَصة — Layer-3 extracted insights over the raw headlines.

    بلاغ المالك «ترسل روابط = أنت قوقل»: القسم يعرض رؤًى مبنيّة (كلود) لا روابطَ خام.
    يعيد {"insights":[{point, evidence}], "note", "raw": [عناوين للاستشهاد]}. إن غاب
    الاستخلاص (بلا مفتاح كلود) يبقى raw فقط ويُعلَن أنه لم يُحلَّل بعد — لا يُدَّعى تحليلٌ.
    """
    cc = result.get("consumer_culture")
    raw = _culture(result)
    if isinstance(cc, dict) and cc.get("insights"):
        return {"insights": _sanitize_points(cc.get("insights")),
                "note": _strip_internal_plumbing(cc.get("note", "")),
                "grounded": True, "raw": raw}
    return {"insights": [], "note": "", "grounded": False, "raw": raw}


def _t_today() -> str:
    import datetime
    return datetime.date.today().isoformat()


# ── Stage 2A: تغطية المصادر لكل قسم + ملحق الأثر — coverage & provenance ──────

_SECTION_FIELDS = {
    "market_size": ("components",),                # سيُفصَّل داخلياً
    "regulatory": ("requirements", "tariff"),
    "competitors": ("competitors", "competitors_named", "maps"),
    "pricing": ("prices", "localprice"),
    "demand": ("faostat",),
    "risk": ("risk",),
    # إصلاح مراجعة Stage 5 (ثغرة ٣): حقائق Google Trends تُحسب لقسم الاتجاه —
    # كانت «الاتجاه 0/0» بينما Trends أسهمت فعلاً لأن خط السنوات dict بلا
    # حقل value مباشر وطبقة trends كانت محسوبة على الطلب.
    "trend": ("trends",),
}


def _section_dps(row: dict, sec: str) -> list[dict]:
    """نقاط بيانات قسم واحد — the ONE fact-to-section extractor (تُستخدم في
    التغطية والبوابة معاً كي يستحيل اختلافهما)."""
    dps: list[dict] = []
    if sec == "market_size":
        comps = row.get("components") or {}
        for k in ("market_size", "saudi_position", "competition"):
            _walk_dps(comps.get(k), dps)
    elif sec == "demand":
        comps = row.get("components") or {}
        _walk_dps(comps.get("demand_capacity"), dps)
        _walk_dps(row.get("faostat"), dps)
    elif sec == "trend":
        # سلسلة الاتجاه متعدد السنوات: dict بسنوات مرصودة/فجوات — كل سنة حقيقة.
        tr = row.get("trend") or {}
        for pt in tr.get("series") or []:
            dps.append({"source": tr.get("source", "UN Comtrade"),
                        "value": pt.get("value"),
                        "note": f"سنة {pt.get('year')} من خط الاتجاه"})
        _walk_dps(row.get("trends"), dps)      # إشارة Google Trends
        # الدرس ٢٦٢: النموُّ ومعدّلُه المركّب **حقائقُ اتجاهٍ محسوبةٌ فعلاً**
        # من حزمة البحث (`MarketSizeAgent`) — استبعادُهما كان يُنتِج «بيانات
        # غير كافية لقسم الاتجاه» في تقريرٍ يطبع معدّل النمو نفسَه.
        research = row.get("research") or {}
        _ms = (research.get("agents") or {}).get("market_size") or {}
        for f in (_ms.get("findings") or []):
            if isinstance(f, dict) and f.get("metric") in (
                    "import_growth_pct", "import_cagr_pct"):
                _walk_dps(f, dps)
    elif sec == "pricing":
        for f in _SECTION_FIELDS.get(sec, ()):
            _walk_dps(row.get(f), dps)
        # إصلاح مراجعة المالك («هل الوكلاء يعملون؟»): الطبقة الحدودية المجانية
        # لوكيل pricing (border_unit_value_usd_kg من كومتريد، §4b) كانت تُحسب
        # فعلاً لكن لا تُقرأ هنا أبداً — فتُعرض «تسعير 0/0» رغم نجاح الوكيل،
        # بنفس علّة قسم trend المُصلَحة أعلاه (تعليق سطر ٢٢٢). "prices"/
        # "localprice" وحدهما (طبقة التجزئة المدفوعة) لا يكفيان على المسار
        # المجاني إذ يبقيان فارغَين بنيوياً خارج /deepen.
        research = row.get("research") or {}
        pricing_agent = (research.get("agents") or {}).get("pricing") or {}
        _walk_dps(pricing_agent.get("findings"), dps)
    else:
        for f in _SECTION_FIELDS.get(sec, ()):
            _walk_dps(row.get(f), dps)
    return dps


# حقولُ عقد المصدر التي يحملها البندُ المُصنَّع في **كلا** فرعَي `_walk_dps`.
# قائمةٌ واحدة لأنّ فرعين بقائمتين تتباعدان: مراجعةٌ ذاتية (§٥٨) وجدَت فرعَ
# `sources[]` وقد فقد `retrieved_at`/`data_year` — وكانا مدموجَين في `main` —
# حين أُضيفت `evidence_ids` إلى قائمته وحدَها. الاتحادُ هنا، والفرعان يقرآنه.
_DP_CARRIED_FIELDS = ("url", "confidence", "evidence_ids", "source_ids",
                      "retrieved_at", "data_year")


def _walk_dps(obj, out):
    """اجمع كل نقاط البيانات (dict أو DataPoint) — collect every datapoint-shaped node.

    إصلاح مراجعة التشغيل الحي: اكتشافات حزمة البحث (Stage 3، §4b) تحمل
    `sources[]` جمعاً لا `source` مفرداً فتغيب عن ملحق الأثر الإجمالي —
    Serper/Maps/مرآة السعودية كانت تُسهم فعلياً دون أن يظهر ذلك في الملحق.
    كل مصدر في sources[] يُسجَّل هنا مساهماً بقيمة الاكتشاف نفسها (المخطط
    يفرض sources غير فارغة فقط عند نجاح القيمة). محاولات §4b الفاشلة تبقى
    نصاً حراً في gaps[] لا نقاط بيانات مفردة — تُقرأ من قسم الفجوات مباشرة
    لا من هذا الملحق (قيد معروف، لا فشل صامتاً داخل قسمها الخاص).
    """
    if isinstance(obj, dict):
        if "source" in obj and "value" in obj:
            out.append(obj)
        elif "metric" in obj and isinstance(obj.get("sources"), list):
            for s in obj["sources"]:
                if isinstance(s, dict) and s.get("source"):
                    # **البند T-10.** كان البندُ المُصنَّع يحمل
                    # `source`/`value`/`note` فقط، فتسقط `url` و`confidence`
                    # و`source_ids` قبل أن تبلغ أيَّ مُستهلِك.
                    #
                    # **والحقولُ تُنسَخ من صفّ المصدر نفسِه حصراً.** مراجعةٌ
                    # ذاتية (§٥٨) التقطت في أوّل علاجٍ لهذا البند رجوعاً إلى
                    # الاكتشاف الأمّ عند غياب الحقل — فيُنسَب رابطُ «UN
                    # Comtrade» إلى صفّ «مسح ميداني» في الاكتشاف نفسِه:
                    # **إسنادٌ مختلَق**، وهو أسوأ من سقوطه. والغائبُ يبقى
                    # غائباً؛ الرابطُ العموميّ يُملأ لاحقاً من السجلّ
                    # (`_public_url`) باسم المصدر لا بتخمينٍ عنه.
                    item = {"source": s["source"], "value": obj.get("value"),
                            "note": obj.get("note", "")}
                    for key in _DP_CARRIED_FIELDS:
                        val = s.get(key)
                        if val not in (None, "", [], ()):
                            item[key] = val
                    out.append(item)
        for v in obj.values():
            _walk_dps(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_dps(v, out)
    elif hasattr(obj, "source") and hasattr(obj, "value"):
        # **البند T-10 — النصفُ الذي فاتني.** عالجتُ فرعَ `sources[]` وحدَه،
        # وهذا الفرعُ (كائنُ `DataPoint`) هو **شكلُ الإنتاج على `/analyze`**:
        # فبقيت الحقولُ تسقط على المسار الذي يخدم كلَّ تحليلٍ كلاسيكيّ، وسجّلتُ
        # البندَ مغلقاً «مُثبَتاً على المصنوع» — والقياسُ كان على مُثبِّتٍ
        # بشكلِ القاموس وحدَه. مراجعةٌ ذاتية (§٥٨) التقطته بعد الدمج.
        item = {"source": obj.source, "value": obj.value,
                "note": getattr(obj, "note", "")}
        for key in _DP_CARRIED_FIELDS:
            val = getattr(obj, key, None)
            if val not in (None, "", [], ()):
                item[key] = val
        out.append(item)


def _provenance(result: dict) -> list[dict]:
    """ملحق الأثر (Stage 2A) — لكل مصدر: المحاولات، المُسهم، وأمثلة أسباب الفشل.
    لا فشل صامتاً: كل نداء فاشل يظهر هنا بملاحظته الموسومة.

    **البند T-10.** الإسنادُ (الروابطُ المرصودة · مدى الثقة المرصود · أسماءُ
    المصادر المدمجة) يُجمَع هنا ويُصاغ **جاهزاً للعرض** في `tail`؛ العارضون
    يطبعونه ولا يبنونه (الدرس ١٠٥ — وقد كان بناؤه في `silk_reports` نقضاً له).

    والقيودُ الحاكمةُ لصدق السطر كلُّها من مراجعاتٍ ذاتية بعد الدمج،
    وجدولُها الكامل في `docs/ENGINE_AUDIT.md §T-10` (بلا عددٍ منطوقٍ
    هنا: ثلاثةُ أعدادٍ متباعدة كانت بنداً في المراجعة الرابعة):

    * **الثقةُ مدىً لا قمّة** — `max` وحدَها تُجمِّل مصدراً أسهم عشرَ مرّاتٍ
      بثقةٍ متدنّية ومرّةً بعالية. والقيمُ خارج `[0,1]` (زلّةُ JSON شائعة:
      `82` بدل `0.82`) تُرفَض، ولا تُقرأ `bool` رقماً. والرفضُ صامتٌ عمداً:
      البديلُ عرضُ «٨٢٠٠٪» أو تسريبُ زلّةِ مزوّدٍ إلى وجهِ التقرير.
    * **الروابطُ المرصودة لا تُهدَر ولا يُنَب عنها** — كان اختلافُها يُسقِطها
      كلَّها فيبقى مصدرُ رصدِ ويبٍ بلا رابطٍ إطلاقاً (أدلّةٌ أكثر ⇒ إسنادٌ
      أقلّ)؛ فصارت تُعرَض جميعاً حتى السقف. و**لا احتياطَ من السجلّ العموميّ
      هنا إطلاقاً**: رابطٌ لم يأتِ منه الرقم يوحي بتحقّقٍ لم يجرِ؛ صفحةُ
      المصدر الرئيسة تعيش في قسم المراجع، لا في سطر الإسناد.
    * **الاقتطاعُ يُعلَن** — قائمةٌ مبتورةٌ بصمتٍ تُقرأ إسناداً كاملاً؛
      فالروابطُ وأسماءُ المصادر كلتاهما تحمل عدّادَ الباقي.
    * **الترتيبُ محفوظ** — `atomic_source_ids` توثّق أنّ الأوّلَ هو المصدرُ
      الأساس، و`sorted` كانت تُضيّع ذلك.
    * **الحقلُ يُسمّى بما هو** — `source_ids` أسماءُ مصادرَ عمومية تُعرَض
      «مصادر مدمجة»، لا «معرّفات أدلة». و`evidence_ids` **لا تُجمَّع هنا ولا
      تُعرَض**: نطاقُها بعثةٌ واحدةٌ (`silk_llm_runtime._run_loop`: `next_id =
      [1]` مع كلّ بعثة/سوق)، فـ`dp1` في بعثتين شيئان مختلفان كان التجميعُ
      باسم المصدر يوحّدهما خطأً؛ ولا مصنوعَ يحمل جدولَ فكِّها فيبقى المعرّفُ
      غيرَ قابلٍ للحلّ عند قارئه. تبقى على `DataPoint` نفسِه وعلى البند الذي
      يمرّ في `_walk_dps` — **ولا تبلغ صفَّ الأثر هذا** (وكذلك `retrieved_at`
      و`data_year`: تُحمَلان في البند مطابقةً لما كان مدموجاً في `main`،
      ولا يقرؤهما أحدٌ اليوم؛ ادّعاءُ وصولها العرضَ كان خطأً في نصّي صحّحته
      مراجعةٌ ذاتية §٥٨).
    """
    # القارئُ القانونيّ يُستورَد صراحةً بلا ارتدادٍ صامت: كان `except` عريضٌ
    # يُبدِله بنسخةٍ محلّية **لا تفكّ المعرّفَ المركّب ولا ترتدّ إلى `source`**،
    # فيتدهور الإسنادُ بصمتٍ إن انكسر الاستيراد يوماً (مراجعةٌ ذاتية §٥٨).
    from silk_data_layer import atomic_source_ids as _atomic
    dps: list[dict] = []
    _walk_dps(result, dps)
    by: dict[str, dict] = {}
    for d in dps:
        src = str(d.get("source") or "?")
        b = by.setdefault(src, {"source": src, "attempted": 0,
                                "contributed": 0, "failures": [], "url": ""})
        b["attempted"] += 1
        _u = str(d.get("url") or "").strip()
        if _u and _u not in b.setdefault("_urls", []):
            b["_urls"].append(_u)
        _c = d.get("confidence")
        if (not isinstance(_c, bool) and isinstance(_c, (int, float))
                and 0.0 <= float(_c) <= 1.0 and d.get("value") is not None):
            b.setdefault("_conf", []).append(float(_c))
        _names = _atomic(d.get("source"), d.get("source_ids"))
        # التوحيدُ بمفتاحِ **المصدر** لا بالسلسلة الحرفية — `atomic_source_ids`
        # توحّد بلا حساسيةِ حالة داخل البند الواحد، وكان التراكمُ هنا يقارن
        # حرفياً فتصير تهجئتان لمصدرٍ واحد مصدرين ويُوسَم صفٌّ **مفردُ المصدر**
        # «مصادر مدمجة» زوراً — ادّعاءُ إسنادٍ مختلَق. ومقيسٌ على شكل الإنتاج:
        # `source` المخدومُ من المخزن يحمل لاحقةً («UN Comtrade (مخزن
        # الحقائق)») بينما `source_ids` تحمل الاسمَ العاري، فينتج «مصادر
        # مدمجة: UN Comtrade، UN Comtrade (مخزن الحقائق)» — مصدرٌ واحد
        # مُقدَّمٌ اثنين. الأوّلُ يفوز، فيبقى الترتيبُ عقداً.
        _seen = b.setdefault("_sids_seen", set())
        for _nm in _names:
            _k = _merge_key(_nm)
            if _k not in _seen:
                _seen.add(_k)
                b.setdefault("_sids", []).append(_nm)
        if d.get("value") is not None:
            b["contributed"] += 1
        elif len(b["failures"]) < 3 and d.get("note"):
            # سدّ تسريب: ملاحظة DataPoint فاشلة خام (مثل "PV.EST fetch
            # failed for CHN: HTTPSConnectionPool(...)") كانت تصل ملحق
            # الأثر — أضمن ملحق ظهوراً بنيوياً (كل DataPoint فاشل في شجرة
            # النتيجة كلها يمرّ هنا) فتُعرَّب عند الجمع لا عند كل مستهلك.
            failure = _strip_internal_plumbing(str(d.get("note")))
            b["failures"].append(_clip_words(failure, 140))   # قصّ معلن (صيد ٣)
    for b in by.values():
        # **الروابطُ المعروضة مرصودةٌ حصراً.** كان الغيابُ يُملأ من السجلّ
        # العموميّ (`_public_url`) — فيرى القارئ رابطاً **لم يأتِ منه الرقم**
        # بل صفحةَ المصدر الرئيسة، وهو إسنادٌ يوحي بتحقّقٍ لم يجرِ. الغيابُ
        # يبقى غياباً؛ وصفحةُ المصدر الرئيسة تعيش في قسم المراجع لا هنا.
        urls = b.pop("_urls", [])
        if urls:
            b["urls"] = urls[:_PROV_URL_CAP]
            b["urls_more"] = max(0, len(urls) - _PROV_URL_CAP)
        b["url"] = urls[0] if urls else ""
        conf = b.pop("_conf", [])
        if conf:
            b["confidence_min"], b["confidence_max"] = min(conf), max(conf)
        # `source_ids` **أسماءُ مصادرَ عمومية** لا معرّفاتِ أدلة: تُقرأ بالقارئ
        # القانونيّ (`atomic_source_ids`، يفكّ الدمج ويحفظ الترتيب) وتُعرَض
        # حين يكون الصفُّ **مدمجاً فعلاً** (أكثر من مصدرٍ ذرّيّ) — وإلا فهي
        # تكرارٌ لاسم الصفّ نفسِه. الخلطُ بينهما كان يُقدِّم اسمَ مصدرٍ شقيقٍ
        # دليلاً لهذا الصفّ (`silk_data_layer` يوثّق التمايز نصّاً).
        b.pop("_sids_seen", None)
        merged = b.pop("_sids", [])
        if len(merged) > 1:
            b["merged_sources"] = merged[:_PROV_ID_CAP]
            # الاقتطاعُ يُعلَن هنا أيضاً — كان الوحيدَ من القوائم الثلاث
            # يُبتَر بصمتٍ، فيُقرأ صفٌّ مدمجٌ من عشرة مصادرَ ثمانيةً.
            b["merged_sources_more"] = max(0, len(merged) - _PROV_ID_CAP)
        # **بلغةِ عارضيه لا بلغةِ العرض.** مُصيِّرا هذا الملحق (`render_docx`
        # و`render_markdown`) عربيّان بالكامل مهما كانت لغةُ العرض — العنوانُ
        # والنثرُ («أسهم N من M محاولة») ثابتان. وتمريرُ لغةٍ إلى الذيل كان
        # يُنتِج سطراً بلغتين على مسارٍ **حيّ**: `silk_platform/api.py:1385`
        # يبني العرضَ بلغة الدراسة و`:1462` يسلّمه `render_docx`، فمصنعٌ
        # إنجليزيّ يُنزِّل «أسهم 1 من 1 محاولة — observed confidence 77%».
        # لذا لا `lang` على هذه الدالّة أصلاً: مُعامِلٌ ميّتٌ يوحي بقدرةٍ غير
        # قائمة، وتعريبُ الملحق كلِّه على مسارٍ إنجليزيّ بندٌ أوسع — `W-03`.
        b["tail"] = _provenance_tail(b, "ar")
    return sorted(by.values(), key=lambda b: -b["contributed"])


# سقفُ الأسماء/الروابط المعروضة — والباقي **يُعلَن** لا يُبتَر بصمت.
_PROV_ID_CAP = 8
_PROV_URL_CAP = 4


# لاحقةُ وسمٍ بين قوسين في نهاية اسم المصدر («… (مخزن الحقائق)») — طريقةُ
# استرجاعٍ لا مصدرٌ ثانٍ، فتُنزَع قبل موازنةِ الأسماء.
_SOURCE_QUALIFIER_RE = re.compile(r"\s*\([^()]*\)\s*$")


def _merge_key(name: object) -> str:
    """مفتاحُ **المصدر** خلف تهجئته — بلا حساسيةِ حالةٍ ولا لاحقةِ وسم.

    «UN Comtrade» و«UN Comtrade (مخزن الحقائق)» مصدرٌ واحد؛ والمقارنةُ
    الحرفية كانت تُقدِّمهما «مصادر مدمجة» — ادّعاءَ إسنادٍ لم يقع.
    """
    return _SOURCE_QUALIFIER_RE.sub("", str(name or "").strip()).casefold()


def _provenance_tail(b: dict, lang: str = "ar") -> str:
    """ذيلُ سطرِ أثر المصدر **جاهزاً للعرض** — يُبنى هنا لا في العارضين.

    الروابطُ داخل قوسين عمداً: النصُّ عربيُّ السياق، و`silk_reports`
    تحقن RLM داخل الأقواس الحاوية لمقاطعَ لاتينية (WP-5) — فلولا القوسان
    لانقلب ترتيبُ الرابط والفواصل في PDF المُحوَّل.

    (مقيسٌ بمستخرِج الحارس نفسِه `fitz`: كلُّ صفٍّ ذي رابطٍ يزيد عدّادَ
    `count_suspicious_brackets` واحداً — أثرُ تقطيعِ المقاطع في الاستخراج لا
    انعكاسٌ مرئيّ. والعدّادُ على تقرير المدقّق يتجاوز العتبةَ من الأساس بلا
    أيّ رابط (٥٦)، فالبندُ مُسجَّلٌ حالةً قائمةً في `docs/ENGINE_AUDIT.md`
    ولا علاقةَ لهذا السطر بنشأته.)
    """
    import silk_i18n as _I
    sep = ", " if str(lang).lower().startswith("en") else "، "
    parts: list[str] = []
    lo, hi = b.get("confidence_min"), b.get("confidence_max")
    if isinstance(lo, float) and isinstance(hi, float):
        # قيمةٌ موجبةٌ دون نصف بالمئة كانت تُقرَّب إلى «0%» فتُقرأ «بلا ثقة»
        # وهي ليست كذلك؛ والصفرُ الحقيقيّ وحدَه يبقى «0%» (§٥٨).
        def _pc(x: float) -> str:
            return "<1" if 0 < x < 0.005 else str(round(x * 100))
        pct = (f"{_pc(lo)}%" if _pc(lo) == _pc(hi)
               else f"{_pc(lo)}–{_pc(hi)}%")
        parts.append(_I.t("prov_confidence", lang, range=pct))
    if b.get("merged_sources"):
        more = int(b.get("merged_sources_more") or 0)
        parts.append(_I.t("prov_merged_sources", lang,
                          names=sep.join(b["merged_sources"]))
                     + (f" (+{more})" if more else ""))
    # `_provenance` وحدَها تنادي هذه الدالّة وتضبط `urls` قبلها، فارتدادٌ
    # إلى `b["url"]` المفرد فرعٌ لا يُنفَّذ — وتبريرُه بـ«صفوفٍ مخزَّنة» كان
    # خاطئاً بالقياس: صفٌّ قديمٌ بـ`confidence_max` وحدَها يفقد ثقتَه هنا
    # على أيّة حال (فرعُ المدى يشترط `confidence_min`). حُذِف (§٥٨).
    urls = b.get("urls") or []
    if urls:
        more = int(b.get("urls_more") or 0)
        parts.append("(" + " ".join(urls)
                     + (f" +{more}" if more else "") + ")")
    return (" — " + " · ".join(parts)) if parts else ""


def _section_coverage(row: dict) -> dict:
    """درجة تغطية لكل قسم — {section: {attempted, contributed, score, single_source,
    low_confidence}}. قسم بمصدر واحد فقط يُعلَّم منخفض الثقة (قاعدة 2A)."""
    out: dict[str, dict] = {}
    for section in _SECTION_FIELDS:
        dps = _section_dps(row, section)
        att = len(dps)
        con = sum(1 for d in dps if d.get("value") is not None)
        srcs = {str(d.get("source")) for d in dps if d.get("value") is not None}
        out[section] = {
            "attempted": att, "contributed": con,
            "score": round(con / att, 2) if att else 0.0,
            "single_source": len(srcs) == 1 and con > 0,
            "low_confidence": (len(srcs) <= 1),
        }
    return out


# ── Stage 2B: بوابة الخصوصية — per-section specificity gate ──────────────────
# العتبات المقترحة (قابلة للضبط): أدنى عدد حقائق سوقية حقيقية ليُعرض القسم كنثر؛
# دونها يُعرض «بيانات غير كافية» + قائمة المصادر المُحاوَلة — لا نثر عام أبداً.
SECTION_THRESHOLDS = {
    "market_size": 2,   # الحجم + (حصة أو تركّز) — رقم واحد لا يصنع قسم سوق
    "demand": 1,
    "regulatory": 2,    # بند اشتراطات + التعريفة (بند خروج عام وحده لا يكفي)
    "competitors": 2,
    "pricing": 1,
    "risk": 2,
    "trend": 2,         # سنتان على الأقل لخط اتجاه
}


def _section_status(row: dict) -> dict:
    """حالة كل قسم بعد بوابة العتبة — {section: {status, contributed, threshold,
    sources_attempted}}. status: ok | insufficient."""
    cov = _section_coverage(row)
    out: dict[str, dict] = {}
    for sec, c in cov.items():
        thr = SECTION_THRESHOLDS.get(sec, 1)
        # نفس المستخرج الواحد — يستحيل اختلاف البوابة عن التغطية (ثغرة ٣).
        dps = _section_dps(row, sec)
        attempted_sources = sorted({str(d.get("source")) for d in dps
                                    if d.get("source")})
        out[sec] = {
            "status": "ok" if c["contributed"] >= thr else "insufficient",
            "contributed": c["contributed"], "threshold": thr,
            "sources_attempted": attempted_sources,
        }
    return out


#: أعدادٌ مؤنّثةٌ للحقائق — «ثلاث حقائق» لا «ثلاثة حقائق» (المعدودُ مؤنّث).
_FEM_ONES = {3: "ثلاث", 4: "أربع", 5: "خمس", 6: "ست", 7: "سبع", 8: "ثماني",
             9: "تسع", 10: "عشر"}


def _facts_needed(n: int) -> str:
    """«حقيقة واحدة» / «حقيقتين» / «ثلاث حقائق» — مجرورٌ بعد «يحتاج»."""
    n = int(n or 0)
    if n <= 1:
        return "حقيقة واحدة"
    if n == 2:
        return "حقيقتين"
    if n <= 10:
        return f"{_FEM_ONES[n]} حقائق"
    return f"{n} حقيقةً"


def _facts_found(n: int) -> str:
    """«واحدة» / «اثنتان» / «ثلاث» — مرفوعٌ فاعلاً لـ«رُصدت»."""
    n = int(n or 0)
    if n == 1:
        return "واحدة"
    if n == 2:
        return "اثنتان"
    if n <= 10:
        return _FEM_ONES.get(n, str(n))
    return str(n)


def insufficient_line(sec_ar: str, st: dict) -> str:
    """جملة النقص الوحيدة المسموح بها (2B-ب) — the only allowed insufficiency text.

    الدرس ٢٦٤: تقول للقارئ **ما ينقص وماذا جُرِّب** بدل حكمٍ آليّ على
    البيانات؛ ونفسُ الأرقام ونفسُ المصادر حرفياً. والمراجعةُ الذاتية (§58)
    ألزمت أمرين: مطابقةُ العدد والمعدود (المعدودُ **مؤنّث**، فلا «رُصدت 0
    حقيقة» ولا «من 2 يحتاجها»)، وذيلُ مصادرَ لا يدّعي محاولةً لم تقع
    («بعد محاولة هذه المصادر: لا مصادر مُحاوَلة» جملةٌ تناقض نفسَها).
    """
    got, need = int(st.get("contributed") or 0), int(st.get("threshold") or 0)
    head = ("لم تُرصد أي حقيقة سوقية" if got <= 0
            else f"رُصدت {_facts_found(got)} من الحقائق السوقية")
    srcs = "، ".join(st.get("sources_attempted") or [])
    tail = f"، بعد محاولة: {srcs}" if srcs else "، ولم تُحاوَل أي مصادر"
    return (f"لم يكتمل قسم «{sec_ar}»: {head}، والقسم يحتاج "
            f"{_facts_needed(need)}{tail}")


# ── Stage 5: مشتقات حزمة البحث (§7) — SWOT قاعدي، شرائح، دليل مورّدين ─────────

def _rmetric(research: dict | None, agent: str, metric: str):
    """قيمة مقياس من حزمة §4b — value of a metric from the research bundle."""
    for f in ((research or {}).get("agents", {}).get(agent, {})
              .get("findings") or []):
        if f.get("metric") == metric and f.get("value") is not None:
            return f.get("value")
    return None


def _swot(research: dict | None) -> dict:
    """SWOT قاعدي (§7-5) — كل خلية من حقيقة مرصودة بدليلها؛ الفارغ يُعلَن.

    اشتقاق عرض صرف: قواعد معلنة فوق حقائق حزمة البحث — لا نثر حر ولا تخمين.
    """
    from silk_narrative import internal_ar
    S, W, O, T = [], [], [], []
    if not research or not research.get("agents"):
        return {"S": S, "W": W, "O": O, "T": T,
                "note": "يتطلب حزمة وكلاء البحث (with_research)"}
    sau = _rmetric(research, "competitor", "saudi_share_pct")
    if sau:
        S.append({"text": f"حضور سعودي قائم بحصة {sau}% من واردات السوق",
                  "evidence": f"UN Comtrade — {internal_ar('saudi_share_pct')}"})
    uv = _rmetric(research, "pricing", "border_unit_value_usd_kg")
    suv = _rmetric(research, "pricing", "saudi_border_unit_value_usd_kg")
    if uv and suv and suv <= uv:
        S.append({"text": f"سعر حدودي سعودي منافس ({suv}$ مقابل متوسط {uv}$/kg)",
                  "evidence": "UN Comtrade — قيم الوحدة"})
    for g in (research.get("agents", {}).get("pricing", {}).get("gaps") or []):
        if "بطاقة" in g or "margin" in g:
            W.append({"text": "الهامش غير محسوب — الناقص: سعر المصنع "
                              "بوحدة المنتج مع توثيق بقية عناصر التكلفة",
                      # صيد ٣: القصّ بعد الترجمة وعند حدّ كلمة معلناً — الشريحة
                      # الخام كانت تبتر وسط الكلمة قبل أن يترجمها المُءَنسِن.
                      "evidence": _clip_words(_humanize_gap_note(g), 120)})
            break
    gate = _rmetric(research, "regulatory", "eligibility_gate")
    if gate:
        W.append({"text": "بوابة أهلية أوروبية مفتوحة (منشأة معتمدة EU 2017/625)",
                  "evidence": f"مرجع L1 — {internal_ar('eligibility_gate')}"})
    cagr = _rmetric(research, "market_size", "import_cagr_pct")
    if cagr is not None and cagr > 5:
        O.append({"text": f"واردات السوق تنمو {cagr}% سنوياً مركّباً",
                  "evidence": f"UN Comtrade — {internal_ar('import_cagr_pct')}"})
    hhi = _rmetric(research, "competitor", "hhi")
    # الموجة 2ب: مقياس HHI البحثي موحّد 0–10000 — عتبة التفتّت 1500
    # (كانت 0.15 على الكسر؛ نفس شريط وزارة العدل ×10000).
    if hhi is not None and hhi < 1500:
        O.append({"text": f"سوق مفتّت (HHI {hhi}) — لا مورّد مهيمناً",
                  "evidence": f"UN Comtrade — {internal_ar('hhi')}"})
    # الموجة د-٣: «موسمية رمضان فرصة» كانت مشتقّةً من **حصةٍ سكانية** لا من
    # طلبٍ مرصود — فرصةٌ بلا دليل. تُحذَف من الفرص؛ الموسميةُ تبقى حقيقةً
    # مرصودةً في بعثة الاتجاهات حيث تُقاس فعلاً.
    top = _rmetric(research, "competitor", "top_supplier_share_pct")
    if top is not None and top > 50:
        T.append({"text": f"مورّد مهيمن بحصة {top}% — حرب أسعار محتملة",
                  "evidence": f"UN Comtrade — {internal_ar('top_supplier_share_pct')}"})
    tariff = _rmetric(research, "regulatory", "tariff_applied_pct")
    if tariff is not None and tariff > 10:
        T.append({"text": f"تعريفة مطبّقة مرتفعة {tariff}%",
                  "evidence": f"WITS — {internal_ar('tariff_applied_pct')}"})
    fx = _rmetric(research, "risk", "fx_volatility_pct")
    if fx is not None and fx > 5:
        T.append({"text": f"تقلب عملة {fx}% (معامل اختلاف)",
                  "evidence": f"World Bank — {internal_ar('PA.NUS.FCRF')}"})
    if _rmetric(research, "risk", "critical_risk"):
        T.append({"text": "خطر سياسي حرج (WGI دون −1.5)",
                  "evidence": f"World Bank — {internal_ar('PV.EST')}"})
    return {"S": S, "W": W, "O": O, "T": T,
            "note": "خلايا مشتقة من الحقائق المتاحة — الخلية الفارغة تعني "
                    "غياب البيانات، لا سلامة الجانب"}


def _segments(research: dict | None) -> list[dict]:
    """شرائح العملاء (§7-8) — دخل × ثقافة استهلاك، بقواعد معلنة وفجوات مصرّحة."""
    if not research or not research.get("agents"):
        return []
    out = []
    gdp = _rmetric(research, "consumer_demand", "gdp_per_capita_usd")
    if gdp is not None:
        tier = ("مرتفع" if gdp > 25_000 else
                "متوسط" if gdp > 8_000 else "منخفض")
        out.append({"segment": f"شريحة الدخل: {tier}",
                    "basis": f"نصيب الفرد {round(gdp):,}$ (World Bank) — "
                             "عتبات معلنة 8k/25k"})
    # الموجة د-٣ (قاعدةُ المالك): **التركيبةُ الدينية ليست طلباً** — لا تُعرَض
    # شريحةَ طلبٍ في أيّ فئة. موضعُ الحلال (شرطُ دخولٍ أم ميزةٌ بثلاثة شروط)
    # يُحسَب في `silk_commercial_analysis.halal_positioning` ويدخل السجلّ.
    si = _rmetric(research, "consumer_demand", "search_interest")
    if si is not None:
        out.append({"segment": f"اهتمام البحث بالمنتج: {si}/100",
                    "basis": "Google Trends — search_interest"})
    return out


def _supplier_directory(research: dict | None) -> dict:
    """دليل المورّدين (§7 بتوجيه المالك) — مرشّحون موسومون غير موثَّقين."""
    return {"saudi": _rmetric(research, "supplier", "saudi_suppliers") or [],
            "target": _rmetric(research, "supplier", "target_distributors")
                      or [],
            # بلا كسر ثقة خام ولا اسم مسار API داخلي على وجه التقرير
            # (تسريب سباكة): الشارة الثلاثية بدل "(ثقة 0.4)"، و«خدمة
            # التعميق المدفوعة» بدل "/deepen".
            "note": "مرشّحون غير موثَّقين (○ غير متحقق) — أكّدهم قبل "
                    "التعاقد؛ الترقية الموثّقة عبر خدمة التعميق المدفوعة"}


def _report_fields(rep: object) -> dict:
    """طبّع AgentReport/dict — a live AgentReport dataclass OR a dict reloaded
    from storage (json_blob)، نفس نمط `_dp` أعلاه."""
    if isinstance(rep, dict):
        return {"agent_name": rep.get("agent_name"),
               "findings": rep.get("findings") or [],
               "failed": bool(rep.get("failed")), "summary": rep.get("summary") or ""}
    return {"agent_name": getattr(rep, "agent_name", None),
           "findings": getattr(rep, "findings", None) or [],
           "failed": bool(getattr(rep, "failed", False)),
           "summary": getattr(rep, "summary", "") or ""}


_TOOL_CALLS_RE = re.compile(r"نداءات أدوات:\s*(\d+)")
_DROPPED_RE = re.compile(r"أُسقطت\s*(\d+)\s*بند")
_GAPS_RE = re.compile(r"فجوات:\s*([^|]*)")

# بلاغ منتج من المالك: التقرير المعروض للعميل كان يكشف السباكة الداخلية
# ("LLMAgent:tariffs_agreements"، وسوم استشهاد خام مثل "dp7") — كلود
# (الكاتب أو بعثة) يستشهد أحياناً حرفياً بوسوم رآها في مدخلاته الخام بدل
# تلخيصها بلغة تجارية. الإصلاح تطبيع حتمي في طبقة العرض، لا تعديل على
# الأرقام: راجع _mission_label/_strip_internal_plumbing تحت.
# `\s*` بعد النقطتين: كلود يكتب أحياناً "LLMMissionAgent: pricing_scout"
# بمسافة (تسريب مُثبَت في المختصر) — بلا `\s*` كان يفلت (تدقيق، النمط A).
_INTERNAL_AGENT_RE = re.compile(r"LLM(?:Mission)?Agent:\s*([A-Za-z_]+)")
_DP_TAG_RE = re.compile(r"\[?dp\d+\]?")
# HF2 (بلاغ أقواسٍ فارغة — تقرير قطر ٢٠٢٦-٠٧-٢٣): كان `_DP_TAG_RE` يحذف نصَّ
# الوسم «dp7» ويترك قوسَه «()» هيكلاً فارغاً («)/(»، «()»، «)///(»). العلاج
# (نفسُ مبدأ WS4: لا قوسٌ حول محذوف): احذفِ **المجموعةَ كاملةً بقوسها** أولاً،
# ثمّ الوسمَ المفردَ الباقي، ثمّ اطوِ أيَّ قوسٍ فارغٍ متبقٍّ. «/／» ضمن الفواصل
# لأنّ خلايا markdown تستبدل «|»→«/» (وملء fullwidth «／»).
_DP_GROUP_RE = re.compile(
    r"[\(（]\s*\[?dp\d+\]?(?:\s*[،,;/／\s]\s*\[?dp\d+\]?)*\s*[\)）]")
_EMPTY_CITATION_GROUP_RE = re.compile(r"[\(（]\s*[/／،,;\s]*[\)）]")
# البند 13 (أمر إصلاح المحرّك): حقلُ مصدرٍ فارغ داخل قوسٍ غير فارغ يترك
# فاصلةً يتيمة — «(، World Bank رصد مباشر لعام 2025)» و«(اهتمام=100، /)»
# (تقرير #10 حرفياً). القاعدة: لا فاصلة يتيمة تُطبع أبداً — تُطوى البادئة
# «(، » واللاحقة «، /)» وتبقى بقية القوس سليمة.
_ORPHAN_LEAD_COMMA_RE = re.compile(r"([\(（])\s*[،,;]\s*")
_ORPHAN_TAIL_COMMA_RE = re.compile(r"\s*[،,;]\s*[/／]?\s*([\)）])")
# البند 23: جملُ لغة النظام عن آلية بناء الملاحق لا تصل القارئ — تُحوَّل
# لصياغة قارئ بإسقاط «آلياً» من عبارات الإحالة (المعنى يبقى صحيحاً).
_SYSTEM_MECHANICS_RE = re.compile(
    r"(يرد أسفل هذا القسم|تلي هذا القسم|يلي هذا القسم|يليان|تليان)\s+آلياً")
# الصنف ١ (موجة عيوب التقرير): «مُصنَّفٌ آلياً» تقول **كيف عمل النظام**، وما
# يحتاجه القارئ هو **ماذا يعني ذلك لقراره**: أن الرمز لم يُراجَع بشرياً. نفسُ
# علاج البند 23 أعلاه (صياغةُ قارئ بلا فقدِ معنى) مطبَّقاً على الصيغة الفعلية
# التي تصل المتن. يُحفَظ الحرفُ السابق (مُصنَّف/صُنِّف/حُسِم) والتالي.
_AUTO_CLASSIFIED_RE = re.compile(
    r"(مُصنَّف|مصنَّف|مصنف|صُنِّف|صنِّف|حُسِم|حسم)(\S*)\s+آليّ?اً")
# HF4.1 (تسريب سلسلةٍ إنجليزيةٍ داخلية إلى §5 — تقرير قطر): ملاحظةُ الحكم
# المبدئيّ ثنائيةُ اللغة («Preliminary only; missing sources flagged, not
# estimated. تنبيه: …») — النصفُ الإنجليزيّ داخليٌّ لا يصل العميل. يُزال
# النصفُ الإنجليزيّ فقط (يبدأ بـPreliminary وينتهي بـestimated)، والعربيّ يبقى.
_PRELIM_EN_NOTE_RE = re.compile(
    r"Preliminary[^.\n]*?(?:estimated|flagged)[^.\n]*\.\s*", re.I)
_WHOLE_JSON_RE = re.compile(r"^\s*[{\[].*[}\]]\s*$", re.S)
# بلاغ حي إنتاجي (تمور/هولندا HS080410): وصلت الواجهةَ أشكالُ JSON خام لم
# يلتقطها _WHOLE_JSON_RE المُرسَّى: (أ) سياج شيفرة "```json {...}" أو "json
# {...}"؛ (ب) JSON مضمَّن خلف بادئة نصية ("التوصية: {\"verdict\":...}")؛
# (ج) لاحقة عدّ أدوات داخلية ("... | tool calls: 2"). تُطهَّر كلها هنا.
_JSON_FENCE_RE = re.compile(r"`{3,}|(?<![A-Za-z؀-ۿ])json(?=\s*[{\[])",
                            re.I)
# الشكل الإنجليزي فقط ("| tool calls: N") — هو ما تسرَّب للعميل. الشكل
# العربي ("نداءات أدوات: N") تِلِمتري مشغّل مشروع يُحلّله _mission_trace_summary
# لعدّ نداءات الأدوات، فلا يُجرَّد هنا (بلاغ حي: تجريده صفّر العدّ في اللوحة).
_TOOL_CALLS_SUFFIX_RE = re.compile(
    r"\s*\|\s*tool calls\s*:?\s*\d+\s*$", re.I)
# تدقيق v2 (تسريب المشرف #7، متابعة مستقلّة): الشكل العربي «نداءات أدوات: N»
# (أرقام لاتينية أو عربية-هندية) تِلِمتري تتبّعٍ مشروع — يُقرأ من الملخّص الخام
# قبل العرض؛ لكنه على أسطح العميل (report.md/ask/brief) عبر `_strip_internal_plumbing`
# سباكةٌ داخلية تُسرَّب. يُجرَّد للعرض فقط، والتتبّع يقرأ الخام فلا يتصفّر عدّ اللوحة.
_AR_TOOL_CALLS_RE = re.compile(
    r"\s*[|]?\s*نداء(?:ات)?\s+أدوات?\s*[:：]\s*[0-9٠-٩۰-۹]+")
# علامات بنية JSON داخلية للنموذج — وجود أيّها يعني تسريب سباكة لا نثر عميل.
# تشمل مفاتيح الحكم بصيغتها الإنجليزية الخام وصيغتها المُعرَّبة (كان
# _EN_FIELD_RE يحوّل verdict/confidence داخل JSON مسرَّب قبل التقاطه، فيظهر
# "{\"الحكم\":...}" على الواجهة — نلتقط الصيغتين).
_INTERNAL_JSON_MARKERS = ('"datapoint_ids"', '"findings"', '"claim"',
                          '"reasoning"', '"verdict"', '"confidence"',
                          # تسريب حي مؤكَّد (المُشرِف): JSON مضمَّن بمفاتيح
                          # score/summary (مخرَج بعثة/محلل) فات علامات البنية
                          # القديمة فوصل مضمَّناً خلف بادئة نصية.
                          '"score"', '"summary"',
                          '"الحكم"', '"درجة الثقة"')

# ريبر DataPoint(...) مسرَّب في نصّ معروض (تسريب حي مؤكَّد، المُشرِف): الكاتب
# يردّد أحياناً تمثيل نقطة بيانات خاماً كما رآه في مدخلاته. المُطهِّر القديم
# كان **ينصف-يترجم** الريبر (يحوّل confidence→«درجة الثقة» ويُبقي الغلاف
# DataPoint(value=…, source=…, …)) فيخرج فرانكنشتاين. الحلّ: يُحيَّد الريبر
# **كاملاً** قبل أي ترجمة حقول — تُستخرَج القيمة المقروءة (value) أو تُعلَن
# فجوة، ولا يبقى اسم الصنف ولا أيّ حقل خام. البنية المعروفة للريبر مُثبَّتة
# (قيم مُقتبَسة تحتمل فواصل/أقواس داخلها فلا تكسر non-greedy).
_DATAPOINT_REPR_RE = re.compile(
    # مرن (بلاغ المشرف الحي): يمسك أي ريبر DataPoint يبدأ بـ value= مهما كان
    # عدد الحقول بعده أو ترتيبها — الصيغة السداسية الكاملة والمختصرة معاً.
    # علامات التنصيص داخل الحقول (بما فيها أقواس داخل note مقتبسة) مسموحة.
    r"DataPoint\(\s*value=(?P<v>'[^']*'|\"[^\"]*\"|[^,)]+?)\s*"
    r"(?:,(?:'[^']*'|\"[^\"]*\"|[^)])*)?\)")
# شبكة أمان (بلاغ المشرف): أي DataPoint(...) لم يلتقطه النمط أعلاه (ترتيب
# حقول شاذ، بلا value=) يُستبدَل كاملاً بفجوة معلنة — نصف الترجمة أسوأ من الخام.
_DATAPOINT_ANY_RE = re.compile(r"DataPoint\((?:'[^']*'|\"[^\"]*\"|[^)])*\)")
# تسريب حقول داخلية إنجليزية في نص معروض (بلاغ مالك: "verdict" و
# "confidence 0.64" وصلا جدولاً في متن تقرير العميل) — الكاتب يردّد أحياناً
# أسماء حقول رآها في مدخلاته. القيمة العشرية بعد confidence تُصاغ بشرياً
# (confidence_phrase) والوسمان يُعرَّبان؛ لا تعديل على أي رقم آخر.
# سدّ تسريب (الطبقة ٥): الفاصل الأصلي [|:：] يطابق خلية جدول ("| confidence
# | 0.64 |") لكن ليس نثراً حرّاً بفاصلة فراغ ("confidence 0.64") — الشكل
# الذي ظهر فعلياً في جواب الدردشة السياقية الحرّ (سطح جديد لهذا المُطهِّر).
_EN_CONF_VALUE_RE = re.compile(r"\bconfidence\b(\s*[|:：]?\s*)(\d?\.\d{1,4})")
# تدقيق v2 (الموجة ١، تسريب المشرف #3): الصيغة العربية الخام «ثقة=٠٫٦٤» (كلمة
# «ثقة» + أرقام عربية-هندية + فاصلة عربية ٫) كانت تنجو من `_EN_CONF_VALUE_RE`
# (إنجليزي فقط). تُلتقَط بأرقامٍ عربية أو لاتينية وتُصاغ بشرياً كنظيرتها.
_AR_DIGIT_FOLD = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_AR_DIGIT_FOLD.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})
_AR_CONF_RE = re.compile(
    r"ثقة\s*[=:：]\s*([0-9٠-٩۰-۹]+[.,٫][0-9٠-٩۰-۹]+)")
# تدقيق v2 (تسريب المشرف #6): بادئة مفتاح بعثة مرقّمة «m3_pricing_scout» —
# البادئة الرقمية «mN_» أمام مفتاحٍ لاتيني تُزال، فيبقى المفتاح ليُترجَم لاسمه
# العربي عبر `_map_mission_keys` (لا مفتاح داخلي مرقّم في المُسلَّم).
_MISSION_NUM_PREFIX_RE = re.compile(r"\bm\d+_(?=[a-z])")
_EN_FIELD_RE = re.compile(r"\b(verdict|confidence)\b")
_EN_FIELD_AR = {"verdict": "الحكم", "confidence": "درجة الثقة"}
# رمز حكم آلة خام (GO/WATCH/NO-GO/CONDITIONAL-GO) داخل نثر حرّ كتبه الكاتب
# نفسه (بلاغ اختبار: "الحكم WATCH — مراقبة قبل الدخول مبني على...") — لا
# حقل مُهيكَل يلتقطه verdict_ar عند مصدره هنا، فالتقاط نصّي مباشر داخل
# السرد. الأطول أولاً (CONDITIONAL-GO/NO-GO قبل GO المجرّدة) كي لا يتبقّى
# "-GO" يتيماً بعد الاستبدال.
# تسريب حي مؤكَّد (المُشرِف): رمز الحكم كان يُطابَق بالحالة الكبيرة فقط، فأيّ
# صيغة أخرى (go/Watch/no-go) تبقى خاماً في المُسلَّم. الآن حساسية-حالة مُلغاة
# (re.I) + توحيد للكبيرة عند التمرير لـ verdict_ar (يوحّدها داخلياً أصلاً).
_RAW_VERDICT_RE = re.compile(r"\b(CONDITIONAL-GO|NO-GO|GO|WATCH)\b", re.I)

# §2.6 (أمر العمل الرئيس): عبارة تُلمِّح إلى «قائمة حقائق» داخلية معطاة
# للنموذج («بين الحقائق المتاحة/المعطاة») تُعاد صياغتها بلغة موجَّهة للقارئ.
_FACTS_LIST_RE = re.compile(
    r"بين\s+الحقائق(?:\s+(?:المتاحة|المعطاة|المتوفّرة|المتوفرة))?")
# §2.7 (أمر العمل الرئيس): سرد فشل الأداة («فشل استعلام WITS مرتين بسبب
# انقطاع الاتصال») يُعاد صياغته كتصريح فجوة بيانات — الرقم لم يتوفّر من
# المصدر الرسمي وقت الإعداد، لا سرد لأعطال تقنية داخلية.
_TOOL_FAILURE_RE = re.compile(
    r"فشل\s+استعلام\s+([A-Za-z؀-ۿ/]+)[^.؛،\n]*?"
    r"(?:بسبب\s+)?(?:انقطاع|فشل|تعذّر|تعذر|توقّف|توقف)\s+الاتصال[^.؛\n]*")


_RAW_JSON_GAP = "تعذّرت قراءة هذا البند — بيانات غير مقروءة من المصدر"

# §2 (أمر العمل الرئيس — صفر ذكر لـ«كلود»/Claude في المُسلَّم): أي ذكر صريح
# للأداة يُصاغ بلغة محايدة موجَّهة للقارئ. تُطبَّق في طبقة العرض على متن
# البحث العميق (سرد/ملخّصات/حدود) فلا يصل الاسم الداخلي إلى المُسلَّم.
_CLAUDE_JSON_FAIL_RE = re.compile(r"رد\s+كلود\s+غير\s+قابل\s+للتفسير[^.،؛\n]*")
_CLAUDE_WORD_RE = re.compile(r"\bClaude\b|كلود")
# §7: كلمة (٣ أحرف فأكثر) تكرّرت فوراً — تُطوى إلى واحدة («التوصية التوصية»).
_DUP_WORD_RE = re.compile(r"(?<!\S)([^\W\d_]{3,})\s+\1(?!\S)")

# البند ١ (تدقيق «تحليل #1» DZA — silk_quality_gate.markdown_artifacts):
# أسوار كود عشوائية («```» بمحتواها الكامل) وتنسيق «**» شارد قد تتسرّب من
# مقطع مصدر مقتبَس حرفياً أو من صياغة الكاتب — تُزالان. **لا تُمَسّ** عناوين
# "## "/"### " البنيوية: هذه إلزامية (silk_ai_judge._REPORT_SECTIONS) وتُقرَأ
# عناوين Word فعلية في silk_reports._docx_deep_research (`line.startswith
# ("## ")`)، وتبقى تُبلَّغ WARN متوقَّعة في بوابة الجودة (test_quality_gate_
# stays_warn_for_ordinary_repairable_findings) — هذا الإصلاح يعالج التسريب
# الفعلي الإضافي (الأسوار/التنسيق الشارد) لا العناوين المطلوبة.
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```\n?")
_SANCTIONED_BOLD = "**ماذا يعني هذا لقرارك:**"
_STRAY_BOLD_RE = re.compile(r"\*\*([^\n*]{1,200}?)\*\*")


def _strip_stray_markdown(text: str) -> str:
    """أزل تنسيق «**» شارد خارج العبارة المرخَّصة الوحيدة (راجع تعليق الثوابت
    أعلاه) — لا يمسّ عناوين "## "/"### ". أسوار الكود («```») تُزال أبكر في
    `_strip_internal_plumbing` (قبل معالجة تسريب JSON) — راجع تعليقها هناك."""
    if not text:
        return text
    return _STRAY_BOLD_RE.sub(
        lambda m: m.group(0) if m.group(0) == _SANCTIONED_BOLD else m.group(1),
        text)


# البند ٢ (تدقيق «تحليل #1» DZA — silk_quality_gate.raw_confidence): رقم ثقة
# عربي خام «ثقة 0.x» متسرّب في السرد رغم حظر عقد الكاتب له صراحة (silk_ai_judge
# deep_report prompt) — شبكة أمان أخيرة، بنفس منطق _EN_CONF_VALUE_RE أعلاه
# للإنجليزية لكن للعربية؛ يستبدل الرقم الخام بعبارة لغوية عبر
# silk_narrative.confidence_phrase (نفس القيمة، عبارة مقروءة — لا اختلاق).
_AR_RAW_CONF_RE = re.compile(r"ثقة\s*[:=]?\s*\(?(0\.\d{1,4})\)?")
# الموجة الرابعة (الدرس ٢٥٧): عند خصوصية أرقام القياس يصير المُصلِحُ **حذفاً**
# لا إعادةَ صياغة — وإلّا أعاد حقنَ «ثقة متوسطة (64%)» في التقرير الذي
# ننظّفه منها (مقيسٌ: المُصلِحُ يُصنِّع التسميةَ ليُرضي حارسَ `raw_confidence`).
# يبتلع البادئةَ («بثقة»/«وثقة») والقوسين المحيطين كي لا يبقى قوسٌ فارغ.
# مراجعة §58 (ثلاث حالاتٍ مُعاد إنتاجها): بلا حدّ كلمةٍ كانت تأكل «درجة ال»
# من «درجة الثقة: 0.8»، وتلتهم قوسَ استشهادٍ لا يخصّها. الآن: البادئاتُ
# («درجة الثقة»/«الثقة»/«بثقة»/«وثقة») تُبتلَع كلمةً كاملةً من حدّها
# (`(?<!\w)`)، والقوسان لا يُحذَفان إلا **متزاوجَين** حول المقطع كلِّه أو حول
# الرقم وحدَه، والفاصلةُ التي تسبق المقطعَ داخل قوسٍ تُبتلَع معه كي لا يبقى «،)».
_CONF_PREFIX = r"(?:درجة\s+)?(?:بال|ال|ب|و)?ثقة\s*[:=]?\s*"
_AR_RAW_CONF_STRIP_RE = re.compile(
    r"\s*[\(（]\s*" + _CONF_PREFIX + r"0\.\d{1,4}\s*[\)）]"          # (ثقة 0.9)
    r"|(?:\s*[،,])?\s*(?<!\w)" + _CONF_PREFIX + r"\(0\.\d{1,4}\)"    # ثقة (0.9)
    r"|(?:\s*[،,])?\s*(?<!\w)" + _CONF_PREFIX + r"0\.\d{1,4}")       # ثقة 0.9


def _ar_conf_repl(m: "re.Match") -> str:
    from silk_narrative import confidence_phrase
    try:
        c = float(m.group(1))
    except ValueError:
        return m.group(0)
    return f"ثقة {confidence_phrase(c)}"


# البند ٥ (تدقيق «تحليل #1» DZA — silk_quality_gate.currency_label_mismatch):
# عمود سعر يَعِد بعملة غير التي رُصدت فعلاً ("السعر/كجم بالدولار" بينما
# الصفوف تحمل €/يورو) — وعدُ تحويلٍ لم يُجرَ، بلاغٌ حيّ حقيقي (لا تسريب
# سرّية). الإصلاح يُعنوِن العمود بالعملة **المرصودة فعلاً** بدل حذف الصفّ أو
# اختلاق تحويل (لا سعر صرف بين الحقائق).
_PRICE_HEADER_CUR_RE = re.compile(r"(السعر[^\n|]{0,20}?)(بالدولار|\bUSD\b)")
_OTHER_CUR_RELABEL = (
    ("باليورو", re.compile(r"باليورو|\bEUR\b|€|يورو")),
    ("بالجنيه الإسترليني", re.compile(r"بالجنيه|\bGBP\b|£|جنيه إسترليني")),
)


def _fix_price_column_currency_label(text: str) -> str:
    """عنوِن عمود السعر بالعملة المرصودة فعلاً في متن التقرير نفسه، لا
    باليورو/الدولار حسب الترويسة وحدها. إن لم تظهر عملة أخرى غير الموعودة في
    الترويسة، لا تغيير (لا مؤشّر مطابَق سلباً — نفس منطق الاكتشاف في
    silk_quality_gate._check_currency_label_mismatch).

    البحث عن العملة الأخرى **يقتصر على نافذة الجدول نفسه** (من الترويسة حتى
    أول سطر فارغ) — لا كامل المستند. بلاغ حي (Master Prompt Part 2، تدقيق
    عيّنة تقرير العميل): بحثٌ على كامل النص كان يُعنوِن عمود سعرٍ مطبَّعٍ
    بالدولار عمداً بـ«باليورو» لمجرّد أنّ قسماً آخر تماماً (نقاش خطر صرف
    العملة، «اليورو هو عملة السوق نفسها») يذكر اليورو — نفس مبدأ نافذة
    الجدول في silk_quality_gate._check_currency_label_mismatch (LESSONS ٤٢)
    لم يكن مطبَّقاً هنا في دالة الإصلاح الشقيقة."""
    if not text:
        return text
    m = _PRICE_HEADER_CUR_RE.search(text)
    if not m:
        return text
    block_end = text.find("\n\n", m.end())
    block_end = block_end if block_end != -1 else len(text)
    block = text[m.start():block_end]
    for label, pat in _OTHER_CUR_RELABEL:
        if pat.search(block):
            return text[:m.start()] + m.group(1) + label + text[m.end():]
    return text


def _extract_or_gap(blob: str) -> str:
    """استخرج قيمة مفتاح مقروء من تفريغ JSON، وإلا فجوة معلنة — لا JSON خام
    يُعرَض إطلاقاً. `reasoning` أولاً (تعليل الحكم المسرَّب)، ثم مفاتيح البعثة
    الشائعة (claim/summary/value/note)."""
    try:
        obj = json.loads(blob)
    except Exception:  # noqa: BLE001 — تفريغ مشوَّه أيضاً غير قابل للعرض خاماً
        return _RAW_JSON_GAP
    if isinstance(obj, dict):
        for key in ("reasoning", "claim", "summary", "value", "note"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return _RAW_JSON_GAP


def _neutralize_datapoint_repr(m: "re.Match") -> str:
    """استبدل ريبر DataPoint(...) كاملاً بقيمته المقروءة، أو فجوة معلنة إن
    كانت None/فارغة (عقد عدم الاختلاق — لا نخترع قيمة لنقطة بلا قيمة)."""
    v = m.group("v").strip()
    if (v[:1] == "'" and v[-1:] == "'") or (v[:1] == '"' and v[-1:] == '"'):
        v = v[1:-1]
    v = v.strip()
    if not v or v == "None":
        return _RAW_JSON_GAP
    return v


def _strip_raw_json_leak(text: str | None) -> str | None:
    """استبدل تفريغ JSON خام بنص عربي مقروء أو فجوة معلنة — بلاغ حي
    (بعثة risk_news أعادت `{"claim": "..."}` حرفياً كملخّص، وحكم كلود
    وصل الواجهةَ كـ`{"verdict":...}` مسيَّجاً بـ"json" أو مضمَّناً خلف بادئة).
    يعالج ثلاثة أشكال فاتت الإصدار المُرسَّى القديم: سياج شيفرة، JSON
    مضمَّن، ولاحقة عدّ أدوات داخلية. نص عادي لا يحمل بنية JSON يمر كما هو."""
    if not text:
        return text
    # (١) أزل لاحقة عدّ الأدوات الداخلية ("... | tool calls: 2").
    out = _TOOL_CALLS_SUFFIX_RE.sub("", text)
    # (٢) أزل سياج الشيفرة (```json / json) قبل كائن JSON إن وُجد.
    if _JSON_FENCE_RE.search(out):
        out = _JSON_FENCE_RE.sub("", out).strip()
    # (٣) النص كلّه JSON — استخرج قيمة مقروءة أو أعلن فجوة (السلوك القائم).
    if _WHOLE_JSON_RE.match(out):
        return _extract_or_gap(out)
    # (٤) JSON مضمَّن خلف/أمام نص، يحمل علامة بنية داخلية — استبدل مجاله
    #     { .. } بقيمة مقروءة/فجوة مع الحفاظ على أي نص عربي سليم حوله.
    if any(m in out for m in _INTERNAL_JSON_MARKERS):
        i, j = out.find("{"), out.rfind("}")
        if i != -1 and j > i:
            out = (out[:i] + _extract_or_gap(out[i:j + 1]) + out[j + 1:]).strip()
    return out


def _mission_label(key: str) -> str:
    """اسم البعثة التجاري بالعربية — نفس الاسم الذي تعرضه لوحة إعدادات
    الوكلاء (silk_missions.MISSIONS[key]['name']) بدل المفتاح snake_case
    الخام أو agent_name الداخلي ("LLMAgent:<key>")."""
    try:
        from silk_missions import MISSIONS
        row = MISSIONS.get(key)
        if row and row.get("name"):
            return row["name"]
    except Exception:  # noqa: BLE001 — تسمية تجميلية لا شرط عرض
        pass
    return key.replace("_", " ")


_MISSION_KEYS_RE = None


def _map_mission_keys(text: str) -> str:
    """استبدل أي مفتاح بعثة داخلي (snake_case) ظاهر في المتن باسمه العربي
    (§2.3) — «(consumer_culture)» → «(ثقافة المستهلك)». يُبنى النمط كسولاً
    من سجل البعثات الواحد (silk_missions.MISSIONS) فلا قائمة يدوية تتقادم؛
    فشل الاستيراد يُعيد النص كما هو (تجميلي لا شرط عرض)."""
    global _MISSION_KEYS_RE
    if _MISSION_KEYS_RE is None:
        try:
            from silk_missions import MISSIONS
            keys = sorted((k for k in MISSIONS if "_" in k), key=len,
                          reverse=True)
            _MISSION_KEYS_RE = (re.compile(
                r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b")
                if keys else re.compile(r"(?!x)x"))
        except Exception:  # noqa: BLE001
            _MISSION_KEYS_RE = re.compile(r"(?!x)x")
    return _MISSION_KEYS_RE.sub(lambda m: _mission_label(m.group(1)), text)


def _category_label(key: str, lang: str = "ar") -> str:
    """اسم تقاطع المحلل الشامل التجاري **بلغة التقرير** — من المعجم الواحد
    `silk_i18n.TERMS["cat_*"]`، وهو نفسُه الذي تُمفصِل عليه بوابة الجودة
    (`silk_quality_gate._check_intersection_insufficiency`)، بدل مفتاح
    إنجليزي خام ("entry_cost") في حدّ معروض للعميل.

    **موجة الخياطة (البند S-08).** كانت التسمية عربيةً واحدةً تُحقَن في
    جملةٍ إنجليزية كما هي («Insufficient evidence for the analyst
    intersection: التنافسية السعرية»)، وحارسُ تسرّب اللغة لا يلتقطها لأنّ
    الشظيّة كلمتان — دون `_MIN_PROSE_WORDS`. اللغةُ تُمرَّر الآن صراحةً؛
    والمعجمُ القديم يبقى احتياطاً رجعياً لا مصدراً ثانياً.
    """
    try:
        import silk_i18n as _i18n
        return _i18n.t(f"cat_{key}", lang)
    except Exception:  # noqa: BLE001 — تسمية تجميلية لا شرط عرض
        pass
    try:
        from silk_market_analyst import _CATEGORY_LABELS
        if key in _CATEGORY_LABELS:
            return _CATEGORY_LABELS[key]
    except Exception:  # noqa: BLE001 — تسمية تجميلية لا شرط عرض
        pass
    return key.replace("_", " ")


def _humanize_gap_note(text: object) -> str:
    """عرّب ملاحظات الحُرّاس/الفجوات الداخلية في سطر حدّ معروض للعميل —
    تفويض للمترجم القانوني الواحد (silk_narrative.translate_gaps /
    INTERNAL_AR): العقود الإنجليزية تبقى كما هي في طبقة البيانات؛
    الترجمة للعرض فقط، لا إعادة صياغة ولا مسّ بالأرقام."""
    from silk_narrative import translate_gaps
    return translate_gaps([text])[0]


_MISSION_KEY_PREFIX_RE = re.compile(r"^([a-z][a-z_]*)(:\s*)")


def _strip_mission_key_prefix(text: str) -> str:
    """بادئة مفتاح بعثة خام أول السطر ("pricing_scout: ...") → الاسم
    التجاري العربي — بلاغ تدقيق: انهيار خيط بعثة يبني الملخّص بـ
    `f"{key}: خطأ غير متوقع: ..."` (silk_missions.py) وهذه البادئة لا
    يلتقطها `_INTERNAL_AGENT_RE` (يطابق "LLMAgent:key" فقط، لا "key:" مجرّدة)."""
    m = _MISSION_KEY_PREFIX_RE.match(text)
    if not m:
        return text
    try:
        from silk_missions import MISSIONS
        if m.group(1) in MISSIONS:
            return _mission_label(m.group(1)) + m.group(2) + text[m.end():]
    except Exception:  # noqa: BLE001 — تسمية تجميلية لا شرط عرض
        pass
    return text


# WP-2 §2 — سقالة «إذن ماذا؟» الحرفية: كانت تعليمة المحلل تفرض ختم كل بند
# بأثره فكتب النموذج العبارةَ نفسها حرفياً داخل القيم فوصلت تقارير عملاء
# مُسلَّمة («إذن ماذا؟ يجب…» ×١٠). التعليمة أُعيدت صياغتها (silk_market_
# analyst) وهذا المُنظِّف شبكة الأمان الحتمية، وبوابة الجودة تُفشِل أي بقايا.
_SO_WHAT_SCAFFOLD_RE = re.compile(
    r"[«\"'()\[]*\s*(?:إذن\s*،?\s*ماذا|So\s+what)\s*[؟?]?\s*[»\"')\]]*\s*[:،—-]*\s*",
    re.I)


def _strip_internal_plumbing(text: str | None,
                             lang: str = "ar") -> str | None:
    """أزل تسريبات السباكة الداخلية من نص معروض للعميل (تقرير مكتوب/حدود
    بحث/ملخّص بعثة) — تفريغ JSON خام كامل يُستبدَل بنص مقروء أو فجوة
    معلنة (`_strip_raw_json_leak`)، "LLMAgent:<key>"/"LLMMissionAgent:
    <key>" وبادئة "<key>: " المجرّدة تُستبدَلان باسم البعثة العربي، ووسوم
    استشهاد خام "dp7"/"[dp7]" تُحذَف، وأسماء الحقول الداخلية الإنجليزية
    (verdict/confidence مع قيمتها العشرية الخامة) تُعرَّب وتُصاغ بشرياً،
    ثم يمرّ النص على `silk_narrative.humanize_technical_note` (نقطة
    التعريب المركزية) لالتقاط أي استثناء بايثون/خطأ HTTP/قالب مصدر متبقٍّ
    لم تلتقطه الأنماط أعلاه. None/فارغ يمر كما هو."""
    if not text:
        return text
    # البند ١ (تدقيق «تحليل #1» DZA): أسوار كود عشوائية («```...```») تُزال
    # **قبل** معالجة تسريب JSON أدناه — وإلا تسبق `_strip_raw_json_leak`
    # فتُزيل أسوار الكود وحدها (فرع (٢) فيها، عام لأي سياج لا JSON فقط)
    # وتترك محتوى الكتلة الخام (مقطع مصدر مقتبَس حرفياً) عارياً كفقرة زائدة.
    text = _CODE_FENCE_RE.sub("", text)
    text = _strip_raw_json_leak(text)
    # لاحقة عدّ نداءات الأدوات العربية (تِلِمتري) — تُجرَّد لسطح العرض؛ التتبّع
    # يقرأ الخام قبل هنا (build_view) فلا يتأثّر عدّ اللوحة (تسريب المشرف #7).
    text = _AR_TOOL_CALLS_RE.sub("", text)
    # حيِّد أيّ ريبر DataPoint(...) **كاملاً** قبل ترجمة الحقول (وإلا نصف-ترجمة):
    # تُستخرَج القيمة المقروءة، أو تُعلَن فجوة إن كانت None/فارغة (لا اختلاق).
    text = _DATAPOINT_REPR_RE.sub(_neutralize_datapoint_repr, text)
    # شبكة أمان: أي DataPoint(...) شاذ نجا من النمط المرن → فجوة معلنة كاملة.
    text = _DATAPOINT_ANY_RE.sub(_RAW_JSON_GAP, text)
    text = _strip_mission_key_prefix(text)
    # تدقيق v2 (تسريب المشرف #6): بادئة «mN_» المرقّمة أمام مفتاح بعثة تُزال
    # قبل تعيين المفاتيح، فيُترجَم المفتاح الباقي لاسمه العربي أدناه.
    text = _MISSION_NUM_PREFIX_RE.sub("", text)
    text = _INTERNAL_AGENT_RE.sub(lambda m: _mission_label(m.group(1)), text)
    # HF2: احذفِ مجموعةَ الاستشهاد «(dp1، dp2)» **كاملةً** قبل الوسم المفرد —
    # وإلّا يبقى «()»/«(/)» هيكلاً فارغاً على وجه العميل (بلاغ قطر). ثمّ اطوِ
    # أيَّ قوسٍ فارغٍ متبقٍّ (نفسُ عائلة النائب الفارغ التي عالجها WS4).
    text = _DP_GROUP_RE.sub("", text)
    text = _DP_TAG_RE.sub("", text)
    text = _EMPTY_CITATION_GROUP_RE.sub("", text)
    # البند 13: فاصلة يتيمة من حقل مصدرٍ فارغ داخل قوسٍ غير فارغ — تُطوى
    # (بعد إزالة الأقواس الفارغة كلياً أعلاه، فلا تولِّد القاعدتان قوساً
    # فارغاً جديداً إلا ويلتقطه تمرير لاحق في نفس العائلة).
    text = _ORPHAN_LEAD_COMMA_RE.sub(r"\1", text)
    text = _ORPHAN_TAIL_COMMA_RE.sub(r"\1", text)
    text = _EMPTY_CITATION_GROUP_RE.sub("", text)
    # الصنف ٢ (موجة عيوب التقرير): المجموعةُ الآمنة على النثر من إصلاح أثرِ
    # الخانة الفارغة — قوسٌ فارغ، فراغٌ مزدوج، فراغٌ قبل علامةِ ترقيم. امتدادٌ
    # لعلاج البند 13 أعلاه بنفس منطقه (لا فاصلةَ يتيمةً تُطبَع أبداً)، ومصدرُ
    # القاعدة واحدٌ يقرؤه الفحصُ أيضاً فلا يتباعد إصلاحٌ عن فحص.
    import silk_i18n as _i18n_tidy
    text = _i18n_tidy.tidy_punctuation(text)
    # البند 23: لغة آلية بناء الملاحق تتحول لصياغة قارئ.
    text = _SYSTEM_MECHANICS_RE.sub(r"\1", text)
    # الصنف ١: «مُصنَّفٌ آلياً» → «مُصنَّفٌ بلا مراجعة بشرية» (المعنى للقارئ).
    text = _AUTO_CLASSIFIED_RE.sub(r"\1\2 بلا مراجعة بشرية", text)
    # §٢ (تدقيق «تحليل #1» DZA): تنسيق «**» شارد + رقم ثقة عربي خام — راجع
    # تعليقات الثوابت أعلاه لماذا لا يُمَسّ "## "/"### ".
    text = _strip_stray_markdown(text)
    if client_metric_privacy():
        text = _AR_RAW_CONF_STRIP_RE.sub("", text)
    else:
        text = _AR_RAW_CONF_RE.sub(_ar_conf_repl, text)
    # §2.3 (أمر العمل الرئيس): مفتاح بعثة داخلي (snake_case) تسرَّب في المتن
    # أو جدول الحكم («(consumer_culture)») يُستبدَل باسمه العربي المعروض.
    text = _map_mission_keys(text)
    # §2.6: «بين الحقائق المتاحة/المعطاة» → لغة موجَّهة للقارئ.
    text = _FACTS_LIST_RE.sub("من المصادر المتاحة", text)
    # §2.7: سرد فشل الأداة → تصريح فجوة بيانات.
    text = _TOOL_FAILURE_RE.sub(
        lambda m: f"لم تتوفّر بيانات {m.group(1)} من المصدر الرسمي وقت "
                  "إعداد التقرير", text)
    # §2: لا ذكر لـ«كلود»/Claude في المُسلَّم.
    text = _CLAUDE_JSON_FAIL_RE.sub("تعذّرت قراءة بيانات هذا البند", text)
    text = _CLAUDE_WORD_RE.sub("التحليل الآلي", text)
    # HF4.1: أزِلِ النصفَ الإنجليزيَّ الداخليَّ من ملاحظة الحكم المبدئيّ (يبقى
    # نظيرُه العربيّ) — لا سلسلةٌ إنجليزيةٌ داخليةٌ تصل متن العميل (§5).
    text = _PRELIM_EN_NOTE_RE.sub("", text)
    # WP-2 §2: سقالة «إذن ماذا؟»/"So what" الحرفية (من تعليمة المحلل
    # القديمة) تُنزَع — الأثر يبقى نثراً مدمجاً؛ العنوان السقالي يُحذَف.
    text = _SO_WHAT_SCAFFOLD_RE.sub("", text)

    def _conf_value(m: "re.Match") -> str:
        from silk_narrative import confidence_phrase
        return f"درجة الثقة{m.group(1)}{confidence_phrase(float(m.group(2)))}"
    # الموجة الرابعة: عند الخصوصية يُحذَف الرقمُ الخام بلا تسميةٍ بديلة
    # (`_client_sanitize` يُنظّف القوسَ الفارغ المتخلّف).
    text = _EN_CONF_VALUE_RE.sub("" if client_metric_privacy() else _conf_value,
                                 text)

    def _ar_conf_value(m: "re.Match") -> str:
        from silk_narrative import confidence_phrase
        raw = m.group(1).translate(_AR_DIGIT_FOLD).replace("٫", ".").replace(",", ".")
        try:
            return f"درجة الثقة {confidence_phrase(float(raw))}"
        except ValueError:
            return "درجة الثقة"
    text = _AR_CONF_RE.sub("" if client_metric_privacy() else _ar_conf_value,
                           text)
    text = _EN_FIELD_RE.sub(lambda m: _EN_FIELD_AR[m.group(1)], text)
    from silk_narrative import humanize_technical_note, verdict_ar
    text = _RAW_VERDICT_RE.sub(lambda m: verdict_ar(m.group(1).upper()), text)
    text = humanize_technical_note(text, lang)
    # §7 (أمر العمل الرئيس — تصحيح التلصيقات المشوَّهة): توسيع رمز الحكم قد
    # يُنتِج تكرار كلمة فوراً («التوصية GO» → «التوصية التوصية بالدخول»).
    # اطوِ أي كلمة (٣ أحرف فأكثر) تكرّرت فوراً بعدها نفسُها.
    text = _DUP_WORD_RE.sub(r"\1", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def _collapse_dead_tables(text: "str | None") -> "str | None":
    """البند 15 (أمر إصلاح المحرّك): جدولٌ أقلُّ من نصف خاناته مملوءة لا
    يُعرَض — يُستبدل بسطرٍ واحد يسمّي الترويسة والناقص (#10: جدول
    TAM/SAM/SOM ثلاثة صفوف كلها «غير متاح»؛ #11: جدول الأسعار كله «يتعذّر
    الحساب»). المعيار والخانة الفارغة نفسهما في حارس البوابة
    (`silk_quality_gate._table_cell_populated`) — مصدر حقيقة واحد."""
    if not text or "|" not in text:
        return text
    from silk_quality_gate import _table_cell_populated
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("|"):
            out.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            j += 1
        block = lines[i:j]
        i = j
        if len(block) < 3:
            out.extend(block)
            continue
        header = [h.strip() for h in block[0].strip().strip("|").split("|")]
        cells: list[str] = []
        missing_cols: set[str] = set()
        for r in block[2:]:
            row = r.strip().strip("|").split("|")
            for idx, c in enumerate(row):
                cells.append(c)
                if not _table_cell_populated(c):
                    missing_cols.add(header[idx].strip()
                                     if idx < len(header) and header[idx].strip()
                                     else f"عمود {idx + 1}")
        populated = sum(1 for c in cells if _table_cell_populated(c))
        if len(cells) >= 4 and populated / len(cells) < 0.5:
            # صيد الفجوات ٣: كان القصّ شريحة خام ([:90]/[:200]) تبتر وسط
            # كلمة بلا إعلان داخل نص عميل — قاعدة «القصّ يُعلَن» (_clip_words).
            head_txt = _clip_words(" / ".join(h for h in header if h), 90)
            out.append(f"غير متاح: جدول «{head_txt}» لم يُعرَض — "
                       f"{len(cells) - populated} من {len(cells)} خانة بلا "
                       "قيمة، والناقص: "
                       + _clip_words("، ".join(sorted(missing_cols)), 200)
                       + ".")
        else:
            out.extend(block)
    return "\n".join(out)


def _sanitize_points(items: list, extra_key: str | None = None) -> list:
    """طهّر قائمة {point, evidence, [extra_key]} — استخلاصات كلود الحرّة
    (ثقافة المستهلك P1، ديناميكيات السوق P2-8) لم تكن تمرّ عبر
    `_strip_internal_plumbing` إطلاقاً رغم أنها نفس نوع النص الحرّ الذي
    قد يردّد وسماً داخلياً رآه كلود في مدخلاته (تسريب تدقيق). `evidence`
    عناوين ويب خارجية مقتبَسة حرفياً — لا تُعدَّل، ليست سباكة داخلية."""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        if "point" in row:
            row["point"] = _strip_internal_plumbing(row.get("point"))
        if extra_key and extra_key in row:
            row[extra_key] = _strip_internal_plumbing(row.get(extra_key))
        out.append(row)
    return out


def _sanitized_dynamics(dynamics: object) -> dict | None:
    """ديناميكيات السوق (P2-8، `silk_ai_judge.classify_dynamics`) مطهَّرة —
    نفس القصور الذي كان في _consumer_culture: قوائم point/evidence حرّة لم
    تمرّ عبر `_strip_internal_plumbing` قط في هذا المسار."""
    if dynamics is None:
        return None
    d = _dp(dynamics)
    v = d.get("value")
    if isinstance(v, dict):
        v = dict(v)
        for key in ("drivers", "restraints", "opportunities", "threats"):
            if key in v:
                v[key] = _sanitize_points(v.get(key))
        if "porter" in v:
            v["porter"] = _sanitize_points(v.get("porter"), extra_key="force")
        if "pestel" in v:
            v["pestel"] = _sanitize_points(v.get("pestel"), extra_key="dimension")
        if v.get("note"):
            v["note"] = _strip_internal_plumbing(v["note"])
        d = {**d, "value": v}
    return d


def _mission_trace_summary(failed: bool, summary: str) -> dict:
    """لوحة تتبّع بلمحة (الموجة ٦، §docs/TUNING.md) — حالة/نداءات أداة/
    بنود مُسقَطة/فجوات، مُستخرَجة من نص ملخّص البعثة (لا تمديد على عقد
    AgentReport — راجع تعليق التصميم في silk_llm_runtime.run_llm_agent)."""
    skipped = "معطّل" in summary
    status = "skipped" if skipped else ("failed" if failed else "succeeded")
    tool_m = _TOOL_CALLS_RE.search(summary)
    dropped_m = _DROPPED_RE.search(summary)
    gaps_m = _GAPS_RE.search(summary)
    gaps_n = len([g for g in (gaps_m.group(1).split("؛") if gaps_m else [])
                 if g.strip()])
    # دورة §58 الثانية: فجواتٌ أسقطها بترُ النافذة (`_gaps_blob` يعلنها
    # مقطعاً مستقلاً «فجوات غير مدرجة: N») تدخل عدَّ اللوحة — كان العدُّ
    # يقرأ المقطعَ المُدرَج وحده فتختفي المُسقَطات من مؤشر صحة البعثة.
    undecl_m = re.search(r"فجوات غير مدرجة:\s*(\d+)", summary)
    if undecl_m:
        gaps_n += int(undecl_m.group(1))
    return {"status": status, "tool_calls": int(tool_m.group(1)) if tool_m else 0,
           "dropped": int(dropped_m.group(1)) if dropped_m else 0,
           "gaps": gaps_n}


def _reconcile_numeric_conflicts(missions: dict, hs_flagged: bool) -> list[dict]:
    """WP-3 §2 — ممرّ مصالحة رقمية قبل العرض، يعمل على بنود نموذج العرض
    (يُعدِّل الوسوم فقط — القيم لا تُمَسّ أبداً، عقد عدم الاختلاق):

    (أ) **قيمة قانونية واحدة لكل رقم**: قيمتان رقميتان كبيرتان (≥ 10000)
        متقاربتان جداً (فرق نسبي ≤ 0.5%) وغير متطابقتين — بلاغ التدقيق:
        6,733,369 مقابل 6,733,376 لواردات 2023 معاً في تقرير واحد — تُحسمان
        لقيمة قانونية (الأعلى ثقةً، فالأولى وروداً)؛ الباقي يُوسَم
        «متعارض — مستبعد» في سجلّ الأدلة، والتعارض يُفصَح عنه مرة واحدة
        (قائمة conflicts المعادة). التقارب الرقمي تقريبٌ مُعلَن لهوية
        (المؤشر، السنة) — لا مطابقة مواضيع بنيوية متاحة عبر البعثات.
    (ب) عند تعليم رمز HS (غير مؤكَّد): بند كومتريد الرقمي يُوسَم «مؤشر
        سياقي» فلا يعرض «✓ موثّق» بينما السرد نفسه يرفضه/يعيد تأطيره.
    (ج) بند جمعه وكيل بحث (وسم tool-use) تسانده قيمة مطابقة من جامعٍ رسمي
        مباشر => `corroborated` (يرفع سقف شارته — silk_narrative)."""
    from silk_narrative import RECONCILED_OUT_TAG, is_agent_gathered
    entries: list[dict] = []
    for m in missions.values():
        for f in (m.get("findings") or []):
            v = f.get("value")
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            entries.append(f)
            if hs_flagged and "comtrade" in str(f.get("source") or "").lower():
                f.setdefault("evidence_tag", "مؤشر سياقي — رمز غير مؤكَّد")
    official_vals = [float(f["value"]) for f in entries
                     if not is_agent_gathered(f.get("source"))]
    for f in entries:
        if is_agent_gathered(f.get("source")):
            fv = float(f["value"])
            if any(abs(fv - ov) <= max(abs(ov), 1.0) * 0.005
                   for ov in official_vals):
                f["corroborated"] = True
    # مراجعة شيفرة PR #147: التقارب الرقمي وحده كان يخاطر بضمّ رقمين لا
    # علاقة بينهما (واردات 6.70م$ وعدد سكان 6.72م مثلاً) فيُستبعَد رقم
    # صحيح بإفصاح تعارضٍ كاذب. تُشترط الآن **هوية سنة معلومة ومتطابقة**
    # (data_year البنيوي أو سنة صريحة في الملاحظة) — بند بلا سنة قابلة
    # للاشتقاق لا يدخل المصالحة أصلاً (تحفّظ: لا حسم بلا هوية).
    def _entry_year(f: dict) -> "int | None":
        dy = f.get("data_year")
        if isinstance(dy, int):
            return dy
        m = re.search(r"(?<!\d)(19\d\d|20\d\d)(?!\d)",
                      f"{f.get('note') or ''}")
        return int(m.group(1)) if m else None

    by_year: dict[int, list[dict]] = {}
    for f in entries:
        if abs(float(f["value"])) < 10000:
            continue
        yr = _entry_year(f)
        if yr is not None:
            by_year.setdefault(yr, []).append(f)
    conflicts: list[dict] = []
    for _yr in sorted(by_year):
        _cluster_year_group(by_year[_yr], conflicts)
    return conflicts


def _cluster_year_group(group: "list[dict]", conflicts: "list[dict]") -> None:
    """عنقدة قيم سنةٍ واحدة بالتقارب النسبي (≤0.5%) — جزء ممرّ المصالحة."""
    from silk_narrative import RECONCILED_OUT_TAG
    big = sorted(group, key=lambda f: float(f["value"]))
    i = 0
    while i < len(big):
        base = float(big[i]["value"])
        cluster = [big[i]]
        j = i + 1
        while j < len(big) and \
                abs(float(big[j]["value"]) - base) <= abs(base) * 0.005:
            cluster.append(big[j])
            j += 1
        distinct = sorted({float(f["value"]) for f in cluster})
        if len(distinct) > 1:
            canonical = max(
                cluster, key=lambda f: float(f.get("confidence") or 0.0))
            cv = float(canonical["value"])
            for f in cluster:
                if float(f["value"]) != cv:
                    f["evidence_tag"] = (
                        f"{RECONCILED_OUT_TAG} — القيمة القانونية المعتمدة "
                        f"{canonical['value']}")
            conflicts.append({
                "canonical_value": canonical["value"],
                "canonical_source": canonical.get("source"),
                "rejected_values": [v for v in distinct if v != cv],
                "note": ("رُصدت قيمتان متقاربتان غير متطابقتين لما يبدو "
                         f"المؤشر نفسه؛ اعتُمدت {canonical['value']} "
                         "(الأعلى ثقة) واستُبعد الباقي موسوماً "
                         f"«{RECONCILED_OUT_TAG}».")})
        i = j


def _mission_gap_lines(name: str, summary: str) -> list[str]:
    """فجوات بعثة معلنة داخل ملخّصها — كل بعثة، لا الفاشلة (صفر نتائج) فقط.

    بعثة قد "تنجح" (نتائج مبنية على استشهاد ≥١) وتُصرّح بفجوات جزئية داخل
    نفس الملخّص («فجوات: لا بيانات أسعار؛ لا بيانات مخاطر») — كانت هذه
    الفجوات غير مرئية لقسم «حدود التقرير» لأن التجميع القديم فحص `failed`
    فقط. إصلاح مراجعة حية: أي فجوة مُعلَنة في أي مكان يجب أن تظهر هنا.
    """
    m = _GAPS_RE.search(summary or "")
    if not m:
        return []
    # D3 (دراسة #12): شظيةُ فجوةٍ تنتهي بـ«…» بترٌ سابقٌ وصل المخزن —
    # تُسقَط دفاعياً (نصُّ البند 12: امنع البتر أو أسقِط السطر). المنبعُ
    # مُصلَحٌ أيضاً (`silk_llm_runtime._gaps_blob` يبتر عند حدّ «؛»).
    return [f"{name}: {g.strip()}" for g in m.group(1).split("؛")
            if g.strip() and not g.strip().endswith(("…", "..."))]


# ── PART B1: مصالحة حدود البعثة مع الحقائق النهائية + قصّ آمن للجملة ────────
_FIRST_CLAUSE_RE = re.compile(r"^(.*?[.؟!،؛])\s")
# مواضيع فجوات البعثات القابلة للحسم بحقيقة بعثة أخرى — كل موضوع:
#   gap_keywords: كلمات تُميّز سطر الحدّ (لأيّ موضوع ينتمي).
#   need_kw_in_fact: هل يلزم أن يحمل بند الحقيقة كلمةَ الموضوع نفسها بجانب
#     الدليل (للحصص/التعريفة نعم — تفادياً لأن يحسم أيّ % عائم فجوةَ حصص).
#   evidence_re: نمط الدليل الرقمي الذي يجب أن يظهر في **بندٍ واحد**.
# تحفّظ صارم: لا يُحسَم حدٌّ إلا بدليل صريح مطابق الموضوع (عقد عدم الاختلاق).
#
# تشديد C-1 (تدقيق 2026-07-20، عائلة البند ١٢): موضوع «الأسعار» كان
# need_kw_in_fact=False بنمطٍ يلتقط **العملةَ وحدَها** (رقم+$/€/دولار)، على
# افتراضٍ خاطئ أن «العملة تُعرّف السعر بلا كلمة سعر». لكنّ العملةَ وحدَها لا
# تُميّز سعرَ تجزئةٍ عن قيمةٍ تجاريّة (حجم سوق/واردات/قيمة طلب كلّها بالعملة)،
# فبندُ «$129.6 مليون واردات» كان يحسم فجوةَ «تسعير المنافسين غير مرصود»
# كذباً — إخفاء فجوةٍ حقيقية على سطر حدٍّ للعميل. الذي يُعرّف سعرَ التجزئة هو
# **العملة + وحدةُ سعرٍ** (‏/كجم، للكيلو، €/kg)؛ فصار الدليلُ يشترط اجتماعهما.
_PRICE_MONEY = r"(?:€|\$|£|ريال|يورو|دولار|درهم)"
_PRICE_PER_UNIT = r"(?:كجم|كغم|كغ|كيلوغرام|كيلو|للكيلو|لتر|وحدة|عبوة|kg|g|l)"
_LIMIT_TOPICS = [
    {"name": "حصص",  # حصص المورّدين وتركّزهم (الحالة الحيّة: 3.39%/55.28%/HHI)
     "gap_keywords": ("حصص", "حصة", "مورّد", "مورد", "موردين", "الموردين",
                      "شركاء", "المصدّرين", "hhi", "تركّز"),
     "need_kw_in_fact": True,
     "evidence_re": re.compile(r"\d+(?:[.,]\d+)?\s*%|\bHHI\b", re.I)},
    {"name": "أسعار",  # سعر المنافسين/التجزئة = عملة **+ وحدة سعر** (لا عملة وحدها)
     "gap_keywords": ("سعر", "أسعار", "تسعير", "التجزئة"),
     "need_kw_in_fact": False,
     "evidence_re": re.compile(
         # رقم … عملة [/] وحدة  (9.96 يورو/كجم، 6.20–9.80 يورو/كغم، 3.20 دولار للكيلو)
         r"\d[\d.,–—\s-]*" + _PRICE_MONEY + r"\s*/?\s*" + _PRICE_PER_UNIT
         # عملة رقم / وحدة  (€3.49/kg، £2.40 / kg)
         + r"|" + _PRICE_MONEY + r"\s*\d[\d.,]*\s*/\s*" + _PRICE_PER_UNIT,
         re.I)},
    {"name": "تعريفة",  # التعريفة الجمركية (نسبة + كلمة تعريفة/رسوم)
     "gap_keywords": ("تعريفة", "جمرك", "رسوم", "tariff"),
     "need_kw_in_fact": True,
     "evidence_re": re.compile(r"\d+(?:[.,]\d+)?\s*%")},
]


def _first_clause(text: str, max_len: int = 180) -> str:
    """أول جملة/شبه-جملة من نصّ — يمنع تضمين ملخّص طويل (≤٧٠٠ محرف) في سطر
    حدٍّ تعيد طبقة docx قصّه عند ٣٠٠ منتصفَ جملة بـ«…». يقطع عند أول علامة
    وقف؛ وإلا عند حدّ متحفّظ بحدود الكلمة (بلا «…» وسط جملة)."""
    s = str(text or "").strip()
    if not s:
        return s
    m = _FIRST_CLAUSE_RE.match(s + " ")
    if m and len(m.group(1)) <= max_len + 40:
        return m.group(1).strip()
    if len(s) <= max_len:
        return s
    cut = s[:max_len].rsplit(" ", 1)[0].strip()
    return cut or s[:max_len].strip()


def _final_fact_texts(missions: dict, by_category: dict) -> list[str]:
    """قائمة نصوص البنود النهائية (قيمة+ملاحظة كل بند) من كل البعثات
    والتقاطعات — كل عنصر بندٌ واحد كي يُشترَط اجتماع الموضوع والرقم فيه."""
    out: list[str] = []
    for v in (missions or {}).values():
        if not isinstance(v, dict):
            continue
        for f in (v.get("findings") or []):
            out.append(f"{f.get('value')} {f.get('note') or ''}")
    for dps in (by_category or {}).values():
        for f in (dps or []):
            out.append(f"{f.get('value')} {f.get('note') or ''}")
    return out


def _topic_resolved(gap_line: str, fact_texts: list[str]) -> "str | None":
    """اسم الموضوع إن كان سطر الحدّ محسوماً بدليل رقمي فعلي، وإلا None.
    الحسم: سطر الحدّ ينتمي لموضوع، وبندُ حقيقةٍ يحمل دليل ذلك الموضوع
    (نمطه الرقمي، ومعه كلمة الموضوع حين need_kw_in_fact). متحفّظ عمداً."""
    low = gap_line.lower()
    for topic in _LIMIT_TOPICS:
        kws = topic["gap_keywords"]
        if not any(k in low for k in kws):
            continue
        for t in fact_texts:
            if not topic["evidence_re"].search(t):
                continue
            if topic["need_kw_in_fact"] and not any(k in t.lower() for k in kws):
                continue
            return topic["name"]
    return None


def _reconcile_mission_limits(lines: list[str],
                              fact_texts: list[str]) -> list[str]:
    """PART B1: أعد وسم كل سطر حدٍّ مشتقٍّ من بعثة حُسم لاحقاً بدليل رقمي
    فعلي في الحقائق النهائية «حُسمت لاحقاً: …»، وأبقِ الباقي حرفياً (لا
    إخفاء فجوة حقيقية). عقد عدم الاختلاق: لا يُحسَم إلا ما له دليل صريح."""
    out: list[str] = []
    for line in lines:
        if _topic_resolved(line, fact_texts):
            out.append(f"حُسمت لاحقاً (وردت في الحقائق المرصودة): {line}")
        else:
            out.append(line)
    return out


# تصنيف لون/تسمية شارة الحكم — مصدر واحد يستهلكه ثلاثة عارضين (لوحة
# الويب، غلاف docx، خلاصة docx التنفيذية) بدل تكرار نفس المنطق بايثون +
# JS بمعيارين قد يختلفان لنفس الرمز (سدّ تسريب الطبقة ٦: كانت لوحة الويب
# تحسب تصنيفها الخاص من رمز الحكم الإنجليزي الخام وتعرض الرمز نفسه كنص
# ظاهر — silk_reports._verdict_tone/_VERDICT_LABELS_AR كانتا نسخة موازية).
_NEGATIVE_ENTRY_HINT_RE = re.compile(
    r"(?:لا|غير|عدم|تأجيل|تجنّب|تجنب)[^\n]{0,15}دخول")
def _verdict_tone(vtxt: object) -> str:
    """تصنيف لون شارة الحكم — go (أخضر)/conditional (مشروط، أخضر مزرقّ)/
    watch (كهرماني)/nogo (أحمر)/unknown (رمادي).

    بلاغ حي (مراجعة المالك على نموذج تقرير العميل): CONDITIONAL-GO كان
    ينهار إلى tone=watch فتعرض الشارة «مراقبة السوق» بينما متن التقرير
    يقول «دخول مشروط» — تناقض على الصفحة الأولى. صار للحكم المشروط tone
    مستقل بتسميته الخاصة («دخول مشروط»، مطابقة لـsilk_narrative.VERDICT_AR)
    فتتّفق الشارة مع المتن. CONDITIONAL قبل GO (يحوي الرمز كليهما) وقبل
    WATCH (لا يحوي WATCH أصلاً)."""
    # ── الموجة Z · البند Z-02 — دورةٌ مغلقة للتصنيف المُصالَح ─────────────
    # مفتاحُ تصنيفٍ يُمرَّر كما هو يعود كما هو. بهذا يستطيع أيُّ مُنادٍ أن
    # يُمرِّر التصنيفَ **المُصالَح** (`view["deep_research"]["verdict_tone"]`)
    # في موضع الرمز الخام فيصل كلَّ مواضع العرض بلا مسارِ اشتقاقٍ ثانٍ.
    # ولا تعارض: لا مُصدِرَ حكمٍ يُخرِج «data_complete» رمزاً خاماً، و«nogo»
    # المجرّدة كانت تُقرأ خطأً `go` قبل هذا الفرع (تحوي «GO»).
    if str(vtxt) in _VERDICT_LABELS_AR:
        return str(vtxt)
    t = str(vtxt or "").upper()
    if "NO-GO" in t or "NO GO" in t:
        return "nogo"
    # «مبدئي وناقص البيانات» حكمٌ حتميٌّ صادر فعلاً، لا غيابَ حكم (بلاغ
    # المالك: كتلة SWOT تحمل توصيةً كاملة والشارة تقول «تعذّر إصدار توصية»).
    # `JuryCommittee.evaluate` تُصدر «PRELIMINARY / INCONCLUSIVE» كلّما فشل
    # وكيلٌ/بعثةٌ واحدة مع بقاء نتائج حقيقية — ولم يكن لها فرعٌ هنا فتنهار
    # إلى unknown. فشلُ نداءٍ واحد يُنقِص التغطية؛ لا يمحو الحكم.
    if "INCONCLUSIVE" in t:
        return "inconclusive"
    # PR A §A2 (بلاغ تحليل ٧): «PRELIMINARY GO» نغمةٌ مستقلّة لا تنهار إلى go —
    # وإلا عرض الغلاف «التوصية بالدخول» بينما الكاتب (verdict_ar) استلم «توصية
    # أولية بالدخول»، فتناقضت الصفحة الأولى مع المتن. قرار المالك: «توصية
    # أولية بالدخول» على كل سطح. تُفحَص قبل فرع «GO» المجرّد (الرمز يحوي GO).
    if "PRELIMINARY" in t and "GO" in t and "NO-GO" not in t and "NO GO" not in t:
        return "preliminary"
    if "CONDITIONAL" in t:
        return "conditional"
    if "WATCH" in t:
        return "watch"
    if "GO" in t:
        return "go"
    # Master Prompt Part 2 §B: بعض مسارات الحكم (نداء كلود المرحلة الثانية،
    # أو مدوّناتٌ يضبطها مستدعٍ) قد تضع التسمية **العربية** مباشرةً بدل
    # الرمز الإنجليزي (`ai["verdict"] = "دخول مشروط"` لا "CONDITIONAL-GO") —
    # كانت تنهار سابقاً إلى "unknown" فتعرض الشارة «تعذّر إصدار توصية» بينما
    # المتن/الجدول يذكران التسمية العربية الصحيحة، وهو بالضبط تناقض الشارة/
    # المتن الذي صُمِّمت هذه الدالة أصلاً لمنعه (بلاغ ٢٠٢٦-٠٧-٢١ أعلاه).
    # نفس ترتيب الفحص (الأخصّ أولاً): «مشروط» قبل «الدخول» المجرّدة لأن
    # «دخول مشروط» تحوي كلمة «دخول» أيضاً.
    s = str(vtxt or "")
    if "عدم الدخول" in s:
        return "nogo"
    if "غير محسوم" in s or "غير محسومة" in s:
        return "inconclusive"
    if "مشروط" in s:
        return "conditional"
    # PR A §A2: تسميةُ «توصية أولية بالدخول» العربية مباشرةً (مسارٌ يضع التسمية
    # بدل الرمز) — تُصنَّف preliminary لا go، فلا تنهار «أولية» فيتناقض الغلاف.
    if "أولية" in s and ("دخول" in s):
        return "preliminary"
    if "مراقبة" in s:
        return "watch"
    # مراجعة الشيفرة: «دخول» المجرّدة بلا سياق نفي تُصنَّف go افتراضياً —
    # لكن نفياً/تأجيلاً بصياغةٍ غير «عدم الدخول» الحرفية («لا يُنصح بالدخول»،
    # «تأجيل الدخول») كان سيُقلَب زوراً إلى go. نمطٌ إضافي يلتقط ألفاظ النفي
    # الشائعة قبل «دخول» ضمن نافذة قصيرة قبل الرجوع لـgo.
    if _NEGATIVE_ENTRY_HINT_RE.search(s):
        return "nogo"
    if "الدخول" in s or "دخول" in s:
        return "go"
    return "unknown"


# تسميات الحكم بالعربية مصنَّفةً بالـtone — مطابقة لـsilk_narrative.VERDICT_AR
# (المترجم القانوني الواحد): conditional=«دخول مشروط» تحديداً، لا «مراقبة
# السوق» (بلاغ مراجعة المالك: الشارة كانت تخالف المتن).
_VERDICT_LABELS_AR = {"go": "التوصية بالدخول", "conditional": "دخول مشروط",
                      # PR A §A2: حكمٌ إيجابيٌّ مبدئيّ بتغطيةٍ ناقصة — تسميةٌ
                      # مستقلّة يتّفق عليها الغلاف والكاتب (قرار المالك).
                      "preliminary": "توصية أولية بالدخول",
                      "watch": "مراقبة السوق", "nogo": "عدم الدخول حالياً",
                      # حكمٌ حتميٌّ صادر بتغطيةٍ ناقصة — ليس غيابَ حكم.
                      "inconclusive": "نتيجة مبدئية — غير محسومة",
                      # «unknown» محجوزةٌ الآن لغيابِ الحكم الحتمي كلياً فقط.
                      "unknown": "تعذّر إصدار توصية",
                      # **الموجة B (البند V-01) — نبراتُ حالةِ الأدلة.**
                      # تُستعمَل حصراً حين يكون أساسُ الحكم «تغطيةَ أدلة» لا
                      # تقييمَ سوق (`JuryCommittee` على المسار العميق). لا
                      # تمسّ تسمياتِ `/analyze` أعلاه بحرف: هناك يصدر الحكمُ
                      # من محرّك القرار الموزون فتسميتُه التجارية صادقة.
                      "data_complete": "اكتمل البحث — لم يصدر تقييمٌ تجاريّ بعد",
                      "data_partial": "بحثٌ ناقص — بعض المصادر لم تُجِب",
                      "data_absent": "تعذّر البحث — لا بيانات كافية لأيّ حكم"}

# ترجمةُ نبرةٍ تجاريةٍ إلى نظيرتها في حالة الأدلة، حين يكون الأساسُ تغطيةً.
_COVERAGE_TONE = {"preliminary": "data_complete",
                  "inconclusive": "data_partial",
                  "nogo": "data_absent"}

# الرمزُ المُعدَّد من المنتِج ← نبرةُ حالة الأدلة (V-02) — بلا مطابقةِ نصّ.
_STATE_TONE = {"coverage_full": "data_complete",
               "coverage_partial": "data_partial",
               "coverage_none": "data_absent"}


def _coverage_basis_tone(tone: str, verdict: object) -> str:
    """حوِّل النبرةَ إلى نظيرةِ **حالةِ الأدلة** حين يُعلن الحكمُ أساسَه تغطية.

    الشرطُ صريحٌ من المنتِج (`verdict["basis"] == "data_coverage"`) لا استنتاجٌ
    من شكل النصّ: حكمٌ صادرٌ عن محرّك القرار الموزون يحتفظ بتسميته التجارية
    كما كان تماماً، وحكمٌ صادرٌ عن عدّاد تغطيةٍ يُسمّى بما هو.
    """
    if not isinstance(verdict, dict):
        return tone
    if str(verdict.get("basis") or "") != "data_coverage":
        return tone
    # **الموجة D (البند V-02).** الرمزُ المُعدَّد يسبق استنتاجَ النبرة من النصّ.
    #
    # `JuryCommittee` يُصدِر سلسلةً مختلطة («NO-GO (insufficient data) — قرار
    # مؤجّل…») كان يفكّكها **مفكّكان مستقلّان بمطابقةٍ نصّية فرعية** — فقد يظهر
    # الحكمُ الواحد بنبرتين حسب أيّهما وصله أوّلاً، وتغييرُ حرفٍ في العبارة
    # يكسر أحدَهما بصمت. الآن `coverage_state` بنيويّ، والمطابقةُ النصّية
    # تبقى احتياطاً للسجلّات المخزَّنة قبل هذه الموجة.
    state = str(verdict.get("coverage_state") or "")
    if state in _STATE_TONE:
        return _STATE_TONE[state]
    return _COVERAGE_TONE.get(tone, tone)


def _verdict_label(tone: str, lang: str = "ar") -> str:
    """تسمية الحكم بلغة التقرير — نفس التصنيف الحتمي، تسميتان (الموجة ٠).

    اللغة **شأن عرضٍ لا شأن حكم**: `tone` يخرج من `_verdict_tone` وحده مهما
    كانت اللغة، فالحكم الذي يقرأه المصنع العربي هو حرفياً الحكم الذي يقرأه
    المصنع الإنجليزي — التسمية وحدها تختلف. العربية تبقى من `_VERDICT_LABELS_AR`
    (المصدر الواحد الذي تقفله اختباراتٌ قائمة)، والإنجليزية من قاموس المصطلحات
    القانوني `silk_i18n.TERMS` فلا لفظَ إنجليزيّ يُكتب في موضع الاستعمال.
    """
    import silk_i18n
    if silk_i18n.normalize(lang) == "ar":
        return _VERDICT_LABELS_AR[tone]
    return silk_i18n.t(f"verdict_{tone}", "en")


# §1 (أمر العمل الرئيس): أنماط توحيد العملة — العملة بالدولار حصراً.
#   _SAR_PAREN_RE: مقابل ريالي مُقوَّس («(نحو 228.8 مليون ريال بسعر الربط 3.75)»
#     أو أي «(... ريال ...)» رقمي) — يُزال بالكامل، لا تحويل عملة في التقرير.
#   _USD_SHORT_*_RE: الاختزال «61م$» / «2.1 مليار$» → الصيغة الكاملة بالدولار.
_SAR_PAREN_RE = re.compile(
    r"\s*\((?:نحو|حوالي|قرابة|~|≈)?\s*[\d.,]+\s*(?:مليون|مليار|ألف|الف)?\s*"
    r"ريال[^)]*\)")
_USD_SHORT_MLN_RE = re.compile(r"(\d[\d.,]*)\s*م\s*\$")
_USD_SHORT_BLN_RE = re.compile(r"(\d[\d.,]*)\s*مليار\s*\$")

# §F-2 (حزمة الفكس v2.1) — بلاغ حي: كلا التعريبين «غوغل» و«قوقل» شُحنا في
# نفس التقرير (الكاتب يستعمل أيّهما بلا اتساق). تعريبٌ واحد قياسي — «قوقل»
# (المستعمَل فعلاً في كل شيفرة المشروع، silk_gmaps.py وأخواتها).
_GOOGLE_TRANSLIT_RE = re.compile(r"غوغل")

# §D-5 (حزمة الفكس v2.1) — بلاغ حي: «بنسبة .%68» (نقطة فاصلة قبل علامة
# النسبة قبل الرقم — ترتيبٌ معكوس). الصيغة الصحيحة دوماً رقمٌ ثم «%» ثم
# (اختيارياً) نقطة ختام جملة. أيّ نقطة ملاصقة لـ«%» **قبلها** بلا رقمٍ
# بينهما، أو «%» متبوعة بنقطة فرقمٍ آخر، خطأ تنسيقٍ لا صيغة شرعية.
_STRAY_PERCENT_RE = re.compile(r"\.\s*%\s*(\d+(?:\.\d+)?)")


def _fix_stray_percent_punctuation(text: str) -> str:
    """أصلح ترتيب «نقطة-نسبة-رقم» المعكوس إلى «رقم-نسبة-نقطة» الصحيح."""
    return _STRAY_PERCENT_RE.sub(r"\1%.", text)


# PR B §B9 (بلاغ تحليل ٧): HHI يُعرَض «7743.7» بدقّة عشرية مختلَقة رغم أن
# المقياس (0-10000 بعد الضرب) رقمٌ صحيح. القيمةُ المخزَّنة صحيحةٌ (نسبة 0.774
# أو عدد صحيح 7743)، لكنّ الكاتب يُعيد اشتقاقها من حصص المورّدين الخام فيُنتِج
# عشريةً وهميّة. حارس البوابة `hhi_false_precision` كان يرصدها بلا إصلاح؛ هذا
# مُصلِحُ عرضٍ حتميّ يقرّبها إلى صحيحٍ قبل وصول النص، فتُصبح النتيجةُ قابلةً
# للإصلاح فعلاً (نفس نمط `_fix_price_column_currency_label`).
_HHI_DECIMAL_FIX_RE = re.compile(r"(HHI[^0-9\n]{0,10})(\d{3,5}\.\d+)")


def _fix_hhi_false_precision(text: str) -> str:
    """قرِّب أيّ «HHI … NNNN.d» إلى عددٍ صحيح (المقياس 0-10000 لا يحمل عشرية)."""
    if not text:
        return text

    def _round(m: "re.Match") -> str:
        try:
            return m.group(1) + str(round(float(m.group(2))))
        except ValueError:
            return m.group(0)

    return _HHI_DECIMAL_FIX_RE.sub(_round, text)


# الموجة الرابعة (الدرس ٢٥٨): مبلغٌ بمنازلَ عشريةٍ زائفة — «51,358,600.874»
# رقمُ استيرادٍ بالدولار بثلاث منازل، مصدرُه `sum(vals)` بلا تقريبٍ في أداة
# كومتريد ثم نسخُ الكاتبِ له حرفياً من كتلة الحقائق. الرقمُ **المخزَّن لا
# يُمَسّ**؛ العرضُ وحده يُقرَّب إلى منزلتين (سقفُ `silk_narrative.AMOUNT_MAX_DP`)
# وعقدُ الإسناد يسمح بذلك صراحةً (`silk_evidence_contract.unsupported_numbers`:
# نصفُ آخِر خانة). النطاق: مبلغٌ بفواصل آلافٍ أو بخمس خاناتٍ فأكثر — فلا يمسّ
# نسبةً ولا سعرَ وحدةٍ ولا إحداثيّاً (خاناتها الصحيحة أقلّ).
_AMOUNT_DECIMAL_FIX_RE = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d{5,})\.(\d{3,})(?!\d)")


_APPENDIX_HEADING_RE = re.compile(
    r"^##\s+\d+\.\s*(?:الملاحق|Appendices)\s*$", re.M)


def _fix_amount_false_precision(text: str) -> str:
    """قرِّب أيّ مبلغٍ كبيرٍ بثلاث منازلَ فأكثر إلى منزلتين (عرضٌ لا تخزين) —
    **في المتن دون الملاحق**: الدقّةُ الكاملة هناك مشروعةٌ (نفسُ حدّ
    `silk_quality_gate._split_off_appendix`؛ مراجعة §58)."""
    if not text:
        return text
    m = _APPENDIX_HEADING_RE.search(text)
    if m:
        return _fix_amount_false_precision(text[:m.start()]) + text[m.start():]

    def _round(m: "re.Match") -> str:
        whole, frac = m.group(1), m.group(2)
        try:
            n = round(float(whole.replace(",", "") + "." + frac), 2)
        except ValueError:
            return m.group(0)
        s = f"{n:,.2f}" if "," in whole else f"{n:.2f}"
        return s.rstrip("0").rstrip(".") if "." in s else s

    return _AMOUNT_DECIMAL_FIX_RE.sub(_round, text)


# الدراسة الحية الرابعة (خلية «سوي سويسرا (نستله)»): بتر-ثم-استئناف بكلمة
# واحدة داخل النص المخزون — منطقة عمى معلنة لفحص الازدواج (كلمة واحدة)
# ولقاصّي الدمج. الرقعة عرضية حتمية تفتح المخزون نظيفاً بلا إعادة توليد.
# **النطاق صفوف الجداول حصراً** (C4 موجة #14 — الملاحظة 3): في النثر الحر
# تراكيبُ عربية مشروعة تُطابق التوقيع نفسه («أما أمام المنافسة»، «كان
# كانون الأول») وطيُّها يغيّر المعنى — بتر كاذب أسوأ من ازدواج مرئي (نص
# المُشرِف)؛ والحادثة نفسها خليةُ جدول. **منطقة الإيجاب الكاذب المعلنة**
# (شرط المُشرِف): تركيبٌ مشروع نادر داخل خلية («أهم أهمية») سيُطوى — لذلك
# كل رقعة تُسجَّل (قبل/بعد/الموضع) في اللوج وفي قناة `render_repairs`
# فتبقى قابلة للتدقيق بعد وقوعها، وقائمة الإيقاف تستثني الوظيفية الشائعة.
# **منطقة العمى**: النثر الحر كله خارج الرقعة (المقابل المقصود أعلاه)،
# بادئة أقصر من ثلاثة أحرف («في فيينا») مستثناة، بتر بكلمتين فأكثر شأن
# فحص الازدواج الحاجب، والمسافة أفقية حصراً (طيٌّ عبر السطر يدمج خليتين).
_PREFIX_STUTTER_STOP = frozenset({
    "سوف", "قال", "قالت", "علي", "عبد", "كان", "كانت", "أما", "اما",
    "على", "إلى", "الى", "بين", "عند", "لدى", "حتى", "منذ", "دون",
    "قبل", "بعد", "فوق", "تحت", "نحو", "حول", "مثل", "عبر", "ضمن",
    "خلف", "أمام", "امام", "حين", "إذا", "اذا", "لكن", "ليس", "بات",
    "صار", "ظلّ", "غير", "بلا"})
_PREFIX_STUTTER_RE = re.compile(r"(?<![ء-ي])([ء-ي]{3,})[ \t]+(\1[ء-ي]+)")


def _fix_truncated_prefix_stutter(text: str) -> "tuple[str, list[dict]]":
    """(النص المُرقَّع، سجل الرقع) — «سوي سويسرا» ← «سويسرا» بسجل تدقيق،
    داخل صفوف الجداول (أسطر «|») حصراً."""
    repairs: list[dict] = []
    if not text or "|" not in text:
        return text, repairs

    def _repl(m: "re.Match") -> str:
        first, second = m.group(1), m.group(2)
        if first in _PREFIX_STUTTER_STOP:
            return m.group(0)
        # صفوف الجداول حصراً: سطرُ المطابقة يحمل فاصل خلايا «|».
        s = m.string
        lo = s.rfind("\n", 0, m.start()) + 1
        hi = s.find("\n", m.end())
        line = s[lo:hi if hi != -1 else len(s)]
        if "|" not in line:
            return m.group(0)
        entry = {"before": m.group(0), "after": second, "offset": m.start()}
        repairs.append(entry)
        log.warning("render repair (truncated-prefix stutter) at %d: "
                    "«%s» → «%s»", m.start(), m.group(0), second)
        return second

    return _PREFIX_STUTTER_RE.sub(_repl, text), repairs


# §D-1 (حزمة الفكس v2.1) — «CAGR (متوسط النمو السنوي المركب) — معدل نمو
# سنوي مركب»: الفحص القديم اكتفى بحرف "(" الفوري، ففاته شرح الكاتب بشرطة
# ("CAGR — معدل نمو سنوي مركب") فحقن تعريفاً ثانياً مكرَّراً بالمعنى فوراً.
_AR_DIACRITICS_RE = re.compile(r"[ً-ْٰ]")
_AR_WORD_RE = re.compile(r"[^\W\d_]{3,}", re.U)


def _ar_norm_word(w: str) -> str:
    """تطبيع خفيف لمقارنة الجذر: نزع التشكيل + أداة التعريف «ال» البادئة —
    كافٍ لمطابقة «النمو» بـ«نمو» و«المركّب» بـ«مركب» بلا محلّل صرفي كامل."""
    w = _AR_DIACRITICS_RE.sub("", w)
    if w.startswith("ال") and len(w) > 4:
        w = w[2:]
    return w


def _already_explained_nearby(s: str, end: int, gloss: str) -> bool:
    """هل الكاتب شرح المصطلح فعلاً قرب أول ورود له — قوسٌ فوري (الصيغة
    القديمة الوحيدة المفحوصة) **أو** شرطة/نقطتان متبوعة بعبارة تتقاطع
    معنوياً مع تعريفنا (≥٢ جذر مشترك) — لا شكل ترقيم بعينه فقط."""
    window = s[end:end + 60]
    if window.lstrip().startswith("("):
        return True
    m = re.match(r"\s*[—\-:]\s*(.{0,50})", window)
    if not m:
        return False
    following_words = {_ar_norm_word(w) for w in _AR_WORD_RE.findall(m.group(1))}
    gloss_words = {_ar_norm_word(w) for w in _AR_WORD_RE.findall(gloss)}
    return len(following_words & gloss_words) >= 2


_TERM_DIACRITICS_RE = re.compile("[\u064b-\u0652\u0670\u0640]")
_TERM_ALEF_RE = re.compile("[أإآ]")


def _norm_for_terms(s: object) -> str:
    """تطبيعٌ خفيفٌ لمطابقة مصطلحٍ عربيّ داخل نثرٍ مُشكَّل — حركاتٌ وتطويلٌ
    وهمزاتٌ تُوحَّد (نظيرُ `silk_quality_gate._norm_ar` عند حدّ العرض)."""
    out = _TERM_DIACRITICS_RE.sub("", str(s or ""))
    return _TERM_ALEF_RE.sub("ا", out).replace("ى", "ي").replace("ة", "ه")


def _apply_merchant_language(text: "str | None") -> "tuple[str, list]":
    """B1 (SPEC-v2): نفّذ عقد لغة التاجر حتمياً على سرد التقرير في النموذج
    الواحد. يعيد (النص المشروح، قائمة المسرد) فيرثهما كل مخرَج (md/docx)
    من مصدر واحد: (١) شرح كل مصطلح تقني عند **أول** ورود بين قوسين بالعربية
    (إن لم يشرحه الكاتب)، (٢) توحيد صياغة العملة بالدولار.

    §1 (أمر العمل الرئيس — تحديث تسليم التقرير): العملة تبقى بالدولار كما
    وردت من المصادر بالضبط — **لا تحويل إلى الريال ولا أي مقابل مُقوَّس**
    (يُلغى تسييق B1 الريالي السابق). أي تسييق ريالي كتبه النموذج يُزال،
    والاختزال «م$» يُوحَّد إلى الصيغة الكاملة «مليون دولار». المسرد يُعاد
    **بنية** (لا نصّاً مُذيَّلاً) كي يعرضه كل مُصدِّر صراحةً. يشرح ويوحّد
    الصياغة فقط — لا يغيّر أي رقم ولا يخترع قيمة (عقد عدم الاختلاق)."""
    import re
    from silk_style_contract import GLOSSARY_ORDER
    s = str(text or "")
    if not s.strip():
        return s, []
    # §1: أزل أي مقابل ريالي مُقوَّس (سعر الربط) — العملة تبقى دولاراً حصراً.
    s = _SAR_PAREN_RE.sub("", s)
    # §1: وحِّد الاختزال «م$»/«مليار$» إلى الصيغة الكاملة بالدولار.
    s = _USD_SHORT_MLN_RE.sub(r"\1 مليون دولار", s)
    s = _USD_SHORT_BLN_RE.sub(r"\1 مليار دولار", s)
    # §D-5: أصلح ترتيب «نقطة-نسبة-رقم» المعكوس («بنسبة .%68» → «بنسبة 68%.»).
    s = _fix_stray_percent_punctuation(s)
    # §F-2: تعريبٌ واحد قياسي لـ«Google» — «قوقل» في كل موضع.
    s = _GOOGLE_TRANSLIT_RE.sub("قوقل", s)
    used: list = []
    for term, gloss in GLOSSARY_ORDER:
        m = re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", s)
        if not m:
            continue
        used.append((term, gloss))
        if _already_explained_nearby(s, m.end(), gloss):
            continue  # الكاتب شرحه فعلاً (قوس أو شرطة) — لا تكرار (§D-1)
        s = s[:m.end()] + f" ({gloss})" + s[m.end():]
    s = re.sub(r"[ \t]{2,}", " ", s)

    # الصنف ٤ (موجة عيوب التقرير): مصطلحاتٌ **عربية** تُستعمَل بلا تعريف
    # (المرآة، عتباتُ التركّز، سعرُ الحدود، نسبةُ التحقّق). `GLOSSARY_ORDER`
    # مبنيٌّ على اختصاراتٍ لاتينية فلا يبلغها. التعريفُ يُضاف **إلى المسرد
    # نفسه** حين يَرِد المصطلح — لا مسارَ عرضٍ ثانٍ، ولا شرحٌ مقحومٌ وسطَ
    # الجملة (يحظره `PLAIN_LANGUAGE_RULE`، وهو بعينه عيبُ «مؤشر التركّز HHI
    # (مؤشر يقيس تركّز السوق…)» الذي رصده الصنف ٢).
    from silk_style_contract import METHODOLOGY_DEFINITIONS_ORDER
    _plain = _norm_for_terms(s)
    for term, definition in METHODOLOGY_DEFINITIONS_ORDER:
        if _norm_for_terms(term) in _plain:
            used.append((term, definition))

    seen: dict = {}
    # **إزالةُ تكرارِ التعريف لا المصطلح**: «نسبة التحقّق» و«نسبة التحقق»
    # هجاءان لمصطلحٍ واحد (مفاتيحُ مطابقةٍ لا مصطلحاتٌ مستقلّة)، وإدراجُهما
    # يُظهِر التعريفَ نفسَه مرّتين في مسردٍ واحد — وهو بعينه عيبُ التكرار
    # الذي تسدّه هذه الموجة.
    by_gloss: dict = {}
    for term, gloss in used:
        if gloss in by_gloss:
            continue
        by_gloss[gloss] = term
        seen.setdefault(term, gloss)

    def _pos(term: str) -> int:
        i = _plain.find(_norm_for_terms(term))
        return i if i >= 0 else len(_plain)

    glossary = [{"term": t, "gloss": g}
                for t, g in sorted(seen.items(), key=lambda kv: _pos(kv[0]))]
    return s, glossary


# القاعدة العامة (قرار المالك — التقادُم من المصدر لا النثر، مراجعة الشيفرة
# #1/#2/#3/#5): الآلية **الأساسية** توسيمُ سنوات الحقائق المتقادِمة المعروفة من
# البيانات (`silk_staleness.stale_fact_years`) أينما وردت، فلا تفلت أيّ صياغة
# («في 2013»/«2013م»/…) ولا يُوسَم رمزُ HS (2008) لأنه ليس سنة حقيقة. التعبير
# النمطي أدناه **شبكة أمان أخيرة** فقط: سياق بيانات صريح (بين قوسين، أو كلمة
# زمنية مسبوقة بفاصل حتى لا تُطابَق داخل كلمة مثل «الطعام» — مراجعة الشيفرة #1).
# البند 14: «منذ» أُخرجت من كلمات السياق الزمني — «العامل منذ 1991» سنةُ
# تشغيلٍ ساكنة لا سنةُ بيانات («منذ عام 2013» تبقى ملتقطة عبر «عام»).
_DATA_YEAR_CTX_RE = re.compile(
    r"\((19\d\d|20\d\d)\)"                                       # بين قوسين: (2013)
    r"|(?:^|[\s(،؛:])(?:عام|سنة|لعام)\s+(19\d\d|20\d\d)(?![\d/])")  # كلمة زمنية بفاصل، بحدّ يمينيّ (لا بادئة رقمٍ أطول)
_STALE_TAG = "الأحدث المتاح"
# البند 14: إبرُ سياق الحقيقة الساكنة — سنةُ تأسيس/إنشاء/تشغيل ليست سنةَ
# بيانات، فلا يلحقها وسم التقادم أبداً.
_STATIC_YEAR_CTX = ("منذ", "تأسست", "تأسس", "التأسيس", "أنشئت", "أنشئ",
                    "أُنشئ", "افتتح", "افتُتح", "founded", "established",
                    "since", "est.")


def _stale_years_threshold() -> int:
    """سنة العتبة — أقدم من (السنة الحالية − SILK_STALE_DATA_YEARS). مصدر واحد
    عبر silk_staleness كي لا تتشعّب النافذة."""
    from silk_staleness import stale_threshold_year
    return stale_threshold_year()


# Wave 6.1 (تدقيق زبدة الفول السوداني/اليمن): حين يكون الحكم «مراقبة»/«مشروط»،
# يجب تسمية **شرطَي قلب الحكم** كحقلين مهيكلين (لا نثر حظّ): بيانات استيراد
# موثوقة تحت الرمز الصحيح (إن كان الرمز مُعلَّماً)، وموزّع محلي مؤكَّد تعاقدياً
# بالاسم. كل شرط يحمل خطوة الإغلاق التي تُقفله فتربطه خارطة الـ٩٠ يوماً. مبنيّ
# على البيانات (لا قائمة منتج صلبة) — يُستهلَك في العرض/المُصدِّرات/المختصر.
FLIP_CONDITIONS_HEADING = "شروط إعادة تقييم القرار"


# قيم حشو تُعامَل كغياب جهة اتصال (لا تُثبِت موزّعاً مؤكَّداً — مراجعة الشيفرة #4).
_FILLER_CONTACTS = frozenset({"", "-", "—", "–", "n/a", "na", "غير متاح",
                              "غير متوفر", "لا يوجد", "none", "null"})


def _real_contact(v: object) -> bool:
    """هل قيمة جهة الاتصال حقيقية (لا حشو/شرطة/«غير متاح حالياً»)؟ — عقد عدم
    الاختلاق: شرط «موزّع مؤكَّد» لا يتحقّق بعلامة حشو. جهةٌ حقيقية = بريدٌ
    (يحوي @ ونقطة) أو هاتفٌ (٥ أرقام فأكثر)؛ فالعبارات النصّية المطوّلة مثل
    «غير متاح حالياً»/«لا يوجد رقم» تُرفَض لأنها بلا @ ولا أرقام كافية
    (مراجعة الشيفرة #4 — الرفض بالبنية لا بمطابقة نصّية حرفية)."""
    s = str(v or "").strip()
    if not s or s.lower() in _FILLER_CONTACTS:
        return False
    if "@" in s and "." in s:                          # بريد إلكتروني
        return True
    return sum(ch.isdigit() for ch in s) >= 5          # هاتف (أرقام كافية)


def _flip_conditions(verdict_tone: str, hs_flagged: bool,
                     importer_leads: dict, market_ar: str,
                     lang: str = "ar", missing_components=None) -> list[dict]:
    """اشتقّ شرطَي قلب الحكم المهيكلين — يُفعَّل فقط للحكم watch/conditional.

    كل شرط: {condition, closes_via, met}. `met=True` حين يوجد دليل مرصود
    يُغلقه فعلاً (لا اختلاق) — موزّع بجهة اتصال مؤكَّدة => شرط الموزّع محقَّق.

    الموجة ٠: **الشرطُ نفسه و`met` نفسها** في اللغتين — النصّ وحده يُولَّد من
    مفتاحه القانوني، فلا يتسرّب شرطٌ عربيٌّ إلى تقريرٍ إنجليزيّ (هذه الحقول
    تصل قسم «ما لم يكتمل للقرار» في مُسلَّم العميل مباشرةً).
    """
    if verdict_tone not in ("watch", "conditional"):
        return []
    import silk_i18n as _i18n
    conds: list[dict] = []
    if hs_flagged:
        conds.append({
            "condition": _i18n.t("flip_cond_hs", lang),
            "closes_via": _i18n.t("flip_via_hs", lang),
            "met": False})
    conds.append({
        "condition": _i18n.t("flip_cond_distributor", lang,
                             market=market_ar or _i18n.t("the_market", lang)),
        "closes_via": _i18n.t("flip_via_distributor", lang),
        # Public contact details cannot establish a signed distribution agreement.
        "met": False})
    from silk_decision import _parts_ar
    for component in dict.fromkeys(missing_components or []):
        label = _parts_ar([component]) if lang == "ar" else str(component).replace('_', ' ')
        conds.append({
            "condition": (f"استكمال بيانات {label} وإعادة تقييم القرار" if lang == "ar"
                          else f"Complete the evidence for {label} and reassess the decision"),
            "closes_via": ("توثيق المدخلات من مصدر مناسب، ثم إعادة الحساب قبل الالتزام بالبيع"
                           if lang == "ar" else
                           "Document the required inputs and recalculate before committing to sales"),
            "met": False})
    return conds


def _has_seasonality_gap(missions: dict) -> bool:
    """هل رصدت بعثة فجوةَ موسمية (قيمة None + ملاحظة تخصّ الموسمية/رمضان)؟

    يلتقط شكلَي الملاحظة: الجديد (silk_trends_agent.SEASONALITY_GAP_CLOSURE)
    والقديم المخزَّن ('no series for seasonality of ...')."""
    for m in (missions or {}).values():
        if not isinstance(m, dict):
            continue
        for f in (m.get("findings") or []):
            d = _dp(f)
            if d.get("value") is not None:
                continue
            note = str(d.get("note") or "")
            if ("موسمي" in note or "رمضان" in note
                    or "seasonalit" in note.lower()):
                return True
    return False


# §D-2 (حزمة الفكس v2.1) — بلاغ حي: 2019/2021 وُسِمَتا «الأحدث المتاح» داخل
# فقرة سلسلتها الخاصة تمتدّ إلى 2023-2024 فعلياً («من 8% في 2019 إلى 12% في
# 2023»). سنةٌ ذُكِرت في نفس الجملة مع سنةٍ أحدث = مقارنة/مسار نمو صريح، لا
# ادّعاء أن هذه السنة القديمة هي «أحدث بيانات متاحة».
# درسا 144 و174 معاً: كان حدُّ النطاق جُملياً بنمط `_SENTENCE_BOUND_RE`
# (وأصلحت الموجة D2 فيه قراءةَ الفاصلة العشرية «1.77» نهايةَ جملة)، ثم
# هُزم النطاقُ الجُمليّ نفسُه بسرد السلسلة الممتد جُملاً (#14) فصار الحدُّ
# **الفقرة** (`\n` حصراً في `_year_in_growth_span` أدناه) — وبذا صارت
# عائلة الفاصلة العشرية مستحيلةً بنيوياً (لا نقطة في الحدود أصلاً) وحُذف
# النمطُ الميّت؛ قفلُ الحادثة السلوكي باقٍ في test_study12_live_defects.


def _year_in_growth_span(s: str, start: int, end: int, yr: int) -> bool:
    """هل تذكر **فقرة** هذه السنة سنةً أخرى أحدث وحديثة معها — مقارنة/مسار
    نمو صريح لا يجوز وسمه «الأحدث المتاح» (§D-2)؟

    الدراسة الحية الرابعة: سرد السلسلة يمتد جُملاً («بدأ من 1.77 في 2019.
    ومرّ بـ7.74 في 2020.» و2023 في جملة مجاورة) فهُزم النطاق الجُملي
    ووُسمت 2019/2020/2021 «الأحدث المتاح» داخل سلسلة تبلغ 2023 — النطاق
    صار الفقرة (حدود \\n) وشرطا اليمن باقيان (السنة الأحدث يجب أن تكون
    حديثة فوق عتبة التقادم). **قيد معلن**: فقرة تخلط حقيقة قديمة مستقلة
    (LPI 2018) بسنة تجارة حديثة ستكبح وسم القديمة أيضاً — الفقرات مواضيعية
    عادةً فالخطر محدود ومقبول مقابل إسكات الوسم المقلوب على السلاسل."""
    lo = s.rfind("\n", 0, start) + 1
    m2 = s.find("\n", end)
    hi = m2 if m2 != -1 else len(s)
    sentence = s[lo:hi]
    for ym in re.finditer(r"(?<![\d/])(19\d\d|20\d\d)(?![\d/])", sentence):
        try:
            y2 = int(ym.group(1))
        except ValueError:
            continue
        # D2 (تدقيق حالة اليمن): سنةٌ أحدث تكبح الوسم فقط إن كانت هي نفسها
        # حديثةً (فوق عتبة التقادم) — «(2013) و31.5% (2018)» حقيقتان قديمتان
        # متجاورتان تستحقان الوسم كلتاهما؛ أما سردٌ يبلغ 2024 فمسارٌ حيّ.
        if y2 > yr and y2 > _stale_years_threshold():
            return True
    return False


def _tag_stale_years(text: "str | None",
                     stale_fact_years: "set[int] | frozenset[int]" = frozenset()) -> str:
    """وسم سنوات البيانات المتقادِمة «الأحدث المتاح» — **أساسه قائمة الحقائق
    المتقادِمة** (provenance) لا تحليل النثر (قرار المالك).

    - **أساسي:** كل سنة في `stale_fact_years` (معروفة متقادِمةً من الحقائق)
      تُوسَم أينما وردت (بحدود آمنة: ليست ملاصقة لرقم/شرطة، فلا يُوسَم رمز HS
      مثل 200811 ولا لائحة 2017/625) — مستقلّةً عن الصياغة («في 2013»/«2013م»).
    - **شبكة أمان:** سنةٌ متقادِمة (≤ العتبة) في سياق بيانات صريح (قوسين/كلمة
      زمنية) حتى لو لم تُمرَّر قائمةٌ — احتياطٌ أخير محافظ.

    عقد عدم الاختلاق: إفصاح فقط، لا يغيّر رقماً؛ أول ورودٍ لكل سنة، ولا تكرار
    إن وسَمها الكاتب أصلاً (نافذة ٤٠ محرفاً)."""
    s = str(text or "")
    if not s.strip():
        return s
    threshold = _stale_years_threshold()
    # جمع كل المرشّحين (موضع، نهاية، سنة): الأساسي من القائمة + الاحتياطي النمطي.
    cands: list[tuple[int, int, int]] = []
    for yr in (stale_fact_years or set()):
        for m in re.finditer(rf"(?<![\d/]){int(yr)}(?![\d/])", s):
            cands.append((m.start(), m.end(), int(yr)))
    for m in _DATA_YEAR_CTX_RE.finditer(s):
        g = m.group(1) or m.group(2)
        try:
            y = int(g)
        except (TypeError, ValueError):
            continue
        if y <= threshold:
            cands.append((m.start(), m.end(), y))
    if not cands:
        return s
    cands.sort()
    tagged: set[int] = set()
    out: list[str] = []
    last = 0
    for start, end, yr in cands:
        if yr in tagged or end < last:
            continue
        if _year_in_growth_span(s, start, end, yr):
            continue  # §D-2: مقارنة/مسار نمو صريح مع سنةٍ أحدث في نفس الجملة
        # البند 14 (أمر إصلاح المحرّك): سنةُ تأسيسٍ/حقيقةٍ ساكنة ليست
        # سلسلةً زمنية — «العامل منذ 1991 — بيانات 1991 (الأحدث المتاح)»
        # وسمٌ فارغُ المعنى (تقريرا #10/#11). سياقُ الثبات قبل السنة يعفيها
        # من الوسم في هذا الموضع فقط (ورودٌ بيانيّ آخر لنفس السنة يظل يوسم).
        # النافذة حتى نهاية التطابق لا بدايته — مرشّح الشبكة الاحتياطية
        # يبتلع الكلمةَ الزمنية داخل تطابقه فتغيب عن نافذةٍ تسبق البداية.
        if any(t in s[max(0, start - 30):end] for t in _STATIC_YEAR_CTX):
            continue
        # ضمّ لاحقة سنةٍ ميلادية/هجرية **مفردة عند حدّ كلمة فقط** (م/هـ/ـ) كي
        # لا تتدلّى بعد الوسم — دون ابتلاع أوّل حرفٍ من كلمةٍ ملاصقة مثل «مايو»
        # (مراجعة الشيفرة #4: «2013مايو» تبقى «مايو» سليمة).
        _era_end = end
        while _era_end < len(s) and s[_era_end] in "مهـ":
            _era_end += 1
        if _era_end > end and (_era_end >= len(s) or not s[_era_end].isalpha()):
            end = _era_end
        # لا تُكرِّر إن كان الوسم مكتوباً أصلاً بعد السنة (نافذة ٤٠ محرفاً).
        if (_STALE_TAG in s[end:end + 80] or
                re.search(r"أحدث\s+(?:نسخة|بيانات)\s+متاحة", s[end:end + 80])):
            tagged.add(yr)
            continue
        tagged.add(yr)
        out.append(s[last:end])
        if re.search(rf"بيانات\s+{yr}[مهـ]*$", s[max(0, start - 20):end]):
            out.append(f" ({_STALE_TAG})")
        else:
            out.append(f" — بيانات {yr} ({_STALE_TAG})")
        last = end
    out.append(s[last:])
    return "".join(out)


def _hs_derivation(result: dict) -> dict | None:
    """سجلّ اشتقاق التصنيف الدائم (الموجة ٤ — توجيه §3.1): فصل ← بند ←
    بند فرعي + أساس الحسم + جملة إفصاح الاستبدال عند رمز مُعلَّم. يُبنى من
    البيانات البنيوية المتوفرة حصراً — لا اختلاق أساسٍ غير معروف."""
    hs6 = str(result.get("hs_code") or "").strip()
    if not re.fullmatch(r"\d{6}", hs6):
        return None
    desc = ""
    try:
        from silk_hs_resolver import official_description
        desc = official_description(hs6) or ""
    except Exception:
        desc = ""
    prov = _hs_provenance(result)
    if prov:
        basis = prov["note_ar"]
    elif result.get("hs_resolution_note"):
        basis = str(result["hs_resolution_note"])
    else:
        basis = ("الرمز مُدخل صراحة في الطلب أو محسوم من مرجع الأصناف — "
                 "راجع منهجية التقرير")
    record = {
        "hs6": hs6,
        "chapter": hs6[:2],
        "heading": hs6[:4],
        "subheading": hs6,
        "official_description": desc,
        "basis": _strip_internal_plumbing(basis),
        "confirmed": (result.get("hs_confirmation") or {}).get("confirmed"),
    }
    conf = result.get("hs_confirmation") or {}
    if conf and conf.get("confirmed") is False:
        # جملة إفصاح الاستبدال الإلزامية (§3.2) — لا خلاصة كمية من رمز مجاور.
        # دورة C4 (صيد ٣): مرآة إنجليزية — كانت عربية فقط فيُسقطها الفصلُ
        # الصلب (`_lang_safe`) صامتةً عن docx الإنجليزي الذي وُجد القسم
        # ليوصلها إليه.
        record["substitution_note"] = (
            f"هذه الأرقام تصف الرمز {hs6} (فئة مجاورة غير مؤكَّدة لمواصفة "
            "المنتج)؛ لا تُنقل إلى فئة المنتج الفعلية، ولا تُبنى عليها "
            "خلاصة حجم أو حصة أو تركّز.")
        record["substitution_note_en"] = (
            f"These figures describe HS code {hs6} (an adjacent category "
            "not confirmed for the product specification); do not carry "
            "them over to the actual product category, and do not build "
            "size, share, or concentration conclusions on them.")
    return record


def _hs_provenance(result: dict) -> dict | None:
    """إفصاحُ مصدر رمز HS حين حُسِم آلياً بالسمة الرقمية — أو `None`.

    بلاغ المُشرِف (`silk_hs_attributes`): بنودُ الترويسة الواحدة تتمايز
    بعتبةٍ رقمية، فيُقاس الرقمُ (بطاقةُ العبوة/مصدرُ ويب) بدل سؤال التاجر
    عنه. **لا يُعرَض رمزٌ حُسِم آلياً بلا ذكرِ دليله** — القارئُ يرى كيف
    اختير البندُ لا مجرّد نتيجته (نفس منطق «سطرُ مصدرٍ لكل رقم»). حسمٌ
    بمسارٍ غير معروف => `None` (لا سطرَ إفصاحٍ مختلَق)."""
    prov = result.get("hs_provenance")
    if not isinstance(prov, dict) or not prov.get("hs6"):
        return None
    src = prov.get("resolved_from")
    label = prov.get("label_ar") or prov.get("attribute") or ""
    measured, unit = prov.get("value"), (prov.get("unit") or "")
    measured_ar = "" if measured is None else f" ({label} {measured}{unit})"
    if src == "image":
        line = (f"الرمز محدَّد من صورة العبوة{measured_ar} — البند "
                f"{prov.get('hs6')} اختير بمطابقة القياس المقروء على نطاقات "
                "بنود الترويسة.")
    elif src == "web":
        line = (f"الرمز محدَّد من مصدر ويب: {prov.get('source_url') or ''}"
                f"{measured_ar} — البند {prov.get('hs6')} اختير بمطابقة هذا "
                "القياس على نطاقات بنود الترويسة (استشهادٌ ثانويّ برابط، "
                "يُراجَع قبل الاعتماد النهائي).")
    else:
        return None
    return {"resolved_from": src, "hs6": prov.get("hs6"),
            "attribute": prov.get("attribute"), "label_ar": label,
            "value": measured, "unit": unit,
            "source_url": prov.get("source_url"),
            "confidence": prov.get("confidence"), "note_ar": line}


def _incomplete_banner(missing: list, lang: str = "ar") -> str:
    """نصُّ شارة «تقرير غير مكتمل» (markdown blockquote) — قرار المالك، تجاوز
    §5-الإتلاف (بلاغ تحليل 20): تقريرٌ ناقصٌ بنيوياً يُسلَّم بدل أن يُتلَف. يُصيغه
    كلُّ مُصدِّرٍ بشكله (md عبر `_md_deep_research`، docx أحمرَ بارزاً عبر
    `_stamp_degraded_banner`، المختصر سطراً) — **لا يُحقَن في `report.text`**
    كي لا يظهر حرفياً في docx الذي يُعيد تفسير النصّ. يتكيّف: أقسامٌ غائبة تُعلَن
    بالاسم فجواتٍ؛ واقتطاعٌ منتصفَ الجملة (الأقسام حاضرةٌ لكن الأخيرةُ مبتورة)
    يُصرَّح به بلا قائمةِ «—» مضلِّلة (مراجعة §58: «فجواتٍ: —» تكذب بوجود أقسام)."""
    names = "، ".join(m for m in (missing or []) if m)
    if lang == "en":
        names_en = ", ".join(m for m in (missing or []) if m)
        if names_en:
            return ("> ⚠️ **INCOMPLETE REPORT** — the following sections were "
                    f"not written and are declared gaps, not findings: "
                    f"{names_en}. The decision and the written sections stand; "
                    "do not draw a conclusion from a missing section.")
        return ("> ⚠️ **INCOMPLETE REPORT** — the report was truncated before "
                "completion (its final section is cut off). The decision and "
                "the written sections stand.")
    if names:
        return ("> ⚠️ **تقرير غير مكتمل** — لم تُكتَب الأقسام التالية وتُعَدّ "
                f"فجواتٍ معلنة لا نتائج: {names}. القرار والأقسام المكتوبة سليمة؛ "
                "لا تُبنى خلاصةٌ على قسمٍ غائب.")
    return ("> ⚠️ **تقرير غير مكتمل** — اقتُطِع التقرير قبل اكتماله (قسمه الأخير "
            "مبتور). القرار والأقسام المكتوبة سليمة.")


def _deep_research_view(result: dict, lang: str = "ar",
                        _ledger: dict | None = None) -> dict | None:
    """قسم البحث العميق (الموجة ٤، V5) — إضافي بحت، لا يمسّ أي مفتاح قائم.

    `lang` (الموجة ٠) يحكم **العرض وحده**: التصنيفات والأرقام والحكم الحتمي
    والأدلة لا تتغيّر بتغيّره — التسميات القالبية فقط. الافتراض `"ar"` فيبقى
    كل مستدعٍ قائم على سلوكه حرفياً.

    **تنبيه تسمية مهم**: هذا المفتاح `view["deep_research"]` مختلف تماماً عن
    `row["research"]` الموجود أصلاً (حزمة وكلاء البحث الثمانية الحتمية،
    Stage 3 §4b) — تعمّد اختيار اسم مختلف لتفادي تصادم دلالي، لا تكرار خطأ.
    None عند غياب `result["deep_research"]` (تحليل /analyze عادي — لا أثر).
    """
    dr = result.get("deep_research")
    if not dr:
        return None
    missions = {}
    for key, rep in (dr.get("missions") or {}).items():
        f = _report_fields(rep)
        # بلاغ حي (risk_news): بعثة قد تعيد JSON خام كملخّص عند فشل تفسير
        # ردّها (silk_llm_runtime._parse_output) — يُطبَّع هنا مرة واحدة
        # فيصل نظيفاً كل مستهلك (جدول الأدلة الخام، حدود البحث، ملخّص
        # التتبّع أدناه).
        clean_summary = _strip_internal_plumbing(f["summary"])
        missions[key] = {
            "name": f["agent_name"], "failed": f["failed"],
            # الاسم التجاري العربي للبعثة — كل مستهلك (جدول docx، لوحة
            # الويب، الملحق التقني) يعرضه بدل مفتاح snake_case الخام
            # (بلاغ مالك: "pricing_scout"/"risk_news" ظهرت حرفياً للعميل).
            "label": _mission_label(key),
            "summary": clean_summary,
            # مراجعة شيفرة PR #147: نسخة سطحية لكل بند — `_dp` تعيد dict
            # المدوّنة **بالمرجع**، وممرّ المصالحة (WP-3) يكتب وسوم عرضٍ
            # (evidence_tag/corroborated) على بنود العرض؛ بلا النسخ كانت
            # الوسوم تتسرّب إلى بنود السجل الخام وتُحفَظ مع أي save_analysis
            # لاحق (مسار regenerate/enrich) — طبقة العرض لا تلمس المخزون.
            "findings": [dict(_dp(x)) for x in f["findings"]],
            # التتبّع يُستخرَج من الملخّص **الخام** (لا المُطهَّر): تِلِمتري عدّ
            # نداءات الأدوات يُجرَّد الآن من سطح العرض (LESSON 57، تسريب المشرف #7).
            "trace": _mission_trace_summary(f["failed"], f["summary"]),
        }
    analyst = dr.get("analyst") or {}
    analyst_report = _report_fields(analyst.get("report"))
    # سدّ تسريب: ملخّص المحلل الشامل نص كلود حرّ فوق نفس الحقائق المعزولة
    # التي يقرأها ملخّص كل بعثة — كان الأخير وحده يمرّ عبر التطهير، تاركاً
    # ثغرة مطابقة (نفس نوع النص، لا سبب لتمييزه).
    analyst_report = {**analyst_report,
                      "summary": _strip_internal_plumbing(analyst_report["summary"])}
    # P2: شارة أدلة ثلاثية (✓/◐/○) محسوبة هنا مرة واحدة في النموذج القانوني —
    # لا رقم ثقة خام يصل الواجهة، ولا منطق تصنيف مكرَّر في JS العميل.
    from silk_narrative import evidence_badge
    # سدّ تسريب (الطبقة ٩): ملاحظة اكتشاف المحلل الشامل تحمل أحياناً وسم
    # تقاطع خام بادئاً ("[entry_cost] تعريفة مطبّقة") — وسم تصنيف داخلي
    # للمحلل نفسه، لا معلومة تفيد القارئ (التقاطع معروف أصلاً من عنوان
    # القسم الذي يُدرَج تحته). يُزال، لا يُترجَم — تكرار لا قيمة إضافية له.
    _cat_tag_re = re.compile(
        r"^\[(?:demand|price_competitiveness|entry_cost|entry_door|swot)\]\s*")
    def _with_badge(x):
        d = _dp(x)
        note = d.get("note")
        if isinstance(note, str) and _cat_tag_re.match(note):
            note = _cat_tag_re.sub("", note)
        # H2 (تدقيق): قيمة/ملاحظة تقاطع المحلل كانتا تصلان /brief و/ask
        # خامّتين — الملخّص وحده كان يُطهَّر. تُطهَّران هنا في المصدر فيرثهما
        # كل مستهلك للـview (اللوحة، المختصر، سياق الدردشة). أرقام/غير-نصّ
        # تُترك كما هي (لا سباكة فيها).
        val = d.get("value")
        d = {**d,
             "value": _strip_internal_plumbing(val) if isinstance(val, str) else val,
             "note": _strip_internal_plumbing(note) if isinstance(note, str) else note}
        # WP-3: الشارة الواعية بالمنشأ — بند جمعه وكيل بحث يُسقَف درجةً.
        from silk_narrative import evidence_badge_for
        return {**d, "confidence_badge": evidence_badge_for(d)}
    by_category = {cat: [_with_badge(x) for x in (dps or [])]
                  for cat, dps in (analyst.get("by_category") or {}).items()}
    report_out = dr.get("report") or {}
    verdict = dr.get("verdict") or {}
    # سدّ تسريب (الطبقة ٦): تعليل حكم كلود (ai.reasoning) نص حرّ — قد يردّد
    # رمز حكم خام أو مصطلحاً داخلياً رآه في مدخلاته (نفس خطر ai.reasoning
    # المذكور في _stage2)، وكان يصل خاماً لكل من لوحة الويب وخلاصة docx
    # التنفيذية بلا أي مُطهِّر. تعقيم هنا مرة واحدة في النموذج القانوني —
    # بقية حقول verdict (الرمز الخام، الثقة) تبقى كما هي لأن تصنيف الشارة
    # (_verdict_tone) يحتاج الرمز الإنجليزي الخام تحديداً.
    if isinstance(verdict.get("ai"), dict) and verdict["ai"].get("reasoning"):
        verdict = {**verdict,
                  "ai": {**verdict["ai"],
                        "reasoning": _strip_internal_plumbing(
                            verdict["ai"]["reasoning"])}}
    # صيد الفجوات ٣: `verdict["note"]` كان الحقل الوحيد في العائلة الذي يبلغ
    # مسارَي md/docx البحثيين خاماً — مدوّنات ما قبل الإصلاح تحمل فيه نصف
    # الملاحظة الداخلي الإنجليزي (شبكة `_PRELIM_EN_NOTE_RE` كانت تُطبَّق على
    # النص السردي فقط). نفس التعقيم مرة واحدة في النموذج القانوني.
    if verdict.get("note"):
        verdict = {**verdict,
                  "note": _strip_internal_plumbing(str(verdict["note"]))}
    # سدّ تسريب: ملاحظات المراجعة غير المحلولة نص كلود حرّ (المراجِع) —
    # كانت تصل limits وview["deep_research"]["report"] خامة تماماً؛ وسبب
    # فشل التقرير (failure_reason) يحمل تفصيل استثناء/HTTP خام متعمَّد
    # لأغراض تشخيص المطوّرين (silk_ai_judge.failure_reason) لكن كان يصل
    # العميل حرفياً بما فيه توجيه تشغيلي ("راجع سجلّات الخادم") — العقد
    # الخام يبقى في `report_out` كما هو؛ التطهير هنا للعرض فقط.
    clean_unresolved = [_strip_internal_plumbing(n)
                        for n in (report_out.get("unresolved_notes") or [])]
    clean_failure_reason = (_strip_internal_plumbing(report_out.get("failure_reason"))
                            if report_out.get("failure_reason") else "")
    # PART B1 (أمر العمل الرئيس — «حدود هذا البحث» تناقض المتن): البعثات
    # تُعلن فجواتها معزولةً وقت تشغيلها المتوازي، فتبقى فجوة بعثة «حصص
    # الموردين غير متاحة» في الحدود حتى لو رصدت بعثة المنافسين لاحقاً
    # 55.28%/HHI. مصالحة متحفّظة: سطر حدٍّ **مشتقّ من بعثة** (فاشلة أو فجوة
    # جزئية) يُعاد وسمه «حُسمت لاحقاً» فقط إن حمل موضوعاً وُجد له دليل رقمي
    # فعلي في الحقائق النهائية (نفس الموضوع + رقم في بند واحد) — وإلا يبقى
    # حرفياً (لا إخفاء فجوة حقيقية، عقد عدم الاختلاق). حدود المحلل/المراجع/
    # الفشل/HS/كلود لا تُمَسّ (ليست فجوات بعثة قابلة للحسم بحقائق بعثة أخرى).
    _fact_texts = _final_fact_texts(missions, by_category)
    # v["summary"] مُطبَّع أصلاً أعلاه (clean_summary) — لا حاجة لإعادة التنظيف.
    # سطر البعثة الفاشلة يحمل الجملة الأولى فقط من الملخّص لا الملخّص كاملاً
    # (كان ≤٧٠٠ محرفاً فتعيد طبقة docx قصّه عند ٣٠٠ منتصفَ جملة بـ"…").
    # الموجة ٠: سطور الحدود قوالبُ من مفاتيح قانونية (`silk_i18n.TERMS`) لا
    # سلاسلُ مكتوبةٌ هنا — فتخرج بلغة التقرير، ولا يتسرّب نصّ بعثةٍ عربيّ إلى
    # تقريرٍ إنجليزيّ عبر قالبٍ ثابت اللغة. (التفصيل `detail` يبقى ما رُصد.)
    import silk_i18n as _i18n
    mission_limits = _reconcile_mission_limits(
        [_i18n.t("limit_mission_uncited", lang, label=_mission_label(k),
                 detail=_first_clause(v['summary']))
         for k, v in missions.items() if v["failed"]]
        # فجوات جزئية داخل بعثات "ناجحة" (نتائج ≥١ لكن ببنود ناقصة معلنة).
        + [g for k, v in missions.items()
           for g in _mission_gap_lines(_mission_label(k), v["summary"])],
        _fact_texts)
    limits = (mission_limits
             # سدّ تسريب (الطبقة ٩): مفتاح تقاطع خام إنجليزي ("entry_cost")
             # كان يصل حدّاً معروضاً للعميل حرفياً — الاسم التجاري العربي
             # (نفس معجم silk_market_analyst._CATEGORY_LABELS المستعمَل في
             # بوابة الجودة) يحل محله.
             + [_i18n.t("limit_analyst_thin", lang,
                        label=_category_label(c, lang))
               for c in (analyst.get("missing_categories") or [])]
             + [_i18n.t("limit_unresolved_note", lang, detail=n)
                for n in clean_unresolved])
    if not report_out.get("report") and clean_failure_reason:
        limits.append(_i18n.t("limit_report_missing", lang,
                              detail=clean_failure_reason))
    if result.get("hs_resolution_note"):
        limits.append(_i18n.t(
            "limit_hs_classification", lang,
            detail=_humanize_gap_note(result['hs_resolution_note'])))
    # وسمُ إعادة التحقّق (resume / إعادة توليد التقرير): رمزٌ أُعيد من سجلٍّ
    # سابق ولم يعد يوافق حُكمَ التصنيف اليوم — يمرّ ويُعلَن، لا يُحجَب ولا يُخفى.
    _reval = result.get("hs_revalidation")
    if isinstance(_reval, dict) and _reval.get("message"):
        limits.insert(0, _reval["message"])
    if result.get("ai_extras_note"):
        limits.append(_i18n.t(
            "limit_ai_extras", lang,
            detail=_humanize_gap_note(result['ai_extras_note'])))
    if verdict.get("ai_note"):
        limits.append(_i18n.t(
            "limit_verdict_note", lang,
            detail=_strip_internal_plumbing(verdict['ai_note'])))
    # Wave 2.2 (تدقيق زبدة الفول السوداني/اليمن — لا بيانات موسمية من Trends):
    # فجوة الموسمية تُعلَن **مرة واحدة** في «ما لم يكتمل» مع خطوة الإغلاق
    # العملية (بحث ميداني/مقابلات موزّعين) — النمط القائم للفجوات، مُوسَّعاً.
    if _has_seasonality_gap(missions) and not any(
            "الموسمية" in l for l in limits):
        from silk_trends_agent import SEASONALITY_GAP_CLOSURE
        limits.append(SEASONALITY_GAP_CLOSURE)
    # WP-1: الحكم المعروض (الشارة/التسمية) من المرحلة الحتمية حصراً.
    from silk_narrative import authoritative_verdict
    v_raw, _ = authoritative_verdict(verdict)
    # ── الموجة Z · البند Z-01 (نصفُه الثاني) — المدوّناتُ المخزَّنة ───────
    # الترقيةُ في `api.py` تخدم التشغيلاتِ **الجديدة** (فيراها الكاتبُ أيضاً).
    # أمّا نتيجةٌ خُزِّنت قبلها فتحمل صفَّ سوقٍ بقرارِ محرّكٍ سليم وحكمَ جوريةٍ
    # غيرَ مُرقّى — فتُعرَض شارةُ «حالة أدلة» فوق قسمِ أساسِ حكمٍ يعلن درجةً
    # وثقة. حكمان في المصنوع نفسِه، من الباب الخلفيّ. المصالحةُ هنا تجعل
    # **الصفَّ** مصدرَ الحكم المعروض متى حمل قراراً صالحاً، أياً كان تاريخُ
    # المدوّنة؛ ولا مسارَ عرضٍ ثانٍ: نفسُ `_verdict_tone` ونفسُ التسمية.
    _row_dec = ((result.get("markets") or [None])[0] or {}).get("decision") or {}
    if _row_dec.get("schema") and not _row_dec.get("error") \
            and _row_dec.get("verdict"):
        v_raw = _row_dec["verdict"]
        verdict_tone = _verdict_tone(v_raw)
    else:
        verdict_tone = _coverage_basis_tone(_verdict_tone(v_raw), verdict)
    # Wave 1.3/3.2/4.1 (تدقيق زبدة الفول السوداني/اليمن): حين يُعلَّم رمز HS
    # غير مؤكَّد (صفة المنتج المميّزة غائبة عن وصف الرمز، silk_hs_confirm)،
    # كل رقم مشتقّ من كومتريد (حجم السوق/HHI/حصص/CAGR) يُعاد تأطيره «مؤشر
    # سياقي لا مقياس فعلي» بملاحظة **منهجية واحدة** (لا تكرار في كل قسم،
    # 4.1)، وثقة الحكم تُسقَف (1.3)، وHHI يخرج من مدخلات تسجيل الحكم (3.2).
    # العقد يُحسَب مرة إن غاب من المدوّنة (نتائج مخزّنة قديمة) — لا اختلاق:
    # confirmed=None (غير قابل للتأكيد) لا يُعامَل تعليماً.
    from silk_hs_confirm import (confirm_hs, is_flagged, CONTEXTUAL_TAG,
                                 cap_confidence_for_flagged_hs)
    hs_conf = result.get("hs_confirmation")
    if not isinstance(hs_conf, dict) and result.get("hs_code"):
        try:
            hs_conf = confirm_hs(str(result.get("product") or ""),
                                 str(result.get("hs_code") or ""))
        except Exception:
            hs_conf = None
    hs_flagged = is_flagged(hs_conf)
    if hs_flagged:
        # PR A §A1: نفس المُسقِّف الواحد المستعمَل قبل الكاتب (المسار الرئيسي +
        # إعادة التوليد) — idempotent هنا: لو مرّ الكاتب على قيمةٍ مسقوفة أصلاً
        # لم يتغيّر شيء، وإلا سُقِّف الغلاف كما كان. لا نسخة سقفٍ محلّية تتباعد.
        verdict = cap_confidence_for_flagged_hs(verdict, hs_conf)
        # ملاحظة منهجية واحدة (4.1) — تُضاف مرة واحدة إلى الحدود، لا في كل قسم.
        _missing = "، ".join((hs_conf or {}).get("missing_terms") or [])
        # درس 191 (B2): وصفٌ غائب (None من silk_hs_classifier) كان يُطبَع
        # «None»/«» — الصيغة الصادقة «غير متاح» (نمط silk_hs_confirm.py:566).
        _cd = str(hs_conf.get('code_desc') or "").strip()
        _cd_clause = (f"(«{_cd}») " if _cd
                      else "(وصفه الرسمي غير متاح في المرجع) ")
        limits.insert(0, f"{CONTEXTUAL_TAG}: رمز HS {hs_conf.get('hs_code')} "
                      f"{_cd_clause}لا يشمل صفة المنتج المميّزة"
                      + (f" ({_missing})" if _missing else "")
                      + " — تُقرأ أرقام الاستيراد والتركّز والحصص كمؤشر سياقي "
                      "حتى تأكيد الرمز الصحيح.")
    # ── الصنف ١٠ (خلف رايته): اتّساعُ البند الجمركيّ يُعلَن كما يُعلَن
    # عدمُ شموله لصفة المنتج — **بالآلة نفسِها** لا بمسارِ عرضٍ ثانٍ:
    # سطرُ حدودٍ واحد + تعليمُ أرقامِ التركّز سياقاً + سقفُ الثقة القائم.
    # العيبُ المرصود: بندٌ يغطّي فئةً كاملةً قُرِئ سوقَ منتجٍ واحد. والاتّساعُ
    # **واقعةُ منتجٍ مُهيَّأة** (`hs_scope`) لا استنتاجَ محرّك.
    _hs_broad = False
    try:
        import silk_market_structure as _MS
        if _MS.enabled() and _MS.hs_scope(result.get("hs_code")) == "broad":
            _hs_broad = True
    except Exception:  # noqa: BLE001 — تهيئةٌ غائبةٌ ليست خطأَ عرض
        _hs_broad = False
    if _hs_broad and not hs_flagged:
        verdict = cap_confidence_for_flagged_hs(verdict, hs_conf)
        limits.insert(0, f"{CONTEXTUAL_TAG}: رمز HS "
                      f"{result.get('hs_code')} يغطي فئةً أوسع من المنتج "
                      "المدروس وفق تهيئة المنتج — تُقرأ أرقام الاستيراد "
                      "والتركّز والحصص سياقاً عاماً للفئة لا قياساً مباشراً "
                      "لهذا المنتج.")
    # البند 18 (موجة سدّ الفجوات F5): صندوقُ التحذير الواحد أعلى التقرير —
    # يُبنى حتمياً من نفس عقد التأكيد الذي يبني سطرَ الحدود أعلاه؛ المُصدِّرون
    # (md/docx/اللوحة) يعرضونه مرةً واحدة في الرأس بدل تكرار جملة التحذير
    # أربع مرات (حادثة #10)، والنجومُ بجانب الأرقام المتأثرة شأنُ الكاتب
    # (تعليمة الموجّه القائمة) — لا آليةَ توسيمٍ حتمية بلا معرفة الأرقام.
    _caveat_box = ""
    if hs_flagged:
        # موجة سدّ الفجوات الثانية: الصندوق بلغة التقرير (i18n) — نص عربي
        # في docx إنجليزي خرقٌ لجدار اللغة.
        # درس 191 (B2): غيابُ الوصف يختار صيغة nodesc — فلا "None" في قالب EN.
        _bx_desc = str(hs_conf.get("code_desc") or "").strip()
        _caveat_box = _i18n.t(
            "hs_caveat_box" if _bx_desc else "hs_caveat_box_nodesc", lang,
            tag=(CONTEXTUAL_TAG if str(lang or "ar").lower() != "en"
                 else "Contextual indicator"),
            hs=hs_conf.get("hs_code"), desc=_bx_desc)
    # إفصاحُ مصدر الرمز حين حُسِم آلياً بالسمة الرقمية — سطرٌ واحدٌ مشترك
    # يُبنى في `_hs_provenance` ويُحقَن هنا وفي `build_view` معاً (مسارا
    # /research و/analyze) بلا نسختين قابلتين للانحراف.
    _hs_prov_view = _hs_provenance(result)
    if _hs_prov_view:
        limits.insert(0, _hs_prov_view["note_ar"])
    # WP-3 §2/§3: ممرّ المصالحة الرقمية (يوسم البنود المستبعدة/السياقية/
    # المسانَدة) + إعلان المصادر التي فشل جمعها كلياً — مصدرٌ كل بنوده
    # أخطاء (value=None) يُستبعَد من سطر «اعتمد هذا التقرير على مصادر…»
    # (silk_reports._client_methodology_paragraph) ويُذكَر هنا في الحدود فقط.
    _conflicts = _reconcile_numeric_conflicts(missions, bool(hs_flagged))
    _src_ok: dict[str, bool] = {}
    from silk_narrative import TOOLUSE_MARK_RE as _TUM
    for _m in missions.values():
        for _f in (_m.get("findings") or []):
            _lbl = _TUM.sub("", str(_f.get("source") or "")).strip(" ،-—")
            if not _lbl:
                continue
            _src_ok[_lbl] = _src_ok.get(_lbl, False) or (
                _f.get("value") is not None)
    for _lbl, _ok in sorted(_src_ok.items()):
        if not _ok and not any(_lbl in l for l in limits):
            limits.append(_i18n.t("limit_source_fetch_failed", lang, label=_lbl))
    # الموجة ٠: طبقةُ «لغة التاجر» (`_apply_merchant_language`) عربيةٌ بحتاً —
    # تحقن شروحاً عربية ومسرداً عربياً داخل النصّ. تشغيلُها على تقريرٍ إنجليزيّ
    # يُنتج نصّاً مختلطاً تحجبه البوابةُ الحاجزة، فلا يخرج تقريرٌ أصلاً.
    # وليست حاجةً هناك أصلاً: عقدُ الكاتب الإنجليزيّ يفرض شرحَ الاختصار **عند
    # أوّل ورود** داخل النثر نفسه (§34) — فالنصّ مفهومٌ بذاته بلا حَقن.
    # الدرس ٢٦٢ — **ملءُ رموز السجلّ أوّلاً، قبل أيّ مُطهِّر**: الرموزُ
    # داخليةٌ بين الكاتب والمخزن حصراً، ومُطهِّرُ السباكة يعرّب أسماءها
    # الإنجليزية فيُفسِدها قبل ملئها (قِياسٌ على هذه الدالّة كشفه). تُملأ
    # هنا مرّةً واحدة فلا يصل قوسٌ أيَّ مُصدِّر. وما تقادَم من المعطيات منذ
    # الكتابة **لا يُملأ بصمت**: يُسجَّل في `ledger_stale` ويُعلَّم.
    _raw_report = report_out.get("report")
    _ledger_stale: list = []
    _ledger_bind: dict = {}
    if _ledger and _raw_report:
        try:
            import silk_fact_ledger as _FL
            _ledger_stale = _FL.stale_keys(dr.get("ledger_snapshot") or {},
                                           _ledger)
            _ledger["stale"] = _ledger_stale
            _raw_report, _ledger_bind = _FL.bind(str(_raw_report), _ledger,
                                                 lang)
        except Exception as _be:  # noqa: BLE001 — الملءُ لا يُسقِط عرضاً
            log.warning("ledger bind skipped: %s", _be)
    _clean_report = _strip_internal_plumbing(_raw_report, lang)
    # الدرس ٢٦١ — نقطةُ التطبيع **عند القراءة**: تقريرٌ مخزَّنٌ كتب الكاتبُ
    # عناوينَه بصيغةٍ أخرى (`# N)` بدل `## N.`) كان يُقرَأ صفرَ أقسامٍ فيُطلِق
    # حاجبَي البنية وقسمِ العميل معاً ويُحجَب تنزيلُه (409) — رغم أنّ نصَّه
    # كاملٌ سليم. التطبيعُ هنا يشفي **التقاريرَ القائمةَ في القاعدة** بلا
    # تعديلِ صفٍّ واحدٍ فيها (البند ٤) وبلا إعادةِ توليدٍ مدفوعة؛ وهو
    # idempotent فلا يغيّر بايتاً في تقريرٍ عناوينُه قانونيةٌ أصلاً.
    _headings_repaired = False
    _heading_repairs: list = []
    try:
        from silk_ai_judge import canonicalize_section_headings
        _canon_report = canonicalize_section_headings(_clean_report, lang)
        _headings_repaired = _canon_report != _clean_report
        if _headings_repaired:
            # شرط المُشرِف C (مراجعة §58 #7): **لا تعديلَ صامتاً على نصٍّ
            # مُسلَّم** — كلُّ سطرِ عنوانٍ أُعيدت كتابتُه يُسجَّل قبل/بعد في
            # قناة `render_repairs` نفسِها التي تحمل رقعةَ تلعثم البادئة.
            _old_h = [l for l in _clean_report.split("\n") if l.strip()]
            _new_h = [l for l in _canon_report.split("\n") if l.strip()]
            _heading_repairs = [
                {"kind": "section_heading", "before": a, "after": b}
                for a, b in zip(_old_h, _new_h) if a != b]
        _clean_report = _canon_report
    except Exception as _he:  # noqa: BLE001 — التطبيعُ تحسينٌ لا شرطُ عرض
        log.warning("heading canonicalization skipped: %s", _he)
    # البند 15 (أمر إصلاح المحرّك): جدول ميت (<50% خانات مملوءة) يُطوى
    # لسطر يسمّي الناقص — قبل أي سطح عرض/تصدير.
    _clean_report = _collapse_dead_tables(_clean_report)
    if lang == "ar":
        _report_text_glossed, _glossary = _apply_merchant_language(_clean_report)
    else:
        _report_text_glossed, _glossary = _clean_report, []
    # البند ٥ (تدقيق «تحليل #1» DZA): عنوِن عمود السعر بالعملة المرصودة
    # فعلاً قبل التخزين في النموذج القانوني — راجع تعليق الدالة أعلاه.
    _report_text_glossed = _fix_price_column_currency_label(_report_text_glossed)
    # PR B §B9: قرِّب دقّةَ HHI العشرية الوهميّة إلى صحيح قبل التخزين/العرض.
    _report_text_glossed = _fix_hhi_false_precision(_report_text_glossed)
    # الموجة الرابعة: نفسُ النمط على المبالغ — خلف رايتها.
    if imports_spotlight():
        _report_text_glossed = _fix_amount_false_precision(_report_text_glossed)
    # الدراسة الحية الرابعة: بادئة مبتورة تسبق كلمتها الكاملة («سوي سويسرا»)
    # تُطوى بسجل تدقيق (كل رقعة مسجّلة قبل/بعد/موضعاً — شرط المُشرِف).
    _report_text_glossed, _prefix_repairs = \
        _fix_truncated_prefix_stutter(_report_text_glossed)
    # الدرس ٢٦١: رقعُ سطورِ العناوين تنضمّ إلى **القناة نفسِها**
    # (شرط المُشرِف C: لا تعديلَ صامتاً على نصٍّ مُسلَّم). الاسمُ
    # `_prefix_repairs` مُثبَّتٌ بقفلَي البند ١٧٥ فلا يُعاد تسميتُه.
    if _heading_repairs:
        _prefix_repairs = list(_prefix_repairs) + _heading_repairs
    # القاعدة العامة (قرار المالك): سنوات الحقائق المتقادِمة تُحسَب من **مصدرها
    # البنيوي** (silk_staleness) لا من النثر، فتُوسَم أينما وردت بأيّ صياغة، ولا
    # يُوسَم رمزُ HS. ثم تحقّقٌ: أيّ سنة حقيقة متقادِمة بلا وسمٍ في السرد
    # تُبلَّغ حدًّا (لا تُصحَّح صامتةً — عقد عدم الاختلاق).
    # القاعدة العامة (قرار المالك): سنوات الحقائق المتقادِمة تُحسَب من الحقل
    # البنيويّ `data_year` (silk_staleness) لا من النثر، فتُوسَم أينما وردت بأيّ
    # صياغة، ولا يُوسَم رمزُ HS. التوسيمُ حتميٌّ شاملٌ لكلّ سنةٍ في القائمة —
    # لا حاجة لمتحقّقٍ لاحق (كان `_stale_tag_misses` غيرَ قابلٍ للإطلاق عملياً،
    # مراجعة الشيفرة #5 — حُذف).
    from silk_staleness import stale_fact_years as _stale_fact_years
    _all_findings = [f for v in missions.values()
                     for f in (v.get("findings") or [])]
    _stale_set = _stale_fact_years(_all_findings)
    _report_text_glossed = _tag_stale_years(_report_text_glossed, _stale_set)
    # قرار المالك (تجاوز §5-الإتلاف، بلاغ تحليل 20): علَما «غير مكتمل» يُرفَعان
    # للعرض؛ الشارةُ تُصاغ في **كل مُصدِّرٍ بشكله** (md/docx/مختصر) لا تُحقَن في
    # `report.text` — إذ يُعيد docx تفسيرَ النصّ فتظهر الـmarkdown حرفياً ومكرَّرة
    # (مراجعة §58 #4). النصّ يبقى نظيفاً؛ العلَمان أدناه يقودان شاراتِ المُصدِّرين.
    _report_incomplete = bool(report_out.get("incomplete"))
    _missing_sections = list(report_out.get("missing_sections") or [])
    # **مراجعة §58 #2 (خطورةٌ عالية).** العلَمان مخزَّنان من لحظةِ الكتابة —
    # أي **قبل** تطبيع العناوين أعلاه. فالتقريرُ الذي يشفيه التطبيعُ كان
    # سيُسلَّم بأقسامه الأحد عشر حاضرةً وفوقها شارةُ «تقرير غير مكتمل: الأحد
    # عشر كلُّها غائبة» — إفصاحٌ كاذبٌ يصل العميل. يُعاد القياسُ من **النصّ
    # المعروض فعلاً**، و**خفضاً فقط**: لا يُوسَم تقريرٌ لم يكن موسوماً (لا
    # شارةَ جديدة من هذا السطر)، ولا يُخفى نقصٌ حقيقيٌّ باقٍ.
    if _headings_repaired and _report_incomplete and _clean_report:
        try:
            from silk_ai_judge import (_missing_sections as _ms_now,
                                       _writer_incomplete as _wi_now)
            # الفحصُ الكامل (نقصٌ بنيويّ **وقطعٌ وسط جملة**): تقريرٌ مقتطعٌ
            # يبقى موسوماً مهما شُفيت عناوينُه — لا نُخفي اقتطاعاً حقيقياً.
            _still = list(_ms_now(_clean_report, lang))
            if not _wi_now(_clean_report, lang):
                _report_incomplete = False
                _missing_sections = []
            elif len(_still) < len(_missing_sections):
                _missing_sections = _still
        except Exception as _me:  # noqa: BLE001 — إعادةُ القياس تحسينٌ لا شرط
            log.warning("incomplete flags not re-measured: %s", _me)
    out = {
        "market": result.get("market"),
        # Wave 2: اسم المنتج المدروس يصل عرض البحث كي يشتقّ منه المُصدِّرُ سطرَ
        # إخلاء المسؤولية بارامتريًّا (لا «التمور السعودية» مثبَّتة) وفلترةَ الجغرافيا.
        "product": result.get("product"),
        "trace_id": dr.get("trace_id"),
        # لافتة التدهور (بلاغ حي، بوابة ما قبل التشغيل api.py) — تصل هنا كي
        # يحملها كل مشتق (docx/مختصر/طرفية/لوحة) لا سطر ملاحظة وحيد مدفون.
        "degraded": bool(result.get("degraded")),
        "degraded_reason": result.get("degraded_reason") or "",
        "missions": missions,
        # سجل رقع العرض (شرط المُشرِف C: التعديل الصامت على نص مُسلَّم
        # ممنوع — كل رقعة قابلة للتدقيق بعد وقوعها).
        "render_repairs": _prefix_repairs,
        # تقرير ٧ §4.2: سجلُّ القناة الواحد — القناةُ الأولى وبديلُها المشروط
        # من أبواب الدخول المرتّبة عند المحلل، بحالةٍ صريحة (مرشّحةٌ من التحليل
        # لا قرارٌ مُثبَت). يقرؤه كلُّ سطحٍ من هنا لا من نثرٍ متفرّق.
        "entry_channel": entry_channel(by_category),
        # تقرير ٧ §4.3: الاشتراطاتُ بنوعها من المرجع حتمياً (لا من نثر البعثة).
        "requirements": _requirements_safe(result),
        "analyst": {"summary": analyst_report["summary"],
                   "missing_categories": analyst.get("missing_categories") or [],
                   "by_category": by_category,
                   # PART B2: التشخيص الذاتي (عدّاد الخام مقابل المُصنَّف +
                   # سبب «كل التقاطعات فارغة») يصل المدوّنة والواجهة فيُقرأ من
                   # GET /analyses/{id} مباشرة — الحادثة القادمة تُشخِّص نفسها.
                   "diagnostics": analyst.get("diagnostics") or {}},
        # سدّ تسريب (الطبقة ٦): تصنيف/تسمية الحكم مُحسَّبان هنا مرة واحدة —
        # لوحة الويب تستهلكهما بدل حساب تصنيفها الخاص من الرمز الخام
        # وعرض الرمز نفسه كنص ظاهر (كان "CONDITIONAL-GO"/"WATCH" يظهر
        # حرفياً على شارة الغلاف).
        "verdict_tone": verdict_tone,
        # الموجة ٠: نفس الاشتقاق الحتمي — التسمية وحدها تتبع لغة التقرير.
        "verdict_label": _verdict_label(verdict_tone, lang),
        "verdict": verdict,
        # فصلٌ بنيويّ بين الحكم والسرد (بلاغ المالك): **الحكم** يُشتقّ من
        # التوليف الحتمي (`silk_synthesis` — المرحلة ١ لا تُطفأ أبداً)، و**السرد**
        # طبقةُ نثرٍ لغويةٍ اختيارية. فشلُ نداء الكاتب يُعلَّم هنا وحده — ولا
        # يمسّ `verdict_tone`/`verdict_label` بحال. الواجهة/المُصدِّرات تعرض
        # «السرد غير متاح» في مكانه بدل تخفيض الشارة.
        "narrative": {
            "available": bool(report_out.get("report")),
            "reason": clean_failure_reason if not report_out.get("report") else "",
            "source": "llm",
        },
        # Wave 1.3: عقد تأكيد رمز HS — يعرضه كل مُصدِّر/لوحة كي يعيد تأطير
        # أرقام كومتريد «مؤشر سياقي» عند التعليم. None/غير مؤكَّد لا يُطأطئ شيئاً.
        "hs_confirmation": hs_conf or {},
        "hs_flagged": bool(hs_flagged),
        # البند 18: صندوق التحذير الواحد (فارغ حين لا تعليم) — انظر بناءه أعلاه.
        "caveat_box": _caveat_box,
        # WP-3 §2: تعارضات رقمية حُسمت — تُفصَح مرة واحدة في سجل الأدلة.
        "reconciliation": {"conflicts": _conflicts},
        # أسلوب التقرير المخزَّن (إعادة توليد أكاديمية) — تقرؤه التصديرات
        # لتختار القالب الافتراضي.
        "report_style": str(dr.get("report_style") or ""),
        # مراجعة شيفرة PR #147: نثر الصياغة التجارية المُخزَّن (WP-2 §3،
        # يكتبه مسار التصدير مرة واحدة عبر save_analysis) يُعاد حمله هنا
        # فلا يُعاد دفع نداءاته مع كل تصدير — مُطهَّراً كأي نص معروض.
        "client_fallback_prose": {
            str(k): _strip_internal_plumbing(str(v))
            for k, v in (dr.get("client_fallback_prose") or {}).items()
            if str(v or "").strip()},
        # Wave 3.1: سبب غياب السعر/كجم لكل صفّ سعر مرصود + سطر الفتح الوحيد.
        # صيد الفجوات ٣: (أ) السبب كان يُحسب على القيمة وحدها — قيمةٌ رقمية
        # («7.49») تُوسم «الوزن غير متاح» رغم أن الوزن معلَن في الملاحظة؛
        # صار التصنيف على القيمة ثم الملاحظة (الأصدق منهما). (ب) المفتاح
        # «store» كان يحمل الملاحظةَ المطهَّرة كاملةً لا متجراً — سُمّي صدقاً.
        # #13 ص14: سقالة الاستشهاد الخام بلغت رف العميل («[مرجع سوق] مبني
        # على: مرجع locale»، «HS040120…, USD») — الملاحظة تُنظَّف للعرض
        # وصفُّ المرجع الداخلي الخالص يُسقَط (انظر `_clean_price_row_note`).
        "price_rows": [
            row for row in (
                {"value": (_dp(x).get("value")),
                 "note": _clean_price_row_note(
                     _strip_internal_plumbing(str(_dp(x).get("note") or ""))),
                 # دورة C4: قيمة None تحتفظ بسببها («وحدة غامضة») — ضمُّ الملاحظة
                 # كان يجعل ذكرَ الوحدة في جملةِ نفيٍ «قابلاً للحساب»، وحرفية
                 # "None" كانت تُحقن في النص المصنف.
                 "reason": _price_row_reason_row(_dp(x))}
                for x in ((missions.get("pricing_scout") or {}).get("findings") or []))
            if (row["note"] or row["value"] is not None)
            and _is_price_row(row["value"], row["note"])],
        "price_unlock": PRICE_UNLOCK_LINE,
        # Wave 3.2: عند تعليم الرمز، التركّز (HHI) سياقٌ فقط لا إشارة تسجيل
        # للحكم لهذا المنتج — الشارة تستهلكها المُصدِّرات.
        # الصنف ١٠: الاتّساعُ المُهيَّأ يُعلِّم أرقامَ التركّز سياقاً كما
        # يُعلّمها عدمُ شمولِ الوصف — نفسُ المفتاح، فلا سطرَ عرضٍ ثانٍ.
        "concentration_context_only": bool(hs_flagged or _hs_broad),
        # Wave 6.1: شرطا قلب الحكم المهيكلان (حكم مراقبة/مشروط) — يعرضهما كل
        # مُصدِّر «شرطا قلب الحكم»، وتربط خارطة الـ٩٠ يوماً كل خطوة بأيّهما تُغلق.
        "flip_conditions": _flip_conditions(
            verdict_tone, hs_flagged,
            dr.get("importer_leads") or {},
            # اسم السوق يتبع اللغة أيضاً — «الأردن» مقابل «Jordan».
            ((result.get("market") or {}).get("name_ar") if lang == "ar"
             else (result.get("market") or {}).get("name_en")) or "",
            lang, (dr.get("verdict") or {}).get("decision_missing_components")),
        # الدرس ٢٦٢: ما تقادَم من معطيات السجلّ منذ كتابة التقرير — يقرؤه
        # المدقّقُ والبوّابة، وتُبنى عليه إعادةُ التوليد تحت الإنفاذ.
        "ledger_stale": _ledger_stale,
        "ledger_bind": _ledger_bind,
        "ledger_unresolved": dr.get("ledger_unresolved") or [],
        "report": {"text": _report_text_glossed,
                  "review_cycles": report_out.get("review_cycles", 0),
                  "unresolved_notes": clean_unresolved,
                  "failure_reason": clean_failure_reason,
                  # بلاغ تحليل 20: علَما «غير مكتمل» + الأقسام الغائبة — يقرؤهما
                  # مُصدِّر docx (لافتة بارزة) والواجهة، والنصّ يحمل الشارة أصلاً.
                  "incomplete": _report_incomplete,
                  "missing_sections": _missing_sections},
        # هدف الدراسة الاحترافية (البند ٦): فرضيات الاستدلال العابر للمهمات
        # — حتمية من الاكتشافات المخزَّنة (silk_inference)، تُبنى عند العرض
        # فتسري على الدراسات المخزونة بلا إعادة تشغيل؛ لا تمسّ الحكم.
        "hypotheses": _hypotheses_safe(dr),
        # B1 (SPEC-v2): مسرد المصطلحات المستعملة فعلاً — بنية يعرضها كل
        # مُصدِّر صراحةً (md/docx المدقّق/docx العميل).
        "glossary": _glossary,
        # C5 (SPEC-v2): قائمة مستوردين/موزعين قابلين للتواصل — بنية يعرضها
        # كل مُصدِّر كجدول في قسم الدخول (خرائط قوقل/Places + مرشّحو ويب).
        "importer_leads": _client_leads(
            dr.get("importer_leads"), result.get("market"),
            product=str(result.get("product") or ""),
            hs_code=result.get("hs_code"),
            report_text=_report_text_glossed),
        # مصدرُ الرمز حين حُسِم آلياً — يصل **عرضَ البحث العميق** لا الحدودَ
        # وحدها: تقريرُ العميل (المُسلَّم الفعليّ) يبني أقسامَه من
        # `deep_research` لا من `limits`، فوضعُه في الحدود وحدها أخرجه من
        # المستند الذي يراه العميل فعلاً. التقطه فحصُ «سلسلةُ الإفصاح في
        # تقريرٍ مُصيَّرٍ فعلاً» — لا اختبارُ وحدةٍ على العرض.
        "hs_provenance": _hs_prov_view,
        # سجلّ اشتقاق التصنيف الدائم (الموجة ٤ §3.1) — فصل/بند/بند فرعي
        # + الوصف الرسمي + أساس الحسم + جملة الاستبدال عند التعليم.
        "hs_derivation": _hs_derivation(result),
        "limits": limits,
        # سجلّ الفجوات المصنَّف G1–G4 (الموجة ١ — إضافي بجانب النص الحر):
        # كل حدّ بصنفه ومعناه للقارئ؛ المستهلكون القدامى يتجاهلونه بأمان.
        "gap_register": (_gap_register(limits)
                         if layer_enabled("GAP_REGISTER") else []),
        # المحرك الاقتصادي (الموجة ٣ — §5.4): مرساة السعر المطبّعة + الحل
        # العكسي لأقصى سعر مصنع + شلال الهوامش المُعلمَن + سؤال الإزاحة.
        # حتمي بالكامل؛ أي عطل = None لا كسر عرض.
        "economics": (_economics_view_safe(dr, result)
                      if layer_enabled("ECONOMICS_SECTION") else None),
        # عقد المالك (بلاغ UK الحي): لا يُسمّى مزوّد داخلي (Volza/Explee/…) على
        # أيّ سطح عميل — لغة أعمال عامة فقط. السطح التشغيلي (?internal=1) قد
        # يبقي التفصيل. الحارس النهائي: _CLIENT_VENDOR_NAMES في silk_reports.
        "next_step": (_i18n.t("next_step_deepen", lang)
                     if str(verdict.get("verdict") or
                           (verdict.get("ai") or {}).get("verdict") or "")
                        .upper().startswith(("GO", "PRELIMINARY GO")) else None),
        # وكيل الميثاق (محرك دراسة السوق، القاعدة ١؛ الموجة ١ — SHADOW):
        # إضافيٌّ بحت، مثل "trace" أعلاه — {} لتشغيلاتٍ سابقة لم تحمل ميثاقاً.
        "charter": dr.get("charter") or {},
        # سجلّ الحقائق (القاعدة ٢؛ الموجة ١ — SHADOW): إضافيٌّ بحت أيضاً —
        # {} لتشغيلاتٍ سابقة لم تحمل سجلّ حقائق (مُطعِّمٌ أُضيف لاحقاً).
        "fact_records": dr.get("fact_records") or {},
        # حقّ الحَكَم في الامتناع (القاعدة ٥؛ الموجة ٣ — SHADOW): إضافيٌّ
        # بحت أيضاً — {} لتشغيلاتٍ سابقة لم تحمل الإشارة.
        "judge_abstain_shadow": dr.get("judge_abstain_shadow") or {},
        # البند 7 (أمر إصلاح المحرّك): فحص اتجاه الحكم عبر التشغيلات —
        # يمرّ للعرض كي تقرأه بوابة الجودة على أي إعادة بناء (تصدير/تجديد)؛
        # {} لتشغيلات سابقة لم تحمله.
        "verdict_consistency": dr.get("verdict_consistency") or {},
    }
    # الموجة الرابعة: وارداتُ السوق بسلسلتها (البند ٢) وبياناتُ الرسوم (البند
    # ٣) — مفتاحان **إضافيّان** خلف رايتيهما؛ مطفأتين العرضُ حرفياً كما كان.
    if imports_spotlight():
        out["imports"] = _imports_view(result, dr, lang)
    if report_charts():
        out["charts"] = _charts_view(result, dr, out.get("imports"), lang,
                                     view=out)
    return out


def _fmt_usd(n: object, lang: str) -> str:
    """مبلغٌ بالدولار بلغة التقرير — العربيةُ عبر `fmt_amount` القائم، والإنجليزية
    بنفس عتبات المقدار (مليون/مليار) كي لا يُقرأ الرقمُ الخامُ بسبعِ خانات."""
    from silk_narrative import fmt_amount, fmt_number
    if lang != "en":
        return fmt_amount(n, "USD")
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    a = abs(v)
    if a >= 1e9:
        return f"USD {v / 1e9:,.2f}".rstrip("0").rstrip(".") + " billion"
    if a >= 1e6:
        return f"USD {v / 1e6:,.2f}".rstrip("0").rstrip(".") + " million"
    return f"USD {fmt_number(v, 0)}"


def _imports_view(result: dict, dr: dict, lang: str) -> "dict | None":
    """وارداتُ السوق من هذا الصنف **جاهزةً للعرض** — البند ٢ من الموجة الرابعة.

    المصدرُ الواحد `silk_deep_pillars.import_series`: نفسُ حقائق بعثة
    `trade_flow` التي يقرأ منها عمودُ السوق، **بلا نداءٍ جديد**. السنةُ التي
    تعذّر جلبُها تُعلَن ولا تُقدَّر؛ سنةٌ واحدةٌ مرصودة = رقمٌ بسنته بلا مسار
    (لا مسارَ بنقطةٍ واحدة). `None` حين لا رقمَ أصلاً — لا هيكلَ فارغ.
    """
    try:
        import silk_deep_pillars as _P
        import silk_i18n as _I
        from silk_narrative import fmt_pct, growth_phrase
        s = _P.import_series(dr.get("missions") or {})
    except Exception as e:  # noqa: BLE001 — طبقةُ عرضٍ لا تُسقِط العرض
        log.warning("imports view skipped: %s", e)
        return None
    pts = s.get("series") or []
    if not pts:
        return None
    latest = pts[-1]
    out = {
        "head": _I.t("imports_head", lang),
        "series": pts,
        "source": latest.get("source") or "UN Comtrade",
        "latest_year": latest["year"],
        "latest_value_usd": latest["value"],
        "value_line": _I.t("imports_value_line", lang,
                           amount=_fmt_usd(latest["value"], lang),
                           year=latest["year"],
                           source=latest.get("source") or "UN Comtrade"),
        "growth_pct": s.get("growth_pct"),
        "cagr_pct": s.get("cagr_pct"),
        "years_missing": s.get("years_missing") or [],
    }
    if len(pts) >= 2 and s.get("growth_pct") is not None:
        g = float(s["growth_pct"])
        y0, y1 = pts[0]["year"], pts[-1]["year"]
        has_cagr = s.get("cagr_pct") is not None
        out["growth_line"] = _I.t(
            "imports_growth_line" if has_cagr else "imports_growth_line_nocagr",
            lang,
            phrase=growth_phrase(s.get("cagr_pct"), g, f"{y0}–{y1}"),
            verb=("grew" if g >= 0 else "shrank"),
            growth=fmt_pct(abs(g)), first_year=y0, last_year=y1,
            cagr=(fmt_pct(s["cagr_pct"]) if has_cagr else ""))
    elif len(pts) >= 2:
        # سنتان فأكثر ولا نموَّ محسوب (مراجعة §58): غيابٌ يُقال لا يُسكَت.
        out["note"] = _I.t("imports_trend_not_computed", lang)
    if len(pts) < 2:
        out["note"] = _I.t("imports_single_year_note", lang,
                           year=latest["year"])
    # فاصلُ القائمة يتبع لغةَ التقرير: الفاصلةُ العربية «،» حرفٌ عربيّ،
    # ووجودُها في سطرٍ إنجليزيٍّ تسرّبُ لغةٍ تُسقِط المستندَ كلَّه ببوّابة
    # اللغة — التقطته صورةُ الرسم في مُسلَّمٍ إنجليزيّ (مراجعة §58).
    _sep = ", " if lang == "en" else "، "
    if out["years_missing"]:
        out["gap_line"] = _I.t("imports_gap_years_note", lang,
                               years=_sep.join(str(y) for y in
                                               out["years_missing"]))
    if any(p.get("mirrored") for p in pts):
        out["mirror_line"] = _I.t(
            "imports_mirrored_note", lang,
            years=_sep.join(str(p["year"]) for p in pts if p.get("mirrored")))
    # نصيبُ السعودية من هذه الواردات — من مكوّن الصفّ نفسِه (لا حسابَ ثانٍ).
    comps = (((result.get("markets") or [None])[0]) or {}).get("components") \
        or {}
    sp = _dp(comps.get("saudi_position")) if comps.get("saudi_position") else {}
    if isinstance(sp.get("value"), (int, float)):
        out["saudi_share_pct"] = float(sp["value"])
        # مراجعة §58: سنةُ الحصّة سنتُها هي لا سنةُ الواردات — بلا `data_year`
        # يُقال الرقمُ بلا سنةٍ مُستعارة (لا اختلاقَ سنة).
        if sp.get("data_year"):
            out["saudi_line"] = _I.t("imports_saudi_line", lang,
                                     pct=fmt_pct(sp["value"]),
                                     year=sp["data_year"])
        else:
            out["saudi_line"] = _I.t("imports_saudi_line_noyear", lang,
                                     pct=fmt_pct(sp["value"]))
    return out


# ── الموجة الخامسة: سجلُّ الرسوم عبر التقرير كلّه ────────────────────────────
# كلُّ رسمٍ دالّةٌ صغيرة تعيد قاموساً أو `None`؛ العقدُ الواحد للويب (SVG) وWord
# (PNG من `silk_chart_image`): {id, kind, unit, title, section, series, source,
# year, note}. الأنواع: `bars` (أعمدة أفقية) / `range` (شريط من أدنى إلى
# أعلى) / `gauge` (قيمةٌ على مناطق). الأقسام: market / competition / economics.
# قاعدةُ الغياب: لا بياناتٍ كافية ⇒ لا رسم (المالك: «يختفي الرسم كلياً»).
CHART_SECTIONS: tuple = ("market", "competition", "economics")
CHART_KINDS: tuple = ("bars", "range", "gauge")

_CURRENCY_TOKEN_RE = re.compile(r"[^\s\d]{1,6}")

_SCENARIO_KEYS = {"منخفض": "chart_scenario_low", "متوسط": "chart_scenario_mid",
                  "مرتفع": "chart_scenario_high"}


_AR_SCRIPT_RE = re.compile(r"[\u0600-\u06FF]")


def _chart_unit_fits_lang(unit: str, lang: str) -> bool:
    """وحدةُ الرسم بلغة التقرير — عملةٌ عربيةٌ يكتبها المحرّك («دينار/كجم») لا
    تصل عنوانَ رسمٍ إنجليزيّ (فتُسقِطه بوّابةُ تسرّب اللغة كلَّ المستند)."""
    return lang != "en" or not _AR_SCRIPT_RE.search(str(unit or ""))


def _chart_labels_fit_lang(rows: list, lang: str) -> bool:
    """التسمياتُ بلغة التقرير — **الفصلُ الصلب لا الترجمة** (سابقةُ
    `_client_decision_numbers_table`: قالبٌ عربيٌّ يكتبه المحرّك يُسقَط على
    التقرير الإنجليزيّ ولا يُترجَم في العرض).

    المِعيارُ بنيويّ: تسميةٌ تحمل حرفاً عربياً على تقريرٍ إنجليزيّ ⇒ لا رسم.
    والعكسُ يمرّ: اسمُ علَمٍ لاتينيّ («Brazil») تسميةٌ صحيحةٌ في تقريرٍ عربيّ.
    """
    if lang != "en":
        return True
    return not any(_AR_SCRIPT_RE.search(str(r.get("label") or ""))
                   for r in rows)


def _chart_imports_trend(imports: "dict | None", lang: str) -> "dict | None":
    import silk_i18n as _I
    pts = (imports or {}).get("series") or []
    # مراجعة §58: عمودٌ واحدٌ بعنوان «بالسنوات» ومعه تعليقٌ يقول «لا يُرسَم
    # مسارٌ بلا سنتين» — الرسمُ يكذّب تعليقَه. سنتان شرطُ المسار كما هو شرطُ
    # جدولِ الواردات نفسِه (`_client_imports_section`).
    if len(pts) < 2:
        return None
    return {
        "id": "imports_trend", "kind": "bars", "unit": "USD",
        "section": "market",
        "title": _I.t("chart_imports_trend", lang),
        "series": [{"label": str(p["year"]), "year": p["year"],
                    "value": p["value"], "muted": bool(p.get("mirrored"))}
                   for p in pts],
        "source": (imports or {}).get("source") or "UN Comtrade",
        "year": f"{pts[0]['year']}–{pts[-1]['year']}",
        # مراجعة §58: عمودٌ باهتٌ (مرآة) بلا تعليلٍ على الرسم نفسِه لغز —
        # السطورُ الثلاثة تُضمّ معاً.
        "note": " · ".join(x for x in (
            (imports or {}).get("note"), (imports or {}).get("gap_line"),
            (imports or {}).get("mirror_line")) if x),
    }


def _chart_supplier_shares(dr: dict, lang: str) -> "dict | None":
    import silk_i18n as _I
    try:
        import silk_deep_pillars as _P
        rows, src_f = _P.top_supplier_shares(dr.get("missions") or {})
    except Exception as e:  # noqa: BLE001
        log.warning("supplier shares chart skipped: %s", e)
        return None
    if not rows:
        return None
    series = [{"label": r["partner"], "value": r["share"],
               "highlight": bool(r.get("saudi"))} for r in rows]
    # تسمياتُ هذا الرسم وحدَها تأتي من خارج المحرّك (أسماءُ الشركاء) — فحصُ
    # اللغة يسري عليها كسائر الرسوم (مراجعة §58: لا استثناءَ لمصدرٍ خارجيّ).
    if not _chart_labels_fit_lang(series, lang):
        return None
    year = (src_f or {}).get("year")
    return {
        "id": "supplier_shares", "kind": "bars", "unit": "%",
        "section": "market",
        "title": _I.t("chart_supplier_shares", lang),
        "series": series,
        "source": (src_f or {}).get("source") or "UN Comtrade",
        "year": str(year) if year else "",
        "note": (_I.t("chart_saudi_highlight_note", lang)
                 if any(r.get("saudi") for r in rows) else
                 _I.t("chart_saudi_absent_note", lang)),
    }


def _chart_demand_interest(dr: dict, lang: str) -> "dict | None":
    """اهتمامُ البحث النسبي: قيمُ Google Trends (0–100) لعدّة استعلاماتٍ من
    بعثة `demand_trends` — التسميةُ نصُّ البعثة نفسُه، لا رقمٌ مستخلَص."""
    import silk_i18n as _I
    m = (dr.get("missions") or {}).get("demand_trends")
    findings = (m.get("findings") if isinstance(m, dict)
                else getattr(m, "findings", None)) or []
    rows, years = [], []
    for f in findings:
        val = f.get("value") if isinstance(f, dict) else getattr(f, "value", None)
        src = str((f.get("source") if isinstance(f, dict)
                   else getattr(f, "source", "")) or "")
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        if "trends" not in src.lower() or not (0 <= float(val) <= 100):
            continue
        note = str((f.get("note") if isinstance(f, dict)
                    else getattr(f, "note", "")) or "")
        label = note.split(";")[0].strip()
        if not label:
            continue
        rows.append({"label": label, "value": float(val)})
        y = f.get("data_year") if isinstance(f, dict) else getattr(f, "data_year", None)
        if isinstance(y, int):
            years.append(y)
    if len(rows) < 2 or not _chart_labels_fit_lang(rows, lang):
        return None
    return {
        "id": "demand_interest", "kind": "bars", "unit": "index",
        "section": "market",
        "title": _I.t("chart_demand_interest", lang),
        "series": rows, "source": "Google Trends",
        "year": str(max(years)) if years else "",
        "note": _I.t("chart_demand_interest_note", lang),
    }


def _chart_supplier_concentration(dr: dict, eco: dict, lang: str,
                                  context_only: bool = False) -> "dict | None":
    """تركّزُ المورّدين: قيمةُ HHI المحسوبة (`economics.hhi`) على مناطقٍ ثلاث من
    ثوابت `silk_economics` — لا عتبةَ ثانية في العرض.

    ورمزٌ مُعلَّمٌ أو مُهيَّأٌ اتّساعاً يجعل الرقمَ سياقاً عامّاً للفئة لا قياساً
    لهذا المنتج؛ التحفّظُ إلزاميٌّ على كلّ سطحٍ يعرضه (`concentration_context_line`
    — المفتاحُ نفسُه الذي يطبعه مُسلَّم العميل)، والصورةُ سطحٌ كسائرها."""
    import silk_i18n as _I
    import silk_economics as _E
    hhi = (eco or {}).get("hhi")
    band = _E.hhi_band(hhi)
    if band is None:
        return None
    labels = {"open": _I.t("chart_band_open", lang),
              "moderate": _I.t("chart_band_moderate", lang),
              "high": _I.t("chart_band_high", lang)}
    # الدرس ٢٧٠: القيمةُ والسنةُ والمصدرُ من حقيقةٍ واحدة (`silk_economics.
    # hhi_fact` عبر العرض الاقتصادي) — لا قارئَ ثانياً للإسناد في المُصيِّر.
    src = str((eco or {}).get("hhi_source") or "")
    year = (eco or {}).get("hhi_year")
    return {
        "id": "supplier_concentration", "kind": "gauge", "unit": "index",
        "metric": "hhi", "section": "competition",
        "title": _I.t("chart_supplier_concentration", lang),
        "value": float(hhi), "band": band, "band_label": labels[band],
        "bands": [
            {"key": "open", "label": labels["open"], "from": 0,
             "to": _E.HHI_MODERATE_CONCENTRATION},
            {"key": "moderate", "label": labels["moderate"],
             "from": _E.HHI_MODERATE_CONCENTRATION,
             "to": _E.HHI_HIGH_CONCENTRATION},
            {"key": "high", "label": labels["high"],
             "from": _E.HHI_HIGH_CONCENTRATION, "to": _E.HHI_SCALE_MAX}],
        "series": [{"label": labels[band], "value": float(hhi)}],
        "source": src, "year": str(year) if year else "",
        "note": " ".join([_I.t("chart_hhi_note", lang)]
                         + ([_I.t("concentration_context_line", lang)]
                            if context_only else [])),
    }


def _chart_landed_cost_ladder(eco: dict, lang: str) -> "dict | None":
    """سلّمُ التكلفة من المصنع إلى الرف: خطواتُ `economics.waterfall` بترتيبها؛
    الخطوةُ المعلميّة باهتة (`muted`) — معلمةٌ معلنةٌ لا رقمٌ مرصود."""
    import silk_i18n as _I
    steps = (eco or {}).get("waterfall") or []
    rows, dropped = [], 0
    for st in steps:
        if not isinstance(st, dict):
            continue
        v = st.get("value")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None   # خطوةٌ بلا رقم = سلّمٌ لا يُرسَم (لا صفرَ مختلَق)
        # مراجعة §58: «سلّمٌ» محورُه مستوياتٌ تراكمية؛ وصفٌّ أدنى مما قبله
        # زيادةٌ مفردة (مبلغُ الشحن مثلاً) لا مستوى — ووضعُه على المحور نفسِه
        # خلطُ مقياسين يُظهِره عموداً لا يُذكَر بجوار تسميةٍ تُقرأ درجةً.
        # القاعدةُ بنيويةٌ لا نصّية: المستوى لا ينقص عن سابقه.
        if rows and float(v) < rows[-1]["value"]:
            dropped += 1
            continue
        rows.append({"label": str(st.get("name") or ""), "value": float(v),
                     "muted": bool(st.get("is_parameter"))})
    if len(rows) < 2 or not _chart_labels_fit_lang(rows, lang):
        return None
    # الوحدةُ: **عملةُ التكلفة كما صرّح بها المالكُ في البطاقة**
    # (`economics.cost_currency`). ملاحظةُ الخطوة الأولى كانت المصدرَ، وهي
    # افتراضُ `margin_waterfall(currency="USD")` الذي لا يصرّح به أحد — فكان
    # المحور يُوسَم «دولاراً» ويُطبَع بعلامته لمبلغٍ بالدينار (مراجعة §58،
    # H1). عملةٌ غيرُ مصرَّحٍ بها ⇒ لا رسم (وحدةٌ مجهولة لا تُوسَم).
    unit = str((eco or {}).get("cost_currency") or "").strip()
    if not unit or not _CURRENCY_TOKEN_RE.fullmatch(unit) \
            or not _chart_unit_fits_lang(unit, lang):
        return None
    note = _I.t("chart_landed_cost_note", lang)
    if dropped:
        note = note + " " + _I.t("chart_landed_cost_increment_note", lang)
    return {
        "id": "landed_cost_ladder", "kind": "bars", "unit": unit,
        "section": "economics",
        "title": _I.t("chart_landed_cost_ladder", lang, unit=unit),
        "series": rows, "source": _I.t("chart_source_cost_model", lang),
        "year": "", "note": note,
    }


def _chart_max_exw_scenarios(eco: dict, lang: str) -> "dict | None":
    """أقصى سعرِ مصنعٍ بالسيناريوهات الثلاثة من الحلّ العكسي؛ السيناريو
    المعتمد في المتن (`headline_scenario`) مميَّز.

    وحين يرصد المحرّكُ تناقضَ التسعير (`economics.pricing_contradiction` —
    الرقمُ أدنى بأكثر من 20% من سعر الاستيراد المرصود) فالتحذيرُ **إلزاميٌّ
    على كلّ سطحِ عرض**: عمودٌ ذهبيٌّ بلا تحفّظٍ يُقرأ سقفاً تفاوضياً، وهو
    عينُ ما يحظره المحرّك (مراجعة §58، H2)."""
    import silk_i18n as _I
    rs = (eco or {}).get("reverse_solve") or {}
    scen = rs.get("scenarios") or []
    rows = []
    for sc in scen:
        if not isinstance(sc, dict):
            continue
        v = sc.get("max_exw")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        key = _SCENARIO_KEYS.get(str(sc.get("scenario") or ""))
        label = _I.t(key, lang) if key else str(sc.get("scenario") or "")
        rows.append({"label": label, "value": float(v),
                     "highlight": str(sc.get("scenario")) == str(rs.get("headline_scenario"))})
    if len(rows) < 2 or not _chart_labels_fit_lang(rows, lang):
        return None
    unit_word = str(rs.get("unit") or "").strip()
    if lang == "en":
        unit_word = {"كجم": "kg", "لتر": "liter", "طن": "ton"}.get(unit_word, unit_word)
    unit = "/".join(x for x in (str(rs.get("currency") or "").strip(),
                                unit_word) if x)
    if not unit or not _chart_unit_fits_lang(unit, lang):
        return None
    return {
        "id": "max_exw_scenarios", "kind": "bars", "unit": unit,
        "section": "economics",
        "title": _I.t("chart_max_exw_scenarios", lang, unit=unit),
        "series": rows, "source": _I.t("chart_source_shelf_model", lang),
        "year": "",
        "note": " ".join(
            [_I.t("chart_max_exw_note", lang)]
            + ([_I.t("chart_max_exw_contradiction_note", lang)]
               if (eco or {}).get("pricing_contradiction") else [])),
    }


def _charts_decision_ranges(eco: dict, lang: str) -> list:
    """مدى أرقام القرار: التقديراتُ (`tier == "estimated"`، بمدىً وغيرُ واسعةٍ
    جداً) مجمَّعةً بالوحدة — رسمٌ لكلّ وحدةٍ بصفَّين فأكثر (لا رسمَ لشريطٍ واحد)."""
    import silk_i18n as _I
    dn = (eco or {}).get("decision_numbers") or []
    by_unit: dict = {}
    for e in dn:
        if not isinstance(e, dict) or e.get("tier") != "estimated" \
                or e.get("too_wide"):
            continue
        rng = e.get("range") or {}
        lo, hi = rng.get("low"), rng.get("high")
        if any(isinstance(x, bool) or not isinstance(x, (int, float))
               for x in (lo, hi)):
            continue
        unit = str(e.get("unit") or "").strip()
        if not unit:
            continue
        val = e.get("value")
        by_unit.setdefault(unit, []).append({
            "label": str(e.get("name") or ""), "low": float(lo),
            "high": float(hi),
            "value": float(val) if isinstance(val, (int, float))
            and not isinstance(val, bool) else None})
    out = []
    for unit, rows in by_unit.items():
        if len(rows) < 2 or not _chart_labels_fit_lang(rows, lang) \
                or not _chart_unit_fits_lang(unit, lang):
            continue
        # مراجعة §58: تعليقُ الرسم يقول «كلُّ شريطٍ من أدنى تقديرٍ إلى أعلاه»؛
        # فصفوفٌ كلُّها نقطيةٌ (أدنى = أعلى) رسمُ مدىً بلا مدى — يُسقَط، وتبقى
        # الأرقامُ في جدول أرقام القرار كما هي.
        if not any(r["high"] > r["low"] for r in rows):
            continue
        out.append({
            "id": f"decision_ranges_{len(out) + 1}", "kind": "range",
            "unit": unit, "section": "economics",
            "title": _I.t("chart_decision_ranges", lang, unit=unit),
            "series": rows, "source": _I.t("chart_source_estimates", lang),
            "year": "", "note": _I.t("chart_decision_ranges_note", lang),
        })
    return out


# الرسومُ التي تُرسِم **قياساً مرصوداً** (لا نموذجَ تكلفةٍ معلمياً) — سنةُ
# الرقم جزءٌ من الرقم فيها (الدرس ٢٥٦)، وغيابُها يُقال لا يُحذَف.
_MEASURED_CHART_IDS = frozenset((
    "imports_trend", "supplier_shares", "demand_interest",
    "supplier_concentration"))


def _chart_declare_year(chart: dict, lang: str) -> dict:
    """سنةٌ غائبةٌ عن رسمٍ مرصود **تُعلَن** في ملاحظته (مراجعة §58): «UN
    Comtrade · مقياس…» بلا سنةٍ يُقرأ رقماً راهناً، والحذفُ أسوأُ من الإعلان."""
    import silk_i18n as _I
    if chart.get("id") in _MEASURED_CHART_IDS \
            and not str(chart.get("year") or "").strip():
        note = str(chart.get("note") or "").strip()
        chart["note"] = (note + " " + _I.t("chart_year_unknown", lang)).strip()
    return chart


def _charts_view(result: dict, dr: dict, imports: "dict | None",
                 lang: str, view: "dict | None" = None) -> list:
    """بياناتُ الرسوم **محضةً** — البند ٣ ثم الموجة الخامسة: الواجهةُ ترسم ولا
    تحسب، وWord يرسم من القاموس نفسه.

    كلُّ رسمٍ يحمل قسمَه ومصدرَه وسنتَه وملاحظةَ نقصِه؛ قيمةٌ غائبة تصل `None`
    (لا صفر) فتُرسَم «—» بلا عمود. الرسومُ بلا بياناتٍ لا تُضاف (لا محورَ
    فارغ). لا خلطَ وحداتٍ على محورٍ واحد: رسمٌ لكلّ وحدة. رسمٌ يتعطّل بناؤه
    يُسقَط معلَناً في السجلّ ولا يُسقِط العرض.
    """
    charts: list = []
    # الاقتصادُ يُحسَب في عرض البحث العميق (`view["economics"]`) لا في النتيجة
    # الخام — الرسومُ الاقتصادية تقرأ من العرض المبنيّ كي لا يُحسَب مرّتين.
    eco = (view or {}).get("economics") or {}
    ctx_only = bool((view or {}).get("concentration_context_only"))
    builders = (
        lambda: _chart_imports_trend(imports, lang),
        lambda: _chart_supplier_shares(dr, lang),
        lambda: _chart_demand_interest(dr, lang),
        lambda: _chart_supplier_concentration(dr, eco, lang, ctx_only),
        lambda: _chart_landed_cost_ladder(eco, lang),
        lambda: _chart_max_exw_scenarios(eco, lang),
        lambda: _charts_decision_ranges(eco, lang),
    )
    for build in builders:
        try:
            got = build()
        except Exception as e:  # noqa: BLE001
            log.warning("report chart skipped: %s", e)
            continue
        for ch in (got if isinstance(got, list) else [got]):
            if ch and ch.get("series"):
                charts.append(_chart_declare_year(ch, lang))
    return charts


def _public_url(source: str) -> str:
    """رابط مجموعة البيانات الرسمي من السجلّ العمومي — "" عند عدم المعرفة
    (لا رابط مختلَق). استيراد كسول كي يبقى العرض بلا تبعية إجبارية."""
    try:
        from silk_data_layer import public_source_url
        return public_source_url(source) or ""
    except Exception:
        return ""



# ── صمّامات الطبقات المرئية (طلب المالك 2026-08-19) ──────────────────────────
# كل طبقة أضافها التوجيه وتراها العين لها مفتاح إطفاء فوري في الإنتاج، بلا
# revert ولا إعادة نشر. **الافتراض ON** — الإطفاء قرار مشغّل صريح يعيد سلوك
# ما قبل الموجة حرفياً (عكسُه انحدارٌ عن سلوكٍ تحقّق منه المالك فعلاً).
def layer_enabled(name: str) -> bool:
    """هل طبقة العرض `name` مفعّلة؟ — `SILK_<NAME>_ENABLED=0/false/off` يطفئها."""
    import os as _os
    raw = _os.environ.get(f"SILK_{name}_ENABLED", "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _clip_words(text: str, limit: int) -> str:
    """قصٌّ على حدّ كلمة لا وسطها — «التكلفة الواصلة» لا تصير «التكلفة ال».

    قاعدة «لا نقاط حذف» البنائية (بلاغ حجب #12): لا سلسلة مبنيّة تُذيَّل
    بـ«…» — كان الذيل هنا يصل سطرَ «بنداً تحتاج تحققاً» على سطوح الحكم
    فيُبقي بوابة نصّ المُنتَج مُطلَقة حتى بعد إعادة التوليد. القصُّ يُعلَن
    لاحقةً مقروءة والتفصيل الكامل في قسم «حدود هذا التقرير» نفسه."""
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0] or t[:limit]
    # دورة C4: اسم القسم كما هو حرفياً («حدود هذا التقرير») — لا صيغة ثانية
    # للقسم نفسه على السطر الواحد (سطر الفجوات يحيل إليه بالاسم الكامل).
    return cut.rstrip("،؛,:") + " (مختصر — التفصيل في حدود هذا التقرير)"


def verification_gap_line(jury: dict | None, gap_sources: list | None) -> str:
    """سطر «الفجوات» الواحد لكل سطوح الحكم (LESSONS 88 — قناة واحدة).

    الحادثة: حقل «بنود تحتاج تحققاً» في جدول الحكم كان يقرأ
    `jury["data_gaps"]` = أسماء وكلاء الفرز **المنهارين** حصراً
    (`silk_agents.py`), وهي قناة تفرغ بالبناء متى نجح الفرز — بينما الفجوات
    الحقيقية انتقلت إلى `limits`/`gap_register`. فأعلن الجدول «لا شيء»
    بينما التقرير نفسه يسرد أحد عشر بنداً. القاعدة العامة: **كل سطح حكم
    يقرأ من هذا المُجمِّع** — لا سجلّ فجوات ثانٍ.

    One canonical verification-gap line for every verdict surface: merges the
    real declared-gap register with any crashed-agent names. Never returns
    «لا شيء» while real gaps exist.
    """
    from silk_narrative import internal_ar
    agent_gaps = [internal_ar(g) for g in ((jury or {}).get("data_gaps") or [])]
    real = [str(g).strip() for g in (gap_sources or [])
            if isinstance(g, str) and str(g).strip()]
    if not real and not agent_gaps:
        return "لا شيء"
    parts = []
    if real:
        head = "؛ ".join(_clip_words(t, 70) for t in real[:2])
        more = (f" (+{len(real) - 2} بنداً — انظر «حدود هذا التقرير»)"
                if len(real) > 2 else "")
        parts.append(f"{len(real)} بنداً تحتاج تحققاً: {head}{more}")
    if agent_gaps:
        parts.append("وكلاء بلا بيانات: " + "، ".join(agent_gaps))
    return " | ".join(parts)


def _gap_register(limits: list) -> list:
    """سجلّ فجوات مهيكل G1–G4 من سطور الحدود (الموجة ١) — تصنيف حتمي من
    النص، بلا شبكة؛ أي عطل = قائمة فارغة (لا يكسر العرض)."""
    try:
        from silk_data_layer import GAP_CLASS_LABEL_AR, classify_gap_class
        return [{"text": l, "gap_class": classify_gap_class(l),
                 "gap_class_label": GAP_CLASS_LABEL_AR[classify_gap_class(l)]}
                for l in (limits or []) if isinstance(l, str) and l.strip()]
    except Exception:
        return []


def _economics_view_safe(dr: dict, result: dict) -> dict | None:
    """قسم الاقتصاد (الموجة ٣) — silk_economics.economics_view بغلاف آمن."""
    try:
        from silk_economics import economics_view
        eco = economics_view(dr, product_card=result.get("product_card"),
                             category=str(result.get("product") or ""),
                             market_iso3=str((result.get("market") or {}).get("iso3") or ""),
                             hs_code=result.get("hs_code"))
        # تطهير نصوص المرساة قبل أي سطح عرض (عائلة LESSONS 11/57): ملاحظة
        # البعثة الخام تصل حقل source — تمرّ بالمُطهِّر كسائر الملاحظات.
        anchor = (eco or {}).get("anchor_price")
        if isinstance(anchor, dict):
            for k in ("source", "note"):
                anchor[k] = _strip_internal_plumbing(str(anchor.get(k) or ""))
        return eco
    except Exception:
        return None


def _vintage_caveat_safe(dp_or_year: object) -> str:
    """تحذير القِدم بطبقتيه (الموجة ١) — يقبل البند كاملاً (فتُقرأ سنته عبر
    fact_year بكل مسانده البنيوية: data_year ثم وسم year= ثم retrieved_at)
    أو سنةً صريحة؛ "" عند غياب السنة أو أي عطل."""
    try:
        import silk_staleness
        return silk_staleness.vintage_caveat(dp_or_year) if dp_or_year else ""
    except Exception:
        return ""


# ── الموجة C · C1 — الحواجزُ التنظيمية تصل العرض بنيوياً ──────────────────

def _regulatory_state(result: dict) -> dict:
    """اجمع حالةَ الحواجز التنظيمية من صفوف الأسواق — بلا مطابقةِ عبارات.

    قبل الموجة C كان حكمُ الأهلية يعيش **ملاحظةً نصّية** مُعلَّقةً على بنودٍ
    لاحقة، فلا يستطيع أيُّ مستهلِكٍ أن يقرّر منه شيئاً. الآن يُرفَع إلى
    `view["regulatory"]` فتقرؤه البوّابةُ الحاجزة والمُصدِّرات معاً — مصدرٌ
    واحد لا اثنان.

    تُمسَح **كلُّ** الأسواق المرفقة: تقريرٌ فيه سوقٌ محجوبٌ وآخرُ سالك لا يجوز
    أن يُخفي الأول. وغيابُ الحقل كلِّه يعني «لم تُفحَص» لا «لا حاجز».
    """
    rows = [r for r in (result.get("markets") or []) if isinstance(r, dict)]
    states = [r["regulatory"] for r in rows
              if isinstance(r.get("regulatory"), dict)]
    if not states:
        return {}

    def _merge(key: str) -> list:
        seen, out = set(), []
        for st in states:
            for row in (st.get(key) or []):
                sig = (row.get("item"), row.get("seq"))
                if sig in seen:
                    continue
                seen.add(sig)
                out.append(row)
        return out

    timeline = next((st.get("access_timeline") for st in states
                     if st.get("access_timeline")), {})
    return {"open_hard": _merge("open_hard"),
            "needs_verification": _merge("needs_verification"),
            "all": _merge("all"), "checked": True,
            "access_timeline": timeline}


def _ledger_safe(result: dict, lang: str = "ar") -> dict:
    """سجلّ الحقائق بغلافٍ آمن (الدرس ٢٦٢) — عطلُه لا يُسقِط تصييراً."""
    try:
        import silk_fact_ledger
        return silk_fact_ledger.build_ledger(result, lang)
    except Exception as exc:  # noqa: BLE001 — إضافةٌ لا شرطُ عرض
        log.warning("fact ledger skipped: %s", exc)
        return {}


def build_view(result: dict, lang: str = "ar") -> dict:
    """ابنِ نموذج العرض القانوني — the ONE canonical view-model (vision §10.1).

    كل المخرجات (لوحة/طرفية/Streamlit/مختصر) تشتق من هذا النموذج حصراً.

    `lang` (الموجة ٠ — لغة المصنع تحكم لغة التقرير): **معامل عرضٍ بحت**. لا
    يغيّر رقماً ولا حكماً ولا ثقةً ولا دليلاً — الكائن التحليلي واحدٌ للّغتين،
    والتسميات القالبية وحدها تتبعه. يُرفَع إلى `view["report_language"]` فيقرؤه
    كل مُصدِّر (docx/pdf/markdown/brief) بدل تمريره مرّةً أخرى في كل توقيع.
    الافتراض `"ar"`: كل مستدعٍ قائم يبقى على سلوكه حرفياً.
    """
    import silk_i18n
    lang = silk_i18n.normalize(lang)
    markets = result.get("markets") or []
    from silk_narrative import internal_ar
    top = markets[0] if markets else None
    decision = _decision(top)
    # حكم واحد لا حكمان (إصلاح مراجعة Stage 5): عند وجود قرار المحرك الموزون
    # (§8) الصالح فهو **الحكم الوحيد** في كل التقرير — هيئة المحلفين تتحول إلى
    # سطر كفاية بيانات بلا كلمة حكم (خطة §8a: الجورية بوابة كفاية لا قرار).
    ed_top = (top or {}).get("decision") or {}
    # (البند 2): حكمٌ فارغ (امتناعٌ ببيانات دون الحد الأدنى) لا يحلّ محلّ
    # سطر الجورية على مسار /analyze أيضاً — نفس عقد المسار العميق (:2360).
    if ed_top.get("schema") and not ed_top.get("error") \
            and ed_top.get("verdict"):
        jury = (top or {}).get("jury") or {}
        # LESSONS 88: القناة الواحدة — يُعاد بناء هذا السطر بعد اكتمال
        # `limits` أدناه (الحدود لم تُبنَ بعد عند هذه النقطة)؛ القيمة هنا
        # مبدئية من قناة الوكلاء وحدها.
        gaps_ar = verification_gap_line(jury, None)
        decision = {
            # الموجة ٥: القاعدة قبل الحكم + الحجة المضادة — من المحرك حصراً.
            "rule": (ed_top.get("decision_rule")
                     if layer_enabled("VERDICT_STRUCTURE") else None),
            "verdict": ed_top.get("verdict"),
            "confidence": ed_top.get("confidence"),
            "score": ed_top.get("score"),
            "why": ed_top.get("why"),
            "counter_case": (ed_top.get("counter_case")
                             if layer_enabled("VERDICT_STRUCTURE") else None),
            "market": (top or {}).get("country"),
            "stage": "silk.decision/v1 — المحرك الموزون (الحكم الوحيد)",
            "sufficiency": (f"بوابة كفاية البيانات: {jury.get('agents_with_data', 0)}/"
                            f"{jury.get('agents_total', 0)} وكلاء أساسيون لديهم "
                            f"بيانات؛ فجوات: {gaps_ar}"),
            # سدّ تسريب (الطبقة ٦): نفس تصنيف الشارة المحسوب لمسار الجورية
            # الاحتياطي أعلاه — هذا الفرع (محرك §8) هو الشائع فعلياً.
            "tone": _verdict_tone(ed_top.get("verdict")),
        }
        # **الموجة Z · Z-06.** أساسُ الحكم جاهزاً للعرض — بنيةٌ واحدة
        # يستهلكها docx العميل والـPDF و`web/platform.html` معاً. الثقةُ
        # المُمرَّرة هي **المعروضة** (المسقوفة عند تعليم رمز HS) لا ثقةُ
        # المحرّك الخام، فلا يظهر رقمان في مستندٍ واحد.
        decision["basis"] = decision_basis(
            ed_top, (((result.get("deep_research") or {}).get("verdict")
                      or {}).get("confidence")), lang,
            oldest_fact_year=_oldest_fact_year(result))
    cp = _competitive_position(top)
    view_markets = []
    for row in markets:
        comps = row.get("components") or {}
        present = sum(1 for c in comps.values() if _dp(c).get("value") is not None)
        view_markets.append({
            "country": row.get("country"), "iso3": row.get("iso3"),
            "score": row.get("total_score"), "confidence": row.get("confidence"),
            # الموجة Z · البند Z-10: المقامُ كان `len(comps) or 4` — فصفٌّ
            # بلا مكوّنات يُعرَض «0/4» و«٤» رقمٌ **مُثبَّتٌ لا مقيس** (والمسارُ
            # العميق يحمل ثمانيةً فأكثر). بسطٌ صادقٌ ومقامٌ مختلَق أسوأُ من
            # غيابٍ معلَن: القارئُ يحسبه قياساً. الغيابُ يُعلَن الآن.
            "components_present": (f"{present}/{len(comps)}" if comps
                                   else "غير متاح" if lang != "en"
                                   else "Not available"),
            # §10.3: سطر مصدر تحت كل رقم — مبني في القالب نفسه فيستحيل
            # بنيوياً ظهور رقم بلا نسب في أي مشتق (docx/نص/لوحة).
            "components_detail": [
                {"name": name, "display_name": internal_ar(name) if lang == "ar" else name.replace("_", " "),
                 "value": d.get("value"),
                 "source": d.get("source"),
                 "confidence": d.get("confidence"),
                 "retrieved_at": d.get("retrieved_at", ""),
                 # سدّ تسريب: ملاحظة DataPoint خام (نجاح إنجليزي مثل "HS…
                 # total World… USD" أو فشل يضمّ استثناء) لم تكن تمرّ عبر
                 # أي مُطهِّر رغم وصولها مباشرة لهذا الحقل في نموذج العرض
                 # القانوني — أي مستهلك مستقبلي (JSON خام، ودجت جديد) يرث
                 # النص المُعرَّب الآن، لا الخام.
                 "note": _strip_internal_plumbing(d.get("note", "")),
                 "status": d.get("status", ""),
                 # عقد المصدر (الموجة ١): الوحدة/الرابط/سنة البيانات/الفترة —
                 # الرابط يُملأ من السجلّ العمومي عند غيابه (لا اختلاق رابط)،
                 # وتحذير القِدم بطبقتيه ضمن نفس البند (§2.4) — من البند كاملاً
                 # (fact_year بكل مسانده البنيوية) لا من data_year وحده.
                 "unit": d.get("unit", ""),
                 "url": d.get("url", "") or _public_url(d.get("source", "")),
                 "data_year": d.get("data_year"),
                 "reference_period": d.get("reference_period", ""),
                 "vintage": _vintage_caveat_safe(d)}
                for name, c in comps.items() for d in [_dp(c)]],
            "recommendation": row.get("recommendation"),
            "quality_flags": row.get("quality_flags") or [],
            "has_competitive_position": "competitive_position" in row,
            # §سنوات الدراسة: خط الاتجاه متعدد السنوات إن فُعِّل (with_trend)،
            # وإلا None — الواجهة تعرضه أو تعلن «يتطلب تفعيل مدى السنوات».
            "trend": row.get("trend"),
            # طبقات الإثراء المرصودة (أسعار/منافسون/موردون) — يعرضها التقرير
            # والواجهة؛ الفارغ يُعلن «غير متاح» لا يُخترع (D4).
            "prices": _prices(row),
            "named_competitors": _named_competitors(row),
            "supplier_countries": row.get("competitors") or [],
            "suppliers": _suppliers(row),
            # Stage 2A: مخاطر (WGI/LPI/FX) + درجة تغطية المصادر لكل قسم
            "risk": [_dp(f) for f in (row.get("risk") or [])],
            "section_coverage": _section_coverage(row),
            "section_status": _section_status(row),   # بوابة 2B
            # Stage 5: حزمة §4b كما تحقق منها المنسّق + قرار §8 + مشتقاتها
            # القاعدية (SWOT/شرائح/دليل مورّدين) — اشتقاق عرض صرف.
            "research": row.get("research"),
            "entry_decision": row.get("decision"),
            "swot": _swot(row.get("research")),
            "segments": _segments(row.get("research")),
            "supplier_directory": _supplier_directory(row.get("research")),
        })
    # إفصاحُ مصدر الرمز يظهر على مسار /analyze أيضاً لا على /research وحده
    # (لا إصلاحَ على مسارٍ واحد — الدرسان ٣٥/٣٧). عند وجود بحثٍ عميق يكون
    # السطرُ محقوناً سلفاً في حدوده، فيُمنَع التكرار أدناه.
    # الدرس ٢٦٢ — سجلّ الحقائق الواحد: يُبنى مرّةً **قبل** الحدود والفجوات
    # فيقرأ منه كلُّ سطح (الأقسام الحتمية، الخلاصة، جدول النواقص، ونثرُ
    # الكاتب بعد ملء رموزه). أيُّ عطلٍ يترك العرضَ كما كان — إضافةٌ لا شرط.
    _ledger = _ledger_safe(result, lang)
    hs_prov = _hs_provenance(result)
    limits = [f"{m['country']}: {_humanize_gap_note(f)}" for m in markets[:5]
              for f in (m.get("quality_flags") or [])]
    # الموجة د-٤: حدٌّ **كاذبٌ** كان يظهر في ١٦/١٦ تقرير — «تعذّر التصنيف»
    # بينما التقريرُ نفسُه يعرض الرمزَ ووصفَه المؤكَّد: `classified` رايةُ
    # مسارِ `/analyze` وحدَه، وتقاريرُ `/research` تصل برمزٍ مُمرَّرٍ أو
    # مؤكَّد فلا تحملها. هو عينُ عائلة البلاغ الأصلي (قسمٌ يقول ناقص وقسمٌ
    # يعرض القيمة)، فصار الحدُّ يُعلَن **فقط** حين لا رمزَ معروفاً أصلاً.
    _hs_known = bool(str(result.get("hs_code") or "").strip()) or bool(
        (result.get("hs_confirmation") or {}).get("confirmed"))
    if not result.get("classified") and not _hs_known:
        limits.insert(0, _humanize_gap_note(result.get("hs_note"))
                     if result.get("hs_note")
                     else silk_i18n.t("limit_unclassified", lang))
    elif not result.get("classified") and result.get("hs_note"):
        # رمزٌ معروفٌ بملاحظةِ حلٍّ حقيقية (تطابقٌ ضعيف، بديلٌ مقترَح) تبقى
        # معلنةً — المحذوفُ هو الادّعاءُ الفارغ وحدَه لا الملاحظةُ المرصودة.
        limits.insert(0, _humanize_gap_note(result.get("hs_note")))
    # قسم البحث العميق (الموجة ٤، V5) — إضافي بحت؛ None لتحليل /analyze عادي.
    dr_view = _deep_research_view(result, lang, _ledger)
    if dr_view:
        # HF3: حارسُ المعقولية عبر المصادر — يقارن المقاديرَ المكشوطة (حجم سوقٍ)
        # بمرتكزات التشغيلة المُتحقَّقة (واردات/سكان) قبل التصيير، فيُسجّل العلاماتِ
        # في المانيفست ويُضيف تحفّظَ نطاقٍ للعميل بدل تسريب رقمٍ متعارضٍ صامتاً.
        # فشلٌ آمنٌ مفتوح: حارسٌ تشخيصيّ لا شرطُ تنفيذ.
        try:
            import silk_plausibility
            _pflags = silk_plausibility.annotate(result)
            if _pflags:
                dr_view["plausibility_flags"] = _pflags
                dr_view["limits"] = (silk_plausibility.caveat_lines(_pflags)
                                     + list(dr_view.get("limits") or []))
            # G4.1: إعفاءُ الإنتاج المحليّ — مرئيٌّ للمراجع في العرض (لا تحفّظَ
            # عميل، لا يدخل limits). فيرى المراجعُ أنّ الحارسَ وقف جانباً ولماذا.
            _pexempt = (result.get("deep_research") or {}).get(
                "plausibility_exemptions")
            if _pexempt:
                dr_view["plausibility_exemptions"] = _pexempt
        except Exception:  # noqa: BLE001
            pass
        limits = dr_view["limits"] + limits
    elif hs_prov:
        limits.insert(0, hs_prov["note_ar"])
    # LESSONS 88 — سجلّ فجوات واحد لكل سطوح الحكم: سطر الكفاية يُعاد بناؤه
    # الآن بعد اكتمال الحدود، فلا يقول «لا شيء» بينما التقرير يسرد بنوداً.
    if isinstance(decision, dict) and decision.get("sufficiency"):
        _jury = (top or {}).get("jury") or {}
        decision["sufficiency"] = (
            f"بوابة كفاية البيانات: {_jury.get('agents_with_data', 0)}/"
            f"{_jury.get('agents_total', 0)} وكلاء أساسيون لديهم بيانات؛ "
            f"فجوات: {verification_gap_line(_jury, limits)}")
    # ترويسة 2B: التغطية الإجمالية % = مُسهم/مُحاوَل عبر أقسام السوق الأعلى.
    top_cov = _section_coverage(markets[0]) if markets else {}
    att = sum(c["attempted"] for c in top_cov.values())
    con = sum(c["contributed"] for c in top_cov.values())
    dr_market = (dr_view or {}).get("market") or {}
    header = {
        "product": result.get("product"), "hs_code": result.get("hs_code"),
        "origin": "SAU",
        # صيد الفجوات ٣: كان name_ar يفوز دائماً فتحمل ترويسةُ docx الإنجليزي
        # «هولندا» — الاسم بلغة التقرير أولاً (معامل عرض بحت، لا مساس بالحكم).
        "target_market": ((markets[0].get("country") or markets[0].get("iso3"))
                          if markets else
                          ((dr_market.get("name_en") if lang == "en"
                            else dr_market.get("name_ar"))
                           or dr_market.get("name_ar")
                           or dr_market.get("name_en"))),
        "date": _t_today(),
        "coverage_pct": round(100 * con / att, 1) if att else 0.0,
    }
    view = {
        # راية التشغيل البرهاني: العواذف تضبط SILK_HERMETIC — كل المشتقات تطبع
        # لافتة TEST RUN؛ وفي الإنتاج يرفض المولّد أي أثر برهاني (silk_reports).
        "test_run": bool(os.environ.get("SILK_HERMETIC")),
        # لافتة التدهور (بلاغ حي) — top-level لتظهر في كل مشتق يقرأ
        # view["degraded"] مباشرة، بلا حاجة لفتح deep_research أولاً.
        "degraded": bool((dr_view or {}).get("degraded")),
        # الموجة C: حالةُ الحواجز التنظيمية بنيوياً — تقرؤها البوّابةُ الحاجزة
        # (`_check_regulatory_blocker`) والمُصدِّرات من **هنا** لا من النثر.
        "regulatory": _regulatory_state(result),
        "degraded_reason": (dr_view or {}).get("degraded_reason") or "",
        "header": header,
        "product": result.get("product"), "hs_code": result.get("hs_code"),
        "hs_confidence": result.get("hs_confidence"),
        # مصدرُ الرمز حين حُسِم آلياً (صورةُ عبوة/رابطُ ويب) — `None` حين
        # حُسِم بالمسار العادي؛ لا حقلَ صامتاً يُفسَّر خطأً.
        "hs_provenance": hs_prov,
        "year": result.get("year"), "preliminary": True,
        "data_year": result.get("data_year", result.get("year")),
        "year_fell_back": bool(result.get("year_fell_back")),
        "classified": result.get("classified", False),
        "decision": decision,
        # الموجة الرابعة: القائمةُ على العرض الأعلى أيضاً — الواجهةُ تُسقِط
        # عمودَ ثقةِ المكوّنات حتى حين لا كتلةَ أساس (لا قرارَ محرّك).
        **({"client_hidden_metrics": list(CLIENT_HIDDEN_METRICS)}
           if client_metric_privacy() else {}),
        "dynamics": _sanitized_dynamics(result.get("dynamics")),
        "competitive_position": cp,
        "completeness": _completeness(markets),
        "markets": view_markets,
        "culture": _culture(result),          # روابط خام (تراجُع/استشهاد)
        "consumer_culture": _consumer_culture(result),  # ثقافة المستهلك المستخلَصة (كلود)
        "brief": (_deep_research_brief(dr_view, lang) if dr_view
                 else _brief(decision, cp, lang)),
        "limits": limits,
        # الدرس ٢٦٢: السجلّ الواحد — إضافيٌّ بحت، ومستهلكوه يقرأون منه.
        "ledger": _ledger,
        "provenance": _provenance(result),   # Stage 2A: لا فشل صامتاً
        # اقتصاد البيانات (persist-5): عدّاد مرصود — مخزن/ذاكرة مقابل جلب حي.
        "data_economics": result.get("data_economics"),
        # HF4.1: ملاحظةُ التشغيلة تمرّ عبر مُطهِّر المتن (كملخّصات البعثات/المحلل
        # أصلاً) — فلا يتسرّب نصفُها الإنجليزيُّ الداخليّ لأيّ سطحِ عميل (§5).
        "note": (_strip_internal_plumbing(result.get("note"))
                 if isinstance(result.get("note"), str) else result.get("note")),
        # التحليل الاحترافي (silk_ai_judge.ai_report) — يحلّ محل الخلاصة
        # الحتمية (exec_summary) في التقرير المصدَّر حين يتوفر؛ None = غياب
        # مفتاح/فشل النداء (ظاهر لا محذوف)، والقالب يرجع حينها لـ exec_summary.
        "ai_report": result.get("report"),
        "ai_report_note": result.get("report_note"),
        # الموجة ٤ (V5): مختلف عن row["research"] القائم — راجع تنبيه التسمية
        # أعلى _deep_research_view. None لتحليل /analyze العادي (لا أثر).
        "deep_research": dr_view,
        # الموجة ٠: لغة هذا التقرير — تُرفَع top-level فيقرؤها كل مُصدِّر بدل
        # تمريرها في كل توقيع (نفس نمط رفع `degraded`). قيمةٌ عرضٍ لا تحليل.
        "report_language": lang,
    }
    # صفوفُ جدول النواقص تُحسَب **بعد اكتمال العرض** (تقرأ الحدودَ وفجواتِ
    # الاقتصاد) وتُرفَع في السجلّ: الواجهةُ والماركداون وWord يقرؤون الصفوفَ
    # نفسَها — لا مسارَ عرضٍ موازياً يتباعد (الدرس ٢، وقانونُ العرض الواحد).
    if isinstance(_ledger, dict):
        try:
            import silk_fact_ledger as _FL
            # الموجة د-٤: التقديراتُ (البند ١١) تُحسَب هنا لأنّ مدخلاتِها في
            # قسم الاقتصاد الذي يُبنى بعد السجلّ — ثمّ أسئلةُ المصدّر (البند
            # ١٠) تقرؤها، ثمّ جدولُ النواقص كما كان. ترتيبٌ واحدٌ لا سطحَ
            # عرضٍ موازٍ: الثلاثةُ صفوفٌ في السجلّ يقرؤها كلُّ مُصدِّر.
            # ثلاثُ خطواتٍ مستقلّة بثلاثة حُرّاس: عطلُ التقديرات كان يقفز
            # فوق الجدولين فيمسح `gaps_table` إلى `[]` — **فجواتٌ حقيقيةٌ
            # تختفي** بسبب عطلٍ في إضافةٍ اختيارية، وفوقها يُطبَع «لا فجوات
            # مرصودة» (§58). لا يُسقِط فشلُ واحدةٍ الأُخريَين.
            try:
                _FL.fill_estimates(view, lang)
            except Exception as _exc:       # noqa: BLE001 — إضافةٌ لا شرطُ عرض
                log.warning("fill_estimates skipped: %s", _exc)
            try:
                _ledger["critical_questions"] = _FL.critical_questions(
                    view, lang)
            except Exception as _exc:       # noqa: BLE001
                log.warning("critical_questions skipped: %s", _exc)
                _ledger.setdefault("critical_questions", [])
            _ledger["gaps_table"] = _FL.gaps_table(view, lang)
        except Exception:                   # noqa: BLE001 — عرضٌ لا يُسقِط تقريراً
            _ledger.setdefault("critical_questions", [])
            _ledger.setdefault("gaps_table", [])
    return view


def render_text(view: dict) -> str:
    """نص الطرفية من القالب — terminal rendering derived from the view only."""
    L = ["═" * 60]
    if view.get("test_run"):
        L.append("⚠ TEST RUN — تشغيل برهاني ببدائل موسومة، ليس تقريراً إنتاجياً")
    L.append(f"المنتج / Product : {view.get('product')}")
    if not view.get("classified"):
        L += ["الحالة: تعذّر التصنيف — could not classify",
              *(f"  حد: {x}" for x in view.get("limits", [])[:3]), "═" * 60]
        return "\n".join(L)
    d = view["decision"]
    h = view.get("header") or {}
    L.append(f"المنتج: {h.get('product')} | HS: {h.get('hs_code')} | "
             f"السوق: {h.get('target_market')} | {h.get('date')} | "
             f"تغطية: {h.get('coverage_pct')}%")
    st0 = (view.get("markets") or [{}])[0].get("section_status") or {}
    for sec, st in st0.items():
        if st.get("status") == "insufficient":
            # مفتاحُ القسم الخام («market_size») كان يُطبَع بين قوسين
            # اسماً للقسم — مفرداتُ كودٍ في نصّ منتَج (مراجعةٌ ذاتية §58).
            # استيرادٌ كسول: `silk_reports` يستورد هذا الملف، فالاستيرادُ
            # العلويّ يصنع دورة. (نمطُ الريبو القائم للاتجاه المعاكس.)
            from silk_reports import _SEC_AR
            L.append("  " + insufficient_line(_SEC_AR.get(sec, sec), st))
    cov0 = (view.get("markets") or [{}])[0].get("section_coverage") or {}
    if cov0:
        L.append("تغطية الأقسام: " + " | ".join(
            f"{k}:{c['contributed']}/{c['attempted']}" for k, c in cov0.items()))
    prov = view.get("provenance") or []
    if prov:
        L.append("أثر المصادر: " + " ، ".join(
            f"{b['source']}={b['contributed']}/{b['attempted']}"
            for b in prov[:6]))
    from silk_narrative import confidence_phrase, verdict_ar
    L += [f"رمز HS: {view['hs_code']} (ثقة {view['hs_confidence']}) | "
          f"سنة {view['year']} | مبدئي",
          f"القرار: {verdict_ar(d.get('verdict'))} "
          f"(ثقة {confidence_phrase(d.get('confidence'))}) — {d.get('market')}",
          f"لماذا: {d.get('why')}", "─" * 60]
    ed = (view.get("markets") or [{}])[0].get("entry_decision") or {}
    if ed.get("schema"):
        # (البند 2): قرارٌ ممتنع score=None — «None» الخام لا يصل سطحاً.
        _sc = ed.get("score")
        _sc_txt = _sc if isinstance(_sc, (int, float)) else "غير محسوبة"
        L.append(f"قرار الدخول (المحرك الموزون): {verdict_ar(ed.get('verdict'))} "
                 f"— النقاط {_sc_txt} — الثقة "
                 f"{confidence_phrase(ed.get('confidence'))} — {ed.get('why')}")
        # الصنف ٧: المصدرُ الواحد — السقفُ القائم (٣) يبقى مطفأةً.
        _oc = open_conditions(ed)
        for c in _oc["shown"]:
            L.append(f"  شرط: {c}")
        if _oc["more_note"]:
            L.append(f"  شرط: {_oc['more_note']} "
                     f"(الإجمالي {_oc['count']})")
    cp = view["competitive_position"]
    L.append("موقعك التنافسي:")
    if cp.get("available"):
        L.append(f"  التغطية: {cp.get('coverage')}")
        for f in cp.get("feasibility_threads") or []:
            L.append(f"  ضد {f['competitor'][:40]}: سعر مرصود "
                     f"{f['observed_price']} — هامشك إن سعّرت مثله "
                     f"{f['margin_at_match_pct']}% وعند البيع أقل 10% "
                     f"{f['margin_at_10pct_below']}%")
        for t in cp.get("competitor_threads") or []:
            if not t.get("observed_price"):
                # خيوط بحث الويب مراجع لا كيانات (إصلاح مراجعة Stage 5، ثغرة ٢).
                L.append(f"  مرجع ويب للمراجعة: {t['name'][:40]} — "
                         f"{t['price_flag']} "
                         f"(اكتمال الخيط {t['thread_completeness']})")
    else:
        L.append(f"  {cp.get('note')}")
    L.append("─" * 60)
    L.append("الأسواق (الأفضل أولاً):")
    for i, m in enumerate(view["markets"], 1):
        # الاسمُ والدرجةُ قد يغيبان (عطبُ محرّكِ القرار على المسار العميق يترك
        # `score=None`) — يُطبَع «—» بدل كسرِ التنسيق بـTypeError على None.
        _country = m.get("country") or (m.get("iso3") or "—")
        _score = m.get("score")
        _score_s = f"{_score:.3f}" if isinstance(_score, (int, float)) else "—"
        L.append(f"  {i:>2}. {_country:<22} score={_score_s} "
                 f"conf={m.get('confidence')} ({m.get('components_present')})")
    if view.get("limits"):
        L.append("حدود هذا التقرير:")
        L += [f"  - {x}" for x in view["limits"][:6]]
    if (view.get("data_economics") or {}).get("note"):
        L.append(f"اقتصاد البيانات: {view['data_economics']['note']}")
    L += ["المختصر:", *(f"  {x}" for x in view["brief"]), "═" * 60]
    return "\n".join(L)


def analysis_context(result: dict, max_chars: int = 6000) -> str:
    """سياق نصي مضغوط لتحليل قائم (10b) — للدردشة السياقية فوق النتيجة.

    يقرأ نتيجة المحرّك المخزّنة حصراً — صفر شبكة، صفر إعادة تشغيل وكلاء.
    كل رقم يُذكر بمصدره؛ الفجوات تُذكر كما هي كي يجيب كلود «غير متوفر في
    هذا التحليل» بدل الاختلاق.
    """
    # سدّ تسريب: هذا السياق يُغذّى مباشرة لبرومبت الدردشة السياقية
    # (silk_ai_judge.answer_about_analysis) — كلود مُطالَب بالاستشهاد حرفياً
    # من هذا النص، فأي مفتاح داخلي خام هنا (اسم مكوّن snake_case، مفتاح وكيل)
    # قابل للظهور حرفياً في جواب يصل العميل مباشرة.
    from silk_narrative import internal_ar
    view = result.get("view") if isinstance(result.get("view"), dict) else None
    view = view or build_view(result)
    L: list[str] = []
    h = view.get("header") or {}
    L.append(f"المنتج: {h.get('product')} (HS {h.get('hs_code')}) — "
             f"السوق الأول: {h.get('target_market')} — سنة البيانات: "
             f"{view.get('data_year', view.get('year'))}")
    for b in view.get("brief") or []:
        L.append(f"الخلاصة: {b}")
    # R2 (تفعيل الدردشة فوق الدراسة العميقة): analysis_context كان يقرأ شكل
    # /analyze حصراً (top فارغ للدراسة العميقة إذ markets=[])، فتُجيب دردشة
    # «اسأل عن الدراسة» من سياق شبه فارغ للدراسات الرئيسية. هنا نضيف تأريض
    # البحث العميق — حقائق البعثات بمصادرها، تقاطعات المحلل، الحكم، والتقرير
    # المكتوب — كي تُؤسَّس الإجابة على كامل الدراسة لا العنوان وحده. لا اختلاق:
    # كل رقم بمصدره، وما ليس هنا يقال «غير متوفر» في برومبت الإجابة نفسه.
    dr = view.get("deep_research")
    if isinstance(dr, dict):
        if dr.get("verdict_label"):
            L.append(f"حكم الدراسة: {dr['verdict_label']}")
        for key, m in (dr.get("missions") or {}).items():
            if not isinstance(m, dict) or m.get("failed"):
                continue
            label = m.get("label") or key
            for f in (m.get("findings") or [])[:3]:
                val = f.get("value")
                if val is None or isinstance(val, (list, dict)):
                    continue
                src = f.get("source") or ""
                L.append(f"{label}: {val}"
                         + (f" [المصدر: {src}]" if src else ""))
        an = dr.get("analyst") or {}
        for cat, dps in (an.get("by_category") or {}).items():
            for d in (dps or [])[:2]:
                val = d.get("value")
                if val is None or isinstance(val, (list, dict)):
                    continue
                L.append(f"تقاطع {_category_label(cat)}: {val}")
        report_text = (dr.get("report") or {}).get("text")
        if report_text:
            L.append("التقرير المكتوب للدراسة:\n" + report_text)
    top = (view.get("markets") or [{}])[0]
    for c in top.get("components_detail") or []:
        name_ar = internal_ar(c.get("name"))
        if c.get("value") is not None:
            # **الموجة C (البند S-02).** تحذيرُ القِدَم كان يُحسَب لكلّ مكوّن
            # (`components_detail[*]["vintage"]`) ثمّ **لا يقرؤه أحد**: مئاتُ
            # الحسابات تُرمى، فيبني الكاتبُ سرداً واثقاً على رقمٍ عمرُه سنوات
            # وهو لا يعلم أنه قديم. الآن يصل كتلةَ الحقائق ملتصقاً برقمه —
            # فمصدرُ الرقم وعمرُه يُقرآن معاً أو لا يُقرآن.
            _vint = str(c.get("vintage") or "").strip()
            _age = f" — {_vint}" if _vint else ""
            L.append(f"{name_ar} = {c['value']} "
                     f"[المصدر: {c.get('source')}{_age}]")
        else:
            why = ("تعذّر الجلب — أعد المحاولة"
                   if c.get("status") == "fetch_failed" else "غير متاح")
            L.append(f"{name_ar}: {why}")
    # المقام مُعلَن دائماً (LESSONS 88 التوأم): «حصة S% (قيمة V$)» متجاورين
    # بلا مقام جعل الكاتب يسمّي **قيمة المورّد** إجماليَّ واردات السوق —
    # رقمان مختلفان لنفس البند في وثيقة واحدة. القاعدة: كل نسبة تُصيَّر
    # ومعها ما هي نسبةٌ منه، وكل قيمة تُسمّى ملكيتها صراحة.
    _tam = None
    for _c in top.get("components_detail") or []:
        if isinstance(_c, dict) and _c.get("name") == "market_size":
            _tam = _c.get("value")
            break
    _den = (f"من إجمالي واردات السوق {_tam}$" if _tam is not None
            else "من إجمالي واردات السوق")
    for sc in (top.get("supplier_countries") or [])[:6]:
        L.append(f"مورّد: {sc.get('partner')} — حصة {sc.get('share')}% {_den}؛ "
                 f"قيمة صادرات هذا المورّد وحده {sc.get('value_usd')}$ "
                 f"(ليست إجمالي واردات السوق) [UN Comtrade]")
    ag = ((top.get("research") or {}).get("agents")) or {}
    for k, a in ag.items():
        k_ar = internal_ar(k)
        for f in (a.get("findings") or [])[:4]:
            if f.get("value") is None or isinstance(f.get("value"),
                                                    (list, dict)):
                continue
            srcs = "، ".join(str(x.get("source")) for x in
                             (f.get("sources") or []) if isinstance(x, dict))
            L.append(f"{k_ar} — {internal_ar(f.get('metric'))} = {f['value']}"
                     f"{(' ' + f['unit']) if f.get('unit') else ''}"
                     f" [المصدر: {srcs or '؟'}]")
        for g in (a.get("gaps") or [])[:2]:
            L.append(f"فجوة {k_ar}: {_humanize_gap_note(g)}")
    ed = top.get("entry_decision") or {}
    # الصنف ٧: المصدرُ الواحد — السقفُ القائم (٤) يبقى مطفأةً.
    _oc = open_conditions(ed)
    for cnd in _oc["shown"]:
        L.append(f"شرط مفتوح: {cnd}")
    if _oc["more_note"]:
        L.append(f"شرط مفتوح: {_oc['more_note']} "
                 f"(الإجمالي {_oc['count']})")
    for x in (view.get("limits") or [])[:6]:
        L.append(f"حدّ معلن: {x}")
    out = "\n".join(L)
    if len(out) <= max_chars:
        return out
    # صيد الفجوات ٣: نص تأريض المحادثة يؤمر الاقتباس الحرفي منه — الشريحة
    # الخام كانت تقطع وسط رقم/كلمة؛ القطع عند آخر سطر كامل قبل السقف.
    cut = out[:max_chars]
    return cut[:cut.rfind("\n")] if "\n" in cut else cut
