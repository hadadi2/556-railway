"""هدف الدراسة الاحترافية — الموجة ٥: عدّاد النثر العربي (البند ٥).

«المعايرة هي التسليم لا الحقن»: العقد يصل الموجّه منذ Part B، وهذا العدّاد
يقيس هل يُطاع — حتمياً بلا نموذج. المقفول هنا: القواعد الثماني تُقاس؛
القياس تحذيري في قناة language_quality؛ الموجّه لا يوصي بما يعدّه العدّاد
ثقيلاً (درس 156 — وُحِّدت قوائم الروابط في هذه الموجة)؛ والعدّاد stdlib
بلا شبكة (AST).
"""
import ast
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import block_network


_TRANSLATED = (
    "يمثل انكماش السوق عاملاً مقيداً أمام الدخول الجديد إلى القطاع. "
    "يتم رصد الأسعار من قبل الفريق بشكل دوري في ثلاث قنوات رئيسية. "
    "لم يُرصد سعر تجزئة موثوق في ضوء محدودية البيانات المتاحة حالياً. "
    "التقرير الحالي يقدم نافذة فرصة واعدة بوصفه أداة قرار للمصدر الجديد. "
    "الشركة الرائدة المحلية الكبرى المهيمنة تسيطر من حيث الحصة على السوق.")

_AUTHENTIC = (
    "انكمش السوق خلال ثلاث سنوات، فضاقت الفرصة أمام مورد جديد. "
    "رصدنا الأسعار في ثلاث قنوات رئيسية على مدار الشهر. "
    "لم نجد سعر تجزئة موثوقاً، لذلك بقيت المقارنة السعرية مفتوحة. "
    "يسيطر مورد واحد على معظم الواردات، لكن قناة التجزئة ما تزال مفتوحة. "
    "استورد الأردن حليباً بقيمة 6.95 مليون دولار سنة 2023.")


# ── العدّاد يفرّق النثرين ─────────────────────────────────────────────────

def test_meter_separates_translated_from_authentic_prose():
    from silk_prose_meter import analyze
    bad = analyze(_TRANSLATED)
    good = analyze(_AUTHENTIC)
    assert len(bad["nominal_openers"]) > len(good["nominal_openers"])
    assert len(bad["passives"]) >= 2 and len(good["passives"]) == 0
    assert sum(bad["heavy_connectors"].values()) >= 2
    assert not good["heavy_connectors"]
    assert bad["literal_terms"] and not good["literal_terms"]


def test_meter_measures_the_goal_examples_verbatim():
    """أمثلة الهدف الحرفية: قاعدة ١."""
    from silk_prose_meter import analyze
    assert analyze("يمثّل انكماش السوق عاملاً مقيّداً أمام أي مورد جديد."
                   )["nominal_openers"]
    assert not analyze("انكمش السوق، فضاقت الفرصة أمام أي مورد جديد قادم."
                       )["nominal_openers"]


def test_meter_is_deterministic_and_count_shaped():
    from silk_prose_meter import analyze, report_lines
    a, b = analyze(_TRANSLATED), analyze(_TRANSLATED)
    assert a == b
    lines = report_lines(a)
    assert lines and any("جُمل النثر" in ln for ln in lines)


def test_report_voice_yousa_is_not_counted_as_passive():
    """«يُوصى بـ» صوت التقرير المعتمد في السجل المهني — ليس مجهولاً يُعدّ."""
    from silk_prose_meter import analyze
    m = analyze("يُوصى بتأجيل الدخول إلى السوق حتى اكتمال ملف الأهلية "
                "التنظيمية كاملاً.")
    assert m["passives"] == []


def test_meter_is_stdlib_only_no_network():
    import silk_prose_meter
    tree = ast.parse(inspect.getsource(silk_prose_meter))
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree)
                if isinstance(n, ast.Import)}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom)}
    assert imported <= {"re", "__future__"}, imported


# ── القناة التحذيرية ───────────────────────────────────────────────────────

def _report(body: str) -> str:
    return f"## 1. الخلاصة التنفيذية\nالتوصية: تأجيل.\n\n## 3. السوق\n{body}"


def test_language_quality_channel_carries_prose_findings():
    import silk_quality_gate as qg
    with block_network():
        out = qg.run_quality_gate({"deep_research": {
            "report": {"text": _report(_TRANSLATED * 2)}, "missions": {}}})
    checks = {f["check"] for f in out["language_quality"]}
    assert any(c.startswith("language_quality_prose_") for c in checks), checks
    # قياس لا حجب: لا اسم prose في مجموعتي الإفشال.
    assert not any(c.startswith("language_quality")
                   for c in qg.FAIL_TRIGGER_CHECKS)


def test_language_quality_prose_silent_on_authentic_text():
    import silk_quality_gate as qg
    with block_network():
        out = qg.run_quality_gate({"deep_research": {
            "report": {"text": _report(_AUTHENTIC * 2)}, "missions": {}}})
    assert not any(f["check"].startswith("language_quality_prose_")
                   for f in out["language_quality"])


# ── الدرس 156: الموجّه لا يوصي بما يعدّه العدّاد ثقيلاً ───────────────────

def test_writer_prompt_recommends_light_connectors_only():
    import silk_ai_judge
    from silk_prose_meter import HEAVY_CONNECTORS
    src = inspect.getsource(silk_ai_judge.deep_report)
    # سطر التوصية بالروابط صار خفيفاً، وقائمة الثقيلة تظهر تحذيراً لا توصية.
    assert "الروابط العربية الخفيفة" in src
    assert "وتجنّب" in src
    # لا مثال موجّه يفتتح بـ«وعليه، فإن» بعد التوحيد.
    assert "وعليه، فإن" not in src
    assert set(HEAVY_CONNECTORS) & {"بوصفه", "من حيث", "في ضوء", "وعليه"}


def test_part_b_carries_the_eight_prose_rules():
    from silk_style_contract import (WRITING_STANDARD_RULE,
                                     WRITING_STANDARD_RULE_EN)
    ar = WRITING_STANDARD_RULE
    assert "نثر عربي أصيل" in ar
    for needle in ("ابدأ بالفعل", "سمِّ الفاعل", "الروابط الخفيفة",
                   "الإضافة ثلاث كلمات", "المعلومة الجديدة آخر الجملة",
                   "12–25"):
        assert needle in ar, needle
    assert "Authentic prose" in WRITING_STANDARD_RULE_EN


# ── الأداة ─────────────────────────────────────────────────────────────────

def test_prose_report_tool_runs_on_a_file(tmp_path, capsys):
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import prose_report
    f = tmp_path / "r.md"
    f.write_text(_TRANSLATED, encoding="utf-8")
    sys.argv = ["prose_report.py", "--file", str(f)]
    prose_report.main()
    out = capsys.readouterr().out
    assert "جُمل النثر" in out and "افتتاح اسمي" in out
