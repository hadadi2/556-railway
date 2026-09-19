"""قفل الدرس ٢٦٤ — كتابة تُقرأ كأنّ محلّلاً كتبها.

بلاغ المالك (2026-09-19): «لا تكرار للجمل القالبية، ولا تكرار للمعلومة في
أكثر من موضع… ادمج النواقص المتشابهة في جدول واحد بدل سردها بالصياغة نفسها».

القياسُ قبل العمل (تُعاد ثمرتُه هنا حارساً): صفرُ جملةٍ تتكرّر حرفياً داخل
التقرير الواحد عبر المدوّنات الستّ عشرة — فالقفلُ يمنع الانحدار لا يدّعي
إصلاحاً لم يقع. والنواقصُ كانت تُسرَد ٧٫٥ سطرٍ في المتوسط عبر ٣–٥ أقسام.

هرمتي: صفر شبكة، صفر مفتاح، صفر إنفاق.
Run: python3 -m pytest tests/test_human_writing.py -q
"""
import collections
import importlib
import pathlib
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import silk_fact_ledger as L                                  # noqa: E402
import silk_render as R                                       # noqa: E402
import silk_reports as SR                                     # noqa: E402
from gen_verdict_baseline import CANONICAL_BLOBS              # noqa: E402


def _keys():
    return sorted(CANONICAL_BLOBS)


def _view(key):
    mod, fn = CANONICAL_BLOBS[key]
    return R.build_view(getattr(importlib.import_module(mod), fn)())


def _sentences(text, min_words=8):
    return [s.strip() for s in re.split(r"(?<=[.؛!؟\n])", text)
            if len(s.split()) >= min_words]


# ── ١) لا جملةَ تتكرّر حرفياً داخل التقرير الواحد ──────────────────────────

@pytest.mark.parametrize("key", _keys())
def test_no_long_sentence_repeats_inside_one_report(key):
    md = SR.render_markdown(_view(key))
    counts = collections.Counter(_sentences(md))
    repeats = {s[:70]: n for s, n in counts.items() if n > 1}
    assert not repeats, repeats


# ── ٢) جدولُ النواقص الواحد يحلّ محلّ السرد المكرّر ───────────────────────

@pytest.mark.parametrize("key", _keys())
def test_the_limits_section_is_one_table_not_a_repeated_list(key):
    md = SR.render_markdown(_view(key))
    assert "## حدود هذا التقرير" in md
    seg = md.split("## حدود هذا التقرير", 1)[1].split("\n## ", 1)[0]
    if "| المعطى |" in seg:
        assert "| الحالة |" in seg and "| ما يلزم لإغلاقه |" in seg
    else:
        # بلا نقصٍ مرصود: سطرٌ واحدٌ صادق، لا جدولٌ فارغ.
        assert len([l for l in seg.strip().split("\n") if l.strip()]) == 1


def test_the_table_separates_missing_from_weakly_documented():
    """الفرقُ الذي طلبه المالك: «ناقص» ≠ «مرصود لكن ضعيف التوثيق»."""
    view = {"ledger": {"gaps": [
        {"label_ar": "الحصة السعودية", "label_en": "Saudi share",
         "status": L.WEAK, "note": "مصدرٌ واحدٌ غير رسمي"},
        {"label_ar": "دخل الفرد", "label_en": "GDP per capita",
         "status": L.MISSING, "note": "لم يُرصد"}]}}
    rows = L.gaps_table(view)
    assert [r["status"] for r in rows] == ["مرصود بتوثيق ضعيف"]


def test_a_consequence_is_not_dressed_up_as_a_closure_path():
    """«اعتُمدت 0% في الحل العكسي» نتيجةٌ لا إجراء — عمودُ «ما يلزم» يبقى
    فارغاً بدل أن يكذب على القارئ."""
    what, how = L._split_gap(
        "التعرفة غير متاحة — اعتُمدت 0% معلنةً في الحل العكسي")
    assert how == "" and what.startswith("التعرفة غير متاحة")


def test_an_actionable_tail_becomes_the_closure_path():
    what, how = L._split_gap(
        "تكلفة المصنع (EXW) غير مدخلة — أدخل سعر المصنع للكيلوغرام")
    assert what == "تكلفة المصنع (EXW) غير مدخلة"
    assert how.startswith("أدخل سعر المصنع")


def test_a_requires_phrase_is_a_closure_path_even_behind_one_word():
    """«إغلاقها يتطلّب بحثاً ميدانياً» سبيلُ إغلاقٍ حقيقيّ — مطابقةُ الصدرِ
    وحدَها كانت تتركه في عمود المعطى فيُقرأ الصفُّ بلا مخرج (مراجعة §58)."""
    what, how = L._split_gap(
        "الموسمية غير متاحة من مؤشرات البحث — إغلاقها يتطلّب بحثاً ميدانياً")
    assert what == "الموسمية غير متاحة من مؤشرات البحث"
    assert how.startswith("إغلاقها يتطلّب")


