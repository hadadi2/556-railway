"""الدرس ٢٩٢ — رمز السوق نفسها لكومتريد (أقفال hermetic).

السوق تُحلّ برقم ISO من countries.csv (الهند 356، أمريكا 840، فرنسا 250…)، وكومتريد يعرف
هذه الدول برموزه الخاصة (699، 842، 251…). الدرس ٢٩٠ ترجم رموز الشركاء **الواردة** فقط،
فكانت دراسة سوقها الهند تطلب `reporterCode=356` وتعود فارغة.
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sent(reporter, partner, flow="M"):
    import silk_data_layer as D
    seen = {}

    def fake(url, params, **kw):
        seen.update(params)
        return {"data": []}

    with mock.patch.object(D, "_cached_get", side_effect=fake):
        D.comtrade_trade("090121", reporter, 2024, flow=flow, partner=partner)
    return seen


def test_market_reporter_code_is_translated_for_comtrade():
    assert _sent(356, "all")["reporterCode"] == "699"     # الهند
    assert _sent("840", 0)["reporterCode"] == "842"       # أمريكا
    assert _sent(250, 0)["reporterCode"] == "251"         # فرنسا


def test_mirror_partner_code_is_translated_for_comtrade():
    sent = _sent("all", 840, flow="X")
    assert sent["partnerCode"] == "842" and "reporterCode" not in sent
    assert _sent(682, 356, flow="X")["partnerCode"] == "699"


def test_codes_comtrade_shares_with_iso_are_unchanged():
    assert _sent(458, 682)["reporterCode"] == "458"       # ماليزيا
    assert _sent(458, 682)["partnerCode"] == "682"        # السعودية
    assert _sent(458, 0)["partnerCode"] == "0"


def test_iso3_to_m49_stays_iso_for_wits_and_wto():
    from silk_data_layer import ISO3_TO_M49
    assert ISO3_TO_M49["IND"] == "356" and ISO3_TO_M49["USA"] == "840"


def test_ranker_maps_a_comtrade_reporter_code_without_reporter_iso():
    import silk_market_ranker as R
    recs = [{"reporterCode": 699, "primaryValue": 1000.0},
            {"reporterCode": 842, "primaryValue": 500.0}]
    with mock.patch("silk_data_layer.comtrade_trade", return_value=recs):
        rows = R.world_import_totals("090121", 2024)
    assert [r["iso3"] for r in rows] == ["IND", "USA"]


def test_world_export_totals_maps_comtrade_codes_and_returns_iso_m49():
    import silk_market_ranker as R
    recs = [{"reporterCode": 842, "primaryValue": 900.0},
            {"reporterCode": 76, "reporterISO": "BRA", "primaryValue": 800.0}]
    with mock.patch("silk_data_layer.comtrade_trade", return_value=recs):
        rows = R.world_export_totals("090121", 2024)
    assert [(r["iso3"], r["m49"]) for r in rows] == [("USA", "840"), ("BRA", "076")] \
        or [(r["iso3"], r["m49"]) for r in rows] == [("USA", "840"), ("BRA", "76")]


def test_import_totals_carry_the_iso_m49_not_the_comtrade_code():
    import silk_market_ranker as R
    with mock.patch("silk_data_layer.comtrade_trade",
                    return_value=[{"reporterCode": 699, "primaryValue": 10.0}]):
        rows = R.world_import_totals("090121", 2024)
    assert rows[0]["m49"] == "356"


def test_collector_stores_comtrade_partner_as_iso3(monkeypatch, tmp_path):
    import silk_collectors as C
    import silk_store
    monkeypatch.setenv("SILK_STORE_DB", str(tmp_path / "store.db"))
    monkeypatch.setenv("COMTRADE_PACE_S", "0")
    silk_store.migrate()
    written = []
    monkeypatch.setattr(silk_store, "upsert_trade_flows",
                        lambda rows: written.extend(rows) or len(rows))
    monkeypatch.setattr(C, "comtrade_budget_left", lambda: 10)
    recs = [{"partnerCode": 699, "primaryValue": 5.0}, {"partnerCode": 0, "primaryValue": 9.0}]
    with mock.patch("silk_data_layer.comtrade_trade", return_value=recs):
        C.collect_comtrade("090121", [{"iso3": "MYS", "m49": "458"}], 2024, pace_seconds=0)
    assert {r["partner_iso3"] for r in written} == {"IND", "WLD"}


def test_store_reader_merges_old_numeric_and_new_iso3_rows(monkeypatch, tmp_path):
    import silk_store
    monkeypatch.setenv("SILK_STORE_DB", str(tmp_path / "store.db"))
    silk_store.migrate()
    rows = [{"hs6": "090121", "reporter_iso3": "MYS", "partner_iso3": p, "year": 2024,
             "flow": "M", "value_usd": v} for p, v in (("699", 100.0), ("IDN", 100.0))]
    silk_store.upsert_trade_flows(rows)
    import time
    time.sleep(1.1)
    silk_store.upsert_trade_flows([{**rows[0], "partner_iso3": "IND", "value_usd": 110.0}])
    out = silk_store.market_imports_from_store("090121", "MYS", 2024)
    by = {p["iso3"]: p["value_usd"] for p in out["partners"]}
    assert by == {"IND": 110.0, "IDN": 100.0}


def test_empty_area_map_is_not_cached(monkeypatch):
    import silk_data_layer as D
    monkeypatch.setattr(D, "_ISO_TO_COMTRADE", {})
    monkeypatch.setattr(D, "_country_m49_index", lambda: {})
    assert D.comtrade_area_code(356) == 356
    monkeypatch.undo()
    assert D.comtrade_area_code(356) == "699"
