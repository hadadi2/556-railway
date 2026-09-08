"""حصص + محفظة (القسم ١٣) — Section 13 quota/wallet locks.

Basic مدى الحياة يصمد أمام التصفير؛ Silver محجوب عند الإطلاق الثالث؛ العدّاد
يزيد عند الإطلاق فقط. كل خصم/إيداع قيد واحد بـbalance_after؛ الدفتر غير قابل
للتعديل؛ التمويل ذرّي بتراجع عند الفشل؛ actor_user_id غير فارغ.

(قسم مفتاح القتل واختبارات بوّابات الرصيد على الإطلاق حُذفت مع التنقيب —
قرار مالك 2026-08-17: «الباقة فقط»؛ عكسُ بوّابة الرصيد مقفول في
`test_platform_pivot_bridge.py::test_launch_ignores_wallet_balance`.)
"""
import sqlite3

import pytest

from platform_helpers import (client, hdr, login, make_factory,
                              make_product_study, mock_engine, seed)
from silk_platform import db as pdb, quota, wallet
from silk_platform.models import Operation


# ════════════════════════════ QUOTA ═════════════════════════════════════════
def test_basic_lifetime_limit_enforced_and_survives_monthly_reset(monkeypatch):
    seed(monkeypatch)
    f = make_factory("basic", "basic@f.local")
    mock_engine(monkeypatch)
    s1 = make_product_study(f["account_id"], f["user_id"])
    s2 = make_product_study(f["account_id"], f["user_id"])
    cl = client()
    tok = login(cl, f["email"], f["password"])
    # الإطلاق الأول ينجح — first (and only lifetime) launch succeeds.
    assert cl.post(f"/platform/studies/{s1}/launch", headers=hdr(tok), json={}
                   ).status_code == 200
    # الثاني محجوب (مدى الحياة = 1) — second blocked.
    r2 = cl.post(f"/platform/studies/{s2}/launch", headers=hdr(tok), json={})
    assert r2.status_code == 403 and r2.json()["detail"]["reason"] == "lifetime_quota_exceeded"
    # التصفير الشهري لا يمسّ Basic — monthly reset does not touch Basic.
    conn = pdb.connect()
    try:
        quota.monthly_reset(conn)
    finally:
        conn.close()
    r3 = cl.post(f"/platform/studies/{s2}/launch", headers=hdr(tok), json={})
    assert r3.status_code == 403  # still blocked after reset


def test_silver_blocked_at_third_monthly_launch(monkeypatch):
    seed(monkeypatch)
    f = make_factory("silver", "silver@f.local")
    mock_engine(monkeypatch)
    ids = [make_product_study(f["account_id"], f["user_id"]) for _ in range(3)]
    cl = client()
    tok = login(cl, f["email"], f["password"])
    assert cl.post(f"/platform/studies/{ids[0]}/launch", headers=hdr(tok), json={}
                   ).status_code == 200
    assert cl.post(f"/platform/studies/{ids[1]}/launch", headers=hdr(tok), json={}
                   ).status_code == 200
    r3 = cl.post(f"/platform/studies/{ids[2]}/launch", headers=hdr(tok), json={})
    assert r3.status_code == 403 and r3.json()["detail"]["reason"] == "monthly_quota_exceeded"


def test_quota_guarded_increment_never_exceeds_cap(monkeypatch):
    """الزيادة المحروسة لا تتجاوز الحدّ — a blocked reserve does NOT increment.

    يقفل إصلاح TOCTOU: reserve عند الحدّ يرجع محجوباً والعدّاد يبقى عند الحدّ
    (لا يتخطّاه)، لأن الزيادة والشرط `< limit` في UPDATE ذرّي واحد.
    """
    seed(monkeypatch)
    f = make_factory("silver", "atomic@f.local", fund_cents=0)
    conn = pdb.connect()
    try:
        d1 = quota.reserve_launch(conn, f["account_id"], actor_user_id=f["user_id"])
        d2 = quota.reserve_launch(conn, f["account_id"], actor_user_id=f["user_id"])
        d3 = quota.reserve_launch(conn, f["account_id"], actor_user_id=f["user_id"])
        assert d1.allowed and d2.allowed and not d3.allowed
        cnt = conn.execute("SELECT current_month_study_count FROM accounts WHERE id=?",
                           (f["account_id"],)).fetchone()[0]
        assert cnt == 2  # never incremented past the Silver cap of 2
    finally:
        conn.close()


