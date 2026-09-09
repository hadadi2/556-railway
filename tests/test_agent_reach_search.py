import json
from types import SimpleNamespace
from unittest.mock import patch

from silk_agent_reach_search import _message, _results
from silk_websearch_agent import web_search


def test_mcp_sources_reach_existing_web_search_contract(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "agent_reach")
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    payload = {"result": {"content": [{"type": "text", "text":
        "Title: Example Distributor\nURL: https://example.test/company\nPublished: N/A\nHighlights:\nPublic company information."}]}}
    response = SimpleNamespace(text="event: message\ndata: " + json.dumps(payload) + "\n\n",
                               raise_for_status=lambda: None)
    with patch("silk_data_layer.throttled_request", return_value=response) as request:
        rows = web_search("food distributors", num=3)
    assert rows[0].value["title"] == "Example Distributor"
    assert rows[0].url == rows[0].value["link"] == "https://example.test/company"
    assert "Exa" in rows[0].source
    assert "Authorization" not in request.call_args.kwargs["headers"]
    assert request.call_args.kwargs["json_body"]["params"]["name"] == "web_search_exa"


def test_error_and_empty_response_never_invent_results(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "agent_reach")
    response = SimpleNamespace(text=json.dumps({"result": {"isError": True, "content": []}}),
                               raise_for_status=lambda: None)
    with patch("silk_data_layer.throttled_request", return_value=response):
        rows = web_search("example")
    assert rows[0].value is None and rows[0].confidence == 0
    assert rows[0].status == "fetch_failed"


def test_source_less_text_is_not_a_finding():
    assert _results({"result": {"content": [{"type": "text", "text": "No source URL"}]}}, 5) == []


def test_json_transport_is_supported():
    assert _message(SimpleNamespace(text='{"result":{"content":[]}}')) == {"result": {"content": []}}
