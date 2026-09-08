"""صمود خطّ /research — الموجة p6 (تدقيق التنفيذ من الطرف إلى الطرف، 2026-08-22).

البلاغ الحيّ (الفرع ب): اكتملت البعثات → مهلة قراءة في المحلل ابتُلعت →
الكاتب شُغِّل على نصّ الخطأ → مهلة قراءة → تقرير None → بوّابة الجودة
analyst_layer_failed → «أُرجعت الحصة». ثمن المحلل (أغلى نداء في التشغيلة)
كان يعيش في الذاكرة حتى الحفظ النهائي ولا يُسترَدّ أبداً.

يقفل هذا الملف مهامّ الخطة `docs/superpowers/plans/2026-08-22-research-
pipeline-resilience.md`:
  T1 — نقاط تفتيش المراحل (`research_stages`) + `mark_research_failed` يدمج
       ولا يستبدل json_blob (الاختبار المطلوب ج).
كل شيء هرمتي — لا شبكة، لا مفتاح كلود.
Run:  python -m pytest tests/test_wave_p6_pipeline_resilience.py -q
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_provider_contextvars():
    """مموّهات هذا الملف تضبط `_last_error` مباشرةً (محاكاة إجهاض/مهلة) ولا
    يمرّ نداء مزوّد حقيقي يعيد ضبطه — فلا يتسرّب إلى اختبارات لاحقة (حارس
    T3 يقرأه). إعادة ضبط قبل كل اختبار وبعده."""
    import silk_llm_provider as lp
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)
    yield
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)


def _tmp_db() -> str:
    return os.path.join(tempfile.mkdtemp(), "silk.db")


def _seed_run(db: str, market_iso3: str = "NLD") -> int:
    from silk_storage import create_research_run
    return create_research_run("تمور", market_iso3, "080410",
                               {"product": "تمور", "market": market_iso3},
                               path=db)


# ── T1 · نقاط تفتيش المراحل · stage checkpoints ──────────────────────────────

def test_stage_checkpoint_roundtrip_and_replace():
    """حفظ مرحلة → تحميلها بنفس الحمولة والحالة؛ حفظ ثانٍ لنفس المفتاح
    **يستبدل** الصفّ (مفتاح أساسي مركّب) ولا يكرّره."""
    from silk_storage import (load_stage_checkpoints, save_stage_checkpoint,
                              _connect)
    db = _tmp_db()
    aid = _seed_run(db)
    save_stage_checkpoint(aid, "analyst", {"summary": "تحليل", "n": 1},
                          status="succeeded", market_iso3="NLD", path=db)
    got = load_stage_checkpoints(aid, path=db)
    assert set(got) == {"analyst"}
    assert got["analyst"]["status"] == "succeeded"
    assert got["analyst"]["payload"] == {"summary": "تحليل", "n": 1}
    assert got["analyst"]["completed_at"]
    save_stage_checkpoint(aid, "analyst", {"summary": "تحليل ٢"},
                          status="failed", market_iso3="NLD", path=db)
    got = load_stage_checkpoints(aid, path=db)
    assert got["analyst"]["status"] == "failed"
    assert got["analyst"]["payload"] == {"summary": "تحليل ٢"}
    with _connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM research_stages "
                         "WHERE analysis_id = ?", (aid,)).fetchone()[0]
    assert n == 1


def test_stage_checkpoint_serializes_dataclasses_like_missions():
    """حمولة تحمل DataPoint/AgentReport تُسلسَل كما تُسلسَل نقاط تفتيش البعثات
    (`_json_default`) — لا استثناء، وتعود كقاموس."""
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    from silk_storage import load_stage_checkpoints, save_stage_checkpoint
    db = _tmp_db()
    aid = _seed_run(db)
    rep = AgentReport("LLMAgent:analyst",
                      [DataPoint("v", "src", 0.7, "[demand] note", "2026-01-01")],
                      False, "ملخّص")
    save_stage_checkpoint(aid, "analyst", {"raw_report": rep, "summary": "x"},
                          path=db)
    got = load_stage_checkpoints(aid, path=db)["analyst"]["payload"]
    assert got["summary"] == "x"
    assert got["raw_report"]["findings"][0]["value"] == "v"


def test_stage_checkpoint_market_filter_rejects_other_market_keeps_legacy():
    """نفس عقد `load_mission_checkpoints`: صفّ مختوم بسوقٍ آخر يُرفَض عند
    طلب سوقٍ محدّد؛ صفّ بلا ختم (قديم) لا يُحجَب."""
    from silk_storage import load_stage_checkpoints, save_stage_checkpoint
    db = _tmp_db()
    aid = _seed_run(db)
    save_stage_checkpoint(aid, "analyst", {"a": 1}, market_iso3="NLD", path=db)
    save_stage_checkpoint(aid, "leads", {"b": 2}, market_iso3=None, path=db)
    got = load_stage_checkpoints(aid, market_iso3="KWT", path=db)
    assert "analyst" not in got          # سوق آخر — مرفوض
    assert got["leads"]["payload"] == {"b": 2}   # بلا ختم — يمرّ
    got_all = load_stage_checkpoints(aid, path=db)
    assert set(got_all) == {"analyst", "leads"}


def test_stage_checkpoint_missing_db_or_run_returns_empty():
    from silk_storage import load_stage_checkpoints
    assert load_stage_checkpoints(999, path=os.path.join(
        tempfile.mkdtemp(), "absent.db")) == {}
    db = _tmp_db()
    _seed_run(db)
    assert load_stage_checkpoints(12345, path=db) == {}


def test_stage_checkpoint_touches_updated_at():
    """نقطة تفتيش مرحلة تحدّث `analyses.updated_at` كما تفعل نقطة تفتيش البعثة
    — المكنَس (٣٠ دقيقة) يقرأه ليميّز الحيّ عن اليتيم."""
    from silk_storage import save_stage_checkpoint, _connect
    db = _tmp_db()
    aid = _seed_run(db)
    with _connect(db) as conn:
        conn.execute("UPDATE analyses SET updated_at = '2000-01-01T00:00:00' "
                     "WHERE id = ?", (aid,))
    save_stage_checkpoint(aid, "verdict", {"v": "GO"}, path=db)
    with _connect(db) as conn:
        ts = conn.execute("SELECT updated_at FROM analyses WHERE id = ?",
                          (aid,)).fetchone()[0]
    assert ts and ts > "2000-01-02"


# ── T1 · mark_research_failed يدمج لا يستبدل (الاختبار المطلوب ج) ────────────

def test_mark_research_failed_merges_prior_blob():
    """صفّ يحمل نتيجة كاملة (محلل + حكم + بعثات مدفوعة) ثم يفشل الذيل —
    الوسم `failed` يُضاف فوق النتيجة ولا يمحوها: كل مفتاح سابق يبقى."""
    from silk_storage import get_analysis, mark_research_failed, _connect
    db = _tmp_db()
    aid = _seed_run(db)
    prior = {"product": "تمور", "hs_code": "080410",
             "deep_research": {"missions": {"m1": {"summary": "ok"}},
                               "analyst": {"summary": "تحليل مدفوع"},
                               "verdict": {"verdict": "WATCH"}},
             "data_economics": {"llm_calls": 30, "cost_usd_estimate": 1.87}}
    with _connect(db) as conn:
        conn.execute("UPDATE analyses SET json_blob = ? WHERE id = ?",
                     (json.dumps(prior, ensure_ascii=False), aid))
    mark_research_failed(aid, "RuntimeError: boom", path=db)
    blob = get_analysis(aid, path=db)
    for key in prior:
        assert blob[key] == prior[key], f"prior key {key} lost/changed"
    assert blob["status"] == "failed"
    assert blob["error"] == "RuntimeError: boom"
    assert blob["failed_at"]
    with _connect(db) as conn:
        st = conn.execute("SELECT status FROM analyses WHERE id = ?",
                          (aid,)).fetchone()[0]
    assert st == "failed"


def test_mark_research_failed_without_prior_blob_writes_small_dict():
    """بلا نتيجة سابقة (NULL) — السلوك القائم: قاموس صغير {status, error}."""
    from silk_storage import get_analysis, mark_research_failed, _connect
    db = _tmp_db()
    aid = _seed_run(db)
    with _connect(db) as conn:
        conn.execute("UPDATE analyses SET json_blob = NULL WHERE id = ?", (aid,))
    mark_research_failed(aid, "X", path=db)
    blob = get_analysis(aid, path=db)
    assert blob == {"status": "failed", "error": "X", "failed_at": blob["failed_at"]}


def test_mark_research_failed_corrupt_blob_does_not_crash():
    """JSON فاسد في الصفّ — لا استثناء؛ يُكتب القاموس الصغير (لا اختلاق دمج)."""
    from silk_storage import get_analysis, mark_research_failed, _connect
    db = _tmp_db()
    aid = _seed_run(db)
    with _connect(db) as conn:
        conn.execute("UPDATE analyses SET json_blob = '{not json' WHERE id = ?",
                     (aid,))
    mark_research_failed(aid, "Y", path=db)
    blob = get_analysis(aid, path=db)
    assert blob["status"] == "failed" and blob["error"] == "Y"


def test_mark_research_failed_placeholder_running_blob_is_merged_too():
    """صفّ حديث الإنشاء يحمل {"status":"running", product, hs_code} — يُدمَج
    (status يصير failed، product/hs_code يبقيان) — سلوك متّسق لا فرعان."""
    from silk_storage import get_analysis, mark_research_failed
    db = _tmp_db()
    aid = _seed_run(db)
    mark_research_failed(aid, "Z", path=db)
    blob = get_analysis(aid, path=db)
    assert blob["status"] == "failed" and blob["error"] == "Z"
    assert blob["product"] == "تمور" and blob["hs_code"] == "080410"


# ── T2 · الخطّ يحفظ المحلل/الحكم/الروابط فور عودتها + مصالحة الدولار مرّة ────

def _client():
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


_ANALYST_JSON = json.dumps({
    "findings": [{"claim": "طلب حقيقي", "category": "demand",
                  "confidence": 0.7, "datapoint_ids": ["dp1"]}],
    "gaps": [], "summary": "تحليل شامل مموّه"})


def _fake_call_tools_ok(system, messages, tools=None, max_tokens=1600,
                        model=None, timeout=None, **kw):
    return {"stop_reason": "end_turn", "content": [
        {"type": "text", "text": _ANALYST_JSON}]}


def _fake_call_verdict(system, user, max_tokens=1600, model=None,
                       timeout=None, **kw):
    return json.dumps({"verdict": "WATCH", "confidence": 0.5, "reasoning": "ok"})


class _CompletedMission:
    """بعثة مكتملة مموّهة (failed=False) — نفس نمط wave13."""
    def __init__(self, spec):
        self._key = spec["key"]

    def run(self, task):
        from silk_agents import AgentReport
        from silk_data_layer import DataPoint
        # نتيجة واحدة حقيقية الشكل كي يستطيع المحلل الاستشهاد بـdp1
        return AgentReport(
            f"LLMMissionAgent:{self._key}",
            [DataPoint("قيمة مموّهة", "UN Comtrade", 0.8,
                       f"{self._key}: بند مموّه", "2026-01-01")],
            False, "ok")


def _research_env(db: str, usage_db: str | None = None):
    from unittest.mock import patch
    env = {"ANTHROPIC_API_KEY": "test", "SILK_API_KEY": "secret"}
    if usage_db:
        env["SILK_USAGE_DB"] = usage_db
    return [patch.dict(os.environ, env),
            patch("silk_llm_runtime._call_tools", side_effect=_fake_call_tools_ok),
            patch("silk_synthesis._call", side_effect=_fake_call_verdict),
            patch("silk_storage._db_path", return_value=db),
            patch("silk_missions.LLMMissionAgent", _CompletedMission)]


def test_pipeline_checkpoints_analyst_verdict_leads_before_writer():
    """بعد عودة المحلل مباشرة — وقبل أول نداء كاتب — يوجد صفّ `analyst` في
    research_stages؛ وبنهاية التشغيلة صفّا `verdict` و`leads` أيضاً."""
    import contextlib
    from unittest.mock import patch
    from silk_storage import load_stage_checkpoints
    db = _tmp_db()
    seen: dict = {}

    def writer_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        # لحظة أول نداء كاتب: هل المحلل محفوظ فعلاً؟ (لا بعد التشغيلة)
        if "analyst_at_writer" not in seen:
            import silk_storage
            rows = silk_storage.load_stage_checkpoints(seen["aid"], path=db)
            seen["analyst_at_writer"] = rows.get("analyst")
        return "## 1. تقرير\nنصّ تقرير مموّه."

    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch("silk_ai_judge._call", side_effect=writer_call))
        import silk_storage
        real_create = silk_storage.create_research_run

        def create_and_remember(*a, **k):
            aid = real_create(*a, **k)
            seen["aid"] = aid
            return aid
        st.enter_context(patch("silk_storage.create_research_run",
                               side_effect=create_and_remember))
        client = _client()
        r = client.post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text
    aid = r.json()["analysis_id"]
    assert seen["analyst_at_writer"] is not None, \
        "analyst stage not checkpointed before the writer ran"
    assert seen["analyst_at_writer"]["status"] == "succeeded"
    assert seen["analyst_at_writer"]["payload"]["analyst_input"]["summary"]
    stages = load_stage_checkpoints(aid, path=db)
    assert {"analyst", "verdict", "leads"} <= set(stages)
    assert stages["verdict"]["payload"].get("verdict")
    # الحمولة بالشكل المخزَّن (T4 يعيد استعمالها حرفياً): analyst_out + analyst_input
    a_out = stages["analyst"]["payload"]["analyst_out"]
    assert a_out["report"]["summary"] and "by_category" in a_out
    assert a_out["diagnostics"]["analyst_failed"] is False


def test_pipeline_checkpoints_failed_analyst_as_failed():
    """محلل فشل نداؤه → الصفّ `analyst` يُحفَظ بحالة failed (لا يُهمَل)."""
    import contextlib
    from unittest.mock import patch
    from silk_storage import load_stage_checkpoints
    db = _tmp_db()

    def analyst_none(system, messages, tools=None, max_tokens=1600,
                     model=None, timeout=None, **kw):
        return None   # المزوّد ابتلع ReadTimeout => None

    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch("silk_llm_runtime._call_tools",
                               side_effect=analyst_none))
        st.enter_context(patch("silk_ai_judge._call",
                               side_effect=lambda *a, **k: "## 1. x\nنصّ."))
        client = _client()
        r = client.post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text
    stages = load_stage_checkpoints(r.json()["analysis_id"], path=db)
    assert stages["analyst"]["status"] == "failed"


def test_usd_reservation_released_exactly_once():
    """الاختبار المطلوب (د): فشلٌ **بعد** reconcile_usd (كتابة الحفظ النهائي
    تفشل على الخيط الخلفي) لا يُصالح الحجز مرّة ثانية.
    الدفتر مُبذَر بـ5$ قبل التشغيلة كي لا تخفي أرضيةُ الصفر الخصمَ المزدوج:
    حجز 3 → 8؛ مصالحة للفعلي (0) → 5؛ مصالحة ثانية خاطئة → 2."""
    import contextlib
    import time
    from unittest.mock import patch
    import silk_usage
    db = _tmp_db()
    usage_db = os.path.join(os.path.dirname(db), "usage.db")
    silk_usage.record_usd(5.0, path=usage_db)
    import silk_storage
    real_save = silk_storage.save_analysis
    calls = {"n": 0}

    def save_fails_once(result, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated disk write failure after reconcile")
        return real_save(result, *a, **k)

    with contextlib.ExitStack() as st:
        for p in _research_env(db, usage_db=usage_db):
            st.enter_context(p)
        st.enter_context(patch("silk_ai_judge._call",
                               side_effect=lambda *a, **k: "## 1. x\nنصّ."))
        st.enter_context(patch("silk_storage.save_analysis",
                               side_effect=save_fails_once))
        client = _client()
        r = client.post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True, "async_run": True})
        assert r.status_code == 202, r.text
        aid = r.json()["analysis_id"]
        deadline = time.monotonic() + 60
        status = "running"
        while time.monotonic() < deadline:
            s = client.get(f"/research/{aid}/status",
                           headers={"X-API-Key": "secret"}).json()
            status = s["status"]
            if status != "running":
                break
            time.sleep(0.2)
    assert status == "failed", status
    assert calls["n"] == 1
    spent = silk_usage.usd_spent_today(path=usage_db)
    assert abs(spent - 5.0) < 1e-6, f"ledger {spent}: reservation reconciled twice"
    prog = silk_storage.get_research_progress(aid, path=db)
    assert prog.get("usd_reconciled") is True


# ── T3 · فشل نداء المحلل يوقف الكاتب — لا يُطعَم نصّ الخطأ (الاختبار المطلوب أ) ──

def _run_with_analyst_http(db: str, post_side_effect, writer_calls: list,
                           ops: list):
    """شغّل /research هرمتياً: البعثات مموّهة، المحلل يمرّ عبر المزوّد الحقيقي
    (requests.post مموّه بـ`post_side_effect`)، الكاتب مموّه عدّاداً."""
    import contextlib
    from unittest.mock import patch

    def writer_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        writer_calls.append(user[:80])
        return "## 1. تقرير\nنصّ."

    with contextlib.ExitStack() as st:
        st.enter_context(patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test",
                                                 "SILK_API_KEY": "secret",
                                                 "SILK_LLM_MAX_RETRIES": "0"}))
        st.enter_context(patch("silk_storage._db_path", return_value=db))
        st.enter_context(patch("silk_missions.LLMMissionAgent", _CompletedMission))
        st.enter_context(patch("silk_synthesis._call", side_effect=_fake_call_verdict))
        st.enter_context(patch("silk_ai_judge._call", side_effect=writer_call))
        # المراجع يشارك `_call` — يُحيَّد كي يعني العدّاد «نداءات الكاتب» حصراً
        st.enter_context(patch("silk_ai_judge.review_report",
                               return_value={"approved": True, "issues": [],
                                             "blocking": False}))
        st.enter_context(patch("requests.post", side_effect=post_side_effect))
        st.enter_context(patch("silk_ops_log.record_error",
                               side_effect=lambda kind, reason, context=None, **k:
                               ops.append((kind, reason, context))))
        client = _client()
        return client.post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})


def test_analyst_timeout_does_not_invoke_writer():
    """الفرع ب الحيّ: ReadTimeout في المحلل ابتُلع → الكاتب شُغِّل على نصّ الخطأ
    بثمن كامل. الآن: فشل **نداء** المحلل = لا كاتب؛ البعثات والحكم محفوظة؛
    الرد جزئي معلَن يحمل نوع الخطأ وهل يستحق إعادة المحاولة."""
    import requests
    from silk_storage import load_stage_checkpoints
    db = _tmp_db()
    writer_calls: list = []
    ops: list = []
    r = _run_with_analyst_http(
        db, requests.exceptions.ReadTimeout("read timed out"), writer_calls, ops)
    assert r.status_code == 200, r.text
    data = r.json()
    assert writer_calls == [], "writer was billed to consume the analyst error string"
    rep = data["deep_research"]["report"]
    assert rep["report"] is None
    assert rep["skipped"] == "writer"
    assert rep["skip_reason"] == "analyst_call_failed"
    assert rep["error_type"] == "ReadTimeout"
    assert rep["retryable"] is True
    assert "ReadTimeout" in rep["failure_reason"]
    assert len(data["deep_research"]["missions"]) == 12
    assert data["deep_research"]["verdict"].get("verdict")   # جورية المرحلة ١ عملت
    assert load_stage_checkpoints(data["analysis_id"], path=db)["analyst"]["status"] == "failed"
    assert any(k == "analyst_failure" for k, _, _ in ops)
    gate = data["view"]["deep_research"]["quality_gate"]
    assert any(f.get("check") == "analyst_layer_failed" for f in gate["findings"])


def test_analyst_permanent_error_is_not_retryable():
    """HTTP 400 من المزوّد (حمولة مرفوضة) — دائم: retryable=False، ورمز الحالة
    يصل النتيجة كي لا يُنصَح بإعادة محاولة عبثية."""
    import requests
    db = _tmp_db()
    writer_calls: list = []
    ops: list = []

    class _R400:
        status_code = 400
        text = '{"type":"invalid_request_error"}'
        headers = {}

        def raise_for_status(self):
            err = requests.exceptions.HTTPError("400 Client Error")
            err.response = self
            raise err

    r = _run_with_analyst_http(db, lambda *a, **k: _R400(), writer_calls, ops)
    assert r.status_code == 200, r.text
    rep = r.json()["deep_research"]["report"]
    assert writer_calls == []
    assert rep["skip_reason"] == "analyst_call_failed"
    assert rep["error_type"] == "HTTPError"
    assert rep["status_code"] == 400
    assert rep["retryable"] is False


def test_analyst_uncategorized_findings_still_reach_writer():
    """المحلل **نجح نداؤه** لكن بنوده بلا وسم [فئة] (findings_present_but_
    uncategorized) — هذه ليست فشل نداء: الكاتب يعمل كما اليوم."""
    db = _tmp_db()
    writer_calls: list = []
    ops: list = []
    text = json.dumps({"findings": [{"claim": "بند بلا فئة",
                                     "confidence": 0.6,
                                     "datapoint_ids": ["dp1"]}],
                       "gaps": [], "summary": "ok"})
    # المحلل يبثّ منذ T6 — المموّه يجيب SSE (نفس الشكل الذي يجمّعه المزوّد)
    sse = [
        "event: message_start",
        "data: " + json.dumps({"type": "message_start", "message": {
            "usage": {"input_tokens": 1}}}), "",
        "event: content_block_start",
        "data: " + json.dumps({"type": "content_block_start", "index": 0,
                               "content_block": {"type": "text", "text": ""}}), "",
        "event: content_block_delta",
        "data: " + json.dumps({"type": "content_block_delta", "index": 0,
                               "delta": {"type": "text_delta", "text": text}}), "",
        "event: content_block_stop",
        "data: " + json.dumps({"type": "content_block_stop", "index": 0}), "",
        "event: message_delta",
        "data: " + json.dumps({"type": "message_delta",
                               "delta": {"stop_reason": "end_turn"},
                               "usage": {"output_tokens": 1}}), "",
        "event: message_stop", "data: " + json.dumps({"type": "message_stop"}), ""]

    class _ROK:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True, **kw):
            yield from sse

        def close(self):
            pass

    r = _run_with_analyst_http(db, lambda *a, **k: _ROK(), writer_calls, ops)
    assert r.status_code == 200, r.text
    assert len(writer_calls) == 1
    rep = r.json()["deep_research"]["report"]
    assert rep["report"] and "skipped" not in rep


# ── T4 · الاستئناف يعيد استعمال المحلل المحفوظ (الاختبار المطلوب ب) ──────────

class _CountingMission(_CompletedMission):
    ran: list = []

    def run(self, task):
        _CountingMission.ran.append(self._key)
        return super().run(task)


def _first_run(db: str, writer_returns, analyst_ok: bool = True) -> int:
    """تشغيلة أولى هرمتية تنتج صفّاً `completed`؛ `writer_returns=None` =>
    بلا نصّ تقرير (الفرع ب)؛ `analyst_ok=False` => فشل نداء المحلل (T3)."""
    import contextlib
    from unittest.mock import patch
    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        if not analyst_ok:
            st.enter_context(patch("silk_llm_runtime._call_tools",
                                   side_effect=lambda *a, **k: None))
        st.enter_context(patch("silk_ai_judge._call",
                               side_effect=lambda *a, **k: writer_returns))
        st.enter_context(patch("silk_ai_judge.review_report",
                               return_value={"approved": True, "issues": [],
                                             "blocking": False}))
        r = _client().post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text
    return r.json()["analysis_id"]


def _resume(db: str, aid: int, analyst_calls: list, writer_calls: list):
    import contextlib
    from unittest.mock import patch
    import silk_market_analyst
    real_analyze = silk_market_analyst.analyze_market

    def counting_analyze(*a, **k):
        analyst_calls.append(1)
        return real_analyze(*a, **k)

    def writer_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        writer_calls.append(1)
        return "## 1. تقرير\nنصّ مُستأنَف."

    _CountingMission.ran = []
    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch("silk_missions.LLMMissionAgent", _CountingMission))
        st.enter_context(patch("silk_market_analyst.analyze_market",
                               side_effect=counting_analyze))
        st.enter_context(patch("silk_ai_judge._call", side_effect=writer_call))
        st.enter_context(patch("silk_ai_judge.review_report",
                               return_value={"approved": True, "issues": [],
                                             "blocking": False}))
        return _client().post("/research", headers={"X-API-Key": "secret"},
                              json={"resume": aid})


def test_resume_reuses_persisted_analyst_and_does_not_rerun_missions():
    """الفرع ب: مكتملة بلا نصّ تقرير، المحلل محفوظ ناجحاً → الاستئناف لا يعيد
    بعثة ولا المحلل؛ الكاتب وحده يعمل مرّة؛ نفس analysis_id؛ نصّ التقرير موجود."""
    db = _tmp_db()
    aid = _first_run(db, writer_returns=None)
    from silk_storage import get_analysis, load_stage_checkpoints
    assert get_analysis(aid, path=db)["deep_research"]["report"]["report"] is None
    assert load_stage_checkpoints(aid, path=db)["analyst"]["status"] == "succeeded"
    analyst_calls: list = []
    writer_calls: list = []
    r = _resume(db, aid, analyst_calls, writer_calls)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["analysis_id"] == aid
    assert _CountingMission.ran == [], "missions re-run on resume"
    assert analyst_calls == [], "persisted analyst was re-paid on resume"
    assert len(writer_calls) == 1
    assert data["deep_research"]["report"]["report"]
    assert data["deep_research"]["analyst"]["report"]["summary"]
    assert data["deep_research"]["analyst"].get("resumed_from_checkpoint") is True
    # الصفّ المخزَّن صار يحمل النصّ (نفس المعرّف، لا صفّ جديد)
    assert get_analysis(aid, path=db)["deep_research"]["report"]["report"]


def test_resume_reruns_failed_analyst_only():
    """المحلل محفوظ **فاشلاً** (T3) → الاستئناف يعيد المحلل وحده (لا بعثات)."""
    db = _tmp_db()
    aid = _first_run(db, writer_returns=None, analyst_ok=False)
    from silk_storage import load_stage_checkpoints
    assert load_stage_checkpoints(aid, path=db)["analyst"]["status"] == "failed"
    analyst_calls: list = []
    writer_calls: list = []
    r = _resume(db, aid, analyst_calls, writer_calls)
    assert r.status_code == 200, r.text
    assert _CountingMission.ran == []
    assert len(analyst_calls) == 1
    assert len(writer_calls) == 1
    assert r.json()["deep_research"]["report"]["report"]


def test_completed_with_report_text_is_pure_replay():
    """العقد القائم: مكتملة **بنصّ** → استئنافها إعادة تسليم بلا أيّ نداء."""
    db = _tmp_db()
    aid = _first_run(db, writer_returns="## 1. تقرير\nنصّ أصلي.")
    analyst_calls: list = []
    writer_calls: list = []
    r = _resume(db, aid, analyst_calls, writer_calls)
    assert r.status_code == 200
    assert _CountingMission.ran == [] and analyst_calls == [] and writer_calls == []
    assert "نصّ أصلي" in r.json()["deep_research"]["report"]["report"]


def test_regen_endpoint_prefers_analyst_stage_checkpoint():
    """POST /analyses/{id}/report: البلوب بلا محلل (فشل ذيل قديم) لكن نقطة
    تفتيش المرحلة موجودة → الكاتب يتسلّم ملخّص المرحلة لا سلسلة فارغة."""
    import contextlib
    from unittest.mock import patch
    from silk_storage import save_stage_checkpoint, _connect
    db = _tmp_db()
    aid = _first_run(db, writer_returns="## 1. x\nنصّ.")
    # امسح المحلل من البلوب فقط (محاكاة بلوب فقير) وأبقِ نقطة التفتيش
    with _connect(db) as conn:
        blob = json.loads(conn.execute("SELECT json_blob FROM analyses WHERE id=?",
                                       (aid,)).fetchone()[0])
        blob["deep_research"].pop("analyst", None)
        conn.execute("UPDATE analyses SET json_blob=? WHERE id=?",
                     (json.dumps(blob, ensure_ascii=False), aid))
    save_stage_checkpoint(aid, "analyst", {
        "analyst_out": {"report": {"summary": "ملخّص المرحلة المحفوظ"},
                        "by_category": {}, "missing_categories": [],
                        "diagnostics": {"analyst_failed": False}},
        "analyst_input": {"summary": "ملخّص المرحلة المحفوظ"}}, path=db)
    seen: dict = {}

    def writer_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        seen["user"] = user
        return "## 1. x\nنصّ مُعاد."

    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch("silk_ai_judge._call", side_effect=writer_call))
        st.enter_context(patch("silk_ai_judge.review_report",
                               return_value={"approved": True, "issues": [],
                                             "blocking": False}))
        r = _client().post(f"/analyses/{aid}/report",
                           headers={"X-API-Key": "secret"})
    assert r.status_code == 200, r.text
    assert "ملخّص المرحلة المحفوظ" in seen["user"]


def test_get_failed_analysis_returns_partial_missions_and_stages():
    """صفّ فاشل ببلوب فقير (عطل قبل أيّ حفظ) → GET /analyses/{id} يُلحِق
    البعثات المحفوظة ونقاط المراحل ويُعلِم `partial: true` — لا فشل فارغ."""
    import contextlib
    from unittest.mock import patch
    from silk_storage import (mark_research_failed, save_mission_checkpoint,
                              save_stage_checkpoint)
    from silk_agents import AgentReport
    db = _tmp_db()
    aid = _seed_run(db)
    for k in ("demand_signal", "pricing_scout"):
        save_mission_checkpoint(aid, k, AgentReport(f"LLMMissionAgent:{k}", [],
                                                    False, "ok"), path=db)
    save_stage_checkpoint(aid, "analyst", {"analyst_input": {"summary": "s"}},
                          path=db)
    mark_research_failed(aid, "RuntimeError: boom", path=db)
    with contextlib.ExitStack() as st:
        st.enter_context(patch.dict(os.environ, {"SILK_API_KEY": "secret"}))
        st.enter_context(patch("silk_storage._db_path", return_value=db))
        r = _client().get(f"/analyses/{aid}", headers={"X-API-Key": "secret"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "failed" and data["partial"] is True
    assert set(data["deep_research"]["missions"]) == {"demand_signal", "pricing_scout"}
    assert data["deep_research"]["stages"]["analyst"]["status"] == "succeeded"


# ── T6 · المحلل يبثّ؛ البعثات كما هي؛ الجزء المُجهَض يُحلَّل لا يُعاد توليده ──

def _market_ref():
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market("Nigeria")
    return ref


def test_analyst_passes_stream_true_regular_mission_does_not():
    """المحلل الشامل (النداء الثقيل) يمرّر stream=True؛ بعثة عادية لا تمرّره
    إطلاقاً (المسار الافتراضي حرفياً — مموّهات البعثات القائمة بلا **kw)."""
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_market_analyst
    from silk_llm_runtime import run_llm_agent
    from silk_missions import MISSIONS
    seen: list = []

    def fake_call_tools(system, messages, tools=None, max_tokens=1600,
                        model=None, timeout=None, **kw):
        seen.append(dict(kw))
        return {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": json.dumps(
                {"findings": [], "gaps": [], "summary": "ok"})}]}

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_llm_runtime._call_tools", side_effect=fake_call_tools):
        silk_market_analyst.analyze_market(
            _market_ref(), "تمور",
            {"demand_signal": AgentReport("LLMMissionAgent:demand_signal", [],
                                          False, "ok")},
            hs_code="080410")
        assert seen and seen[-1].get("stream") is True
        seen.clear()
        run_llm_agent(MISSIONS["pricing_scout"], _market_ref(), product="تمور",
                      hs_code="080410", budget={"tool_calls": 1})
        assert seen and "stream" not in seen[-1]


def test_aborted_stream_partial_is_parsed_when_valid_and_no_regeneration():
    """بثّ أُجهِض لكن النصّ المجمَّع JSON صالح → تُحلَّل النتائج وتُعلَن فجوة
    الإجهاض، **بلا** نداء تذكير/إصلاح إضافي (لا إعادة توليد مدفوعة)."""
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_llm_provider as lp
    import silk_market_analyst
    calls: list = []

    def fake_call_tools(system, messages, tools=None, max_tokens=1600,
                        model=None, timeout=None, **kw):
        calls.append(1)
        lp._last_error.set({"type": "ReadTimeout", "message": "idle"})
        return {"stop_reason": "aborted_timeout", "content": [
            {"type": "text", "text": json.dumps(
                {"findings": [{"claim": "طلب", "category": "demand",
                               "confidence": 0.6, "datapoint_ids": ["dp1"]}],
                 "gaps": [], "summary": "جزئي"})}]}

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_llm_runtime._call_tools", side_effect=fake_call_tools):
        out = silk_market_analyst.analyze_market(
            _market_ref(), "تمور",
            {"demand_signal": AgentReport(
                "LLMMissionAgent:demand_signal",
                [__import__("silk_data_layer").DataPoint(
                    "v", "UN Comtrade", 0.8, "n", "2026-01-01")], False, "ok")},
            hs_code="080410")
    assert len(calls) == 1, "aborted partial must not trigger a second paid call"
    rep = out["report"]
    assert rep.findings and not rep.failed
    # الملخّص يُستبدل عمداً بخلاصة التقاطعات؛ أثر الإجهاض يعيش في التشخيص
    assert out["diagnostics"]["stream_aborted"] is True
    assert out["diagnostics"]["llm_error"]["type"] == "ReadTimeout"


def test_aborted_stream_partial_unparseable_declares_gap_without_repair_call():
    """بثّ أُجهِض ونصّه JSON مبتور → فجوة معلنة تسمّي الإجهاض، ولا نداء إصلاح
    (كان نداء JSON_REPAIR يعيد توليد التحليل كاملاً بثمنه)."""
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_llm_provider as lp
    import silk_market_analyst
    calls: list = []

    def fake_call_tools(system, messages, tools=None, max_tokens=1600,
                        model=None, timeout=None, **kw):
        calls.append(1)
        lp._last_error.set({"type": "StreamTotalTimeout", "message": "900s"})
        return {"stop_reason": "aborted_timeout", "content": [
            {"type": "text", "text": '{"findings": [{"claim": "طل'}]}

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_llm_runtime._call_tools", side_effect=fake_call_tools):
        out = silk_market_analyst.analyze_market(
            _market_ref(), "تمور",
            {"demand_signal": AgentReport("LLMMissionAgent:demand_signal", [],
                                          False, "ok")}, hs_code="080410")
    assert len(calls) == 1
    rep = out["report"]
    assert rep.failed and not rep.findings
    assert "StreamTotalTimeout" in rep.summary or "أُجهِض" in rep.summary
    assert out["diagnostics"]["all_missing_cause"] == "analyst_call_failed"


# ── T3 fix-up · حارس «فشل نداء المحلل» يرى خطأ هذه التشغيلة فقط ───────────────

def test_analyst_gate_ignores_stale_last_error_from_a_previous_call():
    """خطأ قديم في contextvar المزوّد (نداء سابق في السياق نفسه فشل، والمحلل
    لم يمرّ بالمزوّد فلم يُعِد ضبطه) **لا** يوقف الكاتب على تشغيلة سليمة:
    الحارس يقرأ خطأ هذه التشغيلة حصراً."""
    import contextlib
    from unittest.mock import patch
    import silk_llm_provider as lp
    db = _tmp_db()
    writer_calls: list = []

    def writer_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        writer_calls.append(1)
        return "## 1. تقرير\nنصّ."

    # المحلل مموّه عند _call_tools (لا مزوّد ⇒ لا إعادة ضبط) ويعيد صفر نتائج
    # (diagnostics: analyst_call_failed) — مع خطأ قديم مزروع يبدو «فشل نداء».
    def analyst_empty(system, messages, tools=None, max_tokens=1600,
                      model=None, timeout=None, **kw):
        return {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": json.dumps(
                {"findings": [], "gaps": [], "summary": "لا شيء"})}]}

    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch("silk_llm_runtime._call_tools",
                               side_effect=analyst_empty))
        st.enter_context(patch("silk_ai_judge._call", side_effect=writer_call))
        st.enter_context(patch("silk_ai_judge.review_report",
                               return_value={"approved": True, "issues": [],
                                             "blocking": False}))
        lp._last_error.set({"type": "ReadTimeout", "message": "stale from earlier"})
        r = _client().post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text
    rep = r.json()["deep_research"]["report"]
    assert len(writer_calls) == 1, "stale error skipped the writer on a healthy run"
    assert "skipped" not in rep and rep["report"]


# ── T8 · حكم المرحلة ٢: مهلة صريحة + تسجيل سبب فشله ──────────────────────────

def test_synthesis_stage2_uses_long_timeout_and_records_error():
    """كان `_stage2` يستدعي `_call` بلا مهلة فيسقط صامتاً إلى افتراضي ٦٠ث على
    مدخل ثقيل (١٢ تقريراً + المحلل) ولا أثر لفشله. الآن: timeout=_LONG_TIMEOUT
    صراحةً، وعند فشل النداء يحمل الحكم `ai_error` (تفصيل المزوّد) وتبقى
    جورية المرحلة ١ كما هي."""
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_ai_judge as aj
    import silk_llm_provider as lp
    import silk_synthesis
    captured: dict = {}

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        captured["timeout"] = timeout
        lp._last_error.set({"type": "ReadTimeout", "message": "stage2 idle"})
        return None

    reports = [AgentReport("LLMAgent:trade_flow", [], False, "ok")]
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_synthesis._call", side_effect=fake_call):
        verdict = silk_synthesis.synthesize(reports, product="تمور",
                                            market="Nigeria", with_ai=True)
    assert captured["timeout"] == aj._LONG_TIMEOUT
    assert verdict["synthesis_stage"] == 1                 # جورية المرحلة ١ قائمة
    assert "ai" not in verdict
    # الانحدار ٢: صار للسبب مصدرٌ صريح (محليّ مقابل مزوّد) — عقدٌ أوسع بطلب
    # المالك كي لا يلبس عطلٌ برمجيّ ثوبَ «المزوّد غير متاح».
    assert verdict["ai_error"] == {"source": "provider", "type": "ReadTimeout",
                                   "message": "stage2 idle"}


def test_synthesis_stage2_success_carries_no_ai_error():
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_synthesis
    reports = [AgentReport("LLMAgent:trade_flow", [], False, "ok")]
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_synthesis._call", side_effect=_fake_call_verdict):
        verdict = silk_synthesis.synthesize(reports, product="تمور",
                                            market="Nigeria", with_ai=True)
    assert verdict["synthesis_stage"] == 2 and "ai_error" not in verdict


# ── T9 · حارس الميزانية عند حدود المراحل + سجلّ انتقال مهيكل + writer_partial ──

def _fake_call_tools_costly(system, messages, tools=None, max_tokens=1600,
                            model=None, timeout=None, **kw):
    """محلل مموّه يسجّل رموزاً كثيرة (≈1.75$ على النموذج الذكي) كما يفعل
    المزوّد الحقيقي (قناة العدّاد الجانبية)."""
    import silk_ai_judge as aj
    import silk_context
    silk_context.record_llm_usage(aj._MODEL, 100000, 50000)
    return _fake_call_tools_ok(system, messages, tools, max_tokens, model, timeout)


def _run_budget_case(db: str, env: dict, writer_calls: list):
    import contextlib
    from unittest.mock import patch

    def writer_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        writer_calls.append(1)
        return "## 1. تقرير\nنصّ."

    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch.dict(os.environ, env))
        st.enter_context(patch("silk_llm_runtime._call_tools",
                               side_effect=_fake_call_tools_costly))
        st.enter_context(patch("silk_ai_judge._call", side_effect=writer_call))
        st.enter_context(patch("silk_ai_judge.review_report",
                               return_value={"approved": True, "issues": [],
                                             "blocking": False}))
        return _client().post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})


def test_budget_guard_halts_before_writer_with_clear_message():
    """SILK_RESEARCH_MAX_USD=0.01 والمحلل وحده كلّف ≈1.75$ → الكاتب لا يُستدعى؛
    budget_status يسمّي السقف والمرحلة التي أُوقف قبلها برسالة عربية واضحة؛
    ما اكتمل محفوظ والتشغيلة completed (لا خطأ صلب)."""
    from silk_storage import get_research_run, load_stage_checkpoints
    db = _tmp_db()
    writer_calls: list = []
    r = _run_budget_case(db, {"SILK_RESEARCH_MAX_USD": "0.01"}, writer_calls)
    assert r.status_code == 200, r.text
    data = r.json()
    assert writer_calls == []
    bs = data["deep_research"]["budget_status"]
    assert bs["exhausted"] is True
    assert bs["caps_hit"] == ["SILK_RESEARCH_MAX_USD=0.01"]
    # مراجعة §58 #5: البوّابة تُقيَّم بعد المحلل، فأوّلُ مرحلةٍ مدفوعةٍ تُرفَض
    # هي حكمُ المرحلة ٢؛ والكاتب يبقى متخطّىً بالسبب نفسه.
    assert bs["halted_before"] == "synthesis"
    assert bs["message"] and "SILK_" not in bs["message"]      # لغة الزائر لا الكود
    rep = data["deep_research"]["report"]
    assert rep["report"] is None and rep["skip_reason"] == "budget"
    aid = data["analysis_id"]
    assert {"analyst", "verdict"} <= set(load_stage_checkpoints(aid, path=db))
    assert get_research_run(aid, path=db)["status"] == "completed"


def test_daily_usd_cap_halts_mid_run():
    """السقف اليومي يوقف تشغيلةً وسط الطريق حين يدفعها إنفاقُ اليوم المتراكم فوق
    السقف — وهو ما يمنع تشغيلاتٍ متتاليةً من استنزاف الحساب. لا يعتمد على تكلفة
    نموذجٍ بعينه: نبذر إنفاقَ اليوم قرب السقف (تشغيلاتٌ سابقة) فيمرّ الحجزُ الصغير
    ثم أيُّ إنفاقٍ فعليٍّ موجبٍ لهذه التشغيلة يتخطّى السقف ⇒ يُوقَف قبل أوّل نداء
    مدفوع تالٍ ويُسمّى السقف اليومي.

    سابقًا كان الاختبار يثبّت «المحلل ≈1.75$ > سقف 1.5$» — رقمٌ صحيحٌ على Opus
    ($5/$25) لكنه انكسر صامتًا حين بدّل المالكُ الذكيَّ إلى Sonnet ($3/$15، #223
    في 2026-08-21) فهبطت تكلفةُ نفس النداء إلى 1.05$ < 1.5$، فلم يعُد المشهدُ
    يتخطّى السقف والبوّابةُ سليمةٌ إذ لا تُوقِف تشغيلةً تحت الميزانية. البذرُ يجعل
    الاختبار مناعةً ضدّ أي تغيّر سعرٍ لاحق. Seed the day near the cap so any
    positive run spend crosses it — price-independent."""
    import silk_usage
    db = _tmp_db()
    usage_db = os.path.join(os.path.dirname(db), "usage.db")
    # إنفاقُ اليوم من تشغيلاتٍ سابقة (1.4$) قرب سقف 1.5$: الحجزُ الصغير (0.05$)
    # يمرّ (1.45 ≤ 1.5)، ثم إنفاقُ المحلل الفعليُّ (أيُّ مبلغ > 0.1$، ومنه Sonnet
    # عند 1.05$ أو Haiku عند 0.35$) يدفع المتوقَّع اليوميَّ فوق السقف.
    silk_usage.record_usd(1.4, path=usage_db)
    writer_calls: list = []
    r = _run_budget_case(db, {"SILK_PAID_DAILY_USD_CAP": "1.5",
                              "SILK_USAGE_DB": usage_db,
                              "SILK_RESEARCH_EXPECTED_USD": "0.05"}, writer_calls)
    assert r.status_code == 200, r.text
    bs = r.json()["deep_research"]["budget_status"]
    assert writer_calls == []
    assert bs["exhausted"] is True and bs["halted_before"] in ("writer", "synthesis")
    assert any(c.startswith("SILK_PAID_DAILY_USD_CAP=") for c in bs["caps_hit"])


def test_no_cap_means_no_halt():
    db = _tmp_db()
    writer_calls: list = []
    r = _run_budget_case(db, {"SILK_RESEARCH_MAX_USD": ""}, writer_calls)
    assert r.status_code == 200, r.text
    bs = r.json()["deep_research"]["budget_status"]
    assert len(writer_calls) == 1 and "halted_before" not in bs


def test_stage_transition_logs_trace_and_progress(caplog, tmp_path):
    """كل انتقال مرحلة: سطر سجلّ مهيكل (analysis_id/stage/duration_s/tokens/cost)،
    حدث تتبّع kind=stage، وتراكم stage_seconds في لقطة التقدّم (تنجو من الفشل)؛
    وstage_seconds النهائية في data_economics كما كانت."""
    import contextlib
    import logging
    from unittest.mock import patch
    import silk_trace
    from silk_storage import get_research_progress
    db = _tmp_db()
    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch.dict(os.environ, {"SILK_TRACE_DIR": str(tmp_path)}))
        st.enter_context(patch("silk_ai_judge._call",
                               side_effect=lambda *a, **k: "## 1. x\nنصّ."))
        st.enter_context(patch("silk_ai_judge.review_report",
                               return_value={"approved": True, "issues": [],
                                             "blocking": False}))
        st.enter_context(caplog.at_level(logging.INFO, logger="api"))
        r = _client().post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text
    data = r.json()
    aid = data["analysis_id"]
    lines = [rec.getMessage() for rec in caplog.records
             if "stage_transition" in rec.getMessage()]
    assert lines, "no structured stage_transition log lines"
    for needed in ("analysis_id=", "stage=", "duration_s=", "tokens_in=",
                   "tokens_out=", "cost_usd="):
        assert all(needed in ln for ln in lines), needed
    stages_logged = [ln.split("stage=")[1].split()[0] for ln in lines]
    assert {"missions", "analyst", "synthesis", "enrich", "writer"} <= set(stages_logged)
    trace_id = data["deep_research"]["trace_id"]
    ev = [e for e in silk_trace.read_trace(trace_id, dir_path=str(tmp_path))
          if e.get("kind") == "stage"]
    assert {e["stage"] for e in ev} >= {"missions", "analyst", "writer"}
    assert all("duration_s" in e and "cost_usd" in e for e in ev)
    prog = get_research_progress(aid, path=db)
    assert set(prog.get("stage_seconds", {})) >= {"missions", "analyst", "writer"}
    econ = data["data_economics"]
    assert set(econ["stage_seconds"]) == {"missions", "analyst", "synthesis",
                                          "enrich", "writer"}
    assert econ["stage_top_sinks"]


def test_writer_partial_is_checkpointed():
    import contextlib
    from unittest.mock import patch
    from silk_storage import load_stage_checkpoints
    db = _tmp_db()
    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch("silk_ai_judge.write_reviewed_report",
                               return_value={"report": None, "review_cycles": 0,
                                             "unresolved_notes": [],
                                             "failure_reason": "ناقص",
                                             "partial_text": "## 1. مسوّدة جزئية"}))
        r = _client().post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text
    stages = load_stage_checkpoints(r.json()["analysis_id"], path=db)
    assert stages["writer_partial"]["status"] == "partial"
    assert stages["writer_partial"]["payload"]["text"] == "## 1. مسوّدة جزئية"


# ── دفتر الاستخدام في الاختبارات لا يلمس دفتر الجهاز الحقيقي ────────────────

def test_hermetic_usage_ledger_is_not_the_real_one():
    """conftest يوجّه SILK_USAGE_DB إلى دفتر مؤقّت لكل جلسة — حجوزات /research
    التجريبية لا تتراكم في data/usage.db فلا تُطعِم حارس الإنفاق (T9) سقفاً
    زائفاً على تشغيلة حقيقية في الجهاز نفسه."""
    import silk_usage
    path = silk_usage._db_path()
    assert os.path.basename(os.path.dirname(path)).startswith("silk-test-usage-")
    assert os.path.abspath(path) != os.path.abspath(os.path.join("data", "usage.db"))
