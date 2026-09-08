"""إشعارات داخل المنصّة · in-platform notifications (قرار المالك 2026-08-18).

«اضف نظام الاشعارات عند الانتهاء من الدارسة» — مع توصيل الدراسات بمحرّك البحث
العميق (~١٥ دقيقة) يكتب جسرُ المحرّك إشعاراً عند إنهاء كل تشغيلة (نجاحاً أو
فشلاً معلَناً) في **نفس معاملة** الإنهاء، وتقرؤه الواجهة دورياً (جرس + إشعار
متصفح). لا قناة بريد هنا — قرار المالك: داخل المنصّة + المتصفح فقط الآن.

النطاق مستأجَري بالكامل: كل جملة SQL تحمل `account_id = ?` (حارس العزل AST —
الجدول مُدرَج في `TENANT_TABLES`). الكتابة نظامية فقط (الجسر)؛ المستخدم يقرأ
ويعلّم مقروءاً — لا CRUD عام، فالجدول ليس في `repository._WRITABLE` عمداً.
"""
from __future__ import annotations

import logging
import sqlite3

from . import audit
from .db import now_iso

log = logging.getLogger(__name__)

# أقصى ما يُعاد في قراءة واحدة — الواجهة تعرض الأحدث؛ لا ترقيم صفحات (YAGNI).
_LIST_LIMIT = 30

# سقف نصّ الإشعار — R3 (تدقيق 2026-09-01): كان ٥٠٠ بينما `engine_bridge.
# _REASON_MAX` يبني سبباً معلَناً حتى ١٠٠٠ حرف (تسميةُ كل عمودٍ غائب، الدرس
# ٢٠٧)، فكان الجرسُ يقصّ نصفَ السبب الذي وُجد ليُقرأ. مصدرٌ واحد للسقفين.
BODY_MAX = 1000

import datetime  # noqa: E402 — R5 (DB-16): نافذةُ الاحتفاظ


# R5 (DB-13): أنواعُ الإشعارات المعروفة — النوعُ يقود نصَّ الجرس وشريحتَه في
# الواجهة؛ نوعٌ مجهول كان يُكتَب صامتاً فيظهر «غير معروف».
KINDS = frozenset({"study_completed", "study_failed", "study_cancelled"})


def record(conn: sqlite3.Connection, *, account_id: int, kind: str,
           title: str, body: str = "", study_id: int | None = None,
           user_id: int | None = None) -> int:
    """اكتب إشعاراً — لا يلتزم (المُنادي يضبط حدود المعاملة، كنمط audit.record)."""
    if kind not in KINDS:
        raise ValueError(f"unknown notification kind: {kind!r}")
    cur = conn.execute(
        "INSERT INTO platform_notifications (account_id, user_id, kind, "
        "study_id, title, body, created_at) VALUES (?,?,?,?,?,?,?)",
        (account_id, user_id, kind, study_id,
         (title or "")[:200], (body or "")[:BODY_MAX], now_iso()))
    return int(cur.lastrowid)


def notify_study_finish(conn: sqlite3.Connection, study_id: int,
                        account_id: int, *, kind: str, title_fmt: str,
                        body: str) -> None:
    """إشعار إنهاء تشغيلةٍ — المصنعُ ومرآةُ حساب سِلك، في معاملة المُنادي.

    `title_fmt` يحمل `{p}` لاسم المنتج (نطاق المستأجر نفسه؛ الغائب = «دراستك»).
    R3: كان في `engine_bridge` وحده، فمسارُ الإغلاق اليدوي (`lifecycle`) لم
    يُشعِر أحداً إطلاقاً — الآن مصدرٌ واحد يقرؤه المساران.
    """
    row = conn.execute(
        "SELECT product FROM studies WHERE id = ? AND owner_id = ?",
        (study_id, account_id)).fetchone()
    pname = (row["product"] if row else "") or "دراستك"
    record(conn, account_id=account_id, kind=kind, study_id=study_id,
           title=title_fmt.format(p=pname), body=body)
    # مرآةٌ لحساب سِلك (الأدمِن) — جرسُه كان فارغاً **بنيوياً**: الجسر يكتب
    # لحساب المصنع وحده والقراءة مقيّدة بـ`account_id`، فإشرافُ المالك الذي
    # أذِن به (فتح الدراسات، 2026-08-19) كان يكتشف التعثّر بالمصادفة. اسمُ
    # المصنع يُلحَق كي يُعرف صاحبُ الخبر من الجرس مباشرةً.
    vault = conn.execute(
        "SELECT id FROM accounts WHERE is_vault = 1 LIMIT 1").fetchone()
    if vault and int(vault["id"]) != int(account_id):
        owner = conn.execute("SELECT name FROM accounts WHERE id = ?",
                             (account_id,)).fetchone()
        who = (owner["name"] if owner else "") or "مصنع"
        record(conn, account_id=int(vault["id"]), kind=kind, study_id=study_id,
               title=f"{title_fmt.format(p=pname)} — {who}", body=body)


