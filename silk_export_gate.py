"""بوّابةُ تسليمٍ **واحدة** لسطحَي التصدير · one delivery gate, both surfaces.

> **لماذا وُجدت هذه الوحدة** (الموجة B، البند G-01 في `docs/ENGINE_AUDIT.md`).
> كانت البوّابةُ الحاجزة تعيش مغلقةً داخل `api.create_app`، فتحرس نقطتَي
> **المشغّل** (`/analyses/{id}/report.docx|pdf`) وحدَهما؛ ونقاطُ تصدير
> **المصنع** (`silk_platform/api.py`) تبني وتُرسل مباشرةً من `build_view`
> بصفر نداءات بوابة. أي أنّ العميل الدافع كان يتسلّم مصنوعاً لم يمرّ بشرط
> التسليم الذي يفرضه المشغّل على نسخته هو. مُثبَتٌ بإعادة إنتاج: تشغيلةُ
> `/research` أعادت `quality_gate.verdict = "FAIL"` مع **HTTP 200** وعرضٍ كامل.
>
> العلاجُ عند المنشأ لا في العارض: **قرارُ التسليم يُتَّخذ هنا وحدَه**، وكلُّ
> سطحٍ يترجم القرارَ إلى خطأ HTTP بلغته وجمهوره. لا منطقَ بوابةٍ ثانٍ، ولا
> نسخةَ سياسةٍ في `silk_platform/`.
>
> **One gate, one decision.** Each surface only renders the decision; the
> policy lives here and nowhere else.

stdlib فقط؛ الاستيرادات الثقيلة كسولةٌ داخل الدوالّ (كبقية الريبو) فتبقى
الوحدةُ قابلةً للاستيراد بلا شبكةٍ ولا مفاتيح.
"""
from __future__ import annotations

import hmac
import logging
import os

log = logging.getLogger("silk.export_gate")

# صيغُ التصدير التي تمرّ بالبوّابة — الوسمُ يُسجَّل في الحارس وسجلّ العمليات.
FORMATS = ("docx", "pdf", "json")


# ── (١) تحضيرُ نثر الاحتياط قبل الحكم ────────────────────────────────────

def client_prose_needed(dr: dict) -> bool:
    """هل يستدعي قالبُ العميل نداءَ صياغةٍ فعلاً؟ — فحصٌ حتميٌّ رخيصٌ بلا كلود.

    يُقرأ **قبل** حجزِ نصيبٍ من سقفِ إضافات كلود (`free_ai_extras_allowed`
    يحجز ذرّياً ولا يُرَدّ الحجز — البند A7). كان كلُّ تصديرِ تقريرٍ يحجز
    وحدةً حتى حين لا قسمَ بلا سردِ كاتب (فلا نداءَ صياغةٍ يقع)، فتُستنزَف
    السقفُ اليوميّ بمجرّد فتحِ صفحةِ التقرير مراراً ويُرَدّ مسارُ `/deepen`
    الحقيقيّ بـ429 بلا أيّ نداءِ مزوّدٍ مدفوع (بلاغ مراجعة §58).

    يعيد `True` فقط حين يوجد قسمُ عميلٍ بلا سردِ كاتبٍ ومعه بنودٌ خام
    مرشّحةٌ لإعادة الصياغة — وهي عينُ الحالةِ التي يُطلَق فيها كلود.
    """
    dr = dr or {}
    if not dr or dr.get("client_fallback_prose"):
        return False
    try:
        from silk_reports import _client_missing_narrative_heads
        heads = _client_missing_narrative_heads(dr)
    except Exception:  # noqa: BLE001 — تعذّر الفحص = لا حجز (فشل-آمن)
        return False
    return any(items for items in (heads or {}).values())


def prepare_fallback_prose(view: dict, *, ai_allowed: bool,
                           found: dict | None = None,
                           analysis_id: int | None = None) -> bool:
    """حضِّر النثرَ التجاريَّ للأقسام بلا سردِ كاتب — قبل البوّابة لا بعدها.

    كان هذا التحضيرُ يعيش على مسار المشغّل وحدَه (`api.py`)، فيتسلّم المصنعُ
    «السرد غير متاح» حيث يتسلّم المشغّلُ نثراً مُعادَ صياغته ومخزَّناً
    (البند G-05). الآن يُنادى من السطحين.

    `ai_allowed` يقرّره المُنادي عبر بوّابة إضافات كلود القائمة — لا نداءَ
    غيرَ محكوم من هنا. يعيد `True` إن أُضيف نثرٌ جديد فعلاً.
    """
    dr = view.get("deep_research") or {}
    if not dr or dr.get("client_fallback_prose"):
        return False
    try:
        from silk_reports import _client_missing_narrative_heads
        needs = {h: items for h, items in
                 _client_missing_narrative_heads(dr).items() if items}
    except Exception:  # noqa: BLE001 — تعذّر الفحص = لا نداء
        needs = {}
    if not needs or not ai_allowed:
        return False
    try:
        from silk_ai_judge import rephrase_client_sections
        prose = rephrase_client_sections(dr)
    except Exception as e:  # noqa: BLE001 — فشل التحضير تحكمه البوابة
        log.warning("client fallback rephrase failed: %s", e)
        return False
    if not prose:
        return False
    dr["client_fallback_prose"] = prose
    # النثرُ الناجح يُخزَّن على السجل فلا يُعاد دفعُ النداءات مع كل تصدير.
    try:
        stored_dr = (found or {}).get("deep_research")
        if isinstance(stored_dr, dict) and analysis_id:
            stored_dr["client_fallback_prose"] = prose
            import silk_storage
            silk_storage.save_analysis(found, analysis_id=analysis_id)
    except Exception as e:  # noqa: BLE001 — تخزين اختياري
        log.warning("prose cache persist failed: %s", e)
    return True


