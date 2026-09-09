from silk_contact_quality import clean_contact
from silk_reports import _clean_leads
from silk_writer_handoff import writer_reports


def test_us_zip_address_excluded_only_for_other_markets():
    lead = {"name": "Food Distributor", "address": "8636 US-29, Fairfax, VA 22031",
            "email": "user@domain.com", "phone": "571-733-8108"}
    assert clean_contact(lead, "JOR") is None
    assert clean_contact(lead, "USA")["email"] == ""
    assert clean_contact(lead)["phone"] == lead["phone"]
    assert lead["email"] == "user@domain.com"


def test_saved_report_and_writer_exclude_foreign_contacts_and_fake_email():
    leads = [{"name": "Food Distributor", "address": "Washington, DC 20016",
              "phone": "+12025953505"},
             {"name": "Food Trading Company", "address": "Shanghai, China",
              "phone": "+862155555555"},
             {"name": "Jordan Food Company", "address": "Amman, Jordan",
              "phone": "+96264717777", "email": "email@email.com"}]
    cleaned = _clean_leads(leads, {"market": {"iso3": "JOR"}})
    assert len(cleaned) == 1 and cleaned[0]["email"] == ""
    received = writer_reports({}, {"leads": leads}, market="Jordan")
    values = [dp.value for dp in received["contact_enrichment"].findings]
    assert len(values) == 1 and values[0]["name"] == "Jordan Food Company"
    assert "email" not in values[0]


def test_real_email_and_ambiguous_address_preserved():
    lead = {"name": "Distributor", "address": "Industrial Road 12",
            "email": "info@waddanjo.com"}
    assert clean_contact(lead, "JOR") == lead
