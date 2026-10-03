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
            patch("silk_data_layer.comtrade_trade", return_value=[]), \
            patch("silk_storage._db_path", return_value=db):
        # نقصٌ فعلي ([] = لا سجل) ⇒ 409؛ تعذّر الجلب (None) ⇒ 503 ويُختبر منفصلاً.
        import api
        import silk_usage
        client = TestClient(api.create_app())
        hdr = {"X-API-Key": "s"}
        spent0 = silk_usage.usd_spent_today()   # دفترٌ قد يشاركه اختبارٌ سابق
        r = client.post("/research", headers=hdr, json={
            "product": "قهوة محمصة", "market": "Malaysia", "hs_code": "090121",
            "persist": True, "async_run": True, "hs_confirmed": True})
        assert r.status_code == 409, r.text[:300]
        d = r.json()["detail"]
        assert d["error"] == "insufficient_data_preflight"
        assert "سلسلة واردات لثلاث سنوات على الأقل" in d["missing"]
        assert not tools_calls                        # صفر نداء نموذج
        assert silk_usage.usd_spent_today() == spent0  # صفر حجز/خصم
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
    with patch.dict(os.environ, {"SILK_PREFLIGHT_TIMEOUT_S": "3"}), \
            patch("silk_data_layer.comtrade_trade",
                  return_value=[{"partnerCode": 0, "primaryValue": 89_400_000.0}]), \
            patch("silk_data_layer_v2.market_competitors_status",
                  return_value=([DataPoint({"partner": "IDN", "share": 19}, "UN Comtrade", 0.9, "",
                                           "2026-09-27")], False)), \
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


def test_preflight_reads_real_comtrade_shape_list_of_records():
    """بلاغ حي 2026-09-28: comtrade_trade تعيد list[dict] لا DataPoint — القراءة القديمة
    (.value) أعطت صفر سنوات فرُفض كل طلب /research بـ409."""
    from silk_market_resolver import resolve_market
    import silk_study_readiness as R
    ref, _ = resolve_market("Malaysia")
    with patch("silk_data_layer.comtrade_trade",
               return_value=[{"primaryValue": 1.0e6}, {"primaryValue": 2.0e6}]):
        # خروج مبكر عند الكفاية (مراجعة §58 على الدرس 288) — العدّ يقف عند MIN_YEARS.
        assert R._imports_years("090121", ref) == R.MIN_YEARS
    import pytest
    with patch("silk_data_layer.comtrade_trade", return_value=None), \
            pytest.raises(R.Unverified):          # تعذّر الجلب ≠ صفر سنوات
        R._imports_years("090121", ref)
    with patch("silk_data_layer.comtrade_trade", return_value=[]):
        assert R._imports_years("090121", ref) == 0


def test_preflight_total_timeout_is_one_budget_not_per_check():
    import time as _t
    from silk_market_resolver import resolve_market
    import silk_study_readiness as R
    ref, _ = resolve_market("Malaysia")
    slow = lambda *a, **k: _t.sleep(3) or []  # noqa: E731
    t0 = _t.monotonic()
    with patch.dict(os.environ, {"SILK_PREFLIGHT_TIMEOUT_S": "0.5"}), \
            patch("silk_data_layer.comtrade_trade", side_effect=slow), \
            patch("silk_data_layer_v2.market_competitors", side_effect=slow), \
            patch("silk_data_layer_v2.market_competitors_status", side_effect=slow), \
            patch("silk_tariffs_agent.tariff_with_fallback", side_effect=slow):
        # الدالة التي يستدعيها الفحص فعلاً — وإلا بلغ عاملٌ متخلّف بعد المهلة الشبكةَ الحقيقية.
        out = R.preflight("090121", ref)
    assert not out["ok"] and _t.monotonic() - t0 < 2.0


def test_transient_fetch_failure_is_503_unverified_not_409_insufficient():
    from fastapi.testclient import TestClient
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _client(db), \
            patch("silk_data_layer.comtrade_trade", return_value=None), \
            patch("silk_data_layer_v2.market_competitors_status", return_value=([], True)), \
            patch("silk_tariffs_agent.tariff_with_fallback", side_effect=OSError("down")), \
            patch("silk_storage._db_path", return_value=db):
        import api
        r = TestClient(api.create_app()).post("/research", headers={"X-API-Key": "s"}, json={
            "product": "قهوة", "market": "Malaysia", "hs_code": "090121",
            "persist": True, "async_run": True, "hs_confirmed": True})
    assert r.status_code == 503 and r.json()["detail"]["error"] == "preflight_unavailable"


