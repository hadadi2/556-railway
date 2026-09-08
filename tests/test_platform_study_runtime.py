"""أقفال R2 — سجلّ تشغيلات الدراسات الدائم (`study_runs`) والمشرف على التنفيذ.

لماذا هذا الملف (أمر المالك 2026-09-02، إصلاح RC-1 حصراً): كانت تشغيلةُ
الدراسة خيطَ daemon بلا سجلٍّ دائم — لا نبضة ولا هويّة إقلاع ولا سقفَ تزامن
ولا إلغاء ولا ختمَ إغلاق؛ فإعادةُ النشر تترك «قيد الإعداد» ساعةً كاملة،
والتشغيلةُ المتجاوزة تُنفق بعد إرجاع صفّها. هذه الأقفال تُثبت أن **القاعدة
هي المرجع** لكل انتقال (queued→running→completed|failed|interrupted|cancelled)
وأن الإغلاق/الإقلاع لا يتركان دراسةً تبدو سليمةً وهي ميتة.

لا شبكة: المحرّك يُحاكى بـmonkeypatch على `engine_bridge._run_engine` — مقعدٌ
يُحجَب على `threading.Event` كي تُقاس الحالات الوسيطة عمداً. Hermetic only.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sqlite3
import threading
import time

import pytest

from tests.platform_helpers import hdr, login, make_factory, seed, client

pytest.importorskip("fastapi")

_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def env(monkeypatch):
    """بذر + عميل + مصنع ذهبي (سقف ٦ شهرياً) — يكفي لدراسات متعدّدة."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    info = seed(monkeypatch)
    cl = client()
    fac = make_factory("gold", "r2@f.local")
    tok = login(cl, fac["email"], fac["password"])
    return {"cl": cl, "fac": fac, "tok": tok, "info": info}


def _mk_study(cl, tok, **over):
    body = {"product": "تمور سكري", "hs_code": "080410", "market_pref": "ARE",
            **over}
    r = cl.post("/platform/studies", json=body, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


def _launch(env, sid: int) -> dict:
    r = env["cl"].post(f"/platform/studies/{sid}/launch", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    return r.json()


def _conn():
    from silk_platform import db as pdb
    return pdb.connect()


def _study_row(sid: int) -> dict:
    conn = _conn()
    try:
        return dict(conn.execute("SELECT * FROM studies WHERE id = ?",
                                 (sid,)).fetchone())
    finally:
        conn.close()


def _run_rows(sid: int) -> list[dict]:
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM study_runs WHERE study_id = ? ORDER BY id",
            (sid,)).fetchall()]
    finally:
        conn.close()


def _only_run(sid: int) -> dict:
    rows = _run_rows(sid)
    assert len(rows) == 1, rows
    return rows[0]


def _month_count(aid: int) -> int:
    conn = _conn()
    try:
        return int(conn.execute(
            "SELECT current_month_study_count FROM accounts WHERE id = ?",
            (aid,)).fetchone()[0])
    finally:
        conn.close()


def _notifications(sid: int, aid: int) -> list[dict]:
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT kind, title, body FROM platform_notifications "
            "WHERE study_id = ? AND account_id = ? ORDER BY id",
            (sid, aid)).fetchall()]
    finally:
        conn.close()


def _canned(analysis_id: int = 777) -> dict:
    return {"product": "تمور سكري", "hs_code": "080410", "classified": True,
            "markets": [{"country": "الإمارات", "iso3": "ARE",
                         "total_score": 0.5, "confidence": 0.4,
                         "components": {}}],
            "analysis_id": analysis_id, "note": "canned"}


def _blocking_engine(monkeypatch, analysis_id: int = 777, *,
                     cooperative: bool = True):
    """مقعد محرّك يُحجَب حتى `release` — ويتعاون مع الإلغاء كما يفعل الخطّ العميق.

    يعيد (started, release): `started` يُضبَط عند دخول المحرّك، و`release`
    يُطلِقه. `cooperative=True` يفحص `silk_context.check_cancelled` في حلقة
    الانتظار — نفس نقطة التفتيش التي يزرعها R2 عند حدود مراحل الخطّ.
    """
    import silk_platform.engine_bridge as eb
    started = threading.Event()
    release = threading.Event()

    def run(*_a, **_k):
        import silk_context
        started.set()
        deadline = time.monotonic() + 30.0
        while not release.is_set() and time.monotonic() < deadline:
            if cooperative:
                silk_context.check_cancelled("test-stage")
            release.wait(0.05)
        return _canned(analysis_id)

    monkeypatch.setattr(eb, "_run_engine", run)
    return started, release


def _wait_idle(timeout: float = 20.0) -> bool:
    from silk_platform import study_runtime
    return study_runtime.wait_idle(timeout)


