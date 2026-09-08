"""أقفال R1 — الحواجز الحرجة (التدقيق الجنائي 2026-09-01، المرحلة ١، P0).

خمسة عيوب مؤكَّدة بمراجعة الشيفرة (file:line)، كلٌّ بقفلٍ أحمر قبل إصلاحه:
  (أ) كنس الأيتام كان يوسم الدراسة «مكتملة» لمجرّد أن `analysis_id` **مقروء**
      — صفّ محرّك `running`/`failed`/أقدم من محاولتها يكفي (RC-2، ENG-1)، وبلا
      إشعار في أيّ فرع.
  (ب) ثلاثة مجمّعات خيوط (`rank_markets`، `_enrich_research`، `run_market`)
      تُشغَّل بلا `contextvars.copy_context()` فتفقد العمّالُ صامتاً حجبَ إضافات
      كلود ولوحةَ الوكلاء وعدّادَ اقتصاد البيانات (RC-3، CONC-1).
  (ج) الإشعار كان داخل معاملة النجاح وبلا حماية — فشلُ `notifications.record`
      يصعد إلى `bridge_crash` فيقلب نجاحاً محفوظاً إلى فشلٍ مُسترَدّ الحصّة
      (RC-5، ENG-6).
  (د) خطأ 5xx من جسم `/research` كان يصل المصنع **حرفياً** (`reason` بالتتبّع
      والأسرار) عبر `DeepRunRefused` (ENG-4).
  (هـ) وسيط ETA كان يقرأ التشغيلات الفاشلة (مسودّة بمعرّف واستئناف) كأنها
      مكتملة (ENG-5).

هرمتي: المحرّك يُحاكى (`_run_engine`/بوّابة `silk_research_gateway`)، قاعدة
المحرّك معزولة (`SILK_DB` مؤقّت) فصفوف `analyses` حقيقية لا منسوخة. Hermetic.
"""
from __future__ import annotations

import contextvars
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import block_network
from tests.platform_helpers import (client, hdr, login, make_factory,
                                    mock_engine, seed)

pytest.importorskip("fastapi")

_STARTED = "2026-08-17T09:00:00+00:00"


