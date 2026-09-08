"""أقفال الوضع العميق لدراسات المنصّة — deep-mode locks (قرار المالك 2026-08-18).

قرار المالك الحرفي («المنصّة لا تعمل... المحرك الأساسي يحتاج الى 15 دقيقة
عشان يعطيني دراسة»): دراسة المنصّة تشغّل جسم تشغيلة `/research` نفسه عبر
`silk_research_gateway` — لا `analyze` السريع. الأقفال هنا:

١) الافتراضي `deep`؛ `quick` صمّام صريح.
٢) بوابة الإطلاق ترفض معلَناً (503 engine_not_ready) حين لا بوابة مسجَّلة —
   **لا تدهور صامت إلى الوضع السريع أبداً**.
٣) دراسة عميقة بلا سوق مستهدفة تُرفَض (422 study_no_market_deep) قبل أي حجز.
٤) نجاح التشغيلة العميقة: اكتمال + analysis_id + `run_stats.mode=deep` +
   إشعار «اكتملت» في نفس المعاملة.
٥) رفض بوابات الجسم (HTTPException) = مسودّة بسبب عربي معلَن + إرجاع الحصّة
   + إشعار «تعثّرت» — لا اسم صنف استثناء في سطح المصنع.
٦) `result_is_substantive` لنتيجة عميقة: نص التقرير هو الجوهر.
٧) ETA لكل وضعٍ وسيطُه وافتراضُه — لا خلط ثوانٍ بدقائق.
٨) `api.create_app()` يسجّل البوابة فعلاً (مسار واحد، لا خط أنابيب موازٍ).

لا شبكة ولا مفاتيح — المغلقة تُحاكى عبر monkeypatch على وحدة البوابة.
"""
from __future__ import annotations

import json

import pytest

from tests.platform_helpers import hdr, login, make_factory, seed, client


