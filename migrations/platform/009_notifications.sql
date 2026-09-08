-- 009 — إشعارات داخل المنصّة · in-platform notifications (قرار المالك 2026-08-18).
--
-- «اضف نظام الاشعارات عند الانتهاء من الدارسة»: مع توصيل الدراسات بمحرّك
-- البحث العميق (~١٥ دقيقة للتشغيلة) صار الاكتمال حدثاً يستحق تبليغاً — يكتبه
-- جسر المحرّك في نفس معاملة إنهاء التشغيلة (نجاحاً أو فشلاً معلَناً)، وتقرؤه
-- الواجهة عبر GET /platform/notifications (جرس + إشعار متصفح).
--
-- الاسم `platform_notifications` عمداً — حارس حذف المحور يمنع إحياء وحدةٍ/جدولٍ
-- باسم `email_queue`؛ هذا سجلّ أحداث داخل المنصّة لا طابور بريد.
-- إضافي فقط — لا مساس بأي صف قائم. Additive only.
CREATE TABLE IF NOT EXISTS platform_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    user_id INTEGER REFERENCES users(id),          -- NULL = لكل مستخدمي الحساب
    kind TEXT NOT NULL,                            -- study_completed | study_failed | ...
    study_id INTEGER,                              -- مرجع اختياري للدراسة
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    read_at TEXT                                   -- NULL = غير مقروء
);
CREATE INDEX IF NOT EXISTS idx_platform_notifications_account
    ON platform_notifications(account_id, read_at, id);
