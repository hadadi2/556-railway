"""الموجة الرابعة — البند ٣: رسومُ التقرير بياناتٍ محضة، والواجهةُ ترسم.

report charts as pure data (`deep_research.charts`, behind
`SILK_REPORT_CHARTS`), drawn by one self-contained SVG renderer in
`web/platform.html` under the same five rules as the existing markets chart.

كلُّ رسمٍ يحمل مصدرَه وسنتَه وملاحظةَ نقصه؛ القيمةُ الغائبة `None` لا صفر؛
حصةُ السعودية مميَّزة؛ ولا رسمَ لبياناتٍ لا تأتي (لا محورَ فارغ). والألوانُ من
ملف الهوية فقط — الذهبيُّ لونُ بياناتٍ لا واجهة.
"""
import pathlib
import re

import pytest

import silk_render as R
from silk_data_layer import DataPoint

_FLAGS = ("SILK_CLIENT_METRIC_PRIVACY", "SILK_IMPORTS_SPOTLIGHT",
          "SILK_REPORT_CHARTS", "SILK_CONFIDENCE_DISCIPLINE")

_ALLOWED_HEX = {"#2563EB", "#C9A227", "#EEF2F7", "#64748B", "#111827"}


def _clear(monkeypatch) -> None:
    for f in _FLAGS:
        monkeypatch.delenv(f, raising=False)


def _flow(v, y, status=""):
    return DataPoint(v, "UN Comtrade", 0.9,
                     f"HS090121 إجمالي استيراد Malaysia من العالم {y}, USD"
                     if v is not None else
                     f"HS090121 استيراد Malaysia {y}: تعذّر الجلب",
                     "2026-09-17", status=status,
                     data_year=(y if v is not None else None))


def _result(with_suppliers: bool = True) -> dict:
    missions = {"trade_flow": {"findings": [
        _flow(51358600.874, 2021), _flow(None, 2023, "fetch_failed"),
        _flow(89400000.0, 2024)], "failed": False, "summary": "x"}}
    if with_suppliers:
        missions["competitors"] = {"findings": [DataPoint(
            {"hhi": 2100, "year": 2024, "top_suppliers": [
                {"partner": "Brazil", "share": 41.2},
                {"partner": "السعودية", "share": 3.5},
                {"partner": "Vietnam", "share": 22.0},
                {"partner": "Nowhere", "share": 140.0}]},   # خارج ٠–١٠٠ تُسقَط
            "UN Comtrade", 0.9, "ملخّص المورّدين", "2026-09-17")],
            "failed": False, "summary": "y"}
    return {
        "market": {"name_ar": "ماليزيا", "name_en": "Malaysia", "iso3": "MYS"},
        "product": "قهوة محمصة", "hs_code": "090121",
        "deep_research": {"missions": missions,
                          "verdict": {"verdict": "GO", "confidence": 0.8},
                          "report": {"text": "## 1. الخلاصة التنفيذية\nنص.\n"}},
        "markets": [{"country": "ماليزيا", "iso3": "MYS", "total_score": 0.7,
                     "confidence": 0.8, "rank": 1, "deep": True,
                     "components": {}}]}


def _charts(monkeypatch, **flags):
    _clear(monkeypatch)
    for k, v in flags.items():
        monkeypatch.setenv(k, v)
    return R.build_view(_result())["deep_research"].get("charts")


# ── (١) بياناتٌ محضة بمصدرٍ وسنةٍ وملاحظة ──────────────────────────────────

def test_charts_are_pure_data_with_source_year_and_note(monkeypatch):
    charts = _charts(monkeypatch, SILK_IMPORTS_SPOTLIGHT="1",
                     SILK_REPORT_CHARTS="1")
    assert [c["id"] for c in charts] == ["imports_trend", "supplier_shares"]
    trend, shares = charts
    assert trend["unit"] == "USD" and shares["unit"] == "%", "رسمٌ لكلّ وحدة"
    assert trend["source"] == "UN Comtrade" and trend["year"] == "2021–2024"
    assert "2023" in trend["note"], "السنةُ الناقصة تُقال على الرسم"
    assert [p["year"] for p in trend["series"]] == [2021, 2024]
    assert all(p["value"] is not None for p in trend["series"])
    assert shares["year"] == "2024" and shares["source"] == "UN Comtrade"
    for c in charts:
        for k in ("id", "kind", "unit", "title", "series", "source", "year",
                  "note"):
            assert k in c, k
        assert not any(isinstance(x, DataPoint) for x in c["series"])


def test_saudi_row_is_highlighted_and_out_of_range_share_is_dropped(monkeypatch):
    _, shares = _charts(monkeypatch, SILK_IMPORTS_SPOTLIGHT="1",
                        SILK_REPORT_CHARTS="1")
    labels = [r["label"] for r in shares["series"]]
    assert labels == ["Brazil", "السعودية", "Vietnam"]
    assert all("value_usd" not in r for r in shares["series"]), "حقلٌ ميّت"
    assert [r["highlight"] for r in shares["series"]] == [False, True, False]
    assert "الذهبي" in shares["note"]


def test_charted_values_have_a_fact_behind_them(monkeypatch):
    """قيمةٌ مرسومةٌ بلا مقابلٍ في حقائق البعثات = اختلاق — العقدُ يمنعه."""
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    monkeypatch.setenv("SILK_REPORT_CHARTS", "1")
    res = _result()
    v = R.build_view(res)
    facts = {f.value for f in res["deep_research"]["missions"]["trade_flow"]["findings"]
             if isinstance(f.value, (int, float))}
    trend = v["deep_research"]["charts"][0]
    assert {p["value"] for p in trend["series"]} <= facts