@pytest.fixture()
def env(monkeypatch):
    """بذر + عميل + مصنع ذهبي (سقف ٦ شهرياً) — نفس عُدّة R2."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    info = seed(monkeypatch)
    cl = client()
    fac = make_factory("gold", "p0@f.local")
    tok = login(cl, fac["email"], fac["password"])
    return {"cl": cl, "fac": fac, "tok": tok, "info": info}


def _conn():
    from silk_platform import db as pdb
    return pdb.connect()


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


def _audit_actions(sid: int) -> list[str]:
    conn = _conn()
    try:
        return [r["action"] for r in conn.execute(
            "SELECT action FROM audit_log WHERE resource_type = 'study' "
            "AND resource_id = ? ORDER BY id", (str(sid),)).fetchall()]
    finally:
        conn.close()


# ── (أ) الكنس: مقروءٌ ≠ مكتمل ─────────────────────────────────────────────────
def _engine_run(status: str, updated_at: str | None = None) -> int:
    """صفّ تشغيلة محرّك حقيقي في القاعدة المعزولة بحالةٍ وختمِ تحديثٍ بعينه."""
    import silk_storage
    aid = silk_storage.create_research_run("تمور سكري", "ARE", "080410", {})
    if status != "running":
        silk_storage.update_research_status(aid, status)
    if updated_at is not None:
        with silk_storage._open(silk_storage._db_path()) as conn:
            conn.execute("UPDATE analyses SET updated_at = ? WHERE id = ?",
                         (updated_at, aid))
    return aid


def _orphan(conn, owner: int, user: int, analysis_id: int | None) -> int:
    conn.execute(
        "INSERT INTO studies (owner_id, product, state, analysis_id, launched_at, "
        "launched_by_user_id, run_started_at, created_at, updated_at) "
        "VALUES (?, 'تمور سكري', 'in_progress', ?, ?, ?, ?, '', '')",
        (owner, analysis_id, _STARTED, user, _STARTED))
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_sweeper_never_completes_a_study_on_a_non_completed_analysis(env):
    """صفّ محرّك `running`/`failed`/`completed` أقدم من محاولة الدراسة ⇒ تعود
    مسودّةً مع إرجاع الحصّة **وإشعار**؛ المكتمل الطازج وحده يُوسَم مكتملاً
    (بإشعار، وبلا اختلاق وقت انتهاء)."""
    import silk_platform.engine_bridge as eb
    from silk_platform import quota
    owner, user = env["fac"]["account_id"], env["fac"]["user_id"]
    running = _engine_run("running")
    failed = _engine_run("failed")
    stale = _engine_run("completed", updated_at="2026-08-17T08:00:00")
    fresh = _engine_run("completed")            # updated_at = الآن > المحاولة
    conn = _conn()
    try:
        ids = {name: _orphan(conn, owner, user, aid) for name, aid in
               (("running", running), ("failed", failed), ("stale", stale),
                ("fresh", fresh))}
        conn.execute("UPDATE accounts SET current_month_study_count = 4, "
                     "quota_period = ? WHERE id = ?",
                     (quota.current_period(), owner))
        conn.commit()
        swept = eb.sweep_orphans(conn)
    finally:
        conn.close()
    assert swept == {"completed": 1, "reverted": 3, "skipped": 0}
    for name in ("running", "failed", "stale"):
        row = _study_row(ids[name])
        assert row["state"] == "draft", name
        assert "إعادة نشر" in (row["run_error"] or ""), name
        kinds = [n["kind"] for n in _notifications(ids[name], owner)]
        assert "study_failed" in kinds, f"{name}: لا إشعار تعثّر من الكنس"
    done = _study_row(ids["fresh"])
    assert done["state"] == "completed"
    assert done["run_finished_at"] is None       # لا اختلاق وقت انتهاء
    assert "study_completed" in [n["kind"] for n in _notifications(ids["fresh"], owner)]
    assert _month_count(owner) == 1               # ثلاث حصص أُرجعت، واحدة بقيت


def test_sweeper_skips_when_the_engine_store_cannot_be_read(env, monkeypatch):
    """لا حكم بلا دليل: تعذُّر قراءة قاعدة المحرّك = تخطٍّ معلَن، لا مسودّة ولا مكتملة."""
    import silk_platform.engine_bridge as eb
    import silk_storage
    owner, user = env["fac"]["account_id"], env["fac"]["user_id"]
    aid = _engine_run("completed")
    conn = _conn()
    try:
        sid = _orphan(conn, owner, user, aid)
        conn.commit()

        def _boom(*_a, **_k):
            raise sqlite3.OperationalError("engine store unavailable for test")
        monkeypatch.setattr(silk_storage, "get_research_run", _boom)
        swept = eb.sweep_orphans(conn)
    finally:
        conn.close()
    assert swept == {"completed": 0, "reverted": 0, "skipped": 1}
    assert _study_row(sid)["state"] == "in_progress"


# ── (ب) المجمّعات تنسخ السياق في الأب ─────────────────────────────────────────
def test_context_helpers_snapshot_the_callers_context_per_item():
    """`map_with_context`/`submit_with_context`: كل عامل يرى قيمة الأب، ونسخته
    مستقلة (ضبطُ العامل لا يتسرّب للأب ولا لعاملٍ آخر)، والترتيب محفوظ."""
    import silk_context
    var: contextvars.ContextVar[str] = contextvars.ContextVar("r1_probe",
                                                                default="unset")
    var.set("parent")
    seen: list[str] = []
    lock = threading.Lock()

    def work(i: int) -> int:
        with lock:
            seen.append(var.get())
        var.set(f"worker-{i}")
        return i * 10

    with ThreadPoolExecutor(max_workers=3) as ex:
        out = list(silk_context.map_with_context(ex, work, range(5)))
    assert out == [0, 10, 20, 30, 40]
    assert seen == ["parent"] * 5, seen
    assert var.get() == "parent"
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut = silk_context.submit_with_context(ex, lambda: var.get())
    assert fut.result() == "parent"


def _probe():
    """لقطة ما يراه العامل من سياق الأب — (العدّاد نفسه؟، الحجب؟، maps مطفأ؟)."""
    import silk_context
    return (silk_context.data_counter(), silk_context.ai_extras_blocked(),
            silk_context.agent_enabled("maps"))


def test_rank_markets_workers_inherit_block_prefs_and_counter(monkeypatch):
    """`rank_markets` بالتوازي: كل سوق يرى حجبَ الإضافات وإطفاءَ maps **والعدّادَ
    نفسه** — فتُحتسَب نداءاته الحيّة في اقتصاد البيانات (كانت تضيع صامتة)."""
    import silk_context
    import silk_market_ranker as ranker
    real = ranker._gather_row
    seen: list = []

    def rec(hs_code, c, year):
        seen.append(_probe())
        return real(hs_code, c, year)
    monkeypatch.setattr(ranker, "_gather_row", rec)
    with block_network(), silk_context.block_ai_extras(), \
            silk_context.agent_prefs_context({"maps": {"on": False}}):
        counter = silk_context.begin_data_counter()
        ranker.rank_markets("080410", countries=[{"iso3": "ARE", "m49": "784"},
                                                 {"iso3": "EGY", "m49": "818"}])
    assert len(seen) == 2
    assert all(s == (counter, True, False) for s in seen), seen
    assert counter["live_fetches"] > 0, "نداءات العمّال الحيّة لم تُحتسَب"


def test_enrich_research_workers_inherit_the_callers_context(monkeypatch):
    """`_enrich_research` (سوقٌ لكل خيط): المنسّق يرى سياق الأب لا سياقاً فارغاً."""
    import silk_context
    import silk_engine
    import silk_research
    seen: list = []

    def fake_run_market(self, task):
        seen.append(_probe())
        return {"schema": "probe", "agents": {}, "coverage": 0.0,
                "pillar_inputs": {}}
    monkeypatch.setattr(silk_research.ResearchOrchestrator, "run_market",
                        fake_run_market)
    rows = [{"iso3": "ARE", "country": "الإمارات"}, {"iso3": "EGY", "country": "مصر"}]
    with block_network(), silk_context.block_ai_extras(), \
            silk_context.agent_prefs_context({"maps": {"on": False}}):
        counter = silk_context.begin_data_counter()
        silk_engine._enrich_research(rows, "تمور سكري", "080410", 2023, None)
    assert len(seen) == 2
    assert all(s == (counter, True, False) for s in seen), seen


def test_research_orchestrator_agents_inherit_the_callers_context():
    """`run_market` (وكيلٌ لكل خيط): الوكلاء الثمانية يرون حجبَ الإضافات ولوحةَ
    الوكلاء والعدّاد — البوّابة التي تمنع نداء كلود تعمل داخل العامل فعلاً."""
    import silk_context
    from silk_agents import AgentReport
    from silk_research import ResearchOrchestrator
    seen: list = []

    def _mk(name):
        class _Probe:
            AGENT = name

            def run(self, task, instruction=""):
                seen.append(_probe())
                return AgentReport(f"probe:{name}", [], False, "probe")
        return _Probe
    orch = ResearchOrchestrator(timeout=5, agent_classes=[_mk("market_size"),
                                                          _mk("competitor")])
    with block_network(), silk_context.block_ai_extras(), \
            silk_context.agent_prefs_context({"maps": {"on": False}}):
        counter = silk_context.begin_data_counter()
        out = orch.run_market({"product": "تمور", "hs6": "080410", "iso3": "ARE"})
    assert set(out["agents"]) == {"market_size", "competitor"}
    assert len(seen) == 2
    assert all(s == (counter, True, False) for s in seen), seen


# ── (ج) الإشعار لا يُبطل نجاحاً ولا يعلّق فشلاً ────────────────────────────────
def _break_notifications(monkeypatch):
    from silk_platform import notifications

    def _boom(*_a, **_k):
        raise sqlite3.OperationalError("no such table: platform_notifications")
    monkeypatch.setattr(notifications, "record", _boom)


def test_a_notification_failure_never_reverts_a_saved_success(env, monkeypatch):
    """`notifications.record` يرفع ⇒ الدراسة **مكتملة** بمعرّفها، الحصّة محفوظة،
    صفّ التشغيلة مغلق `completed`، وقيدُ تدقيق `notification_failed` يشهد."""
    _break_notifications(monkeypatch)
    eb = mock_engine(monkeypatch, analysis_id=4242)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert eb.wait_idle()
    row = _study_row(s["id"])
    assert row["state"] == "completed", row["run_error"]
    assert row["analysis_id"] == 4242
    assert _month_count(env["fac"]["account_id"]) == 1     # لا إرجاع حصّة
    assert _run_rows(s["id"])[-1]["state"] == "completed"
    actions = _audit_actions(s["id"])
    assert "study_run_completed" in actions
    assert "notification_failed" in actions, actions
    assert _notifications(s["id"], env["fac"]["account_id"]) == []


def test_a_notification_failure_never_leaves_a_failed_study_stuck(env, monkeypatch):
    """نفس العائلة على مسار الفشل: التعثّر يُحسَم (مسودّة + إرجاع + صفّ مغلق)
    ولو تعطّل الإشعار — لا «قيد الإعداد» أبدية."""
    _break_notifications(monkeypatch)
    eb = mock_engine(monkeypatch, analysis_id=4343, classified=False)
    s = _mk_study(env["cl"], env["tok"])
    _launch(env, s["id"])
    assert eb.wait_idle()
    row = _study_row(s["id"])
    assert row["state"] == "draft"
    assert "تصنيف" in (row["run_error"] or "")
    assert _month_count(env["fac"]["account_id"]) == 0     # أُرجعت
    assert _run_rows(s["id"])[-1]["state"] == "failed"
    actions = _audit_actions(s["id"])
    assert "study_run_failed" in actions
    assert "notification_failed" in actions, actions


# ── (د) الخطأ الداخلي يصل بالرمز لا بالنصّ ─────────────────────────────────────
def test_internal_engine_errors_reach_the_factory_redacted(env, monkeypatch):
    """500 `research_run_failed` بسببٍ يحمل تتبّعاً ومفتاحاً ⇒ `run_error` بلا
    `KeyError` ولا الرمز؛ رمز النهاية `engine_failed` (لا «رفض» بمرشّحين)؛
    الحصّة تُرجَع."""
    import silk_research_gateway as gw
    from fastapi import HTTPException

    def run(**_kw):
        raise HTTPException(status_code=500, detail={
            "error": "research_run_failed",
            "reason": "KeyError: 'sk-ant-x' at silk_research_pipeline.py:812"})
    monkeypatch.setattr(gw, "_RUN", run)
    monkeypatch.setattr(gw, "_READINESS", lambda: (True, ""))
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    import silk_platform.engine_bridge as eb
    s = _mk_study(env["cl"], env["tok"], market_pref="ARE")
    _launch(env, s["id"])
    assert eb.wait_idle()
    row = _study_row(s["id"])
    assert row["state"] == "draft"
    err = row["run_error"] or ""
    assert "KeyError" not in err and "sk-ant" not in err, err
    assert "silk_research_pipeline" not in err, err
    assert "عطل تقني" in err
    assert row["hs_candidates"] in (None, "", "[]")
    assert _run_rows(s["id"])[-1]["error_code"] == "engine_failed"
    assert _month_count(env["fac"]["account_id"]) == 0


# ── (هـ) ETA من المكتمل وحده ──────────────────────────────────────────────────
def test_eta_ignores_failed_runs_that_carry_an_analysis_pointer(env):
    """تشغيلة مكتملة ٩٠٠ ث + ثلاث فاشلات (مسودّة بمعرّف استئناف وختم انتهاء،
    ٢ ث) ⇒ الوسيط ٩٠٠ لا ٢."""
    import silk_platform.engine_bridge as eb
    owner = env["fac"]["account_id"]
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO studies (owner_id, state, analysis_id, run_started_at, "
            "run_finished_at, created_at, updated_at) VALUES (?, 'completed', 700, "
            "'2026-08-17T10:00:00+00:00', '2026-08-17T10:15:00+00:00', '', '')",
            (owner,))
        for i in range(3):
            conn.execute(
                "INSERT INTO studies (owner_id, state, analysis_id, run_started_at, "
                "run_finished_at, run_error, created_at, updated_at) "
                "VALUES (?, 'draft', ?, '2026-08-17T11:00:00+00:00', "
                "'2026-08-17T11:00:02+00:00', 'تعثّرت', '', '')",
                (owner, 710 + i))
        conn.commit()
        eta, basis = eb.eta_seconds(conn)
    finally:
        conn.close()
    assert (eta, basis) == (900, "measured_median")
