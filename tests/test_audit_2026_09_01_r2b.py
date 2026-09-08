"""أقفال R2b — سجلّ تشغيلات `/research` الجذري (التدقيق الجنائي 2026-09-01، بقيّة المرحلة ٢).

لماذا هذا الملف: المنصّةُ نالت في R2 سجلّاً دائماً ونبضةً وسقفاً وإلغاءً وختمَ
إغلاق، وبقي خيطُ `/research` الجذري بلا شيءٍ منها: نقاطُ تفتيش البعثات لا
تُحرّك `updated_at` فيحصد الحاصدُ تشغيلةً حيّة ويصالح حجزَها مرّتين؛ والاستئنافُ
على صفٍّ جارٍ يبدأ تشغيلةً ثانية بحجزٍ ثانٍ؛ والحفظُ النهائي خارج `try` فتقريرٌ
مدفوع يضيع ولا يُوسَم الصفّ؛ ولا سقفَ ولا إلغاءَ ولا سجلَّ خيوط؛ والحاصدُ لا
يدور إلا مع `SILK_REFRESH_HOURS`؛ ولقطةُ التقدّم تقرأ قاموساً يكتبه خيطٌ آخر؛
والحجزُ الدولاري يسبق صفَّ التشغيلة فيتسرّب عند عطبٍ بينهما؛ و`/analyze?persist`
يعيد 200 بلا معرّف حين يفشل الحفظ. «إصلاحٌ على مسارٍ واحد نصفُ إصلاح».

هرمتي: قواعد مؤقّتة، كلود مُحاكى، لا شبكة. Hermetic only.
"""
from __future__ import annotations

import datetime
import os
import sqlite3
import sys
import threading
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("fastapi")

from tests.test_wave13_resilience import _fake_call, _fake_call_tools_factory  # noqa: E402

_HDR = {"X-API-Key": "secret"}
_ENV = {"ANTHROPIC_API_KEY": "test", "SILK_RATE_LIMIT": "0", "SILK_API_KEY": "secret",
        "SILK_ORPHAN_REAP_INTERVAL_S": "0", "SILK_EARLY_HALT": "0"}


@pytest.fixture(autouse=True)
def _offline_sources():
    """محاكاة كلود وحدها لا تحجب تعزيزات البيانات؛ لا شبكة في أقفال R2b."""
    with patch("requests.get", side_effect=OSError("network disabled for offline test")), \
            patch("requests.post", side_effect=OSError("network disabled for offline test")), \
            patch("requests.sessions.Session.request",
                  side_effect=OSError("network disabled for offline test")):
        yield


def _db() -> str:
    import silk_storage
    return silk_storage._db_path()


def _client():
    from fastapi.testclient import TestClient
    import api as root_api
    return TestClient(root_api.create_app())


def _backdate(aid: int, minutes: int) -> None:
    stale = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(minutes=minutes)).isoformat(timespec="seconds")
    conn = sqlite3.connect(_db())
    try:
        conn.execute("UPDATE analyses SET updated_at = ? WHERE id = ?", (stale, aid))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def runtime():
    import silk_research_runtime as rt
    rt.reset_for_tests()
    yield rt
    rt.reset_for_tests()


# ══════════════ API-2 — نبضةُ الحاصد من نقاط التفتيش ════════════════════════
def test_mission_checkpoints_and_progress_snapshots_beat_the_reaper_heartbeat():
    """بعثةٌ تُكمِل كلَّ دقيقة كانت تُحصَد «عالقةً» لأن `updated_at` لا يتحرّك."""
    import silk_storage as st
    from silk_agents import AgentReport
    aid = st.create_research_run("تمور", "ESP", "080410", {"product": "تمور"},
                                 path=_db(), market_name="إسبانيا")
    _backdate(aid, 45)
    st.save_mission_checkpoint(aid, "demand", AgentReport(agent_name="x", findings=[]),
                               path=_db(), market_iso3="ESP")
    assert st.reap_orphan_research_runs(stale_minutes=30, path=_db()) == []
    _backdate(aid, 45)
    st.update_research_progress(aid, path=_db(), stage="analyst")
    assert st.reap_orphan_research_runs(stale_minutes=30, path=_db()) == []
    assert st.get_research_run(aid, path=_db())["status"] == "running"


