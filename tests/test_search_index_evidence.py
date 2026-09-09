from dataclasses import asdict
from silk_agents import AgentReport
from silk_data_layer import DataPoint
from silk_search_index_evidence import normalized_reports
from silk_writer_handoff import writer_reports


def test_saved_share_claim_is_replaced_by_its_actual_region_index():
    source = DataPoint({"region": "Amman", "interest": 100}, "Google Trends", .6)
    claim = DataPoint("يتركز البحث 100% في عمّان", "Google Trends", .6,
                      raw_evidence=(asdict(source),))
    original = AgentReport("demand_trends", [claim], False, "Original collector summary")
    reports = {"demand_trends": original}
    clean = normalized_reports(reports)
    dp = clean["demand_trends"].findings[0]
    assert dp.value == source.value
    assert dp.unit == "relative_search_interest_index_0_100"
    assert "ليست 100%" in dp.note
    assert original.findings[0].value == claim.value
    assert not clean["demand_trends"].failed
    assert asdict(normalized_reports(clean)["demand_trends"]) == asdict(clean["demand_trends"])
    assert writer_reports(reports)["demand_trends"].findings[0].value == source.value


def test_real_growth_percent_and_other_sources_preserved():
    growth = DataPoint({"rising_query": "halva", "growth": 200}, "Google Trends", .6)
    report = AgentReport("demand_trends", [growth])
    assert normalized_reports({"demand_trends": report})["demand_trends"] is report
