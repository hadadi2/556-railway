"""حصّة الدراسات لكل مستخدم — per-user study quota (قرار مالك 2026-08-17).

طلب المالك حرفياً: «أريد الأدمِن يحدد عدد الدراسات لكل مستخدم بناءً على الباقة
أو الاشتراك». قبل هذه الموجة كانت الحصّة على مستوى الحساب فقط
(`accounts.current_month_study_count`) بلا أي سبيل لسقفٍ لكل مستخدم، والأدمِن
لا يملك إلا تبديل الطبقة.

الأقفال هنا هرمتية بالكامل (قاعدة منصّة معزولة، لا شبكة، لا مفاتيح) وتغطي:
العقد الافتراضي (لا تغيير سلوك بلا ضبط)، الإنفاذ، التعويض (ختم المُطلِق يُمسَح
عند رفض الحجز فلا تُحتسَب دراسة لم تنطلق)، نقطة الأدمِن، الرسالة العربية،
والتزامن (الدرس ٧٦: لا قبول فوق السقف تحت أي تداخل).
"""
from __future__ import annotations

import threading

import pytest

from tests.platform_helpers import (client, hdr, login, make_factory,
                                    make_product_study, mock_engine, seed)


def _launch(cl, tok, account):
    """أنشئ دراسة سوق مسودّة وأطلقها — يعيد (status, body, study_id).

    (بعد حذف التنقيب: لا SMTP ولا نصّ رسالة — دراسة منتجٍ تكفي للإطلاق.)"""
    sid = make_product_study(account["account_id"], account["user_id"])
    r = cl.post(f"/platform/studies/{sid}/launch", headers=hdr(tok), json={})
    return r.status_code, r.json() if r.content else {}, sid


def _set_quota(cl, admin_tok, account_id, value):
    return cl.post(f"/platform/admin/accounts/{account_id}/quota",
                   headers=hdr(admin_tok),
                   json={"per_user_monthly_studies": value})


# ═══════════ العقد الافتراضي: لا ضبط = لا تغيير سلوك ═══════════════════════
def test_default_is_uncapped_account_quota_alone_governs(monkeypatch):
    """بلا تجاوز أدمِن، حساب silver يطلق دراستيه الشهريتين بمستخدم واحد.

    افتراض كل الطبقات `per_user_monthly_studies=0` (بلا حدّ) عمداً — تغيير
    الأرقام الفعلية قرار تسعير يملكه المالك، فالميزة تُشحَن بلا أثر حتى يضبطها.
    """
    seed(monkeypatch)
    f = make_factory("silver", "uq-default@example.com")
    mock_engine(monkeypatch)
    cl = client()
    tok = login(cl, f["email"], f["password"])
    for _ in range(2):
        code, body, _sid = _launch(cl, tok, f)
        assert code == 200, body
    # الثالثة تُرفَض بحصّة **الحساب** (سقف silver الشهري 2) لا حصّة المستخدم.
    code, body, _sid = _launch(cl, tok, f)
    assert code == 403
    assert body["detail"]["reason"] == "monthly_quota_exceeded"


def test_entitlements_expose_the_per_user_fields(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "uq-ent@example.com")
    mock_engine(monkeypatch)
    cl = client()
    tok = login(cl, f["email"], f["password"])
    ent = cl.get("/platform/entitlements", headers=hdr(tok)).json()
    assert ent["per_user_studies_limit"] == 0      # بلا حدّ افتراضاً
    assert ent["per_user_studies_used"] == 0
    _launch(cl, tok, f)
    ent = cl.get("/platform/entitlements", headers=hdr(tok)).json()
    assert ent["per_user_studies_used"] == 1       # يعدّ إطلاقات المنادي نفسه