def test_an_explanation_after_a_colon_never_becomes_a_closure_path():
    """المراجعةُ الذاتية: شرحُ «بيانات فئة مجاورة» كان يحطّ في خانة «ما يلزم
    لإغلاقه» — فيقرأ العميلُ شرحاً على أنه إجراء."""
    what, how = L._split_gap(
        "بيانات فئة مجاورة — مؤشر سياقي لا مقياس فعلي: رمز HS 040510 لا "
        "يشمل صفة المنتج المميّزة")
    assert how == ""
    assert "رمز HS 040510" in what


def test_clipping_keeps_the_longest_clause_that_fits_not_the_first():
    """«أ؛ ب؛ ج» كانت تعود «أ» ولو وسع الحدُّ مقطعين — إسقاطٌ صامت."""
    out = L.clip_clause("مقطع أول؛ مقطع ثان؛ مقطع ثالث طويل جداً يتجاوز", 26)
    assert out.startswith("مقطع أول؛ مقطع ثان")
    assert "مقطع ثالث" not in out


def test_no_clipped_cell_ever_ends_mid_phrase_without_saying_so():
    """كِسْرٌ مُعلَّق («… لاستكمال أحد») يكذب على القارئ بصمت؛ علامةُ القصّ
    تقول إنّ ثمّة بقيّة."""
    long_text = "أدخل سعر المصنع للكيلوغرام لاستكمال أحد مدخلات سلسلة التكلفة"
    out = L.clip_clause(long_text, 30)
    assert out.endswith("…") and len(out) <= 31
    assert L.clip_clause("نصٌّ قصير", 30) == "نصٌّ قصير"      # لا قصَّ بلا داعٍ


@pytest.mark.parametrize("key", _keys())
def test_whatever_the_table_shortened_is_printed_in_full_beneath_it(key):
    """الجدولُ فهرسٌ لا مقصلة: كلُّ صفٍّ اختُصر يظهر نصُّه كاملاً تحته."""
    view = _view(key)
    rows = L.gaps_table(view)
    md = SR.render_markdown(view)
    flat = " ".join(md.split())
    for r in SR._gaps_detail_rows(rows[:12], ""):
        # ما لا يُقال إلا هنا يُطبَع كاملاً؛ وما قيل في قسمٍ آخر لا يُعاد.
        probe = " ".join(r["full"].split())[:60]
        assert probe in flat, probe


def test_a_gap_already_explained_elsewhere_is_not_repeated_under_the_table():
    """«لا تكرار للمعلومة في أكثر من موضع» (بلاغ المالك): سطرٌ يشرحه قسمُ
    الاقتصاد بنصّه كان يُعاد حرفياً تحت الجدول (قِيس على مدوّنة الأردن)."""
    row = {"clipped": True, "full": "الأسعار المرصودة ليست أسعار رفّ"}
    assert SR._gaps_detail_rows([row], "") == [row]
    assert SR._gaps_detail_rows(
        [row], "… الأسعار المرصودة ليست أسعار رفّ للمستهلك …") == []


def test_the_status_column_is_last_because_the_pdf_measured_it():
    """ترتيبُ الأعمدة هندسةٌ مقيسة: العمودُ الأيسر في جدولٍ عربيّ يلتفّ من
    هامش اليسار فيطابق إمضاءَ انقلاب jc — فالحالةُ (مفرداتٌ قصيرة) آخِراً."""
    view = _view("kuwait_peanut_butter")
    head = SR._gaps_table_md(view)[0]
    assert head.strip().endswith("| الحالة |")
    assert head.index("المعطى") < head.index("ما يلزم لإغلاقه")


def test_the_same_rows_feed_markdown_and_word():
    """مصدرٌ واحد للجدول في السطحين — لا نسختان تتباعدان."""
    import inspect
    assert "_FL.gaps_table" in inspect.getsource(SR._gaps_table_md)
    assert "_FL.gaps_table" in inspect.getsource(SR._docx_gaps_table)


# ── ٣) الصياغاتُ القالبية أُعيدت مرّةً واحدة بلغة محلّل ───────────────────

@pytest.mark.parametrize("key", _keys())
def test_the_dashboard_reads_the_same_rows_the_document_prints(key):
    """قانونُ العرض الواحد: الواجهةُ لا تعيد اشتقاقَ النواقص — الصفوفُ
    نفسُها تُرفَع في العرض فتقرأها الثلاثةُ (md، Word، اللوحة)."""
    view = _view(key)
    assert (view["ledger"]["gaps_table"] ==
            L.gaps_table(view, view.get("report_language") or "ar"))


