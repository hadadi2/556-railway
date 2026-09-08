"""تحليل 20 (التقرير الحيّ الفاشل) — إسقاط القسم المكرَّر من دمج الإكمال.

الدليل المباشر (لصقه المالك): التقرير المسترَدّ حمل القسم «## 5. تحليل المستهلك
والطلب» **مرّتين** — نسخةٌ مبتورةٌ («…أن ق») ثم نسخةٌ كاملة، وتلعثماتِ دمجٍ
(«هذا الانكماش هذا الانكماش»). السبب: البذرة/المسوّدة انقطعت وسط القسم فأعاد
الإكمالُ كتابتَه كاملاً، والدمجُ أبقى الاثنين — فأفشلت البوابةُ `section_structure`.

`_dedupe_duplicate_sections` حتميّ: عند تكرار عنوانٍ حرفياً يُبقي الأخير (الكامل)
ويحذف السابق (المبتور). هرمتي بالكامل. Run:
  python3 -m pytest tests/test_analysis20_duplicate_section_dedup.py -q
"""
import contextlib
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


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


@pytest.fixture(autouse=True)
def _reset_provider_contextvars():
    import silk_llm_provider as lp
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)
    yield
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)


def _mission_reports():
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    return {"trade_flow": AgentReport(
        "LLMAgent:trade_flow",
        [DataPoint("واردات هولندا 33 مليون دولار", "UN Comtrade", 0.9, "n")],
        False, "ok")}


def _report_with_duplicated_section_5() -> str:
    """شكلُ تحليل 20 الحيّ: القسم ٥ مبتورٌ ثم مكرَّرٌ كاملاً، والباقي سليم."""
    secs = ["الخلاصة التنفيذية", "منهجية البحث ونطاقه",
            "نظرة عامة على السوق وحجمه", "ديناميكيات السوق",
            "تحليل المستهلك والطلب", "المشهد التنافسي",
            "التنظيم والوصول للسوق", "اللوجستيات وسلسلة الإمداد",
            "تقييم المخاطر", "التوصيات الاستراتيجية", "الملاحق"]
    parts = [f"## {i}. {s}\nفقرة كاملة." for i, s in enumerate(secs[:4], 1)]
    parts.append("## 5. تحليل المستهلك والطلب\nجدولٌ ثم جملةٌ تنقطع أن ق")  # مبتور
    # الإكمال أعاد ٥ كاملاً ثم ٦..١١
    parts.append("## 5. تحليل المستهلك والطلب\nالنسخةُ الكاملةُ المكتملة.")
    parts += [f"## {i}. {s}\nفقرة كاملة." for i, s in enumerate(secs[5:], 6)]
    return "\n".join(parts)


def test_dedupe_removes_truncated_earlier_section_keeps_complete():
    import silk_ai_judge as aj
    src = _report_with_duplicated_section_5()
    import re
    assert len(re.findall(r"^##\s+5\.", src, re.M)) == 2   # مكرَّرٌ قبل
    out = aj._dedupe_duplicate_sections(src)
    assert len(re.findall(r"^##\s+5\.", out, re.M)) == 1   # مرّةٌ واحدةٌ بعد
    assert "تنقطع أن ق" not in out                          # المبتورُ حُذِف
    assert "النسخةُ الكاملةُ المكتملة." in out              # الكاملُ بقي
    # الأقسام الأحد عشر كلُّها حاضرةٌ مرّةً واحدة، بالترتيب
    assert aj._section_order_issues(out) == []


def test_dedupe_noop_on_clean_report():
    import silk_ai_judge as aj
    from silk_ai_judge import report_sections
    clean = "\n".join(f"## {i}. {s}\nفقرة." for i, s in
                      enumerate(report_sections("ar"), 1))
    assert aj._dedupe_duplicate_sections(clean) == clean


def test_deep_report_seed_midsection_cut_yields_no_duplicate():
    """بذرةٌ مقطوعةٌ وسط القسم ٥، والإكمالُ يعيد ٥ كاملاً + ٦..١١ → لا قسمٌ مكرَّر
    في الناتج، والبنيةُ سليمة (لا يُفشِلها `section_structure`)."""
    import silk_ai_judge as aj
    secs = aj.report_sections("ar")

    def _seed() -> str:
        parts = [f"## {i}. {s}\nفقرة كاملة." for i, s in enumerate(secs[:4], 1)]
        parts.append("## 5. تحليل المستهلك والطلب\nجملةٌ تنقطع أن ق")
        return "\n".join(parts)

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        import silk_llm_provider as lp
        lp._last_stop_reason.set("end_turn")
        # الإكمال يعيد القسم ٥ كاملاً ثم ٦..١١
        body = ["## 5. تحليل المستهلك والطلب\nالنسخةُ الكاملة."]
        body += [f"## {i}. {s}\nفقرة." for i, s in enumerate(secs[5:], 6)]
        return "\n".join(body)

    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake_call):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا", trace_id="run-dup",
                             seed_draft=_seed())
    import re
    assert out
    assert len(re.findall(r"^##\s+5\.", out, re.M)) == 1   # لا تكرار
    assert aj._section_order_issues(out) == []             # بنيةٌ سليمة