def test_reaper_then_pipeline_reconcile_leaves_the_ledger_at_the_final_actual(monkeypatch):
    """حاصدٌ صالَح ١.٠ ثم خطُّ الأنابيب صالَح ٢.٥ — الدفترُ ينتهي عند ٢.٥ لا ٠.٥."""
    import silk_storage as st
    import silk_usage
    monkeypatch.setenv("SILK_PAID_DAILY_USD_CAP", "100")
    aid = st.create_research_run("تمور", "ESP", "080410", {"product": "تمور"},
                                 path=_db(), market_name="إسبانيا")
    day = silk_usage._today()
    assert silk_usage.try_reserve_usd(3.0)
    st.update_research_progress(aid, path=_db(), cost_usd_estimate=1.0)
    monkeypatch.setattr(silk_usage, "expected_run_usd", lambda: 3.0)
    assert st.reconcile_failed_run_usd(aid, path=_db())      # الحاصد: ٣.٠ ← ١.٠
    assert round(silk_usage.usd_spent_today(), 2) == 1.0
    st.reconcile_run_usd_final(aid, reserved=3.0, actual=2.5, day=day, path=_db())
    assert round(silk_usage.usd_spent_today(), 2) == 2.5
    prog = st.get_research_progress(aid, path=_db())
    assert prog["usd_reconciled"] is True and prog["usd_reconciled_actual"] == 2.5


# ══════════════ API-4 — استئنافٌ على صفٍّ جارٍ = 409 ═══════════════════════
def _seed_running() -> int:
    import silk_storage as st
    return st.create_research_run("تمور", "ESP", "080410",
                                  {"product": "تمور", "market_iso3": "ESP",
                                   "hs_code": "080410"},
                                  path=_db(), market_name="إسبانيا")


def test_resume_on_a_running_row_is_409_resume_still_running(runtime):
    with patch.dict(os.environ, _ENV):
        cl = _client()
        aid = _seed_running()                          # `updated_at` طازج
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Spain", "resume": aid})
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["error"] == "resume_still_running" and d["owner"] == "other_process"
        _backdate(aid, 90)                             # قديم — لكن مسجَّل هنا
        runtime.register(aid, origin="http")
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Spain", "resume": aid})
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["owner"] == "this_process"


# ══════════════ API-5 — الحفظُ النهائي داخل try + نقطة تفتيش التقرير ════════
def _fake_llm_stack(tool_calls: list):
    return (patch("silk_llm_runtime._call_tools",
                  side_effect=_fake_call_tools_factory(tool_calls)),
            patch("silk_synthesis._call", side_effect=_fake_call),
            patch("silk_ai_judge._call", side_effect=_fake_call))


def test_a_final_save_failure_marks_the_run_failed_and_keeps_the_report_checkpoint(runtime):
    import silk_storage as st
    tool_calls: list = []
    p1, p2, p3 = _fake_llm_stack(tool_calls)
    with patch.dict(os.environ, _ENV), p1, p2, p3, \
            patch("silk_storage.save_analysis", side_effect=OSError("disk full")):
        cl = _client()
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Nigeria",
                          "hs_code": "080410", "persist": True})
        assert r.status_code == 500, r.text
        d = r.json()["detail"]
        assert d["error"] == "research_run_failed" and d.get("stage") == "save"
        aid = d["analysis_id"]
    assert st.get_research_run(aid, path=_db())["status"] == "failed"
    stages = st.load_stage_checkpoints(aid, path=_db())
    assert stages.get("report", {}).get("status") == "succeeded"
    assert (stages["report"].get("payload") or {}).get("report")


# ══════════════ API-14 — سقفٌ وإلغاءٌ وسجلّ خيوط ════════════════════════════
def _blocking_tools_factory(tool_calls: list, gate: threading.Event,
                            started: threading.Event):
    inner = _fake_call_tools_factory(tool_calls)

    def blocking(*a, **kw):
        started.set()
        gate.wait(10)
        return inner(*a, **kw)
    return blocking


