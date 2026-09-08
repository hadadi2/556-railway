"""أقفال بلاغ تحليل 20 — تسليم التقرير الناقص موسوماً (تجاوز §5-الإتلاف).

طبقةُ العرض: `build_view` يرفع علَمَي `incomplete`/`missing_sections` ويحقن شارة
«تقرير غير مكتمل» في **نصّ التقرير الواحد**، فتظهر في md واللوحة والمحادثة معاً؛
`render_brief` يحمل سطر النقص؛ `render_docx` يحمل اللافتة الحمراء البارزة عبر
`_stamp_degraded_banner` (نقطة اللافتة المشتركة لكل بنّاء docx). تقريرٌ مكتملٌ
لا يحمل أياً منها (لا تلوّث للمسار السويّ — عيّنات `samples/` لا تتغيّر).

طبقةُ المنطق (حارس العملية المدفوعة العقيمة + تسليم الجزئي بدل None + الاستئناف
من الجزء) مقفولةٌ في `test_wave_p6_writer_continuation` و`test_research_report_
quality`. هرمتي بالكامل: لا شبكة، لا مفتاح. Run:
  python3 -m pytest tests/test_analysis20_incomplete_delivery.py -q
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import pytest  # noqa: E402

from canonical_netherlands import netherlands_research_blob  # noqa: E402

_MISSING = ["تقييم المخاطر", "التوصيات الاستراتيجية", "الملاحق"]
_BANNER = "تقرير غير مكتمل"


def _incomplete_blob() -> dict:
    """المدوّنة القانونية نفسُها لكن عقدةُ التقرير موسومةٌ ناقصةً (نظير ما يعيده
    `write_reviewed_report` عند تسليم جزءٍ ناقص بنيوياً)."""
    blob = netherlands_research_blob()
    rep = blob["deep_research"]["report"]
    rep["incomplete"] = True
    rep["missing_sections"] = list(_MISSING)
    return blob


def test_build_view_surfaces_incomplete_flags_and_keeps_text_clean():
    import silk_render
    view = silk_render.build_view(_incomplete_blob())
    rep = view["deep_research"]["report"]
    assert rep["incomplete"] is True
    assert rep["missing_sections"] == _MISSING
    # مراجعة §58 #4: الشارة **لا** تُحقَن في `report.text` (docx يُعيد تفسيره
    # فتظهر markdown حرفياً ومكرَّرة) — النصّ يبقى نظيفاً، والمُصدِّرون يصوغونها.
    assert _BANNER not in rep["text"]


def test_markdown_carries_incomplete_banner():
    import silk_render
    from silk_reports import render_markdown
    md = render_markdown(silk_render.build_view(_incomplete_blob()))
    assert _BANNER in md
    assert "الملاحق" in md            # الأقسام الغائبة معلَنة بالاسم


def test_brief_carries_incomplete_line():
    import silk_render
    from silk_reports import render_brief
    brief = render_brief(silk_render.build_view(_incomplete_blob()))
    assert _BANNER in brief


def test_docx_carries_incomplete_banner_without_raw_markdown():
    import silk_render
    from silk_reports import render_docx
    from docx import Document
    view = silk_render.build_view(_incomplete_blob())
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "report.docx")
        render_docx(view, path)
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs)
    assert _BANNER in text
    # مراجعة §58 #4: لا markdown خام («> ⚠️») مسرّب في متن docx
    assert "> ⚠" not in text and "> ⚠️" not in text


def test_cut_only_incomplete_does_not_claim_missing_sections():
    """مراجعة §58 #2: اقتطاعٌ منتصفَ الجملة والأقسام الأحد عشر حاضرة → لا شارةُ
    «أقسام غائبة: —» مضلِّلة؛ يُقال «اقتُطِع قبل اكتماله»."""
    import silk_render
    from silk_reports import render_markdown, render_brief
    blob = netherlands_research_blob()
    rep = blob["deep_research"]["report"]
    rep["incomplete"] = True
    rep["missing_sections"] = []          # كل الأقسام حاضرة، الأخيرة مبتورة
    view = silk_render.build_view(blob)
    md = render_markdown(view)
    brief = render_brief(view)
    assert "اقتُطِع" in md and "اقتُطِع" in brief
    assert "فجواتٍ معلنة لا نتائج: —" not in md   # لا قائمة «—» كاذبة
    assert "فجوات معلنة لا نتائج): —" not in brief


def test_dashboard_renders_incomplete_flag():
    """اللوحة (web/index.html) تقرأ علَم `incomplete` وتعرض الشارة بنفس نمط لافتة
    التدهور — قفلُ حضورٍ مصدريّ (التحقّق البصريّ الحيّ رُتبةُ ٣ e2e حين يتعافى
    CI؛ اللوحة لا تُصيَّر هرمتياً)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "web", "index.html"), encoding="utf-8").read()
    assert "rep.incomplete" in src            # يقرأ العلَم
    assert "missing_sections" in src          # يعلن الأقسام الغائبة
    assert "تقرير غير مكتمل" in src            # الشارة نفسها


def test_complete_report_has_no_incomplete_banner():
    """المسار السويّ لا يتلوّث: تقريرٌ مكتملٌ بلا علَمٍ ولا شارة (فلا تتغيّر
    عيّنات `samples/`)."""
    import silk_render
    from silk_reports import render_markdown, render_brief
    view = silk_render.build_view(netherlands_research_blob())
    rep = view["deep_research"]["report"]
    assert not rep.get("incomplete")
    assert _BANNER not in rep["text"]
    assert _BANNER not in render_markdown(view)
    assert _BANNER not in render_brief(view)
