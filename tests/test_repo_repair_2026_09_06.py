"""أقفال المراجعة الشاملة: سباقات الواجهة ودورة حياة المشرف.

اختبارات سلوكية بلا شبكة أو إنفاق. Offline behavioural regression locks.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_browser_ci_uses_production_font_pin_and_checksums():
    """دليل PDF يستخدم نفس الخط المثبت في صورة الإنتاج. Same pinned font bytes."""
    workflow = (_ROOT / ".github/workflows/e2e-live-shape.yml").read_text()
    assert "/google/fonts/main/" not in workflow
    assert "GOOGLE_FONTS_COMMIT" in workflow and "Dockerfile" in workflow
    assert 'sha256sum -c "$GITHUB_WORKSPACE/docker/fonts.sha256"' in workflow


@pytest.mark.parametrize("replacement", ["good", "err", "warn"])
def test_old_toast_timer_cannot_hide_a_new_message(replacement):
    """رسالة نجاح قديمة لا تمحو نتيجة إجراء أحدث، حتى إن كان خطأً دائماً."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable: JavaScript behaviour was not exercised")
    page = (_ROOT / "web/platform.html").read_text(encoding="utf-8")
    say = page[page.index("function say("):page.index("const tell =")]
    script = r'''
const assert = require("node:assert/strict");
const timers = new Map();
let serial = 0;
const setTimeout = (fn) => { timers.set(++serial, fn); return serial; };
const clearTimeout = (id) => timers.delete(id);
const el = {textContent: "", className: "", scrollIntoView() {}};
''' + say + r'''
say(el, "first", "good");
const old = serial;
say(el, "second", process.argv[1]);
// أطلق مؤقت الرسالة القديمة فقط إن لم يُلغَ — تحكم حتمي بلا نوم.
if (timers.has(old)) timers.get(old)();
assert.equal(el.className, "msg on " + process.argv[1]);
assert.equal(el.textContent, "second");
if (process.argv[1] === "good") {
  assert.ok(timers.has(serial), "new success has its own expiry");
  timers.get(serial)();
  assert.equal(el.className, "msg");
}
'''
    result = subprocess.run([node, "-e", script, replacement],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("denial", ["readiness", "busy", "budget", "invalid_market"])
def test_refused_resume_does_not_mark_the_saved_attempt_running(monkeypatch, tmp_path, denial):
    """رفضٌ قبل التنفيذ لا يحيي محاولةً فاشلة ولا يمحو وسم مصالحتها."""
    from fastapi.testclient import TestClient
    import api
    import silk_storage as st
    import silk_research_runtime as rt
    import silk_usage

    monkeypatch.setenv("SILK_DB", str(tmp_path / "research.db"))
    monkeypatch.setenv("SILK_USAGE_DB", str(tmp_path / "usage.db"))
    monkeypatch.setenv("SILK_API_KEY", "secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("SILK_RATE_LIMIT", "0")
    client = TestClient(api.create_app())
    aid = st.create_research_run("تمور", "ESP", "080410",
                                 {"product": "تمور", "market": "Spain", "market_iso3": "ESP",
                                  "hs_code": "080410"})
    st.mark_research_failed(aid, "prior attempt failed")
    st.update_research_progress(aid, usd_reconciled=True, usd_reconciled_actual=0.4)
    before, progress = st.get_research_run(aid), st.get_research_progress(aid)
    body = {"resume": aid}
    if denial == "readiness":
        monkeypatch.delenv("ANTHROPIC_API_KEY")
    elif denial == "busy":
        monkeypatch.setattr(rt, "try_acquire", lambda: False)
    elif denial == "budget":
        monkeypatch.setattr(silk_usage, "try_reserve_usd", lambda *a: False)
    else:
        body["market"] = "not-a-real-market-xyz"
    with patch("requests.sessions.Session.request", side_effect=OSError("net blocked")), \
            patch("requests.get", side_effect=OSError("net blocked")), \
            patch("requests.post", side_effect=OSError("net blocked")):
        response = client.post("/research", headers={"X-API-Key": "secret"}, json=body)
    assert response.status_code == {"readiness": 409, "busy": 503,
                                    "budget": 429, "invalid_market": 422}[denial], response.text
    assert st.get_research_run(aid) == before
    assert st.get_research_progress(aid) == progress


def test_resume_claim_has_one_winner_and_rejects_old_generations(tmp_path):
    """اتصالان بنفس اللقطة: مطالبة واحدة؛ واللقطة القديمة لا تعيش بعد فشل آخر."""
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import silk_storage as st

    db = str(tmp_path / "claim.db")
    aid = st.create_research_run("تمور", "ESP", "080410", {}, path=db)
    st.mark_research_failed(aid, "first failure", path=db)
    before = st.get_research_run(aid, path=db)
    gate = threading.Barrier(2)

    def claim():
        gate.wait(timeout=5)
        return st.claim_research_resume(aid, expected=before, path=db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sorted(results) == [False, True]
    st.mark_research_failed(aid, "second failure", path=db)
    assert not st.claim_research_resume(aid, expected=before, path=db)
    latest = st.get_research_run(aid, path=db)
    assert st.claim_research_resume(aid, expected=latest, path=db)


@pytest.mark.parametrize("failure", [False, OSError("claim unavailable")])
def test_failed_resume_claim_returns_its_reservation_and_slot(monkeypatch, tmp_path, failure):
    """الطلب الخاسر/عطب قاعدة المطالبة: لا دولار محجوز ولا فتحة مسرّبة."""
    from fastapi.testclient import TestClient
    import api
    import silk_storage as st
    import silk_usage
    import silk_research_runtime as rt

    monkeypatch.setenv("SILK_DB", str(tmp_path / "research.db"))
    monkeypatch.setenv("SILK_USAGE_DB", str(tmp_path / "usage.db"))
    monkeypatch.setenv("SILK_API_KEY", "secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("SILK_RATE_LIMIT", "0")
    monkeypatch.setenv("SILK_MAX_CONCURRENT_RESEARCH", "1")
    monkeypatch.setenv("SILK_PAID_DAILY_USD_CAP", "100")
    client = TestClient(api.create_app())
    aid = st.create_research_run("تمور", "ESP", "080410",
                                 {"product": "تمور", "market": "Spain", "hs_code": "080410"})
    st.mark_research_failed(aid, "previous failure")
    before = st.get_research_run(aid)
    with patch.object(st, "claim_research_resume", side_effect=failure if failure else None,
                      return_value=False), \
            patch("requests.sessions.Session.request", side_effect=OSError("net blocked")):
        response = client.post("/research", headers={"X-API-Key": "secret"}, json={"resume": aid})
    assert response.status_code == (500 if failure else 409), response.text
    assert st.get_research_run(aid) == before
    assert silk_usage.usd_spent_today() == 0
    assert rt.try_acquire(), "HTTP concurrency slot leaked"
    rt._release_slot()


def test_browser_harness_honours_configured_node_path(monkeypatch):
    """حزمة المتصفح المثبّتة خارج npm العام تُحلّ عبر NODE_PATH المعلَن."""
    from tests.test_rung3_playwright_e2e import _node_path
    monkeypatch.setenv("NODE_PATH", "/tmp/silk-test-node-modules")
    assert _node_path() == "/tmp/silk-test-node-modules"


def test_two_http_resumes_execute_one_pipeline_and_leave_no_double_reservation(monkeypatch, tmp_path):
    """طلبا HTTP يقرآن نفس اللقطة: ينفّذ أحدهما، والآخر 409 بلا حجز باقٍ."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    from fastapi.testclient import TestClient
    import api
    import silk_storage as st
    import silk_usage
    import silk_research_pipeline

    for key, value in {"SILK_DB": str(tmp_path / "research.db"),
                       "SILK_USAGE_DB": str(tmp_path / "usage.db"),
                       "SILK_API_KEY": "secret", "ANTHROPIC_API_KEY": "test",
                       "SILK_RATE_LIMIT": "0", "SILK_MAX_CONCURRENT_RESEARCH": "3",
                       "SILK_PAID_DAILY_USD_CAP": "100"}.items():
        monkeypatch.setenv(key, value)
    release = threading.Event()
    calls = []

    def failing_pipeline(*a, **kw):
        calls.append(1)
        assert release.wait(timeout=10), "no competing response arrived"
        raise RuntimeError("offline test failure after admission")

    monkeypatch.setattr(silk_research_pipeline, "build", lambda **kw: failing_pipeline)
    client = TestClient(api.create_app())
    aid = st.create_research_run("تمور", "ESP", "080410",
                                 {"product": "تمور", "market": "Spain", "hs_code": "080410"})
    st.mark_research_failed(aid, "previous failure")
    real_read = st.get_research_run
    barrier, lock = threading.Barrier(2), threading.Lock()
    reads = 0

    def same_snapshot(*a, **kw):
        nonlocal reads
        row = real_read(*a, **kw)
        with lock:
            reads += 1
            synchronize = reads <= 2
        if synchronize:
            barrier.wait(timeout=5)
        return row

    monkeypatch.setattr(st, "get_research_run", same_snapshot)
    with patch("requests.sessions.Session.request", side_effect=OSError("net blocked")):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(client.post, "/research",
                                   headers={"X-API-Key": "secret"}, json={"resume": aid})
                       for _ in range(2)]
            try:
                first = next(as_completed(futures, timeout=10)).result()
                assert first.status_code == 409, first.text
            finally:
                release.set()
            responses = [f.result(timeout=10) for f in futures]
    assert sorted(r.status_code for r in responses) == [409, 500]
    assert calls == [1]
    assert silk_usage.usd_spent_today() == 0


@pytest.mark.parametrize("stop", ["shutdown", "reset_for_tests"])
def test_supervisor_stop_interrupts_a_long_heartbeat_wait(monkeypatch, stop):
    """الإغلاق لا ينتظر نبضةً كاملة، والمشرف القديم لا يستيقظ في الاختبار التالي."""
    from silk_platform import study_runtime as rt
    monkeypatch.setenv("SILK_PLATFORM_RUN_SUPERVISOR", "1")
    monkeypatch.setenv("SILK_PLATFORM_HEARTBEAT_S", "60")
    monkeypatch.setattr(rt, "_interrupt_run", lambda row: 0)
    thread = rt.start()
    try:
        if stop == "shutdown":
            rt.shutdown(join_s=0.2)
        else:
            rt.reset_for_tests()
        thread.join(timeout=0.2)
        assert not thread.is_alive(), "supervisor survived its stop signal"
    finally:
        rt._STOPPING = True
