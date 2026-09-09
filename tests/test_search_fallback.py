from types import SimpleNamespace
from unittest.mock import patch

from silk_data_layer import DataPoint
from silk_websearch_agent import web_search
import silk_tavily_search as tavily


def test_successful_primary_does_not_spend_fallback_credit(monkeypatch):
    monkeypatch.setenv("SEARCH_FALLBACK_PROVIDER", "tavily")
    rows = [DataPoint({"title": "Primary", "link": "https://example.test"}, "Exa", .5)]
    with patch("silk_websearch_agent._web_search_primary", return_value=rows), \
         patch.object(tavily, "search") as fallback:
        assert web_search("example") is rows
    fallback.assert_not_called()


def test_failed_primary_uses_tavily_with_correct_provenance(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "agent_reach")
    monkeypatch.setenv("SEARCH_FALLBACK_PROVIDER", "tavily")
    secondary = [DataPoint({"title": "Backup", "link": "https://example.test"}, tavily.SOURCE, .5)]
    with patch("silk_websearch_agent._web_search_primary", return_value=[DataPoint(None, "Exa", 0)]), \
         patch.object(tavily, "search", return_value=secondary) as fallback:
        rows = web_search("example", num=3)
    fallback.assert_called_once_with("example", num=3, gl=None, hl=None)
    assert rows[0].source == tavily.SOURCE and "بحث احتياطي" in rows[0].note


def test_both_failures_remain_visible(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "agent_reach")
    monkeypatch.setenv("SEARCH_FALLBACK_PROVIDER", "tavily")
    with patch("silk_websearch_agent._web_search_primary", return_value=[DataPoint(None, "Exa", 0)]), \
         patch.object(tavily, "search", return_value=[DataPoint(None, tavily.SOURCE, 0)]):
        rows = web_search("example")
    assert len(rows) == 2 and all(dp.value is None and dp.confidence == 0 for dp in rows)


def test_tavily_uses_basic_search_and_source_urls(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-only")
    response = SimpleNamespace(raise_for_status=lambda: None,
        json=lambda: {"answer": "Do not use generated answers", "results": [
            {"title": "Page", "url": "https://example.test/page", "content": "Original excerpt"}]})
    with patch("silk_data_layer.throttled_request", return_value=response) as request:
        rows = tavily.search("example")
    body = request.call_args.kwargs["json_body"]
    assert body["search_depth"] == "basic" and body["auto_parameters"] is False
    assert body["include_answer"] is False
    assert rows[0].url == "https://example.test/page"
    assert "generated answers" not in str(rows)
