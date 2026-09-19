"""الدرس ٢٦١ — محدِّدُ العنوانِ الحرفيُّ لا يحجب تقريراً مدفوعاً.

**البلاغ الحيّ (Railway، نشر eacc773، 2026-09-19T05:55:21):**

    write_reviewed_report: delivering INCOMPLETE report
    (17341 chars, 0/11 sections present) — reviewer skipped, flagged incomplete

سبعةَ عشرَ ألفَ حرفٍ مدفوعةٍ خرجت من الكاتب، و**صفرٌ** من الأقسام الأحد عشر
تعرّف عليها المحدِّدُ الحرفيُّ `^##\\s+\\d+\\.` — فأطلق حاجبَين معاً
(`section_structure` + `client_section_placeholder`) وحُجِب تنزيلُ التقرير
كلِّه (409) على **اختلافٍ شكليٍّ في سطرِ عنوان**.

العلاجُ الجذريُّ حتميٌّ ومجانيّ: `canonicalize_section_headings` تُعيد كتابةَ
سطرِ العنوان إلى الصيغة القانونية `## N. <العنوان>` حين — وحين فقط — يطابق
عنوانُه أحدَ العناوين القانونية بعد التطبيع. لا نداءَ نموذجٍ إضافيّ، ولا فحصَ
حاجبٍ جديد، ولا إعادةَ توليدٍ مدفوعة.

هرمتيّ بالكامل: لا شبكة، لا مفتاح. Run:
  python3 -m pytest tests/test_heading_canonicalization.py -q
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import pytest  # noqa: E402

import silk_ai_judge as writer  # noqa: E402

_BODY = "نصّ القسم كاملاً بجملة منتهية."


def _canonical_draft(lang: str = "ar") -> str:
    return "\n\n".join(
        f"## {i}. {title}\n{_BODY}"
        for i, title in enumerate(writer.report_sections(lang), 1))


def _draft_with(fmt, lang: str = "ar") -> str:
    """مسوّدةٌ عناوينُها بصيغةِ `fmt(i, title)` — والمتنُ هو هو."""
    return "\n\n".join(
        f"{fmt(i, title)}\n{_BODY}"
        for i, title in enumerate(writer.report_sections(lang), 1))


def _ar_indic(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


# ── ١) الأشكالُ التي كانت تُحجَب — كلُّها تُصبح مقروءةً بعد التطبيع ──────────

@pytest.mark.parametrize("fmt", [
    lambda i, t: f"# {i}. {t}",                 # مستوى واحد بدل اثنين
    lambda i, t: f"### {i}. {t}",               # ثلاثة
    lambda i, t: f"#### {i}. {t}",
    lambda i, t: f"## {_ar_indic(i)}. {t}",     # أرقام عربية-هندية
    lambda i, t: f"# {_ar_indic(i)}) {t}",
    lambda i, t: f"## {i} - {t}",               # شرطة بدل نقطة
    lambda i, t: f"## {i}) {t}",
    lambda i, t: f"## {i}: {t}",
    lambda i, t: f"## {t}",                     # بلا ترقيم أصلاً
    lambda i, t: f"##{i}.{t}",                  # بلا مسافات
    lambda i, t: f"**{i}. {t}**",               # غامقٌ لا عنوان
    lambda i, t: f"**{t}**",
    lambda i, t: f"{i}. {t}",                   # سطرٌ عارٍ مرقَّم
    lambda i, t: f"{_ar_indic(i)}- {t}",
    lambda i, t: f"## {i}. {t} ",               # مسافةٌ ذيلية
])
def test_every_blocked_heading_shape_becomes_canonical(fmt):
    draft = _draft_with(fmt)
    # الحالةُ المرصودة قبل العلاج: صفرُ أقسامٍ متعرَّف عليها (أو نقصٌ بنيويّ).
    fixed = writer.canonicalize_section_headings(draft)
    assert writer._missing_sections(fixed) == []
    assert writer._writer_incomplete(fixed) == []
    assert writer._section_order_issues(fixed) == []
    # المتنُ لم يُمَسّ — لا حرفَ واحداً من محتوى الكاتب المدفوع.
    assert fixed.count(_BODY) == len(writer.report_sections())


def test_english_report_is_canonicalized_the_same_way():
    draft = _draft_with(lambda i, t: f"# {i}) {t}", lang="en")
    fixed = writer.canonicalize_section_headings(draft, "en")
    assert writer._missing_sections(fixed, "en") == []
    assert writer._section_order_issues(fixed, "en") == []


def test_arabic_diacritics_on_a_heading_do_not_hide_it():
    draft = "## 1. الخُلاصةُ التنفيذيّة\n" + _BODY
    fixed = writer.canonicalize_section_headings(draft)
    assert "## 1. الخلاصة التنفيذية" in fixed


def test_writer_number_is_ignored_in_favour_of_the_canonical_order():
    """رقمُ الكاتبِ الخطأُ لا يكسر الترتيب — الترتيبُ القانونيُّ هو المرجع."""
    draft = _draft_with(lambda i, t: f"## 99. {t}")
    fixed = writer.canonicalize_section_headings(draft)
    assert writer._section_order_issues(fixed) == []
    assert "## 99." not in fixed


# ── ٢) قواعدُ الأمان: لا يمسّ ما ليس عنواناً قانونياً ──────────────────────

def test_a_canonical_draft_is_returned_byte_for_byte():
    draft = _canonical_draft()
    assert writer.canonicalize_section_headings(draft) == draft


def test_idempotent():
    once = writer.canonicalize_section_headings(_draft_with(lambda i, t: f"# {i}. {t}"))
    assert writer.canonicalize_section_headings(once) == once


def test_a_heading_that_is_not_a_canonical_section_is_left_alone():
    draft = ("## 1. الخلاصة التنفيذية\n" + _BODY
             + "\n\n### خارطة طريق الدخول\nبنود.\n\n## 4. قسم من عند الكاتب\nنصّ.")
    fixed = writer.canonicalize_section_headings(draft)
    assert "### خارطة طريق الدخول" in fixed      # المرساةُ الفرعية سليمة
    assert "## 4. قسم من عند الكاتب" in fixed    # عنوانٌ غيرُ قانونيّ كما هو


def test_a_body_line_that_merely_mentions_a_section_name_is_not_promoted():
    draft = ("## 1. الخلاصة التنفيذية\n"
             "يشرح قسم تقييم المخاطر تفاصيل ذلك، وهي جملة متن لا عنوان.\n")
    fixed = writer.canonicalize_section_headings(draft)
    assert "## 9. تقييم المخاطر" not in fixed
    assert writer._missing_sections(fixed) != []   # الفجوةُ تبقى معلَنةً صادقة


def test_a_truly_missing_section_stays_missing():
    """لا تخمينَ ولا fuzzy: عنوانٌ مختلفٌ يبقى غائباً ويُعلَن فجوةً."""
    draft = _canonical_draft().replace("## 9. تقييم المخاطر", "## 9. المخاطر")
    fixed = writer.canonicalize_section_headings(draft)
    assert "تقييم المخاطر" in writer._missing_sections(fixed)


def test_empty_and_none_are_safe():
    assert writer.canonicalize_section_headings("") == ""
    assert writer.canonicalize_section_headings(None) is None


# ── ٣) الأثرُ عند القراءة: مدوّنةٌ حيّةٌ محجوبةٌ تُشفى بلا إعادة توليد ───────

def test_stored_report_with_hash_headings_passes_the_gate_through_build_view():
    """نفسُ الحجبِ الحيِّ (دراسة ٦): نصٌّ مخزَّنٌ عناوينُه `#` — يُقرأ سليماً."""
    import silk_render
    import silk_quality_gate as gate
    from canonical_netherlands import netherlands_research_blob

    blob = netherlands_research_blob()
    text = blob["deep_research"]["report"]["report"]
    # حوّل العناوينَ القانونية إلى `# N)` — الشكلُ الذي كان يحجب.
    broken = re.sub(r"^##\s+(\d+)\.\s*", r"# \1) ", text, flags=re.M)
    assert broken != text
    blob["deep_research"]["report"]["report"] = broken

    view = silk_render.build_view(blob)
    dr = view["deep_research"]
    assert gate._check_section_structure(dr) == []
    assert gate._check_client_section_would_be_placeholder(dr) == []


def test_the_canonical_blob_itself_is_unchanged_by_the_normaliser():
    """«القيمُ مقدّسة»: المسارُ السويُّ لا يتغيّر بايتاً."""
    import silk_render
    from canonical_netherlands import netherlands_research_blob

    blob = netherlands_research_blob()
    before = silk_render.build_view(netherlands_research_blob())
    after = silk_render.build_view(blob)
    assert after["deep_research"]["report"]["text"] == \
        before["deep_research"]["report"]["text"]


# ── ٤) قفلُ الموجّه↔المحلّل: الصيغةُ المأمورةُ هي الصيغةُ المقبولة ──────────
#
# الدرس ٢٥٤ بعائلةٍ جديدة: الموجّهُ يأمر الكاتبَ بصيغةِ عنوانٍ حرفية، وأربعةُ
# محلّلين يقبلون صيغةً حرفية — تباعدُهما يحجب التقريرَ على **طاعةِ الكاتب**.
# القفلُ بنائيٌّ: يفشل CI إن غُيِّر أحدُهما دون الآخر.

_MANDATED_HEADING_SHAPE = "'## <رقم>. <عنوان>'"


def test_the_prompt_still_mandates_the_shape_the_parsers_accept():
    import inspect
    src = inspect.getsource(writer.deep_report)
    assert _MANDATED_HEADING_SHAPE in src, (
        "صيغةُ العنوان في موجّه الكاتب تغيّرت — حدِّث المحلّلين "
        "(_writer_incomplete/_missing_sections/_section_order_issues/"
        "silk_reports._WRITER_HEADING_NUM_RE) والمطبّع معها، أو عُد للصيغة.")


def test_a_heading_in_the_mandated_shape_is_accepted_by_all_four_parsers():
    from silk_reports import _WRITER_HEADING_NUM_RE, _parse_writer_sections_numbered
    title = writer.report_sections()[0]
    line = "## 1. " + title                       # الصيغةُ المأمورةُ حرفياً
    assert _WRITER_HEADING_NUM_RE.match(line)
    draft = _canonical_draft()
    assert writer._missing_sections(draft) == []
    assert writer._writer_incomplete(draft) == []
    assert writer._section_order_issues(draft) == []
    assert len(_parse_writer_sections_numbered(draft)) == \
        len(writer.report_sections())
    # والمطبّعُ يُعيدها كما هي — لا صيغةَ ثالثة.
    assert writer.canonicalize_section_headings(line) == line


# ── ٥) مراجعةُ §58: المطبِّعُ لا يجعل تقريراً أسوأ — مُقاسٌ لا موعود ────────

def test_a_healthy_report_is_never_touched_even_with_a_bold_section_name_inside():
    """مأخذُ المراجعة الذاتية (خطورةٌ عالية): سطرُ متنٍ غامقٌ نصُّه اسمُ قسم
    كان يُرقَّى عنواناً حقيقياً فيكسر تقريراً **كان يُسلَّم سليماً** — أي أنّ
    العلاجَ يصير سببَ حجبٍ جديد. الحارسُ الأوّل يمنع ذلك بنيوياً."""
    draft = _canonical_draft().replace(
        "## 1. الخلاصة التنفيذية\n" + _BODY,
        "## 1. الخلاصة التنفيذية\n" + _BODY + "\n\n**تقييم المخاطر**\nتفصيل.")
    assert writer._section_order_issues(draft) == []
    fixed = writer.canonicalize_section_headings(draft)
    assert fixed == draft                              # بايتاً ببايت
    assert writer._section_order_issues(fixed) == []   # ولا حجبَ مصنوع


def test_a_bare_section_name_is_not_promoted_when_that_section_already_exists():
    """ازدواجٌ مصنوعٌ من المتن أسوأ من عنوانٍ شاذٍّ واحد."""
    draft = _canonical_draft().replace("## 9. تقييم المخاطر", "# 9) تقييم المخاطر")
    draft += "\n\n**تقييم المخاطر**\nسطر متن غامق.\n"
    fixed = writer.canonicalize_section_headings(draft)
    assert fixed.count("## 9. تقييم المخاطر") == 1
    assert "**تقييم المخاطر**" in fixed


def test_the_normaliser_never_lowers_the_structure_score():
    """عقدُ «لا يجعله أسوأ» على كلّ الأشكال المختبَرة — بالقياس لا بالحصر."""
    shapes = [lambda i, t: f"# {i}. {t}", lambda i, t: f"**{t}**",
              lambda i, t: f"{i}. {t}", lambda i, t: f"### {i} - {t}",
              lambda i, t: f"## {i}. **{t}**"]
    for fmt in shapes:
        draft = _draft_with(fmt)
        before = writer._structure_score(draft)
        after = writer._structure_score(
            writer.canonicalize_section_headings(draft))
        assert after >= before, fmt


def test_a_wrong_ordinal_is_corrected_because_the_client_router_keys_on_it():
    """الرقمُ ليس تجميلاً: `_client_section_for` يوجّه بالرقم، فرقمٌ خاطئٌ
    يُسقِط قسماً مكتوباً ويُبلِّغه «نصّاً نائباً» (حادثةُ qatar_peanut_butter:
    `## 4. التنظيم والوصول للسوق` ورقمُه القانونيّ ٧)."""
    draft = _canonical_draft().replace("## 7. التنظيم والوصول للسوق",
                                       "## 4. التنظيم والوصول للسوق")
    fixed = writer.canonicalize_section_headings(draft)
    assert "## 7. التنظيم والوصول للسوق" in fixed
    assert "## 4. التنظيم والوصول للسوق" not in fixed


def test_bold_wrapped_title_after_the_ordinal_is_recognized():
    draft = "## 1. **الخلاصة التنفيذية**\n" + _BODY
    assert "## 1. الخلاصة التنفيذية" in \
        writer.canonicalize_section_headings(draft)
