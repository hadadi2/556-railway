"""هدف الدراسة الاحترافية — الموجة ٤: الملخص التنفيذي حامل القرار (البند ٤).

القاعدة: كل دراسة تفتتح بملخص مستقل قبل المتن — التوصية أولاً، ثم رقمان أو
ثلاثة يتبع كلاً منها معناه، ثم المسار العملي، ثم الشرط الحاجب — تحت 150 كلمة
بلا مصادر ولا مفردة داخلية، ويصمد وحده. الوجود والافتتاح بالتوصية حاجزان
حتميان؛ القيود الأسلوبية تحذيرية (درس 135).
"""
import inspect
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from conftest import block_network, docx_all_text

_REPORT = """## 1. الخلاصة التنفيذية
{summary}

## 2. منهجية البحث ونطاقه
نص المنهجية.

## 3. نظرة عامة على السوق وحجمه
نص السوق.
"""

_GOOD = ("**التوصية: تأجيل الدخول بالحليب السائل إلى السوق الأردني.**\n"
         "استورد السوق 6.95 مليون دولار سنة 2023 — أي أن الحجم المتاح "
         "لمورد جديد لا يغطي كلفة قناة توزيع. الطريق المجدي مستورد مدرج "
         "في القائمة الذهبية. قبل أي التزام: وثّق قيود ترخيص المجفف.")


# ── الحاجز: الافتتاح بالتوصية ─────────────────────────────────────────────

def test_recommendation_first_passes_on_the_template_shape():
    from silk_quality_gate import _check_exec_summary_recommendation_first
    assert _check_exec_summary_recommendation_first(
        _REPORT.format(summary=_GOOD)) == []
    # صيغة «توصي الدراسة» المسموحة في السجل المهني تمرّ أيضاً.
    alt = _REPORT.format(summary="توصي الدراسة بتأجيل الدخول.\nتفصيل.")
    assert _check_exec_summary_recommendation_first(alt) == []


def test_recommendation_buried_after_long_opening_fails():
    """عيب الدراسات المؤسِّس: جملة افتتاح 45 كلمة تدفن الحكم."""
    from silk_quality_gate import _check_exec_summary_recommendation_first
    buried = _REPORT.format(summary=(
        "شهد السوق الأردني للحليب السائل خلال السنوات الثلاث الماضية "
        "تحولات عميقة في بنية الاستيراد والتوزيع معاً.\n"
        "التوصية: تأجيل الدخول."))
    found = _check_exec_summary_recommendation_first(buried)
    assert found and found[0]["check"] == "exec_summary_recommendation_first"
    assert found[0]["repairable"] is True     # تحذيري (نص الهدف + درس 135)


def test_recommendation_first_is_warning_tier_and_silent_without_section():
    """نص الهدف يطلب الحجب للوجود/السقف/المفردات؛ الافتتاح بالتوصية تحذيري
    (فحص أول تشغيلة أظهر إطلاقه على نصوص مشروعة مخزنة — درس 135)."""
    from silk_quality_gate import (FAIL_TRIGGER_CHECKS,
                                   _check_exec_summary_recommendation_first)
    assert "exec_summary_recommendation_first" not in FAIL_TRIGGER_CHECKS
    # لا قسم ١ أصلاً — فحص البنية القائم يغطيه، لا ازدواج إطلاق.
    assert _check_exec_summary_recommendation_first("## 3. السوق\nنص") == []


# ── التحذيري: القيود ───────────────────────────────────────────────────────

def test_constraints_silent_on_the_target_shape():
    from silk_quality_gate import _check_exec_summary_constraints
    assert _check_exec_summary_constraints(_REPORT.format(summary=_GOOD)) == []


def test_constraints_fire_on_words_sources_and_vocab():
    from silk_quality_gate import _check_exec_summary_constraints
    long_sum = "التوصية: تأجيل. " + "كلمة " * 160
    src_sum = "التوصية: تأجيل. وفق UN Comtrade بلغت الواردات 6.95 مليون."
    voc_sum = "التوصية: تأجيل. مؤشر تركّز HHI بلغ 9040."
    for s, needle in ((long_sum, "كلمة"), (src_sum, "Comtrade"),
                      (voc_sum, "HHI")):
        found = _check_exec_summary_constraints(_REPORT.format(summary=s))
        assert found, s[:40]
        assert all(f["repairable"] is True for f in found)
    from silk_quality_gate import FAIL_TRIGGER_CHECKS
    assert "exec_summary_constraints" not in FAIL_TRIGGER_CHECKS


# ── docx العميل: الملخص قسم مستقل يفتتح المستند ───────────────────────────

def _client_view(report_text: str) -> dict:
    return {"product": "تمور", "hs_code": "080410", "year": 2024,
            "report_language": "ar", "markets": [], "test_run": True,
            "deep_research": {
                "product": "تمور",
                "market": {"iso3": "NLD", "name_ar": "هولندا",
                           "name_en": "Netherlands"},
                "verdict": {"verdict": "WATCH", "confidence": 0.6},
                "verdict_label": "مراقبة السوق",
                "report": {"text": report_text},
                "missions": {}, "limits": [], "gap_register": [],
                "economics": {"gaps": []}}}


def test_client_docx_opens_with_a_standalone_summary_section():
    pytest.importorskip("docx")
    from silk_reports import render_client_docx
    view = _client_view(_REPORT.format(summary=_GOOD))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "c.docx")
        with block_network():
            render_client_docx(view, path)
        text = docx_all_text(path)
    lines = [ln for ln in text.split("\n") if ln.strip()]
    assert "الملخص التنفيذي" in lines
    # الملخص قبل «القرار وأساسه» — يفتتح المستند لا يُذاب فيه.
    assert lines.index("الملخص التنفيذي") < lines.index("القرار وأساسه")
    assert "تأجيل الدخول بالحليب السائل" in text


def test_no_orphan_summary_heading_without_narrative():
    """بلا سرد كاتب: لا عنوان ملخص يتيماً — سطر تعذّر السرد يغطي."""
    pytest.importorskip("docx")
    from silk_reports import render_client_docx
    view = _client_view("")
    view["deep_research"]["report"] = {"text": ""}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "c.docx")
        with block_network():
            render_client_docx(view, path)
        text = docx_all_text(path)
    assert "الملخص التنفيذي" not in text


# ── الموجّه: القالب والحدود في المصدرين (الدرس 176) ───────────────────────

def test_writer_prompt_carries_the_150_word_template():
    import silk_ai_judge
    from silk_style_contract import WRITING_STANDARD_RULE
    src = inspect.getsource(silk_ai_judge.deep_report)
    assert src.count("تحت 150 كلمة") >= 2          # تعليمتا 6.2 والقسم ١
    assert "تحت 150 كلمة" in WRITING_STANDARD_RULE  # Part B
    assert "يتبع كلَّ رقمٍ **معناه** لا مصدره" in WRITING_STANDARD_RULE \
        or "يتبع كلَّ رقمٍ معناه" in WRITING_STANDARD_RULE