def test_charts_absent_without_the_flag_and_without_data(monkeypatch):
    assert _charts(monkeypatch, SILK_IMPORTS_SPOTLIGHT="1") is None
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_REPORT_CHARTS", "1")
    v = R.build_view(_result(with_suppliers=False))
    # الرايةُ مفعَّلة وبلا راية الواردات ⇒ لا رسمَ مسار؛ وبلا مورّدين ⇒ لا رسمَ حصص.
    assert v["deep_research"]["charts"] == []


# ── (٢) المُصيِّرُ في الصفحة: القيودُ الخمسة والألوانُ من الهوية ─────────────

def _renderer_body() -> str:
    page = pathlib.Path("web/platform.html").read_text(encoding="utf-8")
    return page.split("function renderReportCharts(")[1].split("\nfunction ")[0]


def test_page_chart_renderer_obeys_the_five_rules():
    body = _renderer_body()
    assert 'direction: "ltr"' in body, "الأرقامُ ltr دائماً"
    assert 'rtl ? "start" : "end"' in body and 'rtl ? "rtl" : "ltr"' in body, "التسميةُ باتجاه حرفها"
    assert "host.clientWidth" in body
    assert 'svg.style.height = "auto"' in body
    assert "height: String(H)" in body and "preserveAspectRatio" in body
    assert "emptyState(" in body, "سلسلةٌ فارغةٌ حالةٌ معلنة لا محورٌ فارغ"
    assert '"—"' in body, "القيمةُ الغائبة شرطةٌ بلا عمود"
    assert "ch.source" in body and "ch.year" in body and "ch.note" in body
    # لا مراقبَ حجمٍ هنا عمداً: الرسمُ يعيش داخل نافذةٍ ثابتة العرض ويعتمد
    # `maxWidth:100%` + `height:auto` (مثل مخطّط الأسواق في نفس النافذة).


def test_page_chart_renderer_uses_only_branding_colours():
    body = _renderer_body()
    used = {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}", body)}
    assert used <= _ALLOWED_HEX, used - _ALLOWED_HEX
    assert "#C9A227" in used, "الذهبيُّ لونُ الصفّ المميَّز (حصة السعودية)"
    assert "r.highlight" in body


def test_report_dialog_injects_charts_after_opening():
    """الحقنُ بعد الفتح (SVG عبر DOM لا نصّ) — وبالموجة الخامسة مجموعةً لكلّ
    قسم بدل معلاقٍ واحد."""
    page = pathlib.Path("web/platform.html").read_text(encoding="utf-8")
    body = page.split("function viewReportBtn(")[1].split("\nfunction ")[0]
    assert 'data-role="rep-charts-' in body
    assert "renderReportCharts(host, _chartGroups[sec])" in body
    assert "dr.charts" in body


# ════════════════════════════════════════════════════════════════════════════
# الموجة الخامسة — الرسمُ عبر التقرير كلّه (الدرس ٢٥٩)
#
# المالك: «اريد كامل التقرير وليس شكل واحد… الرسم البياني لكافة المعلومة التي
# ممكن تتمثل». فالسجلُّ يتوسّع إلى سبعةِ بُناةٍ في ثلاثة أقسام، والعقدُ نفسُه
# يخدم الويب (SVG) وWord (PNG) — ولا رسمَ لبياناتٍ لا تأتي.
# ════════════════════════════════════════════════════════════════════════════

def _dr_charts(monkeypatch, dr_extra: dict, **flags) -> list:
    """رسومُ عرضٍ مبنيٍّ من مدوّنةٍ صغيرة مُحمَّلةٍ بما يخصّ الرسمَ المُختبَر."""
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_REPORT_CHARTS", "1")
    for k, v in flags.items():
        monkeypatch.setenv(k, v)
    res = _result(with_suppliers=False)
    res["deep_research"].update(dr_extra)
    res["product_card"] = dr_extra.pop("_product_card", None) or \
        res.get("product_card")
    return R.build_view(res)["deep_research"].get("charts") or []


def _find(charts: list, cid: str):
    return next((c for c in charts if c["id"] == cid), None)


def _ids(charts: list) -> list:
    return [c["id"] for c in charts]


# ── (٣) العقدُ الموسَّع: قسمٌ ونوعٌ لكلّ رسم ────────────────────────────────

def test_every_chart_declares_a_known_section_and_kind(monkeypatch):
    charts = _charts(monkeypatch, SILK_IMPORTS_SPOTLIGHT="1",
                     SILK_REPORT_CHARTS="1")
    assert charts, "المدوّنةُ تحمل واردات ومورّدين فلا بدّ من رسمين"
    for c in charts:
        assert c["section"] in R.CHART_SECTIONS, c
        assert c["kind"] in R.CHART_KINDS, c
    assert {c["section"] for c in charts} == {"market"}


# ── (٤) اهتمامُ البحث النسبي — صفّان فأكثر، ومصدرُه Google Trends ──────────

def _trends(val, label):
    return DataPoint(val, "Google Trends", 0.6, label, "2026-09-17",
                     data_year=2026)


