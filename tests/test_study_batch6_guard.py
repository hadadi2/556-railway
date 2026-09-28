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
