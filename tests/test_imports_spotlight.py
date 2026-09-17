"""الموجة الرابعة — الدرس ٢٥٨: وارداتُ السوق تتقدّم إلى وجه التقرير.

imports spotlight: the target market's imports of the product — value with
its year, the multi-year series the trade_flow mission already fetches, the
Saudi share — reach the client surfaces behind `SILK_IMPORTS_SPOTLIGHT`.

**المقيس قبل الكتابة:** بعثةُ `trade_flow` تأمر خمسَ سنوات، والأداةُ تُصدِر
نقطةً لكلّ سنة بـ`data_year`، وكلُّها تصل `_metric_findings` — ثم
`_numeric_with_source` يختار الأحدثَ **ويطرح البقيّة**. فالسلسلةُ تُقرَأ من نفس
القائمة بصفر نداءٍ جديد. والدقّةُ الزائفة («51,358,600.874») مصدرُها
`sum(vals)` بلا تقريبٍ في الأداة ثم نسخُ الكاتب لها من كتلة الحقائق.

**حدُّ الدليل المُعلَن:** المدوّناتُ الستّ عشرة تحمل سنةً واحدة (١٥) أو ثلاثاً
(١) ولا `raw_evidence` — فهي لا تُثبِت توفّرَ السلسلة في الإنتاج؛ ما يُثبِته
هذا الملف أنّ الشكلَ الذي تُخرِجه الأداةُ **فعلاً** يُقرَأ صحيحاً (الدرس ١٨٦)
وأنّ سنةً واحدةً تُعرَض رقماً بسنته بلا مسارٍ مختلَق.
"""
import os
import re
from types import SimpleNamespace

import pytest

import silk_deep_pillars as P
import silk_render as R

_FLAGS = ("SILK_CLIENT_METRIC_PRIVACY", "SILK_IMPORTS_SPOTLIGHT",
          "SILK_REPORT_CHARTS", "SILK_CONFIDENCE_DISCIPLINE")

_BY_YEAR = {2021: 51358600.874, 2022: 60100000.0, 2023: None,
            2024: 89400000.0}


def _clear(monkeypatch) -> None:
    for f in _FLAGS:
        monkeypatch.delenv(f, raising=False)


def _tool_findings(monkeypatch, by_year: dict) -> list:
    """حقائقُ التدفّق كما تُخرِجها أداةُ الإنتاج نفسُها — لا مدوّنةٌ يدوية."""
    import silk_llm_runtime as RT

    def _fake_trade(hs, m49, year, flow="M", partner=0):
        v = by_year.get(int(year), "absent")
        if v is None:
            return None                       # تعذّر الجلب (fetch_failed)
        if v == "absent":
            return []
        return [{"primaryValue": v, "netWgt": 0, "partnerCode": 0}]

    monkeypatch.setattr(RT, "comtrade_trade", _fake_trade)
    monkeypatch.setattr(RT, "comtrade_trade_mirror_total",
                        lambda *a, **k: None)
    ctx = {"hs_code": "090121",
           "market": SimpleNamespace(m49=458, name_en="Malaysia",
                                     iso3="MYS", name_ar="ماليزيا")}
    return RT._tool_comtrade_imports({"years": sorted(by_year)}, ctx)


def _result(findings: list, saudi: "float | None" = 3.5) -> dict:
    comps = {"market_size": {"value": 89400000.0, "source": "UN Comtrade",
                             "confidence": 0.9, "data_year": 2024,
                             "note": ""}}
    if saudi is not None:
        comps["saudi_position"] = {"value": saudi, "source": "UN Comtrade",
                                   "confidence": 0.9, "data_year": 2024,
                                   "note": ""}
    return {
        "market": {"name_ar": "ماليزيا", "name_en": "Malaysia", "iso3": "MYS"},
        "product": "قهوة محمصة", "hs_code": "090121",
        "deep_research": {
            "missions": {"trade_flow": {"findings": findings, "failed": False,
                                        "summary": "تدفّق"}},
            "verdict": {"verdict": "CONDITIONAL-GO", "confidence": 0.8},
            "report": {"text": "## 1. الخلاصة التنفيذية\nنوصي بدخولٍ مشروط.\n\n"
                               "## 3. نظرة عامة على السوق وحجمه\nنص.\n"}},
        "markets": [{"country": "ماليزيا", "iso3": "MYS", "total_score": 0.64,
                     "confidence": 0.8, "rank": 1, "deep": True,
                     "components": comps,
                     "decision": {"schema": "silk.decision/v1",
                                  "verdict": "CONDITIONAL-GO", "score": 0.64,
                                  "confidence": 0.8, "weights_option": "A",
                                  "conditions": [],
                                  "pillars": {"market": {"value": 0.6},
                                              "competition": {"value": 0.5},
                                              "profit": {"value": None}}}}]}