# ── (٢) الحكم ─────────────────────────────────────────────────────────────

def _ledger_repair_before_gate(view: dict) -> None:
    """أصلح نصَّ التقرير من السجلّ قبل حكم البوّابة — **تحت الإنفاذ فقط**.

    يكتب الإصلاحاتِ في `view["ledger"]["repairs"]` (يقرؤها المدقّق) ولا يمسّ
    أيّ رقمٍ مخزَّن: الجملةُ وحدها تُعاد صياغتُها من السجلّ نفسِه.
    """
    try:
        import silk_fact_ledger as _FL
        if not _FL.enforce() or not isinstance(view, dict):
            return
        ledger = view.get("ledger") or {}
        dr = view.get("deep_research") or {}
        rep = dr.get("report") if isinstance(dr.get("report"), dict) else None
        if not ledger or not rep or not rep.get("text"):
            return
        fixed, repairs = _FL.repair(rep["text"], ledger,
                                    view.get("report_language") or "ar")
        if repairs:
            rep["text"] = fixed
            ledger["repairs"] = list(ledger.get("repairs") or []) + repairs
    except Exception as exc:  # noqa: BLE001 — الإصلاحُ تحسينٌ لا شرطُ حكم
        log.warning("ledger repair skipped: %s", exc)


def evaluate(view: dict) -> dict:
    """شغّل بوابة الجودة الحتمية على قالب العميل وأعد قرار التسليم.

    عطلٌ داخليٌّ في البوّابة نفسها يُعامَل **FAIL** لا تخطّياً صامتاً: تقريرٌ
    لم يُفحَص فعلياً لا يُسلَّم لعميل.

    يعيد `{"verdict", "findings", "digest", "blocking"}` حيث `digest` قائمةٌ
    مقتضبة صالحةٌ للعرض، و`blocking` هي الملاحظات غير القابلة للإصلاح.
    """
    try:
        import silk_quality_gate
        # الدرس ٢٦٢ (وضع الإنفاذ): **إصلاحٌ من السجلّ أوّلاً ثم الحجب** —
        # جملةٌ تخالف السجلّ تُعاد صياغتُها كاملةً من السجلّ قبل أن تُحجَب،
        # فلا تُهدَر تشغيلةٌ على ما يمكن تصحيحُه حتمياً. في وضع القياس
        # (الافتراضي) لا إصلاحَ ولا حجب — تسجيلٌ فقط.
        _ledger_repair_before_gate(view)
        gate_out = silk_quality_gate.run_quality_gate(view)
        verdict = gate_out.get("verdict", silk_quality_gate.FAIL)
    except Exception as e:  # noqa: BLE001 — عطل البوابة = FAIL، لا تخطٍّ
        log.warning("quality gate crashed during client export: %s", e)
        gate_out = {
            "verdict": "FAIL",
            "findings": [{
                "check": "gate_crash", "repairable": False,
                "note": (f"عطل داخلي في بوابة الجودة أثناء التصدير "
                         f"({type(e).__name__}) — عومل التقرير كأنه FAIL "
                         "لحماية العميل من محتوى لم يُفحَص فعلياً.")}]}
        verdict = "FAIL"
    findings = gate_out.get("findings") or []
    blocking = [f for f in findings if not f.get("repairable", True)]
    digest = [{"check": f.get("check"), "note": f.get("note")}
              for f in (blocking or findings)]
    # حادثة قراءة حجب #12: حمولة 409 حملت أربعة أسماء بينما المُفشِل واحد
    # (`style_connector_excess`) — بقيّتها ملاحظات حاجبة غير قائدة، فقُرئت
    # القائمة كلُّها أسباباً. يُميَّز القائد صراحةً (مفتاح إضافي فقط).
    drivers = _fail_drivers(findings)
    if str(verdict).upper() == "FAIL" and not drivers:
        # حكمٌ FAIL بلا قائدٍ محسوب (عطل بوابة/تعذّر استيراد المجموعات):
        # كلُّ الملاحظات الحاجبة تُعَدّ قائدة — لا حمولةَ FAIL بلا سبب معلن.
        drivers = []
        for f in blocking:
            chk = str(f.get("check") or "")
            if chk and chk not in drivers:
                drivers.append(chk)
    return {"verdict": verdict, "findings": findings,
            "digest": digest, "blocking": blocking, "gate": gate_out,
            "fail_drivers": drivers}


