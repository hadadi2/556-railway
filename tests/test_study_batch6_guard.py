"""الدفعة ٦ — الحراسة والتعميم (P6-2…P6-7) لنمط «دراسة السوق»."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── P6-2 ───────────────────────────────────────────────────────────────
def _dp(value, note="", status=""):
    from silk_data_layer import DataPoint
    return DataPoint(value, "World Bank", 0.95 if value is not None else 0.0, note, "2026-09-28",
                     status=status, data_year=2023 if value is not None else None)


def test_public_indicator_retries_then_succeeds_with_unit_url_status():
    import silk_data_layer as D
    seq = [_dp(None, "PV.EST fetch failed for MYS: boom"), _dp(None, status="fetch_failed"), _dp(0.3, "PV.EST (2023)")]
    with patch.object(D, "_world_bank_for_year", side_effect=seq) as m:
        dp = D.world_bank("MYS", "PV.EST", 2023)
    assert m.call_count == 3 and dp.value == 0.3
    assert dp.status == "ok" and dp.unit and dp.url.endswith("/PV.EST") and dp.data_year == 2023


def test_permanent_failure_is_logged_not_silent():
    import silk_data_layer as D
    import silk_ops_log
    logged = []
    with patch.object(D, "_world_bank_for_year", return_value=_dp(None, "x fetch failed for MYS")) as m, \
            patch.object(silk_ops_log, "record_error", side_effect=lambda k, r, c=None: logged.append(k)):
        dp = D.world_bank("MYS", "PA.NUS.FCRF", None)
    assert m.call_count == 3 and dp.value is None and dp.status == "fetch_failed"
    assert logged == ["data_pipeline_error"]


def test_no_published_value_is_not_retried():
    import silk_data_layer as D
    with patch.object(D, "_world_bank_for_year", return_value=_dp(None, "PV.EST: no value returned for XXX")) as m:
        D.world_bank("XXX", "PV.EST", None)
    assert m.call_count == 1


def test_other_indicators_keep_single_attempt():
    import silk_data_layer as D
    with patch.object(D, "_world_bank_for_year", return_value=_dp(None, "NY.GDP fetch failed for MYS")) as m:
        D.world_bank("MYS", "NY.GDP.MKTP.KD.ZG", None)
    assert m.call_count == 1


# ── P6-3 ───────────────────────────────────────────────────────────────
def test_stale_verification_is_flagged_and_fresh_kept():
    import datetime as dt
    from silk_study_case import verified_label
    today = dt.date(2026, 9, 28)
    assert verified_label("2026-09-23", today) == "2026-09-23"
    assert verified_label("2025-12-01", today) == "2025-12-01 (يُعاد التحقق)"
    assert verified_label("", today) is None


def test_live_case_requirement_rows_carry_verification_and_tax_wording():
    from silk_study_case import build_case
    c = build_case({"deep_research": {}, "product": "قهوة", "hs_code": "090121", "market": "Malaysia"})
    rows = c["requirements"]["rows"]
    assert rows and all(r["verified_at"] is None or r["verified_at"].startswith("20") for r in rows)
    for r in rows:
        if "ضريبة" in r["item"] and "%" not in r["item"]:
            assert "يُحدَّد المعدل من جدول" in r["item"]


# ── P6-4 ───────────────────────────────────────────────────────────────
def test_singapore_is_tagged_reexport_hub_in_live_supplier_rows():
    from silk_study_case import build_case, reexport_hubs
    import silk_deep_pillars
    assert "SGP" in reexport_hubs()
    rows = [{"partner": "Singapore", "share": 16.0}, {"partner": "Indonesia", "share": 12.0},
            {"partner": "Viet Nam", "share": 10.0}]
    with patch.object(silk_deep_pillars, "top_supplier_shares", return_value=(rows, {"year": 2024})):
        c = build_case({"deep_research": {}, "product": "قهوة", "hs_code": "090121", "market": "Malaysia"})
    kinds = {t["iso3"]: t["kind"] for t in c["suppliers"]["top"]}
    assert kinds.get("SGP") == "reexport_hub" and kinds.get("IDN") == "producer"
    from silk_study_numbers import compute
    assert compute(c)["hub"]["iso3"] == "SGP"