def test_insufficient_409_carries_a_factory_readable_reason_without_api_flag():
    from fastapi.testclient import TestClient
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _client(db), \
            patch("silk_data_layer.comtrade_trade", return_value=[]), \
            patch("silk_data_layer_v2.market_competitors_status", return_value=([], False)), \
            patch("silk_tariffs_agent.tariff_with_fallback",
                  return_value=__import__("silk_data_layer").DataPoint(None, "WTO", 0.0, "لا سجل", "")), \
            patch("silk_storage._db_path", return_value=db):
        import api
        r = TestClient(api.create_app()).post("/research", headers={"X-API-Key": "s"}, json={
            "product": "قهوة", "market": "Malaysia", "hs_code": "090121",
            "persist": True, "async_run": True, "hs_confirmed": True})
    d = r.json()["detail"]
    assert r.status_code == 409 and "accept_limited" not in d["reason"] and "الناقص" in d["reason"]


def test_tariff_gap_alone_never_blocks_the_study():
    """بلاغ حي: «الناقص: الرسم الجمركي المنطبق» رفض الدراسة رغم توفّر الواردات والحصص."""
    from silk_data_layer import DataPoint
    from silk_market_resolver import resolve_market
    import silk_study_readiness as R
    ref, _ = resolve_market("Malaysia")
    with patch.dict(os.environ, {"SILK_PREFLIGHT_TIMEOUT_S": "3"}), \
            patch("silk_data_layer.comtrade_trade",
                  return_value=[{"partnerCode": 0, "primaryValue": 89_400_000.0}]), \
            patch("silk_data_layer_v2.market_competitors_status",
                  return_value=([DataPoint({"partner": "IDN", "share": 19}, "UN Comtrade", 0.9, "",
                                           "2026-09-27")], False)), \
            patch("silk_tariffs_agent.tariff_with_fallback",
                  return_value=DataPoint(None, "WTO", 0.0, "لا سجل", "")):
        out = R.preflight("090121", ref)
    assert out["ok"] and not out["missing"]
    assert out["advisory_gaps"] == ["الرسم الجمركي المنطبق"]


def _mirror_only_comtrade(mirror_recs):
    """سوقٌ لا تُبلِغ كومتريد عن نفسها: الاستعلام المباشر [] والمرآة (reporter=all) تحمل السجلات."""
    def fake(hs, reporter, year, flow="M", partner=0):
        if reporter == "all":
            return mirror_recs
        return []
    return fake


def test_preflight_counts_mirror_imports_and_shares_like_the_pipeline():
    """الدرس 288: خط الدراسة يحتاط بالمرآة (silk_llm_runtime) فالفحص المسبق يحتاط بها أيضاً —
    وإلا رُفضت سوقٌ لا تُبلِغ كومتريد (اليمن/ليبيا) رغم أن الدراسة تخدمها."""
    from silk_data_layer import DataPoint
    from silk_market_resolver import resolve_market
    import silk_study_readiness as R
    ref, _ = resolve_market("Malaysia")
    recs = [{"reporterCode": 360, "partnerCode": int(ref.m49), "primaryValue": 5_000_000.0}]
    with patch.dict(os.environ, {"SILK_PREFLIGHT_TIMEOUT_S": "3"}), \
            patch("silk_data_layer.comtrade_trade", side_effect=_mirror_only_comtrade(recs)), \
            patch("silk_data_layer_v2.market_competitors_status", return_value=([], False)), \
            patch("silk_tariffs_agent.tariff_with_fallback",
                  return_value=DataPoint(0.0, "WTO", 0.8, "", "2026-09-27")):
        out = R.preflight("090121", ref)
    assert out["ok"] and not out["missing"], out


def test_mirror_fetch_failure_is_unverified_not_insufficient():
    """المرآة تعذّر جلبها (None) ⇒ «غير مُتحقق» (503) لا «نقص بيانات» (409)."""
    from silk_data_layer import DataPoint
    from silk_market_resolver import resolve_market
    import silk_study_readiness as R
    ref, _ = resolve_market("Malaysia")
    with patch.dict(os.environ, {"SILK_PREFLIGHT_TIMEOUT_S": "3"}), \
            patch("silk_data_layer.comtrade_trade", side_effect=_mirror_only_comtrade(None)), \
            patch("silk_data_layer_v2.market_competitors_status", return_value=([], False)), \
            patch("silk_tariffs_agent.tariff_with_fallback",
                  return_value=DataPoint(0.0, "WTO", 0.8, "", "2026-09-27")):
        out = R.preflight("090121", ref)
    assert not out["ok"] and out["missing"]
    assert set(out["missing"]) <= set(out["unverified"]), out