def test_demand_interest_needs_two_observed_queries(monkeypatch):
    one = {"missions": {"demand_trends": {"findings": [
        _trends(74, "زبدة الفول السوداني")], "failed": False, "summary": ""}}}
    assert _find(_dr_charts(monkeypatch, dict(one)), "demand_interest") is None

    two = {"missions": {"demand_trends": {"findings": [
        _trends(74, "زبدة الفول السوداني"),
        _trends(100, "فوائد زبدة الفول السوداني; monthly mean 0-100: x"),
        _trends(None, "لا سلسلة")], "failed": False, "summary": ""}}}
    ch = _find(_dr_charts(monkeypatch, two), "demand_interest")
    assert ch and ch["kind"] == "bars" and ch["unit"] == "index"
    assert ch["section"] == "market" and ch["source"] == "Google Trends"
    assert [r["value"] for r in ch["series"]] == [74.0, 100.0]
    # الملاحظةُ تقول ما يعنيه المؤشّر — «100» ليست عددَ عمليات بحث.
    assert "100" in ch["note"] and "نسبي" in ch["note"]
    # التسميةُ نصُّ البعثة قبل الفاصلة المنقوطة (لا رقمٌ مستخلَص).
    assert ch["series"][1]["label"] == "فوائد زبدة الفول السوداني"


def test_demand_interest_ignores_values_outside_the_index_range(monkeypatch):
    dr = {"missions": {"demand_trends": {"findings": [
        _trends(74, "أ"), _trends(180, "ب"), _trends(12, "ج")],
        "failed": False, "summary": ""}}}
    ch = _find(_dr_charts(monkeypatch, dr), "demand_interest")
    assert [r["value"] for r in ch["series"]] == [74.0, 12.0], "0–100 حصراً"


# ── (٥) تركّزُ المورّدين — عتباتُه من ثوابت المحرّك لا من العرض ─────────────

def _hhi_dr(hhi):
    """شكلُ الإنتاج حرفياً: نقطةٌ رقمية بملاحظةٍ تحمل «HHI» (هكذا يقرؤها
    `silk_economics._mission_numeric`) وبجانبها الملخّصُ المهيكل بسنته."""
    return {"missions": {"competitors": {"findings": [
        DataPoint(hhi, "UN Comtrade", 0.8, "HHI محسوب من حصص المورّدين",
                  "2026-09-17", data_year=2024),
        DataPoint({"hhi": hhi, "year": 2024, "top_suppliers": []},
                  "UN Comtrade", 0.9, "ملخّص المورّدين", "2026-09-17")],
        "failed": False, "summary": ""}}}


def test_concentration_gauge_reads_its_bands_from_the_engine(monkeypatch):
    import silk_economics as E
    ch = _find(_dr_charts(monkeypatch, _hhi_dr(2100)),
               "supplier_concentration")
    assert ch["kind"] == "gauge" and ch["section"] == "competition"
    assert ch["value"] == 2100.0 and ch["band"] == "moderate"
    assert [b["from"] for b in ch["bands"]] == [
        0, E.HHI_MODERATE_CONCENTRATION, E.HHI_HIGH_CONCENTRATION]
    assert ch["bands"][-1]["to"] == E.HHI_SCALE_MAX
    assert ch["series"] == [{"label": ch["band_label"], "value": 2100.0}]
    assert ch["source"] == "UN Comtrade" and ch["year"] == "2024"


def test_concentration_gauge_absent_without_a_measured_index(monkeypatch):
    assert _find(_dr_charts(monkeypatch, {}), "supplier_concentration") is None


# ── (٦) سلّمُ التكلفة وسيناريوهاتُ أقصى سعرِ مصنع ──────────────────────────

def _eco_dr(**eco):
    base = {"waterfall": None, "reverse_solve": None, "decision_numbers": [],
            "hhi": None, "gaps": [], "anchor_price": None}
    base.update(eco)
    return base


def test_cost_ladder_marks_declared_parameters_muted():
    import silk_economics as E
    steps = E.margin_waterfall(3.1, freight=None, tariff_pct=5.0, vat_pct=0.0,
                               distributor_margin_pct=None,
                               retailer_margin_pct=None)
    # الرسمُ يُبنى من عرض الاقتصاد المبنيّ (`view["deep_research"]["economics"]`)
    # — يُختبَر على بانيه مباشرةً بنفس الشكل الذي يُصدِره المحرّك.
    eco = _eco_dr(waterfall=steps, cost_currency="USD")
    got = R._chart_landed_cost_ladder(eco, "ar")
    assert got["kind"] == "bars" and got["section"] == "economics"
    assert got["unit"] == "USD" and "USD" in got["title"]
    # محورُ «السلّم» مستوياتٌ متتابعة: الزيادةُ المفردة (مبلغُ الشحن) تُسقَط
    # ويُقال أين تُقرأ — لا مقياسان على محورٍ واحد.
    levels, prev = [], None
    for st in steps:
        if prev is None or st["value"] >= prev:
            levels.append(st)
            prev = st["value"]
    assert len(levels) == len(steps) - 1, "خطوةُ الشحن زيادةٌ لا مستوى"
    assert [r["value"] for r in got["series"]] == [s["value"] for s in levels]
    # الباهتُ = ما وسمه المحرّك معلمةً معلنة، لا حكمَ عرضٍ ثانٍ.
    assert [r["muted"] for r in got["series"]] == [bool(s["is_parameter"])
                                                   for s in levels]
    assert got["series"][0]["muted"] is False, "سعرُ المصنع رقمٌ مُدخَل"
    assert any(r["muted"] for r in got["series"]), "الهوامشُ معلماتٌ معلنة"
    assert "جدول التكلفة" in got["note"], "الزيادةُ المُسقَطة تُقال لا تُخفى"


