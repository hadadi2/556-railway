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
    assert body.count('direction: "ltr"') >= 2
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
    page = pathlib.Path("web/platform.html").read_text(encoding="utf-8")
    body = page.split("function viewReportBtn(")[1].split("\nfunction ")[0]
    assert 'data-role="rep-charts"' in body
    assert "renderReportCharts(chartsHost, _charts)" in body
    assert "dr.charts" in body