def _fail_drivers(findings: list) -> list:
    """أسماءُ الملاحظات التي **تقود** حكم FAIL فعلاً — بنفس منطق حكم
    `run_quality_gate` حرفياً: عضويّة `_REGRESSION_GUARD_FIRED`، أو ملاحظة
    غير قابلة للإصلاح ضمن `FAIL_TRIGGER_CHECKS`. الترتيب محفوظ بلا تكرار."""
    try:
        import silk_quality_gate as QG
        guard = QG._REGRESSION_GUARD_FIRED
        triggers = QG.FAIL_TRIGGER_CHECKS
    except Exception:  # noqa: BLE001 — تعذّر الاستيراد: يعالجه احتياط evaluate
        return []
    out: list[str] = []
    for f in findings:
        chk = str(f.get("check") or "")
        if not chk:
            continue
        drives = (chk in guard
                  or (not f.get("repairable", True) and chk in triggers))
        if drives and chk not in out:
            out.append(chk)
    return out


def is_blocked(decision: dict) -> bool:
    """هل يُمنَع التسليم؟ — قراءةٌ واحدة لا تُعاد كتابتها في كل سطح."""
    return str((decision or {}).get("verdict") or "").upper() == "FAIL"


# ── (٣) التجاوز — سلطةُ المالك وحدَها ─────────────────────────────────────

def override_authorized(supplied_key: str | None) -> bool:
    """تجاوزُ الحجب يتطلّب `SILK_OWNER_KEY` مطابقاً؛ مفتاح API العادي لا يكفي.

    غيابُ المفتاح على الخادم = **لا تجاوزَ ممكن** (لا فتحةَ افتراضية).
    """
    owner_key = os.environ.get("SILK_OWNER_KEY", "").strip()
    supplied = (supplied_key or "").strip()
    if not owner_key:
        return False
    # مقارنة ثابتة الزمن كنظيرتها على `X-API-Key` (`api.py:871`) ورموز المنصّة
    # (`silk_platform/tokens.py:49`): `==` يخرج عند أول محرف مختلف فيسرّب طول
    # البادئة الصحيحة زمنياً. هذا أعلى مفتاح سلطةً في النظام (يتجاوز حجب بوّابة
    # الجودة) فلا يجوز أن يكون الوحيد المقارَن بغير compare_digest.
    # Constant-time compare (audit 2026-08-27, finding 12).
    # **بالبايتات لا بالنصّ** (مراجعة §58): `compare_digest` على `str` يرفع
    # TypeError لأي محرف خارج ASCII، فمفتاحٌ يحوي عربية كان يقلب رفضاً مقصوداً
    # (403) إلى 500 عارية. الترميز يجعل الرفض رفضاً في كل الحالات.
    return hmac.compare_digest(supplied.encode("utf-8"),
                               owner_key.encode("utf-8"))


# ── (٤) التسجيل — الحارس وسجلّ العمليات ──────────────────────────────────

def record_override(analysis_id, product, market, findings, fmt) -> None:
    try:
        import silk_watchdog
        silk_watchdog.record_override(analysis_id, product, market,
                                      findings, fmt)
    except Exception as e:  # noqa: BLE001 — تسجيل التجاوز لا يُسقِطه
        log.warning("watchdog override record failed: %s", e)


def record_block(analysis_id, product, market, findings, digest,
                 fmt, surface: str = "operator",
                 fail_drivers: "list | None" = None) -> None:
    """سجّل الحجب في الحارس وسجلّ العمليات — `surface` يميّز مصنعاً من مشغّل.
    `fail_drivers` (شرط المُشرِف F): قائد الحكم يُخزَّن مع كل سجل حجب."""
    try:
        import silk_watchdog
        silk_watchdog.record_blocked_export(analysis_id, product, market,
                                            findings, fmt)
    except Exception as e:  # noqa: BLE001 — التسجيل لا يُسقِط الحجب
        log.warning("watchdog blocked-export record failed: %s", e)
    try:
        import silk_ops_log
        silk_ops_log.record_error(
            "quality_gate_blocked_export",
            f"تصدير العميل ({fmt}) مُنِع: بوابة الجودة أعادت FAIL",
            context={"analysis_id": analysis_id, "surface": surface,
                     "findings": digest,
                     "fail_drivers": [str(x) for x in (fail_drivers or [])]})
    except Exception as e:  # noqa: BLE001
        log.warning("ops-log blocked-export record failed: %s", e)


# ── (٥) ما يُقال لكلّ جمهور ───────────────────────────────────────────────

_OPERATOR_MESSAGE = (
    "تعذّر تسليم هذا التقرير للعميل: بوابة الجودة رصدت مشاكل حاجبة قبل "
    "التسليم. استخدم ?internal=1 للنسخة التشغيلية الكاملة للمدقّق، أو "
    "?override=1 لتخطّي الحجب — التجاوز يتطلّب سلطة المالك المنفصلة "
    "(ترويسة X-Owner-Key المطابقة لـ SILK_OWNER_KEY)؛ مفتاح API العادي "
    "وحده لا يكفي.")