def test_cost_ladder_unit_is_the_declared_cost_currency_never_a_default():
    """مراجعة §58 (H1): `margin_waterfall` يكتب في ملاحظة خطوته الأولى قيمةَ
    وسيطه `currency`، ونداءُ الإنتاج لا يمرّره — فهي «USD» دائماً بينما المال
    نفسُه بعملة البطاقة. فوسمُ المحور بها يطبع «$3.1» لمبلغٍ بالدينار.
    المصدرُ الوحيد للوحدة: `economics.cost_currency` (تصريحُ المالك)."""
    import silk_economics as E
    steps = E.margin_waterfall(3.1, freight=None, tariff_pct=5.0, vat_pct=0.0,
                               distributor_margin_pct=None,
                               retailer_margin_pct=None)
    assert steps[0]["note"] == "USD", "الافتراضُ الداخلي كما هو (لا تغييرَ فيه)"
    got = R._chart_landed_cost_ladder(
        _eco_dr(waterfall=steps, cost_currency="دينار"), "ar")
    assert got["unit"] == "دينار" and "دينار" in got["title"]
    # عملةٌ لم يصرّح بها أحد ⇒ لا رسم (وحدةٌ مجهولة لا تُوسَم).
    assert R._chart_landed_cost_ladder(_eco_dr(waterfall=steps), "ar") is None
    assert R._chart_landed_cost_ladder(
        _eco_dr(waterfall=steps, cost_currency="بعملة تكلفتك"), "ar") is None


def test_cost_currency_is_declared_in_the_economics_view():
    """العرضُ يحمل عملةَ التكلفة كما صرّح بها المالك — مفتاحٌ إضافيّ لا رقم."""
    import silk_economics as E
    eco = E.economics_view(
        {"missions": {}}, category="أغذية",
        product_card={"cost_per_unit": 3.1, "cost_currency": "دينار"})
    assert eco["cost_currency"] == "دينار"
    assert E.economics_view({"missions": {}}, category="أغذية",
                            product_card={"cost_per_unit": 3.1}
                            )["cost_currency"] is None


def test_cost_ladder_absent_when_a_step_has_no_number(monkeypatch):
    broken = [{"name": "سعر المصنع (EXW)", "value": 3.1, "note": "USD",
               "is_parameter": False},
              {"name": "الشحن", "value": None, "note": "USD",
               "is_parameter": True}]
    assert R._chart_landed_cost_ladder(_eco_dr(waterfall=broken), "ar") is None
    assert R._chart_landed_cost_ladder(_eco_dr(), "ar") is None


def test_max_exw_scenarios_highlights_the_headline_one():
    import silk_economics as E
    rs = E.reverse_solve_max_exw(9.5, tariff_pct=5.0, vat_pct=0.0,
                                 freight_pct_of_exw=None,
                                 distributor_margin_pct=None,
                                 retailer_margin_pct=None)
    rs = dict(rs, currency="دينار", unit="كجم")
    ch = R._chart_max_exw_scenarios(_eco_dr(reverse_solve=rs), "ar")
    assert ch["unit"] == "دينار/كجم" and ch["section"] == "economics"
    assert [r["label"] for r in ch["series"]] == ["منخفض", "متوسط", "مرتفع"]
    assert [r["highlight"] for r in ch["series"]] == [False, True, False]
    assert [r["value"] for r in ch["series"]] == [s["max_exw"]
                                                  for s in rs["scenarios"]]


def test_max_exw_chart_absent_without_a_declared_unit():
    import silk_economics as E
    rs = E.reverse_solve_max_exw(9.5, tariff_pct=None, vat_pct=None,
                                 freight_pct_of_exw=None,
                                 distributor_margin_pct=None,
                                 retailer_margin_pct=None)
    assert R._chart_max_exw_scenarios(_eco_dr(reverse_solve=rs), "ar") is None


# ── (٧) مدى أرقام القرار — رسمٌ لكلّ وحدة، وشريطٌ واحدٌ لا يُرسَم ───────────

def _est(name, unit, low, high, value=None, too_wide=False):
    return {"name": name, "tier": "estimated", "unit": unit,
            "range": {"low": low, "high": high}, "value": value,
            "too_wide": too_wide, "tag": "تقدير معلن بمدى", "method": "م",
            "confirm": "ت", "confirm_time": "٣ أيام"}


def test_decision_ranges_groups_by_unit_and_skips_single_bars():
    dn = [_est("حجم الشحنة", "كجم", 26730, 26730, 26730),
          _est("كلفة الدخول", "SAR", 80000, 140000, 110000),
          _est("أقصى خسارة", "SAR", 120000, 120000, 120000),
          {"name": "نقطة التعادل", "tier": "gap", "missing": "س",
           "impact": "ص", "closure": "ع"},
          _est("واسعٌ جداً", "SAR", 1, 999999, 5, too_wide=True)]
    charts = R._charts_decision_ranges(_eco_dr(decision_numbers=dn), "ar")
    assert [c["unit"] for c in charts] == ["SAR"], "وحدةٌ بشريطٍ واحد تُسقَط"
    ch = charts[0]
    assert ch["kind"] == "range" and ch["section"] == "economics"
    assert [r["label"] for r in ch["series"]] == ["كلفة الدخول", "أقصى خسارة"]
    assert ch["series"][0] == {"label": "كلفة الدخول", "low": 80000.0,
                              "high": 140000.0, "value": 110000.0}
    assert "حدود هذا التقرير" in ch["note"], "ما لم يُقدَّر ليس على الرسم"


