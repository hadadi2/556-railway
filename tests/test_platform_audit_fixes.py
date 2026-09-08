"""إصلاحات تدقيق المنصّة العدائي (find all gaps — سؤال المالك «هل من عيب؟»).

درس 193 (2026-08-27):
- MEDIUM: `release_launch` كان يُنقِص العدّاد المخزَّن بلا وعيٍ بالعلامة المائية،
  فإرجاعُ إطلاقٍ سبق إعادةَ تعيينٍ يسرق حجزَ دراسةٍ لاحقة (تحت-إنفاذ الحصّة).
- LOW: فوترة التخزين كانت تُجهِض الجولة كلها على حسابٍ واحد يتجاوز الأرضية.
- LOW: التشخيص كان يستهلك وحدةً من السقف على فشل استيراد (503).

Hermetic؛ منصّة معزولة (conftest).
"""
from __future__ import annotations

from tests.platform_helpers import make_factory, seed


# ── MEDIUM: العلامة المائية تمنع الإرجاع المزدوج ─────────────────────────

def test_release_after_reset_does_not_double_refund(monkeypatch):
    """إطلاقٌ قبل إعادة التعيين لا يُنقِص العدّاد بعدها — لا حصّة مسروقة."""
    seed(monkeypatch)
    fac = make_factory("gold", "reset-race@f.example")
    from silk_platform import db as pdb, quota
    conn = pdb.connect()
    try:
        aid = fac["account_id"]
        # إطلاق S قبل إعادة التعيين (العدّاد 0→1).
        conn.execute("UPDATE accounts SET current_month_study_count = 1, "
                     "quota_period = ? WHERE id = ?",
                     (quota.current_period(), aid))
        conn.commit()
        s_launched = "2020-01-01T00:00:00Z"    # قبل العلامة بكثير
        # إعادة تعيين إدارية (العدّاد→0، العلامة=الآن).
        quota.reset_account_quota(conn, aid)
        # إطلاق S2 بعد إعادة التعيين (0→1).
        conn.execute("UPDATE accounts SET current_month_study_count = 1 "
                     "WHERE id = ?", (aid,))
        conn.commit()
        # S يفشل الآن ويُرجَع بـlaunched_at قبل العلامة.
        released = quota.release_launch(conn, aid, launched_at=s_launched)
        assert released is False, "أُرجِع إطلاقٌ سبق إعادةَ التعيين (خصم مزدوج)"
        count = conn.execute("SELECT current_month_study_count FROM accounts "
                             "WHERE id = ?", (aid,)).fetchone()[0]
        assert count == 1, "حجز S2 سُرِق — العدّاد نزل تحت الحقيقة"
    finally:
        conn.close()


def test_release_of_a_post_reset_launch_still_works(monkeypatch):
    """إطلاقٌ بعد إعادة التعيين يُرجَع طبيعياً (لا حجب زائد)."""
    seed(monkeypatch)
    fac = make_factory("gold", "post-reset@f.example")
    from silk_platform import db as pdb, quota
    from silk_platform.db import now_iso
    conn = pdb.connect()
    try:
        aid = fac["account_id"]
        quota.reset_account_quota(conn, aid)   # العلامة = الآن
        conn.execute("UPDATE accounts SET current_month_study_count = 1 "
                     "WHERE id = ?", (aid,))
        conn.commit()
        released = quota.release_launch(conn, aid, launched_at=now_iso())
        assert released is True
        count = conn.execute("SELECT current_month_study_count FROM accounts "
                             "WHERE id = ?", (aid,)).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_release_without_launched_at_is_backward_compatible(monkeypatch):
    """غياب launched_at (نداء قديم) يُرجِع كما كان."""
    seed(monkeypatch)
    fac = make_factory("gold", "compat@f.example")
    from silk_platform import db as pdb, quota
    conn = pdb.connect()
    try:
        aid = fac["account_id"]
        conn.execute("UPDATE accounts SET current_month_study_count = 1, "
                     "quota_period = ? WHERE id = ?",
                     (quota.current_period(), aid))
        conn.commit()
        assert quota.release_launch(conn, aid) is True
    finally:
        conn.close()


# ── LOW: فوترة التخزين تعزل الحساب الفاشل ─────────────────────────────────

def test_storage_billing_isolates_a_failing_account(monkeypatch):
    """حسابٌ يرفع عند القيد لا يُجهِض فوترة البقية.

    R5 (DB-5): الفوترة تقيّد عبر `wallet.apply_entry` داخل معاملتها (`BEGIN
    IMMEDIATE`) — فالعطلُ يُحقَن هناك؛ المعنى كما كان: فشلُ حسابٍ يُتخطّى.
    """
    seed(monkeypatch)
    a = make_factory("gold", "sb-a@f.example")
    b = make_factory("gold", "sb-b@f.example")
    from silk_platform import db as pdb, jobs, wallet
    conn = pdb.connect()
    try:
        # صورة لكل حساب (كي يُشحَن).
        for f in (a, b):
            conn.execute("INSERT INTO images (owner_id, storage_key, mime_type, "
                         "size_bytes, uploaded_at) VALUES (?,?,?,?,?)",
                         (f["account_id"], f"{f['account_id']}/x.png",
                          "image/png", 2 * 1024**3, "2020-01-01T00:00:00Z"))
        conn.commit()

        real_apply = wallet.apply_entry

        def _boom(conn2, **kw):
            if kw.get("account_id") == a["account_id"]:
                raise RuntimeError("floor breached (simulated)")
            return real_apply(conn2, **kw)
        monkeypatch.setattr(jobs.wallet, "apply_entry", _boom)

        charged = jobs.run_storage_billing(conn, period="2099-01")
        billed_ids = {c["account_id"] for c in charged}
        assert a["account_id"] not in billed_ids   # فشل، تُخطّي
        assert b["account_id"] in billed_ids        # شُحن رغم فشل الأول
    finally:
        conn.close()
