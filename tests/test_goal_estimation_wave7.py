"""هدف الدراسة الاحترافية — الموجة ٧: تقدير المستمرّ لا الحدّي (البند ٧).

المقفول: كل تقدير يحمل حقوله الأربعة معاً (القيمة/الطريقة/المدى/سبيل
التأكيد ومدته)؛ مدى أوسع من ±50% يُعلَن «أوسع من أن يُتصرف به» ولا يُطبع
رقماً؛ لا يُبنى رقم ثالث على تقدير واسع (يُستبعد معلَناً لا صامتاً)؛
الحدّي/التعاقدي (تعرفة/إذن/هوية موزّع/شرط عقد) بلا دالة تقدير أصلاً
(قفل بنيوي)؛ مراجع الشحن/الرسوم تُشحن فارغة (عقد golden_cases: لا صف
بلا رقم متحقق بمصدره وتاريخه)؛ والأرقام الخمسة تُحسب مسبقاً (نمط Z-01)
فيعرضها القالبان (md + client docx) وينقلها الكاتب كما وردت.
"""
import ast
import csv
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import block_network

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── العقد الرباعي وقاعدة ±50% ──────────────────────────────────────────────

def test_estimate_carries_its_four_fields():
    from silk_economics import estimate_trial_shipment
    est = estimate_trial_shipment("حليب")
    assert est["tier"] == "estimated"
    assert est["method"] and "كثافة" not in est["method"]  # المصدر لا الفجوة
    assert est["range"]["low"] < est["range"]["high"]
    assert est["confirm"] and est["confirm_time"]
    assert not est["too_wide"] and est["value"] is not None
    # الاستشهاد الخام حقل منفصل — سطح العميل بلا لاتينية (بوابة اللغة):
    assert est["source"] and "المنشورة" in est["method"]
    # لتر السوق عبر ثابت الكثافة المسجّل — لا فجوة تحويل (البند ١):
    assert est["unit"] == "لتر"
    assert 24_000 < est["range"]["low"] < est["range"]["high"] < 28_500


def test_solid_category_uses_dry_container_per_kg():
    from silk_economics import estimate_trial_shipment
    est = estimate_trial_shipment("تمر")
    assert est["unit"] == "كجم"
    assert est["range"]["low"] == est["range"]["high"] == 26_730.0
    assert est["width_pct"] == 0.0


def test_no_unit_weight_means_declared_none_not_a_guess():
    from silk_economics import estimate_trial_shipment
    assert estimate_trial_shipment("تمر", unit_kg=0) is None


def test_too_wide_range_withholds_the_number():
    from silk_economics import TOO_WIDE_NOTE, _mk_estimate
    est = _mk_estimate("اختبار", 10.0, 100.0, "طريقة", "سبيل", "يوم")
    assert est["too_wide"] is True
    assert est["value"] is None
    assert est["note"] == TOO_WIDE_NOTE
    assert "أوسع من أن يُتصرف به" in est["note"]
    # المدى نفسه يبقى معلناً — الحجب على الرقم الأوسط فقط:
    assert est["range"] == {"low": 10.0, "high": 100.0}


# ── الشحن: ممر متحقق أو سيناريو معلن — ولا رقم فوق تكلفة مجهولة ────────────

def test_freight_requires_cost_when_no_verified_lane():
    from silk_economics import estimate_freight_per_unit
    assert estimate_freight_per_unit("تمر", None) is None
    assert estimate_freight_per_unit("تمر", 0) is None


def test_freight_scenario_path_is_too_wide_and_says_so():
    """نسب السيناريو 5%–25% مداها ±66.7% — فوق العتبة بالبناء: القيمة
    تُحجب والمدى يُعلن. هذا مقصود: بلا سطر ممر متحقق لا رقم شحن يُطبع."""
    from silk_economics import estimate_freight_per_unit
    est = estimate_freight_per_unit("تمر", 4.0)
    assert est["too_wide"] is True and est["value"] is None
    assert est["range"] == {"low": 0.2, "high": 1.0}


