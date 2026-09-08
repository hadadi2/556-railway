"""Read-only audit witnesses for Silk main 8143125; providers are mocked.

These assertions demonstrate the current faults. They are not repair tests.
"""
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

_here = Path(__file__).resolve().parent
_candidates = [p for p in _here.parents if (p / "silk_missions.py").is_file()]
ROOT = Path(os.environ.get("SILK_AUDIT_REPO", str(_candidates[0] if _candidates else _here.parent / "silk-audit-8143125"))).resolve()
OUT = Path(os.environ.get("SILK_AUDIT_OUTPUT_DIR", str(_here))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
for key in list(os.environ):
    if key.startswith(("SILK_", "ANTHROPIC_", "COMTRADE_", "SEARCH_API_")) or key == "DATABASE_URL":
        os.environ.pop(key, None)
os.environ.update({"SILK_HTTP_MIN_GAP_MS": "0", "SILK_COMTRADE_MIN_GAP_MS": "0",
                   "SILK_PLATFORM_RUN_SUPERVISOR": "0", "SILK_PLATFORM_ORPHAN_SWEEP": "0",
                   "SILK_RESEARCH_RUN_SUPERVISOR": "0"})
scratch = tempfile.TemporaryDirectory(prefix="silk-audit-proof-")
os.environ["SILK_DATA_DIR"] = scratch.name
os.environ["SILK_TRACE_DIR"] = scratch.name + "/traces"

import silk_ai_judge as writer
import silk_context as ctx
import silk_evals as ev
import silk_llm_provider as provider
import silk_llm_runtime as runtime
import silk_market_analyst as analyst
import silk_missions as missions
from silk_agents import AgentReport
from silk_data_layer import DataPoint
from silk_market_resolver import resolve_market

market, _ = resolve_market("Netherlands")
findings = []

def record(key, observed):
    findings.append({"id": key, "observed": observed})
    print(json.dumps(findings[-1], ensure_ascii=False), flush=True)

def final_response():
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text":
        json.dumps({"findings": [], "gaps": [], "summary": "Audit complete"})}]}

def complete_draft():
    return "\n\n".join(f"## {i}. {title}\nنص كامل للاختبار."
                        for i, title in enumerate(writer.report_sections(), 1))

def proof_tools():
    observed = []
    def tool(args, context):
        observed.append(args)
        return [DataPoint(1, "Audit source", .8, "Fixture")]
    response = {"stop_reason": "tool_use", "content": [
        {"type": "tool_use", "id": "t1", "name": "web_search", "input": {"q": "fixture"}}]}
    ctx.begin_data_counter()
    with patch.object(runtime, "_call_tools", side_effect=[response, final_response()]), \
         patch.dict(runtime.TOOLS["web_search"], {"fn": tool}):
        runtime._run_loop(missions.MISSIONS["trade_flow"], {"market": market}, {"tool_calls": 1})
    assert len(observed) == 1
    record("F01", {"allowed": ["comtrade_imports"], "executed": "web_search", "count": len(observed)})
    observed.clear()
    response["content"] = [{"type": "tool_use", "id": f"t{i}", "name": "web_search",
                             "input": {"q": i}} for i in range(3)]
    ctx.begin_data_counter()
    with patch.object(runtime, "_call_tools", side_effect=[response, final_response()]), \
         patch.dict(runtime.TOOLS["web_search"], {"fn": tool}), \
         patch.dict(os.environ, {"SILK_RESEARCH_MAX_TOOL_CALLS": "1"}):
        out = runtime._run_loop({"key": "audit", "allowed_tools": ["web_search"]},
                                 {"market": market}, {"tool_calls": 1})
    assert len(observed) == 3
    record("F02", {"mission_limit": 1, "run_limit": 1, "executed": len(observed),
                    "counted": ctx.data_counter()["tool_calls"]})

def proof_faithfulness():
    raw = DataPoint(10000, "UN Comtrade", .9, "Imports USD", "2026-09-07")
    payload = json.dumps({"findings": [{"claim": "Imports are 999999 USD.",
        "datapoint_ids": ["dp1"], "confidence": .9}], "summary": "", "gaps": []})
    parsed = runtime._parse_output(payload, {"dp1": raw})
    assert parsed["findings"] and not parsed["dropped"]
    report = AgentReport("audit", [DataPoint(parsed["findings"][0]["claim"], raw.source, .9, raw.note)])
    score = ev.citation_correctness_score("Imports are 999999 USD.", {"trade_flow": report})
    assert score["score"] == 100
    record("F03", {"source_value": 10000, "accepted_claim_value": 999999, "eval": score})

