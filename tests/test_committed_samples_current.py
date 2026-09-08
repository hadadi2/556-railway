"""العيّناتُ الملتزَمة تطابق ما تُنتِجه الشيفرة اليوم · §10.6 enforcement.

> **القاعدة (§10.6).** المراجعون يفتحون الملفّات من الريبو — لا قناةَ مرفقات.
> فكلُّ تغييرٍ في طبقة العرض يعيد توليدَ العيّنات الملتزَمة في `samples/`.
>
> **والفجوة المقيسة:** القاعدةُ كانت **بلا إنفاذ**. عيّنةُ الكويت الملتزَمة
> على `main` كانت متخلّفةً عن الشيفرة بثلاثة فروق مادّية: **قسمُ النموذج
> الاقتصادي كلُّه غائب** (وهو «أهمّ رقم قرار في الدراسة» — الدرس ٨٤)،
> وترويسةُ «TEST RUN» ما زالت مطبوعةً وقد توقّف المُصيِّر عن إصدارها،
> ورمزُ التعداد تغيّر. أي أنّ المراجعَ يفتح المصنوعَ الملتزَم فيرى تقريراً
> **ليس** ما يُنتِجه الكود — وهو بعينه العطلُ الذي وُجدت §10.6 لمنعه.
>
> **The gap measured:** rule §10.6 had no enforcement, so the committed
> Kuwait sample had drifted from what the renderer actually emits — missing
> the entire economics section. A reviewer opening the committed artifact was
> reading a report the code no longer produces.

هذا القفلُ يعيد توليدَ عيّنات **الماركداون** في الذاكرة ويقارنها بالملتزَم،
بعد تطبيع الحقول المتغيّرة بطبيعتها (تاريخُ التشغيل وحدَه). الـdocx خارجَه
عمداً: طوابعُ الـzip تتغيّر كلَّ تشغيل، فمقارنتُها بايتياً حارسٌ يُحمِّر بلا
انحدارٍ حقيقيّ — وضجيجُ حارسٍ يُطفئه صاحبُه أسوأُ من غيابه.
"""
from __future__ import annotations

import os
import pathlib
import re
import runpy
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DATE_ROW_RE = re.compile(r"(\|\s*(?:التاريخ|Date)\s*\|)\s*\d{4}-\d{2}-\d{2}\s*\|")
# ختمُ زمنِ السحب داخل سطر المصدر — يتغيّر كلَّ يوم، وليس محتوى.
_PULLED_RE = re.compile(r"((?:سُحب|Retrieved)\s*:\s*)\d{4}-\d{2}-\d{2}")
# خلايا تاريخ التوليد في docx: استخراج النص يضع قيمة الخلية سطراً مستقلاً
# بعد سطر تسميتها، فكانت خارج نمط صفّ الماركداون أعلاه — القفل ينجح يومَ
# التزام العيّنة ويحمرّ بانقلاب منتصف الليل بلا أي تغيير محتوى (اكتُشف
# 2026-08-26 صباحاً على شجرةٍ فرقُها الكامل سطرا تاريخ). التطبيع يقيس
# المحتوى لا الساعة.
_DATE_CELL_RE = re.compile(
    r"((?:تاريخ التقرير|تاريخ التوليد|Report date|Generated at)\n)"
    r"\d{4}-\d{2}-\d{2}")


def _normalise(text: str) -> str:
    """طبِّع ما يتغيّر بطبيعته — أختامُ الزمن وحدَها، لا محتوى."""
    out = _DATE_ROW_RE.sub(r"\1 — |", text.replace("\r\n", "\n"))
    out = _DATE_CELL_RE.sub(r"\1—", out)
    return _PULLED_RE.sub(r"\1—", out).strip()


