"""مصادر وأبعاد الحساب: لا أرقام من شرائح أو وحدات مجهولة."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conftest import block_network


def test_invalid_hs_cannot_be_human_approved():
    import silk_hs_pipeline as hs
    with block_network():
        result = hs.classify("Dates", "000000", hs_confirmed=True)
    assert result["classification_status"] != hs.APPROVED
    assert not result.get("final_hs_code")


def test_eurostat_does_not_select_arbitrary_multidimensional_cell():
    from silk_eurostat_agent import _first_value
    assert _first_value({"size": [2], "value": {"0": 40, "1": 100}}) is None
    assert _first_value({"size": [1], "value": {"0": 100}}) == 100


def test_sonnet_standard_price():
    from silk_pricing import MODEL_PRICING
    assert MODEL_PRICING["claude-sonnet-5"] == {"input": 2., "output": 10.}


def test_eval_preserves_failure_and_reads_final_section():
    from silk_evals import _report_fields, _judge_prompt
    assert _report_fields({"failed": True})["failed"] is True
    prompt = _judge_prompt({"deep_research": {"report": {"report": "HEAD" + "x" * 9000 + "TAIL_EVIDENCE"}, "missions": {"trade": {"failed": True}}}})
    assert "TAIL_EVIDENCE" in prompt


def test_trace_size_and_retention_are_bounded(tmp_path, monkeypatch):
    import silk_trace, silk_janitor
    monkeypatch.delenv("SILK_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("SILK_TRACE_RETENTION_DAYS", raising=False)
    assert silk_janitor._days("traces") == 30
    monkeypatch.setenv("SILK_TRACE_MAX_BYTES", "1024")
    with silk_trace.trace_context("bounded", str(tmp_path)) as path:
        for _ in range(20):
            silk_trace.record_event(prompt="x" * 300)
    assert 0 < os.path.getsize(path) <= 1024


def test_trace_retention_runs_without_refresh_scheduler(tmp_path, monkeypatch):
    import time
    import silk_trace
    old = tmp_path / "old.jsonl"
    old.write_text("{}\n")
    os.utime(old, (time.time() - 40 * 86400,) * 2)
    monkeypatch.setenv("SILK_TRACE_RETENTION_DAYS", "30")
    monkeypatch.setenv("SILK_REFRESH_HOURS", "0")
    with silk_trace.trace_context("current", str(tmp_path)):
        silk_trace.record_event(kind="new")
    assert not old.exists()


def test_som_requires_capacity_mass_not_package_count():
    from unittest.mock import patch
    import silk_research as research
    task = {"hs6": "080410", "iso3": "NLD", "m49": "528", "year": 2025,
            "product_card": {"cost_per_unit": 1, "unit": "bottle", "monthly_capacity": 1000}}
    with block_network(), patch("silk_data_layer_v2.market_imports_cached", return_value={"total_usd": 1000000}), patch.object(research, "_growth_window_pairs", return_value=[(2024, 900000), (2025, 1000000)]), patch.object(research, "_border_unit_value", return_value=2):
        values, gaps = research.MarketSizeAgent()._research(task)
        assert not any(f["metric"] == "som_usd" for f in values)
        assert any("som_usd" in gap for gap in gaps)
        task["product_card"]["unit"] = "kg"
        values, _ = research.MarketSizeAgent()._research(task)
        assert next(f["value"] for f in values if f["metric"] == "som_usd") == 24000
