from types import SimpleNamespace
from unittest.mock import patch
import silk_websearch_agent as search


def test_exhausted_credit_is_reported_as_credit_failure(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "test-key")
    monkeypatch.setenv("SEARCH_PROVIDER", "serper")
    monkeypatch.setenv("SILK_SEARCH_CACHE_TTL_S", "0")
    response = SimpleNamespace(status_code=400, json=lambda: {"message": "Not enough credits"})
    with patch("silk_data_layer.throttled_request", return_value=response):
        dp = search.web_search("example")[0]
    assert dp.value is None and dp.confidence == 0 and dp.status == "fetch_failed"
    assert "نفد رصيد" in dp.note
    assert "test-key" not in dp.note
