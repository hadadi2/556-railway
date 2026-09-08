-- ترحيل ٠٢٠: فهارسُ أنماط الاستعلام الفعلية — R5 (تدقيق 2026-09-01، DB-7).
--
-- كلُّ فهرسٍ مبرَّر باستعلامٍ حيّ: تنظيفُ الجلسات المنتهية (`auth.cleanup_expired_sessions`
-- على `expires_at`)، وتقليمُ عدّادات الخنق (`throttle.prune` على `created_at` وحده —
-- فهرسُ 002 على `(identity, created_at)` لا يخدم مدىً على التاريخ وحده)، وتنظيفُ رموز
-- إعادة التعيين، وقائمةُ إشعارات الحساب مرتّبةً بالمعرّف، وبحثُ التدقيق بالفعل والزمن.
-- إضافيّ فقط؛ `IF NOT EXISTS` كي تبقى إعادةُ التطبيق حميدة.
CREATE INDEX IF NOT EXISTS ix_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS ix_login_attempts_created ON login_attempts(created_at);
CREATE INDEX IF NOT EXISTS ix_reset_tokens_expires ON password_reset_tokens(expires_at);
CREATE INDEX IF NOT EXISTS ix_notifications_account_id ON platform_notifications(account_id, id);
CREATE INDEX IF NOT EXISTS ix_audit_action_created ON audit_log(action, created_at);