def test_cancel_stops_a_background_run_at_the_next_stage_boundary(runtime):
    import silk_storage as st
    tool_calls: list = []
    gate, started = threading.Event(), threading.Event()
    with patch.dict(os.environ, _ENV), \
            patch("silk_llm_runtime._call_tools",
                  side_effect=_blocking_tools_factory(tool_calls, gate, started)), \
            patch("silk_synthesis._call", side_effect=_fake_call) as syn, \
            patch("silk_ai_judge._call", side_effect=_fake_call) as judge:
        cl = _client()
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Nigeria", "hs_code": "080410",
                          "persist": True, "async_run": True})
        assert r.status_code == 202, r.text
        aid = r.json()["analysis_id"]
        assert started.wait(10)
        c = cl.post(f"/research/{aid}/cancel", headers=_HDR)
        assert c.status_code == 202, c.text
        assert cl.get(f"/research/{aid}/status", headers=_HDR).json()["cancel_requested"] is True
        gate.set()
        for _ in range(500):
            s = cl.get(f"/research/{aid}/status", headers=_HDR).json()
            if s["status"] != "running":
                break
            time.sleep(0.02)
        assert s["status"] == "failed", s
        assert "أُلغيت" in (s.get("skip_reason") or "")
        assert syn.call_count == 0 and judge.call_count == 0   # لا ذيلَ مدفوعاً بعد الإلغاء


def test_more_than_the_cap_of_http_runs_is_refused_503_research_busy(runtime, monkeypatch):
    monkeypatch.setenv("SILK_MAX_CONCURRENT_RESEARCH", "1")
    runtime.reset_for_tests()
    tool_calls: list = []
    gate, started = threading.Event(), threading.Event()
    with patch.dict(os.environ, _ENV), \
            patch("silk_llm_runtime._call_tools",
                  side_effect=_blocking_tools_factory(tool_calls, gate, started)), \
            patch("silk_synthesis._call", side_effect=_fake_call), \
            patch("silk_ai_judge._call", side_effect=_fake_call):
        cl = _client()
        body = {"product": "تمور", "market": "Nigeria", "hs_code": "080410",
                "persist": True, "async_run": True}
        assert cl.post("/research", headers=_HDR, json=body).status_code == 202
        assert started.wait(10)
        r = cl.post("/research", headers=_HDR, json=body)
        assert r.status_code == 503, r.text
        assert r.json()["detail"]["error"] == "research_busy"
        assert r.headers.get("retry-after")
        gate.set()
        for _ in range(500):
            if not runtime.active_ids():
                break
            time.sleep(0.02)


# ══════════════ API-3 — حاصدٌ يدور بلا `SILK_REFRESH_HOURS` + ختمُ الإغلاق ═══
def test_reaper_tick_runs_without_refresh_hours(runtime, monkeypatch):
    import silk_storage as st
    monkeypatch.delenv("SILK_REFRESH_HOURS", raising=False)
    monkeypatch.setenv("SILK_ORPHAN_REAP_INTERVAL_S", "1")
    calls: list = []
    monkeypatch.setattr(st, "reap_orphan_research_runs",
                        lambda *a, **kw: calls.append(1) or [])
    assert runtime.start_reaper() is not None
    for _ in range(60):
        if calls:
            break
        time.sleep(0.1)
    assert calls, "الحاصد لم يدُر"


def test_shutdown_stamps_in_flight_root_runs_interrupted_and_reconciles(runtime, monkeypatch):
    import silk_storage as st
    import silk_usage
    monkeypatch.setenv("SILK_PAID_DAILY_USD_CAP", "100")
    aid = _seed_running()
    assert silk_usage.try_reserve_usd(3.0)
    st.update_research_progress(aid, path=_db(), cost_usd_estimate=0.4,
                                boot_id=runtime.boot_id())
    runtime.register(aid, origin="http")
    monkeypatch.setattr(silk_usage, "expected_run_usd", lambda: 3.0)
    runtime.shutdown()
    row = st.get_research_run(aid, path=_db())
    assert row["status"] == "failed"
    assert "interrupted" in str(st.get_analysis(aid, path=_db()).get("error") or "")
    assert st.get_research_progress(aid, path=_db()).get("usd_reconciled") is True
    assert round(silk_usage.usd_spent_today(), 2) == 0.4


# ══════════════ API-15 / API-16 / API-12 / CONC-10 ═══════════════════════════
def test_progress_snapshot_copies_usage_outside_the_counter_lock(monkeypatch):
    import silk_context
    import silk_pricing
    import silk_storage as st
    seen: dict = {}
    aid = _seed_running()

    def spy(usage):
        seen["locked"] = silk_context._counter_lock.locked()
        seen["obj"] = usage
        return {"total_usd": 0.0, "unpriced_models": []}

    monkeypatch.setattr(silk_pricing, "estimate_cost_usd", spy)
    live = silk_context.begin_data_counter().setdefault("llm_usage", {})
    live["m"] = {"input": 1}
    try:
        silk_context.snapshot_research_progress(aid, "missions")
    finally:
        silk_context._data_counter.set(None)
    assert seen["locked"] is False
    assert seen["obj"] is not live                 # نسخةٌ لا القاموسُ الحيّ


