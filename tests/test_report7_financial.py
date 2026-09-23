"""تقرير سِلك ٧ — النموذج المالي (§3.5، الدرس ٢٧٦).

financial-model wave: «entry cost ÷ unit margin» is the trial shipment's cash
recovery, not an operating break-even — the two are separate items with their
own names; the operating break-even is relevant fixed costs ÷ unit
contribution margin (EXW), a declared gap when fixed costs are not entered;
and container capacity is stated as a logistics limit, not order size.

كلُّ الحالات مصطنعةٌ لاختبارٍ هرمتيّ.
"""
import pytest

import silk_economics as E

_REV = {"max_exw": 3.5, "unit": "لتر", "currency": "USD"}


def _by(**kw):
    dn = E.build_decision_numbers(category="حليب", **kw)
    return {e["name"]: e for e in dn}


def test_cash_recovery_and_operating_break_even_are_two_items():
    by = _by(cost_per_unit=2.0, cost_currency="USD", reverse=_REV)
    assert E.RECOVERY_NAME in by and E.OPERATING_BE_NAME in by
    assert "نقطة التعادل" not in by, "لا اسمٌ واحد لمقياسين"
    rec = by[E.RECOVERY_NAME]
    assert rec["tier"] == "estimated" and "لا تعادلاً تشغيلياً" in rec["method"]


def test_operating_break_even_is_fixed_costs_over_contribution_margin():
    by = _by(cost_per_unit=2.0, cost_currency="USD", reverse=_REV,
             fixed_costs=30_000.0)
    be = by[E.OPERATING_BE_NAME]
    assert be["tier"] == "estimated"
    assert be["range"]["low"] == pytest.approx(30_000.0 / 1.5)
    assert "التكاليف الثابتة" in be["method"] and "EXW" in be["method"]


def test_without_fixed_costs_the_operating_break_even_is_a_declared_gap():
    be = _by(cost_per_unit=2.0, cost_currency="USD", reverse=_REV)[
        E.OPERATING_BE_NAME]
    assert be["tier"] == "gap" and "التكاليف الثابتة" in be["missing"]
    assert "غير استرداد الشحنة التجريبية" in be["impact"]


def test_negative_margin_and_currency_mismatch_never_compute_a_break_even():
    neg = _by(cost_per_unit=4.0, cost_currency="USD", reverse=_REV,
              fixed_costs=10_000.0)[E.OPERATING_BE_NAME]
    assert neg["tier"] == "gap" and "هامش مساهمة موجب" in neg["missing"]
    cross = _by(cost_per_unit=2.0, cost_currency="SAR", fixed_costs=10_000.0,
                reverse={"max_exw": 3.5, "unit": "لتر", "currency": "JOD"})
    assert cross[E.OPERATING_BE_NAME]["tier"] == "gap"


def test_container_capacity_is_not_presented_as_demand():
    trial = _by()["حجم الشحنة التجريبية"]
    assert "لا حجمُ طلب" in trial["confirm"]


def test_fixed_costs_flow_from_the_product_card():
    out = E.economics_view(
        {"missions": {"pricing_scout": {"findings": [
            {"value": "سعر رف 12 USD", "note": "سعر رف لعبوة 1 كجم"}]}}},
        product_card={"cost_per_unit": 2.0, "cost_currency": "USD",
                      "unit": "kg", "fixed_costs": 20_000},
        category="تمور")
    be = {e["name"]: e for e in out["decision_numbers"]}[E.OPERATING_BE_NAME]
    assert be["tier"] == "estimated", be   # يُحسب فعلاً — لا بندُ فجوةٍ دائم


def test_the_range_comes_from_the_scenarios_not_a_false_point():
    rev = {"max_exw": 3.5, "unit": "لتر", "currency": "USD", "scenarios": [
        {"max_exw": 4.6}, {"max_exw": 3.5}, {"max_exw": 2.4}]}
    be = _by(cost_per_unit=2.0, cost_currency="USD", reverse=rev,
             fixed_costs=30_000.0, monthly_capacity=5_000.0)[E.OPERATING_BE_NAME]
    assert be["range"]["low"] == pytest.approx(30_000 / 2.6)
    assert be["range"]["high"] == pytest.approx(30_000 / 0.4)
    assert be.get("too_wide") or be["range"]["low"] < be["range"]["high"]


def test_zero_is_an_input_and_negative_is_not():
    zero = _by(cost_per_unit=2.0, cost_currency="USD", reverse=_REV,
               fixed_costs=0.0)[E.OPERATING_BE_NAME]
    assert zero["tier"] == "estimated" and zero["range"]["low"] == 0
    neg = _by(cost_per_unit=2.0, cost_currency="USD", reverse=_REV,
              fixed_costs=-30_000.0)[E.OPERATING_BE_NAME]
    assert neg["tier"] == "gap"


def test_entered_fixed_costs_are_not_requested_again_when_currency_blocks():
    be = _by(cost_per_unit=2.0, fixed_costs=20_000.0,
             reverse={"max_exw": 3.5, "unit": "لتر", "currency": "JOD"})[
        E.OPERATING_BE_NAME]
    assert be["tier"] == "gap" and "عملة" in be["missing"]
    assert "صرّح بعملة تكلفتك" in be["closure"]


def test_the_api_product_card_keeps_currency_and_fixed_costs():
    import api
    model = None
    for name in dir(api):
        obj = getattr(api, name)
        if getattr(obj, "__name__", "") == "ProductCard":
            model = obj
    if model is None:
        import inspect
        src = inspect.getsource(api)
        assert "cost_currency: str | None" in src and "fixed_costs: float" in src
        return
    card = model(cost_per_unit=2.0, cost_currency="USD", fixed_costs=10)
    dumped = card.model_dump()
    assert dumped["cost_currency"] == "USD" and dumped["fixed_costs"] == 10


def test_fixed_costs_travel_from_the_catalog_to_the_engine():
    """المدخلُ موصولٌ طرفاً لطرف: ترحيلٌ إضافيّ، قائمةُ أعمدةٍ مسموحة، جسرُ
    المحرّك، والنافذةُ — لا حقلٌ في المحرّك لا يملؤه أحد."""
    import pathlib
    from silk_platform import engine_bridge as EB
    from silk_platform import repository as REPO
    root = pathlib.Path(__file__).resolve().parents[1]
    mig = (root / "migrations/platform/025_product_fixed_costs.sql").read_text(
        encoding="utf-8")
    assert "ALTER TABLE products ADD COLUMN fixed_costs REAL" in mig
    assert "fixed_costs" in REPO._WRITABLE["products"] \
        if hasattr(REPO, "_WRITABLE") else "fixed_costs" in (
            root / "silk_platform/repository.py").read_text(encoding="utf-8")
    card = EB.product_card_from_row({"cost_per_unit": 2.0, "fixed_costs": 9000,
                                     "cost_currency": "SAR"})
    assert card["fixed_costs"] == 9000 and card["cost_currency"] == "SAR"
    page = (root / "web/platform.html").read_text(encoding="utf-8")
    assert 'name="pfixed"' in page and "fixed_costs: num('[name=\"pfixed\"]')" in page
