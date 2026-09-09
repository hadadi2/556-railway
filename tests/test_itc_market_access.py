from silk_itc_tariff import hs6, market_access_evidence, query_url


def test_itc_normalizes_hs_and_keeps_customs_separate_from_vat():
    assert hs6("1704.90") == "170490"
    dp = market_access_evidence("170490", "JOR", "SAU", 2024)
    assert dp.value is None
    assert dp.source == "ITC Market Access Map"
    assert "الضريبة" in dp.note and "التعرفة" in dp.note
    assert "HS170490" in dp.note


def test_itc_query_url_is_actionable():
    url = query_url("170490", "SAU", "JOR")
    assert url.startswith("https://www.macmap.org/en/query/results?")
    assert "product=170490" in url

