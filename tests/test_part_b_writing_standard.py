"""Part B — معيار الكتابة (أمر إصلاح المحرّك) · the writing standard.

الأقفال: (١) ثابت مشترك واحد `WRITING_STANDARD_RULE` يُركَّب في العقدين
التجاري والأكاديمي (والمرآة الإنجليزية في عقديها) — لا نسختين تتباعدان؛
(٢) القواعد العشر حاضرة بإبرها المميزة؛ (٣) فحص `decision_numbers_present`
تحذيري لا مُفشِل (معيار التصعيد الرقمي، الدرس 135).

معايَر على التقرير الذهبي حليب×الأردن + دراسة #12 الحية (شرط المالك).
هرمتي. Run: python3 -m pytest tests/test_part_b_writing_standard.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_style_contract as SC                          # noqa: E402


def test_standard_is_one_shared_constant_in_both_arabic_contracts():
    assert SC.WRITING_STANDARD_RULE in SC.WRITER_STYLE_CONTRACT
    assert SC.WRITING_STANDARD_RULE in SC.ACADEMIC_WRITER_CONTRACT


def test_standard_english_mirror_is_in_both_english_contracts():
    assert SC.WRITING_STANDARD_RULE_EN in SC.WRITER_STYLE_CONTRACT_EN
    assert SC.WRITING_STANDARD_RULE_EN in SC.ACADEMIC_WRITER_CONTRACT_EN


def test_all_ten_rules_present_by_distinctive_needles():
    r = SC.WRITING_STANDARD_RULE
    needles = (
        "قاعدة الطبقتين",                       # 1
        "الخلاصة التنفيذية بقالب ثابت",          # 2
        "السجل المهني",                          # 3
        "تحفظ واحد كحد أقصى",                    # 4
        "يفتتح بإجابة سؤال قراره",               # 5
        "هندسة الجملة",                          # 6
        "ثلاثة أرقام معنوية",                    # 7
        "المعطى الناقص: …",                      # 8 (الحقول الثلاثة)
        "أثره على القرار",                       # 8
        "الإجراء المطلوب",                       # 8
        SC.DECISION_NUMBERS_HEADING,             # 9
        "قبل التسليم راجع",                      # 10
    )
    for n in needles:
        assert n in r, n
    # الافتتاحيات المحظورة مسماة (البند 22 وأخواتها)
    assert "دلالة هذه النتيجة:" in r
    assert "تجدر الإشارة إلى" in r
    # لغة النظام محظورة بمثالها الحي من دراسة #12
    assert "بطاقة منتجك" in r


def test_gate_decision_numbers_check_warns_not_fails():
    import silk_quality_gate as QG
    without = {"deep_research": {
        "report": {"text": "## 10. التوصيات الاستراتيجية\nنص توصيات عادي."},
        "missions": {}}}
    out = QG.run_quality_gate(without)
    hits = [f for f in out["findings"]
            if f["check"] == "decision_numbers_present"]
    assert hits and hits[0]["repairable"] is True
    # تحذيري حتى معيار التصعيد الرقمي (الدرس 135) — ليس عضو إفشال؛ حكم
    # البوابة الكلي قد يفشل من فحوص أخرى على مدونة مصغرة فلا يُقاس عليه.
    assert "decision_numbers_present" not in QG._REGRESSION_GUARD_FIRED
    assert "decision_numbers_present" not in getattr(
        QG, "FAIL_TRIGGER_CHECKS", ())
    with_sec = {"deep_research": {
        "report": {"text": "## 10. التوصيات الاستراتيجية\n"
                           f"### {'أرقام القرار'}\n"
                           "نقطة التعادل = كلفة الدخول ÷ هامش الطن. "
                           "المتاح: الهامش. الناقص: كلفة الدخول."},
        "missions": {}}}
    ok = QG.run_quality_gate(with_sec)
    assert not [f for f in ok["findings"]
                if f["check"] == "decision_numbers_present"]


def test_gate_decision_numbers_check_skips_empty_text():
    import silk_quality_gate as QG
    assert QG._check_decision_numbers_present("") == []


def test_standard_reaches_the_writer_prompt_for_both_styles():
    """العقد المختار (تجاري/أكاديمي) يصل موجّه الكاتب حاملاً المعيار —
    قفل تكامل على سطر الاختيار الحقيقي (§58: الصيغة الأولى كانت صادقة
    دوماً بذيل `or` فلا تقفل شيئاً)."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_ai_judge.py"),
        encoding="utf-8").read()
    flat = " ".join(src.split())
    assert ("ACADEMIC_WRITER_CONTRACT if academic else "
            "WRITER_STYLE_CONTRACT") in flat
    assert ("ACADEMIC_WRITER_CONTRACT_EN if academic else "
            "WRITER_STYLE_CONTRACT_EN") in flat
