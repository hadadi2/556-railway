-- 005 — حصّة الدراسات لكل مستخدم (قرار مالك 2026-08-17) · per-user study quota.
--
-- طلب المالك حرفياً: «أريد الأدمِن يحدد مثلاً عدد الدراسات لكل مستخدم بناءً على
-- الباقة أو الاشتراك». الحصّة القائمة على مستوى الحساب وحده (accounts.
-- current_month_study_count)، فلا سبيل لضبط سقفٍ لكل مستخدمٍ داخل الحساب.
--
-- عمودان إضافيان فقط (قاعدة الترحيلات الإضافية — لا صفّ قائم يتغيّر):
--
-- 1) accounts.per_user_monthly_studies — تجاوزُ (override) الأدمِن لهذا الحساب.
--    NULL = لا تجاوز (يسري افتراض الطبقة من models.TierLimits؛ وافتراض كل
--    الطبقات اليوم 0 = «بلا حدٍّ لكل مستخدم» فلا يتغيّر سلوك أي حساب قائم
--    حتى يضبطه الأدمِن بنفسه). 0 = بلا حدّ صراحةً. >=1 = السقف الشهري
--    لكل مستخدم.
--
-- 2) studies.launched_by_user_id — من أطلق الدراسة فعلاً (يُختَم عند مطالبة
--    draft→in_progress ويُمسَح في مسار التعويض إذا رُفض الحجز). العدّ لكل
--    مستخدمٍ يُشتقّ من هذا العمود + launched_at، فلا عدّاد ثانٍ ينحرف عن
--    الحقيقة (نفس مبدأ «الدفتر هو السجلّ» لا عدّاد موازٍ).
--
-- Additive only. NULL account override = tier default (currently 0 = uncapped
-- for every tier, so existing behavior is unchanged until the admin sets it).
ALTER TABLE accounts ADD COLUMN per_user_monthly_studies INTEGER;
ALTER TABLE studies  ADD COLUMN launched_by_user_id INTEGER REFERENCES users(id);
CREATE INDEX IF NOT EXISTS ix_studies_launched_by
    ON studies(launched_by_user_id, launched_at);
