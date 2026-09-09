"""The same complete evidence reaches writing and review without masking failures."""
from unittest.mock import patch

from silk_agents import AgentReport
from silk_data_layer import DataPoint
from silk_writer_handoff import writer_reports
import silk_ai_judge as judge


def test_writer_and_reviewer_receive_all_missions_and_contact_evidence():
    missions = {f"mission_{i}": AgentReport(f"mission_{i}", [
        DataPoint(f"unique evidence {i}", "source", .7)]) for i in range(12)}
    leads = {"leads": [{"name": "Example Distributor", "phone": "+12345",
                        "source": "google_maps_scraper", "maps_link": "https://example.test/place"}]}
    with patch.object(judge, "deep_report", return_value="Complete draft") as writer, \
         patch.object(judge, "_writer_incomplete", return_value=[]), \
         patch.object(judge, "review_report", return_value={"approved": True}) as reviewer, \
         patch("silk_context.agent_enabled", return_value=True):
        judge.write_reviewed_report(missions, "", {}, "honey", "Jordan", importer_leads=leads)
    received = writer.call_args.args[0]
    assert received is reviewer.call_args.args[1]
    facts = judge._facts(list(received.values()))
    for i in range(12):
        assert f"unique evidence {i}" in facts
    assert "Example Distributor" in facts and "+12345" in facts
    assert "https://example.test/place" in facts
    assert len(missions) == 12  # supplemental evidence never changes mission status


def test_contacts_do_not_turn_failed_mission_into_success():
    failed = AgentReport("channels_importers", [], True, "Search failed")
    missions = {"channels_importers": failed}
    received = writer_reports(missions, {"leads": [{"name": "Example"}]}, "honey")
    assert received["channels_importers"] is failed and failed.failed
    dp = received["contact_enrichment"].findings[0]
    assert dp.confidence == 0 and "لا أنه يستورد" in dp.note
    assert "phone" not in dp.value


def test_no_contacts_stays_explicit_gap():
    received = writer_reports({}, {"leads": [], "note": "Collector timed out"})
    dp = received["contact_enrichment"].findings[0]
    assert dp.value is None and dp.confidence == 0
    assert dp.note == "Collector timed out"
