"""دورة حياة الدراسة — the explicit completed/archived transitions.

`draft→in_progress` (الإطلاق) يملك مساره في `api.launch_study`، والاكتمال
الطبيعي يكتبه **جسر المحرّك** (`engine_bridge`) عند نجاح التحليل. الحالتان هنا:

- **`complete`** — إغلاق يدوي لدراسة `in_progress` عالقة (مسار طوارئ: خيط مات
  ولم يلتقطه كنس الأيتام بعد، أو قرار صريح بإغلاقها). لا يُرفق تقريراً — دراسة
  أُغلقت يدوياً بلا `analysis_id` تبقى بلا تقرير، معلَناً (409 `no_report_yet`).
- **`archive`** — إخفاء نهائي من القائمة النشطة، من أي حالة غير مؤرشفة.

اقترانُ البريد القديم (رفض الإنهاء مع طابور معلّق، إلغاء المصفوف عند الأرشفة)
حُذف مع التنقيب نهائياً (قرار مالك 2026-08-17) — لا طابور بريد في المنصّة.

عمود `state` ليس في `repository._WRITABLE` عمداً (آلة حالات لا تُكتَب بـCRUD
عام) — فلا سبيل لهذه الانتقالات إلا من هنا. State stays out of generic CRUD.
"""
from __future__ import annotations

import sqlite3

from . import audit, notifications, repository
from .db import now_iso

# الانتقالات المسموحة صراحةً · the explicitly allowed transitions.
COMPLETE_FROM = ("in_progress",)
ARCHIVE_FROM = ("draft", "in_progress", "completed")
TERMINAL = ("archived",)


class LifecycleError(Exception):
    """انتقال مرفوض — carries a machine-readable code for the endpoint."""

    def __init__(self, code: str, message: str, **extra):
        self.code = code
        self.extra = extra
        super().__init__(message)

    def as_detail(self) -> dict:
        return {"error": self.code, "message": str(self), **self.extra}


def _load(conn: sqlite3.Connection, account_id: int, study_id: int) -> dict | None:
    """اقرأ الدراسة عبر طبقة العزل — inherits the owner predicate by construction."""
    return repository.studies(conn).get(account_id, study_id)


def complete_study(conn: sqlite3.Connection, *, account_id: int, study_id: int,
                   actor_user_id: int | None) -> dict | None:
    """أغلق دراسة عالقة يدوياً — in_progress → completed. None if not this tenant's.

    الاكتمال الطبيعي يكتبه جسر المحرّك مع `analysis_id`؛ هذا المسار للطوارئ،
    ولا يختلق تقريراً: دراسة أُغلقت بلا نتيجة تبقى بلا تقرير معلَناً.
    """
    study = _load(conn, account_id, study_id)
    if study is None:
        return None
    conn.commit()                       # اطوِ المعلّق قبل BEGIN الصريح
    conn.execute("BEGIN IMMEDIATE")
    try:
        # أعِد القراءة داخل القفل: الحالة قد تتغيّر بين الفحص والكتابة.
        fresh = _load(conn, account_id, study_id)
        if fresh is None:
            conn.rollback()
            return None
        if fresh["state"] not in COMPLETE_FROM:
            conn.rollback()
            raise LifecycleError(
                "invalid_transition",
                f"cannot complete a study that is {fresh['state']}",
                state=fresh["state"], allowed_from=list(COMPLETE_FROM))
        now = now_iso()
        cur = conn.execute(
            "UPDATE studies SET state = 'completed', completed_at = ?, "
            "updated_at = ? WHERE id = ? AND owner_id = ? AND state = 'in_progress'",
            (now, now, study_id, account_id))
        if cur.rowcount == 0:           # سبقنا طلبٌ متزامن · a concurrent call won
            conn.rollback()
            raise LifecycleError("invalid_transition",
                                 "study is no longer in_progress")
        audit.record(conn, action="study_completed", user_id=actor_user_id,
                     account_id=account_id, resource_type="study",
                     resource_id=study_id, changes={"from": "in_progress",
                                                    "manual_close": True})
        # R3 (تدقيق 2026-09-01، ENG-10/BIZ-5): **كل** انتقالٍ نهائي يُشعِر —
        # هذا المسار (إغلاقٌ يدويّ لدراسة عالقة) كان الوحيد الصامت، فيرى
        # المصنعُ حالةً تغيّرت بلا خبر. ولا اختلاقَ تقرير: صفٌّ بلا
        # `analysis_id` يُعلَن مُغلَقاً بلا تقرير. الإشعار لا يُبطل الحسم
        # (`_safely`: فشلُه قيدُ تدقيق `notification_failed` لا استثناء).
        _aid = fresh.get("analysis_id")
        notifications.notify_study_finish_safely(
            conn, study_id, account_id, kind="study_completed",
            title_fmt="أُغلقت دراسة «{p}» يدوياً",
            body=("التقرير جاهز للعرض والتنزيل من قسم الدراسات." if _aid else
                  "أُغلقت بلا تقرير مُولَّد — لم تُنتج التشغيلة نتيجةً محفوظة."))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return _load(conn, account_id, study_id)


def archive_study(conn: sqlite3.Connection, *, account_id: int, study_id: int,
                  actor_user_id: int | None) -> dict | None:
    """أرشِف دراسة — إخفاء نهائي من أي حالة غير مؤرشفة. None لغير المالك."""
    study = _load(conn, account_id, study_id)
    if study is None:
        return None
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        fresh = _load(conn, account_id, study_id)
        if fresh is None:
            conn.rollback()
            return None
        if fresh["state"] in TERMINAL:
            conn.rollback()
            raise LifecycleError("already_archived",
                                 "study is already archived", state=fresh["state"])
        if fresh["state"] not in ARCHIVE_FROM:
            conn.rollback()
            raise LifecycleError(
                "invalid_transition",
                f"cannot archive a study that is {fresh['state']}",
                state=fresh["state"], allowed_from=list(ARCHIVE_FROM))
        now = now_iso()
        marks = ",".join("?" for _ in ARCHIVE_FROM)
        cur = conn.execute(
            f"UPDATE studies SET state = 'archived', updated_at = ? "
            f"WHERE id = ? AND owner_id = ? AND state IN ({marks})",
            (now, study_id, account_id, *ARCHIVE_FROM))
        if cur.rowcount == 0:
            conn.rollback()
            raise LifecycleError("invalid_transition",
                                 "study state changed concurrently")
        audit.record(conn, action="study_archived", user_id=actor_user_id,
                     account_id=account_id, resource_type="study",
                     resource_id=study_id, changes={"from": fresh["state"]})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return _load(conn, account_id, study_id)
