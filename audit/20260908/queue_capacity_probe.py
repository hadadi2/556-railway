"""Offline capacity probe of the real SQLite queue dispatcher; AI is simulated.

This measures offered jobs at the default worker cap (3), not concurrent paid
studies. There is no HTTP admission/quota exercise and no external request.
"""
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import threading
import time
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
os.environ["SILK_PLATFORM_RUN_SUPERVISOR"] = "0"
os.environ["SILK_PLATFORM_ORPHAN_SWEEP"] = "0"
os.environ["SILK_PLATFORM_MAX_CONCURRENT_RUNS"] = "3"
from silk_platform import db, study_runtime as queue, engine_bridge as bridge

results = []
for offered in [1, 10, 50, 100, 500, 1000]:
    with tempfile.TemporaryDirectory(prefix="silk-queue-probe-") as folder:
        os.environ["SILK_DATA_DIR"] = folder
        db.init_db(force=True)
        conn = db.connect()
        now = db.now_iso()
        conn.execute("INSERT INTO accounts(id,name,kind,created_at,updated_at) VALUES (1,'Audit','factory',?,?)", (now,now))
        for i in range(1, offered + 1):
            token = "audit-" + str(i)
            conn.execute("INSERT INTO studies(id,owner_id,state,product,run_token,created_at,updated_at) VALUES (?,1,'in_progress','Audit',?,?,?)", (i,token,now,now))
            queue.create_run(conn, study_id=i, run_token=token, mode="quick", params={"product":"Audit"})
        conn.commit()
        conn.close()
        starts, finishes, durations, seen, active, peak = [], [], [], set(), 0, 0
        lock = threading.Lock()
        ready = threading.Event()
        start = time.monotonic()
        cpu0 = time.process_time()
        def fake_engine_body(study_id, account_id, product, hs, market, hs_confirmed,
                             run_token, lang, card, resume, run=None, **kwargs):
            global active, peak
            stamp = time.monotonic()
            with lock:
                assert study_id not in seen
                seen.add(study_id)
                starts.append(stamp - start)
                active += 1
                peak = max(peak, active)
            # Small fixed provider-like wait; no model, payload, network or PDF.
            ready.wait(.02)
            bridge._finish_success(study_id, account_id, study_id, run_token=run_token)
            with lock:
                active -= 1
                durations.append(time.monotonic() - stamp)
                finishes.append(time.monotonic() - start)
        with patch.object(bridge, "_thread_body", side_effect=fake_engine_body), \
             patch.object(bridge, "_notify_after_commit"), \
             patch("requests.sessions.Session.request", side_effect=OSError("offline audit")):
            queue.recover()
            deadline = start + 60
            while len(finishes) < offered and time.monotonic() < deadline:
                ready.wait(.01)
            assert len(finishes) == offered, (offered, len(finishes))
            # Wait for dispatcher bookkeeping to return, rather than deleting
            # its private database while finishing worker threads still use it.
            while queue._handles() and time.monotonic() < deadline:
                ready.wait(.01)
        conn = db.connect()
        counts = dict(conn.execute("SELECT state,COUNT(*) FROM study_runs GROUP BY state").fetchall())
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        ordered = sorted(starts)
        results.append({"offered_jobs":offered,"worker_cap":3,"peak_payload_workers":peak,
            "completed_unique":len(seen),"states":counts,"integrity":integrity,
            "elapsed_s":round(max(finishes),3),"cpu_s":round(time.process_time()-cpu0,3),
            "queue_wait_p50_s":round(ordered[len(ordered)//2],3),
            "queue_wait_p95_s":round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],3),
            "work_plus_finish_mean_s":round(sum(durations)/len(durations),4),
            "process_max_rss_mib":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2)})
        print(json.dumps(results[-1]),flush=True)
OUT.joinpath("queue-capacity.json").write_text(json.dumps({
    "scope":"real dispatcher and SQLite; 20ms simulated work; no real study pipeline, HTTP admission, quota, model, PDF or external call",
    "results":results},indent=2))