def test_reservation_is_released_when_the_run_row_cannot_be_created(monkeypatch, tmp_path):
    import silk_usage
    monkeypatch.setenv("SILK_PAID_DAILY_USD_CAP", "100")
    # دفترٌ خاصّ بالاختبار — دفترُ الجلسة المشترك يحمل بقايا اختباراتٍ سابقة.
    monkeypatch.setenv("SILK_USAGE_DB", str(tmp_path / "usage.db"))
    with patch.dict(os.environ, _ENV), \
            patch("silk_storage.create_research_run", side_effect=OSError("locked")):
        cl = _client()
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Nigeria", "hs_code": "080410",
                          "persist": True})
        assert r.status_code == 500, r.text
        assert r.json()["detail"]["error"] == "research_run_create_failed"
    assert round(silk_usage.usd_spent_today(), 2) == 0.0


def test_analyze_persist_true_declares_a_failed_save():
    # الشبكةُ مقطوعة على مستوى `requests` (نمطُ test_analyze_persistence_and_glyph)
    # — التحليلُ يتدهور فوراً بدل انتظار Comtrade/كلود الحقيقيَّين.
    _err = OSError("network blocked in test")
    with patch.dict(os.environ, _ENV), \
            patch("requests.get", side_effect=_err), \
            patch("requests.post", side_effect=_err), \
            patch("requests.Session.request", side_effect=_err), \
            patch("silk_storage.save_analysis", side_effect=OSError("disk full")):
        cl = _client()
        r = cl.post("/analyze", headers=_HDR,
                    json={"product": "تمور", "persist": True})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("analysis_id") is None
        assert body.get("persist_error") == "OSError"


def test_boot_id_is_stamped_on_every_root_run(runtime):
    import silk_storage as st
    tool_calls: list = []
    p1, p2, p3 = _fake_llm_stack(tool_calls)
    with patch.dict(os.environ, _ENV), p1, p2, p3:
        cl = _client()
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Nigeria", "hs_code": "080410",
                          "persist": True})
        assert r.status_code == 200, r.text
        aid = r.json()["analysis_id"]
    assert st.get_research_progress(aid, path=_db()).get("boot_id") == runtime.boot_id()


def test_shutdown_hook_and_reaper_are_wired_into_the_root_app():
    import inspect
    import api as root_api
    src = inspect.getsource(root_api.create_app)
    assert 'add_event_handler("shutdown", silk_research_runtime.shutdown)' in src
    assert "silk_research_runtime.start_reaper()" in src


# ══════════════ مراجعة R2b (/code-review high) — قفلٌ لكلّ اكتشاف ═══════════
def test_reaper_tick_skips_runs_live_in_this_process(runtime, monkeypatch):
    """مرحلةُ المحلّل قد تطول عن `SILK_ORPHAN_STALE_MINUTES` بلا نبضةٍ بينها — الحاصدُ
    كان يوسم تشغيلةً **حيّةً في هذه العملية** فاشلةً بعمر النبضة وحده (نظيرُ
    `study_runtime._sweep_stale` يطرح المقابضَ الحيّة)."""
    import silk_storage as st
    monkeypatch.setenv("SILK_ORPHAN_STALE_MINUTES", "30")
    aid = _seed_running()
    _backdate(aid, 45)
    runtime.register(aid, origin="http")
    out = runtime.tick()
    assert out["reaped"] == 0
    assert st.get_research_run(aid, path=_db())["status"] == "running"
    runtime.release(aid)
    assert runtime.tick()["reaped"] == 1
    assert st.get_research_run(aid, path=_db())["status"] == "failed"