def test_counter_increments_only_on_launch(monkeypatch):
    seed(monkeypatch)
    f = make_factory("silver", "s2@f.local")
    mock_engine(monkeypatch)
    cl = client()
    tok = login(cl, f["email"], f["password"])

    def counter():
        conn = pdb.connect()
        try:
            return conn.execute("SELECT current_month_study_count FROM accounts "
                                "WHERE id = ?", (f["account_id"],)).fetchone()[0]
        finally:
            conn.close()

    study = cl.post("/platform/studies", headers=hdr(tok),
                    json={"product": "تمور سكري"}).json()
    assert counter() == 0  # creating a draft does NOT increment
    cl.patch(f"/platform/studies/{study['id']}", headers=hdr(tok),
             json={"product": "تمور خلاص"})
    assert counter() == 0  # editing a draft does NOT increment
    assert cl.post(f"/platform/studies/{study['id']}/launch", headers=hdr(tok),
                   json={}).status_code == 200
    assert counter() == 1  # launch increments exactly once


# ════════════════════════════ WALLET / LEDGER ═══════════════════════════════
def test_every_debit_credit_posts_one_entry_with_balance_after(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "g@f.local")
    conn = pdb.connect()
    try:
        wallet.ensure_wallet(conn, f["account_id"])
        before = conn.execute("SELECT COUNT(*) c FROM ledger_entries WHERE "
                              "account_id = ?", (f["account_id"],)).fetchone()["c"]
        wallet.post_entry(conn, account_id=f["account_id"], actor_user_id=f["user_id"],
                          operation=Operation.WALLET_FUNDED, amount=1000)
        wallet.post_entry(conn, account_id=f["account_id"], actor_user_id=f["user_id"],
                          operation=Operation.EMAIL_SENT, amount=-300)
        rows = conn.execute("SELECT amount, balance_after FROM ledger_entries WHERE "
                            "account_id = ? ORDER BY id", (f["account_id"],)).fetchall()
        assert len(rows) - before == 2
        assert rows[-2]["balance_after"] == 1000   # after +1000
        assert rows[-1]["balance_after"] == 700     # after -300
        w = wallet.get_wallet(conn, f["account_id"])
        assert w["balance"] == 700 and w["lifetime_funded"] == 1000 and w["lifetime_spent"] == 300
    finally:
        conn.close()


def test_ledger_is_immutable(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "g2@f.local")
    conn = pdb.connect()
    try:
        wallet.ensure_wallet(conn, f["account_id"])
        eid = wallet.post_entry(conn, account_id=f["account_id"],
                                actor_user_id=f["user_id"],
                                operation=Operation.WALLET_FUNDED, amount=500)
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE ledger_entries SET amount = 0 WHERE id = ?", (eid,))
            conn.commit()
        conn.rollback()
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM ledger_entries WHERE id = ?", (eid,))
            conn.commit()
        conn.rollback()
        # القيد ما زال سليماً — the entry survives both attempts unchanged.
        assert conn.execute("SELECT amount FROM ledger_entries WHERE id = ?",
                            (eid,)).fetchone()["amount"] == 500
    finally:
        conn.close()


def test_funding_atomic_rollback_on_injected_failure(monkeypatch):
    info = seed(monkeypatch)
    vault = info["vault_account_id"]
    fa = info["factory_a"]["account_id"]
    conn = pdb.connect()
    try:
        v0 = wallet.ensure_wallet(conn, vault)["balance"]
        f0 = wallet.ensure_wallet(conn, fa)["balance"]
        entries0 = conn.execute("SELECT COUNT(*) c FROM ledger_entries").fetchone()["c"]

        def boom():
            raise RuntimeError("injected mid-flow failure")

        with pytest.raises(RuntimeError):
            wallet.fund_wallet(conn, admin_user_id=info["admin"]["id"],
                               factory_account_id=fa, amount_cents=1234,
                               vault_account_id=vault, _fault=boom)
        # لا محفظة تغيّرت ولا قيد كُتب — nothing moved, no entry written.
        assert wallet.get_wallet(conn, vault)["balance"] == v0
        assert wallet.get_wallet(conn, fa)["balance"] == f0
        assert conn.execute("SELECT COUNT(*) c FROM ledger_entries"
                            ).fetchone()["c"] == entries0
    finally:
        conn.close()


def test_actor_user_id_nonnull_for_user_triggered_ops(monkeypatch):
    info = seed(monkeypatch)
    cl = client()
    tadmin = login(cl, info["admin"]["email"], info["admin"]["password"])
    cl.post("/platform/admin/fund", headers=hdr(tadmin),
            json={"account_id": info["factory_a"]["account_id"], "amount_cents": 400})
    conn = pdb.connect()
    try:
        # كل قيد wallet_funded ناتج عن تمويل الأدمِن يحمل معرّف فاعل غير فارغ.
        rows = conn.execute(
            "SELECT actor_user_id FROM ledger_entries WHERE operation_type = "
            "'wallet_funded' AND account_id = ?",
            (info["factory_a"]["account_id"],)).fetchall()
        assert rows and all(r["actor_user_id"] is not None for r in rows)
    finally:
        conn.close()