def proof_review_failure():
    with patch.object(writer, "deep_report", return_value=complete_draft()), \
         patch.object(writer, "review_report", return_value=None):
        out = writer.write_reviewed_report({}, "", {}, "Fixture", "Netherlands")
    assert out["report"] and out["unresolved_notes"] == [] and "review_status" not in out
    record("F04", {"review_returned": None, "report_returned": True,
                    "unresolved_notes": out["unresolved_notes"], "review_cycles": out["review_cycles"]})

def proof_revision_partial():
    partial = "## 1. " + writer.report_sections()[0] + "\nبداية التقرير فقط."
    with patch.object(writer, "deep_report", side_effect=[complete_draft(), partial]), \
         patch.object(writer, "review_report", return_value={"approved": False,
             "issues": ["Missing evidence"], "blocking": ["Missing evidence"]}):
        out = writer.write_reviewed_report({}, "", {}, "Fixture", "Netherlands", max_cycles=2)
    assert out["report"] == partial and "incomplete" not in out and "partial_text" not in out
    record("F05", {"missing_sections": len(writer._missing_sections(out["report"])),
                    "incomplete_flag": out.get("incomplete"), "partial_checkpoint": "partial_text" in out})

def proof_preferences():
    with ctx.agent_prefs_context({"reviewer": {"on": False, "cmd": "AUDIT_REVIEWER_COMMAND"}}), \
         patch.object(writer, "available", return_value=True), \
         patch.object(writer, "_call", return_value='{"issues":[],"blocking":[],"approved":true}') as call:
        writer.review_report(complete_draft(), {})
    assert call.call_count == 1
    prompt = call.call_args.args[1]
    record("F06", {"reviewer_enabled": False, "provider_calls": call.call_count,
                    "custom_instruction_forwarded": "AUDIT_REVIEWER_COMMAND" in prompt})

def proof_resume_dependencies():
    saved = {k: AgentReport(k, [DataPoint("old " + k, "Audit", .8, "old")], False, "old")
             for k in missions.MISSION_ORDER}
    saved["trade_flow"].failed = True
    called = []
    def run(self, task, instruction=""):
        called.append(self.name)
        return AgentReport(self.name, [DataPoint("NEW TRADE", "Audit", .8, "new")], False, "new")
    with patch.object(missions.LLMMissionAgent, "run", run), \
         patch.object(missions, "_bounded_augment", return_value=True):
        out = missions.run_all_missions(market, product="Fixture", hs_code="080410", resume_reports=saved)
    assert out["trade_flow"].findings[0].value == "NEW TRADE"
    assert out["opportunity_gaps"] is saved["opportunity_gaps"]
    record("F07", {"rerun_agents": called, "new_trade": True, "opportunity_result": out["opportunity_gaps"].findings[0].value})

def proof_late_augment():
    report = AgentReport("audit", [], False, "initial")
    release, done = threading.Event(), threading.Event()
    def delayed(rep):
        release.wait(1)
        rep.findings.append(DataPoint(7, "Late", .9))
        done.set()
    with patch.object(missions, "_MISSION_AUGMENT_TIMEOUT_S", .01):
        ok = missions._bounded_augment("audit", report, delayed, report)
    before = len(report.findings)
    release.set()
    assert done.wait(2)
    assert not ok and before == 0 and len(report.findings) == 1
    record("F08", {"returned_success": ok, "findings_on_return": before,
                    "findings_after_timeout_return": len(report.findings)})

def proof_analyst_metadata():
    raw = DataPoint(42, "UN Comtrade", .9, "import", "2026-09-07", unit="USD",
                    url="https://comtradeapi.un.org/", data_year=2025, reference_period="2025",
                    source_ids=("UN Comtrade", "World Bank"), evidence_ids=("dp1",), retrieval_method="api")
    tagged = analyst._tag_source_reports({"trade_flow": AgentReport("trade", [raw])})[0]
    fields = ["unit", "url", "data_year", "reference_period", "source_ids", "evidence_ids", "retrieval_method"]
    assert all(getattr(raw,k) and not getattr(tagged,k) for k in fields)
    record("F09", {"dropped_fields": fields})

