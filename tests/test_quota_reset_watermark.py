"""حصّة واحدة، مصدر حقيقة واحد (find all gaps F17 — درس 192، قرار مالك).

المالك: «إعادة تعيين الأدمِن يجب أن تصفّر العدّاد المشتق أيضاً». العدّاد
المشتقّ لكل مستخدم (`user_launches_this_period`) كان يبقى «مستهلَكاً» بعد إعادة
تعيينٍ تصفّر العدّاد المخزَّن وحده. العلامة المائية `quota_reset_at` مصدرٌ
واحد لنقطة الصفر يحترمه العدّادان.

Hermetic؛ منصّة معزولة (conftest).
"""
from __future__ import annotations

from tests.platform_helpers import (client, hdr, login, make_factory,
                                     make_product_study, seed)


def _launch_study(account_id: int, user_id: int) -> int:
    """أنشئ دراسةً وخُتِمها منطلقةً الآن (تُحتسَب في العدّاد المشتقّ)."""
    from silk_platform import db as pdb
    from silk_platform.db import now_iso
    sid = make_product_study(account_id, user_id, state="in_progress")
    conn = pdb.connect()
    try:
        conn.execute(
            "UPDATE studies SET launched_by_user_id = ?, launched_at = ? "
            "WHERE id = ?", (user_id, now_iso(), sid))
        conn.commit()
    finally:
        conn.close()
    return sid


def test_admin_reset_clears_the_derived_per_user_counter(monkeypatch):
    seed(monkeypatch)
    fac = make_factory("gold", "reset@f.example")
    from silk_platform import db as pdb, quota
    _launch_study(fac["account_id"], fac["user_id"])
    conn = pdb.connect()
    try:
        before = quota.user_launches_this_period(
            conn, fac["account_id"], fac["user_id"])
        assert before == 1, "الدراسة المنطلقة لم تُحتسَب"
        quota.reset_account_quota(conn, fac["account_id"])
        after = quota.user_launches_this_period(
            conn, fac["account_id"], fac["user_id"])
        assert after == 0, "إعادة التعيين لم تصفّر العدّاد المشتقّ"
        # والعدّاد المخزَّن للحساب صُفِّر أيضاً (نفس إعادة التعيين الواحدة).
        acc = conn.execute(
            "SELECT current_month_study_count FROM accounts WHERE id = ?",
            (fac["account_id"],)).fetchone()
        assert acc["current_month_study_count"] == 0
    finally:
        conn.close()


def test_monthly_reset_stamps_the_watermark(monkeypatch):
    """التصفير الشهري يختم العلامة أيضاً — فالعدّادان يُصفَّران معاً عند الحدّ."""
    seed(monkeypatch)
    fac = make_factory("gold", "monthly@f.example")
    from silk_platform import db as pdb, quota
    conn = pdb.connect()
    try:
        conn.execute("UPDATE accounts SET quota_period = '1999-01' WHERE id = ?",
                     (fac["account_id"],))   # فترة قديمة كي يُصفَّر
        conn.commit()
        quota.monthly_reset(conn)
        row = conn.execute("SELECT quota_reset_at FROM accounts WHERE id = ?",
                           (fac["account_id"],)).fetchone()
        assert row["quota_reset_at"], "التصفير الشهري لم يختم العلامة"
    finally:
        conn.close()


def test_admin_reset_quota_endpoint(monkeypatch):
    info = seed(monkeypatch)
    fac = make_factory("gold", "ep@f.example")
    with client() as cl:
        tok = login(cl, info["admin"]["email"], info["admin"]["password"])
        r = cl.post(f"/platform/admin/accounts/{fac['account_id']}/reset-quota",
                    headers=hdr(tok))
        assert r.status_code == 200, r.text
        assert r.json()["quota_reset_at"]
        # حسابٌ وهميّ = 404 صريح لا تصفيرٌ صامت.
        r404 = cl.post("/platform/admin/accounts/999999/reset-quota",
                       headers=hdr(tok))
        assert r404.status_code == 404


def test_watermark_null_default_keeps_existing_behavior(monkeypatch):
    """بلا إعادة تعيينٍ سابقة (NULL) العدّ كما كان — الإضافة عرضية."""
    seed(monkeypatch)
    fac = make_factory("gold", "null@f.example")
    from silk_platform import db as pdb, quota
    _launch_study(fac["account_id"], fac["user_id"])
    conn = pdb.connect()
    try:
        assert quota.user_launches_this_period(
            conn, fac["account_id"], fac["user_id"]) == 1
    finally:
        conn.close()