def notify_study_finish_safely(conn: sqlite3.Connection, study_id: int,
                               account_id: int, *, kind: str, title_fmt: str,
                               body: str) -> bool:
    """`notify_study_finish` بلا صعود — R1 (RC-5/ENG-6)، ويُعمَّم في R3.

    فشلُ الإشعار يُسجَّل (سجلّ الخادم + قيد تدقيق `notification_failed`) ولا
    يمسّ الحسم أبداً: «مكتملة بلا إشعار» أصدقُ من نجاحٍ يُقلَب فشلاً مُسترَدّ
    الحصّة. يعيد True إن كُتب الإشعار.
    """
    try:
        notify_study_finish(conn, study_id, account_id, kind=kind,
                            title_fmt=title_fmt, body=body)
        return True
    except Exception as exc:  # noqa: BLE001 — الإشعار تحسين، الحسم شرط
        log.exception("study %s notification failed (%s)", study_id, kind)
        try:
            audit.record(conn, action="notification_failed",
                         account_id=account_id, resource_type="study",
                         resource_id=study_id,
                         changes={"kind": kind, "error": str(exc)[:200]})
        except Exception:  # noqa: BLE001
            log.exception("study %s notification_failed audit also failed",
                          study_id)
        return False


def prune(conn: sqlite3.Connection, *, read_days: int) -> int:
    """احذف الإشعارات **المقروءة** الأقدم من `read_days` — R5 (DB-16).

    غيرُ المقروء لا يُمَسّ (جرسٌ لم يُرَ ليس قابلاً للنسيان)، و`read_days <= 0`
    = لا حذف. عالميٌّ بالتصميم (لا نطاقَ حساب): تنظيفٌ جدوليّ يقوده المجدول لا
    طلبُ مستأجر. يلتزم فوراً.
    """
    if read_days <= 0:
        return 0
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=read_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "DELETE FROM platform_notifications WHERE read_at IS NOT NULL "
        "AND created_at < ?", (cutoff,))
    conn.commit()
    return int(cur.rowcount)


def list_for_account(conn: sqlite3.Connection, account_id: int) -> dict:
    """أحدث إشعارات الحساب + عدد غير المقروء — حمولة `GET /notifications`."""
    rows = conn.execute(
        "SELECT id, kind, study_id, title, body, created_at, read_at "
        "FROM platform_notifications WHERE account_id = ? "
        "ORDER BY id DESC LIMIT ?", (account_id, _LIST_LIMIT)).fetchall()
    unread = conn.execute(
        "SELECT COUNT(*) AS c FROM platform_notifications "
        "WHERE account_id = ? AND read_at IS NULL", (account_id,)).fetchone()
    return {"notifications": [dict(r) for r in rows],
            "unread_count": int(unread["c"] if unread else 0)}


def mark_read(conn: sqlite3.Connection, account_id: int,
              ids: list[int] | None = None, up_to_id: int | None = None) -> int:
    """علّم إشعاراتٍ مقروءةً — قائمة معرّفات، أو حتى علامةٍ مائية، أو الكل. يعيد العدد.
    يلتزم فوراً (عملية مستخدم مستقلة، لا معاملة أوسع تنتظرها).

    P3 (BIZ-11، تدقيق 2026-09-01): «علّم الكلّ» كان يبتلع إشعاراً **وصل بعد** أن عُرضت
    القائمة على المستخدم — فيختفي خبرٌ لم يره أحد. `up_to_id` علامةٌ مائية: يُعلَّم ما
    كان معروضاً وقتَ الفتح فقط، وما وصل بعده يبقى غيرَ مقروء.
    """
    now = now_iso()
    if ids is None and up_to_id is not None:
        cur = conn.execute(
            "UPDATE platform_notifications SET read_at = ? "
            "WHERE account_id = ? AND read_at IS NULL AND id <= ?",
            (now, account_id, int(up_to_id)))
        conn.commit()
        return int(cur.rowcount or 0)
    if ids is not None:
        # قائمة فارغة = لا شيء يُعلَّم (العقد: الحذف الكامل للحقل هو «الكل» —
        # §58 موجة A: `if ids:` كانت تعامل [] كأنها None فتمسح شارةً لم تُقرأ).
        clean = [int(i) for i in ids][:100]
        if not clean:
            return 0
        marks = ",".join("?" for _ in clean)
        cur = conn.execute(
            "UPDATE platform_notifications SET read_at = ? "
            f"WHERE account_id = ? AND read_at IS NULL AND id IN ({marks})",
            (now, account_id, *clean))
    else:
        cur = conn.execute(
            "UPDATE platform_notifications SET read_at = ? "
            "WHERE account_id = ? AND read_at IS NULL", (now, account_id))
    conn.commit()
    return int(cur.rowcount)