def proof_stream_eof():
    class Response:
        def iter_lines(self, **kwargs):
            events = [{"type": "message_start", "message": {"usage": {"input_tokens": 100}}},
                      {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                      {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "partial text"}}]
            for e in events: yield "data: " + json.dumps(e)
        def close(self): pass
    data, error = provider.AnthropicProvider._consume_stream(Response(), 10)
    assert error is None and data["stop_reason"] is None and data["content"][0]["text"]
    record("F10", {"EOF_without_message_stop": True, "error": error,
                    "stop_reason": data["stop_reason"], "usage": data["usage"]})

def proof_price_units():
    import silk_localprice_agent as price
    rows = [DataPoint({"price": 10, "currency": "USD", "pack_size": "1 kg"}, "Fixture", .8),
            DataPoint({"price": 100, "currency": "JPY", "pack_size": "10 kg"}, "Fixture", .8)]
    out = price.compare_own_price(20, rows)
    assert out["market_avg"] == 55 and out["listings_count"] == 2
    record("F11", {"inputs": [r.value for r in rows], "comparison": out})
    out = price.suggest_price([DataPoint({"price": 100, "currency": "USD"}, "Fixture", .8)],
                             cost_per_unit=50, tariff_pct=None, shipping_per_unit=None)
    assert out["landed_cost_floor"] == 50 and out["margin_at_min_pct"] == 50
    record("F12", {"missing_inputs": ["tariff_pct", "shipping_per_unit"],
                    "landed_cost_floor": out["landed_cost_floor"],
                    "margin_at_min_pct": out["margin_at_min_pct"], "note": out["note"],
                    "reachability": "utility only; no production caller found"})

def proof_resume_identity():
    import silk_storage as storage
    from fastapi.testclient import TestClient
    db = str(Path(scratch.name) / "identity.db")
    seen = {}
    def capture(*args, **kwargs):
        seen.update(kwargs)
        seen["positional"] = [str(a) for a in args]
        raise RuntimeError("audit sentinel: stop after resume boundary")
    with patch.object(storage, "_db_path", return_value=db), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "audit-placeholder", "SILK_API_KEY": "audit-placeholder"}), \
         patch.object(missions, "deep_research", side_effect=capture):
        run = storage.create_research_run("Milk", "YEM", "040120",
            {"product": "Milk", "market": "Yemen", "market_iso3": "YEM", "hs_code": "040120"},
            path=db, market_name="Yemen")
        for key in missions.MISSION_ORDER:
            storage.save_mission_checkpoint(run, key, AgentReport(key,
                [DataPoint("OLD MILK EVIDENCE", "Fixture", .8)], key == "demand_trends", "old milk"),
                path=db, market_iso3="YEM")
        storage.update_research_status(run, "completed", path=db)
        import api
        response = TestClient(api.app).post("/research", headers={"X-API-Key": "audit-placeholder"},
            json={"resume": run, "product": "Dates", "hs_code": "080410", "market": "Yemen"})
    assert seen.get("product") == "Dates" and seen.get("hs_code") == "080410", seen
    assert seen["resume_reports"]["trade_flow"].findings[0].value == "OLD MILK EVIDENCE"
    record("F13", {"original": {"product": "Milk", "hs_code": "040120"},
        "resumed": {"product": seen["product"], "hs_code": seen["hs_code"]},
        "reused_evidence": seen["resume_reports"]["trade_flow"].findings[0].value,
        "response_after_audit_sentinel": response.status_code})

def proof_eval_contract():
    prompt = ev._judge_prompt({"deep_research": {
        "missions": {"failed_fixture": AgentReport("failed_fixture", [], True, "failed")},
        "report": {"report": "a" * 8100 + "AUDIT_REPORT_TAIL"}}})
    assert "فشل=False" in prompt and "AUDIT_REPORT_TAIL" not in prompt
    assert "الخمسة عشر" in prompt and len(writer.report_sections()) == 11
    record("F14", {"failed_mission_told_to_judge": False, "tail_visible": False,
        "expected_sections_in_eval_prompt": 15, "actual_report_sections": len(writer.report_sections())})

def proof_eurostat_dimensions():
    import silk_eurostat_agent as euro
    # A valid multidimensional JSON-stat shape: female subgroup precedes total.
    payload = {"class": "dataset", "version": "2.0", "id": ["sex", "time"],
        "size": [2, 1], "dimension": {
            "sex": {"category": {"index": {"F": 0, "T": 1}}},
            "time": {"category": {"index": {"2025": 0}}}},
        "value": {"0": 40, "1": 100}}
    with patch.object(euro, "_fetch_jsonstat", return_value=payload) as fetch:
        out = euro.foreign_born_population_count("NLD", "NL", 2025)
    params = fetch.call_args.args[1]
    assert out.value == 40 and "sex" not in params and "age" not in params
    record("F16", {"subgroup_value": 40, "total_value": 100,
        "returned_as_population_count": out.value, "query_parameters": params})