# رسالةُ المصنع بلغةِ عميلٍ لا بلغةِ نظام (البند ٤ في LAW: لغة الزائر العادي).
# **ولا تُقال «عطلٌ تقني»** — كان رفضُ الجودة يُترجَم 501/503 «وحدات المحرّك
# غير متاحة» فيُقرأ عطلاً في البنية (البند G-04).
_FACTORY_MESSAGE_AR = (
    "تقريرُ هذه الدراسة لم يجتز فحصَ الجودة النهائيّ، فلم نُسلِّمه — نُفضّل "
    "ألّا نُعطيك تقريراً ناقصاً على أن نُعطيك تقريراً لا يصلح للقرار. "
    "أعِد توليدَ الدراسة، وإن تكرّر الأمر فتواصل معنا.")
_FACTORY_MESSAGE_EN = (
    "This study's report did not pass the final quality check, so we did not "
    "deliver it — we would rather give you no report than one you cannot "
    "safely decide on. Please regenerate the study; if this repeats, contact "
    "us.")


# ── جملةُ الزائر لكل فحصٍ حاجب (بلاغ المالك الثالث، 2026-08-29) ──────────
# الحادثة: سطحُ المصنع كان يطبع **معرّف الفحص الخام** («قائد الحجب:
# unit_conversion_refusal») بينما كلُّ فحصٍ يحمل شرحاً جاهزاً في ملاحظته —
# ثالثُ ظهورٍ لعادةٍ واحدة (الدرسان ٢٠٦/٢٠٧): طبقةٌ تحسب سبباً مقروءاً وسطحٌ
# يطبع رمزاً بدله. وقرارُ `factory_detail` القديم («أسماء الفحوص فقط بلا
# نصوصها الداخلية») كان يقصد ألّا تتسرّب لغةُ بوّابةٍ داخلية — فانتهى إلى
# الأسوأ: لا شرحَ **ولا** لغةَ إنسان، بل معرّف كود.
#
# القاعدة: **لكلّ فحصٍ حاجبٍ جملةٌ بلغة الزائر تقول ما وقع وما يُغلقه** —
# مكتوبةٌ أصالةً بالعربية والإنجليزية (LAW §٤: لا ترجمة آلية على نصّ عميل)،
# ولا يُذكَر فيها اسمُ الفحص ولا مصطلحُ كود. والقفلُ يفرض التغطية: فحصٌ
# حاجبٌ جديد بلا جملةٍ يُحمِّر السويت (`tests/test_gate_client_reasons.py`).
_CLIENT_REASONS: dict[str, dict[str, str]] = {
    "pillar_narrative_sync": {
        "ar": "توجد معلومات في نص التقرير لا تتطابق مع القياسات المعتمدة "
              "في ملخص القرار. يُغلقه: إعادة توليد التقرير؛ وإن تكرر، "
              "أرسل رقم الدراسة للدعم لمراجعة البيانات.",
        "en": "The report narrative does not match the measurements used "
              "in the decision summary. Fix: regenerate the report; if this "
              "recurs, send the study ID to support for a data review."},
    "agent_failed": {
        "ar": "أحدُ مصادر البحث تعذّر تشغيله في هذه التشغيلة، فبقيت جوانبُ "
              "من الدراسة بلا سند. يُغلقه: التحقق من توفر المصدر ثم إعادة "
              "تشغيل البحث؛ إعادة تنزيل الملف وحدها لا تكمل البيانات.",
        "en": "One of the research sources failed to run, leaving parts of "
              "the study unsupported. Fix: check source availability and "
              "rerun the research; downloading again cannot fill missing data."},
    "analyst_layer_failed": {
        "ar": "طبقةُ التحليل الشامل لم تكتمل، فالتقريرُ بلا الربط الذي يحوّل "
              "الأرقام إلى قرار. يُغلقه: إعادة التوليد.",
        "en": "The full-analysis layer did not complete, so the report lacks "
              "the synthesis that turns numbers into a decision. Fix: "
              "regenerate."},
    "cagr_sign_flips_under_base_year": {
        "ar": "اتجاهُ النموّ ينقلب من موجب إلى سالب بتغيير سنة الأساس — رقمٌ "
              "لا يصلح للاستناد إليه. يُغلقه: إعادة التوليد؛ وإن تكرّر فسلسلةُ "
              "السنوات لهذا المنتج/السوق قصيرةٌ جداً.",
        "en": "The growth trend flips sign when the base year changes — not "
              "a number to decide on. Fix: regenerate; if it repeats, the "
              "year series for this product/market is too short."},
    "client_scaffold_leak": {
        "ar": "تسرّبت إلى نصّ التقرير عباراتُ هيكلٍ داخليّة ليست جزءاً من "
              "الدراسة. يُغلقه: إعادة التوليد.",
        "en": "Internal scaffolding text leaked into the report body. Fix: "
              "regenerate."},
    "client_section_placeholder": {
        "ar": "أحدُ أقسام التقرير خرج بنصٍّ نائبٍ بلا محتوى فعليّ. يُغلقه: "
              "إعادة التوليد.",
        "en": "A report section came out as a placeholder with no real "
              "content. Fix: regenerate."},
    "confidence_band_mismatch": {
        "ar": "درجةُ الثقة المعروضة لا تطابق وصفَها اللفظيّ في التقرير. "
              "يُغلقه: إعادة التوليد.",
        "en": "The stated confidence level does not match its wording in the "
              "report. Fix: regenerate."},
    "confidence_value_conflict": {
        "ar": "التقريرُ يذكر قيمتَي ثقةٍ مختلفتين للحكم نفسه. يُغلقه: إعادة "
              "التوليد.",
        "en": "The report states two different confidence values for the "
              "same verdict. Fix: regenerate."},
    "dangling_cross_reference": {
        "ar": "إحالةٌ في التقرير تشير إلى قسمٍ أو جدولٍ غير موجود. يُغلقه: "
              "إعادة التوليد.",
        "en": "A cross-reference points to a section or table that does not "
              "exist. Fix: regenerate."},
    "evidence_body_numeric_contradiction": {
        "ar": "رقمٌ في متن التقرير يخالف الرقمَ نفسَه في سجلّ الأدلة. "
              "يُغلقه: إعادة التوليد.",
        "en": "A number in the report body contradicts the same number in "
              "the evidence log. Fix: regenerate."},
    "gaps_closing_contradiction": {
        "ar": "خاتمةُ التقرير تنفي وجودَ فجوات بينما المتنُ يعلنها. يُغلقه: "
              "إعادة التوليد.",
        "en": "The closing denies data gaps that the body declares. Fix: "
              "regenerate."},
    # الدرس ٢٥٥ — الأربعةُ المُفعَّلاتُ بالرايات (`_FLAGGED_FAIL_TRIGGERS`)
    # كانت **بلا صفٍّ واحد** هنا، فقرأ العميلُ الجملةَ العامّة «يُغلقه: إعادة
    # التوليد» على حاجبٍ **حتميّ** لا تُصلِحه إعادةُ التوليد أبداً — نصيحةٌ
    # خاطئة تُدخِل صاحبَ القرار في حلقةٍ مغلقة. النصيحةُ تُسمّي المدخلَ
    # الناقص حين يكون هو السبب.
    "high_confidence_with_missing_pillar": {
        "ar": "وُصف الحكمُ بثقةٍ عالية بينما جانبٌ أساسيٌّ من التقييم لا "
              "نعرفه بعد (الربحية غالباً — تنقصها كلفةُ الوحدة). يُغلقه: "
              "إدخالُ المدخل الناقص المذكور في «ما يجب إغلاقه قبل "
              "الالتزام» ثم إعادةُ التقييم — إعادةُ التوليد وحدها لا "
              "تُغيّره.",
        "en": "The verdict was described as high-confidence while a core "
              "side of the assessment is still unknown (usually "
              "profitability — it needs your unit cost). Fix: supply the "
              "missing input listed under what must be closed, then "
              "re-evaluate; regenerating alone will not change it."},
    # الدرس ٢٦٢ — فحوصُ سجلّ الحقائق: جملةٌ بلغة العميل تقول ما حدث وما
    # يُغلقه، لا لغةَ نظامٍ ولا اسمَ مفتاح.
    "ledger_value_mismatch": {
        "ar": "رقمٌ في نصّ التقرير يخالف القيمة المرصودة لنفس المعطى. "
              "يُغلقه: إعادة التوليد — النصُّ يُعاد بناؤه على القيمة "
              "المرصودة نفسها.",
        "en": "A figure in the report text contradicts the observed value "
              "of the same fact. Fix: regenerate — the text is rebuilt on "
              "the observed value."},
    "ledger_status_mismatch": {
        "ar": "التقريرُ يعلن معطىً «غير متاح» وهو مرصودٌ فعلاً في هذه "
              "الدراسة. يُغلقه: إعادة التوليد.",
        "en": "The report declares a fact unavailable although it was "
              "actually observed in this study. Fix: regenerate."},
    "ledger_count_mismatch": {
        "ar": "عددُ الشروط المذكور في النصّ يخالف الشروطَ المسمّاة فعلاً. "
              "يُغلقه: إعادة التوليد.",
        "en": "The number of conditions stated in the text contradicts the "
              "conditions actually named. Fix: regenerate."},
    "ledger_series_year_mismatch": {
        "ar": "سنةٌ في نصّ التقرير أحدثُ من أحدث سنةٍ مرصودةٍ في بيانات "
              "الواردات. يُغلقه: إعادة التوليد.",
        "en": "A year in the report text is later than the latest observed "
              "year in the imports data. Fix: regenerate."},
    "chart_year_mismatch": {
        "ar": "سنةُ الرسم البياني تخالف سنةَ بياناته المرصودة. يُغلقه: "
              "إعادة التوليد.",
        "en": "The chart's labelled year differs from the year of its "
              "observed data. Fix: regenerate."},
    "blocking_condition_drift": {
        "ar": "«الشرط الحاجب» مذكورٌ في موضعين بتعريفين مختلفين. يُغلقه: "
              "إعادة التوليد.",
        "en": "The blocking condition is stated twice with two different "
              "definitions. Fix: regenerate."},
    "ledger_stale": {
        "ar": "تحدّثت بياناتُ أحد المعطيات منذ كتابة هذا التقرير، فبعضُ "
              "أقسامه يصف حالةً أقدم. يُغلقه: إعادة التوليد — تُعاد الكتابة "
              "على البيانات الحالية.",
        "en": "One of the facts changed after this report was written, so "
              "some sections describe an older state. Fix: regenerate — the "
              "text is rewritten on the current data."},
    "ledger_token_unbound": {
        "ar": "تعذّر إكمالُ أحد أرقام التقرير من سجلّ بياناته. يُغلقه: "
              "إعادة التوليد.",
        "en": "One of the report's figures could not be filled from its "
              "fact ledger. Fix: regenerate."},
    "metric_value_divergence": {
        "ar": "رقمٌ واحد ظهر بقيمتين مختلفتين في التقرير. يُغلقه: إعادة "
              "التوليد.",
        "en": "One figure appeared with two different values in the "
              "report. Fix: regenerate."},
    "open_conditions_count_mismatch": {
        "ar": "عددُ الشروط المفتوحة المذكور في النصّ يخالف الشروطَ "
              "المسمّاة فعلاً. يُغلقه: إعادة التوليد.",
        "en": "The number of open conditions stated in the text "
              "contradicts the conditions actually named. Fix: "
              "regenerate."},
    "reference_to_nonexistent_figure": {
        "ar": "التقريرُ يُحيل إلى رقمٍ لا وجود له فيه. يُغلقه: إعادة "
              "التوليد.",
        "en": "The report refers to a figure that does not exist in it. "
              "Fix: regenerate."},
    "intersection_insufficiency": {
        "ar": "التوصيةُ مبنيّةٌ على تقاطعٍ من الأدلة أضعفَ من أن يحملها. "
              "يُغلقه: إعادة التوليد بعد اكتمال المصادر الناقصة.",
        "en": "The recommendation rests on an evidence intersection too thin "
              "to carry it. Fix: regenerate after the missing sources fill "
              "in."},
    "language_consistency": {
        "ar": "التقريرُ خرج مختلطَ اللغة — لغةٌ غير التي اخترتَها تسرّبت إلى "
              "نصّه. يُغلقه: إعادة التوليد.",
        "en": "The report came out language-mixed — text in a language other "
              "than the one you chose. Fix: regenerate."},
    "mirror_divergence_contraction_narrative": {
        "ar": "سردُ الانكماش مبنيٌّ على سلسلةٍ ضعيفةِ التسجيل بينما البيانات "
              "المقابلة تخالفها. يُغلقه: إعادة التوليد.",
        "en": "The contraction narrative rests on a weakly-recorded series "
              "that the mirror data contradicts. Fix: regenerate."},
    "off_market_currency": {
        "ar": "أرقامٌ بعملةٍ لا تخصّ السوق المستهدفة تسرّبت إلى التقرير، "
              "فتقرأ مضلِّلةً. يُغلقه: إعادة التوليد.",
        "en": "Figures in a currency foreign to the target market leaked "
              "into the report and read misleadingly. Fix: regenerate."},
    "orphan_short_token": {
        "ar": "بقيت في النصّ شظايا كلماتٍ مبتورة تكسر قراءة الجملة. يُغلقه: "
              "إعادة التوليد.",
        "en": "Truncated word fragments remained in the text and break the "
              "sentence. Fix: regenerate."},
    "placeholder_leak": {
        "ar": "تسرّب إلى التقرير نصٌّ نائبٌ لم يُستبدَل بمحتواه. يُغلقه: "
              "إعادة التوليد.",
        "en": "Placeholder text that was never filled in leaked into the "
              "report. Fix: regenerate."},
    "recommendation_tier_mislabel": {
        "ar": "التوصيةُ موسومةٌ بدرجةٍ أقوى ممّا تسمح به شروطُها المعلنة. "
              "يُغلقه: إعادة التوليد.",
        "en": "The recommendation is labelled stronger than its own stated "
              "conditions allow. Fix: regenerate."},
    "regulatory_hard_blocker_open": {
        "ar": "التوصيةُ إيجابيةٌ رغم شرطِ دخولٍ إلزاميٍّ لم يُحسَم بعد "
              "(اشتراطٌ نظاميٌّ مفتوح). يُغلقه: حسمُ الاشتراط ثم إعادة "
              "التوليد.",
        "en": "The recommendation is positive while a mandatory entry "
              "requirement is still unresolved. Fix: settle the requirement, "
              "then regenerate."},
    "section_structure": {
        "ar": "بنيةُ أقسام التقرير ناقصةٌ أو غيرُ مكتملة. يُغلقه: إعادة "
              "التوليد.",
        "en": "The report's section structure is incomplete. Fix: "
              "regenerate."},
    "source_coverage_below_threshold": {
        "ar": "عددُ المصادر التي استند إليها التقرير دون الحدّ الذي نسلّم "
              "عنده. يُغلقه: إعادة التشغيل بعد اكتمال المصادر.",
        "en": "The report rests on fewer sources than our delivery "
              "threshold. Fix: rerun once the sources fill in."},
    "stale_year_driving_conclusion": {
        "ar": "استنتاجٌ في التقرير مبنيٌّ على سنةٍ قديمة تجاوزت حدّ التقادم. "
              "يُغلقه: إعادة التشغيل لجلب سنةٍ أحدث.",
        "en": "A conclusion rests on a year old enough to be stale. Fix: "
              "rerun to pull a more recent year."},
    "tam_below_single_country_flow": {
        "ar": "حجمُ السوق المعروض أصغرُ من تدفّقٍ من دولةٍ واحدة داخله — "
              "تناقضٌ حسابيّ. يُغلقه: إعادة التوليد.",
        "en": "The stated market size is smaller than a single country's "
              "flow into it — an arithmetic contradiction. Fix: regenerate."},
    "trailing_ellipsis": {
        "ar": "جملةٌ في التقرير انقطعت في منتصفها. يُغلقه: إعادة التوليد.",
        "en": "A sentence in the report is cut off mid-way. Fix: "
              "regenerate."},
    "trends_hollow_completion": {
        "ar": "بحثُ الاتجاهات سُجِّل مكتملاً وهو يعلن غيابَ بيانات الموسمية "
              "وذروة الطلب — يُقرأ تغطيةً ناقصة لا اكتمالاً. يُغلقه: إعادة "
              "التشغيل؛ وإن تكرّر فبياناتُ الموسمية غير متاحة لهذا "
              "المنتج/السوق.",
        "en": "The trends research was recorded as complete while declaring "
              "that seasonality and peak-demand data are missing — that is "
              "partial coverage, not completion. Fix: rerun; if it repeats, "
              "seasonality data is unavailable for this product/market."},
    "unit_conversion_refusal": {
        "ar": "التقريرُ أعلن تعذّرَ تحويل وحدةٍ (لتر↔كجم) رغم أن معامل "
              "التحويل لهذا المنتج مسجّلٌ عندنا بمصدره — رقمٌ كان يجب أن "
              "يُحسَب لا أن يُحجَب. يُغلقه: إعادة التوليد.",
        "en": "The report declared a unit conversion (litre↔kg) impossible "
              "even though the conversion factor for this product is on "
              "record with its source — a number that should have been "
              "computed, not withheld. Fix: regenerate."},
    "verdict_label_conflict": {
        "ar": "تسميةُ الحكم في التقرير تخالف الحكمَ المحسوب. يُغلقه: إعادة "
              "التوليد.",
        "en": "The verdict label contradicts the computed verdict. Fix: "
              "regenerate."},
}