def _seed_run(sid: int, *, token: str, state: str = "running",
              boot_id: str | None = "dead-boot",
              heartbeat_age_s: int | None = 0,
              analysis_id: int | None = None, mode: str = "quick") -> int:
    """صفّ تشغيلة مزروع يدوياً — لمحاكاة إقلاعٍ سابق أو خيطٍ مات."""
    from silk_platform.db import now_iso
    conn = _conn()
    try:
        hb = None
        if heartbeat_age_s is not None:
            hb = (dt.datetime.now(dt.timezone.utc)
                  - dt.timedelta(seconds=heartbeat_age_s)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur = conn.execute(
            "INSERT INTO study_runs (study_id, run_token, state, mode, boot_id, "
            "params_json, analysis_id, created_at, started_at, heartbeat_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, token, state, mode, boot_id, json.dumps({
                "product": "تمور سكري", "hs_code": "080410",
                "market_pref": "ARE", "hs_confirmed": False, "lang": "ar",
                "resume_analysis_id": None, "product_card": None}),
             analysis_id, now_iso(), now_iso() if state == "running" else None,
             hb))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _force_in_progress(sid: int, token: str, aid: int, *, count: int = 1):
    """اضبط الدراسة «قيد الإعداد» برمز محاولةٍ بعينه + عدّاد حصّة محجوز."""
    from silk_platform import quota
    from silk_platform.db import now_iso
    conn = _conn()
    try:
        now = now_iso()
        conn.execute(
            "UPDATE studies SET state = 'in_progress', run_token = ?, "
            "launched_at = ?, run_started_at = ?, run_error = NULL, "
            "run_stats = ? WHERE id = ?",
            (token, now, now, json.dumps({"mode": "quick"}), sid))
        conn.execute("UPDATE accounts SET current_month_study_count = ?, "
                     "quota_period = ? WHERE id = ?",
                     (count, quota.current_period(), aid))
        conn.commit()
    finally:
        conn.close()


# ── ١) الإطلاق ينشئ تشغيلةً دائمة واحدة · TEST 1 ────────────────────────────
def test_launch_creates_exactly_one_durable_run(env, monkeypatch):
    from silk_platform import study_runtime
    started, release = _blocking_engine(monkeypatch)
    s = _mk_study(env["cl"], env["tok"])
    out = _launch(env, s["id"])
    assert out["state"] == "in_progress"             # المفتاح القائم لم يتغيّر
    assert out["run_state"] == "running"             # الفتحة متاحة ⇒ انطلقت فوراً
    assert started.wait(5)
    run = _only_run(s["id"])
    assert run["state"] == "running"
    assert run["boot_id"] == study_runtime.boot_id()
    assert run["run_token"] == _study_row(s["id"])["run_token"]
    assert run["started_at"] and run["heartbeat_at"] and run["finished_at"] is None
    params = json.loads(run["params_json"])
    assert params["product"] == "تمور سكري" and params["market_pref"] == "ARE"
    release.set()
    assert _wait_idle()
    run = _only_run(s["id"])
    assert run["state"] == "completed" and run["finished_at"]
    assert run["analysis_id"] == 777
    assert _study_row(s["id"])["state"] == "completed"


def test_a_stray_active_run_row_is_superseded_on_relaunch(env, monkeypatch):
    """صفٌّ نشطٌ يتيم لدراسةٍ عادت مسودّةً لا يحجب الإطلاق بفهرس الفرادة."""
    # انتهى المحرك الفوري قبل قراءة HTTP في CI فأعاد finished بصورة صحيحة.
    # Hold the engine until the intermediate-state assertion, never race it.
    started, release = _blocking_engine(monkeypatch, 778)
    s = _mk_study(env["cl"], env["tok"])
    _seed_run(s["id"], token="OLD-STRAY", state="running")
    try:
        out = _launch(env, s["id"])                  # لا IntegrityError
        assert started.wait(5)
        assert out["run_state"] in ("running", "queued")
    finally:
        release.set()
    assert _wait_idle()
    rows = _run_rows(s["id"])
    assert [r["state"] for r in rows] == ["interrupted", "completed"]
    assert rows[0]["error_code"] == "superseded"


# ── ٢-٣) الانتظار عند امتلاء الفتحات + السقف لا يُتجاوَز · TEST 2, 3 ─────────
def test_launch_queues_when_the_cap_is_exhausted(env, monkeypatch):
    from silk_platform import study_runtime
    monkeypatch.setenv("SILK_PLATFORM_MAX_CONCURRENT_RUNS", "1")
    started, release = _blocking_engine(monkeypatch)
    a = _mk_study(env["cl"], env["tok"])
    b = _mk_study(env["cl"], env["tok"], product="عسل سدر")
    assert _launch(env, a["id"])["run_state"] == "running"
    assert started.wait(5)
    out_b = _launch(env, b["id"])
    assert out_b["run_state"] == "queued"
    assert _study_row(b["id"])["state"] == "in_progress"   # محجوزة، لا خيط بعد
    assert _only_run(b["id"])["state"] == "queued"
    assert len(study_runtime._HANDLES) == 1
    # القراءة العامّة تُعلن الانتظار بلا تغيير مفاتيح الردّ القائمة.
    r = env["cl"].get(f"/platform/studies/{b['id']}", headers=hdr(env["tok"]))
    assert r.status_code == 200 and r.json()["run"]["queued"] is True
    assert r.json()["run"]["state"] == "queued"
    draft = _mk_study(env["cl"], env["tok"], product="مسودّة")
    r = env["cl"].get("/platform/studies", headers=hdr(env["tok"]))
    by_id = {x["id"]: x for x in r.json()["studies"]}
    assert by_id[b["id"]]["run"]["queued"] is True
    assert "run" not in by_id[draft["id"]]
    release.set()                                    # A تنتهي ⇒ B تنطلق تلقائياً
    assert _wait_idle()
    assert _study_row(a["id"])["state"] == "completed"
    assert _study_row(b["id"])["state"] == "completed"
    assert _only_run(b["id"])["state"] == "completed"