def test_decision_ranges_absent_without_estimates():
    assert R._charts_decision_ranges(_eco_dr(decision_numbers=[
        {"name": "نقطة التعادل", "tier": "gap", "missing": "س",
         "impact": "ص", "closure": "ع"}]), "ar") == []


# ── (٨) الفصلُ الصلب: تسميةٌ عربيةٌ لا تُرسَم على تقريرٍ إنجليزيّ ───────────

def test_arabic_labels_are_dropped_not_translated_on_an_english_report():
    import silk_economics as E
    steps = E.margin_waterfall(3.1, freight=None, tariff_pct=5.0, vat_pct=0.0,
                               distributor_margin_pct=None,
                               retailer_margin_pct=None)
    assert R._chart_landed_cost_ladder(
        _eco_dr(waterfall=steps, cost_currency="USD"), "ar")
    assert R._chart_landed_cost_ladder(
        _eco_dr(waterfall=steps, cost_currency="USD"), "en") is None
    dn = [_est("كلفة الدخول", "SAR", 8, 14, 11),
          _est("أقصى خسارة", "SAR", 12, 12, 12)]
    assert R._charts_decision_ranges(_eco_dr(decision_numbers=dn), "en") == []


# ── (٩) مسحُ المدوّنات الستّ عشرة: العقدُ يصمد وكلُّ قيمةٍ مسنودة ───────────