def test_freight_verified_lane_path(monkeypatch):
    import silk_economics
    monkeypatch.setattr(silk_economics, "_lane_rate",
                        lambda iso3, reefer: (2000.0, 2600.0, "مصدر منشور"))
    est = silk_economics.estimate_freight_per_unit("تمر", None, "JOR")
    assert est["too_wide"] is False and est["value"] is not None
    assert "متحقق" in est["method"]


# ── أرقام القرار الخمسة (نمط Z-01) ─────────────────────────────────────────

_FIVE = ["حجم الشحنة التجريبية", "كلفة الدخول الكلية حتى أول شحنة",
         "نقطة التعادل", "الزمن من القرار إلى أول فاتورة",
         "أقصى خسارة إن فشل الدخول"]


def test_without_cost_five_entries_with_three_field_gaps():
    from silk_economics import build_decision_numbers
    dn = build_decision_numbers(category="حليب")
    assert [e["name"] for e in dn] == _FIVE
    gaps = [e for e in dn if e["tier"] == "gap"]
    assert len(gaps) == 4                      # الشحنة التجريبية تُقدَّر
    for g in gaps:
        assert g["missing"] and g["impact"] and g["closure"], g["name"]
    entry = dn[1]
    assert "تكلفة إنتاج" in entry["missing"] and "لتر" in entry["missing"]


def test_with_cost_the_numbers_compute_and_freight_exclusion_is_declared():
    from silk_economics import build_decision_numbers
    dn = build_decision_numbers(category="حليب", cost_per_unit=2.0,
                                cost_currency="USD",
                                monthly_capacity=50_000.0,
                                reverse={"max_exw": 3.5, "unit": "لتر",
                                         "currency": "USD"})
    by = {e["name"]: e for e in dn}
    entry = by["كلفة الدخول الكلية حتى أول شحنة"]
    assert entry["tier"] == "estimated" and not entry["too_wide"]
    # الشحن السيناريو واسع → مستبعد معلَناً في الطريقة لا مضافاً صفراً صامتاً:
    assert "الشحن بلا سعر ممر متحقق" in entry["method"]
    assert entry["range"]["low"] == pytest.approx(2.0 * 25_526 / 1.03, rel=1e-3)
    be = by["نقطة التعادل"]
    assert be["tier"] == "estimated"
    assert be["range"]["low"] == pytest.approx(
        entry["range"]["low"] / 1.5, rel=1e-3)
    assert be["months_at_capacity"]["low"] > 0
    ml = by["أقصى خسارة إن فشل الدخول"]
    assert ml["range"] == entry["range"]
    assert by["الزمن من القرار إلى أول فاتورة"]["tier"] == "gap"


def test_negative_margin_declares_a_production_decision_gap():
    from silk_economics import build_decision_numbers
    dn = build_decision_numbers(category="حليب", cost_per_unit=4.0,
                                cost_currency="USD",
                                reverse={"max_exw": 3.5, "unit": "لتر",
                                         "currency": "USD"})
    be = {e["name"]: e for e in dn}["نقطة التعادل"]
    assert be["tier"] == "gap" and "هامش موجب" in be["missing"]


def test_no_cross_currency_or_cross_unit_subtraction():
    """مراجعة §58: تكلفة بعملة غير مصرّح بها (أو مخالفة) مقابل سعر مرجعي
    بعملة السوق — لا هامش يُطرح؛ فجوة ثلاثية تسمّي العملة. والوحدة كجم
    لسوق لترية تُحاذى بثابت السجل المعلن لا تُطرح خاماً."""
    from silk_economics import build_decision_numbers

    def _be(**kw):
        dn = build_decision_numbers(category="حليب", cost_per_unit=2.0, **kw)
        return {e["name"]: e for e in dn}["نقطة التعادل"]

    # عملة التكلفة غير مصرّح بها:
    be = _be(reverse={"max_exw": 3.5, "unit": "لتر", "currency": "JOD"})
    assert be["tier"] == "gap" and "غير مصرّح بها" in be["missing"] \
        and "JOD" in be["missing"]
    # عملتان مختلفتان:
    be = _be(cost_currency="SAR",
             reverse={"max_exw": 3.5, "unit": "لتر", "currency": "JOD"})
    assert be["tier"] == "gap" and "SAR" in be["missing"] \
        and "JOD" in be["missing"]
    # وحدة كجم لسوق لترية: تُحاذى بكثافة الحليب 1.03 (سعر/لتر = سعر/كجم×1.03)
    be = _be(cost_currency="USD",
             reverse={"max_exw": 3.5, "unit": "كجم", "currency": "USD"})
    assert be["tier"] == "estimated"
    import pytest as _pt
    # الهامش = 3.5×1.03 − 2.0 — لا طرح خام 3.5−2.0
    entry_low = 2.0 * 25_526 / 1.03
    assert be["range"]["low"] == _pt.approx(
        entry_low / (3.5 * 1.03 - 2.0), rel=1e-2)