# ── (١) السلسلةُ من شكل الأداة الحقيقيّ، والفجوةُ مُعلَنةٌ لا مملوءة ──────────

def test_series_is_read_from_the_tool_shape_and_gaps_are_declared(monkeypatch):
    findings = _tool_findings(monkeypatch, _BY_YEAR)
    s = P.import_series({"trade_flow": {"findings": findings}})
    assert [(p["year"], p["value"]) for p in s["series"]] == [
        (2021, 51358600.874), (2022, 60100000.0), (2024, 89400000.0)]
    assert s["years_missing"] == [2023], "سنةُ الجلب الفاشل تُعلَن"
    assert all(p["value"] is not None for p in s["series"]), "لا صفرَ مختلَق"
    assert s["growth_pct"] == 74.1 and s["cagr_pct"] == 20.3
    # القيمةُ المخزَّنة كما هي — لا تقريبَ في السلسلة نفسها.
    assert s["series"][0]["value"] == 51358600.874


def test_single_year_has_no_trend_and_says_so(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    findings = _tool_findings(monkeypatch, {2024: 89400000.0})
    s = P.import_series({"trade_flow": {"findings": findings}})
    assert len(s["series"]) == 1 and s["growth_pct"] is None
    v = R.build_view(_result(findings))
    imp = v["deep_research"]["imports"]
    assert "89.4 مليون دولار" in imp["value_line"] and "2024" in imp["value_line"]
    assert "growth_line" not in imp
    assert "سنة واحدة" in imp["note"]


def test_unit_price_rows_never_enter_the_series(monkeypatch):
    """«متوسط سعر استيراد» يحمل إبرةَ الواردات نفسَها — المدى يُسقِطه."""
    from silk_data_layer import DataPoint
    findings = _tool_findings(monkeypatch, {2024: 89400000.0}) + [
        DataPoint(5.1234, "UN Comtrade", 0.7,
                  "HS090121 متوسط سعر استيراد Malaysia 2024 (القيمة ÷ الوزن)",
                  "2026-09-17")]
    s = P.import_series({"trade_flow": {"findings": findings}})
    assert [p["value"] for p in s["series"]] == [89400000.0]


# ── (٢) العرضُ: خلف الراية فقط، وباللغتين، وبلا رقمٍ مخزَّنٍ يتغيّر ──────────

def test_view_carries_imports_only_behind_the_flag(monkeypatch):
    _clear(monkeypatch)
    findings = _tool_findings(monkeypatch, _BY_YEAR)
    off = R.build_view(_result(findings))
    assert "imports" not in off["deep_research"]
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    on = R.build_view(_result(findings))
    imp = on["deep_research"]["imports"]
    assert imp["latest_year"] == 2024 and imp["latest_value_usd"] == 89400000.0
    assert "نمو إجمالي 74.1%" in imp["growth_line"]
    assert "20.3%" in imp["growth_line"]
    assert "3.5%" in imp["saudi_line"]
    assert "2023" in imp["gap_line"]
    en = R.build_view(_result(findings), "en")["deep_research"]["imports"]
    assert en["value_line"].startswith("The market imported USD 89.4 million")
    assert "grew 74.1%" in en["growth_line"]
    # لا قيمةَ مخزَّنةً تتغيّر بين الحالتين (سكربتٌ لا عين).
    for key in ("markets",):
        assert off[key][0]["components_detail"] == on[key][0]["components_detail"]
    assert ([f["value"] for f in off["deep_research"]["missions"]["trade_flow"]["findings"]]
            == [f["value"] for f in on["deep_research"]["missions"]["trade_flow"]["findings"]])


def test_no_imports_block_without_a_single_figure(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    findings = _tool_findings(monkeypatch, {2024: None})
    v = R.build_view(_result(findings))
    assert v["deep_research"]["imports"] is None, "لا هيكلَ فارغ"


# ── (٣) الدقّةُ الزائفة: مُصلِحٌ + فحصٌ زوجاً، والمخزَّنُ لا يُمَسّ ────────────

def test_amount_false_precision_fixer_rounds_only_large_amounts():
    fix = R._fix_amount_false_precision
    assert fix("بلغت 51,358,600.874 دولار") == "بلغت 51,358,600.87 دولار"
    assert fix("12345.6789") == "12345.68"
    assert fix("بنسبة 12.4166% وإحداثيّ 24.7136 وسعر 5.1234") == \
        "بنسبة 12.4166% وإحداثيّ 24.7136 وسعر 5.1234"
    assert fix("89,400,000 و 1,234.50") == "89,400,000 و 1,234.50"
    assert fix("") == ""


def test_amount_fixer_and_check_leave_the_appendix_untouched(monkeypatch):
    """مراجعة §58: الدقّةُ الكاملة في «الملاحق» مشروعةٌ — لا تقريبَ ولا فحص."""
    import silk_quality_gate as Q
    text = ("## 3. نظرة عامة\nبلغت 51,358,600.874 دولار.\n\n"
            "## 11. الملاحق\nالقيمة الكاملة 51,358,600.874 دولار.")
    out = R._fix_amount_false_precision(text)
    assert out.count("51,358,600.874") == 1 and out.count("51,358,600.87 ") == 1
    assert out.endswith("الكاملة 51,358,600.874 دولار.")
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    assert Q._check_amount_false_precision(out) == []


def test_saudi_share_never_borrows_the_imports_year(monkeypatch):
    """مراجعة §58: حصةٌ بلا `data_year` تُقال بلا سنةٍ مُستعارة."""
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    findings = _tool_findings(monkeypatch, {2024: 89400000.0})
    res = _result(findings)
    res["markets"][0]["components"]["saudi_position"]["data_year"] = None
    imp = R.build_view(res)["deep_research"]["imports"]
    assert "3.5%" in imp["saudi_line"] and "2024" not in imp["saudi_line"]
    assert "لم يذكرها المصدر" in imp["saudi_line"]


def test_growth_without_cagr_reads_cleanly_in_english(monkeypatch):
    """مراجعة §58: انكماشٌ إلى الصفر يُعطي CAGR غير محسوب — لا «— of —»."""
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    import silk_trend
    monkeypatch.setattr(silk_trend, "cagr_pct", lambda pairs: None)
    findings = _tool_findings(monkeypatch, {2021: 5000000.0, 2024: 2500000.0})
    en = R.build_view(_result(findings), "en")["deep_research"]["imports"]
    assert "shrank 50%" in en["growth_line"]
    assert "of —" not in en["growth_line"] and "not computed" in en["growth_line"]


def test_amount_false_precision_check_pairs_with_the_fixer(monkeypatch):
    import silk_quality_gate as Q
    _clear(monkeypatch)
    assert Q._check_amount_false_precision("51,358,600.874") == []
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    out = Q._check_amount_false_precision("واردات 51,358,600.874 دولار")
    assert out and out[0]["check"] == "amount_false_precision"
    assert out[0]["repairable"] is True
    assert Q._check_amount_false_precision(
        R._fix_amount_false_precision("واردات 51,358,600.874 دولار")) == []


def test_facts_block_shows_two_decimals_but_the_stored_value_is_untouched(monkeypatch):
    from silk_data_layer import DataPoint
    import silk_ai_judge as J
    dp = DataPoint(51358600.874, "UN Comtrade", 0.9, "إجمالي استيراد 2021",
                   "2026-09-17", data_year=2021)
    rep = SimpleNamespace(agent_name="trade_flow", failed=False, findings=[dp])
    _clear(monkeypatch)
    assert "51358600.874" in J._facts([rep])
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    block = J._facts([rep])
    assert "51358600.87" in block and "51358600.874" not in block
    assert dp.value == 51358600.874, "الرقمُ المخزَّن كما هو"


# ── (٤) docx العميل: «السوق بالأرقام» يفتتح بالواردة ────────────────────────

def test_client_docx_opens_market_numbers_with_the_imports_block(monkeypatch, tmp_path):
    pytest.importorskip("docx")
    from tests.conftest import docx_all_text
    import silk_reports as SR
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_HERMETIC", "1")
    findings = _tool_findings(monkeypatch, _BY_YEAR)
    off = docx_all_text(SR.render_client_docx(
        R.build_view(_result(findings)), str(tmp_path / "off.docx")))
    assert "واردات السوق من هذا الصنف" not in off
    monkeypatch.setenv("SILK_IMPORTS_SPOTLIGHT", "1")
    v = R.build_view(_result(findings))
    text = docx_all_text(SR.render_client_docx(v, str(tmp_path / "on.docx")))
    assert "واردات السوق من هذا الصنف" in text
    assert "89.4 مليون دولار" in text
    assert "نمو إجمالي 74.1%" in text
    assert "2023" in text and "لم تُقدَّر" in text
    assert "51.36 مليون دولار" in text, "جدولُ السنوات بمنزلتين"
    assert "51,358,600.874" not in text
