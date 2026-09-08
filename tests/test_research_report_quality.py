"""أقفال جودة تقرير /research (تدقيق تسليم تمور × هولندا).

خمسة عيوب من التقرير المُسلَّم:
  Q1 تسليم مقتطع: القسم ١٠ انتهى وسط جملة والملاحق مفقودة — يُسلَّم بلا إعلان.
  Q2 CAGR متعارض: 13.3% (2020-2024) في الملخّص مقابل 16.3% (2019-2023) في الحكم.
  Q3 عمود العملة مضلِّل: «بالدولار» يحمل قيماً باليورو.
  Q4/Q5 إطناب وتكرار اعتذار الفجوة — تغييرات مُوجِّه (تُختبَر نصّياً على الموجِّه).

هيرمتي — لا شبكة، لا مفتاح حقيقي.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contextlib


@contextlib.contextmanager
def _env(**vals):
    old = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            os.environ[k] = v if v is not None else os.environ.get(k, "")
            if v is None:
                os.environ.pop(k, None)
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ═══ Q1 — تسليم مقتطع يُعلَن فجوةً لا يُشحن خاماً ═════════════════════════

_FULL_REPORT = "\n\n".join(
    f"## {i}. {t}\nفقرة كاملة تنتهي بجملة سليمة."
    for i, t in enumerate((
        "الخلاصة التنفيذية", "منهجية البحث ونطاقه", "نظرة عامة على السوق وحجمه",
        "ديناميكيات السوق", "تحليل المستهلك والطلب", "المشهد التنافسي",
        "التنظيم والوصول للسوق", "اللوجستيات وسلسلة الإمداد", "تقييم المخاطر",
        "التوصيات الاستراتيجية", "الملاحق"), start=1))


def test_truncated_then_still_incomplete_delivers_flagged_partial():
    """قرار المالك (تجاوز §5-الإتلاف، تحليل 20): كاتبٌ يبقى مقتطعاً حتى بعد
    الإكمال العقيم => **يُسلَّم الجزءُ الأوفى** (لا None) كي لا يُهدَر نصٌّ
    مدفوع؛ والمستدعي يَسِمه «غير مكتمل» ويُعلن الأقسام الغائبة. لا لافتة
    تشغيلية (اسم متغيّر بيئة/⚠) تتسرّب داخل نصّ الكاتب. حارسُ العملية العقيمة
    يمنع دفعَ نداءٍ ثانٍ بلا تقدّم (بلاغ تحليل 20: ٦٤ألف رمز، صفر قسم)."""
    import importlib
    import silk_ai_judge
    import silk_llm_provider
    import silk_context
    with _env(ANTHROPIC_API_KEY="k", SILK_WRITER_MAX_TOKENS="1000",
              SILK_MAX_TOKENS_CEILING="2000", SILK_MAX_TOKENS_RETRIES="1"):
        importlib.reload(silk_ai_judge)

        class _Trunc:
            def __init__(self):
                self.calls = 0

            def complete(self, system, user, max_tokens, model, timeout):
                self.calls += 1
                silk_context.record_llm_usage(model, 400, 200)
                silk_llm_provider._last_stop_reason.set("max_tokens")  # دائماً مقتطع
                return "## 1. الخلاصة التنفيذية\nالحكم WATCH. السوق ينمو وي"

            def complete_tools(self, *a, **k):
                return None

        prov = _Trunc()
        silk_llm_provider._provider_instance = prov
        try:
            silk_context.begin_data_counter()
            out = silk_ai_judge.deep_report(
                {}, "ملخّص", {"verdict": "WATCH"}, "تمور", "Netherlands")
        finally:
            silk_llm_provider.reset_provider()
    assert out                                   # يُسلَّم الجزء، لا None
    assert silk_ai_judge._writer_incomplete(out)  # ما زال ناقصاً (معلَن)
    assert "⚠" not in out and "SILK_" not in out  # لا لافتة تشغيلية داخل النصّ
    assert prov.calls == 2   # مسوّدة + إكمالٌ عقيمٌ واحدٌ ثم توقّف (لا ثالثٌ مهدِر)


def test_truncated_then_continuation_completes_ships_full_report():
    """§5: أول نداء مقتطع، ونداء الإكمال يُكمِل الأقسام الباقية => يُشحن
    التقرير كاملاً بلا علامة اكتطاع ولا اسم متغيّر بيئة ولا ⚠."""
    import importlib
    import silk_ai_judge
    import silk_llm_provider
    import silk_context
    with _env(ANTHROPIC_API_KEY="k", SILK_WRITER_MAX_TOKENS="1000",
              SILK_MAX_TOKENS_CEILING="2000", SILK_MAX_TOKENS_RETRIES="1"):
        importlib.reload(silk_ai_judge)

        class _TruncThenComplete:
            def __init__(self):
                self.n = 0

            def complete(self, system, user, max_tokens, model, timeout):
                silk_context.record_llm_usage(model, 400, 200)
                self.n += 1
                # المسوّدة (n=1) مقتطعة بنصّ؛ نداءُ الإكمال (n=2) **يزيد التغطية**
                # فيُكمِل التقرير — يُحتفَظ به (حارسُ العملية العقيمة يُبقي فقط
                # الإكمالات التي تزيد الأقسام، وهذا يزيدها كلَّها).
                if self.n <= 1:
                    silk_llm_provider._last_stop_reason.set("max_tokens")
                    return "## 1. الخلاصة التنفيذية\nالحكم WATCH. السوق ينمو وي"
                silk_llm_provider._last_stop_reason.set("end_turn")
                return _FULL_REPORT

            def complete_tools(self, *a, **k):
                return None

        silk_llm_provider._provider_instance = _TruncThenComplete()
        try:
            silk_context.begin_data_counter()
            out = silk_ai_judge.deep_report(
                {}, "ملخّص", {"verdict": "WATCH"}, "تمور", "Netherlands")
        finally:
            silk_llm_provider.reset_provider()
    assert out                                     # اكتمل عبر نداء الإكمال
    assert "الملاحق" in out                        # آخر قسم حاضر
    assert "⚠" not in out and "SILK_" not in out   # §2.4/§5: لا لافتة تشغيلية
    assert "القسم لم يكتمل" not in out


def test_complete_writer_output_ships_without_ops_warning():
    """§5: اكتمال طبيعي => يُشحن التقرير بلا أي لافتة اكتطاع/متغيّر بيئة."""
    import importlib
    import silk_ai_judge
    import silk_llm_provider
    import silk_context
    with _env(ANTHROPIC_API_KEY="k"):
        importlib.reload(silk_ai_judge)

        class _Complete:
            def complete(self, system, user, max_tokens, model, timeout):
                silk_context.record_llm_usage(model, 400, 200)
                silk_llm_provider._last_stop_reason.set("end_turn")   # اكتمال طبيعي
                return _FULL_REPORT

            def complete_tools(self, *a, **k):
                return None

        silk_llm_provider._provider_instance = _Complete()
        try:
            silk_context.begin_data_counter()
            out = silk_ai_judge.deep_report(
                {}, "ملخّص", {"verdict": "WATCH"}, "تمور", "Netherlands")
        finally:
            silk_llm_provider.reset_provider()
    assert out and "⚠" not in out and "SILK_" not in out


# ═══ Q2 — معدّل نمو سنوي مركّب واحد قانوني (بوابة الجودة) ══════════════════

def _dr_with(text, reasoning=""):
    return {"deep_research": {
        "report": {"text": text},
        "verdict": {"ai": {"reasoning": reasoning}},
        "missions": {}, "analyst": {}}}


def test_quality_gate_flags_inconsistent_cagr_windows():
    import silk_quality_gate as q
    view = _dr_with(
        "واردات هولندا تنمو بمعدّل سنوي مركّب 13.3% خلال 2020-2024.",
        "السوق ينمو 16.3% سنوياً (2019-2023) وهو جاذب.")
    res = q.run_quality_gate(view)
    checks = [f["check"] for f in res["findings"]]
    assert "cagr_inconsistency" in checks
    # يُعلَن ضمن ملاحظات المنهجية (مرئي، لا صامت).
    assert any("13.3" in n and "16.3" in n for n in res["methodology_notes"])


def test_quality_gate_passes_single_canonical_cagr():
    import silk_quality_gate as q
    view = _dr_with(
        "نمو سنوي مركّب 13.3% خلال 2020-2024.",
        "يدعم الحكمَ النموُّ 13.3% خلال 2020-2024.")
    checks = [f["check"] for f in q.run_quality_gate(view)["findings"]]
    assert "cagr_inconsistency" not in checks


# ═══ Q3 — عمود السعر مُعنوَن بالعملة المرصودة لا بوعد تحويل ════════════════

def test_quality_gate_flags_currency_label_mismatch():
    import silk_quality_gate as q
    view = _dr_with("| المنتج | السعر/كجم بالدولار |\n"
                    "| تمر سكري | 7.49 يورو (تعذّر التحويل) |")
    checks = [f["check"] for f in q.run_quality_gate(view)["findings"]]
    assert "currency_label_mismatch" in checks


def test_quality_gate_passes_currency_labeled_by_observed():
    import silk_quality_gate as q
    view = _dr_with("| المنتج | السعر/كجم (بعملة الرصد) |\n"
                    "| تمر سكري | 7.49 يورو |")
    checks = [f["check"] for f in q.run_quality_gate(view)["findings"]]
    assert "currency_label_mismatch" not in checks


def test_writer_prompt_price_column_not_hardcoded_dollar():
    # Q3 على مستوى القالب: موجِّه الكاتب لم يعد يفرض عمود «بالدولار»، بل يطلب
    # التعنون بالعملة المرصودة صراحةً.
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_ai_judge.py"), encoding="utf-8").read()
    assert "السعر/كجم بالدولار" not in src
    assert "بعملة الرصد" in src
    assert "لا تحوّل عملةً ولا تَعِد بتحويلٍ لم يُجرَ" in src


# ═══ Q4/Q5 — قيود الأسلوب في موجِّه الكاتب (تغييرات موجِّه) ════════════════

def test_writer_prompt_carries_prose_and_gap_discipline():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_ai_judge.py"), encoding="utf-8").read()
    assert "٢٥ كلمة وسطياً" in src                    # Q4 طول الجملة
    assert "٣٥ كلمة (السقف الأقصى الموحّد)" in src    # الدرس 150
    assert "تحوّطٌ واحد لكل ادّعاء" in src            # Q4 تحوّط واحد
    assert "تُذكَر مرّةً واحدة في قسمها" in src        # Q5 الفجوة مرّة ثم إحالة