def test_resume_is_409_while_the_handle_is_live_even_if_the_row_was_reaped(runtime):
    """صفٌّ حصده حاصدٌ آخر (أو أُعدِم بأيّ سبب) بينما خيطُه ما زال يعمل هنا —
    الاستئنافُ كان يبدأ خطَّ أنابيب ثانياً على المعرّف نفسه (مقبضان، فتحةٌ تُحرَّر
    مرّتين، نقاطُ تفتيش متداخلة). الحكمُ للمقبض الحيّ قبل حالة الصفّ."""
    import silk_storage as st
    p1, p2, p3 = _fake_llm_stack([])                   # لو تراجع الإصلاح: لا كلود حقيقيّ
    with patch.dict(os.environ, _ENV), p1, p2, p3:
        cl = _client()
        aid = _seed_running()
        runtime.register(aid, origin="http")
        st.mark_research_failed(aid, "orphaned: reaped elsewhere", path=_db())
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Spain", "resume": aid})
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["error"] == "resume_still_running" and d["owner"] == "this_process"


def test_final_reconcile_writes_the_ledger_once_when_the_flag_write_fails(monkeypatch, tmp_path):
    """`reconcile_run_usd_final`: فشلُ كتابة الوسم **بعد** كتابة الدفتر كان يرفع، فيعيد
    خطُّ الأنابيب المصالحةَ من الحجز الكامل ⇒ خصمٌ مزدوج. الرفعُ يجوز قبل الدفتر فقط."""
    import silk_storage as st
    import silk_usage
    monkeypatch.setenv("SILK_USAGE_DB", str(tmp_path / "usage.db"))
    assert silk_usage.try_reserve_usd(3.0)
    aid = _seed_running()
    monkeypatch.setattr(st, "update_research_progress",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("database is locked")))
    st.reconcile_run_usd_final(aid, reserved=3.0, actual=0.4, path=_db())   # لا يرفع
    assert round(silk_usage.usd_spent_today(), 2) == 0.4
    monkeypatch.setattr(st, "get_research_progress",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
    with pytest.raises(OSError):                       # قبل الدفتر ⇒ يرفع والدفترُ كما هو
        st.reconcile_run_usd_final(aid, reserved=3.0, actual=0.4, path=_db())
    assert round(silk_usage.usd_spent_today(), 2) == 0.4


def test_thread_start_failure_releases_the_handle_and_marks_the_row_failed(runtime, monkeypatch, tmp_path):
    """`Thread.start()` يرفع (حدُّ الخيوط في حاويةٍ ضيّقة): المقبضُ كان يبقى مسجَّلاً
    للأبد (409 دائم، إلغاءٌ لخيطٍ لا وجود له) والصفُّ `running` حتى الحاصد."""
    import silk_storage as st
    import silk_usage
    monkeypatch.setenv("SILK_USAGE_DB", str(tmp_path / "usage.db"))
    real_start = threading.Thread.start

    def _start(self):
        if getattr(getattr(self, "_target", None), "__name__", "") == "_research_background":
            raise RuntimeError("can't start new thread")
        return real_start(self)
    monkeypatch.setattr(threading.Thread, "start", _start)
    with patch.dict(os.environ, _ENV):
        cl = _client()
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Nigeria", "hs_code": "080410",
                          "persist": True, "async_run": True})
        assert r.status_code == 500, r.text
        d = r.json()["detail"]
        assert d["error"] == "research_thread_start_failed"
        aid = d["analysis_id"]
    assert runtime.active_ids() == []
    assert st.get_research_run(aid, path=_db())["status"] == "failed"
    assert round(silk_usage.usd_spent_today(), 2) == 0.0
    assert runtime.try_acquire() and runtime.try_acquire() and runtime.try_acquire()
    assert not runtime.try_acquire()                   # السقف ٣ سليم — لا فتحةٌ ضائعة


def test_sync_failure_releases_the_http_slot_exactly_once(runtime, monkeypatch):
    """فشلُ تشغيلةٍ متزامنة بعد التسجيل: `finally` الداخلي يحرّر الفتحة، ثم كان الغلافُ
    الخارجي يحرّرها ثانيةً (`analysis_id` في نطاقه None) ⇒ السقفُ يقبل واحداً زيادة."""
    monkeypatch.setenv("SILK_MAX_CONCURRENT_RESEARCH", "2")
    runtime.reset_for_tests()
    assert runtime.try_acquire()                       # تشغيلةٌ أخرى تحتلّ فتحة
    tool_calls: list = []
    p1, p2, p3 = _fake_llm_stack(tool_calls)
    with patch.dict(os.environ, _ENV), p1, p2, p3, \
            patch("silk_storage.save_analysis", side_effect=OSError("disk full")):
        cl = _client()
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Nigeria",
                          "hs_code": "080410", "persist": True})
        assert r.status_code == 500, r.text
    assert runtime.try_acquire()                       # الفتحةُ الوحيدة الحرّة
    assert not runtime.try_acquire()                   # لا ثالثةَ فوق السقف


