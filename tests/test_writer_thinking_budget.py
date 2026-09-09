"""Sonnet 5 must retain output space for a report after a thinking-only reply."""
from unittest.mock import patch
import silk_ai_judge as judge
import silk_llm_provider as provider


class Response:
    def __init__(self, content, stop="end_turn"):
        self.data = {"content": content, "stop_reason": stop,
                     "usage": {"input_tokens": 10, "output_tokens": 20}}

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


def test_writer_retry_changes_thinking_policy_after_empty_limit(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("SILK_API_KEY", "test-key")
    monkeypatch.setattr(judge, "_MODEL", "claude-sonnet-5")
    sent = []

    def post(url, **kw):
        sent.append(kw["json"])
        if len(sent) == 1:
            return Response([{"type": "thinking", "thinking": ""}], "max_tokens")
        return Response([{"type": "text", "text": "## 1. الخلاصة\nتقرير مسترد."}])

    with patch("requests.post", side_effect=post):
        result = judge.deep_report({}, "", {"verdict": "WATCH"}, "Honey", "Jordan")
    assert result and len(sent) == 2
    assert sent[0]["output_config"] == {"effort": "medium"}
    assert "thinking" not in sent[0]
    assert sent[1]["thinking"] == {"type": "disabled"}
    assert sent[1]["max_tokens"] <= judge._MAX_TOKENS_CEILING


def test_other_models_and_nonwriter_calls_keep_their_policy(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    sent = []

    def post(url, **kw):
        sent.append(kw["json"])
        return Response([{"type": "text", "text": "Complete."}])

    with patch("requests.post", side_effect=post):
        p = provider.AnthropicProvider()
        p.complete("s", "u", 100, "claude-haiku-4-5", 5,
                   effort="medium", thinking_disabled=True)
        p.complete("s", "u", 100, "claude-sonnet-5", 5)
    assert all("output_config" not in x and "thinking" not in x for x in sent)
