"""المهام الخلفية — scheduled background jobs (callable + testable directly).

- التصفير الشهري للحصص: أوّل الشهر 00:00 UTC (يتخطّى Basic) — في quota.py.
- فوترة التخزين: أوّل الشهر 01:00 UTC → قيود 'storage_charge'.
- تنظيف الجلسات: يومياً 02:00 UTC (حذف المنتهية) — في auth.py.
- (عامل طابور البريد حُذف مع التنقيب — قرار مالك 2026-08-17.)

كل مهمّة دالّة نقيّة قابلة للنداء المباشر في الاختبارات؛ الجدولة الفعلية
(APScheduler/cron) تُركَّب في PR لاحق. Each job is a directly-callable function.
"""
from __future__ import annotations

import logging
import math
import sqlite3

from . import auth, quota, wallet
from .models import Operation, PRICE_STORAGE_CENTS_PER_GB_MONTH

log = logging.getLogger(__name__)


def run_monthly_quota_reset(conn: sqlite3.Connection) -> int:
    """مهمّة التصفير الشهري — thin wrapper over quota.monthly_reset."""
    return quota.monthly_reset(conn)


def run_session_cleanup(conn: sqlite3.Connection) -> int:
    """مهمّة تنظيف الجلسات — delete expired sessions; returns rows removed."""
    return auth.cleanup_expired_sessions(conn)


def _billing_description(period: str) -> str:
    """وصف قيد الفوترة لفترة — the period-stamped ledger description (the key).

    الوصف يحمل مفتاح الفترة كي يصير القيد قابلاً للاكتشاف: الدفتر غير قابل
    للتعديل، فالتكرار لا يُصحَّح لاحقاً — الوقاية الوحيدة هي عدم كتابته أصلاً.
    """
    return f"monthly storage billing {period}"


def already_billed(conn: sqlite3.Connection, account_id: int, period: str) -> bool:
    """هل شُحن هذا الحساب لهذه الفترة؟ — has this account been billed this period?"""
    row = conn.execute(
        "SELECT 1 FROM ledger_entries WHERE account_id = ? AND "
        "operation_type = 'storage_charge' AND description = ? LIMIT 1",
        (account_id, _billing_description(period))).fetchone()
    return row is not None


def run_storage_billing(conn: sqlite3.Connection,
                        period: str | None = None) -> list[dict]:
    """فوترة التخزين الشهرية — one 'storage_charge' ledger entry per account.

    التكلفة = ceil(GB) × $0.10/GB-شهر لكل حساب له صور. الحسابات بلا صور لا
    تُشحَن. يرجّع قائمة {account_id, gb, amount_cents} المشحونة.

    **خاملة التكرار** (idempotent): كل قيد موسوم بمفتاح فترته، والحساب المشحون
    لهذه الفترة يُتخطّى — فإعادة تشغيل مهمّة تعطّلت في منتصفها لا تشحن أحداً
    مرّتين. حرجٌ لأن الدفتر غير قابل للتعديل: التكرار غير قابل للتصحيح.
    Skips accounts already billed for `period`; safe to retry after a crash.
    """
    period = period or quota.current_period()
    rows = conn.execute(
        "SELECT owner_id AS account_id, COALESCE(SUM(size_bytes),0) AS bytes "
        "FROM images GROUP BY owner_id HAVING bytes > 0").fetchall()
    charged: list[dict] = []
    for r in rows:
        gb = r["bytes"] / (1024 ** 3)
        amount = math.ceil(gb) * PRICE_STORAGE_CENTS_PER_GB_MONTH
        if amount <= 0:
            continue
        wallet.ensure_wallet(conn, r["account_id"])
        # درس 193: عزل كل حساب — حسابٌ يتجاوز أرضية السحب على المكشوف كان
        # يرفع InsufficientFunds فيُجهِض الجولة كلها، فلا تُشحَن الحسابات بعده
        # (فجوة دفتر تتكرر كل تشغيلة). فشلُ حسابٍ يُسجَّل ويُتخطّى؛ الخمول ضدّ
        # التكرار يبقى (الوسم بمفتاح الفترة) فلا شحن مزدوج للناجحين.
        # R5 (تدقيق 2026-09-01، DB-5): الفحصُ «هل شُحن؟» والقيدُ في **معاملةٍ
        # واحدة** (`BEGIN IMMEDIATE`) — قراءةٌ ثم كتابةٌ في معاملتين كانتا تدعان
        # عاملَين متزامنَين يشحنان الحسابَ مرّتين على دفترٍ لا يُصحَّح.
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        try:
            if already_billed(conn, r["account_id"], period):
                conn.rollback()
                continue   # مشحون سلفاً لهذه الفترة · already billed this period
            wallet.apply_entry(conn, account_id=r["account_id"], actor_user_id=None,
                               operation=Operation.STORAGE_CHARGE, amount=-amount,
                               description=_billing_description(period),
                               metadata={"bytes": r["bytes"],
                                         "gb_ceil": math.ceil(gb),
                                         "period": period},
                               allow_negative=True)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 — حسابٌ واحد لا يُجهِض الجولة
            conn.rollback()
            log.warning("storage billing skipped account %s (%s): %s",
                        r["account_id"], period, exc)
            continue
        charged.append({"account_id": r["account_id"], "gb": math.ceil(gb),
                        "amount_cents": amount, "period": period})
    return charged