# ═══════════ الإنفاذ والتعويض ═══════════════════════════════════════════════
def test_admin_cap_blocks_the_over_cap_launch_with_arabic_ready_detail(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("gold", "uq-cap@example.com")
    mock_engine(monkeypatch)
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    r = _set_quota(cl, admin, f["account_id"], 1)
    assert r.status_code == 200 and r.json()["effective_limit"] == 1

    tok = login(cl, f["email"], f["password"])
    code, body, _sid = _launch(cl, tok, f)
    assert code == 200, body
    code, body, sid2 = _launch(cl, tok, f)
    assert code == 403
    d = body["detail"]
    assert d["reason"] == "user_quota_exceeded"
    assert d["user_limit"] == 1 and d["user_used"] == 1
    # سقف المستخدم قرار أدمِن الحساب لا الطبقة — لا دعوة ترقية مضلِّلة.
    assert d["upgrade"] is False

    # التعويض: الدراسة عادت مسودّةً وخُتمُ المُطلِق مُسِح — لا تُحتسَب أبداً.
    st = cl.get(f"/platform/studies/{sid2}", headers=hdr(tok)).json()
    assert st["state"] == "draft"
    assert st["launched_at"] is None
    assert st["launched_by_user_id"] is None
    # وعدّاد الحساب لم يُحرَق برفض حصّة المستخدم (يزيد فقط بعد عبورها).
    ent = cl.get("/platform/entitlements", headers=hdr(tok)).json()
    assert ent["studies_used"] == 1
    assert ent["per_user_studies_used"] == 1


def test_a_second_user_of_the_same_account_has_their_own_cap(monkeypatch):
    """الحدّ لكل مستخدم لا لكل حساب — زميلٌ آخر يطلق ضمن حدّه هو."""
    info = seed(monkeypatch)
    f = make_factory("gold", "uq-two@example.com")
    mock_engine(monkeypatch)
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    _set_quota(cl, admin, f["account_id"], 1)

    tok = login(cl, f["email"], f["password"])
    assert _launch(cl, tok, f)[0] == 200
    assert _launch(cl, tok, f)[0] == 403          # المالك استهلك حدّه

    # الزميلُ يُدرَج مباشرةً في القاعدة: مسارُ المستخدمين الفرعيين حُذف مع
    # المقاعد (قرار المالك 2026-08-19)، والحدُّ لكل مستخدم مفهومٌ مستقلٌّ عنه
    # ويبقى مُختبَراً — الصفُّ الثاني يمثّل مستخدماً موجوداً في القاعدة.
    from silk_platform import db as pdb, passwords
    from silk_platform.db import now_iso
    conn = pdb.connect()
    try:
        now = now_iso()
        cur = conn.execute(
            "INSERT INTO users (account_id, email, password_hash, role, "
            "first_name, last_name, language_preference, created_at, updated_at)"
            " VALUES (?,?,?, 'factory', 'C', 'Colleague', 'ar', ?, ?)",
            (f["account_id"], "uq-two-b@example.com",
             passwords.hash_password("Factory1234"), now, now))
        uid2 = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()
    tok2 = login(cl, "uq-two-b@example.com", "Factory1234")
    sid = make_product_study(f["account_id"], uid2)
    r2 = cl.post(f"/platform/studies/{sid}/launch", headers=hdr(tok2), json={})
    assert r2.status_code == 200, r2.text          # حدّه الشخصي لم يُستهلك


def test_zero_means_uncapped_and_null_clears_to_tier_default(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("gold", "uq-clear@example.com")
    mock_engine(monkeypatch)
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    _set_quota(cl, admin, f["account_id"], 1)
    tok = login(cl, f["email"], f["password"])
    assert _launch(cl, tok, f)[0] == 200
    assert _launch(cl, tok, f)[0] == 403
    # `0` = بلا حدٍّ صراحةً ⇒ ينفتح الإطلاق (ضمن حصّة الحساب).
    assert _set_quota(cl, admin, f["account_id"], 0).status_code == 200
    assert _launch(cl, tok, f)[0] == 200
    # `null` يمسح التجاوز ويعود افتراض الطبقة (0 اليوم = بلا حدّ أيضاً).
    r = _set_quota(cl, admin, f["account_id"], None)
    assert r.status_code == 200
    assert r.json()["per_user_monthly_studies"] is None


def test_admin_quota_endpoint_guards(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("silver", "uq-guards@example.com")
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    assert _set_quota(cl, admin, 999_999, 1).status_code == 404
    assert _set_quota(cl, admin, f["account_id"], -1).status_code == 422
    r = cl.post(f"/platform/admin/accounts/{f['account_id']}/quota",
                headers=hdr(admin), json={})
    assert r.status_code == 422                    # الحقل مطلوب صراحةً
    # مصنع لا يبلغ نقطة الأدمِن.
    tok = login(cl, f["email"], f["password"])
    assert _set_quota(cl, tok, f["account_id"], 1).status_code == 403


def test_admin_accounts_list_shows_the_effective_per_user_quota(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("gold", "uq-list@example.com")
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    _set_quota(cl, admin, f["account_id"], 3)
    rows = cl.get("/platform/admin/accounts", headers=hdr(admin)).json()["accounts"]
    row = next(a for a in rows if a["id"] == f["account_id"])
    assert row["per_user_monthly_studies"] == 3
    assert row["per_user_quota_effective"] == 3


def test_quota_change_and_refusal_are_audited(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("gold", "uq-audit@example.com")
    mock_engine(monkeypatch)
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    _set_quota(cl, admin, f["account_id"], 1)
    tok = login(cl, f["email"], f["password"])
    _launch(cl, tok, f)
    _launch(cl, tok, f)                            # الرفض المُدقَّق
    audit_rows = cl.get("/platform/admin/audit?action=per_user_quota_changed",
                        headers=hdr(admin)).json()["audit"]
    assert audit_rows, "تغيير الحصّة بلا قيد تدقيق"
    refusals = cl.get("/platform/admin/audit?action=quota_exceeded",
                      headers=hdr(admin)).json()["audit"]
    assert any('"user_quota_exceeded"' in (r.get("changes") or "")
               for r in refusals), "رفض حصّة المستخدم بلا قيد تدقيق بسببه"


# ═══════════ التزامن — الدرس ٧٦ ═════════════════════════════════════════════
def _widen_user_quota_window(monkeypatch, seconds=0.05):
    """وسّع نافذة فحص حصّة المستخدم صناعياً — يقيس التصميم لا ترتيب GIL العابر.

    القسم الحرج أقصر من ميلي ثانية فيتسلسل الخيطان بحكم GIL ويبدو أي تصميم
    «صحيحاً». التوسيع يجعل الفحوص تتداخل فعلاً، فينكشف أي اعتماد على الحظ.
    (نفس منهج `test_platform_concurrency._widen_seat_check_window`.)
    """
    import time
    from silk_platform import quota as q
    monkeypatch.setattr(q, "_user_quota_check_delay",
                        lambda: time.sleep(seconds))


def test_concurrent_over_cap_launches_never_exceed_the_user_cap(monkeypatch):
    """إطلاقات متزامنة فوق سقف المستخدم: لا يثبت منها فوق السقف أبداً.

    **آلية الذرّية بالتصميم لا بقفل إضافي:** المطالبة draft→in_progress كتابة
    UPDATE محروسة تُثبَّت قبل الفحص وتختم المُطلِق، والعدّ يشمل الدراسة
    المُطالَب بها — فأسوأ تداخلٍ يُنتج رفضاً مزدوجاً تحفّظياً (fail-closed)،
    ولا يمكن أن يقبل تشغيلان معاً فوق السقف. النافذة الموسّعة تُثبت ذلك تحت
    تداخل حقيقي لا تسلسل GIL عابر.
    """
    info = seed(monkeypatch)
    f = make_factory("gold", "uq-conc@example.com")
    mock_engine(monkeypatch)
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    _set_quota(cl, admin, f["account_id"], 1)
    tok = login(cl, f["email"], f["password"])
    _widen_user_quota_window(monkeypatch)

    sids = [make_product_study(f["account_id"], f["user_id"])
            for _ in range(4)]
    results: list[int] = []
    lock = threading.Lock()

    # عملاء مسبقو الإنشاء: تركيبُ تطبيقٍ جديد يشغّل كنس الأيتام، وتركيبٌ
    # متزامن مع مطالبة خيطٍ آخر الطازجة قد يكنسها قبل تسجيلها في سجل الجسر
    # (سباق اختبارات لا إنتاج — التركيب الإنتاجي يسبق كل الطلبات).
    clients = {sid: client() for sid in sids}

    def fire(sid):
        r = clients[sid].post(f"/platform/studies/{sid}/launch",
                              headers=hdr(tok), json={})
        with lock:
            results.append(r.status_code)

    threads = [threading.Thread(target=fire, args=(s,)) for s in sids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok = results.count(200)
    assert ok <= 1, f"قبولان فوق سقف المستخدم (1): {results}"
    # وما ثبت فعلاً في القاعدة لا يتجاوز السقف — الحقيقة من الدراسات نفسها.
    from silk_platform import db as pdb, quota as q
    conn = pdb.connect()
    try:
        stuck = q.user_launches_this_period(conn, f["account_id"], f["user_id"])
    finally:
        conn.close()
    assert stuck <= 1, f"ثبت فوق السقف في القاعدة: {stuck}"
    assert stuck == ok, "عدد الثابت في القاعدة يخالف عدد المقبول عبر HTTP"


def test_the_migration_is_additive_and_idempotent(monkeypatch):
    """الترحيل 005 إضافي وخامل التكرار — أعمدة جديدة فقط، لا مساس بصفّ قائم."""
    from tests.platform_helpers import setup_env
    path = setup_env(monkeypatch)
    from silk_platform import db as pdb
    # إعادة تطبيق الترحيلات لا تفعل شيئاً (مسجَّلة) ولا تكسر القاعدة.
    assert pdb.apply_migrations(path) == []
    conn = pdb.connect(path)
    try:
        cols_a = {r[1] for r in conn.execute("PRAGMA table_info(accounts)")}
        cols_s = {r[1] for r in conn.execute("PRAGMA table_info(studies)")}
    finally:
        conn.close()
    assert "per_user_monthly_studies" in cols_a
    assert "launched_by_user_id" in cols_s
    # ترحيل 006 (التحوّل لدراسات السوق) إضافي وخامل التكرار أيضاً.
    for col in ("product", "market_pref", "hs_code", "image_id",
                "analysis_id", "run_started_at", "run_finished_at", "run_error"):
        assert col in cols_s, col


if __name__ == "__main__":
    import subprocess
    import sys
    sys.exit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