def _kuwait_markdown() -> str:
    """نفسُ مسار `tools/gen_kuwait_battery_sample.py` — بما فيه وسمُ التشغيلة
    البرهانية (`SILK_HERMETIC=1`) الذي يُظهِر لافتة TEST RUN في العيّنة.
    مسارٌ مختلفٌ عن مسار التوليد يجعل الحارسَ يقارن مصنوعَين مختلفَين."""
    from silk_render import build_view
    from silk_reports import render_markdown
    import silk_quality_gate
    from tools.canonical_kuwait_peanut_butter import kuwait_research_blob
    prev = os.environ.get("SILK_HERMETIC")
    os.environ["SILK_HERMETIC"] = "1"
    try:
        view = build_view(kuwait_research_blob())
        view["deep_research"]["quality_gate"] = \
            silk_quality_gate.run_quality_gate(view)
        return render_markdown(view)
    finally:
        if prev is None:
            os.environ.pop("SILK_HERMETIC", None)
        else:
            os.environ["SILK_HERMETIC"] = prev


def _research_markdown() -> str:
    """نفسُ مسار `tools/gen_research_sample.py` بلا كتابةٍ على القرص.

    السكربتُ يحرس الكتابةَ بـ`SILK_WRITE_SAMPLES` (الموجة B/E2) — فتشغيلُه
    هنا يقرأ `view` منه بلا توسيخ شجرة العمل."""
    from silk_reports import render_markdown
    ns = runpy.run_path(str(_ROOT / "tools" / "gen_research_sample.py"),
                        run_name="__sample_lock__")
    return render_markdown(ns["view"])


def _analyze_markdown() -> str:
    """عيّنةُ `/analyze` الكاملة — من نفسِ تشغيلة المولّد الحتمية.

    المولّدُ كان يبني ويكتب في دالةٍ واحدة، فبقي هذا المصنوعُ خارجَ القياس
    (مراجعة ذاتية §58). `build_sample_result` مفصولةٌ الآن فلا كتابةَ هنا."""
    from silk_reports import render_markdown
    from tools.gen_analyze_samples import build_sample_result
    return render_markdown(build_sample_result()["view"])


_CASES = [
    ("kuwait_peanut_butter_research_report.md", _kuwait_markdown),
    ("research_report_latest.md", _research_markdown),
    ("report_full_latest.md", _analyze_markdown),
]


def test_every_committed_markdown_sample_is_under_the_lock():
    """لا عيّنةَ ماركداون تفلت من القياس صامتةً.

    القاعدةُ نفسُها التي أنتجت هذه الموجة: ما لا يُقاس لا يُدَّعى صحيحاً.
    فإن أُضيفت عيّنةٌ جديدة إلى `samples/` بلا قفل، يُحمِّر هذا الاختبار."""
    committed = {p.name for p in (_ROOT / "samples").glob("*.md")
                 if p.name != "README.md"}
    locked = {name for name, _ in _CASES}
    assert committed == locked, (
        f"عيّناتٌ ملتزَمة بلا قفل: {sorted(committed - locked)}؛ "
        f"أقفالٌ بلا عيّنة: {sorted(locked - committed)}")


@pytest.mark.parametrize("name,builder", _CASES,
                         ids=[c[0] for c in _CASES])
def test_committed_markdown_sample_matches_what_the_code_emits(name, builder):
    """العيّنةُ الملتزَمة == مخرَجُ المُصيِّر اليوم (§10.6).

    الفشلُ هنا معناه واحدٌ من اثنين، وكلاهما فعلٌ مطلوب لا استثناء:
    إمّا أنّ تغييرَ عرضٍ شُحِن بلا إعادة توليد — فأعِد التوليد
    (`python3 tools/gen_kuwait_battery_sample.py` /
    `python3 tools/gen_research_sample.py`) والتزِم الناتج؛ وإمّا أنّ
    المُصيِّر انحدر — فأصلِح المُصيِّر لا العيّنة."""
    committed = (_ROOT / "samples" / name).read_text(encoding="utf-8")
    fresh = builder()
    assert _normalise(fresh) == _normalise(committed), (
        f"عيّنةُ «{name}» الملتزَمة تخالف مخرَجَ الشيفرة — المراجعُ يفتح "
        "مصنوعاً ليس ما يُنتِجه الكود (§10.6). أعِد التوليد والتزِم الناتج، "
        "أو أصلِح المُصيِّر إن كان الفرقُ انحداراً.")


