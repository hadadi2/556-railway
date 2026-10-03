"""الدرس 290 — المرحلة الأولى من «مقترح تصحيح إنتاج منصة سلك» (2026-10-03).

الدليل: تقريرا الدراسة ٩ (قهوة محمصة 090121 → ماليزيا) حملا «Unclassified area 699» أكبرَ مورّد
بـ26.7% و«757» — رمزا كومتريد للهند وسويسرا. `partner_name` كان يقرأ `countries.csv` (أرقام ISO:
الهند 356، سويسرا 756) فتسقط رموز كومتريد الخاصة. هرمتي.
Run: python3 -m pytest tests/test_proposal_phase1.py -q
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 1.2 رموز شركاء كومتريد ─────────────────────────────────────────────────

def test_comtrade_specific_partner_codes_resolve_to_countries():
    import silk_data_layer as DL
    assert DL.partner_name("699") == "India"
    assert DL.partner_name("757") == "Switzerland"
    assert DL.partner_name("842") == "United States"
    assert DL.partner_name("251") == "France"
    assert "Taiwan" in DL.partner_name("490")
    assert DL.partner_name("899") == "Areas, nes"
    assert DL.comtrade_partner_iso3("699") == "IND"
    assert DL.comtrade_partner_iso3("356") == "IND"          # رقم ISO يبقى صالحاً
    assert DL.comtrade_partner_iso3("899") is None            # تجميع لا دولة
    # طلبات التعرفة تحتاج أرقام ISO — الخريطة المقلوبة لا تتغيّر.
    assert DL.ISO3_TO_M49["IND"] == "356" and DL.ISO3_TO_M49["USA"] == "840"


def test_aggregate_codes_are_marked_and_unknown_codes_are_not():
    import silk_data_layer as DL
    assert DL.is_aggregate_partner("0") and DL.is_aggregate_partner("899")
    assert not DL.is_aggregate_partner("699") and not DL.is_aggregate_partner("360")
    assert not DL.is_aggregate_partner("998")                # مجهول ≠ تجميع


def _recs(rows, key="partnerCode"):
    return [{key: c, "primaryValue": v} for c, v in rows]


def test_market_imports_ranks_countries_and_keeps_aggregates_out_of_competitors():
    import silk_data_layer_v2 as V2
    recs = _recs([(0, 100.0), (699, 30.0), (757, 20.0), (899, 10.0), (360, 40.0)])
    with mock.patch.object(V2, "comtrade_trade", return_value=recs):
        mi = V2.market_imports("090121", "458", 2024)
    comps = [c.value for c in mi["competitors"]]
    assert [c["code"] for c in comps] == ["360", "699", "757"]
    assert [c["partner"] for c in comps] == ["Indonesia", "India", "Switzerland"]
    assert [c["share"] for c in comps] == [40.0, 30.0, 20.0]  # حصةٌ من إجمالي الواردات كلها
    assert [a["code"] for a in mi["aggregates"]] == ["899"]
    assert mi["aggregates"][0]["partner"] == "Areas, nes"


def test_unknown_code_stays_in_the_competitor_set():
    """الرمز المجهول قد يكون دولة — يبقى داخل الحصص وHHI (لا تجميل للتركّز بلا دليل)."""
    import silk_data_layer_v2 as V2
    recs = _recs([(0, 100.0), (998, 60.0), (360, 40.0)])
    with mock.patch.object(V2, "comtrade_trade", return_value=recs):
        mi = V2.market_imports("090121", "458", 2024)
    assert [c.value["code"] for c in mi["competitors"]] == ["998", "360"]


def test_mirror_competitors_skip_aggregate_reporters():
    import silk_data_layer_v2 as V2
    recs = _recs([(699, 30.0), (899, 10.0), (360, 60.0)], key="reporterCode")
    with mock.patch.object(V2, "comtrade_trade", return_value=recs):
        comps = V2.market_competitors_mirror("090121", "458", 2024)
    assert [c.value["code"] for c in comps] == ["360", "699"]


def _gate_dr(top):
    return {"missions": {"competitors": {"findings": [
        {"value": {"year": 2024, "hhi": 1300, "supplier_count": 12, "top_suppliers": top},
         "source": "UN Comtrade", "note": "summary"}]}}}


def test_unknown_partner_gate_is_graded():
    import silk_quality_gate as QG
    big = [{"partner": "Indonesia", "share": 40.0, "code": "360"},
           {"partner": "Unclassified area (Comtrade code 998)", "share": 26.7, "code": "998"}]
    out = QG._check_unknown_partner_codes(_gate_dr(big))
    assert out and out[0]["check"] == "unknown_partner_code" and out[0]["repairable"] is False
    small = [{"partner": f"Country {i}", "share": 10.0, "code": str(100 + i)} for i in range(6)] + [
        {"partner": "Unclassified area (Comtrade code 998)", "share": 0.4, "code": "998"}]
    assert QG._check_unknown_partner_codes(_gate_dr(small)) == []
    assert "Comtrade code" not in str(out[0]["note"])        # ملاحظةٌ بلغة القارئ


def test_unknown_partner_minor_goes_to_ops_log_once():
    import silk_data_layer as DL
    DL._UNKNOWN_PARTNERS_SEEN.clear()
    with mock.patch("silk_ops_log.record_error") as rec:
        DL.partner_name("997")
        DL.partner_name("997")
    assert rec.call_count == 1 and rec.call_args[0][0] == "unknown_partner_code"


# ── 1.1 رمز HS نصٌّ لا رقم ────────────────────────────────────────────────

def test_hs_code_is_not_a_known_number_or_a_tam_candidate():
    import silk_evals as E
    import silk_deep_pillars as DP
    assert 90121.0 not in E._extract_numbers("HS090121 إجمالي استيراد Malaysia 2024, USD")
    assert 90121.0 not in E._extract_numbers("البند HS 0901.21 في ماليزيا")
    assert 89_400_000.0 in E._extract_numbers("HS090121 بلغت 89,400,000 دولار")
    dr = {"missions": {"trade_flow": {"findings": [
        {"value": "واردات HS 200811 بلغت 350 مليون دولار", "note": "واردات 2024", "data_year": 2024}]}}}
    pi = DP.build_pillar_inputs(dr)
    assert pi["market_attractiveness"]["tam_usd"] == 350_000_000.0


def test_itc_hs6_restores_a_lost_leading_zero_but_never_pads_a_heading():
    import silk_itc_tariff as I
    assert I.hs6("090121") == "090121" and I.hs6("90121") == "090121"
    assert I.hs6("0901") == ""


def test_gate_blocks_a_number_equal_to_the_hs_code():
    import silk_quality_gate as QG
    view = {"hs_code": "090121", "deep_research": {"report": {"text":
            "إجمالي واردات ماليزيا 90,121 دولار في 2024."}}}
    out = QG._check_hs_code_as_value(view)
    assert out and out[0]["check"] == "hs_code_as_value" and out[0]["repairable"] is False
    view["deep_research"]["report"]["text"] = "البند HS 090121 (قهوة محمصة) — الواردات 89.4 مليون دولار."
    assert QG._check_hs_code_as_value(view) == []


# ── 1.3 سنة أساس واحدة ────────────────────────────────────────────────────

def _pt(year, value, mirrored=False):
    from silk_data_layer import DataPoint
    return DataPoint(value, "UN Comtrade (مرآة)" if mirrored else "UN Comtrade",
                     0.6 if mirrored else 0.9,
                     f"HS090121 إجمالي استيراد Malaysia من العالم {year}, USD", "2026-10-03",
                     status="mirrored" if mirrored else "", data_year=year)


def test_partial_rule_applies_to_the_latest_mirrored_year_only():
    """قرار المالك: «جزئية» = أحدث سنة فقط، ولم تُبلِغ عنها السوق نفسها، ومرآتها < 80% من متوسط سنتين."""
    import silk_deep_pillars as DP
    low_mirror = {"trade_flow": {"findings": [_pt(2022, 100e6), _pt(2023, 100e6), _pt(2024, 50e6, True)]}}
    s = DP.import_series(low_mirror)
    assert [p["partial"] for p in s["series"]] == [False, False, True]
    assert DP.base_year(low_mirror) == 2023
    real_drop = {"trade_flow": {"findings": [_pt(2022, 100e6), _pt(2023, 100e6), _pt(2024, 70e6)]}}
    assert DP.base_year(real_drop) == 2024                     # هبوط 30% مُبلَّغ مباشرةً يبقى
    old_mirror = {"trade_flow": {"findings": [_pt(2021, 40e6, True), _pt(2022, 100e6), _pt(2023, 100e6)]}}
    assert not any(p["partial"] for p in DP.import_series(old_mirror)["series"])


def test_mirrored_raw_evidence_reaches_the_series():
    import silk_deep_pillars as DP
    raw = [{"value": 74_870_000.0, "source": "UN Comtrade", "confidence": 0.9, "data_year": 2023,
            "note": "HS090121 إجمالي استيراد Malaysia من العالم 2023, USD"},
           {"value": 89_400_000.0, "source": "UN Comtrade (مرآة)", "confidence": 0.6, "data_year": 2024,
            "status": "mirrored", "note": "HS090121 تقدير استيراد Malaysia 2024 من مرآة"}]
    m = {"trade_flow": {"findings": [{"value": "نمت الواردات", "note": "claim", "raw_evidence": raw}]}}
    assert [p["year"] for p in DP.import_series(m)["series"]] == [2023, 2024]


def test_series_augment_fetches_missing_years_once():
    import silk_missions as SM
    from silk_agents import AgentReport
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market("Malaysia")
    report = AgentReport("LLMMissionAgent:trade_flow", [_pt(2024, 89.4e6)], False, "s")
    asked = []

    def fake(args, ctx):
        asked.append(list(args["years"]))
        return [_pt(y, 70e6 + y) for y in args["years"]]
    with mock.patch("silk_llm_runtime._tool_comtrade_imports", side_effect=fake):
        SM._augment_trade_flow_series(report, "090121", ref)
        SM._augment_trade_flow_series(report, "090121", ref)
    import datetime as _dt
    y0 = _dt.date.today().year - 1
    assert asked == [[y for y in range(2019, y0 + 1) if y != 2024]]
    years = sorted(dp.data_year for dp in report.findings)
    assert years == list(range(2019, y0 + 1))


def test_competition_summary_uses_the_base_year_and_labels_a_fallback():
    import silk_missions as SM
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market("Malaysia")
    trade = AgentReport("LLMMissionAgent:trade_flow", [_pt(2023, 74.87e6), _pt(2024, 89.4e6)], False, "s")
    comp = AgentReport("LLMMissionAgent:competitors", [], False, "s")
    calls = []

    def fake(hs, market, year=None, top_n=10, deadline_s=None):
        calls.append(year)
        if year == 2024:
            return [DataPoint(None, "UN Comtrade", 0.0, "لا سجل", "2026-10-03")]
        return [DataPoint({"year": 2023, "hhi": 1307, "supplier_count": 40, "top_suppliers": []},
                          "UN Comtrade", 0.9, "HS090121 مورّدو Malaysia 2023", "2026-10-03")]
    with mock.patch("silk_llm_runtime.competition_summary_findings", side_effect=fake):
        SM._augment_competitors_structured(comp, "090121", ref, trade)
    assert calls[0] == 2024
    summary = comp.findings[0]
    assert summary.value["year"] == 2023 and "أحدث سنة متاحة" in summary.note and "2024" in summary.note


def test_tam_and_ledger_latest_year_come_from_the_base_year():
    import silk_deep_pillars as DP
    m = {"trade_flow": {"findings": [
        _pt(2023, 74_870_000.0), _pt(2024, 89_400_000.0),
        {"value": "بلغت واردات ماليزيا 120 مليون دولار", "note": "تقدير ويب 2024", "data_year": 2024}]}}
    pi = DP.build_pillar_inputs({"missions": m})
    assert pi["market_attractiveness"]["tam_usd"] == 89_400_000.0


def test_chart_year_mismatch_reads_the_range_end():
    import silk_fact_ledger as FL
    view = {"deep_research": {"charts": [{"id": "imports_trend", "year": "2019–2023"}]}}
    out = FL._chart_year_findings(view, 2024)
    assert out and out[0]["check"] == "chart_year_mismatch"
    view["deep_research"]["charts"][0]["year"] = "2019–2024"
    assert FL._chart_year_findings(view, 2024) == []