# الجملةُ العامّة حين لا توجد مخصَّصة — **لا معرّفَ خاماً أبداً** (ملاحظة
# مراجعةٍ ذاتية §58 على هذه الموجة نفسها): الفحوصُ التي تصل قائمةَ الحجب
# أكثرُ من قائدي الفشل (كلُّ ملاحظةٍ غير قابلة للإصلاح تصلها)، وكتابةُ جملةٍ
# مخصَّصةٍ لكلٍّ منها بلا معرفةٍ بمضمونها تخمينٌ يُقدَّم للعميل. الصادقُ:
# جملةٌ عامّةٌ صحيحةٌ دوماً بدل رمزٍ لا يقول شيئاً — والمخصَّصةُ مفروضةٌ على
# قائدي الفشل وحدهم (`tests/test_gate_client_reasons.py`).
_GENERIC_REASON = {
    "ar": ("لم يجتز التقريرُ ملاحظةَ جودةٍ في صياغته أو أرقامه فلم نُسلِّمه. "
           "يُغلقه: إعادة التوليد؛ وإن تكرّر فتواصل معنا."),
    "en": ("The report failed a quality check on its wording or figures, so "
           "we did not deliver it. Fix: regenerate; if it repeats, contact "
           "us."),
}


def client_reason(check: object, lang: str = "ar") -> str:
    """جملةُ الزائر لفحصٍ حاجب — مخصَّصةٌ إن وُجدت، وإلا العامّة.

    **لا تعيد معرّفاً خاماً أبداً**: طباعةُ المعرّف هي بالضبط العطلُ الذي
    وُجدت هذه الخريطة لإغلاقه. ومفتاحٌ فارغ/غير نصّي يعيد `""` (لا شيءَ
    يُوصَف) لا الجملةَ العامّة.
    """
    key = str(check or "").strip()
    if not key:
        return ""
    _lang = "en" if str(lang).lower() == "en" else "ar"
    row = _CLIENT_REASONS.get(key)
    return (row or _GENERIC_REASON)[_lang]