def test_wide_trial_estimate_never_stacks_into_entry(monkeypatch):
    """قاعدة عدم التراكب: شحنة تجريبية واسعة المدى (>±50%) لا تُبنى عليها
    كلفة دخول ولا تعادل ولا أقصى خسارة — تصير فجوات لا أرقاماً مركّبة."""
    import silk_economics
    monkeypatch.setitem(
        silk_economics.CONTAINER_SPECS, "40ft_dry",
        {"payload_kg": (5_000.0, 30_000.0), "source": "اختبار"})
    dn = silk_economics.build_decision_numbers(category="تمر",
                                               cost_per_unit=2.0,
                                               reverse={"max_exw": 3.5})
    by = {e["name"]: e for e in dn}
    assert by["حجم الشحنة التجريبية"]["too_wide"] is True
    for name in ("كلفة الدخول الكلية حتى أول شحنة", "نقطة التعادل",
                 "أقصى خسارة إن فشل الدخول"):
        assert by[name]["tier"] == "gap", name


def test_economics_view_carries_decision_numbers():
    from silk_economics import economics_view
    with block_network():
        eco = economics_view({"missions": {}},
                             product_card={"cost_per_unit": 2.0,
                                           "monthly_capacity": 1000},
                             category="حليب")
    assert [e["name"] for e in eco["decision_numbers"]] == _FIVE


# ── القفل البنيوي: لا مقدّر للحدّي/التعاقدي ────────────────────────────────

def test_no_estimator_exists_for_binary_contractual_items():
    import silk_economics
    src = inspect.getsource(silk_economics)
    tree = ast.parse(src)
    estimators = {n.name for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name.startswith("estimate_")}
    assert estimators == {"estimate_trial_shipment",
                          "estimate_freight_per_unit"}, estimators
    for banned in ("def estimate_tariff", "def estimate_permission",
                   "def estimate_distributor", "def estimate_contract",
                   "def estimate_duty", "def estimate_license"):
        assert banned not in src, banned


# ── مراجع تُشحن فارغة (عقد golden_cases) ───────────────────────────────────