def proof_trends_normalization():
    import silk_trends_agent as trends
    # Same search geography/time, two independent normalized series. A steady
    # but small absolute series can have a higher normalized mean than a large,
    # spiky series. Values are a mathematical fixture, not observed search data.
    exact_counts = [10000] + [100] * 119
    broad_counts = [10] * 120
    normalized = lambda xs: sum(100 * x / max(xs) for x in xs) / len(xs)
    exact_mean, broad_mean = normalized(exact_counts), normalized(broad_counts)
    with patch.object(trends, "trends_context", return_value={"related_top": [{"label": "broad"}]}), \
         patch.object(trends, "trends_interest", return_value=DataPoint(broad_mean, "Google Trends", .7)):
        out = trends.broaden_if_weak("exact", "NL", "today 12-m",
                                    DataPoint(exact_mean, "Google Trends", .7))
    assert out is not None and sum(broad_counts) < sum(exact_counts)
    record("F17", {"fixture_only": True, "exact_total": sum(exact_counts),
        "broad_total": sum(broad_counts), "exact_separate_index_mean": exact_mean,
        "broad_separate_index_mean": broad_mean, "broader_claim_emitted": out.note})

def proof_capacity_units():
    import silk_research as research
    task = {"hs6": "080410", "iso3": "NLD", "m49": "528", "year": 2025,
        "product_card": {"cost_per_unit": 1, "unit": "bottle", "monthly_capacity": 1000}}
    with patch("silk_data_layer_v2.market_imports_cached", return_value={"total_usd": 1000000}), \
         patch.object(research, "_growth_window_pairs", return_value=[(2024, 900000), (2025, 1000000)]), \
         patch.object(research, "_border_unit_value", return_value=2):
        values, gaps = research.MarketSizeAgent()._research(task)
    out = next(f for f in values if f["metric"] == "som_usd")
    assert out["value"] == 24000
    record("F18", {"capacity_unit": "bottle", "monthly_capacity": 1000,
        "border_price_unit": "USD/kg", "border_price": 2, "som_emitted_usd": out["value"],
        "mass_per_bottle_known": False})

def proof_late_cancellation():
    import types
    from silk_platform import engine_bridge as bridge
    run = types.SimpleNamespace(cancel=threading.Event(), cancel_reason="requested", analysis_id=42)
    def finish_engine(*args, **kwargs):
        # Cancellation has arrived before the engine returns its final result.
        run.cancel.set()
        return {"analysis_id": 42, "classified": True, "deep_research": {}}
    with patch.object(bridge, "_run_engine", side_effect=finish_engine), \
         patch.object(bridge, "result_is_substantive", return_value=True), \
         patch.object(bridge, "_finish_success") as success, \
         patch.object(bridge, "_finish_failure") as failure:
        bridge._thread_body(1, 1, "Fixture", "080410", "NLD", run_token="audit", run=run)
    assert run.cancel.is_set() and success.call_count == 1 and failure.call_count == 0
    record("F19", {"cancel_set_before_engine_return": True,
        "success_finalizer_calls": success.call_count, "cancel_finalizer_calls": failure.call_count})

def proof_price_catalog():
    import silk_pricing as pricing
    # Official tariff snapshot checked on 2026-09-07 UTC. This comparison is time
    # sensitive and must be reverified when reproducing on a different date.
    cost = pricing.estimate_cost_usd({"claude-sonnet-5": {
        "input_tokens": 1000000, "output_tokens": 1000000}})
    official = 2 + 10
    assert cost["total_usd"] == 18
    record("F20", {"code_estimate_usd": cost["total_usd"], "official_snapshot_utc_date": "2026-09-07", "official_cost_usd": official,
        "overestimate_percent": 50, "source": "https://platform.claude.com/docs/en/about-claude/pricing"})

