"""البندان 9 و10 من أمر إصلاح المحرّك.

البند 9 (تقرير #11): «مصدر يشير إلى دسم فوق 1% وآخر إلى 6%–10%» — تعارضُ
تعريفٍ مُرِّر خاماً للقارئ والثاني يصف 040140 لا 040120؛ المطلوب مرجعُ
تعريفاتٍ داخلي يحسم بدل العرض.
البند 10 (تقرير #10): العنوان «لا تدخل» ونفس الصفحة «أفضل باب دخول:
SADAFCO» — تسمية الحكم يجب أن تطابق محتواه (قفل دائم). هرمتي. Run:
  python3 -m pytest tests/test_goal9_10_hs_reference_and_label.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_hs_reference as HR                           # noqa: E402
import silk_quality_gate as QG                           # noqa: E402


# ── البند 9: المرجع الداخلي ────────────────────────────────────────────────

def test_reference_settles_the_exact_conflict_of_report_11():
    """040120 = دسم >1% حتى 6% — الرواية «6%–10%» تخص 040140 حصراً."""
    assert "> 1% وحتى 6%" in HR.definition("040120")
    assert "> 6% وحتى 10%" in HR.definition("040140")
    assert "≤ 1%" in HR.definition("040110")


def test_heading_fallback_and_unknown_codes():
    assert "مركّز" in HR.definition("040210")     # سداسي غائب ⇒ بند 0402
    assert HR.definition("999999") is None        # خارج المرجع = غياب معلن
    assert HR.definition("") is None


def test_definition_line_carries_code_and_source():
    line = HR.definition_line("040120")
    assert line.startswith("HS 040120:")
    assert "WCO HS 2022" in line


def test_writer_prompt_injects_the_settling_rule():
    """موجّه الكاتب يحمل قاعدة الحسم — لا عرض تعارض تعريفي للقارئ."""
    import inspect
    import silk_ai_judge as J
    src = inspect.getsource(J)
    assert "التعريف المرجعي الحاسم للبند" in src
    assert "بلا عرض التعارض" in src


# ── البند 10: التسمية تطابق المحتوى ────────────────────────────────────────

def _view(tone, text):
    return {"deep_research": {"missions": {}, "verdict_tone": tone,
                              "report": {"text": text}}, "markets": []}


def test_nogo_label_over_a_named_entry_route_fails():
    """قبول الأمر حرفياً: «لا تدخل» + «أفضل باب دخول: …» = فشل بناء."""
    out = QG.run_quality_gate(_view(
        "nogo", "الحكم عدم الدخول.\nأفضل باب دخول: SADAFCO عبر موزع محلي."))
    hits = [f for f in out["findings"]
            if f["check"] == "verdict_label_matches_content"]
    assert hits and out["verdict"] == QG.FAIL


def test_hypothetical_flip_condition_is_legitimate():
    body = ("الحكم عدم الدخول. لو اكتملت بيانات الترخيص لكان أفضل باب "
            "دخول هو الموزع المدرج في القائمة الذهبية.")
    assert QG._check_verdict_label_matches_content(_view("nogo", body)) == []


def test_non_nogo_labels_are_out_of_scope():
    body = "أفضل باب دخول: موزع مدرج في القائمة الذهبية."
    for tone in ("go", "conditional", "watch", ""):
        assert QG._check_verdict_label_matches_content(_view(tone, body)) == []


def test_check_is_a_fail_trigger():
    assert "verdict_label_matches_content" in QG._REGRESSION_GUARD_FIRED
