"""المراجعة ليست موافقة عند الفشل — writer audit regressions."""
import os
import sys
import json
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import silk_ai_judge as writer
import silk_context as ctx
from conftest import block_network


def draft():
    return "\n\n".join(f"## {i}. {title}\nنص كامل للاختبار." for i, title in enumerate(writer.report_sections(), 1))


def test_unavailable_review_is_never_approval():
    with block_network(), patch.object(writer, "deep_report", return_value=draft()), patch.object(writer, "review_report", return_value=None):
        out = writer.write_reviewed_report({}, "", {}, "Dates", "Netherlands")
    assert out["report"]
    assert out["review_status"] == "unavailable"
    assert out["unresolved_notes"]


def test_failed_revision_preserves_complete_draft():
    with block_network(), patch.object(writer, "deep_report", side_effect=[draft(), "## 1. بداية فقط"]), patch.object(writer, "review_report", return_value={"approved": False, "issues": ["Missing evidence"], "blocking": ["Missing evidence"]}):
        out = writer.write_reviewed_report({}, "", {}, "Dates", "Netherlands", max_cycles=2)
    assert out["report"] == draft()
    assert out["review_status"] == "rejected"
    assert out["unresolved_notes"]


def test_disabled_reviewer_makes_no_provider_calls():
    with block_network(), ctx.agent_prefs_context({"reviewer": {"on": False}}), patch.object(writer, "available", return_value=True), patch.object(writer, "_call") as call:
        out = writer.review_report(draft(), {})
    assert call.call_count == 0
    assert out["review_status"] == "disabled"
    assert out["approved"] is False


def test_stream_eof_is_explicit_partial_failure():
    from silk_llm_provider import AnthropicProvider
    class Response:
        def iter_lines(self, **kwargs):
            for e in [{"type": "message_start", "message": {"usage": {"input_tokens": 100}}}, {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": "partial"}}]:
                yield "data: " + json.dumps(e)
        def close(self):
            pass
    data, error = AnthropicProvider._consume_stream(Response(), 10)
    assert error["type"] == "incomplete_stream"
    assert data["stop_reason"] == "aborted_timeout"
    assert data["content"][0]["text"] == "partial"
