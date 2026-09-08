"""اتساق العقد المركب + تكافؤ التغطية الإنجليزية — أقفال موجة سدّ
الفجوات الثانية (تدقيق «find all gaps» — وكيل قراءة file:line).

الحادثة: ستة عشر تناقضاً حقيقياً في الموجّه المركب (أوامر متضادة لنفس
الكاتب: عبارة تُفرض حرفياً وتُحظر كلغة نظام؛ افتتاحية تُفرض بالإنجليزية
وتُحظر بالعربية؛ أربعة حدود مختلفة لطول الجملة…)، وأربعة فحوص FAIL
عربية المِجَسّ خامدة على الإنجليزية خارج نظر قفل التكافؤ لأنها تأخذ
المتن معاملاً. هرمتي. Run: pytest tests/test_contract_coherence.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name: str) -> str:
    with open(os.path.join(_ROOT, name), encoding="utf-8") as fh:
        return fh.read()


# ── التناقضات المحسومة في الموجّه ────────────────────────────────────


def test_no_system_input_phrase_is_mandated_anywhere():
    """«بطاقة منتجك» كانت محظورة في المعيار ومفروضة حرفياً في تعليمتين —
    زالت من الموجّه كلياً (يُطلب المعطى نفسه: سعر المصنع للكيلوغرام)."""
    assert "بطاقة منتجك" not in _src("silk_ai_judge.py")


def test_no_forbidden_absence_term_is_mandated():
    """«صفّ بفجوة معلنة» كانت تعليمة قسم ٦ بينما البوابة تحظر العبارة."""
    src = _src("silk_ai_judge.py")
    assert "صفّ بفجوة معلنة" not in src
    assert "بمفردتيه القانونيتين" in src


def test_single_sentence_cap_everywhere():
    """أربعة حدود لطول الجملة صارت حداً واحداً: متوسط ≤25، سقف 35 —
    بالعربية والإنجليزية معاً (دورة C4: المرايا الإنجليزية كانت فاتت)."""
    contract = _src("silk_style_contract.py")
    assert "تتجاوز خمساً وعشرين كلمة تُقسَم" not in contract
    assert "جمل كاملة 15–28" not in contract
    assert "15–28-word sentences" not in contract
    assert "it is observed that" not in contract
    judge = _src("silk_ai_judge.py")
    assert "٢٥ كلمة وسطياً كحدّ أعلى؛ الجملة التي تتجاوز ذلك تُقسَم" \
        not in judge


def test_academic_closer_item22_applies_to_english_too():
    """البند 22 كان مطبقاً على الثابت العربي وحده — العقد الإنجليزي كان
    **يفرض** الافتتاحية التي يحظرها موجّه السجل نفسه."""
    import silk_style_contract as SC
    en = SC.ACADEMIC_WRITER_CONTRACT_EN
    assert f'beginning "**{SC.ACADEMIC_SECTION_CLOSER_EN}**"' not in en
    assert "without the boilerplate opener" in en


def test_reviewer_no_longer_blocks_on_the_reversed_b2_rule():
    """المراجع كان يحجب على غياب شرح مقوّس أبطله قرار المالك 2026-08-19
    — صار يحجب على الاختصار العاري بدل معناه، ولا يطلب قوساً."""
    src = _src("silk_ai_judge.py")
    assert "بلا شرح عربي بين قوسين عند أول ورود" not in src
    assert "اختصار استشاري عارٍ" in src


def test_bare_abbreviation_permission_is_gone():
    """سطر السماح («مختصرات استشارية معترف بها دولياً») كان ينقض عقد
    اللغة — صار يوجب المعنى العربي، والمثال التوضيحي بلا (HHI ≈ …)."""
    src = _src("silk_ai_judge.py")
    assert "فاكتب معناها العربي" in src
    assert "(HHI ≈ 2350)" not in src


def test_executive_summary_single_spec():
    """صفحة واحدة، بلا أسماء مصادر — كان: صفحتان في 6.2 وصفحة في تعليمة
    الخلاصة و«بأرقامها المستشهَد بها» ضد «بلا مصادر»."""
    src = _src("silk_ai_judge.py")
    assert "صفحتين كحدّ أقصى" not in src
    assert "بأرقامها المستشهَد بها" not in src
    assert src.count("بلا أسماء مصادر داخل الخلاصة") >= 2


def test_decision_numbers_subsection_is_placed_by_the_prompt():
    """«أرقام القرار» كان يفرضه المعيار ولا تضعه أي تعليمة قسمية."""
    src = _src("silk_ai_judge.py")
    assert "'### أرقام القرار'" in src
    assert "'### Decision numbers'" in src


# ── التغطية الإنجليزية للفحوص ────────────────────────────────────────


def test_english_mirrors_exist_in_the_needle_tuples():
    import silk_quality_gate as QG
    assert "if " in QG._HYPOTHETICAL_TOKENS
    assert "not calculated" in QG._GAP_SENTENCE_TOKENS
    assert "automatically below this section" in QG._SYSTEM_LANGUAGE_NEEDLES
    assert "(," in QG._EMPTY_CITATION_NEEDLES
    assert "not observed" in QG._ABSENCE_FORBIDDEN
    assert "مؤشرا سياقيا" in QG._CAVEAT_NEEDLES     # صيغة النصب المطبَّعة


def test_english_false_positives_are_gone():
    """شرطية إنجليزية مشروعة وجملة فجوة إنجليزية كانتا تُفشِلان تقريراً
    صحيحاً (فحصان FAIL) — direct reproduction من التدقيق."""
    import silk_quality_gate as QG
    assert QG._check_verdict_label_matches_content(
        {"deep_research": {"report": {"text":
            "If the data were complete the best entry route would be a "
            "specialist distributor."}, "verdict_tone": "nogo"}}) == []
    assert QG._check_derived_number_has_inputs(
        {"deep_research": {"report": {"text":
            "Maximum ex-works price is not calculated - missing the 2024 "
            "shelf anchor."}, "economics": {"reverse_solve": None}}}) == []


def test_english_silent_checks_now_fire():
    """لغة نظام إنجليزية، فاصلة لاتينية يتيمة، جدول إنجليزي ميت، مفردات
    غياب إنجليزية — كلها كانت غير مرئية (PASS بلا قياس)."""
    import silk_quality_gate as QG
    assert QG._check_system_language_leak(
        "The appendix follows automatically below this section.")
    assert QG._check_empty_citation("Source: (, World Bank 2025)")
    assert QG._check_dead_table(
        "| Level | Value | Method | Assumption |\n|---|---|---|---|\n"
        "| TAM | not calculated | unknown | TBD |\n"
        "| SAM | not stated | unknown | not calculated |\n"
        "| SOM | TBD | not calculated | unknown |")
    assert QG._check_absence_vocabulary(
        "The margin was not observed and remains a declared gap.")
    assert QG._MSHORT_STYLE_RE.search("reached 4.2m$ last year")


def test_sentence_length_is_not_neutralised_by_decimals():
    """«41.25» كانت تقسم الجملة فتحيّد الفحص في نثر رقمي كثيف."""
    import silk_quality_gate as QG
    long_one = ("the market grew by 41.25 percent " + "word " * 40).strip() + ". "
    assert QG._check_sentence_length(long_one * 6)


def test_parity_lock_sees_text_parameter_checks():
    """قفل التكافؤ كان يعفي كل فحص يأخذ المتن معاملاً — الكاشف يشمل
    `def _check_x(text)` الآن (المصدر يشهد)."""
    src = _src("tests/test_gate_language_parity.py")
    assert "takes_text_param" in src