def client_reasons(checks, lang: str = "ar") -> list[str]:
    """جملُ الزائر لقائمة فحوصٍ — بلا تكرارٍ وبترتيب الورود، وتُسقَط الفارغة."""
    out: list[str] = []
    for c in (checks or []):
        txt = client_reason(c, lang)
        if txt and txt not in out:
            out.append(txt)
    return out


def factory_message(lang: str = "ar") -> str:
    return _FACTORY_MESSAGE_EN if str(lang).lower() == "en" else _FACTORY_MESSAGE_AR


def operator_detail(digest: list, *, fail_drivers: list | None = None) -> dict:
    """حمولةُ 409 لسطح المشغّل — تفاصيلُ الملاحظات كاملةً (جمهورٌ تقنيّ).

    `fail_drivers` (إضافيّ فقط — الشكل القائم كما هو): أسماءُ الملاحظات التي
    قادت حكم FAIL فعلاً، تمييزاً لها عن بقيّة الملاحظات الحاجبة غير القائدة
    في القائمة (حادثة قراءة حجب #12: أربعة أسماء وواحدٌ فقط هو المُفشِل)."""
    out = {"error": "quality_gate_fail", "message": _OPERATOR_MESSAGE,
           "findings": digest}
    if fail_drivers:
        out["fail_drivers"] = [str(x) for x in fail_drivers][:8]
    return out


