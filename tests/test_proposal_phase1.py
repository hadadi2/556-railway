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
