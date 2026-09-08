"""دورة حياة الدراسة — completed/archived transitions (post-pivot).

بعد حذف التنقيب (قرار مالك 2026-08-17): الاكتمال الطبيعي يكتبه جسر المحرّك،
و`complete` اليدوي مسار طوارئ لدراسة عالقة، و`archive` إخفاء نهائي — بلا أي
اقتران بطابور بريد (حُذف). عمود `state` خارج CRUD العام كما كان.
"""
import pytest

from platform_helpers import (client, hdr, login, make_factory,
                              make_product_study, mock_engine, seed)


def _study(account_id: int, user_id: int, state: str = "in_progress") -> int:
    """ملاحظة ترتيب: أنشئ `client()` **قبل** زرع دراسة in_progress — تركيبُ
    التطبيق يشغّل كنس الأيتام (سلوك إنتاجي صحيح) فيُعيد المزروعة يدوياً
    إلى draft لو سبقت التركيب."""
    return make_product_study(account_id, user_id, state=state)


def _state(account_id: int, study_id: int) -> str:
    from silk_platform import db as pdb, repository
    conn = pdb.connect()
    try:
        return repository.studies(conn).get(account_id, study_id)["state"]
    finally:
        conn.close()


# ═══════════════════════ الإنهاء اليدوي · manual complete ════════════════════
def test_complete_moves_in_progress_to_completed_and_stamps_the_time(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "lc-complete@example.com")
    cl = client()
    sid = _study(f["account_id"], f["user_id"])
    tok = login(cl, f["email"], f["password"])
    r = cl.post(f"/platform/studies/{sid}/complete", headers=hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "completed"
    assert body["completed_at"]


@pytest.mark.parametrize("state", ["draft", "completed", "archived"])
def test_complete_only_from_in_progress(monkeypatch, state):
    seed(monkeypatch)
    f = make_factory("gold", f"lc-only-{state}@example.com")
    cl = client()
    sid = _study(f["account_id"], f["user_id"], state)
    tok = login(cl, f["email"], f["password"])
    r = cl.post(f"/platform/studies/{sid}/complete", headers=hdr(tok))
    assert r.status_code == 409
    err = r.json()["detail"]["error"]
    assert err in ("invalid_transition", "already_archived")
    assert _state(f["account_id"], sid) == state


def test_manually_closed_study_has_no_report_and_says_so(monkeypatch):
    """إغلاق يدوي بلا نتيجة محرّك ⇒ لا تقرير، معلَناً (لا اختلاق «مكتملة» بتقرير)."""
    seed(monkeypatch)
    f = make_factory("gold", "lc-noreport@example.com")
    cl = client()
    sid = _study(f["account_id"], f["user_id"])
    tok = login(cl, f["email"], f["password"])
    assert cl.post(f"/platform/studies/{sid}/complete",
                   headers=hdr(tok)).status_code == 200
    r = cl.get(f"/platform/studies/{sid}/report", headers=hdr(tok))
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "no_report_yet"


# ═══════════════════════ الأرشفة · archive ═══════════════════════════════════
@pytest.mark.parametrize("state", ["draft", "in_progress", "completed"])
def test_archive_allowed_from_every_non_terminal_state(monkeypatch, state):
    seed(monkeypatch)
    f = make_factory("gold", f"lc-arch-{state}@example.com")
    cl = client()
    sid = _study(f["account_id"], f["user_id"], state)
    tok = login(cl, f["email"], f["password"])
    r = cl.post(f"/platform/studies/{sid}/archive", headers=hdr(tok))
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "archived"


def test_archiving_twice_is_refused_not_silently_repeated(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "lc-arch-twice@example.com")
    cl = client()
    sid = _study(f["account_id"], f["user_id"])
    tok = login(cl, f["email"], f["password"])
    assert cl.post(f"/platform/studies/{sid}/archive",
                   headers=hdr(tok)).status_code == 200
    r = cl.post(f"/platform/studies/{sid}/archive", headers=hdr(tok))
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "already_archived"


def test_an_archived_study_cannot_be_relaunched(monkeypatch):
    """الأرشفة تُغلق الإطلاق — الإطلاق يشترط draft فيرفض 409."""
    seed(monkeypatch)
    f = make_factory("gold", "lc-relaunch@example.com")
    sid = make_product_study(f["account_id"], f["user_id"])
    cl = client()
    tok = login(cl, f["email"], f["password"])
    assert cl.post(f"/platform/studies/{sid}/archive",
                   headers=hdr(tok)).status_code == 200
    r = cl.post(f"/platform/studies/{sid}/launch", headers=hdr(tok))
    assert r.status_code == 409, r.text
    assert _state(f["account_id"], sid) == "archived"


def test_archive_is_audited_with_the_source_state(monkeypatch):
    """الأرشفة مسجَّلة تدقيقاً بحالتها المصدر — سحبٌ قابل للمراجعة."""
    seed(monkeypatch)
    f = make_factory("gold", "lc-audit@example.com")
    cl = client()
    sid = _study(f["account_id"], f["user_id"])
    tok = login(cl, f["email"], f["password"])
    assert cl.post(f"/platform/studies/{sid}/archive",
                   headers=hdr(tok)).status_code == 200
    from silk_platform import audit, db as pdb
    conn = pdb.connect()
    try:
        rows = audit.search(conn, account_id=f["account_id"],
                            action="study_archived")
    finally:
        conn.close()
    assert rows and '"in_progress"' in (rows[0].get("changes") or "")


# ═════════════════ العزل والصلاحيات · isolation & roles ══════════════════════
@pytest.mark.parametrize("action", ["complete", "archive"])
def test_cannot_transition_another_tenants_study(monkeypatch, action):
    """دراسة حسابٍ آخر ⇒ 404 بلا تسريب وجود + تدقيق + بلا تغيير حالة."""
    seed(monkeypatch)
    a = make_factory("gold", f"lc-iso-a-{action}@example.com")
    b = make_factory("gold", f"lc-iso-b-{action}@example.com")
    cl = client()
    victim = _study(b["account_id"], b["user_id"])
    tok = login(cl, a["email"], a["password"])
    r = cl.post(f"/platform/studies/{victim}/{action}", headers=hdr(tok))
    assert r.status_code == 404
    assert _state(b["account_id"], victim) == "in_progress"
    from silk_platform import audit, db as pdb
    conn = pdb.connect()
    try:
        denied = audit.search(conn, account_id=a["account_id"],
                              action=f"cross_tenant_{action}")
    finally:
        conn.close()
    assert denied, "a cross-tenant transition attempt must be audit-logged"


@pytest.mark.parametrize("action", ["complete", "archive"])
def test_analyst_cannot_transition_a_study(monkeypatch, action):
    info = seed(monkeypatch)
    f = make_factory("gold", f"lc-analyst-{action}@example.com")
    cl = client()
    sid = _study(f["account_id"], f["user_id"])
    tok = login(cl, info["analyst"]["email"], info["analyst"]["password"])
    assert cl.post(f"/platform/studies/{sid}/{action}",
                   headers=hdr(tok)).status_code == 403
    assert _state(f["account_id"], sid) == "in_progress"


@pytest.mark.parametrize("action", ["complete", "archive"])
def test_transitions_require_authentication(monkeypatch, action):
    seed(monkeypatch)
    f = make_factory("gold", f"lc-noauth-{action}@example.com")
    cl = client()
    sid = _study(f["account_id"], f["user_id"])
    assert cl.post(f"/platform/studies/{sid}/{action}").status_code == 401


def test_state_is_not_writable_through_the_generic_patch(monkeypatch):
    """`state` خارج `_WRITABLE` — فلا يُتخطّى الانتقالُ بـPATCH عامّ.

    آلةُ الحالات لها بوّاباتها؛ عمودٌ قابل للكتابة عامّةً كان سيفتح باباً
    ثانياً يتخطّاها. (وأعمدة التشغيل analysis_id/run_* نظامية بنفس القاعدة.)
    """
    seed(monkeypatch)
    f = make_factory("gold", "lc-patch@example.com")
    cl = client()
    sid = _study(f["account_id"], f["user_id"])
    tok = login(cl, f["email"], f["password"])
    r = cl.patch(f"/platform/studies/{sid}", headers=hdr(tok),
                 json={"state": "completed", "analysis_id": 999,
                       "run_error": "x", "product": "زيتون"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product"] == "زيتون"             # المسموح طُبِّق
    assert body["analysis_id"] is None             # النظامي لم يُكتَب
    assert body["run_error"] is None
    assert _state(f["account_id"], sid) == "in_progress"   # الحالة لم تتغيّر
