"""سجلّ التدقيق — audit trail writes and scoped reads.

كل تغيير أو محاولة وصول مرفوضة تُسجَّل. الأدمِن يبحث عالمياً؛ المصنع يرى
حساب نفسه فقط. Admin searches globally; a factory sees only its own account.
"""
from __future__ import annotations

import json
import sqlite3

from .db import now_iso


def record(conn: sqlite3.Connection, *, action: str,
           user_id: int | None = None, account_id: int | None = None,
           resource_type: str | None = None, resource_id: str | int | None = None,
           changes: dict | None = None, ip_address: str | None = None) -> int:
    """اكتب قيداً في سجلّ التدقيق — append one audit entry, return its id.

    لا يُنفِّذ commit (ليكون ذرّياً ضمن معاملة الاستدعاء عند اللزوم)؛ المُنادي
    يلتزم. Does not commit — caller controls the transaction boundary.
    """
    cur = conn.execute(
        "INSERT INTO audit_log (user_id, account_id, action, resource_type, "
        "resource_id, changes, ip_address, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, account_id, action, resource_type,
         None if resource_id is None else str(resource_id),
         json.dumps(changes, ensure_ascii=False) if changes is not None else None,
         ip_address, now_iso()))
    return int(cur.lastrowid)


def record_denied(conn: sqlite3.Connection, *, action: str, user_id: int | None,
                  account_id: int | None, resource_type: str, resource_id: str | int,
                  ip_address: str | None = None) -> int:
    """سجّل محاولة وصول عابرة للمستأجر مرفوضة — log a denied cross-tenant attempt.

    مطلوب صراحةً في معايير القبول («attempts audit-logged»). يلتزم فوراً كي
    يُثبَّت أثر المحاولة حتى لو رُفض الطلب لاحقاً.
    """
    rid = record(conn, action=action, user_id=user_id, account_id=account_id,
                 resource_type=resource_type, resource_id=resource_id,
                 changes={"denied": True}, ip_address=ip_address)
    conn.commit()
    return rid


def search(conn: sqlite3.Connection, *, account_id: int | None = None,
           action: str | None = None, limit: int = 50) -> list[dict]:
    """اقرأ قيود التدقيق — scoped read; account_id=None means global (admin only).

    فرض النطاق مسؤولية المُنادي (النقطة النهائية): تمرِّر account_id للمصنع،
    وNone للأدمِن. The endpoint decides scope; this just applies it.
    """
    sql = "SELECT * FROM audit_log"
    params: list = []
    clauses: list[str] = []
    if account_id is not None:
        clauses.append("account_id = ?")
        params.append(account_id)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# R5 (تدقيق 2026-09-01، DB-16): قيودٌ لا تُحذف أبداً مهما طال الاحتفاظ — أثرُ
# الرفض العابر للمستأجر، وأفعالُ الأدمِن، والمال، والإقرارات القانونية.
_PROTECTED_ACTION_PREFIXES = ("cross_tenant_", "admin_", "tier_", "vault_",
                              "study_advisories_", "checkout_", "account_")


def _cutoff(days: int) -> str:
    import datetime
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def prune(conn: sqlite3.Connection, *, days: int) -> int:
    """احذف قيودَ التدقيق **غيرَ المحميّة** الأقدم من `days` — R5 (DB-16).

    `days <= 0` = لا حذف (الافتراض). القيودُ المحميّة (بادئاتُ الرفض والأدمِن
    والمال والإقرارات) تبقى إلى الأبد. يلتزم فوراً.
    """
    if days <= 0:
        return 0
    # `_` في البادئات بدلُ حرفٍ في LIKE — المطابقةُ بالموضع (`instr … = 1`) لا بالنمط.
    where = " AND ".join("instr(action, ?) <> 1" for _ in _PROTECTED_ACTION_PREFIXES)
    cur = conn.execute(
        f"DELETE FROM audit_log WHERE created_at < ? AND {where}",
        (_cutoff(days), *_PROTECTED_ACTION_PREFIXES))
    conn.commit()
    return int(cur.rowcount)


def prune_checkout(conn: sqlite3.Connection, *, days: int) -> int:
    """احذف قيودَ `checkout_requested` الأقدم من `days` — R7 (AUTH-20).

    `prune` يحمي البادئة `checkout_` عمداً (سجلُّ إيرادات)؛ هذا المسارُ المخصَّص
    وحده يحذفها، بعد نافذة احتفاظٍ طويلة (٣٦٥ يوماً افتراضاً؛ `<= 0` = لا حذف)."""
    if days <= 0:
        return 0
    cur = conn.execute(
        "DELETE FROM audit_log WHERE action = 'checkout_requested' AND created_at < ?",
        (_cutoff(days),))
    conn.commit()
    return int(cur.rowcount)


def scrub_checkout_pii(conn: sqlite3.Connection, *, days: int) -> int:
    """امسح بياناتِ التواصل من قيود `checkout_requested` الأقدم من `days` — AUTH-20.

    القيدُ يبقى (عدُّ الطلبات وتوقيتُها أثرٌ مشروع) وحقلُ `changes` يصير
    `{"scrubbed": true}`؛ `audit_log` بلا مُحفِّز ثبات (المُحفِّزُ على الدفتر
    وسجلّ الموافقات وحدهما). `days <= 0` = لا مسح. يلتزم فوراً.
    """
    if days <= 0:
        return 0
    cur = conn.execute(
        "UPDATE audit_log SET changes = '{\"scrubbed\": true}' "
        "WHERE action = 'checkout_requested' AND created_at < ? "
        "AND (changes IS NULL OR changes NOT LIKE '%\"scrubbed\"%')",
        (_cutoff(days),))
    conn.commit()
    return int(cur.rowcount)
