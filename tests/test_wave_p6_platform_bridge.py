"""رسالة الفشل تقول الحقيقة وإعادةُ الإطلاق تستأنف — الموجة p6 (T10).

الفرع ب الحيّ: «اكتملت البعثات ولم يُنتِج الكاتب نصّ تقرير (آخر خطأ في طبقة
التحليل: ReadTimeout) — أُرجعت الحصة». المُرجَع كان **مقعد الإطلاق** في الباقة
لا المال؛ والدولارات الفعلية (بعثات + محلل) مسجَّلة في دفتر الاستخدام ولا
تُستردّ؛ و«آخر خطأ» كان يُقرأ من contextvar آخر نداء في الخيط (الكاتب/المراجع)
لا من طبقة التحليل؛ وإعادةُ الإطلاق الموصى بها كانت تشغيلةً كاملةً جديدة تعيد
دفع كلّ ما هو محفوظ.
العقد الجديد:
- `_empty_reason` يقرأ النتيجة نفسها (report.failure_reason/skip_reason/
  error_type/retryable + data_economics.cost_usd_estimate)، لا contextvar.
- الرسالة تقول: مقعد الإطلاق أُرجع، التكلفة الفعلية المسجَّلة X$ لا تُستردّ،
  البعثات والتحليل محفوظة، وإعادة الإطلاق تستأنف منها.
- `_finish_failure` يخزّن analysis_id على الدراسة حين حُفظت النتيجة.
- إعادة الإطلاق تمرّر `resume=<id>` للبوّابة حين يطابق المنتج والسوق المحفوظين.
هرمتي بالكامل. Run: python -m pytest tests/test_wave_p6_platform_bridge.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pytest.importorskip("fastapi")

from tests.platform_helpers import hdr, login, make_factory, seed, client  # noqa: E402


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    info = seed(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    cl = client()
    fac = make_factory("silver", "p6@f.local")
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


def _register_gateway(monkeypatch, run, ready=(True, "")):
    import silk_research_gateway as gw
    monkeypatch.setattr(gw, "_RUN", run)
    monkeypatch.setattr(gw, "_READINESS", lambda: ready)


def _branch_b_result(analysis_id: int, cost: float = 1.87) -> dict:
    """نتيجة الفرع ب: مكتملة بلا نصّ تقرير، المحلل فشل نداؤه، الكاتب تُخطّي."""
    return {"product": "تمور سكري", "hs_code": "080410", "markets": [],
            "deep_research": {
                "missions": {k: {"summary": "ok"} for k in ("a", "b")},
                "analyst": {"report": {"summary": "تعذّر نداء كلود (ReadTimeout)"}},
                "verdict": {"verdict": "WATCH"},
                "report": {"report": None, "review_cycles": 0,
                           "unresolved_notes": [],
                           "failure_reason": "فشل نداء كلود (ReadTimeout: read timed out)",
                           "skipped": "writer", "skip_reason": "analyst_call_failed",
                           "error_type": "ReadTimeout", "retryable": True}},
            "data_economics": {"cost_usd_estimate": cost, "llm_calls": 30},
            "analysis_id": analysis_id}


def _seed_research_run(product="تمور سكري", market="ARE") -> int:
    from silk_storage import create_research_run
    return create_research_run(product, market, "080410",
                               {"product": product, "market": market,
                                "hs_code": "080410"})


# ── الرسالة · the message ─────────────────────────────────────────────────────

def test_empty_reason_never_claims_money_returned():
    import silk_llm_provider as lp
    from silk_platform.engine_bridge import _empty_reason
    # خطأ آخر مزروع في contextvar — يجب ألا يُصدَّق (كان يُقرأ منه)
    lp._last_error.set({"type": "HTTPError", "message": "from the reviewer"})
    try:
        msg = _empty_reason(_branch_b_result(777, cost=1.87))
    finally:
        lp._last_error.set(None)
    assert "مقعد الإطلاق" in msg                      # ما أُرجع فعلاً
    assert "1.87" in msg and "لا تُستردّ" in msg      # التكلفة الفعلية المسجَّلة
    assert "ReadTimeout" in msg                       # الطبقة الفاشلة من النتيجة
    assert "HTTPError" not in msg                     # لا صدى لـcontextvar
    assert "777" in msg                               # معرّف التحليل المحفوظ
    assert "تستأنف" in msg or "استئناف" in msg        # إعادة الإطلاق لا تعيد البعثات
    assert "أُرجعت الحصة" not in msg                  # الصياغة القديمة الموهِمة


def test_empty_reason_marks_permanent_error_as_not_retryable():
    from silk_platform.engine_bridge import _empty_reason
    res = _branch_b_result(5)
    res["deep_research"]["report"].update(
        {"error_type": "HTTPError", "status_code": 400, "retryable": False,
         "failure_reason": "فشل نداء كلود (HTTPError: 400)"})
    msg = _empty_reason(res)
    assert "400" in msg and ("قبل إعادة الإطلاق" in msg or "لا تُعِد" in msg)


def test_empty_reason_non_deep_result_keeps_source_wording():
    from silk_platform.engine_bridge import _empty_reason
    msg = _empty_reason({"markets": []})
    assert "المصادر" in msg and "مقعد الإطلاق" in msg
    assert "أُرجعت الحصة" not in msg


# ── التخزين والاستئناف · storage + resume ────────────────────────────────────

def test_finish_failure_stores_analysis_id_and_releases_seat_once(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    aid = _seed_research_run()
    _register_gateway(monkeypatch, lambda **kw: _branch_b_result(aid))
    s = _mk_study(env["cl"], env["tok"], hs_code="080410", market_pref="ARE")
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    row = _study_row(s["id"])
    assert row["state"] == "draft"
    assert row["analysis_id"] == aid                  # المحفوظ يُشار إليه
    assert "مقعد الإطلاق" in (row["run_error"] or "")


def test_relaunch_passes_resume_when_study_has_prior_analysis(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    aid = _seed_research_run()
    calls: list[dict] = []

    def run(**kw):
        calls.append(dict(kw))
        return _branch_b_result(aid)

    _register_gateway(monkeypatch, run)
    s = _mk_study(env["cl"], env["tok"], hs_code="080410", market_pref="ARE")
    r1 = env["cl"].post(f"/platform/studies/{s['id']}/launch", headers=hdr(env["tok"]))
    assert r1.status_code == 200, r1.text
    assert eb.wait_idle()
    assert "resume" not in calls[0]                   # أول إطلاق — لا شيء يُستأنف
    r2 = env["cl"].post(f"/platform/studies/{s['id']}/launch", headers=hdr(env["tok"]))
    assert r2.status_code == 200, r2.text
    assert eb.wait_idle()
    assert calls[1].get("resume") == aid              # إعادة الإطلاق تستأنف المحفوظ
    assert calls[1]["product"] == "تمور سكري" and calls[1]["market"] == "ARE"


def test_relaunch_does_not_resume_when_market_changed(env, monkeypatch):
    import silk_platform.engine_bridge as eb
    aid = _seed_research_run(market="ARE")
    calls: list[dict] = []

    def run(**kw):
        calls.append(dict(kw))
        return _branch_b_result(aid)

    _register_gateway(monkeypatch, run)
    s = _mk_study(env["cl"], env["tok"], hs_code="080410", market_pref="ARE")
    env["cl"].post(f"/platform/studies/{s['id']}/launch", headers=hdr(env["tok"]))
    assert eb.wait_idle()
    # غيّر السوق على الدراسة ثم أعد الإطلاق — لا استئناف لتشغيلة سوقٍ آخر
    r = env["cl"].patch(f"/platform/studies/{s['id']}", json={"market_pref": "KWT"},
                        headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    env["cl"].post(f"/platform/studies/{s['id']}/launch", headers=hdr(env["tok"]))
    assert eb.wait_idle()
    assert "resume" not in calls[1]


def test_platform_deep_run_threads_resume_into_research_impl(monkeypatch, tmp_path):
    """المغلقة المسجَّلة (api._platform_deep_run) تمرّر resume إلى _research_impl:
    معرّف غير موجود ⇒ 404 resume_not_found من مسار /research نفسه (قبل أيّ
    بوّابة جهوزية أو نداء مدفوع) — دليل أن الوسيط وصل. تُستدعى المغلقة مباشرةً
    لأن `_resume_matches` في الجسر يرفض — بحقّ — معرّفاً غير موجود قبلها."""
    monkeypatch.setenv("SILK_DB", str(tmp_path / "engine.db"))
    import importlib
    import api as root_api
    importlib.reload(root_api)
    import silk_research_gateway as gw
    from silk_platform.engine_bridge import _runner_takes
    runner = gw.runner()
    assert runner is not None and _runner_takes(runner, "resume")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        runner(product="تمور سكري", market="ARE", hs_code="080410", resume=999999)
    assert ei.value.status_code == 404
    assert ei.value.detail["error"] == "resume_not_found"


def test_empty_run_without_saved_work_does_not_store_analysis_id(env, monkeypatch):
    """تمييزٌ لازم (تصحيح T10): تشغيلةٌ خرجت **بلا أيّ بيانات** لا يُربَط
    معرّفُها بالدراسة — لا عملَ يُستأنَف، وربطُه يُعلن معرّفاً بلا محتوى ويُغري
    إعادةَ إطلاقٍ تستأنف فراغاً (قفل test_platform_engine_honesty). الفرع ب
    (بعثاتٌ محفوظة بلا نصّ تقرير) يبقى مربوطاً — يُختبَر أعلاه."""
    import silk_platform.engine_bridge as eb
    aid = _seed_research_run()
    empty = {"classified": True, "analysis_id": aid,
             "markets": [{"country": "الإمارات", "total_score": 0.0,
                          "confidence": 0.0,
                          "components": {"market_size": {"value": None}}}]}
    _register_gateway(monkeypatch, lambda **kw: empty)
    s = _mk_study(env["cl"], env["tok"], hs_code="080410", market_pref="ARE")
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    row = _study_row(s["id"])
    assert row["state"] == "draft"
    assert row["analysis_id"] in (None, 0)
    assert "المصادر" in (row["run_error"] or "")
