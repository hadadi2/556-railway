"""اختبار الانحدار المطلوب #5 من أمر إصلاح المحرّك (موجة سدّ الفجوات F6).

نص الأمر: «صفر إصابات على فحوص التكرار والبتر والقوس اليتيم» بعد الفكس —
على **تقرير كامل** لا مقتطفات. الفحوص الثلاثة (`repeated_span`،
`empty_citation`، `trailing_ellipsis`) مُفشِلة (`_REGRESSION_GUARD_FIRED`)،
فانحدارٌ كاذبٌ في أحدها يحجب تسليم كل تقرير سليم بلا أي اختبار يلتقطه —
هذا الملف هو قفل الاتجاه المعاكس: التقرير القانوني الكامل يمرّ نظيفاً،
وحقن عيبٍ واحد يوقع فحصَه وحده. هرمتي. Run:
  python3 -m pytest tests/test_goal_full_report_zero_hits.py -q
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

import silk_quality_gate as QG                           # noqa: E402
import silk_render as R                                  # noqa: E402
from canonical_netherlands import netherlands_research_blob  # noqa: E402

_TRIO = ("repeated_span", "empty_citation", "trailing_ellipsis")


def _gate_checks(view) -> dict:
    out = QG.run_quality_gate(view)
    hits = {}
    for f in out["findings"]:
        hits.setdefault(f["check"], []).append(f.get("note", ""))
    return hits


def test_full_canonical_report_is_clean_on_the_three_fail_checks():
    """التقرير القانوني الكامل (هولندا/تمور — نفس شكل rung-2/3) عبر البوابة:
    صفر إصابات على الثلاثي المُفشِل — سلبية كاذبة في أحدها تُرى هنا فوراً."""
    view = R.build_view(netherlands_research_blob(), "ar")
    hits = _gate_checks(view)
    for chk in _TRIO:
        assert chk not in hits, (chk, hits.get(chk))


def _with_report_text(mutate):
    blob = netherlands_research_blob()
    view = R.build_view(blob, "ar")
    rep = view["deep_research"]["report"]
    rep["text"] = mutate(rep["text"])
    return view


def test_injected_stutter_trips_repeated_span_alone():
    dup = ("تسجل الفئة الضيقة مؤشر تركز سوق مرتفعا جدا هنا "
           "تسجل الفئة الضيقة مؤشر تركز سوق مرتفعا جدا هنا")
    view = _with_report_text(lambda t: t + "\n\n" + dup)
    hits = _gate_checks(view)
    assert "repeated_span" in hits
    assert "empty_citation" not in hits and "trailing_ellipsis" not in hits


def test_injected_orphan_comma_trips_empty_citation_alone():
    view = _with_report_text(
        lambda t: t + "\n\nقيمة مرصودة (، World Bank رصد مباشر لعام 2025).")
    hits = _gate_checks(view)
    assert "empty_citation" in hits
    assert "repeated_span" not in hits and "trailing_ellipsis" not in hits


def test_injected_mid_list_ellipsis_trips_trailing_ellipsis_alone():
    """حقن حادثة البند 12 حرفياً: بند قائمة في منتصف كتلة ينتهي بحذف."""
    view = _with_report_text(
        lambda t: t + "\n\n- الديموغرافيا والاقتصاد الكلي: بيانات ناقصة…\n"
                      "- بند سليم يختم القائمة بجملة تامة ومكتملة.")
    hits = _gate_checks(view)
    assert "trailing_ellipsis" in hits
    assert "repeated_span" not in hits and "empty_citation" not in hits