@pytest.fixture()
def env(monkeypatch):
    """بذر + عميل + مصنع فضي، بوضع deep صريح (العُدّة تفترض quick)."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    info = seed(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    cl = client()
    fac = make_factory("silver", "deep@f.local")
    tok = login(cl, fac["email"], fac["password"])
    return {"cl": cl, "fac": fac, "tok": tok, "info": info}


def _mk_study(cl, tok, **over):
    body = {"product": "تمور سكري", **over}
    r = cl.post("/platform/studies", json=body, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


def _study_row(sid):
    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        return dict(conn.execute("SELECT * FROM studies WHERE id = ?",
                                 (sid,)).fetchone())
    finally:
        conn.close()


def _notifications(account_id):
    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM platform_notifications WHERE account_id = ? "
            "ORDER BY id", (account_id,)).fetchall()]
    finally:
        conn.close()


def _deep_result(analysis_id=901, report_text="# تقرير\n\nمحتوى حقيقي الشكل."):
    return {"product": "تمور سكري", "hs_code": "080410",
            "markets": [],
            "deep_research": {"missions": {}, "analyst": {},
                              "verdict": {"decision": "ادرس بعمق"},
                              "report": {"report": report_text,
                                         "review_cycles": 1}},
            "analysis_id": analysis_id}


def _register_gateway(monkeypatch, run, ready=(True, "")):
    import silk_research_gateway as gw
    monkeypatch.setattr(gw, "_RUN", run)
    monkeypatch.setattr(gw, "_READINESS", lambda: ready)


# ── ١) الافتراضي deep — the default is the real engine ──────────────────────
def test_default_mode_is_deep(monkeypatch):
    import silk_platform.engine_bridge as eb
    monkeypatch.delenv("SILK_PLATFORM_STUDY_MODE", raising=False)
    assert eb.study_mode() == "deep"
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "quick")
    assert eb.study_mode() == "quick"
    # قيمة مجهولة لا تُخترع وضعاً ثالثاً — تعود للافتراضي الصريح.
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "banana")
    assert eb.study_mode() == "deep"


# ── ٢) لا بوابة = رفض معلَن، لا تدهور صامت ───────────────────────────────────
def test_launch_without_gateway_is_refused_503_before_any_claim(env, monkeypatch):
    import silk_research_gateway as gw
    # عزل صريح: اختبار جذرٍ سابق في نفس الجلسة قد يكون سجّل البوابة عالمياً.
    monkeypatch.setattr(gw, "_RUN", None)
    monkeypatch.setattr(gw, "_READINESS", None)
    assert gw.runner() is None  # تطبيق منصّة معزول — لا تسجيل
    s = _mk_study(env["cl"], env["tok"], market_pref="ARE")
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "engine_not_ready"
    row = _study_row(s["id"])
    assert row["state"] == "draft"          # لا مطالبة، لا حصّة محروقة
    assert row["launched_at"] is None


# ── ٣) سوق مستهدفة إلزامية للعمق ─────────────────────────────────────────────
def test_deep_launch_requires_market(env, monkeypatch):
    _register_gateway(monkeypatch, lambda **kw: _deep_result())
    s = _mk_study(env["cl"], env["tok"])   # بلا market_pref
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "study_no_market_deep"
    assert _study_row(s["id"])["state"] == "draft"


# ── ٤) النجاح: اكتمال + mode=deep + إشعار ────────────────────────────────────
def test_deep_success_completes_with_mode_and_notification(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    calls = {}

    def run(**kw):
        calls.update(kw)
        return _deep_result(analysis_id=901)

    _register_gateway(monkeypatch, run)
    s = _mk_study(env["cl"], env["tok"], hs_code="080410", market_pref="ARE")
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    # الموجة ٠: لقطةُ لغة تقرير المصنع تصل جسم `/research` مع بقية المدخلات
    # — مصنعٌ لم يختر لغةً ⇒ «ar» (الافتراض الآمن، لا انقلابَ صامت).
    # الدرس ١٢٠: الجسر يُوسِم رمزَ الكتالوج بمصدره — فلا يُعامَل إجابةَ
    # مشغّلٍ حاضرة في بوّابات HS (حادثة الدراسة #10).
    assert calls == {"product": "تمور سكري", "market": "ARE",
                     "hs_code": "080410", "lang": "ar",
                     "hs_source": "catalog"}
    row = _study_row(s["id"])
    assert row["state"] == "completed"
    assert row["analysis_id"] == 901
    assert json.loads(row["run_stats"])["mode"] == "deep"
    kinds = [n["kind"] for n in _notifications(env["fac"]["account_id"])]
    assert "study_completed" in kinds


# ── ٥) رفض بوابات الجسم = سبب عربي معلَن + إرجاع الحصّة + إشعار ──────────────
def test_gate_refusal_reverts_with_declared_arabic_reason(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    from fastapi import HTTPException

    def run(**kw):
        raise HTTPException(status_code=409, detail={
            "error": "research_not_ready",
            "reason": "ANTHROPIC_API_KEY غير مضبوط — البحث العميق يتطلب كلود"})

    _register_gateway(monkeypatch, run)
    s = _mk_study(env["cl"], env["tok"], market_pref="ARE")
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 200
    assert eb.wait_idle()
    row = _study_row(s["id"])
    assert row["state"] == "draft"
    assert "ANTHROPIC_API_KEY" in row["run_error"]
    # لا رطانة أصناف استثناءات في سطح المصنع.
    assert "HTTPException" not in row["run_error"]
    assert "DeepRunRefused" not in row["run_error"]
    kinds = [n["kind"] for n in _notifications(env["fac"]["account_id"])]
    assert "study_failed" in kinds
    # الحصّة أُرجعت — إطلاق جديد ممكن (الفضية: دراستان/شهر).
    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        assert int(conn.execute(
            "SELECT current_month_study_count FROM accounts WHERE id = ?",
            (env["fac"]["account_id"],)).fetchone()[0]) == 0
    finally:
        conn.close()


# ── ٦) جوهر النتيجة العميقة هو نص التقرير ────────────────────────────────────
def test_substantive_deep_result_is_the_report_text():
    from silk_platform.engine_bridge import result_is_substantive
    assert result_is_substantive(_deep_result())
    empty = _deep_result(report_text="")
    assert not result_is_substantive(empty)
    no_report = {"markets": [], "deep_research": {"report": None}}
    assert not result_is_substantive(no_report)


def test_empty_deep_report_reverts_to_draft(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    _register_gateway(monkeypatch, lambda **kw: _deep_result(report_text=""))
    s = _mk_study(env["cl"], env["tok"], market_pref="ARE")
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 200
    assert eb.wait_idle()
    assert _study_row(s["id"])["state"] == "draft"


# ── ٧) ETA لكل وضع — no cross-mode median pollution ──────────────────────────
def test_eta_is_per_mode(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        # افتراض معلَن قبل أي قياس — deep يعرض 900 «تقديري» لا 240.
        monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
        eta, basis = eb.eta_seconds(conn)
        assert (eta, basis) == (900, "declared_default")
        # صفوف quick تاريخية (8ث) لا تلوّث وسيط deep.
        for i, dur_mode in enumerate([("quick", 8), ("deep", 880)] * 3):
            mode, dur = dur_mode
            conn.execute(
                "INSERT INTO studies (owner_id, title_en, state, analysis_id, "
                "run_started_at, run_finished_at, run_stats, created_at, "
                "updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (env["fac"]["account_id"], f"t{i}", "completed", 100 + i,
                 "2026-08-18T10:00:00", f"2026-08-18T10:{dur // 60:02d}:{dur % 60:02d}",
                 json.dumps({"mode": mode}), "2026-08-18T09:00:00",
                 "2026-08-18T10:20:00"))
        conn.commit()
        eta, basis = eb.eta_seconds(conn)
        assert basis == "measured_median"
        assert eta == 880
        monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "quick")
        eta_q, basis_q = eb.eta_seconds(conn)
        assert basis_q == "measured_median"
        assert eta_q == 8
    finally:
        conn.close()


# ── ٨) الجذر يسجّل البوابة فعلاً — one path, registered at boot ──────────────
def test_root_create_app_registers_the_gateway(monkeypatch, tmp_path):
    import silk_research_gateway as gw
    monkeypatch.setattr(gw, "_RUN", None)
    monkeypatch.setattr(gw, "_READINESS", None)
    monkeypatch.setenv("SILK_DB", str(tmp_path / "engine.db"))
    monkeypatch.setenv("SILK_PLATFORM_DB", str(tmp_path / "platform.db"))
    import api as root_api
    root_api.create_app()
    assert callable(gw.runner())
    # الجهوزية بلا مفتاح كلود = رفض معلَن يسمّي المتغيّر (نفس عقد /research).
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ready, reason = gw.readiness()
    assert ready is False
    assert "ANTHROPIC_API_KEY" in reason


def test_unregistered_gateway_readiness_declares_it():
    import silk_research_gateway as gw
    old_run, old_ready = gw._RUN, gw._READINESS
    try:
        gw.reset()
        ready, reason = gw.readiness()
        assert ready is False and "غير مسجَّل" in reason
    finally:
        gw._RUN, gw._READINESS = old_run, old_ready


# ── أقفال مراجعة §58 (موجة A) — the self-review locks ────────────────────────
def test_fake_valve_rejects_unknown_values_no_sample_leak(monkeypatch):
    """`SILK_PLATFORM_FAKE_ENGINE=0/false` ليست مقعداً — كانت أي قيمة غير
    فارغة تقدّم عيّنة مزيفة «مكتملة» في ثوانٍ على مسار إنتاجي (§58)."""
    import silk_platform.engine_bridge as eb
    import silk_research_gateway as gw
    monkeypatch.setattr(gw, "_RUN", None)
    monkeypatch.setattr(gw, "_READINESS", None)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    for bad in ("0", "false", "off", "banana"):
        monkeypatch.setenv("SILK_PLATFORM_FAKE_ENGINE", bad)
        assert not eb.fake_engine_enabled()
        # القيمة المجهولة لا تُفعّل المقعد: المسار العميق (بلا بوابة) يرفض
        # معلَناً — لا عيّنة مزيفة تعود من هنا أبداً.
        with pytest.raises(eb.DeepRunRefused):
            eb._run_engine("تمور", None, "ARE")


def test_run_stats_mode_is_the_executed_branch_not_env(env, monkeypatch):
    """مقعد وهمي تحت وضع deep يُوسَم `fake` لا `deep` — وسيط ETA «المقاس»
    للعميق لا يجوز أن يتلوث بعيّنة نصف ثانية (§58)."""
    import silk_platform.engine_bridge as eb
    monkeypatch.setenv("SILK_PLATFORM_FAKE_ENGINE", "1")
    assert eb.launch_mode() == "fake"
    s = _mk_study(env["cl"], env["tok"], market_pref="ARE")
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    row = _study_row(s["id"])
    assert row["state"] == "completed"
    assert json.loads(row["run_stats"])["mode"] == "fake"
    # ولا يدخل وسيطَ أي وضع حقيقي.
    assert eb._run_mode(row["run_stats"]) == "fake"


def test_orphan_grace_reads_the_row_mode_not_current_env(env, monkeypatch):
    """نافذة الكنس من ختم الصف: عميق حي في دقيقته الـ20 لا يُيتَّم حتى لو
    بُدّل الصمّام إلى quick أثناء تشغيله (§58)."""
    import datetime as dt
    import silk_platform.engine_bridge as eb
    from silk_platform import db as pdb
    started = (dt.datetime.now(dt.timezone.utc)
               - dt.timedelta(seconds=1200)).isoformat()
    conn = pdb.connect()
    try:
        for mode in ("deep", "quick"):
            conn.execute(
                "INSERT INTO studies (owner_id, title_en, state, product, "
                "run_started_at, run_stats, created_at, updated_at) "
                "VALUES (?,?, 'in_progress', 'تمور', ?, ?, ?, ?)",
                (env["fac"]["account_id"], f"orphan-{mode}", started,
                 json.dumps({"mode": mode}), started, started))
        conn.commit()
        monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "quick")
        out = eb.sweep_orphans(conn)
        assert out["reverted"] == 1     # السريع (900ث) وحده يُرجَع مسودّة
        assert out["skipped"] >= 1      # العميق (3600ث) داخل نافذته — لا حكم
        rows = {r["title_en"]: r["state"] for r in conn.execute(
            "SELECT title_en, state FROM studies "
            "WHERE title_en LIKE 'orphan-%'").fetchall()}
        assert rows == {"orphan-deep": "in_progress", "orphan-quick": "draft"}
    finally:
        conn.close()


def test_launch_claim_stamps_the_row_mode(env, monkeypatch):
    """ختم الوضع يُكتب مع المطالبة نفسها — قبل أي إنهاء (§58)."""
    import silk_platform.engine_bridge as eb

    def slow_run(**kw):
        return _deep_result()

    _register_gateway(monkeypatch, slow_run)
    s = _mk_study(env["cl"], env["tok"], market_pref="ARE")
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    # الختم بقي محمولاً في run_stats النهائية أيضاً (نفس الوضع المنفَّذ).
    assert json.loads(_study_row(s["id"])["run_stats"])["mode"] == "deep"


# ── مقعد deep الوهمي — the deep fake seam passes the honesty guards ──────────
def test_fake_engine_deep_seam_is_tagged_and_substantive(monkeypatch, tmp_path):
    import silk_platform.engine_bridge as eb
    monkeypatch.setenv("SILK_DB", str(tmp_path / "engine.db"))
    monkeypatch.setenv("SILK_PLATFORM_FAKE_ENGINE", "deep")
    assert eb.fake_engine_enabled()
    result = eb._run_engine("تمور", None, "ARE")
    assert result["analysis_id"]
    assert eb.result_is_substantive(result)
    assert "عيّنة اختبار" in result["note"]
    assert "عيّنة" in result["deep_research"]["report"]["report"]