def factory_detail(digest: list, lang: str = "ar", *,
                   fail_drivers: list | None = None) -> dict:
    """حمولةُ 409 لسطح المصنع.

    الملاحظاتُ تُرسَل **بأسماء فحوصها فقط** بلا نصوصها الداخلية: المصنعُ يحتاج
    أن يعرف أنّ تقريره حُجِب ولماذا إجمالاً، لا أن يقرأ لغةَ بوابةٍ داخلية.
    السببُ الكامل مُسجَّلٌ في الحارس وسجلّ العمليات للمشغّل.
    `fail_drivers` إضافيٌّ فقط (انظر `operator_detail`).
    """
    _checks = [str(d.get("check") or "") for d in digest][:8]
    out = {"error": "quality_gate_fail", "message": factory_message(lang),
           "blocked_checks": _checks,
           # الجملُ بلغة الزائر (بلاغ المالك الثالث) — المعرّفاتُ تبقى للآلة
           # وسطحِ المشغّل، والمصنعُ يقرأ ما وقع وما يُغلقه.
           "blocked_reasons": client_reasons(_checks, lang)}
    if fail_drivers:
        out["fail_drivers"] = [str(x) for x in fail_drivers][:8]
        out["fail_driver_reasons"] = client_reasons(fail_drivers, lang)
    return out


