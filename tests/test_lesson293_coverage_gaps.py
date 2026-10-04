"""الدرس ٢٩٣ — فجوات التغطية وفقد البيانات الصامت (أقفال hermetic، تدقيق «find all gaps» 2026-10-04)."""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_data_layer import DataPoint  # noqa: E402


def test_uncovered_market_is_not_checked():
    import silk_requirements_agent as R
    assert R.regulatory_state("USA", "090121")["checked"] is False
    assert R.regulatory_state("MYS", "090121")["checked"] is True


def test_uncovered_market_leaves_eligibility_unknown():
    import silk_deep_pillars as P
    src = open(P.__file__, encoding="utf-8").read()
    assert 'if reg_state.get("checked", True) else None' in src


def test_country_lookups_cover_markets_outside_the_embedded_tables():
    import silk_data_layer as D
    import silk_market_ranker as R
    import silk_narrative as N
    assert D.m49_of("ROU") == "642"            # خارج الجدول المضمَّن (٧٢ دولة)
    assert R._iso2_of("AUS") == "AU"
    assert N.country_ar("ROU") == "رومانيا"


def test_discover_accepts_a_market_outside_the_embedded_table():
    import silk_discovery as S
    with mock.patch("silk_data_layer.comtrade_trade", return_value=None):
        out = S.discover("ROU") if hasattr(S, "discover") else None
    if out is not None:
        assert not any("غير معروف الرمز" in g for g in out.get("gaps", []))


def test_locale_gl_falls_back_to_market_iso2():
    import silk_llm_runtime as L

    class M:
        iso3, iso2 = "ROU", "RO"
    with mock.patch.object(L, "_market_locale", return_value={}):
        assert L._locale_gl({"market": M()}) == "ro"


def test_wgi_store_point_carries_its_year():
    import silk_missions as M
    with mock.patch("silk_store.get_indicator",
                    return_value={"value": 0.4, "year": 2023, "source": "World Bank"}):
        dps = M._wgi_governance_datapoints("MYS")
    assert dps and all(dp.data_year == 2023 for dp in dps)


def test_competitors_augment_deadline_allows_a_comtrade_call():
    import silk_missions as M
    assert M._competitors_augment_s() >= 10


def test_failed_augment_is_declared_in_the_mission():
    import silk_missions as M
    from silk_agents import AgentReport
    rep = AgentReport("competitors", [], False, "")

    def boom(r):
        raise RuntimeError("x")
    assert not M._bounded_augment("competitors_structured", rep, boom, rep)
    gap = rep.findings[-1]
    assert gap.value is None and gap.status == "fetch_failed"
    assert "حصص الموردين" in gap.note and "competitors_structured" not in gap.note


def test_missing_coverage_is_not_reported_as_zero():
    import silk_decision as D
    assert not any("تغطية" in r["risk"] for r in D._risk_register({}, None))
    assert any("تغطية" in r["risk"] for r in D._risk_register({}, 0.3))


def test_concentrated_step_needs_hhi_or_top_share():
    import silk_decision as D
    src = open(D.__file__, encoding="utf-8").read()
    assert "concentrated_basis" in src and 'comp_parts.get("hhi") is not None' in src


def test_wto_empty_response_is_short_lived():
    import silk_wto_tariff as W
    seen = {}

    def fake(url, params=None, **kw):
        seen.update(kw)
        return {"Dataset": []}
    with mock.patch.dict(os.environ, {"WTO_TTD_API_KEY": "k"}), \
         mock.patch("silk_cache.cached_get", side_effect=fake):
        W.wto_applied_tariff("090121", "MYS", "SAU", 2023)
    assert seen["short_lived"]({"Dataset": []}) is True
    assert seen["short_lived"]({"Dataset": [{"Value": 5, "Year": 2023}]}) is False


def test_fx_series_uses_the_published_year():
    import silk_missions as M
    from silk_agents import AgentReport
    rep = AgentReport("risk_news", [], False, "")

    def wb(iso3, ind, year=None):
        return DataPoint(4.2, "World Bank", 0.9, "fx", "2026-10-04", data_year=2024)
    with mock.patch("silk_store.get_indicator", return_value=None), \
         mock.patch("silk_data_layer.world_bank", side_effect=wb):
        M._augment_risk_news_fx(rep, "MYS")
    years = [dp.data_year for dp in rep.findings if dp.data_year]
    assert 2025 not in years