def test_the_dashboard_renders_that_table_not_its_own_list():
    html = (pathlib.Path(_ROOT) / "web" / "index.html").read_text(
        encoding="utf-8")
    assert "gaps_table" in html
    assert "ما يلزم لإغلاقه" in html


def test_the_deterministic_summary_lost_its_robotic_openers():
    """يُقاس **النصُّ الخارج** لا الشيفرة: تعليقٌ يشرح ما استُبدِل يحمل
    العبارةَ القديمة بطبيعته، فقياسُ المصدر يُفشِل إصلاحاً واقعاً."""
    import silk_narrative as N
    view = _view("morocco_juice")
    out = " ".join(N.exec_summary(view))
    assert "الأساس التجاري:" not in out
    assert "لاكتمال الثقة في هذه التوصية يلزم:" not in out


def test_the_insufficiency_line_reads_as_a_sentence_not_a_verdict():
    line = R.insufficient_line("المنافسون", {"contributed": 0, "threshold": 2,
                                             "sources_attempted": []})
    assert not line.startswith("بيانات غير كافية")
    assert line.startswith("لم يكتمل قسم «المنافسون»")


def test_the_insufficiency_line_agrees_in_number_and_gender():
    """المعدودُ مؤنّث: «رُصدت 0 حقيقة» و«من 2 يحتاجها» كسرٌ للعدد والمعدود
    كان القفلُ الأولُ يثبّته حين طالب بظهور الرقمين (مراجعةٌ ذاتية §58)."""
    def line(got, need, srcs=()):
        return R.insufficient_line("الأسعار", {
            "contributed": got, "threshold": need,
            "sources_attempted": list(srcs)})
    assert "لم تُرصد أي حقيقة سوقية" in line(0, 2)
    assert "يحتاج حقيقتين" in line(0, 2)
    assert "يحتاج حقيقة واحدة" in line(0, 1)
    assert "يحتاج ثلاث حقائق" in line(0, 3)
    assert "رُصدت واحدة من الحقائق السوقية" in line(1, 3)
    assert "رُصدت اثنتان من الحقائق السوقية" in line(2, 5)
    assert not any(ch.isdigit() for ch in line(0, 2))


def test_the_insufficiency_line_never_claims_an_attempt_that_did_not_happen():
    """«بعد محاولة هذه المصادر: لا مصادر مُحاوَلة» جملةٌ تناقض نفسَها."""
    assert R.insufficient_line("الأسعار", {
        "contributed": 0, "threshold": 1,
        "sources_attempted": []}).endswith("ولم تُحاوَل أي مصادر")
    assert "بعد محاولة: World Bank" in R.insufficient_line("الأسعار", {
        "contributed": 0, "threshold": 1,
        "sources_attempted": ["World Bank"]})


def test_the_summary_never_calls_a_market_complete_when_sections_are_short():
    """سوقٌ بلا بيانات كان يُقال فيه «مكوّنات التقييم مكتملة» بعد سطرين من
    «لم يُرصد ما يكفي» — فجوةٌ تُقدَّم مُغلَقة (مراجعةٌ ذاتية §58)."""
    import silk_narrative as N
    view = R.build_view({"markets": [{"country": "China", "iso3": "CHN",
                                      "components": {}}]})
    out = " ".join(N.exec_summary(view))
    assert "مكوّنات التقييم الرئيسية لهذا السوق مكتملة" not in out


def test_the_summary_does_not_list_failed_fetches_as_supporting_evidence():
    """«ما يسند هذه القراءة» ادّعاءُ إسناد — وسطرُ «تعذّر الجلب» نقيضُه."""
    import silk_narrative as N
    market = {"country": "China", "iso3": "CHN", "components": {},
              "components_detail": [
                  {"name": "market_size", "status": "fetch_failed"},
                  {"name": "saudi_position", "value": 3.5,
                   "source": "UN Comtrade"}]}
    out = " ".join(N.exec_summary({"markets": [market], "decision": {}}))
    support = out.split("ولم يُرصد بعد:")[0]
    assert "تعذّر الجلب" not in support
    assert "ولم يُرصد بعد:" in out


def test_the_summary_does_not_double_its_punctuation():
    """بندٌ ينتهي بنقطةٍ كان يُنتِج «.؛» و«..» عند الوصل."""
    import silk_narrative as N
    out = " ".join(N.exec_summary(
        {"markets": [{"country": "China", "iso3": "CHN"}],
         "limits": ["حد أول.", "حد ثانٍ."], "decision": {}}))
    assert ".؛" not in out and ".." not in out
