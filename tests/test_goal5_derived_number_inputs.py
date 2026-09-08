"""البند 5 من أمر إصلاح المحرّك — لا رقم مشتق من مدخلات غير مرصودة.

الدليل (direct reproduction — تقرير #11): «أقصى سعر مصنع = $0.3274/كجم»
بأربع منازل بينما جدول الأسعار في القسم نفسه ثلاثة صفوف كلها «يتعذّر
الحساب»/«غير مرصود» — رقم غير قابل للتدقيق. الجذر: الحل العكسي كان يستهلك
سعرَ عبوةٍ (per_unit) مجهولةَ الحجم بعملةٍ غير محوَّلة ويخرج رقماً عارياً
يزيّنه الكاتب «$…/كجم». هرمتي. Run:
  python3 -m pytest tests/test_goal5_derived_number_inputs.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_economics as E                               # noqa: E402
import silk_quality_gate as QG                           # noqa: E402


def _dr_prices(*notes_vals):
    return {"missions": {"pricing_scout": {"findings": [
        {"value": v, "note": n} for v, n in notes_vals]}}}


def test_pack_size_unobserved_suspends_reverse_and_names_the_missing_input():
    """سعر رف بعملة معروفة لكن بلا حجم عبوة ⇒ لا per_kg ⇒ الحل معلّق
    باسم الناقص حرفياً — لا رقم من عبوة مجهولة الحجم (حالة تقرير #11)."""
    eco = E.economics_view(_dr_prices((4.50, "سعر رف في متجر — 4.50 دينار")))
    assert eco["anchor_price"] is not None
    assert eco["reverse_solve"] is None
    gap = [g for g in eco["gaps"] if "غير محسوب" in g and "الناقص" in g]
    assert gap and "حجم العبوة" in gap[0]


def test_currency_unobserved_suspends_reverse_and_names_it():
    eco = E.economics_view(
        _dr_prices((7.49, "سعر رف عبوة 1 كجم في متجر محلي")))
    assert eco["reverse_solve"] is None
    gap = [g for g in eco["gaps"] if "الناقص" in g]
    assert gap and "عملة" in gap[0]


def test_observed_basis_and_currency_compute_with_declared_unit():
    """أساسٌ (كجم) وعملةٌ مرصودان ⇒ الحل يعمل ويحمل وحدته وعملته —
    فلا يستطيع أي عارض تزيينه «$/كجم» اختلاقاً."""
    eco = E.economics_view(
        _dr_prices((7.49, "سعر رف عبوة 1 كجم بسعر 7.49 دينار في متجر")))
    rs = eco["reverse_solve"]
    assert rs and rs["max_exw"] > 0
    assert rs["unit"] == "كجم" and "دينار" in rs["currency"]
    # الأساس per_kg لا per_unit — الجبر على السعر المطبَّع للكيلوغرام
    assert rs["shelf_price"] == eco["anchor_price"]["per_kg"]


def test_litre_basis_is_declared_as_litre():
    """هدف الدراسة الاحترافية (البند ١): وحدة العرض وحدةُ السوق — الحليب
    باللتر لا بالكيلوغرام (كان الفحص يقفل تفضيل كجم القديم؛ حُدِّث عمداً
    مع الموجة، والاسم أصلاً «يُعلَن باللتر»). التحويل لتر↔كجم يبقى محسوباً
    داخلياً (المقارنة الحدودية في `test_goal_units_wave1`)."""
    eco = E.economics_view(
        _dr_prices((6.2, "سعر رف 1 لتر € متجر محلي")), category="milk")
    rs = eco["reverse_solve"]
    assert rs and rs["unit"] == "لتر"      # وحدة السوق للحليب
    assert rs["currency"] == "€"
    assert rs["shelf_price"] == eco["anchor_price"]["per_litre"]


def test_gate_fails_a_numeric_exw_while_reverse_is_suspended():
    view = {"deep_research": {
        "missions": {},
        "economics": {"reverse_solve": None,
                      "gaps": ["أقصى سعر مصنع (EXW) غير محسوب — الناقص: "
                               "حجم العبوة"]},
        "report": {"text": ("## 6. المشهد التنافسي\n"
                            "يبلغ أقصى سعر مصنع قابل للمنافسة 0.3274 "
                            "دولار/كجم وفق النموذج.")}},
        "markets": []}
    out = QG.run_quality_gate(view)
    hits = [f for f in out["findings"]
            if f["check"] == "derived_number_has_inputs"]
    assert hits and out["verdict"] == QG.FAIL
    assert "غير محسوب" in hits[0]["note"]


def test_gate_accepts_the_declared_not_computed_line():
    """سطر البديل المشروع «غير محسوب — الناقص: …» لا يفشل البوابة."""
    view = {"deep_research": {
        "missions": {}, "economics": {"reverse_solve": None, "gaps": []},
        "report": {"text": ("أقصى سعر مصنع قابل للمنافسة: غير محسوب — "
                            "الناقص: حجم العبوة (3 صفوف بلا حجم).")}},
        "markets": []}
    assert QG._check_derived_number_has_inputs(view) == []


def test_gate_silent_when_reverse_solve_is_computed():
    view = {"deep_research": {
        "missions": {},
        "economics": {"reverse_solve": {"max_exw": 3.2, "unit": "كجم",
                                        "currency": "دينار"}},
        "report": {"text": "أقصى سعر مصنع قابل للمنافسة 3.2 دينار/كجم."}},
        "markets": []}
    assert QG._check_derived_number_has_inputs(view) == []


def test_check_is_a_fail_trigger():
    assert "derived_number_has_inputs" in QG._REGRESSION_GUARD_FIRED


def test_writer_prompt_carries_unit_and_currency_or_the_ban():
    """موجّه الكاتب: مع الحل ⇒ الرقم بعملته/وحدته وحظر تحويلٍ ذاتيّ؛
    بدونه ⇒ حظرُ طبع أي رقم مشتق وسطرُ «غير محسوب» الحرفي."""
    import inspect
    import silk_ai_judge as J
    src = inspect.getsource(J)
    assert "لا تحوّل العملة ولا" in src
    assert "لا تطبع أي رقم لأقصى سعر مصنع" in src