def test_shutdown_sets_the_outer_cancel_event_too(runtime):
    """تشغيلةٌ تعمل تحت سياق إلغاءٍ خارجيّ تقرأ حدثَه هو — `shutdown()` كان يضبط
    `cancel` وحده فيوسم الصفَّ منقطعاً ويصالح بينما الخطُّ يواصل نداءاتٍ مدفوعة."""
    h = runtime.register(7, origin="http")
    h.outer = threading.Event()
    runtime.shutdown()
    assert h.cancel.is_set() and h.outer.is_set()


def test_sync_run_without_persist_gives_its_slot_back(runtime, monkeypatch):
    """تشغيلةٌ متزامنة بلا `persist` لا صفَّ ولا مقبضَ لها — فتحتُها كانت تتسرّب
    عند كلّ نجاح حتى يمتلئ السقف بتشغيلاتٍ انتهت."""
    monkeypatch.setenv("SILK_MAX_CONCURRENT_RESEARCH", "1")
    runtime.reset_for_tests()
    p1, p2, p3 = _fake_llm_stack([])
    with patch.dict(os.environ, _ENV), p1, p2, p3:
        cl = _client()
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Nigeria", "hs_code": "080410",
                          "persist": False})           # لا صفَّ ⇒ لا مقبض
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("analysis_id") is None
    assert runtime.active_ids() == []
    assert runtime.try_acquire()                       # الفتحةُ عادت


def test_resumed_run_reconciles_its_fresh_reservation_not_the_previous_attempts(runtime, monkeypatch, tmp_path):
    """محاولةٌ سابقة حصدها الحاصد وصالحها (`usd_reconciled=True`, `usd_reconciled_actual`)
    ثم استُؤنفت بحجزٍ جديد: المصالحةُ النهائية كانت تنطلق من مبلغ المحاولة القديمة
    فيبقى الحجزُ الجديد كاملاً في الدفتر (السقفُ اليوميّ يُغلَق على تشغيلاتٍ انتهت)."""
    import silk_storage as st
    import silk_usage
    monkeypatch.setenv("SILK_USAGE_DB", str(tmp_path / "usage.db"))
    aid = _seed_running()
    silk_usage.record_usd(0.4)                         # ما صالحه الحاصد للمحاولة الأولى
    st.update_research_progress(aid, path=_db(), usd_reconciled=True,
                                usd_reconciled_actual=0.4)
    st.mark_research_failed(aid, "orphaned: reaped", path=_db())
    p1, p2, p3 = _fake_llm_stack([])
    with patch.dict(os.environ, _ENV), p1, p2, p3:
        cl = _client()
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Spain", "resume": aid})
        assert r.status_code == 200, r.text[:300]
    spent = silk_usage.usd_spent_today()
    assert spent < 1.0, spent                          # ٠٫٤ + كلفةُ المحاولة الجديدة — لا ٣٫٤


def test_root_cancel_refuses_platform_owned_runs(runtime):
    """تشغيلةُ جسر المنصّة مسجَّلةٌ هنا بأصل `platform` — إلغاؤها بمفتاح الجذر كان
    يتجاوز دفترَ `study_runtime` (الدراسةُ تنتهي «فشلاً» بلا سببِ إلغاء)."""
    aid = _seed_running()
    runtime.register(aid, origin="platform")
    with patch.dict(os.environ, _ENV):
        cl = _client()
        r = cl.post(f"/research/{aid}/cancel", headers=_HDR)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["error"] == "platform_owned_run"
    assert not runtime.cancel_requested(aid)


def test_tick_runs_the_janitor_once_per_hour_not_every_reap(runtime, monkeypatch):
    """الكنسُ كان يدور مع كلّ حصدٍ (كلَّ ٣٠٠ ث = ١٢× الإيقاع الساعيّ القديم)."""
    import silk_janitor
    calls: list = []
    monkeypatch.setattr(silk_janitor, "sweep", lambda *a, **k: calls.append(1) or {})
    runtime.tick()
    runtime.tick()
    assert len(calls) == 1
    runtime._last_janitor = time.monotonic() - 3601
    runtime.tick()
    assert len(calls) == 2