def test_the_sample_lock_can_actually_fail():
    """الحارسُ يُثبِت قدرتَه على الفشل قبل أن يُصدَّق (الدرس ٩٨): فرقٌ في
    المحتوى يجب أن يُلتقَط، وفرقُ التاريخ وحدَه يجب أن يُطبَّع."""
    base = "| التاريخ | 2026-01-01 |\nالنموذج الاقتصادي\n"
    same_but_dated = "| التاريخ | 2026-08-21 |\nالنموذج الاقتصادي\n"
    drifted = "| التاريخ | 2026-01-01 |\n"
    assert _normalise(base) == _normalise(same_but_dated), \
        "التاريخُ ليس محتوى — تطبيعُه واجب وإلا صار الحارسُ ضجيجاً"
    assert _normalise(base) != _normalise(drifted), \
        "قسمٌ كاملٌ ساقطٌ ولم يلتقطه الحارس — حارسٌ عاجزٌ عن الفشل"


# ═══════ صيد الفجوات ٣ (الدرس 163): docx والمختصر وجسم JSON تحت القفل ═══════
# كان القفل ماركداون فقط — فتخلّفت `client_report_latest_en.docx` ثلاثَ موجاتِ
# عرضٍ بصمت (مفردات غياب لم تعد تُنتَج). مقارنة بايتات الـzip ضجيج فعلاً،
# لكن **النص المستخرج** حتمي — يُقارن هو بعد نفس التطبيع.

def _docx_text(path) -> str:
    from docx import Document
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        for row in tbl.rows:
            parts.extend(c.text for c in row.cells)
    return "\n".join(parts)


def _client_docx_text(lang: str) -> str:
    import tempfile
    from silk_reports import render_client_docx
    from tools.gen_client_report_sample import build_sample_view
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "c.docx")
        render_client_docx(build_sample_view(lang), p)
        return _docx_text(p)


_DOCX_CASES = [
    ("client_report_latest.docx", lambda: _client_docx_text("ar")),
    ("client_report_latest_en.docx", lambda: _client_docx_text("en")),
]


@pytest.mark.parametrize("name,builder", _DOCX_CASES,
                         ids=[c[0] for c in _DOCX_CASES])
def test_committed_client_docx_text_matches_what_the_code_emits(name, builder):
    committed = _docx_text(_ROOT / "samples" / name)
    fresh = builder()
    assert _normalise(fresh) == _normalise(committed), (
        f"نصُّ عيّنة «{name}» الملتزَمة يخالف مخرَجَ المُصيِّر اليوم (§10.6) "
        "— أعِد التوليد (tools/gen_client_report_sample.py [--lang en]) "
        "والتزِم الناتج، أو أصلِح المُصيِّر إن كان الفرقُ انحداراً.")


def test_committed_brief_and_json_are_current():
    """`brief_latest.txt` و`analysis_latest.json` كانا خارج القفل بلا سبب
    معلَن — المختصر يُقارن نصاً، وجسم JSON على مفاتيح عرضه المستقرة."""
    import json as _json
    from silk_reports import render_brief
    from tools.gen_analyze_samples import build_sample_result
    result = build_sample_result()
    committed_brief = (_ROOT / "samples" / "brief_latest.txt").read_text(
        encoding="utf-8")
    assert _normalise(render_brief(result["view"])) == \
        _normalise(committed_brief), "brief_latest.txt متقادم — أعد التوليد"
    committed = _json.loads((_ROOT / "samples" / "analysis_latest.json")
                            .read_text(encoding="utf-8"))
    # الأختام الزمنية تتغير كل تشغيلة — تُقارن بنية العرض ومفاتيحه العليا.
    assert set(committed.get("view", {}).keys()) == \
        set(result["view"].keys()), "شكل view في analysis_latest.json انحرف"
