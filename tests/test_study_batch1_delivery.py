"""الدفعة ١ — الجاهزية قبل الخصم (P1-1)، سقف التكلفة الافتراضي (P1-2)، المهلة الكلية (P1-4)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fake_tools(system, messages, tools=None, max_tokens=None, model=None, timeout=None, **kw):
    return {"text": json.dumps({"findings": []}), "tool_calls": [], "stop_reason": "end_turn",
            "usage": {"input_tokens": 50, "output_tokens": 20}}


def _fake_call(system, user, max_tokens=1600, model=None, timeout=None):
    return json.dumps({"verdict": "WATCH", "confidence": 0.5, "reasoning": "ok"})


def _fake_writer(system, user, max_tokens=1600, model=None, timeout=None):
    return "## 1. الخلاصة التنفيذية\nتقرير تجريبي."


def _client(db, extra_env=None):
    env = {"ANTHROPIC_API_KEY": "t", "SILK_API_KEY": "s", "SILK_RATE_LIMIT": "100000",
           "SILK_DATA_DIR": tempfile.mkdtemp(), "SILK_PREFLIGHT": "1", "SILK_PREFLIGHT_TIMEOUT_S": "3"}
    env.update(extra_env or {})
    return patch.dict(os.environ, env)


# ── P1-1 ──────────────────────────────────────────────────────────────────
def test_preflight_refuses_before_any_reservation_or_model_call():
    from fastapi.testclient import TestClient
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    tools_calls = []

    def counting_tools(*a, **k):
        tools_calls.append(1)
        return _fake_tools(*a, **k)
    with _client(db), \
            patch("silk_llm_runtime._call_tools", side_effect=counting_tools), \
            patch("silk_synthesis._call", side_effect=_fake_call), \
            patch("silk_ai_judge._call", side_effect=_fake_writer), \
            patch("silk_data_layer._cached_get", return_value=None), \
            patch("silk_data_layer._http_get", side_effect=OSError("no net")), \
            patch("silk_storage._db_path", return_value=db):
        import api
        import silk_usage
        client = TestClient(api.create_app())
        hdr = {"X-API-Key": "s"}
        r = client.post("/research", headers=hdr, json={
            "product": "قهوة محمصة", "market": "Malaysia", "hs_code": "090121",
            "persist": True, "async_run": True, "hs_confirmed": True})
        assert r.status_code == 409, r.text[:300]
        d = r.json()["detail"]
        assert d["error"] == "insufficient_data_preflight"
        assert "سلسلة واردات لثلاث سنوات على الأقل" in d["missing"]
        assert not tools_calls                        # صفر نداء نموذج
        assert silk_usage.usd_spent_today() == 0.0    # صفر حجز/خصم
        # accept_limited → يُقبل ويُشغَّل
        r2 = client.post("/research", headers=hdr, json={
            "product": "قهوة محمصة", "market": "Malaysia", "hs_code": "090121",
            "persist": True, "async_run": True, "hs_confirmed": True, "accept_limited": True})
        assert r2.status_code == 202, r2.text[:300]
        aid = r2.json()["analysis_id"]
        for _ in range(3000):
            st = client.get(f"/research/{aid}/status", headers=hdr).json()
            if st.get("status") and st["status"] != "running":
                break
            time.sleep(0.01)
        assert st.get("status") == "completed"


def test_preflight_passes_when_the_three_signals_exist():
    from silk_data_layer import DataPoint
    from silk_market_resolver import resolve_market
    import silk_study_readiness as R
    ref, _ = resolve_market("Malaysia")
    ok_dp = DataPoint(1000.0, "UN Comtrade", 0.9, "imports", "2026-09-27")
    with patch.dict(os.environ, {"SILK_PREFLIGHT_TIMEOUT_S": "3"}), \
            patch("silk_data_layer.comtrade_trade", return_value=ok_dp), \
            patch("silk_data_layer_v2.market_competitors",
                  return_value=[DataPoint({"partner": "IDN", "share": 19}, "UN Comtrade", 0.9, "", "2026-09-27")]), \
            patch("silk_tariffs_agent.tariff_with_fallback",
                  return_value=DataPoint(0.0, "WTO", 0.8, "", "2026-09-27")):
        out = R.preflight("090121", ref)
    assert out["ok"] and not out["missing"]


# ── P1-2 / P1-4 ─────────────────────────────────────────────────────────
def _run_pipeline_with(env_extra: dict, usage_cost: float):
    """تشغيلة محاكاة كاملة؛ تكلفة النداءات تُزوَّر عبر silk_pricing لتتجاوز السقف."""
    from fastapi.testclient import TestClient
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _client(db, {"SILK_PREFLIGHT": "0", **env_extra}), \
            patch("silk_llm_runtime._call_tools", side_effect=_fake_tools), \
            patch("silk_synthesis._call", side_effect=_fake_call), \
            patch("silk_ai_judge._call", side_effect=_fake_writer), \
            patch("silk_data_layer._cached_get", return_value=None), \
            patch("silk_data_layer._http_get", side_effect=OSError("no net")), \
            patch("silk_storage._db_path", return_value=db), \
            patch("silk_pricing.estimate_cost_usd", return_value={"total_usd": usage_cost, "by_model": {}, "unpriced_models": []}):
        import api
        client = TestClient(api.create_app())
        hdr = {"X-API-Key": "s"}
        r = client.post("/research", headers=hdr, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True, "async_run": True, "hs_confirmed": True})
        assert r.status_code == 202, r.text[:300]
        aid = r.json()["analysis_id"]
        for _ in range(3000):
            st = client.get(f"/research/{aid}/status", headers=hdr).json()
            if st.get("status") and st["status"] != "running":
                break
            time.sleep(0.01)
        assert st.get("status") == "completed", st
        return client.get(f"/analyses/{aid}", headers=hdr).json()


def test_default_usd_cap_halts_tail_and_still_delivers():
    res = _run_pipeline_with({}, usage_cost=9.0)      # > 4.0$ الافتراضي
    econ = res.get("data_economics") or {}
    bs = (res.get("deep_research") or {}).get("budget_status") or {}
    assert "SILK_RESEARCH_MAX_USD" in json.dumps(bs, ensure_ascii=False) + json.dumps(econ, ensure_ascii=False)
    assert "cost_usd_by_stage" in econ


def test_explicit_zero_disables_the_usd_cap():
    res = _run_pipeline_with({"SILK_RESEARCH_MAX_USD": "0"}, usage_cost=9.0)
    bs = (res.get("deep_research") or {}).get("budget_status") or {}
    assert "SILK_RESEARCH_MAX_USD" not in json.dumps(bs, ensure_ascii=False)


def test_run_timeout_halts_tail_and_delivers():
    import silk_research_pipeline as P
    real = P.__dict__.get("_mono") or __import__("time")
    # مهلة صفرية عملياً: 0.0001 دقيقة → أي مرحلة لاحقة تُتخطى معلَنة
    res = _run_pipeline_with({"SILK_RESEARCH_MAX_MINUTES": "0.0001"}, usage_cost=0.0)
    bs = (res.get("deep_research") or {}).get("budget_status") or {}
    assert "SILK_RESEARCH_MAX_MINUTES" in json.dumps(bs, ensure_ascii=False)