def proof_hs_reference_override():
    import silk_hs_pipeline as hs
    import silk_hs_confirm as confirm
    out = hs.classify("Dates", "000000", hs_confirmed=True, allow_web=False, allow_claude=False)
    assert out["classification_status"] == "approved" and out["final_hs_code"] == "000000"
    assert not out["official_hs_description"]
    assert confirm.preflight_block("Dates", "000000", True, hs_confidence=out["confidence"]) is None
    record("F21", {"product": "Dates", "approved_hs": out["final_hs_code"],
        "confidence": out["confidence"], "reference_description": out["official_hs_description"],
        "contradictions": out["contradictions"], "downstream_preflight_block": None})

def proof_analysis_foreign_keys():
    import silk_storage as storage
    db = scratch.name + "/foreign-key-proof.db"
    storage.init_db(db, force=True)
    conn = storage._connect(db)
    try:
        enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        declared = conn.execute("PRAGMA foreign_key_list(market_scores)").fetchall()
        conn.execute("INSERT INTO market_scores(analysis_id,country,iso3,total_score,confidence) "
                     "VALUES (999999,'Fixture','NLD',50,.8)")
        conn.commit()
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert enabled == 0 and declared and violations
        record("F22", {"foreign_keys_enabled": enabled, "declared_constraint": "market_scores.analysis_id -> analyses.id",
            "orphan_insert_committed": True, "foreign_key_violations": len(violations),
            "scope": "deliberate invalid insert into an isolated database; no production corruption established"})
    finally:
        conn.close()

def proof_trace_retention():
    import time
    import silk_trace as trace
    import silk_janitor as janitor
    folder = scratch.name + "/retention-proof"
    with trace.trace_context("audit-old-trace", dir_path=folder) as path:
        trace.record_event(event="audit", prompt="Fixture only")
    os.utime(path, (time.time() - 365 * 86400, time.time() - 365 * 86400))
    days = janitor._days("traces")
    removed = janitor._sweep_dir(folder, days, "*.jsonl")
    assert days == 0 and removed == 0 and Path(path).exists()
    record("F24", {"default_trace_retention_days": days, "one_year_old_trace_retained": True,
        "default_cache_retention_days": janitor._days("cache"),
        "scope": "default configuration only; deployed Railway override unknown"})

def proof_new_request_replay():
    import silk_storage as storage
    from fastapi.testclient import TestClient
    import api
    db = scratch.name + "/request-replay-proof.db"
    seen = []
    def stop_at_engine(*args, **kwargs):
        seen.append(kwargs.get("analysis_id"))
        raise RuntimeError("audit sentinel after new run reached engine")
    with patch.object(storage, "_db_path", return_value=db), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "audit-placeholder", "SILK_API_KEY": "audit-placeholder"}), \
         patch.object(missions, "deep_research", side_effect=stop_at_engine):
        client = TestClient(api.app)
        statuses = [client.post("/research", headers={"X-API-Key": "audit-placeholder",
            "Idempotency-Key": "audit-same-logical-request"}, json={"product": "Dates",
            "hs_code": "080410", "hs_confirmed": True, "market": "Yemen"}).status_code for _ in range(2)]
    conn = storage._connect(db)
    try:
        rows = conn.execute("SELECT id,status FROM analyses").fetchall()
    finally:
        conn.close()
    assert len(rows) == 2 and len(seen) == 2, (rows, seen, statuses)
    record("F25", {"same_body_and_idempotency_header": True, "created_analysis_ids": [r[0] for r in rows],
        "engine_entries": len(seen), "statuses_after_intentional_sentinel": statuses,
        "provider_calls": 0, "scope": "new root research POST, not platform launch or resume"})

def main():
    # No outbound calls may escape any witness.
    with patch("requests.sessions.Session.request", side_effect=OSError("network disabled for offline audit")):
        for fn in [proof_tools, proof_faithfulness, proof_review_failure, proof_revision_partial,
                   proof_preferences, proof_resume_dependencies, proof_late_augment,
                   proof_analyst_metadata, proof_stream_eof, proof_price_units,
                   proof_resume_identity, proof_eval_contract, proof_eurostat_dimensions,
                   proof_trends_normalization, proof_capacity_units, proof_late_cancellation,
                   proof_price_catalog, proof_hs_reference_override, proof_analysis_foreign_keys,
                   proof_trace_retention, proof_new_request_replay]:
            fn()
    OUT.joinpath("reproduced_findings.json").write_text(
        json.dumps({"commit": "8143125ea37660986d616007ca1df355ad332b80", "findings": findings},
                   ensure_ascii=False, indent=2))
    print("WITNESSES", len(findings))

if __name__ == "__main__":
    main()