def _canonical_blobs() -> list:
    import importlib
    import inspect
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tools = os.path.join(root, "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    out = []
    for fn in sorted(os.listdir(tools)):
        if not (fn.startswith("canonical_") and fn.endswith(".py")):
            continue
        mod = importlib.import_module(fn[:-3])
        for name, obj in vars(mod).items():
            if not (callable(obj) and not name.startswith("_")
                    and getattr(obj, "__module__", "") == mod.__name__):
                continue
            try:
                if inspect.signature(obj).parameters:
                    continue
                blob = obj()
            except Exception:                                    # noqa: BLE001
                continue
            if isinstance(blob, dict) and "deep_research" in blob:
                out.append((fn[10:-3], blob))
                break
    return out


def test_the_whole_corpus_builds_charts_that_obey_the_contract(monkeypatch):
    """لا استثناء، ولا سلسلةٌ فارغة، ولا قيمةٌ بلا حقيقة — على كلّ مدوّنة."""
    import silk_quality_gate as Q
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    monkeypatch.setenv("SILK_REPORT_CHARTS", "1")
    blobs = _canonical_blobs()
    assert len(blobs) >= 16, f"المدوّناتُ المقيسة: {len(blobs)}"
    drawn = set()
    for key, blob in blobs:
        dr = R.build_view(blob)["deep_research"]
        charts = dr.get("charts")
        assert isinstance(charts, list), key
        for c in charts:
            assert c["series"], f"{key}/{c['id']}: سلسلةٌ فارغة"
            assert c["kind"] in R.CHART_KINDS and c["section"] in R.CHART_SECTIONS
            for k in ("id", "unit", "title", "source", "year", "note"):
                assert k in c, f"{key}/{c['id']}: {k} مفقود"
            drawn.add(c["id"].split("_")[0] if c["id"].startswith("decision")
                      else c["id"])
        assert Q._check_chart_backing(dr) == [], f"{key}: قيمةٌ بلا حقيقة"
    # حدُّ الدليل مُعلَنٌ لا مُضمَر: هذه هي الرسومُ التي تمرّ عليها المدوّنات.
    assert {"imports_trend", "supplier_concentration", "landed_cost_ladder",
            "max_exw_scenarios", "decision", "demand_interest"} <= drawn


def test_charts_stay_absent_without_the_flag_on_the_corpus(monkeypatch):
    _clear(monkeypatch)
    for key, blob in _canonical_blobs()[:3]:
        assert "charts" not in R.build_view(blob)["deep_research"], key


# ── (١٠) مُصيِّرُ الصفحة: ثلاثةُ أنواعٍ بالقواعد الخمسة، ومجموعةٌ لكلّ قسم ──

def test_page_renderer_dispatches_on_kind_with_the_three_cases():
    body = _renderer_body()
    assert "switch (kind)" in body
    for case in ('case "range"', 'case "gauge"', "default:"):
        assert case in body, case
    assert 'ch.kind === "range" || ch.kind === "gauge" ? ch.kind : "bars"' in body
    # القواعدُ الخمسة مرّةً واحدةً للأنواع الثلاثة (المِحفَظةُ مشتركة).
    assert body.count('"ltr"') >= 2
    assert "host.clientWidth" in body and 'svg.style.height = "auto"' in body
    assert "height: String(H)" in body and "preserveAspectRatio" in body
    assert "emptyState(" in body and '"—"' in body


def test_page_renderer_draws_ranges_and_bands_without_new_colours():
    body = _renderer_body()
    used = {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}", body)}
    assert used <= _ALLOWED_HEX, used - _ALLOWED_HEX
    assert "r.low" in body and "r.high" in body, "شريطُ المدى من أدنى لأعلى"
    # اتجاهُ التسمية من حرفها: تسميةٌ عربيةٌ لا تُفرَض ltr فتنقلب أقواسُها.
    assert 'rtl ? "start" : "end"' in body and 'rtl ? "rtl" : "ltr"' in body
    assert "ch.bands" in body and "ch.value" in body, "مناطقُ المؤشّر"
    assert 'unit === "index"' in pathlib.Path("web/platform.html").read_text(
        encoding="utf-8"), "وحدةُ المؤشّر لها فرعُها في المُنسِّق"


def test_report_dialog_places_a_chart_group_per_section():
    page = pathlib.Path("web/platform.html").read_text(encoding="utf-8")
    body = page.split("function viewReportBtn(")[1].split("\nfunction ")[0]
    assert "_chartGroups" in body and "c.section" in body
    assert 'data-role="rep-charts-' in body
    assert "renderReportCharts(host, _chartGroups[sec])" in body
    # مجموعةٌ لم تجد قسمَها تُعرَض ولا تختفي.
    assert '["competition", "economics"].forEach' in body
    assert "_splitWriterSections(rtext)" in body
    assert "_CHART_GROUP_AFTER_ORDINAL" in page


# ── (١١) الوحدةُ أيضاً تخضع للفصل الصلب (لا عملةٌ عربيةٌ في عنوانٍ إنجليزيّ) ──

def test_an_arabic_unit_never_reaches_an_english_chart_title():
    """عملةٌ يكتبها المحرّك بالعربية («دينار/كجم») في عنوان رسمٍ إنجليزيٍّ
    تُسقِط المستندَ كلَّه ببوّابة تسرّب اللغة — فالرسمُ يُسقَط بدلاً منه."""
    import silk_economics as E
    rs = dict(E.reverse_solve_max_exw(9.5, tariff_pct=5.0, vat_pct=0.0,
                                      freight_pct_of_exw=None,
                                      distributor_margin_pct=None,
                                      retailer_margin_pct=None),
              currency="دينار", unit="كجم")
    assert R._chart_max_exw_scenarios(_eco_dr(reverse_solve=rs), "ar")
    assert R._chart_max_exw_scenarios(_eco_dr(reverse_solve=rs), "en") is None
    en = R._chart_max_exw_scenarios(
        _eco_dr(reverse_solve=dict(rs, currency="USD")), "en")
    assert en["unit"] == "USD/kg" and "USD/kg" in en["title"]
    assert R._chart_unit_fits_lang("دينار/كجم", "en") is False
    assert R._chart_unit_fits_lang("دينار/كجم", "ar") is True


# ════════════════════════════════════════════════════════════════════════════
# (١٢) حصادُ المراجعة الذاتية §58 على هذه الموجة — كلُّ ملاحظةٍ بقفلها.
# ════════════════════════════════════════════════════════════════════════════

def test_imports_trend_needs_two_observed_years(monkeypatch):
    """عمودٌ واحدٌ تحت عنوان «بالسنوات» ومعه تعليقٌ يقول «لا مسارَ بسنةٍ
    واحدة» — رسمٌ يكذّب تعليقَه. سنتان شرطُ المسار كشرطِ جدوله."""
    one = {"missions": {"trade_flow": {"findings": [_flow(89400000.0, 2024)],
                                       "failed": False, "summary": "x"}}}
    res = _result(with_suppliers=False)
    res["deep_research"].update(one)
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_REPORT_CHARTS", "1")
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    dr = R.build_view(res)["deep_research"]
    assert dr["imports"]["value_line"], "الرقمُ يبقى مكتوباً في القسم"
    assert _find(dr.get("charts") or [], "imports_trend") is None


def test_the_context_only_badge_reaches_the_gauge_too(monkeypatch):
    """رمزٌ مُعلَّمٌ يجعل التركّزَ سياقاً للفئة؛ التحفّظُ إلزاميٌّ على كلّ سطح
    — والصورةُ سطحٌ (مراجعة §58، M5)."""
    import silk_i18n as I
    hhi_dr = _hhi_dr(2100)
    line = I.t("concentration_context_line", "ar")
    plain = R._chart_supplier_concentration(hhi_dr, _eco_dr(hhi=2100), "ar")
    ctx = R._chart_supplier_concentration(hhi_dr, _eco_dr(hhi=2100), "ar",
                                          True)
    assert line not in plain["note"] and line in ctx["note"]
    # والمفتاحُ يصل البانيَ من **العرض المبنيّ** لا من النتيجة الخام: رمزٌ
    # غيرُ مؤكَّد (`confirmed is False`) هو ما يضبطه في `build_view`.
    res = _result(with_suppliers=False)
    res["deep_research"].update(hhi_dr)
    res["hs_confirmation"] = {"confirmed": False, "missing_terms": ["محمّصة"]}
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_REPORT_CHARTS", "1")
    dr = R.build_view(res)["deep_research"]
    assert dr["concentration_context_only"] is True
    assert line in _find(dr["charts"], "supplier_concentration")["note"]


def test_a_zero_concentration_index_is_a_gap_not_an_open_market():
    """`hhi = حساب أو 0` يكتب صفراً حين لا حصّةَ صالحة؛ وقراءتُه «سوقٌ
    مفتوحة» حكمٌ على قياسٍ غائب — عائلةُ الصفر المختلَق (البند ٨)."""
    import silk_economics as E
    assert E.hhi_band(0) is None and E.hhi_band(0.0) is None
    assert E.hhi_band(1200) == "open" and E.hhi_band(2100) == "moderate"
    assert E.hhi_band(9000) == "high" and E.hhi_band(10_001) is None
    assert R._chart_supplier_concentration({}, _eco_dr(hhi=0), "ar") is None


def test_the_pricing_contradiction_warning_reaches_the_max_exw_chart():
    """المحرّكُ يحظر تقديمَ هذا الرقم أساساً للتفاوض عند التناقض؛ فعمودٌ
    ذهبيٌّ بلا تحفّظٍ يُقرأ سقفاً تفاوضياً (مراجعة §58، H2)."""
    import silk_economics as E
    import silk_i18n as I
    rs = dict(E.reverse_solve_max_exw(9.5, tariff_pct=5.0, vat_pct=0.0,
                                      freight_pct_of_exw=None,
                                      distributor_margin_pct=None,
                                      retailer_margin_pct=None),
              currency="USD", unit="كجم")
    plain = R._chart_max_exw_scenarios(_eco_dr(reverse_solve=rs), "ar")
    warned = R._chart_max_exw_scenarios(
        _eco_dr(reverse_solve=rs, pricing_contradiction={
            "shortfall_pct": 43.1, "note": "تحذير…"}), "ar")
    warn = I.t("chart_max_exw_contradiction_note", "ar")
    assert warn not in plain["note"] and warn in warned["note"]
    assert "للتفاوض" in warn, "نصُّ الحظر نفسُه لا إحالةٌ عليه"
    en = R._chart_max_exw_scenarios(
        _eco_dr(reverse_solve=rs, pricing_contradiction={"x": 1}), "en")
    assert I.t("chart_max_exw_contradiction_note", "en") in en["note"]


def test_a_range_chart_needs_at_least_one_real_span():
    """تعليقُ الرسم يقول «كلُّ شريطٍ من أدنى تقديرٍ إلى أعلاه» — فصفوفٌ كلُّها
    نقطيةٌ رسمُ مدىً بلا مدى (مراجعة §58، M10)."""
    points = [_est("كلفة الدخول", "SAR", 82863, 82863, 82863),
              _est("أقصى خسارة", "SAR", 82863, 82863, 82863)]
    assert R._charts_decision_ranges(_eco_dr(decision_numbers=points),
                                     "ar") == []
    mixed = points + [_est("هامش", "SAR", 10, 40, 25)]
    got = R._charts_decision_ranges(_eco_dr(decision_numbers=mixed), "ar")
    assert len(got) == 1 and len(got[0]["series"]) == 3


def test_a_measured_chart_without_a_year_says_so(monkeypatch):
    """الدرس ٢٥٦: سنةُ الرقم جزءٌ منه — وغيابُها يُقال لا يُحذَف."""
    import silk_i18n as I
    dr = {"missions": {"competitors": {"findings": [
        DataPoint(2100, "UN Comtrade", 0.8, "HHI محسوب من حصص المورّدين",
                  "2026-09-17")], "failed": False, "summary": ""}}}
    ch = _find(_dr_charts(monkeypatch, dr), "supplier_concentration")
    assert ch["year"] == ""
    assert I.t("chart_year_unknown", "ar") in ch["note"]
    # ونموذجُ التكلفة ليس قياساً مرصوداً فلا سنةَ تُطلَب منه.
    import silk_economics as E
    steps = E.margin_waterfall(3.1, freight=None, tariff_pct=5.0, vat_pct=0.0,
                               distributor_margin_pct=None,
                               retailer_margin_pct=None)
    ladder = R._chart_declare_year(R._chart_landed_cost_ladder(
        _eco_dr(waterfall=steps, cost_currency="USD"), "ar"), "ar")
    assert I.t("chart_year_unknown", "ar") not in ladder["note"]


def test_every_chart_string_survives_the_client_sanitizer():
    """نصوصُ الرسوم تُطبَع في مُسلَّم العميل تعليقاً وتُرسَم داخل الصورة —
    فطبقةُ اللغة المبسّطة تعيد صياغتَها. جملةٌ تُشوَّه («سعر المصنع من سعر
    المصنع المُدخَل») تصل المالكَ كما هي (مراجعة §58، M6)."""
    import silk_i18n as I
    import silk_reports as SR
    src = pathlib.Path("silk_i18n.py").read_text(encoding="utf-8")
    keys = list(dict.fromkeys(re.findall(r'"(chart_[a-z_0-9]+)":', src)))
    assert len(keys) >= 25, keys
    for k in keys:
        for lang in ("ar", "en"):
            txt = I.t(k, lang, unit="X", years="Y")
            out = SR._lang_safe(SR._client_sanitize(txt, lang), lang)
            assert out.strip() == txt.strip(), f"{k}/{lang}: {out}"
            assert SR._client_forbidden_hits(out, lang) == [], f"{k}/{lang}"


def test_the_chart_backing_check_actually_fires():
    """حارسٌ لا يُشعِل أبداً يمرّ كلَّ اختبارٍ يقيس «صفرَ ملاحظات» — فالقفلُ
    حالةٌ موجبة: قيمةٌ مختلَقةٌ وسلسلةٌ فارغة، كلٌّ تُلتقَط (مراجعة §58، M11)."""
    import silk_quality_gate as Q
    dr = {"missions": {}, "economics": {"hhi": 2100},
          "charts": [{"id": "supplier_concentration", "kind": "gauge",
                      "unit": "index", "value": 2100,
                      "series": [{"label": "متوسطة", "value": 2100}]}]}
    assert Q._check_chart_backing(dr) == [], "قيمةٌ مسنودةٌ تمرّ"
    made_up = dict(dr, charts=[dict(dr["charts"][0], value=3333,
                                    series=[{"label": "م", "value": 3333}])])
    hits = Q._check_chart_backing(made_up)
    assert len(hits) == 1 and hits[0]["check"] == "chart_without_backing_value"
    assert "3333" in hits[0]["note"]
    empty = dict(dr, charts=[{"id": "x", "kind": "bars", "series": []}])
    assert "سلسلةٌ فارغة" in Q._check_chart_backing(empty)[0]["note"]
    # ولا فحصَ بلا مفتاحٍ للرسوم (الرايةُ مطفأة) — لا ملاحظةَ من العدم.
    assert Q._check_chart_backing({"missions": {}}) == []


def test_the_two_number_formatters_print_the_same_number():
    """رقمٌ واحدٌ بقيمتين (`41.2%` في المستند و`41.3%` على الشاشة) يُنسَب إلى
    البيانات وهو من الطبع: `round` المصرفيّ مقابل `Math.round`. التطابقُ
    مقيسٌ بتشغيل المُنسِّق نفسِه في node (يُتخطّى إن غاب)."""
    import json
    import shutil
    import subprocess
    import silk_chart_image as CI
    node = shutil.which("node")
    if not node:
        pytest.skip("node غير متاح — التطابقُ يُقاس حيث يوجد المحرّكان")
    page = pathlib.Path("web/platform.html").read_text(encoding="utf-8")
    fn = "function _chartNum(" + page.split("function _chartNum(")[1] \
        .split("\n}\n")[0] + "\n}\n"
    cases = [("%", 41.25), ("%", 3.0), ("%", 0.05), ("%", 99.95),
             ("index", 2100.5), ("index", 1499.5), ("USD", 120.5),
             ("USD", 3.105), ("USD", 89400000.0), ("USD", 1.5e9),
             ("USD", 2500.0), ("USD", 0.0), ("دينار", 82863.125),
             ("SAR", 1234.5), ("كجم", 0.125)]
    script = (fn + "const C=" + json.dumps(cases) +
              ";console.log(JSON.stringify(C.map(([u,v])=>_chartNum(v,u))));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    js = json.loads(out.stdout)
    py = [CI._num({"unit": u}, v) for u, v in cases]
    assert py == js, [(c, a, b) for c, a, b in zip(cases, py, js) if a != b]


def test_the_page_places_the_economics_group_where_the_docx_does():
    """المجموعةُ كانت مثبَّتةً بعد القسم التاسع (المخاطر) بتعليقٍ يقول إنّها
    تطابق docx — وقسمُ الاقتصاد في docx يُبنى بعد الحلقة كلِّها (§58، M8)."""
    import silk_reports as SR
    page = pathlib.Path("web/platform.html").read_text(encoding="utf-8")
    body = page.split("function viewReportBtn(")[1].split("\nfunction ")[0]
    assert "const _CHART_GROUP_AFTER_ORDINAL = {competition: 6};" in page
    assert SR._CLIENT_SECTION_BY_ORDINAL[6] == "المنافسة والتسعير والهامش"
    assert SR._CLIENT_SECTION_BY_ORDINAL[9] != "المنافسة والتسعير والهامش"
    # وتُعرَض في ذيل السرد (مسارُ «مجموعةٌ لم تجد قسمَها») لا تُسقَط.
    assert '["competition", "economics"].forEach' in body
    # وبلا مجموعةٍ تُحقَن لا يُقسَّم السرد (شكلُ الرايةِ المطفأة كما كان).
    assert "const _needSplit" in body and "html += mdLite(rtext);" in body


def test_the_page_reads_a_value_exactly_as_the_image_renderer_does():
    """`known` كانت تُمرّر `""` (صفراً) و`true` (واحداً) فتُرسَم أعمدةً،
    ومصيّرُ الصورة يطبع «—» لكلَيهما — قراءتان لقيمةٍ واحدة (§58، L2)."""
    import silk_chart_image as CI
    body = _renderer_body()
    assert 'typeof x === "number" && Number.isFinite(x)' in body
    for bad in ("", True, None, "3"):
        assert CI._known(bad) is False, bad
    assert CI._known(3) and CI._known(3.5)
    # ومقياسُ المقياس (gauge) موجبٌ في المصيّرين (لا قسمةً على صفر).
    assert "Math.max(1e-9," in body
    assert CI.chart_png({"id": "g", "kind": "gauge", "unit": "index",
                         "title": "ت", "value": 0.5,
                         "bands": [{"label": "أ", "from": 0, "to": 0}],
                         "series": [{"label": "أ", "value": 0.5}]}, "ar")


def test_a_malformed_series_never_reaches_the_export():
    """عقدُ `chart_png`: «أيُّ استثناءٍ ⇒ None». `_rows`/`caption` كانتا خارج
    الحماية فيمرّ الاستثناءُ إلى التصدير (§58، L3)."""
    import silk_chart_image as CI
    for bad in (3, "x", {"a": 1}):
        assert CI.chart_png({"id": "b", "kind": "bars", "series": bad}) is None
    assert CI.chart_png({"id": "b", "kind": "bars", "series": None}) is None
    assert CI.caption(None) == "" and CI.caption({}) == ""
