"""أقفال R3 — آلة حالة الدراسة وصدق الواجهة (التدقيق الجنائي 2026-09-01، المرحلة ٣).

لماذا هذا الملف: حالة الدراسة كانت تُقرأ من ثلاثة مصادر لا يلتقي منها اثنان
على الشاشة — `studies.state` رباعيّة القيم، `run_error` نصٌّ حرّ، و`study_runs`
(R2) الذي لا يبلغ الواجهة منه إلا «منتظرة/جارية». فتشغيلةٌ **انقطعت** بإعادة
نشر وتشغيلةٌ **تعثّرت** بعطل وتشغيلةٌ **أُلغيت** بيد المصنع كلّها «مسودّة»
بسطرٍ أحمر واحد؛ والإغلاق اليدوي لا يُشعِر؛ والجرس يقصّ السبب المعلَن عند ٥٠٠
حرف؛ و`/research/{id}/status` لا يقول هل ثمّة تقرير؛ والاستطلاع يضرب الخادم
من تبويبٍ مخفيّ ويبتلع 401 خارج `loadAll`.

هرمتي: قاعدة المنصّة والمحرّك معزولتان، المحرّك يُحاكى (`mock_engine`) أو يُقاد
بنداءات كلود مموَّهة (نمط `test_research_live_progress`). Hermetic only.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.platform_helpers import (client, hdr, login, make_factory,  # noqa: E402
                                    mock_engine, seed)

pytest.importorskip("fastapi")

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PAGE = _ROOT / "web" / "platform.html"


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    info = seed(monkeypatch)
    cl = client()
    fac = make_factory("gold", "r3@f.local")
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


def _study_row(sid: int) -> dict:
    conn = _conn()
    try:
        return dict(conn.execute("SELECT * FROM studies WHERE id = ?",
                                 (sid,)).fetchone())
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


def _vault_id() -> int:
    conn = _conn()
    try:
        return int(conn.execute(
            "SELECT id FROM accounts WHERE is_vault = 1 LIMIT 1").fetchone()[0])
    finally:
        conn.close()


def _insert_in_progress(owner: int, user: int, product: str = "تمور سكري") -> int:
    """صفٌّ «قيد الإعداد» **بلا** سجلّ تشغيلة — شكل ما قبل الترحيل 018."""
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO studies (owner_id, product, state, launched_at, "
            "launched_by_user_id, run_started_at, created_at, updated_at) "
            "VALUES (?, ?, 'in_progress', '2026-08-17T09:00:00+00:00', ?, "
            "'2026-08-17T09:00:00+00:00', '', '')", (owner, product, user))
        sid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.commit()
        return sid
    finally:
        conn.close()


def _close_study_with_run(sid: int, run_state: str, error_code: str,
                          run_error: str) -> None:
    """أنهِ دراسةً مسودّةً بصفّ `study_runs` منتهٍ بحالةٍ بعينها (كما يتركها الجسر)."""
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO study_runs (study_id, run_token, state, mode, params_json, "
            "created_at, started_at, finished_at, error_code, error_text) "
            "VALUES (?, ?, ?, 'quick', '{}', '2026-08-17T09:00:00+00:00', "
            "'2026-08-17T09:00:01+00:00', '2026-08-17T09:05:00+00:00', ?, ?)",
            (sid, f"tok-{sid}-{run_state}", run_state, error_code, run_error))
        conn.execute("UPDATE studies SET state = 'draft', run_error = ?, "
                     "launched_at = NULL WHERE id = ?", (run_error, sid))
        conn.commit()
    finally:
        conn.close()


# ── (١) الحذف لا يترك عملاً جارياً يتيماً — حتى بلا سجلّ تشغيلة ─────────────────
def test_delete_refuses_a_pre_018_in_progress_row_without_a_run_row(env):
    """صفٌّ «قيد الإعداد» بلا `study_runs` (قبل الترحيل 018) كان يُحذف بلا
    اعتراض — 409 `study_in_progress` معلَن، والصفّ باقٍ."""
    sid = _insert_in_progress(env["fac"]["account_id"], env["fac"]["user_id"])
    r = env["cl"].delete(f"/platform/studies/{sid}", headers=hdr(env["tok"]))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "study_in_progress"
    assert _study_row(sid)["state"] == "in_progress"


# ── (٢) آخر تشغيلة منتهية تُرفَق بالمسودّة — انقطعت/أُلغيت/تعثّرت متمايزة ─────────
def test_list_and_detail_carry_last_run_for_drafts_whose_last_attempt_ended(env):
    cl, tok = env["cl"], env["tok"]
    fresh = _mk_study(cl, tok)                       # لم تُطلَق قطّ
    cut = _mk_study(cl, tok)
    _close_study_with_run(cut["id"], "interrupted", "interrupted",
                          "انقطع التنفيذ بإعادة نشر — أعد الإطلاق")
    canc = _mk_study(cl, tok)
    _close_study_with_run(canc["id"], "cancelled", "cancelled", "أُلغيت بطلبك")
    rows = {r["id"]: r for r in cl.get("/platform/studies",
                                       headers=hdr(tok)).json()["studies"]}
    assert rows[fresh["id"]].get("last_run") is None
    assert rows[cut["id"]]["last_run"]["state"] == "interrupted"
    assert rows[cut["id"]]["last_run"]["error_code"] == "interrupted"
    assert rows[cut["id"]]["last_run"]["finished_at"]
    assert rows[canc["id"]]["last_run"]["state"] == "cancelled"
    one = cl.get(f"/platform/studies/{cut['id']}", headers=hdr(tok)).json()
    assert one["last_run"]["state"] == "interrupted"
    # لا تسريب سباكة: لا boot_id ولا params_json في الحمولة.
    assert not {"boot_id", "params_json"} & set(one["last_run"])


# ── (٣) كل انتقالٍ نهائي يُشعِر — الإغلاق اليدوي أيضاً ───────────────────────────
def test_manual_complete_writes_a_notification_for_the_factory_and_the_vault(env):
    owner = env["fac"]["account_id"]
    sid = _insert_in_progress(owner, env["fac"]["user_id"])
    r = env["cl"].post(f"/platform/studies/{sid}/complete", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert _study_row(sid)["state"] == "completed"
    mine = _notifications(sid, owner)
    assert [n["kind"] for n in mine] == ["study_completed"], mine
    assert "يدوياً" in mine[0]["title"]
    assert "بلا تقرير" in mine[0]["body"]          # لا اختلاق تقرير لإغلاقٍ يدوي
    vault = _notifications(sid, _vault_id())
    assert vault and vault[0]["kind"] == "study_completed"


def test_engine_success_writes_the_completion_notification(env, monkeypatch):
    """قفلٌ هرمتيّ لمسار النجاح السريع — كان محروساً بالمتصفّح وحده."""
    eb = mock_engine(monkeypatch, analysis_id=5150)
    s = _mk_study(env["cl"], env["tok"])
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    kinds = [n["kind"] for n in _notifications(s["id"], env["fac"]["account_id"])]
    assert kinds == ["study_completed"], kinds


def test_the_bell_carries_the_whole_declared_reason(env):
    """سبب تعثّرٍ بطول `_REASON_MAX` (١٠٠٠) يصل الجرس كاملاً — كان يُقصّ عند ٥٠٠."""
    from silk_platform import notifications
    from silk_platform.engine_bridge import _REASON_MAX
    body = "س" * _REASON_MAX
    conn = _conn()
    try:
        nid = notifications.record(conn, account_id=env["fac"]["account_id"],
                                   kind="study_failed", title="ت", body=body)
        conn.commit()
        stored = conn.execute("SELECT body FROM platform_notifications WHERE id = ?",
                              (nid,)).fetchone()[0]
    finally:
        conn.close()
    assert len(stored) == _REASON_MAX


# ── (٤) `/research/{id}/status` يقول هل ثمّة تقرير ولماذا لا ────────────────────
def _root_client():
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


def _seed_run(db: str, *, product="تمور", market="Nigeria", iso3="NGA") -> int:
    import silk_storage
    return silk_storage.create_research_run(
        product, iso3, "080410",
        {"product": product, "market": market, "market_iso3": iso3,
         "hs_code": "080410"}, path=db)


def test_status_reports_report_presence_degradation_and_skip_reason():
    import silk_storage
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with patch.dict(os.environ, {"SILK_API_KEY": "secret"}), \
         patch("silk_storage._db_path", return_value=db):
        cl = _root_client()
        h = {"X-API-Key": "secret"}
        running = _seed_run(db)
        done = _seed_run(db)
        silk_storage.save_analysis(
            {"product": "تمور", "hs_code": "080410", "markets": [],
             "deep_research": {"missions": {}, "report": {"report": "نصّ التقرير"}}},
            path=db, analysis_id=done)
        partial = _seed_run(db)
        silk_storage.save_analysis(
            {"product": "تمور", "hs_code": "080410", "markets": [],
             "deep_research": {"missions": {"m": {}}, "report": {"report": ""}}},
            path=db, analysis_id=partial)
        failed = _seed_run(db)
        silk_storage.mark_research_failed(failed, "الكاتب فشل: مهلة الكتابة", path=db)

        st = cl.get(f"/research/{running}/status", headers=h).json()
        assert (st["status"], st["report_present"], st["degraded"],
                st["skip_reason"]) == ("running", False, False, None)
        st = cl.get(f"/research/{done}/status", headers=h).json()
        assert (st["status"], st["report_present"], st["degraded"]) == (
            "completed", True, False)
        st = cl.get(f"/research/{partial}/status", headers=h).json()
        assert (st["status"], st["report_present"], st["degraded"]) == (
            "completed", False, True)
        st = cl.get(f"/research/{failed}/status", headers=h).json()
        assert st["status"] == "failed" and st["report_present"] is False
        assert "مهلة" in (st["skip_reason"] or "")


def _fake_call_tools_factory(probe):
    def fake_call_tools(system, messages, tools=None, max_tokens=1600,
                        model=None, timeout=None):
        probe()
        return {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": json.dumps(
                {"findings": [], "gaps": [], "summary": "ok"})}],
            "usage": {"input_tokens": 100, "output_tokens": 50}}
    return fake_call_tools


def _fake_call(system, user, max_tokens=1600, model=None, timeout=None):
    return json.dumps({"verdict": "WATCH", "confidence": 0.5, "reasoning": "ok"})


def _fake_call_writer(system, user, max_tokens=1600, model=None, timeout=None):
    return "## 1. الخلاصة التنفيذية\nتقرير تجريبي كامل."


def test_resume_marks_the_run_running_before_re_executing():
    """استئنافُ تشغيلة فاشلة يُعيدها `running` قبل أوّل بعثة — كان المستطلِع
    يقرأ `failed` طوال إعادة التنفيذ ثم `completed` فجأة."""
    import silk_storage
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    seen: list[str] = []

    def probe():
        # البعثات تعمل بالتوازي — أكثر من خيط قد يسجّل؛ المهمّ ما رآه كلٌّ منها.
        seen.append(silk_storage.get_research_run(aid, path=db)["status"])

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test",
                                 "SILK_API_KEY": "secret"}), \
         patch("silk_llm_runtime._call_tools",
               side_effect=_fake_call_tools_factory(probe)), \
         patch("silk_synthesis._call", side_effect=_fake_call), \
         patch("silk_ai_judge._call", side_effect=_fake_call_writer), \
         patch("silk_storage._db_path", return_value=db):
        aid = _seed_run(db)
        silk_storage.mark_research_failed(aid, "انقطعت قبل البعثات", path=db)
        cl = _root_client()
        r = cl.post("/research", headers={"X-API-Key": "secret"},
                    json={"resume": aid, "persist": True})
        assert r.status_code == 200, r.text
    assert seen and set(seen) == {"running"}, seen
    assert silk_storage.get_research_run(aid, path=db)["status"] == "completed"


# ── (٥) الصفحة: حالة واحدة لا لبس فيها، 401 مركزيّ، لا استطلاع من تبويب مخفيّ ────
def _without_comments(src: str) -> str:
    src = re.sub(r"<!--.*?-->", " ", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


def _fn_body(html: str, name: str) -> str:
    m = re.search(rf"function {re.escape(name)}\((.*?)\n\}}", html, re.S)
    assert m, f"الدالة {name} غائبة عن الصفحة"
    return m.group(0)


@pytest.fixture(scope="module")
def html() -> str:
    return _PAGE.read_text(encoding="utf-8")


def test_page_derives_one_unambiguous_chip_per_study(html):
    """مشتقٌّ واحد يقرأ المصادر الثلاثة ويميّز النهايات — لا «مسودّة» تبتلع
    الانقطاع والإلغاء والتعثّر في سطرٍ أحمر واحد."""
    # المشتقُّ زوجٌ: `studyBucket` يسمّي الدلو و`studyChip` يترجمه للعين.
    body = (_without_comments(_fn_body(html, "studyBucket"))
            + _without_comments(_fn_body(html, "studyChip")))
    assert "last_run" in body and "run_error" in body and "queued" in body
    assert "RUN_STATE_AR" in body, "الشريحة لا تقرأ تسميات حالات التشغيلة"
    for key in ("interrupted", "cancelled"):
        assert key in body, f"الشريحة لا تميّز `{key}` عن التعثّر العامّ"
    page = _without_comments(html)
    for label in ("تعثّرت", "انقطعت", "أُلغيت", "في الانتظار"):
        assert label in page, f"الصفحة بلا تسمية «{label}»"
    # الجداول الثلاثة تمرّ بالمشتقّ الواحد — لا نسخة ثانية من منطق الحالة.
    assert html.count("studyChip(") >= 4, "الجداول لا تستعمل المشتقّ الواحد"
    assert re.search(r"(?<![\w])study_in_progress\s*:", html), (
        "كود 409 الجديد بلا رسالة عربية")


def test_run_states_of_migration_018_all_have_a_visitor_label(html):
    migration = (_ROOT / "migrations" / "platform" / "018_study_runs.sql"
                 ).read_text(encoding="utf-8")
    m = re.search(r"CHECK \(state IN \(([^)]+)\)", migration)
    assert m
    states = [s.strip().strip("'") for s in m.group(1).replace("\n", "").split(",")]
    assert len(states) == 6
    for st in states:
        assert re.search(rf"RUN_STATE_AR\s*=\s*\{{[^}}]*\b{st}\b", html, re.S), (
            f"حالة تشغيلة `{st}` بلا تسمية زائر في الصفحة")


def test_page_centralises_401_and_pauses_polling_when_hidden(html):
    api_fn = _without_comments(_fn_body(html, "api"))
    assert "401" in api_fn and "doLogout" in api_fn, "401 غير مركزيّ في api()"
    assert "/auth/logout" in api_fn, "حارس التكرار: لا خروجَ على فشل الخروج نفسه"
    poll = _without_comments(_fn_body(html, "_syncStudyPoll"))
    assert "document.hidden" in poll, "الاستطلاع يضرب الخادم من تبويبٍ مخفيّ"
    assert "visibilitychange" in _without_comments(html), (
        "لا تحديث فوريّ عند عودة التبويب")


def test_admin_failure_cell_is_bounded_and_keeps_the_whole_reason_in_the_tooltip(html):
    """سببُ الفشل صار يصل ١٠٠٠ حرفاً (BODY_MAX) — خليّةٌ بلا حدٍّ تمطّ صفَّ
    الجدول وتدفع بقيةَ الأعمدة خارج الشاشة. القصُّ عرضٌ لا فقدان: النصّ
    كاملاً في `title`."""
    body = _without_comments(_fn_body(html, "renderAdminStudies"))
    held = re.search(r"(?:const|let)\s+(\w+)\s*=\s*s\.run_error[^;]*;", body)
    assert held, "خليّة فشل الأدمِن لا تمسك السبب في متغيّر قابل للقصّ"
    var = held.group(1)
    cut = re.search(rf"{re.escape(var)}\.slice\(\s*0\s*,\s*(\d+)\s*\)", body)
    assert cut, "خليّة فشل الأدمِن بلا حدٍّ للعرض"
    assert int(cut.group(1)) == 120, f"حدُّ العرض {cut.group(1)} لا ١٢٠"
    assert re.search(rf"\.title\s*=\s*{re.escape(var)}\s*;", body), (
        "النصّ الكامل لا يصل المستخدم — لا `title` بالسبب كاملاً على الخليّة")


def test_rung3_flow_carries_the_two_new_browser_steps_and_declares_the_skip():
    """قفلٌ بنيويّ لرُتبة ٣: الخطوتان الجديدتان موجودتان، والبذرُ موصولٌ من
    بايثون إلى العقدة، وغيابُ البذر **يُعلَن** تخطّياً لا يمرّ صامتاً."""
    flow = (_ROOT / "tests" / "e2e" / "platform_flow.cjs").read_text(encoding="utf-8")
    for step in ("interrupted_chip_visible", "expired_session_returns_to_login"):
        assert f'ok("{step}"' in flow, f"خطوة رُتبة ٣ «{step}» غائبة"
        assert f'fail("{step}"' in flow, f"«{step}» بلا فشلٍ معلَن — نجاحٌ بلا فحص"
    assert 'SKIP interrupted_chip_visible' in flow, "تخطٍّ صامت بلا بذر"
    assert "انقطعت" in flow, "التدفّق لا يفحص التسمية نفسها"

    runner = (_ROOT / "tests" / "test_rung3_playwright_e2e.py").read_text(encoding="utf-8")
    assert 'SILK_LIVE_SHAPE_SEED_INTERRUPTED' in runner, "البذر غير مطلوب من بايثون"
    assert 'SEED_INTERRUPTED="1"' in runner, "العلَم لا يصل سكربت العقدة"

    server = (_ROOT / "tools" / "live_shape_server.py").read_text(encoding="utf-8")
    assert "_seed_interrupted_study" in server, "الخادم الحيّ لا يبذر المنقطعة"
    assert "'interrupted'" in server, "الصفُّ المبذور ليس `interrupted`"
    # اسمُ المنتج مصدرٌ واحد يقرؤه الطرفان — لا سلسلتان تنحرفان.
    import re as _re
    m = _re.search(r'INTERRUPTED_PRODUCT\s*=\s*"([^"]+)"', server)
    assert m, "لا اسمَ معلَناً للدراسة المبذورة"
    assert m.group(1) in flow, "اسمُ المنتج في التدفّق يخالف ما يبذره الخادم"


def test_the_three_endings_differ_in_tone_not_only_in_words(html):
    """هدفُ R3 أن تُميَّز النهايات — فلا تكفي كلماتٌ ثلاث بلونٍ واحد. «تعثّرت»
    عطلٌ (`bad`، وهو ما تنصّ عليه الخطة)، «انقطعت» قابلةٌ للاستئناف بإطلاقٍ
    جديد (`warn`)، «أُلغيت» فعلُ المصنع نفسه (محايد). ثلاثةُ أصنافٍ متمايزة
    كلُّها معرَّفٌ في CSS الصفحة — لا صنفَ مخترَع بلا لون."""
    m = re.search(r"RUN_STATE_PILL\s*=\s*\{(.*?)\}", html, re.S)
    assert m, "لا خريطةَ ألوانٍ لحالات التشغيلة"
    tones = dict(re.findall(r"(\w+)\s*:\s*\"(\w+)\"", m.group(1)))
    assert tones.get("failed") == "bad", f"«تعثّرت» بلون {tones.get('failed')}"
    ends = [tones.get(k) for k in ("failed", "interrupted", "cancelled")]
    assert len(set(ends)) == 3, f"النهاياتُ الثلاث بلونين أو أقلّ: {ends}"
    for tone in set(tones.values()):
        assert re.search(rf"\.pill\.{tone}\s*\{{", html), (
            f"الصنف `pill {tone}` بلا تعريفٍ في CSS الصفحة")


def test_no_stray_control_characters_in_the_browser_flow():
    """قفلُ نظافة: محرفُ تحكّمٍ منفلت (0x08 مكان `\b`) داخل نمطٍ منتظم يقلبه
    صامتاً — الفحصُ يمرّ أو يسقط لسببٍ خاطئ ولا شيء في الشيفرة يبدو معطوباً.
    رُصد حيّاً 2026-09-03 على فحص لون الشريحة."""
    raw = (_ROOT / "tests" / "e2e" / "platform_flow.cjs").read_text(encoding="utf-8")
    bad = [(i + 1, repr(ln)[:70]) for i, ln in enumerate(raw.splitlines())
           if any(ord(c) < 32 and c != "	" for c in ln)]
    assert not bad, f"محارف تحكّم في تدفّق المتصفّح: {bad[:3]}"


# ── فجوات R3 الثلاث التي أغفلتها الخطة (تدقيق §28 R3: FE-3 «رقاقة»، FE-4، خطوة ٥) ──
def test_the_filter_buckets_come_from_the_same_derivation_as_the_chip(html):
    """FE-3 غيرُ مغلقٍ بشريحةٍ وحدها: مرشِّحُ الحالة كان أربعَ حالاتٍ خامٍ، فمن
    يرشّح «مسودّة» يرى المتعثّرة والمنقطعة والملغاة مختلطةً بمن لم تُطلَق قطّ —
    عينُ الالتباس الذي وُجدت R3 لإزالته. المصدرُ **واحد**: `studyBucket`."""
    page = _without_comments(html)
    bucket = _fn_body(page, "studyBucket")
    assert "last_run" in bucket and "run_error" in bucket, (
        "المشتقُّ لا يقرأ مصادر النهاية")
    chip = _without_comments(_fn_body(page, "studyChip"))
    assert "studyBucket(" in chip, "الشريحة لا تُبنى على المشتقّ الواحد"
    chips_fn = _without_comments(_fn_body(page, "renderStudyChips"))
    assert "studyBucket(" in chips_fn, "رقاقاتُ المرشِّح ما تزال على الحالة الخام"
    match_fn = _without_comments(_fn_body(page, "studyMatches"))
    assert "studyBucket(" in match_fn, "المطابقةُ ما تزال على الحالة الخام"
    # البحثُ يجد الدراسة بالكلمة التي تراها العين على شريحتها.
    assert "studyChip(" in match_fn or "studyBucket(" in match_fn


def test_a_run_past_the_sweep_grace_says_the_platform_will_reset_it(html):
    """FE-4: «تجاوزت المدة المعتادة» لا تقول ما الذي سيحدث — والعميل لا يعرف
    نافذة السماح أصلاً. الخادمُ يرسلها (`grace_s`) **فقط** حين يكون الكنسُ
    مفعَّلاً، فالوعدُ بالتعافي لا يُقال إلا حين يكون صادقاً."""
    dur = _without_comments(_fn_body(html, "_durText"))
    assert "grace_s" in dur, "نصُّ المدة لا يقرأ نافذة السماح"
    page = _without_comments(html)
    assert "ستُعيدها المنصّة" in page, "لا إشارةَ توقّفٍ تقول ما سيحدث"
    api_src = (_ROOT / "silk_platform" / "api.py").read_text(encoding="utf-8")
    assert '"grace_s"' in api_src, "الخادم لا يعلن نافذة السماح"
    assert "sweeper_enabled" in api_src, (
        "الوعدُ يُرسَل حتى مع كنسٍ معطَّل — ادّعاءٌ لا يسنده شيء")


def test_a_stuck_in_progress_row_has_a_way_out_on_the_screen(html):
    """خطوة ٥ في §28 R3 + FE-21: الخادم يسمح بأرشفة `in_progress` (`ARCHIVE_FROM`)
    ويرفعها 409 `study_running` إن كانت التشغيلة نشطةً فعلاً — أي أن الأرشفة
    **هي** مخرجُ الصفّ العالق. والشاشة كانت تخفيها عن `in_progress` حصراً،
    فيبقى صاحبُ الصفّ بين حذفٍ مرفوض وإلغاءٍ يردّ «لا تشغيلة جارية»."""
    body = _without_comments(_fn_body(html, "renderStudyRows"))
    assert 'actBtn(ar_en("أرشفة"' in body, "جدولُ الدراسات بلا أرشفة"
    # لم تعد الأرشفة محجوبةً عن «قيد الإعداد» — الخادم هو من يقرّر بـ409.
    assert not re.search(r'state !== "archived" && s\.state !== "in_progress"', body), (
        "الأرشفة ما تزال محجوبةً عن الصفّ العالق")
    lifecycle_src = (_ROOT / "silk_platform" / "lifecycle.py").read_text(encoding="utf-8")
    assert '"in_progress"' in lifecycle_src.split("ARCHIVE_FROM")[1][:80], (
        "الخادم لم يعد يسمح بأرشفة `in_progress` — الافتراض سقط")