def _all_markets():
    """كل أسواق المنصّة (data/countries.csv، ٢٥٠ صفاً) — ما له رمز M49 فقط."""
    from silk_market_resolver import _load, _to_ref
    return [_to_ref(r, 1.0) for r in _load() if (r.get("m49") or "").strip()]


def test_every_market_has_a_tariff_reporter_code():
    """الدرس 288 (كل الدراسات لا واحدة): رمز المُبلِّغ كان من جدول ثابت لـ٧٢ دولة، فـ١٦٨ سوقاً
    لا تُسأل WITS ولا WTO عن تعرفتها أصلاً. المرجع `countries.csv` يحمل الرمز الرقمي للجميع."""
    from silk_tariffs_agent import _wits_reporter_code, _EU_ISO3, _EU_WITS_CODE
    missing = []
    for m in _all_markets():
        code, is_eu = _wits_reporter_code(m.iso3)
        want = _EU_WITS_CODE if m.iso3 in _EU_ISO3 else m.m49.zfill(3)
        if code != want or is_eu != (m.iso3 in _EU_ISO3):
            missing.append((m.iso3, code, want))
    assert not missing, missing[:20]
    assert _wits_reporter_code("MYS") == ("458", False)
    assert _wits_reporter_code("UNK") == (None, False)    # كوسوفو: لا رمز M49 ⇒ فجوة معلنة
    assert _wits_reporter_code("") == (None, False)


def test_preflight_sweep_over_every_market():
    """الفحص المسبق لكل سوق: تعرفة غائبة وحدها لا ترفض، وسوقٌ تخدمها المرآة لا تُرفض."""
    from silk_data_layer import DataPoint
    import silk_study_readiness as R
    no_tariff = DataPoint(None, "World Bank WITS", 0.0, "لا سجل", "")
    present = [{"reporterCode": 360, "partnerCode": 0, "primaryValue": 5_000_000.0}]
    share = ([DataPoint({"partner": "IDN", "share": 19}, "UN Comtrade", 0.9, "", "2026-09-27")], False)
    refused = []
    with patch.dict(os.environ, {"SILK_PREFLIGHT_TIMEOUT_S": "3"}), \
            patch("silk_tariffs_agent.tariff_with_fallback", return_value=no_tariff):
        for m in _all_markets():
            with patch("silk_data_layer.comtrade_trade", return_value=present), \
                    patch("silk_data_layer_v2.market_competitors_status", return_value=share):
                a = R.preflight("090121", m)
            with patch("silk_data_layer.comtrade_trade", side_effect=_mirror_only_comtrade(present)), \
                    patch("silk_data_layer_v2.market_competitors_status", return_value=([], False)):
                b = R.preflight("090121", m)
            for label, out in (("tariff-gap", a), ("mirror", b)):
                if not out["ok"]:
                    refused.append((m.iso3, label, out["missing"]))
    assert not refused, refused[:20]