@pytest.mark.parametrize("fname,cols", [
    ("freight_lanes_l1.csv", {"lane", "mode", "container", "rate_low_usd",
                              "rate_high_usd", "source_url", "retrieved_at",
                              "verified_by"}),
    ("cert_fees_l1.csv", {"market_iso3", "category", "fee_name",
                          "fee_low_usd", "fee_high_usd", "source_url",
                          "retrieved_at", "verified_by"}),
])
def test_reference_csvs_rows_must_be_sourced(fname, cols):
    path = os.path.join(_REPO, "data", fname)
    with open(path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert set(reader.fieldnames) == cols
        for row in reader:                     # تُشحن فارغة؛ أي صف مستقبلي
            assert str(row.get("source_url") or "").strip(), row
            assert str(row.get("retrieved_at") or "").strip(), row


def test_container_constants_carry_their_source():
    from silk_economics import CONTAINER_SPECS
    for key, spec in CONTAINER_SPECS.items():
        assert spec["source"], key
        lo, hi = spec["payload_kg"]
        assert 15_000 < lo <= hi < 30_000, key


# ── فحص البوابة التحذيري estimate_fields_complete ──────────────────────────

def _view_with(dn):
    return {"deep_research": {"economics": {"decision_numbers": dn}}}


def test_gate_fires_on_estimate_missing_its_fields():
    from silk_quality_gate import _check_estimate_fields_complete
    bad = {"name": "س", "tier": "estimated", "method": "",
           "range": {"low": 1, "high": None}, "confirm": "x",
           "confirm_time": "", "too_wide": False, "value": 1}
    f = _check_estimate_fields_complete(_view_with([bad]))
    assert f and f[0]["check"] == "estimate_fields_complete"
    note = f[0]["note"]
    assert "طريقة الاشتقاق" in note and "المدى" in note \
        and "مدة التأكيد" in note


def test_gate_fires_on_wide_estimate_with_printed_value():
    from silk_quality_gate import _check_estimate_fields_complete
    bad = {"name": "س", "tier": "estimated", "method": "م",
           "range": {"low": 1, "high": 9}, "confirm": "x",
           "confirm_time": "يوم", "too_wide": True, "value": 5}
    f = _check_estimate_fields_complete(_view_with([bad]))
    assert f and "قيمة مطبوعة" in f[0]["note"]


def test_gate_silent_on_complete_estimates_and_gaps():
    from silk_economics import build_decision_numbers
    from silk_quality_gate import _check_estimate_fields_complete
    dn = build_decision_numbers(category="حليب", cost_per_unit=2.0,
                                cost_currency="USD",
                                reverse={"max_exw": 3.5, "unit": "لتر",
                                         "currency": "USD"})
    assert _check_estimate_fields_complete(_view_with(dn)) == []
    assert _check_estimate_fields_complete({"deep_research": {}}) == []


def test_estimate_check_is_warn_tier_not_fail():
    from silk_quality_gate import FAIL_TRIGGER_CHECKS
    assert "estimate_fields_complete" not in FAIL_TRIGGER_CHECKS


# ── السطحان + الكاتب ينقل لا يحسب (نمط Z-01) ───────────────────────────────

def _result_with_cost():
    return {"product": "حليب", "hs_code": "040120", "year": 2024,
            "report_language": "ar", "markets": [], "test_run": True,
            "product_card": {"cost_per_unit": 2.0, "currency": "USD"},
            "deep_research": {
                "product": "حليب", "missions": {},
                "market": {"iso3": "JOR", "name_ar": "الأردن",
                           "name_en": "Jordan"},
                "verdict": {"verdict": "WATCH", "confidence": 0.6},
                "verdict_label": "مراقبة السوق",
                "report": {"text": "## 1. الخلاصة التنفيذية\n"
                                   "التوصية: تأجيل.\n"},
                "limits": [], "gap_register": []}}


def test_markdown_and_client_docx_show_decision_numbers(tmp_path):
    pytest.importorskip("docx")
    from conftest import docx_all_text
    from silk_render import build_view
    from silk_reports import render_client_docx, render_markdown
    with block_network():
        view = build_view(_result_with_cost())
    dn = view["deep_research"]["economics"]["decision_numbers"]
    assert [e["name"] for e in dn] == _FIVE
    md = render_markdown(view)
    assert "أرقام القرار (محسوبة حتمياً" in md
    assert "حجم الشحنة التجريبية" in md
    assert "ما يؤكده ومدته" in md
    assert "المصدر:" in md                       # الاستشهاد على سطح المشغّل
    path = os.path.join(tmp_path, "c.docx")
    with block_network():
        render_client_docx(view, path)
    text = docx_all_text(path)
    assert "أرقام القرار (محسوبة حتمياً)" in text
    assert "لا نعرفه بعد — الناقص:" in text      # فجوات الزمن/التعادل


def test_writer_prompt_transfers_precomputed_numbers_verbatim():
    import silk_ai_judge
    src = inspect.getsource(silk_ai_judge)
    assert "انقلها كما وردت داخل قسم " in src
    assert "لا تحسب بديلاً" in src
    # الفجوة تصل الكاتب بحقولها الثلاثة لا كإعلان غياب عارٍ:
    assert "المعطى الناقص:" in src and "سبيل الإغلاق:" in src