def test_the_cap_is_never_exceeded(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    monkeypatch.setenv("SILK_PLATFORM_MAX_CONCURRENT_RUNS", "2")
    lock = threading.Lock()
    seen = {"now": 0, "max": 0}

    def run(*_a, **_k):
        with lock:
            seen["now"] += 1
            seen["max"] = max(seen["max"], seen["now"])
        time.sleep(0.25)
        with lock:
            seen["now"] -= 1
        return _canned(779)

    monkeypatch.setattr(eb, "_run_engine", run)
    ids = [_mk_study(env["cl"], env["tok"], product=f"منتج {i}")["id"]
           for i in range(6)]
    for sid in ids:
        _launch(env, sid)
    assert _wait_idle(40)
    assert seen["max"] <= 2, seen
    assert all(_study_row(sid)["state"] == "completed" for sid in ids)
    assert all(_only_run(sid)["state"] == "completed" for sid in ids)


# ── ٤) المطالبة بالتشغيلة واحدةٌ لا تتكرّر · TEST 4 ──────────────────────────
def test_duplicate_claim_is_impossible(env, monkeypatch):
    from silk_platform import study_runtime
    started, release = _blocking_engine(monkeypatch)
    s = _mk_study(env["cl"], env["tok"])
    _force_in_progress(s["id"], "T-RACE", env["fac"]["account_id"])
    _seed_run(s["id"], token="T-RACE", state="queued", boot_id=None,
              heartbeat_age_s=None)
    n = 6
    barrier = threading.Barrier(n)
    started_counts: list[int] = []
    errors: list[BaseException] = []

    def race():
        try:
            barrier.wait(timeout=10)
            started_counts.append(study_runtime.dispatch())
        except BaseException as exc:  # noqa: BLE001 — يُجمَع للتقرير
            errors.append(exc)

    threads = [threading.Thread(target=race) for _ in range(n)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    assert not errors, errors
    assert sum(started_counts) == 1                  # رابح واحد بالضبط
    assert len(study_runtime._HANDLES) == 1
    assert _only_run(s["id"])["state"] == "running"
    # فهرس الفرادة الجزئي: صفٌّ نشط ثانٍ لنفس الدراسة مرفوض بنيوياً.
    with pytest.raises(sqlite3.IntegrityError):
        _seed_run(s["id"], token="T-SECOND", state="queued")
    release.set()
    assert _wait_idle()


# ── ٥-٧) النبضة والتقادم وحماية الحيّ · TEST 5, 6, 7 ─────────────────────────
def test_heartbeat_advances_for_registered_runs_only(env, monkeypatch):
    from silk_platform import study_runtime
    started, release = _blocking_engine(monkeypatch)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert started.wait(5)
    foreign = _mk_study(env["cl"], env["tok"], product="غريب")
    _force_in_progress(foreign["id"], "T-FOREIGN", env["fac"]["account_id"])
    _seed_run(foreign["id"], token="T-FOREIGN", heartbeat_age_s=60)
    hb0 = _only_run(s["id"])["heartbeat_at"]
    hb_foreign = _only_run(foreign["id"])["heartbeat_at"]
    time.sleep(1.1)                                   # دقّة `now_iso` ثانية
    out = study_runtime.tick()
    assert out["heartbeat"] == 1
    assert _only_run(s["id"])["heartbeat_at"] > hb0
    fr = _only_run(foreign["id"])
    assert fr["heartbeat_at"] == hb_foreign          # لم يُنبَض (لا مقبض له)
    assert fr["state"] == "running"                  # ولم يُكنَس (طازج ضمن العتبة)
    release.set()
    assert _wait_idle()


def test_a_stale_run_is_interrupted_with_refund_pointer_and_notification(env):
    from silk_platform import study_runtime
    import silk_storage
    aid = env["fac"]["account_id"]
    s = _mk_study(env["cl"], env["tok"])
    _force_in_progress(s["id"], "T-STALE", aid, count=1)
    engine_id = silk_storage.create_research_run(
        "تمور سكري", "ARE", "080410", {"product": "تمور سكري", "market": "ARE"})
    _seed_run(s["id"], token="T-STALE", heartbeat_age_s=600,
              analysis_id=engine_id)
    out = study_runtime.tick()
    assert out["interrupted"] == 1
    run = _only_run(s["id"])
    assert run["state"] == "interrupted" and run["error_code"] == "interrupted"
    assert run["finished_at"]
    row = _study_row(s["id"])
    assert row["state"] == "draft"
    assert "انقطع" in (row["run_error"] or "")
    assert row["analysis_id"] == engine_id          # مؤشّر الاستئناف محفوظ
    assert _month_count(aid) == 0                    # الحصّة أُرجعت
    kinds = [n["kind"] for n in _notifications(s["id"], aid)]
    assert "study_failed" in kinds
    # صفّ المحرّك نفسه لا يبقى 'running' إلى الأبد — حجزه يُصالَح فوراً.
    assert silk_storage.get_research_run(engine_id)["status"] == "failed"


def test_a_healthy_run_is_never_interrupted(env, monkeypatch):
    from silk_platform import study_runtime
    started, release = _blocking_engine(monkeypatch)
    own = _mk_study(env["cl"], env["tok"])
    _launch(env, own["id"])
    assert started.wait(5)
    other = _mk_study(env["cl"], env["tok"], product="آخر")
    _force_in_progress(other["id"], "T-FRESH", env["fac"]["account_id"])
    _seed_run(other["id"], token="T-FRESH", boot_id="other-container",
              heartbeat_age_s=5)                    # حيّ في حاويةٍ أخرى (نشر متداخل)
    out = study_runtime.tick()
    assert out["interrupted"] == 0
    assert _only_run(own["id"])["state"] == "running"
    assert _only_run(other["id"])["state"] == "running"
    assert _study_row(other["id"])["state"] == "in_progress"
    release.set()
    assert _wait_idle()


# ── ٨) الإلغاء التعاوني · TEST 8 ──────────────────────────────────────────────
def test_cancel_a_queued_run_reverts_immediately(env, monkeypatch):
    monkeypatch.setenv("SILK_PLATFORM_MAX_CONCURRENT_RUNS", "1")
    started, release = _blocking_engine(monkeypatch)
    a = _mk_study(env["cl"], env["tok"])
    b = _mk_study(env["cl"], env["tok"], product="عسل")
    _launch(env, a["id"])
    assert started.wait(5)
    assert _launch(env, b["id"])["run_state"] == "queued"
    r = env["cl"].post(f"/platform/studies/{b['id']}/cancel", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert r.json()["run_state"] == "cancelled"
    run = _only_run(b["id"])
    assert run["state"] == "cancelled" and run["error_code"] == "cancelled"
    row = _study_row(b["id"])
    assert row["state"] == "draft" and "أُلغيت" in (row["run_error"] or "")
    assert _month_count(env["fac"]["account_id"]) == 1     # حصّة A وحدها
    assert _only_run(a["id"])["state"] == "running"
    release.set()
    assert _wait_idle()
    assert _study_row(a["id"])["state"] == "completed"


def test_cancel_a_running_run_is_cooperative_and_declared(env, monkeypatch):
    from silk_platform import study_runtime
    started, release = _blocking_engine(monkeypatch)   # لا release ⇒ الإلغاء وحده يوقفه
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert started.wait(5)
    r = env["cl"].post(f"/platform/studies/{s['id']}/cancel", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert r.json()["run_state"] == "cancelling"
    assert _only_run(s["id"])["cancel_requested_at"]
    assert any(h.cancel.is_set() for h in study_runtime._HANDLES.values())
    assert _wait_idle()
    run = _only_run(s["id"])
    assert run["state"] == "cancelled"
    row = _study_row(s["id"])
    assert row["state"] == "draft"
    assert "أُلغيت" in (row["run_error"] or "")
    assert "RunCancelled" not in (row["run_error"] or "")   # لا رطانة للمصنع
    assert _month_count(env["fac"]["account_id"]) == 0
    # طلبٌ ثانٍ على دراسةٍ لم تعد جارية = 409 معلَن.
    r = env["cl"].post(f"/platform/studies/{s['id']}/cancel", headers=hdr(env["tok"]))
    assert r.status_code == 409 and r.json()["detail"]["error"] == "study_not_running"


def test_a_late_cancel_never_discards_a_durably_saved_success(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    from silk_platform import study_runtime

    def run(*_a, **_k):
        for h in list(study_runtime._HANDLES.values()):
            h.cancel.set()                            # وصل الإلغاء بعد فوات الأوان
        return _canned(780)

    monkeypatch.setattr(eb, "_run_engine", run)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert _wait_idle()
    assert _study_row(s["id"])["state"] == "completed"
    assert _only_run(s["id"])["state"] == "completed"


def test_accepted_cancel_before_completion_commit_preserves_saved_analysis(env, monkeypatch):
    """الإلغاء المقبول في SQLite يفوز قبل معاملة الاكتمال؛ لا حذف للنتيجة."""
    import silk_platform.engine_bridge as eb
    started, release = threading.Event(), threading.Event()
    def run(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return _canned(782)
    monkeypatch.setattr(eb, "_run_engine", run)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    try:
        assert started.wait(5)
        r = env["cl"].post(f"/platform/studies/{s['id']}/cancel", headers=hdr(env["tok"]))
        assert r.status_code == 200
    finally:
        release.set()
    assert _wait_idle()
    assert _only_run(s["id"])["state"] == "cancelled"
    assert _only_run(s["id"])["analysis_id"] == 782


def test_cancel_needs_a_running_study_and_stays_tenant_scoped(env, monkeypatch):
    s = _mk_study(env["cl"], env["tok"])
    r = env["cl"].post(f"/platform/studies/{s['id']}/cancel", headers=hdr(env["tok"]))
    assert r.status_code == 409 and r.json()["detail"]["error"] == "study_not_running"
    other = make_factory("silver", "r2-other@f.local")
    tok2 = login(env["cl"], other["email"], other["password"])
    r = env["cl"].post(f"/platform/studies/{s['id']}/cancel", headers=hdr(tok2))
    assert r.status_code == 404                      # لا تسريب وجود عبر المستأجر


def test_cancel_cannot_accept_after_a_stale_read_loses_to_completion(env):
    """الاكتمال بين SELECT وUPDATE لا ينتج قبول إلغاء كاذباً."""
    from silk_platform import study_runtime, lifecycle
    study = _mk_study(env["cl"], env["tok"])
    run_id = _seed_run(study["id"], token="cancel-read-race")
    conn = _conn()
    class RacingConnection:
        def execute(self, sql, parameters=()):
            if sql.startswith("UPDATE study_runs SET cancel_requested_at"):
                conn.execute("UPDATE study_runs SET state='completed' WHERE id=?", (run_id,))
                conn.commit()
            return conn.execute(sql, parameters)
        def __getattr__(self, name):
            return getattr(conn, name)
    try:
        with pytest.raises(lifecycle.LifecycleError):
            study_runtime.request_cancel(RacingConnection(), study_id=study["id"], account_id=env["fac"]["account_id"], actor_user_id=None)
    finally:
        conn.close()


# ── ٩-١٠) الفشل والنجاح يُغلقان صفّ التشغيلة على سياجه · TEST 9, 10 ─────────
def test_engine_failure_marks_the_run_failed_and_redacted(env, monkeypatch):
    import silk_platform.engine_bridge as eb

    def boom(*_a, **_k):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(eb, "_run_engine", boom)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert _wait_idle()
    run = _only_run(s["id"])
    assert run["state"] == "failed" and run["error_code"] == "engine_failed"
    assert run["finished_at"]
    assert "RuntimeError" not in (run["error_text"] or "")
    assert "engine exploded" in (run["error_text"] or "")
    assert _study_row(s["id"])["state"] == "draft"


def test_the_run_row_closes_even_when_the_study_fence_misses(env):
    """قاعدة السياج الذاتي: صفُّ تشغيلةٍ عالق يحجب كل إطلاقٍ لاحق — فلا يُترك."""
    import silk_platform.engine_bridge as eb
    s = _mk_study(env["cl"], env["tok"])
    _seed_run(s["id"], token="T-ORPHAN", state="running")   # الدراسة مسودّة أصلاً
    eb._finish_failure(s["id"], env["fac"]["account_id"], "سبب", run_token="T-ORPHAN")
    run = _only_run(s["id"])
    assert run["state"] == "failed" and run["finished_at"]
    assert _study_row(s["id"])["state"] == "draft"


def test_success_marks_the_run_completed(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    monkeypatch.setattr(eb, "_run_engine", lambda *a, **k: _canned(781))
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert _wait_idle()
    run = _only_run(s["id"])
    assert run["state"] == "completed" and run["finished_at"]
    assert run["analysis_id"] == 781 and run["error_code"] is None
    assert _study_row(s["id"])["analysis_id"] == 781


# ── ١١) الإغلاق لا يوسم مكتملاً ولا يترك جارياً · TEST 11 ────────────────────
def test_shutdown_interrupts_active_runs_and_never_completes_them(env, monkeypatch):
    from fastapi.testclient import TestClient
    from silk_platform import study_runtime
    from silk_platform.api import create_platform_app
    started, release = _blocking_engine(monkeypatch)
    with TestClient(create_platform_app()) as cl:   # مدير السياق يشغّل حدث الإغلاق
        tok = login(cl, env["fac"]["email"], env["fac"]["password"])
        s = _mk_study(cl, tok)
        r = cl.post(f"/platform/studies/{s['id']}/launch", headers=hdr(tok))
        assert r.status_code == 200
        assert started.wait(5)
    run = _only_run(s["id"])
    assert run["state"] == "interrupted" and run["error_code"] == "interrupted"
    row = _study_row(s["id"])
    assert row["state"] == "draft" and "انقطع" in (row["run_error"] or "")
    assert study_runtime.dispatch() == 0             # لا مطالبة أثناء الإغلاق
    release.set()                                    # الخيط يصحو متأخّراً — مسيَّج
    assert _wait_idle()
    assert _study_row(s["id"])["state"] == "draft"
    assert _only_run(s["id"])["state"] == "interrupted"
    client()                                         # تركيبٌ جديد يمسح علم الإغلاق
    assert study_runtime._STOPPING is False


# ── ١٢-١٣) تعافي الإقلاع وهويّة الإقلاع · TEST 12, 13 ─────────────────────────
def test_startup_recovery_interrupts_stale_and_dispatches_queued(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    from silk_platform import study_runtime
    monkeypatch.setattr(eb, "_run_engine", lambda *a, **k: _canned(782))
    aid = env["fac"]["account_id"]
    dead = _mk_study(env["cl"], env["tok"], product="ميتة")
    _force_in_progress(dead["id"], "T-DEAD", aid)
    _seed_run(dead["id"], token="T-DEAD", boot_id="previous-boot",
              heartbeat_age_s=900)
    queued = _mk_study(env["cl"], env["tok"], product="منتظرة")
    _force_in_progress(queued["id"], "T-QUEUED", aid)
    _seed_run(queued["id"], token="T-QUEUED", state="queued",
              boot_id="previous-boot", heartbeat_age_s=None)
    out = study_runtime.recover()
    assert out["interrupted"] == 1 and out["dispatched"] == 1
    assert _only_run(dead["id"])["state"] == "interrupted"
    assert _study_row(dead["id"])["state"] == "draft"
    assert _wait_idle()
    assert _only_run(queued["id"])["state"] == "completed"
    assert _study_row(queued["id"])["state"] == "completed"


def test_boot_id_distinguishes_current_from_previous_boot(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    from silk_platform import study_runtime
    assert re.fullmatch(r"[0-9a-f]{32}", study_runtime.boot_id())
    monkeypatch.setattr(eb, "_run_engine", lambda *a, **k: _canned(783))
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert _wait_idle()
    mine = _only_run(s["id"])["boot_id"]
    assert mine == study_runtime.boot_id()
    monkeypatch.setattr(study_runtime, "BOOT_ID", "0" * 32)   # إقلاعٌ جديد
    assert study_runtime.boot_id() == "0" * 32
    assert study_runtime.boot_id() != mine
    conn = _conn()
    try:
        prev = conn.execute("SELECT COUNT(*) FROM study_runs WHERE boot_id != ?",
                            (study_runtime.boot_id(),)).fetchone()[0]
    finally:
        conn.close()
    assert prev == 1


def test_shutdown_only_touches_runs_of_this_boot(env, monkeypatch):
    from silk_platform import study_runtime
    aid = env["fac"]["account_id"]
    other = _mk_study(env["cl"], env["tok"], product="حاوية أخرى")
    _force_in_progress(other["id"], "T-OTHER", aid)
    _seed_run(other["id"], token="T-OTHER", boot_id="other-container",
              heartbeat_age_s=2)
    out = study_runtime.shutdown()
    assert out["interrupted"] == 0
    assert _only_run(other["id"])["state"] == "running"
    study_runtime.reset_for_tests()


# ── ١٤) المهلة القصوى تعاونية ثم حاسمة · TEST 14 ─────────────────────────────
def test_timeout_sets_cancel_and_finalizes_immediately(env, monkeypatch):
    from silk_platform import study_runtime
    started, release = _blocking_engine(monkeypatch)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert started.wait(5)
    h = next(iter(study_runtime._HANDLES.values()))
    h.started_monotonic -= 100_000                    # أقدم من أي نافذة سماح
    out = study_runtime.tick()
    assert out["timed_out"] == 1
    assert h.cancel.is_set()
    run = _only_run(s["id"])
    assert run["state"] == "failed" and run["error_code"] == "timeout"
    row = _study_row(s["id"])
    assert row["state"] == "draft" and "المهلة" in (row["run_error"] or "")
    release.set()
    assert _wait_idle()
    assert _study_row(s["id"])["state"] == "draft"    # الخيط المتأخّر مسيَّج


# ── الكنس القديم يترك التشغيلات المسجَّلة لمشرفها · legacy sweep boundary ──────
def test_legacy_sweep_skips_run_backed_studies(env):
    import silk_platform.engine_bridge as eb
    aid = env["fac"]["account_id"]
    s = _mk_study(env["cl"], env["tok"])
    _force_in_progress(s["id"], "T-BACKED", aid)
    _seed_run(s["id"], token="T-BACKED", boot_id="previous-boot",
              heartbeat_age_s=99_999)
    conn = _conn()
    try:
        conn.execute("UPDATE studies SET run_started_at = '2020-01-01T00:00:00Z' "
                     "WHERE id = ?", (s["id"],))
        conn.commit()
        swept = eb.sweep_orphans(conn)
    finally:
        conn.close()
    assert swept["reverted"] == 0 and swept["completed"] == 0
    assert _study_row(s["id"])["state"] == "in_progress"


# ── الحذف والترحيل · delete guard + additive migration ────────────────────────
def test_delete_refuses_an_active_run_and_cleans_terminal_rows(env, monkeypatch):
    started, release = _blocking_engine(monkeypatch)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert started.wait(5)
    r = env["cl"].delete(f"/platform/studies/{s['id']}", headers=hdr(env["tok"]))
    assert r.status_code == 409 and r.json()["detail"]["error"] == "study_running"
    release.set()
    assert _wait_idle()
    r = env["cl"].delete(f"/platform/studies/{s['id']}", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert _run_rows(s["id"]) == []


def test_migration_018_is_additive_and_idempotent(tmp_path):
    from silk_platform import db as pdb
    sql = (_ROOT / "migrations" / "platform" / "018_study_runs.sql").read_text(
        encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS study_runs" in sql
    assert "ux_study_runs_active" in sql
    assert "DROP " not in sql.upper() and "DELETE " not in sql.upper()
    assert "ALTER TABLE studies" not in sql                 # حالات الدراسة لم تُمَسّ
    path = str(tmp_path / "p.db")
    first = pdb.apply_migrations(path)
    assert "018" in first
    assert pdb.apply_migrations(path) == []
    conn = pdb.connect(path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(study_runs)")}
        states = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'studies'").fetchone()[0]
    finally:
        conn.close()
    assert {"study_id", "run_token", "state", "mode", "boot_id", "params_json",
            "analysis_id", "heartbeat_at", "cancel_requested_at",
            "error_code"} <= cols
    assert "'draft','in_progress','completed','archived'" in states


# ── الواجهة الدنيا · minimal UI wiring ───────────────────────────────────────
def test_page_wires_cancel_and_waiting_label():
    html = (_ROOT / "web" / "platform.html").read_text(encoding="utf-8")
    assert '"cancel"' in html and "في الانتظار" in html
    assert re.search(r"(?<![\w])study_not_running\s*:", html)
    assert re.search(r"(?<![\w])study_running\s*:", html)


# ── مراجعة §58 على R2 — أقفال الملاحظات · self-review locks ──────────────────
def test_archive_and_complete_refuse_a_study_with_an_active_run(env, monkeypatch):
    """§58 #1: أرشفةُ دراسةٍ منتظرة كانت تترك صفَّها منتظراً فيُنفَّذ لاحقاً على
    دراسةٍ مؤرشفة بلا ربطٍ ولا إرجاع حصّة — 409 معلَن كالحذف، والإلغاء هو المخرج."""
    monkeypatch.setenv("SILK_PLATFORM_MAX_CONCURRENT_RUNS", "1")
    started, release = _blocking_engine(monkeypatch)
    a = _mk_study(env["cl"], env["tok"])
    b = _mk_study(env["cl"], env["tok"], product="منتظرة")
    _launch(env, a["id"])
    assert started.wait(5)
    assert _launch(env, b["id"])["run_state"] == "queued"
    for action in ("archive", "complete"):
        r = env["cl"].post(f"/platform/studies/{b['id']}/{action}",
                           headers=hdr(env["tok"]))
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["error"] == "study_running"
    assert _only_run(b["id"])["state"] == "queued"
    r = env["cl"].post(f"/platform/studies/{b['id']}/cancel", headers=hdr(env["tok"]))
    assert r.status_code == 200 and r.json()["run_state"] == "cancelled"
    r = env["cl"].post(f"/platform/studies/{b['id']}/archive", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    release.set()
    assert _wait_idle()


def test_dispatch_never_runs_a_queued_row_whose_study_left_in_progress(env, monkeypatch):
    """§58 #1 (حزام ثانٍ): صفٌّ منتظر لدراسةٍ لم تعد «قيد الإعداد» يُغلَق
    `cancelled` عند المطالبة — لا خيط، لا إنفاق."""
    from silk_platform import study_runtime
    started, release = _blocking_engine(monkeypatch)
    s = _mk_study(env["cl"], env["tok"])                    # مسودّة
    _seed_run(s["id"], token="T-STRAY-Q", state="queued", boot_id=None,
              heartbeat_age_s=None)
    assert study_runtime.dispatch() == 0
    assert not started.is_set()
    run = _only_run(s["id"])
    assert run["state"] == "cancelled" and run["finished_at"]
    assert _study_row(s["id"])["state"] == "draft"


def test_launch_survives_a_dispatch_failure_after_commit(env, monkeypatch):
    """§58 #5: عطلٌ في المطالبة بعد الالتزام (قفلٌ مشغول) لا يقلب إطلاقاً ناجحاً
    إلى 500 — الردّ يعلن «منتظرة» والمشرف يطالب بها في دورته."""
    from silk_platform import study_runtime

    def boom():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(study_runtime, "dispatch", boom)
    s = _mk_study(env["cl"], env["tok"])
    out = _launch(env, s["id"])
    assert out["state"] == "in_progress" and out["run_state"] == "queued"
    assert _study_row(s["id"])["state"] == "in_progress"
    assert _only_run(s["id"])["state"] == "queued"


def test_delete_race_with_a_fresh_queued_row_is_409_not_500(env, monkeypatch):
    """§58 #3: إطلاقٌ متزامن يُدرج صفّاً منتظراً بين فحص الحذف وتنفيذه — المفتاح
    الأجنبي يرفض الحذف، والرفض يُعلَن 409 لا 500."""
    from silk_platform import study_runtime
    s = _mk_study(env["cl"], env["tok"])
    _force_in_progress(s["id"], "T-RACE-DEL", env["fac"]["account_id"])
    _seed_run(s["id"], token="T-RACE-DEL", state="queued", boot_id=None,
              heartbeat_age_s=None)
    monkeypatch.setattr(study_runtime, "has_active_run", lambda conn, sid: False)
    r = env["cl"].delete(f"/platform/studies/{s['id']}", headers=hdr(env["tok"]))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "study_running"
    assert _study_row(s["id"])["state"] == "in_progress"
    assert _only_run(s["id"])["state"] == "queued"


def test_sweeper_pass_applies_the_timeout_when_the_supervisor_is_off(env, monkeypatch):
    """§58 #4: بلا خيط المشرف (SILK_PLATFORM_RUN_SUPERVISOR=0) كانت المهلة القصوى
    تختفي مع تخطّي الكنس القديم للصفوف المسجَّلة — كنسةُ المجدول تُنبض بدله."""
    from silk_platform import scheduler, study_runtime
    monkeypatch.setenv("SILK_PLATFORM_RUN_SUPERVISOR", "0")
    started, release = _blocking_engine(monkeypatch)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert started.wait(5)
    h = next(iter(study_runtime._HANDLES.values()))
    h.started_monotonic -= 100_000
    scheduler.sweep_pass()
    run = _only_run(s["id"])
    assert run["state"] == "failed" and run["error_code"] == "timeout"
    assert _study_row(s["id"])["state"] == "draft"
    release.set()
    assert _wait_idle()


def test_a_user_cancel_that_crosses_the_grace_window_stays_cancelled(env, monkeypatch):
    """§58 #8: مهلةٌ تنقضي بعد طلب إلغاءٍ لا تُعيد تسمية طلب المصنع «تعثّراً»."""
    from silk_platform import study_runtime
    started, release = _blocking_engine(monkeypatch, cooperative=False)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert started.wait(5)
    r = env["cl"].post(f"/platform/studies/{s['id']}/cancel", headers=hdr(env["tok"]))
    assert r.status_code == 200 and r.json()["run_state"] == "cancelling"
    h = next(iter(study_runtime._HANDLES.values()))
    h.started_monotonic -= 100_000
    out = study_runtime.tick()
    assert out["timed_out"] == 1
    run = _only_run(s["id"])
    assert run["state"] == "cancelled" and run["error_code"] == "cancelled"
    assert "أُلغيت" in (_study_row(s["id"])["run_error"] or "")
    release.set()
    assert _wait_idle()


def test_interrupting_a_cancel_requested_dead_run_labels_it_cancelled(env):
    """§58 #9: طلبُ إلغاءٍ على تشغيلةٍ ماتت عمليتُها يُحسَم «أُلغيت» لا «انقطع»."""
    from silk_platform import study_runtime
    from silk_platform.db import now_iso
    aid = env["fac"]["account_id"]
    s = _mk_study(env["cl"], env["tok"])
    _force_in_progress(s["id"], "T-DEAD-CANCEL", aid)
    rid = _seed_run(s["id"], token="T-DEAD-CANCEL", boot_id="dead", heartbeat_age_s=900)
    conn = _conn()
    try:
        conn.execute("UPDATE study_runs SET cancel_requested_at = ? WHERE id = ?",
                     (now_iso(), rid))
        conn.commit()
    finally:
        conn.close()
    assert study_runtime.tick()["interrupted"] == 1
    run = _only_run(s["id"])
    assert run["state"] == "cancelled" and run["error_code"] == "cancelled"
    row = _study_row(s["id"])
    assert row["state"] == "draft" and "أُلغيت" in (row["run_error"] or "")
    assert _month_count(aid) == 0


# ── مراجعة تدقيق الفرق النهائي (2026-09-02) · final diff-audit review locks ──
def test_mount_survives_a_starlette_without_app_level_add_event_handler(monkeypatch):
    """تدقيق الفرق النهائي: Starlette ≥1.0 حذفت `add_event_handler`/`on_startup`/
    `on_shutdown` من `Starlette`/`FastAPI` (أُبقيت على `APIRouter` وحدها) — والمكدّس
    الذي يحلّه حرفياً `pip install -r requirements.txt -r requirements-ci.txt`
    (أمرا CI وDockerfile) يحمل Starlette 1.6.0 اليوم إذ `requirements.txt` لا يثبّت
    Starlette، بينما محليّاً 0.52.1 لا تزال تحمل الطريقة على `Starlette` فيمرّ
    الاستدعاء القديم محلياً زوراً بينما ينهار الإقلاع فعلياً على المكدّس المنشور.
    هذا القفل يحاكي غيابها فيثبت أن `mount()` يستعمل الشكل الثابت عبر الإصدارين:
    `app.router.add_event_handler` لا `app.add_event_handler`."""
    import starlette.applications
    from fastapi import FastAPI
    import silk_platform
    from silk_platform import study_runtime

    monkeypatch.delattr(starlette.applications.Starlette, "add_event_handler",
                        raising=False)
    app = FastAPI()
    assert not hasattr(app, "add_event_handler")        # تأكيدُ أن المحاكاة نجحت
    assert silk_platform.mount(app) is True
    assert study_runtime.shutdown in app.router.on_shutdown


def test_a_crash_between_the_queued_cancel_writes_leaves_a_recoverable_row(
        env, monkeypatch):
    """تدقيق الفرق النهائي: الفرع المنتظِر في `request_cancel` كان يُغلق صفَّ
    `study_runs` ويلتزم (اتصال المنادي)، ثم يستدعي `_finish_failure` (اتصالٌ ثانٍ،
    التزامٌ ثانٍ) لإعادة الدراسة مسودّةً وإرجاع الحصّة — عطلٌ بين الالتزامين كان
    يترك الصفّ «أُلغيت» والدراسة «قيد الإعداد» بلا تشغيلةٍ نشطة، غير قابلٍ للإلغاء
    ولا لإعادة الإطلاق حتى نافذة الكنس القديم (٩٠٠/٣٦٠٠ث). الآن الإغلاق يقع **داخل**
    التزام `_finish_failure` نفسه (على سياج `_close_run_row` لصفٍّ لا يزال `queued`)
    — فعطلٌ قبله يترك الصفَّ `queued` بعلَم إلغاءٍ مضبوط: قابلٌ للمطالبة عادةً،
    ويُلغي نفسه عند نقطة تفتيشه الأولى (نفس مسار الاختبار السابق)."""
    monkeypatch.setenv("SILK_PLATFORM_MAX_CONCURRENT_RUNS", "1")
    started, release = _blocking_engine(monkeypatch)
    a = _mk_study(env["cl"], env["tok"])
    b = _mk_study(env["cl"], env["tok"], product="عسل")
    _launch(env, a["id"])
    assert started.wait(5)
    assert _launch(env, b["id"])["run_state"] == "queued"

    import silk_platform.engine_bridge as eb
    orig_finish_failure = eb._finish_failure

    def boom(*a_, **k_):
        monkeypatch.setattr(eb, "_finish_failure", orig_finish_failure)  # مرّةً واحدة
        raise RuntimeError("simulated crash before the studies-revert commit")

    monkeypatch.setattr(eb, "_finish_failure", boom)
    from silk_platform import db as pdb, study_runtime
    conn = pdb.connect()
    try:
        with pytest.raises(RuntimeError):
            study_runtime.request_cancel(
                conn, study_id=b["id"], account_id=env["fac"]["account_id"],
                actor_user_id=None)
    finally:
        conn.close()
    # الصفّ لا يزال «منتظراً» موسوماً بطلب الإلغاء — لا «أُلغيت» بلا مقابل.
    run = _only_run(b["id"])
    assert run["state"] == "queued" and run["cancel_requested_at"]
    # الدراسة لا تزال «قيد الإعداد» متّسقةً مع الصفّ — لا انفصال بين الاثنين.
    assert _study_row(b["id"])["state"] == "in_progress"
    release.set()
    assert _wait_idle()
    assert _study_row(a["id"])["state"] == "completed"


def test_cancel_flag_set_before_registration_is_honoured_at_start(env, monkeypatch):
    """§58 #10: إلغاءٌ سُجِّل في القاعدة قبل تسجيل المقبض يُلتقَط عند بدء الخيط
    لا عند النبضة التالية."""
    from silk_platform import study_runtime
    from silk_platform.db import now_iso
    started, release = _blocking_engine(monkeypatch)
    s = _mk_study(env["cl"], env["tok"])
    _force_in_progress(s["id"], "T-EARLY-CANCEL", env["fac"]["account_id"])
    rid = _seed_run(s["id"], token="T-EARLY-CANCEL", state="queued", boot_id=None,
                    heartbeat_age_s=None)
    conn = _conn()
    try:
        conn.execute("UPDATE study_runs SET cancel_requested_at = ? WHERE id = ?",
                     (now_iso(), rid))
        conn.commit()
    finally:
        conn.close()
    assert study_runtime.dispatch() == 1
    assert _wait_idle(10)                             # بلا release ولا tick
    run = _only_run(s["id"])
    assert run["state"] == "cancelled"
    assert "أُلغيت" in (_study_row(s["id"])["run_error"] or "")
