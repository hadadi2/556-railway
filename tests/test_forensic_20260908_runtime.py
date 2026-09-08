"""قفل ثغرات التدقيق: حدود التنفيذ وعزل النتائج — forensic regressions."""
import os
import sys
import json
import threading
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import silk_context as ctx
import silk_llm_runtime as runtime
import silk_missions as missions
from silk_agents import AgentReport
from silk_data_layer import DataPoint
from silk_market_resolver import resolve_market
from conftest import block_network


def test_dispatch_enforces_mission_and_each_tool_budget(monkeypatch):
    market, _ = resolve_market("Netherlands")
    final = {"content": [{"type": "text", "text": json.dumps({"findings": [], "gaps": [], "summary": "done"})}]}
    for allowed, expected in [([], 0), (["web_search"], 1)]:
        observed = []
        response = {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": str(i), "name": "web_search", "input": {"query": "test"}} for i in range(3)]}
        ctx.begin_data_counter()
        monkeypatch.setenv("SILK_RESEARCH_MAX_TOOL_CALLS", "1")
        with block_network(), patch.object(runtime, "_call_tools", side_effect=[response, final]), patch.dict(runtime.TOOLS["web_search"], {"fn": lambda *a: observed.append(a) or []}):
            runtime._run_loop({"key": "audit", "allowed_tools": allowed}, {"market": market}, {"tool_calls": 1})
        assert len(observed) == expected
        assert ctx.data_counter()["tool_calls"] == expected


def test_timed_out_augment_cannot_mutate_published_report(monkeypatch):
    report = AgentReport("audit", [], False, "initial")
    release, done = threading.Event(), threading.Event()
    def augment(candidate):
        release.wait(2)
        candidate.findings.append(DataPoint(7, "Late", .9))
        done.set()
    monkeypatch.setattr(missions, "_MISSION_AUGMENT_TIMEOUT_S", .01)
    try:
        assert not missions._bounded_augment("audit", report, augment, report)
    finally:
        release.set()
        assert done.wait(3)
    assert report.findings == []


def test_tagging_preserves_provenance():
    from silk_market_analyst import _tag_source_reports
    from dataclasses import asdict
    dp = DataPoint(100, "Source", .9, "note", unit="USD", url="https://source.invalid", data_year=2025, evidence_ids=["raw1"])
    tagged = _tag_source_reports({"trade": AgentReport("trade", [dp])})[0]
    original, actual = asdict(dp), asdict(tagged)
    original["note"] = "[trade] note"
    assert actual == original


def test_analysis_connections_enforce_foreign_keys(tmp_path):
    import silk_storage
    import sqlite3
    conn = silk_storage._connect(str(tmp_path / "analysis.db"))
    try:
        conn.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE child(id INTEGER REFERENCES parent(id))")
        import pytest
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO child VALUES (99)")
    finally:
        conn.close()


def test_resume_invalidates_dependent_opportunity():
    market, _ = resolve_market("Netherlands")
    saved = {k: AgentReport(k, [DataPoint("old", "Source", .8)]) for k in missions.MISSION_ORDER}
    saved["trade_flow"].failed = True
    with block_network(), patch.object(missions.LLMMissionAgent, "run", return_value=AgentReport("new", [DataPoint("new", "Source", .8)])), patch.object(missions, "_bounded_augment", return_value=True):
        out = missions.run_all_missions(market, "Dates", "080410", resume_reports=saved)
    assert out["opportunity_gaps"] is not saved["opportunity_gaps"]
    assert out["pricing_scout"] is saved["pricing_scout"]


def test_unknown_cost_components_are_not_zero():
    from silk_localprice_agent import suggest_price
    out = suggest_price([DataPoint({"price": 100, "currency": "USD", "pack_size": "1 kg"}, "Source", .8)], cost_per_unit=50, currency="USD", pack_size="1 kg")
    assert out["suggested_min"] == 100
    assert out["landed_cost_floor"] is None
    assert out["margin_at_min_pct"] is None


def test_mixed_currency_pack_prices_are_not_averaged():
    from silk_localprice_agent import compare_own_price
    out = compare_own_price(20, [DataPoint({"price": 10, "currency": "USD", "pack_size": "1 kg"}, "Source", .8), DataPoint({"price": 100, "currency": "JPY", "pack_size": "10 kg"}, "Source", .8)])
    assert out["market_avg"] is None
    assert out["verdict"] is None


def test_numeric_claim_is_checked_against_source_not_its_own_text():
    raw = DataPoint(10000, "UN Comtrade", .9, "Imports USD")
    def parse(claim):
        return runtime._parse_output(json.dumps({"findings": [{"claim": claim, "datapoint_ids": ["dp1"], "confidence": .9}]}), {"dp1": raw})
    assert parse("Imports 999999 USD")["findings"] == []
    assert parse("Imports 10,000 USD")["findings"]
    assert parse("الواردات ١٠٬٠٠٠ USD")["findings"]
    assert not parse("Imports 10,000 EUR")["findings"]


def test_shared_reservations_cannot_overshoot():
    import contextvars
    from concurrent.futures import ThreadPoolExecutor
    counter = ctx.begin_data_counter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(contextvars.copy_context().run, ctx.reserve_data, "tool_calls", 3) for _ in range(100)]
    assert sum(f.result() for f in futures) == 3
    assert counter["tool_calls"] == 3


def test_raw_evidence_survives_checkpoint_and_is_not_repeated_in_prompt(tmp_path):
    import silk_storage
    from silk_evidence_contract import raw_snapshots
    from silk_ai_judge import _facts
    raw = DataPoint(10000, "UN Comtrade", .9, "UNIQUE_RAW_MARKER", unit="USD")
    first = DataPoint("Imports 10000 USD", raw.source, .9, raw_evidence=raw_snapshots([raw]))
    second = DataPoint("Evidence repeated", raw.source, .9, raw_evidence=raw_snapshots([raw]))
    report = AgentReport("trade", [first, second])
    path = str(tmp_path / "evidence.db")
    aid = silk_storage.create_research_run("Dates", "NLD", "080410", {}, path=path)
    silk_storage.save_mission_checkpoint(aid, "trade", report, path=path, market_iso3="NLD")
    restored = silk_storage.load_mission_checkpoints(aid, path=path, market_iso3="NLD")["trade"]
    assert restored.findings[0].raw_evidence[0]["value"] == 10000
    assert _facts([restored]).count("UNIQUE_RAW_MARKER") == 1


def test_provider_retry_must_reserve_before_every_http_attempt(monkeypatch):
    import requests
    import pytest
    from silk_llm_provider import AnthropicProvider
    ctx.begin_data_counter()
    monkeypatch.setenv("SILK_RESEARCH_MAX_LLM_CALLS", "1")
    monkeypatch.setenv("SILK_LLM_RETRY_BASE_S", "0")
    with block_network(), patch("requests.post", side_effect=requests.exceptions.ConnectTimeout("net blocked")) as post:
        with pytest.raises(RuntimeError, match="run_llm_attempt_budget_exhausted"):
            AnthropicProvider()._post("offline-key", {"model": "claude-sonnet-5"}, 10)
    assert post.call_count == 1
    assert ctx.data_counter()["llm_attempts"] == 1