def test_mirror_path_fits_the_comtrade_throttle_budget():
    """مراجعة §58 على الدرس 288: سوقٌ لا تُبلِغ كومتريد كانت تحتاج ١٠ نداءات مُتباعدة ١٫١ث فتتجاوز
    مهلة ٨ث ⇒ 503 وفشل الدراسة «لعطل تقني» في أول إطلاق. القفل: خروج مبكر عند حسم السنوات،
    مرآة السنة الأحدث تُجلب مرةً واحدة للفحصين، ومهلة افتراضية تتّسع لمباعدة كومتريد."""
    import threading
    from silk_data_layer import DataPoint
    from silk_market_resolver import resolve_market
    import silk_study_readiness as R
    ref, _ = resolve_market("Yemen")
    calls, lock = [], threading.Lock()
    recs = [{"reporterCode": 682, "partnerCode": int(ref.m49), "primaryValue": 2_000_000.0}]

    def fake(hs, reporter, year, flow="M", partner=0):
        with lock:
            calls.append((reporter, year, flow))
        return recs if reporter == "all" else []
    with patch.dict(os.environ, {"SILK_PREFLIGHT_TIMEOUT_S": "3"}), \
            patch("silk_data_layer.comtrade_trade", side_effect=fake), \
            patch("silk_data_layer_v2.market_competitors_status", return_value=([], False)), \
            patch("silk_tariffs_agent.tariff_with_fallback",
                  return_value=DataPoint(None, "WTO", 0.0, "لا سجل", "")):
        out = R.preflight("040630", ref)
    assert out["ok"], out
    y0 = __import__("datetime").date.today().year - 1
    mirrors = [c for c in calls if c[0] == "all"]
    assert mirrors.count(("all", y0, "X")) == 1, calls          # single-flight بين الفحصين
    assert len(calls) <= 6, calls                               # ٣ سنوات مباشر+مرآة ثم توقّف
    assert (ref.m49, y0 - 3, "M") not in calls, calls           # لا سنة رابعة بعد الحسم
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SILK_PREFLIGHT_TIMEOUT_S", None)
        assert R._timeout_s() >= 20                              # ٧ نداءات × ١٫١ث + زمن الشبكة


def test_shares_mirror_is_tried_even_when_the_direct_fetch_failed():
    """تكافؤ مع `competition_summary_findings`: فشل الجلب المباشر لا يمنع المرآة."""
    from silk_market_resolver import resolve_market
    import silk_study_readiness as R
    ref, _ = resolve_market("Yemen")
    recs = [{"reporterCode": 682, "partnerCode": int(ref.m49), "primaryValue": 2_000_000.0}]
    with patch("silk_data_layer.comtrade_trade", side_effect=_mirror_only_comtrade(recs)), \
            patch("silk_data_layer_v2.market_competitors_status", return_value=([], True)):
        assert R._shares_present("040630", ref) is True
    import pytest
    with patch("silk_data_layer.comtrade_trade", side_effect=_mirror_only_comtrade([])), \
            patch("silk_data_layer_v2.market_competitors_status", return_value=([], True)), \
            pytest.raises(R.Unverified):                         # المباشر مجهول والمرآة فارغة
        R._shares_present("040630", ref)


def _lagging_market_competitors(y0):
    """سوقٌ لم تُودِع سنتها الأخيرة بعد (شائع حتى منتصف السنة): السنة الأحدث فارغة، السابقة حاضرة."""
    from silk_data_layer import DataPoint

    def fake(hs, m49, year):
        if year == y0:
            return []
        return [DataPoint({"partner": "Indonesia", "code": "360", "value_usd": 9e6, "share": 60.0},
                          "UN Comtrade", 0.9, "", "2026-10-03"),
                DataPoint({"partner": "Brazil", "code": "76", "value_usd": 6e6, "share": 40.0},
                          "UN Comtrade", 0.9, "", "2026-10-03")]
    return fake


def test_supplier_shares_fall_back_to_the_previous_year_in_pipeline_and_preflight():
    """الدرس 288 (كل الدراسات): جدول المورّدين وفحص الحصص كانا يقرآن السنة الأحدث وحدها — فكل سوق
    لم تُودِع سنتها الأخيرة بعد تُرفض أو تفقد جدولها. بلا سنة صريحة: الأحدث ثم السابقة، موسومة."""
    import datetime as _dt
    from silk_market_resolver import resolve_market
    from silk_llm_runtime import competition_summary_findings
    import silk_study_readiness as R
    ref, _ = resolve_market("Malaysia")
    y0 = _dt.date.today().year - 1
    with patch("silk_data_layer_v2.market_competitors", side_effect=_lagging_market_competitors(y0)), \
            patch("silk_data_layer_v2.market_competitors_mirror", return_value=[]):
        out = competition_summary_findings("090121", ref)
        explicit = competition_summary_findings("090121", ref, year=y0)
    assert out[0].value["year"] == y0 - 1 and out[0].value["supplier_count"] == 2, out[0].note
    assert explicit[0].value is None                      # السنة الصريحة تُحترم حرفياً
    rows = _lagging_market_competitors(y0)

    def status(hs, m49, year):
        return rows(hs, m49, year), False
    with patch("silk_data_layer_v2.market_competitors_status", side_effect=status), \
            patch("silk_data_layer.comtrade_trade", return_value=[]):
        assert R._shares_present("090121", ref) is True