# ── (٦) ما يراه المصنع على سطح القراءة ───────────────────────────────────

def client_quality_summary(decision: dict, lang: str = "ar") -> dict:
    """ملخّصٌ صالحٌ للعرض على سطح المصنع (البند G-02).

    كان حكمُ البوّابة لا يصل أيَّ سطحٍ للمصنع إطلاقاً: لا حجبٌ ولا حتى إخبار.
    هذا الملخّصُ يُلحَق بحمولة `GET /platform/studies/{id}/report` فتعرضه
    الواجهة، فيعلم المصنعُ حالةَ جودة تقريره بدل أن يظنّها سليمةً دائماً.
    """
    verdict = str((decision or {}).get("verdict") or "").upper()
    n_block = len((decision or {}).get("blocking") or [])
    if verdict == "FAIL":
        # `factory_message` يُطبّع اللغةَ داخلياً (سطر 183)، فكلا فرعَي الشرط
        # القديم كانا يعيدان نفسَ السلسلة — يُطوى إلى نداءٍ واحد كبقية الفروع.
        note = factory_message(lang)
    elif verdict.startswith("PASS-WITH"):
        # صيد الفجوات ٣: كانت المقارنة بـ"WARN" بينما ثابت البوابة
        # "PASS-WITH-WARNINGS" — فرعٌ ميت، وتقريرٌ مثقلٌ بالملاحظات كان
        # يُعلَن للمصنع نجاحاً نظيفاً (G-02 نصف مُنفَّذ).
        note = ("اجتاز التقريرُ فحصَ الجودة مع ملاحظات — راجع قسم «حدود "
                "المنهجية وجودة البيانات» في التقرير."
                if lang != "en" else
                "The report passed the quality check with notes — see the "
                "methodology-and-data-limits section.")
    else:
        note = ("اجتاز التقريرُ فحصَ الجودة."
                if lang != "en" else "The report passed the quality check.")
    # شرط المُشرِف F (الدراسة الحية الرابعة — حجبٌ وصل بلا أسماء فحوص):
    # كل سطح حجب يحمل أسماء الملاحظات الحاجبة وقائدها — «لا أستطيع التصرف
    # في حجبٍ لا يقول ما الذي فشل».
    out = {"verdict": verdict or "UNKNOWN",
           "blocking_count": n_block, "note": note}
    if verdict == "FAIL":
        out["blocked_checks"] = [
            str(f.get("check") or "")
            for f in ((decision or {}).get("blocking") or [])
            if isinstance(f, dict)][:8]
        out["fail_drivers"] = [
            str(x) for x in ((decision or {}).get("fail_drivers") or [])][:8]
        # نفسُ الخريطة الواحدة على سطح القراءة (لا نسخةَ نصٍّ ثانية).
        out["blocked_reasons"] = client_reasons(out["blocked_checks"], lang)
        out["fail_driver_reasons"] = client_reasons(out["fail_drivers"], lang)
    return out
