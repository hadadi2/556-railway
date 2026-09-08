"""أولية الفوترة المستخلَصة — the billing primitive (charge_metered).

تقرير الحملة المدفوع ($1) حُذف مع التنقيب (قرار مالك 2026-08-17: «الباقة فقط»
تحكم الدراسات — لا خصم لكل دراسة/تقرير). `billing.py` **باقٍ بقرار المالك**
لفوترة الاشتراكات مستقبلاً، وهذان القفلان يحرسان عقده المباشر: رفض المبالغ
غير الموجبة، واسترجاع مفتاح الخمول من الدفتر (وخمول المفتاح المتزامن مقفول في
`test_platform_concurrency.py::test_concurrent_metered_charges_on_one_key_...`).
"""
import pytest

from tests.platform_helpers import make_factory, seed


# ═══════════════════ الطبقة المستخلَصة · the billing primitive ═══════════════
def test_charge_metered_rejects_a_non_positive_amount(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "bill-zero@example.com", fund_cents=500)
    from silk_platform import billing, db as pdb
    from silk_platform.models import Operation
    conn = pdb.connect()
    try:
        for bad in (0, -100):
            with pytest.raises(billing.BillingError):
                billing.charge_metered(
                    conn, account_id=f["account_id"], actor_user_id=f["user_id"],
                    operation=Operation.REPORT_GENERATED, amount_cents=bad,
                    key="k")
    finally:
        conn.close()


def test_charge_key_is_recoverable_from_the_ledger(monkeypatch):
    """المفتاح مخزَّن في وصف القيد فيُستعلَم بلا جدول جديد (نمط jobs.already_billed)."""
    seed(monkeypatch)
    f = make_factory("gold", "bill-key@example.com", fund_cents=500)
    from silk_platform import billing, db as pdb
    from silk_platform.models import Operation
    conn = pdb.connect()
    try:
        assert billing.already_charged(conn, f["account_id"],
                                       Operation.REPORT_GENERATED, "k1") is None
        billing.charge_metered(conn, account_id=f["account_id"],
                               actor_user_id=f["user_id"],
                               operation=Operation.REPORT_GENERATED,
                               amount_cents=100, key="k1")
        found = billing.already_charged(conn, f["account_id"],
                                        Operation.REPORT_GENERATED, "k1")
        assert found is not None and found["amount"] == -100
        # مفتاح آخر لم يُخصَم · a different key is still unbilled.
        assert billing.already_charged(conn, f["account_id"],
                                       Operation.REPORT_GENERATED, "k2") is None
    finally:
        conn.close()
