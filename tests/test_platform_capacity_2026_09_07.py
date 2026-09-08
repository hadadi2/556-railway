"""ضغط طابور محلي: ألف تشغيلة بمحرك بديل، وليس ألف بحث حي متزامن.

Exercises real SQLite claims, worker completion and cleanup. No paid providers.
"""
import json
import threading
import time

from tests.platform_helpers import make_factory, seed


def test_thousand_queued_runs_complete_once_with_bounded_workers(monkeypatch):
    from silk_platform import db, engine_bridge as eb, study_runtime as rt
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    monkeypatch.setenv("SILK_PLATFORM_MAX_CONCURRENT_RUNS", "3")
    seed(monkeypatch)
    fac = make_factory("gold", "capacity@f.local")
    lock = threading.Lock()
    seen = {"active": 0, "peak": 0, "calls": 0}
    first_three = threading.Event()

    def engine(*a, **kw):
        with lock:
            seen["active"] += 1
            seen["calls"] += 1
            seen["peak"] = max(seen["peak"], seen["active"])
            number = seen["calls"]
            if number == 3:
                first_three.set()
        try:
            if number <= 3:
                assert first_three.wait(10), "scheduler did not fill three slots"
            return {"product": "تمور سكري", "hs_code": "080410", "classified": True,
                    "markets": [{"country": "الإمارات", "iso3": "ARE",
                                 "total_score": 0.5, "confidence": 0.4,
                                 "components": {}}], "analysis_id": number}
        finally:
            with lock:
                seen["active"] -= 1

    monkeypatch.setattr(eb, "_run_engine", engine)
    conn = db.connect()
    now = db.now_iso()
    try:
        for i in range(1000):
            token = f"capacity-{i}"
            cur = conn.execute(
                "INSERT INTO studies (owner_id, product, hs_code, market_pref, "
                "state, run_token, launched_at, run_started_at, created_at, updated_at) "
                "VALUES (?, 'تمور سكري', '080410', 'ARE', 'in_progress', ?, ?, ?, ?, ?)",
                (fac["account_id"], token, now, now, now, now))
            rt.create_run(conn, study_id=cur.lastrowid, run_token=token, mode="quick",
                          params={"product": "تمور سكري", "hs_code": "080410",
                                  "market_pref": "ARE", "hs_confirmed": True,
                                  "lang": "ar"})
        conn.commit()
    finally:
        conn.close()
    started = time.monotonic()
    rt.dispatch()
    assert rt.wait_idle(90), "durable queue did not drain"
    elapsed = time.monotonic() - started
    conn = db.connect()
    try:
        states = dict(conn.execute(
            "SELECT state, COUNT(*) FROM study_runs GROUP BY state").fetchall())
        assert states == {"completed": 1000}, states
        assert conn.execute("SELECT COUNT(*) FROM studies WHERE state='completed'").fetchone()[0] == 1000
    finally:
        conn.close()
    assert seen == {"active": 0, "peak": 3, "calls": 1000}
    assert not rt._HANDLES and not eb._ACTIVE
    print(json.dumps({"scope": "local SQLite scheduler with fake engine; not live research",
                      "runs": 1000, "peak_engine_calls": seen["peak"],
                      "elapsed_seconds": round(elapsed, 3), "paid_calls": 0}))
